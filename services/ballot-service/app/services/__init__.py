"""Ballot service — core business logic.

Implements the cast_vote algorithm per SAD §10 (Concurrency and Idempotency Design):

1. BEGIN
2. INSERT idempotency_records ON CONFLICT (eligibility_ref, idempotency_key) DO NOTHING
   - 0 rows inserted → read existing record:
       request_hash same  → return stored response (200 idempotent replay)
       request_hash diff  → raise IDEMPOTENCY_CONFLICT (409)
3. INSERT ballots; UNIQUE(election_id, eligibility_ref) violation → VOTER_ALREADY_VOTED (409)
4. INSERT outbox_events (VoteAccepted); UPDATE idempotency_records (response_snapshot); COMMIT

Election gate check (fail-closed): always verify against Voter Service live;
503 if Voter unreachable. Rejects if election not OPEN or now > end_at.

Privacy guarantees:
- candidate_id never in logs, events, or responses (only in DB ballot commitment)
- eligibility_ref in VoteAccepted payload only (per event contract §8.3)
- No user_id, email, IP, or name in ballot DB or events
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

# pyrefly: ignore [missing-import]
import httpx
# pyrefly: ignore [missing-import]
from sqlalchemy import select, update
# pyrefly: ignore [missing-import]
from sqlalchemy.dialects.postgresql import insert
# pyrefly: ignore [missing-import]
from sqlalchemy.exc import IntegrityError
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    compute_ballot_commitment,
    compute_receipt_code,
    compute_request_hash,
    generate_ballot_nonce,
)
from app.infrastructure.models import (
    AuditAck,
    Ballot,
    ElectionGate,
    IdempotencyRecord,
    OutboxEvent,
)

logger = logging.getLogger("ballot_service.service")


# ── Structured error ────────────────────────────────────────────
class BallotError(Exception):
    """Structured error for ballot-service operations."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ── Voter Service client ─────────────────────────────────────────
async def _fetch_ballot_info(election_id: uuid.UUID) -> dict:
    """Call GET /internal/v1/elections/{id}/ballot-info on voter-service.

    Raises BallotError(SERVICE_UNAVAILABLE, 503) if unreachable or non-200.
    """
    url = f"{settings.VOTER_SERVICE_URL}/internal/v1/elections/{election_id}/ballot-info"
    try:
        async with httpx.AsyncClient(timeout=settings.VOTER_CALL_TIMEOUT) as client:
            resp = await client.get(
                url,
                headers={"X-Internal-Key": settings.INTERNAL_API_KEY},
            )
    except httpx.TimeoutException:
        logger.warning("voter_service_timeout", extra={"election_id": str(election_id)})
        raise BallotError(
            "SERVICE_UNAVAILABLE",
            "Voter service tidak tersedia saat ini. Coba lagi nanti.",
            503,
        )
    except Exception as exc:
        logger.warning(
            "voter_service_error",
            extra={"election_id": str(election_id), "error": str(exc)[:200]},
        )
        raise BallotError(
            "SERVICE_UNAVAILABLE",
            "Voter service tidak tersedia saat ini. Coba lagi nanti.",
            503,
        )

    if resp.status_code == 404:
        raise BallotError("NOT_FOUND", "Pemilihan tidak ditemukan.", 404)
    if resp.status_code != 200:
        logger.warning(
            "voter_service_unexpected",
            extra={"election_id": str(election_id), "status": resp.status_code},
        )
        raise BallotError(
            "SERVICE_UNAVAILABLE",
            "Voter service mengembalikan respons tidak terduga.",
            503,
        )
    return resp.json()


async def _validate_election_open(election_id: uuid.UUID) -> dict:
    """Verify election is OPEN and within its voting window.

    Always calls Voter Service synchronously (fail-closed per SAD §10).
    Returns ballot_info dict on success.
    Raises BallotError(ELECTION_NOT_OPEN, 409) or BallotError(SERVICE_UNAVAILABLE, 503).
    """
    ballot_info = await _fetch_ballot_info(election_id)

    election_status = ballot_info.get("status")
    if election_status != "OPEN":
        raise BallotError(
            "ELECTION_NOT_OPEN",
            f"Pemilihan tidak sedang berlangsung. Status: {election_status}.",
            409,
        )

    end_at_str = ballot_info.get("end_at")
    if end_at_str:
        try:
            end_at = datetime.fromisoformat(end_at_str.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > end_at:
                raise BallotError(
                    "ELECTION_NOT_OPEN",
                    "Waktu pemungutan suara sudah berakhir.",
                    409,
                )
        except ValueError:
            pass  # if parse fails, do not block (Voter Service is authoritative)

    return ballot_info


# ── Main cast_vote algorithm ─────────────────────────────────────
async def cast_vote(
    db: AsyncSession,
    *,
    election_id: uuid.UUID,
    candidate_id: uuid.UUID,
    eligibility_ref: str,
    idempotency_key: str,
    correlation_id: uuid.UUID,
    ballot_info: dict,                   # pre-validated from Voter Service
) -> tuple[dict, bool]:
    """Record a vote atomically per SAD §10 algorithm.

    Returns (receipt_dict, is_replay).
    Raises BallotError on any business error.

    Transaction boundary:
      BEGIN
        INSERT idempotency_records … ON CONFLICT DO NOTHING  ← serializes concurrent same-key
        INSERT ballots                                        ← UNIQUE prevents double vote
        INSERT outbox_events
        UPDATE idempotency_records (snapshot)
      COMMIT

    Failure modes handled:
    - Same key, same payload, already committed → idempotent replay (200)
    - Same key, different candidate  → IDEMPOTENCY_CONFLICT (409)
    - Different key, eligibility already voted → VOTER_ALREADY_VOTED (409)
    - Crash before COMMIT → full rollback; client may retry
    - Crash after COMMIT → idempotency record committed; retry yields stored response
    """
    # Validate candidate belongs to this election (from ballot_info returned by Voter)
    candidate_ids = {str(c["id"]) for c in ballot_info.get("candidates", [])}
    if str(candidate_id) not in candidate_ids:
        raise BallotError(
            "VALIDATION_ERROR",
            "Kandidat tidak terdaftar dalam pemilihan ini.",
            422,
        )

    # Precompute all values outside the transaction
    request_hash = compute_request_hash(election_id, candidate_id)
    nonce = generate_ballot_nonce()
    commitment = compute_ballot_commitment(election_id, candidate_id, nonce)
    receipt_id = uuid.uuid4()
    receipt_code = compute_receipt_code(receipt_id)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.IDEMPOTENCY_TTL_SECONDS)
    outbox_id = uuid.uuid4()

    response_snapshot: dict[str, Any] = {
        "receipt_id": str(receipt_id),
        "election_id": str(election_id),
        "accepted_at": now.isoformat(),
        "receipt_code": receipt_code,
        "audit_status": "PENDING",
    }

    try:
        # ── Step 1: INSERT idempotency (ON CONFLICT DO NOTHING) ──────
        stmt = (
            insert(IdempotencyRecord)
            .values(
                election_id=election_id,
                eligibility_ref=eligibility_ref,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_snapshot=response_snapshot,
                created_at=now,
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(
                index_elements=None,
                constraint="uq_idempotency_ref_key",
            )
            .returning(IdempotencyRecord.id)
        )
        result = await db.execute(stmt)
        inserted_row = result.fetchone()

        if inserted_row is None:
            # Record already exists → fetch it
            existing = await db.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.eligibility_ref == eligibility_ref,
                    IdempotencyRecord.idempotency_key == idempotency_key,
                )
            )
            existing_rec = existing.scalar_one_or_none()
            if existing_rec is None:
                # Race: inserted by concurrent tx that hasn't committed yet; treat as conflict
                raise BallotError(
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key sedang diproses oleh request lain.",
                    409,
                )
            if existing_rec.request_hash != request_hash:
                await db.rollback()
                raise BallotError(
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key sudah digunakan dengan payload yang berbeda.",
                    409,
                )
            # Same payload → idempotent replay
            await db.rollback()
            stored = existing_rec.response_snapshot
            return stored, True

        # ── Step 2: INSERT ballot (RETURNING id) ─────────────────────
        ballot_stmt = (
            insert(Ballot)
            .values(
                election_id=election_id,
                eligibility_ref=eligibility_ref,
                candidate_id=candidate_id,
                ballot_nonce=nonce,
                ballot_commitment=commitment,
                receipt_id=receipt_id,
                outbox_event_id=outbox_id,
                status="ACCEPTED",
                accepted_at=now,
            )
            .returning(Ballot.id)
        )
        ballot_res = await db.execute(ballot_stmt)
        ballot_row = ballot_res.fetchone()
        ballot_db_id = str(ballot_row[0]) if ballot_row else None

        # ── Step 3: INSERT outbox event (VoteAccepted) ───────────────
        # Privacy: candidate_id NOT included in payload (SAD §11, §8.3)
        outbox_payload: dict[str, Any] = {
            "election_id": str(election_id),
            "ballot_id": ballot_db_id,          # DB-generated uuid via RETURNING
            "receipt_id": str(receipt_id),
            "accepted_at": now.isoformat(),
            "ballot_commitment": commitment,
            "eligibility_ref": eligibility_ref,  # only for Voter consumer per §8.3
        }
        outbox_stmt = insert(OutboxEvent).values(
            id=outbox_id,
            event_type="VoteAccepted",
            routing_key="vote.accepted",
            schema_version="1.0",
            correlation_id=correlation_id,
            payload=outbox_payload,
            status="PENDING",
            attempts=0,
            next_attempt_at=now,
            created_at=now,
        )
        await db.execute(outbox_stmt)

        # ── Step 4: UPDATE idempotency record with final snapshot ────
        await db.execute(
            update(IdempotencyRecord)
            .where(
                IdempotencyRecord.eligibility_ref == eligibility_ref,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
            .values(response_snapshot=response_snapshot)
        )

        await db.commit()

        logger.info(
            "vote_accepted",
            extra={
                "service": "ballot-service",
                "election_id": str(election_id),
                "receipt_id": str(receipt_id),
                "correlation_id": str(correlation_id),
                # NOTE: candidate_id intentionally omitted from log
            },
        )
        return response_snapshot, False

    except IntegrityError as exc:
        await db.rollback()
        constraint = str(exc.orig) if exc.orig else ""
        if "uq_ballots_election_eligibility" in constraint:
            raise BallotError(
                "VOTER_ALREADY_VOTED",
                "Hak memilih Anda sudah digunakan.",
                409,
            )
        logger.error(
            "ballot_integrity_error",
            extra={"error": str(exc)[:300]},
        )
        raise BallotError("INTERNAL_ERROR", "Terjadi kesalahan sistem.", 500)


# ── Receipt lookup ───────────────────────────────────────────────
async def get_receipt(
    db: AsyncSession,
    receipt_id: uuid.UUID,
) -> dict:
    """Return receipt status without any candidate or voter identity data."""
    result = await db.execute(
        select(Ballot).where(Ballot.receipt_id == receipt_id)
    )
    ballot = result.scalar_one_or_none()
    if ballot is None:
        raise BallotError("RECEIPT_NOT_FOUND", "Receipt tidak ditemukan.", 404)

    # Determine audit_status from audit_acks
    ack_result = await db.execute(
        select(AuditAck).where(AuditAck.source_event_id == ballot.outbox_event_id)
    )
    ack = ack_result.scalar_one_or_none()
    audit_status = "RECORDED" if ack is not None else "PENDING"

    return {
        "receipt_id": ballot.receipt_id,
        "election_id": ballot.election_id,
        "accepted_at": ballot.accepted_at,
        "audit_status": audit_status,
    }


# ── Election gate update (from ElectionOpened/Closed events) ────
async def upsert_election_gate(
    db: AsyncSession,
    election_id: uuid.UUID,
    status: str,
    closed_at: datetime | None = None,
) -> None:
    """Update local election_gates cache idempotently."""
    now = datetime.now(timezone.utc)
    stmt = (
        insert(ElectionGate)
        .values(
            election_id=election_id,
            status=status,
            closed_at=closed_at,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["election_id"],
            set_={"status": status, "closed_at": closed_at, "updated_at": now},
        )
    )
    await db.execute(stmt)
    await db.commit()
