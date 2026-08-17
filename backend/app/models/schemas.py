from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

# --- Authentication ---
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters long")
    full_name: str = Field(..., min_length=1)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    user_id: Optional[int] = None


# --- Resume / Profile ---
class SkillGapRequest(BaseModel):
    target_role: str

class LearningResource(BaseModel):
    title: str
    url: str

class SkillGapResponse(BaseModel):
    present_skills: List[str]
    missing_skills: List[str]
    skill_score: int
    recommendations: List[str]
    learning_resources: List[Union[LearningResource, str]]

class CoverLetterRequest(BaseModel):
    target_role: str
    company_name: Optional[str] = None
    tone: str = "formal"  # formal, casual, creative

class CoverLetterResponse(BaseModel):
    cover_letter: str


# --- Resume Tailoring ---
class ResumeTailorRequest(BaseModel):
    job_id: str

class KeywordChange(BaseModel):
    original: str
    optimized: str

class ResumeTailorResponse(BaseModel):
    tailored_resume: str
    keyword_changes: List[KeywordChange]
    ats_score_estimate: int


# --- Jobs ---
class JobFilterCriteria(BaseModel):
    title: Optional[str] = None
    location: Optional[str] = None
    is_remote: Optional[bool] = None
    hours_old: Optional[int] = 48
    job_type: Optional[str] = None  # remote, hybrid, onsite, any

class JobOut(BaseModel):
    id: str
    title: str
    company: str
    location: str
    description: str
    url: str
    posted_at: str
    source: str
    match_score: Optional[float] = None
    matched_skills: Optional[List[str]] = None
    missing_skills: Optional[List[str]] = None
    job_type: Optional[str] = None  # remote, hybrid, onsite

class JobListResponse(BaseModel):
    jobs: List[JobOut]


# --- Applications ---
class ApplicationPackageResponse(BaseModel):
    cover_letter: str
    resume_bullets: List[str]
    key_points: List[str]
    suggested_subject_line: str

class ApplicationSubmitRequest(BaseModel):
    job_id: str
    status: str = "applied"
    notes: Optional[str] = None
    cover_letter: Optional[str] = None
    resume_bullets: Optional[Union[List[str], str]] = None
    location: Optional[str] = None
    job_url: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    resume_version_id: Optional[int] = None
    tone: Optional[str] = "formal"

class ApplicationHistoryOut(BaseModel):
    id: str
    user_id: int
    job_id: str
    job_title: str
    company: str
    applied_at: str
    status: str
    cover_letter: str
    resume_bullets: List[str]
    notes: str
    location: Optional[str] = None
    job_url: Optional[str] = None
    resume_version_id: Optional[int] = None
    tone: Optional[str] = None
    status_history: Optional[List[Dict[str, Any]]] = None


# --- Email Verification & Password Reset ---
class ResendVerificationRequest(BaseModel):
    email: EmailStr

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=6)

class VerificationResponse(BaseModel):
    message: str
    verified: bool

class PasswordResetResponse(BaseModel):
    message: str
    success: bool


# --- Job Applications ---
class JobApplicationCreate(BaseModel):
    job_id: str
    company: str
    title: str
    location: Optional[str] = None
    job_url: Optional[str] = None
    cover_letter: Optional[str] = None
    notes: Optional[str] = None

class JobApplicationOut(BaseModel):
    id: int
    user_id: int
    job_id: str
    company: str
    title: str
    location: Optional[str] = None
    job_url: Optional[str] = None
    applied_date: datetime
    status: str
    cover_letter: Optional[str] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True

class JobApplicationListResponse(BaseModel):
    applications: List[JobApplicationOut]
    total: int
    skip: int
    limit: int

class WeeklySummaryOut(BaseModel):
    total_applications: int
    companies: List[str]
    applications: List[JobApplicationOut]
