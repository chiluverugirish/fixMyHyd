"""
Celery application configuration for FixMyHyd.
"""

from celery import Celery
from config import settings

# Create Celery app
celery_app = Celery(
    "fixmyhyd",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "fixmyhyd.tasks.image_tasks",
        "fixmyhyd.tasks.audio_tasks",
        "fixmyhyd.tasks.text_tasks",
        "fixmyhyd.tasks.report_tasks",
    ]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Optional: Configure result expiration
celery_app.conf.result_expires = 3600  # 1 hour

# Optional: Configure task routing
celery_app.conf.task_routes = {
    "fixmyhyd.tasks.image_tasks.*": {"queue": "image_processing"},
    "fixmyhyd.tasks.audio_tasks.*": {"queue": "audio_processing"},
    "fixmyhyd.tasks.text_tasks.*": {"queue": "text_processing"},
    "fixmyhyd.tasks.report_tasks.*": {"queue": "report_generation"},
}

# Optional: Configure task priorities
celery_app.conf.task_default_queue = "default"
celery_app.conf.task_queues = [
    {
        "name": "image_processing",
        "routing_key": "image_processing",
    },
    {
        "name": "audio_processing", 
        "routing_key": "audio_processing",
    },
    {
        "name": "text_processing",
        "routing_key": "text_processing",
    },
    {
        "name": "report_generation",
        "routing_key": "report_generation",
    },
    {
        "name": "default",
        "routing_key": "default",
    },
]
