"""Tests for audit-service health endpoints."""

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
    assert data["service"] == "audit-service"


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
    assert data["service"] == "audit-service"


class _FakeConsumer:
    def __init__(self, ready):
        self.ready = ready


@pytest.mark.asyncio
@pytest.mark.parametrize("ready,code", [(True, 200), (False, 503)])
async def test_ready_reflects_consumer_when_configured(client, monkeypatch, ready, code):
    async def db_ok(*_a, **_k):
        return True, "ok"

    monkeypatch.setattr("app.main.check_db_ready", db_ok)
    monkeypatch.setattr(app.state, "consumer", _FakeConsumer(ready), raising=False)
    resp = await client.get("/health/ready")
    assert resp.status_code == code
    assert resp.json()["checks"]["message_broker"]["status"] == ("ok" if ready else "unavailable")


@pytest.mark.asyncio
async def test_ready_ignores_broker_when_consumer_disabled(client, monkeypatch):
    async def db_ok(*_a, **_k):
        return True, "ok"

    monkeypatch.setattr("app.main.check_db_ready", db_ok)
    monkeypatch.setattr(app.state, "consumer", None, raising=False)
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert "message_broker" not in resp.json()["checks"]
