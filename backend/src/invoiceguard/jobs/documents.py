"""Upload and replay, each writing its job to the outbox in the same transaction."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from invoiceguard.db import models as m
from invoiceguard.extraction.service import register_upload
from invoiceguard.jobs.outbox import TOPIC_EXTRACT, enqueue
from invoiceguard.workflow import audit
from invoiceguard.workflow.errors import IllegalTransition
from invoiceguard.workflow.service import lock_invoice, transition
from invoiceguard.workflow.state_machine import InvoiceState as S


def submit_document(
    session: Session,
    pdf: bytes,
    *,
    filename: str,
    actor: str,
    template_id: str | None = None,
) -> m.Invoice:
    row = register_upload(session, pdf, filename=filename, actor=actor, template_id=template_id)
    enqueue(session, TOPIC_EXTRACT, {"invoice_id": str(row.id)})
    return row


def replay_failed(session: Session, invoice_id: uuid.UUID, *, actor: str) -> m.Invoice:
    """Send a dead-lettered invoice back through extraction."""
    row = lock_invoice(session, invoice_id)
    if S(row.status) is not S.FAILED:
        raise IllegalTransition(f"only FAILED invoices can be replayed, this one is {row.status}")
    open_jobs = session.scalars(
        select(m.FailedJob).where(
            m.FailedJob.invoice_id == invoice_id, m.FailedJob.status == "FAILED"
        )
    ).all()
    for job in open_jobs:
        job.status = "REPLAYED"
        job.replayed_at = func.now()
    transition(session, row, S.RECEIVED, actor=actor, payload={"why": "replay from dead letter"})
    enqueue(session, TOPIC_EXTRACT, {"invoice_id": str(row.id)})
    audit.record(
        session,
        event_type="job.replayed",
        actor=actor,
        invoice_id=row.id,
        trace_id=row.trace_id,
        payload={"failed_jobs": [job.id for job in open_jobs]},
    )
    return row
