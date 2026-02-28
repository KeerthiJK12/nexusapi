from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.rate_limit import RateLimitExceededError, enforce_org_rate_limit


def _ensure_request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    try:
        return str(uuid.UUID(str(rid)))
    except (ValueError, TypeError):
        generated = str(uuid.uuid4())
        request.state.request_id = generated
        return generated


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        claims = getattr(request.state, "user_claims", None) or {}
        org_id = claims.get("organisation_id")
        if org_id:
            try:
                await enforce_org_rate_limit(request.app.state.redis, org_id)
            except RateLimitExceededError as exc:
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(exc.retry_after)},
                    content={
                        "error": "rate_limit_exceeded",
                        "message": "Too many requests.",
                        "request_id": _ensure_request_id(request),
                    },
                )
        return await call_next(request)
