from invoiceguard.jobs.celery_app import celery_app


@celery_app.task(name="invoiceguard.ping")
def ping() -> str:
    return "pong"
