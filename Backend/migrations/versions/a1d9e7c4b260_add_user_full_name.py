"""add an independent full name to users

Revision ID: a1d9e7c4b260
Revises: 6c36225c6f30
Create Date: 2026-07-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1d9e7c4b260"
down_revision: Union[str, Sequence[str], None] = "6c36225c6f30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(length=255), nullable=True))
    op.execute(
        """
        UPDATE users AS user_account
        SET full_name = COALESCE(
            (
                SELECT NULLIF(BTRIM(employee.name), '')
                FROM employees AS employee
                WHERE employee.employee_id = user_account.employee_id
                LIMIT 1
            ),
            NULLIF(
                INITCAP(
                    REGEXP_REPLACE(BTRIM(user_account.username), '[._\\-\\s]+', ' ', 'g')
                ),
                ''
            ),
            'User'
        )
        """
    )
    op.alter_column("users", "full_name", existing_type=sa.String(length=255), nullable=False)


def downgrade() -> None:
    op.drop_column("users", "full_name")
