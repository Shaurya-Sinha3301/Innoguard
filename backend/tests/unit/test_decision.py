from decimal import Decimal

from invoiceguard.domain.decision import Outcome, Signals, Thresholds, decide
from invoiceguard.domain.policy import PolicyResult

D = Decimal
CLEAN = PolicyResult(eligible=True, hard_violations=())


def signals(confidence="1", quality="1", policy=CLEAN, exact_duplicate=False):
    return Signals(D(confidence), D(quality), policy, exact_duplicate)


def test_all_clear_auto_approves():
    assert decide(signals()).outcome is Outcome.AUTO_APPROVE


def test_hard_violation_overrides_perfect_extraction_confidence():
    blocked = PolicyResult(eligible=False, hard_violations=("NO_RECEIPT",))
    decision = decide(signals(confidence="1", policy=blocked))
    assert decision.outcome is Outcome.NEEDS_REVIEW
    assert decision.reasons == ("NO_RECEIPT",)


def test_low_extraction_confidence_alone_sends_to_review():
    decision = decide(signals(confidence="0.80"))
    assert decision.outcome is Outcome.NEEDS_REVIEW
    assert decision.reasons == ("LOW_EXTRACTION_CONFIDENCE",)


def test_low_match_quality_alone_sends_to_review():
    decision = decide(signals(quality="0.5"))
    assert decision.outcome is Outcome.NEEDS_REVIEW
    assert decision.reasons == ("LOW_MATCH_QUALITY",)


def test_exact_duplicate_is_rejected_regardless_of_other_signals():
    assert decide(signals(exact_duplicate=True)).outcome is Outcome.REJECT


def test_all_reasons_are_reported_to_the_reviewer():
    blocked = PolicyResult(eligible=False, hard_violations=("PRICE_VARIANCE",))
    decision = decide(signals(confidence="0.5", quality="0.5", policy=blocked))
    assert decision.reasons == ("PRICE_VARIANCE", "LOW_EXTRACTION_CONFIDENCE", "LOW_MATCH_QUALITY")


def test_thresholds_are_configurable():
    relaxed = Thresholds(min_extraction_confidence=D("0.5"))
    assert decide(signals(confidence="0.60"), relaxed).outcome is Outcome.AUTO_APPROVE
