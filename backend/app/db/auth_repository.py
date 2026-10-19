from datetime import datetime
from uuid import uuid4

from fastapi import Depends
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DatabaseSession

from app.db.session import get_db
from app.models import Session, User


class AuthRepository:
    def __init__(self, database: DatabaseSession):
        self.database = database

    def upsert_user(self, email: str, name: str | None, avatar: str | None) -> User:
        # Also match pre-existing mixed-case emails before enforcing normalized storage.
        user = self.database.scalar(select(User).where(func.lower(func.btrim(User.email)) == email))
        if user is not None:
            user.email = email
            if name is not None:
                user.name = name
            if avatar is not None:
                user.avatar_url = avatar
            self.database.flush()
            return user
        values = {"id": uuid4(), "email": email, "name": name, "avatar_url": avatar}
        updates = {"updated_at": func.now()}
        if name is not None:
            updates["name"] = name
        if avatar is not None:
            updates["avatar_url"] = avatar
        statement = (
            insert(User)
            .values(**values)
            .on_conflict_do_update(index_elements=[User.email], set_=updates)
            .returning(User)
        )
        return self.database.scalars(statement).one()

    def add_session(self, session: Session) -> None:
        self.database.add(session)

    def user_for_session(self, hashed_token: str, now: datetime) -> User | None:
        statement = (
            select(User)
            .join(Session, Session.user_id == User.id)
            .where(Session.token_hash == hashed_token, Session.expires_at > now)
        )
        return self.database.scalar(statement)

    def delete_session(self, hashed_token: str) -> None:
        self.database.execute(delete(Session).where(Session.token_hash == hashed_token))

    def consume_handoff(self, hashed_token: str, now: datetime):
        return self.database.scalar(
            delete(Session)
            .where(Session.token_hash == hashed_token, Session.expires_at > now)
            .returning(Session.user_id)
        )

    def commit(self) -> None:
        self.database.commit()


def get_auth_repository(database: DatabaseSession = Depends(get_db)) -> AuthRepository:
    return AuthRepository(database)
