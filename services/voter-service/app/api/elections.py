"""Elections API router for voter-service per API Contract Specification §5.3."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin, require_any_authenticated
from app.infrastructure.database import get_session
from app.schemas import (
    CandidateCreateRequest,
    CandidateResponse,
    ElectionCreateRequest,
    ElectionDetailResponse,
    ElectionStatusResponse,
    PageResponse,
    VoterImportRequest,
    VoterImportResponse,
)
from app.services import (
    VoterError,
    add_candidate,
    close_election,
    create_election,
    get_election_by_id,
    import_voters,
    list_elections,
    open_election,
    schedule_election,
)

router = APIRouter(prefix="/api/v1/elections", tags=["elections"])


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


# ── POST /api/v1/elections ─────────────────────────────────────
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ElectionDetailResponse,
    summary="Create a new election in DRAFT status",
)
async def handle_create_election(
    request: Request,
    body: ElectionCreateRequest,
    admin_payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    creator_id = uuid.UUID(admin_payload["sub"])
    try:
        election = await create_election(db, data=body, creator_id=creator_id)
        # Fetch detailed format
        return await get_election_by_id(db, election.id, caller_role="ADMIN")
    except VoterError as exc:
        return _voter_error_response(request, exc)


# ── GET /api/v1/elections ──────────────────────────────────────
@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=PageResponse,
    summary="List elections with pagination and filtering",
)
async def handle_list_elections(
    request: Request,
    status_filter: str | None = Query(None, alias="status"),
    sort: str = Query("created_at", pattern="^(created_at|start_at)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth_payload: dict = Depends(require_any_authenticated),
    db: AsyncSession = Depends(get_session),
):
    caller_role = auth_payload.get("role", "VOTER")
    try:
        return await list_elections(
            db,
            status_filter=status_filter,
            sort_by=sort,
            page=page,
            page_size=page_size,
            caller_role=caller_role,
        )
    except VoterError as exc:
        return _voter_error_response(request, exc)


# ── GET /api/v1/elections/{id} ─────────────────────────────────
@router.get(
    "/{id}",
    status_code=status.HTTP_200_OK,
    response_model=ElectionDetailResponse,
    summary="Get election details and candidate list",
)
async def handle_get_election(
    request: Request,
    id: uuid.UUID,
    auth_payload: dict = Depends(require_any_authenticated),
    db: AsyncSession = Depends(get_session),
):
    caller_role = auth_payload.get("role", "VOTER")
    try:
        return await get_election_by_id(db, id, caller_role=caller_role)
    except VoterError as exc:
        return _voter_error_response(request, exc)


# ── POST /api/v1/elections/{id}/candidates ─────────────────────
@router.post(
    "/{id}/candidates",
    status_code=status.HTTP_201_CREATED,
    response_model=CandidateResponse,
    summary="Add candidate to an election in DRAFT status",
)
async def handle_add_candidate(
    request: Request,
    id: uuid.UUID,
    body: CandidateCreateRequest,
    _admin_payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await add_candidate(db, election_id=id, data=body)
    except VoterError as exc:
        return _voter_error_response(request, exc)


# ── POST /api/v1/elections/{id}/voters/import ──────────────────
@router.post(
    "/{id}/voters/import",
    status_code=status.HTTP_201_CREATED,
    response_model=VoterImportResponse,
    summary="Import registered voters in batch",
)
async def handle_import_voters(
    request: Request,
    id: uuid.UUID,
    body: VoterImportRequest,
    _admin_payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    try:
        count = await import_voters(db, election_id=id, voters_list=body.voters)
        return VoterImportResponse(election_id=id, imported=count)
    except VoterError as exc:
        return _voter_error_response(request, exc)


# ── POST /api/v1/elections/{id}/schedule ───────────────────────
@router.post(
    "/{id}/schedule",
    status_code=status.HTTP_200_OK,
    response_model=ElectionStatusResponse,
    summary="Transition election DRAFT -> SCHEDULED and generate eligibility",
)
async def handle_schedule_election(
    request: Request,
    id: uuid.UUID,
    _admin_payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    try:
        election = await schedule_election(db, election_id=id)
        return ElectionStatusResponse(
            id=election.id,
            status=election.status,
            opened_at=election.opened_at,
            closed_at=election.closed_at,
        )
    except VoterError as exc:
        return _voter_error_response(request, exc)


# ── POST /api/v1/elections/{id}/open ───────────────────────────
@router.post(
    "/{id}/open",
    status_code=status.HTTP_200_OK,
    response_model=ElectionStatusResponse,
    summary="Transition election SCHEDULED -> OPEN and emit ElectionOpened event",
)
async def handle_open_election(
    request: Request,
    id: uuid.UUID,
    _admin_payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    cid_str = getattr(request.state, "correlation_id", None)
    cid = uuid.UUID(cid_str) if cid_str else None
    try:
        election = await open_election(db, election_id=id, correlation_id=cid)
        return ElectionStatusResponse(
            id=election.id,
            status=election.status,
            opened_at=election.opened_at,
            closed_at=election.closed_at,
        )
    except VoterError as exc:
        return _voter_error_response(request, exc)


# ── POST /api/v1/elections/{id}/close ──────────────────────────
@router.post(
    "/{id}/close",
    status_code=status.HTTP_200_OK,
    response_model=ElectionStatusResponse,
    summary="Transition election OPEN -> CLOSED and emit ElectionClosed event",
)
async def handle_close_election(
    request: Request,
    id: uuid.UUID,
    _admin_payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    cid_str = getattr(request.state, "correlation_id", None)
    cid = uuid.UUID(cid_str) if cid_str else None
    try:
        election = await close_election(db, election_id=id, correlation_id=cid)
        return ElectionStatusResponse(
            id=election.id,
            status=election.status,
            opened_at=election.opened_at,
            closed_at=election.closed_at,
        )
    except VoterError as exc:
        return _voter_error_response(request, exc)
