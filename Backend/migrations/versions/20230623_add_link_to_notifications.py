"""add_link_to_notifications

Revision ID: addlinktonotifs
Revises: e0c0df4e622b
Create Date: 2026-06-23 13:48:40.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "addlinktonotifs"
down_revision = "e0c0df4e622b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("link", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("notifications", "link")
