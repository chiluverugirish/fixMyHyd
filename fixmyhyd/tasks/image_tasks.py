"""
Image processing tasks for Celery.
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


@celery_app.task(bind=True, name="fixmyhyd.tasks.image_tasks.analyze_image")
def analyze_image_task(self, image_bytes: bytes, provider: str = "gemini") -> Dict[str, Any]:
    """Analyze image using AI provider with circuit breaker protection."""
    try:
        # Load prompt template
        prompt_template = prompt_loader.format_prompt(
            "image_analysis",
            categories=prompt_loader.get_categories("image_analysis")
        )
        
        # Create provider instance
        provider_config = {
            "name": provider,
            "api_key": settings.GOOGLE_API_KEY_IMAGE if provider == "gemini" else settings.GROQ_API_KEY,
            "base_url": settings.GROQ_BASE_URL if provider == "groq" else None,
            "timeout": settings.GEMINI_TIMEOUT if provider == "gemini" else settings.GROQ_TIMEOUT,
        }
        
        ai_provider = ProviderFactory.create_provider(provider, provider_config)
        
        # Execute with circuit breaker
        result = circuit_breaker_manager.call(
            provider,
            ai_provider.analyze_image,
            image_bytes,
            prompt_template
        )
        
        logger.info(f"Image analysis completed using {provider}")
        return result
        
    except Exception as e:
        logger.error(f"Image analysis task failed: {e}")
        # Try fallback provider
        if provider == "gemini":
            logger.info("Falling back to Groq for image analysis")
            return analyze_image_task.apply_async(args=[image_bytes, "groq"])
        raise


@celery_app.task(bind=True, name="fixmyhyd.tasks.image_tasks.extract_exif")
def extract_exif_task(self, image_bytes: bytes) -> Dict[str, Any]:
    """Extract EXIF data from image."""
    try:
        from PIL import Image
        import io
        from PIL.ExifTags import TAGS
        
        image = Image.open(io.BytesIO(image_bytes))
        exif_data = {}
        
        if hasattr(image, '_getexif'):
            exif_info = image._getexif()
            if exif_info:
                for tag, value in exif_info.items():
                    decoded = TAGS.get(tag, tag)
                    exif_data[decoded] = value
        
        # Extract GPS data if available
        gps_data = {}
        if 'GPSInfo' in exif_data:
            # Simplified GPS extraction
            # In production, use proper GPS parsing library
            gps_data = {'raw': str(exif_data['GPSInfo'])}
        
        return {
            "exif": exif_data,
            "gps": gps_data,
            "has_gps": bool(gps_data)
        }
        
    except Exception as e:
        logger.error(f"EXIF extraction failed: {e}")
        return {"exif": {}, "gps": {}, "has_gps": False}
