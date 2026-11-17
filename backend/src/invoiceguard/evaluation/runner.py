"""Score the pipeline on the locked set.

    python -m invoiceguard.evaluation.runner --extractor oracle --gate
    python -m invoiceguard.evaluation.runner --extractor noisy --noise-rate 0.4 --gate
    python -m invoiceguard.evaluation.runner --extractor live \
        --provider groq --model openai/gpt-oss-20b
    python -m invoiceguard.evaluation.runner --extractor replay \
        --provider groq --model openai/gpt-oss-20b

`live` calls the model and records every response under eval/recordings/<provider>__<model>/;
`replay` re-scores those recordings without calling the model. Only live or replay runs
measure a real model. Oracle and noisy runs test the controls, not extraction accuracy.
"""

import argparse
import dataclasses
import json
import random
import statistics
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from invoiceguard.domain.decision import Outcome, Signals, Thresholds, decide
from invoiceguard.domain.duplicates import file_hash
from invoiceguard.domain.models import Invoice
from invoiceguard.domain.pipeline import reconcile
from invoiceguard.evaluation.dataset import Case, load_locked
from invoiceguard.evaluation.noise import NoisyExtractor
from invoiceguard.extraction.cache import CachedExtractor
from invoiceguard.extraction.client import ExtractionError, Extractor, LlmUsage
from invoiceguard.extraction.evidence import check_evidence, page_texts
from invoiceguard.extraction.fakes import FakeExtractor, truth_as_extraction
from invoiceguard.extraction.metrics import cost_usd, tokens_per_second
from invoiceguard.extraction.normalizer import normalize
from invoiceguard.generator.cases import CaseLabel, Scenario, generate_scenario
from invoiceguard.generator.pdf import render_invoice_pdf

REPO_EVAL = Path(__file__).resolve().parents[4] / "eval"
REAL_PROVIDERS = {"groq", "anthropic"}  # simulated extractors use their own provider names
HEADER_FIELDS = ("invoice_number", "vendor_id", "po_number", "currency", "subtotal", "tax", "total")
_GOOD_AUTO = {"CLEAN", "PARTIAL_RECEIPT_BILLED_CORRECTLY"}


@dataclass
class CaseResult:
    case: Case
    expected: str
    is_bad: bool
    outcome: str
    reasons: list[str]
    confidence: Decimal
    hard_violations: list[str]
    match_quality: Decimal
    exact_duplicate: bool
    fields_correct: dict[str, bool] = field(default_factory=dict)
    usage: LlmUsage | None = None


def _materialise(case: Case) -> tuple[Scenario, bytes, Invoice]:
    scenario = generate_scenario(random.Random(case.index), case.index, CaseLabel(case.label))
    pdf = render_invoice_pdf(scenario.invoice, case.template)
    pdf_hash = file_hash(pdf)
    # The document's own hash is what duplicate detection sees in production.
    old = scenario.invoice.file_hash
    existing = tuple(
        dataclasses.replace(e, file_hash=pdf_hash) if e.file_hash == old else e
        for e in scenario.existing_invoices
    )
    truth = dataclasses.replace(scenario.invoice, file_hash=pdf_hash)
    return dataclasses.replace(scenario, invoice=truth, existing_invoices=existing), pdf, truth


def evaluate_case(case: Case, extractor: Extractor) -> CaseResult:
    scenario, pdf, truth = _materialise(case)
    base = {
        "case": case,
        "expected": scenario.expected_outcome.value,
        "is_bad": scenario.is_bad,
    }
    try:
        response = extractor.extract(pdf)
    except ExtractionError as exc:
        return CaseResult(
            **base,
            outcome=Outcome.NEEDS_REVIEW.value,
            reasons=["EXTRACTION_FAILED", str(exc)],
            confidence=Decimal(0),
            hard_violations=["EXTRACTION_FAILED"],
            match_quality=Decimal(0),
            exact_duplicate=False,
        )

    normalized = normalize(response.invoice, truth.file_hash)
    fields, evidence_issues = check_evidence(normalized.fields, page_texts(pdf))
    confidence = min((f.confidence for f in fields if f.value), default=Decimal(0))

    if normalized.invoice is None:
        issues = ["EXTRACTION_INCOMPLETE", *normalized.issues, *evidence_issues]
        return CaseResult(
            **base,
            outcome=Outcome.NEEDS_REVIEW.value,
            reasons=issues,
            confidence=confidence,
            hard_violations=issues,
            match_quality=Decimal(0),
            exact_duplicate=False,
            usage=response.usage,
        )

    read = normalized.invoice
    # As in production, the PO and receipts are looked up by the number that was read.
    po_found = scenario.po is not None and read.po_number == scenario.po.po_number
    result = reconcile(
        read,
        scenario.po if po_found else None,
        scenario.receipts if po_found else (),
        scenario.existing_invoices,
        extraction_confidence=confidence,
    )
    fields_correct = {name: getattr(read, name) == getattr(truth, name) for name in HEADER_FIELDS}
    fields_correct["lines"] = read.lines == truth.lines
    return CaseResult(
        **base,
        outcome=result.decision.outcome.value,
        reasons=list(result.decision.reasons),
        confidence=confidence,
        hard_violations=list(result.policy.hard_violations),
        match_quality=result.match.match_quality,
        exact_duplicate=result.duplicates.exact,
        fields_correct=fields_correct,
        usage=response.usage,
    )


def _ratio(part: int, whole: int) -> float | None:
    return None if whole == 0 else round(part / whole, 4)


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return round(statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1], 1)


def compute_metrics(results: list[CaseResult]) -> dict[str, Any]:
    """Every rate states its denominator in its name or in eval/README.md."""
    n = len(results)
    auto = [r for r in results if r.outcome == Outcome.AUTO_APPROVE.value]
    bad = [r for r in results if r.is_bad]
    flagged = [r for r in results if r.outcome != Outcome.AUTO_APPROVE.value]
    bad_auto = [r for r in auto if r.is_bad]
    eligible = [r for r in results if not r.is_bad and r.case.label in _GOOD_AUTO]

    fields: dict[str, float | None] = {}
    scored = [r for r in results if r.fields_correct]
    for name in (*HEADER_FIELDS, "lines"):
        fields[name] = _ratio(sum(r.fields_correct.get(name, False) for r in scored), len(scored))

    usages = [r.usage for r in results if r.usage and r.usage.provider in REAL_PROVIDERS]
    latencies = sorted(float(u.latency_ms) for u in usages)
    costs = [cost_usd(u) for u in usages]
    tps = [float(t) for t in (tokens_per_second(u) for u in usages) if t is not None]

    # A clean invoice that was misread and still auto-approved would post wrong data. That
    # is a failure too, even though the invoice itself was not "bad".
    misread_auto = [r for r in auto if r.fields_correct and not all(r.fields_correct.values())]

    return {
        "cases": n,
        "false_approvals": len(bad_auto),
        "misread_auto_approvals": len(misread_auto),
        "false_approval_proportion": _ratio(len(bad_auto), len(auto)),  # bad auto / all auto
        "bad_invoice_escape_rate": _ratio(len(bad_auto), len(bad)),  # bad auto / all bad
        "detection_precision": _ratio(sum(r.is_bad for r in flagged), len(flagged)),
        "detection_recall": _ratio(sum(r.is_bad for r in flagged), len(bad)),
        "straight_through_rate": _ratio(
            sum(r.outcome == Outcome.AUTO_APPROVE.value for r in eligible), len(eligible)
        ),  # auto-approved / clean invoices eligible for auto-approval
        "review_rate": _ratio(sum(r.outcome == Outcome.NEEDS_REVIEW.value for r in results), n),
        "decision_accuracy": _ratio(sum(r.outcome == r.expected for r in results), n),
        "field_exact_match": fields,
        "model_calls": len(usages),
        "p50_latency_ms": _percentile(latencies, 50),
        "p95_latency_ms": _percentile(latencies, 95),
        "cost_per_request_usd": (
            None if not costs else float((sum(costs) / len(costs)).quantize(Decimal("0.000001")))
        ),
        "avg_tokens_per_second": None if not tps else round(sum(tps) / len(tps), 1),
    }


def threshold_curve(results: list[CaseResult], steps: list[Decimal]) -> list[dict[str, Any]]:
    """Coverage (share of all cases auto-approved) against bad-invoice escape rate, as the
    extraction-confidence threshold moves. Hard violations always block, at any threshold."""
    from invoiceguard.domain.policy import PolicyResult

    bad_total = sum(r.is_bad for r in results)
    rows = []
    for threshold in steps:
        auto = bad_auto = 0
        for r in results:
            decision = decide(
                Signals(
                    extraction_confidence=r.confidence,
                    match_quality=r.match_quality,
                    policy=PolicyResult(not r.hard_violations, tuple(r.hard_violations)),
                    exact_duplicate=r.exact_duplicate,
                ),
                Thresholds(min_extraction_confidence=threshold),
            )
            if decision.outcome is Outcome.AUTO_APPROVE:
                auto += 1
                bad_auto += r.is_bad
        rows.append(
            {
                "threshold": float(threshold),
                "coverage": _ratio(auto, len(results)),
                "escape_rate": _ratio(bad_auto, bad_total),
            }
        )
    return rows


def curve_svg(rows: list[dict[str, Any]]) -> str:
    """A small dependency-free SVG of the threshold curve."""
    w, h, pad = 520, 300, 48
    xs = [r["threshold"] for r in rows]
    lo, hi = min(xs), max(xs)

    def x(v: float) -> float:
        return pad + (v - lo) / ((hi - lo) or 1) * (w - 2 * pad)

    def y(v: float | None) -> float:
        return h - pad - (v or 0) * (h - 2 * pad)

    def path(key: str) -> str:
        return " ".join(
            f"{'M' if i == 0 else 'L'}{x(r['threshold']):.1f},{y(r[key]):.1f}"
            for i, r in enumerate(rows)
        )

    header = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        'font-family="sans-serif" font-size="11">'
    )
    legend = (
        f'<text x="{w - pad}" y="{pad - 20}" text-anchor="end" fill="#1d4ed8">'
        "coverage (auto-approved / all)</text>\n"
        f'<text x="{w - pad}" y="{pad - 6}" text-anchor="end" fill="#dc2626">'
        "escape rate (bad auto-approved / all bad)</text>"
    )
    return f"""{header}
<rect width="{w}" height="{h}" fill="white"/>
<line x1="{pad}" y1="{h - pad}" x2="{w - pad}" y2="{h - pad}" stroke="#888"/>
<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{h - pad}" stroke="#888"/>
<text x="{w / 2}" y="{h - 12}" text-anchor="middle">extraction-confidence threshold</text>
<text x="{pad - 6}" y="{pad}" text-anchor="end">100%</text>
<text x="{pad - 6}" y="{h - pad}" text-anchor="end">0%</text>
<text x="{pad}" y="{h - pad + 14}" text-anchor="middle">{lo}</text>
<text x="{w - pad}" y="{h - pad + 14}" text-anchor="middle">{hi}</text>
<path d="{path("coverage")}" fill="none" stroke="#1d4ed8" stroke-width="2"/>
<path d="{path("escape_rate")}" fill="none" stroke="#dc2626" stroke-width="2"/>
{legend}
</svg>
"""


def run(cases: list[Case], extractor: Extractor) -> dict[str, Any]:
    results = [evaluate_case(c, extractor) for c in cases]
    by_split = {
        split: compute_metrics([r for r in results if r.case.split == split])
        for split in sorted({r.case.split for r in results})
    }
    escapes = [
        {"case": r.case.case_id, "label": r.case.label, "template": r.case.template}
        for r in results
        if r.is_bad and r.outcome == Outcome.AUTO_APPROVE.value
    ]
    steps = [Decimal(s) / 100 for s in range(50, 100, 5)] + [Decimal("0.99")]
    return {
        "overall": compute_metrics(results),
        "by_split": by_split,
        "escaped_bad_invoices": escapes,
        "curve": threshold_curve(results, steps),
    }


def recordings_dir(provider: str, model: str) -> Path:
    """One folder per provider and model; model ids may contain '/', so it is replaced."""
    return REPO_EVAL / "recordings" / f"{provider}__{model.replace('/', '__')}"


def build_extractor(
    kind: str, cases: list[Case], model: str, rate: float, provider: str = "groq"
) -> Extractor:
    recordings = recordings_dir(provider, model)
    if kind == "live":
        from invoiceguard.jobs.extractor_factory import live_extractor

        return CachedExtractor(recordings, live_extractor(provider, model))
    if kind == "replay":
        return CachedExtractor(recordings)
    truth: dict[str, tuple[Invoice, str]] = {}
    for case in cases:
        _, pdf, invoice = _materialise(case)
        truth[file_hash(pdf)] = (invoice, case.template)
    if kind == "noisy":
        return NoisyExtractor(truth, rate=rate)

    class Oracle:
        def extract(self, pdf: bytes):
            invoice, template = truth[file_hash(pdf)]
            return FakeExtractor(truth_as_extraction(invoice, template)).extract(pdf)

    return Oracle()


def check_gate(kind: str, metrics: dict[str, Any], gates: dict[str, Any]) -> list[str]:
    failures = []
    for rule, limit in gates.get(kind, {}).items():
        name, bound = rule.rsplit("_", 1)
        value = metrics[name]
        if value is None:
            continue
        if bound == "max" and value > limit:
            failures.append(f"{name} = {value}, above the allowed {limit}")
        if bound == "min" and value < limit:
            failures.append(f"{name} = {value}, below the required {limit}")
    return failures


def to_markdown(kind: str, report: dict[str, Any]) -> str:
    lines = [f"# Evaluation: {kind} extractor", ""]
    if kind in ("oracle", "noisy"):
        lines += [
            "> Controls test, not an accuracy result. The extractions are simulated "
            f"({kind}); these figures say nothing about a real model's accuracy.",
            "",
        ]
    lines += ["| Metric | Overall | " + " | ".join(report["by_split"]) + " |"]
    lines += ["| --- | --- | " + " | ".join("---" for _ in report["by_split"]) + " |"]
    keys = [k for k, v in report["overall"].items() if not isinstance(v, dict)]
    for key in keys:
        row = [str(report["overall"][key])] + [str(m[key]) for m in report["by_split"].values()]
        lines.append(f"| {key} | " + " | ".join(row) + " |")
    lines += ["", "Field exact match:", ""]
    for name, value in report["overall"]["field_exact_match"].items():
        lines.append(f"- {name}: {value}")
    lines += ["", f"Escaped bad invoices: {len(report['escaped_bad_invoices'])}", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate InvoiceGuard on the locked set")
    parser.add_argument("--extractor", choices=["oracle", "noisy", "replay", "live"], required=True)
    parser.add_argument("--provider", choices=["groq", "anthropic"], default="groq")
    parser.add_argument("--model", default="openai/gpt-oss-20b")
    parser.add_argument("--noise-rate", type=float, default=0.4)
    parser.add_argument("--set", type=Path, default=REPO_EVAL / "locked" / "cases.json")
    parser.add_argument("--out", type=Path, default=REPO_EVAL / "reports")
    parser.add_argument("--gate", action="store_true", help="exit non-zero if a gate fails")
    args = parser.parse_args()

    cases = load_locked(args.set)
    extractor = build_extractor(
        args.extractor, cases, args.model, args.noise_rate, provider=args.provider
    )
    report = run(cases, extractor)

    name = (
        args.extractor
        if args.extractor in ("oracle", "noisy")
        else f"{args.extractor}-{recordings_dir(args.provider, args.model).name}"
    )
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{name}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.out / f"{name}.md").write_text(to_markdown(args.extractor, report), encoding="utf-8")
    (args.out / f"{name}-curve.svg").write_text(curve_svg(report["curve"]), encoding="utf-8")
    print(to_markdown(args.extractor, report))

    if args.gate:
        gates = json.loads((REPO_EVAL / "gates.json").read_text(encoding="utf-8"))
        failures = check_gate(args.extractor, report["overall"], gates)
        for failure in failures:
            print(f"GATE FAILED: {failure}", file=sys.stderr)
        return 1 if failures else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
