"""Adopt ai_interaction_traces and add ai_conversations and ai_turns tables.

Revision ID: c9e1a2b3d4f5
Revises: 7b056bf2c4d6
Create Date: 2026-11-06 08:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9e1a2b3d4f5"
down_revision: Union[str, Sequence[str], None] = "7b056bf2c4d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    # M1: Adopt ai_interaction_traces into Alembic and add reviewer / turn_id columns
    if "ai_interaction_traces" not in existing_tables:
        op.create_table(
            "ai_interaction_traces",
            sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
            sa.Column("turn_id", sa.String(length=64), nullable=True),
            sa.Column("user_id", sa.String(length=100), nullable=True),
            sa.Column("role", sa.String(length=50), nullable=False, server_default="Manager"),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("sanitized_prompt", sa.Text(), nullable=False),
            sa.Column("session_state", sa.JSON(), nullable=False),
            sa.Column("tool_calls", sa.JSON(), nullable=False),
            sa.Column("tool_digest", sa.JSON(), nullable=False),
            sa.Column("structured_response", sa.JSON(), nullable=False),
            sa.Column("provider_name", sa.String(length=60), nullable=False, server_default="deterministic"),
            sa.Column("model_name", sa.String(length=100), nullable=False, server_default="pms-deterministic-v1"),
            sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("non_empty_evidence", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("guardrail_triggered", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("feedback_rating", sa.String(length=20), nullable=True),
            sa.Column("feedback_reason", sa.String(length=120), nullable=True),
            sa.Column("is_distillation_eligible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("reviewer_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("reviewer_id", sa.String(length=100), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(
                "feedback_rating IS NULL OR feedback_rating IN ('up', 'down')",
                name="ck_ai_trace_feedback_rating",
            ),
        )
        op.create_index("idx_ai_trace_distillation", "ai_interaction_traces", ["is_distillation_eligible", "created_at"])
        op.create_index("idx_ai_trace_user_created", "ai_interaction_traces", ["user_id", "created_at"])
        op.create_index("ix_ai_interaction_traces_turn_id", "ai_interaction_traces", ["turn_id"])
    else:
        existing_cols = {col["name"] for col in insp.get_columns("ai_interaction_traces")}
        if "turn_id" not in existing_cols:
            op.add_column("ai_interaction_traces", sa.Column("turn_id", sa.String(length=64), nullable=True))
        if "reviewer_verified" not in existing_cols:
            op.add_column(
                "ai_interaction_traces",
                sa.Column("reviewer_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        if "reviewer_id" not in existing_cols:
            op.add_column("ai_interaction_traces", sa.Column("reviewer_id", sa.String(length=100), nullable=True))
        if "reviewed_at" not in existing_cols:
            op.add_column(
                "ai_interaction_traces",
                sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            )
        existing_ix = {ix["name"] for ix in insp.get_indexes("ai_interaction_traces")}
        if "ix_ai_interaction_traces_turn_id" not in existing_ix:
            op.create_index("ix_ai_interaction_traces_turn_id", "ai_interaction_traces", ["turn_id"])

    # M2: Create ai_conversations and ai_turns
    if "ai_conversations" not in existing_tables:
        op.create_table(
            "ai_conversations",
            sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
            sa.Column("owner_user_id", sa.String(length=100), nullable=False),
            sa.Column("owner_role", sa.String(length=64), nullable=False, server_default="Manager"),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
            sa.Column("context_version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("confirmed_context", sa.JSON(), nullable=False),
            sa.Column("pending_clarification", sa.JSON(), nullable=True),
            sa.Column("last_subject_employee_id", sa.String(length=100), nullable=True),
            sa.Column("last_subject_employee_name", sa.String(length=160), nullable=True),
            sa.Column("last_operation_kind", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "status IN ('active', 'archived', 'deleted')",
                name="ck_ai_conversations_status",
            ),
        )
        op.create_index("ix_ai_conversations_owner_user_id", "ai_conversations", ["owner_user_id"])
        op.create_index("idx_ai_conversations_owner_updated", "ai_conversations", ["owner_user_id", "updated_at"])

    if "ai_turns" not in existing_tables:
        op.create_table(
            "ai_turns",
            sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
            sa.Column(
                "conversation_id",
                sa.String(length=64),
                sa.ForeignKey("ai_conversations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("turn_index", sa.Integer(), nullable=False),
            sa.Column("client_request_id", sa.String(length=100), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
            sa.Column("claim_token", sa.String(length=64), nullable=True),
            sa.Column("processing_deadline", sa.DateTime(timezone=True), nullable=True),
            sa.Column("user_prompt_redacted", sa.Text(), nullable=False, server_default=""),
            sa.Column("validated_plan", sa.JSON(), nullable=False),
            sa.Column("evidence_summary", sa.JSON(), nullable=False),
            sa.Column("response_payload", sa.JSON(), nullable=False),
            sa.Column("outcome", sa.String(length=40), nullable=False, server_default="answer"),
            sa.Column("route_used", sa.String(length=40), nullable=False, server_default="local_rules"),
            sa.Column("provider_calls", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_ms", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("conversation_id", "client_request_id", name="uq_ai_turns_conv_client_req"),
            sa.UniqueConstraint("conversation_id", "turn_index", name="uq_ai_turns_conv_turn_index"),
            sa.CheckConstraint(
                "status IN ('pending', 'completed', 'failed', 'superseded')",
                name="ck_ai_turns_status",
            ),
        )
        op.create_index("ix_ai_turns_conversation_id", "ai_turns", ["conversation_id"])
        op.create_index("idx_ai_turns_conv_created", "ai_turns", ["conversation_id", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "ai_turns" in existing_tables:
        op.drop_table("ai_turns")
    if "ai_conversations" in existing_tables:
        op.drop_table("ai_conversations")
    if "ai_interaction_traces" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("ai_interaction_traces")}
        existing_ix = {ix["name"] for ix in insp.get_indexes("ai_interaction_traces")}
        if "ix_ai_interaction_traces_turn_id" in existing_ix:
            op.drop_index("ix_ai_interaction_traces_turn_id", table_name="ai_interaction_traces")
        for col_name in ("reviewed_at", "reviewer_id", "reviewer_verified", "turn_id"):
            if col_name in existing_cols:
                op.drop_column("ai_interaction_traces", col_name)
