"""VoxGuard auth-service — FastAPI application."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.core.config import settings
from app.infrastructure.database import check_db_ready

logger = logging.getLogger("auth_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("auth-service starting", extra={"service": "auth-service", "port": 8001})
    yield
    logger.info("auth-service shutting down")


app = FastAPI(
    title="VoxGuard Auth Service",
    version="0.1.0",
    docs_url="/docs" if settings.APP_ENV in ("local", "test") else None,
    lifespan=lifespan,
)

app.include_router(auth_router)


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
        extra={
            "service": "auth-service",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "elapsed_ms": elapsed_ms,
            "request_id": request_id,
        },
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("unhandled_error", extra={"service": "auth-service", "request_id": request_id})
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred.", "details": [], "request_id": request_id}},
    )


@app.get("/health/live", tags=["health"])
async def health_live():
    return {"status": "ok", "service": "auth-service"}


@app.get("/health/ready", tags=["health"])
async def health_ready():
    checks: dict = {}
    all_ok = True
    db_ok, db_msg = await check_db_ready()
    if not db_ok:
        checks["database"] = {"status": "unavailable", "error": db_msg}
        all_ok = False
    else:
        checks["database"] = {"status": "ok"}
    code = 200 if all_ok else 503
    return JSONResponse(
        status_code=code,
        content={"status": "ok" if all_ok else "degraded", "service": "auth-service", "checks": checks},
    )
