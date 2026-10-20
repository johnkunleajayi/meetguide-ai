"""Gemini dedicated Live STT adapter. Audio/text exist only in bounded memory."""

import asyncio
import base64
import json
import logging
import time
from collections import deque

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from app.transcription.provider import ProviderError, TranscriptEvent

WIRE_LOGGER = logging.Logger("meetguide.transcription.gemini.wire", logging.CRITICAL + 1)
WIRE_LOGGER.addHandler(logging.NullHandler())
WIRE_LOGGER.propagate = False
URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
VOCABULARY = [
    "Salesforce",
    "Service Cloud",
    "Sales Cloud",
    "HubSpot",
    "Zapier",
    "Zendesk",
    "Paystack",
    "RevOps",
    "Apex",
    "SOQL",
    "LWC",
    "Omni-Channel",
]
RENEW_SECONDS = 570  # Renew before the documented ten-minute provider session limit.


def decode(payload):
    try:
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError
    except ValueError, TypeError, UnicodeError:
        raise ProviderError("Gemini transcription returned a malformed event.") from None
    if "error" in data:
        error = data["error"]
        code = error.get("code") if isinstance(error, dict) else None
        if code in {401, 403}:
            raise ProviderError(
                "Gemini transcription authentication failed. Check backend key/access.", False
            )
        if code == 429:
            raise ProviderError(
                "Gemini transcription quota/rate limit reached. Check quota before restarting.",
                False,
            )
        raise ProviderError(
            "Gemini transcription rejected the stream. Check backend model configuration.", False
        )
    return data


class GeminiConnection:
    def __init__(self, socket):
        self.socket = socket
        self.began = time.monotonic()
        self.segment = None
        self.last_segment = -1
        self.events = deque()
        self.pending = bytearray()
        self.finishing = False

    async def send_audio(self, pcm):
        # Aggregate existing 20ms PCM packets into 100ms, without transcoding.
        self.pending.extend(pcm)
        while len(self.pending) >= 3200:
            chunk = bytes(self.pending[:3200])
            del self.pending[:3200]
            await self._audio(chunk)

    async def _audio(self, pcm):
        await self.socket.send(
            json.dumps(
                {
                    "realtimeInput": {
                        "audio": {
                            "data": base64.b64encode(pcm).decode("ascii"),
                            "mimeType": "audio/pcm;rate=16000",
                        }
                    }
                }
            )
        )

    def normalize(self, data):
        if "goAway" in data:
            raise ProviderError(
                "Gemini transcription renewing connection; speech during the gap may be missing."
            )
        content = data.get("serverContent", {})
        if not isinstance(content, dict):
            raise ProviderError("Gemini transcription returned a malformed event.")
        # These are independent hypotheses/finals, not conversational-model text deltas.
        for key, final in (("interimInputTranscription", False), ("inputTranscription", True)):
            if key not in content:
                continue
            item = content[key]
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                raise ProviderError("Gemini transcription returned a malformed transcript.")
            text = item["text"].strip()
            if not text and self.segment is None:
                continue
            if self.segment is None:
                # Live STT has no word timestamps: use receipt-relative milliseconds.
                self.segment = max(
                    self.last_segment + 1, int((time.monotonic() - self.began) * 1000)
                )
            self.events.append(TranscriptEvent(self.segment, text[:4096], final))
            if final:
                self.last_segment = self.segment
                self.segment = None

    async def receive(self):
        if self.events:
            return self.events.popleft()
        try:
            data = decode(await self.socket.recv())
        except ConnectionClosed as error:
            if self.finishing:
                raise
            code = error.rcvd.code if error.rcvd else None
            if code in {1008, 1007}:
                raise ProviderError(
                    "Gemini transcription rejected access/configuration. Check model/key/quota.",
                    False,
                ) from None
            raise ProviderError(
                "Gemini transcription disconnected. Reconnecting; gap audio is not buffered."
            ) from None
        self.normalize(data)
        return self.events.popleft() if self.events else None

    async def keepalive(self):
        if not self.finishing and time.monotonic() - self.began >= RENEW_SECONDS:
            raise ProviderError(
                "Gemini transcription session renewal. Reconnecting; gap audio may be missing."
            )
        await self.socket.ping()

    async def finish(self):
        self.finishing = True
        if self.pending:
            await self._audio(bytes(self.pending))
            self.pending.clear()
        await self.socket.send('{"realtimeInput":{"audioStreamEnd":true}}')

    async def close(self):
        self.pending.clear()
        self.events.clear()
        await self.socket.close()


class GeminiTranscriptionProvider:
    def __init__(self, settings):
        self.settings = settings

    async def connect(self):
        # Native relay allows ten seconds for ready; cap the entire handshake below it.
        try:
            return await asyncio.wait_for(self._connect(), timeout=8)
        except TimeoutError:
            raise ProviderError("Gemini transcription setup timed out. Reconnecting.") from None

    async def _connect(self):
        socket = None
        try:
            socket = await connect(
                URL + "?key=" + self.settings.gemini_api_key.get_secret_value(),
                open_timeout=8,
                close_timeout=1,
                ping_interval=20,
                ping_timeout=20,
                compression=None,
                max_size=65536,
                max_queue=8,
                logger=WIRE_LOGGER,
            )
            await asyncio.wait_for(
                socket.send(
                    json.dumps(
                        {
                            "setup": {
                                "model": "models/" + self.settings.gemini_transcribe_model,
                                "generationConfig": {"responseModalities": ["TEXT"]},
                                "inputAudioTranscription": {
                                    "languageCodes": [self.settings.transcription_language],
                                    "mode": "VERBATIM",
                                    "customVocabulary": VOCABULARY,
                                },
                                # Automatic VAD; local assembly remains authoritative.
                            }
                        }
                    )
                ),
                timeout=3,
            )
            data = decode(await asyncio.wait_for(socket.recv(), timeout=8))
            if "setupComplete" not in data:
                raise ProviderError("Gemini transcription setup was not acknowledged.")
            return GeminiConnection(socket)
        except BaseException as error:
            if socket is not None:
                try:
                    await asyncio.wait_for(socket.close(), timeout=1)
                except Exception:
                    pass
            if isinstance(error, (ProviderError, asyncio.CancelledError)):
                raise
            if (
                isinstance(error, ConnectionClosed)
                and error.rcvd
                and error.rcvd.code in {1007, 1008}
            ):
                raise ProviderError(
                    "Gemini transcription rejected setup. Check backend model/key/quota.", False
                ) from None
            if isinstance(error, InvalidStatus) and error.response.status_code in {
                400,
                401,
                403,
                429,
            }:
                raise ProviderError(
                    "Gemini rejected transcription access/config/quota. Check backend settings.",
                    False,
                ) from None
            raise ProviderError(
                "Cannot connect to Gemini transcription. Check backend network/model access."
            ) from None
