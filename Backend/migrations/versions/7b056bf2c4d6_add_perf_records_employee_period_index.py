"""Add composite index on performance_records (employee_id, year, month).

Revision ID: 7b056bf2c4d6
Revises: a59bcd11f746
Create Date: 2026-10-22 13:38:52.000000

Accelerates CorrectiveActionService._prefetch_performance_records and
summary_records_indexed by enabling indexed lookups on employee_id and period.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b056bf2c4d6'
down_revision: Union[str, Sequence[str], None] = 'a59bcd11f746'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_indexes = {ix["name"] for ix in insp.get_indexes("performance_records")}
    if "idx_perf_records_emp_period" not in existing_indexes:
        op.create_index(
            "idx_perf_records_emp_period",
            "performance_records",
            ["employee_id", "year", "month"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_indexes = {ix["name"] for ix in insp.get_indexes("performance_records")}
    if "idx_perf_records_emp_period" in existing_indexes:
        op.drop_index("idx_perf_records_emp_period", table_name="performance_records")
