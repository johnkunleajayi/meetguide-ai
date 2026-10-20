"""Bounded Responses SSE normalization into the existing JSON-fragment contract."""

import json

from app.cues.provider import ProviderUnavailable
from app.cues.stream_timing import mark


async def events(response):
    received, buffer, data = 0, bytearray(), []
    async for chunk in response.aiter_bytes():
        if chunk:
            mark("first_raw_chunk")
        received += len(chunk)
        if received > 1048576:
            raise ProviderUnavailable("RESPONSE_TOO_LARGE", 200)
        buffer.extend(chunk)
        while b"\n" in buffer:
            line, _, rest = buffer.partition(b"\n")
            buffer = bytearray(rest)
            line = line.rstrip(b"\r")
            if line.startswith(b"data:"):
                data.append(line[5:].lstrip())
                if sum(map(len, data)) > 65536:
                    raise ProviderUnavailable("RESPONSE_TOO_LARGE", 200)
            elif not line and data:
                event = json.loads(b"\n".join(data))
                data = []
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    raise ValueError
                yield event
        if len(buffer) > 65536:
            raise ProviderUnavailable("RESPONSE_TOO_LARGE", 200)
    if buffer.strip() or data:
        raise ValueError


def text_fragment(event, raw):
    kind = event["type"]
    if kind in {"response.refusal.delta", "response.refusal.done"}:
        raise ProviderUnavailable("FINISH_SAFETY", 200)
    if kind in {"error", "response.failed", "response.incomplete"}:
        # Fixed mappings only. Never retain/emit provider messages or arbitrary codes.
        error = event if kind == "error" else event.get("response", {}).get("error") or {}
        reason = {
            "rate_limit_exceeded": "RESOURCE_EXHAUSTED",
            "insufficient_quota": "RESOURCE_EXHAUSTED",
            "server_error": "UNAVAILABLE",
            "invalid_api_key": "UNAUTHENTICATED",
        }.get(error.get("code"), "PROVIDER_UNAVAILABLE")
        raise ProviderUnavailable(reason, 200)
    if kind == "response.output_text.delta":
        if event["output_index"] != 0 or event["content_index"] != 0:
            raise ValueError
        delta = event["delta"]
        if not isinstance(delta, str):
            raise ValueError
        return delta, False
    if kind == "response.completed":
        response = event["response"]
        output = response["output"]
        if response["status"] != "completed" or len(output) != 1:
            raise ValueError
        message = output[0]
        content = message["content"]
        if (
            message["type"] != "message"
            or message["status"] != "completed"
            or len(content) != 1
            or content[0]["type"] != "output_text"
            or content[0]["text"] != raw
        ):
            raise ValueError
        return "", True
    if kind not in {
        "response.created",
        "response.in_progress",
        "response.queued",
        "response.output_item.added",
        "response.content_part.added",
        "response.output_text.done",
        "response.content_part.done",
        "response.output_item.done",
    }:
        raise ValueError
    return "", False
