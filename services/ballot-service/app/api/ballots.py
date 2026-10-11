"""Ballot API router — POST /api/v1/ballots and GET /api/v1/ballots/receipt/{id}.

Per API Contract §5.4, §6.1-6.2.
"""

from __future__ import annotations

import re
import uuid
import logging

import jwt
from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_voter_payload
from app.core.security import compute_receipt_code, decode_vote_ticket
from app.infrastructure.database import get_session
from app.schemas import BallotReceiptResponse, ReceiptLookupResponse
from app.services import BallotError, cast_vote, get_receipt, _validate_election_open

logger = logging.getLogger("ballot_service.api")

router = APIRouter(prefix="/api/v1/ballots", tags=["Ballots"])

_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def _error_response(request: Request, exc: BallotError) -> JSONResponse:
    rid = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": [],
                "request_id": rid,
            }
        },
    )


def _validation_error(request: Request, field: str, issue: str) -> JSONResponse:
    rid = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Input tidak valid.",
                "details": [{"field": field, "issue": issue}],
                "request_id": rid,
            }
        },
    )


# ── POST /api/v1/ballots ────────────────────────────────────────
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Cast a vote (castBallot)",
    operation_id="castBallot",
)
async def handle_cast_ballot(
    request: Request,
    _voter_payload: dict = Depends(get_current_voter_payload),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_session),
):
    """POST /api/v1/ballots — Cast a ballot.

    Header: Authorization: Bearer <access_token> (role=VOTER)
    Header: Idempotency-Key: <16-64 chars [A-Za-z0-9_-]>
    Body: { election_id, candidate_id, vote_ticket }

    Returns 201 on success, 200 on idempotent replay.
    """
    rid = getattr(request.state, "request_id", "unknown")
    correlation_id_str = getattr(request.state, "correlation_id", rid)
    try:
        correlation_id = uuid.UUID(correlation_id_str)
    except ValueError:
        correlation_id = uuid.uuid4()

    # ── 1. Validate Idempotency-Key header ───────────────────────
    if not idempotency_key:
        return _validation_error(request, "Idempotency-Key", "Header wajib ada.")
    if not _IDEMPOTENCY_KEY_RE.match(idempotency_key):
        return _validation_error(
            request,
            "Idempotency-Key",
            "Format tidak valid. Gunakan 16-64 karakter [A-Za-z0-9_-].",
        )

    # ── 2. Parse request body ────────────────────────────────────
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request body tidak valid JSON.",
                    "details": [],
                    "request_id": rid,
                }
            },
        )

    election_id_raw = body.get("election_id")
    candidate_id_raw = body.get("candidate_id")
    vote_ticket = body.get("vote_ticket")

    if not election_id_raw or not candidate_id_raw or not vote_ticket:
        return _validation_error(request, "body", "election_id, candidate_id, vote_ticket wajib ada.")

    try:
        election_id = uuid.UUID(str(election_id_raw))
        candidate_id = uuid.UUID(str(candidate_id_raw))
    except ValueError:
        return _validation_error(request, "election_id/candidate_id", "Format UUID tidak valid.")

    # ── 3. Validate vote_ticket (JWT) ────────────────────────────
    try:
        ticket_payload = decode_vote_ticket(vote_ticket, election_id)
    except jwt.ExpiredSignatureError:
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "VOTE_TICKET_INVALID",
                    "message": "Vote ticket telah kedaluwarsa.",
                    "details": [],
                    "request_id": rid,
                }
            },
        )
    except Exception as exc:
        logger.info(
            "vote_ticket_invalid",
            extra={"election_id": str(election_id), "reason": type(exc).__name__},
        )
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "VOTE_TICKET_INVALID",
                    "message": "Vote ticket tidak valid atau bukan untuk pemilihan ini.",
                    "details": [],
                    "request_id": rid,
                }
            },
        )

    eligibility_ref: str = ticket_payload.get("sub", "")
    if not eligibility_ref or len(eligibility_ref) != 64:
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "VOTE_TICKET_INVALID",
                    "message": "Vote ticket mengandung eligibility_ref yang tidak valid.",
                    "details": [],
                    "request_id": rid,
                }
            },
        )

    # ── 4. Validate election is OPEN (fail-closed) ───────────────
    try:
        ballot_info = await _validate_election_open(election_id)
    except BallotError as exc:
        return _error_response(request, exc)

    # ── 5. Cast vote in atomic transaction ───────────────────────
    try:
        receipt_dict, is_replay = await cast_vote(
            db,
            election_id=election_id,
            candidate_id=candidate_id,
            eligibility_ref=eligibility_ref,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            ballot_info=ballot_info,
        )
    except BallotError as exc:
        return _error_response(request, exc)

    response = BallotReceiptResponse(
        receipt_id=uuid.UUID(receipt_dict["receipt_id"]),
        receipt_code=receipt_dict["receipt_code"],
        election_id=uuid.UUID(receipt_dict["election_id"]),
        accepted_at=receipt_dict["accepted_at"],
        audit_status=receipt_dict.get("audit_status", "PENDING"),
    )

    if is_replay:
        return JSONResponse(
            status_code=200,
            content=response.model_dump(mode="json"),
            headers={"Idempotent-Replayed": "true"},
        )
    return JSONResponse(
        status_code=201,
        content=response.model_dump(mode="json"),
    )


# ── GET /api/v1/ballots/receipt/{receipt_id} ────────────────────
@router.get(
    "/receipt/{receipt_id}",
    status_code=status.HTTP_200_OK,
    response_model=ReceiptLookupResponse,
    summary="Get ballot receipt status (getReceipt)",
    operation_id="getReceipt",
)
async def handle_get_receipt(
    request: Request,
    receipt_id: uuid.UUID,
    _voter_payload: dict = Depends(get_current_voter_payload),
    db: AsyncSession = Depends(get_session),
):
    """GET /api/v1/ballots/receipt/{receipt_id} — Check receipt status.

    Header: X-Receipt-Code (required per API Contract §5.4 No.16).
    Returns receipt without candidate choice, eligibility_ref, or voter identity.
    Error 404 if id not found OR receipt_code wrong (not differentiated per contract).
    audit_status: PENDING | RECORDED.
    """
    import secrets as _secrets
    rid = getattr(request.state, "request_id", "unknown")

    # ── Validate X-Receipt-Code header ───────────────────────────
    provided_code = request.headers.get("x-receipt-code", "").strip()
    if not provided_code:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Header X-Receipt-Code wajib ada.",
                    "details": [{"field": "X-Receipt-Code", "issue": "Header wajib ada."}],
                    "request_id": rid,
                }
            },
        )

    # Compute expected code and constant-time compare
    expected_code = compute_receipt_code(receipt_id)
    if not _secrets.compare_digest(provided_code, expected_code):
        # Return 404 (same as not found — per contract, not differentiated)
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "RECEIPT_NOT_FOUND",
                    "message": "Receipt tidak ditemukan.",
                    "details": [],
                    "request_id": rid,
                }
            },
        )

    # ── Fetch receipt data ────────────────────────────────────────
    try:
        data = await get_receipt(db, receipt_id=receipt_id)
    except BallotError as exc:
        return _error_response(request, exc)
    return ReceiptLookupResponse(**data)
