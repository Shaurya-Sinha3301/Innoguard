from fastapi import FastAPI
from fastapi.responses import JSONResponse

from invoiceguard.api import health
from invoiceguard.api.routers import invoices

app = FastAPI(title="InvoiceGuard")
app.include_router(invoices.router)


@app.get("/health")
def get_health() -> JSONResponse:
    checks = health.run_checks()
    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        status_code=200 if healthy else 503,
    )
