"""Create private user-owned context documents and retrieval chunks.

Revision ID: 0003_context_library
Revises: 0002_sessions
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_context_library"
down_revision = "0002_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "context_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("context_type", sa.String(64), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(32), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("processing_version", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('ready', 'deleting')", name="ck_document_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_context_documents_user_id", "context_documents", ["user_id"])
    op.create_table(
        "context_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["context_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "position", name="uq_context_chunk_position"),
    )
    op.create_index("ix_context_chunks_document_id", "context_chunks", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_context_chunks_document_id", table_name="context_chunks")
    op.drop_table("context_chunks")
    op.drop_index("ix_context_documents_user_id", table_name="context_documents")
    op.drop_table("context_documents")
