# InvoiceGuard

An approval-gated agent that reconciles supplier invoices against purchase orders and goods receipts (three-way matching), applies deterministic controls, sends doubtful cases to a human reviewer, and records an audit trail that can reconstruct every decision.

**Status:** work in progress. Release 1 is a single deployed workflow on clean PDFs. All demo data is synthetic, and no figures are published until a reproducible run produces them.

## Run locally

Requires Docker with Compose.

```bash
docker compose up --build
```

Then check the stack:

```bash
curl http://localhost:8000/health
docker compose exec api python -m invoiceguard.jobs.ping
```

The first command reports Postgres and Redis status. The second sends a task through Redis to the worker and prints `pong`.

## Tests

```bash
cd backend
pip install -e ".[dev]"
ruff check .
pytest
```

## Layout

- `backend/` FastAPI app, Celery jobs, Alembic migrations, tests
- `deploy/` Dockerfile and hosting configuration
- `docker-compose.yml` local stack: Postgres, Redis, API, worker
