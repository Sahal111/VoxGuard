"""Business logic service layer for voter-service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import compute_eligibility_ref
from app.infrastructure.models import (
    Candidate,
    Election,
    OutboxEvent,
    Voter,
    VotingEligibility,
)
from app.schemas import (
    CandidateCreateRequest,
    CandidateResponse,
    ElectionCreateRequest,
    ElectionDetailResponse,
    ElectionSummaryResponse,
    PageMetadata,
    PageResponse,
    VoterImportItem,
)
# pyrefly: ignore [missing-import]
from voxguard_contracts.events import EventType


class VoterError(Exception):
    """Structured error for voter-service operations."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ── Elections ───────────────────────────────────────────────────
async def create_election(
    db: AsyncSession,
    *,
    data: ElectionCreateRequest,
    creator_id: uuid.UUID,
) -> Election:
    """Create a new election in DRAFT status."""
    if data.is_attack_lab and not settings.ATTACK_LAB_ENABLED:
        raise VoterError("FORBIDDEN", "Attack Lab election creation is currently disabled.", 403)

    election = Election(
        id=uuid.uuid4(),
        title=data.title,
        description=data.description,
        status="DRAFT",
        start_at=data.start_at,
        end_at=data.end_at,
        is_attack_lab=data.is_attack_lab,
        created_by=creator_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(election)
    await db.commit()
    await db.refresh(election)
    return election


async def get_election_by_id(
    db: AsyncSession,
    election_id: uuid.UUID,
    caller_role: str,
) -> ElectionDetailResponse:
    """Retrieve election details with candidates and optional role-specific counts."""
    query = (
        select(Election)
        .where(Election.id == election_id)
        .options(selectinload(Election.candidates))
    )
    result = await db.execute(query)
    election: Election | None = result.scalar_one_or_none()

    if election is None:
        raise VoterError("NOT_FOUND", "Election not found.", 404)

    # VOTER & AUDITOR cannot see DRAFT elections per API Contract §5.3
    if election.status == "DRAFT" and caller_role in ("VOTER", "AUDITOR"):
        raise VoterError("NOT_FOUND", "Election not found.", 404)

    candidates_resp = [
        CandidateResponse.model_validate(c) for c in election.candidates
    ]

    voter_count = None
    participation_count = None

    if caller_role in ("ADMIN", "AUDITOR"):
        # Count total voters
        voter_cnt_res = await db.execute(
            select(func.count(Voter.id)).where(Voter.election_id == election_id)
        )
        voter_count = voter_cnt_res.scalar() or 0

        # Count voted
        part_cnt_res = await db.execute(
            select(func.count(VotingEligibility.id)).where(
                VotingEligibility.election_id == election_id,
                VotingEligibility.status == "VOTED",
            )
        )
        participation_count = part_cnt_res.scalar() or 0

    return ElectionDetailResponse(
        id=election.id,
        title=election.title,
        description=election.description,
        status=election.status,
        start_at=election.start_at,
        end_at=election.end_at,
        opened_at=election.opened_at,
        closed_at=election.closed_at,
        finalized_at=election.finalized_at,
        is_attack_lab=election.is_attack_lab,
        candidates=candidates_resp,
        created_at=election.created_at,
        voter_count=voter_count,
        participation_count=participation_count,
    )


async def list_elections(
    db: AsyncSession,
    *,
    status_filter: str | None = None,
    sort_by: str = "created_at",
    page: int = 1,
    page_size: int = 20,
    caller_role: str = "VOTER",
) -> PageResponse:
    """List elections with pagination and role-based visibility filtering."""
    query = select(Election)

    if caller_role in ("VOTER", "AUDITOR"):
        query = query.where(Election.status != "DRAFT")

    if status_filter:
        query = query.where(Election.status == status_filter.upper())

    # Total count
    count_query = select(func.count()).select_from(query.subquery())
    total_res = await db.execute(count_query)
    total = total_res.scalar() or 0

    # Sorting
    if sort_by == "start_at":
        query = query.order_by(Election.start_at.desc())
    else:
        query = query.order_by(Election.created_at.desc())

    # Pagination
    offset = max(0, (page - 1) * page_size)
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    elections = result.scalars().all()

    items = [
        ElectionSummaryResponse(
            id=e.id,
            title=e.title,
            status=e.status,
            start_at=e.start_at,
            end_at=e.end_at,
        )
        for e in elections
    ]

    return PageResponse(
        items=items,
        page=PageMetadata(page=page, page_size=page_size, total=total),
    )


# ── Candidates ──────────────────────────────────────────────────
async def add_candidate(
    db: AsyncSession,
    election_id: uuid.UUID,
    data: CandidateCreateRequest,
) -> CandidateResponse:
    """Add a candidate to an election in DRAFT status."""
    result = await db.execute(select(Election).where(Election.id == election_id))
    election = result.scalar_one_or_none()
    if election is None:
        raise VoterError("NOT_FOUND", "Election not found.", 404)

    if election.status != "DRAFT":
        raise VoterError(
            "ELECTION_INVALID_STATE",
            f"Candidates can only be modified in DRAFT state. Current status is {election.status}.",
            409,
        )

    candidate = Candidate(
        id=uuid.uuid4(),
        election_id=election_id,
        name=data.name.strip(),
        description=data.description.strip(),
        ballot_order=data.ballot_order,
        created_at=datetime.now(timezone.utc),
    )
    db.add(candidate)
    try:
        await db.commit()
        await db.refresh(candidate)
    except IntegrityError:
        await db.rollback()
        raise VoterError(
            "CONFLICT",
            "A candidate with this name or ballot_order already exists in this election.",
            409,
        )

    return CandidateResponse.model_validate(candidate)


# ── Voter Registration / Import ─────────────────────────────────
async def import_voters(
    db: AsyncSession,
    election_id: uuid.UUID,
    voters_list: list[VoterImportItem],
) -> int:
    """Import eligible voters in batch for an election in DRAFT status (all-or-nothing)."""
    result = await db.execute(select(Election).where(Election.id == election_id))
    election = result.scalar_one_or_none()
    if election is None:
        raise VoterError("NOT_FOUND", "Election not found.", 404)

    if election.status != "DRAFT":
        raise VoterError(
            "ELECTION_INVALID_STATE",
            f"Voters can only be imported in DRAFT state. Current status is {election.status}.",
            409,
        )

    # In-batch duplicate validation
    seen_emails: set[str] = set()
    seen_refs: set[str] = set()
    for item in voters_list:
        if item.email in seen_emails:
            raise VoterError(
                "UNPROCESSABLE_ENTITY",
                f"Duplicate email '{item.email}' found within import batch.",
                422,
            )
        if item.external_ref in seen_refs:
            raise VoterError(
                "UNPROCESSABLE_ENTITY",
                f"Duplicate external_ref '{item.external_ref}' found within import batch.",
                422,
            )
        seen_emails.add(item.email)
        seen_refs.add(item.external_ref)

    now = datetime.now(timezone.utc)
    voter_models = [
        Voter(
            id=uuid.uuid4(),
            election_id=election_id,
            email_normalized=item.email,
            external_ref=item.external_ref,
            display_label=item.display_label,
            user_id=None,
            created_at=now,
        )
        for item in voters_list
    ]

    db.add_all(voter_models)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise VoterError(
            "CONFLICT",
            "One or more voters are already registered in this election.",
            409,
        )

    return len(voter_models)


# ── Lifecycle Transitions ───────────────────────────────────────
async def schedule_election(
    db: AsyncSession,
    election_id: uuid.UUID,
) -> Election:
    """Transition election DRAFT -> SCHEDULED. Freezes candidates and computes eligibility."""
    query = (
        select(Election)
        .where(Election.id == election_id)
        .options(selectinload(Election.candidates), selectinload(Election.voters))
        .with_for_update()
    )
    result = await db.execute(query)
    election = result.scalar_one_or_none()

    if election is None:
        raise VoterError("NOT_FOUND", "Election not found.", 404)

    if election.status != "DRAFT":
        raise VoterError(
            "ELECTION_INVALID_STATE",
            f"Cannot schedule election in status '{election.status}'. Must be DRAFT.",
            409,
        )

    if len(election.candidates) < 2:
        raise VoterError(
            "UNPROCESSABLE_ENTITY",
            "Election requires at least 2 candidates to be scheduled.",
            422,
        )

    if len(election.voters) < 1:
        raise VoterError(
            "UNPROCESSABLE_ENTITY",
            "Election requires at least 1 registered voter to be scheduled.",
            422,
        )

    now = datetime.now(timezone.utc)
    if election.end_at <= now:
        raise VoterError(
            "UNPROCESSABLE_ENTITY",
            "Election end_at must be in the future.",
            422,
        )

    # Compute and insert VotingEligibility records
    eligibility_records = []
    for voter in election.voters:
        eligibility_ref = compute_eligibility_ref(
            settings.ELIGIBILITY_PEPPER,
            election.id,
            voter.id,
        )
        eligibility_records.append(
            VotingEligibility(
                id=uuid.uuid4(),
                election_id=election.id,
                voter_id=voter.id,
                eligibility_ref=eligibility_ref,
                status="ELIGIBLE",
                created_at=now,
                updated_at=now,
            )
        )

    db.add_all(eligibility_records)
    election.status = "SCHEDULED"
    election.updated_at = now
    election.version += 1

    await db.commit()
    await db.refresh(election)
    return election


async def open_election(
    db: AsyncSession,
    election_id: uuid.UUID,
    correlation_id: uuid.UUID | None = None,
) -> Election:
    """Transition election SCHEDULED -> OPEN and write ElectionOpened event to outbox."""
    query = select(Election).where(Election.id == election_id).with_for_update()
    result = await db.execute(query)
    election = result.scalar_one_or_none()

    if election is None:
        raise VoterError("NOT_FOUND", "Election not found.", 404)

    if election.status != "SCHEDULED":
        raise VoterError(
            "ELECTION_INVALID_STATE",
            f"Cannot open election in status '{election.status}'. Must be SCHEDULED.",
            409,
        )

    now = datetime.now(timezone.utc)
    if now >= election.end_at:
        raise VoterError(
            "ELECTION_INVALID_STATE",
            "Election end time has already passed; cannot open.",
            409,
        )

    election.status = "OPEN"
    election.opened_at = now
    election.updated_at = now
    election.version += 1

    # Outbox event
    cid = correlation_id or uuid.uuid4()
    outbox = OutboxEvent(
        id=uuid.uuid4(),
        event_type=EventType.ELECTION_OPENED.value,
        routing_key="election.opened",
        schema_version="1.0",
        correlation_id=cid,
        payload={
            "election_id": str(election.id),
            "opened_at": now.isoformat(),
            "start_at": election.start_at.isoformat(),
            "end_at": election.end_at.isoformat(),
        },
        status="PENDING",
        created_at=now,
        next_attempt_at=now,
    )
    db.add(outbox)

    await db.commit()
    await db.refresh(election)
    return election


async def close_election(
    db: AsyncSession,
    election_id: uuid.UUID,
    correlation_id: uuid.UUID | None = None,
) -> Election:
    """Transition election OPEN -> CLOSED and write ElectionClosed event to outbox."""
    query = select(Election).where(Election.id == election_id).with_for_update()
    result = await db.execute(query)
    election = result.scalar_one_or_none()

    if election is None:
        raise VoterError("NOT_FOUND", "Election not found.", 404)

    if election.status != "OPEN":
        raise VoterError(
            "ELECTION_INVALID_STATE",
            f"Cannot close election in status '{election.status}'. Must be OPEN.",
            409,
        )

    now = datetime.now(timezone.utc)
    election.status = "CLOSED"
    election.closed_at = now
    election.updated_at = now
    election.version += 1

    # Outbox event
    cid = correlation_id or uuid.uuid4()
    outbox = OutboxEvent(
        id=uuid.uuid4(),
        event_type=EventType.ELECTION_CLOSED.value,
        routing_key="election.closed",
        schema_version="1.0",
        correlation_id=cid,
        payload={
            "election_id": str(election.id),
            "closed_at": now.isoformat(),
        },
        status="PENDING",
        created_at=now,
        next_attempt_at=now,
    )
    db.add(outbox)

    await db.commit()
    await db.refresh(election)
    return election


# ── Internal Service-to-Service Queries ─────────────────────────
async def get_ballot_info(
    db: AsyncSession,
    election_id: uuid.UUID,
) -> dict:
    """Internal query for ballot-service: election status and candidates."""
    query = (
        select(Election)
        .where(Election.id == election_id)
        .options(selectinload(Election.candidates))
    )
    result = await db.execute(query)
    election = result.scalar_one_or_none()

    if election is None:
        raise VoterError("NOT_FOUND", "Election not found.", 404)

    return {
        "election_id": election.id,
        "title": election.title,
        "status": election.status,
        "end_at": election.end_at,
        "candidates": [
            CandidateResponse.model_validate(c) for c in election.candidates
        ],
    }


async def issue_vote_ticket(
    db: AsyncSession,
    election_id: uuid.UUID,
    user_id: uuid.UUID,
    user_email: str | None = None,
) -> dict:
    """Internal ticket issuance: links user account, marks eligibility TICKET_ISSUED, returns pseudonym."""
    res_elec = await db.execute(select(Election).where(Election.id == election_id))
    election = res_elec.scalar_one_or_none()
    if election is None:
        raise VoterError("NOT_FOUND", "Election not found.", 404)

    if election.status != "OPEN":
        raise VoterError("ELECTION_NOT_OPEN", "Election is not currently OPEN for voting.", 400)

    # Find voter record by user_id or matching email
    voter_query = select(Voter).where(Voter.election_id == election_id)
    if user_email:
        voter_query = voter_query.where(
            (Voter.user_id == user_id) | (Voter.email_normalized == user_email.lower().strip())
        )
    else:
        voter_query = voter_query.where(Voter.user_id == user_id)

    res_voter = await db.execute(voter_query)
    voter = res_voter.scalar_one_or_none()
    if voter is None:
        raise VoterError("NOT_ELIGIBLE", "Voter is not registered in this election.", 403)

    # Link user_id if not yet bound
    if voter.user_id is None:
        voter.user_id = user_id

    # Fetch eligibility
    res_elig = await db.execute(
        select(VotingEligibility)
        .where(
            VotingEligibility.election_id == election_id,
            VotingEligibility.voter_id == voter.id,
        )
        .with_for_update()
    )
    eligibility = res_elig.scalar_one_or_none()
    if eligibility is None:
        raise VoterError("NOT_ELIGIBLE", "Eligibility record not found.", 403)

    if eligibility.status == "VOTED":
        raise VoterError("VOTER_ALREADY_VOTED", "Hak memilih ini sudah digunakan.", 409)

    if eligibility.status not in ("ELIGIBLE", "TICKET_ISSUED"):
        raise VoterError("NOT_ELIGIBLE", f"Voter status is {eligibility.status}.", 403)

    now = datetime.now(timezone.utc)
    eligibility.status = "TICKET_ISSUED"
    eligibility.ticket_issued_at = now
    eligibility.updated_at = now

    await db.commit()

    return {
        "election_id": election_id,
        "eligibility_ref": eligibility.eligibility_ref,
        "status": eligibility.status,
    }


async def get_election_summary_internal(
    db: AsyncSession,
    election_id: uuid.UUID,
) -> dict:
    """Internal summary for result-service."""
    query = (
        select(Election)
        .where(Election.id == election_id)
        .options(selectinload(Election.candidates))
    )
    result = await db.execute(query)
    election = result.scalar_one_or_none()
    if election is None:
        raise VoterError("NOT_FOUND", "Election not found.", 404)

    total_elig_res = await db.execute(
        select(func.count(VotingEligibility.id)).where(VotingEligibility.election_id == election_id)
    )
    total_eligible = total_elig_res.scalar() or 0

    total_voted_res = await db.execute(
        select(func.count(VotingEligibility.id)).where(
            VotingEligibility.election_id == election_id,
            VotingEligibility.status == "VOTED",
        )
    )
    total_voted = total_voted_res.scalar() or 0

    return {
        "election_id": election.id,
        "title": election.title,
        "status": election.status,
        "closed_at": election.closed_at,
        "candidates": [
            CandidateResponse.model_validate(c) for c in election.candidates
        ],
        "total_eligible": total_eligible,
        "total_voted": total_voted,
    }
