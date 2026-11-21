"""Posting grants: how a person lets an agent post one approved case.

A person approves a case in the review UI. If an agent should then post it, the person
issues a grant. The grant is bound to the case version and amount at that moment, expires
within minutes, and is spent by its first successful use. If anything about the case changes
after issue (an edit, a new version, a different amount) the grant no longer matches and the
agent is refused. An agent therefore never decides; it carries out one posting a person
already approved and explicitly released.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from invoiceguard.db import models as m
from invoiceguard.workflow import audit
from invoiceguard.workflow.errors import GrantInvalid, NotApproved
from invoiceguard.workflow.posting import PostResult, has_valid_approval, post_invoice
from invoiceguard.workflow.service import lock_invoice
from invoiceguard.workflow.state_machine import POSTABLE
from invoiceguard.workflow.state_machine import InvoiceState as S

MIN_TTL_MINUTES = 1
MAX_TTL_MINUTES = 60
DEFAULT_TTL_MINUTES = 15


def issue_grant(
    session: Session,
    case_id: uuid.UUID,
    *,
    issued_by: str,
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
) -> m.PostingGrant:
    if not MIN_TTL_MINUTES <= ttl_minutes <= MAX_TTL_MINUTES:
        raise ValueError(f"a grant lasts between {MIN_TTL_MINUTES} and {MAX_TTL_MINUTES} minutes")
    row = lock_invoice(session, case_id)
    if S(row.status) not in POSTABLE:
        raise NotApproved(f"the case is {row.status}; only an approved case can be released")
    if not has_valid_approval(session, row):
        raise NotApproved("there is no valid approval for the current version and amount")
    grant = m.PostingGrant(
        case_id=row.id,
        case_version=row.version,
        amount=row.total,
        issued_by=issued_by,
        expires_at=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
    )
    session.add(grant)
    session.flush()
    audit.record(
        session,
        event_type="grant.issued",
        actor=issued_by,
        case_id=row.id,
        trace_id=row.trace_id,
        payload={
            "grant": grant.id,
            "version": row.version,
            "amount": row.total,
            "expires_at": grant.expires_at,
        },
    )
    return grant


def _why_invalid(session: Session, grant_id: uuid.UUID, row: m.Case) -> str:
    grant = session.get(m.PostingGrant, grant_id)
    if grant is None or grant.case_id != row.id:
        return "no such grant for this case"
    if grant.used_at is not None:
        return "this grant has already been used"
    if grant.expires_at <= datetime.now(UTC):
        return "this grant has expired"
    return "the case changed after the grant was issued (new version or amount)"


def post_with_grant(
    session: Session, case_id: uuid.UUID, grant_id: uuid.UUID, *, actor: str
) -> PostResult:
    """Spend the grant and post, in one transaction. If posting fails the grant is not spent
    (the caller rolls the transaction back)."""
    row = lock_invoice(session, case_id)
    spent = session.execute(
        update(m.PostingGrant)
        .where(
            m.PostingGrant.id == grant_id,
            m.PostingGrant.case_id == row.id,
            m.PostingGrant.used_at.is_(None),
            m.PostingGrant.expires_at > datetime.now(UTC),
            m.PostingGrant.case_version == row.version,
            m.PostingGrant.amount == row.total,
        )
        .values(used_at=datetime.now(UTC), used_by=actor)
        .returning(m.PostingGrant.id)
    ).scalar_one_or_none()
    if spent is None:
        reason = _why_invalid(session, grant_id, row)
        audit.record(
            session,
            event_type="grant.refused",
            actor=actor,
            case_id=row.id,
            trace_id=row.trace_id,
            payload={"grant": grant_id, "reason": reason},
        )
        raise GrantInvalid(reason)
    audit.record(
        session,
        event_type="grant.used",
        actor=actor,
        case_id=row.id,
        trace_id=row.trace_id,
        payload={"grant": grant_id},
    )
    return post_invoice(session, case_id, actor=actor)


def grants_for_case(session: Session, case_id: uuid.UUID) -> list[m.PostingGrant]:
    return list(
        session.scalars(
            select(m.PostingGrant)
            .where(m.PostingGrant.case_id == case_id)
            .order_by(m.PostingGrant.created_at.desc())
        )
    )
