# Deploying the Release 1 demo

The public demo runs on synthetic data in **replay** mode: every sample invoice has a
recorded (simulated) extraction, so the hosted system never calls the model and costs
nothing per invoice. Uploads of other PDFs fail cleanly into the dead-letter queue, which
is itself part of the demo.

| Part | Where | Notes |
| --- | --- | --- |
| API | Render web service, Ohio (`render.yaml`) | Free plan sleeps when idle, so the first request after a pause is slow |
| Worker + dispatcher | Render background worker, Ohio | No free plan for workers; check current pricing |
| Postgres | Neon, AWS us-east-2 | Pooled URL for the app, direct URL for migrations |
| Redis | Render Key Value, Ohio | Created by the Blueprint, private network only |
| Review UI | Vercel, from `web/` | Static build |

Check each provider's current pricing and free-tier limits before you start.

## 1. Postgres (Neon)

The project is linked with the Neon CLI (`neon init`, `neon deploy`; config in `neon.ts`).
`neon env pull` writes `DATABASE_URL` (pooled, for the app) and `DATABASE_URL_UNPOOLED`
(direct, for migrations) into the gitignored `.env.local`. Copy those two values into
Render; the app adds the psycopg driver name itself and disables prepared statements on
the pooled connection.

## 2. Redis

Nothing to do: the Blueprint creates a free Render Key Value instance in Ohio and injects
its private `REDIS_URL` into the API and the worker. It accepts no connections from the
internet. A per-command-billed Redis (such as Upstash) is a poor fit here, because a Celery
worker polls continuously even when idle.

## 3. API and worker (Render)

1. In Render, create a Blueprint from this repository; it reads `render.yaml` and creates
   the API, the worker and Redis, all in Ohio next to the Neon database.
2. When prompted, fill in:
   - `DATABASE_URL`: Neon's **pooled** URL (host ends in `-pooler`), on both services.
   - `DATABASE_URL_UNPOOLED`: Neon's **direct** URL, on the API only; migrations use it.
   - `API_KEYS`: reviewer keys as `key:name` pairs, for example
     `<a long random string>:demo-reviewer`. Generate the key yourself; never commit it.
   - `CORS_ORIGINS`: the Vercel URL from step 4 (you can set it after step 4).
   - `GROQ_API_KEY`: leave empty for replay mode.
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
- Live extraction instead of replay: set `EXTRACTION_MODE=live` and `GROQ_API_KEY` on the
  worker (provider `groq`, model `openai/gpt-oss-20b` by default), and set a spending
  limit on the Groq account first.
- Runbook for queue backlogs, failed jobs and a bad posting: `docs/runbook.md`.
