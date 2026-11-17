"""Transactional outbox.

A job is written to the `outbox` table in the same transaction as the invoice it belongs
to, so a job is never lost when Redis is down and never exists for an invoice that was
rolled back. A dispatcher publishes pending rows to the queue afterwards. Delivery is
at-least-once, so every consumer must be idempotent.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from invoiceguard.db.models import OutboxMessage

TOPIC_EXTRACT = "invoice.extract"
MAX_BACKOFF_SECONDS = 60

Publisher = Callable[[str, dict[str, Any], int], None]


def enqueue(session: Session, topic: str, payload: dict[str, Any]) -> None:
    session.add(OutboxMessage(topic=topic, payload=payload, status="PENDING", attempts=0))


@dataclass(frozen=True)
class DispatchResult:
    sent: int
    failed: int


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(2**attempts, MAX_BACKOFF_SECONDS))


def dispatch_pending(
    session_factory: sessionmaker, publish: Publisher, *, limit: int = 50
) -> DispatchResult:
    """Publish due messages. Rows are claimed with SKIP LOCKED, so several dispatchers can
    run at once without sending the same message twice in one pass."""
    sent = failed = 0
    with session_factory() as session:
        messages = session.scalars(
            select(OutboxMessage)
            .where(OutboxMessage.status == "PENDING", OutboxMessage.available_at <= func.now())
            .order_by(OutboxMessage.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        for message in messages:
            try:
                publish(message.topic, message.payload, message.id)
            except Exception:  # broker down or rejecting: keep the row and try later
                message.attempts += 1
                message.available_at = func.now() + _backoff(message.attempts)
                failed += 1
            else:
                message.status = "SENT"
                sent += 1
        session.commit()
    return DispatchResult(sent, failed)
