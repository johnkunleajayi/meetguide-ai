from uuid import UUID

from sqlalchemy import DateTime, Text, update
from sqlalchemy.dialects import postgresql

from app.db.base import Base
from app.models import User


def test_user_registered_with_shared_metadata() -> None:
    assert User.__table__.metadata is Base.metadata
    assert Base.metadata.tables["users"] is User.__table__
    assert set(Base.metadata.tables) == {"users"}
    assert set(User.__table__.columns.keys()) == {
        "id",
        "email",
        "name",
        "avatar_url",
        "created_at",
        "updated_at",
    }


def test_uuid_primary_key_and_insert_default() -> None:
    column = User.__table__.c.id
    assert list(User.__table__.primary_key.columns) == [column]
    assert isinstance(column.type, postgresql.UUID)
    assert column.type.as_uuid
    assert not column.nullable
    first = column.default.arg(None)
    second = column.default.arg(None)
    assert isinstance(first, UUID)
    assert first.version == 4
    assert first != second


def test_email_is_required_and_uniquely_indexed() -> None:
    table = User.__table__
    assert not table.c.email.nullable
    assert table.c.email.type.length == 320
    indexes = list(table.indexes)
    assert len(indexes) == 1
    assert indexes[0].name == "ix_users_email"
    assert indexes[0].unique
    assert list(indexes[0].columns) == [table.c.email]


def test_profile_fields_optional() -> None:
    user = User(email="person@example.test")
    assert user.name is None
    assert user.avatar_url is None
    assert User.__table__.c.name.nullable
    assert User.__table__.c.avatar_url.nullable
    assert isinstance(User.__table__.c.avatar_url.type, Text)


def test_timestamps_are_timezone_aware_and_database_defaulted() -> None:
    for name in ("created_at", "updated_at"):
        column = User.__table__.c[name]
        assert isinstance(column.type, DateTime)
        assert column.type.timezone
        assert not column.nullable
        assert str(column.server_default.arg) == "now()"


def test_orm_updates_updated_at_without_overwriting_created_at() -> None:
    statement = update(User).where(User.email == "person@example.test").values(name="Person")
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "updated_at=now()" in sql
    assert "created_at=" not in sql
