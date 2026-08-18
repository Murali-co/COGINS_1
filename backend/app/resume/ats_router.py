from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from app.auth.utils import get_current_user
from app.auth.models import DBManager
from app.db.session import SessionLocal
from app.db.models import ResumeVersion
from app.llm.ats_scorer import ATSScorer

router = APIRouter(prefix="/ats", tags=["ats"])

class ATSScoreRequest(BaseModel):
    job_description: str
    resume_text: Optional[str] = None  # If not provided, use latest user resume

class ATSScoreResponse(BaseModel):
    overall_score: int
    pass_ats: bool
    recommendation: str
    breakdown: dict
    matched_keywords: list
    suggestions: str

@router.post("/score", response_model=ATSScoreResponse)
async def calculate_ats_score(
    request: ATSScoreRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Calculate ATS compatibility score for resume against job description
    
    Scoring breakdown:
    - Keyword match (30%): How many JD keywords are in resume
    - Skills match (30%): Technical and soft skills alignment
    - Experience level (20%): Years of experience
    - ATS formatting (20%): Standard sections, structure, special characters
    """
    
    # Get resume text
    resume_text = request.resume_text
    if not resume_text:
        # Fetch user's latest resume
        db = SessionLocal()
        try:
            latest_resume = db.query(ResumeVersion).filter(
                ResumeVersion.user_id == current_user["id"]
            ).order_by(ResumeVersion.created_at.desc()).first()
            
            if not latest_resume:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No resume found for user. Please upload a resume first."
                )
            
            resume_text = latest_resume.resume_text
        finally:
            db.close()
    
    if not resume_text or len(resume_text) < 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resume text is too short (minimum 50 characters)"
        )
    
    if not request.job_description or len(request.job_description) < 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job description is too short (minimum 50 characters)"
        )
    
    try:
        # Generate ATS score
        ats_result = await ATSScorer.generate_ats_score_detailed(
            resume_text,
            request.job_description
        )
        
        return ats_result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating ATS score: {str(e)}"
        )

@router.post("/quick-check")
async def quick_ats_check(request: ATSScoreRequest):
    """
    Quick ATS compatibility check without using user's resume
    Useful for checking hypothetical resume/JD pairs
    """
    if not request.resume_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="resume_text is required for quick check"
        )
    
    try:
        keyword_score, keywords = ATSScorer.calculate_keyword_match(
            request.resume_text,
            request.job_description
        )
        
        skills_score, skills = ATSScorer.calculate_skills_match(
            request.resume_text,
            request.job_description
        )
        
        format_score, issues = ATSScorer.check_ats_formatting(request.resume_text)
        
        return {
            "keyword_match_score": int(keyword_score),
            "skills_match_score": int(skills_score),
            "formatting_score": int(format_score),
            "average_score": int((keyword_score + skills_score + format_score) / 3),
            "formatting_issues": issues,
            "matched_skills": skills.get('soft_keywords', []) + skills.get('technical_keywords', [])
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error performing ATS check: {str(e)}"
        )

@router.get("/formatting-tips")
async def get_ats_formatting_tips():
    """
    Get tips for ATS-friendly resume formatting
    """
    return {
        "do": [
            "Use standard section headers: Summary, Experience, Education, Skills, Projects",
            "Use bullet points (•) for better readability",
            "Include quantifiable achievements (e.g., '30% improvement in performance')",
            "Match job description keywords where appropriate",
            "Use standard fonts (Arial, Calibri, Helvetica)",
            "Stick to standard formatting (no graphics, charts, or logos)",
            "Use standard dates format (MM/YYYY or Month Year)",
            "Include relevant keywords naturally throughout the resume"
        ],
        "dont": [
            "Avoid tables, columns, or complex layouts",
            "Don't use graphics, images, or special characters",
            "Don't use fancy fonts or unusual colors",
            "Avoid multiple font sizes or styles",
            "Don't use PDFs with embedded images (use plain text-based PDFs)",
            "Avoid URLs with tracking parameters or shortened links",
            "Don't use abbreviations unless they're industry standard",
            "Avoid irrelevant personal information"
        ],
        "technical_keywords": list(ATSScorer.TECHNICAL_SKILLS)[:20],
        "soft_skills": list(ATSScorer.SOFT_SKILLS),
        "required_sections": list(ATSScorer.REQUIRED_SECTIONS)
    }
