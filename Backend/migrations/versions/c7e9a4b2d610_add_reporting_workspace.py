"""add reporting workspace persistence

Revision ID: c7e9a4b2d610
Revises: 7f3c9a1d2e40
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c7e9a4b2d610"
down_revision = "7f3c9a1d2e40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "generated_reports",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("report_type", sa.String(length=50), nullable=False),
        sa.Column("scope_summary", sa.String(length=255), nullable=False),
        sa.Column("period_label", sa.String(length=100), nullable=False),
        sa.Column("created_by_user_id", uuid_type, nullable=True),
        sa.Column("created_by_name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("output_format", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("file_data", sa.LargeBinary(), nullable=False),
        sa.Column("configuration", json_type, nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("warning", sa.Text(), nullable=True),
        sa.CheckConstraint("output_format IN ('excel', 'pdf', 'pptx')", name="ck_generated_report_format"),
        sa.CheckConstraint("status IN ('ready', 'failed')", name="ck_generated_report_status"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_generated_report_owner_created", "generated_reports", ["created_by_user_id", "created_at"])

    op.create_table(
        "saved_report_templates",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("report_type", sa.String(length=50), nullable=False),
        sa.Column("configuration", json_type, nullable=False),
        sa.Column("included_sections", json_type, nullable=False),
        sa.Column("preferred_format", sa.String(length=20), nullable=False),
        sa.Column("owner_user_id", uuid_type, nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("preferred_format IN ('excel', 'pdf', 'pptx')", name="ck_saved_report_template_format"),
        sa.CheckConstraint("visibility IN ('private')", name="ck_saved_report_template_visibility"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "name", name="uq_saved_report_template_owner_name"),
    )
    op.create_index("idx_saved_report_template_owner_updated", "saved_report_templates", ["owner_user_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("idx_saved_report_template_owner_updated", table_name="saved_report_templates")
    op.drop_table("saved_report_templates")
    op.drop_index("idx_generated_report_owner_created", table_name="generated_reports")
    op.drop_table("generated_reports")
