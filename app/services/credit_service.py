from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_transaction import CreditTransaction
from app.models.organisation import Organisation
from app.models.user import User


class InsufficientCreditsError(Exception):
    def __init__(self, required: int) -> None:
        super().__init__(f"You need {required} credits.")
        self.required = required


async def get_balance(session: AsyncSession, organisation_id: uuid.UUID) -> int:
    query = select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
        CreditTransaction.organisation_id == organisation_id
    )
    result = await session.execute(query)
    return int(result.scalar_one())


async def get_recent_transactions(
    session: AsyncSession, organisation_id: uuid.UUID, limit: int = 10
) -> list[CreditTransaction]:
    query = (
        select(CreditTransaction)
        .where(CreditTransaction.organisation_id == organisation_id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def grant_credits(
    session: AsyncSession,
    organisation_id: uuid.UUID,
    user_id: uuid.UUID,
    amount: int,
    reason: str,
) -> CreditTransaction:
    tx = CreditTransaction(
        organisation_id=organisation_id,
        user_id=user_id,
        amount=amount,
        reason=reason,
        idempotency_key=None,
    )
    session.add(tx)
    await session.flush()
    return tx


async def deduct_credits(
    session: AsyncSession,
    organisation_id: uuid.UUID,
    user_id: uuid.UUID,
    amount: int,
    reason: str,
    idempotency_key: str | None = None,
) -> CreditTransaction:
    if amount <= 0:
        raise ValueError("amount must be positive")

    lock_query = select(Organisation).where(Organisation.id == organisation_id).with_for_update()
    await session.execute(lock_query)

    if idempotency_key:
        existing_query = select(CreditTransaction).where(
            CreditTransaction.idempotency_key == idempotency_key,
            CreditTransaction.organisation_id == organisation_id,
        )
        existing_result = await session.execute(existing_query)
        existing = existing_result.scalar_one_or_none()
        if existing:
            return existing

    balance = await get_balance(session, organisation_id)
    if balance < amount:
        raise InsufficientCreditsError(required=amount)

    tx = CreditTransaction(
        organisation_id=organisation_id,
        user_id=user_id,
        amount=-amount,
        reason=reason,
        idempotency_key=idempotency_key,
    )
    session.add(tx)
    try:
        await session.flush()
    except IntegrityError:
        if not idempotency_key:
            raise
        dup_query = select(CreditTransaction).where(
            CreditTransaction.idempotency_key == idempotency_key,
            CreditTransaction.organisation_id == organisation_id,
        )
        dup_res = await session.execute(dup_query)
        dup = dup_res.scalar_one_or_none()
        if dup is None:
            raise
        return dup
    return tx


async def _resolve_actor_user_id(
    session: AsyncSession,
    organisation_id: uuid.UUID,
    preferred_user_id: uuid.UUID | None,
) -> uuid.UUID:
    if preferred_user_id is not None:
        return preferred_user_id
    result = await session.execute(
        select(User.id)
        .where(User.organisation_id == organisation_id)
        .order_by(User.created_at.asc())
        .limit(1)
    )
    user_id = result.scalar_one_or_none()
    if user_id is None:
        raise RuntimeError("No user exists for organisation; cannot issue refund.")
    return user_id


async def refund_summarise_credits_if_needed(
    session: AsyncSession,
    organisation_id: uuid.UUID,
    user_id: uuid.UUID | None,
    job_id: uuid.UUID,
    failure_code: str,
) -> CreditTransaction | None:
    refund_key = f"summarise_refund:{job_id}"
    existing_query = select(CreditTransaction).where(
        CreditTransaction.idempotency_key == refund_key,
        CreditTransaction.organisation_id == organisation_id,
    )
    existing_res = await session.execute(existing_query)
    existing = existing_res.scalar_one_or_none()
    if existing is not None:
        return None

    actor_id = await _resolve_actor_user_id(session, organisation_id, user_id)
    refund_tx = CreditTransaction(
        organisation_id=organisation_id,
        user_id=actor_id,
        amount=10,
        reason=f"api_summarise_refund:{failure_code}",
        idempotency_key=refund_key,
    )
    session.add(refund_tx)
    try:
        await session.flush()
    except IntegrityError:
        return None
    return refund_tx
