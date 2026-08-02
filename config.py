"""
FixMyHyd Configuration
Handles environment-based configuration for development and production using Pydantic Settings.
"""

import os
from typing import List
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """Application settings using Pydantic for validation."""
    
    # Application
    APP_NAME: str = "FixMyHyd"
    VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv('DEBUG', 'true').lower() == 'true'
    SECRET_KEY: str = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
    
    # Server
    HOST: str = os.getenv('HOST', '0.0.0.0')
    PORT: int = int(os.getenv('PORT', '8000'))
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:5001",
    ]
    
    # Database
    DATABASE_URL: str = os.getenv('DATABASE_URL', '')
    DATABASE_PATH: str = os.getenv('DATABASE_PATH', 'fixmyhyd.db')
    
    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = os.getenv('CLOUDINARY_CLOUD_NAME', '')
    CLOUDINARY_API_KEY: str = os.getenv('CLOUDINARY_API_KEY', '')
    CLOUDINARY_API_SECRET: str = os.getenv('CLOUDINARY_API_SECRET', '')
    
    # AI Providers - Gemini
    GOOGLE_API_KEY_IMAGE: str = os.getenv('GOOGLE_API_KEY_IMAGE', '')
    GOOGLE_API_KEY_AUDIO: str = os.getenv('GOOGLE_API_KEY_AUDIO', '')
    GOOGLE_API_KEY_TEXT: str = os.getenv('GOOGLE_API_KEY_TEXT', '')
    GOOGLE_API_KEY_REPORT: str = os.getenv('GOOGLE_API_KEY_REPORT', '')
    
    # AI Providers - Groq
    GROQ_API_KEY: str = os.getenv('GROQ_API_KEY', '')
    GROQ_BASE_URL: str = os.getenv('GROQ_BASE_URL', 'https://api.groq.com/openai/v1')
    GROQ_TEXT_MODEL: str = os.getenv('GROQ_TEXT_MODEL', 'llama-3.1-8b-instant')
    GROQ_VISION_MODEL: str = os.getenv('GROQ_VISION_MODEL', 'llama-3.2-11b-vision-preview')
    GROQ_AUDIO_MODEL: str = os.getenv('GROQ_AUDIO_MODEL', 'whisper-large-v3')
    
    # AI Timeouts
    GEMINI_TIMEOUT: int = int(os.getenv('GEMINI_TIMEOUT', '25'))
    GROQ_TIMEOUT: int = int(os.getenv('GROQ_TIMEOUT', '25'))
    CLOUDINARY_TIMEOUT: int = int(os.getenv('CLOUDINARY_TIMEOUT', '30'))
    GEOCODE_TIMEOUT: int = int(os.getenv('GEOCODE_TIMEOUT', '8'))
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_BOT_URL: str = os.getenv('TELEGRAM_BOT_URL', 'https://t.me/FixMyHYDbot')
    
    # Celery & Redis
    CELERY_BROKER_URL: str = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND: str = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
    REDIS_URL: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # URLs
    PORTAL_BASE_URL: str = os.getenv('PORTAL_BASE_URL') or os.getenv('RENDER_EXTERNAL_URL') or 'http://localhost:8000'
    
    # Monitoring
    PROMETHEUS_ENABLED: bool = os.getenv('PROMETHEUS_ENABLED', 'false').lower() == 'true'
    PROMETHEUS_PORT: int = int(os.getenv('PROMETHEUS_PORT', '9090'))
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Legacy compatibility
def get_portal_base_url():
    return Settings().PORTAL_BASE_URL


# Create settings instance
settings = Settings()

# Legacy config classes for backward compatibility
class Config:
    """Base configuration (legacy)."""
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    DEBUG = settings.DEBUG
    SECRET_KEY = settings.SECRET_KEY
    PORTAL_BASE_URL = settings.PORTAL_BASE_URL
    PORT = settings.PORT
    DATABASE_URL = settings.DATABASE_URL
    DATABASE_PATH = settings.DATABASE_PATH
    CLOUDINARY_CLOUD_NAME = settings.CLOUDINARY_CLOUD_NAME
    CLOUDINARY_API_KEY = settings.CLOUDINARY_API_KEY
    CLOUDINARY_API_SECRET = settings.CLOUDINARY_API_SECRET
    GOOGLE_API_KEY_IMAGE = settings.GOOGLE_API_KEY_IMAGE
    GOOGLE_API_KEY_AUDIO = settings.GOOGLE_API_KEY_AUDIO
    GOOGLE_API_KEY_TEXT = settings.GOOGLE_API_KEY_TEXT
    GOOGLE_API_KEY_REPORT = settings.GOOGLE_API_KEY_REPORT
    TELEGRAM_BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN
    TELEGRAM_BOT_URL = settings.TELEGRAM_BOT_URL


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = True


# Select configuration based on environment (legacy)
env = os.getenv('FLASK_ENV', 'development')
if env == 'production':
    config = ProductionConfig()
elif env == 'testing':
    config = TestingConfig()
else:
    config = DevelopmentConfig()
