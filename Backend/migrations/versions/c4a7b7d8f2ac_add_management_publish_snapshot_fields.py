"""add management publish snapshot fields

Revision ID: c4a7b7d8f2ac
Revises: b8f2d4a9c731
Create Date: 2026-07-08 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4a7b7d8f2ac"
down_revision: Union[str, Sequence[str], None] = "b8f2d4a9c731"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("team_configuration_versions", sa.Column("preview_snapshot", sa.JSON(), nullable=True))
    op.add_column("team_configuration_versions", sa.Column("total_weight", sa.Numeric(7, 4), nullable=True))
    op.add_column("team_configuration_versions", sa.Column("overall_score", sa.Numeric(10, 2), nullable=True))
    op.add_column(
        "team_configuration_versions",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("team_configuration_versions", "is_active")
    op.drop_column("team_configuration_versions", "overall_score")
    op.drop_column("team_configuration_versions", "total_weight")
    op.drop_column("team_configuration_versions", "preview_snapshot")
