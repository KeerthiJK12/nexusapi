from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency_record import IdempotencyRecord

IDEMPOTENCY_WINDOW = timedelta(hours=24)
IDEMPOTENCY_PENDING_STATUS = 0


async def get_recent_idempotency_record(
    session: AsyncSession,
    organisation_id: uuid.UUID,
    endpoint: str,
    idempotency_key: str,
) -> IdempotencyRecord | None:
    cutoff = datetime.now(UTC) - IDEMPOTENCY_WINDOW
    query = (
        select(IdempotencyRecord)
        .where(IdempotencyRecord.organisation_id == organisation_id)
        .where(IdempotencyRecord.endpoint == endpoint)
        .where(IdempotencyRecord.idempotency_key == idempotency_key)
        .where(IdempotencyRecord.created_at >= cutoff)
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


def is_finalized(record: IdempotencyRecord) -> bool:
    return record.status_code != IDEMPOTENCY_PENDING_STATUS


async def claim_idempotency_key(
    session: AsyncSession,
    organisation_id: uuid.UUID,
    endpoint: str,
    idempotency_key: str,
) -> tuple[IdempotencyRecord, bool]:
    cutoff = datetime.now(UTC) - IDEMPOTENCY_WINDOW

    delete_stmt = (
        IdempotencyRecord.__table__.delete()
        .where(IdempotencyRecord.organisation_id == organisation_id)
        .where(IdempotencyRecord.endpoint == endpoint)
        .where(IdempotencyRecord.idempotency_key == idempotency_key)
        .where(IdempotencyRecord.created_at < cutoff)
    )
    await session.execute(delete_stmt)

    stmt = (
        insert(IdempotencyRecord)
        .values(
            organisation_id=organisation_id,
            endpoint=endpoint,
            idempotency_key=idempotency_key,
            status_code=IDEMPOTENCY_PENDING_STATUS,
            response_body={},
        )
        .on_conflict_do_nothing(
            index_elements=["organisation_id", "endpoint", "idempotency_key"]
        )
        .returning(IdempotencyRecord.id)
    )
    result = await session.execute(stmt)
    created_id = result.scalar_one_or_none()

    if created_id:
        created = await session.get(IdempotencyRecord, created_id)
        if created is None:
            raise RuntimeError("Failed to load inserted idempotency record")
        return created, True

    existing_query = (
        select(IdempotencyRecord)
        .where(IdempotencyRecord.organisation_id == organisation_id)
        .where(IdempotencyRecord.endpoint == endpoint)
        .where(IdempotencyRecord.idempotency_key == idempotency_key)
    )
    existing_result = await session.execute(existing_query)
    existing = existing_result.scalar_one_or_none()
    if existing is None:
        raise RuntimeError("Idempotency claim conflict without existing row")
    return existing, False


async def upsert_idempotency_record(
    session: AsyncSession,
    organisation_id: uuid.UUID,
    endpoint: str,
    idempotency_key: str,
    status_code: int,
    response_body: dict,
) -> IdempotencyRecord:
    stmt = (
        insert(IdempotencyRecord)
        .values(
            organisation_id=organisation_id,
            endpoint=endpoint,
            idempotency_key=idempotency_key,
            status_code=status_code,
            response_body=response_body,
        )
        .on_conflict_do_nothing(
            index_elements=["organisation_id", "endpoint", "idempotency_key"]
        )
        .returning(IdempotencyRecord.id)
    )
    result = await session.execute(stmt)
    created_id = result.scalar_one_or_none()

    if created_id:
        created = await session.get(IdempotencyRecord, created_id)
        if created is None:
            raise RuntimeError("Failed to load inserted idempotency record")
        return created

    existing = await get_recent_idempotency_record(session, organisation_id, endpoint, idempotency_key)
    if existing is None:
        raise RuntimeError("Idempotency record conflict without existing row")
    return existing


async def finalize_idempotency_record(
    session: AsyncSession,
    organisation_id: uuid.UUID,
    endpoint: str,
    idempotency_key: str,
    status_code: int,
    response_body: dict,
) -> IdempotencyRecord:
    query = (
        select(IdempotencyRecord)
        .where(IdempotencyRecord.organisation_id == organisation_id)
        .where(IdempotencyRecord.endpoint == endpoint)
        .where(IdempotencyRecord.idempotency_key == idempotency_key)
    )
    result = await session.execute(query)
    record = result.scalar_one_or_none()
    if record is None:
        raise RuntimeError("Idempotency record missing during finalize")
    record.status_code = status_code
    record.response_body = response_body
    await session.flush()
    return record


async def wait_for_finalized_idempotency_record(
    session: AsyncSession,
    organisation_id: uuid.UUID,
    endpoint: str,
    idempotency_key: str,
    timeout_seconds: float = 5.0,
    poll_interval_seconds: float = 0.05,
) -> IdempotencyRecord | None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        query = (
            select(IdempotencyRecord)
            .where(IdempotencyRecord.organisation_id == organisation_id)
            .where(IdempotencyRecord.endpoint == endpoint)
            .where(IdempotencyRecord.idempotency_key == idempotency_key)
            .execution_options(populate_existing=True)
        )
        result = await session.execute(query)
        record = result.scalar_one_or_none()
        if record is not None and is_finalized(record):
            return record
        await asyncio.sleep(poll_interval_seconds)
    return None
