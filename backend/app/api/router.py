from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.desktop_auth import router as desktop_auth_router
from app.api.health import router as health_router
from app.transcription.api import router as transcription_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)

api_router.include_router(auth_router)

api_router.include_router(desktop_auth_router)

api_router.include_router(transcription_router)
