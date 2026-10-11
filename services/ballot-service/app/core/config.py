"""Configuration loaded from environment variables for ballot-service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_ENV: str = "local"

    # Database
    BALLOT_DATABASE_URL: str
    BALLOT_DATABASE_URL_SYNC: str = ""
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT: int = 10

    # Security
    JWT_SECRET: str                        # shared with auth-service to verify user Bearer JWT
    JWT_ALGORITHM: str = "HS256"
    VOTE_TICKET_SECRET: str                # shared with voter-service to verify vote_ticket JWT
    VOTE_TICKET_ALGORITHM: str = "HS256"
    RECEIPT_HMAC_KEY: str = "dev-receipt-hmac-key-must-be-secret-in-prod"

    # Internal service calls
    INTERNAL_API_KEY: str = "dev-internal-key"
    VOTER_SERVICE_URL: str = "http://localhost:8002"
    VOTER_CALL_TIMEOUT: float = 2.0        # fail-closed per SAD §10

    # Idempotency
    IDEMPOTENCY_TTL_SECONDS: int = 86_400  # 24 h

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
