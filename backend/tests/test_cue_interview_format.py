"""Fictional interview context and fake streams; no real provider traffic."""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from test_cues import PARAGRAPHS, draft, evidence, payload
from test_openai_cues import Stream, delta, frame, frames

from app.cues.domain import Draft
from app.cues.openai import OpenAIProvider
from app.cues.preview import preview
from app.cues.prompt import SYSTEM, user_prompt, validate_draft
from app.cues.provider import ProviderUnavailable
from app.cues.service import generate_cue
from app.preparations.domain import PreparedContext, Selection


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("Real provider traffic forbidden")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)


def concise():
    return Draft(
        paragraphs=[
            "I would clarify the business outcome and constraints before recommending a platform."
        ],
        talking_points=[
            "I would map the interfaces, data ownership and latency requirements.",
            "I would compare integration options against security, cost and support needs.",
            "I would validate the preferred design through a small pilot "
            "with agreed acceptance criteria.",
        ],
    )


def test_adaptive_concise_and_existing_paragraph_answers():
    result = validate_draft(concise(), [])
    assert result.answer.count("• ") == 3
    assert result.grounding == "general_approach"
    assert len(result.answer.split()) < 100
    simple = Draft(
        paragraphs=[
            "I would first confirm the outcome we want, then agree on a practical next step "
            "and a clear way to validate it."
        ]
    )
    assert "•" not in validate_draft(simple, []).answer
    assert "architecture answers" in SYSTEM and "behavioral answers" in SYSTEM
    assert "Simple questions do not need" in SYSTEM
    assert validate_draft(draft(), []).answer == "\n\n".join(PARAGRAPHS)


def test_talking_points_retain_personal_grounding():
    value = concise()
    value.talking_points[0] = "I worked at InventedCorp and delivered 50 projects."
    with pytest.raises(ValueError, match="Personal history without evidence"):
        validate_draft(value, [])
    item = evidence("Developed Salesforce integrations with external APIs.")
    value.talking_points[0] = "I developed Salesforce integrations with external APIs."
    value.evidence_ids = ["E1"]
    assert validate_draft(value, [item]).grounding == "document_supported"


def test_valid_json_with_unfinished_sentence_is_not_ready():
    value = concise()
    value.talking_points[-1] = "I would compare the options with the customer's"
    with pytest.raises(ValueError, match="Incomplete spoken text"):
        validate_draft(value, [])
    shown = preview(value.model_dump_json(), [])
    assert "I would clarify" in shown and "customer's" not in shown
    assert preview("[]", []) == ""


def test_first_partial_precedes_completion_and_points_reconstruct(settings):
    settings.openai_api_key = SecretStr("fake-testing-key")
    done, events = False, []

    class Delayed(Stream):
        async def __aiter__(self):
            nonlocal done
            for chunk in self.chunks:
                yield chunk
            done = True

    def handler(request):
        assert json.loads(request.content)["model"] == settings.openai_live_cue_model
        return httpx.Response(200, stream=Delayed(frames(concise())))

    async def emit(event):
        events.append(event)
        if event["type"] == "partial":
            assert not done

    provider = OpenAIProvider(settings, httpx.MockTransport(handler))
    result = asyncio.run(generate_cue(provider, payload(), [], emit))
    assert any(event["type"] == "partial" for event in events)
    assert result.answer == validate_draft(concise(), []).answer


def test_incomplete_sentence_resets_and_regenerates_only_once():
    value = concise()
    value.talking_points[-1] = "I would compare the options with the customer's"
    calls, events = [], []

    class Fake:
        async def stream(self, system, user):
            calls.append(system)
            yield value.model_dump_json()

    async def emit(event):
        events.append(event)

    with pytest.raises(ProviderUnavailable):
        asyncio.run(generate_cue(Fake(), payload(), [], emit))
    assert len(calls) == 2
    assert len([e for e in events if e["type"] == "reset"]) == 2
    assert not any(e["type"] == "ready" for e in events)


def test_missing_openai_completion_cannot_be_ready(settings):
    settings.openai_api_key = SecretStr("fake-testing-key")
    raw = concise().model_dump_json()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, stream=Stream([frame(delta(raw))]))
    )
    provider = OpenAIProvider(settings, transport)
    with pytest.raises(ProviderUnavailable):
        asyncio.run(generate_cue(provider, payload(), [], lambda event: asyncio.sleep(0)))


def test_frozen_purpose_objective_and_three_selected_excerpts_reach_prompt():
    chosen = [
        evidence(text)
        for text in [
            "Developed Salesforce integrations with external APIs.",
            "The role covers enterprise infrastructure, security and integration proposals.",
            "The company provides technology consulting services.",
        ]
    ]
    for i, item in enumerate(chosen):
        item.id = f"E{i + 1}"
    request = payload(question="How would you modernize an enterprise CRM?")
    request._preparation = PreparedContext(
        preparation_id=uuid4(),
        user_id=uuid4(),
        purpose="job_interview",
        objective="Solutions Architect interview at Fictional Technology Limited",
        documents=[Selection(document_id=item.document_id) for item in chosen],
    )
    data = json.loads(user_prompt(request, chosen))
    assert data["session_preparation"]["purpose"] == "job_interview"
    assert data["session_preparation"]["objective"] == request._preparation.objective
    assert len(data["document_evidence"]) == 3
    assert "Choose technologies from the question" in SYSTEM
    assert "not verified facts" in SYSTEM


def test_legacy_two_paragraph_complete_json_cannot_end_mid_sentence():
    # This previously passed shape, word-count and grounding validation despite
    # being syntactically complete JSON with unfinished spoken content.
    value = Draft(
        paragraphs=[
            PARAGRAPHS[0],
            PARAGRAPHS[1] + " For integration, I'd compare APIs or middleware with the customer's",
        ]
    )
    with pytest.raises(ValueError, match="Incomplete spoken text"):
        validate_draft(value, [])
