from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from models.models import AiConversation, AiInteractionTrace, AiTurn
from services.ai.trace_logger import ensure_trace_schema_once


class ConversationOwnershipError(PermissionError):
    """Raised when a caller attempts to access or mutate another user's conversation."""


class ConversationDeletedError(ConversationOwnershipError):
    """Raised when a caller sends a request for a conversation that was already deleted/reset."""


class ConversationStaleContextError(RuntimeError):
    """Raised when a turn carries a stale context_version or superseded claim token."""


class RequestIdReuseConflictError(ConversationStaleContextError):
    """Raised when a client_request_id is reused with different prompt or filter parameters."""


class TurnAlreadyInFlightError(RuntimeError):
    """Raised when a duplicate client_request_id is currently being processed by another worker."""


class ConversationMigrationUnavailableError(RuntimeError):
    """Raised when conversation persistence tables are not yet migrated in production."""


def compute_request_fingerprint(
    *,
    prompt: str,
    clarification_choice_id: str | None = None,
    answer_detail: str | None = None,
    session_filters: dict[str, Any] | None = None,
) -> str:
    canonical = {
        "prompt": " ".join((prompt or "").strip().split()).casefold(),
        "clarification_choice_id": str(clarification_choice_id or "").strip(),
        "answer_detail": str(answer_detail or "auto").strip().casefold(),
    }
    raw = json.dumps(canonical, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_scope_fingerprint(scope: dict[str, Any] | None) -> str:
    s = scope or {}
    canonical = {
        "user_id": str(s.get("user_id") or "anonymous"),
        "role": str(s.get("role") or "Manager"),
        "is_active": bool(s.get("is_active", True)),
        "has_unrestricted_team_access": bool(s.get("has_unrestricted_team_access", False)),
        "accessible_teams": sorted(str(x) for x in (s.get("accessible_teams") or s.get("allowed_teams") or [])),
        "accessible_functions": sorted(str(x) for x in (s.get("accessible_functions") or s.get("allowed_functions") or [])),
        "accessible_branches": sorted(str(x) for x in (s.get("accessible_branches") or s.get("allowed_branches") or [])),
        "accessible_regions": sorted(str(x) for x in (s.get("accessible_regions") or s.get("allowed_regions") or [])),
        "allowed_performance_levels": sorted(str(x) for x in (s.get("allowed_performance_levels") or [])),
    }
    raw = json.dumps(canonical, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AiConversationRepository:
    """Data access layer for server-owned AI conversations and idempotent turns."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._schema_ready_cache: bool | None = None
        ensure_trace_schema_once(self.db)

    def is_schema_ready(self) -> bool:
        if self._schema_ready_cache is not None:
            return self._schema_ready_cache
        try:
            bind = self.db.get_bind()
            insp = sa_inspect(bind)
            tables = set(insp.get_table_names())
            ready = "ai_conversations" in tables and "ai_turns" in tables
            self._schema_ready_cache = ready
            return ready
        except Exception:
            return False

    def _require_schema_ready(self) -> None:
        if not self.is_schema_ready():
            self.db.rollback()
            raise ConversationMigrationUnavailableError(
                "AI conversation persistence schema is not yet migrated. Run Alembic upgrade c9e1a2b3d4f5."
            )

    def create_conversation(
        self,
        *,
        owner_user_id: str,
        owner_role: str,
        initial_confirmed_context: dict[str, Any] | None = None,
        conversation_id: str | None = None,
    ) -> AiConversation:
        self._require_schema_ready()
        conv_id = str(conversation_id or uuid.uuid4())
        now_dt = datetime.now(timezone.utc)
        row = AiConversation(
            id=conv_id,
            owner_user_id=str(owner_user_id or "anonymous"),
            owner_role=str(owner_role or "Manager"),
            status="active",
            context_version=1,
            confirmed_context=dict(initial_confirmed_context or {}),
            pending_clarification=None,
            last_subject_employee_id=None,
            last_subject_employee_name=None,
            last_operation_kind=None,
            created_at=now_dt,
            updated_at=now_dt,
        )
        try:
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
            return row
        except (OperationalError, ProgrammingError) as exc:
            self.db.rollback()
            raise ConversationMigrationUnavailableError(
                "AI conversation persistence schema is not yet migrated."
            ) from exc

    def get_owned_conversation(
        self,
        *,
        conversation_id: str,
        owner_user_id: str,
        include_deleted: bool = False,
    ) -> AiConversation | None:
        self._require_schema_ready()
        row = (
            self.db.query(AiConversation)
            .filter(AiConversation.id == str(conversation_id))
            .first()
        )
        if row is None:
            return None
        if str(row.owner_user_id) != str(owner_user_id or "anonymous"):
            raise ConversationOwnershipError("Conversation not found for current user.")
        if not include_deleted and row.status == "deleted":
            return None
        return row

    def get_or_create_owned_conversation(
        self,
        *,
        conversation_id: str | None,
        owner_user_id: str,
        owner_role: str,
        initial_confirmed_context: dict[str, Any] | None = None,
    ) -> AiConversation:
        self._require_schema_ready()
        if conversation_id:
            existing = self.get_owned_conversation(
                conversation_id=conversation_id,
                owner_user_id=owner_user_id,
                include_deleted=True,
            )
            if existing is not None:
                if existing.status == "deleted":
                    raise ConversationDeletedError("Conversation has been reset or deleted.")
                return existing
        return self.create_conversation(
            owner_user_id=owner_user_id,
            owner_role=owner_role,
            initial_confirmed_context=initial_confirmed_context,
            conversation_id=conversation_id,
        )

    def soft_delete_conversation(
        self,
        *,
        conversation_id: str,
        owner_user_id: str,
    ) -> bool:
        self._require_schema_ready()
        row = self.get_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_user_id,
            include_deleted=False,
        )
        if row is None:
            return False
        now_dt = datetime.now(timezone.utc)
        row.status = "deleted"
        row.deleted_at = now_dt
        row.updated_at = now_dt
        row.confirmed_context = {}
        row.pending_clarification = None
        row.last_subject_employee_id = None
        row.last_subject_employee_name = None
        row.last_operation_kind = None
        self.db.commit()
        return True

    def claim_or_get_turn(
        self,
        *,
        conversation_id: str,
        client_request_id: str,
        user_prompt_redacted: str,
        request_fingerprint: str = "",
        scope_fingerprint: str = "",
        eval_id: str = "",
        deadline_seconds: int = 15,
    ) -> tuple[AiTurn, bool]:
        """Claim an idempotent turn slot using compare-and-swap semantics.

        Returns `(turn_row, is_already_completed)`.
        Raises:
        - `RequestIdReuseConflictError` if the same `client_request_id` is reused with different input.
        - `TurnAlreadyInFlightError` if another active worker owns the claim before deadline.
        """
        self._require_schema_ready()
        now_dt = datetime.now(timezone.utc)
        deadline_dt = now_dt + timedelta(seconds=max(5, deadline_seconds))
        claim_tok = str(uuid.uuid4())

        existing = (
            self.db.query(AiTurn)
            .filter(
                AiTurn.conversation_id == str(conversation_id),
                AiTurn.client_request_id == str(client_request_id),
            )
            .first()
        )
        if existing is not None:
            ev_sum = dict(existing.evidence_summary or {})
            stored_req_fp = str(ev_sum.get("request_fingerprint") or "")
            if stored_req_fp and request_fingerprint and stored_req_fp != request_fingerprint:
                raise RequestIdReuseConflictError(
                    "client_request_id was already used with a different prompt or filter context."
                )

            was_completed = existing.status == "completed"
            if was_completed and existing.response_payload:
                stored_scope_fp = str(ev_sum.get("scope_fingerprint") or "")
                stored_eval_id = str(ev_sum.get("eval_id") or "")
                scope_unchanged = (not stored_scope_fp) or (not scope_fingerprint) or (stored_scope_fp == scope_fingerprint)
                eval_unchanged = (not stored_eval_id) or (not eval_id) or (stored_eval_id == eval_id)
                if scope_unchanged and eval_unchanged:
                    return existing, True
                # Scope or published data changed since original execution -> re-claim to recompute!

            existing_deadline = existing.processing_deadline
            if existing_deadline is not None and existing_deadline.tzinfo is None:
                existing_deadline = existing_deadline.replace(tzinfo=timezone.utc)
            if existing.status == "pending" and existing_deadline and existing_deadline > now_dt:
                raise TurnAlreadyInFlightError(
                    "Duplicate client_request_id is currently in flight."
                )
            # Re-claim expired, failed, or invalidated turn via compare-and-swap update
            ev_sum["request_fingerprint"] = request_fingerprint
            ev_sum["scope_fingerprint"] = scope_fingerprint
            ev_sum["eval_id"] = eval_id
            ev_sum["reclaimed_from_completed"] = bool(was_completed)
            updated = (
                self.db.query(AiTurn)
                .filter(
                    AiTurn.id == existing.id,
                    AiTurn.claim_token == existing.claim_token,
                )
                .update(
                    {
                        AiTurn.status: "pending",
                        AiTurn.claim_token: claim_tok,
                        AiTurn.processing_deadline: deadline_dt,
                        AiTurn.evidence_summary: ev_sum,
                    },
                    synchronize_session=False,
                )
            )
            self.db.commit()
            if updated == 0:
                raise TurnAlreadyInFlightError(
                    "Turn claim was acquired by another concurrent request."
                )
            self.db.refresh(existing)
            return existing, False

        max_idx_row = (
            self.db.query(AiTurn.turn_index)
            .filter(AiTurn.conversation_id == str(conversation_id))
            .order_by(AiTurn.turn_index.desc())
            .first()
        )
        next_idx = (int(max_idx_row[0]) + 1) if max_idx_row and max_idx_row[0] is not None else 1

        turn = AiTurn(
            id=str(uuid.uuid4()),
            conversation_id=str(conversation_id),
            turn_index=next_idx,
            client_request_id=str(client_request_id),
            status="pending",
            claim_token=claim_tok,
            processing_deadline=deadline_dt,
            user_prompt_redacted=user_prompt_redacted,
            validated_plan={},
            evidence_summary={
                "request_fingerprint": request_fingerprint,
                "scope_fingerprint": scope_fingerprint,
                "eval_id": eval_id,
            },
            response_payload={},
            outcome="answer",
            route_used="local_rules",
            provider_calls=0,
            total_ms=0.0,
            created_at=now_dt,
        )
        try:
            self.db.add(turn)
            self.db.commit()
            self.db.refresh(turn)
            return turn, False
        except IntegrityError:
            self.db.rollback()
            raced = (
                self.db.query(AiTurn)
                .filter(
                    AiTurn.conversation_id == str(conversation_id),
                    AiTurn.client_request_id == str(client_request_id),
                )
                .first()
            )
            if raced is not None:
                ev_raced = dict(raced.evidence_summary or {})
                stored_req_fp = str(ev_raced.get("request_fingerprint") or "")
                if stored_req_fp and request_fingerprint and stored_req_fp != request_fingerprint:
                    raise RequestIdReuseConflictError(
                        "client_request_id was already used with a different prompt or filter context."
                    )
                if raced.status == "completed" and raced.response_payload:
                    return raced, True
            raise TurnAlreadyInFlightError(
                "Duplicate client_request_id is currently in flight."
            )

    def complete_turn_and_advance_context(
        self,
        *,
        conversation_id: str,
        owner_user_id: str,
        expected_context_version: int | None,
        turn_id: str,
        claim_token: str | None,
        validated_plan: dict[str, Any],
        evidence_summary: dict[str, Any],
        response_payload: dict[str, Any],
        outcome: str,
        route_used: str,
        provider_calls: int,
        total_ms: float,
        new_confirmed_context: dict[str, Any],
        pending_clarification: dict[str, Any] | None,
        last_subject_employee_id: str | None,
        last_subject_employee_name: str | None,
        last_operation_kind: str | None,
    ) -> int:
        """Complete a claimed turn and advance conversation context_version atomically.

        Rejects stale `expected_context_version` or superseded `claim_token` without mutating
        either the turn or the conversation.
        """
        self._require_schema_ready()
        now_dt = datetime.now(timezone.utc)
        conv = self.get_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_user_id,
            include_deleted=True,
        )
        if conv is None:
            raise ConversationOwnershipError("Conversation not found.")
        if conv.status == "deleted":
            raise ConversationDeletedError("Conversation was deleted before turn completion.")

        target_version = (
            int(expected_context_version)
            if expected_context_version is not None
            else int(conv.context_version)
        )
        if int(conv.context_version) != target_version:
            raise ConversationStaleContextError(
                f"Stale context_version {target_version}; current is {conv.context_version}."
            )

        next_version = target_version + 1
        response_with_version = dict(response_payload)
        response_with_version["conversation_id"] = str(conversation_id)
        response_with_version["turn_id"] = str(turn_id)
        response_with_version["context_version"] = next_version

        existing_turn = self.db.query(AiTurn).filter(AiTurn.id == str(turn_id)).first()
        merged_ev_summary = dict((existing_turn.evidence_summary if existing_turn else None) or {})
        merged_ev_summary.update(dict(evidence_summary or {}))

        turn_filter = [
            AiTurn.id == str(turn_id),
            AiTurn.conversation_id == str(conversation_id),
            AiTurn.status == "pending",
        ]
        if claim_token is not None:
            turn_filter.append(AiTurn.claim_token == str(claim_token))

        updated_turn = (
            self.db.query(AiTurn)
            .filter(*turn_filter)
            .update(
                {
                    AiTurn.status: "completed",
                    AiTurn.validated_plan: dict(validated_plan or {}),
                    AiTurn.evidence_summary: merged_ev_summary,
                    AiTurn.response_payload: response_with_version,
                    AiTurn.outcome: str(outcome or "answer"),
                    AiTurn.route_used: str(route_used or "local_rules"),
                    AiTurn.provider_calls: int(provider_calls or 0),
                    AiTurn.total_ms: float(total_ms or 0.0),
                    AiTurn.completed_at: now_dt,
                },
                synchronize_session=False,
            )
        )
        if updated_turn == 0:
            self.db.rollback()
            raise ConversationStaleContextError(
                "Turn claim token was superseded or turn was already completed by another worker."
            )

        updated_conv = (
            self.db.query(AiConversation)
            .filter(
                AiConversation.id == str(conversation_id),
                AiConversation.owner_user_id == str(owner_user_id or "anonymous"),
                AiConversation.status == "active",
                AiConversation.context_version == target_version,
            )
            .update(
                {
                    AiConversation.context_version: next_version,
                    AiConversation.confirmed_context: dict(new_confirmed_context or {}),
                    AiConversation.pending_clarification: pending_clarification,
                    AiConversation.last_subject_employee_id: last_subject_employee_id,
                    AiConversation.last_subject_employee_name: last_subject_employee_name,
                    AiConversation.last_operation_kind: last_operation_kind,
                    AiConversation.updated_at: now_dt,
                },
                synchronize_session=False,
            )
        )
        if updated_conv == 0:
            self.db.rollback()
            raise ConversationStaleContextError(
                f"Concurrent turn advanced conversation context_version from {target_version}."
            )

        self.db.commit()
        return next_version

    def cleanup_expired_conversations_and_traces(
        self,
        *,
        conversation_retention_days: int = 30,
        trace_retention_days: int = 90,
    ) -> dict[str, int]:
        self._require_schema_ready()
        now_dt = datetime.now(timezone.utc)
        conv_cutoff = now_dt - timedelta(days=max(1, conversation_retention_days))
        trace_cutoff = now_dt - timedelta(days=max(1, trace_retention_days))

        deleted_convs = (
            self.db.query(AiConversation)
            .filter(AiConversation.updated_at < conv_cutoff)
            .delete(synchronize_session=False)
        )
        deleted_traces = (
            self.db.query(AiInteractionTrace)
            .filter(
                AiInteractionTrace.created_at < trace_cutoff,
                AiInteractionTrace.reviewer_verified.is_(False),
            )
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return {
            "deleted_conversations": int(deleted_convs or 0),
            "deleted_traces": int(deleted_traces or 0),
        }
