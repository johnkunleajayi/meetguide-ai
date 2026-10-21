"""Fictional data, repository doubles and offline PostgreSQL DDL only."""

import json
from io import StringIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from test_context import ORIGIN, upload
from test_context import library as library
from test_cues import cue_api as cue_api
from test_cues import payload, post

from app.context.repository import ContextRepository
from app.core.auth import SESSION_COOKIE
from app.cues.prompt import user_prompt
from app.models.preparation import ActivePreparation, Preparation, PreparationDocument
from app.preparations.domain import PURPOSES
from app.preparations.repository import PreparationRepository
from app.preparations.snapshot import resolve


def save(
    client,
    purpose="custom",
    documents=(),
    objective="Discuss the fictional project",
    identifier=None,
):
    body = dict(
        purpose=purpose,
        objective=objective,
        documents=[dict(document_id=d, context_role="reference_material") for d in documents],
    )
    return client.request(
        "PUT" if identifier else "POST",
        "/api/preparations" + (f"/{identifier}" if identifier else ""),
        json=body,
        headers=ORIGIN,
    )


@pytest.mark.parametrize("purpose", [*PURPOSES, "future_workshop"])
def test_purpose_objective_persist_and_optional_context(library, purpose):
    client, *_ = library
    created = save(client, purpose, objective="  A fictional objective  ")
    assert created.status_code == 201
    item = created.json()
    assert item["purpose"] == purpose and item["objective"] == "A fictional objective"
    assert item["documents"] == [] and not item["active"]
    assert client.get("/api/preparations").json() == [item]


def test_existing_document_explicit_reuse_detach_and_actual_delete(library):
    client, repo, storage, _ = library
    document = upload(client).json()
    assert client.get("/api/preparations").json() == []
    first = save(client, "job_interview", [document["id"]]).json()
    second = save(client, "sales_meeting", [document["id"]]).json()
    assert len(second["documents"]) == 1
    detached = save(client, "job_interview", identifier=first["id"]).json()
    assert detached["documents"] == []
    assert UUID(document["id"]) in repo.documents and repo.chunks
    assert client.get("/api/preparations").json()[1]["documents"]
    assert (
        client.delete(f"/api/context/documents/{document['id']}", headers=ORIGIN).status_code == 204
    )
    assert not repo.documents and not repo.chunks
    assert all(not item["documents"] for item in client.get("/api/preparations").json())
    assert not list(storage.root.iterdir())


def test_active_switch_ownership_and_untrusted_origin(library):
    client, _, _, users = library
    a, b = save(client).json(), save(client, "client_meeting").json()
    for item in [a, b]:
        assert (
            client.post(f"/api/preparations/{item['id']}/activate", headers=ORIGIN).status_code
            == 204
        )
        assert [p["id"] for p in client.get("/api/preparations").json() if p["active"]] == [
            item["id"]
        ]
    document = upload(client).json()
    client.cookies.set(SESSION_COOKIE, "1" * 43)
    assert client.get("/api/preparations").json() == []
    assert save(client, documents=[document["id"]]).status_code == 404
    assert save(client, identifier=a["id"]).status_code == 404
    assert client.post(f"/api/preparations/{a['id']}/activate", headers=ORIGIN).status_code == 404
    assert (
        client.post(
            f"/api/preparations/{a['id']}/freeze",
            headers={"Authorization": "Bearer " + "1" * 43},
            json={"expected_updated_at": a["updated_at"]},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/preparations", json={"purpose": "custom", "objective": "test"}
        ).status_code
        == 403
    )
    client.cookies.clear()
    assert client.get("/api/preparations").status_code == 401


def test_frozen_snapshot_revision_and_purpose_prompt(library):
    client, _, _, users = library
    doc = upload(client).json()
    a = save(client, "sales_meeting", [doc["id"]], "Discovery with fictional Acme").json()
    native = {"Authorization": "Bearer " + "0" * 43}
    freeze_url = f"/api/preparations/{a['id']}/freeze"
    response = client.post(
        freeze_url, headers=native, json={"expected_updated_at": a["updated_at"]}
    )
    assert response.status_code == 200
    token = response.json()["preparation_token"]
    snapshot = resolve(client.app, users[0].id, token)
    changed = save(client, "internal_meeting", objective="A changed objective", identifier=a["id"])
    assert changed.status_code == 200
    assert (
        client.post(
            freeze_url, headers=native, json={"expected_updated_at": a["updated_at"]}
        ).status_code
        == 409
    )
    b = save(client).json()
    client.post(f"/api/preparations/{b['id']}/activate", headers=ORIGIN)
    assert resolve(client.app, users[0].id, token) == snapshot
    request = payload()
    request._preparation = snapshot
    prompt = json.loads(user_prompt(request, []))
    assert prompt["session_preparation"] == {
        "purpose": "sales_meeting",
        "objective": "Discovery with fictional Acme",
    }
    assert snapshot.documents[0].document_id == UUID(doc["id"])
    for owner, value in [(users[1].id, token), (users[0].id, token + "bad")]:
        with pytest.raises(ValueError):
            resolve(client.app, owner, value)
    # A browser cookie cannot request a native live snapshot.
    assert (
        client.post(
            freeze_url, headers=ORIGIN, json={"expected_updated_at": a["updated_at"]}
        ).status_code
        == 401
    )


def test_scoped_retrieval_no_cross_preparation_or_user_leakage(library):
    client, *_ = library
    a = upload(client, b"Salesforce integration experience for Client Alpha.", "resume.txt").json()
    b = upload(client, b"Salesforce product proposal for Client Beta.", "proposal.txt").json()
    pa = save(client, "job_interview", [a["id"]]).json()
    pb = save(client, "sales_meeting", [b["id"]]).json()
    empty = save(client).json()

    def retrieve(prep, **extra):
        return client.post(
            "/api/context/retrieve",
            headers=ORIGIN,
            json={"query": "Salesforce", "preparation_id": prep, **extra},
        )

    for prep, expected in [(pa, a), (pb, b)]:
        result = retrieve(prep["id"])
        assert result.status_code == 200
        assert {row["document_id"] for row in result.json()} == {expected["id"]}
    assert retrieve(pb["id"], document_id=a["id"]).json() == []
    assert retrieve(empty["id"]).json() == []
    client.cookies.set(SESSION_COOKIE, "1" * 43)
    assert retrieve(pa["id"]).status_code == 404


def test_postgres_constraints_and_migration_offline():
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    revision = ScriptDirectory.from_config(config).get_revision("0004_session_preparations")
    assert revision.down_revision == "0003_context_library"
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        revision.module.upgrade()
    sql = output.getvalue()
    for model in [Preparation, PreparationDocument, ActivePreparation]:
        assert f"CREATE TABLE {model.__tablename__}" in sql
        ddl = str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
        assert "user_id" in ddl
    assert "FOREIGN KEY(document_id, user_id)" in sql
    assert "FOREIGN KEY(preparation_id, user_id)" in sql
    assert "uq_document_owner" in sql and "ON DELETE CASCADE" in sql
    assert "INSERT" not in sql and "DELETE FROM" not in sql
    output.seek(0)
    output.truncate()
    with Operations.context(context):
        revision.module.downgrade()
    assert "DROP TABLE context_documents" not in output.getvalue()


def test_real_repository_queries_scope_owners_and_ready_documents():
    owner, identifier = uuid4(), uuid4()

    class Database:
        def __init__(self):
            self.queries = []

        def scalar(self, query):
            self.queries.append(query)
            return None

        def execute(self, query):
            self.queries.append(query)
            return self

        def all(self):
            return []

    database = Database()
    assert PreparationRepository(database).owned(owner, identifier) is None
    assert ContextRepository(database).scoped_rows(owner, [identifier]) == []
    for query in database.queries:
        compiled = query.compile(dialect=postgresql.dialect())
        assert owner in compiled.params.values()
        assert "user_id =" in str(compiled)
    assert "status =" in str(database.queries[-1]) and " IN " in str(database.queries[-1])
    count = len(database.queries)
    assert ContextRepository(database).scoped_rows(owner, []) == []
    assert len(database.queries) == count


def test_live_cue_rejects_missing_snapshot_before_provider(cue_api):
    client, provider, repository, _ = cue_api
    response = client.post(
        "/api/cues/generate",
        json=payload().model_dump(),
        headers={"Authorization": "Bearer " + "a" * 43},
    )
    assert response.status_code == 409
    assert not provider.calls and not repository.owners


def test_live_cue_receives_frozen_purpose_objective_and_preserves_interview_grounding(cue_api):
    client, provider, _, _ = cue_api
    response = post(client)
    assert response.status_code == 200
    assert response.json()["grounding"] == "document_supported"
    sent = provider.calls[0][1]
    assert sent["session_preparation"] == {
        "purpose": "job_interview",
        "objective": "Fictional interview",
    }
    assert sent["document_evidence"][0]["context_role"] == "resume"


def test_snapshot_expires_without_logging_contents(library, monkeypatch):
    from itsdangerous.timed import TimestampSigner

    from app.preparations.snapshot import MAX_AGE, freeze

    client, _, _, users = library
    item = save(client).json()
    from app.preparations.domain import PreparationView

    token = freeze(client.app, users[0].id, PreparationView.model_validate(item))
    current = TimestampSigner.get_timestamp
    monkeypatch.setattr(TimestampSigner, "get_timestamp", lambda self: current(self) + MAX_AGE + 1)
    with pytest.raises(ValueError, match="expired or is invalid"):
        resolve(client.app, users[0].id, token)


def test_no_document_live_scope_does_not_fall_back_to_account_resume(cue_api):
    from datetime import UTC, datetime

    from app.preparations.domain import PreparationView
    from app.preparations.snapshot import freeze

    client, provider, repository, user = cue_api
    now = datetime.now(UTC)
    view = PreparationView(
        id=uuid4(),
        purpose="sales_meeting",
        objective="Fictional discovery",
        documents=[],
        created_at=now,
        updated_at=now,
    )
    client.preparation_token = freeze(client.app, user.id, view)
    result = post(client)
    assert result.status_code == 200 and result.json()["grounding"] == "general_approach"
    assert repository.owners == []
    assert provider.calls[0][1]["document_evidence"] == []


@pytest.mark.parametrize(
    "language",
    ["auto", "python", "javascript", "typescript", "java", "apex", "csharp", "go", "sql", "other"],
)
def test_optional_coding_preferences_persist_and_freeze(library, language):
    from app.preparations.domain import PreparationView
    from app.preparations.snapshot import freeze

    client, _, _, users = library
    body = {
        "purpose": "job_interview",
        "objective": "Fictional coding interview",
        "documents": [],
        "technical_interview": True,
        "coding_language": language,
    }
    response = client.post("/api/preparations", json=body, headers=ORIGIN)
    assert response.status_code == 201
    saved = response.json()
    assert saved["technical_interview"] is True and saved["coding_language"] == language
    assert client.get("/api/preparations").json()[0]["coding_language"] == language
    token = freeze(client.app, users[0].id, PreparationView.model_validate(saved))
    assert resolve(client.app, users[0].id, token).coding_language == language
