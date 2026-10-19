from datetime import datetime
from urllib.parse import urlencode
from uuid import UUID

import httpx
from authlib.integrations.base_client import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from joserfc.errors import JoseError
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse

from app.core import auth, desktop_auth
from app.db.auth_repository import AuthRepository, get_auth_repository

router = APIRouter(prefix="/auth", tags=["authentication"])
NO_STORE = {"Cache-Control": "no-store"}


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    name: str | None
    avatar_url: str | None
    created_at: datetime
    updated_at: datetime


def google_client(request: Request):
    settings = request.app.state.settings
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(503, "Google login is not configured", headers=NO_STORE)
    return request.app.state.oauth.create_client("google")


@router.get("/google/login")
async def google_login(request: Request) -> Response:
    client = google_client(request)
    request.session.clear()
    desktop = None
    keys = {"desktop_port", "desktop_state", "code_challenge"}
    if keys.intersection(request.query_params):
        port = request.query_params.get("desktop_port", "")
        state = request.query_params.get("desktop_state")
        challenge = request.query_params.get("code_challenge")
        if (
            any(len(request.query_params.getlist(key)) != 1 for key in keys)
            or not port.isascii()
            or not port.isdecimal()
            or len(port) > 5
            or not 1024 <= int(port) <= 65535
            or not auth.valid_token(state)
            or not auth.valid_token(challenge)
        ):
            raise HTTPException(400, "Invalid desktop login request", headers=NO_STORE)
        desktop = {"port": int(port), "state": state, "challenge": challenge}
    try:
        response = await client.authorize_redirect(
            request, request.app.state.settings.google_redirect_uri
        )
    except OAuthError, httpx.HTTPError, ValueError:
        raise HTTPException(
            503, "Google login is temporarily unavailable", headers=NO_STORE
        ) from None
    if desktop is not None:
        # Signed OAuth cookie binds the handoff to this browser's Google login state.
        request.session["desktop_login"] = desktop
    response.headers.update(NO_STORE)
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request, repository: AuthRepository = Depends(get_auth_repository)
) -> Response:
    client = google_client(request)
    if not request.query_params.get("state"):
        request.session.clear()
        raise HTTPException(400, "Invalid Google login state", headers=NO_STORE)
    settings = request.app.state.settings
    desktop = request.session.get("desktop_login")
    try:
        tokens = await client.authorize_access_token(
            request,
            claims_options={
                "iss": {
                    "essential": True,
                    "values": ["https://accounts.google.com", "accounts.google.com"],
                },
                "aud": {"essential": True, "value": settings.google_client_id},
                "sub": {"essential": True},
                "exp": {"essential": True},
            },
            leeway=30,
        )
    except OAuthError:
        raise HTTPException(
            400, "Invalid Google login callback or state", headers=NO_STORE
        ) from None
    except JoseError, ValueError, KeyError:
        raise HTTPException(401, "Invalid Google identity", headers=NO_STORE) from None
    except httpx.HTTPError:
        raise HTTPException(
            503, "Google login is temporarily unavailable", headers=NO_STORE
        ) from None
    finally:
        request.session.clear()
    claims = tokens.get("userinfo")
    if not isinstance(claims, dict):
        raise HTTPException(401, "Invalid Google identity", headers=NO_STORE)
    if desktop is not None:
        try:
            code = await run_in_threadpool(
                desktop_auth.create_handoff, repository, claims, desktop["challenge"]
            )
        except auth.InvalidIdentity:
            raise HTTPException(
                403, "A verified Google email is required", headers=NO_STORE
            ) from None
        except SQLAlchemyError:
            raise HTTPException(
                503, "Authentication is temporarily unavailable", headers=NO_STORE
            ) from None
        query = urlencode({"code": code, "state": desktop["state"]})
        return RedirectResponse(
            f"http://127.0.0.1:{desktop['port']}/callback?{query}",
            status_code=303,
            headers={**NO_STORE, "Referrer-Policy": "no-referrer"},
        )
    try:
        _, raw_token = await run_in_threadpool(
            auth.complete_login,
            repository,
            claims,
            settings,
            request.cookies.get(auth.SESSION_COOKIE),
        )
    except auth.InvalidIdentity:
        raise HTTPException(403, "A verified Google email is required", headers=NO_STORE) from None
    except SQLAlchemyError:
        raise HTTPException(
            503, "Authentication is temporarily unavailable", headers=NO_STORE
        ) from None
    response = RedirectResponse(settings.frontend_origin, status_code=303, headers=NO_STORE)
    response.set_cookie(
        auth.SESSION_COOKIE,
        raw_token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/me", response_model=AuthenticatedUser)
def me(
    request: Request,
    response: Response,
    repository: AuthRepository = Depends(get_auth_repository),
):
    try:
        user = auth.authenticated_user(repository, request.cookies.get(auth.SESSION_COOKIE))
    except SQLAlchemyError:
        raise HTTPException(
            503, "Authentication is temporarily unavailable", headers=NO_STORE
        ) from None
    if user is None:
        raise HTTPException(401, "Not authenticated", headers=NO_STORE)
    response.headers.update(NO_STORE)
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, repository: AuthRepository = Depends(get_auth_repository)) -> Response:
    settings = request.app.state.settings
    if request.headers.get("origin") not in settings.cors_origins:
        raise HTTPException(403, "Untrusted request origin", headers=NO_STORE)
    try:
        auth.logout(repository, request.cookies.get(auth.SESSION_COOKIE))
    except SQLAlchemyError:
        raise HTTPException(
            503, "Authentication is temporarily unavailable", headers=NO_STORE
        ) from None
    response = Response(status_code=204, headers=NO_STORE)
    response.delete_cookie(
        auth.SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=settings.secure_cookies
    )
    return response
