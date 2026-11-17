# Deploying the Release 1 demo

The public demo runs on synthetic data in **replay** mode: every sample invoice has a
recorded (simulated) extraction, so the hosted system never calls the model and costs
nothing per invoice. Uploads of other PDFs fail cleanly into the dead-letter queue, which
is itself part of the demo.

| Part | Where | Notes |
| --- | --- | --- |
| API | Render web service (`render.yaml`) | Free plan sleeps when idle, so the first request after a pause is slow |
| Worker + dispatcher | Render background worker | No free plan for workers; check current pricing |
| Postgres | Neon | Paste the connection string as given; the app adds the driver name |
| Redis | Upstash, or Render Key Value | See the Redis note below |
| Review UI | Vercel, from `web/` | Static build |

Check each provider's current pricing and free-tier limits before you start.

## 1. Postgres (Neon)

Create a project and copy its connection string (it ends in `?sslmode=require`). That is
the `DATABASE_URL` for both Render services.

## 2. Redis

Create a Redis database and copy its `rediss://` URL as `REDIS_URL`.

**Note:** a Celery worker polls Redis continuously even when idle. On a free tier with a
monthly command quota (Upstash bills per command) that can use the quota up. If it does,
use a Redis that is not billed per command, such as Render Key Value in the same region.

## 3. API and worker (Render)

1. In Render, create a Blueprint from this repository; it reads `render.yaml`.
2. When prompted, fill in:
   - `DATABASE_URL`, `REDIS_URL`: from steps 1 and 2.
   - `API_KEYS`: reviewer keys as `key:name` pairs, for example
     `<a long random string>:demo-reviewer`. Generate the key yourself; never commit it.
   - `CORS_ORIGINS`: the Vercel URL from step 4 (you can set it after step 4).
   - `ANTHROPIC_API_KEY`: leave empty for replay mode.
3. Deploy. The API runs `alembic upgrade head` on start-up.
4. Check `https://<api>.onrender.com/health` returns `"status": "ok"`.

## 4. Review UI (Vercel)

1. Import the repository in Vercel with **root directory `web`** (framework: Vite).
2. Set `VITE_API_URL` to the Render API URL.
3. Optionally set `VITE_DEMO_HINT` to a line shown on the sign-in screen, for example how
   to get a demo key. If you publish a demo key there, anyone can approve and post the
   synthetic invoices; the rate limits and the `WRITES_ENABLED` switch exist for that.
4. Deploy, then put the Vercel URL into the API's `CORS_ORIGINS` and redeploy the API.

## 5. Load the demo invoices

Run the loader once against the hosted database, from your machine:

```bash
docker compose run --rm -e DATABASE_URL="<neon url>" api python -m invoiceguard.generator.demo_data --count 24 --submit
```

The hosted worker then processes them through the normal outbox and queue path.

## Operating the demo

- Pause all writes: set `WRITES_ENABLED=false` on the API service.
- Live extraction instead of replay: set `EXTRACTION_MODE=anthropic` and
  `ANTHROPIC_API_KEY` on the worker, and put a spend limit on that API key first.
- Runbook for queue backlogs, failed jobs and a bad posting: `docs/runbook.md`.
