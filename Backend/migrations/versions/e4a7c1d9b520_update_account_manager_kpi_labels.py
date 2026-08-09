"""update Account Manager KPI labels

Revision ID: e4a7c1d9b520
Revises: d9f4b6a1c230
Create Date: 2026-07-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4a7c1d9b520"
down_revision: Union[str, Sequence[str], None] = "d9f4b6a1c230"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LABELS = {
    "am_requests": ("Requests Delivery Rate", "Requests"),
    "am_modifications": ("Modification Rate", "Modifications"),
}


def _update_labels(*, use_new_labels: bool) -> None:
    bind = op.get_bind()
    for kpi_key, (new_label, old_label) in LABELS.items():
        bind.execute(
            sa.text(
                """
                UPDATE team_kpi_config
                SET kpi_label = :label
                WHERE performance_level = 'Employee'
                  AND position_name = 'Account Manager'
                  AND kpi_key = :kpi_key
                  AND team_id IN (
                    SELECT id
                    FROM teams
                    WHERE team_level = 'employee'
                      AND lower(COALESCE(display_name, name)) = 'marketing'
                  )
                """
            ),
            {
                "label": new_label if use_new_labels else old_label,
                "kpi_key": kpi_key,
            },
        )


def upgrade() -> None:
    _update_labels(use_new_labels=True)


def downgrade() -> None:
    _update_labels(use_new_labels=False)
