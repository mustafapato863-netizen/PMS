"""create team onboarding drafts

Revision ID: 0402585d70d0
Revises: c1a8f6d2e4b7
Create Date: 2026-07-06 21:54:54.550758
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0402585d70d0"
down_revision: Union[str, Sequence[str], None] = "c1a8f6d2e4b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_onboarding_drafts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("team_identity", sa.JSON(), nullable=True),
        sa.Column("workbook_metadata", sa.JSON(), nullable=True),
        sa.Column("selected_sheet", sa.String(length=100), nullable=True),
        sa.Column("header_row", sa.Integer(), nullable=True),
        sa.Column("core_column_mappings", sa.JSON(), nullable=True),
        sa.Column("kpis", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("team_onboarding_drafts")
