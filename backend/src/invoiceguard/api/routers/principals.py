"""Manage the people and agents that may call the API. Admin scope only.

A key is returned once, when the principal is created. Only its hash is stored, so a lost
key cannot be recovered: disable the principal and create a new one.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoiceguard.api.auth import (
    AGENT_SCOPES,
    HUMAN_SCOPES,
    SCOPES,
    Principal,
    hash_key,
    new_key,
    require_scope,
)
from invoiceguard.api.deps import get_session
from invoiceguard.api.ratelimit import WRITE_GUARDS
from invoiceguard.db import models as m
from invoiceguard.packs.registry import get_pack, list_packs
from invoiceguard.workflow import audit

router = APIRouter(prefix="/principals", tags=["principals"])
ADMIN = Depends(require_scope("admin"))


class PrincipalIn(BaseModel):
    name: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._ -]*$")
    kind: str = Field(pattern="^(human|agent)$")
    scopes: list[str]
    packs: list[str] | None = None  # default: every installed pack


class PrincipalOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    scopes: list[str]
    packs: list[str]
    key_prefix: str
    disabled: bool
    created_by: str
    last_used_at: str | None


class CreatedOut(PrincipalOut):
    key: str  # shown once


def _out(row: m.Principal) -> dict[str, object]:
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "scopes": sorted(row.scopes),
        "packs": row.packs,
        "key_prefix": row.key_prefix,
        "disabled": row.disabled,
        "created_by": row.created_by,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
    }


@router.get("", response_model=list[PrincipalOut], dependencies=[ADMIN])
def list_principals(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    rows = session.scalars(select(m.Principal).order_by(m.Principal.created_at))
    return [_out(r) for r in rows]


@router.post("", response_model=CreatedOut, status_code=201, dependencies=WRITE_GUARDS)
def create_principal(
    body: PrincipalIn,
    session: Session = Depends(get_session),
    admin: Principal = ADMIN,
) -> dict[str, object]:
    unknown = set(body.scopes) - SCOPES
    if unknown:
        raise HTTPException(422, f"unknown scopes: {sorted(unknown)}")
    # An agent proposes; a person decides. Agent keys can never approve, reject or administer.
    allowed = AGENT_SCOPES if body.kind == "agent" else HUMAN_SCOPES | {"admin"}
    forbidden = set(body.scopes) - allowed
    if forbidden:
        raise HTTPException(422, f"a {body.kind} key cannot hold: {sorted(forbidden)}")
    if not body.scopes:
        raise HTTPException(422, "give the key at least one scope")
    packs = body.packs or [p.id for p in list_packs()]
    missing = [p for p in packs if get_pack(p) is None]
    if missing:
        raise HTTPException(422, f"unknown packs: {missing}")

    key = new_key()
    row = m.Principal(
        name=body.name.strip(),
        kind=body.kind,
        scopes=sorted(set(body.scopes)),
        packs=packs,
        key_hash=hash_key(key),
        key_prefix=key[:8],
        created_by=admin.name,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "a principal with that name already exists") from exc
    audit.record(
        session,
        event_type="principal.created",
        actor=admin.name,
        payload={"name": row.name, "kind": row.kind, "scopes": row.scopes, "packs": row.packs},
    )
    return {**_out(row), "key": key}


@router.post("/{principal_id}/disable", response_model=PrincipalOut, dependencies=WRITE_GUARDS)
def disable_principal(
    principal_id: uuid.UUID,
    session: Session = Depends(get_session),
    admin: Principal = ADMIN,
) -> dict[str, object]:
    row = session.get(m.Principal, principal_id)
    if row is None:
        raise HTTPException(404, "principal not found")
    row.disabled = True
    audit.record(
        session, event_type="principal.disabled", actor=admin.name, payload={"name": row.name}
    )
    return _out(row)
