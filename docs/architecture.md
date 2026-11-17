# Design and trade-offs

## Goal

Automate the routine part of accounts-payable reconciliation without ever letting a model
approve or pay anything on its own. The system should clear clean invoices, explain every
exception in terms a clerk can check, and be able to answer an auditor's question: what did
it see, what did it decide, and who approved.

## Boundaries

| Component | Responsibility | Does not |
| --- | --- | --- |
| Extraction (LLM) | Read fields and quote the text each came from | Compute, match, decide or write |
| Normaliser | Turn printed strings into typed values; refuse ambiguous ones | Guess |
| Evidence check | Confirm each quoted snippet is in the PDF; cap confidence if not | Trust the model's confidence |
| Matching + validation | Three-way match and arithmetic, in plain code | Depend on the model |
| Policy | Decide which findings block auto-approval | Blend signals into one score |
| Workflow | Own states, transitions, approvals and versions | Write to the system of record |
| Posting service | The only writer to the system of record | Post without a valid approval |
| MCP server | Read-only lookups for agents | Write anything (Release 1) |

## Key decisions

**Three-way matching, not invoice-to-PO.** A PO says what was ordered; a goods receipt
says what arrived. Matching only to the PO would approve invoices for goods that never
came. Receipts are summed across deliveries, and earlier invoices against the same PO count
towards the ordered and received quantities, so split invoices cannot over-bill.

**Three signals, not one score.** A perfectly read invoice can still be a duplicate, lack
a receipt, or exceed policy. Extraction confidence, match quality and policy eligibility
stay separate, and a hard violation overrides confidence.

**Duplicate detection is separate from posting idempotency.** Duplicates are caught in two
layers in Release 1: identical file hash (rejected) and vendor plus normalised invoice
number (sent to review). Posting idempotency is a different mechanism that stops the same
approved posting being applied twice.

**Approvals are bound to a version and an amount.** A material edit increments the
invoice version, which voids every earlier approval. The posting service checks for an
approval on the current version with the current amount.

**Posting has three layers of protection.** A row lock serialises concurrent attempts; an
idempotency key (invoice, version, amount) turns repeats into a no-op; a database unique
constraint is the last line of defence. Tests show exactly one posting with the lock on,
and still exactly one with the lock switched off.

**The model call is outside every transaction.** The job commits the EXTRACTING state,
calls the model, then records the result in a new transaction. A slow model never holds a
row lock.

**Transactional outbox.** An upload and its job are written in one transaction; a
dispatcher publishes pending rows with `SKIP LOCKED`, backing off while the broker is
down. Delivery is at-least-once, so the extraction job is idempotent: a duplicate delivery
finds the invoice past extraction and stops.

**Failures are classified.** Rate limits, network and 5xx errors are transient and retried
with backoff; refusals, malformed output and rejected requests are permanent. Either kind,
once out of attempts, lands in the dead-letter table with an operator replay.

**Record and replay.** Every live model response is stored by file hash. CI, evaluation and
the hosted demo replay recordings, so results are reproducible and free. Simulated records
are labelled with their own provider name and can never be mistaken for model output.

**The audit log is append-only in the database.** A trigger rejects UPDATE, DELETE and
TRUNCATE on audit events, so the guarantee does not depend on application code.

## Thresholds (Release 1 defaults)

| Setting | Value | Where |
| --- | --- | --- |
| Price tolerance | 2% of the PO price | `domain/models.py` `Tolerances` |
| Quantity tolerance | 0% | same |
| Amount tolerance for arithmetic | 0.01 | same |
| Minimum extraction confidence | 0.90 | `domain/decision.py` `Thresholds` |
| Minimum match quality | 1.0 (every line clean) | same |
| Auto-approval value limit | 10,000 (invoice currency) | `domain/policy.py` `PolicyConfig` |
| Confidence cap for unverified evidence | 0.5 | `extraction/evidence.py` |
| Extraction attempts | 4 | `EXTRACTION_MAX_ATTEMPTS` |

These were chosen for the synthetic data, not tuned on a real backlog. The threshold curve
in `eval/reports/` shows the trade-off between automation and risk as confidence moves.

## Evaluation design

The locked set is split by vendor layout: two layouts are used while developing and one is
held out. Metrics state their denominators. Besides the false-approval count, the harness
counts *misread* auto-approvals, a clean invoice approved with a wrongly read field, because
that would post wrong data even though the invoice itself was fine. Both are gated at zero.

## Not in Release 1

Scanned documents, near-duplicate detection, credit notes and multi-currency, posting
through a gated MCP capability, calibration, tracing export, multi-tenancy, SSO, and posting
reversal. The schema already carries `currency` and `invoice_type` so these extend it
rather than rewrite it.
