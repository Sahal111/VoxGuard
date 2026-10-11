"""Pytest configuration for result-service."""

import os

# Set test environment before any app imports
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("RESULT_DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db")
