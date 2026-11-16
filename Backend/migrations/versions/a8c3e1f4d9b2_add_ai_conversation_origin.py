"""Add origin column and owner/origin index to ai_conversations.

Revision ID: a8c3e1f4d9b2
Revises: f4d2e8a9c1b3
Create Date: 2026-11-16 12:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8c3e1f4d9b2"
down_revision: Union[str, Sequence[str], None] = "f4d2e8a9c1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CHECK_NAME = "ck_ai_conversations_origin"
_INDEX_NAME = "idx_ai_conversations_owner_origin_updated"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())
    if "ai_conversations" not in existing_tables:
        return

    conv_cols = {col["name"] for col in insp.get_columns("ai_conversations")}
    if "origin" not in conv_cols:
        op.add_column(
            "ai_conversations",
            sa.Column(
                "origin",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'workspace'"),
            ),
        )

    existing_checks = {
        ck.get("name") for ck in insp.get_check_constraints("ai_conversations") if ck.get("name")
    }
    if _CHECK_NAME not in existing_checks:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("ai_conversations") as batch_op:
                batch_op.create_check_constraint(
                    _CHECK_NAME,
                    "origin IN ('workspace', 'page_assistant')",
                )
        else:
            op.create_check_constraint(
                _CHECK_NAME,
                "ai_conversations",
                "origin IN ('workspace', 'page_assistant')",
            )

    existing_indexes = {
        idx.get("name") for idx in insp.get_indexes("ai_conversations") if idx.get("name")
    }
    if _INDEX_NAME not in existing_indexes:
        op.create_index(
            _INDEX_NAME,
            "ai_conversations",
            ["owner_user_id", "origin", "updated_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())
    if "ai_conversations" not in existing_tables:
        return

    existing_indexes = {
        idx.get("name") for idx in insp.get_indexes("ai_conversations") if idx.get("name")
    }
    if _INDEX_NAME in existing_indexes:
        op.drop_index(_INDEX_NAME, table_name="ai_conversations")

    existing_checks = {
        ck.get("name") for ck in insp.get_check_constraints("ai_conversations") if ck.get("name")
    }
    conv_cols = {col["name"] for col in insp.get_columns("ai_conversations")}

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("ai_conversations") as batch_op:
            if _CHECK_NAME in existing_checks:
                batch_op.drop_constraint(_CHECK_NAME, type_="check")
            if "origin" in conv_cols:
                batch_op.drop_column("origin")
    else:
        if _CHECK_NAME in existing_checks:
            op.drop_constraint(_CHECK_NAME, "ai_conversations", type_="check")
        if "origin" in conv_cols:
            op.drop_column("ai_conversations", "origin")
