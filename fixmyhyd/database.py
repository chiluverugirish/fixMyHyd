"""
Database connection and session management for FixMyHyd.
Supports both SQLite (development) and PostgreSQL (production).
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from contextlib import contextmanager

from config import settings

# Database URL handling
def get_database_url() -> str:
    """Get the appropriate database URL based on environment."""
    if settings.DATABASE_URL:
        # Convert postgres:// to postgresql:// for SQLAlchemy
        db_url = settings.DATABASE_URL
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return db_url
    
    # Fallback to SQLite for development
    db_path = "/tmp/fixmyhyd.db" if "/opt/render" in os.getcwd() else settings.DATABASE_PATH
    return f"sqlite:///{db_path}"


# Create engine
engine = create_engine(
    get_database_url(),
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def init_db():
    """Initialize database tables."""
    from fixmyhyd.models import User, Admin, Complaint, StatusHistory
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created/verified")


def close_db():
    """Close database connections."""
    engine.dispose()
    print("✅ Database engine disposed")


@contextmanager
def get_db() -> Session:
    """Get database session context manager."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session() -> Session:
    """Get database session dependency for FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
