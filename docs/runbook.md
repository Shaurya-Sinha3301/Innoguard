# Runbook

For whoever operates the demo. Commands assume the local Compose stack; on Render, run the
same SQL against the Neon database and read logs in the Render dashboard.

## First look

```bash
curl -s http://localhost:8000/health        # postgres and redis must both be "ok"
```

The Metrics page shows open failed jobs and pending outbox rows. Both should normally be 0.

## Outbox backlog: invoices stay in RECEIVED

**Signs:** `outbox_pending` keeps growing; uploads never leave RECEIVED.

1. Check Redis in `/health`. If it is down, nothing is lost: jobs wait in the outbox and
   go out with backoff once Redis is back. Fix Redis first.
2. Check the dispatcher is running:
   `docker compose logs dispatcher --since 10m` should show `outbox sent=...` lines.
   On Render the dispatcher runs inside the worker container; if it has died there, restart
   the worker service.
3. Rows that keep failing show a rising `attempts`:
   `SELECT id, attempts, available_at FROM outbox WHERE status = 'PENDING' ORDER BY id;`

## Failed jobs (dead letter)

**Signs:** invoices in FAILED; entries on the Failed jobs page.

1. Read the error. `retries exhausted` means the model or network kept failing;
   `no recorded extraction` in replay mode means the PDF is not a sample with a recording;
   `the model declined` or `request rejected` are permanent.
2. Fix the cause (model outage over, key valid, mode correct), then press **Replay** on the
   Failed jobs page, or `POST /invoices/{id}/replay`. The job is idempotent, so replaying is
   safe. Do not replay in a loop while the cause is still there.

## Invoice stuck in EXTRACTING

A worker crashed mid-job. Tasks are acknowledged late, so Celery normally redelivers and the
job continues from EXTRACTING. If the queue entry itself was lost (Redis data wiped),
put the job back through the outbox:

```sql
INSERT INTO outbox (topic, payload, status, attempts)
VALUES ('invoice.extract', jsonb_build_object('invoice_id', '<invoice id>'), 'PENDING', 0);
```

## A posting that should not have happened

Release 1 has **no reversal**. The posting row and its audit events stay; the audit log is
append-only by design.

1. Pause writes: set `WRITES_ENABLED=false` on the API and redeploy, so nothing else posts.
2. Reconstruct what happened from the audit timeline on the invoice page: extracted values
   and evidence, the reasons, the approval (who, which version, which amount) and the
   posting key.
3. Correct it in the system of record outside InvoiceGuard, and record why.
4. Find the cause before turning writes back on. If a rule or threshold let it through, add
   a case to the evaluation set that reproduces it.

## Abuse or unexpected load on the public demo

- Writes and uploads are limited per reviewer key (`RATE_LIMIT_*` settings).
- `WRITES_ENABLED=false` makes every change return 503 while reads keep working.
- To revoke a key, remove it from `API_KEYS` and redeploy.

## Live extraction costs more than expected

Model calls and their cost are on the Metrics page, per model. Switch the worker back to
`EXTRACTION_MODE=replay`, and keep a spend limit on the API key.
