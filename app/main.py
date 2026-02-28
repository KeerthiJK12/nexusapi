from __future__ import annotations

from contextlib import asynccontextmanager
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import analyse, auth, credits, health, jobs, me, summarise
from app.core.config import get_settings
from app.core.errors import APIError
from app.core.logging import configure_logging
from app.middleware.jwt_middleware import JWTMiddleware
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.rate_limit_middleware import RateLimitMiddleware

settings = get_settings()
configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _app.state.redis = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    yield
    await _app.state.redis.close()


app = FastAPI(title=settings.app_name, debug=False, lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(JWTMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(credits.router)
app.include_router(analyse.router)
app.include_router(summarise.router)
app.include_router(jobs.router)


def _error_request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    try:
        return str(uuid.UUID(str(rid)))
    except (ValueError, TypeError):
        generated = str(uuid.uuid4())
        request.state.request_id = generated
        return generated


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    payload = {
        "error": exc.code,
        "message": exc.message,
        "request_id": _error_request_id(request),
    }
    payload.update(exc.details)
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content=payload,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, _exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Request body or params are invalid.",
            "request_id": _error_request_id(request),
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "http_error",
            "message": str(exc.detail),
            "request_id": _error_request_id(request),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred.",
            "request_id": _error_request_id(request),
        },
    )
