"""Synthetic transcript fixtures and mocked Gemini only; no real provider calls."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.cues.provider import ProviderUnavailable
from app.db.auth_repository import get_auth_repository
from app.intent.api import get_intent_provider
from app.intent.domain import IntentInput, IntentResult
from app.intent.gemini import GeminiIntentProvider


def payload(**changes):
    return {
        "text": "I'd like to hear more about that migration.",
        "context": [{"speaker": "you", "text": "I tested the Salesforce integration."}],
        "can_continue": False,
        **changes,
    }


class FakeIntent:
    def __init__(self):
        self.calls = []
        self.failure = None
        self.kind = "ACTIONABLE_REQUEST"

    async def classify(self, value):
        self.calls.append(value)
        if self.failure:
            raise self.failure
        return IntentResult(
            kind=self.kind,
            normalized_request="How did you test the migration?"
            if self.kind != "NOT_ACTIONABLE"
            else "",
            confidence=0.94,
        )


@pytest.fixture
def intent_api(client):
    user = SimpleNamespace(id=uuid4())

    class Auth:
        def user_for_session(self, hashed, now):
            return user

    fake = FakeIntent()
    fake.user_id = user.id
    client.app.dependency_overrides[get_auth_repository] = lambda: Auth()
    client.app.dependency_overrides[get_intent_provider] = lambda: fake
    yield client, fake
    client.app.dependency_overrides.clear()


def post(client, body=None, headers=None):
    return client.post(
        "/api/intent/classify",
        json=body or payload(),
        headers=headers or {"Authorization": "Bearer " + "a" * 43},
    )


@pytest.mark.parametrize(
    "kind", ["ACTIONABLE_REQUEST", "FOLLOW_UP", "CONTINUATION", "NOT_ACTIONABLE"]
)
def test_structured_classification_and_no_store(intent_api, kind):
    client, provider = intent_api
    provider.kind = kind
    response = post(
        client,
        payload(
            previous_request="Tell me about the migration.", can_continue=kind == "CONTINUATION"
        ),
    )
    assert response.status_code == 200
    assert response.json()["kind"] == kind
    assert response.headers["cache-control"] == "no-store"
    assert not client.app.state.intent_pending


@pytest.mark.parametrize(
    "text",
    [
        "Tell me about your experience.",
        "And challenges you faced.",
        "Why?",
        "How did you undo the Salesforce migration?",
        "We completed the project.",
    ],
)
def test_bounded_transcript_inputs_reach_replaceable_provider(intent_api, text):
    client, provider = intent_api
    response = post(client, payload(text=text))
    assert response.status_code == 200
    assert provider.calls[0].text == text
    assert not hasattr(provider.calls[0], "document_evidence")


@pytest.mark.parametrize(
    "change",
    [
        {"text": "x" * 1601},
        {"context": [{"speaker": "you", "text": "x" * 1000}] * 5},
        {"documents": ["not allowed"]},
        {"can_continue": True, "previous_request": None},
    ],
)
def test_invalid_or_unbounded_input_never_reaches_gemini(intent_api, change):
    client, provider = intent_api
    assert post(client, payload(**change)).status_code == 422
    assert not provider.calls


def test_native_authentication_and_origin_are_required(intent_api):
    client, provider = intent_api
    assert client.post("/api/intent/classify", json=payload()).status_code == 401
    assert (
        post(
            client,
            headers={"Authorization": "Bearer " + "a" * 43, "Origin": "http://127.0.0.1:5173"},
        ).status_code
        == 403
    )
    assert not provider.calls


@pytest.mark.parametrize("error", [TimeoutError(), ProviderUnavailable()])
def test_timeout_or_unavailable_returns_sanitized_fallback_response(intent_api, error):
    client, provider = intent_api
    provider.failure = error
    response = post(client)
    assert response.status_code == 503
    assert "local detection" in response.json()["detail"]
    assert not client.app.state.intent_pending


def test_continuation_cannot_cross_an_ineligible_boundary(intent_api):
    client, provider = intent_api
    provider.kind = "CONTINUATION"
    assert post(client).status_code == 503


def test_disabled_intent_never_uses_provider(client):
    client.app.state.settings.gemini_intent_enabled = False
    client.app.dependency_overrides[get_auth_repository] = lambda: SimpleNamespace(
        user_for_session=lambda *args: SimpleNamespace(id=uuid4())
    )
    assert post(client).status_code == 503
    client.app.dependency_overrides.clear()


def test_gemini_adapter_is_small_structured_and_contains_transcript_only(settings):
    configured = settings.model_copy(update={"gemini_api_key": SecretStr("synthetic-test-key")})

    def handle(request):
        assert "synthetic-test-key" not in str(request.url)
        data = json.loads(request.content)
        assert data["generationConfig"]["maxOutputTokens"] == 384
        assert "kind" in data["generationConfig"]["responseJsonSchema"]["properties"]
        sent = json.loads(data["contents"][0]["parts"][0]["text"])
        assert set(sent) == {"text", "context", "previous_request", "can_continue"}
        result = {
            "kind": "FOLLOW_UP",
            "normalized_request": "Why did you test the migration that way?",
            "confidence": 0.94,
        }
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(result)}]}}
                ]
            },
        )

    provider = GeminiIntentProvider(configured, httpx.MockTransport(handle))
    result = asyncio.run(provider.classify(IntentInput.model_validate(payload(text="Why?"))))
    assert result.kind == "FOLLOW_UP"


@pytest.mark.parametrize("mode", ["timeout", "quota", "malformed", "invalid_schema"])
def test_real_adapter_failure_modes_are_sanitized(settings, mode):
    configured = settings.model_copy(update={"gemini_api_key": SecretStr("synthetic-test-key")})

    def handle(request):
        if mode == "timeout":
            raise httpx.ReadTimeout("private request body must not leak")
        if mode == "quota":
            return httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}})
        text = (
            "not json"
            if mode == "malformed"
            else json.dumps({"kind": "UNSUPPORTED", "normalized_request": "Why?", "confidence": 1})
        )
        return httpx.Response(
            200,
            json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]},
        )

    provider = GeminiIntentProvider(configured, httpx.MockTransport(handle))
    with pytest.raises(ProviderUnavailable):
        asyncio.run(provider.classify(IntentInput.model_validate(payload())))


def test_intent_concurrency_and_body_size_limits(intent_api):
    client, provider = intent_api
    client.app.state.intent_pending[provider.user_id] = 1
    assert post(client).status_code == 429
    assert not provider.calls
    client.app.state.intent_pending.clear()
    response = client.post(
        "/api/intent/classify",
        content=b"x" * 32769,
        headers={"Authorization": "Bearer " + "a" * 43},
    )
    assert response.status_code == 413
    assert not provider.calls


@pytest.mark.parametrize(
    "failure", [None, TimeoutError(), ProviderUnavailable("RESOURCE_EXHAUSTED", 429)]
)
def test_intent_timing_is_correlated_and_content_free(intent_api, caplog, failure):
    client, provider = intent_api
    provider.failure = failure
    response = post(
        client,
        headers={
            "Authorization": "Bearer " + "a" * 43,
            "X-MeetGuide-Question-Id": "q-intent-timing",
        },
    )
    assert response.status_code == (200 if failure is None else 503)
    record = next(
        json.loads(item.message.split("[MeetGuide Timing] ", 1)[1])
        for item in caplog.records
        if "[MeetGuide Timing]" in item.message
    )
    assert record["question_id"] == "q-intent-timing"
    assert record["intent_route"] == "gemini" and record["intent_request_ms"] >= 0
    assert record["conversation_turn_count"] == 1
    if failure is not None:
        assert record["provider_error_type"] in {"TIMEOUT", "RESOURCE_EXHAUSTED"}
    assert payload()["text"] not in caplog.text
    assert payload()["context"][0]["text"] not in caplog.text
    assert "a" * 43 not in caplog.text
