"""
Text processing tasks for Celery.
"""

import logging
from typing import Dict, Any
from celery import shared_task

from fixmyhyd.tasks.celery_app import celery_app
from fixmyhyd.ai.providers.factory import ProviderFactory
from fixmyhyd.ai.circuit_breaker import circuit_breaker_manager
from fixmyhyd.ai.prompts import prompt_loader
from config import settings

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="fixmyhyd.tasks.text_tasks.analyze_text")
def analyze_text_task(self, text: str, provider: str = "gemini") -> Dict[str, Any]:
    """Analyze text using AI provider with circuit breaker protection."""
    try:
        # Load prompt template
        prompt_template = prompt_loader.format_prompt(
            "text_analysis",
            complaint_text=text,
            categories=prompt_loader.get_categories("text_analysis")
        )
        
        # Create provider instance
        provider_config = {
            "name": provider,
            "api_key": settings.GOOGLE_API_KEY_TEXT if provider == "gemini" else settings.GROQ_API_KEY,
            "base_url": settings.GROQ_BASE_URL if provider == "groq" else None,
            "timeout": settings.GEMINI_TIMEOUT if provider == "gemini" else settings.GROQ_TIMEOUT,
        }
        
        ai_provider = ProviderFactory.create_provider(provider, provider_config)
        
        # Execute with circuit breaker
        result = circuit_breaker_manager.call(
            provider,
            ai_provider.analyze_text,
            text,
            prompt_template
        )
        
        logger.info(f"Text analysis completed using {provider}")
        return result
        
    except Exception as e:
        logger.error(f"Text analysis task failed: {e}")
        # Try fallback provider
        if provider == "gemini":
            logger.info("Falling back to Groq for text analysis")
            return analyze_text_task.apply_async(args=[text, "groq"])
        raise


@celery_app.task(bind=True, name="fixmyhyd.tasks.text_tasks.extract_location")
def extract_location_task(self, text: str) -> Dict[str, Any]:
    """Extract location information from text."""
    try:
        from fixmyhyd.services.location_service import LocationService
        from fixmyhyd.database import SessionLocal
        
        with SessionLocal() as db:
            location_service = LocationService(db)
            
            # Try to extract location from text
            # This is a simplified implementation
            # In production, use NER models or more sophisticated geocoding
            
            location_data = {
                "extracted_address": None,
                "confidence": 0.0,
                "suggestions": []
            }
            
            # Simple keyword matching for Hyderabad locations
            hyderabad_keywords = [
                "Hyderabad", "Secunderabad", "Charminar", "Gachibowli",
                "Madhapur", "Banjara Hills", "Jubilee Hills", "Kukatpally"
            ]
            
            found_locations = [loc for loc in hyderabad_keywords if loc.lower() in text.lower()]
            
            if found_locations:
                location_data["extracted_address"] = found_locations[0]
                location_data["confidence"] = 0.7
                location_data["suggestions"] = found_locations
            
            return location_data
            
    except Exception as e:
        logger.error(f"Location extraction failed: {e}")
        return {"extracted_address": None, "confidence": 0.0, "suggestions": []}


@celery_app.task(bind=True, name="fixmyhyd.tasks.text_tasks.classify_priority")
def classify_priority_task(self, text: str, category: str) -> str:
    """Classify complaint priority based on text and category."""
    try:
        # Priority classification logic
        high_priority_keywords = [
            "emergency", "dangerous", "hazard", "accident", "fire",
            "block", "blocked", "overflow", "leak", "broken", "damaged"
        ]
        
        critical_priority_keywords = [
            "life threatening", "immediate", "urgent", "critical",
            "severe", "major", "collapse"
        ]
        
        text_lower = text.lower()
        
        # Check for critical priority
        if any(keyword in text_lower for keyword in critical_priority_keywords):
            return "Critical"
        
        # Check for high priority
        if any(keyword in text_lower for keyword in high_priority_keywords):
            return "High"
        
        # Category-based priority
        high_priority_categories = [
            "Damaged Electrical Infrastructure",
            "Sewage Leak/Overflow"
        ]
        
        if category in high_priority_categories:
            return "High"
        
        # Default to medium
        return "Medium"
        
    except Exception as e:
        logger.error(f"Priority classification failed: {e}")
        return "Medium"
