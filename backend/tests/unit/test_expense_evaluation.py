"""The expenses evaluation gates run in the test suite too, not only in CI."""

import pytest

from invoiceguard.packs.expenses import evaluation


def test_the_locked_set_matches_its_pin():
    assert len(evaluation.load_locked()) == 216


@pytest.mark.parametrize("kind", ["oracle", "noisy"])
def test_the_gates_pass(kind):
    report = evaluation.run(kind, noise_rate=0.4, seed=7)
    assert evaluation.check_gates(kind, report["all"]) == []
    assert evaluation.check_gates(kind, report["held_out"]) == []
    assert report["escaped"] == [] and report["misread_auto"] == []


def test_the_oracle_gets_every_decision_right_on_every_layout():
    report = evaluation.run("oracle", noise_rate=0.0, seed=7)
    assert report["all"]["decision_accuracy"] == 1.0
    assert report["held_out"]["decision_accuracy"] == 1.0
