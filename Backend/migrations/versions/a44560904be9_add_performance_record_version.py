"""add_performance_record_version

Revision ID: a44560904be9
Revises: ae60ff0d2447
Create Date: 2026-06-20 21:14:23.471612

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a44560904be9'
down_revision: Union[str, Sequence[str], None] = 'ae60ff0d2447'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('performance_record_versions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('original_record_id', sa.UUID(), nullable=False),
        sa.Column('original_record_year', sa.SmallInteger(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('score', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column('grade', sa.String(length=5), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('changed_by_user_id', sa.UUID(), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('change_reason', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['changed_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['original_record_id', 'original_record_year'], ['performance_records.id', 'performance_records.year'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('original_record_id', 'version_number', name='uq_record_version')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('performance_record_versions')
