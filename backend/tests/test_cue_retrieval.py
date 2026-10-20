"""Synthetic résumé/context only. No provider calls or real database connections."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_context import library as library
from test_context import upload
from test_preparations import save

from app.context.retrieval import LocalLexicalIndex
from app.cues.domain import CueInput
from app.cues.retrieval_query import retrieval_query
from app.cues.service import retrieve_evidence
from app.preparations.domain import PreparedContext, Selection
from app.preparations.snapshot import freeze, resolve


def question(owner, documents=(), purpose="job_interview", text="Tell me about yourself."):
    request = CueInput(
        type="question", speaker="them", finalized=True, confidence=0.94, question=text
    )
    request._preparation = PreparedContext(
        preparation_id=uuid4(),
        user_id=owner,
        purpose=purpose,
        objective="Salesforce Administrator interview with Fictional Co",
        documents=[Selection(document_id=d, context_role="resume") for d in documents],
    )
    return request


def test_broad_introduction_searches_selected_resume_and_cannot_leak_to_other_preparations(library):
    from uuid import UUID

    from app.preparations.domain import PreparationView

    client, repository, _, users = library
    resume = upload(
        client,
        b"Professional summary\nSalesforce Administrator building integrations.\n\n"
        b"Skills\nService Cloud and API automation.",
        "fictional-resume.txt",
    ).json()
    other = upload(
        client, b"Project agenda\nQuarterly procurement review and vendor approval.", "agenda.txt"
    ).json()
    a = save(client, "job_interview", [resume["id"]]).json()
    b = save(client, "job_interview").json()
    c = save(client, "job_interview", [other["id"]]).json()
    for preparation in [a, b, c]:
        snapshot = resolve(
            client.app,
            users[0].id,
            freeze(client.app, users[0].id, PreparationView.model_validate(preparation)),
        )
        request = question(users[0].id)
        request._preparation = snapshot
        evidence = retrieve_evidence(repository, users[0].id, request)
        if preparation is a:
            # Prove the exact lexical failure independently of the fixed query builder.
            rows = repository.scoped_rows(users[0].id, [UUID(resume["id"])])
            assert LocalLexicalIndex().rank(request.question, rows, 3) == []
            assert evidence and {e.document_id for e in evidence} == {UUID(resume["id"])}
            assert "Salesforce Administrator" in evidence[0].text
        else:
            assert all(e.document_id != UUID(resume["id"]) for e in evidence)
            if preparation is b:
                assert evidence == []
        # Same signed scope cannot be reused as another account's context.
        assert retrieve_evidence(repository, users[1].id, request) == []


@pytest.mark.parametrize(
    "text",
    [
        "Tell me about yourself.",
        "Could you tell me a bit about yourself?",
        "Walk me through your background.",
        "Introduce yourself.",
    ],
)
def test_interview_introduction_uses_only_bounded_preparation_objective(text):
    request = question(uuid4(), text=text)
    query = retrieval_query(request)
    assert request._preparation.objective in query and "professional summary" in query


@pytest.mark.parametrize(
    "purpose,text",
    [
        ("sales_meeting", "Tell me about yourself."),
        ("job_interview", "How did you test the Salesforce integration?"),
        ("job_interview", "What was the biggest challenge?"),
    ],
)
def test_other_purposes_specific_questions_and_followups_keep_existing_query(purpose, text):
    request = question(uuid4(), purpose=purpose, text=text)
    assert retrieval_query(request) == text + " "


def test_defensive_filter_never_ranks_an_unselected_document():
    owner, selected, unselected = uuid4(), uuid4(), uuid4()

    class Repository:
        def scoped_rows(self, user, ids):
            assert user == owner and ids == [selected]
            return [
                (
                    SimpleNamespace(id=unselected),
                    SimpleNamespace(
                        id=uuid4(), position=0, text="Professional summary Salesforce skills"
                    ),
                )
            ]

    assert retrieve_evidence(Repository(), owner, question(owner, [selected])) == []
