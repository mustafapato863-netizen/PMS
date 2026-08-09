"""add display name to teams

Revision ID: b1f3d8e7a901
Revises: c4a7b7d8f2ac
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1f3d8e7a901"
down_revision: Union[str, Sequence[str], None] = "c4a7b7d8f2ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("display_name", sa.String(length=255), nullable=True))
    op.execute("UPDATE teams SET display_name = name WHERE display_name IS NULL")


def downgrade() -> None:
    op.drop_column("teams", "display_name")
