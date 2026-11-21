"""Append-only audit events. The database rejects any change to an event once written."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from invoiceguard.db.models import AuditEvent


def jsonable(value: Any) -> Any:
    """Convert values (Decimal, UUID, enums, dates) into JSON-safe data."""
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [jsonable(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (uuid.UUID, date, datetime)):
        return str(value)
    return value


def record(
    session: Session,
    *,
    event_type: str,
    actor: str,
    case_id: uuid.UUID | None = None,
    trace_id: str | None = None,
    payload: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> None:
    session.add(
        AuditEvent(
            case_id=case_id,
            trace_id=trace_id,
            event_type=event_type,
            actor=actor,
            payload=jsonable(payload or {}),
            duration_ms=duration_ms,
        )
    )
