"""Request/response schemas for auth-service — per API Contract §5.2."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Request schemas ─────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., max_length=254)
    password: str = Field(..., min_length=12, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=100)
    role: str | None = Field(default=None, pattern="^(ADMIN|VOTER|AUDITOR)$")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()

    model_config = {"extra": "forbid"}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()

    model_config = {"extra": "forbid"}


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)

    model_config = {"extra": "forbid"}


class LogoutRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)

    model_config = {"extra": "forbid"}


# ── Response schemas ────────────────────────────────────────────
class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserBrief(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: str

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: str
    user: UserBrief


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: str

    model_config = {"from_attributes": True}
