# Evaluation: noisy extractor

> Controls test, not an accuracy result. The extractions are simulated (noisy); these figures say nothing about a real model's accuracy.

| Metric | Overall | dev | held_out |
| --- | --- | --- | --- |
| cases | 216 | 144 | 72 |
| false_approvals | 0 | 0 | 0 |
| misread_auto_approvals | 0 | 0 | 0 |
| false_approval_proportion | 0.0 | 0.0 | 0.0 |
| bad_invoice_escape_rate | 0.0 | 0.0 | 0.0 |
| detection_precision | 0.8438 | 0.8308 | 0.871 |
| detection_recall | 1.0 | 1.0 | 1.0 |
| straight_through_rate | 0.6667 | 0.5833 | 0.8333 |
| review_rate | 0.8056 | 0.8194 | 0.7778 |
| decision_accuracy | 0.9444 | 0.9306 | 0.9722 |
| model_calls | 0 | 0 | 0 |
| p50_latency_ms | None | None | None |
| p95_latency_ms | None | None | None |
| cost_per_request_usd | None | None | None |
| avg_tokens_per_second | None | None | None |

Field exact match:

- invoice_number: 1.0
- vendor_id: 0.9259
- po_number: 0.9398
- currency: 1.0
- subtotal: 1.0
- tax: 1.0
- total: 0.9259
- lines: 0.8796

Escaped bad invoices: 0
