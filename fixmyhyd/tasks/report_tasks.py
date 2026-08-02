"""
Report generation tasks for Celery.
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


@celery_app.task(bind=True, name="fixmyhyd.tasks.report_tasks.generate_report")
def generate_report_task(
    self,
    image_analysis: Dict[str, Any],
    voice_transcription: str,
    text_analysis: Dict[str, Any],
    location_text: str,
    provider: str = "gemini"
) -> Dict[str, Any]:
    """Generate formal report using AI provider with circuit breaker protection."""
    try:
        # Load prompt template
        prompt_template = prompt_loader.format_prompt(
            "report_generation",
            image_analysis=image_analysis,
            voice_transcription=voice_transcription,
            text_analysis=text_analysis,
            location_text=location_text
        )
        
        # Create provider instance
        provider_config = {
            "name": provider,
            "api_key": settings.GOOGLE_API_KEY_REPORT if provider == "gemini" else settings.GROQ_API_KEY,
            "base_url": settings.GROQ_BASE_URL if provider == "groq" else None,
            "timeout": settings.GEMINI_TIMEOUT if provider == "gemini" else settings.GROQ_TIMEOUT,
        }
        
        ai_provider = ProviderFactory.create_provider(provider, provider_config)
        
        # Prepare data for report generation
        data = {
            "image_analysis": image_analysis,
            "voice_transcription": voice_transcription,
            "text_analysis": text_analysis,
            "location_text": location_text
        }
        
        # Execute with circuit breaker
        result = circuit_breaker_manager.call(
            provider,
            ai_provider.generate_report,
            data
        )
        
        logger.info(f"Report generation completed using {provider}")
        return result
        
    except Exception as e:
        logger.error(f"Report generation task failed: {e}")
        # Try fallback provider
        if provider == "gemini":
            logger.info("Falling back to Groq for report generation")
            return generate_report_task.apply_async(
                args=[image_analysis, voice_transcription, text_analysis, location_text, "groq"]
            )
        raise


@celery_app.task(bind=True, name="fixmyhyd.tasks.report_tasks.process_complaint")
def process_complaint_task(
    self,
    complaint_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Process complete complaint with all AI tasks."""
    try:
        from fixmyhyd.tasks.image_tasks import analyze_image_task, extract_exif_task
        from fixmyhyd.tasks.audio_tasks import transcribe_audio_task
        from fixmyhyd.tasks.text_tasks import analyze_text_task, classify_priority_task
        
        results = {
            "status": "processing",
            "steps": {}
        }
        
        # Step 1: Extract EXIF data if image provided
        if complaint_data.get("image_bytes"):
            results["steps"]["exif"] = extract_exif_task(complaint_data["image_bytes"])
            
            # Step 2: Analyze image
            results["steps"]["image_analysis"] = analyze_image_task(complaint_data["image_bytes"])
        
        # Step 3: Transcribe audio if provided
        if complaint_data.get("audio_bytes"):
            results["steps"]["audio_transcription"] = transcribe_audio_task(complaint_data["audio_bytes"])
        
        # Step 4: Analyze text description
        if complaint_data.get("description"):
            results["steps"]["text_analysis"] = analyze_text_task(complaint_data["description"])
            
            # Step 5: Classify priority
            category = results["steps"].get("image_analysis", {}).get("category", "Other")
            results["steps"]["priority"] = classify_priority_task(complaint_data["description"], category)
        
        # Step 6: Generate final report
        report_data = {
            "image_analysis": results["steps"].get("image_analysis", {}),
            "voice_transcription": results["steps"].get("audio_transcription", ""),
            "text_analysis": results["steps"].get("text_analysis", {}),
            "location_text": complaint_data.get("location_text", "")
        }
        
        results["steps"]["report"] = generate_report_task(report_data)
        
        results["status"] = "completed"
        logger.info("Complaint processing completed successfully")
        
        return results
        
    except Exception as e:
        logger.error(f"Complaint processing failed: {e}")
        results["status"] = "failed"
        results["error"] = str(e)
        raise
