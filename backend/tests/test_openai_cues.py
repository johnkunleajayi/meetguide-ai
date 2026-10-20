"""Fictional documents and mocked HTTPX streams only; never load .env or call providers."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from test_cues import PARAGRAPHS, QUOTE, draft, evidence, payload
from test_cues import cue_api as cue_api

from app.core.timing import Timing, current
from app.cues import api
from app.cues.gemini import GeminiProvider
from app.cues.openai import OpenAIProvider
from app.cues.provider import ProviderUnavailable
from app.cues.service import generate_cue
from app.cues.stream_timing import STAGES
from app.preparations.domain import Selection
from app.preparations.snapshot import freeze, resolve


@pytest.fixture(autouse=True)
def no_provider_network(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("Use MockTransport; real provider traffic is forbidden")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)


def frame(event):
    return (
        "event: "
        + event["type"]
        + "\r\ndata: "
        + json.dumps(event, ensure_ascii=False)
        + "\r\n\r\n"
    ).encode()


def delta(text):
    return {
        "type": "response.output_text.delta",
        "output_index": 0,
        "content_index": 0,
        "delta": text,
    }


def complete(raw):
    return {
        "type": "response.completed",
        "response": {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": raw}],
                }
            ],
        },
    }


def frames(value):
    raw = value.model_dump_json() if hasattr(value, "model_dump_json") else value
    return (
        [frame({"type": "response.created"})]
        + [frame(delta(raw[i : i + 53])) for i in range(0, len(raw), 53)]
        + [frame(complete(raw))]
    )


class Stream(httpx.AsyncByteStream):
    def __init__(self, chunks, error=None):
        self.chunks, self.error = chunks, error
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            await asyncio.sleep(0)
            yield chunk
        if self.error:
            raise self.error

    async def aclose(self):
        self.closed = True


def configure(settings):
    settings.live_cue_enabled = True
    settings.live_cue_provider = "openai"
    settings.openai_api_key = SecretStr("fictional-openai-key")


def install(client, monkeypatch, handler):
    settings = client.app.state.settings
    configure(settings)
    client.app.dependency_overrides.pop(api.get_provider, None)
    provider = OpenAIProvider(settings, httpx.MockTransport(handler))
    monkeypatch.setattr(api, "OpenAIProvider", lambda settings: provider)

    def forbidden(*args, **kwargs):
        pytest.fail("OpenAI must never fall back to Gemini")

    monkeypatch.setattr(api, "GeminiProvider", forbidden)
    return provider


def post(client, attempt=1):
    response = client.post(
        "/api/cues/generate",
        json={**payload().model_dump(), "preparation_token": client.preparation_token},
        headers={
            "Authorization": "Bearer " + "a" * 43,
            "Accept": "application/x-ndjson",
            "X-MeetGuide-Question-Id": "q-openai",
            "X-MeetGuide-Attempt": str(attempt),
        },
    )
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines()]


def timing_records(caplog):
    return [
        json.loads(r.message.split("[MeetGuide Timing] ")[1])
        for r in caplog.records
        if "[MeetGuide Timing]" in r.message
    ]


def test_provider_selection_and_missing_key_do_not_fall_back(settings):
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)), headers={}
    )
    assert settings.live_cue_provider == "gemini"
    settings.live_cue_enabled = True
    settings.gemini_api_key = SecretStr("fictional-gemini-key")
    assert isinstance(api.get_provider(request), GeminiProvider)
    settings.live_cue_provider = "openai"
    with pytest.raises(HTTPException) as error:
        api.get_provider(request)
    assert error.value.status_code == 503
    settings.openai_api_key = SecretStr("fictional-openai-key")
    settings.gemini_api_key = None
    assert isinstance(api.get_provider(request), OpenAIProvider)
    settings.live_cue_enabled = False
    with pytest.raises(HTTPException):
        api.get_provider(request)
    assert "fictional-openai-key" not in repr(settings)


def test_openai_partial_precedes_completion_with_same_prompt_schema_and_validation(settings):
    from app.cues.prompt import SYSTEM, user_prompt

    configure(settings)

    async def run():
        ready, finish = asyncio.Event(), asyncio.Event()
        output = draft(True)
        raw = output.model_dump_json()
        boundary = raw.index(PARAGRAPHS[1])
        item = evidence()
        request_payload = payload(
            context=[{"speaker": "them", "text": "A fictional project topic."}]
        )

        class Paused(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield frame(delta(raw[:boundary]))
                await finish.wait()
                yield frame(delta(raw[boundary:]))
                yield frame(complete(raw))

        def handler(request):
            assert request.url == "https://api.openai.com/v1/responses"
            assert request.headers["authorization"] == "Bearer fictional-openai-key"
            body = json.loads(request.content)
            assert body["instructions"] == SYSTEM
            assert body["input"] == [
                {"role": "user", "content": user_prompt(request_payload, [item])}
            ]
            assert body["model"] == "gpt-6-luna"
            assert body["reasoning"] == {"effort": "none"}
            assert body["stream"] is True and body["store"] is False
            assert body["max_output_tokens"] == 2200
            schema = body["text"]["format"]["schema"]
            assert body["text"]["format"]["strict"] is True
            assert schema["additionalProperties"] is False
            assert set(schema["required"]) == {"paragraphs", "evidence_ids"}
            return httpx.Response(200, stream=Paused())

        emitted = []

        async def emit(event):
            emitted.append(event)
            if event["type"] == "partial":
                ready.set()

        timing = Timing("q-openai")
        token = current.set(timing)
        try:
            task = asyncio.create_task(
                generate_cue(
                    OpenAIProvider(settings, httpx.MockTransport(handler)),
                    request_payload,
                    [item],
                    emit,
                )
            )
            await asyncio.wait_for(ready.wait(), 1)
            assert not task.done()
            assert emitted[0]["answer"].startswith("I developed Salesforce")
            finish.set()
            result = await task
            assert result.answer == "\n\n".join(output.paragraphs)
            assert result.grounding == "document_supported"
            assert result.sources[0].document_id == item.document_id
            assert timing.values["live_cue_time_to_first_output_ms"] >= 0
        finally:
            current.reset(token)

    asyncio.run(run())


def test_openai_endpoint_uses_frozen_context_and_all_timing_boundaries(
    cue_api, monkeypatch, caplog
):
    client, _, repository, user = cue_api
    requests = []
    scope = resolve(client.app, user.id, client.preparation_token)

    def handler(request):
        body = json.loads(request.content)
        data = json.loads(body["input"][0]["content"])
        requests.append(data)
        assert data["session_preparation"] == {
            "purpose": scope.purpose,
            "objective": scope.objective,
        }
        assert data["document_evidence"][0]["text"] == QUOTE
        return httpx.Response(200, stream=Stream(frames(draft(True))))

    install(client, monkeypatch, handler)
    events = post(client)
    assert events[-1]["type"] == "ready"
    assert events[-1]["result"]["grounding"] == "document_supported"
    assert any(e["type"] == "partial" for e in events)
    assert all(e["question_id"] == "q-openai" and e["attempt"] == 1 for e in events)
    assert repository.owners == [user.id] and len(requests) == 1
    assert not client.app.state.cue_pending
    record = timing_records(caplog)[-1]
    assert record["provider"] == "openai" and record["model"] == "gpt-6-luna"
    assert record["retrieved_excerpt_count"] == 1 and record["retrieval_ms"] >= 0
    for stage in STAGES:
        assert record["stream_diagnostics"][0][stage + "_offset_ms"] >= 0
    for secret in [QUOTE, payload().question, PARAGRAPHS[0], "fictional-openai-key", "a" * 43]:
        assert secret not in json.dumps(timing_records(caplog))


@pytest.mark.parametrize("scope_kind", ["empty", "different", "other_user"])
def test_openai_cannot_receive_unselected_resume(cue_api, monkeypatch, scope_kind):
    client, _, repository, user = cue_api
    selected = (
        [] if scope_kind == "empty" else [Selection(document_id=uuid4(), context_role="agenda")]
    )
    view = SimpleNamespace(
        id=uuid4(), purpose="sales_meeting", objective="Fictional client review", documents=selected
    )
    client.preparation_token = freeze(
        client.app, uuid4() if scope_kind == "other_user" else user.id, view
    )
    calls = []

    def handler(request):
        data = json.loads(json.loads(request.content)["input"][0]["content"])
        assert data["document_evidence"] == []
        assert data["session_preparation"]["purpose"] == "sales_meeting"
        calls.append(data)
        return httpx.Response(200, stream=Stream(frames(draft())))

    install(client, monkeypatch, handler)
    if scope_kind == "other_user":
        response = client.post(
            "/api/cues/generate",
            json={**payload().model_dump(), "preparation_token": client.preparation_token},
            headers={"Authorization": "Bearer " + "a" * 43, "Accept": "application/x-ndjson"},
        )
        assert response.status_code == 409 and not calls
    else:
        events = post(client)
        assert events[-1]["result"]["grounding"] == "general_approach"
        assert events[-1]["result"]["sources"] == [] and len(calls) == 1


@pytest.mark.parametrize(
    "failure",
    [
        "before",
        "after",
        "timeout_before",
        "timeout_after",
        "malformed",
        "missing_complete",
        "mismatch",
        "refusal",
        "quota",
        "unavailable",
    ],
)
def test_openai_failures_are_safe_and_never_use_gemini(cue_api, monkeypatch, caplog, failure):
    client, *_ = cue_api
    calls, streams = [], []

    def handler(request):
        calls.append(1)
        if failure in {"quota", "unavailable"}:
            return httpx.Response(
                429 if failure == "quota" else 503,
                json={"error": {"message": "fictional-openai-key PRIVATE_PROVIDER_CONTENT"}},
            )
        if failure == "before":
            raise httpx.ConnectError("PRIVATE_PROVIDER_CONTENT")
        if failure == "timeout_before":
            raise httpx.ReadTimeout("PRIVATE_PROVIDER_CONTENT")
        raw = draft().model_dump_json()
        chunks, error = frames(draft()), None
        if failure in {"after", "timeout_after"}:
            chunks = [frame(delta(raw[: raw.index(PARAGRAPHS[1])]))]
            error = (httpx.ReadTimeout if failure == "timeout_after" else httpx.ReadError)(
                "PRIVATE_PROVIDER_CONTENT"
            )
        elif failure == "malformed":
            chunks = [b"data: PRIVATE_PROVIDER_CONTENT\n\n"]
        elif failure == "missing_complete":
            chunks = [frame(delta(raw))]
        elif failure == "mismatch":
            chunks = [frame(delta(raw)), frame(complete("PRIVATE_PROVIDER_CONTENT"))]
        elif failure == "refusal":
            chunks = [
                frame({"type": "response.refusal.delta", "delta": "PRIVATE_PROVIDER_CONTENT"})
            ]
        stream = Stream(chunks, error)
        streams.append(stream)
        return httpx.Response(200, stream=stream)

    install(client, monkeypatch, handler)
    events = post(client)
    assert events[-1]["type"] == "error" and not any(e["type"] == "ready" for e in events)
    assert len(calls) == 1 and not client.app.state.cue_pending
    assert all(stream.closed for stream in streams)
    records = timing_records(caplog)
    assert records[-1]["provider"] == "openai"
    assert records[-1]["provider_error_type"]
    assert "PRIVATE_PROVIDER_CONTENT" not in caplog.text
    assert "fictional-openai-key" not in caplog.text


def test_openai_validation_rejection_keeps_same_bounded_regeneration_policy(
    cue_api, monkeypatch, caplog
):
    client, *_ = cue_api
    calls = []
    invalid = draft()
    invalid.paragraphs[0] += " I worked at InventedCorp on SAP projects."

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, stream=Stream(frames(invalid)))

    install(client, monkeypatch, handler)
    events = post(client)
    assert events[-1]["type"] == "error"
    assert not any(e["type"] == "ready" for e in events)
    assert any(e["type"] == "reset" for e in events)
    assert len(calls) == 2
    assert "REGENERATE CONSERVATIVELY" in calls[1]["instructions"]
    assert calls[0]["input"] == calls[1]["input"]
    record = timing_records(caplog)[-1]
    assert record["generation_attempt_count"] == 2
    assert [d["generation_attempt"] for d in record["stream_diagnostics"]] == [1, 2]
    assert "InventedCorp" not in caplog.text


def test_retry_restarts_partial_with_same_question_id_and_incremented_attempt(cue_api, monkeypatch):
    client, *_ = cue_api
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raw = draft().model_dump_json()
            return httpx.Response(
                200,
                stream=Stream(
                    [frame(delta(raw[: raw.index(PARAGRAPHS[1])]))], httpx.ReadError("private")
                ),
            )
        return httpx.Response(200, stream=Stream(frames(draft(True))))

    install(client, monkeypatch, handler)
    first = post(client)
    assert any(e["type"] == "partial" for e in first) and first[-1]["type"] == "error"
    retried = post(client, attempt=2)
    assert retried[-1]["type"] == "ready"
    assert retried[-1]["result"]["answer"] == "\n\n".join(draft(True).paragraphs)
    assert all(e["question_id"] == "q-openai" and e["attempt"] == 2 for e in retried)
    assert len(calls) == 2


def test_openai_handles_split_unicode_sse_and_legacy_reconstruction(settings):
    configure(settings)
    output = draft()
    output.paragraphs[0] = output.paragraphs[0].replace("I'd", "I’d")
    wire = b"".join(frames(output))

    def handler(request):
        return httpx.Response(200, stream=Stream([wire[i : i + 7] for i in range(0, len(wire), 7)]))

    result = asyncio.run(
        OpenAIProvider(settings, httpx.MockTransport(handler)).generate("unchanged", "context")
    )
    assert result == output


@pytest.mark.parametrize(
    "event,reason",
    [
        (
            {"type": "error", "code": "rate_limit_exceeded", "message": "private"},
            "RESOURCE_EXHAUSTED",
        ),
        (
            {
                "type": "response.failed",
                "response": {"error": {"code": "server_error", "message": "private"}},
            },
            "UNAVAILABLE",
        ),
        (
            {"type": "response.incomplete", "response": {"status": "incomplete"}},
            "PROVIDER_UNAVAILABLE",
        ),
        (
            {
                "type": "response.output_text.delta",
                "delta": 123,
                "output_index": 0,
                "content_index": 0,
            },
            "MALFORMED_RESPONSE",
        ),
        (
            {
                "type": "response.output_text.delta",
                "delta": "private",
                "output_index": 1,
                "content_index": 0,
            },
            "MALFORMED_RESPONSE",
        ),
    ],
)
def test_openai_provider_events_fail_closed_without_echoing_private_data(
    settings, caplog, event, reason
):
    configure(settings)
    provider = OpenAIProvider(
        settings,
        httpx.MockTransport(lambda request: httpx.Response(200, stream=Stream([frame(event)]))),
    )
    with pytest.raises(ProviderUnavailable) as error:
        asyncio.run(provider.generate("private instructions", "private conversation"))
    assert error.value.reason == reason
    assert "private" not in caplog.text


@pytest.mark.parametrize(
    "wire", [b"x" * 65537, frame(delta("x" * 17000))], ids=["oversized-frame", "oversized-draft"]
)
def test_openai_bounds_protocol_and_structured_output_size(settings, wire):
    configure(settings)
    provider = OpenAIProvider(
        settings, httpx.MockTransport(lambda request: httpx.Response(200, stream=Stream([wire])))
    )
    with pytest.raises(ProviderUnavailable) as error:
        asyncio.run(provider.generate("instructions", "context"))
    assert error.value.reason == "RESPONSE_TOO_LARGE"
