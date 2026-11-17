"""Fixed-window rate limits per reviewer, counted in Redis, plus a write kill switch.

Limits fail open if Redis is unreachable: the demo stays usable, and the outage shows up
in the health check instead.
"""

import logging
import time
from collections.abc import Callable
from typing import Protocol

import redis
from fastapi import Depends, HTTPException

from invoiceguard.api.auth import current_user
from invoiceguard.config import settings

log = logging.getLogger("invoiceguard.ratelimit")


class Counter(Protocol):
    def incr(self, key: str, ttl_seconds: int) -> int: ...


class RedisCounter:
    def __init__(self) -> None:
        self._client: redis.Redis | None = None

    def incr(self, key: str, ttl_seconds: int) -> int:
        if self._client is None:
            self._client = redis.Redis.from_url(
                settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5
            )
        pipe = self._client.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl_seconds)
        return int(pipe.execute()[0])


counter: Counter = RedisCounter()


def writes_allowed() -> None:
    if not settings.writes_enabled:
        raise HTTPException(503, "changes are paused on this deployment")


def limit(bucket: str, per_minute: Callable[[], int]) -> Callable[..., None]:
    def dependency(user: str = Depends(current_user)) -> None:
        allowed = per_minute()
        if allowed <= 0:
            return
        window = int(time.time() // 60)
        try:
            count = counter.incr(f"ratelimit:{bucket}:{user}:{window}", 70)
        except redis.RedisError:
            log.warning("rate limiter unavailable; allowing request")
            return
        if count > allowed:
            raise HTTPException(429, "too many requests; try again in a minute")

    return dependency


write_limit = limit("write", lambda: settings.rate_limit_writes_per_minute)
upload_limit = limit("upload", lambda: settings.rate_limit_uploads_per_minute)
WRITE_GUARDS = [Depends(writes_allowed), Depends(write_limit)]
UPLOAD_GUARDS = [Depends(writes_allowed), Depends(upload_limit)]
