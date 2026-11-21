"""The invoice pack's manifest must agree with the code that actually runs the rules."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from invoiceguard.domain.decision import Thresholds
from invoiceguard.domain.matching import DiscrepancyCode
from invoiceguard.domain.models import Tolerances
from invoiceguard.domain.policy import PolicyConfig
from invoiceguard.domain.validation import ValidationCode
from invoiceguard.packs.base import Manifest
from invoiceguard.packs.registry import get_pack, list_packs

PACK = get_pack("invoices")
assert PACK is not None
M = PACK.manifest


def test_every_reason_the_rules_can_emit_is_described_in_the_manifest():
    declared = {r.code for r in M.reasons}
    emitted = (
        {c.value for c in DiscrepancyCode}
        | {c.value for c in ValidationCode}
        | {"DUPLICATE_EXACT", "DUPLICATE_BUSINESS_KEY", "HIGH_VALUE"}
        | {"LOW_EXTRACTION_CONFIDENCE", "LOW_MATCH_QUALITY"}
        | {"EXTRACTION_INCOMPLETE", "EXTRACTION_FAILED"}
    )
    assert emitted <= declared, f"undescribed reasons: {sorted(emitted - declared)}"


def test_thresholds_and_tolerances_are_the_ones_the_code_uses():
    t = Thresholds()
    assert M.thresholds.min_extraction_confidence == t.min_extraction_confidence
    assert M.thresholds.min_match_quality == t.min_match_quality
    assert M.thresholds.max_auto_amount == PolicyConfig().max_auto_total
    tol = Tolerances()
    assert M.tolerances.price_pct == tol.price_pct
    assert M.tolerances.qty_pct == tol.qty_pct
    assert M.tolerances.amount_abs == tol.amount_abs


def test_the_price_tolerance_is_what_the_price_variance_text_says():
    text = next(r.explain for r in M.reasons if r.code == "PRICE_VARIANCE")
    assert f"{M.tolerances.price_pct:f}%" in text


def test_soft_reasons_are_exactly_the_two_signals_that_are_not_policy_violations():
    soft = {r.code for r in M.reasons if r.severity == "soft"}
    assert soft == {"LOW_EXTRACTION_CONFIDENCE", "LOW_MATCH_QUALITY"}


def test_registry_lists_the_invoice_pack():
    assert [p.id for p in list_packs()] == ["invoices", "expenses"]
    assert get_pack("nope") is None


def _minimal(**overrides):
    base = {
        "id": "x",
        "name": "X",
        "version": 1,
        "description": "d",
        "document": "doc",
        "fields": [{"name": "a", "label": "A"}],
        "reasons": [{"code": "R1", "label": "R", "explain": "e"}],
        "thresholds": {"min_extraction_confidence": "0.9", "min_match_quality": "1"},
        "queue_columns": ["ref"],
        "detail_sections": ["reasons"],
    }
    return {**base, **overrides}


def test_a_minimal_manifest_is_valid():
    assert Manifest.model_validate(_minimal()).thresholds.max_auto_amount is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"reasons": [{"code": "R1", "label": "R", "explain": "e"}] * 2},
        {"fields": [{"name": "a", "label": "A"}, {"name": "a", "label": "B"}]},
        {"implied_reason": "NOT_DECLARED"},
        {"unexpected_key": 1},
    ],
)
def test_a_malformed_manifest_is_refused_at_load(overrides):
    with pytest.raises(ValidationError):
        Manifest.model_validate(_minimal(**overrides))


def test_decimal_values_survive_the_yaml_round_trip():
    assert M.thresholds.max_auto_amount == Decimal("10000")


# ------------------------------------------------------------------ the expenses pack

EXPENSES = get_pack("expenses")
assert EXPENSES is not None


def test_every_reason_the_expense_rules_can_emit_is_described():
    from invoiceguard.packs.expenses.generator import ExpenseLabel

    declared = {r.code for r in EXPENSES.manifest.reasons}
    emitted = {
        "UNKNOWN_EMPLOYEE", "WRONG_CARD", "UNKNOWN_CATEGORY", "CATEGORY_BLOCKED",
        "OVER_CATEGORY_CAP", "DATE_IN_FUTURE", "CLAIM_TOO_OLD", "NO_CARD_TRANSACTION",
        "AMOUNT_MISMATCH", "CURRENCY_MISMATCH", "DUPLICATE_CLAIM", "DUPLICATE_EXACT",
        "HIGH_VALUE", "LOW_EXTRACTION_CONFIDENCE", "LOW_MATCH_QUALITY",
        "EXTRACTION_INCOMPLETE", "EXTRACTION_FAILED",
    }  # fmt: skip
    assert emitted <= declared, sorted(emitted - declared)
    assert {label.value for label in ExpenseLabel} - {"CLEAN"} <= declared


def test_the_expense_manifest_numbers_are_the_ones_the_rules_use():
    from invoiceguard.packs.expenses.models import ExpensePolicy, ExpenseTolerances

    tol, policy = ExpenseTolerances(), ExpensePolicy()
    m = EXPENSES.manifest
    assert m.tolerances.amount_abs == tol.amount_abs
    assert m.tolerances.date_window_days == tol.date_window_days
    assert m.tolerances.max_claim_age_days == tol.max_claim_age_days
    assert m.thresholds.max_auto_amount == policy.max_auto_amount
    t = Thresholds()
    assert m.thresholds.min_extraction_confidence == t.min_extraction_confidence
    assert m.thresholds.min_match_quality == t.min_match_quality


def test_the_expense_reason_texts_state_the_numbers_the_rules_use():
    m = EXPENSES.manifest
    text = {r.code: r.explain for r in m.reasons}
    assert f"{m.tolerances.max_claim_age_days} days" in text["CLAIM_TOO_OLD"]
    assert f"{m.tolerances.date_window_days} days" in text["NO_CARD_TRANSACTION"]


def test_both_packs_name_what_a_case_is_called():
    assert PACK.manifest.case_noun == "invoice" and EXPENSES.manifest.case_noun == "claim"
    assert len(PACK.manifest.how_it_works) == len(EXPENSES.manifest.how_it_works) == 3
