from io import StringIO
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.models import User

BACKEND = Path(__file__).resolve().parents[1]
REVISION = "0001_create_users"


def migration_script():
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    # ScriptDirectory reads revision files only, never env.py or application settings.
    return ScriptDirectory.from_config(config)


def normalize_sql(sql: str) -> str:
    return " ".join(sql.split()).rstrip(";")


def test_first_migration_remains_root() -> None:
    scripts = migration_script()
    assert scripts.get_heads() == ["0003_context_library"]
    revision = scripts.get_revision(REVISION)
    assert revision.down_revision is None
    assert revision.dependencies is None


def test_migration_matches_postgresql_model_ddl_without_connecting(monkeypatch) -> None:
    def forbidden_connection(*args, **kwargs):
        raise AssertionError("Migration tests must never connect to a database")

    monkeypatch.setattr(Engine, "connect", forbidden_connection)
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    revision = migration_script().get_revision(REVISION)
    with Operations.context(context):
        revision.module.upgrade()

    dialect = postgresql.dialect()
    expected_table = normalize_sql(str(CreateTable(User.__table__).compile(dialect=dialect)))
    index = next(iter(User.__table__.indexes))
    expected_index = normalize_sql(str(CreateIndex(index).compile(dialect=dialect)))
    statements = [normalize_sql(sql) for sql in output.getvalue().split(";") if sql.strip()]
    assert statements == [expected_table, expected_index]
    assert "TIMESTAMP WITH TIME ZONE" in statements[0]
    assert "UUID NOT NULL" in statements[0]


def test_downgrade_reverses_table_and_index_without_connecting() -> None:
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    revision = migration_script().get_revision(REVISION)
    with Operations.context(context):
        revision.module.downgrade()
    statements = [normalize_sql(sql) for sql in output.getvalue().split(";") if sql.strip()]
    assert statements == ["DROP INDEX ix_users_email", "DROP TABLE users"]
