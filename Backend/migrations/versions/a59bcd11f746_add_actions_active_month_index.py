"""Add composite index on actions (is_active, month).

Revision ID: a59bcd11f746
Revises: b4e7c2a9d815
Create Date: 2026-10-22 13:38:45.047459

Accelerates ActionRepository.list_active_for_follow_up by replacing sequential
table scans with an index scan when filtering active actions by month.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a59bcd11f746'
down_revision: Union[str, Sequence[str], None] = 'b4e7c2a9d815'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_indexes = {ix["name"] for ix in insp.get_indexes("actions")}
    if "idx_action_active_month" not in existing_indexes:
        op.create_index(
            "idx_action_active_month",
            "actions",
            ["is_active", "month"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_indexes = {ix["name"] for ix in insp.get_indexes("actions")}
    if "idx_action_active_month" in existing_indexes:
        op.drop_index("idx_action_active_month", table_name="actions")
