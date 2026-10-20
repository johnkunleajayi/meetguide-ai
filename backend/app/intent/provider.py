from typing import Protocol

from app.intent.domain import IntentInput, IntentResult


class IntentProvider(Protocol):
    async def classify(self, payload: IntentInput) -> IntentResult: ...
