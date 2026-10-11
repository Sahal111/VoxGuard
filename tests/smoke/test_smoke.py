"""
Smoke tests for VoxGuard — verify services respond to health checks.

Prerequisites:
  - Docker Compose running: docker compose up -d
  - All services healthy: docker compose ps

Run:
  pytest tests/smoke/ -v
"""

import pytest
import httpx

SERVICES = {
    "api-gateway": "http://localhost:8000",
    "auth-service": "http://localhost:8001",
    "voter-service": "http://localhost:8002",
    "ballot-service": "http://localhost:8003",
    "audit-service": "http://localhost:8004",
    "result-service": "http://localhost:8005",
    "security-service": "http://localhost:8006",
}

TIMEOUT = 5.0


@pytest.fixture(scope="module")
def client():
    with httpx.Client(timeout=TIMEOUT) as c:
        yield c


@pytest.mark.parametrize("service,base_url", SERVICES.items())
def test_health_live(client: httpx.Client, service: str, base_url: str):
    """Each service should respond to GET /health/live with 200."""
    try:
        resp = client.get(f"{base_url}/health/live")
    except httpx.ConnectError:
        pytest.skip(f"{service} not reachable at {base_url} — is Docker Compose running?")
        return

    assert resp.status_code == 200, f"{service} health/live returned {resp.status_code}"
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == service


@pytest.mark.parametrize("service,base_url", SERVICES.items())
def test_health_ready(client: httpx.Client, service: str, base_url: str):
    """Each service should respond to GET /health/ready."""
    try:
        resp = client.get(f"{base_url}/health/ready")
    except httpx.ConnectError:
        pytest.skip(f"{service} not reachable — is Docker Compose running?")
        return

    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "status" in data


def test_gateway_routes_unknown_path(client: httpx.Client):
    """Gateway should return 404 for unknown API paths."""
    try:
        resp = client.get("http://localhost:8000/api/v1/nonexistent")
    except httpx.ConnectError:
        pytest.skip("Gateway not reachable")
        return

    assert resp.status_code == 404


def test_gateway_returns_request_id(client: httpx.Client):
    """Gateway should return X-Request-ID header."""
    try:
        resp = client.get("http://localhost:8000/health/live")
    except httpx.ConnectError:
        pytest.skip("Gateway not reachable")
        return

    assert "x-request-id" in resp.headers


def test_frontend_accessible(client: httpx.Client):
    """Frontend dev server should serve HTML."""
    try:
        resp = client.get("http://localhost:5173")
    except httpx.ConnectError:
        pytest.skip("Frontend not reachable at port 5173")
        return

    assert resp.status_code == 200
    assert "VoxGuard" in resp.text
