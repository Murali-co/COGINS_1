import traceback
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status, Query
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.auth.utils import get_current_user
from app.auth.models import DBManager
from app.models.schemas import (
    JobFilterCriteria, JobOut, JobListResponse
)
from app.jobs.scraper import JobScraper
from app.jobs.filter import JobFilter
from app.jobs.matcher import JobMatcher
from app.utils.bg_jobs import create_job, update_job, get_job
from app.services.email_service import EmailService

router = APIRouter(prefix="/jobs", tags=["jobs"])

async def run_manual_fetch_task(job_id: str, user_id: int, title: str, location: str, hours_old: int = 48):
    """
    Full Phase-2 Pipeline:
    Scrape → Deduplicate → Filter by Age → Store in ChromaDB → Semantic Match → Rank → Return
    """
    try:
        update_job(job_id, "processing")
        
        print(f"\n{'='*70}")
        print(f"🚀 PHASE-2 PIPELINE INITIATED")
        print(f"{'='*70}")
        print(f"User ID: {user_id}")
        print(f"Search Term: {title}")
        print(f"Location: {location}")
        print(f"Max Age: {hours_old} hours")
        print(f"{'='*70}\n")
        
        # ── Step 1: Scrape jobs (includes deduplication) ──
        print(f"STEP 1: SCRAPING & DEDUPLICATING")
        print(f"-" * 70)
        jobs = JobScraper.scrape(
            search_term=title,
            location=location,
            results_wanted=30,
            hours_old=hours_old
        )
        print(f"✅ STEP 1 COMPLETE: Fetched & deduplicated {len(jobs)} jobs\n")
        
        matched_count = 0
        saved_count = 0
        
        if jobs:
            # ── Step 2: Store in ChromaDB ──
            print(f"STEP 2: STORING IN VECTOR DATABASE (ChromaDB)")
            print(f"-" * 70)
            try:
                JobMatcher.upsert_jobs(jobs)
                saved_count = len(jobs)
                print(f"✅ STEP 2 COMPLETE: Saved {saved_count} jobs to vector database\n")
            except Exception as store_err:
                print(f"⚠️ STEP 2 WARNING: Storage error: {store_err}")
                traceback.print_exc()
            
            # ── Step 3: Semantic Match against user profile ──
            print(f"STEP 3: SEMANTIC MATCHING & RANKING")
            print(f"-" * 70)
            try:
                matched_jobs = JobMatcher.match_jobs_for_user(user_id, limit=min(len(jobs), 50))
                matched_count = len(matched_jobs)
                
                high_matches = [mj for mj in matched_jobs if mj.get("match_score", 0) >= 80.0]
                print(f"✅ STEP 3 COMPLETE: Matched {matched_count} jobs")
                print(f"   → {len(high_matches)} high-quality matches (≥80%)")
                print(f"   → {matched_count - len(high_matches)} moderate matches (<80%)\n")
                
                # Generate notifications for high matches
                for j in high_matches[:5]:  # Limit notifications
                    try:
                        DBManager.add_notification(
                            user_id=user_id,
                            title="🎯 New Job Match Found!",
                            message=f"'{j['title']}' at '{j['company']}' matches {j['match_score']:.0f}% of your profile",
                            type="job_alert"
                        )
                    except Exception:
                        pass
            except Exception as match_err:
                print(f"⚠️ STEP 3 WARNING: Matching skipped (user may not have a profile)")
                print(f"   Error: {match_err}\n")
        
        print(f"{'='*70}")
        print(f"✅ PHASE-2 PIPELINE COMPLETE")
        print(f"{'='*70}")
        print(f"Results Summary:")
        print(f"  • Fetched: {len(jobs)} jobs")
        print(f"  • Saved: {saved_count} jobs")
        print(f"  • Matched: {matched_count} jobs")
        print(f"{'='*70}\n")
        
        update_job(job_id, "completed", result={
            "count": len(jobs),
            "saved_count": saved_count,
            "matched_count": matched_count,
            "jobs_preview": [j["title"] for j in jobs[:5]] if jobs else []
        })
    except __import__('asyncio').CancelledError:
        print(f"\n❌ MANUAL FETCH PIPELINE CANCELLED (Server Shutdown)")
        update_job(job_id, "failed", error="Server shutdown during execution.")
        raise
    except Exception as e:
        print(f"\n{'='*70}")
        print(f"❌ PHASE-2 PIPELINE FAILED")
        print(f"{'='*70}")
        print(f"Error: {e}")
        print(f"Traceback:")
        traceback.print_exc()
        print(f"{'='*70}\n")
        update_job(job_id, "failed", error=str(e))


@router.get("/fetch")
async def trigger_fetch(
    background_tasks: BackgroundTasks,
    title: Optional[str] = Query(None, description="Job title keyword to search"),
    location: Optional[str] = Query(None, description="Location to search"),
    hours_old: Optional[int] = Query(None, description="Max job age in hours"),
    job_type: Optional[str] = Query(None, description="Optional job type filter (remote, hybrid, onsite)"),
    current_user: dict = Depends(get_current_user)
):
    # Retrieve user's criteria if not specified in query
    user_id = current_user["id"]
    criteria = DBManager.get_criteria(user_id)
    
    fetch_title = title or (criteria["title"] if criteria and criteria.get("title") else "Software Engineer")
    fetch_loc = location or (criteria["location"] if criteria and criteria.get("location") else "Any")
    fetch_hours = hours_old or (criteria.get("hours_old", 48) if criteria else 48)
    
    # Save/update user criteria if we got query params
    if title or location or job_type is not None:
        DBManager.save_criteria(
            user_id=user_id,
            title=fetch_title,
            location=fetch_loc,
            is_remote=(fetch_loc == "Remote"),
            job_type=job_type,
            hours_old=fetch_hours
        )
        
    job_id = create_job()
    background_tasks.add_task(
        run_manual_fetch_task,
        job_id,
        user_id,
        fetch_title,
        fetch_loc,
        fetch_hours
    )
    
    return {"job_id": job_id, "status": "pending"}

@router.get("/{job_id}/status")
async def get_job_status(job_id: str, current_user: dict = Depends(get_current_user)):
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Background task ID not found."
        )
    return job

@router.get("/list", response_model=JobListResponse)
async def list_jobs(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    
    # Try to return match-scored results if user has a profile
    try:
        matched = JobMatcher.match_jobs_for_user(user_id=user_id, limit=100)
        if matched:
            # Apply filtering based on saved criteria if any
            criteria = DBManager.get_criteria(user_id)
            if criteria:
                matched = JobFilter.filter_jobs(
                    jobs=matched,
                    title=criteria.get("title"),
                    location=criteria.get("location"),
                    is_remote=criteria.get("is_remote"),
                    job_type=criteria.get("job_type")
                )
            return {"jobs": [JobOut(**j) for j in matched]}
    except Exception:
        pass
    
    # Fallback: return unscored jobs
    collection = JobMatcher.get_collection()
    results = collection.get(limit=100)
    jobs = JobMatcher._format_unmatched_jobs(results)
    
    criteria = DBManager.get_criteria(user_id)
    if criteria:
        jobs = JobFilter.filter_jobs(
            jobs=jobs,
            title=criteria.get("title"),
            location=criteria.get("location"),
            is_remote=criteria.get("is_remote"),
            job_type=criteria.get("job_type")
        )
    
    return {"jobs": jobs}

@router.post("/match", response_model=JobListResponse)
async def match_jobs(current_user: dict = Depends(get_current_user)):
    matched = JobMatcher.match_jobs_for_user(user_id=current_user["id"], limit=50)
    
    # Apply filtering based on saved criteria if any
    criteria = DBManager.get_criteria(current_user["id"])
    if criteria:
        matched = JobFilter.filter_jobs(
            jobs=matched,
            title=criteria.get("title"),
            location=criteria.get("location"),
            is_remote=criteria.get("is_remote"),
            job_type=criteria.get("job_type")
        )
        
    return {"jobs": [JobOut(**j) for j in matched]}

@router.post("/criteria")
async def save_filter_criteria(
    criteria: JobFilterCriteria,
    current_user: dict = Depends(get_current_user)
):
    DBManager.save_criteria(
        user_id=current_user["id"],
        title=criteria.title,
        location=criteria.location,
        is_remote=criteria.is_remote,
        job_type=criteria.job_type,
        hours_old=criteria.hours_old or 48
    )
    return {"message": "Job filter criteria saved successfully."}

@router.get("/criteria")
async def get_filter_criteria(current_user: dict = Depends(get_current_user)):
    criteria = DBManager.get_criteria(current_user["id"])
    if not criteria:
        return {"title": "", "location": "", "is_remote": None, "job_type": None, "hours_old": 48}
    return criteria

@router.get("/explain/{job_id}")
async def explain_job_match(
    job_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        explanation = await JobMatcher.explain_job_match(
            user_id=current_user["id"],
            job_id=job_id
        )
        return explanation
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )




