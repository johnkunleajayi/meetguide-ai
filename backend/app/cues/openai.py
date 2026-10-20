"""Optional Live Cue adapter. HTTPX only; no SDK retries or cross-provider fallback."""

import logging

import httpx
from pydantic import ValidationError

from app.core.timing import current
from app.cues.domain import Draft
from app.cues.openai_stream import events, text_fragment
from app.cues.provider import ProviderUnavailable
from app.cues.stream_timing import mark

logger = logging.getLogger(__name__)


def unavailable(reason, status=None):
    error = ProviderUnavailable(reason, status)
    logger.warning("Live Cue OpenAI failure: http_status=%s reason=%s", error.status, error.reason)
    return error


def http_reason(status):
    return {
        400: "INVALID_ARGUMENT",
        401: "UNAUTHENTICATED",
        403: "PERMISSION_DENIED",
        404: "NOT_FOUND",
        408: "TIMEOUT",
        429: "RESOURCE_EXHAUSTED",
        500: "INTERNAL",
        502: "UNAVAILABLE",
        503: "UNAVAILABLE",
        504: "TIMEOUT",
    }.get(status, "HTTP_ERROR")


class OpenAIProvider:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    async def generate(self, system: str, user: str) -> Draft:
        # Legacy whole-response clients consume the same bounded structured stream.
        raw = "".join([fragment async for fragment in self.stream(system, user)])
        try:
            return Draft.model_validate_json(raw)
        except ValidationError:
            raise unavailable("RESPONSE_SCHEMA_REJECTED", 200) from None

    async def stream(self, system: str, user: str):
        if not self.settings.openai_api_key:
            raise unavailable("KEY_NOT_CONFIGURED")
        if timing := current.get():
            timing.values.update(provider="openai", model=self.settings.openai_live_cue_model)
        schema = Draft.model_json_schema()
        # Strict Structured Outputs requires every property, including empty evidence_ids.
        # This changes only the wire schema; shared Draft/grounding semantics stay intact.
        schema["required"] = list(schema["properties"])
        schema["properties"]["evidence_ids"].pop("default", None)
        body = {
            "model": self.settings.openai_live_cue_model,
            "instructions": system,
            "input": [{"role": "user", "content": user}],
            "reasoning": {"effort": "none"},
            "temperature": 0.2,
            "max_output_tokens": 2200,
            "stream": True,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "meetguide_live_cue",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        try:
            async with httpx.AsyncClient(
                timeout=25, follow_redirects=False, transport=self.transport, trust_env=False
            ) as client:
                mark("http_request_started")
                async with client.stream(
                    "POST",
                    "https://api.openai.com/v1/responses",
                    headers={
                        "Authorization": "Bearer "
                        + self.settings.openai_api_key.get_secret_value(),
                        "Accept": "text/event-stream",
                    },
                    json=body,
                ) as response:
                    mark("headers_received")
                    if response.status_code != 200:
                        # Never parse/log provider error bodies: they can echo private input.
                        raise unavailable(http_reason(response.status_code), response.status_code)
                    raw, complete = "", False
                    async for event in events(response):
                        if complete:
                            raise unavailable("MALFORMED_RESPONSE", 200)
                        fragment, complete = text_fragment(event, raw)
                        if fragment:
                            raw += fragment
                            if len(raw.encode()) > 16384:
                                raise unavailable("RESPONSE_TOO_LARGE", 200)
                            mark("first_content_fragment")
                            yield fragment
                    if not complete or not raw:
                        raise unavailable("MALFORMED_RESPONSE", 200)
        except httpx.TimeoutException:
            raise unavailable("TIMEOUT") from None
        except httpx.HTTPError:
            raise unavailable("TRANSPORT_ERROR") from None
        except ValueError, KeyError, TypeError, AttributeError, IndexError:
            raise unavailable("MALFORMED_RESPONSE", 200) from None
