# FixMyHyd Procfile for architecture upgrade v1.0.0
# Using FastAPI with Uvicorn workers instead of Flask + Gunicorn

# Web service (FastAPI)
web: uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2 --worker-class uvicorn.workers.UvicornWorker

# Telegram bot worker
worker: python bot.py

# Celery worker (optional - can be run separately)
# celery: celery -A fixmyhyd.tasks.celery_app worker --loglevel=info --concurrency=2
