from invoiceguard.config import Settings, uses_pooler
from invoiceguard.db.session import engine_options

POOLED = "postgresql://u:p@ep-x-pooler.c-9.us-east-2.aws.neon.tech/db?sslmode=require"
DIRECT = "postgresql://u:p@ep-x.c-9.us-east-2.aws.neon.tech/db?sslmode=require"


def test_migrations_use_the_direct_url_when_given():
    s = Settings(database_url=POOLED, database_url_unpooled=DIRECT)
    assert s.database_url.startswith("postgresql+psycopg://") and "-pooler" in s.database_url
    assert s.migration_database_url.startswith("postgresql+psycopg://")
    assert "-pooler" not in s.migration_database_url


def test_migrations_fall_back_to_the_app_url_locally():
    s = Settings(
        database_url="postgresql+psycopg://u:p@localhost:5433/db", database_url_unpooled=None
    )
    assert s.migration_database_url == s.database_url


def test_pooled_connections_disable_prepared_statements():
    assert uses_pooler(Settings(database_url=POOLED).database_url)
    assert engine_options(Settings(database_url=POOLED).database_url)["connect_args"] == {
        "prepare_threshold": None
    }
    direct = engine_options(Settings(database_url=DIRECT).database_url)
    assert "connect_args" not in direct and direct["pool_pre_ping"] is True
