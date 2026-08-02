"""
Audio processing tasks for Celery.
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


@celery_app.task(bind=True, name="fixmyhyd.tasks.audio_tasks.transcribe_audio")
def transcribe_audio_task(self, audio_bytes: bytes, language: str = "en", provider: str = "groq") -> str:
    """Transcribe audio using AI provider with circuit breaker protection."""
    try:
        # Load prompt template
        prompt_template = prompt_loader.format_prompt(
            "audio_transcription",
            language=language
        )
        
        # Create provider instance
        provider_config = {
            "name": provider,
            "api_key": settings.GROQ_API_KEY,
            "base_url": settings.GROQ_BASE_URL,
            "timeout": settings.GROQ_TIMEOUT,
        }
        
        ai_provider = ProviderFactory.create_provider(provider, provider_config)
        
        # Execute with circuit breaker
        result = circuit_breaker_manager.call(
            provider,
            ai_provider.transcribe_audio,
            audio_bytes,
            language
        )
        
        logger.info(f"Audio transcription completed using {provider}")
        return result
        
    except Exception as e:
        logger.error(f"Audio transcription task failed: {e}")
        # For audio, Groq is the primary choice (Whisper)
        # Could fallback to other providers in future
        raise


@celery_app.task(bind=True, name="fixmyhyd.tasks.audio_tasks.process_voice_note")
def process_voice_note_task(self, audio_bytes: bytes, language: str = "en") -> Dict[str, Any]:
    """Process voice note with transcription and sentiment analysis."""
    try:
        # Transcribe audio
        transcription = transcribe_audio_task(audio_bytes, language)
        
        # Additional processing could be added here:
        # - Sentiment analysis
        # - Language detection
        # - Speaker identification
        
        return {
            "transcription": transcription,
            "language": language,
            "status": "completed"
        }
        
    except Exception as e:
        logger.error(f"Voice note processing failed: {e}")
        raise
