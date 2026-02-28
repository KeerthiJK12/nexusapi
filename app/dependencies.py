from __future__ import annotations

import uuid

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.errors import APIError
from app.db.session import get_db_session
from app.models.user import User, UserRole


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> User:
    claims = getattr(request.state, "user_claims", None)
    if claims is None:
        raise APIError(status_code=401, code="missing_jwt", message="Authorization bearer token is required.")

    user_id_raw = claims.get("sub")
    org_id_raw = claims.get("organisation_id")
    if not user_id_raw or not org_id_raw:
        raise APIError(status_code=401, code="invalid_jwt", message="Token claims are incomplete.")

    try:
        user_id = uuid.UUID(user_id_raw)
        org_id = uuid.UUID(org_id_raw)
    except ValueError as exc:
        raise APIError(status_code=401, code="invalid_jwt", message="Token claims are malformed.") from exc

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise APIError(status_code=401, code="user_deleted", message="User no longer exists.")
    if user.organisation_id != org_id:
        raise APIError(status_code=401, code="invalid_jwt", message="Token organisation mismatch.")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.admin:
        raise APIError(status_code=403, code="forbidden", message="Admin role required.")
    return user
