"""Security helpers for ballot-service: JWT validation, HMAC receipt code."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid

import jwt

from app.core.config import settings


# ── User JWT (Bearer access token from auth-service) ───────────
def decode_access_token(token: str) -> dict:
    """Decode and verify user access token (HS256, issued by auth-service).

    Required claims: sub, email, role, exp, iat, jti.
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["sub", "email", "role", "exp", "iat", "jti"]},
    )


# ── Vote ticket JWT (issued by voter-service) ──────────────────
def decode_vote_ticket(token: str, election_id: uuid.UUID) -> dict:
    """Decode and verify a vote_ticket JWT.

    Verifies:
    - Signature with VOTE_TICKET_SECRET
    - Expiry
    - aud == 'voxguard-ballot'
    - typ == 'vote-ticket'
    - election_id claim matches supplied election_id

    Returns payload dict on success. Raises jwt.* on failure.
    """
    payload = jwt.decode(
        token,
        settings.VOTE_TICKET_SECRET,
        algorithms=[settings.VOTE_TICKET_ALGORITHM],
        audience="voxguard-ballot",
        options={"require": ["sub", "election_id", "exp", "iat", "aud", "typ"]},
    )
    if payload.get("typ") != "vote-ticket":
        raise jwt.InvalidTokenError("typ claim must be 'vote-ticket'")
    if str(payload.get("election_id")) != str(election_id):
        raise jwt.InvalidTokenError("election_id mismatch in vote_ticket")
    return payload


# ── Receipt HMAC code ──────────────────────────────────────────
def compute_receipt_code(receipt_id: uuid.UUID) -> str:
    """Derive receipt_code = HMAC-SHA256(RECEIPT_HMAC_KEY, receipt_id) → hex48.

    The code can be recomputed for replay without persisting it in the DB.
    The receipt_code is truncated to 48 hex chars for readability.
    """
    digest = hmac.HMAC(
        settings.RECEIPT_HMAC_KEY.encode("utf-8"),
        str(receipt_id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:48]


# ── Internal key ───────────────────────────────────────────────
def verify_internal_key(key: str | None) -> bool:
    """Constant-time comparison for internal service key."""
    if not key or not settings.INTERNAL_API_KEY:
        return False
    return secrets.compare_digest(key, settings.INTERNAL_API_KEY)


# ── Ballot commitment ──────────────────────────────────────────
def compute_ballot_commitment(
    election_id: uuid.UUID,
    candidate_id: uuid.UUID,
    nonce: str,
) -> str:
    """Compute ballot_commitment = SHA-256(election_id:candidate_id:nonce).

    Allows result-service to detect tampering with candidate_id without
    exposing the choice in audit events (SAD §12).
    """
    data = f"{election_id}:{candidate_id}:{nonce}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def generate_ballot_nonce() -> str:
    """Generate a 256-bit cryptographically random nonce (64 hex chars)."""
    return secrets.token_hex(32)


# ── Request hash ───────────────────────────────────────────────
def compute_request_hash(election_id: uuid.UUID, candidate_id: uuid.UUID) -> str:
    """SHA-256 of canonical {election_id, candidate_id} for idempotency dedup."""
    canonical = f"{election_id}:{candidate_id}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
