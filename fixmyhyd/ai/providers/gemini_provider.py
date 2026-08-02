"""
Gemini AI provider implementation using LangChain.
"""

import json
import base64
import io
from typing import Dict, Any, Optional
from PIL import Image
import logging

from google import genai
from google.genai import types as genai_types

from ..base import BaseAIProvider

logger = logging.getLogger(__name__)


class GeminiProvider(BaseAIProvider):
    """Gemini AI provider implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize Gemini provider."""
        super().__init__(config)
        self._validate_config(["api_key"])
        
        self.client = genai.Client(api_key=config["api_key"])
        self.model = config.get("model", "gemini-2.0-flash-lite")
        self.timeout = config.get("timeout", 25)
    
    def analyze_image(self, image_bytes: bytes, prompt: str) -> Dict[str, Any]:
        """Analyze image using Gemini vision model."""
        try:
            # Load image
            image = Image.open(io.BytesIO(image_bytes))
            
            # Prepare content
            content = [
                prompt,
                image
            ]
            
            # Generate response
            response = self.client.models.generate_content(
                model=self.model,
                contents=content,
                generation_config=genai_types.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=256,
                )
            )
            
            # Parse response
            text = response.text if response.text else ""
            
            # Try to parse as JSON
            try:
                result = json.loads(text.replace("```json", "").replace("```", "").strip())
            except json.JSONDecodeError:
                # Fallback to text response
                result = {
                    "summary": text,
                    "category": "Other",
                    "confidence": 0.5
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Gemini image analysis error: {e}")
            raise
    
    def transcribe_audio(self, audio_bytes: bytes, language: str = "en") -> str:
        """Transcribe audio using Gemini."""
        try:
            # For now, Gemini doesn't have dedicated audio transcription
            # This is a placeholder - in production, use Whisper or similar
            logger.warning("Gemini audio transcription not fully implemented")
            return "Audio transcription placeholder"
            
        except Exception as e:
            logger.error(f"Gemini audio transcription error: {e}")
            raise
    
    def analyze_text(self, text: str, prompt: str) -> Dict[str, Any]:
        """Analyze text using Gemini."""
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt + f"\n\nText: {text}",
                generation_config=genai_types.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=512,
                )
            )
            
            # Parse response
            text_response = response.text if response.text else ""
            
            # Try to parse as JSON
            try:
                result = json.loads(text_response.replace("```json", "").replace("```", "").strip())
            except json.JSONDecodeError:
                # Fallback to text response
                result = {
                    "category": "Other",
                    "priority": "Medium",
                    "summary": text_response,
                    "actionable_steps": []
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Gemini text analysis error: {e}")
            raise
    
    def generate_report(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate formal report using Gemini."""
        try:
            prompt = self._build_report_prompt(data)
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                generation_config=genai_types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=512,
                )
            )
            
            # Parse response
            text_response = response.text if response.text else ""
            
            # Try to parse as JSON
            try:
                result = json.loads(text_response.replace("```json", "").replace("```", "").strip())
            except json.JSONDecodeError:
                # Fallback to structured response
                result = {
                    "subject": data.get("subject", "Civic Complaint"),
                    "description": text_response,
                    "zone": "Unknown"
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Gemini report generation error: {e}")
            raise
    
    def health_check(self) -> bool:
        """Check if Gemini provider is healthy."""
        try:
            # Simple health check by generating minimal content
            response = self.client.models.generate_content(
                model=self.model,
                contents="Health check",
                generation_config=genai_types.GenerationConfig(
                    max_output_tokens=10,
                )
            )
            return response.text is not None
        except Exception as e:
            logger.error(f"Gemini health check failed: {e}")
            return False
    
    def _build_report_prompt(self, data: Dict[str, Any]) -> str:
        """Build prompt for report generation."""
        return f"""You are an AI assistant for GHMC Hyderabad. Synthesize this information into a structured formal complaint.
Return ONLY a valid JSON object with: "subject", "description", "zone" (Hyderabad zone if determinable, else "Unknown").
Data:
- Image Analysis: {data.get('image_analysis')}
- Voice Transcription: {data.get('voice_transcription')}
- Text Analysis: {data.get('text_analysis')}
- Location: {data.get('location_text', 'Not provided')}"""
