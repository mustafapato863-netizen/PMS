"""Add the administrator switch that turns PMS AI on or off.

Revision ID: d1a8e4c6b720
Revises: c9e1a2b3d4f5
Create Date: 2026-11-08 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1a8e4c6b720"
down_revision: Union[str, Sequence[str], None] = "c9e1a2b3d4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AI_SETTING_KEY = "ai_enabled"


def upgrade() -> None:
    op.create_table(
        "product_settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )
    product_settings = sa.table(
        "product_settings",
        sa.column("key", sa.String),
        sa.column("enabled", sa.Boolean),
    )
    op.bulk_insert(product_settings, [{"key": AI_SETTING_KEY, "enabled": False}])


def downgrade() -> None:
    op.drop_table("product_settings")
