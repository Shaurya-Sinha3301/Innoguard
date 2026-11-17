# InvoiceGuard

A controlled financial workflow for accounts payable. It reads supplier invoices,
reconciles them against purchase orders **and** goods receipts (three-way matching),
applies deterministic controls, sends anything doubtful to a human reviewer, and keeps an
append-only audit trail that can reconstruct every decision.

The model only reads the document. Arithmetic, matching, policy and posting are plain,
tested code, and nothing reaches the system of record without a valid, version-bound
approval.

> **Status: Release 1.** One complete workflow on clean PDFs. All data is synthetic, and
> no accuracy figure is published until a reproducible run against a real model produces
> it (see [Evaluation](#evaluation)).

## How it works

```mermaid
flowchart LR
    U[PDF upload] --> O[(Outbox row,<br/>same transaction)]
    O --> D[Dispatcher] --> Q[Redis / Celery]
    Q --> X[Extraction<br/>LLM, structured output]
    X --> N[Normaliser +<br/>evidence check]
    N --> M[Three-way match<br/>PO + receipt + invoice]
    M --> P[Policy]
    P -->|all clear| A[Auto-approve]
    P -->|anything doubtful| R[Review queue]
    P -->|exact duplicate| J[Reject]
    R -->|human approves| AP[Approved v N]
    A --> S[Posting service<br/>lock + idempotency key + unique constraint]
    AP --> S
    S --> DB[(Postgres +<br/>append-only audit log)]
```

The decision uses three separate signals, never one blended score:

| Signal | Question |
| --- | --- |
| Extraction confidence | Was the document read correctly? (capped if the quoted evidence is not in the PDF) |
| Match quality | Do the invoice, PO line and receipt describe the same transaction? |
| Policy eligibility | Is this allowed to proceed (tolerances, receipts, duplicates, value limit)? |

A hard policy violation always blocks auto-approval, even at perfect confidence.

## What it demonstrates

- **Concurrency-safe posting.** Two to six workers post the same approved invoice at once
  against real Postgres; exactly one posting happens and every outcome is audited. A second
  test turns the row lock off and shows the unique constraint alone still holds.
- **Reliable background work.** A transactional outbox means a job is never lost when Redis
  is down; verified by stopping Redis mid-run. Retries, an idempotent job, and a dead-letter
  queue with replay.
- **Version-bound approvals.** Editing an approved invoice voids the approval; posting
  checks the approval matches the current version and amount.
- **Extraction provenance.** Every value is stored with its confidence and the exact text
  it came from; a quoted snippet that is not in the PDF caps confidence.
- **Prompt-injection resistance.** A PDF that tells the model to approve it cannot: even a
  simulated fooled extraction is caught by the evidence check and the arithmetic.
- **Evaluation discipline.** A hash-locked test set with a held-out vendor layout, metrics
  with stated denominators, and CI gates that fail on any wrongly auto-approved invoice.
- **Least-privilege agent tools.** A read-only MCP server whose calls run in database
  transactions that refuse writes.
- **LLM cost and latency per call**, with one trace ID per invoice.

## Quick start (local)

Requires Docker with Compose and Node 20+.

```bash
docker compose up --build -d
docker compose exec api python -m invoiceguard.generator.demo_data --count 16 --submit
cd web && npm install && npm run dev
```

Open http://localhost:5173 and sign in with the local development key `dev-key`. The demo
runs in replay mode with simulated extractions, so it needs no API key. To extract with a
real model, set `EXTRACTION_MODE=anthropic` and `ANTHROPIC_API_KEY` before starting.

Health check: `curl http://localhost:8000/health`

## Tests

```bash
cd backend && pip install -e ".[dev]" && ruff check . && pytest
```

Integration and concurrency tests create a throwaway Postgres database from the real
migrations, so they need Postgres running (Compose provides it).

## Evaluation

```bash
cd backend
python -m invoiceguard.evaluation.runner --extractor oracle --gate
python -m invoiceguard.evaluation.runner --extractor noisy --gate
```

Oracle and noisy runs test the controls with simulated extraction; they are not model
accuracy results. Real-model numbers come from a `live` run, which records responses so
`replay` can re-score them in CI. Details and metric definitions: [eval/README.md](eval/README.md).

## Repository layout

| Path | Contents |
| --- | --- |
| `backend/src/invoiceguard/domain` | Matching, validation, duplicates, policy, decision (no I/O) |
| `backend/src/invoiceguard/workflow` | State machine, approvals, posting service, audit log |
| `backend/src/invoiceguard/extraction` | Model client, normaliser, evidence check, cost metrics |
| `backend/src/invoiceguard/jobs` | Outbox, dispatcher, extraction job, dead letter and replay |
| `backend/src/invoiceguard/mcp_server` | Read-only MCP tools |
| `backend/src/invoiceguard/evaluation` | Locked set, simulated errors, runner and gates |
| `web/` | React review UI |
| `eval/` | Locked test set, gates, reports, model recordings |
| `docs/` | Design, deployment, runbook, case study |

## Documents

- [Design and trade-offs](docs/design.md)
- [Deployment](docs/deploy.md)
- [Runbook](docs/runbook.md)
- [Case study: what broke and what I changed](docs/case-study.md)
- [Discovery brief](docs/discovery-brief.md)
- [Platform feedback](docs/platform-feedback.md)

## Known limitations

- Synthetic data only, and a Postgres database stands in for the ERP. No claim of
  ERP-grade compliance or production readiness.
- Clean PDFs only; no scanned or handwritten invoices.
- Static API keys for reviewer identity; no SSO or user management.
- No posting reversal; a wrong posting is handled outside the system (see the runbook).
- The model's confidence is self-reported and uncalibrated; the evidence check is the
  independent control.

## Release 2 (planned, not built)

Scanned and skewed documents, near-duplicate and perceptual-hash detection, credit notes,
multi-currency, posting through a gated MCP capability with short-lived approval tokens,
calibration reports, tracing export (Langfuse or OpenTelemetry), and worker scaling.
