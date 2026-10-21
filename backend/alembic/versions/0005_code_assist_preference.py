"""Optional technical interview preferences; existing preparations stay normal.

Revision ID: 0005_code_assist_preference
Revises: 0004_session_preparations
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_code_assist_preference"
down_revision = "0004_session_preparations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "session_preparations",
        sa.Column("technical_interview", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "session_preparations",
        sa.Column("coding_language", sa.String(20), nullable=False, server_default="auto"),
    )


def downgrade():
    op.drop_column("session_preparations", "coding_language")
    op.drop_column("session_preparations", "technical_interview")
