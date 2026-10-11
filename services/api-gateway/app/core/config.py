"""Configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_ENV: str = "local"

    # Upstream service URLs
    AUTH_SERVICE_URL: str = "http://auth-service:8001"
    VOTER_SERVICE_URL: str = "http://voter-service:8002"
    BALLOT_SERVICE_URL: str = "http://ballot-service:8003"
    AUDIT_SERVICE_URL: str = "http://audit-service:8004"
    RESULT_SERVICE_URL: str = "http://result-service:8005"
    SECURITY_SERVICE_URL: str = "http://security-service:8006"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Timeouts (seconds)
    UPSTREAM_TIMEOUT: float = 8.0

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
