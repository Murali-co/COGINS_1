import secrets
import hashlib
import pyotp
from datetime import timedelta, datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Query, Body
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr
from app.models.schemas import (
    UserRegister, UserLogin, Token, UserOut,
    ForgotPasswordRequest, ResetPasswordRequest,
    PasswordResetResponse,
    TwoFactorConfirmRequest, TwoFactorDisableRequest, TwoFactorVerifyRequest
)
from app.auth.models import DBManager
from app.auth.utils import (
    get_password_hash, verify_password, create_access_token, get_current_user, get_current_admin_user,
    generate_verification_token, generate_refresh_token, hash_refresh_token, generate_csrf_token
)
from app.config import settings
from app.services.email_service import EmailService
from app.utils.limiter import limiter

router = APIRouter(prefix="/auth", tags=["auth"])

class ResendVerificationRequest(BaseModel):
    email: EmailStr


def issue_tokens_and_set_cookies(user_id: int, user_email: str, request: Request, response: Response) -> tuple:
    """Helper to generate access token, opaque refresh token, and CSRF token and set secure cookies."""
    token_data = {"user_id": user_id, "email": user_email}
    access_token = create_access_token(data=token_data)
    
    raw_refresh_token = generate_refresh_token()
    token_hash = hash_refresh_token(raw_refresh_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    
    DBManager.create_refresh_token(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        user_agent=user_agent,
        ip_address=ip_address
    )
    
    csrf_tok = generate_csrf_token()
    
    # Set authorization cookie (15 min)
    response.set_cookie(
        key="authorization",
        value=f"Bearer {access_token}",
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="strict",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/"
    )
    
    # Set refresh_token cookie (30 days)
    response.set_cookie(
        key="refresh_token",
        value=raw_refresh_token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/"
    )
    
    # Set csrf_token cookie (non-httpOnly for JS header echo)
    response.set_cookie(
        key="csrf_token",
        value=csrf_tok,
        httponly=False,
        secure=settings.ENVIRONMENT == "production",
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/"
    )
    
    return access_token, raw_refresh_token, csrf_tok


@router.post("/register")
@limiter.limit("5/hour")
async def register(user_data: UserRegister, request: Request):
    """Register a new user"""
    ip_addr = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    # Check if user already exists
    existing_user = DBManager.get_user_by_email(user_data.email)
    if existing_user:
        DBManager.log_auth_event("login_failed", ip_address=ip_addr, user_agent=ua, detail="Registration failed: email already registered")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    hashed_password = get_password_hash(user_data.password)
    user_id = DBManager.create_user(
        email=user_data.email,
        hashed_pw=hashed_password,
        full_name=user_data.full_name
    )
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error registering user"
        )
    
    # Generate email verification token
    token = generate_verification_token()
    expiry = datetime.now(timezone.utc) + timedelta(hours=24)
    DBManager.set_verification_token(user_id, token, expiry)
    
    # Send verification email
    verification_link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    email_sent = EmailService.send_verification_email(
        email=user_data.email,
        full_name=user_data.full_name,
        verification_link=verification_link
    )

    DBManager.log_auth_event("user_registered", user_id=user_id, ip_address=ip_addr, user_agent=ua, detail="User registered successfully")

    response_payload = {
        "message": "Registration successful. Please verify your email before logging in.",
        "email_sent": email_sent,
    }

    is_non_prod = settings.ENVIRONMENT.lower() not in {"production", "prod"}
    if not email_sent and is_non_prod:
        response_payload["verification_link"] = verification_link

    return response_payload


@router.post("/login", response_model=Token)
@limiter.limit("8/minute")
async def login(credentials: UserLogin, request: Request, response: Response):
    """Login with email and password"""
    ip_addr = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    email = credentials.email.strip().lower()

    # Lockout check: 8 failed login attempts in last 15 mins for this target email
    failed_attempts = DBManager.count_recent_failed_logins(email, minutes=15)
    if failed_attempts >= 8:
        DBManager.log_auth_event("account_locked", user_id=None, ip_address=ip_addr, user_agent=ua, detail=f"Account locked due to {failed_attempts} failed attempts for {email}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account temporarily locked due to multiple failed login attempts. Please try again in 15 minutes."
        )

    user = DBManager.get_user_by_email(credentials.email)
    if not user or not verify_password(credentials.password, user["hashed_password"]):
        DBManager.log_auth_event("login_failed", user_id=user["id"] if user else None, ip_address=ip_addr, user_agent=ua, detail=f"Incorrect email or password for {email}")
        new_failed_count = DBManager.count_recent_failed_logins(email, minutes=15)
        if new_failed_count >= 8:
            DBManager.log_auth_event("account_locked", user_id=user["id"] if user else None, ip_address=ip_addr, user_agent=ua, detail=f"Account locked following failed login for {email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not user.get("email_verified"):
        is_test_or_dev = settings.ENVIRONMENT.lower() in {"development", "test", "testing"}
        has_pending_verification = bool(user.get("verification_token"))
        if not is_test_or_dev or not has_pending_verification:
            DBManager.log_auth_event("login_failed", user_id=user["id"], ip_address=ip_addr, user_agent=ua, detail=f"Unverified email login attempt for {email}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Please verify your email address before logging in."
            )
    
    if user.get("two_factor_enabled"):
        pending_token = create_access_token(
            data={"user_id": user["id"], "email": user["email"], "purpose": "2fa_pending"},
            expires_delta=timedelta(minutes=5)
        )
        DBManager.log_auth_event("2fa_challenge_issued", user_id=user["id"], ip_address=ip_addr, user_agent=ua, detail=f"2FA verification required for {email}")
        return {
            "access_token": "",
            "token_type": "bearer",
            "requires_2fa": True,
            "pending_token": pending_token
        }

    access_token, raw_refresh, csrf_tok = issue_tokens_and_set_cookies(user["id"], user["email"], request, response)
    DBManager.log_auth_event("login_success", user_id=user["id"], ip_address=ip_addr, user_agent=ua, detail="Login successful")
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/refresh", response_model=Token)
@limiter.limit("60/minute")
async def refresh(request: Request, response: Response):
    """
    Refresh access token using opaque refresh token cookie.
    Implements token rotation and replay detection.
    """
    raw_refresh_token = request.cookies.get("refresh_token")
    if not raw_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token cookie missing"
        )
    
    token_hash = hash_refresh_token(raw_refresh_token)
    record = DBManager.get_refresh_token_by_hash(token_hash)
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    # REPLAY ATTACK DETECTION: Token was already revoked
    if record.get("revoked_at") is not None:
        user_id = record["user_id"]
        DBManager.revoke_all_user_refresh_tokens(user_id)
        response.delete_cookie("refresh_token", path="/")
        response.delete_cookie("authorization", path="/")
        response.delete_cookie("csrf_token", path="/")
        DBManager.log_auth_event("login_failed", user_id=user_id, ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"), detail="Replay attack detected: revoked refresh token reused")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected. All sessions revoked."
        )
        
    # EXPIRY CHECK
    expires_at = record.get("expires_at")
    if isinstance(expires_at, str):
        val = expires_at.replace(" ", "T")
        try:
            if "+" in val or "-" in val.split("T")[-1]:
                expires_at_dt = datetime.fromisoformat(val)
            else:
                expires_at_dt = datetime.fromisoformat(val).replace(tzinfo=timezone.utc)
        except Exception:
            expires_at_dt = datetime.now(timezone.utc) - timedelta(seconds=1)
    else:
        expires_at_dt = expires_at
        if expires_at_dt and expires_at_dt.tzinfo is None:
            expires_at_dt = expires_at_dt.replace(tzinfo=timezone.utc)

    if not expires_at_dt or datetime.now(timezone.utc) > expires_at_dt:
        DBManager.revoke_refresh_token(token_hash)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired"
        )
        
    user = DBManager.get_user_by_id(record["user_id"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with refresh token not found"
        )
        
    # ROTATION: Revoke current refresh token row
    DBManager.revoke_refresh_token(token_hash)
    
    # Issue new refresh token & access token & CSRF token
    access_token, new_raw_refresh, new_csrf = issue_tokens_and_set_cookies(user["id"], user["email"], request, response)
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
async def logout(request: Request, response: Response):
    """
    Logout endpoint. Revokes refresh token in database and clears cookies.
    """
    raw_refresh_token = request.cookies.get("refresh_token")
    if raw_refresh_token:
        token_hash = hash_refresh_token(raw_refresh_token)
        DBManager.revoke_refresh_token(token_hash)
        
    response.delete_cookie(key="authorization", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    response.delete_cookie(key="csrf_token", path="/")
    return {"message": "Logged out successfully"}


@router.get("/sessions")
@limiter.limit("60/minute")
async def list_sessions(request: Request, current_user: dict = Depends(get_current_user)):
    """
    List user's active, non-revoked refresh token sessions.
    Includes is_current flag comparing token_hash to request refresh token.
    """
    raw_refresh = request.cookies.get("refresh_token")
    current_hash = hash_refresh_token(raw_refresh) if raw_refresh else None

    sessions = DBManager.get_active_user_sessions(current_user["id"])
    return [
        {
            "id": s["id"],
            "created_at": s["created_at"],
            "expires_at": s["expires_at"],
            "user_agent": s.get("user_agent"),
            "ip_address": s.get("ip_address"),
            "is_current": (s["token_hash"] == current_hash) if current_hash else False,
        }
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
@limiter.limit("60/minute")
async def revoke_session(session_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    """
    Revoke a specific session by ID ("log out other devices").
    Disallows revoking current session from this endpoint (force /logout for current session).
    """
    raw_refresh = request.cookies.get("refresh_token")
    current_hash = hash_refresh_token(raw_refresh) if raw_refresh else None

    target_session = DBManager.get_refresh_token_by_id(session_id)
    if target_session and target_session.get("token_hash") == current_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke your current session from this endpoint. Please use /auth/logout instead."
        )

    revoked = DBManager.revoke_session_by_id(session_id, current_user["id"])
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or already revoked"
        )
    return {"message": "Session revoked successfully"}


@router.post("/sessions/revoke-others")
@limiter.limit("30/minute")
async def revoke_other_sessions(request: Request, current_user: dict = Depends(get_current_user)):
    """
    Revoke all active sessions for current user EXCEPT the current session.
    """
    raw_refresh = request.cookies.get("refresh_token")
    current_hash = hash_refresh_token(raw_refresh) if raw_refresh else None

    count = DBManager.revoke_other_user_sessions(current_user["id"], current_hash)
    DBManager.log_auth_event(
        "sessions_revoked",
        user_id=current_user["id"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        detail=f"Revoked {count} other active sessions"
    )
    return {"message": f"Successfully logged out {count} other device(s).", "revoked_count": count}


@router.get("/me", response_model=UserOut)
async def read_users_me(current_user: dict = Depends(get_current_user)):
    """Get current user profile"""
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "full_name": current_user["full_name"],
        "created_at": current_user["created_at"],
        "two_factor_enabled": current_user.get("two_factor_enabled", False),
        "auto_approve_external_actions": current_user.get("auto_approve_external_actions", False),
        "is_admin": current_user.get("is_admin", False),
    }


@router.post("/forgot-password", response_model=dict)
@limiter.limit("3/hour")
async def forgot_password(request: Request, body: ForgotPasswordRequest):
    """Request a password reset link for the user."""
    ip_addr = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    user = DBManager.get_user_by_email(body.email)
    if user:
        expiry = datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_EXPIRY_MINUTES)
        reset_token = create_access_token(
            data={"user_id": user["id"], "action": "reset_password"},
            expires_delta=timedelta(minutes=settings.PASSWORD_RESET_EXPIRY_MINUTES),
        )
        DBManager.set_reset_password_token(user["id"], reset_token, expiry)

        EmailService.send_password_reset_email(
            email=body.email,
            full_name=user.get("full_name", "User"),
            reset_link=f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        )
        DBManager.log_auth_event("password_reset_requested", user_id=user["id"], ip_address=ip_addr, user_agent=ua, detail=f"Reset requested for {body.email}")
    else:
        DBManager.log_auth_event("password_reset_requested", user_id=None, ip_address=ip_addr, user_agent=ua, detail=f"Reset requested for unknown email {body.email}")

    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/reset-password", response_model=PasswordResetResponse)
async def reset_password(request: ResetPasswordRequest, req: Request):
    """Reset password using a one-time token."""
    ip_addr = req.client.host if req.client else None
    ua = req.headers.get("user-agent")

    try:
        payload = jwt.decode(request.token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("user_id")
        action = payload.get("action")
        if user_id is None or action != "reset_password":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token.")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expired or invalid reset token.")

    # SINGLE-USE ENFORCEMENT: Check reset token matches user database record
    user = DBManager.get_user_by_id(user_id)
    if not user or user.get("reset_password_token") != request.token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has already been used or is invalid."
        )

    expiry = user.get("reset_password_token_expiry")
    if expiry:
        expiry_dt = None
        if isinstance(expiry, str):
            val = expiry.replace(" ", "T")
            try:
                if "+" in val or "-" in val.split("T")[-1]:
                    expiry_dt = datetime.fromisoformat(val)
                else:
                    expiry_dt = datetime.fromisoformat(val).replace(tzinfo=timezone.utc)
            except Exception:
                expiry_dt = None
        else:
            expiry_dt = expiry
            if expiry_dt and expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)

        if expiry_dt and datetime.now(timezone.utc) > expiry_dt:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset token has expired.")

    hashed_password = get_password_hash(request.password)
    DBManager.reset_password(user_id, hashed_password)
    DBManager.log_auth_event("password_reset_completed", user_id=user_id, ip_address=ip_addr, user_agent=ua, detail="Password reset successfully")

    return {"message": "Password reset successfully! You can now log in with your new password.", "success": True}


@router.get("/verify-email/{token}")
async def verify_email(token: str, request: Request, response: Response):
    """Verify email address with token"""
    user = DBManager.get_user_by_verification_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )
        
    # Check expiry
    expiry = user.get("verification_token_expiry")
    if expiry:
        expiry_dt = None
        if isinstance(expiry, str):
            val = expiry.replace(" ", "T")
            try:
                if "+" in val or "-" in val.split("T")[-1]:
                    expiry_dt = datetime.fromisoformat(val)
                else:
                    expiry_dt = datetime.fromisoformat(val).replace(tzinfo=timezone.utc)
            except Exception:
                for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        expiry_dt = datetime.strptime(expiry, fmt).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue
        else:
            expiry_dt = expiry
            if expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                
        if expiry_dt and datetime.now(timezone.utc) > expiry_dt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification token has expired"
            )
            
    DBManager.verify_email(user["id"])
    access_token, raw_refresh, csrf_tok = issue_tokens_and_set_cookies(user["id"], user["email"], request, response)
    DBManager.log_auth_event("login_success", user_id=user["id"], ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"), detail="Email verified and logged in")
    return {
        "verified": True,
        "message": "Email verified successfully!",
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.post("/resend-verification")
@limiter.limit("3/hour")
async def resend_verification(request: Request, body: ResendVerificationRequest):
    """Resend email verification token"""
    user = DBManager.get_user_by_email(body.email)
    if user and not user.get("email_verified"):
        token = generate_verification_token()
        expiry = datetime.now(timezone.utc) + timedelta(hours=24)
        DBManager.set_verification_token(user["id"], token, expiry)
        
        verification_link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        EmailService.send_verification_email(
            email=user["email"],
            full_name=user["full_name"],
            verification_link=verification_link
        )
        
    return {"message": "If that account exists and needs verification, an email has been sent."}


@router.get("/admin/stats")
async def get_admin_stats(req: Request, current_user: dict = Depends(get_current_admin_user)):
    ip_addr = req.client.host if req.client else None
    ua = req.headers.get("user-agent")
    DBManager.log_auth_event("admin_action", user_id=current_user["id"], ip_address=ip_addr, user_agent=ua, detail="Accessed admin stats")
    return DBManager.get_admin_metrics()


@router.get("/admin/audit-log")
@limiter.limit("60/minute")
async def get_admin_audit_log(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    event_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_admin_user)
):
    """Admin-only audit log endpoint with filtering and pagination"""
    ip_addr = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    DBManager.log_auth_event("admin_action", user_id=current_user["id"], ip_address=ip_addr, user_agent=ua, detail="Accessed admin audit log")

    return DBManager.get_admin_audit_logs(
        page=page,
        per_page=per_page,
        event_type=event_type,
        start_date=start_date,
        end_date=end_date
    )


# ===== 2FA ENDPOINTS =====
@router.post("/2fa/setup")
@limiter.limit("10/minute")
async def setup_2fa(request: Request, current_user: dict = Depends(get_current_user)):
    """Generate TOTP secret and otpauth URL for 2FA setup"""
    if current_user.get("two_factor_enabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is already enabled on this account.")
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    otpauth_url = totp.provisioning_uri(name=current_user["email"], issuer_name="COGNIS")
    return {
        "secret": secret,
        "otpauth_url": otpauth_url
    }


@router.post("/2fa/confirm")
@limiter.limit("10/minute")
async def confirm_2fa(body: TwoFactorConfirmRequest, request: Request, current_user: dict = Depends(get_current_user)):
    """Verify setup code, enable 2FA, and generate 10 single-use backup codes"""
    totp = pyotp.TOTP(body.secret)
    if not totp.verify(body.code.strip()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")

    # Generate 10 random 8-character backup codes
    backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]
    code_hashes = [hashlib.sha256(bc.encode("utf-8")).hexdigest() for bc in backup_codes]

    DBManager.set_user_2fa_secret(current_user["id"], secret=body.secret, enabled=True)
    DBManager.save_user_backup_codes(current_user["id"], code_hashes)
    DBManager.log_auth_event("2fa_enabled", user_id=current_user["id"], ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"), detail="2FA enabled successfully")

    return {
        "message": "Two-factor authentication enabled successfully. Store your backup codes safely.",
        "backup_codes": backup_codes
    }


@router.post("/2fa/disable")
@limiter.limit("10/minute")
async def disable_2fa(body: TwoFactorDisableRequest, request: Request, current_user: dict = Depends(get_current_user)):
    """Disable 2FA after verifying current user password"""
    if not verify_password(body.password, current_user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect password.")

    DBManager.set_user_2fa_secret(current_user["id"], secret=None, enabled=False)
    DBManager.save_user_backup_codes(current_user["id"], [])
    DBManager.log_auth_event("2fa_disabled", user_id=current_user["id"], ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"), detail="2FA disabled successfully")

    return {"message": "Two-factor authentication disabled successfully."}


@router.post("/2fa/backup-codes/regenerate")
@limiter.limit("5/minute")
async def regenerate_backup_codes(request: Request, current_user: dict = Depends(get_current_user)):
    """Regenerate 10 new backup codes for 2FA-enabled user"""
    if not current_user.get("two_factor_enabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA must be enabled to generate backup codes.")

    backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]
    code_hashes = [hashlib.sha256(bc.encode("utf-8")).hexdigest() for bc in backup_codes]
    DBManager.save_user_backup_codes(current_user["id"], code_hashes)
    DBManager.log_auth_event("2fa_backup_codes_regenerated", user_id=current_user["id"], ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"), detail="2FA backup codes regenerated")

    return {"backup_codes": backup_codes}


@router.post("/2fa/verify", response_model=Token)
@limiter.limit("10/minute")
async def verify_2fa(body: TwoFactorVerifyRequest, request: Request, response: Response):
    """Verify 2FA TOTP code or backup code after login challenge"""
    ip_addr = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        payload = jwt.decode(body.pending_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("user_id")
        purpose = payload.get("purpose")
        if user_id is None or purpose != "2fa_pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid 2FA session token.")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA verification session expired. Please log in again.")

    user = DBManager.get_user_by_id(user_id)
    if not user or not user.get("two_factor_enabled") or not user.get("two_factor_secret"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is not enabled for this user.")

    clean_code = body.code.strip()
    totp = pyotp.TOTP(user["two_factor_secret"])
    is_valid = totp.verify(clean_code)

    if not is_valid:
        # Fallback check: try backup code
        is_valid = DBManager.verify_and_consume_backup_code(user_id, clean_code)

    if not is_valid:
        DBManager.log_auth_event("login_failed", user_id=user_id, ip_address=ip_addr, user_agent=ua, detail="Invalid 2FA verification code")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid 2FA code or backup code.")

    access_token, raw_refresh, csrf_tok = issue_tokens_and_set_cookies(user["id"], user["email"], request, response)
    DBManager.log_auth_event("login_success", user_id=user["id"], ip_address=ip_addr, user_agent=ua, detail="2FA login successful")

    return {"access_token": access_token, "token_type": "bearer"}


@router.patch("/preferences/auto-approve-external")
async def update_auto_approve_preference(
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Toggle auto_approve_external_actions preference for current user."""
    auto_approve = bool(payload.get("auto_approve_external_actions", False))
    DBManager.update_auto_approve_external_actions(current_user["id"], auto_approve)
    DBManager.log_auth_event(
        user_id=current_user["id"],
        event_type="user_preference_updated",
        detail=f"Updated auto_approve_external_actions to {auto_approve}"
    )
    return {
        "status": "success",
        "auto_approve_external_actions": auto_approve
    }



