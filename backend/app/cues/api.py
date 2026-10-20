import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.api.auth import NO_STORE
from app.api.desktop_auth import bearer
from app.context.repository import ContextRepository, get_context_repository
from app.core.auth import authenticated_user
from app.core.timing import Timing, current
from app.cues.domain import CueInput, CueResult
from app.cues.gemini import GeminiProvider
from app.cues.lifecycle import CueDisconnected, until_disconnect
from app.cues.openai import OpenAIProvider
from app.cues.provider import ProviderUnavailable
from app.cues.service import generate_cue, retrieve_evidence
from app.db.auth_repository import AuthRepository, get_auth_repository
from app.preparations.snapshot import resolve

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
    key = (
        settings.openai_api_key
        if settings.live_cue_provider == "openai"
        else settings.gemini_api_key
    )
    if not settings.live_cue_enabled or not key:
        timing = Timing(
            request.headers.get("x-meetguide-question-id"), enabled=settings.app_env != "production"
        )
        timing.values["provider_error_type"] = (
            "KEY_NOT_CONFIGURED" if not key else "LIVE_CUE_DISABLED"
        )
        timing.values.update(**provider_metadata(settings))
        timing.finish()
        raise HTTPException(
            503, "Live Cue is not configured", headers={**NO_STORE, **timing.headers()}
        )
    return (
        OpenAIProvider(settings)
        if settings.live_cue_provider == "openai"
        else GeminiProvider(settings)
    )


def provider_metadata(settings):
    return {
        "provider": settings.live_cue_provider,
        "model": settings.openai_live_cue_model
        if settings.live_cue_provider == "openai"
        else settings.live_cue_model,
    }


@router.post("/generate", response_model=CueResult)
async def generate(
    request: Request,
    user=Depends(cue_user),
    repository: ContextRepository = Depends(get_context_repository),
    provider=Depends(get_provider),
):
    timing = Timing(
        request.headers.get("x-meetguide-question-id"),
        enabled=request.app.state.settings.app_env != "production",
    )
    timing.values.update(**provider_metadata(request.app.state.settings))
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
    try:
        payload._preparation = resolve(request.app, user.id, payload.preparation_token)
    except ValueError:
        raise HTTPException(
            409, "Choose a valid preparation and start a new desktop session", headers=NO_STORE
        ) from None
    # Per-process bounded concurrency and per-account in-flight limit; no transcript cache.
    pending = request.app.state.cue_pending
    if pending.get(user.id, 0) >= 2 or sum(pending.values()) >= 8:
        timing.values.update(provider_error_type="BACKEND_BUSY", provider_http_status=429)
        timing.finish()
        raise HTTPException(
            429, "Live Cue is busy. Please retry.", headers={**NO_STORE, **timing.headers()}
        )
    pending[user.id] = pending.get(user.id, 0) + 1
    timing.values.update(
        live_cue_streaming=False,
        live_cue_time_to_first_output_ms=None,
        conversation_turn_count=len(payload.context),
        conversation_context_char_count=sum(len(turn.text) for turn in payload.context),
        question_char_count=len(payload.question),
    )
    if request.headers.get("accept") == "application/x-ndjson":
        from app.cues.streaming import response

        raw_attempt = request.headers.get("x-meetguide-attempt", "1")
        attempt = (
            int(raw_attempt)
            if raw_attempt.isascii() and raw_attempt.isdigit() and len(raw_attempt) <= 6
            else 1
        )
        return response(payload, user, repository, provider, timing, pending, max(1, attempt))
    token = current.set(timing)
    try:
        with timing.measure("retrieval_ms"):
            evidence = await run_in_threadpool(retrieve_evidence, repository, user.id, payload)
        timing.values.update(
            retrieved_excerpt_count=len(evidence),
            retrieved_context_char_count=sum(len(item.text) for item in evidence),
        )
        result = await until_disconnect(
            request, asyncio.wait_for(generate_cue(provider, payload, evidence), timeout=27)
        )
    except CueDisconnected:
        from starlette.responses import Response

        timing.values["provider_error_type"] = "CLIENT_DISCONNECTED"
        return Response(status_code=499, headers=NO_STORE)
    except (SQLAlchemyError, ProviderUnavailable, TimeoutError) as error:
        timing.values["provider_error_type"] = (
            error.reason
            if isinstance(error, ProviderUnavailable)
            else "TIMEOUT"
            if isinstance(error, TimeoutError)
            else "DATABASE_ERROR"
        )
        timing.values["provider_http_status"] = getattr(error, "status", None)
        raise HTTPException(
            503,
            "Unable to prepare a grounded answer. Please retry.",
            headers={**NO_STORE, **timing.headers()},
        ) from None
    finally:
        timing.finish()
        current.reset(token)
        pending[user.id] -= 1
        if not pending[user.id]:
            del pending[user.id]
    from starlette.responses import JSONResponse

    return JSONResponse(result.model_dump(mode="json"), headers={**NO_STORE, **timing.headers()})
