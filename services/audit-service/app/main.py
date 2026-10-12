"""VoxGuard audit-service — FastAPI application."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.audit import router as audit_router
from app.api.deps import AuditError
from app.consumer import AuditConsumer
from app.core.config import settings
from app.infrastructure.database import async_session, check_db_ready

logger = logging.getLogger("audit_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown. The VoteAccepted consumer runs only when RABBITMQ_URL is set."""
    logger.info("audit-service starting", extra={"service": "audit-service", "port": 8004})
    consumer_task = None
    app.state.consumer = None
    if settings.RABBITMQ_URL:
        app.state.consumer = AuditConsumer(
            url=settings.RABBITMQ_URL,
            session_factory=async_session,
            exchange=settings.AUDIT_EXCHANGE,
            queue=settings.AUDIT_QUEUE,
            prefetch=settings.AUDIT_PREFETCH,
            retry_delays_ms=settings.AUDIT_RETRY_DELAYS_MS,
        )
        consumer_task = asyncio.create_task(app.state.consumer.run())
    else:
        logger.warning("audit_consumer_disabled_no_rabbitmq_url")
    yield
    logger.info("audit-service shutting down")
    if consumer_task is not None:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="VoxGuard audit-service",
    version="0.1.0",
    docs_url="/docs" if settings.APP_ENV in ("local", "test") else None,
    lifespan=lifespan,
)

app.include_router(audit_router)


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
        extra={
            "service": "audit-service",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "elapsed_ms": elapsed_ms,
            "request_id": request_id,
            "correlation_id": correlation_id,
        },
    )
    return response


# ── Error handlers ──────────────────────────────────────────────
def _error(request: Request, status_code: int, code: str, message: str, details=None):
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or [],
                "request_id": getattr(request.state, "request_id", "unknown"),
            }
        },
    )


@app.exception_handler(AuditError)
async def audit_error_handler(request: Request, exc: AuditError):
    return _error(request, exc.status_code, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [
        {"field": ".".join(str(p) for p in err["loc"] if p != "query" and p != "path"), "issue": err["msg"]}
        for err in exc.errors()
    ]
    return _error(request, 422, "VALIDATION_ERROR", "Input tidak valid.", details)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(
        "unhandled_error",
        extra={"service": "audit-service", "request_id": request_id},
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred.",
                "details": [],
                "request_id": request_id,
            }
        },
    )


# ── Health endpoints ────────────────────────────────────────────
@app.get("/health/live", tags=["health"])
async def health_live():
    return {"status": "ok", "service": "audit-service"}


@app.get("/health/ready", tags=["health"])
async def health_ready():
    checks = {}
    all_ok = True
    db_ok, db_msg = await check_db_ready()
    if not db_ok:
        checks["database"] = {"status": "unavailable", "error": db_msg}
        all_ok = False
    else:
        checks["database"] = {"status": "ok"}
    consumer = getattr(app.state, "consumer", None)
    if consumer is not None:  # required dependency whenever the consumer is configured
        if consumer.ready:
            checks["message_broker"] = {"status": "ok"}
        else:
            checks["message_broker"] = {"status": "unavailable"}
            all_ok = False
    status = "ok" if all_ok else "degraded"
    code = 200 if all_ok else 503
    return JSONResponse(
        status_code=code,
        content={"status": status, "service": "audit-service", "checks": checks},
    )
