"""Deepgram Listen v1 adapter. API key stays on the server."""

import json
import logging
import math
from urllib.parse import urlencode

from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from app.transcription.provider import ProviderError, TranscriptEvent

# Prevent websocket frame/header debug logs from exposing audio, text or API keys.
WIRE_LOGGER = logging.Logger("meetguide.transcription.wire", level=logging.CRITICAL + 1)
WIRE_LOGGER.addHandler(logging.NullHandler())
WIRE_LOGGER.propagate = False


def parse_event(payload: str | bytes) -> TranscriptEvent | None:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ProviderError("The transcription provider returned an invalid response.")
    if data.get("type") == "Error":
        raise ProviderError(
            "Transcription provider rejected the stream. Check provider quota and configuration.",
            False,
        )
    if data.get("type") != "Results":
        return None
    try:
        text = data["channel"]["alternatives"][0]["transcript"]
        start = data["start"]
        final = data["is_final"]
        if not isinstance(text, str) or not isinstance(final, bool):
            raise ValueError
        if (
            isinstance(start, bool)
            or not isinstance(start, (int, float))
            or not math.isfinite(start)
            or start < 0
        ):
            raise ValueError
        return TranscriptEvent(round(start * 1000), text.strip()[:4096], final)
    except KeyError, IndexError, TypeError, ValueError:
        raise ProviderError("The transcription provider returned an invalid result.") from None


class DeepgramConnection:
    def __init__(self, socket):
        self.socket = socket

    async def send_audio(self, pcm):
        await self.socket.send(pcm)

    async def receive(self):
        return parse_event(await self.socket.recv())

    async def keepalive(self):
        await self.socket.send('{"type":"KeepAlive"}')

    async def finish(self):
        # CloseStream flushes the final results before the provider closes.
        await self.socket.send('{"type":"CloseStream"}')

    async def close(self):
        await self.socket.close()


class DeepgramProvider:
    def __init__(self, settings):
        self.settings = settings

    async def connect(self):
        query = urlencode(
            {
                "model": self.settings.transcription_model,
                "language": self.settings.transcription_language,
                "encoding": "linear16",
                "sample_rate": 16000,
                "channels": 1,
                "interim_results": "true",
                "punctuate": "true",
                "smart_format": "true",
                "endpointing": 300,
                "mip_opt_out": "true",
            }
        )
        try:
            socket = await connect(
                "wss://api.deepgram.com/v1/listen?" + query,
                additional_headers={
                    "Authorization": "Token " + self.settings.deepgram_api_key.get_secret_value()
                },
                open_timeout=8,
                close_timeout=1,
                ping_interval=20,
                ping_timeout=20,
                compression=None,
                max_size=65536,
                max_queue=8,
                logger=WIRE_LOGGER,
            )
        except InvalidStatus as error:
            if error.response.status_code in {400, 401, 402, 403}:
                raise ProviderError(
                    "Deepgram rejected the connection. Check backend key, account and model.",
                    False,
                ) from None
            raise ProviderError("Transcription provider is unavailable. Reconnecting.") from None
        except Exception:
            raise ProviderError(
                "Cannot connect to the transcription provider. Check backend internet access."
            ) from None
        return DeepgramConnection(socket)
