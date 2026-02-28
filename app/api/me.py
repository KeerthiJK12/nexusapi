from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.dependencies import get_current_user
from app.models.organisation import Organisation
from app.models.user import User

router = APIRouter(tags=["auth"])


@router.get("/me")
async def me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    org_result = await session.execute(select(Organisation).where(Organisation.id == user.organisation_id))
    organisation = org_result.scalar_one()
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
        },
        "organisation": {
            "id": str(organisation.id),
            "name": organisation.name,
            "slug": organisation.slug,
        },
    }
