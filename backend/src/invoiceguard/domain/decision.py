"""Decision: combine three separate signals. Never a single blended score."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from invoiceguard.domain.policy import PolicyResult


class Outcome(StrEnum):
    AUTO_APPROVE = "AUTO_APPROVE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECT = "REJECT"


@dataclass(frozen=True)
class Thresholds:
    min_extraction_confidence: Decimal = Decimal("0.90")
    min_match_quality: Decimal = Decimal("1")


@dataclass(frozen=True)
class Signals:
    extraction_confidence: Decimal  # was the document read correctly?
    match_quality: Decimal  # do invoice, PO and receipt describe the same transaction?
    policy: PolicyResult  # is the transaction allowed to proceed?
    exact_duplicate: bool


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    reasons: tuple[str, ...]


def decide(signals: Signals, thresholds: Thresholds = Thresholds()) -> Decision:
    """Reject exact duplicates; send anything doubtful to review; approve only if all clear.

    Hard policy violations are listed first and always block auto-approval, even when
    extraction confidence is perfect.
    """
    if signals.exact_duplicate:
        return Decision(Outcome.REJECT, ("DUPLICATE_EXACT",))

    reasons = list(signals.policy.hard_violations)
    if signals.extraction_confidence < thresholds.min_extraction_confidence:
        reasons.append("LOW_EXTRACTION_CONFIDENCE")
    if signals.match_quality < thresholds.min_match_quality:
        reasons.append("LOW_MATCH_QUALITY")

    if reasons:
        return Decision(Outcome.NEEDS_REVIEW, tuple(reasons))
    return Decision(Outcome.AUTO_APPROVE, ())
