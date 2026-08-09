"""add planning action title

Revision ID: ab31d8e7c4f2
Revises: f9a3d6c8b271
"""

from alembic import op
import sqlalchemy as sa


revision = "ab31d8e7c4f2"
down_revision = "f9a3d6c8b271"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("actions", sa.Column("plan_title", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("actions", "plan_title")
