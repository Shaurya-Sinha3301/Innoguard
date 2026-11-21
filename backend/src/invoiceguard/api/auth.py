"""Who is calling, and what they may do.

Two kinds of key resolve to a Principal:

* Reviewer keys from the API_KEYS environment variable ("key:name" pairs). They are people
  working in the review UI and carry the human scopes. A name listed in ADMIN_USERS also
  gets the admin scope.
* Keys issued through the admin API (prefix "ig_"), stored only as a SHA-256 hash. These
  are the keys given to agents and integrations. An agent can never hold review or admin
  scope, so it cannot approve or reject anything: a person decides, an agent proposes.

The name recorded in the audit log always comes from the key, never from a request body.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from invoiceguard.api.deps import get_session
from invoiceguard.config import settings
from invoiceguard.db import models as m

KEY_PREFIX = "ig_"

# What each scope allows.
#   read     see cases, documents, metrics and packs
#   submit   upload a document or submit structured data
#   propose  record a suggested decision (changes no state)
#   review   approve, reject, edit, replay: the decisions that belong to a person
#   post     post an approved case to the system of record (an agent also needs a grant)
#   admin    manage principals
SCOPES = frozenset({"read", "submit", "propose", "review", "post", "admin"})
HUMAN_SCOPES = frozenset({"read", "submit", "review", "post"})
AGENT_SCOPES = frozenset({"read", "submit", "propose", "post"})
_TOUCH_EVERY = timedelta(minutes=5)


@dataclass(frozen=True)
class Principal:
    name: str
    kind: str  # "human" or "agent"
    scopes: frozenset[str]
    packs: tuple[str, ...] = ("invoices",)

    def can(self, scope: str) -> bool:
        return scope in self.scopes


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_key() -> str:
    """A fresh key. Shown once at creation; only its hash is kept."""
    return KEY_PREFIX + secrets.token_urlsafe(32)


def parse_api_keys(raw: str) -> dict[str, str]:
    users: dict[str, str] = {}
    for pair in raw.split(","):
        key, sep, name = pair.strip().partition(":")
        if sep and key and name:
            users[key] = name
    return users


def _admin_names() -> set[str]:
    return {n.strip() for n in settings.admin_users.split(",") if n.strip()}


def _from_environment(key: str) -> Principal | None:
    for known, name in parse_api_keys(settings.api_keys).items():
        if secrets.compare_digest(known, key):
            scopes = HUMAN_SCOPES | ({"admin"} if name in _admin_names() else set())
            return Principal(name=name, kind="human", scopes=frozenset(scopes))
    return None


def _from_database(session: Session, key: str) -> Principal | None:
    if not key.startswith(KEY_PREFIX):
        return None
    row = session.scalar(select(m.Principal).where(m.Principal.key_hash == hash_key(key)))
    if row is None or row.disabled:
        return None
    now = datetime.now(UTC)
    if row.last_used_at is None or now - row.last_used_at > _TOUCH_EVERY:
        session.execute(
            update(m.Principal).where(m.Principal.id == row.id).values(last_used_at=now)
        )
    return Principal(
        name=row.name, kind=row.kind, scopes=frozenset(row.scopes), packs=tuple(row.packs)
    )


def presented_key(x_api_key: str | None, authorization: str | None) -> str | None:
    """The key from X-API-Key, or from 'Authorization: Bearer' (what MCP clients send)."""
    if x_api_key:
        return x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def authenticate(session: Session, key: str | None) -> Principal | None:
    if not key:
        return None
    return _from_environment(key) or _from_database(session, key)


def current_principal(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Principal:
    principal = authenticate(session, presented_key(x_api_key, authorization))
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid or missing API key")
    return principal


def current_user(principal: Principal = Depends(current_principal)) -> str:
    """The name actions are recorded under."""
    return principal.name


def require_scope(scope: str):
    """Dependency that refuses the request unless the caller holds the scope."""

    def check(principal: Principal = Depends(current_principal)) -> Principal:
        if not principal.can(scope):
            raise HTTPException(status_code=403, detail=f"this key does not have the {scope} scope")
        return principal

    return check
