"""Core audit-service business logic.

Responsibilities:
1. append_event() — idempotent event ingestion into the hash chain
2. verify_chain() — walk chain and verify each event_hash
3. get_events() — paginated query of audit_events (payload_public only)
4. get_proof() — proof endpoint data: chain head, checkpoints, receipt lookup
5. get_summary_internal() — for result-service reconciliation
6. get_commitments_internal() — list ballot_commitments for result-service

Hash chain per SAD §14 / ERD §5.10:
  event_hash = SHA-256(JSON{scope_id, sequence, source_event_id, source_event_type,
                              occurred_at, payload_public, prev_hash})
  scope_id = election_id (or GLOBAL_SCOPE for non-election events)
  sequence starts at 1 per scope

Idempotency:
  UNIQUE(source_event_id) on audit_events prevents double-recording.
  ON CONFLICT DO NOTHING → treated as already processed.

Privacy:
  payload_public is always filtered through the allowlist before storage.
  candidate_id, eligibility_ref, user_id, email never stored.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    compute_checkpoint_hmac,
    compute_event_hash,
    project_payload,
)
from app.infrastructure.models import (
    AuditChainHead,
    AuditCheckpoint,
    AuditEvent,
    IntegrityCheck,
    OutboxEvent,
    ProcessedEvent,
)

logger = logging.getLogger("audit_service.service")

# GLOBAL scope for events not tied to a specific election
GLOBAL_SCOPE = uuid.UUID("00000000-0000-0000-0000-000000000000")


class AuditError(Exception):
    """Structured error for audit-service operations."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ── Event ingestion ─────────────────────────────────────────────
async def append_event(
    db: AsyncSession,
    *,
    source_event_id: uuid.UUID,
    source_event_type: str,
    occurred_at: datetime,
    correlation_id: uuid.UUID,
    raw_payload: dict,
    scope_id: uuid.UUID | None = None,
    consumer: str = "audit-service",
) -> dict | None:
    """Idempotently record one event into the audit hash chain.

    Returns the created AuditEvent dict, or None if already processed.

    Algorithm per SAD §14:
    1. Check processed_events for dedup (per source_event_id + consumer)
    2. SELECT FOR UPDATE audit_chain_heads to get prev_hash and last_sequence
    3. Project payload through allowlist
    4. Compute event_hash over canonical fields
    5. INSERT audit_events (UNIQUE source_event_id → ON CONFLICT DO NOTHING)
    6. UPSERT audit_chain_heads
    7. INSERT processed_events
    8. COMMIT
    """
    # Determine scope: election_id if present in payload, else GLOBAL_SCOPE
    if scope_id is None:
        eid = raw_payload.get("election_id")
        scope_id = uuid.UUID(str(eid)) if eid else GLOBAL_SCOPE

    # ── 1. Check dedup ──────────────────────────────────────────
    existing = await db.execute(
        select(ProcessedEvent).where(
            ProcessedEvent.event_id == source_event_id,
            ProcessedEvent.consumer == consumer,
        )
    )
    if existing.scalar_one_or_none() is not None:
        logger.info(
            "audit_event_already_processed",
            extra={"source_event_id": str(source_event_id), "consumer": consumer},
        )
        return None

    # ── 2. Lock chain head ──────────────────────────────────────
    head_res = await db.execute(
        select(AuditChainHead)
        .where(AuditChainHead.scope_id == scope_id)
        .with_for_update()
    )
    head = head_res.scalar_one_or_none()
    if head is None:
        prev_hash = settings.GENESIS_HASH
        next_sequence = 1
    else:
        prev_hash = head.last_hash
        next_sequence = head.last_sequence + 1

    # ── 3. Project payload ─────────────────────────────────────
    payload_public = project_payload(source_event_type, raw_payload)

    # ── 4. Compute hash ─────────────────────────────────────────
    now = datetime.now(timezone.utc)
    event_hash = compute_event_hash(
        scope_id=scope_id,
        sequence=next_sequence,
        source_event_id=source_event_id,
        source_event_type=source_event_type,
        occurred_at=occurred_at,
        payload_public=payload_public,
        prev_hash=prev_hash,
    )

    # ── 5. INSERT audit_events ──────────────────────────────────
    event_id = uuid.uuid4()
    try:
        await db.execute(
            insert(AuditEvent).values(
                id=event_id,
                scope_id=scope_id,
                sequence=next_sequence,
                source_event_id=source_event_id,
                source_event_type=source_event_type,
                occurred_at=occurred_at,
                recorded_at=now,
                correlation_id=correlation_id,
                payload_public=payload_public,
                prev_hash=prev_hash,
                event_hash=event_hash,
            )
        )
    except IntegrityError:
        await db.rollback()
        logger.info(
            "audit_event_dedup_integrity",
            extra={"source_event_id": str(source_event_id)},
        )
        return None

    # ── 6. UPSERT chain head ────────────────────────────────────
    await db.execute(
        insert(AuditChainHead)
        .values(
            scope_id=scope_id,
            last_sequence=next_sequence,
            last_hash=event_hash,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["scope_id"],
            set_={
                "last_sequence": next_sequence,
                "last_hash": event_hash,
                "updated_at": now,
            },
        )
    )

    # ── 7. INSERT processed_events ──────────────────────────────
    await db.execute(
        insert(ProcessedEvent).values(
            event_id=source_event_id,
            consumer=consumer,
            processed_at=now,
        )
    )

    await db.commit()

    logger.info(
        "audit_event_recorded",
        extra={
            "scope_id": str(scope_id),
            "sequence": next_sequence,
            "event_type": source_event_type,
            "source_event_id": str(source_event_id),
        },
    )
    return {
        "id": event_id,
        "scope_id": scope_id,
        "sequence": next_sequence,
        "source_event_id": source_event_id,
        "source_event_type": source_event_type,
        "occurred_at": occurred_at,
        "recorded_at": now,
        "payload_public": payload_public,
        "event_hash": event_hash,
    }


# ── Chain verification ──────────────────────────────────────────
async def verify_chain(
    db: AsyncSession,
    scope_id: uuid.UUID,
    requested_by: uuid.UUID | None = None,
) -> dict:
    """Walk the audit chain for a scope and verify every event_hash.

    Returns dict compatible with [S-VERIFY-AUDIT] schema.
    Integrity failures reported in body (not HTTP error) per API contract §5.5 No.18.
    Always INSERTs an integrity_checks record.
    """
    # Fetch all events in order
    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.scope_id == scope_id)
        .order_by(AuditEvent.sequence.asc())
    )
    events = result.scalars().all()

    if not events:
        # No events yet — trivially valid, sequence 0
        ic = IntegrityCheck(
            scope_id=scope_id,
            status="VALID",
            events_checked=0,
            head_sequence=0,
            head_hash=settings.GENESIS_HASH,
            requested_by=requested_by,
        )
        db.add(ic)
        await db.commit()
        return {
            "scope_id": str(scope_id),
            "status": "VALID",
            "events_checked": 0,
            "head_sequence": 0,
            "head_hash": settings.GENESIS_HASH,
        }

    prev_hash = settings.GENESIS_HASH
    first_failure_sequence: int | None = None
    failure_reason: str | None = None

    for evt in events:
        computed = compute_event_hash(
            scope_id=evt.scope_id,
            sequence=evt.sequence,
            source_event_id=evt.source_event_id,
            source_event_type=evt.source_event_type,
            occurred_at=evt.occurred_at,
            payload_public=evt.payload_public,
            prev_hash=prev_hash,
        )
        if computed != evt.event_hash:
            first_failure_sequence = evt.sequence
            failure_reason = "EVENT_HASH_MISMATCH"
            break
        prev_hash = evt.event_hash

    status = "VALID" if first_failure_sequence is None else "INVALID"
    head_evt = events[-1]

    ic = IntegrityCheck(
        scope_id=scope_id,
        status=status,
        events_checked=len(events),
        head_sequence=head_evt.sequence,
        head_hash=head_evt.event_hash,
        first_failure_sequence=first_failure_sequence,
        failure_reason=failure_reason,
        requested_by=requested_by,
    )
    db.add(ic)
    await db.commit()

    result_dict: dict[str, Any] = {
        "scope_id": str(scope_id),
        "status": status,
        "events_checked": len(events),
        "head_sequence": head_evt.sequence,
        "head_hash": head_evt.event_hash,
    }
    if first_failure_sequence is not None:
        result_dict["first_failure"] = {
            "sequence": first_failure_sequence,
            "reason": failure_reason,
        }
    return result_dict


# ── Query events (public endpoint) ─────────────────────────────
async def get_events(
    db: AsyncSession,
    *,
    election_id: uuid.UUID | None = None,
    event_type: str | None = None,
    from_sequence: int | None = None,
    to_sequence: int | None = None,
    order: str = "asc",
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Paginated audit event list per API contract §5.5 No.17."""
    scope = election_id if election_id else GLOBAL_SCOPE
    q = select(AuditEvent).where(AuditEvent.scope_id == scope)
    if event_type:
        q = q.where(AuditEvent.source_event_type == event_type)
    if from_sequence is not None:
        q = q.where(AuditEvent.sequence >= from_sequence)
    if to_sequence is not None:
        q = q.where(AuditEvent.sequence <= to_sequence)

    count_q = select(func.count()).select_from(q.subquery())
    total_res = await db.execute(count_q)
    total = total_res.scalar() or 0

    if order == "desc":
        q = q.order_by(AuditEvent.sequence.desc())
    else:
        q = q.order_by(AuditEvent.sequence.asc())

    offset = (page - 1) * page_size
    q = q.offset(offset).limit(page_size)
    result = await db.execute(q)
    events = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": str(e.id),
                "scope_id": str(e.scope_id),
                "sequence": e.sequence,
                "source_event_id": str(e.source_event_id),
                "source_event_type": e.source_event_type,
                "occurred_at": e.occurred_at.isoformat(),
                "recorded_at": e.recorded_at.isoformat(),
                "payload_public": e.payload_public,
                "event_hash": e.event_hash,
            }
            for e in events
        ],
    }


# ── Proof endpoint ──────────────────────────────────────────────
async def get_proof(
    db: AsyncSession,
    election_id: uuid.UUID,
    receipt_id: uuid.UUID | None = None,
) -> dict:
    """Return chain proof per API contract §5.5 No.19.

    No identity, candidate_id, or eligibility_ref in response.
    """
    scope_id = election_id

    # Chain head
    head_res = await db.execute(
        select(AuditChainHead).where(AuditChainHead.scope_id == scope_id)
    )
    head = head_res.scalar_one_or_none()

    # Latest integrity check
    ic_res = await db.execute(
        select(IntegrityCheck)
        .where(IntegrityCheck.scope_id == scope_id)
        .order_by(IntegrityCheck.created_at.desc())
        .limit(1)
    )
    last_check = ic_res.scalar_one_or_none()

    # Receipt event lookup (by receipt_id in payload_public)
    receipt_event = None
    if receipt_id is not None:
        re_res = await db.execute(
            select(AuditEvent).where(
                AuditEvent.scope_id == scope_id,
                AuditEvent.source_event_type == "VoteAccepted",
                AuditEvent.payload_public["receipt_id"].astext == str(receipt_id),
            )
        )
        re = re_res.scalar_one_or_none()
        if re is not None:
            receipt_event = {
                "sequence": re.sequence,
                "event_hash": re.event_hash,
                "source_event_id": str(re.source_event_id),
                "recorded_at": re.recorded_at.isoformat(),
            }

    return {
        "election_id": str(election_id),
        "head": {
            "sequence": head.last_sequence if head else 0,
            "hash": head.last_hash if head else settings.GENESIS_HASH,
        },
        "last_verification": {
            "status": last_check.status if last_check else None,
            "events_checked": last_check.events_checked if last_check else None,
            "checked_at": last_check.created_at.isoformat() if last_check else None,
        },
        "receipt_event": receipt_event,
    }


# ── Internal: summary for result-service ───────────────────────
async def get_summary_internal(
    db: AsyncSession,
    election_id: uuid.UUID,
) -> dict:
    """Count VoteAccepted events for this election (for reconciliation)."""
    scope_id = election_id
    q = select(func.count()).select_from(
        select(AuditEvent)
        .where(
            AuditEvent.scope_id == scope_id,
            AuditEvent.source_event_type == "VoteAccepted",
        )
        .subquery()
    )
    res = await db.execute(q)
    vote_count = res.scalar() or 0

    head_res = await db.execute(
        select(AuditChainHead).where(AuditChainHead.scope_id == scope_id)
    )
    head = head_res.scalar_one_or_none()

    return {
        "election_id": str(election_id),
        "audit_vote_events": vote_count,
        "head_sequence": head.last_sequence if head else 0,
        "head_hash": head.last_hash if head else settings.GENESIS_HASH,
    }


# ── Internal: commitments for result-service ───────────────────
async def get_commitments_internal(
    db: AsyncSession,
    election_id: uuid.UUID,
) -> dict:
    """Return list of ballot_commitment values from VoteAccepted events.

    Privacy: only ballot_commitment and ballot_id — no candidate_id, eligibility_ref.
    """
    scope_id = election_id
    q = select(AuditEvent).where(
        AuditEvent.scope_id == scope_id,
        AuditEvent.source_event_type == "VoteAccepted",
    ).order_by(AuditEvent.sequence.asc())
    res = await db.execute(q)
    events = res.scalars().all()

    commitments = [
        {
            "ballot_id": e.payload_public.get("ballot_id"),
            "ballot_commitment": e.payload_public.get("ballot_commitment"),
            "sequence": e.sequence,
        }
        for e in events
    ]
    return {
        "election_id": str(election_id),
        "count": len(commitments),
        "commitments": commitments,
    }
