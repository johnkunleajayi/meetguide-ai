import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.api.auth import NO_STORE
from app.api.desktop_auth import bearer
from app.context.repository import ContextRepository, get_context_repository
from app.core.auth import authenticated_user
from app.cues.domain import CueInput, CueResult
from app.cues.gemini import GeminiProvider
from app.cues.lifecycle import CueDisconnected, until_disconnect
from app.cues.provider import ProviderUnavailable
from app.cues.service import generate_cue, retrieve_evidence
from app.db.auth_repository import AuthRepository, get_auth_repository

router = APIRouter(prefix="/cues", tags=["live cues"])


def cue_user(request: Request, repository: AuthRepository = Depends(get_auth_repository)):
    # Native bearer only, never an ambient web cookie. Native vault owns the credential.
    try:
        user = authenticated_user(repository, bearer(request))
    except SQLAlchemyError:
        raise HTTPException(
            503, "Authentication is temporarily unavailable", headers=NO_STORE
        ) from None
    if user is None:
        raise HTTPException(401, "Not authenticated", headers=NO_STORE)
    if request.headers.get("origin"):
        raise HTTPException(403, "Native authentication required", headers=NO_STORE)
    return user


def get_provider(request: Request):
    settings = request.app.state.settings
    if not settings.live_cue_enabled or not settings.gemini_api_key:
        raise HTTPException(503, "Live Cue is not configured", headers=NO_STORE)
    return GeminiProvider(settings)


@router.post("/generate", response_model=CueResult)
async def generate(
    request: Request,
    user=Depends(cue_user),
    repository: ContextRepository = Depends(get_context_repository),
    provider=Depends(get_provider),
):
    content = bytearray()
    async for part in request.stream():
        if len(content) + len(part) > 32768:
            raise HTTPException(413, "Live Cue input is too large", headers=NO_STORE)
        content.extend(part)
    try:
        payload = CueInput.model_validate_json(content)
    except ValidationError:
        raise HTTPException(
            422, "A bounded finalized question event is required", headers=NO_STORE
        ) from None
    # Per-process bounded concurrency and per-account in-flight limit; no transcript cache.
    pending = request.app.state.cue_pending
    if pending.get(user.id, 0) >= 2 or sum(pending.values()) >= 8:
        raise HTTPException(429, "Live Cue is busy. Please retry.", headers=NO_STORE)
    pending[user.id] = pending.get(user.id, 0) + 1
    try:
        evidence = await run_in_threadpool(retrieve_evidence, repository, user.id, payload)
        result = await until_disconnect(
            request, asyncio.wait_for(generate_cue(provider, payload, evidence), timeout=27)
        )
    except CueDisconnected:
        from starlette.responses import Response

        return Response(status_code=499, headers=NO_STORE)
    except SQLAlchemyError, ProviderUnavailable, TimeoutError:
        raise HTTPException(
            503, "Unable to prepare a grounded answer. Please retry.", headers=NO_STORE
        ) from None
    finally:
        pending[user.id] -= 1
        if not pending[user.id]:
            del pending[user.id]
    from starlette.responses import JSONResponse

    return JSONResponse(result.model_dump(mode="json"), headers=NO_STORE)
