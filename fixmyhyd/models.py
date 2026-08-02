"""
SQLAlchemy ORM models for FixMyHyd.
"""

from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from fixmyhyd.database import Base


class User(Base):
    """User model for citizen accounts."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=True, index=True)
    password_hash = Column(String, nullable=True)
    name = Column(String, nullable=False)
    phone = Column(String, unique=True, nullable=True, index=True)
    telegram_id = Column(String, unique=True, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    complaints = relationship("Complaint", back_populates="user")


class Admin(Base):
    """Admin model for administrative accounts."""
    __tablename__ = "admins"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Complaint(Base):
    """Complaint model for civic issues."""
    __tablename__ = "complaints"
    
    id = Column(Integer, primary_key=True, index=True)
    ghmc_id = Column(String, unique=True, nullable=False, index=True)
    category = Column(String, nullable=False)
    priority = Column(String, default="Medium")
    subject = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    location = Column(Text, nullable=True)
    zone = Column(String, nullable=True)
    gps_lat = Column(Float, nullable=True)
    gps_lng = Column(Float, nullable=True)
    status = Column(String, default="Submitted")
    submitted_by = Column(String, default="Citizen")
    source = Column(String, default="portal")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    image_path = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="complaints")
    status_history = relationship("StatusHistory", back_populates="complaint")


class StatusHistory(Base):
    """Status history model for tracking complaint status changes."""
    __tablename__ = "status_history"
    
    id = Column(Integer, primary_key=True, index=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id"), nullable=False)
    old_status = Column(String, nullable=True)
    new_status = Column(String, nullable=False)
    changed_by = Column(String, nullable=True)
    comments = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    complaint = relationship("Complaint", back_populates="status_history")
