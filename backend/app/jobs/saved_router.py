from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.db.models import SavedJob
from app.db.session import SessionLocal
from app.auth.utils import get_current_user
from pydantic import BaseModel
from datetime import datetime, timezone

router = APIRouter(prefix="/jobs/saved", tags=["saved-jobs"])

class SaveJobRequest(BaseModel):
    job_id: str
    job_title: str
    company: str
    location: str = None
    job_url: str = None
    notes: str = None

class SavedJobResponse(BaseModel):
    id: int
    job_id: str
    job_title: str
    company: str
    location: str = None
    job_url: str = None
    notes: str = None
    saved_at: datetime

    class Config:
        from_attributes = True

@router.post("/save", response_model=SavedJobResponse)
async def save_job(
    req: SaveJobRequest,
    current_user: dict = Depends(get_current_user)
):
    """Save a job to watchlist"""
    db = SessionLocal()
    try:
        # Check if already saved
        existing = db.query(SavedJob).filter(
            SavedJob.user_id == current_user["id"],
            SavedJob.job_id == req.job_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Job already saved"
            )
        
        # Add new saved job
        saved_job = SavedJob(
            user_id=current_user["id"],
            job_id=req.job_id,
            job_title=req.job_title,
            company=req.company,
            location=req.location,
            job_url=req.job_url,
            notes=req.notes
        )
        db.add(saved_job)
        db.commit()
        db.refresh(saved_job)
        return saved_job
    finally:
        db.close()

@router.get("/list", response_model=List[SavedJobResponse])
async def get_saved_jobs(
    current_user: dict = Depends(get_current_user)
):
    """Get all saved jobs for current user"""
    db = SessionLocal()
    try:
        saved_jobs = db.query(SavedJob).filter(
            SavedJob.user_id == current_user["id"]
        ).order_by(SavedJob.saved_at.desc()).all()
        return saved_jobs
    finally:
        db.close()

@router.delete("/{saved_job_id}")
async def remove_saved_job(
    saved_job_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Remove a job from watchlist"""
    db = SessionLocal()
    try:
        saved_job = db.query(SavedJob).filter(
            SavedJob.id == saved_job_id,
            SavedJob.user_id == current_user["id"]
        ).first()
        
        if not saved_job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Saved job not found"
            )
        
        db.delete(saved_job)
        db.commit()
        return {"message": "Saved job removed"}
    finally:
        db.close()

@router.patch("/{saved_job_id}/notes")
async def update_saved_job_notes(
    saved_job_id: int,
    notes: str,
    current_user: dict = Depends(get_current_user)
):
    """Update notes for a saved job"""
    db = SessionLocal()
    try:
        saved_job = db.query(SavedJob).filter(
            SavedJob.id == saved_job_id,
            SavedJob.user_id == current_user["id"]
        ).first()
        
        if not saved_job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Saved job not found"
            )
        
        saved_job.notes = notes
        db.commit()
        db.refresh(saved_job)
        return saved_job
    finally:
        db.close()
