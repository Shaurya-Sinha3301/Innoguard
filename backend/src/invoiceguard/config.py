from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # hide_input_in_errors: a bad connection string must never be echoed into the logs,
    # because it contains a password.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    # Application traffic. On Neon this is the pooled URL (host ends in -pooler).
    database_url: str = "postgresql+psycopg://invoiceguard:invoiceguard@localhost:5433/invoiceguard"
    # Migrations need a direct connection; on Neon this is DATABASE_URL_UNPOOLED.
    # Falls back to database_url when unset (local Postgres has no pooler).
    database_url_unpooled: str | None = None
    redis_url: str = "redis://localhost:6380/0"
    # Reviewer identities as "key:name" pairs, comma separated. Empty means nobody can sign in.
    api_keys: str = ""
    # Where clients reach this service (used for MCP discovery metadata and host checks).
    public_url: str = "http://localhost:8000"
    # The OAuth authorization server that issues tokens for the MCP endpoint. Unset means
    # API-key mode: clients present an issued key as a bearer token.
    mcp_issuer_url: str | None = None
    rate_limit_mcp_per_minute: int = 60
    # Accounts. Anyone can create one while signup is open; turn it off for a private
    # deployment and create accounts another way. ADMIN_EMAILS lists who becomes an
    # administrator on signup; if it is empty, the very first account is the administrator.
    signup_enabled: bool = True
    admin_emails: str = ""
    session_days: int = 7
    # What a new account may do. Agent keys a person generates for themselves are limited to
    # what their account may do, and never include review or admin.
    signup_scopes: str = "read,submit,review,post"
    rate_limit_auth_per_minute: int = 10
    # Reviewer names (from API_KEYS) that may also manage principals and keys.
    admin_users: str = ""
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

    @field_validator("redis_url", mode="before")
    @classmethod
    def _check_redis_url(cls, url: str) -> str:
        """Fail early with a plain message, not a traceback from inside Celery. Values pasted
        from a provider's dashboard often arrive with quotes, a 'REDIS_URL=' prefix, an
        https:// REST address or a whole redis-cli command."""
        url = url.strip().strip("\"'")
        if url.upper().startswith("REDIS_URL="):
            url = url.split("=", 1)[1].strip().strip("\"'")
        if not url.startswith(("redis://", "rediss://", "unix://")):
            raise ValueError(
                "REDIS_URL must start with redis:// or rediss:// (a TLS Redis such as Upstash "
                "uses rediss://default:<password>@<host>:6379). It looks like a different kind "
                "of address, such as an https:// REST URL or a pasted redis-cli command."
            )
        return url

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
