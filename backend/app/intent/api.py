import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from app.api.auth import NO_STORE
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
    try:
        result = await asyncio.wait_for(provider.classify(payload), timeout=8)
        if result.kind == "CONTINUATION" and not payload.can_continue:
            raise ProviderUnavailable()
        from starlette.responses import JSONResponse

        return JSONResponse(result.model_dump(), headers=NO_STORE)
    except ProviderUnavailable, TimeoutError, ValidationError:
        raise HTTPException(
            503, "Semantic intent is unavailable; use local detection", headers=NO_STORE
        ) from None
    finally:
        pending.pop(user.id, None)
