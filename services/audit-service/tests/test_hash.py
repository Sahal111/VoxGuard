"""UT-HASH: hash-chain canonicalisation is deterministic and covers every field."""

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import canonical_timestamp, compute_event_hash

SCOPE = uuid.UUID("6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3")
SRC = uuid.UUID("0c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f")
CORR = uuid.UUID("7a9c1e3f-5b7d-4f91-8a23-4c6e8a0b2d47")
WHEN = datetime(2026, 10, 12, 8, 20, 11, 123456, tzinfo=timezone.utc)
GENESIS = "0" * 64
PAYLOAD = {"election_id": str(SCOPE), "receipt_id": "r1", "ballot_commitment": "c" * 64}


def h(**override):
    args = dict(
        scope_id=SCOPE, sequence=1, source_event_id=SRC, source_event_type="VoteAccepted",
        occurred_at=WHEN, correlation_id=CORR, payload_public=PAYLOAD, prev_hash=GENESIS,
    )
    args.update(override)
    return compute_event_hash(**args)


def test_known_answer_matches_spec_canonical_form():
    # Independent re-statement of SAD §12: sorted keys, no spaces, UTF-8, µs UTC timestamps.
    canonical = (
        '{"correlation_id":"%s","occurred_at":"2026-10-12T08:20:11.123456Z",'
        '"payload_public":%s,"prev_hash":"%s","scope_id":"%s","sequence":1,'
        '"source_event_id":"%s","source_event_type":"VoteAccepted"}'
        % (CORR, json.dumps(PAYLOAD, sort_keys=True, separators=(",", ":")), GENESIS, SCOPE, SRC)
    )
    assert h() == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_deterministic_and_hex():
    assert h() == h()
    assert len(h()) == 64 and h() == h().lower()


def test_payload_key_order_does_not_matter():
    assert h(payload_public=dict(reversed(list(PAYLOAD.items())))) == h()


def test_timezone_representation_does_not_matter():
    jakarta = WHEN.astimezone(timezone(timedelta(hours=7)))
    assert h(occurred_at=jakarta) == h()


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope_id", uuid.uuid4()),
        ("sequence", 2),
        ("source_event_id", uuid.uuid4()),
        ("source_event_type", "VoteRejected"),
        ("occurred_at", WHEN + timedelta(microseconds=1)),
        ("correlation_id", uuid.uuid4()),
        ("payload_public", {**PAYLOAD, "receipt_id": "r2"}),
        ("prev_hash", "1" * 64),
    ],
)
def test_every_field_changes_the_hash(field, value):
    assert h(**{field: value}) != h()


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError):
        canonical_timestamp(datetime(2026, 10, 12, 8, 20, 11))
