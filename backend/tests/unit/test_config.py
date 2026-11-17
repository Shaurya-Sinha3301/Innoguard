import pytest

from invoiceguard.config import Settings


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            "postgres://u:p@ep-x.neon.tech/db?sslmode=require",
            "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require",
        ),
        ("postgresql://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ],
)
def test_hosted_database_urls_get_the_psycopg_driver(given, expected):
    assert Settings(database_url=given).database_url == expected
