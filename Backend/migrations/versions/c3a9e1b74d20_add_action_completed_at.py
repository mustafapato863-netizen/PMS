"""add completed_at to actions

Revision ID: c3a9e1b74d20
Revises: a6d4e8f1c220
Create Date: 2026-09-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3a9e1b74d20"
down_revision: Union[str, Sequence[str], None] = "a6d4e8f1c220"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "actions",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("actions", "completed_at")
