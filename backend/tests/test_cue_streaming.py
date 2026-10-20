"""Mocked SSE/ASGI only; no provider credentials or live traffic."""

import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr
from test_cues import PARAGRAPHS, FakeProvider, draft, evidence, payload
from test_cues import cue_api as cue_api

from app.core.timing import Timing, current
from app.cues.api import get_provider
from app.cues.domain import Draft
from app.cues.gemini import GeminiProvider
from app.cues.preview import preview
from app.cues.provider import ProviderUnavailable
from app.cues.service import generate_cue


class Stream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


class Provider(FakeProvider):
    async def stream(self, system, user):
        value = await self.generate(system, user)
        raw = value.model_dump_json()
        for i in range(0, len(raw), 23):
            await asyncio.sleep(0)
            yield raw[i : i + 23]


def test_gemini_sse_uses_identical_schema_model_and_reconstructs_fragments(settings):
    settings.gemini_api_key = SecretStr("fake-private-key")
    raw = draft().model_dump_json()
    pieces = [raw[:50], raw[50:200], raw[200:]]

    def handler(request):
        assert request.url.path.endswith(settings.live_cue_model + ":streamGenerateContent")
        assert request.url.params["alt"] == "sse"
        body = json.loads(request.content)
        assert body["generationConfig"]["responseJsonSchema"] == Draft.model_json_schema()
        assert body["generationConfig"]["maxOutputTokens"] == 2200
        frames = []
        for index, piece in enumerate(pieces):
            candidate = {"index": 0, "content": {"parts": [{"text": piece}]}}
            if index == 2:
                candidate["finishReason"] = "STOP"
            frames.append(("data: " + json.dumps({"candidates": [candidate]}) + "\n\n").encode())
        wire = b"".join(frames)
        return httpx.Response(200, stream=Stream([wire[i : i + 7] for i in range(0, len(wire), 7)]))

    async def run():
        return "".join(
            [
                s
                async for s in GeminiProvider(settings, httpx.MockTransport(handler)).stream(
                    "system", "user"
                )
            ]
        )

    assert asyncio.run(run()) == raw


@pytest.mark.parametrize(
    "mode", ["malformed", "quota", "unavailable", "disconnect", "timeout", "missing_stop"]
)
def test_gemini_stream_failures_are_sanitized(settings, mode):
    settings.gemini_api_key = SecretStr("fake-private-key")

    def handler(request):
        if mode == "timeout":
            raise httpx.ReadTimeout("private-context", request=request)
        if mode == "disconnect":
            raise httpx.ConnectError("private-context", request=request)
        if mode in {"quota", "unavailable"}:
            return httpx.Response(
                429 if mode == "quota" else 503,
                json={
                    "error": {"status": "RESOURCE_EXHAUSTED" if mode == "quota" else "UNAVAILABLE"}
                },
            )
        return httpx.Response(
            200,
            stream=Stream(
                [
                    b"data: private-context\n\n"
                    if mode == "malformed"
                    else b'data: {"candidates":[{"content":{"parts":[{"text":"{}"}]}}]}\n\n'
                ]
            ),
        )

    async def run():
        return [
            s
            async for s in GeminiProvider(settings, httpx.MockTransport(handler)).stream(
                "system", "user"
            )
        ]

    with pytest.raises(ProviderUnavailable) as error:
        asyncio.run(run())
    assert "private-context" not in str(error.value)


def test_partial_is_useful_before_provider_finishes_and_final_validation_is_unchanged():
    async def run():
        emitted = []
        saw_first = asyncio.Event()
        finish = asyncio.Event()

        class Paused:
            async def stream(self, system, user):
                raw = draft().model_dump_json()
                boundary = raw.index(PARAGRAPHS[1])
                yield raw[:boundary]
                await finish.wait()
                yield raw[boundary:]

        timing = Timing("q-stream")
        token = current.set(timing)

        async def emit(event):
            emitted.append(event)
            if event["type"] == "partial":
                saw_first.set()

        try:
            task = asyncio.create_task(generate_cue(Paused(), payload(), [], emit))
            await asyncio.wait_for(saw_first.wait(), 1)
            assert not task.done() and emitted[0]["answer"].startswith("I would start")
            assert "paragraphs" not in emitted[0]["answer"]
            assert timing.values["live_cue_time_to_first_output_ms"] >= 0
            finish.set()
            result = await task
            assert result.answer == "\n\n".join(PARAGRAPHS)
        finally:
            current.reset(token)

    asyncio.run(run())


def test_preview_blocks_obvious_unsupported_history_and_unfinished_claims():
    assert not preview('{"paragraphs":["I worked at InventedCorp on SAP projects."]}', [])
    assert not preview('{"paragraphs":["I worked at InventedCorp', [evidence()])
    assert (
        preview(json.dumps({"paragraphs": ["I would clarify the goal."]}), [])
        == "I would clarify the goal."
    )


def test_streaming_endpoint_keeps_scope_validates_and_logs_no_private_text(cue_api, caplog):
    client, _, repository, _ = cue_api
    provider = Provider()
    client.app.dependency_overrides[get_provider] = lambda: provider
    response = client.post(
        "/api/cues/generate",
        json={**payload().model_dump(), "preparation_token": client.preparation_token},
        headers={
            "Authorization": "Bearer " + "a" * 43,
            "Accept": "application/x-ndjson",
            "X-MeetGuide-Question-Id": "q-stream",
            "X-MeetGuide-Attempt": "2",
        },
    )
    events = [json.loads(line) for line in response.text.splitlines()]
    assert response.status_code == 200 and events[-1]["type"] == "ready"
    assert any(e["type"] == "partial" for e in events[:-1])
    assert all(e["question_id"] == "q-stream" and e["attempt"] == 2 for e in events)
    assert events[-1]["result"]["grounding"] == "document_supported"
    assert repository.owners and not client.app.state.cue_pending
    records = [
        json.loads(r.message.split("[MeetGuide Timing] ")[1])
        for r in caplog.records
        if "[MeetGuide Timing]" in r.message
    ]
    assert records[-1]["live_cue_streaming"] is True
    assert records[-1]["retrieval_ms"] >= 0 and records[-1]["validation_ms"] >= 0
    assert records[-1]["live_cue_completed_at"] >= records[-1]["live_cue_first_output_at"]
    assert "Salesforce integration" not in json.dumps(records)


@pytest.mark.parametrize("failure", ["before", "after", "malformed", "validation"])
def test_failure_and_validation_never_leave_a_ready_partial(cue_api, failure):
    client, *_ = cue_api

    class Broken:
        async def stream(self, system, user):
            if failure == "before":
                raise ProviderUnavailable("UNAVAILABLE", 503)
            if failure == "validation":
                yield json.dumps(
                    {"paragraphs": ["I would clarify the goal.", "Too short."], "evidence_ids": []}
                )
                return
            yield '{"paragraphs":["I would clarify the goal. '
            if failure == "after":
                raise ProviderUnavailable("TRANSPORT_ERROR")
            yield "broken-json"

    client.app.dependency_overrides[get_provider] = lambda: Broken()
    response = client.post(
        "/api/cues/generate",
        json={**payload().model_dump(), "preparation_token": client.preparation_token},
        headers={"Authorization": "Bearer " + "a" * 43, "Accept": "application/x-ndjson"},
    )
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]["type"] == "error" and not any(e["type"] == "ready" for e in events)
    assert not client.app.state.cue_pending
    if failure == "validation":
        assert any(e["type"] == "reset" for e in events)


@pytest.mark.parametrize("partial", [False, True])
def test_shared_deadline_cancels_stream_before_or_after_partial_without_new_retry(partial):
    async def run():
        sent = []
        cancelled = asyncio.Event()

        class Slow:
            async def stream(self, system, user):
                try:
                    if partial:
                        yield '{"paragraphs":["I would clarify the goal. '
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

        async def emit(event):
            sent.append(event)

        with pytest.raises(TimeoutError):
            await asyncio.wait_for(generate_cue(Slow(), payload(), [], emit), 0.02)
        assert cancelled.is_set()
        assert any(e["type"] == "partial" for e in sent) == partial

    asyncio.run(run())


@pytest.mark.parametrize("disconnect", [False, True])
def test_asgi_flushes_partial_before_completion_and_disconnect_cleans_up(cue_api, disconnect):
    client, _, _, _ = cue_api

    async def run():
        release = asyncio.Event()
        first = asyncio.Event()
        closed = asyncio.Event()
        lost = asyncio.Event()

        class Paused:
            async def stream(self, system, user):
                raw = draft().model_dump_json()
                boundary = raw.index(PARAGRAPHS[1])
                try:
                    yield raw[:boundary]
                    await release.wait()
                    yield raw[boundary:]
                finally:
                    closed.set()

        client.app.dependency_overrides[get_provider] = lambda: Paused()
        content = json.dumps(
            {**payload().model_dump(), "preparation_token": client.preparation_token}
        ).encode()
        sent = []
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": content, "more_body": False}
            await lost.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)
            if message["type"] == "http.response.body" and b'"partial"' in message.get("body", b""):
                first.set()

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/cues/generate",
            "raw_path": b"/api/cues/generate",
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"authorization", b"Bearer " + b"a" * 43),
                (b"accept", b"application/x-ndjson"),
                (b"content-type", b"application/json"),
            ],
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 12345),
        }
        task = asyncio.create_task(client.app(scope, receive, send))
        await asyncio.wait_for(first.wait(), 2)
        assert not task.done()
        if disconnect:
            lost.set()
        else:
            release.set()
        await asyncio.wait_for(task, 2)
        assert closed.is_set() and not client.app.state.cue_pending
        output = b"".join(message.get("body", b"") for message in sent)
        assert (b'"ready"' in output) is (not disconnect)

    asyncio.run(run())


def test_streaming_zero_document_preparation_never_uses_account_resume(cue_api):
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.preparations.domain import PreparationView
    from app.preparations.snapshot import freeze

    client, _, repository, user = cue_api
    now = datetime.now(UTC)
    view = PreparationView(
        id=uuid4(),
        purpose="job_interview",
        objective="Fictional interview",
        documents=[],
        created_at=now,
        updated_at=now,
    )
    provider = Provider()
    client.app.dependency_overrides[get_provider] = lambda: provider
    response = client.post(
        "/api/cues/generate",
        json={**payload().model_dump(), "preparation_token": freeze(client.app, user.id, view)},
        headers={"Authorization": "Bearer " + "a" * 43, "Accept": "application/x-ndjson"},
    )
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]["type"] == "ready" and events[-1]["result"]["grounding"] == "general_approach"
    assert repository.owners == [] and provider.calls[0][1]["document_evidence"] == []


def test_stream_boundary_diagnostics_are_ordered_and_content_free(cue_api, settings, caplog):
    from app.cues.stream_timing import PAIRS, STAGES

    client, *_ = cue_api
    settings.gemini_api_key = SecretStr("fake-private-key")
    raw = draft().model_dump_json()

    def handler(request):
        frames = []
        # A metadata event deliberately precedes content: raw != decoded content.
        frames.append(b'data: {"usageMetadata":{}}\n\n')
        for index, piece in enumerate([raw[:30], raw[30:250], raw[250:]]):
            candidate = {"content": {"parts": [{"text": piece}]}}
            if index == 2:
                candidate["finishReason"] = "STOP"
            frames.append(("data: " + json.dumps({"candidates": [candidate]}) + "\n\n").encode())
        return httpx.Response(200, stream=Stream(frames))

    provider = GeminiProvider(settings, httpx.MockTransport(handler))
    client.app.dependency_overrides[get_provider] = lambda: provider
    response = client.post(
        "/api/cues/generate",
        json={**payload().model_dump(), "preparation_token": client.preparation_token},
        headers={"Authorization": "Bearer " + "a" * 43, "Accept": "application/x-ndjson"},
    )
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]["type"] == "ready"
    assert events[-1]["result"]["answer"] == "\n\n".join(PARAGRAPHS)
    records = [
        json.loads(r.message.split("[MeetGuide Timing] ")[1])
        for r in caplog.records
        if "[MeetGuide Timing]" in r.message
    ]
    diagnostics = records[-1]["stream_diagnostics"]
    assert len(diagnostics) == 1
    record = diagnostics[0]
    assert record["generation_attempt"] == 1
    for stage in STAGES:
        assert record[stage + "_at_unix_ms"] > 0
        assert record[stage + "_offset_ms"] >= 0
    for start, end in PAIRS:
        assert record[start + "_to_" + end + "_ms"] >= 0
        assert record[end + "_offset_ms"] >= record[start + "_offset_ms"]
    assert "ndjson_partial_lead_before_generation_completed_ms" in record
    for private in [raw, PARAGRAPHS[0], payload().question, "fake-private-key", "a" * 43]:
        assert private not in json.dumps(records)


def test_stream_diagnostics_keep_first_boundaries_and_attempts_separate():
    from app.cues.stream_timing import mark

    timing = Timing("q-diagnostic", enabled=False)
    token = current.set(timing)
    try:
        timing.values["generation_attempt_count"] = 1
        mark("http_request_started")
        mark("first_displayable_text")
        before = dict(timing.values["stream_diagnostics"][0])
        mark("first_displayable_text")
        assert timing.values["stream_diagnostics"][0] == before
        timing.values["generation_attempt_count"] = 2
        mark("http_request_started")
        # A queued first-attempt partial keeps its original diagnostic identity.
        mark("first_ndjson_partial_yielded", 1)
        records = timing.values["stream_diagnostics"]
        assert len(records) == 2
        assert "first_ndjson_partial_yielded_at_unix_ms" in records[0]
        assert "first_ndjson_partial_yielded_at_unix_ms" not in records[1]
        mark("private-unrecognized-content")
        assert "private-unrecognized-content" not in json.dumps(records)
    finally:
        current.reset(token)
