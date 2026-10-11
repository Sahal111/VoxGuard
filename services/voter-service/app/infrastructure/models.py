"""SQLAlchemy ORM models for voter_db — per ERD §5.3–5.6, §5.14, §6.1."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Election(Base):
    __tablename__ = "elections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'DRAFT'"))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_attack_lab: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    candidates: Mapped[list[Candidate]] = relationship(
        back_populates="election", cascade="all, delete-orphan", order_by="Candidate.ballot_order"
    )
    voters: Mapped[list[Voter]] = relationship(
        back_populates="election", cascade="all, delete-orphan"
    )
    eligibilities: Mapped[list[VotingEligibility]] = relationship(
        back_populates="election", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("char_length(title) BETWEEN 3 AND 150", name="ck_elections_title_len"),
        CheckConstraint("char_length(description) <= 2000", name="ck_elections_desc_len"),
        CheckConstraint("status IN ('DRAFT', 'SCHEDULED', 'OPEN', 'CLOSED', 'FINALIZED')", name="ck_elections_status"),
        CheckConstraint("start_at < end_at", name="ck_elections_start_before_end"),
        CheckConstraint("closed_at IS NULL OR opened_at IS NOT NULL", name="ck_elections_close_after_open"),
    )


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    election_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("elections.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    ballot_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    election: Mapped[Election] = relationship(back_populates="candidates")

    __table_args__ = (
        UniqueConstraint("election_id", "name", name="uq_candidates_election_name"),
        UniqueConstraint("election_id", "ballot_order", name="uq_candidates_election_ballot_order"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 100", name="ck_candidates_name_len"),
        CheckConstraint("char_length(description) <= 1000", name="ck_candidates_desc_len"),
        CheckConstraint("ballot_order >= 1", name="ck_candidates_ballot_order"),
    )


class Voter(Base):
    __tablename__ = "voters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    election_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("elections.id", ondelete="CASCADE"), nullable=False
    )
    email_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    external_ref: Mapped[str] = mapped_column(Text, nullable=False)
    display_label: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    election: Mapped[Election] = relationship(back_populates="voters")
    eligibility: Mapped[VotingEligibility | None] = relationship(
        back_populates="voter",
        uselist=False,
        cascade="all, delete-orphan",
        overlaps="eligibilities",
    )

    __table_args__ = (
        UniqueConstraint("election_id", "email_normalized", name="uq_voters_election_email"),
        UniqueConstraint("election_id", "external_ref", name="uq_voters_election_external_ref"),
        UniqueConstraint("election_id", "id", name="uq_voters_election_id"),
        Index(
            "uq_voters_election_user",
            "election_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        CheckConstraint("email_normalized = lower(email_normalized)", name="ck_voters_email_lower"),
    )


class VotingEligibility(Base):
    __tablename__ = "voting_eligibility"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    election_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    voter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    eligibility_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ELIGIBLE'"))
    ticket_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voted_marked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    election: Mapped[Election] = relationship(back_populates="eligibilities")
    voter: Mapped[Voter] = relationship(back_populates="eligibility")

    __table_args__ = (
        ForeignKeyConstraint(
            ["election_id", "voter_id"],
            ["voters.election_id", "voters.id"],
            ondelete="CASCADE",
            name="fk_eligibility_voter_composite",
        ),
        ForeignKeyConstraint(
            ["election_id"],
            ["elections.id"],
            ondelete="CASCADE",
            name="fk_eligibility_election",
        ),
        UniqueConstraint("election_id", "voter_id", name="uq_eligibility_election_voter"),
        UniqueConstraint("election_id", "eligibility_ref", name="uq_eligibility_election_ref"),
        CheckConstraint(
            "status IN ('ELIGIBLE', 'TICKET_ISSUED', 'VOTED', 'REVOKED')",
            name="ck_eligibility_status",
        ),
        CheckConstraint(
            "char_length(eligibility_ref) = 64 AND eligibility_ref ~ '^[0-9a-f]{64}$'",
            name="ck_eligibility_ref_hex",
        ),
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    routing_key: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'1.0'"))
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
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
        CheckConstraint("status IN ('PENDING', 'PUBLISHED', 'FAILED')", name="ck_outbox_status"),
    )


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    consumer: Mapped[str] = mapped_column(Text, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
