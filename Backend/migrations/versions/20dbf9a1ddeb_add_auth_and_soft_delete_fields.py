"""add_auth_and_soft_delete_fields

Revision ID: 20dbf9a1ddeb
Revises: 975c072657f1
Create Date: 2026-06-20 20:40:02.743293

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20dbf9a1ddeb'
down_revision: Union[str, Sequence[str], None] = '975c072657f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create role_permissions table
    op.create_table('role_permissions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('permission', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('role', 'permission', name='uq_role_permission')
    )
    # Add auth columns to users table
    op.add_column('users', sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))
    # Add soft delete column to actions table
    op.add_column('actions', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('actions', 'is_active')
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_login_attempts')
    op.drop_table('role_permissions')
