"""Bounded Gemini SSE adapter. Yields JSON text fragments, never protocol frames."""

import json

import httpx

from app.cues.domain import Draft
from app.cues.gemini import FINISH_CODES, http_reason, unavailable
from app.cues.stream_timing import mark


async def stream(provider, system, user):
    if not provider.settings.gemini_api_key:
        raise unavailable("KEY_NOT_CONFIGURED")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{provider.settings.live_cue_model}:streamGenerateContent?alt=sse"
    try:
        async with httpx.AsyncClient(
            timeout=25, follow_redirects=False, transport=provider.transport, trust_env=False
        ) as client:
            mark("http_request_started")
            async with client.stream(
                "POST",
                endpoint,
                headers={"x-goog-api-key": provider.settings.gemini_api_key.get_secret_value()},
                json={
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                    "generationConfig": {
                        "temperature": 0.2,
                        "maxOutputTokens": 2200,
                        "responseMimeType": "application/json",
                        "responseJsonSchema": Draft.model_json_schema(),
                    },
                },
            ) as response:
                mark("headers_received")
                received = 0
                buffer = bytearray()
                data = []
                stopped = False
                async for chunk in response.aiter_bytes():
                    if chunk:
                        mark("first_raw_chunk")
                    received += len(chunk)
                    if received > (65536 if response.status_code != 200 else 1048576):
                        raise unavailable("RESPONSE_TOO_LARGE", response.status_code)
                    buffer.extend(chunk)
                    if response.status_code != 200:
                        continue
                    if len(buffer) > 65536 and b"\n" not in buffer:
                        raise unavailable("RESPONSE_TOO_LARGE", 200)
                    while b"\n" in buffer:
                        line, _, rest = buffer.partition(b"\n")
                        buffer = bytearray(rest)
                        line = line.rstrip(b"\r")
                        if line.startswith(b"data:"):
                            data.append(line[5:].lstrip())
                        elif not line and data:
                            event = json.loads(b"\n".join(data))
                            data = []
                            if "candidates" not in event and set(event) <= {
                                "usageMetadata",
                                "modelVersion",
                                "responseId",
                            }:
                                continue
                            if stopped:
                                raise unavailable("MALFORMED_RESPONSE", 200)
                            candidates = event["candidates"]
                            if len(candidates) != 1 or candidates[0].get("index", 0) != 0:
                                raise unavailable("NO_SINGLE_CANDIDATE", 200)
                            candidate = candidates[0]
                            finish = candidate.get("finishReason")
                            if finish:
                                if finish != "STOP":
                                    code = finish if finish in FINISH_CODES else "UNKNOWN"
                                    raise unavailable("FINISH_" + code, 200)
                                stopped = True
                            for part in candidate.get("content", {}).get("parts", []):
                                if not part.get("thought", False):
                                    value = part.get("text", "")
                                    if not isinstance(value, str):
                                        raise ValueError
                                    if value:
                                        mark("first_content_fragment")
                                        yield value
                if response.status_code != 200:
                    raise unavailable(http_reason(buffer), response.status_code)
                if buffer.strip() or data or not stopped:
                    raise unavailable("MALFORMED_RESPONSE", 200)
    except httpx.TimeoutException:
        raise unavailable("TIMEOUT") from None
    except httpx.HTTPError:
        raise unavailable("TRANSPORT_ERROR") from None
    except ValueError, KeyError, TypeError, AttributeError, IndexError:
        raise unavailable("MALFORMED_RESPONSE", 200) from None
