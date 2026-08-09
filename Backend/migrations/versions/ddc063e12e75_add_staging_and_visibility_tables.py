"""add staging and visibility tables

Revision ID: ddc063e12e75
Revises: b8f2d4a9c731
Create Date: 2026-07-07 16:01:39.716826
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "ddc063e12e75"
down_revision: Union[str, Sequence[str], None] = "b8f2d4a9c731"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "upload_batches",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("reporting_month", sa.String(length=20), nullable=False),
        sa.Column("reporting_year", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="quarantined"),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "raw_performance_staging",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("batch_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.String(length=100), nullable=False),
        sa.Column("employee_name", sa.String(length=255), nullable=False),
        sa.Column("performance_level", sa.String(length=30), nullable=False, server_default="Employee"),
        sa.Column("raw_row_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validation_status", sa.String(length=30), nullable=False, server_default="pending_config"),
        sa.Column("quarantine_reason", sa.Text(), nullable=True),
        sa.Column("staged_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["upload_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "team_batch_statuses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("batch_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["upload_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "team_id", name="uq_batch_team_status"),
    )
    op.create_table(
        "team_workspace_visibility",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("workspace_key", sa.String(length=30), nullable=False),
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("dashboard_mode", sa.String(length=50), nullable=False, server_default="roster"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "workspace_key", name="uq_team_workspace"),
    )


def downgrade() -> None:
    op.drop_table("team_workspace_visibility")
    op.drop_table("team_batch_statuses")
    op.drop_table("raw_performance_staging")
    op.drop_table("upload_batches")
