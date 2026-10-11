"""Pytest configuration for ballot-service."""

import os

# Set test environment BEFORE any app imports
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "BALLOT_DATABASE_URL",
    "postgresql+asyncpg://ballot_app:changeme_ballot@localhost:5432/ballot_db",
)
os.environ.setdefault(
    "BALLOT_DATABASE_URL_SYNC",
    "postgresql+psycopg2://ballot_app:changeme_ballot@localhost:5432/ballot_db",
)
os.environ.setdefault("JWT_SECRET", "test-secret-key-must-be-at-least-32-chars-long!")
os.environ.setdefault("VOTE_TICKET_SECRET", "test-vote-ticket-secret-must-be-32chars!")
os.environ.setdefault("RECEIPT_HMAC_KEY", "test-receipt-hmac-key-must-be-32chars-long!")
os.environ.setdefault("INTERNAL_API_KEY", "dev-internal-key")
os.environ.setdefault("VOTER_SERVICE_URL", "http://localhost:8002")
