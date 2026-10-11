"""VoxGuard API Gateway — routes requests to upstream services."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger("api_gateway")

# ── Route mapping: prefix -> upstream base URL ──────────────────────
ROUTE_MAP: list[tuple[str, str]] = [
    ("/api/v1/auth", settings.AUTH_SERVICE_URL),
    ("/api/v1/elections", settings.VOTER_SERVICE_URL),
    ("/api/v1/ballots", settings.BALLOT_SERVICE_URL),
    ("/api/v1/audit", settings.AUDIT_SERVICE_URL),
    ("/api/v1/results", settings.RESULT_SERVICE_URL),
    ("/api/v1/security", settings.SECURITY_SERVICE_URL),
]

http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.UPSTREAM_TIMEOUT),
        follow_redirects=False,
    )
    logger.info("api-gateway starting", extra={"service": "api-gateway", "port": 8000})
    yield
    await http_client.aclose()
    logger.info("api-gateway shutting down")


app = FastAPI(
    title="VoxGuard API Gateway",
    version="0.1.0",
    docs_url="/docs" if settings.APP_ENV in ("local", "test") else None,
    lifespan=lifespan,
)


# ── Middleware: Request ID & Correlation ID ─────────────────────────
@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id")
    if not request_id:
        request_id = str(uuid.uuid4())

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
            "service": "api-gateway",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "elapsed_ms": elapsed_ms,
            "request_id": request_id,
            "correlation_id": correlation_id,
        },
    )
    return response


# ── Error handler ───────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(
        "unhandled_error",
        extra={"service": "api-gateway", "request_id": request_id},
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


# ── Health endpoints ────────────────────────────────────────────────
@app.get("/health/live", tags=["health"])
async def health_live():
    return {"status": "ok", "service": "api-gateway"}


@app.get("/health/ready", tags=["health"])
async def health_ready():
    return {"status": "ok", "service": "api-gateway", "checks": {}}


# ── Proxy helper ────────────────────────────────────────────────────
def _find_upstream(path: str) -> tuple[str, str] | None:
    """Find upstream URL and matching prefix for a request path."""
    for prefix, upstream_url in ROUTE_MAP:
        if path.startswith(prefix):
            return upstream_url, prefix
    return None


def _build_upstream_headers(request: Request, upstream_path: str = "") -> dict[str, str]:
    """Build headers for upstream request.

    Defense-in-depth: strip X-User-Id and X-User-Email for ballot routes
    per API Contract §6.1 — ballot-service must not receive identity headers
    to prevent any accidental PII association with ballot data.
    """
    # Headers that must never be forwarded from client (hop-by-hop + identity spoofing)
    HOP_BY_HOP = frozenset(("host", "connection", "transfer-encoding", "keep-alive"))

    # Identity headers stripped for ALL routes (they must only come from auth flow)
    ALWAYS_STRIP = frozenset(("x-user-id", "x-user-email", "x-internal-key"))

    # Additional identity headers stripped specifically for ballot routes (defense-in-depth)
    BALLOT_STRIP = frozenset(("x-forwarded-user", "x-auth-user", "x-voter-id"))

    is_ballot_route = upstream_path.startswith("/api/v1/ballots")

    headers: dict[str, str] = {}
    for key, value in request.headers.items():
        lower_key = key.lower()
        if lower_key in HOP_BY_HOP:
            continue
        if lower_key in ALWAYS_STRIP:
            continue
        if is_ballot_route and lower_key in BALLOT_STRIP:
            continue
        headers[key] = value

    # Ensure request/correlation IDs are always set
    headers["X-Request-ID"] = request.state.request_id
    headers["X-Correlation-ID"] = request.state.correlation_id
    return headers


# ── Catch-all proxy route ──────────────────────────────────────────
@app.api_route(
    "/api/v1/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def proxy(request: Request, path: str):
    """Forward API requests to the appropriate upstream service."""
    request_id = getattr(request.state, "request_id", "unknown")

    full_path = f"/api/v1/{path}"
    match = _find_upstream(full_path)

    if match is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "NOT_FOUND",
                    "message": "No upstream service for this path.",
                    "details": [],
                    "request_id": request_id,
                }
            },
        )

    upstream_url, prefix = match

    # Build the upstream path — forward the full /api/v1/... path
    upstream_path = full_path
    query = str(request.url.query)
    if query:
        upstream_path += f"?{query}"

    target_url = f"{upstream_url}{upstream_path}"

    body = await request.body()
    headers = _build_upstream_headers(request, upstream_path=full_path)

    try:
        assert http_client is not None
        upstream_resp = await http_client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
        )
    except httpx.TimeoutException:
        logger.warning(
            "upstream_timeout",
            extra={
                "service": "api-gateway",
                "target": target_url,
                "request_id": request_id,
            },
        )
        return JSONResponse(
            status_code=504,
            content={
                "error": {
                    "code": "GATEWAY_TIMEOUT",
                    "message": "Upstream service did not respond in time.",
                    "details": [],
                    "request_id": request_id,
                }
            },
        )
    except httpx.ConnectError:
        logger.warning(
            "upstream_unavailable",
            extra={
                "service": "api-gateway",
                "target": target_url,
                "request_id": request_id,
            },
        )
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "SERVICE_UNAVAILABLE",
                    "message": "Upstream service is unavailable.",
                    "details": [],
                    "request_id": request_id,
                }
            },
        )
    except Exception:
        logger.exception(
            "upstream_error",
            extra={
                "service": "api-gateway",
                "target": target_url,
                "request_id": request_id,
            },
        )
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "code": "BAD_GATEWAY",
                    "message": "Error communicating with upstream service.",
                    "details": [],
                    "request_id": request_id,
                }
            },
        )

    # Build response — forward status, headers, body
    resp_headers = dict(upstream_resp.headers)
    # Remove hop-by-hop headers
    for h in ("transfer-encoding", "connection", "content-encoding", "content-length"):
        resp_headers.pop(h, None)

    resp_headers["X-Request-ID"] = request_id
    resp_headers["X-Correlation-ID"] = request.state.correlation_id

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers=resp_headers,
    )
