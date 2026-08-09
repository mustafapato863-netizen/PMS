"""add source domain markers and team level fallback

Revision ID: a2d91f4c1b7e
Revises: 2b7f1d9e4c21
Create Date: 2026-07-08 11:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2d91f4c1b7e"
down_revision: Union[str, Sequence[str], None] = "2b7f1d9e4c21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE teams SET team_level = 'employee' WHERE team_level IS NULL")
    op.add_column(
        "upload_batches",
        sa.Column(
            "source_domain",
            sa.String(length=40),
            nullable=False,
            server_default="employee_performance",
        ),
    )
    op.add_column(
        "team_onboarding_drafts",
        sa.Column(
            "source_domain",
            sa.String(length=40),
            nullable=False,
            server_default="employee_performance",
        ),
    )
    op.alter_column("upload_batches", "source_domain", server_default=None)
    op.alter_column("team_onboarding_drafts", "source_domain", server_default=None)


def downgrade() -> None:
    op.drop_column("team_onboarding_drafts", "source_domain")
    op.drop_column("upload_batches", "source_domain")
