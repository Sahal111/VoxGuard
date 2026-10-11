"""SQLAlchemy ORM models for ballot_db.

Tables: ballots, idempotency_records, outbox_events, election_gates,
        audit_acks, processed_events.

No cross-database foreign keys (SAD §7.1). All references to voter_db
(election_id, candidate_id, eligibility_ref) are logical-only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Ballot(Base):
    """Append-only ballot record. Per ERD §5.7 — no user_id, email, IP."""

    __tablename__ = "ballots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    election_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    eligibility_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ballot_nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    ballot_commitment: Mapped[str] = mapped_column(String(64), nullable=False)
    receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()")
    )
    outbox_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'ACCEPTED'")
    )
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("election_id", "eligibility_ref", name="uq_ballots_election_eligibility"),
        UniqueConstraint("receipt_id", name="uq_ballots_receipt_id"),
        UniqueConstraint("outbox_event_id", name="uq_ballots_outbox_event_id"),
        CheckConstraint("status = 'ACCEPTED'", name="ck_ballots_status"),
        CheckConstraint(
            "char_length(eligibility_ref) = 64 AND eligibility_ref ~ '^[0-9a-f]{64}$'",
            name="ck_ballots_eligibility_ref_hex",
        ),
        CheckConstraint(
            "char_length(ballot_nonce) = 64 AND ballot_nonce ~ '^[0-9a-f]{64}$'",
            name="ck_ballots_nonce_hex",
        ),
        CheckConstraint(
            "char_length(ballot_commitment) = 64 AND ballot_commitment ~ '^[0-9a-f]{64}$'",
            name="ck_ballots_commitment_hex",
        ),
    )


class IdempotencyRecord(Base):
    """Per-eligibility_ref idempotency store. Per ERD §5.8."""

    __tablename__ = "idempotency_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    election_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    eligibility_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "eligibility_ref", "idempotency_key", name="uq_idempotency_ref_key"
        ),
        CheckConstraint(
            "idempotency_key ~ '^[A-Za-z0-9_-]{16,64}$'",
            name="ck_idempotency_key_format",
        ),
        CheckConstraint(
            "char_length(eligibility_ref) = 64 AND eligibility_ref ~ '^[0-9a-f]{64}$'",
            name="ck_idempotency_ref_hex",
        ),
        Index("ix_idempotency_expires_at", "expires_at"),
    )


class OutboxEvent(Base):
    """Transactional outbox for at-least-once event delivery. Per ERD §5.14."""

    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    routing_key: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'1.0'")
    )
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'PENDING'")
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PUBLISHED', 'FAILED')", name="ck_outbox_status"
        ),
    )


class ElectionGate(Base):
    """Local gate cache for election OPEN/CLOSED status. Per ERD §5.9.

    Used for fast local rejection; always cross-checked with Voter Service
    per SAD §10 (fail-closed if Voter unreachable).
    """

    __tablename__ = "election_gates"

    election_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('OPEN', 'CLOSED')", name="ck_election_gates_status"
        ),
    )


class AuditAck(Base):
    """Acknowledgement from audit-service that a VoteAccepted event was chained. Per ERD §5.9."""

    __tablename__ = "audit_acks"

    source_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    audit_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "char_length(event_hash) = 64 AND event_hash ~ '^[0-9a-f]{64}$'",
            name="ck_audit_acks_hash_hex",
        ),
    )


class ProcessedEvent(Base):
    """Idempotency dedup for consumed events. Per ERD §5.14."""

    __tablename__ = "processed_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    consumer: Mapped[str] = mapped_column(Text, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
