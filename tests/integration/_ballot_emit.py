"""Helper for test_audit_integration.py — run as a subprocess with cwd=services/ballot-service.

Casts one vote through ballot-service's real cast_vote() (real DB transaction, real
outbox row) and publishes the outbox with the real OutboxPublisher to RabbitMQ.
EMIT_RELAY_ONLY=1 skips the vote and only runs one outbox relay pass.
Prints one JSON line describing what was emitted. Not a test module.
"""

import asyncio
import json
import os
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def main() -> None:
    from app.infrastructure.models import Ballot
    from app.infrastructure.publisher import OutboxPublisher
    from app.services import cast_vote

    engine = create_async_engine(os.environ["BALLOT_DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)

    if os.environ.get("EMIT_RELAY_ONLY"):  # just run one outbox relay pass, cast nothing
        publisher = OutboxPublisher(os.environ["RABBITMQ_URL"], exchange_name=os.environ["EMIT_EXCHANGE"])
        async with factory() as db:
            published = await publisher.process_batch(db)
        await publisher.close()
        await engine.dispose()
        print(json.dumps({"published": published}))
        return

    election_id = uuid.UUID(os.environ["EMIT_ELECTION_ID"])
    candidate_id = uuid.uuid4()
    eligibility_ref = uuid.uuid4().hex + uuid.uuid4().hex  # 64 hex chars

    async with factory() as db:
        receipt, _ = await cast_vote(
            db,
            election_id=election_id,
            candidate_id=candidate_id,
            eligibility_ref=eligibility_ref,
            idempotency_key=uuid.uuid4().hex,
            correlation_id=uuid.uuid4(),
            ballot_info={"candidates": [{"id": str(candidate_id)}]},
        )

    publisher = OutboxPublisher(os.environ["RABBITMQ_URL"], exchange_name=os.environ["EMIT_EXCHANGE"])
    async with factory() as db:
        published = await publisher.process_batch(db)
    await publisher.close()

    async with factory() as db:
        ballot = (
            await db.execute(select(Ballot).where(Ballot.receipt_id == uuid.UUID(receipt["receipt_id"])))
        ).scalar_one()
    await engine.dispose()

    print(
        json.dumps(
            {
                "published": published,
                "event_id": str(ballot.outbox_event_id),
                "ballot_id": str(ballot.id),
                "receipt_id": receipt["receipt_id"],
                "receipt_code": receipt["receipt_code"],
                "ballot_commitment": ballot.ballot_commitment,
                "candidate_id": str(candidate_id),
                "eligibility_ref": eligibility_ref,
            }
        )
    )


asyncio.run(main())
