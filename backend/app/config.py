import os
from pathlib import Path
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DEBUG: bool = False

    @field_validator("DEBUG", mode="before")
    def parse_debug(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on", "t"}:
                return True
            if normalized in {"0", "false", "no", "n", "off", "f", "release", "prod", "production"}:
                return False
        return value

    @model_validator(mode="after")
    def validate_production_security(self):
        env = self.ENVIRONMENT.lower()
        if env in {"production", "prod"}:
            key = self.SECRET_KEY
            if len(key) < 32:
                raise ValueError("SECRET_KEY must be at least 32 characters long in production.")
            forbidden_substrings = ["test", "secret", "changeme", "dev", "example", "default"]
            if any(sub in key.lower() for sub in forbidden_substrings):
                raise ValueError("SECRET_KEY contains insecure placeholder substring in production environment.")
        return self
    
    # JWT authentication
    # Must be set in backend/.env.
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # Short-lived access token (15 minutes)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30    # Long-lived refresh token (30 days)

    # Ollama Local LLM
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"

    # Gemini Cloud LLM
    LLM_PROVIDER: str = "ollama"  # "ollama" or "gemini"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # Database
    CHROMA_PATH: str = "./data/chroma_db"
    # PostgreSQL database URL (Neon compatible). Must be set in backend/.env.
    DATABASE_URL: str
    
    # Upload folder
    UPLOAD_DIR: str = "./uploads"
    
    # Environment
    ENVIRONMENT: str = "development"
    
    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"
    
    # Email Service (Resend) - https://resend.com
    RESEND_API_KEY: str = ""
    FRONTEND_URL: str = "http://localhost:3000"
    
    # SMTP Email Configuration
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""  # Gmail address
    SMTP_PASSWORD: str = ""  # Gmail app password
    EMAIL_FROM: str = "noreply@cognis.ai"
    
    # Email Token Settings
    EMAIL_VERIFICATION_EXPIRY_HOURS: int = 24
    PASSWORD_RESET_EXPIRY_MINUTES: int = 15

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

# Ensure directories exist
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.CHROMA_PATH).mkdir(parents=True, exist_ok=True)
# NOTE: database will be managed externally (PostgreSQL/Neon). Do not create local sqlite path.
