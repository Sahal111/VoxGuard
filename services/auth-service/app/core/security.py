"""Password hashing and JWT token management for auth-service."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

# ── Password hashing (bcrypt) ───────────────────────────────────

def hash_password(password: str) -> str:
    """Hash password using bcrypt. Never log the password."""
    pw_bytes = password.encode("utf-8")
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash. Returns False on any error."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


# ── Refresh token ───────────────────────────────────────────────
def generate_refresh_token() -> str:
    """Generate a cryptographically secure refresh token (64 hex chars)."""
    return secrets.token_hex(32)


def hash_token(token: str) -> str:
    """SHA-256 hash of a token. Only the hash is stored in DB."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── JWT access token ────────────────────────────────────────────
def create_access_token(
    user_id: uuid.UUID,
    email: str,
    role: str,
    display_name: str,
) -> tuple[str, int]:
    """Create a signed JWT access token. Returns (token, expires_in_seconds)."""
    expires_in = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "display_name": display_name,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT access token. Raises jwt exceptions on failure."""
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["sub", "email", "role", "exp", "iat", "jti"]},
    )
