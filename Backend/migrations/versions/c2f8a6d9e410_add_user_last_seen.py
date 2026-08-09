"""add durable last-seen time to users

Revision ID: c2f8a6d9e410
Revises: a1d9e7c4b260
Create Date: 2026-07-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2f8a6d9e410"
down_revision: Union[str, Sequence[str], None] = "a1d9e7c4b260"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE users SET last_seen_at = last_login WHERE last_login IS NOT NULL")


def downgrade() -> None:
    op.drop_column("users", "last_seen_at")
