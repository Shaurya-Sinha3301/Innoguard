"""Posting service: the only code that writes to the system of record.

Safety comes from three layers working together:
1. a row lock on the invoice serialises concurrent attempts;
2. a unique idempotency key (invoice, version, amount) makes a repeat a no-op;
3. a database unique constraint is the last line of defence if the first two were bypassed.
"""

import hashlib
import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from invoiceguard.db import models as m
from invoiceguard.domain.money import quantize_money
from invoiceguard.workflow import audit
from invoiceguard.workflow.errors import NotApproved
from invoiceguard.workflow.service import lock_invoice, transition
from invoiceguard.workflow.state_machine import POSTABLE
from invoiceguard.workflow.state_machine import InvoiceState as S

_APPROVING_DECISIONS = ("APPROVE", "AUTO_APPROVE")


class PostOutcome(StrEnum):
    POSTED = "POSTED"
    ALREADY_PROCESSED = "ALREADY_PROCESSED"


@dataclass(frozen=True)
class PostResult:
    outcome: PostOutcome
    case_id: uuid.UUID
    idempotency_key: str


def idempotency_key(case_id: uuid.UUID, version: int, total: Decimal) -> str:
    """Stable key for one invoice, one version and one amount."""
    amount = quantize_money(total)
    return hashlib.sha256(f"{case_id}:{version}:{amount}".encode()).hexdigest()


def post_invoice(session: Session, case_id: uuid.UUID, *, actor: str) -> PostResult:
    row = lock_invoice(session, case_id)
    key = idempotency_key(row.id, row.version, row.total)

    already = session.scalar(select(m.Posting.id).where(m.Posting.idempotency_key == key))
    if already is not None:
        return _already_processed(session, row, actor, key)

    if S(row.status) not in POSTABLE:
        raise NotApproved(f"invoice is {row.status}, not approved")
    approval_id = session.scalar(
        select(m.Approval.id)
        .where(
            m.Approval.case_id == row.id,
            m.Approval.case_version == row.version,
            m.Approval.decision.in_(_APPROVING_DECISIONS),
            m.Approval.amount == row.total,
        )
        .limit(1)
    )
    if approval_id is None:
        raise NotApproved("no valid approval for the current invoice version and amount")

    inserted = session.execute(
        pg_insert(m.Posting)
        .values(
            idempotency_key=key,
            case_id=row.id,
            case_version=row.version,
            status="POSTED",
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(m.Posting.id)
    ).scalar_one_or_none()
    if inserted is None:
        return _already_processed(session, row, actor, key)

    transition(session, row, S.POSTING, actor=actor)
    transition(session, row, S.POSTED, actor=actor)
    audit.record(
        session,
        event_type="posting.posted",
        actor=actor,
        case_id=row.id,
        trace_id=row.trace_id,
        payload={"idempotency_key": key, "version": row.version, "amount": row.total},
    )
    return PostResult(PostOutcome.POSTED, row.id, key)


def _already_processed(session: Session, row: m.Case, actor: str, key: str) -> PostResult:
    audit.record(
        session,
        event_type="posting.already_processed",
        actor=actor,
        case_id=row.id,
        trace_id=row.trace_id,
        payload={"idempotency_key": key},
    )
    return PostResult(PostOutcome.ALREADY_PROCESSED, row.id, key)
