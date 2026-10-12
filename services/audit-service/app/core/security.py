"""Cryptographic helpers for audit-service: hash chain, HMAC checkpoint, JWT."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timezone

import jwt

from app.core.config import settings


# ── Hash chain ─────────────────────────────────────────────────
def canonical_timestamp(value: datetime) -> str:
    """UTC, microsecond precision, fixed width (SAD §12). Naive datetimes are rejected."""
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def compute_event_hash(
    scope_id: uuid.UUID,
    sequence: int,
    source_event_id: uuid.UUID,
    source_event_type: str,
    occurred_at: datetime,
    correlation_id: uuid.UUID,
    payload_public: dict,
    prev_hash: str,
) -> str:
    """event_hash = SHA-256(canonical JSON of the event fields, including prev_hash).

    Field set follows SAD §12. Canonical form: keys sorted, no whitespace, UTF-8,
    timestamps as fixed-width UTC. Output: 64-char lowercase hex.
    """
    canonical = json.dumps(
        {
            "scope_id": str(scope_id),
            "sequence": sequence,
            "source_event_id": str(source_event_id),
            "source_event_type": source_event_type,
            "occurred_at": canonical_timestamp(occurred_at),
            "correlation_id": str(correlation_id),
            "payload_public": payload_public,
            "prev_hash": prev_hash,
        },
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Checkpoint HMAC ────────────────────────────────────────────
def compute_checkpoint_hmac(
    scope_id: uuid.UUID,
    sequence: int,
    event_hash: str,
    reason: str,
) -> str:
    """HMAC-SHA256(AUDIT_CHECKPOINT_KEY, canonical checkpoint data).

    Key never stored in DB. Used to detect offline tampering of checkpoint records.
    """
    canonical = f"{scope_id}:{sequence}:{event_hash}:{reason}"
    return hmac.HMAC(
        settings.AUDIT_CHECKPOINT_KEY.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ── Internal key ───────────────────────────────────────────────
def verify_internal_key(key: str | None) -> bool:
    """Constant-time comparison for internal service key."""
    if not key or not settings.INTERNAL_API_KEY:
        return False
    return secrets.compare_digest(key, settings.INTERNAL_API_KEY)


# ── User JWT (Bearer access token from auth-service) ───────────
def decode_access_token(token: str) -> dict:
    """Decode and verify an access token (same claims as ballot/auth services).

    Fail-closed: with no JWT_SECRET configured every token is rejected.
    """
    if not settings.JWT_SECRET:
        raise jwt.InvalidTokenError("JWT_SECRET not configured")
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["sub", "email", "role", "exp", "iat", "jti"]},
    )


# ── Payload allowlist projection ───────────────────────────────
# Fields permitted in payload_public for each event type.
# All other fields are stripped before recording in audit chain.
# Privacy: no candidate_id, eligibility_ref, user_id, email, IP.
PAYLOAD_ALLOWLIST: dict[str, set[str]] = {
    "VoteAccepted": {"election_id", "ballot_id", "receipt_id", "accepted_at", "ballot_commitment"},
    "VoteRejected": {"election_id", "reason_code", "occurred_at"},
    "ElectionOpened": {"election_id", "title", "opened_at", "end_at"},
    "ElectionClosed": {"election_id", "closed_at"},
    "TallyCompleted": {"election_id", "tally_run_id", "total_ballots", "audit_vote_events", "voter_participation"},
    "ResultFinalized": {"election_id", "tally_run_id", "result_hash", "finalized_at"},
    "SecurityAlertRaised": {"election_id", "rule_code", "severity", "raised_at"},
}


def project_payload(event_type: str, raw_payload: dict) -> dict:
    """Return only allowlisted fields for the given event_type.

    Unknown event types → empty dict (conservative; do not record unknown fields).
    Fields not in allowlist are silently dropped (never logged in full).
    """
    allowed = PAYLOAD_ALLOWLIST.get(event_type, set())
    return {k: v for k, v in raw_payload.items() if k in allowed}
