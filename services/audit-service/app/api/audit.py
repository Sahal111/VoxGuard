"""Audit endpoints: GET /audit/events, /audit/elections/{id}/verify, /proof.

API Contract §4 #17-19. Only allowlisted `payload_public` ever leaves this
service; no identity, candidate choice, eligibility_ref, nonce or token exists in
the audit tables, and the output is projected through the allowlist again as
defense in depth.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuditError, require_roles
from app.core.security import project_payload
from app.infrastructure.database import get_session
from app.schemas import (
    AuditEventOut,
    AuditEventPage,
    PageInfo,
    ProofResponse,
    VerifyAuditResponse,
)
from app.services.chain import GLOBAL_SCOPE_ID, build_proof, list_events, verify_chain

router = APIRouter(prefix="/api/v1/audit", tags=["Audit"])

MAX_PAGE_SIZE = 100


@router.get("/events", response_model=AuditEventPage, operation_id="listAuditEvents")
async def list_audit_events(
    election_id: uuid.UUID | None = Query(None, description="Empty → GLOBAL scope"),
    event_type: str | None = Query(None, max_length=64),
    from_sequence: int | None = Query(None, ge=1),
    to_sequence: int | None = Query(None, ge=1),
    order: Literal["asc", "desc"] = Query("asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    _user: dict = Depends(require_roles("ADMIN", "AUDITOR")),
    db: AsyncSession = Depends(get_session),
):
    rows, total = await list_events(
        db,
        scope_id=election_id or GLOBAL_SCOPE_ID,
        event_type=event_type,
        from_sequence=from_sequence,
        to_sequence=to_sequence,
        order=order,
        page=page,
        page_size=page_size,
    )
    items = []
    for row in rows:
        item = AuditEventOut.model_validate(row)
        item.payload_public = project_payload(row.source_event_type, row.payload_public)
        items.append(item)
    return AuditEventPage(items=items, page=PageInfo(page=page, page_size=page_size, total=total))


@router.get(
    "/elections/{election_id}/verify",
    response_model=VerifyAuditResponse,
    operation_id="verifyAuditChain",
)
async def verify_audit_chain(
    election_id: uuid.UUID,
    user: dict = Depends(require_roles("ADMIN", "AUDITOR")),
    db: AsyncSession = Depends(get_session),
):
    """Integrity failures are reported in the body (status=INVALID), not as HTTP errors."""
    try:
        requested_by = uuid.UUID(str(user.get("sub")))
    except ValueError:
        requested_by = None
    outcome = await verify_chain(db, election_id, requested_by)
    if outcome is None:
        raise AuditError("NOT_FOUND", "Catatan audit untuk pemilihan ini tidak tersedia.", 404)
    return VerifyAuditResponse(
        check_id=outcome.check_id,
        election_id=outcome.scope_id,
        status=outcome.status,
        events_checked=outcome.events_checked,
        head_sequence=outcome.head_sequence,
        head_hash=outcome.head_hash,
        first_failure=outcome.first_failure,
        checkpoint=outcome.checkpoint,
        checked_at=outcome.checked_at,
    )


@router.get(
    "/elections/{election_id}/proof",
    response_model=ProofResponse,
    operation_id="getAuditProof",
)
async def get_audit_proof(
    election_id: uuid.UUID,
    receipt_id: uuid.UUID | None = Query(None),
    _user: dict = Depends(require_roles("ADMIN", "AUDITOR", "VOTER")),
    db: AsyncSession = Depends(get_session),
):
    """Proof facts only: hashes and counts. `valid` here never means 'system uncompromised'."""
    proof = await build_proof(db, election_id, receipt_id)
    if proof is None:
        raise AuditError("NOT_FOUND", "Catatan audit untuk pemilihan ini tidak tersedia.", 404)
    return ProofResponse(**proof)
