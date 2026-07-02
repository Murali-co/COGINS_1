from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, update, func, inspect, text
from app.db.session import engine, SessionLocal
from app.db.models import (
    Base,
    User,
    ApplicationHistory,
    UserCriteria,
    ChatMessage,
    InterviewSession,
    ResumeVersion,
    Notification,
    SavedJob,
    Feedback,
)


def ensure_user_admin_column():
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    columns = [col["name"] for col in inspector.get_columns("users")]
    
    with engine.connect() as conn:
        # Add is_admin column if missing
        if "is_admin" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE"))
            print("✅ Added 'is_admin' column to users table")
        
        # Add email_notifications column if missing
        if "email_notifications" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN email_notifications BOOLEAN DEFAULT 1"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN email_notifications BOOLEAN DEFAULT TRUE"))
            print("✅ Added 'email_notifications' column to users table")
        
        # Add daily_digest column if missing
        if "daily_digest" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN daily_digest BOOLEAN DEFAULT 1"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN daily_digest BOOLEAN DEFAULT TRUE"))
            print("✅ Added 'daily_digest' column to users table")
        
        # Add scrape_frequency_hours column if missing
        if "scrape_frequency_hours" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN scrape_frequency_hours INTEGER DEFAULT 12"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN scrape_frequency_hours INTEGER DEFAULT 12"))
            print("✅ Added 'scrape_frequency_hours' column to users table")

        # Add email verification columns if missing
        if "email_verified" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 0"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE"))
            print("✅ Added 'email_verified' column to users table")

        if "verification_token" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN verification_token VARCHAR NULL UNIQUE"))
            print("✅ Added 'verification_token' column to users table")

        if "verification_token_expiry" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN verification_token_expiry TIMESTAMP WITH TIME ZONE NULL"))
            print("✅ Added 'verification_token_expiry' column to users table")

        if "reset_password_token" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN reset_password_token VARCHAR NULL UNIQUE"))
            print("✅ Added 'reset_password_token' column to users table")

        if "reset_password_token_expiry" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN reset_password_token_expiry TIMESTAMP WITH TIME ZONE NULL"))
            print("✅ Added 'reset_password_token_expiry' column to users table")
        
        # Ensure user criteria table has job_type support
        if "user_criteria" in inspector.get_table_names():
            user_criteria_cols = [col["name"] for col in inspector.get_columns("user_criteria")]
            if "job_type" not in user_criteria_cols:
                conn.execute(text("ALTER TABLE user_criteria ADD COLUMN job_type VARCHAR NULL"))
                print("✅ Added 'job_type' column to user_criteria table")
        
        # Ensure applications_history table has location and job_url columns
        if "applications_history" in inspector.get_table_names():
            app_history_cols = [col["name"] for col in inspector.get_columns("applications_history")]
            if "location" not in app_history_cols:
                conn.execute(text("ALTER TABLE applications_history ADD COLUMN location VARCHAR NULL"))
                print("✅ Added 'location' column to applications_history table")
            if "job_url" not in app_history_cols:
                conn.execute(text("ALTER TABLE applications_history ADD COLUMN job_url VARCHAR NULL"))
                print("✅ Added 'job_url' column to applications_history table")
        conn.commit()


# Ensure tables exist (for development). Production should use Alembic migrations.
Base.metadata.create_all(bind=engine)
# Note: ensure_user_admin_column() is called from app.main at startup


def init_db():
    """Compatibility helper used by tests to create tables."""
    Base.metadata.create_all(bind=engine)
    ensure_user_admin_column()


def model_to_dict(inst) -> Dict[str, Any]:
    res = {}
    for c in inst.__table__.columns:
        val = getattr(inst, c.name)
        # Convert datetimes to ISO strings for compatibility with existing API
        if isinstance(val, datetime):
            res[c.name] = val.isoformat(sep=' ')
            continue
        res[c.name] = val
    return res


class DBManager:
    @staticmethod
    def create_user(email: str, hashed_pw: str, full_name: str) -> Optional[int]:
        db = SessionLocal()
        try:
            user = User(email=email, hashed_password=hashed_pw, full_name=full_name, is_admin=True)
            db.add(user)
            db.commit()
            db.refresh(user)
            return user.id
        except IntegrityError:
            db.rollback()
            return None
        finally:
            db.close()

    @staticmethod
    def delete_user(user_id: int) -> None:
        db = SessionLocal()
        try:
            db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == email).first()
            return model_to_dict(user) if user else None
        finally:
            db.close()

    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            return model_to_dict(user) if user else None
        finally:
            db.close()

    @staticmethod
    def get_criteria(user_id: int) -> Optional[Dict[str, Any]]:
        db = SessionLocal()
        try:
            crit = db.get(UserCriteria, user_id)
            if crit:
                res = model_to_dict(crit)
                return res
            return None
        finally:
            db.close()

    @staticmethod
    def save_criteria(user_id: int, title: Optional[str], location: Optional[str], is_remote: Optional[bool], job_type: Optional[str] = None, hours_old: int = 48):
        db = SessionLocal()
        try:
            obj = UserCriteria(
                user_id=user_id,
                title=title,
                location=location,
                is_remote=is_remote,
                job_type=job_type,
                hours_old=hours_old,
            )
            db.merge(obj)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def add_application(app_id: str, user_id: int, job_id: str, job_title: str, company: str, applied_at, status: str, cover_letter: str, resume_bullets: str, notes: str, location: Optional[str] = None, job_url: Optional[str] = None):
        db = SessionLocal()
        try:
            # Accept string timestamps for backward compatibility
            if isinstance(applied_at, str):
                try:
                    applied_at_dt = datetime.fromisoformat(applied_at)
                except Exception:
                    # fallback: try common format
                    applied_at_dt = datetime.strptime(applied_at, "%Y-%m-%d %H:%M:%S")
            else:
                applied_at_dt = applied_at

            app = ApplicationHistory(
                id=app_id,
                user_id=user_id,
                job_id=job_id,
                job_title=job_title,
                company=company,
                applied_at=applied_at_dt,
                status=status,
                cover_letter=cover_letter,
                resume_bullets=resume_bullets,
                notes=notes,
                location=location,
                job_url=job_url
            )
            db.add(app)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_applications(user_id: int) -> List[Dict[str, Any]]:
        db = SessionLocal()
        try:
            rows = db.query(ApplicationHistory).filter(ApplicationHistory.user_id == user_id).order_by(ApplicationHistory.applied_at.desc()).all()
            return [model_to_dict(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def get_application(app_id: str, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a single application by ID, ensuring user owns it"""
        db = SessionLocal()
        try:
            row = db.query(ApplicationHistory).filter(
                ApplicationHistory.id == app_id,
                ApplicationHistory.user_id == user_id
            ).first()
            return model_to_dict(row) if row else None
        finally:
            db.close()

    @staticmethod
    def create_interview_session(session_id: str, user_id: int, job_id: Optional[str], target_role: Optional[str], chat_history: str):
        db = SessionLocal()
        try:
            session = InterviewSession(id=session_id, user_id=user_id, job_id=job_id, target_role=target_role, chat_history=chat_history)
            db.add(session)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_interview_session(session_id: str) -> Optional[Dict[str, Any]]:
        db = SessionLocal()
        try:
            s = db.get(InterviewSession, session_id)
            return model_to_dict(s) if s else None
        finally:
            db.close()

    @staticmethod
    def update_interview_session(session_id: str, chat_history: str, is_finished: bool, feedback: Optional[str] = None, score: Optional[int] = None):
        db = SessionLocal()
        try:
            stmt = update(InterviewSession).where(InterviewSession.id == session_id).values(chat_history=chat_history, is_finished=is_finished, feedback=feedback, score=score)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_user_interviews(user_id: int) -> List[Dict[str, Any]]:
        db = SessionLocal()
        try:
            rows = db.query(InterviewSession).filter(InterviewSession.user_id == user_id).order_by(InterviewSession.created_at.desc()).all()
            return [model_to_dict(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def save_resume_version(user_id: int, resume_text: str, label: str):
        db = SessionLocal()
        try:
            rv = ResumeVersion(user_id=user_id, resume_text=resume_text, version_label=label)
            db.add(rv)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_resume_versions(user_id: int) -> List[Dict[str, Any]]:
        db = SessionLocal()
        try:
            rows = db.query(ResumeVersion).filter(ResumeVersion.user_id == user_id).order_by(ResumeVersion.created_at.desc()).all()
            return [model_to_dict(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def get_resume_version_by_id(version_id: int) -> Optional[Dict[str, Any]]:
        db = SessionLocal()
        try:
            r = db.get(ResumeVersion, version_id)
            return model_to_dict(r) if r else None
        finally:
            db.close()

    @staticmethod
    def add_notification(user_id: int, title: str, message: str, type: str):
        db = SessionLocal()
        try:
            n = Notification(user_id=user_id, title=title, message=message, type=type)
            db.add(n)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_notifications(user_id: int, only_unread: bool = False) -> List[Dict[str, Any]]:
        db = SessionLocal()
        try:
            q = db.query(Notification).filter(Notification.user_id == user_id)
            if only_unread:
                q = q.filter(Notification.is_read == False)
            rows = q.order_by(Notification.created_at.desc()).all()
            return [model_to_dict(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def mark_notification_read(notification_id: int, user_id: int):
        db = SessionLocal()
        try:
            stmt = update(Notification).where(Notification.id == notification_id, Notification.user_id == user_id).values(is_read=True)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def mark_all_notifications_read(user_id: int):
        db = SessionLocal()
        try:
            stmt = update(Notification).where(Notification.user_id == user_id).values(is_read=True)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_admin_metrics() -> Dict[str, Any]:
        db = SessionLocal()
        try:
            total_users = db.query(func.count(User.id)).scalar() or 0
            total_chats = db.query(func.count(ChatMessage.id)).scalar() or 0
            total_apps = db.query(func.count(ApplicationHistory.id)).scalar() or 0
            total_interviews = db.query(func.count(InterviewSession.id)).scalar() or 0
            return {
                "total_users": total_users,
                "total_chats": total_chats,
                "total_applications": total_apps,
                "total_interviews": total_interviews,
            }
        finally:
            db.close()

    @staticmethod
    def update_password(user_id: int, hashed_pw: str):
        db = SessionLocal()
        try:
            stmt = update(User).where(User.id == user_id).values(hashed_password=hashed_pw)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def update_application_status(app_id: str, status: str):
        """Update application status"""
        db = SessionLocal()
        try:
            stmt = update(ApplicationHistory).where(ApplicationHistory.id == app_id).values(status=status)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def save_job(user_id: int, job_id: str, job_title: str, company: str, location: Optional[str] = None, job_url: Optional[str] = None) -> Optional[int]:
        """Save a job for later reference"""
        db = SessionLocal()
        try:
            # Check if already saved
            existing = db.query(SavedJob).filter(
                SavedJob.user_id == user_id,
                SavedJob.job_id == job_id
            ).first()
            if existing:
                return existing.id
            
            saved_job = SavedJob(
                user_id=user_id,
                job_id=job_id,
                job_title=job_title,
                company=company,
                location=location,
                job_url=job_url
            )
            db.add(saved_job)
            db.commit()
            db.refresh(saved_job)
            return saved_job.id
        except IntegrityError:
            db.rollback()
            return None
        finally:
            db.close()

    @staticmethod
    def get_saved_jobs(user_id: int) -> List[Dict[str, Any]]:
        """Get all saved jobs for a user"""
        db = SessionLocal()
        try:
            rows = db.query(SavedJob).filter(SavedJob.user_id == user_id).order_by(SavedJob.saved_at.desc()).all()
            return [model_to_dict(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def unsave_job(user_id: int, job_id: str) -> bool:
        """Remove a saved job"""
        db = SessionLocal()
        try:
            stmt = text("DELETE FROM saved_jobs WHERE user_id = :user_id AND job_id = :job_id")
            result = db.execute(stmt, {"user_id": user_id, "job_id": job_id})
            db.commit()
            return result.rowcount > 0
        finally:
            db.close()

    @staticmethod
    def is_job_saved(user_id: int, job_id: str) -> bool:
        """Check if a job is saved by user"""
        db = SessionLocal()
        try:
            exists = db.query(SavedJob).filter(
                SavedJob.user_id == user_id,
                SavedJob.job_id == job_id
            ).first() is not None
            return exists
        finally:
            db.close()

    @staticmethod
    def update_user_full_name(user_id: int, full_name: str):
        """Update user's full name"""
        db = SessionLocal()
        try:
            stmt = update(User).where(User.id == user_id).values(full_name=full_name)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def update_user_preference(user_id: int, preference: str, value: any):
        """Update a specific user preference"""
        db = SessionLocal()
        try:
            valid_preferences = {"email_notifications", "daily_digest", "scrape_frequency_hours", "preferred_model"}
            if preference not in valid_preferences:
                raise ValueError(f"Invalid preference: {preference}")
            
            update_dict = {getattr(User, preference): value}
            stmt = update(User).where(User.id == user_id).values(**update_dict)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    # ===== EMAIL VERIFICATION METHODS =====
    @staticmethod
    def set_verification_token(user_id: int, token: str, expiry: datetime):
        """Store verification token for a user"""
        db = SessionLocal()
        try:
            stmt = update(User).where(User.id == user_id).values(
                verification_token=token,
                verification_token_expiry=expiry
            )
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_user_by_verification_token(token: str) -> Optional[Dict[str, Any]]:
        """Get user by verification token"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.verification_token == token).first()
            return model_to_dict(user) if user else None
        finally:
            db.close()

    @staticmethod
    def verify_email(user_id: int):
        """Mark email as verified"""
        db = SessionLocal()
        try:
            stmt = update(User).where(User.id == user_id).values(
                email_verified=True,
                verification_token=None,
                verification_token_expiry=None
            )
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    # ===== PASSWORD RESET METHODS =====
    @staticmethod
    def set_reset_password_token(user_id: int, token: str, expiry: datetime):
        """Store password reset token for a user"""
        db = SessionLocal()
        try:
            stmt = update(User).where(User.id == user_id).values(
                reset_password_token=token,
                reset_password_token_expiry=expiry
            )
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_user_by_reset_token(token: str) -> Optional[Dict[str, Any]]:
        """Get user by password reset token"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.reset_password_token == token).first()
            return model_to_dict(user) if user else None
        finally:
            db.close()

    @staticmethod
    def reset_password(user_id: int, hashed_password: str):
        """Reset password and clear token"""
        db = SessionLocal()
        try:
            stmt = update(User).where(User.id == user_id).values(
                hashed_password=hashed_password,
                reset_password_token=None,
                reset_password_token_expiry=None
            )
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    # ===== JOB APPLICATION METHODS =====
    @staticmethod
    def create_job_application(user_id: int, job_id: str, company: str, title: str, 
                              location: Optional[str] = None, job_url: Optional[str] = None,
                              cover_letter: Optional[str] = None, notes: Optional[str] = None) -> Optional[int]:
        """Create a new job application"""
        from app.db.models import JobApplication
        db = SessionLocal()
        try:
            # Check if already applied
            existing = db.query(JobApplication).filter(
                JobApplication.user_id == user_id,
                JobApplication.job_id == job_id
            ).first()
            if existing:
                return existing.id
            
            app = JobApplication(
                user_id=user_id,
                job_id=job_id,
                company=company,
                title=title,
                location=location,
                job_url=job_url,
                cover_letter=cover_letter,
                notes=notes,
                status="pending"
            )
            db.add(app)
            db.commit()
            db.refresh(app)
            return app.id
        except IntegrityError:
            db.rollback()
            return None
        finally:
            db.close()

    @staticmethod
    def get_job_applications(user_id: int, status: Optional[str] = None, skip: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
        """Get job applications for a user"""
        from app.db.models import JobApplication
        db = SessionLocal()
        try:
            q = db.query(JobApplication).filter(JobApplication.user_id == user_id)
            if status:
                q = q.filter(JobApplication.status == status)
            rows = q.order_by(JobApplication.applied_date.desc()).offset(skip).limit(limit).all()
            return [model_to_dict(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def get_job_application(app_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific job application"""
        from app.db.models import JobApplication
        db = SessionLocal()
        try:
            app = db.query(JobApplication).filter(
                JobApplication.id == app_id,
                JobApplication.user_id == user_id
            ).first()
            return model_to_dict(app) if app else None
        finally:
            db.close()

    @staticmethod
    def update_job_application_status(app_id: int, status: str):
        """Update job application status"""
        from app.db.models import JobApplication
        db = SessionLocal()
        try:
            stmt = update(JobApplication).where(JobApplication.id == app_id).values(status=status)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_weekly_applications(user_id: int, days: int = 7) -> List[Dict[str, Any]]:
        """Get applications from the last N days"""
        from app.db.models import JobApplication
        from datetime import datetime, timedelta
        db = SessionLocal()
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            rows = db.query(JobApplication).filter(
                JobApplication.user_id == user_id,
                JobApplication.applied_date >= cutoff_date
            ).order_by(JobApplication.applied_date.desc()).all()
            return [model_to_dict(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def get_all_users() -> List[Dict[str, Any]]:
        """Get all users (for scheduled jobs and notifications)"""
        db = SessionLocal()
        try:
            users = db.query(User).all()
            return [model_to_dict(u) for u in users]
        finally:
            db.close()

    @staticmethod
    def create_feedback(user_id: int, feedback_text: str) -> Optional[int]:
        """Save user feedback to database"""
        db = SessionLocal()
        try:
            fb = Feedback(user_id=user_id, feedback_text=feedback_text)
            db.add(fb)
            db.commit()
            db.refresh(fb)
            return fb.id
        except Exception as e:
            db.rollback()
            print(f"[DB] Failed to save feedback to database: {e}")
            return None
        finally:
            db.close()

