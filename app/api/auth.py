from __future__ import annotations

import re

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.config import get_settings
from app.core.errors import APIError
from app.core.security import create_access_token
from app.db.session import get_db_session
from app.models.organisation import Organisation
from app.models.user import User, UserRole
from app.schemas.auth import TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def _slugify(domain: str) -> str:
    clean = re.sub(r"[^a-z0-9-]", "-", domain.lower())
    clean = re.sub(r"-+", "-", clean).strip("-")
    return clean or "org"


@router.get("/google")
async def auth_google(request: Request):
    if not settings.google_client_id or not settings.google_client_secret:
        raise APIError(status_code=401, code="oauth_not_configured", message="Google OAuth is not configured.")
    redirect_uri = settings.oauth_redirect_uri or str(request.url_for("auth_callback"))
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="auth_callback", response_model=TokenResponse)
async def auth_callback(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        token = await oauth.google.authorize_access_token(request)
        userinfo = token.get("userinfo")
        if not userinfo:
            userinfo = await oauth.google.parse_id_token(request, token)
    except Exception as exc:
        raise APIError(status_code=401, code="oauth_failed", message="Google authentication failed.") from exc

    email = userinfo.get("email")
    name = userinfo.get("name") or "Unknown"
    google_id = userinfo.get("sub")
    if not email or not google_id:
        raise APIError(status_code=401, code="oauth_failed", message="Google authentication failed.")

    domain = email.split("@")[-1].lower()
    org_slug = _slugify(domain)

    async with session.begin():
        org_result = await session.execute(select(Organisation).where(Organisation.slug == org_slug))
        organisation = org_result.scalar_one_or_none()

        created_org = False
        if organisation is None:
            organisation = Organisation(name=domain, slug=org_slug)
            session.add(organisation)
            await session.flush()
            created_org = True

        user_result = await session.execute(select(User).where(User.email == email))
        user = user_result.scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                name=name,
                google_id=google_id,
                organisation_id=organisation.id,
                role=UserRole.admin if created_org else UserRole.member,
            )
            session.add(user)
            await session.flush()
        else:
            user.name = name
            user.google_id = google_id

    jwt_token = create_access_token(
        subject=str(user.id),
        extra={
            "user_id": str(user.id),
            "organisation_id": str(user.organisation_id),
            "role": user.role.value,
        },
    )
    return JSONResponse(content=TokenResponse(access_token=jwt_token).model_dump())
