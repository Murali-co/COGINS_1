from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    func,
)
from sqlalchemy.orm import relationship
from .session import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False, server_default='false')
    preferred_model = Column(String, nullable=True, default='qwen2.5:7b')
    email_notifications = Column(Boolean, nullable=True, default=True)
    daily_digest = Column(Boolean, nullable=True, default=True)
    scrape_frequency_hours = Column(Integer, nullable=True, default=12)
    last_active_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Email verification fields
    email_verified = Column(Boolean, nullable=False, default=False, server_default='false')
    verification_token = Column(String, nullable=True, unique=True)
    verification_token_expiry = Column(DateTime(timezone=True), nullable=True)
    
    # Password reset fields
    reset_password_token = Column(String, nullable=True, unique=True)
    reset_password_token_expiry = Column(DateTime(timezone=True), nullable=True)

    # 2FA fields
    two_factor_enabled = Column(Boolean, nullable=False, default=False, server_default='false')
    two_factor_secret = Column(String, nullable=True)

    # Orchestrator preferences
    auto_approve_external_actions = Column(Boolean, nullable=False, default=False, server_default='false')
    



class ApplicationHistory(Base):
    __tablename__ = "applications_history"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(String, nullable=False)
    job_title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    applied_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String, nullable=False)
    cover_letter = Column(Text, nullable=False)
    resume_bullets = Column(Text, nullable=False)
    notes = Column(Text, nullable=False)
    location = Column(String, nullable=True)
    job_url = Column(String, nullable=True)
    resume_version_id = Column(Integer, nullable=True)
    tone = Column(String, nullable=True)


class ApplicationStatusHistory(Base):
    __tablename__ = "application_status_history"
    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(String, ForeignKey("applications_history.id"), nullable=False, index=True)
    status = Column(String, nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())


class UserCriteria(Base):
    __tablename__ = "user_criteria"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    title = Column(String, nullable=True)
    location = Column(String, nullable=True)
    is_remote = Column(Boolean, nullable=True)
    job_type = Column(String, nullable=True)
    hours_old = Column(Integer, default=48)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(String, nullable=True)
    target_role = Column(String, nullable=True)
    interview_mode = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_finished = Column(Boolean, default=False)
    chat_history = Column(Text, nullable=False)
    feedback = Column(Text, nullable=True)
    score = Column(Integer, nullable=True)


class ResumeVersion(Base):
    __tablename__ = "resume_versions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    resume_text = Column(Text, nullable=False)
    version_label = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SavedJob(Base):
    __tablename__ = "saved_jobs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(String, nullable=False)
    job_title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String, nullable=True)
    job_url = Column(String, nullable=True)
    saved_at = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(Text, nullable=True)
    stage = Column(String, nullable=True, default="saved")


class PushToken(Base):
    __tablename__ = "push_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String, nullable=False, unique=True)
    device_type = Column(String, nullable=True, default="web")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class JobApplication(Base):
    __tablename__ = "job_applications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(String, nullable=False, index=True)
    company = Column(String, nullable=False)
    title = Column(String, nullable=False)
    location = Column(String, nullable=True)
    job_url = Column(String, nullable=True)
    applied_date = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String, nullable=False, default="pending")  # pending, viewed, rejected, accepted
    cover_letter = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Feedback(Base):
    __tablename__ = "feedbacks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    feedback_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)


class AuthAuditLog(Base):
    __tablename__ = "auth_audit_log"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    event_type = Column(String(50), nullable=False)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    detail = Column(Text, nullable=True)


class TwoFactorBackupCode(Base):
    __tablename__ = "two_factor_backup_codes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code_hash = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    used_at = Column(DateTime(timezone=True), nullable=True)

