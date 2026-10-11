"""Pytest configuration for voter-service."""

import os

# Set test environment before any app imports
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("VOTER_DATABASE_URL", "postgresql+asyncpg://voter_app:changeme_voter@localhost:5432/voter_db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-must-be-at-least-32-chars-long!")
os.environ.setdefault("ELIGIBILITY_PEPPER", "test-pepper-secret-key-must-be-at-least-32-chars!")
os.environ.setdefault("INTERNAL_API_KEY", "dev-internal-key")
os.environ.setdefault("ATTACK_LAB_ENABLED", "false")
