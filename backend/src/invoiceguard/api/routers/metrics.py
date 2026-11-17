from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from invoiceguard import reporting
from invoiceguard.api.auth import current_user
from invoiceguard.api.deps import get_session

router = APIRouter(tags=["metrics"])


@router.get("/metrics/summary")
def metrics_summary(
    session: Session = Depends(get_session),
    _user: str = Depends(current_user),
) -> dict[str, Any]:
    return reporting.summary(session)
