from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_DEBUG: bool = False
    INGEST_API_KEY: str | None = None
    RULES_PATH: str = "rules/rules.yaml"

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433
    POSTGRES_USER: str = "app"
    POSTGRES_PASSWORD: str = "app"
    POSTGRES_DB: str = "insider"

    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID: str | None = None

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()