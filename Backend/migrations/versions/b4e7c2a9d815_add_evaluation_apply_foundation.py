"""Add the evaluation apply foundation tables.

Revision ID: b4e7c2a9d815
Revises: f7c3a9e1d5b8
Create Date: 2026-10-10 12:00:00.000000

Expand-only job header, per-record stage evidence, and cache outbox.
Downgrade counts evaluation-apply jobs, advanced claim epochs, controls,
stage rows, and outbox rows, and raises before it drops or restores anything.
"""

from alembic import op

from services.evaluation.apply_job_schema import (
    APPLY_FOUNDATION_PREDECESSOR,
    APPLY_FOUNDATION_REVISION,
    downgrade_apply_foundation,
    upgrade_apply_foundation,
)


revision = APPLY_FOUNDATION_REVISION
down_revision = APPLY_FOUNDATION_PREDECESSOR
branch_labels = None
depends_on = None


def upgrade() -> None:
    upgrade_apply_foundation(op.get_bind())


def downgrade() -> None:
    downgrade_apply_foundation(op.get_bind())
