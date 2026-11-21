# Evaluation: noisy extractor

> Controls test, not an accuracy result. The extractions are simulated (noisy); these figures say nothing about a real model's accuracy.

| Metric | Overall | dev | held_out |
| --- | --- | --- | --- |
| cases | 216 | 144 | 72 |
| false_approvals | 0 | 0 | 0 |
| misread_auto_approvals | 1 | 1 | 0 |
| false_approval_proportion | 0.0 | 0.0 | 0.0 |
| bad_invoice_escape_rate | 0.0 | 0.0 | 0.0 |
| detection_precision | 0.8482 | 0.8372 | 0.871 |
| detection_recall | 1.0 | 1.0 | 1.0 |
| straight_through_rate | 0.6944 | 0.625 | 0.8333 |
| review_rate | 0.8009 | 0.8125 | 0.7778 |
| decision_accuracy | 0.9491 | 0.9375 | 0.9722 |
| model_calls | 0 | 0 | 0 |
| p50_latency_ms | None | None | None |
| p95_latency_ms | None | None | None |
| cost_per_request_usd | None | None | None |
| avg_tokens_per_second | None | None | None |

Field exact match:

- invoice_number: 1.0
- vendor_id: 0.9259
- po_number: 0.9352
- currency: 1.0
- subtotal: 1.0
- tax: 1.0
- total: 0.9398
- lines: 0.8843

Escaped bad invoices: 0
