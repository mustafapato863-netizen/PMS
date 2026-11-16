"""Classify pre-origin conversations as legacy and widen origin constraint.

Revision ID: b3f7d2a9c6e1
Revises: a8c3e1f4d9b2
Create Date: 2026-11-16 15:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3f7d2a9c6e1"
down_revision: Union[str, Sequence[str], None] = "a8c3e1f4d9b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CHECK_NAME = "ck_ai_conversations_origin"


def _has_origin_table(bind: sa.Connection) -> bool:
    insp = sa.inspect(bind)
    if "ai_conversations" not in set(insp.get_table_names()):
        return False
    return "origin" in {col["name"] for col in insp.get_columns("ai_conversations")}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_origin_table(bind):
        return

    checks = {
        ck.get("name") for ck in sa.inspect(bind).get_check_constraints("ai_conversations") if ck.get("name")
    }
    if _CHECK_NAME in checks:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("ai_conversations") as batch_op:
                batch_op.drop_constraint(_CHECK_NAME, type_="check")
        else:
            op.drop_constraint(_CHECK_NAME, "ai_conversations", type_="check")

    # Before the origin-aware API was deployed, the workspace default also
    # captured page-assistant conversations. Their source cannot be inferred
    # safely, so classify every existing workspace row as legacy. New app
    # writes provide an explicit origin after this migration.
    bind.execute(
        sa.text("UPDATE ai_conversations SET origin = 'legacy' WHERE origin = 'workspace'")
    )

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("ai_conversations") as batch_op:
            batch_op.create_check_constraint(
                _CHECK_NAME,
                "origin IN ('workspace', 'page_assistant', 'legacy')",
            )
            batch_op.alter_column(
                "origin",
                existing_type=sa.String(length=32),
                existing_nullable=False,
                server_default=sa.text("'legacy'"),
            )
    else:
        op.create_check_constraint(
            _CHECK_NAME,
            "ai_conversations",
            "origin IN ('workspace', 'page_assistant', 'legacy')",
        )
        op.alter_column(
            "ai_conversations",
            "origin",
            existing_type=sa.String(length=32),
            existing_nullable=False,
            server_default=sa.text("'legacy'"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_origin_table(bind):
        return

    checks = {
        ck.get("name") for ck in sa.inspect(bind).get_check_constraints("ai_conversations") if ck.get("name")
    }
    if _CHECK_NAME in checks:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("ai_conversations") as batch_op:
                batch_op.drop_constraint(_CHECK_NAME, type_="check")
        else:
            op.drop_constraint(_CHECK_NAME, "ai_conversations", type_="check")

    # The older schema has no legacy category. Keep every conversation while
    # reducing only its source classification during a rollback.
    bind.execute(
        sa.text("UPDATE ai_conversations SET origin = 'workspace' WHERE origin = 'legacy'")
    )

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("ai_conversations") as batch_op:
            batch_op.create_check_constraint(
                _CHECK_NAME,
                "origin IN ('workspace', 'page_assistant')",
            )
            batch_op.alter_column(
                "origin",
                existing_type=sa.String(length=32),
                existing_nullable=False,
                server_default=sa.text("'workspace'"),
            )
    else:
        op.create_check_constraint(
            _CHECK_NAME,
            "ai_conversations",
            "origin IN ('workspace', 'page_assistant')",
        )
        op.alter_column(
            "ai_conversations",
            "origin",
            existing_type=sa.String(length=32),
            existing_nullable=False,
            server_default=sa.text("'workspace'"),
        )
