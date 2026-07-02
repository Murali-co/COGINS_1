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
        async with httpx.AsyncClient(timeout=3.0) as client:
            url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
            response = await client.get(url)
            # Ollama tags returns 200 with model list
            if response.status_code not in [200, 204, 404]:
                ollama_status = f"unhealthy: status code {response.status_code}"
    except Exception as e:
        ollama_status = f"unhealthy: {str(e)}"
        
    overall_status = "healthy"
    if "unhealthy" in sqlite_status or "unhealthy" in chroma_status or "unhealthy" in ollama_status:
        overall_status = "degraded"
        
    return {
        "status": overall_status,
        "sqlite": sqlite_status,
        "chromadb": chroma_status,
        "ollama": ollama_status
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
            "profile/", "llm/", "feedback/", "analytics/", "health"
        ]):
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Not Found"})
            
        static_file = os.path.join("static", catchall)
        if os.path.exists(static_file) and os.path.isfile(static_file):
            return FileResponse(static_file)
            
        index_path = os.path.join("static", "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
            
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Frontend assets not found."})


