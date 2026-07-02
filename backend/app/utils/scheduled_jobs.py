"""
Scheduled Jobs for COGNIS
Handles periodic tasks using APScheduler
"""

import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.auth.models import DBManager
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


# ===== SCHEDULED JOB FUNCTIONS =====

def send_weekly_job_summary():
    """
    Scheduled job to send weekly application summary every Sunday at 9 AM
    """
    try:
        logger.info("📧 Starting weekly job summary email task...")
        
        # Get all users
        users = DBManager.get_all_users()  # You may need to implement this
        
        for user in users:
            if not user.get("email_notifications"):
                continue
            
            user_id = user["id"]
            
            # Get applications from the last 7 days
            weekly_apps = DBManager.get_weekly_applications(user_id, days=7)
            
            if not weekly_apps:
                logger.info(f"No applications for user {user_id} this week")
                continue
            
            # Calculate statistics
            total_applications = len(weekly_apps)
            unique_companies = len(set(app.get('company', '') for app in weekly_apps))
            
            # Send email
            success = EmailService.send_weekly_summary_email(
                email=user["email"],
                full_name=user.get("full_name", "User"),
                total_applications=total_applications,
                applications=weekly_apps
            )
            
            if success:
                logger.info(f"✅ Weekly summary sent to {user['email']}")
            else:
                logger.warning(f"❌ Failed to send weekly summary to {user['email']}")
        
        logger.info("✅ Weekly job summary email task completed")
        
    except Exception as e:
        logger.error(f"❌ Error in send_weekly_job_summary: {str(e)}")


def send_daily_job_alerts():
    """
    Scheduled job to send daily job alerts every day at 8 AM
    Matches jobs from JobMatcher against user profiles
    """
    try:
        logger.info("📧 Starting daily job alerts task...")
        
        # Get all users with email notifications enabled
        users = DBManager.get_all_users()  # You may need to implement this
        
        for user in users:
            if not user.get("email_notifications"):
                continue
            
            user_id = user["id"]
            
            # Get matching jobs for user (this assumes JobMatcher.match_jobs_for_user exists)
            try:
                from app.jobs.matcher import JobMatcher
                matching_jobs = JobMatcher.match_jobs_for_user(user_id=user_id, limit=10)
                
                if not matching_jobs:
                    logger.info(f"No matching jobs for user {user_id}")
                    continue
                
                # Send alert email
                success = EmailService.send_job_alert_email(
                    email=user["email"],
                    full_name=user.get("full_name", "User"),
                    jobs=matching_jobs
                )
                
                if success:
                    logger.info(f"✅ Daily job alert sent to {user['email']} ({len(matching_jobs)} jobs)")
                else:
                    logger.warning(f"❌ Failed to send daily job alert to {user['email']}")
                    
            except Exception as e:
                logger.warning(f"Error matching jobs for user {user_id}: {str(e)}")
                continue
        
        logger.info("✅ Daily job alerts task completed")
        
    except Exception as e:
        logger.error(f"❌ Error in send_daily_job_alerts: {str(e)}")


def send_application_reminder():
    """
    Scheduled job to remind users with no recent applications
    Runs every Wednesday at 5 PM
    """
    try:
        logger.info("📧 Starting application reminder task...")
        
        # Get all users
        users = DBManager.get_all_users()  # You may need to implement this
        
        for user in users:
            if not user.get("email_notifications"):
                continue
            
            user_id = user["id"]
            
            # Check if user has applied in the last 7 days
            recent_apps = DBManager.get_weekly_applications(user_id, days=7)
            
            if len(recent_apps) == 0:
                # User hasn't applied in a week - send reminder
                subject = "🚀 Keep Your Job Search Momentum Going!"
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <style>
                        body {{ font-family: Arial, sans-serif; background-color: #f4f4f4; }}
                        .container {{ max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; }}
                        .header {{ background-color: #f59e0b; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                        .content {{ padding: 20px; }}
                        .button {{ background-color: #f59e0b; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 20px 0; }}
                        .footer {{ background-color: #f9fafb; padding: 10px; text-align: center; font-size: 12px; color: #6b7280; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>Keep Applying! 💪</h1>
                        </div>
                        <div class="content">
                            <p>Hi {user.get('full_name', 'User')},</p>
                            <p>We noticed you haven't applied for any jobs this week. Consistency is key to landing your dream role!</p>
                            <p>Here are some tips to stay motivated:</p>
                            <ul>
                                <li>Apply for at least 3-5 jobs daily</li>
                                <li>Customize your resume for each role</li>
                                <li>Follow up on pending applications</li>
                                <li>Update your LinkedIn profile</li>
                            </ul>
                            <a href="{user.get('dashboard_link', 'http://localhost:3000/job-board')}" class="button">Continue Job Search</a>
                        </div>
                        <div class="footer">
                            <p>&copy; 2026 COGNIS AI. All rights reserved.</p>
                        </div>
                    </div>
                </body>
                </html>
                """
                
                EmailService.send_email(
                    to_email=user["email"],
                    subject=subject,
                    html_content=html_content
                )
                logger.info(f"✅ Application reminder sent to {user['email']}")
        
        logger.info("✅ Application reminder task completed")
        
    except Exception as e:
        logger.error(f"❌ Error in send_application_reminder: {str(e)}")


# ===== SCHEDULER SETUP =====

def start_scheduler():
    """Initialize and start the APScheduler"""
    
    if scheduler.running:
        logger.warning("Scheduler is already running")
        return
    
    try:
        # Weekly job summary - Every Sunday at 9 AM
        scheduler.add_job(
            send_weekly_job_summary,
            CronTrigger(day_of_week=6, hour=9, minute=0),  # Sunday 9 AM
            id="weekly_job_summary",
            name="Weekly Job Application Summary",
            replace_existing=True
        )
        logger.info("✅ Scheduled: Weekly job summary (Sundays at 9 AM)")
        
        # Daily job alerts - Every day at 8 AM
        scheduler.add_job(
            send_daily_job_alerts,
            CronTrigger(hour=8, minute=0),  # Every day at 8 AM
            id="daily_job_alerts",
            name="Daily Job Alerts",
            replace_existing=True
        )
        logger.info("✅ Scheduled: Daily job alerts (Every day at 8 AM)")
        
        # Application reminder - Every Wednesday at 5 PM
        scheduler.add_job(
            send_application_reminder,
            CronTrigger(day_of_week=2, hour=17, minute=0),  # Wednesday 5 PM
            id="application_reminder",
            name="Application Reminder",
            replace_existing=True
        )
        logger.info("✅ Scheduled: Application reminder (Wednesdays at 5 PM)")
        
        # Start the scheduler
        scheduler.start()
        logger.info("✅ APScheduler started successfully")
        
    except Exception as e:
        logger.error(f"❌ Error starting scheduler: {str(e)}")
        raise


def stop_scheduler():
    """Stop the APScheduler"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("✅ APScheduler stopped")
