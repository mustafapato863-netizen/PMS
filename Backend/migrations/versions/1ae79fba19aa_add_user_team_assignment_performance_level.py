"""add performance level to user team assignments

Revision ID: 1ae79fba19aa
Revises: f4b2c8d9e1a0
"""

from alembic import op
import sqlalchemy as sa


revision = "1ae79fba19aa"
down_revision = "f4b2c8d9e1a0"
branch_labels = None
depends_on = None


LEVEL_CHECK = "performance_level IS NULL OR performance_level IN ('Employee', 'Managerial', 'Corporate')"


def upgrade():
    with op.batch_alter_table("user_team_assignments") as batch_op:
        batch_op.add_column(sa.Column("performance_level", sa.String(20), nullable=True))
        batch_op.create_check_constraint("ck_user_team_assignment_performance_level", LEVEL_CHECK)
        batch_op.create_index(
            "idx_user_team_assignment_scope",
            ["user_id", "team_id", "performance_level"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("user_team_assignments") as batch_op:
        batch_op.drop_index("idx_user_team_assignment_scope")
        batch_op.drop_constraint("ck_user_team_assignment_performance_level", type_="check")
        batch_op.drop_column("performance_level")
