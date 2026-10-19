from io import StringIO
from unittest.mock import MagicMock
from uuid import uuid4

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import DateTime
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session as DatabaseSession
from sqlalchemy.schema import CreateIndex, CreateTable
from test_user_migration import BACKEND, normalize_sql

from app.db.auth_repository import AuthRepository
from app.db.base import Base
from app.models import Session, User


def test_session_model_and_migration_metadata():
    table = Session.__table__
    assert table.metadata is Base.metadata
    assert isinstance(table.c.id.type, postgresql.UUID)
    assert isinstance(table.c.user_id.type, postgresql.UUID)
    assert next(iter(table.c.user_id.foreign_keys)).target_fullname == "users.id"
    assert next(iter(table.c.user_id.foreign_keys)).ondelete == "CASCADE"
    assert not any(column.nullable for column in table.columns)
    assert table.c.token_hash.type.length == 64
    indexes = {index.name: index for index in table.indexes}
    assert indexes["ix_sessions_token_hash"].unique
    assert list(indexes["ix_sessions_token_hash"].columns) == [table.c.token_hash]
    for column in [table.c.expires_at, table.c.created_at]:
        assert isinstance(column.type, DateTime) and column.type.timezone
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["0003_context_library"]
    revision = scripts.get_revision("0002_sessions")
    assert revision.down_revision == "0001_create_users"
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        revision.module.upgrade()
    statements = [normalize_sql(sql) for sql in output.getvalue().split(";") if sql.strip()]
    dialect = postgresql.dialect()
    assert statements[0] == normalize_sql(str(CreateTable(table).compile(dialect=dialect)))
    expected_indexes = [
        normalize_sql(str(CreateIndex(index).compile(dialect=dialect))) for index in table.indexes
    ]
    assert sorted(statements[1:]) == sorted(expected_indexes)
    output.seek(0)
    output.truncate()
    with Operations.context(context):
        revision.module.downgrade()
    assert [normalize_sql(sql) for sql in output.getvalue().split(";") if sql.strip()] == [
        "DROP INDEX ix_sessions_token_hash",
        "DROP INDEX ix_sessions_user_id",
        "DROP TABLE sessions",
    ]


def test_repository_upsert_is_postgresql_atomic_and_returns_user():
    database = MagicMock(spec=DatabaseSession)
    database.scalar.return_value = None
    expected = User(id=uuid4(), email="person@example.test")
    database.scalars.return_value.one.return_value = expected
    result = AuthRepository(database).upsert_user("person@example.test", "Person", None)
    assert result is expected
    statement = database.scalars.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (email) DO UPDATE" in sql
    assert "RETURNING users.id" in sql
    assert statement.compile().params["email"] == "person@example.test"
    assert not database.commit.called


def test_repository_updates_legacy_email_without_erasing_profile():
    database = MagicMock(spec=DatabaseSession)
    user = User(
        id=uuid4(),
        email=" PERSON@EXAMPLE.TEST ",
        name="Existing",
        avatar_url="https://example.test/existing.png",
    )
    database.scalar.return_value = user
    result = AuthRepository(database).upsert_user("person@example.test", None, None)
    assert result is user
    assert user.email == "person@example.test" and user.name == "Existing"
    assert user.avatar_url == "https://example.test/existing.png"
    assert database.flush.called and not database.scalars.called


def test_repository_session_lookup_checks_expiry_and_hash():
    from datetime import UTC, datetime

    database = MagicMock(spec=DatabaseSession)
    now = datetime.now(UTC)
    hashed = "f" * 64
    AuthRepository(database).user_for_session(hashed, now)
    statement = database.scalar.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "JOIN sessions ON sessions.user_id = users.id" in sql
    assert "sessions.token_hash =" in sql and "sessions.expires_at >" in sql
    params = statement.compile().params
    assert hashed in params.values() and now in params.values()
