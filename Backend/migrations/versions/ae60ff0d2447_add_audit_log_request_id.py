"""add_audit_log_request_id

Revision ID: ae60ff0d2447
Revises: b31d52f82865
Create Date: 2026-06-20 21:02:41.588117

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ae60ff0d2447'
down_revision: Union[str, Sequence[str], None] = 'b31d52f82865'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('audit_log', sa.Column('request_id', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('audit_log', 'request_id')
