"""Privacy: audit payload projection never keeps choice, identity or secrets."""

from app.core.security import project_payload

FORBIDDEN = {"candidate_id", "eligibility_ref", "user_id", "email", "ballot_nonce", "receipt_code", "token", "vote_ticket"}


def test_vote_accepted_drops_everything_outside_allowlist():
    raw = {
        "election_id": "e", "ballot_id": "b", "receipt_id": "r",
        "accepted_at": "t", "ballot_commitment": "c",
        "candidate_id": "x", "eligibility_ref": "y", "user_id": "u", "email": "a@b.c",
        "ballot_nonce": "n", "receipt_code": "VG-1", "token": "jwt", "vote_ticket": "jwt2",
    }
    out = project_payload("VoteAccepted", raw)
    assert set(out) == {"election_id", "ballot_id", "receipt_id", "accepted_at", "ballot_commitment"}
    assert not FORBIDDEN & set(out)


def test_unknown_event_type_records_nothing():
    assert project_payload("SomethingNew", {"election_id": "e", "candidate_id": "x"}) == {}
