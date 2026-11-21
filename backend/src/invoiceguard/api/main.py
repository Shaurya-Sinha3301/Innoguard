from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from invoiceguard.api import health
from invoiceguard.api.auth import Principal, current_principal
from invoiceguard.api.routers import (
    accounts,
    agent,
    cases,
    documents,
    invoices,
    metrics,
    packs,
    principals,
)
from invoiceguard.config import settings
from invoiceguard.mcp_server import server as mcp_module

mcp_app = mcp_module.http_app()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # The MCP transport needs its session manager running for as long as the API is.
    async with mcp_module.mcp.session_manager.run():
        yield


app = FastAPI(title="InvoiceGuard", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-API-Key", "Authorization", "Content-Type"],
)
app.include_router(accounts.router)
app.include_router(invoices.router)
app.include_router(cases.router)
app.include_router(agent.router)
app.include_router(documents.router)
app.include_router(metrics.router)
app.include_router(packs.router)
app.include_router(principals.router)


@app.get("/me")
def who_am_i(principal: Principal = Depends(current_principal)) -> dict[str, object]:
    """Who the current key signs actions as, and what it may do."""
    return {
        "name": principal.name,
        "kind": principal.kind,
        "scopes": sorted(principal.scopes),
        "packs": list(principal.packs),
        "email": principal.email,
        "account": principal.user_id is not None,
    }


@app.get("/health")
def get_health() -> JSONResponse:
    checks = health.run_checks()
    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        status_code=200 if healthy else 503,
    )


# Last, so every API route above wins; the MCP app answers /mcp and its discovery metadata.
app.mount("/", mcp_app)
