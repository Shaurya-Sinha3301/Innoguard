"""Explicit invoice lifecycle: durable states and validated transitions."""

from enum import StrEnum

from invoiceguard.workflow.errors import IllegalTransition


class InvoiceState(StrEnum):
    RECEIVED = "RECEIVED"
    EXTRACTING = "EXTRACTING"
    EXTRACTED = "EXTRACTED"
    VALIDATED = "VALIDATED"
    MATCHED = "MATCHED"
    AUTO_APPROVED = "AUTO_APPROVED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"
    POSTING = "POSTING"
    POSTED = "POSTED"
    FAILED = "FAILED"


S = InvoiceState

ALLOWED: dict[InvoiceState, frozenset[InvoiceState]] = {
    S.RECEIVED: frozenset({S.EXTRACTING, S.VALIDATED, S.FAILED}),
    S.EXTRACTING: frozenset({S.EXTRACTED, S.FAILED}),
    S.EXTRACTED: frozenset({S.VALIDATED, S.NEEDS_REVIEW}),
    S.VALIDATED: frozenset({S.MATCHED}),
    S.MATCHED: frozenset({S.AUTO_APPROVED, S.NEEDS_REVIEW, S.REJECTED}),
    # A material edit sends an approved invoice back to review (see workflow.service).
    S.AUTO_APPROVED: frozenset({S.POSTING, S.NEEDS_REVIEW}),
    S.NEEDS_REVIEW: frozenset({S.APPROVED, S.REJECTED}),
    S.APPROVED: frozenset({S.POSTING, S.NEEDS_REVIEW}),
    # A failed post returns to APPROVED so it can be retried safely.
    S.POSTING: frozenset({S.POSTED, S.APPROVED, S.FAILED}),
    S.POSTED: frozenset(),
    S.REJECTED: frozenset(),
    # A failed job can be replayed from the start.
    S.FAILED: frozenset({S.RECEIVED}),
}

# States from which posting is allowed (an approval for the current version must also exist).
POSTABLE = frozenset({S.APPROVED, S.AUTO_APPROVED})


def can_transition(current: InvoiceState, target: InvoiceState) -> bool:
    return target in ALLOWED[current]


def assert_transition(current: str, target: str) -> None:
    cur, tgt = InvoiceState(current), InvoiceState(target)
    if not can_transition(cur, tgt):
        raise IllegalTransition(f"cannot move an invoice from {cur.value} to {tgt.value}")
