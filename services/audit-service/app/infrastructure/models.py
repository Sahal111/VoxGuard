"""SQLAlchemy ORM models for audit_db.

Tables: audit_events, audit_chain_heads, audit_checkpoints,
        integrity_checks, outbox_events, processed_events.

No cross-database foreign keys. All references to other services
(election_id, ballot_id, etc.) are logical UUIDs without FK.
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


class AuditEvent(Base):
    """Append-only tamper-evident audit event. Per ERD §5.10."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_event_type: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payload_public: Mapped[dict] = mapped_column(JSON, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("scope_id", "sequence", name="uq_audit_events_scope_seq"),
        UniqueConstraint("source_event_id", name="uq_audit_events_source_event_id"),
        CheckConstraint("sequence >= 1", name="ck_audit_events_sequence_positive"),
        CheckConstraint(
            "char_length(prev_hash) = 64 AND prev_hash ~ '^[0-9a-f]{64}$'",
            name="ck_audit_events_prev_hash_hex",
        ),
        CheckConstraint(
            "char_length(event_hash) = 64 AND event_hash ~ '^[0-9a-f]{64}$'",
            name="ck_audit_events_event_hash_hex",
        ),
        Index("ix_audit_events_scope_id", "scope_id"),
        Index("ix_audit_events_source_event_type", "source_event_type"),
    )


class AuditChainHead(Base):
    """Per-scope chain head pointer. Per ERD §5.11."""

    __tablename__ = "audit_chain_heads"

    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    last_sequence: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    last_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'" + "0" * 64 + "'")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class AuditCheckpoint(Base):
    """Periodic chain checkpoint with HMAC. Per ERD §5.11."""

    __tablename__ = "audit_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    exported_path: Mapped[str] = mapped_column(Text, nullable=False)
    hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("scope_id", "sequence", name="uq_audit_checkpoints_scope_seq"),
        CheckConstraint(
            "reason IN ('ELECTION_CLOSED', 'RESULT_FINALIZED', 'PERIODIC', 'MANUAL')",
            name="ck_audit_checkpoints_reason",
        ),
    )


class IntegrityCheck(Base):
    """Records of chain integrity verification runs. Per ERD §5.11."""

    __tablename__ = "integrity_checks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    events_checked: Mapped[int] = mapped_column(BigInteger, nullable=False)
    head_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    head_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_failure_sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkpoint_compared: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    checkpoint_matches: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("status IN ('VALID', 'INVALID')", name="ck_integrity_checks_status"),
        CheckConstraint("events_checked >= 0", name="ck_integrity_checks_events_checked"),
        Index("ix_integrity_checks_scope_id", "scope_id"),
    )


class OutboxEvent(Base):
    """Transactional outbox for audit-service published events."""

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
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PUBLISHED', 'FAILED')", name="ck_outbox_status"
        ),
        Index("ix_outbox_status_next", "status", "next_attempt_at"),
    )


class ProcessedEvent(Base):
    """Idempotency dedup for consumed incoming events."""

    __tablename__ = "processed_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    consumer: Mapped[str] = mapped_column(Text, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
