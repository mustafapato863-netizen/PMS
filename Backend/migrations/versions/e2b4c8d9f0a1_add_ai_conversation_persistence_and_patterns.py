"""Add AI conversation title/turn persistence columns and ai_approved_patterns table.

Revision ID: e2b4c8d9f0a1
Revises: d1a8e4c6b720
Create Date: 2026-11-15 22:55:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "e2b4c8d9f0a1"
down_revision: Union[str, Sequence[str], None] = "d1a8e4c6b720"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON_COMPAT = sa.JSON().with_variant(JSONB(), "postgresql")

AI_AUDIT_OP_VALUES: tuple[str, ...] = (
    "AI_FEEDBACK_REVIEW",
    "AI_FEEDBACK_PURGE",
    "AI_FEEDBACK_DELETE",
    "AI_FEEDBACK_EXPORT_BUNDLE",
    "AI_APPROVED_PATTERN_CREATE",
    "AI_APPROVED_PATTERN_DELETE",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        has_audit_op = (
            bind.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'audit_op'")).scalar()
            is not None
        )
        if has_audit_op:
            with op.get_context().autocommit_block():
                for label in AI_AUDIT_OP_VALUES:
                    op.execute(sa.text(f"ALTER TYPE audit_op ADD VALUE IF NOT EXISTS '{label}'"))

    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "ai_conversations" in existing_tables:
        conv_cols = {col["name"] for col in insp.get_columns("ai_conversations")}
        if "title" not in conv_cols:
            op.add_column("ai_conversations", sa.Column("title", sa.String(length=200), nullable=True))

    if "ai_turns" in existing_tables:
        turn_cols = {col["name"] for col in insp.get_columns("ai_turns")}
        if "user_prompt" not in turn_cols:
            op.add_column("ai_turns", sa.Column("user_prompt", sa.Text(), nullable=True))
        if "error_message" not in turn_cols:
            op.add_column("ai_turns", sa.Column("error_message", sa.Text(), nullable=True))

    if "ai_approved_patterns" not in existing_tables:
        op.create_table(
            "ai_approved_patterns",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("source_trace_id", sa.String(length=64), nullable=True),
            sa.Column("normalized_pattern", sa.Text(), nullable=False),
            sa.Column("example_prompt_redacted", sa.Text(), nullable=False),
            sa.Column("intent", sa.String(length=64), nullable=False),
            sa.Column("operation_kind", sa.String(length=64), nullable=True),
            sa.Column("requested_parts", JSON_COMPAT, nullable=True),
            sa.Column("tool_choice", sa.String(length=80), nullable=True),
            sa.Column("metric_hint", sa.String(length=120), nullable=True),
            sa.Column("failure_category", sa.String(length=64), nullable=True),
            sa.Column("verified_against_pms", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("approved_by_user_id", sa.String(length=100), nullable=True),
            sa.Column("review_notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_ai_approved_patterns_source_trace_id", "ai_approved_patterns", ["source_trace_id"])
        op.create_index("idx_ai_approved_patterns_active_intent", "ai_approved_patterns", ["is_active", "intent"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    for table, columns in (
        ("ai_approved_patterns", ()),
        ("ai_turns", ("user_prompt", "error_message")),
        ("ai_conversations", ("title",)),
    ):
        if table not in existing_tables:
            continue
        stored = sa.Table(table, sa.MetaData(), autoload_with=bind)
        checks = [stored.c[name].is_not(None) for name in columns if name in stored.c]
        if columns and not checks:
            continue
        query = sa.select(sa.literal(1)).select_from(stored).limit(1)
        if checks:
            query = query.where(sa.or_(*checks))
        if bind.execute(query).first() is not None:
            raise RuntimeError(f"Downgrade would discard saved AI data in {table}.")

    if "ai_approved_patterns" in existing_tables:
        op.drop_index("idx_ai_approved_patterns_active_intent", table_name="ai_approved_patterns")
        op.drop_index("ix_ai_approved_patterns_source_trace_id", table_name="ai_approved_patterns")
        op.drop_table("ai_approved_patterns")

    if "ai_turns" in existing_tables:
        turn_cols = {col["name"] for col in insp.get_columns("ai_turns")}
        if "error_message" in turn_cols:
            with op.batch_alter_table("ai_turns") as batch_op:
                batch_op.drop_column("error_message")
        if "user_prompt" in turn_cols:
            with op.batch_alter_table("ai_turns") as batch_op:
                batch_op.drop_column("user_prompt")

    if "ai_conversations" in existing_tables:
        conv_cols = {col["name"] for col in insp.get_columns("ai_conversations")}
        if "title" in conv_cols:
            with op.batch_alter_table("ai_conversations") as batch_op:
                batch_op.drop_column("title")

    # PostgreSQL enum labels added to `audit_op` (AI_AUDIT_OP_VALUES) are
    # intentionally retained on downgrade: PostgreSQL does not support dropping
    # individual enum labels without recreating the type, and older versions can
    # safely ignore unused labels while preserving historical audit_log rows.
