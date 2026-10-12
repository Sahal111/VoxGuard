"""Response schemas for the audit endpoints (API Contract §5.1, API_CONTRACTS B.4)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scope_id: uuid.UUID
    sequence: int
    source_event_id: uuid.UUID
    source_event_type: str
    occurred_at: datetime
    recorded_at: datetime
    payload_public: dict
    prev_hash: str
    event_hash: str


class PageInfo(BaseModel):
    page: int
    page_size: int
    total: int


class AuditEventPage(BaseModel):
    items: list[AuditEventOut]
    page: PageInfo


class FirstFailure(BaseModel):
    sequence: int
    reason: str


class CheckpointComparison(BaseModel):
    compared: bool
    matches: bool | None
    checkpoint_sequence: int | None


class VerifyAuditResponse(BaseModel):
    check_id: uuid.UUID
    election_id: uuid.UUID
    status: str
    events_checked: int
    head_sequence: int
    head_hash: str
    first_failure: FirstFailure | None
    checkpoint: CheckpointComparison
    checked_at: datetime


class LatestCheckpoint(BaseModel):
    sequence: int
    event_hash: str
    reason: str
    created_at: datetime


class LastVerified(BaseModel):
    status: str
    checked_at: datetime


class ReceiptEvent(BaseModel):
    sequence: int
    prev_hash: str
    event_hash: str


class ProofResponse(BaseModel):
    election_id: uuid.UUID
    hash_algorithm: str
    canonicalization: str
    genesis_hash: str
    event_count: int
    head_sequence: int
    head_hash: str
    latest_checkpoint: LatestCheckpoint | None
    last_verified: LastVerified | None
    receipt_event: ReceiptEvent | None
