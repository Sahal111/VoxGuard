"""Append-only audit chain: atomic append, integrity verification, read models.

Trust model (SAD §12): the chain *detects* modification of stored records by
anyone who cannot also rewrite every later hash and the head. A party with
write access to this whole database (and the checkpoint key, if used) can
rebuild a consistent chain. Nothing here prevents that; see
docs/09_AUDIT_SERVICE_NOTES.md.
"""

from __future__ import annotations

import hmac
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

# pyrefly: ignore [missing-import]
from sqlalchemy import func, select, text
# pyrefly: ignore [missing-import]
from sqlalchemy.dialects.postgresql import insert as pg_insert
# pyrefly: ignore [missing-import]
from sqlalchemy.exc import IntegrityError
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.security import compute_checkpoint_hmac, compute_event_hash
from app.infrastructure.models import (
    AuditChainHead,
    AuditCheckpoint,
    AuditEvent,
    IntegrityCheck,
    ProcessedEvent,
)

logger = logging.getLogger("audit_service.chain")

GLOBAL_SCOPE_ID = uuid.UUID(int=0)  # scope for events that belong to no election
VERIFY_BATCH = 1000


# ── Append ─────────────────────────────────────────────────────
@dataclass(frozen=True)
class AppendResult:
    status: str  # "RECORDED" | "DUPLICATE"
    sequence: int | None = None
    event_hash: str | None = None


async def record_event(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    consumer: str,
    source_event_id: uuid.UUID,
    source_event_type: str,
    scope_id: uuid.UUID,
    occurred_at: datetime,
    correlation_id: uuid.UUID,
    payload_public: dict,
) -> AppendResult:
    """Append one event to its scope's chain in a single transaction.

    Dedup marker (processed_events), chain-head lock, event insert and head
    update commit together or not at all. The head row is locked FOR UPDATE, so
    concurrent appenders to one scope are serialised and sequences never fork.
    """
    async with session_factory() as session, session.begin():
        fresh = await session.execute(
            pg_insert(ProcessedEvent)
            .values(event_id=source_event_id, consumer=consumer)
            .on_conflict_do_nothing()
            .returning(ProcessedEvent.event_id)
        )
        if fresh.first() is None:
            return AppendResult("DUPLICATE")

        # Create the head row if this is the scope's first event, then lock it.
        await session.execute(
            pg_insert(AuditChainHead).values(scope_id=scope_id).on_conflict_do_nothing()
        )
        head = (
            await session.execute(
                select(AuditChainHead)
                .where(AuditChainHead.scope_id == scope_id)
                .with_for_update()
            )
        ).scalar_one()

        sequence = head.last_sequence + 1
        event_hash = compute_event_hash(
            scope_id,
            sequence,
            source_event_id,
            source_event_type,
            occurred_at,
            correlation_id,
            payload_public,
            head.last_hash,
        )
        try:
            async with session.begin_nested():
                session.add(
                    AuditEvent(
                        scope_id=scope_id,
                        sequence=sequence,
                        source_event_id=source_event_id,
                        source_event_type=source_event_type,
                        occurred_at=occurred_at,
                        correlation_id=correlation_id,
                        payload_public=payload_public,
                        prev_hash=head.last_hash,
                        event_hash=event_hash,
                    )
                )
        except IntegrityError as exc:
            # Same source event already chained (e.g. recorded under another consumer name).
            if "uq_audit_events_source_event_id" in str(exc.orig):
                return AppendResult("DUPLICATE")
            raise

        head.last_sequence = sequence
        head.last_hash = event_hash
        head.updated_at = func.now()
        return AppendResult("RECORDED", sequence, event_hash)


# ── Verify ─────────────────────────────────────────────────────
@dataclass
class VerifyOutcome:
    check_id: uuid.UUID
    scope_id: uuid.UUID
    status: str  # VALID | INVALID
    events_checked: int
    head_sequence: int
    head_hash: str
    first_failure: dict | None  # {"sequence": int, "reason": str}
    checkpoint: dict  # {"compared", "matches", "checkpoint_sequence"}
    checked_at: datetime


async def verify_chain(
    session: AsyncSession,
    scope_id: uuid.UUID,
    requested_by: uuid.UUID | None = None,
) -> VerifyOutcome | None:
    """Recompute the whole chain for one scope from the stored rows.

    Reads inside one REPEATABLE READ snapshot so concurrent appends cannot cause
    a false HEAD_MISMATCH. Returns None when the scope has no chain at all.
    Each call records a row in integrity_checks (failure_reason is a fixed code).
    """
    # Must be the first statement of the transaction.
    await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))

    head = (
        await session.execute(select(AuditChainHead).where(AuditChainHead.scope_id == scope_id))
    ).scalar_one_or_none()
    any_event = (
        await session.execute(
            select(AuditEvent.sequence).where(AuditEvent.scope_id == scope_id).limit(1)
        )
    ).first()
    if head is None and any_event is None:
        await session.rollback()
        return None

    failure: tuple[int, str] | None = None
    last_seq, last_hash, checked = 0, settings.GENESIS_HASH, 0
    cursor = 0
    while failure is None:
        rows = (
            await session.execute(
                select(AuditEvent)
                .where(AuditEvent.scope_id == scope_id, AuditEvent.sequence > cursor)
                .order_by(AuditEvent.sequence)
                .limit(VERIFY_BATCH)
            )
        ).scalars().all()
        if not rows:
            break
        for ev in rows:
            if ev.sequence != last_seq + 1:
                failure = (last_seq + 1, "SEQUENCE_GAP")
            elif ev.prev_hash != last_hash:
                failure = (ev.sequence, "PREV_HASH_MISMATCH")
            elif (
                compute_event_hash(
                    ev.scope_id,
                    ev.sequence,
                    ev.source_event_id,
                    ev.source_event_type,
                    ev.occurred_at,
                    ev.correlation_id,
                    ev.payload_public,
                    ev.prev_hash,
                )
                != ev.event_hash
            ):
                failure = (ev.sequence, "EVENT_HASH_MISMATCH")
            if failure:
                break
            last_seq, last_hash, checked = ev.sequence, ev.event_hash, checked + 1
        cursor = rows[-1].sequence

    head_seq = head.last_sequence if head else 0
    head_hash = head.last_hash if head else settings.GENESIS_HASH

    # Stored head must equal what the recomputed chain ends at.
    if failure is None and (head_seq != last_seq or head_hash != last_hash):
        failure = (min(head_seq, last_seq) + 1, "HEAD_MISMATCH")

    checkpoint = {"compared": False, "matches": None, "checkpoint_sequence": None}
    if failure is None:
        cp = (
            await session.execute(
                select(AuditCheckpoint)
                .where(AuditCheckpoint.scope_id == scope_id)
                .order_by(AuditCheckpoint.sequence.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if cp is not None:
            checkpoint = {"compared": True, "matches": False, "checkpoint_sequence": cp.sequence}
            expected_mac = compute_checkpoint_hmac(cp.scope_id, cp.sequence, cp.event_hash, cp.reason)
            if hmac.compare_digest(cp.hmac, expected_mac) and cp.sequence <= last_seq:
                stored = (
                    await session.execute(
                        select(AuditEvent.event_hash).where(
                            AuditEvent.scope_id == scope_id, AuditEvent.sequence == cp.sequence
                        )
                    )
                ).scalar_one_or_none()
                checkpoint["matches"] = stored == cp.event_hash
            if not checkpoint["matches"]:
                failure = (cp.sequence, "CHECKPOINT_MISMATCH")

    row = IntegrityCheck(
        scope_id=scope_id,
        status="INVALID" if failure else "VALID",
        events_checked=checked,
        head_sequence=head_seq,
        head_hash=head_hash,
        first_failure_sequence=failure[0] if failure else None,
        failure_reason=failure[1] if failure else None,
        checkpoint_compared=checkpoint["compared"],
        checkpoint_matches=checkpoint["matches"],
        requested_by=requested_by,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    await session.commit()

    if failure:
        logger.warning(
            "audit_integrity_failed",
            extra={"scope_id": str(scope_id), "sequence": failure[0], "reason": failure[1]},
        )
    return VerifyOutcome(
        check_id=row.id,
        scope_id=scope_id,
        status=row.status,
        events_checked=checked,
        head_sequence=head_seq,
        head_hash=head_hash,
        first_failure={"sequence": failure[0], "reason": failure[1]} if failure else None,
        checkpoint=checkpoint,
        checked_at=row.created_at,
    )


# ── Read models ────────────────────────────────────────────────
async def list_events(
    session: AsyncSession,
    *,
    scope_id: uuid.UUID,
    event_type: str | None,
    from_sequence: int | None,
    to_sequence: int | None,
    order: str,
    page: int,
    page_size: int,
) -> tuple[list[AuditEvent], int]:
    conditions = [AuditEvent.scope_id == scope_id]
    if event_type:
        conditions.append(AuditEvent.source_event_type == event_type)
    if from_sequence is not None:
        conditions.append(AuditEvent.sequence >= from_sequence)
    if to_sequence is not None:
        conditions.append(AuditEvent.sequence <= to_sequence)

    total = (
        await session.execute(select(func.count()).select_from(AuditEvent).where(*conditions))
    ).scalar_one()
    ordering = AuditEvent.sequence.desc() if order == "desc" else AuditEvent.sequence.asc()
    rows = (
        await session.execute(
            select(AuditEvent)
            .where(*conditions)
            .order_by(ordering)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), total


async def build_proof(
    session: AsyncSession, scope_id: uuid.UUID, receipt_id: uuid.UUID | None
) -> dict | None:
    """Public-safe proof facts for one scope. None when the scope has no chain."""
    head = (
        await session.execute(select(AuditChainHead).where(AuditChainHead.scope_id == scope_id))
    ).scalar_one_or_none()
    if head is None:
        return None

    event_count = (
        await session.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.scope_id == scope_id)
        )
    ).scalar_one()
    checkpoint = (
        await session.execute(
            select(AuditCheckpoint)
            .where(AuditCheckpoint.scope_id == scope_id)
            .order_by(AuditCheckpoint.sequence.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    last_check = (
        await session.execute(
            select(IntegrityCheck)
            .where(IntegrityCheck.scope_id == scope_id)
            .order_by(IntegrityCheck.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    receipt_event = None
    if receipt_id is not None:
        receipt_event = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.scope_id == scope_id,
                    AuditEvent.source_event_type == "VoteAccepted",
                    AuditEvent.payload_public["receipt_id"].astext == str(receipt_id),
                )
            )
        ).scalar_one_or_none()

    return {
        "election_id": scope_id,
        "hash_algorithm": "SHA-256",
        "canonicalization": "JSON kunci terurut, tanpa spasi, UTF-8, timestamp UTC mikrodetik",
        "genesis_hash": settings.GENESIS_HASH,
        "event_count": event_count,
        "head_sequence": head.last_sequence,
        "head_hash": head.last_hash,
        "latest_checkpoint": (
            {
                "sequence": checkpoint.sequence,
                "event_hash": checkpoint.event_hash,
                "reason": checkpoint.reason,
                "created_at": checkpoint.created_at,
            }
            if checkpoint
            else None
        ),
        "last_verified": (
            {"status": last_check.status, "checked_at": last_check.created_at}
            if last_check
            else None
        ),
        "receipt_event": (
            {
                "sequence": receipt_event.sequence,
                "prev_hash": receipt_event.prev_hash,
                "event_hash": receipt_event.event_hash,
            }
            if receipt_event
            else None
        ),
    }
