"""Agent suggestions: a proposed decision that changes nothing.

An agent reads a case and says what it would do and why. The suggestion is stored next to the
case for a person to read. Nothing here moves a case between states.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoiceguard.db import models as m
from invoiceguard.workflow import audit
from invoiceguard.workflow.errors import IllegalTransition, InvoiceNotFound
from invoiceguard.workflow.state_machine import InvoiceState as S

DECISIONS = ("approve", "reject", "hold")
MAX_RATIONALE = 1000


def propose(
    session: Session, case_id: uuid.UUID, *, actor: str, decision: str, rationale: str
) -> m.Suggestion:
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {', '.join(DECISIONS)}")
    rationale = rationale.strip()
    if not 5 <= len(rationale) <= MAX_RATIONALE:
        raise ValueError(f"give a rationale of 5 to {MAX_RATIONALE} characters")
    row = session.get(m.Case, case_id)
    if row is None:
        raise InvoiceNotFound(str(case_id))
    if row.status != S.NEEDS_REVIEW.value:
        raise IllegalTransition(
            f"suggestions are for cases waiting for review; this is {row.status}"
        )
    suggestion = m.Suggestion(
        case_id=row.id,
        case_version=row.version,
        decision=decision,
        rationale=rationale,
        proposed_by=actor,
    )
    session.add(suggestion)
    session.flush()
    audit.record(
        session,
        event_type="suggestion.proposed",
        actor=actor,
        case_id=row.id,
        trace_id=row.trace_id,
        payload={"suggestion": suggestion.id, "decision": decision, "version": row.version},
    )
    return suggestion


def dismiss(
    session: Session, case_id: uuid.UUID, suggestion_id: int, *, actor: str
) -> m.Suggestion:
    suggestion = session.get(m.Suggestion, suggestion_id)
    if suggestion is None or suggestion.case_id != case_id:
        raise InvoiceNotFound(f"suggestion {suggestion_id}")
    if suggestion.status == "OPEN":
        suggestion.status = "DISMISSED"
        suggestion.resolved_by = actor
        suggestion.resolved_at = datetime.now(UTC)
        audit.record(
            session,
            event_type="suggestion.dismissed",
            actor=actor,
            case_id=case_id,
            payload={"suggestion": suggestion_id},
        )
    return suggestion


def for_case(session: Session, case_id: uuid.UUID) -> list[m.Suggestion]:
    return list(
        session.scalars(
            select(m.Suggestion)
            .where(m.Suggestion.case_id == case_id)
            .order_by(m.Suggestion.id.desc())
        )
    )
