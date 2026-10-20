import json
import logging

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.cues.domain import Draft
from app.cues.provider import ProviderUnavailable

logger = logging.getLogger(__name__)
ERROR_CODES = {
    "INVALID_ARGUMENT",
    "NOT_FOUND",
    "PERMISSION_DENIED",
    "UNAUTHENTICATED",
    "RESOURCE_EXHAUSTED",
    "UNAVAILABLE",
    "INTERNAL",
    "FAILED_PRECONDITION",
}
FINISH_CODES = {
    "STOP",
    "MAX_TOKENS",
    "SAFETY",
    "RECITATION",
    "OTHER",
    "BLOCKLIST",
    "PROHIBITED_CONTENT",
    "SPII",
}


def unavailable(reason: str, status: int | None = None) -> ProviderUnavailable:
    # Only application-controlled reasons/statuses; never exception text, headers or bodies.
    logger.warning("Live Cue Gemini failure: http_status=%s reason=%s", status, reason)
    return ProviderUnavailable(reason, status)


def http_reason(data: bytes) -> str:
    try:
        error = json.loads(data).get("error", {})
        status = error.get("status")
        return status if status in ERROR_CODES else "HTTP_ERROR"
    except ValueError, TypeError, AttributeError:
        return "HTTP_ERROR"


class GeminiProvider:
    def __init__(self, settings: Settings, transport=None):
        self.settings, self.transport = settings, transport

    async def stream(self, system: str, user: str):
        from app.cues.gemini_stream import stream

        async for fragment in stream(self, system, user):
            yield fragment

    async def generate(self, system: str, user: str) -> Draft:
        return await self.request_json(system, user, Draft, 2200)

    async def request_json(self, system: str, user: str, response_model, token_limit: int):
        if not self.settings.gemini_api_key:
            raise unavailable("KEY_NOT_CONFIGURED")
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.settings.live_cue_model}:generateContent"
        try:
            async with httpx.AsyncClient(
                timeout=25, follow_redirects=False, transport=self.transport, trust_env=False
            ) as client:
                async with client.stream(
                    "POST",
                    endpoint,
                    headers={"x-goog-api-key": self.settings.gemini_api_key.get_secret_value()},
                    json={
                        "systemInstruction": {"parts": [{"text": system}]},
                        "contents": [{"role": "user", "parts": [{"text": user}]}],
                        "generationConfig": {
                            "temperature": 0.2,
                            "maxOutputTokens": token_limit,
                            "responseMimeType": "application/json",
                            "responseJsonSchema": response_model.model_json_schema(),
                        },
                    },
                ) as response:
                    data = bytearray()
                    async for part in response.aiter_bytes():
                        if len(data) + len(part) > 65536:
                            raise unavailable("RESPONSE_TOO_LARGE", response.status_code)
                        data.extend(part)
                    if response.status_code != 200:
                        raise unavailable(http_reason(data), response.status_code)

            body = json.loads(data)
            candidates = body["candidates"]
            if len(candidates) != 1:
                raise unavailable("NO_SINGLE_CANDIDATE", 200)
            finish = candidates[0].get("finishReason")
            if finish != "STOP":
                code = finish if isinstance(finish, str) and finish in FINISH_CODES else "UNKNOWN"
                raise unavailable("FINISH_" + code, 200)
            parts = candidates[0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts if not part.get("thought", False))
            return response_model.model_validate_json(text)
        except httpx.TimeoutException:
            raise unavailable("TIMEOUT") from None
        except httpx.HTTPError:
            raise unavailable("TRANSPORT_ERROR") from None
        except ValidationError:
            raise unavailable("RESPONSE_SCHEMA_REJECTED", 200) from None
        except ValueError, KeyError, TypeError, AttributeError, IndexError:
            # HTTP/parser exceptions may contain secrets or input; never surface/log them.
            raise unavailable("MALFORMED_RESPONSE", 200) from None
