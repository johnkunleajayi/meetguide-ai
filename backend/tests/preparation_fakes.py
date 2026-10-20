"""In-memory repository double only. PostgreSQL constraints are checked via offline DDL."""

from datetime import UTC, datetime
from uuid import uuid4

from app.preparations.domain import PreparationView


class MemoryPreparations:
    def __init__(self, documents):
        self.documents = documents
        self.items = {}
        self.owners = {}
        self.active = {}

    def list(self, user_id):
        return [
            item.model_copy(
                update={
                    "active": self.active.get(user_id) == item.id,
                    "documents": [
                        entry
                        for entry in item.documents
                        if entry.document_id in self.documents.documents
                    ],
                }
            )
            for item in self.items.values()
            if self.owners[item.id] == user_id
        ]

    def view(self, user_id, preparation_id):
        return (
            next((item for item in self.list(user_id) if item.id == preparation_id), None)
            or self.missing()
        )

    def missing(self):
        raise LookupError

    def save(self, user_id, payload, preparation_id=None):
        if preparation_id:
            self.view(user_id, preparation_id)
        ids = [entry.document_id for entry in payload.documents]
        if len(set(ids)) != len(ids):
            raise ValueError("Select each document once")
        if any(
            self.documents.owned(user_id, identifier) is None
            or self.documents.documents[identifier].status != "ready"
            for identifier in ids
        ):
            raise LookupError
        now = datetime.now(UTC)
        identifier = preparation_id or uuid4()
        item = PreparationView(
            id=identifier,
            **payload.model_dump(),
            created_at=self.items[identifier].created_at if preparation_id else now,
            updated_at=now,
        )
        self.items[identifier] = item
        self.owners[identifier] = user_id
        return item

    def activate(self, user_id, identifier):
        self.view(user_id, identifier)
        self.active[user_id] = identifier
