"""Score the expenses pack on a locked synthetic set.

    python -m invoiceguard.packs.expenses.evaluation --extractor oracle --gate
    python -m invoiceguard.packs.expenses.evaluation --extractor noisy --gate

Oracle and noisy runs test the controls with simulated extraction. They are not model
accuracy results: they show that the rules, the evidence check and the card-statement
cross-check catch the errors a reader could make, not how often a real model makes them.

The set is split by receipt layout: "slip" is held out. Cases are pinned by a SHA-256 hash,
and the runner refuses a set whose content no longer matches its pin. The gates are shared
with the invoices pack (eval/gates.json): no bad claim auto-approved, and no claim
auto-approved with a misread field.
"""

import argparse
import hashlib
import json
import random
import sys
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from invoiceguard.domain.decision import Outcome
from invoiceguard.extraction.client import ExtractionError, Extractor
from invoiceguard.extraction.evidence import check_evidence, page_texts
from invoiceguard.packs.expenses import PACK
from invoiceguard.packs.expenses.fakes import NoisyExpenseExtractor, truth_as_extraction
from invoiceguard.packs.expenses.generator import (
    HELD_OUT_TEMPLATES,
    TEMPLATES,
    TODAY,
    ExpenseLabel,
    ExpenseScenario,
    generate_expense_scenario,
    render_expense_pdf,
)
from invoiceguard.packs.expenses.models import Expense
from invoiceguard.packs.expenses.rules import reconcile_expense

REPO_EVAL = Path(__file__).resolve().parents[5] / "eval"
LOCKED_PATH = REPO_EVAL / "locked" / "expense_cases.json"
GATES_PATH = REPO_EVAL / "gates.json"
PER_LABEL = 18
FIELDS = (
    "employee_id",
    "merchant",
    "expense_date",
    "currency",
    "total",
    "tax",
    "card_last4",
    "category",
)


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    index: int
    label: str
    template: str
    split: str  # "dev" or "held_out"


def build_cases(per_label: int = PER_LABEL) -> list[EvalCase]:
    cases = []
    for label_no, label in enumerate(ExpenseLabel):
        for k in range(per_label):
            template = TEMPLATES[k % len(TEMPLATES)]
            split = "held_out" if template in HELD_OUT_TEMPLATES else "dev"
            index = 200_000 + label_no * 1_000 + k
            cases.append(
                EvalCase(f"{label.value.lower()}-{k:03d}", index, label.value, template, split)
            )
    return cases


def content_hash(cases: list[EvalCase]) -> str:
    canonical = json.dumps([asdict(c) for c in cases], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def write_locked(path: Path = LOCKED_PATH) -> None:
    cases = build_cases()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "description": "Locked evaluation set for the expenses pack. Do not tune on it.",
        "held_out_templates": list(HELD_OUT_TEMPLATES),
        "sha256": content_hash(cases),
        "cases": [asdict(c) for c in cases],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_locked(path: Path = LOCKED_PATH) -> list[EvalCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = [EvalCase(**c) for c in data["cases"]]
    if content_hash(cases) != data["sha256"] or cases != build_cases():
        raise SystemExit("the locked expense set does not match its pin; refusing to score it")
    return cases


@dataclass
class CaseResult:
    case: EvalCase
    expected: str
    expected_reason: str | None
    is_bad: bool
    outcome: str
    reasons: list[str]
    fields_correct: dict[str, bool] = field(default_factory=dict)


def _materialise(case: EvalCase) -> tuple[ExpenseScenario, bytes, Expense]:
    scenario = generate_expense_scenario(
        random.Random(case.index), case.index, ExpenseLabel(case.label)
    )
    pdf = render_expense_pdf(scenario.expense, case.template)
    pdf_hash = hashlib.sha256(pdf).hexdigest()
    # The document's own hash is what duplicate detection sees in production.
    old = scenario.expense.file_hash
    truth = Expense(**{**scenario.expense.__dict__, "file_hash": pdf_hash})
    existing = tuple(
        type(e)(**{**e.__dict__, "file_hash": pdf_hash}) if e.file_hash == old else e
        for e in scenario.existing
    )
    scenario = ExpenseScenario(
        scenario.label,
        truth,
        scenario.employee,
        scenario.categories,
        scenario.transactions,
        existing,
    )
    return scenario, pdf, truth


def evaluate_case(case: EvalCase, extractor: Extractor) -> CaseResult:
    scenario, pdf, truth = _materialise(case)
    base = {
        "case": case,
        "expected": scenario.expected_outcome.value,
        "expected_reason": scenario.expected_reason,
        "is_bad": scenario.is_bad,
    }
    try:
        response = extractor.extract(pdf, PACK.id)
    except ExtractionError as exc:
        return CaseResult(
            **base, outcome=Outcome.NEEDS_REVIEW.value, reasons=["EXTRACTION_FAILED", str(exc)]
        )

    normalized = PACK.normalize(response.extracted, truth.file_hash)
    fields, evidence_issues = check_evidence(normalized.fields, page_texts(pdf))
    confidence = min((f.confidence for f in fields if f.value), default=Decimal(0))
    if normalized.value is None:
        reasons = ["EXTRACTION_INCOMPLETE", *normalized.issues, *evidence_issues]
        return CaseResult(**base, outcome=Outcome.NEEDS_REVIEW.value, reasons=reasons)

    read: Expense = normalized.value
    # As in production, reference data is looked up by what was read.
    employee = (
        scenario.employee
        if scenario.employee and scenario.employee.employee_id == read.employee_id
        else None
    )
    category = next((c for c in scenario.categories if c.category == read.category), None)
    transactions = [t for t in scenario.transactions if t.card_last4 == read.card_last4]
    result = reconcile_expense(
        read,
        employee,
        category,
        transactions,
        scenario.existing,
        today=TODAY,
        extraction_confidence=confidence,
        tolerances=PACK._tolerances(),
        policy=PACK._policy(),
        thresholds=PACK._thresholds(),
    )
    correct = {name: getattr(read, name) == getattr(truth, name) for name in FIELDS}
    return CaseResult(
        **base,
        outcome=result.decision.outcome.value,
        reasons=list(result.decision.reasons),
        fields_correct=correct,
    )


def _ratio(part: int, whole: int) -> float | None:
    return None if whole == 0 else round(part / whole, 4)


def compute_metrics(results: list[CaseResult]) -> dict[str, Any]:
    """Every rate states its denominator in its name."""
    auto = [r for r in results if r.outcome == Outcome.AUTO_APPROVE.value]
    bad = [r for r in results if r.is_bad]
    bad_auto = [r for r in auto if r.is_bad]
    # A clean claim that was misread and still auto-approved would reimburse wrong data.
    misread_auto = [r for r in auto if r.fields_correct and not all(r.fields_correct.values())]
    eligible = [r for r in results if r.case.label == ExpenseLabel.CLEAN.value]
    return {
        "cases": len(results),
        "false_approvals": len(bad_auto),
        "misread_auto_approvals": len(misread_auto),
        "bad_claim_escape_rate": _ratio(len(bad_auto), len(bad)),  # bad auto / all bad
        "straight_through_rate": _ratio(
            sum(r.outcome == Outcome.AUTO_APPROVE.value for r in eligible), len(eligible)
        ),  # auto-approved / clean claims
        "review_rate": _ratio(
            sum(r.outcome == Outcome.NEEDS_REVIEW.value for r in results), len(results)
        ),
        "decision_accuracy": _ratio(sum(r.outcome == r.expected for r in results), len(results)),
        "named_reason_present": _ratio(
            sum(r.expected_reason in r.reasons for r in results if r.expected_reason),
            sum(1 for r in results if r.expected_reason),
        ),  # cases whose expected reason code was reported / cases that have one
    }


def check_gates(kind: str, metrics: dict[str, Any]) -> list[str]:
    gates = json.loads(GATES_PATH.read_text(encoding="utf-8"))[kind]
    failures = []
    if metrics["false_approvals"] > gates["false_approvals_max"]:
        failures.append(
            f"false approvals {metrics['false_approvals']} > {gates['false_approvals_max']}"
        )
    if metrics["misread_auto_approvals"] > gates["misread_auto_approvals_max"]:
        failures.append(f"misread auto-approvals {metrics['misread_auto_approvals']}")
    minimum = gates.get("decision_accuracy_min")
    if minimum is not None and (metrics["decision_accuracy"] or 0) < minimum:
        failures.append(f"decision accuracy {metrics['decision_accuracy']} < {minimum}")
    return failures


def run(kind: str, noise_rate: float, seed: int) -> dict[str, Any]:
    cases = load_locked()
    truth: dict[str, tuple[Expense, str]] = {}
    for case in cases:
        _, pdf, expense = _materialise(case)
        truth[hashlib.sha256(pdf).hexdigest()] = (expense, case.template)

    class Oracle:
        def extract(self, pdf, pack=None):
            from invoiceguard.extraction.client import ExtractionResponse, LlmUsage

            expense, template = truth[hashlib.sha256(pdf).hexdigest()]
            return ExtractionResponse(
                truth_as_extraction(expense, template),
                LlmUsage("simulated-oracle", "oracle", 0, 0, 0),
            )

    extractor = (
        Oracle() if kind == "oracle" else NoisyExpenseExtractor(truth, rate=noise_rate, seed=seed)
    )
    results = [evaluate_case(c, extractor) for c in cases]
    overall = compute_metrics(results)
    held_out = compute_metrics([r for r in results if r.case.split == "held_out"])
    return {
        "pack": PACK.id,
        "extractor": kind,
        "noise_rate": noise_rate if kind == "noisy" else None,
        "all": overall,
        "held_out": held_out,
        "escaped": [r.case.case_id for r in results if r.is_bad and r.outcome == "AUTO_APPROVE"],
        "misread_auto": [
            r.case.case_id
            for r in results
            if r.outcome == "AUTO_APPROVE"
            and r.fields_correct
            and not all(r.fields_correct.values())
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Score the expenses pack on the locked set")
    parser.add_argument("--extractor", choices=("oracle", "noisy"), default="oracle")
    parser.add_argument("--noise-rate", type=float, default=0.4)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--write-locked", action="store_true")
    args = parser.parse_args()
    if args.write_locked:
        write_locked()
        print(f"wrote {LOCKED_PATH}")
        return
    report = run(args.extractor, args.noise_rate, args.seed)
    print(json.dumps(report, indent=2))
    if args.gate:
        failures = check_gates(args.extractor, report["all"]) + check_gates(
            args.extractor, report["held_out"]
        )
        if failures:
            print("GATE FAILED: " + "; ".join(failures), file=sys.stderr)
            sys.exit(1)
        print("gates passed")


if __name__ == "__main__":
    main()
