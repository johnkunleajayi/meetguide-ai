"""All provider calls are fakes/MockTransport; no real résumé or external API is used."""

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.context.repository import get_context_repository
from app.cues.api import get_provider
from app.cues.domain import CueInput, Draft, Evidence
from app.cues.gemini import GeminiProvider
from app.cues.lifecycle import CueDisconnected, until_disconnect
from app.cues.prompt import HONEST_BRIDGE, SYSTEM, user_prompt, validate_draft
from app.cues.provider import ProviderUnavailable
from app.cues.service import generate_cue, retrieve_evidence
from app.db.auth_repository import get_auth_repository
from app.preparations.domain import PreparationView, PreparedContext, Selection
from app.preparations.snapshot import freeze

PARAGRAPHS = [
    (
        "I would start by clarifying the goal and the systems involved, then trace how "
        "information needs to move between them. I'd check the assumptions with the team "
        "and agree on a small, clear outcome before choosing an approach."
    ),
    (
        "I would break the work into manageable steps, validate each step in a safe environment, "
        "and keep the risks visible throughout. I'd explain the tradeoffs plainly and adjust "
        "the plan based on feedback rather than promise an outcome without enough information."
    ),
]
QUOTE = "Developed Salesforce integrations with external APIs."


def payload(**values):
    return CueInput.model_validate(
        {
            "type": "question",
            "speaker": "them",
            "finalized": True,
            "confidence": 0.94,
            "question": "How did you handle the Salesforce integration?",
            "context": [],
            **values,
        }
    )


def draft(grounded=False):
    return Draft(
        paragraphs=(
            [
                "I developed Salesforce integrations with external APIs. " + PARAGRAPHS[0],
                PARAGRAPHS[1],
            ]
            if grounded
            else PARAGRAPHS.copy()
        ),
        evidence_ids=["E1"] if grounded else [],
    )


def evidence(text=QUOTE):
    return Evidence(id="E1", document_id=uuid4(), chunk_id=uuid4(), text=text)


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.fail = False

    async def generate(self, system, user):
        self.calls.append((system, json.loads(user)))
        if self.fail:
            raise ProviderUnavailable()
        return draft(bool(json.loads(user)["document_evidence"]))


@pytest.fixture
def cue_api(client):
    user = SimpleNamespace(id=uuid4())
    item = evidence()
    provider = FakeProvider()

    class Repository:
        def __init__(self):
            self.owners = []
            self.empty = False

        def scoped_rows(self, owner, documents):
            self.owners.append(owner)
            return (
                []
                if self.empty
                else [
                    (
                        SimpleNamespace(id=item.document_id),
                        SimpleNamespace(id=item.chunk_id, position=0, text=item.text),
                    )
                ]
            )

    repository = Repository()

    class Auth:
        def user_for_session(self, hashed, now):
            return user

    client.app.dependency_overrides[get_auth_repository] = lambda: Auth()
    client.app.dependency_overrides[get_context_repository] = lambda: repository
    client.app.dependency_overrides[get_provider] = lambda: provider
    now = datetime.now(UTC)
    view = PreparationView(
        id=uuid4(),
        purpose="job_interview",
        objective="Fictional interview",
        documents=[Selection(document_id=item.document_id, context_role="resume")],
        created_at=now,
        updated_at=now,
    )
    client.preparation_token = freeze(client.app, user.id, view)
    yield client, provider, repository, user
    client.app.dependency_overrides.clear()


def post(client, body=None, **kwargs):
    return client.post(
        "/api/cues/generate",
        json={**(body or payload().model_dump()), "preparation_token": client.preparation_token},
        headers={"Authorization": "Bearer " + "a" * 43},
        **kwargs,
    )


def test_question_generates_bounded_grounded_ready_to_speak_answer(cue_api):
    client, provider, repository, user = cue_api
    response = post(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer"].startswith("I developed Salesforce")
    assert len(body["answer"].split("\n\n")) == 2
    assert body["grounding"] == "document_supported" and len(body["sources"]) == 1
    assert repository.owners == [user.id] and len(provider.calls) == 1
    assert response.headers["cache-control"] == "no-store"
    assert not client.app.state.cue_pending


@pytest.mark.parametrize(
    "change",
    [
        {"type": "important_point"},
        {"speaker": "you"},
        {"finalized": False},
        {"confidence": 0.7},
        {"question": "x"},
        {"question": "x" * 1601},
        {"context": [{"speaker": "them", "text": "x" * 1000}] * 5},
    ],
)
def test_nonquestions_interims_and_unbounded_input_never_call_provider(cue_api, change):
    client, provider, *_ = cue_api
    response = post(client, {**payload().model_dump(), **change})
    assert response.status_code == 422 and not provider.calls


def test_no_context_and_provider_failure_are_safe_and_retryable(cue_api):
    client, provider, repository, _ = cue_api
    repository.empty = True
    response = post(client)
    assert response.status_code == 200 and response.json()["grounding"] == "general_approach"
    assert response.json()["sources"] == []
    provider.fail = True
    assert post(client).status_code == 503
    assert not client.app.state.cue_pending
    provider.fail = False
    assert post(client).status_code == 200


def test_cookie_only_missing_and_untrusted_origin_rejected(cue_api):
    client, provider, *_ = cue_api
    assert client.post("/api/cues/generate", json=payload().model_dump()).status_code == 401
    assert (
        client.post(
            "/api/cues/generate",
            json={**payload().model_dump(), "preparation_token": client.preparation_token},
            headers={"Authorization": "Bearer " + "a" * 43, "Origin": "https://untrusted.example"},
        ).status_code
        == 403
    )
    assert not provider.calls


def test_disabled_by_default_and_api_key_never_in_repr(cue_api, settings):
    client, *_ = cue_api
    client.app.dependency_overrides.pop(get_provider)
    assert not settings.live_cue_enabled and settings.gemini_api_key is None
    assert post(client).status_code == 503
    settings.gemini_api_key = SecretStr("fake-test-key")
    assert "fake-test-key" not in repr(settings)


def test_busy_and_oversized_request_do_not_call_provider(cue_api):
    client, provider, _, user = cue_api
    client.app.state.cue_pending[user.id] = 2
    assert post(client).status_code == 429
    client.app.state.cue_pending.clear()
    assert (
        client.post(
            "/api/cues/generate",
            content=b"x" * 32769,
            headers={"Authorization": "Bearer " + "a" * 43},
        ).status_code
        == 413
    )
    assert not provider.calls


def test_retrieval_uses_recent_you_topic_for_followup_and_only_owned_rows():
    owner = uuid4()
    calls = []
    document_id = uuid4()

    class Repository:
        def scoped_rows(self, user, documents):
            calls.append(user)
            return [
                (
                    SimpleNamespace(id=document_id),
                    SimpleNamespace(id=uuid4(), position=0, text=QUOTE),
                )
            ]

    request = payload(
        question="What was the biggest challenge?",
        context=[{"speaker": "you", "text": "I worked on Salesforce integration."}],
    )
    request._preparation = PreparedContext(
        preparation_id=uuid4(),
        user_id=owner,
        purpose="job_interview",
        objective="Fictional interview",
        documents=[Selection(document_id=document_id, context_role="resume")],
    )
    result = retrieve_evidence(Repository(), owner, request)
    assert calls == [owner] and result and QUOTE in result[0].text
    prompt = json.loads(user_prompt(request, result))
    assert prompt["recent_conversation"][0]["speaker"] == "you"
    assert "UNTRUSTED DATA" in SYSTEM and "not verified evidence" in SYSTEM


def test_evidence_is_at_most_three_excerpts_and_3600_characters():
    document_id, owner = uuid4(), uuid4()

    class Repository:
        def scoped_rows(self, user, documents):
            return [
                (
                    SimpleNamespace(id=document_id),
                    SimpleNamespace(id=uuid4(), position=i, text="Salesforce " * 500),
                )
                for i in range(10)
            ]

    request = payload()
    request._preparation = PreparedContext(
        preparation_id=uuid4(),
        user_id=owner,
        purpose="job_interview",
        objective="Fictional interview",
        documents=[Selection(document_id=document_id, context_role="resume")],
    )
    result = retrieve_evidence(Repository(), owner, request)
    assert len(result) == 3 and sum(len(item.text) for item in result) <= 3600


def test_honest_bridge_and_hypothetical_requested_technology_are_allowed():
    answer = draft()
    answer.paragraphs[0] = (
        HONEST_BRIDGE + " " + answer.paragraphs[0].replace("the systems involved", "SAP S/4HANA")
    )
    assert validate_draft(answer, []).grounding == "general_approach"


def test_invalid_draft_is_sanitized_as_provider_failure():
    class InvalidProvider:
        async def generate(self, system, user):
            return Draft(paragraphs=["You should mention your experience.", "Explain the result."])

    with pytest.raises(ProviderUnavailable):
        asyncio.run(generate_cue(InvalidProvider(), payload(), []))


def test_gemini_contract_uses_mocked_http_and_no_key_in_url(settings):
    settings.gemini_api_key = SecretStr("fake-test-key")

    def handler(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        assert not request.url.query and request.headers["x-goog-api-key"] == "fake-test-key"
        body = json.loads(request.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert "tools" not in body
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": draft().model_dump_json()}]},
                    }
                ]
            },
        )

    output = asyncio.run(
        GeminiProvider(settings, httpx.MockTransport(handler)).generate(SYSTEM, "fictional test")
    )
    assert output.paragraphs == PARAGRAPHS


@pytest.mark.parametrize(
    "body,status",
    [
        ({}, 200),
        ({"candidates": []}, 200),
        ({"candidates": ["invalid candidate"]}, 200),
        ({"candidates": [{"finishReason": "STOP", "content": {"parts": [None]}}]}, 200),
        ({"candidates": [{"finishReason": "MAX_TOKENS"}]}, 200),
        ({"error": "fake private detail"}, 429),
        ({}, 503),
    ],
)
def test_gemini_failures_are_sanitized(settings, body, status):
    settings.gemini_api_key = SecretStr("fake-test-key")
    with pytest.raises(ProviderUnavailable) as error:
        asyncio.run(
            GeminiProvider(
                settings, httpx.MockTransport(lambda _: httpx.Response(status, json=body))
            ).generate(SYSTEM, "fictional test")
        )
    assert not str(error.value)


def test_disconnect_cancels_generation():
    async def scenario():
        finished = asyncio.Event()

        class Disconnected:
            async def is_disconnected(self):
                return True

        async def work():
            try:
                await asyncio.sleep(60)
            finally:
                finished.set()

        with pytest.raises(CueDisconnected):
            await until_disconnect(Disconnected(), work())
        assert finished.is_set()

    asyncio.run(scenario())


def test_hypothetical_supporting_sentence_does_not_require_repeated_first_person():
    answer = draft()
    answer.paragraphs[0] += " This would keep the scope clear and reduce unnecessary risk."
    assert validate_draft(answer, []).grounding == "general_approach"
    answer.paragraphs[0] += " I managed Salesforce projects, so this would be familiar."
    with pytest.raises(ValueError):
        validate_draft(answer, [])


def test_safe_gemini_http_diagnostics_never_echo_error_body_or_key(settings, caplog):
    settings.gemini_api_key = SecretStr("fake-private-key")
    response = {
        "error": {
            "status": "RESOURCE_EXHAUSTED",
            "message": "fake-private-key private-resume private-transcript private-answer",
        }
    }
    with pytest.raises(ProviderUnavailable):
        asyncio.run(
            GeminiProvider(
                settings, httpx.MockTransport(lambda _: httpx.Response(429, json=response))
            ).generate("private-system", "private-user")
        )
    assert "http_status=429 reason=RESOURCE_EXHAUSTED" in caplog.text
    for secret in [
        "fake-private-key",
        "private-resume",
        "private-transcript",
        "private-answer",
        "private-user",
        "private-system",
    ]:
        assert secret not in caplog.text


def test_safe_grounding_diagnostic_distinguishes_local_rejection(caplog):
    class InvalidProvider:
        async def generate(self, system, user):
            output = draft()
            output.paragraphs[0] += " I worked at FictionalCorp on a private-example project."
            return output

    with pytest.raises(ProviderUnavailable):
        asyncio.run(generate_cue(InvalidProvider(), payload(), []))
    assert "Live Cue validation: attempt=2 reason=Personal history without evidence" in caplog.text
    assert "private-example" not in caplog.text


def test_short_finalized_followup_uses_context_and_preserves_input_guards(cue_api):
    client, provider, *_ = cue_api
    body = payload().model_dump()
    body["question"] = "Why?"
    assert post(client, body).status_code == 422
    assert not provider.calls
    body["context"] = [{"speaker": "you", "text": "I developed Salesforce integrations."}]
    for invalid in [
        {"finalized": False},
        {"confidence": 0.5},
        {"speaker": "you"},
        {"question": "Wh"},
    ]:
        assert post(client, {**body, **invalid}).status_code == 422
    assert not provider.calls
    response = post(client, body)
    assert response.status_code == 200
    assert len(provider.calls) == 1
    assert provider.calls[0][1]["question"] == "Why?"


@pytest.mark.parametrize("failed", [False, True])
def test_content_free_stage_timings_and_retry(cue_api, caplog, failed):
    client, provider, repository, _ = cue_api
    provider.fail = failed
    response = client.post(
        "/api/cues/generate",
        json={**payload().model_dump(), "preparation_token": client.preparation_token},
        headers={"Authorization": "Bearer " + "a" * 43, "X-MeetGuide-Question-Id": "q-timing-test"},
    )
    assert response.status_code == (503 if failed else 200)
    assert response.headers["x-meetguide-question-id"] == "q-timing-test"
    assert float(response.headers["x-meetguide-backend-ms"]) >= 0
    records = [
        json.loads(record.message.split("[MeetGuide Timing] ", 1)[1])
        for record in caplog.records
        if "[MeetGuide Timing]" in record.message
    ]
    timing = records[-1]
    assert timing["question_id"] == "q-timing-test"
    assert timing["retrieval_ms"] >= 0 and timing["live_cue_generation_ms"] >= 0
    assert timing["backend_total_ms"] >= timing["retrieval_ms"]
    assert timing["conversation_turn_count"] == timing["conversation_context_char_count"] == 0
    assert timing["question_char_count"] == len(payload().question)
    assert timing["retrieved_excerpt_count"] == 1 and timing["retrieved_context_char_count"] == len(
        QUOTE
    )
    assert (
        timing["live_cue_streaming"] is False and timing["live_cue_time_to_first_output_ms"] is None
    )
    if failed:
        assert timing["provider_error_type"] == "PROVIDER_UNAVAILABLE"
        provider.fail = False
        assert post(client).status_code == 200
    else:
        assert timing["validation_ms"] >= 0
        assert response.json()["answer"].startswith("I developed Salesforce")
    logged = json.dumps(records)
    for secret in [QUOTE, payload().question, "a" * 43, PARAGRAPHS[0]]:
        assert secret not in logged


def test_unsafe_correlation_and_error_details_are_not_logged(caplog):
    from app.core.timing import Timing

    timing = Timing("private-resume-text")
    timing.finish()
    assert timing.values["question_id"].startswith("q-")
    assert "private-resume-text" not in caplog.text
    error = ProviderUnavailable("private-provider-content", "secret-status")
    assert error.reason == "PROVIDER_UNAVAILABLE" and error.status is None


def test_timing_counts_actual_bounded_context_without_logging_it(cue_api, caplog):
    client, _, _, _ = cue_api
    private = "FICTIONAL_PRIVATE_CONTEXT_SENTINEL"
    response = post(client, payload(context=[{"speaker": "them", "text": private}]).model_dump())
    assert response.status_code == 200
    record = next(
        json.loads(item.message.split("[MeetGuide Timing] ", 1)[1])
        for item in caplog.records
        if "[MeetGuide Timing]" in item.message
    )
    assert record["conversation_turn_count"] == 1
    assert record["conversation_context_char_count"] == len(private)
    assert private not in caplog.text
