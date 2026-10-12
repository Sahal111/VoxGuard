"""Consumer validation: what is accepted, what is a permanent (DLQ) failure."""

import json
import uuid
from datetime import datetime, timezone

import pytest

from app.consumer import PermanentError, parse_vote_accepted

CANDIDATE = str(uuid.uuid4())
ELIGIBILITY = "e" * 64


def envelope(**override):
    body = {
        "event_id": str(uuid.uuid4()),
        "event_type": "VoteAccepted",
        "schema_version": "1.0",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "producer": "ballot-service",
        "correlation_id": str(uuid.uuid4()),
        "payload": {
            "election_id": str(uuid.uuid4()),
            "ballot_id": str(uuid.uuid4()),
            "receipt_id": str(uuid.uuid4()),
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "ballot_commitment": "a" * 64,
            "eligibility_ref": ELIGIBILITY,
        },
    }
    body.update(override)
    return body


def encode(body) -> bytes:
    return json.dumps(body).encode()


def reason(body) -> str:
    with pytest.raises(PermanentError) as exc:
        parse_vote_accepted(body if isinstance(body, bytes) else encode(body))
    return exc.value.reason


def test_valid_event_is_projected_and_normalised():
    body = envelope()
    parsed = parse_vote_accepted(encode(body))
    assert parsed.source_event_id == uuid.UUID(body["event_id"])
    assert parsed.scope_id == uuid.UUID(body["payload"]["election_id"])
    assert set(parsed.payload_public) == {
        "election_id", "ballot_id", "receipt_id", "accepted_at", "ballot_commitment",
    }
    assert parsed.payload_public["accepted_at"].endswith("Z")
    assert ELIGIBILITY not in json.dumps(parsed.payload_public)


def test_eligibility_ref_is_not_required():
    body = envelope()
    del body["payload"]["eligibility_ref"]
    parse_vote_accepted(encode(body))


@pytest.mark.parametrize("raw", [b"not json", b"\xff\xfe", b"[]", b'"str"', b""])
def test_malformed_json_is_permanent(raw):
    assert reason(raw) == "MALFORMED_JSON"


def test_legacy_source_service_field_is_rejected_by_contract():
    body = envelope()
    del body["producer"]
    body["source_service"] = "ballot-service"
    assert reason(body) == "INVALID_ENVELOPE"


@pytest.mark.parametrize("missing", ["event_id", "event_type", "occurred_at", "correlation_id", "payload", "producer"])
def test_missing_envelope_field(missing):
    body = envelope()
    del body[missing]
    assert reason(body) == "INVALID_ENVELOPE"


def test_unknown_envelope_field_rejected():
    assert reason(envelope(extra="x")) == "INVALID_ENVELOPE"


def test_major_version_unknown():
    assert reason(envelope(schema_version="2.0")) == "UNSUPPORTED_SCHEMA_VERSION"


def test_minor_version_bump_is_accepted():
    parse_vote_accepted(encode(envelope(schema_version="1.7")))


def test_wrong_event_type():
    assert reason(envelope(event_type="ElectionOpened")) == "UNEXPECTED_EVENT_TYPE"


def test_wrong_producer():
    assert reason(envelope(producer="auth-service")) == "UNEXPECTED_PRODUCER"


def test_naive_occurred_at():
    assert reason(envelope(occurred_at="2026-10-12T08:20:11")) == "INVALID_ENVELOPE"


@pytest.mark.parametrize("missing", ["election_id", "ballot_id", "receipt_id", "accepted_at", "ballot_commitment"])
def test_missing_payload_field(missing):
    body = envelope()
    del body["payload"][missing]
    assert reason(body) == "INVALID_PAYLOAD"


@pytest.mark.parametrize("commitment", ["short", "A" * 64, "g" * 64, "a" * 63])
def test_bad_commitment(commitment):
    body = envelope()
    body["payload"]["ballot_commitment"] = commitment
    assert reason(body) == "INVALID_PAYLOAD"


def test_naive_accepted_at():
    body = envelope()
    body["payload"]["accepted_at"] = "2026-10-12T08:20:11"
    assert reason(body) == "INVALID_PAYLOAD"


def test_candidate_id_in_payload_is_never_stored():
    body = envelope()
    body["payload"]["candidate_id"] = CANDIDATE
    parsed = parse_vote_accepted(encode(body))
    assert CANDIDATE not in json.dumps(parsed.payload_public)
