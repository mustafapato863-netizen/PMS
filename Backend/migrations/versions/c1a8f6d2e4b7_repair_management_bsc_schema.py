"""repair management BSC schema drift

Revision ID: c1a8f6d2e4b7
Revises: 9b4d6e1a2c33
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = "c1a8f6d2e4b7"
down_revision = "9b4d6e1a2c33"
branch_labels = None
depends_on = None


def _uuid_type():
    return postgresql.UUID(as_uuid=True)


def _tables(bind):
    return set(inspect(bind).get_table_names())


def _columns(bind, table_name):
    return {column["name"] for column in inspect(bind).get_columns(table_name)}


def _indexes(bind, table_name):
    return {index["name"] for index in inspect(bind).get_indexes(table_name)}


def upgrade():
    bind = op.get_bind()
    tables = _tables(bind)

    if "management_kpi_snapshots" not in tables:
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
            sa.Column("upload_batch_id", _uuid_type(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_by", sa.String(length=100), nullable=True),
            sa.CheckConstraint("performance_level IN ('Managerial', 'Corporate')", name="ck_management_kpi_snapshot_level"),
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
        tables.add("management_kpi_snapshots")

    if "management_kpi_config" in tables:
        columns = _columns(bind, "management_kpi_config")
        if "upload_batch_id" not in columns:
            op.add_column("management_kpi_config", sa.Column("upload_batch_id", _uuid_type(), nullable=True))
        indexes = _indexes(bind, "management_kpi_config")
        if "idx_management_kpi_config_batch" not in indexes:
            op.create_index("idx_management_kpi_config_batch", "management_kpi_config", ["upload_batch_id"], unique=False)

    if "management_kpi_config_history" in tables:
        columns = _columns(bind, "management_kpi_config_history")
        if "upload_batch_id" not in columns:
            op.add_column("management_kpi_config_history", sa.Column("upload_batch_id", _uuid_type(), nullable=True))
        if "source_filename" not in columns:
            op.add_column("management_kpi_config_history", sa.Column("source_filename", sa.String(length=255), nullable=True))
        indexes = _indexes(bind, "management_kpi_config_history")
        if "idx_management_kpi_config_history_batch" not in indexes:
            op.create_index("idx_management_kpi_config_history_batch", "management_kpi_config_history", ["upload_batch_id"], unique=False)

    if "management_kpi_snapshots" in tables:
        columns = _columns(bind, "management_kpi_snapshots")
        if "upload_batch_id" not in columns:
            op.add_column("management_kpi_snapshots", sa.Column("upload_batch_id", _uuid_type(), nullable=True))
        indexes = _indexes(bind, "management_kpi_snapshots")
        if "idx_management_kpi_snapshot_lookup" not in indexes:
            op.create_index(
                "idx_management_kpi_snapshot_lookup",
                "management_kpi_snapshots",
                ["team_id", "performance_level", "year", "month"],
                unique=False,
            )
        if "idx_management_kpi_snapshot_batch" not in indexes:
            op.create_index("idx_management_kpi_snapshot_batch", "management_kpi_snapshots", ["upload_batch_id"], unique=False)

    if "user_team_assignments" in tables:
        op.alter_column("user_team_assignments", "performance_level", nullable=True)


def downgrade():
    pass
