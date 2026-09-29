"""allow team-level key actions in the actions table

Revision ID: d7a4c8b1e650
Revises: c3a9e1b74d20
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d7a4c8b1e650"
down_revision: Union[str, Sequence[str], None] = "c3a9e1b74d20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE action_type ADD VALUE IF NOT EXISTS 'Team Action'")


def downgrade() -> None:
    # PostgreSQL enum labels are intentionally retained on downgrade. Older
    # application versions can ignore this extra label, while removing it may
    # destroy the ability to read team actions already saved with the value.
    pass
