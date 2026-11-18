from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application traffic. On Neon this is the pooled URL (host ends in -pooler).
    database_url: str = "postgresql+psycopg://invoiceguard:invoiceguard@localhost:5433/invoiceguard"
    # Migrations need a direct connection; on Neon this is DATABASE_URL_UNPOOLED.
    # Falls back to database_url when unset (local Postgres has no pooler).
    database_url_unpooled: str | None = None
    redis_url: str = "redis://localhost:6380/0"
    # Reviewer identities as "key:name" pairs, comma separated. Empty means nobody can sign in.
    api_keys: str = ""
    # Extraction provider and model. "groq" uses GROQ_API_KEY; "anthropic" uses
    # ANTHROPIC_API_KEY (set EXTRACTION_MODEL to a Claude model then, e.g. claude-haiku-5-5).
    extraction_provider: str = "groq"
    extraction_model: str = "openai/gpt-oss-20b"
    # "live" calls the provider and records every response; "replay" never calls it.
    extraction_mode: str = "live"
    extraction_cache_dir: str = "/app/extraction-cache"
    extraction_max_attempts: int = 4
    # Comma-separated browser origins allowed to call the API (the review UI).
    cors_origins: str = "http://localhost:5173"
    # Public-demo safety: per-key limits on writes and uploads, and a switch to pause writes.
    rate_limit_writes_per_minute: int = 60
    rate_limit_uploads_per_minute: int = 10
    writes_enabled: bool = True

    @field_validator("database_url", "database_url_unpooled")
    @classmethod
    def _use_psycopg_driver(cls, url: str | None) -> str | None:
        """Hosted Postgres (Neon, Render) hands out postgres:// or postgresql:// URLs;
        SQLAlchemy needs the driver named explicitly."""
        if not url:
            return None if url is None else url
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url

    @property
    def migration_database_url(self) -> str:
        return self.database_url_unpooled or self.database_url


def uses_pooler(url: str) -> bool:
    """Neon's pooled endpoints have a hostname ending in -pooler (PgBouncer, transaction mode)."""
    from sqlalchemy.engine import make_url

    return "-pooler" in (make_url(url).host or "")


settings = Settings()
