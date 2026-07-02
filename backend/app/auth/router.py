from datetime import timedelta, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Response
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr
from app.models.schemas import (
    UserRegister, UserLogin, Token, UserOut,
    ForgotPasswordRequest, ResetPasswordRequest,
    PasswordResetResponse
)
from app.auth.models import DBManager
from app.auth.utils import (
    get_password_hash, verify_password, create_access_token, get_current_user, get_current_admin_user,
    generate_verification_token
)
from app.config import settings
from app.services.email_service import EmailService

router = APIRouter(prefix="/auth", tags=["auth"])

class ResendVerificationRequest(BaseModel):
    email: EmailStr

@router.post("/register")
async def register(user_data: UserRegister, response: Response):
    """Register a new user"""
    # Check if user already exists
    existing_user = DBManager.get_user_by_email(user_data.email)
    if existing_user:
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
    EmailService.send_verification_email(
        email=user_data.email,
        full_name=user_data.full_name,
        verification_link=verification_link
    )
    
    return {"message": "Registration successful. Please check your email to verify your account."}


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, response: Response):
    """Login with email and password"""
    user = DBManager.get_user_by_email(credentials.email)
    if not user or not verify_password(credentials.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not user.get("email_verified"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before logging in."
        )
    
    token_data = {"user_id": user["id"], "email": user["email"]}
    access_token = create_access_token(data=token_data)
    
    # Set httpOnly cookie
    response.set_cookie(
        key="authorization",
        value=f"Bearer {access_token}",
        httponly=True,
        secure=settings.ENVIRONMENT == "production",  # HTTPS only in prod
        samesite="strict",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # Align with access token expiry (30 days)
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
async def logout(response: Response):
    """
    Logout endpoint. Clears httpOnly cookie.
    """
    response.delete_cookie(
        key="authorization",
        secure=settings.ENVIRONMENT == "production",
        samesite="strict"
    )
    return {"message": "Logged out successfully"}

@router.get("/me", response_model=UserOut)
async def read_users_me(current_user: dict = Depends(get_current_user)):
    """Get current user profile"""
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "full_name": current_user["full_name"],
        "created_at": current_user["created_at"]
    }


@router.post("/forgot-password", response_model=dict)
async def forgot_password(request: ForgotPasswordRequest):
    """Request a password reset link for the user."""
    user = DBManager.get_user_by_email(request.email)
    if user:
        reset_token = create_access_token(
            data={"user_id": user["id"], "action": "reset_password"},
            expires_delta=timedelta(minutes=settings.PASSWORD_RESET_EXPIRY_MINUTES),
        )
        EmailService.send_password_reset_email(
            email=request.email,
            full_name=user.get("full_name", "User"),
            reset_link=f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        )
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/reset-password", response_model=PasswordResetResponse)
async def reset_password(request: ResetPasswordRequest):
    """Reset password using a one-time token."""
    try:
        payload = jwt.decode(request.token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("user_id")
        action = payload.get("action")
        if user_id is None or action != "reset_password":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token.")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expired or invalid reset token.")

    hashed_password = get_password_hash(request.password)
    DBManager.update_password(user_id, hashed_password)
    return {"message": "Password reset successfully! You can now log in with your new password.", "success": True}


@router.get("/verify-email/{token}")
async def verify_email(token: str):
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
    return {"verified": True, "message": "Email verified successfully!"}

@router.post("/resend-verification")
async def resend_verification(request: ResendVerificationRequest):
    """Resend email verification token"""
    user = DBManager.get_user_by_email(request.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    if user.get("email_verified"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified"
        )
        
    # Generate new token
    token = generate_verification_token()
    expiry = datetime.now(timezone.utc) + timedelta(hours=24)
    DBManager.set_verification_token(user["id"], token, expiry)
    
    verification_link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    EmailService.send_verification_email(
        email=user["email"],
        full_name=user["full_name"],
        verification_link=verification_link
    )
    
    return {"message": "Verification email sent successfully."}


@router.get("/admin/stats")
async def get_admin_stats(current_user: dict = Depends(get_current_admin_user)):
    return DBManager.get_admin_metrics()


