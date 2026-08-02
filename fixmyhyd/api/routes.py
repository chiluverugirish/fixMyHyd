"""
API routes for FixMyHyd FastAPI application.
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional
import logging

from fixmyhyd.database import get_db_session
from fixmyhyd.models import User, Complaint, StatusHistory
from fixmyhyd.schemas import (
    ComplaintCreate, ComplaintResponse, ComplaintListResponse,
    UserCreate, UserResponse, UserLogin
)
from fixmyhyd.services.user_service import UserService
from fixmyhyd.services.complaint_service import ComplaintService
from fixmyhyd.services.location_service import LocationService
from fixmyhyd.constants import COMPLAINT_CATEGORIES

logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/v1", tags=["API"])


# Health check
@api_router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "1.0.0"}


# User endpoints
@api_router.post("/users/register", response_model=UserResponse)
async def register_user(user_data: UserCreate, db: Session = Depends(get_db_session)):
    """Register a new user."""
    try:
        user_service = UserService(db)
        user = user_service.create_user(user_data)
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"User registration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@api_router.post("/users/login")
async def login_user(user_data: UserLogin, db: Session = Depends(get_db_session)):
    """Login user and return token."""
    try:
        user_service = UserService(db)
        token = user_service.authenticate_user(user_data.phone, user_data.password)
        if not token:
            raise HTTPException(
                status_code=401,
                detail="Invalid phone number or password"
            )
        return {"access_token": token, "token_type": "bearer"}
    except Exception as e:
        logger.error(f"User login error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Complaint endpoints
@api_router.post("/complaints", response_model=ComplaintResponse)
async def create_complaint(
    image: UploadFile = File(...),
    description: str = Form(...),
    audio: Optional[UploadFile] = File(None),
    device_lat: Optional[float] = Form(None),
    device_lng: Optional[float] = Form(None),
    location_text: Optional[str] = Form(None),
    user_id: Optional[int] = Form(None),
    telegram_id: Optional[str] = Form(None),
    db: Session = Depends(get_db_session)
):
    """Create a new complaint with AI processing."""
    try:
        complaint_service = ComplaintService(db)
        location_service = LocationService(db)
        
        # Process location
        location_data = await location_service.process_location(
            device_lat, device_lng, location_text
        )
        
        # Create complaint data
        complaint_data = ComplaintCreate(
            description=description,
            image=image,
            audio=audio,
            **location_data,
            user_id=user_id,
            telegram_id=telegram_id
        )
        
        # Process complaint with AI
        complaint = await complaint_service.create_complaint(complaint_data)
        return complaint
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Complaint creation error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@api_router.get("/complaints", response_model=ComplaintListResponse)
async def list_complaints(
    skip: int = 0,
    limit: int = 20,
    user_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db_session)
):
    """List complaints with optional filters."""
    try:
        complaint_service = ComplaintService(db)
        complaints = complaint_service.list_complaints(
            skip=skip, limit=limit, user_id=user_id, status=status
        )
        return complaints
    except Exception as e:
        logger.error(f"Complaint list error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@api_router.get("/complaints/{complaint_id}", response_model=ComplaintResponse)
async def get_complaint(complaint_id: int, db: Session = Depends(get_db_session)):
    """Get a specific complaint by ID."""
    try:
        complaint_service = ComplaintService(db)
        complaint = complaint_service.get_complaint(complaint_id)
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")
        return complaint
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Complaint retrieval error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@api_router.patch("/complaints/{complaint_id}/status")
async def update_complaint_status(
    complaint_id: int,
    new_status: str,
    comments: Optional[str] = None,
    changed_by: Optional[str] = None,
    db: Session = Depends(get_db_session)
):
    """Update complaint status."""
    try:
        complaint_service = ComplaintService(db)
        complaint = complaint_service.update_status(
            complaint_id, new_status, comments, changed_by
        )
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")
        return complaint
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Status update error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Telegram bot endpoints
@api_router.post("/bot/register-user")
async def bot_register_user(
    telegram_id: str,
    name: str,
    username: Optional[str] = None,
    phone: Optional[str] = None,
    db: Session = Depends(get_db_session)
):
    """Register or link user from Telegram bot."""
    try:
        user_service = UserService(db)
        result = user_service.register_telegram_user(
            telegram_id, name, username, phone
        )
        return result
    except Exception as e:
        logger.error(f"Bot user registration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@api_router.post("/bot/submit-complaint")
async def bot_submit_complaint(
    image: UploadFile = File(...),
    telegram_id: str = Form(...),
    description: str = Form(default=""),
    audio: Optional[UploadFile] = File(None),
    gps_lat: Optional[float] = Form(None),
    gps_lng: Optional[float] = Form(None),
    location_text: Optional[str] = Form(None),
    db: Session = Depends(get_db_session)
):
    """Submit complaint from Telegram bot."""
    try:
        complaint_service = ComplaintService(db)
        location_service = LocationService(db)
        
        # Process location
        location_data = await location_service.process_location(
            gps_lat, gps_lng, location_text
        )
        
        # Create complaint
        complaint_data = ComplaintCreate(
            description=description,
            image=image,
            audio=audio,
            **location_data,
            telegram_id=telegram_id
        )
        
        complaint = await complaint_service.create_complaint(complaint_data)
        return complaint
        
    except Exception as e:
        logger.error(f"Bot complaint submission error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@api_router.get("/bot/user-complaints/{telegram_id}")
async def bot_user_complaints(telegram_id: str, db: Session = Depends(get_db_session)):
    """Get complaints for a Telegram user."""
    try:
        complaint_service = ComplaintService(db)
        complaints = complaint_service.get_user_complaints_by_telegram(telegram_id)
        return {"complaints": complaints}
    except Exception as e:
        logger.error(f"Bot user complaints error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@api_router.post("/bot/reset-password")
async def bot_reset_password(telegram_id: str, db: Session = Depends(get_db_session)):
    """Reset password for Telegram user."""
    try:
        user_service = UserService(db)
        result = user_service.reset_password_telegram(telegram_id)
        return result
    except Exception as e:
        logger.error(f"Bot password reset error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
