#!/bin/bash
# Avvia Celery worker in background
celery -A backend.celery_app worker --loglevel=info --concurrency=2 &
# Avvia uvicorn
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 2 --access-log
