"""Security helpers for voter-service: JWT decoding, HMAC pseudonym generation."""

from __future__ import annotations

import hmac
import hashlib
import secrets
import uuid

import jwt

from app.core.config import settings


def decode_access_token(token: str) -> dict:
    """Decode and verify an HS256 JWT access token issued by auth-service."""
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["sub", "email", "role", "exp", "iat", "jti"]},
    )


def compute_eligibility_ref(
    pepper: str,
    election_id: uuid.UUID,
    voter_id: uuid.UUID,
) -> str:
    """Compute deterministic pseudonym: HMAC-SHA256(pepper, election_id:voter_id).

    Per SAD §8.3 & ERD §7.2:
    - Stable within the election (allows UNIQUE constraint to prevent double voting).
    - Different across elections.
    - Irreversible without ELIGIBILITY_PEPPER.
    - Yields a 64-character lowercase hexadecimal string.
    """
    message = f"{election_id}:{voter_id}".encode("utf-8")
    return hmac.new(
        pepper.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()


def verify_internal_key(key: str | None) -> bool:
    """Verify internal service-to-service key (constant-time compare)."""
    if not key or not settings.INTERNAL_API_KEY:
        return False
    return secrets.compare_digest(key, settings.INTERNAL_API_KEY)
