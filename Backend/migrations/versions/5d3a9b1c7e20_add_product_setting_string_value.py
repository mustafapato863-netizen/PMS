"""Restore the string-value column used by deployment-wide PMS AI settings.

Revision ID: 5d3a9b1c7e20
Revises: c2d3e4f5a6b7

The original product_settings migration created only the boolean switch. The
current ProductSetting ORM also maps value_str for AI access tiers; on an
upgraded database missing that column, even querying the boolean switch raises
a SQL error. The AI settings GET then appears Off (fail closed), while PUT fails.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "5d3a9b1c7e20"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def _has_value_str() -> bool:
    columns = sa.inspect(op.get_bind()).get_columns("product_settings")
    return any(column["name"] == "value_str" for column in columns)


def upgrade() -> None:
    # Some fresh databases created with current metadata already have the
    # column. Keep this safe for those databases as well as old installations.
    if not _has_value_str():
        op.add_column(
            "product_settings",
            sa.Column("value_str", sa.String(length=80), nullable=True),
        )


def downgrade() -> None:
    if _has_value_str():
        op.drop_column("product_settings", "value_str")
