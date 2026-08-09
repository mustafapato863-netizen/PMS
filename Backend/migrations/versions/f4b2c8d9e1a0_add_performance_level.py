"""add performance level business dimension

Revision ID: f4b2c8d9e1a0
Revises: addlinktonotifs
"""

from alembic import op
import sqlalchemy as sa


revision = "f4b2c8d9e1a0"
down_revision = "addlinktonotifs"
branch_labels = None
depends_on = None


LEVEL_CHECK = "performance_level IN ('Employee', 'Managerial', 'Corporate')"


def upgrade():
    with op.batch_alter_table("employees") as batch_op:
        batch_op.add_column(sa.Column("performance_level", sa.String(20), nullable=False, server_default="Employee"))
        batch_op.create_check_constraint("ck_employee_performance_level", LEVEL_CHECK)

    with op.batch_alter_table("performance_records") as batch_op:
        batch_op.add_column(sa.Column("performance_level", sa.String(20), nullable=False, server_default="Employee"))
        batch_op.create_check_constraint("ck_performance_record_level", LEVEL_CHECK)

    with op.batch_alter_table("team_kpi_config") as batch_op:
        batch_op.add_column(sa.Column("performance_level", sa.String(20), nullable=False, server_default="Employee"))
        batch_op.drop_constraint("uq_kpi_team_key", type_="unique")
        batch_op.create_unique_constraint("uq_kpi_team_level_key", ["team_id", "performance_level", "kpi_key"])
        batch_op.create_check_constraint("ck_team_kpi_performance_level", LEVEL_CHECK)


def downgrade():
    with op.batch_alter_table("team_kpi_config") as batch_op:
        batch_op.drop_constraint("ck_team_kpi_performance_level", type_="check")
        batch_op.drop_constraint("uq_kpi_team_level_key", type_="unique")
        batch_op.create_unique_constraint("uq_kpi_team_key", ["team_id", "kpi_key"])
        batch_op.drop_column("performance_level")

    with op.batch_alter_table("performance_records") as batch_op:
        batch_op.drop_constraint("ck_performance_record_level", type_="check")
        batch_op.drop_column("performance_level")

    with op.batch_alter_table("employees") as batch_op:
        batch_op.drop_constraint("ck_employee_performance_level", type_="check")
        batch_op.drop_column("performance_level")
