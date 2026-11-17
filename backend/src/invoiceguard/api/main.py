from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from invoiceguard.api import health
from invoiceguard.api.routers import documents, invoices, metrics
from invoiceguard.config import settings

app = FastAPI(title="InvoiceGuard")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)
app.include_router(invoices.router)
app.include_router(documents.router)
app.include_router(metrics.router)


@app.get("/health")
def get_health() -> JSONResponse:
    checks = health.run_checks()
    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        status_code=200 if healthy else 503,
    )
