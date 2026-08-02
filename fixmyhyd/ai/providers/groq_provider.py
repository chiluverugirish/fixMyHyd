"""
Groq AI provider implementation using LangChain.
"""

import json
import base64
import io
from typing import Dict, Any, Optional
import requests
import logging

from ..base import BaseAIProvider

logger = logging.getLogger(__name__)


class GroqProvider(BaseAIProvider):
    """Groq AI provider implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize Groq provider."""
        super().__init__(config)
        self._validate_config(["api_key", "base_url"])
        
        self.api_key = config["api_key"]
        self.base_url = config["base_url"]
        self.text_model = config.get("text_model", "llama-3.1-8b-instant")
        self.vision_model = config.get("vision_model", "llama-3.2-11b-vision-preview")
        self.audio_model = config.get("audio_model", "whisper-large-v3")
        self.timeout = config.get("timeout", 25)
    
    def analyze_image(self, image_bytes: bytes, prompt: str) -> Dict[str, Any]:
        """Analyze image using Groq vision model."""
        try:
            # Encode image to base64
            image_data = base64.b64encode(image_bytes).decode("utf-8")
            
            # Prepare messages
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                        },
                    ],
                }
            ]
            
            # Make API call
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.vision_model,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": 256,
                    "response_format": {"type": "json_object"},
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            
            # Parse response
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Parse JSON
            try:
                result = json.loads(content.replace("```json", "").replace("```", "").strip())
            except json.JSONDecodeError:
                result = {
                    "summary": content,
                    "category": "Other",
                    "confidence": 0.5
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Groq image analysis error: {e}")
            raise
    
    def transcribe_audio(self, audio_bytes: bytes, language: str = "en") -> str:
        """Transcribe audio using Groq Whisper."""
        try:
            # Determine MIME type
            # For simplicity, assuming OGG format (Telegram default)
            files = {
                "file": ("audio.ogg", io.BytesIO(audio_bytes), "audio/ogg")
            }
            data = {"model": self.audio_model}
            
            # Make API call
            response = requests.post(
                f"{self.base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                files=files,
                data=data,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            # Parse response
            data = response.json()
            transcript = data.get("text") or data.get("transcript", "")
            
            return str(transcript).strip() if transcript else ""
            
        except Exception as e:
            logger.error(f"Groq audio transcription error: {e}")
            raise
    
    def analyze_text(self, text: str, prompt: str) -> Dict[str, Any]:
        """Analyze text using Groq."""
        try:
            messages = [{"role": "user", "content": prompt + f"\n\nText: {text}"}]
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.text_model,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": 512,
                    "response_format": {"type": "json_object"},
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            
            # Parse response
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Parse JSON
            try:
                result = json.loads(content.replace("```json", "").replace("```", "").strip())
            except json.JSONDecodeError:
                result = {
                    "category": "Other",
                    "priority": "Medium",
                    "summary": content,
                    "actionable_steps": []
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Groq text analysis error: {e}")
            raise
    
    def generate_report(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate formal report using Groq."""
        try:
            prompt = self._build_report_prompt(data)
            messages = [{"role": "user", "content": prompt}]
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.text_model,
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 512,
                    "response_format": {"type": "json_object"},
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            
            # Parse response
            response_data = response.json()
            content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Parse JSON
            try:
                result = json.loads(content.replace("```json", "").replace("```", "").strip())
            except json.JSONDecodeError:
                result = {
                    "subject": data.get("subject", "Civic Complaint"),
                    "description": content,
                    "zone": "Unknown"
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Groq report generation error: {e}")
            raise
    
    def health_check(self) -> bool:
        """Check if Groq provider is healthy."""
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.text_model,
                    "messages": [{"role": "user", "content": "Health check"}],
                    "max_tokens": 10,
                },
                timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Groq health check failed: {e}")
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
