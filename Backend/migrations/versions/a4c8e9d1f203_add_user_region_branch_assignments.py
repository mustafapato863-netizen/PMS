"""Add explicit user region and branch scope grants.

Revision ID: a4c8e9d1f203
Revises: f2a9c61b8d43
Create Date: 2026-10-07
"""

from __future__ import annotations

import json
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4c8e9d1f203"
down_revision: Union[str, Sequence[str], None] = "f2a9c61b8d43"
branch_labels = None
depends_on = None


_BRANCH_ALIASES = {
    "dubai": ("DUBAI", "DXB"),
    "sharjah": ("SHARJAH", "SHARQA", "SHJ"),
    "ajman": ("AJMAN", "AJM"),
    "clinics": ("CLINIC", "CLINICS"),
}


def _branch_from_payload(payload) -> str | None:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            return None
    if not isinstance(payload, dict):
        return None
    raw_data = payload.get("raw_data")
    if not isinstance(raw_data, dict):
        return None
    text = " ".join(str(raw_data.get(key) or "").upper() for key in ("Branch", "Site", "Area", "Out Team", "Team"))
    matches = {
        branch
        for branch, aliases in _BRANCH_ALIASES.items()
        if any(re.search(rf"(?<![A-Z0-9]){re.escape(alias)}(?![A-Z0-9])", text) for alias in aliases)
    }
    return next(iter(matches)) if len(matches) == 1 else None


def upgrade() -> None:
    op.add_column("performance_records", sa.Column("branch_key", sa.String(length=30), nullable=True))
    op.create_index(
        "idx_perf_record_branch_scope",
        "performance_records",
        ["branch_key", "year", "month"],
    )

    # Backfill only a unique branch explicitly named in the stored source data.
    # Rows without such evidence remain NULL and are excluded from branch scopes.
    connection = op.get_bind()
    records = sa.table(
        "performance_records",
        sa.column("id", sa.UUID()),
        sa.column("year", sa.SmallInteger()),
        sa.column("record_payload", sa.JSON()),
        sa.column("branch_key", sa.String(length=30)),
    )
    pending = connection.execute(
        sa.select(records.c.id, records.c.year, records.c.record_payload)
        .where(records.c.branch_key.is_(None))
    )
    for row in pending:
        branch_key = _branch_from_payload(row.record_payload)
        if branch_key:
            connection.execute(
                records.update()
                .where(sa.and_(records.c.id == row.id, records.c.year == row.year))
                .values(branch_key=branch_key)
            )

    op.add_column("performance_plans", sa.Column("branch_key", sa.String(length=30), nullable=True))
    op.create_index("idx_performance_plan_branch_scope", "performance_plans", ["branch_key", "team_id"])
    op.add_column("actions", sa.Column("branch_key", sa.String(length=30), nullable=True))
    op.create_index("idx_action_branch_scope", "actions", ["branch_key", "team_id", "year", "month"])

    op.create_table(
        "user_region_assignments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("region_code", sa.String(length=10), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("assigned_by", sa.String(length=100), nullable=False, server_default="Admin"),
        sa.CheckConstraint("region_code IN ('UAE', 'EGY', 'Other')", name="ck_user_region_assignment_code"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "region_code", name="uq_user_region_assignment"),
    )
    op.create_index(
        "idx_user_region_assignment_scope",
        "user_region_assignments",
        ["user_id", "region_code"],
    )

    op.create_table(
        "user_branch_assignments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("branch_key", sa.String(length=30), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("assigned_by", sa.String(length=100), nullable=False, server_default="Admin"),
        sa.CheckConstraint("branch_key IN ('dubai', 'sharjah', 'ajman', 'clinics')", name="ck_user_branch_assignment_key"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "branch_key", name="uq_user_branch_assignment"),
    )
    op.create_index(
        "idx_user_branch_assignment_scope",
        "user_branch_assignments",
        ["user_id", "branch_key"],
    )


def downgrade() -> None:
    op.drop_index("idx_action_branch_scope", table_name="actions")
    op.drop_column("actions", "branch_key")
    op.drop_index("idx_performance_plan_branch_scope", table_name="performance_plans")
    op.drop_column("performance_plans", "branch_key")
    op.drop_index("idx_user_branch_assignment_scope", table_name="user_branch_assignments")
    op.drop_table("user_branch_assignments")
    op.drop_index("idx_user_region_assignment_scope", table_name="user_region_assignments")
    op.drop_table("user_region_assignments")
    op.drop_index("idx_perf_record_branch_scope", table_name="performance_records")
    op.drop_column("performance_records", "branch_key")
