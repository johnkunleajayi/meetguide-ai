"""Native-only bearer transport for the same opaque MeetGuide sessions."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import NO_STORE, AuthenticatedUser
from app.core import auth, desktop_auth
from app.db.auth_repository import AuthRepository, get_auth_repository

router = APIRouter(prefix="/auth/desktop", tags=["desktop authentication"])


class DesktopExchange(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    code: str = Field(min_length=87, max_length=87, repr=False)
    verifier: str = Field(min_length=43, max_length=43, repr=False)


class DesktopSession(BaseModel):
    session_token: str = Field(repr=False)


def bearer(request: Request) -> str | None:
    value = request.headers.get("authorization", "")
    scheme, _, token = value.partition(" ")
    return token if scheme.lower() == "bearer" and auth.valid_token(token) else None


@router.post("/exchange", response_model=DesktopSession)
def exchange(
    payload: DesktopExchange,
    request: Request,
    response: Response,
    repository: AuthRepository = Depends(get_auth_repository),
):
    try:
        token = desktop_auth.exchange_handoff(
            repository, payload.code, payload.verifier, request.app.state.settings
        )
    except SQLAlchemyError:
        raise HTTPException(
            503, "Authentication is temporarily unavailable", headers=NO_STORE
        ) from None
    if token is None:
        raise HTTPException(401, "Invalid or expired desktop handoff", headers=NO_STORE)
    response.headers.update(NO_STORE)
    return DesktopSession(session_token=token)


@router.get("/me", response_model=AuthenticatedUser)
def me(
    request: Request,
    response: Response,
    repository: AuthRepository = Depends(get_auth_repository),
):
    try:
        user = auth.authenticated_user(repository, bearer(request))
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
    # This route accepts only an explicit bearer credential, never an ambient cookie.
    token = bearer(request)
    if token is None:
        raise HTTPException(401, "Not authenticated", headers=NO_STORE)
    try:
        auth.logout(repository, token)
    except SQLAlchemyError:
        raise HTTPException(
            503, "Authentication is temporarily unavailable", headers=NO_STORE
        ) from None
    return Response(status_code=204, headers=NO_STORE)
