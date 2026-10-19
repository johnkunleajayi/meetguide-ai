from datetime import datetime
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.api.auth import NO_STORE
from app.context.extraction import MAX_UPLOAD, InvalidDocument
from app.context.repository import ContextRepository, get_context_repository
from app.context.retrieval import LocalLexicalIndex
from app.context.service import ContextLibrary
from app.context.storage import LocalDocumentStorage
from app.core import auth
from app.db.auth_repository import AuthRepository, get_auth_repository
from app.models import User

router = APIRouter(prefix="/context", tags=["context library"])


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    context_type: str
    media_type: str
    size_bytes: int
    status: str
    created_at: datetime


class RetrievalQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)
    query: str = Field(min_length=2, max_length=500)
    document_id: UUID | None = None
    limit: int = Field(default=5, ge=1, le=10)


class ContextMatch(BaseModel):
    document_id: UUID
    document_name: str
    context_type: str
    chunk_id: UUID
    text: str
    score: float
    rank: int


def current_user(
    request: Request, repository: AuthRepository = Depends(get_auth_repository)
) -> User:
    # Web cookie auth; native consumption is intentionally deferred to its milestone.
    try:
        user = auth.authenticated_user(repository, request.cookies.get(auth.SESSION_COOKIE))
    except SQLAlchemyError:
        raise HTTPException(
            503, "Authentication is temporarily unavailable", headers=NO_STORE
        ) from None
    if user is None:
        raise HTTPException(401, "Not authenticated", headers=NO_STORE)
    if (
        request.method != "GET"
        and request.headers.get("origin") != request.app.state.settings.frontend_origin
    ):
        raise HTTPException(403, "Untrusted request origin", headers=NO_STORE)
    return user


def get_storage(request: Request):
    return LocalDocumentStorage(request.app.state.settings.context_storage_dir)


def get_library(
    repository: ContextRepository = Depends(get_context_repository), storage=Depends(get_storage)
):
    return ContextLibrary(repository, storage, LocalLexicalIndex())


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents(
    response: Response,
    user: User = Depends(current_user),
    library: ContextLibrary = Depends(get_library),
):
    response.headers.update(NO_STORE)
    try:
        return library.repository.list(user.id)
    except SQLAlchemyError:
        raise HTTPException(
            503, "Context Library is temporarily unavailable", headers=NO_STORE
        ) from None


@router.post("/documents", status_code=201, response_model=DocumentSummary)
async def upload_document(
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    library: ContextLibrary = Depends(get_library),
):
    # Stream raw file bytes, not multipart: limit before buffering/spooling to disk.
    # Filename is URL-encoded UTF-8 in a header, never part of a storage path or URL.
    name = request.headers.get("x-document-name", "")
    if not name or len(name) > 2160:
        raise HTTPException(422, "A valid document filename is required", headers=NO_STORE)
    length = request.headers.get("content-length")
    if length is not None and (
        not length.isdecimal() or len(length) > 10 or int(length) > MAX_UPLOAD
    ):
        raise HTTPException(413, "Maximum upload size is 5 MB", headers=NO_STORE)
    content = bytearray()
    async for part in request.stream():
        if len(content) + len(part) > MAX_UPLOAD:
            raise HTTPException(413, "Maximum upload size is 5 MB", headers=NO_STORE)
        content.extend(part)
    try:
        document = await run_in_threadpool(
            library.upload, user.id, unquote(name, errors="strict"), bytes(content), "resume"
        )
    except (InvalidDocument, UnicodeError) as error:
        detail = str(error) if isinstance(error, InvalidDocument) else "Invalid document filename"
        raise HTTPException(422, detail, headers=NO_STORE) from None
    except OSError, SQLAlchemyError:
        raise HTTPException(
            503, "Unable to store document. Please retry.", headers=NO_STORE
        ) from None
    response.headers.update(NO_STORE)
    return document


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document_id: UUID,
    user: User = Depends(current_user),
    library: ContextLibrary = Depends(get_library),
):
    try:
        if not library.delete(user.id, document_id):
            raise HTTPException(404, "Document not found", headers=NO_STORE)
    except OSError, SQLAlchemyError:
        raise HTTPException(
            503, "Deletion incomplete. Please retry deleting this document.", headers=NO_STORE
        ) from None
    return Response(status_code=204, headers=NO_STORE)


@router.post("/retrieve", response_model=list[ContextMatch])
def retrieve(
    payload: RetrievalQuery,
    response: Response,
    user: User = Depends(current_user),
    library: ContextLibrary = Depends(get_library),
):
    try:
        rows = library.repository.rows(user.id, payload.document_id)
        ranked = library.index.rank(payload.query, rows, payload.limit)
    except SQLAlchemyError:
        raise HTTPException(
            503, "Context Library is temporarily unavailable", headers=NO_STORE
        ) from None
    response.headers.update(NO_STORE)
    return [
        ContextMatch(
            document_id=doc.id,
            document_name=doc.name,
            context_type=doc.context_type,
            chunk_id=chunk.id,
            text=chunk.text,
            score=round(score, 6),
            rank=rank,
        )
        for rank, (score, doc, chunk) in enumerate(ranked, 1)
    ]
