from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIError
from app.db.session import get_db_session
from app.dependencies import get_current_user, require_admin
from app.models.user import User
from app.schemas.credits import (
    BalanceResponse,
    BalanceWithTransactionsResponse,
    CreditTransactionResponse,
    GrantCreditsRequest,
)
from app.services.credit_service import get_balance, get_recent_transactions, grant_credits

router = APIRouter(prefix="/credits", tags=["credits"])


@router.post("/grant", response_model=BalanceResponse)
async def grant(
    payload: GrantCreditsRequest,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> BalanceResponse:
    target_user_id = admin_user.id
    if payload.user_id:
        try:
            target_user_id = uuid.UUID(payload.user_id)
        except ValueError as exc:
            raise APIError(status_code=422, code="invalid_user_id", message="user_id must be a valid UUID.") from exc

    try:
        await grant_credits(
            session=session,
            organisation_id=admin_user.organisation_id,
            user_id=target_user_id,
            amount=payload.amount,
            reason=payload.reason,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    current = await get_balance(session, admin_user.organisation_id)
    return BalanceResponse(balance=current)


@router.get("/balance", response_model=BalanceWithTransactionsResponse)
async def balance(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> BalanceWithTransactionsResponse:
    current = await get_balance(session, user.organisation_id)
    rows = await get_recent_transactions(session, user.organisation_id, limit=10)
    transactions = [
        CreditTransactionResponse(
            id=str(row.id),
            amount=row.amount,
            reason=row.reason,
            created_at=row.created_at.isoformat() if row.created_at else None,
        )
        for row in rows
    ]
    return BalanceWithTransactionsResponse(balance=current, transactions=transactions)
