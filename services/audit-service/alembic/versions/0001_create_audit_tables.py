"""create audit_db tables

Revision ID: 0001_audit_tables
Revises:
Create Date: 2026-10-12

Tables per ERD §5.10, §5.11, §5.14. audit_events is append-only at the
application level via a trigger (DBC-11); a table owner or superuser can still
disable it, which is exactly why verification recomputes the chain.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_audit_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_event_type", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload_public", postgresql.JSONB(), nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("scope_id", "sequence", name="uq_audit_events_scope_seq"),
        sa.UniqueConstraint("source_event_id", name="uq_audit_events_source_event_id"),
        sa.CheckConstraint("sequence >= 1", name="ck_audit_events_sequence_positive"),
        sa.CheckConstraint(
            "char_length(prev_hash) = 64 AND prev_hash ~ '^[0-9a-f]{64}$'",
            name="ck_audit_events_prev_hash_hex",
        ),
        sa.CheckConstraint(
            "char_length(event_hash) = 64 AND event_hash ~ '^[0-9a-f]{64}$'",
            name="ck_audit_events_event_hash_hex",
        ),
    )
    op.create_index("ix_audit_events_scope_id", "audit_events", ["scope_id"])
    op.create_index("ix_audit_events_source_event_type", "audit_events", ["source_event_type"])
    # receipt inclusion lookup (GET /audit/elections/{id}/proof?receipt_id=)
    op.execute(
        "CREATE INDEX ix_audit_events_receipt_id ON audit_events ((payload_public ->> 'receipt_id'))"
    )

    op.create_table(
        "audit_chain_heads",
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("last_sequence", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_hash", sa.String(64), server_default=sa.text("'" + "0" * 64 + "'"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "audit_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("exported_path", sa.Text(), nullable=False),
        sa.Column("hmac", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("scope_id", "sequence", name="uq_audit_checkpoints_scope_seq"),
        sa.CheckConstraint(
            "reason IN ('ELECTION_CLOSED', 'RESULT_FINALIZED', 'PERIODIC', 'MANUAL')",
            name="ck_audit_checkpoints_reason",
        ),
    )

    op.create_table(
        "integrity_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("events_checked", sa.BigInteger(), nullable=False),
        sa.Column("head_sequence", sa.BigInteger(), nullable=False),
        sa.Column("head_hash", sa.String(64), nullable=False),
        sa.Column("first_failure_sequence", sa.BigInteger(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("checkpoint_compared", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("checkpoint_matches", sa.Boolean(), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('VALID', 'INVALID')", name="ck_integrity_checks_status"),
        sa.CheckConstraint("events_checked >= 0", name="ck_integrity_checks_events_checked"),
    )
    op.create_index("ix_integrity_checks_scope_id", "integrity_checks", ["scope_id"])

    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("routing_key", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), server_default=sa.text("'1.0'"), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('PENDING', 'PUBLISHED', 'FAILED')", name="ck_outbox_status"),
    )
    op.create_index("ix_outbox_status_next", "outbox_events", ["status", "next_attempt_at"])

    op.create_table(
        "processed_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consumer", sa.Text(), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # DBC-11: audit_events rows are never updated or deleted through normal SQL.
    op.execute(
        """
        CREATE FUNCTION audit_forbid_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_audit_events_immutable BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION audit_forbid_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_audit_events_no_truncate BEFORE TRUNCATE ON audit_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_forbid_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_truncate ON audit_events")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_immutable ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS audit_forbid_mutation()")
    op.drop_table("processed_events")
    op.drop_index("ix_outbox_status_next", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("ix_integrity_checks_scope_id", table_name="integrity_checks")
    op.drop_table("integrity_checks")
    op.drop_table("audit_checkpoints")
    op.drop_table("audit_chain_heads")
    op.execute("DROP INDEX IF EXISTS ix_audit_events_receipt_id")
    op.drop_index("ix_audit_events_source_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_scope_id", table_name="audit_events")
    op.drop_table("audit_events")
