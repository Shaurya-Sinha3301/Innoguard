from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://invoiceguard:invoiceguard@localhost:5433/invoiceguard"
    redis_url: str = "redis://localhost:6380/0"


settings = Settings()
