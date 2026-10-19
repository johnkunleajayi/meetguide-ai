import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.context.extraction import InvalidDocument, extract, safe_name
from app.context.repository import ContextRepository
from app.context.retrieval import RetrievalIndex
from app.context.storage import DocumentStorage
from app.models.document import Document, DocumentChunk


class ContextLibrary:
    def __init__(
        self, repository: ContextRepository, storage: DocumentStorage, index: RetrievalIndex
    ):
        self.repository, self.storage, self.index = repository, storage, index

    def upload(self, user_id: UUID, name: str, content: bytes, context_type: str) -> Document:
        if context_type != "resume":
            raise InvalidDocument("Only resume context is supported for now.")
        if self.repository.count(user_id) >= 50:
            raise InvalidDocument(
                "The library supports up to 50 documents. Delete one before uploading."
            )
        name = safe_name(name)
        text, media = extract(content, name)
        document = Document(
            id=uuid4(),
            user_id=user_id,
            name=name,
            context_type=context_type,
            media_type=media,
            size_bytes=len(content),
            storage_key=uuid4().hex,
            sha256=hashlib.sha256(content).hexdigest(),
            status="ready",
            extracted_text=text,
            created_at=datetime.now(UTC),
            processing_version="local-v1",
        )
        chunks = [
            DocumentChunk(id=uuid4(), document_id=document.id, position=position, text=part)
            for position, part in enumerate(self.index.chunks(text))
        ]
        self.storage.put(document.storage_key, content)
        try:
            self.repository.add(document, chunks)
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            self.storage.delete(document.storage_key)
            raise
        return document

    def delete(self, user_id: UUID, document_id: UUID) -> bool:
        document = self.repository.owned(user_id, document_id)
        if document is None:
            return False
        # Durable tombstone: a failed file/DB deletion can be retried and cannot be retrieved.
        document.status = "deleting"
        self.repository.commit()
        self.storage.delete(document.storage_key)
        self.repository.remove(document)
        self.repository.commit()
        return True
