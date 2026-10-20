from uuid import UUID

from fastapi import Depends
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, defer

from app.db.session import get_db
from app.models.document import Document, DocumentChunk


class ContextRepository:
    def __init__(self, database: Session):
        self.database = database

    def list(self, user_id: UUID) -> list[Document]:
        return list(
            self.database.scalars(
                select(Document)
                .options(defer(Document.extracted_text))
                .where(Document.user_id == user_id)
                .order_by(Document.created_at.desc())
            )
        )

    def count(self, user_id: UUID) -> int:
        return self.database.scalar(
            select(func.count()).select_from(Document).where(Document.user_id == user_id)
        )

    def owned(self, user_id: UUID, document_id: UUID) -> Document | None:
        return self.database.scalar(
            select(Document)
            .options(defer(Document.extracted_text))
            .where(Document.id == document_id, Document.user_id == user_id)
            .with_for_update()
        )

    def add(self, document: Document, chunks: list[DocumentChunk]) -> None:
        self.database.add(document)
        self.database.flush()
        self.database.add_all(chunks)

    def rows(self, user_id: UUID, document_id: UUID | None) -> list[tuple[Document, DocumentChunk]]:
        statement = (
            select(Document, DocumentChunk)
            .options(defer(Document.extracted_text))
            .join(DocumentChunk, DocumentChunk.document_id == Document.id)
            .where(Document.user_id == user_id, Document.status == "ready")
        )
        if document_id is not None:
            statement = statement.where(Document.id == document_id)
        return list(self.database.execute(statement).all())

    def scoped_rows(self, user_id: UUID, document_ids: list[UUID]):
        if not document_ids:
            return []
        return list(
            self.database.execute(
                select(Document, DocumentChunk)
                .options(defer(Document.extracted_text))
                .join(DocumentChunk, DocumentChunk.document_id == Document.id)
                .where(
                    Document.user_id == user_id,
                    Document.status == "ready",
                    Document.id.in_(document_ids),
                )
            ).all()
        )

    def remove(self, document: Document) -> None:
        from app.models.preparation import Preparation, PreparationDocument

        self.database.execute(
            update(Preparation)
            .where(
                Preparation.user_id == document.user_id,
                Preparation.id.in_(
                    select(PreparationDocument.preparation_id).where(
                        PreparationDocument.user_id == document.user_id,
                        PreparationDocument.document_id == document.id,
                    )
                ),
            )
            .values(updated_at=func.now())
        )
        # Ownership was checked under a row lock; DB cascade removes every chunk.
        self.database.execute(
            delete(Document).where(Document.id == document.id, Document.user_id == document.user_id)
        )

    def commit(self) -> None:
        self.database.commit()

    def rollback(self) -> None:
        self.database.rollback()


def get_context_repository(database: Session = Depends(get_db)) -> ContextRepository:
    return ContextRepository(database)
