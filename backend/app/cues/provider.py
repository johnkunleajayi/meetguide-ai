"""Vendor-neutral boundary. Credentials and HTTP stay in the backend adapter."""

from collections.abc import AsyncIterator
from typing import Protocol

from app.cues.domain import Draft


class ProviderUnavailable(Exception):
    def __init__(self, reason="PROVIDER_UNAVAILABLE", status=None):
        allowed = {
            "PROVIDER_UNAVAILABLE",
            "KEY_NOT_CONFIGURED",
            "VALIDATION_REJECTED",
            "INVALID_ARGUMENT",
            "NOT_FOUND",
            "PERMISSION_DENIED",
            "UNAUTHENTICATED",
            "RESOURCE_EXHAUSTED",
            "UNAVAILABLE",
            "INTERNAL",
            "FAILED_PRECONDITION",
            "HTTP_ERROR",
            "RESPONSE_TOO_LARGE",
            "NO_SINGLE_CANDIDATE",
            "TIMEOUT",
            "TRANSPORT_ERROR",
            "RESPONSE_SCHEMA_REJECTED",
            "MALFORMED_RESPONSE",
            "FINISH_STOP",
            "FINISH_MAX_TOKENS",
            "FINISH_SAFETY",
            "FINISH_RECITATION",
            "FINISH_OTHER",
            "FINISH_BLOCKLIST",
            "FINISH_PROHIBITED_CONTENT",
            "FINISH_SPII",
            "FINISH_UNKNOWN",
        }
        self.reason = reason if reason in allowed else "PROVIDER_UNAVAILABLE"
        self.status = status if type(status) is int and 100 <= status <= 599 else None
        super().__init__()


class CueProvider(Protocol):
    def stream(self, system: str, user: str) -> AsyncIterator[str]: ...

    async def generate(self, system: str, user: str) -> Draft: ...
