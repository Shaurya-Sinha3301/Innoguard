import pytest

from invoiceguard.config import Settings


@pytest.mark.parametrize(
    "given",
    [
        "rediss://default:s3cret@fit-owl-1234.upstash.io:6379",
        '"rediss://default:s3cret@host:6379"',
        "REDIS_URL=rediss://default:s3cret@host:6379",
        "  redis://redis:6379/0  ",
    ],
)
def test_redis_url_accepts_the_usual_pasted_variants(given):
    url = Settings(redis_url=given).redis_url
    assert url.startswith(("redis://", "rediss://")) and url == url.strip() and '"' not in url


@pytest.mark.parametrize(
    "given",
    [
        "https://fit-owl-1234.upstash.io",
        "redis-cli --tls -u redis://default:s3cret@host:6379",
        "default:s3cret@host:6379",
    ],
)
def test_redis_url_rejects_wrong_formats_without_leaking_the_password(given):
    with pytest.raises(ValueError) as caught:
        Settings(redis_url=given)
    message = str(caught.value)
    assert "must start with redis:// or rediss://" in message
    assert "s3cret" not in message


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
