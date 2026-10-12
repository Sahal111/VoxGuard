"""Endpoint guards that must hold before the database is ever touched."""

import time
import uuid

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app

pytestmark = pytest.mark.asyncio
ELECTION = uuid.uuid4()
PATHS = [
    "/api/v1/audit/events",
    f"/api/v1/audit/elections/{ELECTION}/verify",
    f"/api/v1/audit/elections/{ELECTION}/proof",
]


def token(role, secret=None, exp_delta=300):
    now = int(time.time())
    return jwt.encode(
        {"sub": str(uuid.uuid4()), "email": "x@y.z", "role": role, "iat": now, "exp": now + exp_delta, "jti": str(uuid.uuid4())},
        secret or settings.JWT_SECRET,
        algorithm="HS256",
    )


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def bearer(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.mark.parametrize("path", PATHS)
async def test_no_token_is_401(client, path):
    resp = await client.get(path)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"
    assert resp.json()["error"]["request_id"]


@pytest.mark.parametrize("path", PATHS)
async def test_forged_or_expired_token_is_401(client, path):
    assert (await client.get(path, headers=bearer(token("ADMIN", secret="w" * 40)))).status_code == 401
    assert (await client.get(path, headers=bearer(token("ADMIN", exp_delta=-10)))).status_code == 401


@pytest.mark.parametrize("path", PATHS[:2])
async def test_voter_cannot_list_or_verify(client, path):
    resp = await client.get(path, headers=bearer(token("VOTER")))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_unknown_role_is_forbidden_on_proof(client):
    assert (await client.get(PATHS[2], headers=bearer(token("GUEST")))).status_code == 403


@pytest.mark.parametrize(
    "path,query",
    [
        ("/api/v1/audit/events", "?page=0"),
        ("/api/v1/audit/events", "?page_size=101"),
        ("/api/v1/audit/events", "?order=sideways"),
        ("/api/v1/audit/events", "?election_id=not-a-uuid"),
        ("/api/v1/audit/events", "?from_sequence=0"),
        ("/api/v1/audit/elections/not-a-uuid/verify", ""),
        (f"/api/v1/audit/elections/{ELECTION}/proof", "?receipt_id=nope"),
    ],
)
async def test_bad_input_is_422_standard_error(client, path, query):
    resp = await client.get(path + query, headers=bearer(token("ADMIN")))
    assert resp.status_code == 422
    body = resp.json()["error"]
    assert body["code"] == "VALIDATION_ERROR" and body["details"]


async def test_auth_checked_before_validation(client):
    assert (await client.get("/api/v1/audit/events?page=0")).status_code == 401
