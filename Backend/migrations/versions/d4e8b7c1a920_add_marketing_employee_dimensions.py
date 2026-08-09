"""add Marketing employee position dimensions

Revision ID: d4e8b7c1a920
Revises: c1a8f6d2e4b7
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "d4e8b7c1a920"
down_revision = "c1a8f6d2e4b7"
branch_labels = None
depends_on = None


def _columns(bind, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(bind).get_columns(table_name)}


def _unique_constraints(bind, table_name: str) -> set[str]:
    return {
        constraint["name"]
        for constraint in inspect(bind).get_unique_constraints(table_name)
        if constraint.get("name")
    }


def _indexes(bind, table_name: str) -> set[str]:
    return {index["name"] for index in inspect(bind).get_indexes(table_name)}


def upgrade():
    bind = op.get_bind()

    employee_columns = _columns(bind, "employees")
    if "position_name" not in employee_columns:
        op.add_column("employees", sa.Column("position_name", sa.String(length=255), nullable=True))

    performance_columns = _columns(bind, "performance_records")
    if "position_name" not in performance_columns:
        op.add_column("performance_records", sa.Column("position_name", sa.String(length=255), nullable=True))
    if "region" not in performance_columns:
        op.add_column("performance_records", sa.Column("region", sa.String(length=10), nullable=True))

    config_columns = _columns(bind, "team_kpi_config")
    constraints = _unique_constraints(bind, "team_kpi_config")
    indexes = _indexes(bind, "team_kpi_config")
    with op.batch_alter_table("team_kpi_config") as batch_op:
        if "position_name" not in config_columns:
            batch_op.add_column(
                sa.Column("position_name", sa.String(length=255), nullable=False, server_default=""),
            )
        if "perspective" not in config_columns:
            batch_op.add_column(sa.Column("perspective", sa.String(length=50), nullable=True))
        if "uq_kpi_team_level_key" in constraints:
            batch_op.drop_constraint("uq_kpi_team_level_key", type_="unique")
        if "uq_kpi_team_level_position_key" not in constraints:
            batch_op.create_unique_constraint(
                "uq_kpi_team_level_position_key",
                ["team_id", "performance_level", "position_name", "kpi_key"],
            )
        if "idx_kpi_config_team_level" in indexes:
            batch_op.drop_index("idx_kpi_config_team_level")
        batch_op.create_index(
            "idx_kpi_config_team_level",
            ["team_id", "performance_level", "position_name"],
            unique=False,
        )

    with op.batch_alter_table("kpi_values") as batch_op:
        batch_op.alter_column(
            "contribution",
            existing_type=sa.Numeric(6, 2),
            type_=sa.Numeric(7, 4),
            existing_nullable=False,
        )


def downgrade():
    with op.batch_alter_table("kpi_values") as batch_op:
        batch_op.alter_column(
            "contribution",
            existing_type=sa.Numeric(7, 4),
            type_=sa.Numeric(6, 2),
            existing_nullable=False,
        )

    constraints = _unique_constraints(op.get_bind(), "team_kpi_config")
    indexes = _indexes(op.get_bind(), "team_kpi_config")
    with op.batch_alter_table("team_kpi_config") as batch_op:
        if "idx_kpi_config_team_level" in indexes:
            batch_op.drop_index("idx_kpi_config_team_level")
        batch_op.create_index(
            "idx_kpi_config_team_level",
            ["team_id", "performance_level"],
            unique=False,
        )
        if "uq_kpi_team_level_position_key" in constraints:
            batch_op.drop_constraint("uq_kpi_team_level_position_key", type_="unique")
        if "uq_kpi_team_level_key" not in constraints:
            batch_op.create_unique_constraint(
                "uq_kpi_team_level_key",
                ["team_id", "performance_level", "kpi_key"],
            )
        batch_op.drop_column("perspective")
        batch_op.drop_column("position_name")
    op.drop_column("performance_records", "region")
    op.drop_column("performance_records", "position_name")
    op.drop_column("employees", "position_name")
