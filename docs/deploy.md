# Deploying the Release 1 demo

The public demo runs on synthetic data in **replay** mode: every sample invoice has a
recorded (simulated) extraction, so the hosted system never calls the model and costs
nothing per invoice. Uploads of other PDFs fail cleanly into the dead-letter queue, which
is itself part of the demo.

| Part | Where | Notes |
| --- | --- | --- |
| API + worker + dispatcher | One Render free web service, Ohio (`render.yaml`) | No payment card needed. Sleeps when idle; the first request after a pause is slow, and queued uploads are processed when it wakes |
| Postgres | Neon, AWS us-east-2 | Pooled URL for the app, direct URL for migrations |
| Redis | Upstash, free | Render allows only one free Key Value instance per account, so the queue uses Upstash |
| Review UI | Vercel, from `web/` | Static build |

Check each provider's current pricing and free-tier limits before you start.

## 1. Postgres (Neon)

The project is linked with the Neon CLI (`neon init`, `neon deploy`; config in `neon.ts`).
`neon env pull` writes `DATABASE_URL` (pooled, for the app) and `DATABASE_URL_UNPOOLED`
(direct, for migrations) into the gitignored `.env.local`. Copy those two values into
Render; the app adds the psycopg driver name itself and disables prepared statements on
the pooled connection.

## 2. Redis (Upstash, free)

1. Sign up at upstash.com and create a **Redis** database in a US East region (closest to
   Render's Ohio), with TLS on.
2. Copy its **`rediss://...`** connection URL. This is your `REDIS_URL`.

Render allows only one free Key Value instance per account, which is why the Blueprint
does not create one. Upstash bills per command, and a Celery worker polls Redis while it is
awake; the free service sleeps when idle, so check Upstash's current free quota and watch
its usage. If the quota runs out, jobs wait safely in the Postgres outbox, and you can
switch to a Render Key Value instance (paid) or another Redis.

## 3. API and worker (Render)

1. In Render, create a Blueprint from this repository; it reads `render.yaml` and creates
   one free service in Ohio next to the Neon database: the app (API, worker and
   dispatcher in one container). No payment card is needed.
2. When prompted, fill in:
   - `REDIS_URL`: the `rediss://` URL from step 2.
   - `DATABASE_URL`: Neon's **pooled** URL (host ends in `-pooler`).
   - `DATABASE_URL_UNPOOLED`: Neon's **direct** URL; migrations use it.
   - `API_KEYS`: reviewer keys as `key:name` pairs, for example
     `<a long random string>:demo-reviewer`. Generate the key yourself; never commit it.
   - `ADMIN_USERS`: the reviewer name(s) from `API_KEYS` that may issue agent keys, for
     example `demo-reviewer`. Leave empty to disable key management.
   - `CORS_ORIGINS`: the Vercel URL from step 4 (you can set it after step 4).

   `PUBLIC_URL` is set in `render.yaml` to this service's address. Change it if your Render
   service has a different URL; the MCP endpoint rejects requests addressed to any other host.
   - `GROQ_API_KEY`: `unused` in replay mode (Render may not accept an empty value).
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

- Busier demo: move the worker to its own Render background worker (paid) by splitting the
  `celery` and dispatcher lines out of `deploy/start.sh` and giving the worker service its own
  start command.

- Pause all writes: set `WRITES_ENABLED=false` on the API service.
- Live extraction instead of replay: set `EXTRACTION_MODE=live` and `GROQ_API_KEY` on the
  worker (provider `groq`, model `openai/gpt-oss-20b` by default), and set a spending
  limit on the Groq account first.
- Runbook for queue backlogs, failed jobs and a bad posting: `docs/runbook.md`.
