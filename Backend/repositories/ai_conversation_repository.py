from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.models import AiConversation, AiInteractionTrace, AiTurn
from services.ai.trace_logger import ensure_trace_schema_once


class ConversationOwnershipError(PermissionError):
    """Raised when a caller attempts to access or mutate another user's conversation."""


class ConversationStaleContextError(RuntimeError):
    """Raised when a turn carries a stale context_version that conflicts with a newer committed turn."""


class TurnAlreadyInFlightError(RuntimeError):
    """Raised when a duplicate client_request_id is currently being processed by another worker."""


class AiConversationRepository:
    """Data access layer for server-owned AI conversations and idempotent turns."""

    def __init__(self, db: Session) -> None:
        self.db = db
        ensure_trace_schema_once(self.db)

    def create_conversation(
        self,
        *,
        owner_user_id: str,
        owner_role: str,
        initial_confirmed_context: dict[str, Any] | None = None,
        conversation_id: str | None = None,
    ) -> AiConversation:
        conv_id = str(conversation_id or uuid.uuid4())
        now_dt = datetime.now(timezone.utc)
        row = AiConversation(
            id=conv_id,
            owner_user_id=str(owner_user_id or "anonymous"),
            owner_role=str(owner_role or "Manager"),
            status="active",
            context_version=0,
            confirmed_context=dict(initial_confirmed_context or {}),
            pending_clarification=None,
            last_subject_employee_id=None,
            last_subject_employee_name=None,
            last_operation_kind=None,
            created_at=now_dt,
            updated_at=now_dt,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_owned_conversation(
        self,
        *,
        conversation_id: str,
        owner_user_id: str,
        include_deleted: bool = False,
    ) -> AiConversation | None:
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
        if conversation_id:
            existing = self.get_owned_conversation(
                conversation_id=conversation_id,
                owner_user_id=owner_user_id,
            )
            if existing is not None:
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
        row = self.get_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_user_id,
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
        deadline_seconds: int = 15,
    ) -> tuple[AiTurn, bool]:
        """Claim an idempotent turn slot using compare-and-swap semantics.

        Returns `(turn_row, is_already_completed)`.
        Raises `TurnAlreadyInFlightError` if another active worker owns the claim before deadline.
        """
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
            if existing.status == "completed" and existing.response_payload:
                return existing, True
            existing_deadline = existing.processing_deadline
            if existing_deadline is not None and existing_deadline.tzinfo is None:
                existing_deadline = existing_deadline.replace(tzinfo=timezone.utc)
            if existing.status == "pending" and existing_deadline and existing_deadline > now_dt:
                raise TurnAlreadyInFlightError(
                    "Duplicate client_request_id is currently in flight."
                )
            # Re-claim expired or failed turn via compare-and-swap update
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
            evidence_summary={},
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
            if raced is not None and raced.status == "completed" and raced.response_payload:
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
        """Complete a claimed turn and advance conversation context_version atomically."""
        now_dt = datetime.now(timezone.utc)
        conv = self.get_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_user_id,
        )
        if conv is None:
            raise ConversationOwnershipError("Conversation not found.")

        if expected_context_version is not None and int(conv.context_version) != int(expected_context_version):
            raise ConversationStaleContextError(
                f"Stale context_version {expected_context_version}; current is {conv.context_version}."
            )

        next_version = int(conv.context_version) + 1
        updated_conv = (
            self.db.query(AiConversation)
            .filter(
                AiConversation.id == str(conversation_id),
                AiConversation.owner_user_id == str(owner_user_id or "anonymous"),
                AiConversation.context_version == int(conv.context_version),
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
            raise ConversationStaleContextError("Concurrent turn advanced conversation context_version.")

        response_with_version = dict(response_payload)
        response_with_version["conversation_id"] = str(conversation_id)
        response_with_version["turn_id"] = str(turn_id)
        response_with_version["context_version"] = next_version

        turn_filter = [AiTurn.id == str(turn_id)]
        if claim_token:
            turn_filter.append(AiTurn.claim_token == str(claim_token))
        self.db.query(AiTurn).filter(*turn_filter).update(
            {
                AiTurn.status: "completed",
                AiTurn.validated_plan: dict(validated_plan or {}),
                AiTurn.evidence_summary: dict(evidence_summary or {}),
                AiTurn.response_payload: response_with_version,
                AiTurn.outcome: str(outcome or "answer"),
                AiTurn.route_used: str(route_used or "local_rules"),
                AiTurn.provider_calls: int(provider_calls or 0),
                AiTurn.total_ms: float(total_ms or 0.0),
                AiTurn.completed_at: now_dt,
            },
            synchronize_session=False,
        )
        self.db.commit()
        return next_version

    def cleanup_expired_conversations_and_traces(
        self,
        *,
        conversation_retention_days: int = 30,
        trace_retention_days: int = 90,
    ) -> dict[str, int]:
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
