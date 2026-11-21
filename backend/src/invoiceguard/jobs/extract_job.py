"""The extraction job, written without Celery so it can be tested directly.

It is idempotent: a duplicate delivery of the same job finds the invoice past extraction
and does nothing. Transient model failures are retried; permanent ones, or transient ones
that exhaust their attempts, park the invoice in the dead-letter table for a human.
"""

import uuid
from enum import StrEnum

from sqlalchemy.orm import sessionmaker

from invoiceguard.extraction.client import (
    ExtractionError,
    Extractor,
    TransientExtractionError,
)
from invoiceguard.extraction.service import (
    complete_extraction,
    document_bytes,
    fail_extraction,
)
from invoiceguard.workflow.errors import IllegalTransition, InvoiceNotFound
from invoiceguard.workflow.service import SYSTEM, lock_invoice, transition
from invoiceguard.workflow.state_machine import InvoiceState as S


class JobOutcome(StrEnum):
    DONE = "DONE"
    RETRY = "RETRY"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


def run_extraction_job(
    session_factory: sessionmaker,
    case_id: uuid.UUID,
    extractor: Extractor,
    *,
    attempt: int,
    max_attempts: int,
) -> JobOutcome:
    with session_factory() as session:
        try:
            row = lock_invoice(session, case_id)
        except InvoiceNotFound:
            return JobOutcome.SKIPPED
        status = S(row.status)
        if status not in (S.RECEIVED, S.EXTRACTING):
            return JobOutcome.SKIPPED  # already extracted: a duplicate delivery
        if status is S.RECEIVED:
            transition(session, row, S.EXTRACTING, actor=SYSTEM)
        # EXTRACTING means a retry, or a redelivery after a worker crash.
        pdf = document_bytes(session, case_id)
        session.commit()

    # The model call runs outside any database transaction.
    try:
        response = extractor.extract(pdf)
    except ExtractionError as exc:
        return _fail(session_factory, case_id, str(exc), attempt)
    except (TransientExtractionError, OSError, TimeoutError) as exc:
        if attempt < max_attempts:
            return JobOutcome.RETRY
        return _fail(
            session_factory, case_id, f"retries exhausted after {attempt}: {exc}", attempt
        )

    with session_factory() as session:
        try:
            complete_extraction(session, case_id, response)
        except IllegalTransition:
            session.rollback()  # another worker finished this invoice first
            return JobOutcome.SKIPPED
        session.commit()
    return JobOutcome.DONE


def _fail(
    session_factory: sessionmaker, case_id: uuid.UUID, error: str, attempt: int
) -> JobOutcome:
    with session_factory() as session:
        try:
            fail_extraction(session, case_id, error=error, attempts=attempt)
        except IllegalTransition:
            session.rollback()
            return JobOutcome.SKIPPED
        session.commit()
    return JobOutcome.FAILED
