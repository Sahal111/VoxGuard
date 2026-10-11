"""FastAPI dependencies for ballot-service: authentication and authorization."""

from __future__ import annotations

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.security import decode_access_token


class BallotAuthError(Exception):
    """Auth error that carries HTTP status and standard error body."""

    def __init__(self, code: str, message: str, status_code: int):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def get_current_voter_payload(request: Request) -> dict:
    """Extract and verify Bearer JWT. Only VOTER role may cast ballots."""
    rid = getattr(request.state, "request_id", "unknown")

    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise BallotAuthError("UNAUTHORIZED", "Missing or malformed Authorization header.", 401)

    raw_token = auth_header[7:].strip()
    try:
        payload = decode_access_token(raw_token)
    except jwt.ExpiredSignatureError:
        raise BallotAuthError("UNAUTHORIZED", "Access token has expired.", 401)
    except Exception:
        raise BallotAuthError("UNAUTHORIZED", "Invalid token.", 401)

    if payload.get("role") != "VOTER":
        raise BallotAuthError("FORBIDDEN", "Only voters may cast ballots.", 403)

    return payload
