import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from invoiceguard.api import schemas
from invoiceguard.api.auth import current_user, require_scope
from invoiceguard.api.deps import get_session
from invoiceguard.api.ratelimit import WRITE_GUARDS
from invoiceguard.db import models as m
from invoiceguard.domain import models as d
from invoiceguard.workflow import repo, service
from invoiceguard.workflow.errors import (
    IllegalTransition,
    InvoiceNotFound,
    NotApproved,
    StaleVersion,
)
from invoiceguard.workflow.posting import post_invoice

router = APIRouter(
    prefix="/invoices", tags=["invoices"], dependencies=[Depends(require_scope("read"))]
)

SUBMIT = [Depends(require_scope("submit")), *WRITE_GUARDS]
REVIEW = [Depends(require_scope("review")), *WRITE_GUARDS]
POST = [Depends(require_scope("post")), *WRITE_GUARDS]


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvoiceNotFound):
        return HTTPException(404, "invoice not found")
    if isinstance(exc, (StaleVersion, NotApproved, IllegalTransition)):
        return HTTPException(409, str(exc))
    return HTTPException(422, str(exc))


@router.post("", response_model=schemas.InvoiceOut, status_code=201, dependencies=SUBMIT)
def submit(
    body: schemas.InvoiceIn,
    session: Session = Depends(get_session),
    user: str = Depends(current_user),
) -> m.Invoice:
    invoice = d.Invoice(
        invoice_number=body.invoice_number,
        vendor_id=body.vendor_id,
        po_number=body.po_number,
        currency=body.currency,
        lines=tuple(d.InvoiceLine(ln.sku, ln.qty, ln.unit_price) for ln in body.lines),
        subtotal=body.subtotal,
        tax=body.tax,
        total=body.total,
        file_hash=body.file_hash,
    )
    return service.submit_invoice(session, invoice, actor=user)


@router.get("", response_model=list[schemas.InvoiceRow])
def list_invoices(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
    _user: str = Depends(current_user),
) -> list[dict]:
    query = select(m.Invoice).order_by(m.Invoice.created_at.desc()).limit(limit)
    if status:
        query = query.where(m.Invoice.status == status)
    rows = list(session.scalars(query))
    reasons = _latest_reasons(session, [row.id for row in rows])
    return [
        {**schemas.InvoiceOut.model_validate(row).model_dump(), "reasons": reasons.get(row.id, [])}
        for row in rows
    ]


def _latest_reasons(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """The reasons recorded on each invoice's most recent decision, from the audit log."""
    if not ids:
        return {}
    found = session.execute(
        text(
            """
            SELECT DISTINCT ON (invoice_id) invoice_id, payload->'reasons'
            FROM audit_events
            WHERE invoice_id = ANY(:ids)
              AND event_type = 'invoice.state_changed'
              AND jsonb_typeof(payload->'reasons') = 'array'
              AND jsonb_array_length(payload->'reasons') > 0
            ORDER BY invoice_id, id DESC
            """
        ),
        {"ids": ids},
    ).all()
    return {invoice_id: list(reasons) for invoice_id, reasons in found}


@router.get("/{invoice_id}", response_model=schemas.InvoiceDetail)
def get_invoice(
    invoice_id: uuid.UUID,
    session: Session = Depends(get_session),
    _user: str = Depends(current_user),
) -> dict:
    row = session.get(m.Invoice, invoice_id)
    if row is None:
        raise HTTPException(404, "invoice not found")
    approvals = session.scalars(
        select(m.Approval).where(m.Approval.invoice_id == invoice_id).order_by(m.Approval.id)
    ).all()
    timeline = session.scalars(
        select(m.AuditEvent).where(m.AuditEvent.invoice_id == invoice_id).order_by(m.AuditEvent.id)
    ).all()
    llm_calls = session.scalars(
        select(m.LlmCall).where(m.LlmCall.invoice_id == invoice_id).order_by(m.LlmCall.id)
    ).all()
    po = repo.load_po(session, row.po_number)
    receipts = repo.load_receipts(session, row.po_number)
    received: dict[str, Decimal] = {}
    for receipt in receipts:
        for line in receipt.lines:
            received[line.sku] = received.get(line.sku, Decimal(0)) + line.qty
    return {
        "reasons": _latest_reasons(session, [row.id]).get(row.id, []),
        "purchase_order": None
        if po is None
        else {
            "po_number": po.po_number,
            "vendor_id": po.vendor_id,
            "currency": po.currency,
            "lines": [
                {"sku": ln.sku, "qty": ln.qty, "unit_price": ln.unit_price} for ln in po.lines
            ],
        },
        "receipt_count": len(receipts),
        "received": received,
        **schemas.InvoiceOut.model_validate(row).model_dump(),
        "subtotal": row.subtotal,
        "tax": row.tax,
        "trace_id": row.trace_id,
        "lines": sorted(row.lines, key=lambda line: line.line_no),
        "approvals": approvals,
        "timeline": timeline,
        "llm_calls": llm_calls,
    }


def _decide(approve: bool):
    def endpoint(
        invoice_id: uuid.UUID,
        body: schemas.DecisionIn,
        session: Session = Depends(get_session),
        user: str = Depends(current_user),
    ) -> m.Invoice:
        action = service.approve_invoice if approve else service.reject_invoice
        try:
            return action(
                session,
                invoice_id,
                reviewer=user,
                expected_version=body.expected_version,
                reason=body.reason,
            )
        except (InvoiceNotFound, StaleVersion, IllegalTransition, ValueError) as exc:
            raise _http_error(exc) from exc

    return endpoint


router.post("/{invoice_id}/approve", response_model=schemas.InvoiceOut, dependencies=REVIEW)(
    _decide(True)
)
router.post("/{invoice_id}/reject", response_model=schemas.InvoiceOut, dependencies=REVIEW)(
    _decide(False)
)


@router.post("/{invoice_id}/edit", response_model=schemas.InvoiceOut, dependencies=REVIEW)
def edit(
    invoice_id: uuid.UUID,
    body: schemas.EditIn,
    session: Session = Depends(get_session),
    user: str = Depends(current_user),
) -> m.Invoice:
    changes = dict(body.changes)
    for field in ("subtotal", "tax", "total"):
        if field in changes:
            changes[field] = Decimal(str(changes[field]))
    try:
        return service.edit_invoice(
            session,
            invoice_id,
            actor=user,
            expected_version=body.expected_version,
            reason=body.reason,
            **changes,
        )
    except (InvoiceNotFound, StaleVersion, IllegalTransition, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post("/{invoice_id}/post", response_model=schemas.PostOut, dependencies=POST)
def post(
    invoice_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: str = Depends(current_user),
) -> schemas.PostOut:
    try:
        result = post_invoice(session, invoice_id, actor=user)
    except (InvoiceNotFound, NotApproved, IllegalTransition) as exc:
        raise _http_error(exc) from exc
    return schemas.PostOut(
        outcome=result.outcome.value,
        invoice_id=result.invoice_id,
        idempotency_key=result.idempotency_key,
    )
