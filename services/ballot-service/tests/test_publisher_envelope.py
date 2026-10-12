"""Regression: ballot outbox envelope must satisfy the shared event contract.

audit-service validates incoming messages with voxguard_contracts.EventEnvelope
(extra="forbid", `producer` required). A publisher that emits `source_service`
instead would see every VoteAccepted dead-lettered.
"""

import inspect
import json
import uuid
from datetime import datetime, timezone

# pyrefly: ignore [missing-import]
from voxguard_contracts import EventEnvelope, EventType, Producer

from app.infrastructure.models import OutboxEvent
from app.infrastructure.publisher import OutboxPublisher


def _outbox_event() -> OutboxEvent:
    return OutboxEvent(
        id=uuid.uuid4(),
        event_type="VoteAccepted",
        routing_key="vote.accepted",
        schema_version="1.0",
        correlation_id=uuid.uuid4(),
        payload={
            "election_id": str(uuid.uuid4()),
            "ballot_id": str(uuid.uuid4()),
            "receipt_id": str(uuid.uuid4()),
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "ballot_commitment": "a" * 64,
            "eligibility_ref": "b" * 64,
        },
        created_at=datetime.now(timezone.utc),
    )


def test_envelope_validates_against_shared_contract():
    event = _outbox_event()
    body = json.loads(OutboxPublisher("amqp://unused")._build_envelope(event))

    assert "source_service" not in body
    envelope = EventEnvelope.model_validate(body)
    assert envelope.producer is Producer.BALLOT_SERVICE
    assert envelope.event_type is EventType.VOTE_ACCEPTED
    assert envelope.event_id == event.id
    assert envelope.correlation_id == event.correlation_id


def test_envelope_never_carries_candidate_choice():
    body = json.loads(OutboxPublisher("amqp://unused")._build_envelope(_outbox_event()))
    assert "candidate_id" not in json.dumps(body)


def test_default_exchange_matches_docs():
    default = inspect.signature(OutboxPublisher.__init__).parameters["exchange_name"].default
    assert default == "voxguard.events"


def test_cast_vote_uses_postgres_insert():
    # The generic sqlalchemy insert() has no on_conflict_do_nothing → POST /ballots 500'd on real PostgreSQL.
    from app import services

    assert hasattr(services.insert(OutboxEvent), "on_conflict_do_nothing")
