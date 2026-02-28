from __future__ import annotations

import uuid

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.job import Job, JobStatus
from app.services.credit_service import refund_summarise_credits_if_needed


async def get_arq_pool() -> ArqRedis:
    settings = get_settings()
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    return await create_pool(redis_settings)


async def create_job(
    session: AsyncSession,
    organisation_id: uuid.UUID,
) -> Job:
    job = Job(organisation_id=organisation_id, status=JobStatus.queued, result=None, error=None)
    session.add(job)
    await session.flush()
    return job


async def enqueue_job(task_name: str, job_id: uuid.UUID, payload: dict) -> None:
    redis = await get_arq_pool()
    await redis.enqueue_job(task_name, str(job_id), payload)


async def mark_job_failed(
    session: AsyncSession,
    job_id: uuid.UUID,
    error: str,
    refund_user_id: uuid.UUID | None = None,
) -> None:
    result = await session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        return
    job.status = JobStatus.failed
    job.error = error
    await refund_summarise_credits_if_needed(
        session=session,
        organisation_id=job.organisation_id,
        user_id=refund_user_id,
        job_id=job.id,
        failure_code=error,
    )
    await session.flush()
