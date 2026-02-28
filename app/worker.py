from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.job import Job, JobStatus
from app.services.credit_service import refund_summarise_credits_if_needed


async def _run_job(job_id: str, payload: dict, operation: str) -> dict:
    async with AsyncSessionLocal() as session:
        uid = uuid.UUID(job_id)
        query = select(Job).where(Job.id == uid)
        result = await session.execute(query)
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError("Job not found")

        job.status = JobStatus.running
        await session.commit()

        try:
            text = payload.get("text", "")
            summary = " ".join(text.split()[:25])
            output = {"operation": operation, "summary": summary, "input_length": len(text)}
            job.status = JobStatus.succeeded
            job.result = output
            job.error = None
            await session.commit()
            return output
        except Exception as exc:
            job.status = JobStatus.failed
            job.error = str(exc)
            await refund_summarise_credits_if_needed(
                session=session,
                organisation_id=job.organisation_id,
                user_id=None,
                job_id=job.id,
                failure_code="worker_execution_failed",
            )
            await session.commit()
            raise


async def summarise_task(ctx, job_id: str, payload: dict) -> dict:
    return await _run_job(job_id, payload, operation="summarise")


class WorkerSettings:
    functions = [summarise_task]
