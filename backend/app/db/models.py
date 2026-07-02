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
