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
    JWT_SECRET: str = ""            # shared with auth-service; empty = every token rejected
    JWT_ALGORITHM: str = "HS256"

    # Audit chain
    GENESIS_HASH: str = "0" * 64   # 64 zeros — initial prev_hash for first event

    # Event consumer (SAD §11). Empty RABBITMQ_URL disables the consumer.
    RABBITMQ_URL: str = ""
    AUDIT_EXCHANGE: str = "voxguard.events"
    AUDIT_QUEUE: str = "audit.vote-accepted"
    AUDIT_PREFETCH: int = 1                       # one in flight → deterministic order
    # Tiered retry per SAD §11.3: failure 1..3 wait these delays, failure 4 → DLQ.
    AUDIT_RETRY_DELAYS_MS: list[int] = [5_000, 30_000, 120_000]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
