"""Adopt ai_interaction_traces and add ai_conversations and ai_turns tables.

Safe Rollback Procedure:
------------------------
1. Application-level rollback (recommended, zero data loss):
   Set `PMS_AI_CONVERSATION_STATE_ENABLED=false` in the environment to revert the
   orchestrator to stateless session context without dropping persisted conversation
   turns, audit traces, or Admin review metadata.
2. Schema-level downgrade (`alembic downgrade 7b056bf2c4d6`):
   - Never drops `ai_interaction_traces` or its columns (`turn_id`, `reviewer_verified`,
     `reviewer_id`, `reviewed_at`), because those columns may have existed prior to
     adoption and are backward-compatible (`nullable=True` or `server_default=false`).
   - Refuses to drop `ai_turns` or `ai_conversations` when persisted conversation turns
     or trace review/turn metadata exist (unless `PMS_ALLOW_DESTRUCTIVE_AI_DOWNGRADE=1`
     is explicitly set for disposable test environments).

Revision ID: c9e1a2b3d4f5
Revises: 7b056bf2c4d6
Create Date: 2026-11-06 08:45:00.000000
"""
from __future__ import annotations

import os
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9e1a2b3d4f5"
down_revision: Union[str, Sequence[str], None] = "7b056bf2c4d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TRACE_REQUIRED_BASE_COLUMNS: dict[str, tuple[tuple[str, ...], bool]] = {
    # col_name: (allowed_type_substrings, allow_nullable)
    "id": (("uuid", "char", "varchar", "text", "string"), False),
    "user_id": (("char", "varchar", "text", "string"), True),
    "role": (("char", "varchar", "text", "string"), False),
    "prompt": (("text", "varchar", "char", "string"), False),
    "sanitized_prompt": (("text", "varchar", "char", "string"), False),
    "session_state": (("json", "text"), False),
    "tool_calls": (("json", "text"), False),
    "tool_digest": (("json", "text"), False),
    "structured_response": (("json", "text"), False),
    "provider_name": (("char", "varchar", "text", "string"), False),
    "model_name": (("char", "varchar", "text", "string"), False),
    "latency_ms": (("int", "integer", "bigint", "smallint"), False),
    "non_empty_evidence": (("bool", "boolean", "int", "integer", "smallint"), False),
    "guardrail_triggered": (("bool", "boolean", "int", "integer", "smallint"), False),
    "feedback_rating": (("char", "varchar", "text", "string"), True),
    "feedback_reason": (("char", "varchar", "text", "string"), True),
    "is_distillation_eligible": (("bool", "boolean", "int", "integer", "smallint"), False),
    "created_at": (("timestamp", "datetime", "date", "text", "char", "varchar"), False),
    "updated_at": (("timestamp", "datetime", "date", "text", "char", "varchar"), False),
}

_TRACE_OPTIONAL_V2_COLUMNS: dict[str, tuple[str, ...]] = {
    "turn_id": ("char", "varchar", "text", "string"),
    "reviewer_verified": ("bool", "boolean", "int", "integer", "smallint"),
    "reviewer_id": ("char", "varchar", "text", "string"),
    "reviewed_at": ("timestamp", "datetime", "date", "text", "char", "varchar"),
}

_CONVERSATION_REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "id": ("char", "varchar", "text", "string"),
    "owner_user_id": ("char", "varchar", "text", "string"),
    "owner_role": ("char", "varchar", "text", "string"),
    "status": ("char", "varchar", "text", "string"),
    "context_version": ("int", "integer", "bigint", "smallint"),
    "confirmed_context": ("json", "text"),
    "pending_clarification": ("json", "text"),
    "last_subject_employee_id": ("char", "varchar", "text", "string"),
    "last_subject_employee_name": ("char", "varchar", "text", "string"),
    "last_operation_kind": ("char", "varchar", "text", "string"),
    "created_at": ("timestamp", "datetime", "date", "text", "char", "varchar"),
    "updated_at": ("timestamp", "datetime", "date", "text", "char", "varchar"),
    "deleted_at": ("timestamp", "datetime", "date", "text", "char", "varchar"),
}

_TURN_REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "id": ("char", "varchar", "text", "string"),
    "conversation_id": ("char", "varchar", "text", "string"),
    "turn_index": ("int", "integer", "bigint", "smallint"),
    "client_request_id": ("char", "varchar", "text", "string"),
    "status": ("char", "varchar", "text", "string"),
    "claim_token": ("char", "varchar", "text", "string"),
    "processing_deadline": ("timestamp", "datetime", "date", "text", "char", "varchar"),
    "user_prompt_redacted": ("text", "varchar", "char", "string"),
    "validated_plan": ("json", "text"),
    "evidence_summary": ("json", "text"),
    "response_payload": ("json", "text"),
    "outcome": ("char", "varchar", "text", "string"),
    "route_used": ("char", "varchar", "text", "string"),
    "provider_calls": ("int", "integer", "bigint", "smallint"),
    "total_ms": ("float", "real", "double", "numeric", "decimal"),
    "created_at": ("timestamp", "datetime", "date", "text", "char", "varchar"),
    "completed_at": ("timestamp", "datetime", "date", "text", "char", "varchar"),
}


def _type_matches(col_type: Any, allowed_tokens: tuple[str, ...], dialect_name: str) -> bool:
    type_str = str(col_type).strip().casefold()
    if dialect_name == "postgresql" and allowed_tokens == ("bool", "boolean", "int", "integer", "smallint"):
        return any(tok in type_str for tok in ("bool", "boolean"))
    return any(tok in type_str for tok in allowed_tokens)


def _validate_existing_trace_table(insp: sa.Inspector, dialect_name: str) -> set[str]:
    cols = {col["name"]: col for col in insp.get_columns("ai_interaction_traces")}
    missing = sorted(set(_TRACE_REQUIRED_BASE_COLUMNS.keys()) - set(cols.keys()))
    if missing:
        raise RuntimeError(
            "Incompatible existing schema for 'ai_interaction_traces': missing required base columns "
            f"{missing}. Refusing to adopt partial or incompatible table."
        )

    incompatible_types: list[str] = []
    for col_name, (allowed_types, _allow_nullable) in _TRACE_REQUIRED_BASE_COLUMNS.items():
        col_info = cols[col_name]
        if not _type_matches(col_info["type"], allowed_types, dialect_name):
            incompatible_types.append(f"{col_name} (found {col_info['type']!s}, expected {allowed_types})")

    for opt_col, allowed_types in _TRACE_OPTIONAL_V2_COLUMNS.items():
        if opt_col in cols and not _type_matches(cols[opt_col]["type"], allowed_types, dialect_name):
            incompatible_types.append(f"{opt_col} (found {cols[opt_col]['type']!s}, expected {allowed_types})")

    if incompatible_types:
        raise RuntimeError(
            "Incompatible existing schema for 'ai_interaction_traces': column type mismatch on "
            f"{', '.join(incompatible_types)}."
        )

    pk = insp.get_pk_constraint("ai_interaction_traces") or {}
    pk_cols = list(pk.get("constrained_columns") or [])
    if pk_cols != ["id"]:
        raise RuntimeError(
            "Incompatible existing schema for 'ai_interaction_traces': primary key must be ['id'], "
            f"found {pk_cols}."
        )

    return set(cols.keys())


def _validate_existing_conversations_table(insp: sa.Inspector, dialect_name: str) -> None:
    cols = {col["name"]: col for col in insp.get_columns("ai_conversations")}
    missing = sorted(set(_CONVERSATION_REQUIRED_COLUMNS.keys()) - set(cols.keys()))
    if missing:
        raise RuntimeError(
            f"Incompatible existing schema for 'ai_conversations': missing required columns {missing}."
        )
    for col_name, allowed_types in _CONVERSATION_REQUIRED_COLUMNS.items():
        if not _type_matches(cols[col_name]["type"], allowed_types, dialect_name):
            raise RuntimeError(
                f"Incompatible existing schema for 'ai_conversations': column '{col_name}' has incompatible type {cols[col_name]['type']!s}."
            )
    pk = insp.get_pk_constraint("ai_conversations") or {}
    if list(pk.get("constrained_columns") or []) != ["id"]:
        raise RuntimeError("Incompatible existing schema for 'ai_conversations': primary key must be ['id'].")


def _validate_existing_turns_table(insp: sa.Inspector, dialect_name: str) -> None:
    cols = {col["name"]: col for col in insp.get_columns("ai_turns")}
    missing = sorted(set(_TURN_REQUIRED_COLUMNS.keys()) - set(cols.keys()))
    if missing:
        raise RuntimeError(
            f"Incompatible existing schema for 'ai_turns': missing required columns {missing}."
        )
    for col_name, allowed_types in _TURN_REQUIRED_COLUMNS.items():
        if not _type_matches(cols[col_name]["type"], allowed_types, dialect_name):
            raise RuntimeError(
                f"Incompatible existing schema for 'ai_turns': column '{col_name}' has incompatible type {cols[col_name]['type']!s}."
            )
    pk = insp.get_pk_constraint("ai_turns") or {}
    if list(pk.get("constrained_columns") or []) != ["id"]:
        raise RuntimeError("Incompatible existing schema for 'ai_turns': primary key must be ['id'].")
    uqs = [ tuple(sorted(u.get("column_names") or [])) for u in insp.get_unique_constraints("ai_turns") ]
    required_uqs = [
        tuple(sorted(("conversation_id", "client_request_id"))),
        tuple(sorted(("conversation_id", "turn_index"))),
    ]
    for req_uq in required_uqs:
        if req_uq not in uqs:
            raise RuntimeError(
                f"Incompatible existing schema for 'ai_turns': missing unique constraint on {req_uq}."
            )


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    dialect_name = bind.dialect.name
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
        existing_cols = _validate_existing_trace_table(insp, dialect_name)
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
        if "idx_ai_trace_distillation" not in existing_ix:
            op.create_index("idx_ai_trace_distillation", "ai_interaction_traces", ["is_distillation_eligible", "created_at"])
        if "idx_ai_trace_user_created" not in existing_ix:
            op.create_index("idx_ai_trace_user_created", "ai_interaction_traces", ["user_id", "created_at"])
        if "ix_ai_interaction_traces_turn_id" not in existing_ix:
            op.create_index("ix_ai_interaction_traces_turn_id", "ai_interaction_traces", ["turn_id"])

    # M2: Create or validate ai_conversations and ai_turns
    if "ai_conversations" not in existing_tables:
        op.create_table(
            "ai_conversations",
            sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
            sa.Column("owner_user_id", sa.String(length=100), nullable=False),
            sa.Column("owner_role", sa.String(length=64), nullable=False, server_default="Manager"),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
            sa.Column("context_version", sa.Integer(), nullable=False, server_default="1"),
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
    else:
        _validate_existing_conversations_table(insp, dialect_name)
        existing_conv_ix = {ix["name"] for ix in insp.get_indexes("ai_conversations")}
        if "ix_ai_conversations_owner_user_id" not in existing_conv_ix:
            op.create_index("ix_ai_conversations_owner_user_id", "ai_conversations", ["owner_user_id"])
        if "idx_ai_conversations_owner_updated" not in existing_conv_ix:
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
    else:
        _validate_existing_turns_table(insp, dialect_name)
        existing_turn_ix = {ix["name"] for ix in insp.get_indexes("ai_turns")}
        if "ix_ai_turns_conversation_id" not in existing_turn_ix:
            op.create_index("ix_ai_turns_conversation_id", "ai_turns", ["conversation_id"])
        if "idx_ai_turns_conv_created" not in existing_turn_ix:
            op.create_index("idx_ai_turns_conv_created", "ai_turns", ["conversation_id", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())
    allow_destructive = os.environ.get("PMS_ALLOW_DESTRUCTIVE_AI_DOWNGRADE", "").strip().casefold() in (
        "1",
        "true",
        "yes",
    )

    if not allow_destructive:
        if "ai_turns" in existing_tables:
            turn_count = int(bind.execute(sa.text("SELECT COUNT(*) FROM ai_turns")).scalar() or 0)
            if turn_count > 0:
                raise RuntimeError(
                    f"Refusing destructive downgrade: 'ai_turns' contains {turn_count} persisted turn(s). "
                    "Use the safe application rollback procedure (PMS_AI_CONVERSATION_STATE_ENABLED=false) instead."
                )
        if "ai_conversations" in existing_tables:
            conv_count = int(bind.execute(sa.text("SELECT COUNT(*) FROM ai_conversations")).scalar() or 0)
            if conv_count > 0:
                raise RuntimeError(
                    f"Refusing destructive downgrade: 'ai_conversations' contains {conv_count} persisted conversation(s). "
                    "Use the safe application rollback procedure (PMS_AI_CONVERSATION_STATE_ENABLED=false) instead."
                )
        if "ai_interaction_traces" in existing_tables:
            trace_cols = {col["name"] for col in insp.get_columns("ai_interaction_traces")}
            if {"reviewer_verified", "reviewer_id", "reviewed_at", "turn_id"}.issubset(trace_cols):
                bool_true_sql = "true" if bind.dialect.name == "postgresql" else "1"
                reviewed_count = int(
                    bind.execute(
                        sa.text(
                            "SELECT COUNT(*) FROM ai_interaction_traces "
                            f"WHERE reviewer_verified = {bool_true_sql} OR reviewer_id IS NOT NULL "
                            "OR reviewed_at IS NOT NULL OR turn_id IS NOT NULL"
                        )
                    ).scalar()
                    or 0
                )
                if reviewed_count > 0:
                    raise RuntimeError(
                        f"Refusing destructive downgrade: 'ai_interaction_traces' contains {reviewed_count} reviewed/linked trace row(s). "
                        "Use the safe application rollback procedure (PMS_AI_CONVERSATION_STATE_ENABLED=false) instead."
                    )

    if "ai_turns" in existing_tables:
        op.drop_table("ai_turns")
    if "ai_conversations" in existing_tables:
        op.drop_table("ai_conversations")
    # Note: Do NOT drop columns from ai_interaction_traces during downgrade.
    # Those columns (turn_id, reviewer_verified, reviewer_id, reviewed_at) may have existed
    # prior to migration adoption on runtime-initialized schemas and are backward-compatible.
