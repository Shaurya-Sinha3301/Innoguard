"""What agents and the people supervising them do around a case: suggestions and grants."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from invoiceguard.api.auth import Principal, require_scope
from invoiceguard.api.deps import get_session
from invoiceguard.api.ratelimit import WRITE_GUARDS
from invoiceguard.workflow import grants, suggestions
from invoiceguard.workflow.errors import IllegalTransition, InvoiceNotFound, NotApproved

router = APIRouter(prefix="/invoices/{case_id}", tags=["agents"])
READ = Depends(require_scope("read"))


class SuggestionIn(BaseModel):
    decision: str
    rationale: str


class SuggestionOut(BaseModel):
    id: int
    case_version: int
    decision: str
    rationale: str
    proposed_by: str
    status: str
    resolved_by: str | None
    created_at: datetime


class GrantIn(BaseModel):
    ttl_minutes: int = Field(default=grants.DEFAULT_TTL_MINUTES)


class GrantOut(BaseModel):
    id: uuid.UUID
    case_version: int
    amount: str
    issued_by: str
    expires_at: datetime
    used_at: datetime | None
    used_by: str | None


def _grant_out(g) -> GrantOut:
    return GrantOut(
        id=g.id,
        case_version=g.case_version,
        amount=str(g.amount),
        issued_by=g.issued_by,
        expires_at=g.expires_at,
        used_at=g.used_at,
        used_by=g.used_by,
    )


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvoiceNotFound):
        return HTTPException(404, "not found")
    if isinstance(exc, (IllegalTransition, NotApproved)):
        return HTTPException(409, str(exc))
    return HTTPException(422, str(exc))


@router.get("/suggestions", response_model=list[SuggestionOut], dependencies=[READ])
def list_suggestions(case_id: uuid.UUID, session: Session = Depends(get_session)):
    return suggestions.for_case(session, case_id)


@router.post(
    "/suggestions",
    response_model=SuggestionOut,
    status_code=201,
    dependencies=[Depends(require_scope("propose")), *WRITE_GUARDS],
)
def propose(
    case_id: uuid.UUID,
    body: SuggestionIn,
    session: Session = Depends(get_session),
    who: Principal = Depends(require_scope("propose")),
):
    try:
        return suggestions.propose(
            session, case_id, actor=who.name, decision=body.decision, rationale=body.rationale
        )
    except (InvoiceNotFound, IllegalTransition, ValueError) as exc:
        raise _error(exc) from exc


@router.post(
    "/suggestions/{suggestion_id}/dismiss",
    response_model=SuggestionOut,
    dependencies=[*WRITE_GUARDS],
)
def dismiss(
    case_id: uuid.UUID,
    suggestion_id: int,
    session: Session = Depends(get_session),
    who: Principal = Depends(require_scope("review")),
):
    try:
        return suggestions.dismiss(session, case_id, suggestion_id, actor=who.name)
    except InvoiceNotFound as exc:
        raise _error(exc) from exc


@router.get("/grants", response_model=list[GrantOut], dependencies=[READ])
def list_grants(case_id: uuid.UUID, session: Session = Depends(get_session)):
    return [_grant_out(g) for g in grants.grants_for_case(session, case_id)]


@router.post("/grants", response_model=GrantOut, status_code=201, dependencies=[*WRITE_GUARDS])
def issue_grant(
    case_id: uuid.UUID,
    body: GrantIn,
    session: Session = Depends(get_session),
    who: Principal = Depends(require_scope("review")),
):
    """A person releases one approved case for an agent to post. Agents cannot call this."""
    try:
        grant = grants.issue_grant(
            session, case_id, issued_by=who.name, ttl_minutes=body.ttl_minutes
        )
    except (InvoiceNotFound, NotApproved, ValueError) as exc:
        raise _error(exc) from exc
    return _grant_out(grant)
