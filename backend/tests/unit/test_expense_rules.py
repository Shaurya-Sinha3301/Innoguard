"""The expense rules and normaliser, on their own (no database)."""

import random
from datetime import date
from decimal import Decimal

import pytest

from invoiceguard.domain.decision import Outcome
from invoiceguard.extraction.normalizer import NormalizationError
from invoiceguard.packs.expenses.fakes import truth_as_extraction
from invoiceguard.packs.expenses.generator import (
    TEMPLATES,
    TODAY,
    ExpenseLabel,
    generate_expense_scenario,
    printed_values,
    render_expense_pdf,
)
from invoiceguard.packs.expenses.models import ExpenseTolerances
from invoiceguard.packs.expenses.normalizer import (
    normalize_expense,
    parse_card_last4,
    parse_date,
)
from invoiceguard.packs.expenses.rules import (
    find_card_transaction,
    normalize_merchant,
    reconcile_expense,
    same_merchant,
)


def run(scenario, **overrides):
    wanted = scenario.expense.category
    category = next((c for c in scenario.categories if c.category == wanted), None)
    return reconcile_expense(
        scenario.expense,
        scenario.employee,
        category,
        scenario.transactions,
        scenario.existing,
        today=TODAY,
        **overrides,
    )


@pytest.mark.parametrize("label", list(ExpenseLabel))
def test_every_label_reaches_its_expected_outcome_and_reason(label):
    for index in range(20):
        scenario = generate_expense_scenario(random.Random(index), 5000 + index, label)
        result = run(scenario)
        assert result.decision.outcome is scenario.expected_outcome, (label, index)
        if scenario.expected_reason:
            assert scenario.expected_reason in result.decision.reasons, (label, index)
        else:
            assert result.decision.reasons == ()


def test_a_blocked_category_is_only_ever_blocked_not_over_the_cap():
    scenario = generate_expense_scenario(random.Random(1), 1, ExpenseLabel.CATEGORY_BLOCKED)
    reasons = run(scenario).decision.reasons
    assert "CATEGORY_BLOCKED" in reasons and "OVER_CATEGORY_CAP" not in reasons


def test_a_hard_violation_blocks_auto_approval_even_at_perfect_confidence():
    scenario = generate_expense_scenario(random.Random(1), 1, ExpenseLabel.OVER_CATEGORY_CAP)
    result = run(scenario, extraction_confidence=Decimal(1))
    assert result.decision.outcome is Outcome.NEEDS_REVIEW


def test_low_extraction_confidence_alone_sends_a_clean_claim_to_review():
    scenario = generate_expense_scenario(random.Random(1), 1, ExpenseLabel.CLEAN)
    result = run(scenario, extraction_confidence=Decimal("0.5"))
    assert result.decision.outcome is Outcome.NEEDS_REVIEW
    assert result.decision.reasons == ("LOW_EXTRACTION_CONFIDENCE",)


def test_the_statement_descriptor_need_not_match_the_receipt_exactly():
    assert same_merchant("Starbucks", "STARBUCKS #1042")
    assert same_merchant("Uber India", "UBER INDIA")
    assert not same_merchant("Starbucks", "ZOMATO")
    assert normalize_merchant("Cafe Coffee Day #77") == "cafecoffeeday"


def test_the_card_match_picks_the_nearest_amount_within_the_date_window():
    scenario = generate_expense_scenario(random.Random(2), 2, ExpenseLabel.CLEAN)
    near = scenario.transactions[0]
    far_date = near.__class__(
        "late", near.card_last4, near.merchant, date(2020, 1, 1), near.amount, near.currency
    )
    match = find_card_transaction(scenario.expense, [far_date, near], ExpenseTolerances())
    assert match.transaction is near and match.clean


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-11-12", date(2026, 11, 12)),
        ("12 Nov 2026", date(2026, 11, 12)),
        ("12 November 2026", date(2026, 11, 12)),
        ("12/11/2026", date(2026, 11, 12)),
    ],
)
def test_dates_are_read_day_first(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize("raw", ["11/12/26", "Nov 12", "yesterday", ""])
def test_ambiguous_dates_are_refused_not_guessed(raw):
    with pytest.raises(NormalizationError):
        parse_date(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("XXXX XXXX XXXX 4821", "4821"), ("**** 4821", "4821"), ("Card ending 4821", "4821")],
)
def test_card_digits_are_the_last_four(raw, expected):
    assert parse_card_last4(raw) == expected


def test_a_card_without_digits_is_refused():
    with pytest.raises(NormalizationError):
        parse_card_last4("cash")


@pytest.mark.parametrize("template", TEMPLATES)
def test_a_perfect_reading_of_every_layout_normalises_back_to_the_truth(template):
    scenario = generate_expense_scenario(random.Random(3), 3, ExpenseLabel.CLEAN)
    truth = scenario.expense
    normalized = normalize_expense(truth_as_extraction(truth, template), truth.file_hash)
    assert normalized.issues == []
    assert normalized.value == truth.__class__(**{**truth.__dict__, "tax": truth.tax})


def test_missing_required_fields_are_reported_not_guessed():
    scenario = generate_expense_scenario(random.Random(3), 3, ExpenseLabel.CLEAN)
    extracted = truth_as_extraction(scenario.expense, "classic")
    extracted.total.value = None
    normalized = normalize_expense(extracted, "h")
    assert normalized.value is None and "MISSING_FIELD:total" in normalized.issues


def test_the_pdf_carries_every_printed_value_the_oracle_quotes():
    from invoiceguard.extraction.evidence import page_texts

    scenario = generate_expense_scenario(random.Random(4), 4, ExpenseLabel.CLEAN)
    for template in TEMPLATES:
        text = " ".join(page_texts(render_expense_pdf(scenario.expense, template)))
        for name, value in printed_values(scenario.expense, template).items():
            assert value.lower() in " ".join(text.split()).lower(), (template, name)
