#!/bin/sh
# Start-up for the hosted free-plan container: migrate, then run the outbox dispatcher and
# the Celery worker in the background and the API in the foreground. Render has no free
# plan for background workers, so all three share one free web service.
set -e

alembic upgrade head

python -m invoiceguard.jobs.dispatcher &
celery -A invoiceguard.jobs.celery_app worker --pool=solo --loglevel=info &

exec uvicorn invoiceguard.api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
