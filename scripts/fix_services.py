"""
Regenerate main.py files for all backend services with correct formatting.
Fixes indentation issues from the initial generation.
"""

import os

ROOT = "/Users/sahalanwarhadi/project_Sahal/VoxGuard/services"

# Services that have a database
DB_SERVICES = {
    "auth-service": ("auth_service", 8001, "AUTH_DATABASE_URL"),
    "voter-service": ("voter_service", 8002, "VOTER_DATABASE_URL"),
    "ballot-service": ("ballot_service", 8003, "BALLOT_DATABASE_URL"),
    "audit-service": ("audit_service", 8004, "AUDIT_DATABASE_URL"),
    "result-service": ("result_service", 8005, "RESULT_DATABASE_URL"),
    "security-service": ("security_service", 8006, "SECURITY_DATABASE_URL"),
}

def gen_main(name: str, slug: str, port: int, has_db: bool) -> str:
    db_import = "\nfrom app.infrastructure.database import check_db_ready" if has_db else ""
    db_check = ""
    if has_db:
        db_check = """
    db_ok, db_msg = await check_db_ready()
    if not db_ok:
        checks["database"] = {"status": "unavailable", "error": db_msg}
        all_ok = False
    else:
        checks["database"] = {"status": "ok"}"""

    return f'''"""VoxGuard {name} — FastAPI application."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.core.config import settings{db_import}

logger = logging.getLogger("{slug}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown."""
    logger.info("{name} starting", extra={{"service": "{name}", "port": {port}}})
    yield
    logger.info("{name} shutting down")


app = FastAPI(
    title="VoxGuard {name}",
    version="0.1.0",
    docs_url="/docs" if settings.APP_ENV in ("local", "test") else None,
    lifespan=lifespan,
)


# ── Middleware: Request ID & Correlation ID ──────────────────────
@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    correlation_id = request.headers.get("x-correlation-id") or request_id
    request.state.request_id = request_id
    request.state.correlation_id = correlation_id

    start = time.monotonic()
    response: Response = await call_next(request)
    elapsed_ms = round((time.monotonic() - start) * 1000, 2)

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Correlation-ID"] = correlation_id

    logger.info(
        "request",
        extra={{
            "service": "{name}",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "elapsed_ms": elapsed_ms,
            "request_id": request_id,
            "correlation_id": correlation_id,
        }},
    )
    return response


# ── Error handler ───────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(
        "unhandled_error",
        extra={{"service": "{name}", "request_id": request_id}},
    )
    return JSONResponse(
        status_code=500,
        content={{
            "error": {{
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred.",
                "details": [],
                "request_id": request_id,
            }}
        }},
    )


# ── Health endpoints ────────────────────────────────────────────
@app.get("/health/live", tags=["health"])
async def health_live():
    return {{"status": "ok", "service": "{name}"}}


@app.get("/health/ready", tags=["health"])
async def health_ready():
    checks = {{}}
    all_ok = True{db_check}
    status = "ok" if all_ok else "degraded"
    code = 200 if all_ok else 503
    return JSONResponse(
        status_code=code,
        content={{"status": status, "service": "{name}", "checks": checks}},
    )
'''


def gen_config(slug: str, db_env_var: str | None) -> str:
    db_field = ""
    if db_env_var:
        sync_var = db_env_var + "_SYNC"
        db_field = f"""
    {db_env_var}: str
    {sync_var}: str = ""
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT: int = 10"""

    return f'''"""Configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_ENV: str = "local"{db_field}

    model_config = {{"env_file": ".env", "extra": "ignore"}}


settings = Settings()
'''


def gen_database(name: str, slug: str, db_env_var: str) -> str:
    return f'''"""Database engine and session management for {name}."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text

from app.core.config import settings

logger = logging.getLogger("{slug}.db")

engine = create_async_engine(
    settings.{db_env_var},
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def check_db_ready(timeout: float = 3.0) -> tuple[bool, str]:
    """Check database connectivity with timeout."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:
        logger.warning("db_health_check_failed", extra={{"error": str(exc)[:200]}})
        return False, str(exc)[:200]
'''


for svc_name, (slug, port, db_env) in DB_SERVICES.items():
    svc_dir = os.path.join(ROOT, svc_name)

    # main.py
    main_path = os.path.join(svc_dir, "app", "main.py")
    with open(main_path, "w") as f:
        f.write(gen_main(svc_name, slug, port, True))
    print(f"  FIXED: {svc_name}/app/main.py")

    # config.py
    cfg_path = os.path.join(svc_dir, "app", "core", "config.py")
    with open(cfg_path, "w") as f:
        f.write(gen_config(slug, db_env))
    print(f"  FIXED: {svc_name}/app/core/config.py")

    # database.py
    db_path = os.path.join(svc_dir, "app", "infrastructure", "database.py")
    with open(db_path, "w") as f:
        f.write(gen_database(svc_name, slug, db_env))
    print(f"  FIXED: {svc_name}/app/infrastructure/database.py")

print("\n✓ All service files regenerated with correct formatting.")
