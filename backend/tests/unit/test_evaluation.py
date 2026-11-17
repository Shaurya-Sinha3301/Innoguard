import json
from decimal import Decimal

import pytest

from invoiceguard.evaluation import dataset
from invoiceguard.evaluation.runner import (
    CaseResult,
    build_extractor,
    check_gate,
    compute_metrics,
    evaluate_case,
)


def result(label, is_bad, outcome, expected="AUTO_APPROVE", fields_ok=True, split="dev"):
    case = dataset.Case(f"{label}-x", 1, label, "classic", split)
    return CaseResult(
        case=case,
        expected=expected,
        is_bad=is_bad,
        outcome=outcome,
        reasons=[],
        confidence=Decimal("0.98"),
        hard_violations=[],
        match_quality=Decimal(1),
        exact_duplicate=False,
        fields_correct={"total": fields_ok},
    )


def test_metric_denominators():
    results = [
        result("CLEAN", False, "AUTO_APPROVE"),
        result("CLEAN", False, "NEEDS_REVIEW"),
        result("PRICE_VARIANCE", True, "AUTO_APPROVE", expected="NEEDS_REVIEW"),
        result("PRICE_VARIANCE", True, "NEEDS_REVIEW", expected="NEEDS_REVIEW"),
        result("NO_PO", True, "NEEDS_REVIEW", expected="NEEDS_REVIEW"),
    ]
    m = compute_metrics(results)
    assert m["false_approvals"] == 1
    assert m["false_approval_proportion"] == 0.5  # 1 bad of 2 auto-approved
    assert m["bad_invoice_escape_rate"] == round(1 / 3, 4)  # 1 of 3 bad invoices
    assert m["detection_recall"] == round(2 / 3, 4)
    assert m["detection_precision"] == round(2 / 3, 4)  # 2 bad of 3 flagged
    assert m["straight_through_rate"] == 0.5  # 1 of 2 clean invoices


def test_misread_clean_invoice_that_is_auto_approved_is_counted():
    m = compute_metrics([result("CLEAN", False, "AUTO_APPROVE", fields_ok=False)])
    assert m["false_approvals"] == 0
    assert m["misread_auto_approvals"] == 1


def test_gate_checks_bounds():
    gates = {"noisy": {"false_approvals_max": 0, "decision_accuracy_min": 0.9}}
    assert check_gate("noisy", {"false_approvals": 0, "decision_accuracy": 0.95}, gates) == []
    failures = check_gate("noisy", {"false_approvals": 2, "decision_accuracy": 0.5}, gates)
    assert len(failures) == 2


def test_locked_set_detects_tampering(tmp_path):
    path = tmp_path / "cases.json"
    dataset.write_locked(path, dataset.build_cases(per_label=2))
    assert len(dataset.load_locked(path)) == 24
    data = json.loads(path.read_text())
    assert data["cases"][0]["label"] != "NO_PO"
    data["cases"][0]["label"] = "NO_PO"
    path.write_text(json.dumps(data))
    with pytest.raises(dataset.LockMismatch):
        dataset.load_locked(path)


def test_held_out_template_is_kept_out_of_dev():
    cases = dataset.build_cases(per_label=3)
    assert {c.template for c in cases if c.split == "held_out"} == set(dataset.HELD_OUT_TEMPLATES)
    assert not {c.template for c in cases if c.split == "dev"} & set(dataset.HELD_OUT_TEMPLATES)


def test_oracle_and_noisy_never_auto_approve_bad_or_misread_invoices():
    cases = dataset.build_cases(per_label=3)
    for kind in ("oracle", "noisy"):
        extractor = build_extractor(kind, cases, "unused", rate=0.6)
        metrics = compute_metrics([evaluate_case(c, extractor) for c in cases])
        assert metrics["false_approvals"] == 0, kind
        assert metrics["misread_auto_approvals"] == 0, kind
