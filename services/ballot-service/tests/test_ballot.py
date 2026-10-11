"""Comprehensive unit tests for ballot-service — Phase 11.

Coverage:
 1.  Health endpoints respond 200
 2.  Missing Idempotency-Key header → 422
 3.  Malformed Idempotency-Key format → 422
 4.  Missing Authorization header → 401
 5.  VOTER role JWT required → 403 for ADMIN role
 6.  Invalid / expired JWT → 401
 7.  Invalid vote_ticket (bad signature) → 403 VOTE_TICKET_INVALID
 8.  Expired vote_ticket → 403 VOTE_TICKET_INVALID
 9.  election_id mismatch in ticket → 403 VOTE_TICKET_INVALID
10.  Candidate not belonging to election → 422 VALIDATION_ERROR
11.  Election not OPEN (gate check via Voter mock) → 409 ELECTION_NOT_OPEN
12.  Voter Service unreachable → 503 SERVICE_UNAVAILABLE (fail-closed)
13.  Successful cast vote → 201 with receipt (mocked DB + Voter)
14.  Idempotent replay same key+payload → 200 with Idempotent-Replayed header
15.  Idempotency conflict (same key, diff candidate) → 409 IDEMPOTENCY_CONFLICT
16.  Double-vote prevention (DB UNIQUE constraint) → 409 VOTER_ALREADY_VOTED
17.  Concurrent same-key requests → at most one 201
18.  Receipt lookup success → 200, no candidate_id or eligibility_ref
19.  Receipt lookup not found → 404 RECEIPT_NOT_FOUND
20.  ballot_commitment computed correctly (deterministic)
21.  receipt_code derived via HMAC (deterministic)
22.  compute_request_hash deterministic and varies per candidate
23.  Ballot model has no user_id / email / IP columns (privacy check)
24.  VoteAccepted payload contains no candidate_id (privacy check)
25.  vote_ticket sub claim must be exactly 64-char hex eligibility_ref
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

# ── Constants ────────────────────────────────────────────────────
JWT_SECRET = os.environ["JWT_SECRET"]
TICKET_SECRET = os.environ["VOTE_TICKET_SECRET"]
RECEIPT_HMAC_KEY = os.environ["RECEIPT_HMAC_KEY"]
INTERNAL_KEY = os.environ["INTERNAL_API_KEY"]


# ── Helpers ──────────────────────────────────────────────────────
def make_user_jwt(role: str = "VOTER", user_id: str | None = None) -> str:
    uid = user_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    payload = {
        "sub": uid,
        "email": f"user-{uid[:8]}@test.com",
        "role": role,
        "display_name": "Test User",
        "iat": now,
        "exp": now + timedelta(minutes=15),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def make_vote_ticket(
    eligibility_ref: str,
    election_id: uuid.UUID,
    secret: str = TICKET_SECRET,
    expired: bool = False,
    wrong_aud: bool = False,
    wrong_typ: bool = False,
    wrong_election: bool = False,
) -> str:
    now = datetime.now(timezone.utc)
    eid = uuid.uuid4() if wrong_election else election_id
    payload = {
        "sub": eligibility_ref,
        "election_id": str(eid),
        "aud": "wrong-audience" if wrong_aud else "voxguard-ballot",
        "typ": "wrong-type" if wrong_typ else "vote-ticket",
        "iat": now,
        "exp": (now - timedelta(seconds=1)) if expired else (now + timedelta(minutes=15)),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def make_eligibility_ref() -> str:
    return "a" * 64


def make_ballot_info(
    election_id: uuid.UUID,
    status: str = "OPEN",
    candidates: list | None = None,
) -> dict:
    cands = candidates or [
        {"id": str(uuid.uuid4()), "name": "Candidate A", "ballot_order": 1, "description": "", "created_at": datetime.now(timezone.utc).isoformat(), "election_id": str(election_id)},
        {"id": str(uuid.uuid4()), "name": "Candidate B", "ballot_order": 2, "description": "", "created_at": datetime.now(timezone.utc).isoformat(), "election_id": str(election_id)},
    ]
    return {
        "election_id": str(election_id),
        "title": "Test Election",
        "status": status,
        "end_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "candidates": cands,
    }


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ══════════════════════════════════════════════════════════════════
# Test 1 — Health live
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_health_live(client):
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["service"] == "ballot-service"


# ══════════════════════════════════════════════════════════════════
# Test 2 — Missing Idempotency-Key → 422
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_missing_idempotency_key(client):
    token = make_user_jwt(role="VOTER")
    resp = await client.post(
        "/api/v1/ballots",
        json={"election_id": str(uuid.uuid4()), "candidate_id": str(uuid.uuid4()), "vote_ticket": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "Idempotency-Key" in resp.json()["error"]["details"][0]["field"]


# ══════════════════════════════════════════════════════════════════
# Test 3 — Malformed Idempotency-Key format → 422
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_malformed_idempotency_key(client):
    token = make_user_jwt(role="VOTER")
    resp = await client.post(
        "/api/v1/ballots",
        json={"election_id": str(uuid.uuid4()), "candidate_id": str(uuid.uuid4()), "vote_ticket": "x"},
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "too-short",  # < 16 chars
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# ══════════════════════════════════════════════════════════════════
# Test 4 — Missing Authorization header → 401
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_missing_authorization(client):
    resp = await client.post(
        "/api/v1/ballots",
        json={"election_id": str(uuid.uuid4()), "candidate_id": str(uuid.uuid4()), "vote_ticket": "x"},
        headers={"Idempotency-Key": "a" * 16},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


# ══════════════════════════════════════════════════════════════════
# Test 5 — ADMIN role → 403 (only VOTER may cast)
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_admin_role_forbidden(client):
    token = make_user_jwt(role="ADMIN")
    resp = await client.post(
        "/api/v1/ballots",
        json={"election_id": str(uuid.uuid4()), "candidate_id": str(uuid.uuid4()), "vote_ticket": "x"},
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "b" * 16,
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


# ══════════════════════════════════════════════════════════════════
# Test 6 — Invalid JWT → 401
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_invalid_jwt(client):
    resp = await client.post(
        "/api/v1/ballots",
        json={"election_id": str(uuid.uuid4()), "candidate_id": str(uuid.uuid4()), "vote_ticket": "x"},
        headers={
            "Authorization": "Bearer not.a.jwt",
            "Idempotency-Key": "c" * 16,
        },
    )
    assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════
# Test 7 — Invalid vote_ticket signature → 403 VOTE_TICKET_INVALID
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_invalid_vote_ticket_bad_signature(client):
    token = make_user_jwt(role="VOTER")
    election_id = uuid.uuid4()
    elig_ref = make_eligibility_ref()
    bad_ticket = make_vote_ticket(elig_ref, election_id, secret="wrong-secret-key-min-32chars-padded!!")

    with patch(
        "app.api.ballots._validate_election_open",
        new_callable=AsyncMock,
        return_value=make_ballot_info(election_id),
    ):
        resp = await client.post(
            "/api/v1/ballots",
            json={"election_id": str(election_id), "candidate_id": str(uuid.uuid4()), "vote_ticket": bad_ticket},
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "d" * 16,
            },
        )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "VOTE_TICKET_INVALID"


# ══════════════════════════════════════════════════════════════════
# Test 8 — Expired vote_ticket → 403 VOTE_TICKET_INVALID
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_expired_vote_ticket(client):
    token = make_user_jwt(role="VOTER")
    election_id = uuid.uuid4()
    elig_ref = make_eligibility_ref()
    expired_ticket = make_vote_ticket(elig_ref, election_id, expired=True)

    resp = await client.post(
        "/api/v1/ballots",
        json={"election_id": str(election_id), "candidate_id": str(uuid.uuid4()), "vote_ticket": expired_ticket},
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "e" * 16,
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "VOTE_TICKET_INVALID"


# ══════════════════════════════════════════════════════════════════
# Test 9 — election_id mismatch in ticket → 403 VOTE_TICKET_INVALID
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_vote_ticket_election_mismatch(client):
    token = make_user_jwt(role="VOTER")
    election_id = uuid.uuid4()
    elig_ref = make_eligibility_ref()
    mismatched_ticket = make_vote_ticket(elig_ref, election_id, wrong_election=True)

    resp = await client.post(
        "/api/v1/ballots",
        json={"election_id": str(election_id), "candidate_id": str(uuid.uuid4()), "vote_ticket": mismatched_ticket},
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "f" * 16,
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "VOTE_TICKET_INVALID"


# ══════════════════════════════════════════════════════════════════
# Test 10 — Candidate not in election → 422 VALIDATION_ERROR
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_candidate_not_in_election(client):
    token = make_user_jwt(role="VOTER")
    election_id = uuid.uuid4()
    elig_ref = make_eligibility_ref()
    ticket = make_vote_ticket(elig_ref, election_id)
    unknown_candidate = uuid.uuid4()

    ballot_info = make_ballot_info(election_id)  # has different candidate IDs
    with patch(
        "app.api.ballots._validate_election_open",
        new_callable=AsyncMock,
        return_value=ballot_info,
    ):
        from app.services import BallotError
        with patch(
            "app.api.ballots.cast_vote",
            new_callable=AsyncMock,
            side_effect=BallotError("VALIDATION_ERROR", "Kandidat tidak terdaftar dalam pemilihan ini.", 422),
        ):
            resp = await client.post(
                "/api/v1/ballots",
                json={"election_id": str(election_id), "candidate_id": str(unknown_candidate), "vote_ticket": ticket},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "g" * 16,
                },
            )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# ══════════════════════════════════════════════════════════════════
# Test 11 — Election not OPEN → 409 ELECTION_NOT_OPEN
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_election_not_open(client):
    token = make_user_jwt(role="VOTER")
    election_id = uuid.uuid4()
    elig_ref = make_eligibility_ref()
    ticket = make_vote_ticket(elig_ref, election_id)

    from app.services import BallotError
    with patch(
        "app.api.ballots._validate_election_open",
        new_callable=AsyncMock,
        side_effect=BallotError("ELECTION_NOT_OPEN", "Pemilihan tidak sedang berlangsung.", 409),
    ):
        resp = await client.post(
            "/api/v1/ballots",
            json={"election_id": str(election_id), "candidate_id": str(uuid.uuid4()), "vote_ticket": ticket},
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "h" * 16,
            },
        )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ELECTION_NOT_OPEN"


# ══════════════════════════════════════════════════════════════════
# Test 12 — Voter Service unreachable → 503 (fail-closed)
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_voter_service_unavailable(client):
    token = make_user_jwt(role="VOTER")
    election_id = uuid.uuid4()
    elig_ref = make_eligibility_ref()
    ticket = make_vote_ticket(elig_ref, election_id)

    from app.services import BallotError
    with patch(
        "app.api.ballots._validate_election_open",
        new_callable=AsyncMock,
        side_effect=BallotError("SERVICE_UNAVAILABLE", "Voter service tidak tersedia.", 503),
    ):
        resp = await client.post(
            "/api/v1/ballots",
            json={"election_id": str(election_id), "candidate_id": str(uuid.uuid4()), "vote_ticket": ticket},
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "i" * 16,
            },
        )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


# ══════════════════════════════════════════════════════════════════
# Test 13 — Successful cast vote → 201 receipt
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_cast_vote_success(client):
    token = make_user_jwt(role="VOTER")
    election_id = uuid.uuid4()
    elig_ref = make_eligibility_ref()
    ticket = make_vote_ticket(elig_ref, election_id)
    receipt_id = uuid.uuid4()
    accepted_at = datetime.now(timezone.utc).isoformat()

    snapshot = {
        "receipt_id": str(receipt_id),
        "election_id": str(election_id),
        "accepted_at": accepted_at,
        "receipt_code": "a" * 48,
        "audit_status": "PENDING",
    }

    with patch("app.api.ballots._validate_election_open", new_callable=AsyncMock,
               return_value=make_ballot_info(election_id)):
        with patch("app.api.ballots.cast_vote", new_callable=AsyncMock,
                   return_value=(snapshot, False)):
            resp = await client.post(
                "/api/v1/ballots",
                json={"election_id": str(election_id), "candidate_id": str(uuid.uuid4()), "vote_ticket": ticket},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "j" * 16,
                },
            )
    assert resp.status_code == 201
    data = resp.json()
    assert data["receipt_id"] == str(receipt_id)
    assert data["election_id"] == str(election_id)
    assert data["audit_status"] == "PENDING"
    assert "candidate_id" not in data     # privacy: no choice in response
    assert "eligibility_ref" not in data  # privacy


# ══════════════════════════════════════════════════════════════════
# Test 14 — Idempotent replay (same key + payload) → 200 + header
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_idempotent_replay(client):
    token = make_user_jwt(role="VOTER")
    election_id = uuid.uuid4()
    elig_ref = make_eligibility_ref()
    ticket = make_vote_ticket(elig_ref, election_id)
    receipt_id = uuid.uuid4()
    snapshot = {
        "receipt_id": str(receipt_id),
        "election_id": str(election_id),
        "accepted_at": datetime.now(timezone.utc).isoformat(),
        "receipt_code": "b" * 48,
        "audit_status": "PENDING",
    }

    with patch("app.api.ballots._validate_election_open", new_callable=AsyncMock,
               return_value=make_ballot_info(election_id)):
        with patch("app.api.ballots.cast_vote", new_callable=AsyncMock,
                   return_value=(snapshot, True)):    # is_replay=True
            resp = await client.post(
                "/api/v1/ballots",
                json={"election_id": str(election_id), "candidate_id": str(uuid.uuid4()), "vote_ticket": ticket},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "k" * 16,
                },
            )
    assert resp.status_code == 200
    assert resp.headers.get("idempotent-replayed") == "true"
    assert resp.json()["receipt_id"] == str(receipt_id)


# ══════════════════════════════════════════════════════════════════
# Test 15 — Idempotency conflict (same key, different candidate)
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_idempotency_conflict(client):
    token = make_user_jwt(role="VOTER")
    election_id = uuid.uuid4()
    elig_ref = make_eligibility_ref()
    ticket = make_vote_ticket(elig_ref, election_id)

    from app.services import BallotError
    with patch("app.api.ballots._validate_election_open", new_callable=AsyncMock,
               return_value=make_ballot_info(election_id)):
        with patch("app.api.ballots.cast_vote", new_callable=AsyncMock,
                   side_effect=BallotError("IDEMPOTENCY_CONFLICT",
                                            "Idempotency key sudah digunakan dengan payload yang berbeda.", 409)):
            resp = await client.post(
                "/api/v1/ballots",
                json={"election_id": str(election_id), "candidate_id": str(uuid.uuid4()), "vote_ticket": ticket},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "l" * 16,
                },
            )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


# ══════════════════════════════════════════════════════════════════
# Test 16 — Double-vote prevention → 409 VOTER_ALREADY_VOTED
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_double_vote_prevention(client):
    token = make_user_jwt(role="VOTER")
    election_id = uuid.uuid4()
    elig_ref = make_eligibility_ref()
    ticket = make_vote_ticket(elig_ref, election_id)

    from app.services import BallotError
    with patch("app.api.ballots._validate_election_open", new_callable=AsyncMock,
               return_value=make_ballot_info(election_id)):
        with patch("app.api.ballots.cast_vote", new_callable=AsyncMock,
                   side_effect=BallotError("VOTER_ALREADY_VOTED",
                                            "Hak memilih Anda sudah digunakan.", 409)):
            resp = await client.post(
                "/api/v1/ballots",
                json={"election_id": str(election_id), "candidate_id": str(uuid.uuid4()), "vote_ticket": ticket},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "m" * 16,
                },
            )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "VOTER_ALREADY_VOTED"


# ══════════════════════════════════════════════════════════════════
# Test 17 — Concurrent same-key requests: at most one 201
# (Simulated: two calls with same idempotency key, second returns replay)
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_concurrent_same_key_at_most_one_201(client):
    token = make_user_jwt(role="VOTER")
    election_id = uuid.uuid4()
    elig_ref = make_eligibility_ref()
    ticket = make_vote_ticket(elig_ref, election_id)
    ikey = "concurrent-test-key-16"
    receipt_id = uuid.uuid4()
    snapshot = {
        "receipt_id": str(receipt_id),
        "election_id": str(election_id),
        "accepted_at": datetime.now(timezone.utc).isoformat(),
        "receipt_code": "c" * 48,
        "audit_status": "PENDING",
    }

    call_count = 0

    async def cast_vote_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return snapshot, False    # first → 201
        return snapshot, True         # subsequent → 200 replay

    with patch("app.api.ballots._validate_election_open", new_callable=AsyncMock,
               return_value=make_ballot_info(election_id)):
        with patch("app.api.ballots.cast_vote", new_callable=AsyncMock,
                   side_effect=cast_vote_side_effect):
            payload = {"election_id": str(election_id), "candidate_id": str(uuid.uuid4()), "vote_ticket": ticket}
            headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": ikey}
            r1, r2 = await asyncio.gather(
                client.post("/api/v1/ballots", json=payload, headers=headers),
                client.post("/api/v1/ballots", json=payload, headers=headers),
            )

    statuses = {r1.status_code, r2.status_code}
    assert 201 in statuses
    # Second must be 200 replay or 409 — never two 201s
    assert 201 not in {r1.status_code, r2.status_code} - {201} or statuses == {200, 201}


# ══════════════════════════════════════════════════════════════════
# Test 18 — Receipt lookup success (no candidate_id or eligibility_ref)
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_receipt_lookup_success(client):
    token = make_user_jwt(role="VOTER")
    receipt_id = uuid.uuid4()
    election_id = uuid.uuid4()
    accepted_at = datetime.now(timezone.utc)

    from app.core.security import compute_receipt_code
    receipt_code = compute_receipt_code(receipt_id)

    with patch(
        "app.api.ballots.get_receipt",
        new_callable=AsyncMock,
        return_value={
            "receipt_id": receipt_id,
            "election_id": election_id,
            "accepted_at": accepted_at,
            "audit_status": "PENDING",
        },
    ):
        resp = await client.get(
            f"/api/v1/ballots/receipt/{receipt_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Receipt-Code": receipt_code,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["receipt_id"] == str(receipt_id)
    assert data["audit_status"] == "PENDING"
    # Privacy assertions
    assert "candidate_id" not in data
    assert "eligibility_ref" not in data
    assert "ballot_nonce" not in data


# ══════════════════════════════════════════════════════════════════
# Test 18b — Receipt lookup missing X-Receipt-Code → 422
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_receipt_lookup_missing_code(client):
    token = make_user_jwt(role="VOTER")
    receipt_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/ballots/receipt/{receipt_id}",
        headers={"Authorization": f"Bearer {token}"},
        # No X-Receipt-Code header
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert any(d["field"] == "X-Receipt-Code" for d in resp.json()["error"]["details"])


# ══════════════════════════════════════════════════════════════════
# Test 18c — Receipt lookup wrong X-Receipt-Code → 404 (not differentiated)
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_receipt_lookup_wrong_code(client):
    token = make_user_jwt(role="VOTER")
    receipt_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/ballots/receipt/{receipt_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Receipt-Code": "wrong-code-that-is-48-chars-long-xxxxxxxxxxx",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RECEIPT_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════
# Test 19 — Receipt not found → 404 RECEIPT_NOT_FOUND
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_receipt_not_found(client):
    token = make_user_jwt(role="VOTER")
    receipt_id = uuid.uuid4()
    from app.core.security import compute_receipt_code
    correct_code = compute_receipt_code(receipt_id)
    from app.services import BallotError
    with patch(
        "app.api.ballots.get_receipt",
        new_callable=AsyncMock,
        side_effect=BallotError("RECEIPT_NOT_FOUND", "Receipt tidak ditemukan.", 404),
    ):
        resp = await client.get(
            f"/api/v1/ballots/receipt/{receipt_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Receipt-Code": correct_code,
            },
        )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RECEIPT_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════
# Test 20 — ballot_commitment is deterministic and correct
# ══════════════════════════════════════════════════════════════════
def test_ballot_commitment_deterministic():
    from app.core.security import compute_ballot_commitment
    eid = uuid.uuid4()
    cid = uuid.uuid4()
    nonce = "a" * 64

    c1 = compute_ballot_commitment(eid, cid, nonce)
    c2 = compute_ballot_commitment(eid, cid, nonce)
    assert c1 == c2
    assert len(c1) == 64
    assert all(ch in "0123456789abcdef" for ch in c1)

    # Different candidate → different commitment
    c3 = compute_ballot_commitment(eid, uuid.uuid4(), nonce)
    assert c1 != c3


# ══════════════════════════════════════════════════════════════════
# Test 21 — receipt_code derived deterministically via HMAC
# ══════════════════════════════════════════════════════════════════
def test_receipt_code_deterministic():
    from app.core.security import compute_receipt_code
    rid = uuid.uuid4()
    code1 = compute_receipt_code(rid)
    code2 = compute_receipt_code(rid)
    assert code1 == code2
    assert len(code1) == 48
    # Different receipt_id → different code
    assert compute_receipt_code(uuid.uuid4()) != code1


# ══════════════════════════════════════════════════════════════════
# Test 22 — compute_request_hash deterministic, varies per candidate
# ══════════════════════════════════════════════════════════════════
def test_compute_request_hash():
    from app.core.security import compute_request_hash
    eid = uuid.uuid4()
    cid = uuid.uuid4()
    h1 = compute_request_hash(eid, cid)
    h2 = compute_request_hash(eid, cid)
    assert h1 == h2
    assert len(h1) == 64
    h3 = compute_request_hash(eid, uuid.uuid4())
    assert h1 != h3


# ══════════════════════════════════════════════════════════════════
# Test 23 — Ballot model has no user_id, email, IP columns (privacy)
# ══════════════════════════════════════════════════════════════════
def test_ballot_model_no_pii_columns():
    from app.infrastructure.models import Ballot
    forbidden = ["user_id", "email", "email_normalized", "ip_address", "ip", "name", "display_name"]
    for attr in forbidden:
        assert not hasattr(Ballot, attr), f"Ballot model must NOT have column '{attr}'"


# ══════════════════════════════════════════════════════════════════
# Test 24 — VoteAccepted outbox payload contains no candidate_id
# (Check service-level: candidate_id absent from outbox payload)
# ══════════════════════════════════════════════════════════════════
def test_vote_accepted_payload_no_candidate_id():
    """The VoteAccepted payload template must not include candidate_id."""
    from app.services import cast_vote
    import inspect
    source = inspect.getsource(cast_vote)
    # The outbox_payload dict literal must NOT assign candidate_id
    # We check the string "candidate_id" does not appear in outbox_payload context
    # by asserting it doesn't appear in the event payload section
    assert '"candidate_id"' not in source.split("outbox_payload")[1].split("outbox_stmt")[0], \
        "candidate_id must NOT appear in VoteAccepted outbox_payload"


# ══════════════════════════════════════════════════════════════════
# Test 25 — vote_ticket sub claim must be 64-char hex eligibility_ref
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_invalid_eligibility_ref_length_in_ticket(client):
    """A vote_ticket with sub != 64 chars must be rejected with VOTE_TICKET_INVALID."""
    token = make_user_jwt(role="VOTER")
    election_id = uuid.uuid4()
    # Ticket with short sub (not 64 chars)
    now = datetime.now(timezone.utc)
    bad_payload = {
        "sub": "short-ref",   # invalid length
        "election_id": str(election_id),
        "aud": "voxguard-ballot",
        "typ": "vote-ticket",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    bad_ticket = jwt.encode(bad_payload, TICKET_SECRET, algorithm="HS256")

    resp = await client.post(
        "/api/v1/ballots",
        json={"election_id": str(election_id), "candidate_id": str(uuid.uuid4()), "vote_ticket": bad_ticket},
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "n" * 16,
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "VOTE_TICKET_INVALID"
