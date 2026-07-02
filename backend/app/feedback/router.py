from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.auth.utils import get_current_user
from app.services.email_service import EmailService

router = APIRouter(prefix="/feedback", tags=["feedback"])

class FeedbackSubmitRequest(BaseModel):
    feedback: str

@router.post("/submit")
async def submit_feedback(
    request: FeedbackSubmitRequest,
    current_user: dict = Depends(get_current_user)
):
    """Submit feedback which emails the administrator and logs locally"""
    if not request.feedback.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feedback content cannot be empty."
        )
    
    from app.auth.models import DBManager
    DBManager.create_feedback(current_user["id"], request.feedback)

    success = EmailService.send_feedback_email(
        user_email=current_user["email"],
        user_name=current_user["full_name"],
        feedback_text=request.feedback
    )
    
    return {"message": "Feedback submitted successfully. Thank you!"}
