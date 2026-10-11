"""Auth API router — endpoints per API Contract §5.2."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_payload, require_any_authenticated
from app.infrastructure.database import get_session
from app.schemas import (
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    RefreshTokenResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services import (
    AuthError,
    get_user_by_id,
    login_user,
    logout_user,
    refresh_tokens,
    register_user,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _auth_error_response(request: Request, exc: AuthError) -> JSONResponse:
    rid = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": [],
                "request_id": rid,
            }
        },
    )


# ── POST /api/v1/auth/register ─────────────────────────────────
@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
    summary="Register a new account",
)
async def register(
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_session),
):
    # Determine caller role for privilege elevation check
    caller_role: str | None = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from app.core.security import decode_access_token
            payload = decode_access_token(auth_header[7:])
            caller_role = payload.get("role")
        except Exception:
            pass

    target_role = body.role or "VOTER"
    try:
        user = await register_user(
            db,
            email=body.email,
            password=body.password,
            display_name=body.display_name,
            role=target_role,
            requested_by_role=caller_role,
        )
    except AuthError as exc:
        return _auth_error_response(request, exc)

    return UserResponse.model_validate(user)


# ── POST /api/v1/auth/login ────────────────────────────────────
@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=TokenResponse,
    summary="Authenticate and obtain tokens",
)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_session),
):
    try:
        access_token, raw_refresh, expires_in, user = await login_user(
            db, email=body.email, password=body.password
        )
    except AuthError as exc:
        return _auth_error_response(request, exc)

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=expires_in,
        refresh_token=raw_refresh,
        user={
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
        },
    )


# ── POST /api/v1/auth/refresh ──────────────────────────────────
@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
    response_model=RefreshTokenResponse,
    summary="Refresh access token using refresh token",
)
async def refresh(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_session),
):
    try:
        access_token, new_refresh, expires_in = await refresh_tokens(
            db, raw_refresh_token=body.refresh_token
        )
    except AuthError as exc:
        return _auth_error_response(request, exc)

    return RefreshTokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=expires_in,
        refresh_token=new_refresh,
    )


# ── POST /api/v1/auth/logout ───────────────────────────────────
@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke refresh session",
)
async def logout(
    request: Request,
    body: LogoutRequest,
    db: AsyncSession = Depends(get_session),
    _payload: dict = Depends(require_any_authenticated),
):
    await logout_user(db, raw_refresh_token=body.refresh_token)
    return JSONResponse(status_code=204, content=None)


# ── GET /api/v1/auth/me ────────────────────────────────────────
@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=MeResponse,
    summary="Get current authenticated user",
)
async def me(
    request: Request,
    payload: dict = Depends(require_any_authenticated),
    db: AsyncSession = Depends(get_session),
):
    user_id = uuid.UUID(payload["sub"])
    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        rid = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=401,
            content={"error": {"code": "UNAUTHORIZED", "message": "User not found.", "details": [], "request_id": rid}},
        )
    return MeResponse.model_validate(user)
