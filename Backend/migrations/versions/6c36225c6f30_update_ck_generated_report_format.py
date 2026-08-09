"""update_ck_generated_report_format

Revision ID: 6c36225c6f30
Revises: e8c1a7d4b920
Create Date: 2026-07-23 18:38:56.395391

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6c36225c6f30'
down_revision: Union[str, Sequence[str], None] = 'e8c1a7d4b920'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("ck_generated_report_format", "generated_reports", type_="check")
    op.create_check_constraint(
        "ck_generated_report_format",
        "generated_reports",
        "output_format IN ('excel', 'pdf', 'pptx')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_generated_report_format", "generated_reports", type_="check")
    op.create_check_constraint(
        "ck_generated_report_format",
        "generated_reports",
        "output_format IN ('excel')",
    )
