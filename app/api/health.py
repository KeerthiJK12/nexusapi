from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIError
from app.db.session import get_db_session

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Health check")
async def health(session: AsyncSession = Depends(get_db_session)) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise APIError(status_code=503, code="service_unavailable", message="Database unreachable") from exc
    return {"status": "healthy"}
