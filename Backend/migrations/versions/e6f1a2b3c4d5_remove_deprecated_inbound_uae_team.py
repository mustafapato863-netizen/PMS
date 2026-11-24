"""Permanently remove deprecated Inbound UAE team and all related data.

Revision ID: e6f1a2b3c4d5
Revises: d2a1b8c90e41
Create Date: 2026-11-24 17:10:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from services.deprecated_team_purge import purge_deprecated_inbound_uae


revision: str = "e6f1a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = "d2a1b8c90e41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    purge_deprecated_inbound_uae(op.get_bind())


def downgrade() -> None:
    # Deleted data for the deprecated Inbound UAE team is intentionally not restored.
    pass
