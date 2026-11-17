"""Document flow: upload -> extraction -> normalisation -> evidence check -> reconciliation.

The model call is deliberately outside any database transaction: `begin_extraction`
commits the EXTRACTING state, the caller calls the model, then `complete_extraction` (or
`fail_extraction`) records the result in a new transaction.
"""

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoiceguard.db import models as m
from invoiceguard.domain.duplicates import normalize_invoice_number
from invoiceguard.extraction.client import ExtractionResponse
from invoiceguard.extraction.evidence import check_evidence, page_texts
from invoiceguard.extraction.metrics import record_llm_call
from invoiceguard.extraction.normalizer import normalize
from invoiceguard.workflow import audit
from invoiceguard.workflow.service import (
    SYSTEM,
    apply_reconciliation,
    lock_invoice,
    transition,
)
from invoiceguard.workflow.state_machine import InvoiceState as S

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def register_upload(
    session: Session,
    pdf: bytes,
    *,
    filename: str,
    actor: str,
    template_id: str | None = None,
) -> m.Invoice:
    if not pdf.startswith(b"%PDF"):
        raise ValueError("only PDF files are accepted")
    if len(pdf) > MAX_UPLOAD_BYTES:
        raise ValueError("file is larger than the 5 MB limit")

    row = m.Invoice(
        file_hash=hashlib.sha256(pdf).hexdigest(),
        status=S.RECEIVED.value,
        version=1,
        trace_id=uuid.uuid4().hex,
    )
    session.add(row)
    session.flush()
    session.add(
        m.Document(
            invoice_id=row.id,
            filename=filename,
            content_type="application/pdf",
            template_id=template_id,
            data=pdf,
        )
    )
    audit.record(
        session,
        event_type="invoice.received",
        actor=actor,
        invoice_id=row.id,
        trace_id=row.trace_id,
        payload={"filename": filename, "bytes": len(pdf), "file_hash": row.file_hash},
    )
    return row


def document_bytes(session: Session, invoice_id: uuid.UUID) -> bytes:
    return session.scalars(
        select(m.Document.data).where(m.Document.invoice_id == invoice_id)
    ).one()


def begin_extraction(session: Session, invoice_id: uuid.UUID, *, actor: str = SYSTEM) -> bytes:
    row = lock_invoice(session, invoice_id)
    transition(session, row, S.EXTRACTING, actor=actor)
    return document_bytes(session, invoice_id)


def complete_extraction(
    session: Session,
    invoice_id: uuid.UUID,
    response: ExtractionResponse,
    *,
    actor: str = SYSTEM,
) -> m.Invoice:
    row = lock_invoice(session, invoice_id)
    pdf = document_bytes(session, invoice_id)

    record_llm_call(
        session, invoice_id=row.id, step="extract", usage=response.usage, trace_id=row.trace_id
    )
    normalized = normalize(response.invoice, row.file_hash)
    fields, evidence_issues = check_evidence(normalized.fields, page_texts(pdf))
    issues = normalized.issues + evidence_issues
    confidence = min((f.confidence for f in fields if f.value), default=normalized.confidence)

    for record in fields:
        session.add(
            m.ExtractionField(
                invoice_id=row.id,
                field=record.field,
                value=record.value,
                confidence=record.confidence,
                page=record.page,
                snippet=record.snippet,
            )
        )

    transition(
        session,
        row,
        S.EXTRACTED,
        actor=actor,
        payload={"confidence": confidence, "issues": issues, "model": response.usage.model},
    )

    if normalized.invoice is None:
        transition(
            session,
            row,
            S.NEEDS_REVIEW,
            actor=actor,
            payload={"reasons": ["EXTRACTION_INCOMPLETE", *issues]},
        )
        return row

    invoice = normalized.invoice
    row.invoice_number = invoice.invoice_number
    row.number_norm = normalize_invoice_number(invoice.invoice_number)
    row.vendor_id = invoice.vendor_id
    row.po_number = invoice.po_number
    row.currency = invoice.currency
    row.subtotal = invoice.subtotal
    row.tax = invoice.tax
    row.total = invoice.total
    row.lines = [
        m.InvoiceLine(line_no=i, sku=line.sku, qty=line.qty, unit_price=line.unit_price)
        for i, line in enumerate(invoice.lines, start=1)
    ]
    session.flush()

    apply_reconciliation(session, row, actor=actor, extraction_confidence=confidence)
    return row


def fail_extraction(
    session: Session,
    invoice_id: uuid.UUID,
    *,
    error: str,
    attempts: int,
    actor: str = SYSTEM,
) -> m.Invoice:
    """Park the invoice in FAILED with an inspectable dead-letter record."""
    row = lock_invoice(session, invoice_id)
    transition(session, row, S.FAILED, actor=actor, payload={"error": error, "attempts": attempts})
    session.add(m.FailedJob(invoice_id=row.id, task="extract", error=error, attempts=attempts))
    return row
