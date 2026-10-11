"""Internal service-to-service router for voter-service per API Contract Specification §3.3."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_internal_call
from app.infrastructure.database import get_session
from app.schemas import (
    BallotInfoResponse,
    ElectionSummaryInternalResponse,
    IssueTicketRequest,
    IssueTicketResponse,
)
from app.services import (
    VoterError,
    get_ballot_info,
    get_election_summary_internal,
    issue_vote_ticket,
)

router = APIRouter(prefix="/internal/v1/elections", tags=["internal"])


def _voter_error_response(request: Request, exc: VoterError) -> JSONResponse:
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


# ── GET /internal/v1/elections/{id}/ballot-info ────────────────
@router.get(
    "/{id}/ballot-info",
    status_code=status.HTTP_200_OK,
    response_model=BallotInfoResponse,
    summary="Internal endpoint for ballot-service to get election info and candidate list",
)
async def handle_get_ballot_info(
    request: Request,
    id: uuid.UUID,
    _auth: None = Depends(require_internal_call),
    db: AsyncSession = Depends(get_session),
):
    try:
        data = await get_ballot_info(db, election_id=id)
        return BallotInfoResponse(**data)
    except VoterError as exc:
        return _voter_error_response(request, exc)


# ── POST /internal/v1/elections/{id}/eligibility/tickets ───────
@router.post(
    "/{id}/eligibility/tickets",
    status_code=status.HTTP_200_OK,
    response_model=IssueTicketResponse,
    summary="Internal endpoint for ticket issuance (verifies voter and produces pseudonym)",
)
async def handle_issue_ticket(
    request: Request,
    id: uuid.UUID,
    body: IssueTicketRequest,
    _auth: None = Depends(require_internal_call),
    db: AsyncSession = Depends(get_session),
):
    try:
        data = await issue_vote_ticket(
            db,
            election_id=id,
            user_id=body.user_id,
            user_email=body.email,
        )
        return IssueTicketResponse(**data)
    except VoterError as exc:
        return _voter_error_response(request, exc)


# ── GET /internal/v1/elections/{id}/summary ────────────────────
@router.get(
    "/{id}/summary",
    status_code=status.HTTP_200_OK,
    response_model=ElectionSummaryInternalResponse,
    summary="Internal endpoint for result-service to reconcile election summary",
)
async def handle_get_summary(
    request: Request,
    id: uuid.UUID,
    _auth: None = Depends(require_internal_call),
    db: AsyncSession = Depends(get_session),
):
    try:
        data = await get_election_summary_internal(db, election_id=id)
        return ElectionSummaryInternalResponse(**data)
    except VoterError as exc:
        return _voter_error_response(request, exc)
