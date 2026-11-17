# Evaluation

All data here is synthetic. The locked set (`locked/cases.json`) has 216 cases: 12 case
types, 18 each, rendered in three vendor layouts. The `ledger` layout is held out, so its
results show how extraction copes with a layout that was never used while developing. The
file is pinned by a SHA-256 hash, and the runner refuses to score it if it has been edited.
Prompts and thresholds must not be tuned on it.

## Four ways to run it

| Extractor | What it measures | Calls the model |
| --- | --- | --- |
| `oracle` | Whether the decision rules reach the right outcome when extraction is perfect | No |
| `noisy` | Whether the controls catch simulated extraction errors (wrong digits, dropped lines, invented evidence, low confidence) | No |
| `live` | A real model on the locked set; every response is recorded under `recordings/<provider>__<model>/` | Yes |
| `replay` | Re-scores recorded responses, so the numbers are reproducible and free | No |

Only `live` and `replay` measure a real model. Oracle and noisy results test the controls
and say nothing about a model's accuracy.

```bash
cd backend
python -m invoiceguard.evaluation.runner --extractor oracle --gate
python -m invoiceguard.evaluation.runner --extractor noisy --gate
GROQ_API_KEY=... python -m invoiceguard.evaluation.runner --extractor live --provider groq --model openai/gpt-oss-20b
python -m invoiceguard.evaluation.runner --extractor replay --provider groq --model openai/gpt-oss-20b --gate
```

A live run over 216 PDFs makes 216 model calls; check current pricing before running it.
Commit `recordings/<provider>__<model>/` afterwards, and CI will re-score it on every change.

## Metrics and their denominators

| Metric | Definition |
| --- | --- |
| `false_approvals` | Count of bad invoices that were auto-approved |
| `misread_auto_approvals` | Count of auto-approved invoices with any field read wrongly (wrong data would be posted) |
| `false_approval_proportion` | Bad invoices auto-approved ÷ all auto-approved invoices |
| `bad_invoice_escape_rate` | Bad invoices auto-approved ÷ all bad invoices |
| `detection_precision` | Flagged invoices that are bad ÷ all flagged invoices (flagged = not auto-approved) |
| `detection_recall` | Bad invoices flagged ÷ all bad invoices |
| `straight_through_rate` | Clean invoices auto-approved ÷ clean invoices eligible for auto-approval |
| `review_rate` | Invoices sent to review ÷ all invoices |
| `decision_accuracy` | Invoices reaching their expected outcome ÷ all invoices |
| `field_exact_match` | Per field, correct reads ÷ invoices that were read |
| `p50/p95_latency_ms`, `cost_per_request_usd`, `avg_tokens_per_second` | Real model calls only |

"Bad" covers price and quantity variances, missing or partial receipts billed in full,
missing POs, vendor mismatches, total mismatches and duplicates. High-value invoices are
clean but always go to a human by policy, which is why oracle precision is below 1.0.

## Gates

`gates.json` holds the limits CI enforces: no false approvals and no misread
auto-approvals for any extractor, and every decision correct under perfect extraction.

## Threshold curve

Each run writes `reports/<run>-curve.svg`: coverage (share of all invoices auto-approved)
against the bad-invoice escape rate as the extraction-confidence threshold moves.
