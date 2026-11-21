"""Accounts: sign up, log in, and generate API keys for yourself.

A person logs in once with an email and password and gets a session. From there they can
explore the review desk. When an agent or integration needs to act for them, they generate an
API key here: it belongs to them, can do no more than they can, never includes the decisions
that belong to a person (review, admin), and stops working if their account is disabled.
"""

import re
import time
import uuid
from datetime import UTC, datetime, timedelta

import redis
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoiceguard.api import ratelimit
from invoiceguard.api.auth import (
    _DUMMY_HASH,
    AGENT_SCOPES,
    SCOPES,
    Principal,
    current_principal,
    hash_key,
    hash_password,
    key_scopes_for,
    new_key,
    new_session_token,
    presented_key,
    require_scope,
    verify_password,
)
from invoiceguard.api.deps import get_session
from invoiceguard.api.ratelimit import WRITE_GUARDS
from invoiceguard.config import settings
from invoiceguard.db import models as m
from invoiceguard.packs.registry import list_packs
from invoiceguard.workflow import audit

router = APIRouter(tags=["accounts"])

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_KEYS_PER_USER = 20


# ---------------------------------------------------------------- shapes


class SignupIn(BaseModel):
    email: str = Field(max_length=200)
    name: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9._ -]*$")
    password: str = Field(min_length=10, max_length=200)


class LoginIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    scopes: list[str]
    packs: list[str]
    is_admin: bool
    disabled: bool
    last_login_at: datetime | None


class SessionOut(BaseModel):
    token: str
    expires_at: datetime
    user: UserOut


class KeyIn(BaseModel):
    label: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9._ -]*$")
    scopes: list[str]
    packs: list[str] | None = None


class KeyOut(BaseModel):
    id: uuid.UUID
    name: str
    scopes: list[str]
    packs: list[str]
    key_prefix: str
    disabled: bool
    last_used_at: datetime | None


class KeyCreated(KeyOut):
    key: str  # shown once


def _user_out(user: m.User) -> dict[str, object]:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "scopes": sorted(user.scopes),
        "packs": user.packs,
        "is_admin": user.is_admin,
        "disabled": user.disabled,
        "last_login_at": user.last_login_at,
    }


def _key_out(row: m.Principal) -> dict[str, object]:
    return {
        "id": row.id,
        "name": row.name,
        "scopes": sorted(row.scopes),
        "packs": row.packs,
        "key_prefix": row.key_prefix,
        "disabled": row.disabled,
        "last_used_at": row.last_used_at,
    }


# ---------------------------------------------------------------- throttling


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return (forwarded.split(",")[0].strip() if forwarded else None) or (
        request.client.host if request.client else "unknown"
    )


def _throttle(request: Request, email: str) -> None:
    """Slow down password guessing: a few attempts a minute per address and per email."""
    allowed = settings.rate_limit_auth_per_minute
    if allowed <= 0:
        return
    window = int(time.time() // 60)
    for scope in (f"ip:{_client_ip(request)}", f"email:{email.lower()}"):
        try:
            count = ratelimit.counter.incr(f"ratelimit:auth:{scope}:{window}", 70)
        except redis.RedisError:
            continue  # limits fail open, as everywhere else
        if count > allowed:
            raise HTTPException(429, "too many attempts; try again in a minute")


# ---------------------------------------------------------------- sessions


def _start_session(session: Session, user: m.User) -> tuple[str, datetime]:
    token = new_session_token()
    expires = datetime.now(UTC) + timedelta(days=settings.session_days)
    session.add(m.UserSession(user_id=user.id, token_hash=hash_key(token), expires_at=expires))
    user.last_login_at = datetime.now(UTC)
    return token, expires


def _is_first_admin(session: Session, email: str) -> bool:
    designated = {e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}
    if designated:
        return email in designated
    return session.scalar(select(func.count()).select_from(m.User)) == 0


@router.post("/auth/signup", response_model=SessionOut, status_code=201)
def signup(
    body: SignupIn, request: Request, session: Session = Depends(get_session)
) -> dict[str, object]:
    if not settings.signup_enabled:
        raise HTTPException(403, "sign-up is closed on this deployment")
    email = body.email.strip().lower()
    if not _EMAIL.match(email):
        raise HTTPException(422, "enter a valid email address")
    _throttle(request, email)

    scopes = sorted(
        {s.strip() for s in settings.signup_scopes.split(",") if s.strip()} & SCOPES - {"admin"}
    )
    is_admin = _is_first_admin(session, email)
    user = m.User(
        email=email,
        name=body.name.strip(),
        name_key=body.name.strip().lower(),
        password_hash=hash_password(body.password),
        scopes=scopes,
        packs=[p.id for p in list_packs()],
        is_admin=is_admin,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "that email or name is already taken") from exc
    token, expires = _start_session(session, user)
    audit.record(
        session,
        event_type="account.created",
        actor=user.name,
        payload={"email": email, "admin": is_admin},
    )
    return {"token": token, "expires_at": expires, "user": _user_out(user)}


@router.post("/auth/login", response_model=SessionOut)
def login(
    body: LoginIn, request: Request, session: Session = Depends(get_session)
) -> dict[str, object]:
    email = body.email.strip().lower()
    _throttle(request, email)
    user = session.scalar(select(m.User).where(m.User.email == email))
    # Always do the same work, so timing does not reveal whether the email exists.
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not ok or user.disabled:
        raise HTTPException(401, "wrong email or password")
    token, expires = _start_session(session, user)
    return {"token": token, "expires_at": expires, "user": _user_out(user)}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, session: Session = Depends(get_session)) -> None:
    """End the session this token belongs to. Safe to call with anything."""
    token = presented_key(request.headers.get("x-api-key"), request.headers.get("authorization"))
    if token:
        row = session.scalar(
            select(m.UserSession).where(m.UserSession.token_hash == hash_key(token))
        )
        if row is not None:
            row.revoked = True


# ---------------------------------------------------------------- my API keys


def _account(who: Principal) -> uuid.UUID:
    if who.user_id is None:
        raise HTTPException(403, "sign in with an account to manage your own API keys")
    return who.user_id


@router.get("/me/keys", response_model=list[KeyOut])
def my_keys(
    session: Session = Depends(get_session), who: Principal = Depends(current_principal)
) -> list[dict[str, object]]:
    owner = _account(who)
    rows = session.scalars(
        select(m.Principal).where(m.Principal.owner_id == owner).order_by(m.Principal.created_at)
    )
    return [_key_out(r) for r in rows]


@router.post("/me/keys", response_model=KeyCreated, status_code=201, dependencies=WRITE_GUARDS)
def create_my_key(
    body: KeyIn,
    session: Session = Depends(get_session),
    who: Principal = Depends(require_scope("read")),
) -> dict[str, object]:
    owner = _account(who)
    unknown = set(body.scopes) - SCOPES
    if unknown:
        raise HTTPException(422, f"unknown scopes: {sorted(unknown)}")
    # An agent proposes; a person decides. And a key never exceeds the person who made it.
    forbidden = set(body.scopes) - AGENT_SCOPES
    if forbidden:
        raise HTTPException(422, f"an API key cannot hold: {sorted(forbidden)}")
    beyond = set(body.scopes) - key_scopes_for(who.scopes)
    if beyond:
        raise HTTPException(422, f"your account cannot grant: {sorted(beyond)}")
    if not body.scopes:
        raise HTTPException(422, "give the key at least one scope")
    packs = body.packs or list(who.packs)
    if set(packs) - set(who.packs):
        raise HTTPException(422, "your account cannot grant access to those workflows")
    count = session.scalar(
        select(func.count()).select_from(m.Principal).where(m.Principal.owner_id == owner)
    )
    if count >= MAX_KEYS_PER_USER:
        raise HTTPException(409, f"you already have {MAX_KEYS_PER_USER} keys; disable some first")

    key = new_key()
    row = m.Principal(
        name=f"{who.name} / {body.label.strip()}",
        kind="agent",
        scopes=sorted(set(body.scopes)),
        packs=packs,
        key_hash=hash_key(key),
        key_prefix=key[:8],
        created_by=who.name,
        owner_id=owner,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "you already have a key with that label") from exc
    audit.record(
        session,
        event_type="principal.created",
        actor=who.name,
        payload={"name": row.name, "kind": "agent", "scopes": row.scopes, "self_service": True},
    )
    return {**_key_out(row), "key": key}


@router.post("/me/keys/{key_id}/disable", response_model=KeyOut, dependencies=WRITE_GUARDS)
def disable_my_key(
    key_id: uuid.UUID,
    session: Session = Depends(get_session),
    who: Principal = Depends(current_principal),
) -> dict[str, object]:
    owner = _account(who)
    row = session.get(m.Principal, key_id)
    if row is None or row.owner_id != owner:
        raise HTTPException(404, "key not found")
    row.disabled = True
    audit.record(
        session, event_type="principal.disabled", actor=who.name, payload={"name": row.name}
    )
    return _key_out(row)


# ---------------------------------------------------------------- administering people

ADMIN = Depends(require_scope("admin"))


@router.get("/users", response_model=list[UserOut], dependencies=[ADMIN])
def list_users(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    return [_user_out(u) for u in session.scalars(select(m.User).order_by(m.User.created_at))]


def _set_disabled(
    session: Session, user_id: uuid.UUID, admin: Principal, disabled: bool
) -> dict[str, object]:
    user = session.get(m.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    if user.id == admin.user_id and disabled:
        raise HTTPException(409, "you cannot disable your own account")
    user.disabled = disabled
    audit.record(
        session,
        event_type="account.disabled" if disabled else "account.enabled",
        actor=admin.name,
        payload={"email": user.email},
    )
    return _user_out(user)


@router.post("/users/{user_id}/disable", response_model=UserOut, dependencies=WRITE_GUARDS)
def disable_user(
    user_id: uuid.UUID,
    session: Session = Depends(get_session),
    admin: Principal = ADMIN,
) -> dict[str, object]:
    return _set_disabled(session, user_id, admin, True)


@router.post("/users/{user_id}/enable", response_model=UserOut, dependencies=WRITE_GUARDS)
def enable_user(
    user_id: uuid.UUID,
    session: Session = Depends(get_session),
    admin: Principal = ADMIN,
) -> dict[str, object]:
    return _set_disabled(session, user_id, admin, False)
