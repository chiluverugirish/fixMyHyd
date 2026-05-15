"""
FixMyHyd Configuration
Handles environment-based configuration for development and production.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Base configuration."""
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    DEBUG = FLASK_ENV == 'development'
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
    PORTAL_BASE_URL = os.getenv('PORTAL_BASE_URL', 'http://localhost:5001')
    PORT = int(os.getenv('PORT', 5001))
    
    # Database
    DATABASE_URL = os.getenv('DATABASE_URL', '')
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'fixmyhyd.db')
    
    # Cloudinary
    CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET')
    
    # Gemini API Keys
    GOOGLE_API_KEY_IMAGE = os.getenv('GOOGLE_API_KEY_IMAGE')
    GOOGLE_API_KEY_AUDIO = os.getenv('GOOGLE_API_KEY_AUDIO')
    GOOGLE_API_KEY_TEXT = os.getenv('GOOGLE_API_KEY_TEXT')
    GOOGLE_API_KEY_REPORT = os.getenv('GOOGLE_API_KEY_REPORT')
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_BOT_URL = os.getenv('TELEGRAM_BOT_URL', 'https://t.me/FixMyHYDbot')


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration for Render."""
    DEBUG = False
    TESTING = False
    # Ensure production settings are secure
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = True


# Select configuration based on environment
env = os.getenv('FLASK_ENV', 'development')
if env == 'production':
    config = ProductionConfig()
elif env == 'testing':
    config = TestingConfig()
else:
    config = DevelopmentConfig()
