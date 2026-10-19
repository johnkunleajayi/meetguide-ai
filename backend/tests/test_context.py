"""API tests use repository doubles, never SQLite or the developer's Neon database."""

from io import BytesIO, StringIO
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.context.api import get_storage
from app.context.extraction import MAX_UPLOAD, InvalidDocument, extract, normalize, safe_name
from app.context.repository import ContextRepository, get_context_repository
from app.context.retrieval import chunk_text
from app.context.storage import LocalDocumentStorage
from app.core.auth import SESSION_COOKIE
from app.db.auth_repository import get_auth_repository
from app.db.base import Base
from app.models import Document, DocumentChunk, User

ORIGIN = {"Origin": "http://127.0.0.1:5173"}


class MemoryContextRepository:
    def __init__(self):
        self.documents = {}
        self.chunks = []

    def list(self, user_id):
        return [doc for doc in self.documents.values() if doc.user_id == user_id]

    def count(self, user_id):
        return len(self.list(user_id))

    def owned(self, user_id, document_id):
        doc = self.documents.get(document_id)
        return doc if doc and doc.user_id == user_id else None

    def add(self, document, chunks):
        self.documents[document.id] = document
        self.chunks.extend(chunks)

    def rows(self, user_id, document_id):
        return [
            (doc, chunk)
            for doc in self.list(user_id)
            if doc.status == "ready" and (document_id is None or doc.id == document_id)
            for chunk in self.chunks
            if chunk.document_id == doc.id
        ]

    def remove(self, document):
        self.documents.pop(document.id, None)
        self.chunks = [chunk for chunk in self.chunks if chunk.document_id != document.id]

    def commit(self):
        pass

    def rollback(self):
        pass


@pytest.fixture
def library(client, tmp_path):
    repo = MemoryContextRepository()
    storage = LocalDocumentStorage(tmp_path / "private")
    users = [User(id=uuid4(), email=f"user{i}@example.test") for i in range(2)]

    class Auth:
        def user_for_session(self, hashed_token, now):
            # Tokens distinguish authenticated identities, production hashes lookup in PostgreSQL.
            from app.core.auth import token_hash

            return next(
                (user for i, user in enumerate(users) if hashed_token == token_hash(str(i) * 43)),
                None,
            )

    client.app.dependency_overrides[get_auth_repository] = lambda: Auth()
    client.app.dependency_overrides[get_context_repository] = lambda: repo
    client.app.dependency_overrides[get_storage] = lambda: storage
    client.cookies.set(SESSION_COOKIE, "0" * 43)
    yield client, repo, storage, users
    client.app.dependency_overrides.clear()


def upload(client, content=b"Experience\nLed a team of six engineers.", name="resume.txt"):
    return client.post(
        "/api/context/documents",
        content=content,
        headers={**ORIGIN, "X-Document-Name": name, "Content-Type": "application/octet-stream"},
    )


def make_pdf(text="Salesforce integration and API automation."):
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    if text:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_docx(xml=None):
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.document.main+xml"/></Types>',
        )
        archive.writestr(
            "word/document.xml",
            xml
            or '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Leadership</w:t></w:r></w:p>"
            "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Managed six engineers.</w:t></w:r>"
            "</w:p></w:tc></w:tr></w:tbl></w:body></w:document>",
        )
    return buffer.getvalue()


def test_authenticated_upload_list_and_private_response(library):
    client, repo, storage, users = library
    response = upload(client)
    assert response.status_code == 201
    body = response.json()
    assert body["context_type"] == "resume" and body["status"] == "ready"
    assert body["media_type"] == "text/plain"
    assert not {"storage_key", "extracted_text", "user_id", "sha256"}.intersection(body)
    document = repo.documents[UUID(body["id"])]
    assert document.user_id == users[0].id
    assert (storage.root / document.storage_key).read_bytes().startswith(b"Experience")
    assert repo.chunks and repo.chunks[0].document_id == document.id
    listing = client.get("/api/context/documents")
    assert listing.json() == [body]
    assert listing.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/context/documents"),
        ("post", "/api/context/documents"),
        ("post", "/api/context/retrieve"),
        ("delete", f"/api/context/documents/{uuid4()}"),
    ],
)
def test_unauthenticated_rejection(library, method, path):
    client, *_ = library
    client.cookies.clear()
    assert getattr(client, method)(path, headers=ORIGIN).status_code == 401


def test_untrusted_or_missing_origin_cannot_upload_retrieve_or_delete(library):
    client, *_ = library
    assert (
        client.post(
            "/api/context/documents", content=b"hello", headers={"X-Document-Name": "cv.txt"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/context/retrieve",
            json={"query": "leadership"},
            headers={"Origin": "https://untrusted.example"},
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "data,name,expected",
    [
        (make_pdf(), "cv.pdf", "Salesforce"),
        (make_docx(), "cv.docx", "Managed"),
        (b"\xef\xbb\xbfLeadership\r\nManaged six engineers.", "cv.txt", "Leadership"),
    ],
)
def test_supported_format_upload_and_extraction(library, data, name, expected):
    client, repo, *_ = library
    response = upload(client, data, name)
    assert response.status_code == 201, response.text
    document = repo.documents[UUID(response.json()["id"])]
    assert expected in document.extracted_text


@pytest.mark.parametrize(
    "data,name",
    [
        (b"", "cv.txt"),
        (b"  \n\t", "cv.txt"),
        (b"not a PDF", "cv.pdf"),
        (b"%PDF-1.7\nsecret malformed content", "cv.pdf"),
        (b"PK\x03\x04bad zip", "cv.docx"),
        (b"MZ\x00binary", "cv.txt"),
        (b"hello", "cv.exe"),
        (b"<html>not text</html>", "cv.txt"),
        (b"\xff\xfe", "cv.txt"),
        (make_pdf(""), "scanned.pdf"),
        (make_docx("<notword/>"), "cv.docx"),
    ],
)
def test_invalid_empty_malformed_and_spoofed_files_leave_no_data(library, data, name):
    client, repo, storage, *_ = library
    response = upload(client, data, name)
    assert response.status_code == 422
    assert "secret malformed content" not in response.text
    assert not repo.documents and not repo.chunks
    assert not storage.root.exists() or not list(storage.root.iterdir())


def test_upload_size_limit_with_and_without_content_length(library):
    client, repo, *_ = library
    headers = {**ORIGIN, "X-Document-Name": "cv.txt"}
    assert upload(client, b"a" * (MAX_UPLOAD + 1)).status_code == 413
    assert (
        client.post(
            "/api/context/documents", content=iter([b"a" * MAX_UPLOAD, b"b"]), headers=headers
        ).status_code
        == 413
    )
    assert not repo.documents


def test_ownership_isolation_for_list_retrieval_and_delete(library):
    client, repo, storage, *_ = library
    identifier = upload(client, b"Salesforce integration API automation.").json()["id"]
    client.cookies.set(SESSION_COOKIE, "1" * 43)
    assert client.get("/api/context/documents").json() == []
    for document_id in [None, identifier]:
        response = client.post(
            "/api/context/retrieve",
            json={"query": "Salesforce", "document_id": document_id},
            headers=ORIGIN,
        )
        assert response.status_code == 200 and response.json() == []
    assert client.delete(f"/api/context/documents/{identifier}", headers=ORIGIN).status_code == 404
    assert len(repo.documents) == 1 and len(list(storage.root.iterdir())) == 1


def test_retrieval_ranking_identity_and_no_matches(library):
    client, *_ = library
    first = upload(
        client, b"Salesforce integrations\nBuilt Salesforce API automation and integrations."
    ).json()["id"]
    second = upload(
        client, b"Leadership\nManaged and mentored a team of six engineers.", "leadership.txt"
    ).json()["id"]
    for query, expected in [
        ("Salesforce integration experience", first),
        ("leadership experience", second),
    ]:
        hits = client.post("/api/context/retrieve", json={"query": query}, headers=ORIGIN).json()
        assert hits[0]["document_id"] == expected
        assert hits[0]["chunk_id"] and hits[0]["text"] and hits[0]["document_name"]
        assert hits[0]["score"] > 0 and hits[0]["rank"] == 1
    assert (
        client.post("/api/context/retrieve", json={"query": "astrophysics"}, headers=ORIGIN).json()
        == []
    )


def test_delete_removes_file_document_text_chunks_and_search_results(library):
    client, repo, storage, *_ = library
    identifier = upload(client).json()["id"]
    response = client.delete(f"/api/context/documents/{identifier}", headers=ORIGIN)
    assert response.status_code == 204
    assert not repo.documents and not repo.chunks and not list(storage.root.iterdir())
    assert client.get("/api/context/documents").json() == []
    assert (
        client.post("/api/context/retrieve", json={"query": "leadership"}, headers=ORIGIN).json()
        == []
    )


def test_failed_delete_is_tombstoned_not_retrievable_and_retryable(library, monkeypatch):
    client, repo, storage, *_ = library
    identifier = upload(client).json()["id"]
    original = storage.delete
    monkeypatch.setattr(
        storage, "delete", lambda _: (_ for _ in ()).throw(OSError("private storage path"))
    )
    response = client.delete(f"/api/context/documents/{identifier}", headers=ORIGIN)
    assert response.status_code == 503 and "private storage path" not in response.text
    assert repo.documents[UUID(identifier)].status == "deleting"
    assert (
        client.post("/api/context/retrieve", json={"query": "leadership"}, headers=ORIGIN).json()
        == []
    )
    monkeypatch.setattr(storage, "delete", original)
    assert client.delete(f"/api/context/documents/{identifier}", headers=ORIGIN).status_code == 204


def test_database_failure_cleans_uploaded_file(library, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    client, _, storage, _ = library
    repo = library[1]
    monkeypatch.setattr(
        repo, "add", lambda *_: (_ for _ in ()).throw(SQLAlchemyError("private database error"))
    )
    response = upload(client)
    assert response.status_code == 503 and "private database error" not in response.text
    assert not list(storage.root.iterdir())


def test_chunking_and_normalization_preserve_content_and_bounds():
    text = normalize(
        "Leadership\r\n\r\nManaged   six people.\r\n\r\n"
        + "Salesforce integration experience. " * 100
    )
    chunks = chunk_text(text)
    assert len(chunks) > 1 and all(0 < len(chunk) <= 1200 for chunk in chunks)
    assert "Managed six people." in chunks[0]
    assert all("Salesforce" in chunk for chunk in chunks[1:])
    assert chunk_text("") == []


def test_safe_storage_identifiers_filenames_and_symlinks(tmp_path):
    storage = LocalDocumentStorage(tmp_path)
    assert safe_name("../../private\\cv.txt") == "cv.txt"
    for key in ["../secret", "x" * 32, "", "/outside"]:
        with pytest.raises(ValueError):
            storage.put(key, b"safe")
    key = uuid4().hex
    storage.put(key, b"safe")
    with pytest.raises(FileExistsError):
        storage.put(key, b"overwrite")
    assert (tmp_path / key).read_bytes() == b"safe"


def test_docx_entity_and_zip_bomb_protection():
    malicious = '<!DOCTYPE x [<!ENTITY content "secret">]><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:t>&content;</w:t></w:p></w:document>'
    with pytest.raises(InvalidDocument):
        extract(make_docx(malicious), "cv.docx")
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "a" * 100_000)
    with pytest.raises(InvalidDocument):
        extract(buffer.getvalue(), "cv.docx")


def test_repository_sql_scopes_all_reads_and_deletes():
    class Database:
        def __init__(self):
            self.statements = []

        def scalars(self, query):
            self.statements.append(query)
            return []

        def scalar(self, query):
            self.statements.append(query)
            return None

        def execute(self, query):
            self.statements.append(query)
            return self

        def all(self):
            return []

    database = Database()
    repo = ContextRepository(database)
    owner, identifier = uuid4(), uuid4()
    repo.list(owner)
    repo.count(owner)
    repo.owned(owner, identifier)
    repo.rows(owner, identifier)
    repo.remove(Document(id=identifier, user_id=owner))
    for query in database.statements:
        sql = str(query.compile(dialect=postgresql.dialect()))
        assert "context_documents.user_id =" in sql and owner in query.compile().params.values()
        assert "context_documents.extracted_text" not in sql


def test_web_cors_allows_credentialed_upload_and_delete(client):
    for method in ["POST", "DELETE"]:
        response = client.options(
            "/api/context/documents",
            headers={
                **ORIGIN,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "content-type,x-document-name",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == ORIGIN["Origin"]
        assert response.headers["access-control-allow-credentials"] == "true"


def test_migration_metadata_and_offline_ddl():
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["0003_context_library"]
    revision = scripts.get_revision("0003_context_library")
    assert revision.down_revision == "0002_sessions"
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        revision.module.upgrade()

    def normalize_sql(sql):
        normalized = " ".join(sql.split()).rstrip(";")
        return normalized[:-1].rstrip() if normalized.startswith("CREATE TABLE") else normalized

    statements = [normalize_sql(sql) for sql in output.getvalue().split(";") if sql.strip()]
    expected = []
    for model in [Document, DocumentChunk]:
        assert model.__table__.metadata is Base.metadata
        expected.append(
            normalize_sql(str(CreateTable(model.__table__).compile(dialect=postgresql.dialect())))
        )
        expected.extend(
            normalize_sql(str(CreateIndex(index).compile(dialect=postgresql.dialect())))
            for index in model.__table__.indexes
        )
    # SQL constraint declaration order has no semantic significance.
    assert [sorted(sql.split(", ")) for sql in statements] == [
        sorted(sql.split(", ")) for sql in expected
    ]
    assert "ON DELETE CASCADE" in output.getvalue()
    output.seek(0)
    output.truncate()
    with Operations.context(context):
        revision.module.downgrade()
    assert "DROP TABLE context_chunks" in output.getvalue()
    assert "DROP TABLE context_documents" in output.getvalue()
