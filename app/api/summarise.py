from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIError
from app.db.session import get_db_session
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.summarise import SummariseRequest, SummariseResponse
from app.services.credit_service import InsufficientCreditsError, deduct_credits
from app.services.idempotency_service import (
    claim_idempotency_key,
    finalize_idempotency_record,
    is_finalized,
    wait_for_finalized_idempotency_record,
)
from app.services.job_service import create_job, enqueue_job, mark_job_failed

router = APIRouter(prefix="/api", tags=["product"])
SUMMARISE_COST = 10


def _api_job_status(internal_status: str) -> str:
    if internal_status == "queued":
        return "pending"
    if internal_status == "succeeded":
        return "completed"
    return internal_status


def _replay_or_raise(record_status: int, record_body: dict) -> JSONResponse:
    if record_status >= 400:
        raise APIError(
            status_code=record_status,
            code=record_body.get("error", "idempotent_request_failed"),
            message=record_body.get("message", "Idempotent request failed."),
        )
    return JSONResponse(status_code=record_status, content=record_body)


@router.post("/summarise", response_model=SummariseResponse, status_code=202)
async def summarise(
    payload: SummariseRequest,
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_db_session),
) -> SummariseResponse:
    endpoint = "POST:/api/summarise"
    credit_idempotency_key: str | None = None

    if idempotency_key:
        record, is_owner = await claim_idempotency_key(
            session, user.organisation_id, endpoint, idempotency_key
        )
        await session.commit()
        if not is_owner:
            if is_finalized(record):
                return _replay_or_raise(record.status_code, record.response_body)
            finalized = await wait_for_finalized_idempotency_record(
                session, user.organisation_id, endpoint, idempotency_key
            )
            if finalized is not None:
                return _replay_or_raise(finalized.status_code, finalized.response_body)
            raise APIError(
                status_code=409,
                code="idempotency_in_progress",
                message="An identical request is currently being processed.",
            )
        credit_idempotency_key = f"credit:{record.id}"

    try:
        await deduct_credits(
            session=session,
            organisation_id=user.organisation_id,
            user_id=user.id,
            amount=SUMMARISE_COST,
            reason="api_summarise",
            idempotency_key=credit_idempotency_key,
        )
        job = await create_job(session=session, organisation_id=user.organisation_id)
        await session.commit()
    except InsufficientCreditsError as exc:
        await session.rollback()
        if idempotency_key:
            await finalize_idempotency_record(
                session,
                user.organisation_id,
                endpoint,
                idempotency_key,
                402,
                {"error": "insufficient_credits", "message": str(exc)},
            )
            await session.commit()
        raise APIError(status_code=402, code="insufficient_credits", message=str(exc)) from exc
    except Exception as exc:
        await session.rollback()
        if idempotency_key:
            await finalize_idempotency_record(
                session,
                user.organisation_id,
                endpoint,
                idempotency_key,
                500,
                {"error": "summarise_failed", "message": "Unable to create summary job."},
            )
            await session.commit()
        raise APIError(status_code=500, code="summarise_failed", message="Unable to create summary job.") from exc

    response = SummariseResponse(job_id=str(job.id), status=_api_job_status(job.status.value))
    try:
        await enqueue_job("summarise_task", job.id, {"text": payload.text})
    except Exception as exc:
        await mark_job_failed(session, job.id, "worker_enqueue_failed", refund_user_id=user.id)
        if idempotency_key:
            await finalize_idempotency_record(
                session,
                user.organisation_id,
                endpoint,
                idempotency_key,
                503,
                {"error": "queue_unavailable", "message": "Job queue unavailable."},
            )
        await session.commit()
        raise APIError(status_code=503, code="queue_unavailable", message="Job queue unavailable.") from exc

    if idempotency_key:
        await finalize_idempotency_record(
            session,
            user.organisation_id,
            endpoint,
            idempotency_key,
            202,
            response.model_dump(),
        )
        await session.commit()

    return response
