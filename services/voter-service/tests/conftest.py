"""Pytest configuration for voter-service."""

import os

# Set test environment before any app imports
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("VOTER_DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db")
