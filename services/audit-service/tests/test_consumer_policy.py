"""Retry / dead-letter policy of the consumer, with a fake channel (no broker)."""

import pytest

from app.consumer import FAILURE_HEADER, RETRY_HEADER, AuditConsumer

pytestmark = pytest.mark.asyncio


class FakeMessage:
    def __init__(self, headers=None, body=b"{}"):
        self.body = body
        self.headers = headers or {}
        self.content_type = "application/json"
        self.message_id = "m1"
        self.correlation_id = "c1"
        self.acked = 0
        self.nacked = []

    async def ack(self):
        self.acked += 1

    async def nack(self, requeue=True):
        self.nacked.append(requeue)


class FakeExchange:
    def __init__(self, fail=False):
        self.fail = fail
        self.published = []

    async def publish(self, message, routing_key, mandatory=False):
        if self.fail:
            raise ConnectionError("broker down")
        self.published.append((routing_key, message))


class FakeChannel:
    def __init__(self, fail=False):
        self.default_exchange = FakeExchange(fail)


def make(fail=False, delays=(5000, 30000, 120000)):
    consumer = AuditConsumer(
        url="amqp://unused", session_factory=None, exchange="x", queue="audit.q", retry_delays_ms=delays
    )
    consumer._channel = FakeChannel(fail)
    return consumer, consumer._channel.default_exchange


async def test_tiers_then_dlq_on_fourth_failure():
    consumer, exchange = make()
    targets = []
    attempt = 0
    for _ in range(4):
        msg = FakeMessage({RETRY_HEADER: attempt} if attempt else {})
        await consumer._retry_or_dead_letter(msg, "OperationalError")
        assert msg.acked == 1 and not msg.nacked
        key, republished = exchange.published[-1]
        targets.append(key)
        attempt = republished.headers[RETRY_HEADER]
    assert targets == ["audit.q.retry.5000ms", "audit.q.retry.30000ms", "audit.q.retry.120000ms", "audit.q.dlq"]


async def test_retry_copy_keeps_body_and_records_failure_class_only():
    consumer, exchange = make()
    msg = FakeMessage(body=b'{"a":1}')
    await consumer._retry_or_dead_letter(msg, "OperationalError")
    _, copy = exchange.published[0]
    assert copy.body == b'{"a":1}'
    assert copy.headers[FAILURE_HEADER] == "OperationalError"
    assert copy.delivery_mode.name == "PERSISTENT"


async def test_permanent_failure_goes_straight_to_dlq():
    consumer, exchange = make()
    msg = FakeMessage()
    await consumer._dead_letter(msg, "INVALID_PAYLOAD")
    assert [k for k, _ in exchange.published] == ["audit.q.dlq"]
    assert exchange.published[0][1].headers[FAILURE_HEADER] == "INVALID_PAYLOAD"
    assert msg.acked == 1


async def test_failed_republish_nacks_and_never_acks():
    consumer, _ = make(fail=True)
    for call in (
        lambda m: consumer._retry_or_dead_letter(m, "OperationalError"),
        lambda m: consumer._dead_letter(m, "INVALID_PAYLOAD"),
    ):
        msg = FakeMessage()
        await call(msg)
        assert msg.acked == 0
        assert msg.nacked == [True]


async def test_topology_names():
    consumer, _ = make()
    assert consumer.dlq_name == "audit.q.dlq"
    assert consumer.retry_queue_name(0) == "audit.q.retry.5000ms"
    assert consumer.connected is False


async def test_changing_delays_changes_queue_names():
    # RabbitMQ rejects redeclaring a queue with a different TTL; names must follow the delay.
    a, _ = make(delays=(100, 200))
    b, _ = make(delays=(300, 200))
    assert a.retry_queue_name(0) != b.retry_queue_name(0)
    assert a.retry_queue_name(1) == b.retry_queue_name(1)
