"""Tests for ballot-service health endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_live(client):
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "ballot-service"


@pytest.mark.asyncio
async def test_health_live_returns_request_id(client):
    resp = await client.get("/health/live", headers={"X-Request-ID": "test-req-123"})
    assert resp.headers.get("x-request-id") == "test-req-123"


@pytest.mark.asyncio
async def test_health_ready(client):
    resp = await client.get("/health/ready")
    # Without real DB, may return 503 or 200 depending on service
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "status" in data
    assert data["service"] == "ballot-service"
