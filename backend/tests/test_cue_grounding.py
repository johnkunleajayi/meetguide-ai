"""Fictional evidence and fake providers only. No live API or personal documents."""

import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.cues.domain import Draft
from app.cues.gemini import GeminiProvider
from app.cues.prompt import SYSTEM, validate_draft
from app.cues.provider import ProviderUnavailable
from app.cues.service import generate_cue
from tests.test_cues import PARAGRAPHS, draft, evidence, payload

SOURCE = (
    "Developed Salesforce integrations with external APIs. Collaborated with colleagues "
    "to map fields and test data exchanges. Investigated inconsistent data formats. "
    "Worked at ExampleWorks. Reduced manual processing by 20%."
)
SPOKEN = [
    "I worked on connecting Salesforce with external systems through APIs. My work included "
    "mapping fields and checking that data moved correctly between the systems. One challenge "
    "was dealing with inconsistent data formats, which meant looking carefully at how values "
    "were represented on each side.",
    "I collaborated with colleagues on the mapping and testing. That gave me a practical "
    "way to investigate the mismatches rather than assume that every field meant the same "
    "thing in both systems. For a similar integration, I would keep those checks visible "
    "and validate the exchanges before extending the scope.",
]


class FakeProvider:
    def __init__(self, *outputs):
        self.outputs = outputs
        self.calls = []

    async def generate(self, system, user):
        self.calls.append((system, json.loads(user)))
        return self.outputs[min(len(self.calls) - 1, len(self.outputs) - 1)]


def spoken(prefix=""):
    return Draft(paragraphs=[prefix + SPOKEN[0], SPOKEN[1]], evidence_ids=["E1"])


def test_realistic_spoken_paraphrase_succeeds_with_one_call_and_no_quotes():
    provider = FakeProvider(spoken())
    result = asyncio.run(generate_cue(provider, payload(), [evidence(SOURCE)]))
    assert result.answer == "\n\n".join(SPOKEN)
    assert result.grounding == "document_supported"
    assert len(provider.calls) == 1
    assert "claims" not in Draft.model_json_schema()["properties"]
    assert not hasattr(GeminiProvider, "verify")


@pytest.mark.parametrize("source", [SOURCE, SOURCE.replace(" ", "\n"), SOURCE.upper()])
def test_rewording_capitals_and_pdf_line_breaks_do_not_require_lexical_equivalence(source):
    assert validate_draft(spoken(), [evidence(source)]).answer.startswith("I worked on connecting")


def test_natural_transitions_and_responsibility_paraphrases_are_not_verb_matched():
    output = spoken("I was responsible for field mapping and integration testing. ")
    assert validate_draft(output, [evidence(SOURCE)]).answer.startswith("I was responsible")


@pytest.mark.parametrize(
    "fabrication, reason",
    [
        ("I implemented SAP integrations. ", "Unsupported technology"),
        ("I worked at InventedCorp. ", "Unsupported named fact"),
        ("I built a project named InventedApollo. ", "Unsupported named fact"),
        ("I reduced manual processing by 40%. ", "Unsupported numeric fact"),
        ("I managed 50 engineers. ", "Unsupported numeric fact"),
        ("I single-handedly built the integration. ", "Unsupported sole credit"),
    ],
)
def test_concrete_fabrications_regenerate_once_then_remain_blocked(fabrication, reason, caplog):
    provider = FakeProvider(spoken(fabrication))
    with pytest.raises(ProviderUnavailable):
        asyncio.run(generate_cue(provider, payload(), [evidence(SOURCE)]))
    assert len(provider.calls) == 2
    assert reason in provider.calls[1][0]
    assert "REGENERATE CONSERVATIVELY" in provider.calls[1][0]
    assert fabrication not in caplog.text and SOURCE not in caplog.text
    assert provider.calls[0][1] == provider.calls[1][1]


def test_regeneration_can_recover_without_resending_rejected_answer():
    bad = spoken("I worked at InventedCorp. ")
    provider = FakeProvider(bad, spoken())
    result = asyncio.run(generate_cue(provider, payload(), [evidence(SOURCE)]))
    assert "InventedCorp" not in result.answer
    assert "InventedCorp" not in json.dumps(provider.calls[1])
    assert len(provider.calls) == 2


def test_documented_employer_and_metric_are_allowed():
    output = spoken("I worked at ExampleWorks. I reduced manual processing by 20%. ")
    assert validate_draft(output, [evidence(SOURCE)]).grounding == "document_supported"


def test_unsupported_system_can_be_discussed_as_an_honest_hypothetical_bridge():
    output = spoken()
    output.paragraphs[0] = (
        "I can't point to a confirmed example with SAP. "
        "I would use my integration approach to understand the interfaces first. " + SPOKEN[0]
    )
    assert validate_draft(output, [evidence(SOURCE)]).answer.startswith("I can't point")


def test_no_context_rejects_personal_history_but_allows_natural_general_approach():
    assert validate_draft(draft(), []).grounding == "general_approach"
    provider = FakeProvider(Draft(paragraphs=SPOKEN), draft())
    assert asyncio.run(generate_cue(provider, payload(), [])).grounding == "general_approach"
    assert len(provider.calls) == 2


def test_unknown_source_id_cannot_create_a_grounding_indicator():
    output = spoken()
    output.evidence_ids = ["another-users-chunk"]
    with pytest.raises(ValueError, match="Unsupported evidence"):
        validate_draft(output, [evidence(SOURCE)])


def test_provider_failure_is_not_automatically_retried():
    class FailedProvider:
        calls = 0

        async def generate(self, system, user):
            self.calls += 1
            raise ProviderUnavailable()

    provider = FailedProvider()
    with pytest.raises(ProviderUnavailable):
        asyncio.run(generate_cue(provider, payload(), []))
    assert provider.calls == 1


def test_gemini_normal_path_is_one_http_request_without_claim_or_verdict_schema(settings):
    settings.gemini_api_key = SecretStr("fake-only")
    requests = []

    def handle(request):
        requests.append(request)
        schema = json.loads(request.content)["generationConfig"]["responseJsonSchema"]
        assert set(schema["properties"]) == {"paragraphs", "evidence_ids"}
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": spoken().model_dump_json()}]},
                    }
                ]
            },
        )

    provider = GeminiProvider(settings, httpx.MockTransport(handle))
    assert asyncio.run(generate_cue(provider, payload(), [evidence(SOURCE)])).answer
    assert len(requests) == 1


def test_prompt_is_grounded_without_forcing_sentence_templates():
    for instruction in [
        "ONLY evidence",
        "Never invent",
        "responsibilities",
        "challenges",
        "negation",
    ]:
        assert instruction in SYSTEM
    assert "No verbatim quotes" in SYSTEM
    assert "not verified evidence" in SYSTEM
    assert PARAGRAPHS


def test_metric_substrings_are_not_evidence_and_negation_does_not_bypass_other_facts():
    output = spoken("I reduced processing by 40%. ")
    with pytest.raises(ValueError, match="Unsupported numeric fact"):
        validate_draft(output, [evidence(SOURCE.replace("20%", "140%"))])
    output = spoken("I worked at InventedCorp, but not on that project. ")
    with pytest.raises(ValueError, match="Unsupported named fact"):
        validate_draft(output, [evidence(SOURCE)])


def test_question_and_conversation_are_not_used_to_justify_fabricated_technology():
    provider = FakeProvider(spoken("I implemented SAP integrations. "), spoken())
    request = payload(
        question="Tell me about SAP integration.",
        context=[{"speaker": "them", "text": "We need SAP expertise."}],
    )
    result = asyncio.run(generate_cue(provider, request, [evidence(SOURCE)]))
    assert "SAP" not in result.answer and len(provider.calls) == 2


def test_normal_words_and_transferable_hypothetical_are_not_new_technology_claims():
    output = spoken("My experience would transfer to SAP integration planning. ")
    output.paragraphs[1] = "I worked with colleagues to react quickly to data issues. " + SPOKEN[1]
    assert validate_draft(output, [evidence(SOURCE)]).answer
