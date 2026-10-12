"""Outbox publisher for ballot-service.

Implements the Transactional Outbox pattern: reads PENDING events from
outbox_events and publishes to RabbitMQ using aio-pika.

Design principles:
- At-least-once delivery: events may be published more than once if the
  broker ACK arrives but the DB UPDATE fails. Consumers MUST be idempotent.
- No concurrent processing of the same event: SELECT ... FOR UPDATE SKIP LOCKED
  ensures each worker locks different rows.
- Status lifecycle: PENDING → (published + acked) → PUBLISHED
                            → (max retries exceeded) → FAILED
- Events are never deleted; FAILED events require operator action.
- No candidate_id, JWT, receipt_code, or secrets logged.

Event envelope (voxguard-contracts schema):
{
  "event_id":      str(uuid),
  "event_type":    str,
  "schema_version": str,
  "occurred_at":   ISO-8601,
  "correlation_id": str(uuid),
  "producer":      "ballot-service",
  "payload":       {...}   # no candidate_id, no eligibility_ref except for VoteAccepted
}
Envelope and exchange follow API Contract §8.1 / SAD §11.1 (exchange
"voxguard.events", field "producer"); audit-service rejects anything else.

Usage:
  publisher = OutboxPublisher(settings.RABBITMQ_URL)
  await publisher.connect()
  published = await publisher.process_batch(db)   # call periodically
  await publisher.close()

The publisher is wired as a background task in main.py lifespan via asyncio.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

# pyrefly: ignore [missing-import]
from aiormq.abc import DeliveredMessage
# pyrefly: ignore [missing-import]
from sqlalchemy import select, update
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import OutboxEvent

if TYPE_CHECKING:
    pass

logger = logging.getLogger("ballot_service.publisher")

MAX_ATTEMPTS = 5
BATCH_SIZE = 50
POLL_INTERVAL_SECONDS = 5


class UnroutableEventError(Exception):
    """Broker accepted the publish but no queue was bound, so nobody would receive it."""


class OutboxPublisher:
    """Publishes outbox events to RabbitMQ.

    Requires aio-pika. If RabbitMQ is unavailable at startup, connect()
    will retry automatically when process_batch() is called.
    """

    def __init__(self, rabbitmq_url: str, exchange_name: str = "voxguard.events"):
        self._url = rabbitmq_url
        self._exchange_name = exchange_name
        self._connection = None
        self._channel = None
        self._exchange = None

    async def connect(self) -> bool:
        """Establish connection and declare exchange. Returns True on success."""
        try:
            import aio_pika  # type: ignore[import]

            self._connection = await aio_pika.connect_robust(self._url)
            self._channel = await self._connection.channel()
            await self._channel.set_qos(prefetch_count=BATCH_SIZE)
            self._exchange = await self._channel.declare_exchange(
                self._exchange_name,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )
            logger.info("outbox_publisher_connected", extra={"exchange": self._exchange_name})
            return True
        except Exception as exc:
            logger.warning(
                "outbox_publisher_connect_failed",
                extra={"error": type(exc).__name__},
            )
            self._connection = None
            self._channel = None
            self._exchange = None
            return False

    async def close(self) -> None:
        """Close RabbitMQ connection gracefully."""
        try:
            if self._connection and not self._connection.is_closed:
                await self._connection.close()
        except Exception:
            pass
        self._connection = None
        self._channel = None
        self._exchange = None

    def _is_connected(self) -> bool:
        return (
            self._connection is not None
            and not getattr(self._connection, "is_closed", True)
        )

    async def _ensure_connected(self) -> bool:
        if self._is_connected():
            return True
        return await self.connect()

    def _build_envelope(self, event: OutboxEvent) -> bytes:
        """Build voxguard event envelope per contracts schema.

        Privacy: eligibility_ref included only for voter-service consumer (SAD §8.3).
        candidate_id never included.
        """
        envelope = {
            "event_id": str(event.id),
            "event_type": event.event_type,
            "schema_version": event.schema_version,
            "occurred_at": event.created_at.isoformat()
            if isinstance(event.created_at, datetime)
            else str(event.created_at),
            "correlation_id": str(event.correlation_id),
            "producer": "ballot-service",
            "payload": event.payload,
        }
        return json.dumps(envelope, default=str).encode("utf-8")

    async def process_batch(self, db: AsyncSession) -> int:
        """Fetch and publish one batch of PENDING outbox events.

        Returns the number of events successfully published in this batch.
        Called periodically by the background polling loop.
        """
        if not await self._ensure_connected():
            logger.warning("outbox_publisher_not_connected_skipping_batch")
            return 0

        now = datetime.now(timezone.utc)

        # SELECT PENDING events eligible for next attempt, lock them (skip locked
        # so multiple workers don't collide)
        try:
            result = await db.execute(
                select(OutboxEvent)
                .where(
                    OutboxEvent.status == "PENDING",
                    OutboxEvent.next_attempt_at <= now,
                    OutboxEvent.attempts < MAX_ATTEMPTS,
                )
                .order_by(OutboxEvent.created_at.asc())
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
            events = result.scalars().all()
        except Exception as exc:
            logger.warning(
                "outbox_publisher_fetch_error",
                extra={"error": type(exc).__name__, "msg": str(exc)[:200]},
            )
            await db.rollback()
            return 0

        published = 0
        for event in events:
            try:
                import aio_pika  # type: ignore[import]

                message = aio_pika.Message(
                    body=self._build_envelope(event),
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    message_id=str(event.id),
                    correlation_id=str(event.correlation_id),
                )
                # mandatory=True: with no queue bound the broker still Acks a confirm and
                # silently drops the message, which would mark it PUBLISHED and lose it.
                # An unroutable message comes back as a Basic.Return instead of an Ack.
                confirmation = await self._exchange.publish(
                    message,
                    routing_key=event.routing_key,
                    mandatory=True,
                )
                if isinstance(confirmation, DeliveredMessage):
                    raise UnroutableEventError("no queue bound for routing key")

                # Mark PUBLISHED only after broker confirmed
                await db.execute(
                    update(OutboxEvent)
                    .where(OutboxEvent.id == event.id)
                    .values(
                        status="PUBLISHED",
                        attempts=event.attempts + 1,
                        published_at=datetime.now(timezone.utc),
                    )
                )
                published += 1
                logger.info(
                    "outbox_event_published",
                    extra={
                        "event_id": str(event.id),
                        "event_type": event.event_type,
                        "routing_key": event.routing_key,
                        "attempt": event.attempts + 1,
                    },
                )

            except Exception as exc:
                new_attempts = event.attempts + 1
                import math

                backoff = min(300, int(2 ** min(new_attempts, 8)))
                new_next = datetime.now(timezone.utc).replace(
                    second=0, microsecond=0
                )
                from datetime import timedelta

                new_next = datetime.now(timezone.utc) + timedelta(seconds=backoff)

                status = "FAILED" if new_attempts >= MAX_ATTEMPTS else "PENDING"
                await db.execute(
                    update(OutboxEvent)
                    .where(OutboxEvent.id == event.id)
                    .values(
                        attempts=new_attempts,
                        next_attempt_at=new_next,
                        status=status,
                        last_error=str(exc)[:500],
                    )
                )
                logger.warning(
                    "outbox_event_publish_error",
                    extra={
                        "event_id": str(event.id),
                        "event_type": event.event_type,
                        "attempt": new_attempts,
                        "status": status,
                        "error": type(exc).__name__,
                    },
                )
                # Reconnect on connection errors
                if "connection" in type(exc).__name__.lower() or "channel" in type(exc).__name__.lower():
                    await self.close()

        try:
            await db.commit()
        except Exception as exc:
            logger.error(
                "outbox_publisher_commit_error",
                extra={"error": str(exc)[:200]},
            )
            await db.rollback()
            return 0

        return published


async def run_outbox_publisher_loop(
    rabbitmq_url: str,
    session_factory,
    poll_interval: int = POLL_INTERVAL_SECONDS,
) -> None:
    """Background coroutine: poll and publish outbox events indefinitely.

    Designed to run as an asyncio Task in FastAPI lifespan.
    Errors are caught and logged; the loop never raises.
    """
    publisher = OutboxPublisher(rabbitmq_url)
    logger.info("outbox_publisher_loop_starting")

    while True:
        try:
            async with session_factory() as db:
                published = await publisher.process_batch(db)
                if published > 0:
                    logger.debug(
                        "outbox_batch_done", extra={"published": published}
                    )
        except asyncio.CancelledError:
            logger.info("outbox_publisher_loop_cancelled")
            await publisher.close()
            raise
        except Exception as exc:
            logger.error(
                "outbox_publisher_loop_error",
                extra={"error": type(exc).__name__, "msg": str(exc)[:200]},
            )

        await asyncio.sleep(poll_interval)
