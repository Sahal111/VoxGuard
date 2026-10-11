"""FastAPI authentication & authorization dependencies for voter-service."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
import jwt

from app.core.security import decode_access_token, verify_internal_key


async def get_current_user_payload(request: Request) -> dict:
    """Extract and verify Bearer JWT from Authorization header."""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Missing or malformed Authorization header."},
        )

    raw_token = auth_header[7:].strip()
    try:
        return decode_access_token(raw_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_EXPIRED", "message": "Access token has expired."},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid token."},
        )


async def require_any_authenticated(
    payload: dict = Depends(get_current_user_payload),
) -> dict:
    return payload


async def require_admin(
    payload: dict = Depends(get_current_user_payload),
) -> dict:
    if payload.get("role") != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Admin privileges required."},
        )
    return payload


async def require_internal_call(
    x_internal_key: str | None = Header(None, alias="X-Internal-Key"),
) -> None:
    if not verify_internal_key(x_internal_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Invalid or missing internal service key."},
        )
