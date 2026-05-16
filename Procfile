# Gunicorn settings for stability:
# - workers: 2 (Render free tier safe)
# - threads: 4 (handles concurrent requests without blocking)
# - timeout: 120 (gives time for AI + Cloudinary processing)
# - keep-alive: 5 (reuse connections)
# - worker-class: gthread (threaded workers)
web: gunicorn app:app --workers 2 --threads 4 --timeout 120 --keep-alive 5 --worker-class gthread --bind 0.0.0.0:$PORT
worker: python bot.py
