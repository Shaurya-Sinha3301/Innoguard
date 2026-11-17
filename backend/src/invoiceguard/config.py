from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://invoiceguard:invoiceguard@localhost:5433/invoiceguard"
    redis_url: str = "redis://localhost:6380/0"
    # Reviewer identities as "key:name" pairs, comma separated. Empty means nobody can sign in.
    api_keys: str = ""
    # Extraction model; set EXTRACTION_MODEL to change it (for example claude-opus-5-5).
    extraction_model: str = "claude-haiku-5-5"
    # "anthropic" for live calls, "replay" to use recorded responses only.
    extraction_mode: str = "anthropic"
    extraction_cache_dir: str = "/app/extraction-cache"
    extraction_max_attempts: int = 4
    # Comma-separated browser origins allowed to call the API (the review UI).
    cors_origins: str = "http://localhost:5173"
    # Public-demo safety: per-key limits on writes and uploads, and a switch to pause writes.
    rate_limit_writes_per_minute: int = 60
    rate_limit_uploads_per_minute: int = 10
    writes_enabled: bool = True

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, url: str) -> str:
        """Hosted Postgres (Neon, Render) hands out postgres:// or postgresql:// URLs;
        SQLAlchemy needs the driver named explicitly."""
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url


settings = Settings()
