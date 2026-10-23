"""Small backend-only OpenAI intent classifier. No retries or vendor fallback."""

import json

import httpx
from pydantic import ValidationError

from app.cues.openai import http_reason
from app.cues.provider import ProviderUnavailable
from app.intent.domain import IntentInput, IntentResult
from app.intent.prompt import SYSTEM


class OpenAIIntentProvider:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    async def classify(self, payload: IntentInput) -> IntentResult:
        if not self.settings.openai_api_key:
            raise ProviderUnavailable("KEY_NOT_CONFIGURED")
        body = {
            "model": self.settings.openai_live_cue_model,
            "instructions": SYSTEM,
            "input": [
                {"role": "user", "content": json.dumps(payload.model_dump(), ensure_ascii=False)}
            ],
            "reasoning": {"effort": "none"},
            "temperature": 0.2,
            "max_output_tokens": 384,
            "stream": False,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "meetguide_intent",
                    "strict": True,
                    "schema": IntentResult.model_json_schema(),
                }
            },
        }
        try:
            async with httpx.AsyncClient(
                timeout=8, follow_redirects=False, trust_env=False, transport=self.transport
            ) as client:
                async with client.stream(
                    "POST",
                    "https://api.openai.com/v1/responses",
                    headers={
                        "Authorization": "Bearer " + self.settings.openai_api_key.get_secret_value()
                    },
                    json=body,
                ) as response:
                    if response.status_code != 200:
                        # Never parse provider error bodies: they may echo private input.
                        raise ProviderUnavailable(
                            http_reason(response.status_code), response.status_code
                        )
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 32768:
                            raise ProviderUnavailable("RESPONSE_TOO_LARGE", 200)
            data = json.loads(raw)
            if data["status"] != "completed" or len(data["output"]) != 1:
                raise ProviderUnavailable("MALFORMED_RESPONSE", 200)
            message = data["output"][0]
            content = message["content"]
            if (
                message["type"] != "message"
                or message["status"] != "completed"
                or len(content) != 1
            ):
                raise ProviderUnavailable("MALFORMED_RESPONSE", 200)
            if content[0]["type"] != "output_text":
                raise ProviderUnavailable("FINISH_SAFETY", 200)
            return IntentResult.model_validate_json(content[0]["text"])
        except httpx.TimeoutException:
            raise ProviderUnavailable("TIMEOUT") from None
        except httpx.HTTPError:
            raise ProviderUnavailable("TRANSPORT_ERROR") from None
        except ValidationError:
            raise ProviderUnavailable("RESPONSE_SCHEMA_REJECTED", 200) from None
        except ValueError, KeyError, TypeError, AttributeError, IndexError:
            raise ProviderUnavailable("MALFORMED_RESPONSE", 200) from None
