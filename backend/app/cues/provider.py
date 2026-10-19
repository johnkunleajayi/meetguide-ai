"""Vendor-neutral boundary. Credentials and HTTP stay in the backend adapter."""

from typing import Protocol

from app.cues.domain import Draft


class ProviderUnavailable(Exception):
    pass


class CueProvider(Protocol):
    async def generate(self, system: str, user: str) -> Draft: ...
