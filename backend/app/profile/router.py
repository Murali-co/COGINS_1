from fastapi import APIRouter, Depends
from app.auth.utils import get_current_user
from app.auth.models import DBManager
from app.db.session import SessionLocal
from app.db.models import ResumeVersion, UserCriteria, InterviewSession, ApplicationHistory
from pydantic import BaseModel

router = APIRouter(prefix="/profile", tags=["profile"])

class ProfileCompletenessResponse(BaseModel):
    completion_score: int
    resume_uploaded: bool
    skills_filled: bool
    criteria_set: bool
    interview_practiced: bool
    applications_submitted: bool
    breakdown: dict

    class Config:
        from_attributes = True

@router.get("/completeness", response_model=ProfileCompletenessResponse)
async def get_profile_completeness(current_user: dict = Depends(get_current_user)):
    """
    Calculate profile completeness score (0-100%)
    
    Breakdown:
    - Resume uploaded: 20%
    - Skills filled: 20%
    - Search criteria set: 20%
    - Interview practiced: 20%
    - Applications submitted: 20%
    """
    db = SessionLocal()
    try:
        user_id = current_user["id"]
        
        # 1. Check resume uploaded
        resume = db.query(ResumeVersion).filter(
            ResumeVersion.user_id == user_id
        ).first()
        resume_uploaded = resume is not None
        
        # 2. Check skills filled (via profile in vector DB or extract from resume)
        # For now, check if resume exists and has decent length
        skills_filled = resume_uploaded and len(resume.resume_text) > 200 if resume else False
        
        # 3. Check criteria set
        criteria = db.query(UserCriteria).filter(
            UserCriteria.user_id == user_id
        ).first()
        criteria_set = criteria is not None and criteria.title is not None
        
        # 4. Check interview practiced
        interview = db.query(InterviewSession).filter(
            InterviewSession.user_id == user_id,
            InterviewSession.is_finished == True
        ).first()
        interview_practiced = interview is not None
        
        # 5. Check applications submitted
        application = db.query(ApplicationHistory).filter(
            ApplicationHistory.user_id == user_id
        ).first()
        applications_submitted = application is not None
        
        # Calculate score
        score_parts = {
            "resume": 20 if resume_uploaded else 0,
            "skills": 20 if skills_filled else 0,
            "criteria": 20 if criteria_set else 0,
            "interview": 20 if interview_practiced else 0,
            "applications": 20 if applications_submitted else 0,
        }
        
        total_score = sum(score_parts.values())
        
        return {
            "completion_score": total_score,
            "resume_uploaded": resume_uploaded,
            "skills_filled": skills_filled,
            "criteria_set": criteria_set,
            "interview_practiced": interview_practiced,
            "applications_submitted": applications_submitted,
            "breakdown": score_parts
        }
    finally:
        db.close()

@router.get("/recommendations")
async def get_profile_recommendations(current_user: dict = Depends(get_current_user)):
    """
    Get personalized recommendations to improve profile completeness
    """
    db = SessionLocal()
    try:
        user_id = current_user["id"]
        recommendations = []
        
        # Check each component and provide recommendations
        resume = db.query(ResumeVersion).filter(
            ResumeVersion.user_id == user_id
        ).first()
        
        if not resume:
            recommendations.append({
                "priority": "high",
                "title": "Upload Your Resume",
                "description": "Your resume is the foundation of your job profile. Upload it to enable skill analysis and job matching.",
                "action": "/resume/upload"
            })
        elif len(resume.resume_text) < 500:
            recommendations.append({
                "priority": "medium",
                "title": "Expand Your Resume",
                "description": "Your resume seems brief. Add more details about your experience, skills, and accomplishments.",
                "action": "/resume/edit"
            })
        
        criteria = db.query(UserCriteria).filter(
            UserCriteria.user_id == user_id
        ).first()
        
        if not criteria or not criteria.title:
            recommendations.append({
                "priority": "high",
                "title": "Set Job Search Criteria",
                "description": "Tell us what kind of roles you're looking for. This helps us find better matches.",
                "action": "/jobs/criteria"
            })
        
        interview = db.query(InterviewSession).filter(
            InterviewSession.user_id == user_id,
            InterviewSession.is_finished == True
        ).first()
        
        if not interview:
            recommendations.append({
                "priority": "medium",
                "title": "Practice Interview Skills",
                "description": "Do a mock interview to get feedback and prepare for real interviews.",
                "action": "/interview/start"
            })
        
        application = db.query(ApplicationHistory).filter(
            ApplicationHistory.user_id == user_id
        ).first()
        
        if not application:
            recommendations.append({
                "priority": "high",
                "title": "Start Applying to Jobs",
                "description": "Find and apply to your first job using tailored cover letters and resumes.",
                "action": "/jobs/matched"
            })
        
        return {
            "recommendations": recommendations,
            "total_suggestions": len(recommendations)
        }
    finally:
        db.close()
