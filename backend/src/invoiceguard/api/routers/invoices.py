import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from invoiceguard.api import schemas
from invoiceguard.api.auth import current_user
from invoiceguard.api.deps import get_session
from invoiceguard.db import models as m
from invoiceguard.domain import models as d
from invoiceguard.workflow import service
from invoiceguard.workflow.errors import (
    IllegalTransition,
    InvoiceNotFound,
    NotApproved,
    StaleVersion,
)
from invoiceguard.workflow.posting import post_invoice

router = APIRouter(prefix="/invoices", tags=["invoices"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvoiceNotFound):
        return HTTPException(404, "invoice not found")
    if isinstance(exc, (StaleVersion, NotApproved, IllegalTransition)):
        return HTTPException(409, str(exc))
    return HTTPException(422, str(exc))


@router.post("", response_model=schemas.InvoiceOut, status_code=201)
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


@router.get("", response_model=list[schemas.InvoiceOut])
def list_invoices(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
    _user: str = Depends(current_user),
) -> list[m.Invoice]:
    query = select(m.Invoice).order_by(m.Invoice.created_at.desc()).limit(limit)
    if status:
        query = query.where(m.Invoice.status == status)
    return list(session.scalars(query))


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
    return {
        **schemas.InvoiceOut.model_validate(row).model_dump(),
        "subtotal": row.subtotal,
        "tax": row.tax,
        "lines": sorted(row.lines, key=lambda line: line.line_no),
        "approvals": approvals,
        "timeline": timeline,
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


router.post("/{invoice_id}/approve", response_model=schemas.InvoiceOut)(_decide(True))
router.post("/{invoice_id}/reject", response_model=schemas.InvoiceOut)(_decide(False))


@router.post("/{invoice_id}/edit", response_model=schemas.InvoiceOut)
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


@router.post("/{invoice_id}/post", response_model=schemas.PostOut)
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
