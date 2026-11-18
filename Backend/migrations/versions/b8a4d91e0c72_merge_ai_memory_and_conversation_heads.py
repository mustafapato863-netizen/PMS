"""Merge AI user-memory and legacy conversation-origin migration branches.

Revision ID: b8a4d91e0c72
Revises: a1b2c3d4e5f6, b3f7d2a9c6e1

This merge revision is deliberately schema-neutral. Both parents must run
before the application considers the database upgraded to the single head.
It does not rewrite either already-deployed migration.
"""

from __future__ import annotations

from typing import Sequence, Union

revision: str = "b8a4d91e0c72"
down_revision: Union[str, Sequence[str], None] = ("a1b2c3d4e5f6", "b3f7d2a9c6e1")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
