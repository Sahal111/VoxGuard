"""Integration tests for Phase 12 — audit-service consumer, chain, verify, proof.

REAL PostgreSQL and RabbitMQ are required. Nothing here mocks the database or the
broker; VoteAccepted events are produced by ballot-service's own cast_vote() and
OutboxPublisher (see _ballot_emit.py). Everything is SKIPPED when the infra
environment variables below are not set or the services are unreachable.

  AUDIT_IT_PG_URL    postgresql://user:pw@host:5432/postgres   (role may CREATE DATABASE)
  AUDIT_IT_AMQP_URL  amqp://user:pw@host:5672/vhost            (user may declare queues/exchanges)
  AUDIT_IT_ALLOW_BROKER_RESTART=1   also run the broker-outage test; it runs
                     `rabbitmqctl stop_app` / `start_app` on the broker, so only
                     enable it against a disposable broker.

Run (separately from test_ballot_integration.py is fine, together also works —
this module swaps its own `app` package in and out of sys.modules):

  python3 -m pytest tests/integration/test_audit_integration.py -v

Unit tests live in services/audit-service/tests/ (no DB, no broker).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import types
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pytest
import pytest_asyncio

ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = ROOT / "services" / "audit-service"
BALLOT_DIR = ROOT / "services" / "ballot-service"
EMIT_SCRIPT = Path(__file__).with_name("_ballot_emit.py")

PG_URL = os.environ.get("AUDIT_IT_PG_URL", "")
AMQP_URL = os.environ.get("AUDIT_IT_AMQP_URL", "")
ALLOW_BROKER_RESTART = os.environ.get("AUDIT_IT_ALLOW_BROKER_RESTART") == "1"

JWT_SECRET = "it-jwt-secret-must-be-at-least-32-chars-long!"
CHECKPOINT_KEY = "it-checkpoint-key-must-be-at-least-32-chars!"


def _infra_reason() -> str | None:
    if not PG_URL or not AMQP_URL:
        return "AUDIT_IT_PG_URL / AUDIT_IT_AMQP_URL not set"
    try:
        import psycopg2

        psycopg2.connect(PG_URL, connect_timeout=2).close()
    except Exception as exc:
        return f"PostgreSQL unreachable ({type(exc).__name__})"
    parsed = urlparse(AMQP_URL)
    try:
        socket.create_connection((parsed.hostname, parsed.port or 5672), timeout=2).close()
    except OSError as exc:
        return f"RabbitMQ unreachable ({type(exc).__name__})"
    return None


_SKIP = _infra_reason()
pytestmark = [
    pytest.mark.skipif(_SKIP is not None, reason=_SKIP or ""),
    pytest.mark.asyncio,
]

SENSITIVE_PAYLOAD = {
    "candidate_id": "11111111-2222-4333-8444-555555555555",
    "eligibility_ref": "ab" * 32,
    "email": "pemilih@example.test",
    "user_id": "99999999-8888-4777-8666-555555555555",
    "receipt_code": "VG-LEAK-LEAK-LEAK-LEAK",
}


# ══════════════════════════════════════════════════════════════
# Infrastructure helpers
# ══════════════════════════════════════════════════════════════
def _pg_url(database: str, driver: str):
    from sqlalchemy.engine import make_url

    return make_url(PG_URL).set(database=database, drivername=driver)


def _pg_admin(sql: str) -> None:
    import psycopg2

    conn = psycopg2.connect(PG_URL)
    conn.autocommit = True
    try:
        conn.cursor().execute(sql)
    finally:
        conn.close()


def _pg_exec(database: str, sql: str, params: tuple = ()) -> list[tuple]:
    """Autocommit statement against a test database (used to tamper with data)."""
    import psycopg2

    url = _pg_url(database, "postgresql").render_as_string(hide_password=False)
    conn = psycopg2.connect(url)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else []
    finally:
        conn.close()


def _alembic_upgrade(service_dir: Path, env_extra: dict) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=service_dir,
        env={**os.environ, **env_extra},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]


def _purge_app_modules() -> None:
    for name in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[name]


@pytest.fixture(scope="module")
def audit():
    """Import audit-service's `app` package, then remove it again so other test
    modules (ballot-service also has a package called `app`) are unaffected."""
    os.environ["AUDIT_DATABASE_URL"] = _pg_url("unused", "postgresql+asyncpg").render_as_string(hide_password=False)
    os.environ["JWT_SECRET"] = JWT_SECRET
    os.environ["AUDIT_CHECKPOINT_KEY"] = CHECKPOINT_KEY
    os.environ["RABBITMQ_URL"] = ""  # the app under test must not start its own consumer
    _purge_app_modules()
    sys.path.insert(0, str(AUDIT_DIR))
    from app import consumer as consumer_mod
    from app import main as main_mod
    from app.core import config as config_mod
    from app.core import security as security_mod
    from app.infrastructure import database as database_mod
    from app.infrastructure import models as models_mod
    from app.services import chain as chain_mod

    yield types.SimpleNamespace(
        consumer=consumer_mod,
        main=main_mod,
        config=config_mod,
        security=security_mod,
        database=database_mod,
        models=models_mod,
        chain=chain_mod,
    )
    sys.path.remove(str(AUDIT_DIR))
    _purge_app_modules()


@pytest.fixture(scope="module")
def audit_template():
    """Empty database migrated once with the REAL alembic migration; tests clone it."""
    name = f"audit_it_tpl_{uuid.uuid4().hex[:10]}"
    _pg_admin(f'CREATE DATABASE "{name}"')
    sync = _pg_url(name, "postgresql+psycopg2").render_as_string(hide_password=False)
    _alembic_upgrade(AUDIT_DIR, {"AUDIT_DATABASE_URL_SYNC": sync})
    yield name
    _pg_admin(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(scope="module")
def ballot_db():
    name = f"ballot_it_{uuid.uuid4().hex[:10]}"
    _pg_admin(f'CREATE DATABASE "{name}"')
    urls = {
        "BALLOT_DB_NAME": name,
        "BALLOT_DATABASE_URL": _pg_url(name, "postgresql+asyncpg").render_as_string(hide_password=False),
        "BALLOT_DATABASE_URL_SYNC": _pg_url(name, "postgresql+psycopg2").render_as_string(hide_password=False),
    }
    _alembic_upgrade(BALLOT_DIR, urls)
    yield urls
    _pg_admin(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


class Env:
    def __init__(self, audit, name, engine, sf):
        self.audit = audit
        self.db_name = name
        self.engine = engine
        self.sf = sf
        tag = uuid.uuid4().hex[:10]
        self.exchange = f"vg.it.{tag}"
        self.queue = f"audit.it.{tag}"

    @property
    def dlq(self) -> str:
        return f"{self.queue}.dlq"

    def sql(self, sql: str, params: tuple = ()) -> list[tuple]:
        return _pg_exec(self.db_name, sql, params)

    async def scalar(self, sql: str, **params):
        from sqlalchemy import text

        async with self.sf() as s:
            return (await s.execute(text(sql), params)).scalar_one()


@pytest_asyncio.fixture
async def env(audit, audit_template):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    name = f"audit_it_{uuid.uuid4().hex[:12]}"
    _pg_admin(f'CREATE DATABASE "{name}" TEMPLATE "{audit_template}"')
    engine = create_async_engine(
        _pg_url(name, "postgresql+asyncpg").render_as_string(hide_password=False), pool_size=10
    )
    e = Env(audit, name, engine, async_sessionmaker(engine, expire_on_commit=False))
    yield e
    await engine.dispose()
    _pg_admin(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    await _cleanup_broker(e)


async def _cleanup_broker(e: Env) -> None:
    import aio_pika

    with contextlib.suppress(Exception):
        conn = await aio_pika.connect_robust(AMQP_URL)
        async with conn:
            ch = await conn.channel()
            for q in [e.queue, e.dlq, *[f"{e.queue}.retry.{ms}ms" for ms in (100, 200, 5000, 30000, 120000)]]:
                with contextlib.suppress(Exception):
                    await ch.queue_delete(q)
            with contextlib.suppress(Exception):
                await ch.exchange_delete(e.exchange)


async def wait_for(predicate, timeout: float = 20.0, interval: float = 0.1):
    deadline = time.monotonic() + timeout
    while True:
        result = await predicate()
        if result:
            return result
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting for condition")
        await asyncio.sleep(interval)


async def start_consumer(env: Env, *, delays=(200, 200, 200), session_factory=None):
    consumer = env.audit.consumer.AuditConsumer(
        url=AMQP_URL,
        session_factory=session_factory or env.sf,
        exchange=env.exchange,
        queue=env.queue,
        prefetch=1,
        retry_delays_ms=delays,
    )
    task = asyncio.create_task(consumer.run())

    async def ready():
        return consumer.ready

    await wait_for(ready, timeout=30)
    return consumer, task


async def stop_consumer(task: asyncio.Task) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def envelope(election_id=None, *, event_id=None, extra_payload=None, **override) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    body = {
        "event_id": str(event_id or uuid.uuid4()),
        "event_type": "VoteAccepted",
        "schema_version": "1.0",
        "occurred_at": now,
        "producer": "ballot-service",
        "correlation_id": str(uuid.uuid4()),
        "payload": {
            "election_id": str(election_id or uuid.uuid4()),
            "ballot_id": str(uuid.uuid4()),
            "receipt_id": str(uuid.uuid4()),
            "accepted_at": now,
            "ballot_commitment": uuid.uuid4().hex + uuid.uuid4().hex,
            **(extra_payload or {}),
        },
    }
    body.update(override)
    return body


async def publish_raw(env: Env, body: bytes | dict, routing_key: str = "vote.accepted") -> None:
    import aio_pika

    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    conn = await aio_pika.connect_robust(AMQP_URL)
    async with conn:
        ch = await conn.channel(publisher_confirms=True)
        ex = await ch.declare_exchange(env.exchange, aio_pika.ExchangeType.TOPIC, durable=True)
        await ex.publish(
            aio_pika.Message(data, delivery_mode=aio_pika.DeliveryMode.PERSISTENT, content_type="application/json"),
            routing_key=routing_key,
        )


async def get_one(queue_name: str, timeout: float = 15.0):
    """Take one message from a queue (acks it). Returns (headers, body) or None."""
    import aio_pika

    conn = await aio_pika.connect_robust(AMQP_URL)
    async with conn:
        ch = await conn.channel()
        q = await ch.declare_queue(queue_name, durable=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = await q.get(fail=False, timeout=2)
            if msg is not None:
                await msg.ack()
                return dict(msg.headers or {}), msg.body
            await asyncio.sleep(0.2)
    return None


def emit_real_vote(ballot_db: dict, env: Env, election_id: uuid.UUID | None = None, *, relay_only=False) -> dict:
    """Cast a vote through ballot-service's real code and publish its real outbox."""
    result = subprocess.run(
        [sys.executable, str(EMIT_SCRIPT)],
        cwd=BALLOT_DIR,
        env={
            **os.environ,
            **ballot_db,
            "PYTHONPATH": str(BALLOT_DIR),
            "JWT_SECRET": "ballot-jwt-secret-must-be-at-least-32-chars!",
            "VOTE_TICKET_SECRET": "ballot-ticket-secret-must-be-32-chars!!",
            "RECEIPT_HMAC_KEY": "ballot-receipt-key-must-be-at-least-32-chars",
            "RABBITMQ_URL": AMQP_URL,
            "EMIT_ELECTION_ID": str(election_id or uuid.uuid4()),
            "EMIT_EXCHANGE": env.exchange,
            **({"EMIT_RELAY_ONLY": "1"} if relay_only else {}),
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


async def record(env: Env, election_id: uuid.UUID, n: int, *, payload_extra: dict | None = None):
    """Append n events directly through record_event (real DB, no broker)."""
    results = []
    for i in range(n):
        results.append(
            await env.audit.chain.record_event(
                env.sf,
                consumer="it",
                source_event_id=uuid.uuid4(),
                source_event_type="VoteAccepted",
                scope_id=election_id,
                occurred_at=datetime.now(timezone.utc),
                correlation_id=uuid.uuid4(),
                payload_public={"election_id": str(election_id), "n": i, **(payload_extra or {})},
            )
        )
    return results


async def verify(env: Env, election_id: uuid.UUID):
    async with env.sf() as s:
        return await env.audit.chain.verify_chain(s, election_id)


def disable_immutability(env: Env) -> None:
    env.sql("ALTER TABLE audit_events DISABLE TRIGGER trg_audit_events_immutable")


# ══════════════════════════════════════════════════════════════
# 1. Migration
# ══════════════════════════════════════════════════════════════
async def test_01_migration_applies_to_empty_database(audit):
    name = f"audit_it_mig_{uuid.uuid4().hex[:10]}"
    _pg_admin(f'CREATE DATABASE "{name}"')
    try:
        sync = _pg_url(name, "postgresql+psycopg2").render_as_string(hide_password=False)
        _alembic_upgrade(AUDIT_DIR, {"AUDIT_DATABASE_URL_SYNC": sync})
        tables = {r[0] for r in _pg_exec(name, "select tablename from pg_tables where schemaname='public'")}
        assert {
            "audit_events", "audit_chain_heads", "audit_checkpoints",
            "integrity_checks", "outbox_events", "processed_events",
        } <= tables
        triggers = {r[0] for r in _pg_exec(name, "select tgname from pg_trigger where not tgisinternal")}
        assert {"trg_audit_events_immutable", "trg_audit_events_no_truncate"} <= triggers
    finally:
        _pg_admin(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


async def test_01b_audit_events_reject_update_delete_truncate(env):
    election = uuid.uuid4()
    await record(env, election, 2)
    import psycopg2

    for stmt in (
        "UPDATE audit_events SET payload_public = '{}'::jsonb",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ):
        with pytest.raises(psycopg2.Error, match="append-only"):
            env.sql(stmt)
    assert await env.scalar("select count(*) from audit_events") == 2


# ══════════════════════════════════════════════════════════════
# 2. Real VoteAccepted from ballot-service through RabbitMQ
# ══════════════════════════════════════════════════════════════
async def test_02_real_ballot_event_is_consumed_and_chained(env, ballot_db):
    consumer, task = await start_consumer(env)
    try:
        election = uuid.uuid4()
        emitted = await asyncio.to_thread(emit_real_vote, ballot_db, env, election)
        assert emitted["published"] == 1  # ballot side: published to the broker

        async def stored():
            return await env.scalar("select count(*) from audit_events") == 1

        await wait_for(stored)  # audit side: consumed AND committed to the chain

        rows = env.sql(
            "select source_event_id, scope_id, sequence, payload_public::text, prev_hash from audit_events"
        )
        source_id, scope, sequence, payload_text, prev_hash = rows[0]
        payload = json.loads(payload_text)
        assert str(source_id) == emitted["event_id"]
        assert str(scope) == str(election) and sequence == 1 and prev_hash == "0" * 64
        assert payload["ballot_id"] == emitted["ballot_id"]
        assert payload["receipt_id"] == emitted["receipt_id"]
        assert payload["ballot_commitment"] == emitted["ballot_commitment"]
        assert set(payload) == {"election_id", "ballot_id", "receipt_id", "accepted_at", "ballot_commitment"}
        # Privacy: nothing identifying or secret was persisted anywhere in audit_db.
        dump = json.dumps(env.sql("select * from audit_events"), default=str)
        for secret in (emitted["candidate_id"], emitted["eligibility_ref"], emitted["receipt_code"]):
            assert secret not in dump
        assert (await verify(env, election)).status == "VALID"
    finally:
        await stop_consumer(task)


async def test_02b_event_published_before_audit_queue_exists_is_not_lost(env, ballot_db):
    """No queue bound yet → broker would silently drop it. Ballot must keep it PENDING and retry."""
    election = uuid.uuid4()
    first = await asyncio.to_thread(emit_real_vote, ballot_db, env, election)
    assert first["published"] == 0  # unroutable ≠ published
    status, attempts, error = _pg_exec(
        ballot_db["BALLOT_DB_NAME"],
        "select status, attempts, last_error from outbox_events where id = %s",
        (first["event_id"],),
    )[0]
    assert (status, attempts) == ("PENDING", 1) and "no queue bound" in (error or "")

    consumer, task = await start_consumer(env)  # queue is now declared and bound
    try:
        await asyncio.sleep(3)  # outbox backoff after 1st failure is 2 s
        retry = await asyncio.to_thread(emit_real_vote, ballot_db, env, relay_only=True)
        assert retry["published"] >= 1

        async def stored():
            return await env.scalar(
                "select count(*) from audit_events where source_event_id = :i", i=uuid.UUID(first["event_id"])
            ) == 1

        await wait_for(stored)  # published → consumed → stored, each observed separately
    finally:
        await stop_consumer(task)


# ══════════════════════════════════════════════════════════════
# 3. Duplicates
# ══════════════════════════════════════════════════════════════
async def test_03_duplicate_event_creates_one_record(env):
    consumer, task = await start_consumer(env)
    try:
        election = uuid.uuid4()
        dup = envelope(election)
        for _ in range(5):
            await publish_raw(env, dup)
        sentinel = envelope(election)  # prefetch=1 → handled after all five duplicates
        await publish_raw(env, sentinel)

        async def sentinel_done():
            return await env.scalar(
                "select count(*) from audit_events where source_event_id = :i", i=uuid.UUID(sentinel["event_id"])
            ) == 1

        await wait_for(sentinel_done)
        assert await env.scalar(
            "select count(*) from audit_events where source_event_id = :i", i=uuid.UUID(dup["event_id"])
        ) == 1
        assert await env.scalar("select count(*) from audit_events") == 2
        assert await env.scalar("select last_sequence from audit_chain_heads") == 2
        assert (await verify(env, election)).status == "VALID"
    finally:
        await stop_consumer(task)


# ══════════════════════════════════════════════════════════════
# 4 + 5. Chain of several events verifies
# ══════════════════════════════════════════════════════════════
async def test_04_05_two_events_form_a_valid_chain(env):
    consumer, task = await start_consumer(env)
    try:
        election = uuid.uuid4()
        await publish_raw(env, envelope(election))
        await publish_raw(env, envelope(election))

        async def two():
            return await env.scalar("select count(*) from audit_events") == 2

        await wait_for(two)
        rows = env.sql("select sequence, prev_hash, event_hash from audit_events order by sequence")
        assert [r[0] for r in rows] == [1, 2]
        assert rows[0][1] == "0" * 64 and rows[1][1] == rows[0][2]
        outcome = await verify(env, election)
        assert outcome.status == "VALID" and outcome.events_checked == 2 and outcome.first_failure is None
        assert outcome.head_hash == rows[1][2]
        # the check itself is recorded without sensitive detail
        assert env.sql("select status, failure_reason from integrity_checks") == [("VALID", None)]
    finally:
        await stop_consumer(task)


# ══════════════════════════════════════════════════════════════
# 6. Tampering is detected (test database only)
# ══════════════════════════════════════════════════════════════
async def _chain_of_ten(env: Env) -> uuid.UUID:
    election = uuid.uuid4()
    await record(env, election, 10)
    assert (await verify(env, election)).status == "VALID"
    disable_immutability(env)
    return election


async def test_06a_modified_payload_detected(env):
    election = await _chain_of_ten(env)
    env.sql("UPDATE audit_events SET payload_public = jsonb_set(payload_public, '{n}', '999') WHERE sequence = 5")
    out = await verify(env, election)
    assert out.status == "INVALID" and out.first_failure == {"sequence": 5, "reason": "EVENT_HASH_MISMATCH"}


async def test_06b_modified_hash_detected(env):
    election = await _chain_of_ten(env)
    env.sql("UPDATE audit_events SET event_hash = repeat('a', 64) WHERE sequence = 5")
    out = await verify(env, election)
    assert out.status == "INVALID" and out.first_failure["sequence"] == 5


async def test_06c_deleted_middle_event_detected(env):
    election = await _chain_of_ten(env)
    env.sql("DELETE FROM audit_events WHERE sequence = 4")
    out = await verify(env, election)
    assert out.status == "INVALID" and out.first_failure == {"sequence": 4, "reason": "SEQUENCE_GAP"}


async def test_06d_reordered_events_detected(env):
    election = await _chain_of_ten(env)
    env.sql("UPDATE audit_events SET sequence = 99 WHERE sequence = 3")
    env.sql("UPDATE audit_events SET sequence = 3 WHERE sequence = 4")
    env.sql("UPDATE audit_events SET sequence = 4 WHERE sequence = 99")
    out = await verify(env, election)
    assert out.status == "INVALID" and out.first_failure["sequence"] == 3


async def test_06e_inserted_forged_event_detected(env):
    election = await _chain_of_ten(env)
    env.sql(
        "INSERT INTO audit_events (scope_id, sequence, source_event_id, source_event_type, occurred_at, "
        "correlation_id, payload_public, prev_hash, event_hash) VALUES (%s, 11, gen_random_uuid(), "
        "'VoteAccepted', now(), gen_random_uuid(), '{}'::jsonb, repeat('b', 64), repeat('c', 64))",
        (str(election),),
    )
    out = await verify(env, election)
    assert out.status == "INVALID" and out.first_failure["sequence"] == 11


async def test_06f_truncated_tail_detected_by_head(env):
    election = await _chain_of_ten(env)
    env.sql("DELETE FROM audit_events WHERE sequence = 10")
    out = await verify(env, election)
    assert out.status == "INVALID" and out.first_failure["reason"] == "HEAD_MISMATCH"


async def _checkpoint_at(env: Env, election: uuid.UUID, sequence: int) -> None:
    (event_hash,) = env.sql(
        "select event_hash from audit_events where scope_id = %s and sequence = %s", (str(election), sequence)
    )[0]
    mac = env.audit.security.compute_checkpoint_hmac(election, sequence, event_hash, "MANUAL")
    env.sql(
        "INSERT INTO audit_checkpoints (scope_id, sequence, event_hash, reason, exported_path, hmac) "
        "VALUES (%s, %s, %s, 'MANUAL', '/test', %s)",
        (str(election), sequence, event_hash, mac),
    )


async def test_06g_truncation_with_repaired_head_caught_by_checkpoint(env):
    election = uuid.uuid4()
    await record(env, election, 10)
    await _checkpoint_at(env, election, 10)
    assert (await verify(env, election)).checkpoint == {"compared": True, "matches": True, "checkpoint_sequence": 10}
    disable_immutability(env)
    env.sql("DELETE FROM audit_events WHERE sequence = 10")
    (h9,) = env.sql("select event_hash from audit_events where sequence = 9")[0]
    env.sql("UPDATE audit_chain_heads SET last_sequence = 9, last_hash = %s", (h9,))  # attacker fixes the head
    out = await verify(env, election)
    assert out.status == "INVALID" and out.first_failure == {"sequence": 10, "reason": "CHECKPOINT_MISMATCH"}


async def _rebuild_chain(env: Env, election: uuid.UUID) -> None:
    """What an attacker with full write access to audit_db (but not the HMAC key) can do."""
    sec = env.audit.security
    rows = env.sql(
        "select sequence, source_event_id, source_event_type, occurred_at, correlation_id, payload_public "
        "from audit_events where scope_id = %s order by sequence",
        (str(election),),
    )
    prev = "0" * 64
    for seq, sid, etype, occurred, corr, payload in rows:
        payload = {**payload, "forged": True} if seq == 5 else payload
        new_hash = sec.compute_event_hash(election, seq, sid, etype, occurred, corr, payload, prev)
        env.sql(
            "UPDATE audit_events SET payload_public = %s::jsonb, prev_hash = %s, event_hash = %s WHERE sequence = %s",
            (json.dumps(payload), prev, new_hash, seq),
        )
        prev = new_hash
    env.sql("UPDATE audit_chain_heads SET last_hash = %s", (prev,))


async def test_06h_full_rebuild_is_caught_only_with_a_checkpoint(env):
    # Honest limit (SAD §12): with no checkpoint, a consistent rebuild is undetectable.
    election = await _chain_of_ten(env)
    await _rebuild_chain(env, election)
    assert (await verify(env, election)).status == "VALID"

    # With an HMAC checkpoint made before the attack, the rebuild no longer matches.
    election2 = uuid.uuid4()
    await record(env, election2, 10)
    await _checkpoint_at(env, election2, 10)
    await _rebuild_chain(env, election2)
    out = await verify(env, election2)
    assert out.status == "INVALID" and out.first_failure["reason"] == "CHECKPOINT_MISMATCH"


async def test_06i_forged_checkpoint_without_key_is_rejected(env):
    election = uuid.uuid4()
    await record(env, election, 3)
    (h,) = env.sql("select event_hash from audit_events where sequence = 3")[0]
    env.sql(
        "INSERT INTO audit_checkpoints (scope_id, sequence, event_hash, reason, exported_path, hmac) "
        "VALUES (%s, 3, %s, 'MANUAL', '/x', repeat('0', 64))",
        (str(election), h),
    )
    out = await verify(env, election)
    assert out.status == "INVALID" and out.first_failure["reason"] == "CHECKPOINT_MISMATCH"


# ══════════════════════════════════════════════════════════════
# 7. Failed transaction leaves nothing behind
# ══════════════════════════════════════════════════════════════
async def test_07_failed_transaction_leaves_chain_consistent(env):
    election = uuid.uuid4()
    await record(env, election, 2)
    head_before = env.sql("select last_sequence, last_hash from audit_chain_heads")
    source_id = uuid.uuid4()
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        # PostgreSQL jsonb rejects \u0000, so the audit_events INSERT fails after the
        # dedup row and the head lock were already taken in the same transaction.
        await env.audit.chain.record_event(
            env.sf,
            consumer="it",
            source_event_id=source_id,
            source_event_type="VoteAccepted",
            scope_id=election,
            occurred_at=datetime.now(timezone.utc),
            correlation_id=uuid.uuid4(),
            payload_public={"bad": "x\u0000y"},
        )
    assert env.sql("select last_sequence, last_hash from audit_chain_heads") == head_before
    assert env.sql("select count(*) from processed_events where event_id = %s", (str(source_id),)) == [(0,)]
    assert env.sql("select count(*) from audit_events") == [(2,)]
    # the same source event can still be recorded later, with the next sequence
    result = await env.audit.chain.record_event(
        env.sf,
        consumer="it",
        source_event_id=source_id,
        source_event_type="VoteAccepted",
        scope_id=election,
        occurred_at=datetime.now(timezone.utc),
        correlation_id=uuid.uuid4(),
        payload_public={"ok": True},
    )
    assert result.status == "RECORDED" and result.sequence == 3
    assert (await verify(env, election)).status == "VALID"


# ══════════════════════════════════════════════════════════════
# 8. Concurrency
# ══════════════════════════════════════════════════════════════
async def test_08_concurrent_appends_keep_one_linear_chain(env):
    scope_a, scope_b = uuid.uuid4(), uuid.uuid4()
    shared = uuid.uuid4()  # one source event delivered concurrently many times

    def one(scope, source=None):
        return env.audit.chain.record_event(
            env.sf,
            consumer="it",
            source_event_id=source or uuid.uuid4(),
            source_event_type="VoteAccepted",
            scope_id=scope,
            occurred_at=datetime.now(timezone.utc),
            correlation_id=uuid.uuid4(),
            payload_public={"election_id": str(scope)},
        )

    jobs = [one(scope_a) for _ in range(30)] + [one(scope_b) for _ in range(10)] + [one(scope_a, shared) for _ in range(8)]
    results = await asyncio.gather(*jobs)

    assert sum(r.status == "DUPLICATE" for r in results) == 7  # 8 deliveries of `shared` → 1 recorded
    for scope, expected in ((scope_a, 31), (scope_b, 10)):
        seqs = [r[0] for r in env.sql("select sequence from audit_events where scope_id = %s order by sequence", (str(scope),))]
        assert seqs == list(range(1, expected + 1))
        out = await verify(env, scope)
        assert out.status == "VALID" and out.events_checked == expected and out.head_sequence == expected


# ══════════════════════════════════════════════════════════════
# 9. Restart
# ══════════════════════════════════════════════════════════════
async def test_09_events_published_while_down_are_processed_after_restart(env):
    _, task = await start_consumer(env)  # declares durable queue + bindings
    await stop_consumer(task)
    election = uuid.uuid4()
    for _ in range(3):
        await publish_raw(env, envelope(election))  # consumer is down; broker holds them
    assert await env.scalar("select count(*) from audit_events") == 0

    _, task = await start_consumer(env)
    try:
        async def three():
            return await env.scalar("select count(*) from audit_events") == 3

        await wait_for(three)
        assert (await verify(env, election)).status == "VALID"
    finally:
        await stop_consumer(task)


async def test_09b_crash_before_ack_redelivers_without_duplicate(env):
    import aio_pika

    _, task = await start_consumer(env)
    await stop_consumer(task)
    election = uuid.uuid4()
    msg = envelope(election)
    await publish_raw(env, msg)

    # A worker receives the message and dies before acking it (CC-05).
    conn = await aio_pika.connect_robust(AMQP_URL)
    ch = await conn.channel()
    q = await ch.declare_queue(env.queue, durable=True)
    got = await q.get(timeout=10)
    assert got is not None
    await conn.close()  # no ack

    _, task = await start_consumer(env)
    try:
        async def one():
            return await env.scalar("select count(*) from audit_events") == 1

        await wait_for(one)
        await asyncio.sleep(0.5)
        assert await env.scalar("select count(*) from audit_events") == 1
    finally:
        await stop_consumer(task)


# ══════════════════════════════════════════════════════════════
# 10. Malformed events
# ══════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "label,body,reason",
    [
        ("garbage", b"this is not json", "MALFORMED_JSON"),
        ("legacy_field", None, "INVALID_ENVELOPE"),
        ("bad_payload", None, "INVALID_PAYLOAD"),
        ("future_major", None, "UNSUPPORTED_SCHEMA_VERSION"),
    ],
)
async def test_10_malformed_event_is_dead_lettered_not_recorded(env, label, body, reason):
    if label == "legacy_field":
        legacy = envelope()
        legacy["source_service"] = legacy.pop("producer")
        body = json.dumps(legacy).encode()
    elif label == "bad_payload":
        bad = envelope()
        del bad["payload"]["ballot_commitment"]
        body = json.dumps(bad).encode()
    elif label == "future_major":
        body = json.dumps(envelope(schema_version="2.0")).encode()

    _, task = await start_consumer(env)
    try:
        await publish_raw(env, body)
        got = await get_one(env.dlq)
        assert got is not None, "malformed message was lost instead of dead-lettered"
        headers, dead_body = got
        assert headers["x-vg-failure"] == reason
        assert dead_body == body  # preserved verbatim for manual inspection / replay
        assert await env.scalar("select count(*) from audit_events") == 0
        assert await env.scalar("select count(*) from processed_events") == 0
        # and the work queue is not stuck on it
        follow = envelope()
        await publish_raw(env, follow)

        async def processed():
            return await env.scalar("select count(*) from audit_events") == 1

        await wait_for(processed)
    finally:
        await stop_consumer(task)


# ══════════════════════════════════════════════════════════════
# 11. Public endpoints leak nothing
# ══════════════════════════════════════════════════════════════
def _token(audit, role: str) -> str:
    import jwt

    now = int(time.time())
    return jwt.encode(
        {"sub": str(uuid.uuid4()), "email": "x@y.z", "role": role, "iat": now, "exp": now + 300, "jti": uuid.uuid4().hex},
        audit.config.settings.JWT_SECRET,
        algorithm="HS256",
    )


async def test_11_endpoints_expose_no_sensitive_data(env):
    from httpx import ASGITransport, AsyncClient

    audit = env.audit
    consumer, task = await start_consumer(env)
    election = uuid.uuid4()
    first = envelope(election, extra_payload=SENSITIVE_PAYLOAD)
    try:
        await publish_raw(env, first)
        await publish_raw(env, envelope(election, extra_payload=SENSITIVE_PAYLOAD))

        async def two():
            return await env.scalar("select count(*) from audit_events") == 2

        await wait_for(two)
    finally:
        await stop_consumer(task)

    async def override():
        async with env.sf() as session:
            yield session

    audit.main.app.dependency_overrides[audit.database.get_session] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=audit.main.app), base_url="http://t") as client:
            admin = {"Authorization": f"Bearer {_token(audit, 'ADMIN')}"}
            voter = {"Authorization": f"Bearer {_token(audit, 'VOTER')}"}
            receipt = first["payload"]["receipt_id"]

            events = await client.get("/api/v1/audit/events", params={"election_id": str(election)}, headers=admin)
            verify_resp = await client.get(f"/api/v1/audit/elections/{election}/verify", headers=admin)
            proof = await client.get(f"/api/v1/audit/elections/{election}/proof", params={"receipt_id": receipt}, headers=voter)
            proof_none = await client.get(f"/api/v1/audit/elections/{election}/proof", headers=voter)
            missing = await client.get(f"/api/v1/audit/elections/{uuid.uuid4()}/proof", headers=voter)
            missing_verify = await client.get(f"/api/v1/audit/elections/{uuid.uuid4()}/verify", headers=admin)
            forbidden = await client.get("/api/v1/audit/events", headers=voter)

        assert (events.status_code, verify_resp.status_code, proof.status_code, proof_none.status_code) == (200, 200, 200, 200)
        assert missing.status_code == 404 and missing_verify.status_code == 404 and forbidden.status_code == 403
        assert missing.json()["error"]["code"] == "NOT_FOUND"

        everything = "".join(r.text for r in (events, verify_resp, proof, proof_none, missing, forbidden))
        for value in SENSITIVE_PAYLOAD.values():
            assert value not in everything
        for key in ("candidate_id", "eligibility_ref", "email", "user_id", "receipt_code", "nonce"):
            assert key not in everything

        # Contract shapes (API_CONTRACTS B.4)
        body = events.json()
        assert body["page"] == {"page": 1, "page_size": 20, "total": 2}
        assert set(body["items"][0]) == {
            "id", "scope_id", "sequence", "source_event_id", "source_event_type", "occurred_at",
            "recorded_at", "payload_public", "prev_hash", "event_hash",
        }
        assert set(body["items"][0]["payload_public"]) == {
            "election_id", "ballot_id", "receipt_id", "accepted_at", "ballot_commitment",
        }
        assert verify_resp.json()["status"] == "VALID" and verify_resp.json()["first_failure"] is None
        p = proof.json()
        assert p["hash_algorithm"] == "SHA-256" and p["event_count"] == 2 and p["head_sequence"] == 2
        assert p["last_verified"]["status"] == "VALID"  # verify ran earlier in this test
        assert p["receipt_event"]["sequence"] == 1
        assert set(p["receipt_event"]) == {"sequence", "prev_hash", "event_hash"}
        assert proof_none.json()["receipt_event"] is None

        # an unknown receipt is simply "not recorded", never an error that confirms/denies anything else
        async with AsyncClient(transport=ASGITransport(app=audit.main.app), base_url="http://t") as client:
            other = await client.get(
                f"/api/v1/audit/elections/{election}/proof", params={"receipt_id": str(uuid.uuid4())}, headers=voter
            )
        assert other.status_code == 200 and other.json()["receipt_event"] is None

        # tampered chain is reported in the body, not as an HTTP error (Contract #18)
        disable_immutability(env)
        env.sql("UPDATE audit_events SET payload_public = '{}'::jsonb WHERE sequence = 2")
        async with AsyncClient(transport=ASGITransport(app=audit.main.app), base_url="http://t") as client:
            bad = await client.get(f"/api/v1/audit/elections/{election}/verify", headers=admin)
        assert bad.status_code == 200
        assert bad.json()["status"] == "INVALID"
        assert bad.json()["first_failure"] == {"sequence": 2, "reason": "EVENT_HASH_MISMATCH"}
    finally:
        audit.main.app.dependency_overrides.clear()


async def test_11b_events_endpoint_page_size_is_bounded(env):
    from httpx import ASGITransport, AsyncClient

    audit = env.audit
    election = uuid.uuid4()
    await record(env, election, 5)

    async def override():
        async with env.sf() as session:
            yield session

    audit.main.app.dependency_overrides[audit.database.get_session] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=audit.main.app), base_url="http://t") as client:
            h = {"Authorization": f"Bearer {_token(audit, 'AUDITOR')}"}
            ok = await client.get("/api/v1/audit/events", params={"election_id": str(election), "page_size": 2, "page": 3, "order": "desc"}, headers=h)
            too_big = await client.get("/api/v1/audit/events", params={"page_size": 1000}, headers=h)
        assert too_big.status_code == 422
        assert [i["sequence"] for i in ok.json()["items"]] == [1] and ok.json()["page"]["total"] == 5
    finally:
        audit.main.app.dependency_overrides.clear()


# ══════════════════════════════════════════════════════════════
# 12. Retry policy: database failure and broker failure
# ══════════════════════════════════════════════════════════════
class FlakySessionFactory:
    """Real session factory that fails the first `failures` calls like a database outage."""

    def __init__(self, real, failures: int):
        self.real = real
        self.failures = failures
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.failures > 0:
            self.failures -= 1
            from sqlalchemy.exc import OperationalError

            raise OperationalError("INSERT", {}, ConnectionRefusedError("database down"))
        return self.real()


async def test_12a_database_failure_is_retried_then_recorded(env):
    flaky = FlakySessionFactory(env.sf, failures=2)
    _, task = await start_consumer(env, session_factory=flaky)
    try:
        election = uuid.uuid4()
        await publish_raw(env, envelope(election))

        async def recorded():
            return await env.scalar("select count(*) from audit_events") == 1

        await wait_for(recorded, timeout=30)
        assert flaky.calls == 3  # two failures went through retry tiers, third succeeded
        assert await env.scalar("select count(*) from processed_events") == 1
        assert (await get_one(env.dlq, timeout=1)) is None  # nothing was dead-lettered
    finally:
        await stop_consumer(task)


async def test_12b_persistent_database_failure_ends_in_dlq_after_tiers(env):
    flaky = FlakySessionFactory(env.sf, failures=10_000)
    _, task = await start_consumer(env, session_factory=flaky, delays=(200, 200, 200))
    try:
        body = json.dumps(envelope()).encode()
        await publish_raw(env, body)
        got = await get_one(env.dlq, timeout=30)
        assert got is not None, "event lost after retries were exhausted"
        headers, dead_body = got
        assert headers["x-vg-failure"] == "RETRIES_EXHAUSTED" and headers["x-vg-retry"] == 3
        assert dead_body == body
        assert flaky.calls == 4  # initial attempt + 3 retry tiers
        assert await env.scalar("select count(*) from audit_events") == 0
    finally:
        await stop_consumer(task)


async def test_12c_dead_lettered_event_can_be_replayed_safely(env):
    flaky = FlakySessionFactory(env.sf, failures=10_000)
    consumer, task = await start_consumer(env, session_factory=flaky, delays=(100, 100, 100))
    body = json.dumps(envelope()).encode()
    try:
        await publish_raw(env, body)
        got = await get_one(env.dlq, timeout=30)
        assert got is not None
    finally:
        await stop_consumer(task)
    _, task = await start_consumer(env)  # database healthy again
    try:
        await publish_raw(env, body)  # operator replays the dead letter (twice, to prove idempotence)
        await publish_raw(env, body)

        async def one():
            return await env.scalar("select count(*) from audit_events") == 1

        await wait_for(one)
        await asyncio.sleep(0.5)
        assert await env.scalar("select count(*) from audit_events") == 1
    finally:
        await stop_consumer(task)


@pytest.mark.skipif(
    not (ALLOW_BROKER_RESTART and shutil.which("rabbitmqctl")),
    reason="set AUDIT_IT_ALLOW_BROKER_RESTART=1 on a disposable broker (needs rabbitmqctl)",
)
async def test_12d_consumer_survives_broker_outage(env):
    consumer, task = await start_consumer(env)
    try:
        await publish_raw(env, envelope())

        async def one():
            return await env.scalar("select count(*) from audit_events") == 1

        await wait_for(one)

        subprocess.run(["rabbitmqctl", "stop_app"], check=True, capture_output=True, timeout=120)

        async def not_ready():
            return not consumer.ready

        await wait_for(not_ready, timeout=30)  # readiness reports the outage

        subprocess.run(["rabbitmqctl", "start_app"], check=True, capture_output=True, timeout=180)

        async def ready_again():
            return consumer.ready

        await wait_for(ready_again, timeout=90)
        await publish_raw(env, envelope())

        async def two():
            return await env.scalar("select count(*) from audit_events") == 2

        await wait_for(two, timeout=30)  # same consumer instance resumed without restart
    finally:
        subprocess.run(["rabbitmqctl", "start_app"], capture_output=True, timeout=180)
        await stop_consumer(task)
