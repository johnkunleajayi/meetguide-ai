"""Session preparation and explicit document selection; no existing context backfill.

Revision ID: 0004_session_preparations
Revises: 0003_context_library
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_session_preparations"
down_revision = "0003_context_library"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_document_owner", "context_documents", ["id", "user_id"])
    op.create_table(
        "session_preparations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("objective", sa.String(600), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_preparation_owner"),
    )
    op.create_index("ix_session_preparations_user_id", "session_preparations", ["user_id"])
    op.create_table(
        "preparation_documents",
        sa.Column("preparation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("context_role", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["preparation_id", "user_id"],
            ["session_preparations.id", "session_preparations.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "user_id"],
            ["context_documents.id", "context_documents.user_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "active_preparations",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("preparation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["preparation_id", "user_id"],
            ["session_preparations.id", "session_preparations.user_id"],
            ondelete="CASCADE",
        ),
    )


def downgrade():
    op.drop_table("active_preparations")
    op.drop_table("preparation_documents")
    op.drop_index("ix_session_preparations_user_id", "session_preparations")
    op.drop_table("session_preparations")
    op.drop_constraint("uq_document_owner", "context_documents", type_="unique")
