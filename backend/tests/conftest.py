"""Shared fixtures. Integration tests run against a throwaway Postgres database that is
created from the real Alembic migrations, so the schema under test is the deployed one."""

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from invoiceguard.config import settings

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
    eng = sa.create_engine(test_database_url)
    yield eng
    eng.dispose()
