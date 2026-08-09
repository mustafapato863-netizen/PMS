"""add management kpi config tables

Revision ID: 7c2f3b8a9d11
Revises: 1ae79fba19aa
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "7c2f3b8a9d11"
down_revision = "1ae79fba19aa"
branch_labels = None
depends_on = None


def _uuid_type():
    return postgresql.UUID(as_uuid=True)


LEVEL_CHECK = "performance_level IN ('Managerial', 'Corporate')"
SCOPE_CHECK = (
    "((position_name IS NOT NULL AND employee_identifier IS NULL) OR "
    "(position_name IS NULL AND employee_identifier IS NOT NULL))"
)


def upgrade():
    op.create_table(
        "management_kpi_config",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("team_id", _uuid_type(), nullable=False),
        sa.Column("performance_level", sa.String(length=20), nullable=False),
        sa.Column("position_name", sa.String(length=255), nullable=True),
        sa.Column("employee_identifier", sa.String(length=50), nullable=True),
        sa.Column("perspective_key", sa.String(length=50), nullable=False),
        sa.Column("kpi_key", sa.String(length=100), nullable=False),
        sa.Column("kpi_label", sa.String(length=255), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("weight", sa.Numeric(7, 4), nullable=False),
        sa.Column("target_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("target_unit", sa.String(length=20), nullable=True),
        sa.Column("display_order", sa.SmallInteger(), nullable=False),
        sa.Column("effective_month", sa.String(length=20), nullable=False),
        sa.Column("effective_year", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_by", sa.String(length=100), nullable=True),
        sa.CheckConstraint(LEVEL_CHECK, name="ck_management_kpi_config_level"),
        sa.CheckConstraint(SCOPE_CHECK, name="ck_management_kpi_config_scope"),
        sa.CheckConstraint("weight > 0", name="ck_management_kpi_config_weight_positive"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "team_id",
            "performance_level",
            "effective_month",
            "effective_year",
            "position_name",
            "employee_identifier",
            "kpi_key",
            name="uq_management_kpi_config_scope",
        ),
    )
    op.create_index(
        "idx_management_kpi_config_lookup",
        "management_kpi_config",
        ["team_id", "performance_level", "effective_year", "effective_month", "position_name", "employee_identifier"],
        unique=False,
    )

    op.create_table(
        "management_kpi_config_history",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("config_id", _uuid_type(), nullable=True),
        sa.Column("team_id", _uuid_type(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("old_values", sa.JSON(), nullable=True),
        sa.Column("new_values", sa.JSON(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("changed_by", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_management_kpi_config_history_team",
        "management_kpi_config_history",
        ["team_id", "changed_at"],
        unique=False,
    )

    op.create_table(
        "management_kpi_snapshots",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("team_id", _uuid_type(), nullable=False),
        sa.Column("employee_identifier", sa.String(length=50), nullable=False),
        sa.Column("employee_name", sa.String(length=255), nullable=False),
        sa.Column("position_name", sa.String(length=255), nullable=False),
        sa.Column("performance_level", sa.String(length=20), nullable=False),
        sa.Column("month", sa.String(length=20), nullable=False),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("perspective_key", sa.String(length=50), nullable=False),
        sa.Column("kpi_key", sa.String(length=100), nullable=False),
        sa.Column("kpi_label", sa.String(length=255), nullable=False),
        sa.Column("actual_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_by", sa.String(length=100), nullable=True),
        sa.CheckConstraint(LEVEL_CHECK, name="ck_management_kpi_snapshot_level"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "team_id",
            "employee_identifier",
            "performance_level",
            "month",
            "year",
            "kpi_key",
            name="uq_management_kpi_snapshot_scope",
        ),
    )
    op.create_index(
        "idx_management_kpi_snapshot_lookup",
        "management_kpi_snapshots",
        ["team_id", "performance_level", "year", "month"],
        unique=False,
    )


def downgrade():
    op.drop_index("idx_management_kpi_snapshot_lookup", table_name="management_kpi_snapshots")
    op.drop_table("management_kpi_snapshots")

    op.drop_index("idx_management_kpi_config_history_team", table_name="management_kpi_config_history")
    op.drop_table("management_kpi_config_history")

    op.drop_index("idx_management_kpi_config_lookup", table_name="management_kpi_config")
    op.drop_table("management_kpi_config")
