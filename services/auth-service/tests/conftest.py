"""Pytest configuration for auth-service."""

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("AUTH_DATABASE_URL", "postgresql+asyncpg://auth_app:dev_auth_pass@localhost:5432/auth_db")
os.environ.setdefault("AUTH_DATABASE_URL_SYNC", "postgresql://auth_app:dev_auth_pass@localhost:5432/auth_db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-must-be-at-least-32-chars-long!")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")
