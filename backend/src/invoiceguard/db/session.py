from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from invoiceguard.config import settings, uses_pooler


def engine_options(url: str) -> dict[str, Any]:
    """Behind a transaction-mode pooler (Neon's -pooler endpoint), turn off psycopg's
    automatic server-side prepared statements, which assume one session per connection.
    pool_pre_ping replaces connections a scaled-to-zero compute has closed."""
    options: dict[str, Any] = {"pool_pre_ping": True}
    if uses_pooler(url):
        options["connect_args"] = {"prepare_threshold": None}
    return options


engine = create_engine(settings.database_url, **engine_options(settings.database_url))
SessionLocal = sessionmaker(engine, expire_on_commit=False)
