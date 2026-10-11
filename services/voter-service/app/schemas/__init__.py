"""Pydantic schemas for voter-service per API Contract Specification §5.1 & §5.3."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# ── Election schemas ────────────────────────────────────────────
class ElectionCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=150)
    description: str = Field(default="", max_length=2000)
    start_at: datetime
    end_at: datetime
    is_attack_lab: bool = False

    @model_validator(mode="after")
    def validate_dates(self) -> ElectionCreateRequest:
        if self.start_at >= self.end_at:
            raise ValueError("start_at must be strictly before end_at")
        return self

    model_config = {"extra": "forbid"}


class CandidateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    ballot_order: int = Field(..., ge=1)

    model_config = {"extra": "forbid"}


class CandidateResponse(BaseModel):
    id: uuid.UUID
    election_id: uuid.UUID
    name: str
    description: str
    ballot_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class VoterImportItem(BaseModel):
    email: EmailStr = Field(..., max_length=254)
    external_ref: str = Field(..., min_length=1, max_length=100)
    display_label: str = Field(..., min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()

    model_config = {"extra": "forbid"}


class VoterImportRequest(BaseModel):
    voters: list[VoterImportItem] = Field(..., min_length=1, max_length=1000)

    model_config = {"extra": "forbid"}


class VoterImportResponse(BaseModel):
    election_id: uuid.UUID
    imported: int


class ElectionDetailResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    status: str
    start_at: datetime
    end_at: datetime
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    finalized_at: datetime | None = None
    is_attack_lab: bool
    candidates: list[CandidateResponse] = Field(default_factory=list)
    created_at: datetime
    voter_count: int | None = None
    participation_count: int | None = None

    model_config = {"from_attributes": True}


class ElectionSummaryResponse(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    start_at: datetime
    end_at: datetime

    model_config = {"from_attributes": True}


class PageMetadata(BaseModel):
    page: int
    page_size: int
    total: int


class PageResponse(BaseModel):
    items: list[ElectionSummaryResponse]
    page: PageMetadata


class ElectionStatusResponse(BaseModel):
    id: uuid.UUID
    status: str
    opened_at: datetime | None = None
    closed_at: datetime | None = None


# ── Internal Service-to-Service Schemas ─────────────────────────
class BallotInfoResponse(BaseModel):
    election_id: uuid.UUID
    title: str
    status: str
    end_at: datetime
    candidates: list[CandidateResponse]


class IssueTicketRequest(BaseModel):
    user_id: uuid.UUID
    email: EmailStr | None = None

    model_config = {"extra": "forbid"}


class IssueTicketResponse(BaseModel):
    election_id: uuid.UUID
    eligibility_ref: str
    status: str


class ElectionSummaryInternalResponse(BaseModel):
    election_id: uuid.UUID
    title: str
    status: str
    closed_at: datetime | None
    candidates: list[CandidateResponse]
    total_eligible: int
    total_voted: int
