from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIError
from app.db.session import get_db_session
from app.dependencies import get_current_user
from app.models.job import Job, JobStatus
from app.models.user import User
from app.services.credit_service import refund_summarise_credits_if_needed

router = APIRouter(prefix="/api", tags=["product"])
PENDING_TIMEOUT = timedelta(minutes=5)


def _api_job_status(internal_status: str) -> str:
    if internal_status == "queued":
        return "pending"
    if internal_status == "succeeded":
        return "completed"
    return internal_status


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    query = select(Job).where(Job.id == job_id, Job.organisation_id == user.organisation_id)
    result = await session.execute(query)
    job = result.scalar_one_or_none()
    if job is None:
        raise APIError(status_code=404, code="job_not_found", message="Job not found.")

    if job.status in {JobStatus.queued, JobStatus.running} and job.created_at:
        elapsed = datetime.now(UTC) - job.created_at
        if elapsed > PENDING_TIMEOUT:
            job.status = JobStatus.failed
            job.error = "job_timeout"
            await refund_summarise_credits_if_needed(
                session=session,
                organisation_id=job.organisation_id,
                user_id=user.id,
                job_id=job.id,
                failure_code="job_timeout",
            )
            await session.commit()

    return {
        "id": str(job.id),
        "status": _api_job_status(job.status.value),
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }
