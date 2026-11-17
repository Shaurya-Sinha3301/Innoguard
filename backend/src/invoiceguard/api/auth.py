"""Simple API-key authentication that maps a key to a named reviewer.

Release 1 limitation: keys are static and configured by environment variable. There is
no user management, expiry or SSO. The reviewer name recorded in the audit log comes from
the key, never from the request body.
"""

import secrets

from fastapi import Header, HTTPException

from invoiceguard.config import settings


def parse_api_keys(raw: str) -> dict[str, str]:
    users: dict[str, str] = {}
    for pair in raw.split(","):
        key, sep, name = pair.strip().partition(":")
        if sep and key and name:
            users[key] = name
    return users


def current_user(x_api_key: str | None = Header(default=None)) -> str:
    if x_api_key:
        for key, name in parse_api_keys(settings.api_keys).items():
            if secrets.compare_digest(key, x_api_key):
                return name
    raise HTTPException(status_code=401, detail="invalid or missing API key")
