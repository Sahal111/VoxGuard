"""Pydantic schemas for ballot-service per API Contract §5.4, §6.1-6.2."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── Request ─────────────────────────────────────────────────────
class CastBallotRequest(BaseModel):
    """[S-VOTE-IN] Body for POST /api/v1/ballots."""

    election_id: uuid.UUID
    candidate_id: uuid.UUID
    vote_ticket: str = Field(..., min_length=10, description="JWT vote ticket from voter-service")

    model_config = {"extra": "forbid"}


# ── Responses ───────────────────────────────────────────────────
class BallotReceiptResponse(BaseModel):
    """[S-RECEIPT] Successful cast vote response."""

    receipt_id: uuid.UUID
    receipt_code: str
    election_id: uuid.UUID
    accepted_at: datetime
    audit_status: str = "PENDING"


class ReceiptLookupResponse(BaseModel):
    """GET /api/v1/ballots/receipt/{receipt_id} response.

    Privacy: no candidate_id, eligibility_ref, or voter identity.
    """

    receipt_id: uuid.UUID
    election_id: uuid.UUID
    accepted_at: datetime
    audit_status: str   # PENDING | RECORDED
