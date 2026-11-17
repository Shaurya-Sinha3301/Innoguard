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


settings = Settings()
