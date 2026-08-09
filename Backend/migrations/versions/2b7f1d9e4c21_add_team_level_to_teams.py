"""add team level to teams

Revision ID: 2b7f1d9e4c21
Revises: ddc063e12e75
Create Date: 2026-07-08 10:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2b7f1d9e4c21"
down_revision: Union[str, Sequence[str], None] = "ddc063e12e75"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "teams",
        sa.Column("team_level", sa.String(length=20), nullable=False, server_default="employee"),
    )
    op.execute(
        """
        UPDATE teams
        SET team_level = 'management'
        WHERE lower(name) IN (
            'managerial',
            'corporate',
            'balanced_scorecard',
            'strategy_map',
            'management_overview',
            'perspective_summary'
        )
        """
    )
    op.alter_column("teams", "team_level", server_default=None)


def downgrade() -> None:
    op.drop_column("teams", "team_level")
