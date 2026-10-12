"""FastAPI dependencies for audit-service: backend authentication and RBAC."""

from __future__ import annotations

import jwt
from fastapi import Request

from app.core.security import decode_access_token


class AuditError(Exception):
    """Error carrying HTTP status and the standard error body fields (Contract §7)."""

    def __init__(self, code: str, message: str, status_code: int):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def require_roles(*roles: str):
    """Dependency factory: valid Bearer access token whose `role` is one of `roles`."""

    async def dependency(request: Request) -> dict:
        header = request.headers.get("authorization")
        if not header or not header.startswith("Bearer "):
            raise AuditError("UNAUTHORIZED", "Token autentikasi tidak ada atau tidak valid.", 401)
        try:
            payload = decode_access_token(header[7:].strip())
        except jwt.ExpiredSignatureError:
            raise AuditError("UNAUTHORIZED", "Token autentikasi telah kedaluwarsa.", 401)
        except Exception:
            raise AuditError("UNAUTHORIZED", "Token autentikasi tidak ada atau tidak valid.", 401)
        if payload.get("role") not in roles:
            raise AuditError("FORBIDDEN", "Peran Anda tidak berwenang untuk tindakan ini.", 403)
        return payload

    return dependency
