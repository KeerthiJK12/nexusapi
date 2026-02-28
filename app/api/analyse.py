from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIError
from app.db.session import get_db_session
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.analyse import AnalyseRequest, AnalyseResponse
from app.services.credit_service import InsufficientCreditsError, deduct_credits, get_balance
from app.services.idempotency_service import (
    claim_idempotency_key,
    finalize_idempotency_record,
    is_finalized,
    wait_for_finalized_idempotency_record,
)

router = APIRouter(prefix="/api", tags=["product"])
ANALYSE_COST = 25


def _replay_or_raise(record_status: int, record_body: dict) -> JSONResponse:
    if record_status >= 400:
        raise APIError(
            status_code=record_status,
            code=record_body.get("error", "idempotent_request_failed"),
            message=record_body.get("message", "Idempotent request failed."),
            details={k: v for k, v in record_body.items() if k not in {"error", "message"}},
        )
    return JSONResponse(status_code=record_status, content=record_body)


@router.post("/analyse", response_model=AnalyseResponse)
async def analyse(
    payload: AnalyseRequest,
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_db_session),
) -> AnalyseResponse:
    endpoint = "POST:/api/analyse"
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
            amount=ANALYSE_COST,
            reason="api_analyse",
            idempotency_key=credit_idempotency_key,
        )
        await session.commit()
    except InsufficientCreditsError as exc:
        await session.rollback()
        try:
            current_balance = await get_balance(session, user.organisation_id)
        except Exception:
            # Preserve contract: insufficient balance should still return 402.
            current_balance = None
        error_payload = {
            "error": "insufficient_credits",
            "message": str(exc),
            "balance": current_balance,
            "required": ANALYSE_COST,
        }
        if idempotency_key:
            await finalize_idempotency_record(
                session,
                user.organisation_id,
                endpoint,
                idempotency_key,
                402,
                error_payload,
            )
            await session.commit()
        raise APIError(
            status_code=402,
            code="insufficient_credits",
            message=str(exc),
            details=(
                {"balance": current_balance, "required": ANALYSE_COST}
                if current_balance is not None
                else {"required": ANALYSE_COST}
            ),
        ) from exc
    except Exception as exc:
        await session.rollback()
        if idempotency_key:
            await finalize_idempotency_record(
                session,
                user.organisation_id,
                endpoint,
                idempotency_key,
                500,
                {"error": "analysis_failed", "message": "Text processing failed."},
            )
            await session.commit()
        raise APIError(status_code=500, code="analysis_failed", message="Text processing failed.") from exc

    try:
        words = payload.text.split()
        word_count = len(words)
        unique_words = len({w.lower() for w in words})
        remaining = await get_balance(session, user.organisation_id)
        response = AnalyseResponse(
            result=f"Analysis complete. Word count: {word_count}. Unique words: {unique_words}.",
            credits_remaining=remaining,
        )
    except Exception as exc:
        if idempotency_key:
            await finalize_idempotency_record(
                session,
                user.organisation_id,
                endpoint,
                idempotency_key,
                500,
                {"error": "analysis_failed", "message": "Text processing failed."},
            )
            await session.commit()
        raise APIError(status_code=500, code="analysis_failed", message="Text processing failed.") from exc

    if idempotency_key:
        await finalize_idempotency_record(
            session,
            user.organisation_id,
            endpoint,
            idempotency_key,
            200,
            response.model_dump(),
        )
        await session.commit()

    return response
