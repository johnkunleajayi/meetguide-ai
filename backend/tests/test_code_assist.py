"""Mocked Code Assist; synthetic problem/context only. No code execution or provider traffic."""

import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from test_cues import cue_api as cue_api
from test_cues import evidence, payload
from test_openai_cues import Stream, complete, delta, frame, frames, install, timing_records

from app.cues import code_assist
from app.cues.domain import CodeDraft, CodingContext
from app.cues.openai import OpenAIProvider
from app.cues.service import generate_cue
from app.preparations.domain import PreparationInput, PreparedContext
from app.preparations.snapshot import freeze, resolve

CODE = """def duplicates(values):
    seen = set()
    result = set()
    for value in values:
        if value in seen:
            result.add(value)
        seen.add(value)
    return list(result)
"""


def answer(**kw):
    return CodeDraft(
        **{
            "language": "Python",
            "approach": "Use sets to track seen values and distinct duplicates.",
            "code": CODE,
            "complexity": "Expected O(n) time and O(n) auxiliary space for hashable values.",
            "what_to_say": (
                "I use one set for values I have seen and another for duplicates, "
                "so each value is examined once."
            ),
            "evidence_ids": [],
            **kw,
        }
    )


def code_input(**kw):
    return payload(
        **{
            "cue_kind": "code",
            "question": "Write a function that finds duplicates in an array.",
            **kw,
        }
    )


def post_code(client, **kw):
    return client.post(
        "/api/cues/generate",
        json={**code_input(**kw).model_dump(), "preparation_token": client.preparation_token},
        headers={
            "Authorization": "Bearer " + "a" * 43,
            "Accept": "application/x-ndjson",
            "X-MeetGuide-Question-Id": "q-code",
        },
    )


@pytest.mark.parametrize(
    "query,expected",
    [
        ("Implement this in Python.", "python"),
        ("Write an Apex trigger to prevent duplicate Contacts.", "apex"),
        ("Create a SQL query for second highest salary.", "sql"),
        ("How would you go about reversing a list?", "auto"),
    ],
)
def test_explicit_and_auto_language(query, expected):
    assert code_assist.language(payload(cue_kind="code", question=query)) == expected


def test_language_precedence_and_resume_language_is_not_a_preference():
    request = code_input()
    request._preparation = PreparedContext(
        preparation_id=uuid4(),
        user_id=uuid4(),
        purpose="job_interview",
        objective="Fictional coding interview",
        technical_interview=True,
        coding_language="apex",
    )
    assert code_assist.language(request) == "apex"
    request.coding_context = CodingContext(
        problem="Reverse a linked list", language="Java", code="previous code"
    )
    assert code_assist.language(request) == "Java"
    request.question = "Implement this in Python."
    assert code_assist.language(request) == "python"
    generic = payload(
        cue_kind="code",
        question="Reverse a linked list please.",
        context=[{"speaker": "you", "text": "My background includes Python and Salesforce."}],
    )
    assert code_assist.language(generic) == "auto"


def test_code_contract_format_complexity_and_grounding():
    result = code_assist.validate(answer(), [])
    assert result.code_assist.code == CODE
    assert result.answer == answer().what_to_say
    assert result.sources == [] and result.grounding == "general_approach"
    assert code_assist.validate(answer(complexity=None), []).code_assist.complexity is None
    with pytest.raises(ValueError):
        code_assist.validate(
            answer(what_to_say="I worked at InventedCorp on SAP projects."), [evidence()]
        )
    with pytest.raises(ValueError):
        code_assist.validate(answer(evidence_ids=["unselected"]), [])
    with pytest.raises(ValidationError):
        answer(code="")


def test_code_partial_before_final_uses_same_openai_transport(settings):
    async def run():
        settings.openai_api_key = SecretStr("fictional-openai-key")
        raw = answer().model_dump_json()
        boundary = raw.index('"complexity"')
        seen, finish = asyncio.Event(), asyncio.Event()
        emitted = []

        class Paused(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield frame(delta(raw[:boundary]))
                await finish.wait()
                yield frame(delta(raw[boundary:]))
                yield frame(complete(raw))

        def handler(request):
            body = json.loads(request.content)
            assert body["model"] == "gpt-6-luna" and body["stream"] is True
            assert body["text"]["format"]["schema"]["properties"]["code"]["type"] == "string"
            assert body["store"] is False and body["reasoning"] == {"effort": "none"}
            return httpx.Response(200, stream=Paused())

        async def emit(event):
            emitted.append(event)
            if event["type"] == "partial":
                seen.set()

        task = asyncio.create_task(
            generate_cue(
                OpenAIProvider(settings, httpx.MockTransport(handler)), code_input(), [], emit
            )
        )
        await asyncio.wait_for(seen.wait(), 1)
        assert not task.done() and emitted[-1]["code_assist"]["code"].startswith("def duplicates")
        finish.set()
        result = await task
        assert result.code_assist.code == CODE

    asyncio.run(run())


def test_frozen_preference_no_documents_and_session_coding_context(cue_api, monkeypatch, caplog):
    client, _, _, user = cue_api
    view = SimpleNamespace(
        id=uuid4(),
        purpose="job_interview",
        objective="Synthetic technical interview",
        documents=[],
        technical_interview=True,
        coding_language="python",
    )
    client.preparation_token = freeze(client.app, user.id, view)
    view.coding_language = "java"
    assert resolve(client.app, user.id, client.preparation_token).coding_language == "python"
    calls = []

    def handler(request):
        body = json.loads(request.content)
        data = json.loads(body["input"][0]["content"])
        calls.append(data)
        assert data["document_evidence"] == []
        assert data["session_preparation"]["objective"] == "Synthetic technical interview"
        assert data["coding_language"] == "python"
        return httpx.Response(200, stream=Stream(frames(answer())))

    install(client, monkeypatch, handler)
    response = post_code(client)
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]["type"] == "ready"
    assert events[-1]["result"]["code_assist"]["code"] == CODE
    assert all(e["question_id"] == "q-code" for e in events)
    response = post_code(
        client,
        question="Can you optimize that solution?",
        coding_context=CodingContext(problem="Find duplicates", code=CODE, language="python"),
    )
    assert calls[-1]["coding_context"]["code"] == CODE
    logged = json.dumps(timing_records(caplog))
    assert CODE not in logged and "Synthetic technical interview" not in logged


def test_code_validation_failure_resets_and_retains_retry_contract(cue_api, monkeypatch):
    client, *_ = cue_api
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            stream=Stream(frames(answer(what_to_say="I worked at InventedCorp on SAP projects."))),
        )

    install(client, monkeypatch, handler)
    events = [json.loads(line) for line in post_code(client).text.splitlines()]
    assert events[-1]["type"] == "error" and any(e["type"] == "reset" for e in events)
    assert len(calls) == 2 and "structured Code Assist" in calls[1]["instructions"]


def test_legacy_preparations_and_migration_defaults(monkeypatch):
    old = PreparationInput(purpose="job_interview", objective="Interview")
    assert old.technical_interview is False and old.coding_language == "auto"
    path = Path(__file__).parents[1] / "alembic/versions/0005_code_assist_preference.py"
    spec = importlib.util.spec_from_file_location("code_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    columns = []
    monkeypatch.setattr(
        migration.op, "add_column", lambda table, column: columns.append((table, column))
    )
    migration.upgrade()
    assert migration.down_revision == "0004_session_preparations"
    assert [c.name for _, c in columns] == ["technical_interview", "coding_language"]
    assert all(not c.nullable and c.server_default is not None for _, c in columns)


@pytest.mark.parametrize("scope_kind", ["selected", "empty", "different", "other_user"])
def test_code_request_document_scope_is_never_account_wide(cue_api, monkeypatch, scope_kind):
    from app.preparations.domain import Selection

    client, _, _, user = cue_api
    original = resolve(client.app, user.id, client.preparation_token)
    documents = original.documents if scope_kind == "selected" else []
    if scope_kind == "different":
        documents = [Selection(document_id=uuid4())]
    view = SimpleNamespace(
        id=uuid4(), purpose="job_interview", objective="Synthetic technical", documents=documents
    )
    client.preparation_token = freeze(
        client.app, uuid4() if scope_kind == "other_user" else user.id, view
    )
    calls = []

    def handler(request):
        data = json.loads(json.loads(request.content)["input"][0]["content"])
        calls.append(data)
        assert len(data["document_evidence"]) == (1 if scope_kind == "selected" else 0)
        return httpx.Response(200, stream=Stream(frames(answer())))

    install(client, monkeypatch, handler)
    response = post_code(client, question="Write a function that calls external APIs.")
    if scope_kind == "other_user":
        assert response.status_code == 409 and not calls
    else:
        events = [json.loads(line) for line in response.text.splitlines()]
        assert events[-1]["type"] == "ready"
        assert len(calls) == 1


@pytest.mark.parametrize(
    "text",
    [
        "I scan the array once.",
        "I use a set to track values.",
        "I would use a set.",
        "I would solve this with two pointers.",
        "I'm using one SOQL query to keep this bulk-safe.",
        "I've used a set to track values in this solution.",
        "I built a function to scan the array once.",
    ],
)
def test_code_procedural_first_person_without_documents(text):
    assert code_assist.validate(answer(what_to_say=text), []).answer == text
    assert code_assist.preview(answer(what_to_say=text).model_dump_json(), []) is not None


@pytest.mark.parametrize(
    "text",
    [
        "I have five years of Python experience.",
        "I built this system at my previous company.",
        "I used this approach at Salesforce.",
        "In my current role I maintain the billing system.",
        "I've used a set at Salesforce.",
        "I built a function and I worked at InventedCorp.",
    ],
)
def test_code_personal_claims_still_need_evidence(text):
    with pytest.raises(ValueError, match="Personal history without evidence"):
        code_assist.validate(answer(what_to_say=text), [])


def test_document_supported_history_and_normal_cue_unchanged():
    from app.cues.grounding import grounding_issue

    text = "I used Python at Salesforce."
    assert (
        code_assist.validate(
            answer(what_to_say=text, evidence_ids=["E1"]), [evidence(text)]
        ).grounding
        == "document_supported"
    )
    procedural = "I've used a set to track values in this solution."
    assert grounding_issue(procedural, []) == "Personal history without evidence"
    assert code_assist.validate(answer(what_to_say=procedural), []).answer == procedural


def test_zero_document_followup_procedural_answer_needs_no_regeneration(settings):
    async def run():
        settings.openai_api_key = SecretStr("fictional-key")
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(
                200,
                stream=Stream(
                    frames(answer(what_to_say="I've used a set to track values in this solution."))
                ),
            )

        result = await generate_cue(
            OpenAIProvider(settings, httpx.MockTransport(handler)),
            code_input(
                question="Can you optimize that solution?",
                coding_context=CodingContext(
                    problem="Find duplicates", language="python", code=CODE
                ),
            ),
            [],
        )
        assert result.code_assist is not None
        assert len(calls) == 1

    asyncio.run(run())


def test_unrelated_evidence_does_not_support_years_of_experience():
    with pytest.raises(ValueError, match="Unsupported numeric fact"):
        code_assist.validate(
            answer(what_to_say="I have five years of Python experience."),
            [evidence("Python scripting for a reporting tool.")],
        )


REALISTIC_APPROACH = (
    "I use one set to track values already encountered and a second set to ensure "
    "each duplicate appears only once in the result."
)
REALISTIC_SPOKEN = (
    "I use sets for expected constant-time membership checks, so I can scan the array "
    "once instead of comparing every pair. One set tracks values I have seen, and "
    "another prevents reporting the same duplicate more than once."
)


@pytest.mark.parametrize(
    "draft",
    [
        answer(approach=REALISTIC_APPROACH, what_to_say=REALISTIC_SPOKEN),
        answer(
            approach="I've chosen this approach because lookup is O(1) on average.",
            what_to_say="I've removed the frequency dictionary to reduce auxiliary memory.",
        ),
        answer(
            language="Apex",
            code="Set<String> seen = new Set<String>();\n",
            approach="My approach is to collect keys before querying.",
            complexity=None,
            what_to_say="I'm using one SOQL query to keep this bulk-safe.",
        ),
        answer(
            language="SQL",
            code="SELECT DISTINCT salary FROM employees;\n",
            approach="I would use a distinct projection.",
            complexity=None,
            what_to_say="I chose this approach to return unique salaries.",
        ),
    ],
)
def test_complete_current_solution_payloads_without_documents(draft):
    assert code_assist.validate(draft, []).code_assist.code == draft.code
    assert code_assist.preview(draft.model_dump_json(), []) is not None


@pytest.mark.parametrize(
    "claim",
    [
        "I have five years of Python experience.",
        "I've used Python professionally for five years.",
        "I built a similar system at my previous company.",
        "At Salesforce I implemented this pattern.",
        "In my current role I use this every day.",
        "I have solved this problem many times before.",
    ],
)
def test_complete_payload_biography_needs_evidence(claim):
    draft = answer(approach=REALISTIC_APPROACH, what_to_say=claim)
    with pytest.raises(ValueError, match="Personal history without evidence"):
        code_assist.validate(draft, [])
    assert code_assist.preview(draft.model_dump_json(), []) is None
    assert (
        code_assist.validate(
            answer(what_to_say=claim, evidence_ids=["E1"]), [evidence(claim)]
        ).grounding
        == "document_supported"
    )


def test_diagnostics_identify_field_rule_and_sentence_without_content(caplog):
    from app.cues.code_claims import inspect_fields

    claim = "I built a similar system at my previous company."
    draft = answer(what_to_say="I scan the array once. " + claim)
    rejection = inspect_fields(draft.model_dump(), [])
    assert (rejection.field, rejection.sentence_index, rejection.rule) == (
        "what_to_say",
        1,
        "employment",
    )
    with pytest.raises(ValueError):
        code_assist.validate(draft, [])
    assert "field=what_to_say sentence_index=1 rule=employment" in caplog.text
    assert claim not in caplog.text and CODE not in caplog.text


def test_realistic_followup_stream_succeeds_without_regeneration(settings):
    async def run():
        settings.openai_api_key = SecretStr("fictional-key")
        calls, events = [], []
        draft = answer(
            approach="I've chosen this approach because lookup is O(1) on average.",
            what_to_say=REALISTIC_SPOKEN,
        )

        def handler(request):
            calls.append(request)
            return httpx.Response(200, stream=Stream(frames(draft)))

        async def emit(event):
            events.append(event)

        result = await generate_cue(
            OpenAIProvider(settings, httpx.MockTransport(handler)),
            code_input(
                question="Can you optimize that solution?",
                coding_context=CodingContext(
                    problem="Find duplicates", language="python", code=CODE
                ),
            ),
            [],
            emit,
        )
        assert result.answer == REALISTIC_SPOKEN
        assert len(calls) == 1
        assert any(event["type"] == "partial" for event in events)
        assert not any(event["type"] == "reset" for event in events)

    asyncio.run(run())
