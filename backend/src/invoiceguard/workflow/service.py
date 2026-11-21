"""Invoice workflow: submit, reconcile, approve, reject and edit.

Every function works inside the caller's transaction and never commits, so a failure
anywhere rolls back the state change together with its audit events.
"""

import time
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from invoiceguard.db import models as m
from invoiceguard.domain import models as d
from invoiceguard.domain.decision import Outcome
from invoiceguard.domain.duplicates import normalize_invoice_number
from invoiceguard.domain.pipeline import Reconciliation, reconcile
from invoiceguard.packs.base import PackReconciliation
from invoiceguard.packs.registry import require_pack
from invoiceguard.workflow import audit, repo
from invoiceguard.workflow.errors import IllegalTransition, InvoiceNotFound, StaleVersion
from invoiceguard.workflow.state_machine import InvoiceState as S
from invoiceguard.workflow.state_machine import assert_transition

SYSTEM = "system"
EDITABLE_FIELDS = frozenset({"po_number", "vendor_id", "currency", "subtotal", "tax", "total"})
_EDITABLE_STATES = frozenset({S.NEEDS_REVIEW, S.APPROVED, S.AUTO_APPROVED})


def lock_invoice(session: Session, case_id: uuid.UUID) -> m.Case:
    """Load an invoice and hold a row lock until the transaction ends."""
    # populate_existing: always read the locked row from the database, never a stale copy
    # this session may already hold in memory.
    row = session.execute(
        select(m.Case)
        .where(m.Case.id == case_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if row is None:
        raise InvoiceNotFound(str(case_id))
    return row


def transition(
    session: Session,
    row: m.Case,
    target: S,
    *,
    actor: str,
    payload: dict[str, Any] | None = None,
) -> None:
    assert_transition(row.status, target.value)
    previous = row.status
    row.status = target.value
    row.updated_at = func.now()
    audit.record(
        session,
        event_type="invoice.state_changed",
        actor=actor,
        case_id=row.id,
        trace_id=row.trace_id,
        payload={"from": previous, "to": target.value, **(payload or {})},
    )


def reconcile_row(
    session: Session, row: m.Case, extraction_confidence: Decimal = Decimal(1)
) -> Reconciliation:
    return reconcile(
        repo.to_domain_invoice(row),
        repo.load_po(session, row.po_number),
        repo.load_receipts(session, row.po_number),
        repo.load_existing(
            session,
            exclude_id=row.id,
            file_hash=row.file_hash,
            vendor_id=row.vendor_id,
            number_norm=row.number_norm,
        ),
        extraction_confidence=extraction_confidence,
        previously_invoiced=repo.previously_invoiced(
            session, po_number=row.po_number, exclude_id=row.id
        ),
    )


def apply_reconciliation(
    session: Session,
    row: m.Case,
    *,
    actor: str = SYSTEM,
    extraction_confidence: Decimal = Decimal(1),
) -> PackReconciliation:
    """Run the deterministic pipeline and move the invoice to its outcome state."""
    started = time.perf_counter()
    result = require_pack(row.pack_id).reconcile(session, row, extraction_confidence)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    transition(session, row, S.VALIDATED, actor=actor)
    transition(
        session,
        row,
        S.MATCHED,
        actor=actor,
        payload={**result.matched_payload, "duration_ms": elapsed_ms},
    )

    decision = result.decision
    payload = {"reasons": list(decision.reasons)}
    if decision.outcome is Outcome.AUTO_APPROVE:
        transition(session, row, S.AUTO_APPROVED, actor=actor, payload=payload)
        session.add(
            m.Approval(
                case_id=row.id,
                case_version=row.version,
                amount=row.total,
                reviewer=SYSTEM,
                decision="AUTO_APPROVE",
                reason="all signals clear",
            )
        )
        audit.record(
            session,
            event_type="approval.recorded",
            actor=SYSTEM,
            case_id=row.id,
            trace_id=row.trace_id,
            payload={"decision": "AUTO_APPROVE", "version": row.version, "amount": row.total},
        )
    elif decision.outcome is Outcome.NEEDS_REVIEW:
        transition(session, row, S.NEEDS_REVIEW, actor=actor, payload=payload)
    else:
        transition(session, row, S.REJECTED, actor=actor, payload=payload)
    return result


def submit_invoice(
    session: Session,
    invoice: d.Invoice,
    *,
    actor: str = SYSTEM,
    trace_id: str | None = None,
    extraction_confidence: Decimal = Decimal(1),
) -> m.Case:
    row = m.Case(
        invoice_number=invoice.invoice_number,
        number_norm=normalize_invoice_number(invoice.invoice_number),
        vendor_id=invoice.vendor_id,
        po_number=invoice.po_number,
        currency=invoice.currency,
        subtotal=invoice.subtotal,
        tax=invoice.tax,
        total=invoice.total,
        file_hash=invoice.file_hash,
        status=S.RECEIVED.value,
        version=1,
        trace_id=trace_id or uuid.uuid4().hex,
    )
    row.lines = [
        m.CaseLine(line_no=i, sku=line.sku, qty=line.qty, unit_price=line.unit_price)
        for i, line in enumerate(invoice.lines, start=1)
    ]
    session.add(row)
    session.flush()
    audit.record(
        session,
        event_type="invoice.received",
        actor=actor,
        case_id=row.id,
        trace_id=row.trace_id,
        payload={"invoice_number": invoice.invoice_number, "total": invoice.total},
    )
    apply_reconciliation(
        session, row, actor=actor, extraction_confidence=extraction_confidence
    )
    return row


def _require_reason(reason: str) -> str:
    if not reason or not reason.strip():
        raise ValueError("a reason is required")
    return reason.strip()


def _decide_review(
    session: Session,
    case_id: uuid.UUID,
    *,
    reviewer: str,
    expected_version: int,
    reason: str,
    approve: bool,
) -> m.Case:
    reason = _require_reason(reason)
    row = lock_invoice(session, case_id)
    if row.version != expected_version:
        raise StaleVersion(
            f"invoice is at version {row.version}, the decision was made on {expected_version}"
        )
    target = S.APPROVED if approve else S.REJECTED
    transition(session, row, target, actor=reviewer, payload={"reason": reason})
    session.add(
        m.Approval(
            case_id=row.id,
            case_version=row.version,
            amount=row.total,
            reviewer=reviewer,
            decision="APPROVE" if approve else "REJECT",
            reason=reason,
        )
    )
    audit.record(
        session,
        event_type="approval.recorded",
        actor=reviewer,
        case_id=row.id,
        trace_id=row.trace_id,
        payload={
            "decision": "APPROVE" if approve else "REJECT",
            "version": row.version,
            "amount": row.total,
            "reason": reason,
        },
    )
    return row


def approve_invoice(
    session: Session, case_id: uuid.UUID, *, reviewer: str, expected_version: int, reason: str
) -> m.Case:
    return _decide_review(
        session,
        case_id,
        reviewer=reviewer,
        expected_version=expected_version,
        reason=reason,
        approve=True,
    )


def reject_invoice(
    session: Session, case_id: uuid.UUID, *, reviewer: str, expected_version: int, reason: str
) -> m.Case:
    return _decide_review(
        session,
        case_id,
        reviewer=reviewer,
        expected_version=expected_version,
        reason=reason,
        approve=False,
    )


def edit_invoice(
    session: Session,
    case_id: uuid.UUID,
    *,
    actor: str,
    expected_version: int,
    reason: str,
    **changes: Any,
) -> m.Case:
    """Apply a material edit. It bumps the version and voids any earlier approval."""
    reason = _require_reason(reason)
    unknown = set(changes) - EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"fields cannot be edited: {sorted(unknown)}")

    row = lock_invoice(session, case_id)
    if row.version != expected_version:
        raise StaleVersion(
            f"invoice is at version {row.version}, the edit was made on {expected_version}"
        )
    if S(row.status) not in _EDITABLE_STATES:
        raise IllegalTransition(f"an invoice in state {row.status} cannot be edited")

    was_approved = S(row.status) in (S.APPROVED, S.AUTO_APPROVED)
    diff = {
        field: {"from": getattr(row, field), "to": value}
        for field, value in changes.items()
        if getattr(row, field) != value
    }
    for field, value in changes.items():
        setattr(row, field, value)
    row.version += 1

    if S(row.status) is not S.NEEDS_REVIEW:
        transition(
            session,
            row,
            S.NEEDS_REVIEW,
            actor=actor,
            payload={"why": "material edit voids the earlier approval"},
        )
    audit.record(
        session,
        event_type="invoice.edited",
        actor=actor,
        case_id=row.id,
        trace_id=row.trace_id,
        payload={"changes": diff, "reason": reason, "new_version": row.version},
    )
    if was_approved:
        audit.record(
            session,
            event_type="approval.voided",
            actor=actor,
            case_id=row.id,
            trace_id=row.trace_id,
            payload={"voided_version": row.version - 1},
        )

    session.flush()
    session.refresh(row)
    result = require_pack(row.pack_id).reconcile(session, row, Decimal(1))
    audit.record(
        session,
        event_type="invoice.reconciled_after_edit",
        actor=SYSTEM,
        case_id=row.id,
        trace_id=row.trace_id,
        payload={
            "outcome": result.decision.outcome.value,
            "reasons": list(result.decision.reasons),
        },
    )
    return row
