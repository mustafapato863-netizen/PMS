"""Add persisted per-user function access grants.

Revision ID: f2a9c61b8d43
Revises: a6d4e8f1c220, e8c1a7d4b920
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f2a9c61b8d43"
down_revision = ("a6d4e8f1c220", "e8c1a7d4b920")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_function_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("function_name", sa.String(length=50), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("assigned_by", sa.String(length=100), server_default="Admin", nullable=False),
        sa.CheckConstraint(
            "function_name IN ('Call Center', 'RCM', 'Pre-Approvals', 'Marketing')",
            name="ck_user_function_assignment_name",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "function_name", name="uq_user_function_assignment"),
    )
    op.create_index(
        "idx_user_function_assignment_scope",
        "user_function_assignments",
        ["user_id", "function_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_user_function_assignment_scope", table_name="user_function_assignments")
    op.drop_table("user_function_assignments")
