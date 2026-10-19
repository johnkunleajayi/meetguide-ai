from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Process liveness only; database readiness is deliberately not checked."""
    return HealthResponse(status="ok", service=request.app.state.settings.app_name)
