"""Configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_ENV: str = "local"
    SECURITY_DATABASE_URL: str
    SECURITY_DATABASE_URL_SYNC: str = ""
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT: int = 10

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
