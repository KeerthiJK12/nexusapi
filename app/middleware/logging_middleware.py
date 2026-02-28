from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        started_at = time.perf_counter()
        incoming_request_id = request.headers.get("X-Request-ID")
        try:
            request_id = str(uuid.UUID(incoming_request_id)) if incoming_request_id else str(uuid.uuid4())
        except (ValueError, TypeError):
            request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        claims = getattr(request.state, "user_claims", None) or {}
        logger.info(
            "http_request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(elapsed_ms, 2),
            organisation_id=claims.get("organisation_id"),
            user_id=claims.get("sub"),
        )
        response.headers["X-Request-ID"] = request_id
        return response
