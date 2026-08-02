"""
Base AI provider interface for LangChain integration.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from PIL import Image
import io


class BaseAIProvider(ABC):
    """Abstract base class for AI providers."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize provider with configuration."""
        self.config = config
        self.name = config.get("name", "unknown")
    
    def analyze_image(self, image_bytes: bytes, prompt: str) -> Dict[str, Any]:
        """Analyze image and return structured results."""
        pass
    
    def transcribe_audio(self, audio_bytes: bytes, language: str = "en") -> str:
        """Transcribe audio to text."""
        pass
    
    def analyze_text(self, text: str, prompt: str) -> Dict[str, Any]:
        """Analyze text and return structured results."""
        pass
    
    def generate_report(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate formal report from structured data."""
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """Check if provider is healthy and accessible."""
        pass
    
    def _load_image(self, image_bytes: bytes) -> Image.Image:
        """Load image from bytes."""
        return Image.open(io.BytesIO(image_bytes))
    
    def _validate_config(self, required_keys: List[str]):
        """Validate that required configuration keys are present."""
        missing_keys = [key for key in required_keys if key not in self.config]
        if missing_keys:
            raise ValueError(f"Missing required config keys: {missing_keys}")
