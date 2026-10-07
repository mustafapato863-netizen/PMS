"""Track mandatory first-login password changes without locking existing users.

Revision ID: c8d3f6a1b205
Revises: b7e2d6a9f104
"""

from alembic import op
import sqlalchemy as sa

revision = "c8d3f6a1b205"
down_revision = "b7e2d6a9f104"
branch_labels = None
depends_on = None


def upgrade():
    # Existing accounts remain usable. The admin creation endpoint sets True
    # explicitly for new accounts; clients cannot opt out of this requirement.
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("users", "must_change_password")
