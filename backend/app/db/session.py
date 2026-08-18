from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings


# Use a synchronous SQLAlchemy engine with connection pooling for Neon/Postgres
ENGINE_URL = settings.DATABASE_URL

# If a modern psycopg (v3) driver is installed, prefer the 'psycopg' SQLAlchemy
# dialect by ensuring the URL scheme includes '+psycopg'. This avoids SQLAlchemy
# trying to import the legacy 'psycopg2' module when the plain 'postgresql://'
# scheme is used.
if ENGINE_URL and ENGINE_URL.startswith("postgresql://") and "+" not in ENGINE_URL:
    try:
        import psycopg  # type: ignore
        ENGINE_URL = ENGINE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    except Exception:
        # psycopg not available; leave URL as-is so SQLAlchemy will attempt
        # to use psycopg2 if present.
        pass

if ENGINE_URL.startswith("sqlite"):
    engine = create_engine(
        ENGINE_URL,
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )
else:
    engine = create_engine(
        ENGINE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        future=True,
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()


def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
