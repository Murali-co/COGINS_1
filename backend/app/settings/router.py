from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.auth.utils import get_current_user
from app.auth.models import DBManager

router = APIRouter(prefix="/settings", tags=["settings"])

class UserSettingsUpdate(BaseModel):
    full_name: str = None
    email_notifications: bool = None
    daily_digest: bool = None
    scrape_frequency_hours: int = None

class UserSettingsResponse(BaseModel):
    id: int
    email: str
    full_name: str
    email_notifications: bool = True
    daily_digest: bool = True
    scrape_frequency_hours: int = 12

    class Config:
        from_attributes = True

@router.get("/profile", response_model=UserSettingsResponse)
async def get_settings(current_user: dict = Depends(get_current_user)):
    """Get current user settings"""
    user = DBManager.get_user_by_id(current_user["id"])
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "email_notifications": user.get("email_notifications", True),
        "daily_digest": user.get("daily_digest", True),
        "scrape_frequency_hours": user.get("scrape_frequency_hours", 12)
    }

@router.patch("/profile")
async def update_settings(
    updates: UserSettingsUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update user settings"""
    try:
        user_id = current_user["id"]
        
        if updates.full_name:
            DBManager.update_user_full_name(user_id, updates.full_name)
        
        if updates.email_notifications is not None:
            DBManager.update_user_preference(user_id, "email_notifications", updates.email_notifications)
        
        if updates.daily_digest is not None:
            DBManager.update_user_preference(user_id, "daily_digest", updates.daily_digest)
        
        if updates.scrape_frequency_hours is not None:
            if updates.scrape_frequency_hours < 1 or updates.scrape_frequency_hours > 168:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Scrape frequency must be between 1 and 168 hours"
                )
            DBManager.update_user_preference(user_id, "scrape_frequency_hours", updates.scrape_frequency_hours)
        
        return {
            "message": "Settings updated successfully",
            "user": {
                "id": user_id,
                "full_name": updates.full_name or current_user["full_name"],
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update settings: {str(e)}"
        )

@router.post("/preferences/notification-frequency")
async def set_notification_frequency(
    enabled: bool,
    current_user: dict = Depends(get_current_user)
):
    """Enable/disable email notifications"""
    DBManager.update_user_preference(current_user["id"], "email_notifications", enabled)
    return {"message": f"Email notifications {'enabled' if enabled else 'disabled'}"}

@router.post("/preferences/scrape-frequency")
async def set_scrape_frequency(
    hours: int,
    current_user: dict = Depends(get_current_user)
):
    """Set job scraping frequency (hours)"""
    if hours < 1 or hours > 168:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Frequency must be between 1 and 168 hours (1 week max)"
        )
    DBManager.update_user_preference(current_user["id"], "scrape_frequency_hours", hours)
    return {"message": f"Scraping frequency set to {hours} hours"}

@router.post("/password/change")
async def change_password(
    current_password: str,
    new_password: str,
    current_user: dict = Depends(get_current_user)
):
    """Change user password"""
    from app.auth.utils import verify_password, get_password_hash
    
    user = DBManager.get_user_by_id(current_user["id"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not verify_password(current_password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )
    
    hashed_new_password = get_password_hash(new_password)
    DBManager.update_password(current_user["id"], hashed_new_password)
    
    return {"message": "Password changed successfully"}
