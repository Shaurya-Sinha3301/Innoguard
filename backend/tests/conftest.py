"""Shared fixtures. Integration tests run against a throwaway Postgres database that is
created from the real Alembic migrations, so the schema under test is the deployed one."""

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from invoiceguard.config import settings
from invoiceguard.db.models import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_NAME = "invoiceguard_test"


def _admin_engine():
    admin_url = make_url(settings.database_url).set(database="postgres")
    return sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")


@pytest.fixture(scope="session")
def test_database_url() -> str:
    admin = _admin_engine()
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)"))
        conn.execute(sa.text(f"CREATE DATABASE {TEST_DB_NAME}"))

    url = make_url(settings.database_url).set(database=TEST_DB_NAME)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
    command.upgrade(config, "head")

    yield url.render_as_string(hide_password=False)

    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture(scope="session")
def engine(test_database_url):
    eng = sa.create_engine(test_database_url, pool_size=10)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def clean_db(engine):
    """Empty every table before a test. Audit events are append-only, so the trigger is
    switched off for this test-only wipe and switched back on straight after."""
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(sa.text("ALTER TABLE audit_events DISABLE TRIGGER USER"))
        conn.execute(sa.text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        conn.execute(sa.text("ALTER TABLE audit_events ENABLE TRIGGER USER"))
    yield
