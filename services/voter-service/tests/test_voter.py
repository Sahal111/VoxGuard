"""Comprehensive unit tests for voter-service endpoints and business rules."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import compute_eligibility_ref
from app.main import app

BASE = "/api/v1/elections"
INTERNAL_BASE = "/internal/v1/elections"
TEST_JWT_SECRET = "test-secret-key-must-be-at-least-32-chars-long!"
TEST_PEPPER = "test-pepper-secret-key-must-be-at-least-32-chars!"


# ── Helpers ─────────────────────────────────────────────────────
def make_jwt(
    user_id: str | None = None,
    role: str = "ADMIN",
    email: str = "admin@example.com",
    expired: bool = False,
) -> str:
    uid = user_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    exp = now - timedelta(minutes=1) if expired else now + timedelta(minutes=15)
    return jwt.encode(
        {
            "sub": uid,
            "email": email,
            "role": role,
            "display_name": "Test User",
            "iat": now,
            "exp": exp,
            "jti": str(uuid.uuid4()),
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )


def make_election_obj(**kwargs):
    election = MagicMock()
    election.id = kwargs.get("id", uuid.uuid4())
    election.title = kwargs.get("title", "Pemilihan Umum")
    election.description = kwargs.get("description", "Deskripsi")
    election.status = kwargs.get("status", "DRAFT")
    election.start_at = kwargs.get("start_at", datetime.now(timezone.utc) + timedelta(hours=1))
    election.end_at = kwargs.get("end_at", datetime.now(timezone.utc) + timedelta(hours=5))
    election.opened_at = kwargs.get("opened_at", None)
    election.closed_at = kwargs.get("closed_at", None)
    election.finalized_at = kwargs.get("finalized_at", None)
    election.is_attack_lab = kwargs.get("is_attack_lab", False)
    election.candidates = kwargs.get("candidates", [])
    election.voters = kwargs.get("voters", [])
    election.created_at = datetime.now(timezone.utc)
    election.updated_at = datetime.now(timezone.utc)
    return election


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ══════════════════════════════════════════════════════════════════
# Test 1 — Create election as ADMIN succeeds
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_create_election_admin_success(client):
    admin_token = make_jwt(role="ADMIN")
    now = datetime.now(timezone.utc)
    election = make_election_obj(
        title="Pemilihan Ketua",
        start_at=now + timedelta(hours=1),
        end_at=now + timedelta(hours=3),
    )

    with (
        patch("app.api.elections.create_election", new_callable=AsyncMock, return_value=election),
        patch("app.api.elections.get_election_by_id", new_callable=AsyncMock) as mock_get,
    ):
        from app.schemas import ElectionDetailResponse
        mock_get.return_value = ElectionDetailResponse(
            id=election.id,
            title=election.title,
            description=election.description,
            status="DRAFT",
            start_at=election.start_at,
            end_at=election.end_at,
            is_attack_lab=False,
            candidates=[],
            created_at=election.created_at,
        )

        resp = await client.post(
            BASE,
            json={
                "title": "Pemilihan Ketua",
                "description": "Deskripsi pemilihan",
                "start_at": (now + timedelta(hours=1)).isoformat(),
                "end_at": (now + timedelta(hours=3)).isoformat(),
                "is_attack_lab": False,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "DRAFT"
    assert data["title"] == "Pemilihan Ketua"


# ══════════════════════════════════════════════════════════════════
# Test 2 — Create election unauthenticated → 401
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_create_election_unauthenticated(client):
    now = datetime.now(timezone.utc)
    resp = await client.post(
        BASE,
        json={
            "title": "Pemilihan Unauth",
            "start_at": (now + timedelta(hours=1)).isoformat(),
            "end_at": (now + timedelta(hours=2)).isoformat(),
        },
    )
    assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════
# Test 3 — Create election by VOTER → 403 Forbidden
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_create_election_voter_forbidden(client):
    voter_token = make_jwt(role="VOTER")
    now = datetime.now(timezone.utc)
    resp = await client.post(
        BASE,
        json={
            "title": "Pemilihan Ilegal",
            "start_at": (now + timedelta(hours=1)).isoformat(),
            "end_at": (now + timedelta(hours=2)).isoformat(),
        },
        headers={"Authorization": f"Bearer {voter_token}"},
    )
    assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════
# Test 4 — Create election with invalid dates (start >= end) → 422
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_create_election_invalid_dates(client):
    admin_token = make_jwt(role="ADMIN")
    now = datetime.now(timezone.utc)
    resp = await client.post(
        BASE,
        json={
            "title": "Tanggal Terbalik",
            "start_at": (now + timedelta(hours=3)).isoformat(),
            "end_at": (now + timedelta(hours=1)).isoformat(),
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════
# Test 5 — DRAFT election hidden from VOTER / AUDITOR
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_draft_election_hidden_from_voter(client):
    voter_token = make_jwt(role="VOTER")
    elec_id = uuid.uuid4()

    from app.services import VoterError
    with patch(
        "app.api.elections.get_election_by_id",
        new_callable=AsyncMock,
        side_effect=VoterError("NOT_FOUND", "Election not found.", 404),
    ):
        resp = await client.get(
            f"{BASE}/{elec_id}",
            headers={"Authorization": f"Bearer {voter_token}"},
        )
    assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════
# Test 6 — Add candidate to DRAFT election succeeds
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_add_candidate_success(client):
    admin_token = make_jwt(role="ADMIN")
    elec_id = uuid.uuid4()
    from app.schemas import CandidateResponse

    cand_resp = CandidateResponse(
        id=uuid.uuid4(),
        election_id=elec_id,
        name="Calon A",
        description="Visi Calon A",
        ballot_order=1,
        created_at=datetime.now(timezone.utc),
    )

    with patch("app.api.elections.add_candidate", new_callable=AsyncMock, return_value=cand_resp):
        resp = await client.post(
            f"{BASE}/{elec_id}/candidates",
            json={"name": "Calon A", "description": "Visi Calon A", "ballot_order": 1},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Calon A"
    assert resp.json()["ballot_order"] == 1


# ══════════════════════════════════════════════════════════════════
# Test 7 — Add candidate rejects duplicate ballot order / name
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_add_candidate_conflict(client):
    admin_token = make_jwt(role="ADMIN")
    elec_id = uuid.uuid4()
    from app.services import VoterError

    with patch(
        "app.api.elections.add_candidate",
        new_callable=AsyncMock,
        side_effect=VoterError("CONFLICT", "Candidate name or ballot order already exists in this election.", 409),
    ):
        resp = await client.post(
            f"{BASE}/{elec_id}/candidates",
            json={"name": "Calon A", "ballot_order": 1},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


# ══════════════════════════════════════════════════════════════════
# Test 8 — Add candidate rejected when election not in DRAFT status
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_add_candidate_invalid_state(client):
    admin_token = make_jwt(role="ADMIN")
    elec_id = uuid.uuid4()
    from app.services import VoterError

    with patch(
        "app.api.elections.add_candidate",
        new_callable=AsyncMock,
        side_effect=VoterError("ELECTION_INVALID_STATE", "Candidates can only be modified in DRAFT state.", 409),
    ):
        resp = await client.post(
            f"{BASE}/{elec_id}/candidates",
            json={"name": "Calon B", "ballot_order": 2},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ELECTION_INVALID_STATE"


# ══════════════════════════════════════════════════════════════════
# Test 9 — Import voters in batch succeeds
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_import_voters_success(client):
    admin_token = make_jwt(role="ADMIN")
    elec_id = uuid.uuid4()

    with patch("app.api.elections.import_voters", new_callable=AsyncMock, return_value=2):
        resp = await client.post(
            f"{BASE}/{elec_id}/voters/import",
            json={
                "voters": [
                    {"email": "voter1@example.com", "external_ref": "VOT-001", "display_label": "Voter 1"},
                    {"email": "voter2@example.com", "external_ref": "VOT-002", "display_label": "Voter 2"},
                ]
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 201
    assert resp.json()["imported"] == 2


# ══════════════════════════════════════════════════════════════════
# Test 10 — Import voters with in-batch duplicates rejected → 422
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_import_voters_batch_duplicate(client):
    admin_token = make_jwt(role="ADMIN")
    elec_id = uuid.uuid4()
    from app.services import VoterError

    with patch(
        "app.api.elections.import_voters",
        new_callable=AsyncMock,
        side_effect=VoterError("UNPROCESSABLE_ENTITY", "Duplicate email found within import batch.", 422),
    ):
        resp = await client.post(
            f"{BASE}/{elec_id}/voters/import",
            json={
                "voters": [
                    {"email": "duplicate@example.com", "external_ref": "VOT-001", "display_label": "Voter 1"},
                    {"email": "duplicate@example.com", "external_ref": "VOT-002", "display_label": "Voter 2"},
                ]
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════
# Test 11 — Schedule election transitions DRAFT -> SCHEDULED
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_schedule_election_success(client):
    admin_token = make_jwt(role="ADMIN")
    elec_id = uuid.uuid4()
    election = make_election_obj(id=elec_id, status="SCHEDULED")

    with patch("app.api.elections.schedule_election", new_callable=AsyncMock, return_value=election):
        resp = await client.post(
            f"{BASE}/{elec_id}/schedule",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "SCHEDULED"


# ══════════════════════════════════════════════════════════════════
# Test 12 — Schedule election fails if < 2 candidates → 422
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_schedule_election_insufficient_candidates(client):
    admin_token = make_jwt(role="ADMIN")
    elec_id = uuid.uuid4()
    from app.services import VoterError

    with patch(
        "app.api.elections.schedule_election",
        new_callable=AsyncMock,
        side_effect=VoterError("UNPROCESSABLE_ENTITY", "Election requires at least 2 candidates.", 422),
    ):
        resp = await client.post(
            f"{BASE}/{elec_id}/schedule",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════
# Test 13 — Open election transitions SCHEDULED -> OPEN
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_open_election_success(client):
    admin_token = make_jwt(role="ADMIN")
    elec_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    election = make_election_obj(id=elec_id, status="OPEN", opened_at=now)

    with patch("app.api.elections.open_election", new_callable=AsyncMock, return_value=election):
        resp = await client.post(
            f"{BASE}/{elec_id}/open",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "OPEN"
    assert resp.json()["opened_at"] is not None


# ══════════════════════════════════════════════════════════════════
# Test 14 — Illegal transition (DRAFT -> OPEN skipping SCHEDULED) rejected → 409
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_open_election_illegal_transition(client):
    admin_token = make_jwt(role="ADMIN")
    elec_id = uuid.uuid4()
    from app.services import VoterError

    with patch(
        "app.api.elections.open_election",
        new_callable=AsyncMock,
        side_effect=VoterError("ELECTION_INVALID_STATE", "Cannot open election in status 'DRAFT'. Must be SCHEDULED.", 409),
    ):
        resp = await client.post(
            f"{BASE}/{elec_id}/open",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ELECTION_INVALID_STATE"


# ══════════════════════════════════════════════════════════════════
# Test 15 — Close election transitions OPEN -> CLOSED
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_close_election_success(client):
    admin_token = make_jwt(role="ADMIN")
    elec_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    election = make_election_obj(id=elec_id, status="CLOSED", closed_at=now)

    with patch("app.api.elections.close_election", new_callable=AsyncMock, return_value=election):
        resp = await client.post(
            f"{BASE}/{elec_id}/close",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "CLOSED"
    assert resp.json()["closed_at"] is not None


# ══════════════════════════════════════════════════════════════════
# Test 16 — Pseudonym HMAC computation verification
# ══════════════════════════════════════════════════════════════════
def test_eligibility_ref_pseudonym_computation():
    elec_id = uuid.uuid4()
    voter_id = uuid.uuid4()

    ref1 = compute_eligibility_ref(TEST_PEPPER, elec_id, voter_id)
    ref2 = compute_eligibility_ref(TEST_PEPPER, elec_id, voter_id)

    # Must be deterministic for the same election and voter
    assert ref1 == ref2
    assert len(ref1) == 64
    assert all(c in "0123456789abcdef" for c in ref1)

    # Must differ across elections
    elec_id2 = uuid.uuid4()
    ref3 = compute_eligibility_ref(TEST_PEPPER, elec_id2, voter_id)
    assert ref1 != ref3

    # Must differ across voters
    voter_id2 = uuid.uuid4()
    ref4 = compute_eligibility_ref(TEST_PEPPER, elec_id, voter_id2)
    assert ref1 != ref4


# ══════════════════════════════════════════════════════════════════
# Test 17 — Internal ticket issuance succeeds for eligible voter
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_internal_issue_ticket_success(client):
    elec_id = uuid.uuid4()
    user_id = uuid.uuid4()
    expected_ref = "a" * 64

    with patch(
        "app.api.internal.issue_vote_ticket",
        new_callable=AsyncMock,
        return_value={
            "election_id": elec_id,
            "eligibility_ref": expected_ref,
            "status": "TICKET_ISSUED",
        },
    ):
        resp = await client.post(
            f"{INTERNAL_BASE}/{elec_id}/eligibility/tickets",
            json={"user_id": str(user_id)},
            headers={"X-Internal-Key": "dev-internal-key"},
        )
    assert resp.status_code == 200
    assert resp.json()["eligibility_ref"] == expected_ref
    assert resp.json()["status"] == "TICKET_ISSUED"


# ══════════════════════════════════════════════════════════════════
# Test 18 — Internal ticket issuance rejected for already voted → 409
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_internal_issue_ticket_already_voted(client):
    elec_id = uuid.uuid4()
    user_id = uuid.uuid4()
    from app.services import VoterError

    with patch(
        "app.api.internal.issue_vote_ticket",
        new_callable=AsyncMock,
        side_effect=VoterError("VOTER_ALREADY_VOTED", "Hak memilih ini sudah digunakan.", 409),
    ):
        resp = await client.post(
            f"{INTERNAL_BASE}/{elec_id}/eligibility/tickets",
            json={"user_id": str(user_id)},
            headers={"X-Internal-Key": "dev-internal-key"},
        )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "VOTER_ALREADY_VOTED"


# ══════════════════════════════════════════════════════════════════
# Test 19 — Internal ticket issuance rejected without internal key → 403
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_internal_endpoint_rejects_missing_key(client):
    elec_id = uuid.uuid4()
    user_id = uuid.uuid4()
    resp = await client.post(
        f"{INTERNAL_BASE}/{elec_id}/eligibility/tickets",
        json={"user_id": str(user_id)},
    )
    assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════
# Test 20 — Model voter/eligibility separation: no candidate choice column
# ══════════════════════════════════════════════════════════════════
def test_privacy_voter_models_have_no_ballot_choice():
    from app.infrastructure.models import Voter, VotingEligibility

    # Verify no candidate or choice columns exist in Voter or VotingEligibility
    forbidden_attributes = ["candidate_id", "choice", "ballot_id", "vote", "selected_candidate"]
    for attr in forbidden_attributes:
        assert not hasattr(Voter, attr), f"Voter model must NOT have {attr}"
        assert not hasattr(VotingEligibility, attr), f"VotingEligibility model must NOT have {attr}"


# ══════════════════════════════════════════════════════════════════
# Test 21 — Health check endpoints still respond 200
# ══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_voter_health_live(client):
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["service"] == "voter-service"
