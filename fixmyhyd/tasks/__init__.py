"""
Celery task definitions for FixMyHyd async processing.
"""

from .celery_app import celery_app

__all__ = ["celery_app"]
