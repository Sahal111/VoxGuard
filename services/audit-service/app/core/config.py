"""Configuration for audit-service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_ENV: str = "local"

    # Database
    AUDIT_DATABASE_URL: str
    AUDIT_DATABASE_URL_SYNC: str = ""
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT: int = 10

    # Security
    INTERNAL_API_KEY: str = "dev-internal-key"
    AUDIT_CHECKPOINT_KEY: str = "dev-checkpoint-hmac-key-must-be-secret-in-prod"

    # Audit chain
    GENESIS_HASH: str = "0" * 64   # 64 zeros — initial prev_hash for first event

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
