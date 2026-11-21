"""Cases across every pack. `/invoices` is the same data restricted to the invoices pack."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from invoiceguard.api import schemas
from invoiceguard.api.auth import Principal, require_scope
from invoiceguard.api.deps import get_session
from invoiceguard.api.routers.invoices import case_detail, list_cases_in
from invoiceguard.packs.registry import get_pack

router = APIRouter(prefix="/cases", tags=["cases"])


def _allowed(who: Principal, pack: str | None) -> None:
    if pack is not None and (get_pack(pack) is None or pack not in who.packs):
        raise HTTPException(404, "unknown pack, or this key cannot use it")


@router.get("", response_model=list[schemas.InvoiceRow])
def list_cases(
    pack: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
    who: Principal = Depends(require_scope("read")),
) -> list[dict]:
    _allowed(who, pack)
    rows = list_cases_in(session, status=status, limit=limit, pack=pack)
    return [r for r in rows if r["pack_id"] in who.packs]


@router.get("/{case_id}", response_model=schemas.InvoiceDetail)
def get_case(
    case_id: uuid.UUID,
    session: Session = Depends(get_session),
    who: Principal = Depends(require_scope("read")),
) -> dict:
    detail = case_detail(session, case_id)
    _allowed(who, detail["pack_id"])
    return detail
