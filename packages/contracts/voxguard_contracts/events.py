"""Event envelope schema — shared across all services per API Contract Specification §8.1."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field


class EventType(str, enum.Enum):
    ELECTION_OPENED = "ElectionOpened"
    ELECTION_CLOSED = "ElectionClosed"
    VOTE_ACCEPTED = "VoteAccepted"
    VOTE_REJECTED = "VoteRejected"
    AUDIT_RECORDED = "AuditRecorded"
    TALLY_COMPLETED = "TallyCompleted"
    RESULT_FINALIZED = "ResultFinalized"
    SECURITY_ALERT_RAISED = "SecurityAlertRaised"
    SECURITY_SIGNAL_OBSERVED = "SecuritySignalObserved"


class Producer(str, enum.Enum):
    API_GATEWAY = "api-gateway"
    AUTH_SERVICE = "auth-service"
    VOTER_SERVICE = "voter-service"
    BALLOT_SERVICE = "ballot-service"
    AUDIT_SERVICE = "audit-service"
    RESULT_SERVICE = "result-service"
    SECURITY_SERVICE = "security-service"


class EventEnvelope(BaseModel):
    """Standard event envelope per API Contract §8.1."""

    event_id: UUID
    event_type: EventType
    schema_version: str = Field(default="1.0", pattern=r"^[0-9]+\.[0-9]+$")
    occurred_at: datetime
    producer: Producer
    correlation_id: UUID
    payload: dict

    model_config = {"extra": "forbid"}
