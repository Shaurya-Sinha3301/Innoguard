import redis
from sqlalchemy import text

from invoiceguard.config import settings
from invoiceguard.db.session import engine


def check_postgres() -> str:
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        return "ok"
    except Exception as exc:  # report the failure type, never connection details
        return f"error: {type(exc).__name__}"


def check_redis() -> str:
    try:
        redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2).ping()
        return "ok"
    except Exception as exc:
        return f"error: {type(exc).__name__}"


def run_checks() -> dict[str, str]:
    return {"postgres": check_postgres(), "redis": check_redis()}
