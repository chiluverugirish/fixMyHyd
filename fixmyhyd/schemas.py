"""
Pydantic schemas for request/response validation.
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Any
from datetime import datetime

try:
    from fastapi import UploadFile
except ImportError:
    UploadFile = Any  # type: ignore


# User schemas
class UserBase(BaseModel):
    """Base user schema."""
    name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None


class UserCreate(UserBase):
    """User creation schema."""
    password: str = Field(..., min_length=6, max_length=100)
    telegram_id: Optional[str] = None


class UserLogin(BaseModel):
    """User login schema."""
    phone: str = Field(..., min_length=10, max_length=20)
    password: str = Field(..., min_length=1)


class UserResponse(UserBase):
    """User response schema."""
    id: int
    telegram_id: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


# Complaint schemas
class ComplaintBase(BaseModel):
    """Base complaint schema."""
    description: str = Field(..., min_length=10, max_length=2000)
    category: Optional[str] = None
    priority: Optional[str] = "Medium"
    subject: Optional[str] = None
    location: Optional[str] = None
    zone: Optional[str] = None
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None


class ComplaintCreate(ComplaintBase):
    """Complaint creation schema."""
    image: Optional[UploadFile] = None
    audio: Optional[UploadFile] = None
    user_id: Optional[int] = None
    telegram_id: Optional[str] = None


class ComplaintResponse(ComplaintBase):
    """Complaint response schema."""
    id: int
    ghmc_id: str
    status: str
    submitted_by: str
    source: str
    user_id: Optional[int] = None
    image_path: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ComplaintListResponse(BaseModel):
    """Complaint list response schema."""
    complaints: List[ComplaintResponse]
    total: int
    skip: int
    limit: int


# Admin schemas
class AdminBase(BaseModel):
    """Base admin schema."""
    username: str = Field(..., min_length=3, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)


class AdminCreate(AdminBase):
    """Admin creation schema."""
    password: str = Field(..., min_length=6, max_length=100)


class AdminResponse(AdminBase):
    """Admin response schema."""
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


# Status history schemas
class StatusHistoryBase(BaseModel):
    """Base status history schema."""
    old_status: Optional[str] = None
    new_status: str
    changed_by: Optional[str] = None
    comments: Optional[str] = None


class StatusHistoryResponse(StatusHistoryBase):
    """Status history response schema."""
    id: int
    complaint_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


# Location schemas
class LocationResponse(BaseModel):
    """Location response schema."""
    address: Optional[str] = None
    zone: Optional[str] = None
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    formatted_address: Optional[str] = None


# AI processing schemas
class ImageAnalysisResult(BaseModel):
    """Image analysis result schema."""
    summary: str
    category: str
    confidence: Optional[float] = None


class AudioTranscriptionResult(BaseModel):
    """Audio transcription result schema."""
    transcript: str
    language: Optional[str] = None
    confidence: Optional[float] = None


class TextAnalysisResult(BaseModel):
    """Text analysis result schema."""
    category: str
    priority: str
    summary: str
    actionable_steps: List[str]


class ReportGenerationResult(BaseModel):
    """Report generation result schema."""
    subject: str
    description: str
    zone: str
