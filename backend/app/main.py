from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Initialize database schema BEFORE importing any routers
from app.auth.models import ensure_user_admin_column
ensure_user_admin_column()
print("✅ Database schema verified/migrated at startup")

from app.config import settings
from app.auth.router import router as auth_router
from app.resume.router import router as resume_router
from app.jobs.router import router as jobs_router
from app.jobs.saved_router import router as saved_jobs_router
from app.applications.router import router as apply_router
from app.rag.router import router as rag_router
from app.copilot.router import router as copilot_router
from app.interview.router import router as interview_router
from app.market.router import router as market_router
from app.notifications.router import router as notifications_router
from app.settings.router import router as settings_router
from app.profile.router import router as profile_router
from app.llm.router import router as llm_router
from app.feedback.router import router as feedback_router
from app.analytics.router import router as analytics_router
from app.orchestrator.router import router as orchestrator_router
from app.jobs.scheduler import start_scheduler, shutdown_scheduler

# Optional: RateLimit handling (only if slowapi is installed)
try:
    from slowapi.errors import RateLimitExceeded  # type: ignore
    from slowapi import _rate_limit_exceeded_handler  # type: ignore
    SLOWAPI_AVAILABLE = True
except ImportError:
    SLOWAPI_AVAILABLE = False
    RateLimitExceeded = None
    _rate_limit_exceeded_handler = None

# Import limiter (also optional)
try:
    from app.utils.limiter import limiter
    LIMITER_AVAILABLE = True
except ImportError:
    LIMITER_AVAILABLE = False
    limiter = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage app lifecycle: startup and shutdown events.
    Uses modern FastAPI lifespan pattern instead of deprecated @app.on_event.
    """
    # Startup
    print("COGNIS Backend starting up...")
    try:
        start_scheduler()
        print("Job scheduler started successfully.")
    except Exception as e:
        print(f"Warning: Failed to start scheduler on startup: {e}")
    
    yield
    
    # Shutdown
    print("COGNIS Backend shutting down...")
    try:
        shutdown_scheduler()
        print("Job scheduler shut down successfully.")
    except Exception as e:
        print(f"Warning: Failed to shut down scheduler: {e}")


app = FastAPI(
    title="COGNIS API",
    description="Local AI Career Copilot Backend Service",
    version="1.0.0",
    lifespan=lifespan
)

# Add rate limiting if available
if LIMITER_AVAILABLE and limiter:
    app.state.limiter = limiter
    if SLOWAPI_AVAILABLE and RateLimitExceeded and _rate_limit_exceeded_handler:
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

import hmac

EXEMPT_CSRF_PATHS = {
    "/auth/login", "/auth/register", "/auth/refresh",
    "/auth/forgot-password", "/auth/reset-password", "/auth/resend-verification",
    "/auth/2fa/verify",
    "/health", "/", "/docs", "/openapi.json", "/redoc"
}

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # 1. Double-submit CSRF Protection for state-changing HTTP methods
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        path = request.url.path.rstrip("/") or "/"
        if path not in EXEMPT_CSRF_PATHS and not any(path.startswith(p) for p in ["/docs", "/openapi.json"]):
            csrf_cookie = request.cookies.get("csrf_token")
            csrf_header = request.headers.get("x-csrf-token") or request.headers.get("X-CSRF-Token")
            if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header):
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "CSRF token validation failed"}
                )

    response = await call_next(request)

    # 2. Security Headers
    if settings.ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    ollama_origin = settings.OLLAMA_BASE_URL.rstrip("/")
    frontend_origin = settings.FRONTEND_URL.rstrip("/")
    csp_policy = (
        f"default-src 'self'; "
        f"connect-src 'self' {ollama_origin} {frontend_origin}; "
        f"img-src 'self' data:; "
        f"script-src 'self' 'unsafe-inline'; "
        f"style-src 'self' 'unsafe-inline'"
    )
    response.headers["Content-Security-Policy"] = csp_policy

    return response


# CORS Middleware Setup
origins = [org.strip() for org in settings.CORS_ORIGINS.split(",") if org.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(auth_router)
app.include_router(resume_router)
app.include_router(jobs_router)
app.include_router(saved_jobs_router)
app.include_router(apply_router)
app.include_router(rag_router)
app.include_router(copilot_router)
app.include_router(interview_router)
app.include_router(market_router)
app.include_router(notifications_router)
app.include_router(settings_router)
app.include_router(profile_router)
app.include_router(llm_router)
app.include_router(feedback_router)
app.include_router(analytics_router)
app.include_router(orchestrator_router)

# Secure Global Exception Handler to prevent stack trace leakage to client
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log the full traceback internally for developer diagnostics
    import traceback
    print(f"CRITICAL ERROR on {request.method} {request.url}:")
    traceback.print_exc()
    
    if settings.DEBUG:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": str(exc),
                "traceback": traceback.format_exc()
            }
        )
    
    # Return a generic safe message to client
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please contact administrator."}
    )

@app.get("/")
async def root_health_check():
    return {"status": "healthy", "service": "COGNIS — Local AI Career Copilot"}

@app.get("/health")
async def detailed_health_check():
    import httpx
    
    # 1. Check PostgreSQL
    sqlite_status = "healthy"
    try:
        # attempt a simple connection test using SQLAlchemy engine
        from sqlalchemy import text
        from app.db.session import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        sqlite_status = f"unhealthy: {str(e)}"
        
    # 2. Check ChromaDB
    chroma_status = "healthy"
    try:
        from app.vector_db.chroma_client import ChromaDBClient
        client = ChromaDBClient.get_client()
        client.list_collections()
    except Exception as e:
        chroma_status = f"unhealthy: {str(e)}"
        
    # 3. Check Ollama
    ollama_status = "healthy"
    try:
        print(f"[HealthCheck] Testing Ollama connection to URL: {settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags")
        async with httpx.AsyncClient(timeout=3.0) as client:
            url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
            response = await client.get(url)
            # Ollama tags returns 200 with model list
            if response.status_code not in [200, 204, 404]:
                ollama_status = f"unhealthy: status code {response.status_code}"
                print(f"[HealthCheck] Ollama returned non-success code: {response.status_code}")
    except Exception as e:
        import traceback
        print("[HealthCheck] Ollama check failed with exception:")
        traceback.print_exc()
        ollama_status = f"unhealthy: {type(e).__name__}: {str(e)}"
        
    overall_status = "healthy"
    if "unhealthy" in sqlite_status or "unhealthy" in chroma_status or "unhealthy" in ollama_status:
        overall_status = "degraded"
        
    return {
        "status": overall_status,
        "sqlite": sqlite_status,
        "chromadb": chroma_status,
        "ollama": ollama_status
    }


@app.get("/api/health/ollama")
async def ollama_health_detail():
    """
    Detailed Ollama health endpoint that also reports whether the configured model is available.
    """
    import httpx
    models = []
    reachable = False
    model_available = False
    details = ""
    try:
        url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
        print(f"[OllamaHealth] querying {url}")
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            reachable = resp.status_code == 200
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("model") or m.get("name") for m in data.get("models", [])]
                model_available = settings.OLLAMA_MODEL in models
            else:
                details = f"unexpected status {resp.status_code}"
    except Exception as e:
        import traceback
        traceback.print_exc()
        details = f"{type(e).__name__}: {str(e)}"

    return {
        "ollama_reachable": reachable,
        "configured_model": settings.OLLAMA_MODEL,
        "model_available": model_available,
        "available_models": models,
        "details": details,
    }


# Optional SPA Frontend Serving
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

if os.environ.get("SERVE_STATIC_FRONTEND") == "true" or os.path.exists("static"):
    @app.get("/{catchall:path}", include_in_schema=False)
    async def serve_react_app(catchall: str):
        # Exclude API endpoints from routing to React app index
        if any(catchall.startswith(prefix) for prefix in [
            "auth/", "resume/", "jobs/", "apply/", "rag/", "copilot/", 
            "interview/", "market/", "notifications/", "settings/", 
            "profile/", "llm/", "feedback/", "analytics/", "orchestrator/", "health"
        ]):
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Not Found"})
            
        static_file = os.path.join("static", catchall)
        if os.path.exists(static_file) and os.path.isfile(static_file):
            return FileResponse(static_file)
            
        index_path = os.path.join("static", "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
            
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Frontend assets not found."})


