"""
Complaint service for handling complaint-related business logic.
"""

import uuid
import io
import os
import time
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

import cloudinary.uploader

from fixmyhyd.models import Complaint, StatusHistory, User
from fixmyhyd.schemas import ComplaintCreate, ComplaintResponse, ComplaintListResponse
from fixmyhyd.constants import COMPLAINT_CATEGORIES
from fixmyhyd.ai.providers.factory import ProviderFactory
from fixmyhyd.ai.prompts import prompt_loader
from fixmyhyd.ai.circuit_breaker import circuit_breaker_manager
from config import settings


class ComplaintService:
    """Service for complaint operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def generate_ghmc_id(self) -> str:
        """Generate unique GHMC complaint ID."""
        # Format: GHMC-YYYYMMDD-XXXX
        date_str = datetime.utcnow().strftime("%Y%m%d")
        random_str = uuid.uuid4().hex[:6].upper()
        return f"GHMC-{date_str}-{random_str}"
    
    def create_complaint(self, complaint_data: ComplaintCreate) -> ComplaintResponse:
        """Create a new complaint with AI processing."""
        ghmc_id = self.generate_ghmc_id()
        
        # Determine user
        user_id = complaint_data.user_id
        if complaint_data.telegram_id:
            user = self.db.query(User).filter(
                User.telegram_id == complaint_data.telegram_id
            ).first()
            if user:
                user_id = user.id
        
        # Read image bytes
        image_bytes = None
        if complaint_data.image:
            image_bytes = complaint_data.image.file.read()
        
        # Read audio bytes
        audio_bytes = None
        if complaint_data.audio:
            audio_bytes = complaint_data.audio.file.read()
        
        # AI Processing
        image_analysis = {}
        voice_transcription = None
        text_analysis = {}
        formal_report = {}
        
        try:
            # Image analysis
            if image_bytes:
                prompt_template = prompt_loader.format_prompt(
                    "image_analysis",
                    categories=prompt_loader.get_categories("image_analysis")
                )
                provider_config = {
                    "name": "gemini",
                    "api_key": settings.GOOGLE_API_KEY_IMAGE,
                    "timeout": settings.GEMINI_TIMEOUT,
                }
                ai_provider = ProviderFactory.create_provider("gemini", provider_config)
                image_analysis = circuit_breaker_manager.call(
                    "gemini",
                    ai_provider.analyze_image,
                    image_bytes,
                    prompt_template
                ) or {}
        except Exception as e:
            print(f"[AI] Image analysis failed: {e}")
        
        try:
            # Audio transcription
            if audio_bytes:
                provider_config = {
                    "name": "groq",
                    "api_key": settings.GROQ_API_KEY,
                    "base_url": settings.GROQ_BASE_URL,
                    "timeout": settings.GROQ_TIMEOUT,
                }
                ai_provider = ProviderFactory.create_provider("groq", provider_config)
                voice_transcription = circuit_breaker_manager.call(
                    "groq",
                    ai_provider.transcribe_audio,
                    audio_bytes
                )
        except Exception as e:
            print(f"[AI] Audio transcription failed: {e}")
        
        # Build full description
        full_description = complaint_data.description or ""
        if voice_transcription:
            full_description += f"\n\n(Voice: {voice_transcription})"
        if not full_description:
            full_description = image_analysis.get("summary", "Civic issue reported via image")
        
        try:
            # Text analysis
            prompt_template = prompt_loader.format_prompt(
                "text_analysis",
                complaint_text=full_description,
                categories=prompt_loader.get_categories("text_analysis")
            )
            provider_config = {
                "name": "gemini",
                "api_key": settings.GOOGLE_API_KEY_TEXT,
                "timeout": settings.GEMINI_TIMEOUT,
            }
            ai_provider = ProviderFactory.create_provider("gemini", provider_config)
            text_analysis = circuit_breaker_manager.call(
                "gemini",
                ai_provider.analyze_text,
                full_description,
                prompt_template
            ) or {}
        except Exception as e:
            print(f"[AI] Text analysis failed: {e}")
        
        try:
            # Formal report generation
            report_prompt = prompt_loader.format_prompt(
                "report_generation",
                image_analysis=image_analysis,
                voice_transcription=voice_transcription or "",
                text_analysis=text_analysis,
                location_text=complaint_data.location or "Not provided"
            )
            provider_config = {
                "name": "gemini",
                "api_key": settings.GROQ_API_KEY,
                "base_url": settings.GROQ_BASE_URL,
                "timeout": settings.GROQ_TIMEOUT,
            }
            ai_provider = ProviderFactory.create_provider("groq", provider_config)
            formal_report = circuit_breaker_manager.call(
                "groq",
                ai_provider.generate_report,
                {
                    "image_analysis": image_analysis,
                    "voice_transcription": voice_transcription or "",
                    "text_analysis": text_analysis,
                    "location_text": complaint_data.location or "Not provided",
                }
            ) or {}
        except Exception as e:
            print(f"[AI] Report generation failed: {e}")
        
        # Determine final values
        final_category = text_analysis.get("category", image_analysis.get("category", "Other"))
        final_priority = text_analysis.get("priority", "Medium")
        subject = formal_report.get("subject", text_analysis.get("summary", "Civic Issue"))
        description = formal_report.get("description", full_description)
        zone = formal_report.get("zone", "Unknown")
        
        # Upload image
        image_path = None
        if image_bytes:
            try:
                safe_id = ghmc_id.replace("/", "_")
                upload_response = cloudinary.uploader.upload(
                    image_bytes,
                    public_id=f"fixmyhyd/{safe_id}",
                    folder="fixmyhyd_complaints",
                    resource_type="auto",
                    format="jpg",
                )
                image_path = upload_response.get("secure_url", upload_response.get("url"))
            except Exception as e:
                print(f"[CLOUDINARY] Upload failed: {e}")
                uploads_dir = os.path.join("static", "uploads")
                os.makedirs(uploads_dir, exist_ok=True)
                image_filename = f"{ghmc_id.replace('/', '_')}.jpg"
                with open(os.path.join(uploads_dir, image_filename), "wb") as f:
                    f.write(image_bytes)
                image_path = f"uploads/{image_filename}"
        
        # Create complaint
        complaint = Complaint(
            ghmc_id=ghmc_id,
            category=final_category,
            priority=final_priority,
            subject=subject[:255] if subject else "Civic Issue",
            description=description,
            location=complaint_data.location,
            zone=zone,
            gps_lat=complaint_data.gps_lat,
            gps_lng=complaint_data.gps_lng,
            status="Submitted",
            submitted_by="Citizen",
            source="bot" if complaint_data.telegram_id else "portal",
            user_id=user_id,
            image_path=image_path,
        )
        
        self.db.add(complaint)
        self.db.commit()
        self.db.refresh(complaint)
        
        # Create initial status history
        status_history = StatusHistory(
            complaint_id=complaint.id,
            old_status=None,
            new_status="Submitted",
            changed_by="System",
            comments="Complaint submitted"
        )
        self.db.add(status_history)
        self.db.commit()
        
        return ComplaintResponse.model_validate(complaint)
    
    def get_complaint(self, complaint_id: int) -> Optional[ComplaintResponse]:
        """Get complaint by ID."""
        complaint = self.db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint:
            return None
        return ComplaintResponse.model_validate(complaint)
    
    def get_complaint_by_ghmc_id(self, ghmc_id: str) -> Optional[ComplaintResponse]:
        """Get complaint by GHMC ID."""
        complaint = self.db.query(Complaint).filter(Complaint.ghmc_id == ghmc_id).first()
        if not complaint:
            return None
        return ComplaintResponse.model_validate(complaint)
    
    def list_complaints(
        self,
        skip: int = 0,
        limit: int = 20,
        user_id: Optional[int] = None,
        status: Optional[str] = None
    ) -> ComplaintListResponse:
        """List complaints with optional filters."""
        query = self.db.query(Complaint)
        
        if user_id:
            query = query.filter(Complaint.user_id == user_id)
        
        if status:
            query = query.filter(Complaint.status == status)
        
        total = query.count()
        complaints = query.order_by(Complaint.created_at.desc()).offset(skip).limit(limit).all()
        
        return ComplaintListResponse(
            complaints=[ComplaintResponse.model_validate(c) for c in complaints],
            total=total,
            skip=skip,
            limit=limit
        )
    
    def get_user_complaints_by_telegram(self, telegram_id: str) -> List[ComplaintResponse]:
        """Get complaints for a Telegram user."""
        user = self.db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            return []
        
        complaints = self.db.query(Complaint).filter(
            Complaint.user_id == user.id
        ).order_by(Complaint.created_at.desc()).limit(20).all()
        
        return [ComplaintResponse.model_validate(c) for c in complaints]
    
    def update_status(
        self,
        complaint_id: int,
        new_status: str,
        comments: Optional[str] = None,
        changed_by: Optional[str] = None
    ) -> Optional[ComplaintResponse]:
        """Update complaint status."""
        complaint = self.db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint:
            return None
        
        old_status = complaint.status
        complaint.status = new_status
        complaint.updated_at = datetime.utcnow()
        
        # Create status history
        status_history = StatusHistory(
            complaint_id=complaint.id,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by or "System",
            comments=comments
        )
        self.db.add(status_history)
        
        self.db.commit()
        self.db.refresh(complaint)
        
        return ComplaintResponse.model_validate(complaint)
    
    def get_complaint_categories(self) -> List[str]:
        """Get available complaint categories."""
        return COMPLAINT_CATEGORIES
