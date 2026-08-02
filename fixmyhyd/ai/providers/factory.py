"""
Factory for creating AI provider instances.
"""

from typing import Dict, Any, Optional
from ..base import BaseAIProvider
from .gemini_provider import GeminiProvider
from .groq_provider import GroqProvider


class ProviderFactory:
    """Factory for creating AI provider instances."""
    
    _providers = {
        "gemini": GeminiProvider,
        "groq": GroqProvider,
    }
    
    @classmethod
    def create_provider(cls, provider_name: str, config: Dict[str, Any]) -> BaseAIProvider:
        """Create a provider instance by name."""
        provider_class = cls._providers.get(provider_name.lower())
        if not provider_class:
            raise ValueError(f"Unknown provider: {provider_name}. Available: {list(cls._providers.keys())}")
        
        return provider_class(config)
    
    @classmethod
    def register_provider(cls, name: str, provider_class: type):
        """Register a new provider class."""
        cls._providers[name.lower()] = provider_class
    
    @classmethod
    def get_available_providers(cls) -> list:
        """Get list of available provider names."""
        return list(cls._providers.keys())
