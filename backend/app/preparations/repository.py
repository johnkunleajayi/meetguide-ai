from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.document import Document
from app.models.preparation import ActivePreparation, Preparation, PreparationDocument
from app.preparations.domain import PreparationInput, PreparationView, Selection


class PreparationRepository:
    def __init__(self, database: Session):
        self.database = database

    def owned(self, user_id: UUID, preparation_id: UUID):
        return self.database.scalar(
            select(Preparation)
            .where(Preparation.id == preparation_id, Preparation.user_id == user_id)
            .with_for_update()
        )

    def list(self, user_id):
        items = self.database.scalars(
            select(Preparation)
            .where(Preparation.user_id == user_id)
            .order_by(Preparation.updated_at.desc())
        ).all()
        active = self.database.get(ActivePreparation, user_id)
        selections = self.database.scalars(
            select(PreparationDocument).where(PreparationDocument.user_id == user_id)
        ).all()
        return [
            PreparationView(
                id=item.id,
                purpose=item.purpose,
                objective=item.objective,
                created_at=item.created_at,
                updated_at=item.updated_at,
                active=bool(active and active.preparation_id == item.id),
                documents=[
                    Selection(document_id=link.document_id, context_role=link.context_role)
                    for link in selections
                    if link.preparation_id == item.id
                ],
            )
            for item in items
        ]

    def save(self, user_id, payload: PreparationInput, preparation_id=None):
        # Serialize saves/activation per account, including first preparation creation.
        from app.models.user import User

        self.database.execute(select(User.id).where(User.id == user_id).with_for_update())
        item = (
            self.owned(user_id, preparation_id) if preparation_id else Preparation(user_id=user_id)
        )
        if item is None:
            raise LookupError
        ids = {entry.document_id for entry in payload.documents}
        if len(ids) != len(payload.documents):
            raise ValueError("Select each document once")
        owned = (
            set(
                self.database.scalars(
                    select(Document.id)
                    .where(
                        Document.user_id == user_id,
                        Document.status == "ready",
                        Document.id.in_(ids),
                    )
                    .with_for_update()
                ).all()
            )
            if ids
            else set()
        )
        if owned != ids:
            raise LookupError
        if preparation_id is None and len(self.list(user_id)) >= 100:
            raise ValueError("Up to 100 preparations are supported")
        item.purpose, item.objective = payload.purpose, payload.objective
        item.updated_at = datetime.now(UTC)
        self.database.add(item)
        self.database.flush()
        self.database.execute(
            delete(PreparationDocument).where(
                PreparationDocument.preparation_id == item.id,
                PreparationDocument.user_id == user_id,
            )
        )
        self.database.add_all(
            [
                PreparationDocument(
                    preparation_id=item.id,
                    user_id=user_id,
                    document_id=entry.document_id,
                    context_role=entry.context_role,
                )
                for entry in payload.documents
            ]
        )
        self.database.commit()
        return next(view for view in self.list(user_id) if view.id == item.id)

    def activate(self, user_id, preparation_id):
        from app.models.user import User

        self.database.execute(select(User.id).where(User.id == user_id).with_for_update())
        if self.owned(user_id, preparation_id) is None:
            raise LookupError
        self.database.execute(
            insert(ActivePreparation)
            .values(user_id=user_id, preparation_id=preparation_id)
            .on_conflict_do_update(
                index_elements=[ActivePreparation.user_id], set_={"preparation_id": preparation_id}
            )
        )
        self.database.commit()

    def view(self, user_id, preparation_id):
        # Lock while snapshotting so a concurrent save cannot mix purpose and selection.
        if self.owned(user_id, preparation_id) is None:
            raise LookupError
        return next(view for view in self.list(user_id) if view.id == preparation_id)


def get_preparations(database: Session = Depends(get_db)):
    return PreparationRepository(database)
