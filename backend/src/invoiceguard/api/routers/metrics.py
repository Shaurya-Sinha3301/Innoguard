from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from invoiceguard import reporting
from invoiceguard.api.auth import current_user, require_scope
from invoiceguard.api.deps import get_session

router = APIRouter(tags=["metrics"], dependencies=[Depends(require_scope("read"))])


@router.get("/metrics/summary")
def metrics_summary(
    pack: str | None = None,
    session: Session = Depends(get_session),
    _user: str = Depends(current_user),
) -> dict[str, Any]:
    return reporting.summary(session, pack)
