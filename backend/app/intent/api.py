import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from app.api.auth import NO_STORE
from app.core.timing import Timing
from app.cues.api import cue_user
from app.cues.provider import ProviderUnavailable
from app.intent.domain import IntentInput, IntentResult
from app.intent.gemini import GeminiIntentProvider
from app.intent.provider import IntentProvider

router = APIRouter(prefix="/intent", tags=["intent"])


def get_intent_provider(request: Request) -> IntentProvider:
    settings = request.app.state.settings
    if (
        not settings.gemini_intent_enabled
        or not settings.live_cue_enabled
        or not settings.gemini_api_key
    ):
        raise HTTPException(
            503, "Semantic intent is unavailable; use local detection", headers=NO_STORE
        )
    return GeminiIntentProvider(settings)


@router.post("/classify", response_model=IntentResult)
async def classify(request: Request, user=Depends(cue_user), provider=Depends(get_intent_provider)):
    content = bytearray()
    async for part in request.stream():
        if len(content) + len(part) > 32768:
            raise HTTPException(413, "Intent input is too large", headers=NO_STORE)
        content.extend(part)
    try:
        payload = IntentInput.model_validate_json(content)
    except ValidationError:
        raise HTTPException(
            422, "Bounded transcript context is required", headers=NO_STORE
        ) from None
    pending = request.app.state.intent_pending
    if pending.get(user.id, 0) or sum(pending.values()) >= 4:
        raise HTTPException(429, "Intent is busy; use local detection", headers=NO_STORE)
    pending[user.id] = 1
    timing = Timing(
        request.headers.get("x-meetguide-question-id"),
        stage="backend_intent",
        enabled=request.app.state.settings.app_env != "production",
    )
    timing.values.update(
        intent_route="gemini",
        question_char_count=len(payload.text),
        conversation_turn_count=len(payload.context),
        conversation_context_char_count=sum(len(turn.text) for turn in payload.context),
    )
    try:
        with timing.measure("intent_request_ms"):
            result = await asyncio.wait_for(provider.classify(payload), timeout=8)
        if result.kind == "CONTINUATION" and not payload.can_continue:
            raise ProviderUnavailable()
        from starlette.responses import JSONResponse

        return JSONResponse(result.model_dump(), headers=NO_STORE)
    except (ProviderUnavailable, TimeoutError, ValidationError) as error:
        timing.values["provider_error_type"] = (
            error.reason
            if isinstance(error, ProviderUnavailable)
            else "TIMEOUT"
            if isinstance(error, TimeoutError)
            else "RESPONSE_SCHEMA_REJECTED"
        )
        timing.values["provider_http_status"] = getattr(error, "status", None)
        raise HTTPException(
            503, "Semantic intent is unavailable; use local detection", headers=NO_STORE
        ) from None
    finally:
        timing.finish()
        pending.pop(user.id, None)
