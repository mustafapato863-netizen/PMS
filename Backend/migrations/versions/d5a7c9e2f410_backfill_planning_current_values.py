"""backfill planning current values from the first measured baseline

Revision ID: d5a7c9e2f410
Revises: ab31d8e7c4f2
"""

from alembic import op


revision = "d5a7c9e2f410"
down_revision = "ab31d8e7c4f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table_name in ("performance_plans", "plan_objectives", "plan_kpis"):
        op.execute(
            f"UPDATE {table_name} "
            "SET current_value = baseline_value "
            "WHERE current_value IS NULL"
        )


def downgrade() -> None:
    # This is a corrective data migration. The former NULL rows cannot be
    # distinguished safely from legitimate baseline-equals-current rows.
    pass
