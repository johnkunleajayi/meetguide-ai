"""Provider-neutral streaming speech-to-text contract. No storage or logging."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, repr=False)
class TranscriptEvent:
    segment: int
    text: str
    final: bool
    provider_received_at: float | None = field(default=None, compare=False)


class ProviderError(Exception):
    """Safe, actionable error; never include vendor responses or credentials."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class StreamingConnection(Protocol):
    async def send_audio(self, pcm: bytes) -> None: ...
    async def receive(self) -> TranscriptEvent | None: ...
    async def keepalive(self) -> None: ...
    async def finish(self) -> None: ...
    async def close(self) -> None: ...


class StreamingProvider(Protocol):
    async def connect(self) -> StreamingConnection: ...


def get_provider(settings) -> StreamingProvider:
    # Explicit selection only: provider failures never spend another vendor's quota.
    if settings.transcription_provider == "gemini":
        from app.transcription.gemini import GeminiTranscriptionProvider

        if settings.gemini_api_key:
            return GeminiTranscriptionProvider(settings)
        raise ProviderError("Set GEMINI_API_KEY on the backend and restart the API.", False)
    if settings.transcription_provider == "deepgram":
        from app.transcription.deepgram import DeepgramProvider

        if settings.deepgram_api_key:
            return DeepgramProvider(settings)
        raise ProviderError("Set DEEPGRAM_API_KEY on the backend and restart the API.", False)
    raise ProviderError("Unsupported transcription provider configuration.", False)
