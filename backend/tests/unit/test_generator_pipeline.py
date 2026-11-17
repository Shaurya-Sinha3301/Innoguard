"""Regression check of the deterministic core against its own generated ground truth.

This is not an accuracy claim: the generator and the rules are written together, so
agreement here shows the rules behave as designed, nothing more. Real evaluation
(held-out vendor templates, extraction errors) comes in phase D.
"""

from collections import Counter

import pytest

from invoiceguard.domain.pipeline import reconcile
from invoiceguard.generator.cases import CaseLabel, generate

SEEDS = (1, 2, 3)
PER_SEED = 12 * 40  # every label 40 times per seed


@pytest.mark.parametrize("seed", SEEDS)
def test_every_scenario_reaches_its_expected_outcome(seed):
    mismatches = []
    for scenario in generate(seed, PER_SEED):
        result = reconcile(
            scenario.invoice, scenario.po, scenario.receipts, scenario.existing_invoices
        )
        if result.decision.outcome is not scenario.expected_outcome:
            mismatches.append(
                (scenario.label.value, result.decision.outcome.value, result.decision.reasons)
            )
    assert mismatches == []


def test_generator_covers_every_label_evenly():
    counts = Counter(s.label for s in generate(seed=7, count=12 * 10))
    assert set(counts) == set(CaseLabel)
    assert set(counts.values()) == {10}


def test_generator_is_deterministic_for_a_seed():
    first = [(s.label, s.invoice) for s in generate(5, 60)]
    second = [(s.label, s.invoice) for s in generate(5, 60)]
    assert first == second


def test_no_bad_invoice_is_ever_auto_approved():
    for scenario in generate(11, 12 * 40):
        result = reconcile(
            scenario.invoice, scenario.po, scenario.receipts, scenario.existing_invoices
        )
        if scenario.is_bad:
            assert result.decision.outcome.value != "AUTO_APPROVE", scenario.label
