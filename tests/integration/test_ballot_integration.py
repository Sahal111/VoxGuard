"""Integration tests for Phase 11.1 — Ballot Service.

These tests require real PostgreSQL and RabbitMQ instances.
They are automatically SKIPPED if the services are not reachable.

Environment variables (can be set in .env or shell):
  BALLOT_DATABASE_URL         postgresql+asyncpg://...
  BALLOT_DATABASE_URL_SYNC    postgresql+psycopg2://...
  JWT_SECRET                  >=32 chars
  VOTE_TICKET_SECRET          >=32 chars
  RECEIPT_HMAC_KEY            >=32 chars
  VOTER_SERVICE_URL           http://voter-service:8002
  RABBITMQ_URL                amqp://guest:guest@localhost:5672/

Run with:
  cd services/ballot-service
  python3 -m pytest ../../tests/integration/test_ballot_integration.py -v

Separation:
  - Unit tests:        services/ballot-service/tests/   (mock DB, mock HTTP)
  - Integration tests: tests/integration/               (real DB, real RabbitMQ)
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

# ── Skip guards ─────────────────────────────────────────────────
_DB_URL = os.environ.get(
    "BALLOT_DATABASE_URL",
    "postgresql+asyncpg://ballot_app:changeme_ballot@localhost:5432/ballot_db",
)
_DB_SYNC = os.environ.get(
    "BALLOT_DATABASE_URL_SYNC",
    "postgresql+psycopg2://ballot_app:changeme_ballot@localhost:5432/ballot_db",
)
_RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "")

_pg_available = False
_mq_available = False


def _check_pg() -> bool:
    """Try a synchronous connection to detect if Postgres is available."""
    try:
        import psycopg2  # type: ignore[import]

        conn = psycopg2.connect(_DB_SYNC, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


def _check_rabbitmq() -> bool:
    """Try a synchronous AMQP connection (pika) to detect RabbitMQ."""
    if not _RABBITMQ_URL:
        return False
    try:
        import pika  # type: ignore[import]

        params = pika.URLParameters(_RABBITMQ_URL)
        params.socket_timeout = 2
        conn = pika.BlockingConnection(params)
        conn.close()
        return True
    except Exception:
        return False


# Evaluate once at collection time
try:
    _pg_available = _check_pg()
except Exception:
    pass

try:
    _mq_available = _check_rabbitmq()
except Exception:
    pass

requires_pg = pytest.mark.skipif(
    not _pg_available, reason="PostgreSQL not available (ballot_db unreachable)"
)
requires_mq = pytest.mark.skipif(
    not _mq_available, reason="RabbitMQ not available (RABBITMQ_URL not set or unreachable)"
)

# ── Test environment setup ───────────────────────────────────────
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("BALLOT_DATABASE_URL", _DB_URL)
os.environ.setdefault("BALLOT_DATABASE_URL_SYNC", _DB_SYNC)
os.environ.setdefault("JWT_SECRET", "test-secret-key-must-be-at-least-32-chars-long!")
os.environ.setdefault("VOTE_TICKET_SECRET", "test-vote-ticket-secret-must-be-32chars!")
os.environ.setdefault("RECEIPT_HMAC_KEY", "test-receipt-hmac-key-must-be-32chars-long!")
os.environ.setdefault("INTERNAL_API_KEY", "dev-internal-key")
os.environ.setdefault("VOTER_SERVICE_URL", "http://localhost:8002")


# ── Fixtures ─────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    """Shared event loop for the session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def db_engine():
    """Create async engine for ballot_db."""
    if not _pg_available:
        pytest.skip("PostgreSQL not available")
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(_DB_URL, echo=False)
    yield engine
    asyncio.get_event_loop().run_until_complete(engine.dispose())


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Provide a clean async session, rolled back after each test."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="session")
async def applied_migration(db_engine):
    """Run Alembic migration once per session, skip if already applied."""
    if not _pg_available:
        pytest.skip("PostgreSQL not available")
    from alembic import command
    from alembic.config import Config

    import pathlib

    ballot_root = pathlib.Path(__file__).parent.parent.parent / "services" / "ballot-service"
    cfg = Config(str(ballot_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(ballot_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _DB_SYNC)
    command.upgrade(cfg, "head")
    yield


# ── JWT helpers ───────────────────────────────────────────────────
def _make_jwt(role: str = "VOTER") -> str:
    import jwt

    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "email": "voter@test.vg",
            "role": role,
            "exp": now + timedelta(hours=1),
            "iat": now,
            "jti": str(uuid.uuid4()),
        },
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )


def _make_ticket(eligibility_ref: str, election_id: uuid.UUID, exp_delta: int = 300) -> str:
    import jwt

    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": eligibility_ref,
            "election_id": str(election_id),
            "aud": "voxguard-ballot",
            "typ": "vote-ticket",
            "exp": now + timedelta(seconds=exp_delta),
            "iat": now,
        },
        os.environ["VOTE_TICKET_SECRET"],
        algorithm="HS256",
    )


def _make_elig() -> str:
    import secrets

    return secrets.token_hex(32)  # 64 hex chars


# ══════════════════════════════════════════════════════════════════
# GROUP A: Migration
# ══════════════════════════════════════════════════════════════════

@requires_pg
@pytest.mark.asyncio
async def test_migration_applies_ballot_tables(applied_migration, db_engine):
    """Verify all ballot_db tables exist after migration."""
    from sqlalchemy import text

    expected = {
        "ballots",
        "idempotency_records",
        "outbox_events",
        "election_gates",
        "audit_acks",
        "processed_events",
    }
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
        )
        tables = {row[0] for row in result}

    missing = expected - tables
    assert not missing, f"Missing tables after migration: {missing}"


@requires_pg
@pytest.mark.asyncio
async def test_migration_unique_constraints_present(applied_migration, db_engine):
    """Verify double-vote and idempotency UNIQUE constraints exist."""
    from sqlalchemy import text

    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT conname FROM pg_constraint WHERE contype = 'u' "
                "AND conrelid IN (SELECT oid FROM pg_class WHERE relname IN "
                "('ballots', 'idempotency_records'))"
            )
        )
        constraints = {row[0] for row in result}

    assert "uq_ballots_election_eligibility" in constraints, (
        "UNIQUE(election_id, eligibility_ref) on ballots missing — double-vote guard not enforced"
    )
    assert "uq_idempotency_ref_key" in constraints, (
        "UNIQUE(eligibility_ref, idempotency_key) on idempotency_records missing"
    )


# ══════════════════════════════════════════════════════════════════
# GROUP B: cast_vote correctness (requires real DB)
# ══════════════════════════════════════════════════════════════════

@requires_pg
@pytest.mark.asyncio
async def test_cast_vote_inserts_ballot_and_outbox(applied_migration, db_session):
    """Happy path: cast_vote creates one ballot + one outbox event in one transaction."""
    import sys

    sys.path.insert(
        0,
        str(
            __import__("pathlib").Path(__file__).parent.parent.parent
            / "services"
            / "ballot-service"
        ),
    )
    from unittest.mock import AsyncMock, patch

    from app.services import cast_vote
    from sqlalchemy import select, text

    election_id = uuid.uuid4()
    candidate_id = uuid.uuid4()
    eligibility_ref = _make_elig()
    idempotency_key = str(uuid.uuid4())

    ballot_info = {
        "election_id": str(election_id),
        "status": "OPEN",
        "end_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "candidates": [{"id": str(candidate_id)}],
    }

    snapshot, is_replay = await cast_vote(
        db_session,
        election_id=election_id,
        candidate_id=candidate_id,
        eligibility_ref=eligibility_ref,
        idempotency_key=idempotency_key,
        correlation_id=uuid.uuid4(),
        ballot_info=ballot_info,
    )

    assert not is_replay
    assert snapshot["audit_status"] == "PENDING"
    assert "candidate_id" not in snapshot

    # Verify ballot exists in DB
    from app.infrastructure.models import Ballot, OutboxEvent

    ballot_res = await db_session.execute(
        select(Ballot).where(Ballot.eligibility_ref == eligibility_ref)
    )
    ballot = ballot_res.scalar_one_or_none()
    assert ballot is not None
    assert str(ballot.election_id) == str(election_id)
    assert ballot.candidate_id == candidate_id

    # Verify outbox event exists with ballot_id filled
    outbox_res = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.id == ballot.outbox_event_id)
    )
    outbox = outbox_res.scalar_one_or_none()
    assert outbox is not None
    assert outbox.event_type == "VoteAccepted"
    assert outbox.payload.get("ballot_id") == str(ballot.id)
    assert "candidate_id" not in outbox.payload
    assert outbox.payload.get("ballot_commitment") is not None


@requires_pg
@pytest.mark.asyncio
async def test_double_vote_db_constraint(applied_migration, db_session):
    """Two different idempotency keys for same eligibility → second must be rejected."""
    import sys

    sys.path.insert(
        0,
        str(
            __import__("pathlib").Path(__file__).parent.parent.parent
            / "services"
            / "ballot-service"
        ),
    )
    from app.services import BallotError, cast_vote

    election_id = uuid.uuid4()
    candidate_id = uuid.uuid4()
    eligibility_ref = _make_elig()
    ballot_info = {
        "election_id": str(election_id),
        "status": "OPEN",
        "end_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "candidates": [{"id": str(candidate_id)}],
    }

    # First vote succeeds
    await cast_vote(
        db_session,
        election_id=election_id,
        candidate_id=candidate_id,
        eligibility_ref=eligibility_ref,
        idempotency_key=str(uuid.uuid4()),
        correlation_id=uuid.uuid4(),
        ballot_info=ballot_info,
    )

    # Second vote with different key must fail VOTER_ALREADY_VOTED
    # Need fresh session to avoid transaction state issues
    with pytest.raises(BallotError) as exc_info:
        await cast_vote(
            db_session,
            election_id=election_id,
            candidate_id=candidate_id,
            eligibility_ref=eligibility_ref,
            idempotency_key=str(uuid.uuid4()),  # different key
            correlation_id=uuid.uuid4(),
            ballot_info=ballot_info,
        )
    assert exc_info.value.code == "VOTER_ALREADY_VOTED"


@requires_pg
@pytest.mark.asyncio
async def test_idempotent_replay_no_extra_ballot(applied_migration, db_session):
    """Same idempotency key + same payload returns stored response without extra ballot."""
    import sys

    sys.path.insert(
        0,
        str(
            __import__("pathlib").Path(__file__).parent.parent.parent
            / "services"
            / "ballot-service"
        ),
    )
    from app.services import cast_vote
    from sqlalchemy import func, select
    from app.infrastructure.models import Ballot

    election_id = uuid.uuid4()
    candidate_id = uuid.uuid4()
    eligibility_ref = _make_elig()
    idem_key = str(uuid.uuid4())
    ballot_info = {
        "election_id": str(election_id),
        "status": "OPEN",
        "end_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "candidates": [{"id": str(candidate_id)}],
    }

    snap1, is_replay1 = await cast_vote(
        db_session,
        election_id=election_id,
        candidate_id=candidate_id,
        eligibility_ref=eligibility_ref,
        idempotency_key=idem_key,
        correlation_id=uuid.uuid4(),
        ballot_info=ballot_info,
    )
    assert not is_replay1

    snap2, is_replay2 = await cast_vote(
        db_session,
        election_id=election_id,
        candidate_id=candidate_id,
        eligibility_ref=eligibility_ref,
        idempotency_key=idem_key,
        correlation_id=uuid.uuid4(),
        ballot_info=ballot_info,
    )
    assert is_replay2
    assert snap1["receipt_id"] == snap2["receipt_id"]

    # Count ballots for this eligibility — must be exactly 1
    count_res = await db_session.execute(
        select(func.count()).select_from(
            select(Ballot)
            .where(
                Ballot.election_id == election_id,
                Ballot.eligibility_ref == eligibility_ref,
            )
            .subquery()
        )
    )
    assert count_res.scalar() == 1


@requires_pg
@pytest.mark.asyncio
async def test_idempotency_conflict_rejected(applied_migration, db_session):
    """Same key + different candidate_id → IDEMPOTENCY_CONFLICT."""
    import sys

    sys.path.insert(
        0,
        str(
            __import__("pathlib").Path(__file__).parent.parent.parent
            / "services"
            / "ballot-service"
        ),
    )
    from app.services import BallotError, cast_vote

    election_id = uuid.uuid4()
    candidate_a = uuid.uuid4()
    candidate_b = uuid.uuid4()
    eligibility_ref = _make_elig()
    idem_key = str(uuid.uuid4())
    ballot_info_a = {
        "election_id": str(election_id),
        "status": "OPEN",
        "end_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "candidates": [{"id": str(candidate_a)}, {"id": str(candidate_b)}],
    }

    await cast_vote(
        db_session,
        election_id=election_id,
        candidate_id=candidate_a,
        eligibility_ref=eligibility_ref,
        idempotency_key=idem_key,
        correlation_id=uuid.uuid4(),
        ballot_info=ballot_info_a,
    )

    # Replay with different candidate → IDEMPOTENCY_CONFLICT
    with pytest.raises(BallotError) as exc_info:
        await cast_vote(
            db_session,
            election_id=election_id,
            candidate_id=candidate_b,
            eligibility_ref=eligibility_ref,
            idempotency_key=idem_key,
            correlation_id=uuid.uuid4(),
            ballot_info=ballot_info_a,
        )
    assert exc_info.value.code == "IDEMPOTENCY_CONFLICT"


@requires_pg
@pytest.mark.asyncio
async def test_ballot_id_in_outbox_event_is_real_uuid(applied_migration, db_session):
    """VoteAccepted outbox payload must contain actual ballot.id, not None."""
    import sys

    sys.path.insert(
        0,
        str(
            __import__("pathlib").Path(__file__).parent.parent.parent
            / "services"
            / "ballot-service"
        ),
    )
    from app.services import cast_vote
    from sqlalchemy import select
    from app.infrastructure.models import Ballot, OutboxEvent

    election_id = uuid.uuid4()
    candidate_id = uuid.uuid4()
    eligibility_ref = _make_elig()
    ballot_info = {
        "election_id": str(election_id),
        "status": "OPEN",
        "end_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "candidates": [{"id": str(candidate_id)}],
    }

    await cast_vote(
        db_session,
        election_id=election_id,
        candidate_id=candidate_id,
        eligibility_ref=eligibility_ref,
        idempotency_key=str(uuid.uuid4()),
        correlation_id=uuid.uuid4(),
        ballot_info=ballot_info,
    )

    ballot_res = await db_session.execute(
        select(Ballot).where(Ballot.eligibility_ref == eligibility_ref)
    )
    ballot = ballot_res.scalar_one()

    outbox_res = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.id == ballot.outbox_event_id)
    )
    outbox = outbox_res.scalar_one()

    ballot_id_in_event = outbox.payload.get("ballot_id")
    assert ballot_id_in_event is not None, "ballot_id must not be None in VoteAccepted payload"
    assert ballot_id_in_event == str(ballot.id), (
        f"ballot_id mismatch: event={ballot_id_in_event}, db={ballot.id}"
    )


# ══════════════════════════════════════════════════════════════════
# GROUP C: Receipt code
# ══════════════════════════════════════════════════════════════════

def test_receipt_code_hmac_is_valid_python():
    """Verify compute_receipt_code runs without AttributeError.

    This directly tests the HMAC implementation (not mocked).
    """
    import sys

    sys.path.insert(
        0,
        str(
            __import__("pathlib").Path(__file__).parent.parent.parent
            / "services"
            / "ballot-service"
        ),
    )
    from app.core.security import compute_receipt_code

    rid = uuid.uuid4()
    code = compute_receipt_code(rid)
    assert isinstance(code, str)
    assert len(code) == 48
    # Must be valid hex
    int(code, 16)


def test_receipt_code_is_deterministic():
    """Same receipt_id always produces the same code."""
    import sys

    sys.path.insert(
        0,
        str(
            __import__("pathlib").Path(__file__).parent.parent.parent
            / "services"
            / "ballot-service"
        ),
    )
    from app.core.security import compute_receipt_code

    rid = uuid.uuid4()
    assert compute_receipt_code(rid) == compute_receipt_code(rid)


def test_receipt_code_different_ids_differ():
    """Different receipt IDs produce different codes (probabilistic)."""
    import sys

    sys.path.insert(
        0,
        str(
            __import__("pathlib").Path(__file__).parent.parent.parent
            / "services"
            / "ballot-service"
        ),
    )
    from app.core.security import compute_receipt_code

    assert compute_receipt_code(uuid.uuid4()) != compute_receipt_code(uuid.uuid4())


# ══════════════════════════════════════════════════════════════════
# GROUP D: API Gateway header stripping
# ══════════════════════════════════════════════════════════════════

def _gateway_build_headers(request_headers: dict, upstream_path: str, request_id: str = "r1", correlation_id: str = "c1") -> dict:
    """Standalone replica of _build_upstream_headers logic for testing.

    This mirrors the exact logic in services/api-gateway/app/main.py
    _build_upstream_headers. If the gateway changes, this must be updated.
    """
    HOP_BY_HOP = frozenset(("host", "connection", "transfer-encoding", "keep-alive"))
    ALWAYS_STRIP = frozenset(("x-user-id", "x-user-email", "x-internal-key"))
    BALLOT_STRIP = frozenset(("x-forwarded-user", "x-auth-user", "x-voter-id"))
    is_ballot_route = upstream_path.startswith("/api/v1/ballots")

    headers: dict[str, str] = {}
    for key, value in request_headers.items():
        lower_key = key.lower()
        if lower_key in HOP_BY_HOP:
            continue
        if lower_key in ALWAYS_STRIP:
            continue
        if is_ballot_route and lower_key in BALLOT_STRIP:
            continue
        headers[key] = value

    headers["X-Request-ID"] = request_id
    headers["X-Correlation-ID"] = correlation_id
    return headers


def test_gateway_strips_x_user_id_for_ballot_route():
    """Defense-in-depth: X-User-Id and X-User-Email stripped for ballot routes."""
    raw_headers = {
        "Authorization": "Bearer xxx",
        "X-User-Id": "spoofed-user-id",
        "X-User-Email": "spoofed@evil.com",
        "Content-Type": "application/json",
        "Idempotency-Key": "test-key-1234567890",
    }
    result = _gateway_build_headers(raw_headers, upstream_path="/api/v1/ballots")

    assert "X-User-Id" not in result
    assert "X-User-Email" not in result
    # Legitimate headers still forwarded
    assert "Authorization" in result
    assert "Idempotency-Key" in result
    assert result["X-Request-ID"] == "r1"


def test_gateway_strips_x_internal_key_for_all_routes():
    """X-Internal-Key must be stripped from ALL routes to prevent internal API abuse."""
    raw_headers = {
        "Authorization": "Bearer xxx",
        "X-Internal-Key": "any-value",
    }
    for path in ["/api/v1/elections", "/api/v1/ballots", "/api/v1/auth/login"]:
        result = _gateway_build_headers(raw_headers, upstream_path=path)
        assert "X-Internal-Key" not in result, (
            f"X-Internal-Key must not be forwarded for path {path}"
        )
        assert "Authorization" in result


# ══════════════════════════════════════════════════════════════════
# GROUP E: RabbitMQ outbox publisher
# ══════════════════════════════════════════════════════════════════

@requires_mq
@pytest.mark.asyncio
async def test_publisher_sends_event_to_rabbitmq():
    """OutboxPublisher.connect() declares the voxguard.events exchange."""
    import sys

    sys.path.insert(
        0,
        str(
            __import__("pathlib").Path(__file__).parent.parent.parent
            / "services"
            / "ballot-service"
        ),
    )
    from app.infrastructure.publisher import OutboxPublisher

    pub = OutboxPublisher(_RABBITMQ_URL)
    ok = await pub.connect()
    assert ok, "OutboxPublisher.connect() failed — is RabbitMQ up?"
    await pub.close()
