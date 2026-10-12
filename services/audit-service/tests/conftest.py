"""Pytest configuration for audit-service unit tests (no DB, no broker)."""

import os

# Set test environment before any app imports
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("AUDIT_DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-must-be-at-least-32-chars-long!")
os.environ.setdefault("AUDIT_CHECKPOINT_KEY", "test-checkpoint-key-must-be-at-least-32-chars!")
# Unit tests never start the consumer, whatever the developer's shell exports.
os.environ["RABBITMQ_URL"] = ""
