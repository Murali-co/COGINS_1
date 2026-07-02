from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, HTTPException, status, Request
from typing import Dict, Any, List
from app.auth.utils import get_current_user
from app.auth.models import DBManager
from app.resume.parser import ResumeParser
from app.resume.cleaner import ResumeCleaner
from app.resume.extractor import SkillExtractor
from app.vector_db.profile_store import ProfileStore
from app.llm.skill_gap import SkillGapAnalyzer
from app.llm.cover_letter import CoverLetterGenerator
from app.llm.ollama_client import OllamaClient
from app.models.schemas import SkillGapRequest, CoverLetterRequest, CoverLetterResponse, ResumeTailorRequest, ResumeTailorResponse
from app.utils.bg_jobs import create_job, update_job, get_job
from app.jobs.matcher import JobMatcher
from app.llm.resume_tailor import ResumeTailorEngine
from app.utils.limiter import limiter
from app.db.session import SessionLocal
from pydantic import BaseModel
import os
import json
import asyncio

router = APIRouter(prefix="/resume", tags=["resume"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_MIME_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
]
ALLOWED_EXTENSIONS = [".pdf", ".docx"]

async def run_analysis_task(job_id: str, user_id: int, target_role: str):
    try:
        update_job(job_id, "processing")
        
        # 1. Fetch user profile
        profile = ProfileStore.get_profile(user_id)
        if not profile or not profile.get("resume_text"):
            raise ValueError("No resume uploaded for user. Please upload a resume first.")

        skills = profile.get("skills", [])
        resume_text = profile.get("resume_text", "")
        
        # 2. Run Skill Gap Analysis (Ollama)
        gap_results = await SkillGapAnalyzer.analyze(skills, target_role)
        
        # 3. Generate baseline Cover Letter (Ollama)
        cover_letter = await CoverLetterGenerator.generate(resume_text, target_role, tone="formal")
        
        result = {
            "skill_gap": gap_results,
            "cover_letter": cover_letter,
            "target_role": target_role
        }
        
        update_job(job_id, "completed", result=result)
    except __import__('asyncio').CancelledError:
        print(f"Resume analysis task {job_id} was cancelled due to server shutdown.")
        update_job(job_id, "failed", error="Server shutdown during analysis.")
        raise
    except Exception as e:
        print(f"Error in background resume analysis task: {e}")
        update_job(job_id, "failed", error=str(e))

@router.post("/upload")
@limiter.limit("5/minute")
async def upload_resume(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    # 1. Validate File Size
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds the 10MB limit."
        )

    # 2. Validate MIME Type and Extension
    filename = file.filename or ""
    _, ext = os.path.splitext(filename.lower())
    if ext not in ALLOWED_EXTENSIONS or file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only PDF and DOCX files are allowed."
        )

    # 3. Parse and Clean Resume
    try:
        raw_text = ResumeParser.parse(file_bytes, filename)
        if not raw_text.strip():
            raise ValueError("Extracted text is empty. The file may be scanned or empty.")
            
        cleaned_sections = ResumeCleaner.segment_sections(raw_text)
        
        # Re-assemble cleaned text
        cleaned_full_text = "\n\n".join([f"[{sec.upper()}]\n{content}" for sec, content in cleaned_sections.items() if content])
        
        # Extract Skills
        extracted_skills_data = SkillExtractor.extract_skills(cleaned_full_text, cleaned_sections)
        skills_list = [item["skill"] for item in extracted_skills_data]
        
        # 4. Save to vector DB
        ProfileStore.store_profile(
            user_id=current_user["id"],
            resume_text=cleaned_full_text,
            skills=skills_list
        )
        
        # Save historical version
        DBManager.save_resume_version(
            user_id=current_user["id"],
            resume_text=cleaned_full_text,
            label=f"Resume Upload: {filename}"
        )
        
        return {
            "message": "Resume uploaded and processed successfully.",
            "skills": skills_list,
            "text_preview": cleaned_full_text[:1000] + ("..." if len(cleaned_full_text) > 1000 else "")
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process resume: {str(e)}"
        )

@router.post("/analyze")
@limiter.limit("5/minute")
async def analyze_resume(
    request: Request,
    req_body: SkillGapRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    # Check if profile exists
    profile = ProfileStore.get_profile(current_user["id"])
    if not profile or not profile.get("resume_text"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload a resume first."
        )

    # Create job id and spin off background task
    job_id = create_job()
    background_tasks.add_task(
        run_analysis_task,
        job_id,
        current_user["id"],
        req_body.target_role
    )
    
    return {"job_id": job_id, "status": "pending"}

@router.get("/profile")
async def get_profile(current_user: dict = Depends(get_current_user)):
    profile = ProfileStore.get_profile(current_user["id"])
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No resume profile found. Please upload a resume first."
        )
    return profile

@router.post("/suggest-roles")
@limiter.limit("5/minute")
async def suggest_roles(request: Request, current_user: dict = Depends(get_current_user)):
    """
    Automatically suggests top 3-5 job roles based on the uploaded resume.
    Call this right after /upload succeeds.
    """
    profile = ProfileStore.get_profile(current_user["id"])
    if not profile or not profile.get("resume_text"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No resume uploaded.")
    
    resume_text = profile["resume_text"][:3000]  # truncate to save tokens
    skills = profile.get("skills", [])
    
    prompt = f"""
You are a career expert. Based on this resume, suggest the TOP 5 most suitable job roles for this candidate.

Resume:
{resume_text}

Extracted Skills: {', '.join(skills[:20]) if skills else 'Not extracted yet'}

Return ONLY a JSON array of exactly 5 role strings. No explanation, no markdown.
Example: ["Software Engineer", "Backend Developer", "Python Developer", "API Engineer", "Data Engineer"]
"""
    
    try:
        result = await OllamaClient.generate(prompt)
        result = result.strip()
        # Clean markdown fences if present
        if "```" in result:
            result = result.split("```")[1].replace("json", "").strip()
        roles = json.loads(result)
        if not isinstance(roles, list):
            raise ValueError("Not a list")
        roles = [str(r).strip() for r in roles[:5] if r]
    except Exception as e:
        print(f"Error suggesting roles: {e}")
        # Fallback based on skills
        roles = ["Software Engineer", "Backend Developer", "Full Stack Developer",
                 "Python Developer", "API Developer"]
    
    return {"suggested_roles": roles}

@router.post("/cover-letter", response_model=CoverLetterResponse)
@limiter.limit("5/minute")
async def generate_cover_letter_tone(
    request: Request,
    req_body: CoverLetterRequest,
    current_user: dict = Depends(get_current_user)
):
    profile = ProfileStore.get_profile(current_user["id"])
    if not profile or not profile.get("resume_text"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload a resume first."
        )
    text = await CoverLetterGenerator.generate(
        resume_text=profile["resume_text"],
        target_role=req_body.target_role,
        company_name=req_body.company_name,
        tone=req_body.tone
    )
    text = text.replace("[Your Name]", current_user["full_name"])
    text = text.replace("[Candidate Name]", current_user["full_name"])
    return {"cover_letter": text}

@router.post("/tailor", response_model=ResumeTailorResponse)
@limiter.limit("5/minute")
async def tailor_resume(
    request: Request,
    req_body: ResumeTailorRequest,
    current_user: dict = Depends(get_current_user)
):
    # 1. Fetch user profile
    profile = ProfileStore.get_profile(current_user["id"])
    if not profile or not profile.get("resume_text"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload a resume first."
        )

    # 2. Fetch target job from vector db
    collection = JobMatcher.get_collection()
    job_data = collection.get(ids=[req_body.job_id])
    if not job_data or not job_data["ids"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target job listing not found in local database."
        )

    job_desc = job_data["documents"][0]

    # 3. Call LLM Tailoring Engine
    tailored_result = await ResumeTailorEngine.tailor(profile["resume_text"], job_desc)
    return tailored_result

class ProfileEditRequest(BaseModel):
    skills: List[str]
    resume_text: str

@router.post("/profile/edit")
async def edit_profile(
    req: ProfileEditRequest,
    current_user: dict = Depends(get_current_user)
):
    ProfileStore.store_profile(
        user_id=current_user["id"],
        resume_text=req.resume_text,
        skills=req.skills
    )
    DBManager.save_resume_version(
        user_id=current_user["id"],
        resume_text=req.resume_text,
        label="Manual Edit via Dashboard"
    )
    return {"message": "Profile updated successfully."}

@router.get("/versions")
async def get_resume_versions(current_user: dict = Depends(get_current_user)):
    return DBManager.get_resume_versions(current_user["id"])

@router.post("/versions/restore/{version_id}")
async def restore_resume_version(
    version_id: int,
    current_user: dict = Depends(get_current_user)
):
    version = DBManager.get_resume_version_by_id(version_id)
    if not version or version["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found."
        )
        
    cleaned_sections = ResumeCleaner.segment_sections(version["resume_text"])
    cleaned_full_text = "\n\n".join([f"[{sec.upper()}]\n{content}" for sec, content in cleaned_sections.items() if content])
    extracted_skills_data = SkillExtractor.extract_skills(cleaned_full_text, cleaned_sections)
    skills_list = [item["skill"] for item in extracted_skills_data]
    
    ProfileStore.store_profile(
        user_id=current_user["id"],
        resume_text=version["resume_text"],
        skills=skills_list
    )
    return {"message": "Version restored successfully.", "skills": skills_list}

# ATS Score endpoints
from pydantic import BaseModel as PydanticModel
from typing import Optional
from app.llm.ats_scorer import ATSScorer

class ATSScoreRequest(PydanticModel):
    job_description: str
    resume_text: Optional[str] = None

@router.post("/ats/score")
async def calculate_ats_score(
    request: ATSScoreRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Calculate ATS compatibility score for resume against job description
    """
    resume_text = request.resume_text
    if not resume_text:
        # Fetch user's latest resume
        db = SessionLocal()
        try:
            from app.db.models import ResumeVersion
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

@router.post("/ats/quick-check")
async def quick_ats_check(request: ATSScoreRequest):
    """Quick ATS compatibility check"""
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

@router.get("/ats/formatting-tips")
async def get_ats_formatting_tips():
    """Get tips for ATS-friendly resume formatting"""
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

