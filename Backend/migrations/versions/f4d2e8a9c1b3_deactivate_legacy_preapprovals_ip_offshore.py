"""Deactivate legacy empty Pre-Approvals IP Offshore team when Pre-Approvals IP is active.

Revision ID: f4d2e8a9c1b3
Revises: e2b4c8d9f0a1
Create Date: 2026-11-16 09:19:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4d2e8a9c1b3"
down_revision: Union[str, Sequence[str], None] = "e2b4c8d9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())
    if "teams" not in existing_tables:
        return

    has_active_ip = bind.execute(
        sa.text(
            "SELECT 1 FROM teams "
            "WHERE name = :ip_name AND team_level = :lvl AND region = :reg AND is_active = :active "
            "LIMIT 1"
        ),
        {"ip_name": "Pre-Approvals IP", "lvl": "employee", "reg": "EGY", "active": True},
    ).first()
    if not has_active_ip:
        return

    offshore_rows = bind.execute(
        sa.text(
            "SELECT id FROM teams "
            "WHERE name = :off_name AND team_level = :lvl AND region = :reg AND is_active = :active"
        ),
        {"off_name": "Pre-Approvals IP Offshore", "lvl": "employee", "reg": "EGY", "active": True},
    ).fetchall()

    for (offshore_id,) in offshore_rows:
        if "performance_records" in existing_tables:
            has_records = bind.execute(
                sa.text("SELECT 1 FROM performance_records WHERE team_id = :tid LIMIT 1"),
                {"tid": offshore_id},
            ).first()
            if has_records:
                continue
        bind.execute(
            sa.text("UPDATE teams SET is_active = :inactive WHERE id = :tid"),
            {"inactive": False, "tid": offshore_id},
        )


def downgrade() -> None:
    # Legacy Pre-Approvals IP Offshore deactivation is intentionally preserved on downgrade
    # when Pre-Approvals IP is active so unused legacy rows do not reappear in catalogs.
    pass
