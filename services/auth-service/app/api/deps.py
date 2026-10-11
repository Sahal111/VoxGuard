"""FastAPI dependencies for auth-service — JWT verification, session injection."""

from __future__ import annotations

import uuid

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.infrastructure.database import get_session

bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail={"code": "UNAUTHORIZED", "message": "Authentication required."},
)


def _err(request: Request, code: str, message: str, status_code: int) -> HTTPException:
    rid = getattr(request.state, "request_id", "unknown")
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message, "details": [], "request_id": rid}},
    )


async def get_current_user_payload(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """Decode and validate JWT. Raises 401 on any failure."""
    if credentials is None:
        raise _err(request, "UNAUTHORIZED", "Authentication required.", 401)
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise _err(request, "UNAUTHORIZED", "Token has expired.", 401)
    except jwt.InvalidTokenError:
        raise _err(request, "UNAUTHORIZED", "Invalid token.", 401)
    return payload


def require_roles(*roles: str):
    """Dependency factory: require one of the given roles."""

    async def _check(
        request: Request,
        payload: dict = Depends(get_current_user_payload),
    ) -> dict:
        if payload.get("role") not in roles:
            raise _err(request, "FORBIDDEN", "Insufficient permissions.", 403)
        return payload

    return _check


# Convenience pre-built role dependencies
require_any_authenticated = require_roles("ADMIN", "VOTER", "AUDITOR")
require_admin = require_roles("ADMIN")
