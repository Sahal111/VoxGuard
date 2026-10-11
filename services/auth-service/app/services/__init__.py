"""Auth business logic service layer."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.infrastructure.models import RefreshSession, User


class AuthError(Exception):
    """Structured auth error with error code."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def register_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str,
    role: str = "VOTER",
    requested_by_role: str | None = None,
) -> User:
    """Create a new user account.

    Only ADMIN callers can set role != VOTER.
    """
    if role != "VOTER" and requested_by_role != "ADMIN":
        raise AuthError("FORBIDDEN", "Only ADMIN can create non-VOTER accounts.", 403)

    password_hash = hash_password(password)
    user = User(
        id=uuid.uuid4(),
        email=email,
        display_name=display_name,
        password_hash=password_hash,
        role=role,
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise AuthError("CONFLICT", "Email already registered.", 409)
    return user


async def login_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
) -> tuple[str, str, int, User]:
    """Authenticate user. Returns (access_token, refresh_token, expires_in, user).

    Uses generic error message to avoid user enumeration.
    Account lockout: after MAX_FAILED_LOGIN_ATTEMPTS consecutive failures.
    """
    result = await db.execute(select(User).where(User.email == email))
    user: User | None = result.scalar_one_or_none()

    # Generic message — don't reveal whether email exists
    _GENERIC_ERROR = AuthError("UNAUTHORIZED", "Invalid credentials.", 401)

    if user is None:
        raise _GENERIC_ERROR

    if not user.is_active:
        raise _GENERIC_ERROR

    now = datetime.now(timezone.utc)

    # Check lockout
    if user.locked_until and user.locked_until > now:
        raise AuthError("ACCOUNT_LOCKED", "Account is temporarily locked.", 423)

    # Verify password
    if not verify_password(password, user.password_hash):
        # Increment failure counter
        new_count = user.failed_login_count + 1
        updates: dict = {"failed_login_count": new_count, "updated_at": now}
        if new_count >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
            updates["locked_until"] = now + timedelta(
                minutes=settings.ACCOUNT_LOCKOUT_MINUTES
            )
        await db.execute(
            update(User).where(User.id == user.id).values(**updates)
        )
        await db.commit()
        raise _GENERIC_ERROR

    # Success — reset failure counter
    raw_refresh = generate_refresh_token()
    token_hash = hash_token(raw_refresh)
    expires_at = now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    family_id = uuid.uuid4()

    session = RefreshSession(
        id=uuid.uuid4(),
        user_id=user.id,
        family_id=family_id,
        token_hash=token_hash,
        issued_at=now,
        expires_at=expires_at,
    )
    db.add(session)

    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            failed_login_count=0,
            locked_until=None,
            last_login_at=now,
            updated_at=now,
        )
    )
    await db.commit()

    access_token, expires_in = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        display_name=user.display_name,
    )
    return access_token, raw_refresh, expires_in, user


async def refresh_tokens(
    db: AsyncSession,
    *,
    raw_refresh_token: str,
) -> tuple[str, str, int]:
    """Rotate refresh token. Returns (new_access_token, new_refresh_token, expires_in).

    Refresh token reuse detection: revokes the whole family on reuse.
    """
    token_hash = hash_token(raw_refresh_token)
    result = await db.execute(
        select(RefreshSession)
        .where(RefreshSession.token_hash == token_hash)
        .with_for_update()
    )
    session: RefreshSession | None = result.scalar_one_or_none()

    _INVALID = AuthError("UNAUTHORIZED", "Refresh token is invalid or expired.", 401)

    if session is None:
        raise _INVALID

    now = datetime.now(timezone.utc)

    # Already revoked — reuse detected; revoke entire family
    if session.revoked_at is not None:
        await db.execute(
            update(RefreshSession)
            .where(
                RefreshSession.family_id == session.family_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await db.commit()
        raise _INVALID

    if session.expires_at <= now:
        raise _INVALID

    # Load user
    user_result = await db.execute(
        select(User).where(User.id == session.user_id)
    )
    user: User | None = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise _INVALID

    # Rotate: mark old session revoked, create new one in same family
    new_raw = generate_refresh_token()
    new_hash = hash_token(new_raw)
    new_expires = now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    new_session = RefreshSession(
        id=uuid.uuid4(),
        user_id=user.id,
        family_id=session.family_id,
        token_hash=new_hash,
        issued_at=now,
        expires_at=new_expires,
    )
    db.add(new_session)

    session.revoked_at = now
    session.rotated_at = now
    session.replaced_by = new_session.id

    await db.commit()

    access_token, expires_in = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        display_name=user.display_name,
    )
    return access_token, new_raw, expires_in


async def logout_user(db: AsyncSession, *, raw_refresh_token: str) -> None:
    """Revoke the refresh session for the given token. Idempotent."""
    token_hash = hash_token(raw_refresh_token)
    now = datetime.now(timezone.utc)
    await db.execute(
        update(RefreshSession)
        .where(
            RefreshSession.token_hash == token_hash,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await db.commit()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
