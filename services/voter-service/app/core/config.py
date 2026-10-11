"""Configuration loaded from environment variables for voter-service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_ENV: str = "local"

    # Database
    VOTER_DATABASE_URL: str
    VOTER_DATABASE_URL_SYNC: str = ""
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT: int = 10

    # Security & Tokens
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ELIGIBILITY_PEPPER: str = "default-voter-eligibility-pepper-must-be-secret-in-prod"
    INTERNAL_API_KEY: str = "dev-internal-key"
    ATTACK_LAB_ENABLED: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
