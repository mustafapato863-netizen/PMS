"""restructure report builder templates drafts and immutable snapshots

Revision ID: f9a3d6c8b271
Revises: e3b8c1d4f920
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f9a3d6c8b271"
down_revision = "e3b8c1d4f920"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "report_templates",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("template_key", sa.String(100), nullable=False),
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_user_id", uuid_type, nullable=True),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="private"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("definition_json", json_type, nullable=False),
        sa.Column("theme_key", sa.String(50), nullable=False, server_default="sgh_default"),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("preferred_format", sa.String(20), nullable=False, server_default="pdf"),
        sa.Column("is_system_template", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("visibility IN ('private', 'organization')", name="ck_report_template_visibility"),
        sa.CheckConstraint("preferred_format IN ('pdf', 'pptx')", name="ck_report_template_format"),
        sa.CheckConstraint("version >= 1", name="ck_report_template_version"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_key", "version", name="uq_report_template_key_version"),
    )
    op.create_index("idx_report_template_owner_updated", "report_templates", ["owner_user_id", "updated_at"])
    op.create_index("idx_report_template_type_active", "report_templates", ["report_type", "is_archived"])

    op.create_table(
        "report_drafts",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("template_id", uuid_type, nullable=True),
        sa.Column("template_version", sa.Integer(), nullable=True),
        sa.Column("owner_user_id", uuid_type, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="editing"),
        sa.Column("primary_period_month", sa.String(20), nullable=False),
        sa.Column("primary_period_year", sa.SmallInteger(), nullable=False),
        sa.Column("comparison_period_month", sa.String(20), nullable=True),
        sa.Column("comparison_period_year", sa.SmallInteger(), nullable=True),
        sa.Column("scope_json", json_type, nullable=False),
        sa.Column("definition_json", json_type, nullable=False),
        sa.Column("management_commentary_json", json_type, nullable=False),
        sa.Column("validation_json", json_type, nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_saved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('editing', 'ready', 'generated', 'archived')", name="ck_report_draft_status"),
        sa.CheckConstraint("version >= 1", name="ck_report_draft_version"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["report_templates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_report_draft_owner_updated", "report_drafts", ["owner_user_id", "updated_at"])
    op.create_index("idx_report_draft_period_type", "report_drafts", ["primary_period_year", "primary_period_month", "report_type"])

    columns = [
        sa.Column("draft_id", uuid_type, nullable=True), sa.Column("template_id", uuid_type, nullable=True),
        sa.Column("template_version", sa.Integer(), nullable=True), sa.Column("primary_period_month", sa.String(20), nullable=True),
        sa.Column("primary_period_year", sa.SmallInteger(), nullable=True), sa.Column("comparison_period_month", sa.String(20), nullable=True),
        sa.Column("comparison_period_year", sa.SmallInteger(), nullable=True),
        sa.Column("scope_json", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("final_definition_json", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("narrative_snapshot_json", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("data_snapshot_json", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("validation_json", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("safe_error_message", sa.Text(), nullable=True), sa.Column("integrity_identifier", sa.String(64), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]
    for column in columns:
        op.add_column("generated_reports", column)
    op.create_foreign_key("fk_generated_report_draft", "generated_reports", "report_drafts", ["draft_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_generated_report_template", "generated_reports", "report_templates", ["template_id"], ["id"], ondelete="SET NULL")
    op.create_unique_constraint("uq_generated_report_integrity", "generated_reports", ["integrity_identifier"])
    op.create_index("idx_generated_report_period_type", "generated_reports", ["primary_period_year", "primary_period_month", "report_type"])


def downgrade() -> None:
    op.drop_index("idx_generated_report_period_type", table_name="generated_reports")
    op.drop_constraint("uq_generated_report_integrity", "generated_reports", type_="unique")
    op.drop_constraint("fk_generated_report_template", "generated_reports", type_="foreignkey")
    op.drop_constraint("fk_generated_report_draft", "generated_reports", type_="foreignkey")
    for name in ["updated_at", "generated_at", "integrity_identifier", "safe_error_message", "validation_json", "data_snapshot_json", "narrative_snapshot_json", "final_definition_json", "scope_json", "comparison_period_year", "comparison_period_month", "primary_period_year", "primary_period_month", "template_version", "template_id", "draft_id"]:
        op.drop_column("generated_reports", name)
    op.drop_index("idx_report_draft_period_type", table_name="report_drafts")
    op.drop_index("idx_report_draft_owner_updated", table_name="report_drafts")
    op.drop_table("report_drafts")
    op.drop_index("idx_report_template_type_active", table_name="report_templates")
    op.drop_index("idx_report_template_owner_updated", table_name="report_templates")
    op.drop_table("report_templates")
