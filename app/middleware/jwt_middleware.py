from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.security import InvalidTokenError, decode_access_token


def _ensure_request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    try:
        return str(uuid.UUID(str(rid)))
    except (ValueError, TypeError):
        generated = str(uuid.uuid4())
        request.state.request_id = generated
        return generated


class JWTMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        public_paths = {"/health", "/auth/google", "/auth/callback"}
        if request.url.path in public_paths:
            request.state.user_claims = None
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "error": "missing_jwt",
                    "message": "Authorization bearer token is required.",
                    "request_id": _ensure_request_id(request),
                },
            )

        token = auth_header.removeprefix("Bearer ").strip()
        try:
            request.state.user_claims = decode_access_token(token)
        except InvalidTokenError:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "invalid_jwt",
                    "message": "Token is invalid or expired.",
                    "request_id": _ensure_request_id(request),
                },
            )

        return await call_next(request)
