"""Standard error response schema per API Contract Specification §7."""

from __future__ import annotations

# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    field: str | None = None
    issue: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
    request_id: str | None = None


class ErrorResponse(BaseModel):
    """Top-level error wrapper: ``{"error": {...}}``."""

    error: ErrorBody
