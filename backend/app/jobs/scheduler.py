from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.auth.models import DBManager
from app.db.models import User
from app.db.session import SessionLocal
from app.jobs.scraper import JobScraper
from app.jobs.matcher import JobMatcher
from app.services.email_service import EmailService
import asyncio
from datetime import datetime, timedelta, timezone

scheduler = AsyncIOScheduler()

async def scheduled_scraping_job():
    """
    Finds active users, reads their search criteria, 
    scrapes relevant jobs, and saves them to ChromaDB.
    """
    print("Starting scheduled job scraping task...")
    
    # 1. Fetch all users from DB via SQLAlchemy
    db = SessionLocal()
    try:
        users = db.query(User.id).all()
    finally:
        db.close()
    
    if not users:
        print("No registered users. Skipping scheduled scrape.")
        return
        
    for user in users:
        user_id = user.id
        # Get user criteria
        criteria = DBManager.get_criteria(user_id)
        if not criteria or not criteria.get("title"):
            print(f"User {user_id} has no active job search criteria. Skipping scheduled scrape.")
            continue
            
        search_title = criteria["title"]
        location = criteria.get("location")
        if not location or location.strip().lower() in ["any", "", "all"]:
            location = "Bengaluru, India"
                
        try:
            print(f"Scraping jobs for User {user_id}: '{search_title}' in '{location}'...")
            jobs = JobScraper.scrape(
                search_term=search_title,
                location=location,
                results_wanted=20,
                hours_old=48
            )
            
            if jobs:
                # Upsert jobs to ChromaDB
                JobMatcher.upsert_jobs(jobs)
                print(f"Successfully scraped and stored {len(jobs)} jobs for User {user_id}.")
                
                # Check for matches and send notifications + emails for high match scores (>=80%)
                try:
                    matched_jobs = JobMatcher.match_jobs_for_user(user_id, limit=10)
                    high_matches = [mj for mj in matched_jobs if mj.get("match_score", 0) >= 80.0]
                    
                    # Get user email for notifications
                    user_obj = db.query(User).filter(User.id == user_id).first()
                    user_email = user_obj.email if user_obj else None
                    
                    for j in high_matches:
                        # Add in-app notification
                        DBManager.add_notification(
                            user_id=user_id,
                            title="New Job Match Found!",
                            message=f"'{j['title']}' at '{j['company']}' matches {j['match_score']}% of your profile skills.",
                            type="job_alert"
                        )
                        
                        # Send email notification if configured
                        if user_email:
                            EmailService.send_job_match_alert(
                                to_email=user_email,
                                job_title=j['title'],
                                company=j['company'],
                                match_score=j['match_score']
                            )
                except Exception as match_err:
                    print(f"Error checking matches/generating notifications for user {user_id}: {match_err}")

            else:
                print(f"No jobs found for User {user_id}.")
        except Exception as e:
            print(f"Error in scheduler scraping for User {user_id}: {e}")
            import traceback
            traceback.print_exc()
            
        # Polite delay between user scrapes
        await asyncio.sleep(5)

async def scheduled_cleanup_job():
    print("Starting scheduled stale jobs cleanup task...")
    try:
        JobMatcher.cleanup_old_jobs(days=30)
    except Exception as e:
        print(f"Error in scheduler cleanup job: {e}")

def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(scheduled_scraping_job, 'interval', hours=12, id='job_scraper_job')
        scheduler.add_job(scheduled_cleanup_job, 'interval', days=1, id='db_cleanup_job')
        
        # Weekly job summary - Every Sunday at 9 AM
        scheduler.add_job(
            send_weekly_job_summary,
            'cron',
            day_of_week=6,  # Sunday
            hour=9,
            minute=0,
            id='weekly_job_summary',
            name='Weekly Job Application Summary'
        )
        
        # Daily job alerts - Every day at 8 AM
        scheduler.add_job(
            send_daily_job_alerts,
            'cron',
            hour=8,
            minute=0,
            id='daily_job_alerts',
            name='Daily Job Alerts'
        )
        
        scheduler.start()
        print("APScheduler started.")


async def send_weekly_job_summary():
    """Send weekly application summary every Sunday at 9 AM"""
    try:
        print("📧 Sending weekly job application summaries...")
        users = DBManager.get_all_users()
        
        for user in users:
            if not user.get("email_notifications"):
                continue
            
            weekly_apps = DBManager.get_weekly_applications(user["id"], days=7)
            
            if weekly_apps:
                EmailService.send_weekly_summary_email(
                    email=user["email"],
                    full_name=user.get("full_name", "User"),
                    total_applications=len(weekly_apps),
                    applications=weekly_apps
                )
                print(f"✅ Weekly summary sent to {user['email']}")
    except Exception as e:
        print(f"❌ Error in weekly job summary: {e}")


async def send_daily_job_alerts():
    """Send daily job alerts every day at 8 AM"""
    try:
        print("📧 Sending daily job alerts...")
        users = DBManager.get_all_users()
        
        for user in users:
            if not user.get("email_notifications"):
                continue
            
            try:
                matching_jobs = JobMatcher.match_jobs_for_user(user["id"], limit=10)
                
                if matching_jobs:
                    EmailService.send_job_alert_email(
                        email=user["email"],
                        full_name=user.get("full_name", "User"),
                        jobs=matching_jobs
                    )
                    print(f"✅ Daily alert sent to {user['email']}")
            except Exception as match_err:
                print(f"Error matching jobs for user {user['id']}: {match_err}")
    except Exception as e:
        print(f"❌ Error in daily job alerts: {e}")


def shutdown_scheduler():
    if scheduler.running:
        try:
            scheduler.shutdown()
        except Exception as e:
            print(f"Warning during scheduler shutdown: {e}")
        print("APScheduler shut down.")
