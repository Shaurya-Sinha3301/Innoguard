# Evaluation: oracle extractor

> Controls test, not an accuracy result. The extractions are simulated (oracle); these figures say nothing about a real model's accuracy.

| Metric | Overall | dev | held_out |
| --- | --- | --- | --- |
| cases | 216 | 144 | 72 |
| false_approvals | 0 | 0 | 0 |
| misread_auto_approvals | 0 | 0 | 0 |
| false_approval_proportion | 0.0 | 0.0 | 0.0 |
| bad_invoice_escape_rate | 0.0 | 0.0 | 0.0 |
| detection_precision | 0.9 | 0.9 | 0.9 |
| detection_recall | 1.0 | 1.0 | 1.0 |
| straight_through_rate | 1.0 | 1.0 | 1.0 |
| review_rate | 0.75 | 0.75 | 0.75 |
| decision_accuracy | 1.0 | 1.0 | 1.0 |
| model_calls | 0 | 0 | 0 |
| p50_latency_ms | None | None | None |
| p95_latency_ms | None | None | None |
| cost_per_request_usd | None | None | None |
| avg_tokens_per_second | None | None | None |

Field exact match:

- invoice_number: 1.0
- vendor_id: 1.0
- po_number: 1.0
- currency: 1.0
- subtotal: 1.0
- tax: 1.0
- total: 1.0
- lines: 1.0

Escaped bad invoices: 0
