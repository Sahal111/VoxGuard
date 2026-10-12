"""RabbitMQ consumer: ballot-service `VoteAccepted` → audit chain.

Delivery policy (SAD §11.3, API Contract §8.4):
- Message is acked only after the audit transaction committed (or was recognised
  as a duplicate that is already committed).
- Permanent failures (bad JSON, bad envelope/payload, unknown major schema
  version, unexpected producer/type) go straight to `<queue>.dlq`.
- Transient failures go through tiered retry queues (default 5 s, 30 s, 120 s);
  the failure after the last tier goes to the DLQ.
- A message is acked only after its retry/DLQ copy was broker-confirmed. If that
  republish fails the message is nacked back onto the queue — never dropped.
- The DLQ is never consumed automatically; replaying is a manual operation and is
  safe because recording is idempotent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

# pyrefly: ignore [missing-import]
import aio_pika
# pyrefly: ignore [missing-import]
from aio_pika.abc import AbstractIncomingMessage
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, ConfigDict, Field, ValidationError
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import canonical_timestamp, project_payload
from app.services.chain import record_event
# pyrefly: ignore [missing-import]
from voxguard_contracts import EventEnvelope, EventType, Producer

logger = logging.getLogger("audit_service.consumer")

ROUTING_KEY = "vote.accepted"
CONSUMER_NAME = "audit-service.vote-accepted"
SUPPORTED_MAJOR = "1"
RETRY_HEADER = "x-vg-retry"
FAILURE_HEADER = "x-vg-failure"


class PermanentError(Exception):
    """Message can never be processed; goes to the DLQ without retry."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class VoteAcceptedPayload(BaseModel):
    # eligibility_ref etc. are ignored here and never stored (allowlist below).
    model_config = ConfigDict(extra="ignore")

    election_id: uuid.UUID
    ballot_id: uuid.UUID
    receipt_id: uuid.UUID
    accepted_at: datetime
    ballot_commitment: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ParsedEvent:
    source_event_id: uuid.UUID
    source_event_type: str
    scope_id: uuid.UUID
    occurred_at: datetime
    correlation_id: uuid.UUID
    payload_public: dict


def parse_vote_accepted(body: bytes) -> ParsedEvent:
    """Validate raw message bytes into a ParsedEvent or raise PermanentError(reason)."""
    try:
        raw = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise PermanentError("MALFORMED_JSON")
    if not isinstance(raw, dict):
        raise PermanentError("MALFORMED_JSON")
    try:
        envelope = EventEnvelope.model_validate(raw)
    except ValidationError:
        raise PermanentError("INVALID_ENVELOPE")

    if envelope.schema_version.split(".")[0] != SUPPORTED_MAJOR:
        raise PermanentError("UNSUPPORTED_SCHEMA_VERSION")
    if envelope.event_type is not EventType.VOTE_ACCEPTED:
        raise PermanentError("UNEXPECTED_EVENT_TYPE")
    if envelope.producer is not Producer.BALLOT_SERVICE:
        raise PermanentError("UNEXPECTED_PRODUCER")
    if envelope.occurred_at.tzinfo is None:
        raise PermanentError("INVALID_ENVELOPE")
    try:
        payload = VoteAcceptedPayload.model_validate(envelope.payload)
    except ValidationError:
        raise PermanentError("INVALID_PAYLOAD")
    if payload.accepted_at.tzinfo is None:
        raise PermanentError("INVALID_PAYLOAD")

    # Normalised representation (stable UUID/timestamp format) → allowlist projection.
    payload_public = project_payload(
        "VoteAccepted",
        {
            "election_id": str(payload.election_id),
            "ballot_id": str(payload.ballot_id),
            "receipt_id": str(payload.receipt_id),
            "accepted_at": canonical_timestamp(payload.accepted_at),
            "ballot_commitment": payload.ballot_commitment,
        },
    )
    return ParsedEvent(
        source_event_id=envelope.event_id,
        source_event_type=envelope.event_type.value,
        scope_id=payload.election_id,
        occurred_at=envelope.occurred_at.astimezone(timezone.utc),
        correlation_id=envelope.correlation_id,
        payload_public=payload_public,
    )


class AuditConsumer:
    def __init__(
        self,
        *,
        url: str,
        session_factory: async_sessionmaker[AsyncSession],
        exchange: str,
        queue: str,
        prefetch: int = 1,
        retry_delays_ms: Sequence[int] = (5_000, 30_000, 120_000),
    ):
        self._url = url
        self._session_factory = session_factory
        self._exchange_name = exchange
        self._queue_name = queue
        self._prefetch = prefetch
        self._retry_delays = list(retry_delays_ms)
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractRobustChannel | None = None
        self._consuming = False

    # ── Names ────────────────────────────────────────────────
    @property
    def dlq_name(self) -> str:
        return f"{self._queue_name}.dlq"

    def retry_queue_name(self, tier: int) -> str:
        # Delay is part of the name: RabbitMQ refuses to redeclare a queue with a different
        # x-message-ttl (PRECONDITION_FAILED), so changing AUDIT_RETRY_DELAYS_MS must create
        # new queues instead of crash-looping the consumer. Old queues drain via their own TTL.
        return f"{self._queue_name}.retry.{self._retry_delays[tier]}ms"

    @property
    def connected(self) -> bool:
        """Live broker connection. RobustConnection.is_closed stays False while it is
        reconnecting, so look at the underlying transport as well."""
        conn = self._connection
        if conn is None or conn.is_closed or conn.reconnecting:
            return False
        transport = getattr(conn, "transport", None)
        return transport is not None and not transport.connection.is_closed

    @property
    def ready(self) -> bool:
        """Connected AND topology declared AND consuming (what readiness reports)."""
        return self._consuming and self.connected

    # ── Lifecycle ────────────────────────────────────────────
    async def run(self) -> None:
        """Connect (retrying with backoff) and consume until cancelled."""
        backoff = 1.0
        while True:
            try:
                await self._start()
                break
            except asyncio.CancelledError:
                await self.close()
                raise
            except Exception as exc:
                logger.warning(
                    "audit_consumer_connect_failed",
                    extra={"error": type(exc).__name__, "detail": str(exc)[:200], "retry_in_s": backoff},
                )
                await self.close()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
        try:
            # connect_robust re-establishes connection, topology and the consumer itself.
            await asyncio.Future()
        except asyncio.CancelledError:
            await self.close()
            raise

    async def _start(self) -> None:
        self._connection = await aio_pika.connect_robust(self._url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self._prefetch)

        exchange = await self._channel.declare_exchange(
            self._exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
        )
        queue = await self._channel.declare_queue(self._queue_name, durable=True)
        await queue.bind(exchange, routing_key=ROUTING_KEY)
        await self._channel.declare_queue(self.dlq_name, durable=True)
        for tier, delay in enumerate(self._retry_delays):
            await self._channel.declare_queue(
                self.retry_queue_name(tier),
                durable=True,
                arguments={
                    "x-message-ttl": delay,
                    "x-dead-letter-exchange": "",
                    "x-dead-letter-routing-key": self._queue_name,
                },
            )
        await queue.consume(self._on_message)
        self._consuming = True
        logger.info("audit_consumer_started", extra={"queue": self._queue_name})

    async def close(self) -> None:
        self._consuming = False
        try:
            if self._connection is not None and not self._connection.is_closed:
                await self._connection.close()
        except Exception:
            pass
        self._connection = None
        self._channel = None

    # ── Message handling ─────────────────────────────────────
    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        try:
            parsed = parse_vote_accepted(message.body)
        except PermanentError as exc:
            await self._dead_letter(message, exc.reason)
            return
        except Exception:  # never leave an unparseable message unacked (prefetch would stall)
            await self._dead_letter(message, "PARSE_ERROR")
            return

        try:
            result = await record_event(
                self._session_factory,
                consumer=CONSUMER_NAME,
                source_event_id=parsed.source_event_id,
                source_event_type=parsed.source_event_type,
                scope_id=parsed.scope_id,
                occurred_at=parsed.occurred_at,
                correlation_id=parsed.correlation_id,
                payload_public=parsed.payload_public,
            )
        except Exception as exc:
            await self._retry_or_dead_letter(message, type(exc).__name__)
            return

        logger.info(
            "audit_event_processed",
            extra={
                "event_id": str(parsed.source_event_id),
                "status": result.status,
                "sequence": result.sequence,
            },
        )
        # Committed (or already committed earlier) → safe to ack.
        try:
            await message.ack()
        except Exception as exc:  # channel lost: broker redelivers, dedup absorbs it
            logger.warning("audit_ack_failed", extra={"error": type(exc).__name__})

    async def _retry_or_dead_letter(self, message: AbstractIncomingMessage, failure: str) -> None:
        attempt = int((message.headers or {}).get(RETRY_HEADER, 0))
        if attempt < len(self._retry_delays):
            logger.warning(
                "audit_event_retry",
                extra={"failure": failure, "attempt": attempt + 1, "tier": attempt + 1},
            )
            await self._republish_then_ack(
                message, self.retry_queue_name(attempt), attempt + 1, failure
            )
        else:
            await self._dead_letter(message, "RETRIES_EXHAUSTED", attempt=attempt, detail=failure)

    async def _dead_letter(
        self,
        message: AbstractIncomingMessage,
        reason: str,
        *,
        attempt: int | None = None,
        detail: str | None = None,
    ) -> None:
        logger.error(
            "audit_event_dead_lettered",
            extra={"reason": reason, "detail": detail, "message_id": message.message_id},
        )
        if attempt is None:
            attempt = int((message.headers or {}).get(RETRY_HEADER, 0))
        await self._republish_then_ack(message, self.dlq_name, attempt, reason)

    async def _republish_then_ack(
        self, message: AbstractIncomingMessage, queue_name: str, attempt: int, failure: str
    ) -> None:
        headers = dict(message.headers or {})
        headers[RETRY_HEADER] = attempt
        headers[FAILURE_HEADER] = failure  # fixed code / exception class name only
        try:
            await self._channel.default_exchange.publish(
                aio_pika.Message(
                    body=message.body,
                    headers=headers,
                    content_type=message.content_type,
                    message_id=message.message_id,
                    correlation_id=message.correlation_id,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=queue_name,
                mandatory=True,
            )
        except Exception as exc:
            logger.error(
                "audit_republish_failed",
                extra={"queue": queue_name, "error": type(exc).__name__},
            )
            try:
                await message.nack(requeue=True)
            except Exception:
                pass  # channel gone: unacked message returns to the queue by itself
            return
        try:
            await message.ack()
        except Exception as exc:
            logger.warning("audit_ack_failed", extra={"error": type(exc).__name__})
