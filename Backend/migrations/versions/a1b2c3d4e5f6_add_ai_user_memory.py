"""add ai user memory table

Revision ID: a1b2c3d4e5f6
Revises: e1b6c9d4a870, a6d4e8f1c220, f2a9c61b8d43
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = ("e1b6c9d4a870", "a6d4e8f1c220", "f2a9c61b8d43")
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_user_memory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("preferences", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("query_patterns", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("interaction_summary", sa.Text(), nullable=True),
        sa.Column("feedback_signals", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_ai_user_memory_user_id", "ai_user_memory", ["user_id"])
    op.create_index("idx_ai_user_memory_last_accessed", "ai_user_memory", ["last_accessed_at"])


def downgrade():
    op.drop_index("idx_ai_user_memory_last_accessed", table_name="ai_user_memory")
    op.drop_index("idx_ai_user_memory_user_id", table_name="ai_user_memory")
    op.drop_table("ai_user_memory")
