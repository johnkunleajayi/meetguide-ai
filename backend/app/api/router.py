from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.desktop_auth import router as desktop_auth_router
from app.api.health import router as health_router
from app.context.api import router as context_router
from app.cues.api import router as cues_router
from app.intent.api import router as intent_router
from app.transcription.api import router as transcription_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)

api_router.include_router(auth_router)

api_router.include_router(desktop_auth_router)

api_router.include_router(transcription_router)

api_router.include_router(context_router)

api_router.include_router(cues_router)

api_router.include_router(intent_router)
