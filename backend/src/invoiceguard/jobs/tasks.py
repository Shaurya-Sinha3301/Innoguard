import uuid

from invoiceguard.config import settings
from invoiceguard.db.session import SessionLocal
from invoiceguard.jobs.celery_app import celery_app
from invoiceguard.jobs.extract_job import JobOutcome, run_extraction_job
from invoiceguard.jobs.extractor_factory import build_extractor


@celery_app.task(name="invoiceguard.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="invoiceguard.extract", bind=True, max_retries=None)
def extract_invoice(self, case_id: str) -> str:
    attempt = self.request.retries + 1
    outcome = run_extraction_job(
        SessionLocal,
        uuid.UUID(case_id),
        build_extractor(),
        attempt=attempt,
        max_attempts=settings.extraction_max_attempts,
    )
    if outcome is JobOutcome.RETRY:
        raise self.retry(countdown=min(2**attempt, 60))
    return outcome.value


def publish(topic: str, payload: dict, message_id: int) -> None:
    """Outbox publisher. retry=False makes a broker outage fail fast, so the outbox keeps
    the row and tries again later instead of blocking the dispatcher."""
    if topic != "invoice.extract":
        raise ValueError(f"unknown topic {topic}")
    extract_invoice.apply_async(
        args=[payload["case_id"]], task_id=f"outbox-{message_id}", retry=False
    )
