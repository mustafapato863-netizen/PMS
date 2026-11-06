from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from models.ai_schemas import (
    AiClarificationPrompt,
    AiConversationContextPayload,
    ConfirmedQueryContext,
    SessionFilterContext,
)
from models.models import AiConversation, AiTurn, User
from repositories.ai_conversation_repository import (
    AiConversationRepository,
    ConversationDeletedError,
    ConversationMigrationUnavailableError,
    ConversationOwnershipError,
    ConversationStaleContextError,
    RequestIdReuseConflictError,
    TurnAlreadyInFlightError,
    compute_request_fingerprint,
    compute_scope_fingerprint,
)
from services.ai.catalog import evaluation_cache_identity
from services.ai.trace_logger import sanitize_prompt_for_router_training
from services.cache_invalidation_service import CacheInvalidationService
from services.insights_service import InsightAccessError

ConversationAccessError = ConversationOwnershipError
ConversationVersionConflictError = ConversationStaleContextError

__all__ = [
    "AiConversationService",
    "ConversationAccessError",
    "ConversationDeletedError",
    "ConversationMigrationUnavailableError",
    "ConversationOwnershipError",
    "ConversationStaleContextError",
    "ConversationVersionConflictError",
    "RequestIdReuseConflictError",
    "TurnAlreadyInFlightError",
    "compute_request_fingerprint",
    "compute_scope_fingerprint",
]


class AiConversationService:
    """Service layer for managing server-owned AI conversations and context state."""

    def __init__(self, db: Session, scope: dict[str, Any] | None = None) -> None:
        self.db = db
        self.scope = scope or {}
        self.repo = AiConversationRepository(db)
        self.owner_user_id = str(self.scope.get("user_id") or "anonymous")
        self.owner_role = str(self.scope.get("role") or "Manager")

    def is_schema_ready(self) -> bool:
        return self.repo.is_schema_ready()

    def _resolve_owner(self, scope: dict[str, Any] | None) -> tuple[str, str]:
        eff_scope = scope if scope is not None else self.scope
        return (
            str(eff_scope.get("user_id") or self.owner_user_id or "anonymous"),
            str(eff_scope.get("role") or self.owner_role or "Manager"),
        )

    def validate_live_account_and_scope(self, scope: dict[str, Any] | None = None) -> dict[str, Any]:
        """Revalidate current account status, role, and scope assignments against live database rows when present."""
        eff_scope = dict(scope if scope is not None else self.scope)
        if eff_scope.get("is_active") is False:
            raise InsightAccessError("User account is inactive or access has been revoked.")

        uid_str = str(eff_scope.get("user_id") or "").strip()
        if uid_str and uid_str != "anonymous":
            try:
                parsed_uid = uuid.UUID(uid_str)
                user_row = self.db.query(User).filter(User.id == parsed_uid).first()
                if user_row is not None:
                    if not bool(user_row.is_active):
                        raise InsightAccessError("User account is inactive or access has been revoked.")
                    eff_scope["is_active"] = True
                    if user_row.role:
                        eff_scope["db_role"] = str(user_row.role)
            except (ValueError, TypeError):
                pass
            except InsightAccessError:
                raise
            except Exception:
                pass
        return eff_scope

    @staticmethod
    def _row_to_payload(row: AiConversation) -> AiConversationContextPayload:
        confirmed_dict = dict(row.confirmed_context or {})
        try:
            confirmed = ConfirmedQueryContext(**confirmed_dict) if confirmed_dict else ConfirmedQueryContext()
        except Exception:
            confirmed = ConfirmedQueryContext()

        pending_clar: AiClarificationPrompt | None = None
        if isinstance(row.pending_clarification, dict) and row.pending_clarification.get("code"):
            try:
                pending_clar = AiClarificationPrompt(**row.pending_clarification)
            except Exception:
                pending_clar = None

        return AiConversationContextPayload(
            conversation_id=str(row.id),
            owner_user_id=str(row.owner_user_id),
            status=str(row.status or "active"),  # type: ignore[arg-type]
            context_version=int(row.context_version or 1),
            confirmed_context=confirmed,
            pending_clarification=pending_clar,
            last_subject_employee_id=row.last_subject_employee_id,
            last_subject_employee_name=row.last_subject_employee_name,
            last_operation_kind=row.last_operation_kind,
            created_at=row.created_at.isoformat() if row.created_at else None,
            updated_at=row.updated_at.isoformat() if row.updated_at else None,
        )

    def create_conversation(
        self,
        *,
        scope: dict[str, Any] | None = None,
        session_state: SessionFilterContext | None = None,
        initial_state: SessionFilterContext | None = None,
    ) -> AiConversationContextPayload:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, owner_role = self._resolve_owner(eff_scope)
        st = session_state or initial_state
        initial_ctx: dict[str, Any] = {}
        if st is not None:
            if st.last_confirmed_query is not None:
                initial_ctx = st.last_confirmed_query.model_dump()
            else:
                initial_ctx = ConfirmedQueryContext(
                    team=st.team,
                    function=st.function,
                    position=st.position,
                    branch=st.branch,
                    performance_level=st.performance_level,
                ).model_dump()
        row = self.repo.create_conversation(
            owner_user_id=owner_id,
            owner_role=owner_role,
            initial_confirmed_context=initial_ctx,
        )
        return self._row_to_payload(row)

    def get_conversation_context(
        self,
        conversation_id: str,
        *,
        scope: dict[str, Any] | None = None,
    ) -> AiConversationContextPayload | None:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, _ = self._resolve_owner(eff_scope)
        row = self.repo.get_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_id,
            include_deleted=False,
        )
        if row is None:
            return None
        return self._row_to_payload(row)

    def get_context(
        self,
        *,
        conversation_id: str | None = None,
        scope: dict[str, Any] | None = None,
        initial_state: SessionFilterContext | None = None,
    ) -> AiConversationContextPayload:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, owner_role = self._resolve_owner(eff_scope)
        initial_ctx: dict[str, Any] = {}
        if initial_state is not None:
            if initial_state.last_confirmed_query is not None:
                initial_ctx = initial_state.last_confirmed_query.model_dump()
            else:
                initial_ctx = ConfirmedQueryContext(
                    team=initial_state.team,
                    function=initial_state.function,
                    position=initial_state.position,
                    branch=initial_state.branch,
                    performance_level=initial_state.performance_level,
                ).model_dump()
        row = self.repo.get_or_create_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_id,
            owner_role=owner_role,
            initial_confirmed_context=initial_ctx,
        )
        return self._row_to_payload(row)

    def claim_or_replay_turn(
        self,
        *,
        conversation_id: str,
        scope: dict[str, Any] | None = None,
        prompt: str,
        client_request_id: str | None = None,
        expected_context_version: int | None = None,
        clarification_choice_id: str | None = None,
        answer_detail: str | None = None,
        session_state: SessionFilterContext | None = None,
        known_employee_names: list[str] | None = None,
        eval_id: str | None = None,
    ) -> tuple[AiTurn, dict[str, Any] | None]:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, owner_role = self._resolve_owner(eff_scope)
        conv = self.repo.get_or_create_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_id,
            owner_role=owner_role,
        )
        eff_req_id = str(client_request_id or uuid.uuid4())
        session_filters = session_state.model_dump() if session_state is not None else {}
        req_fp = compute_request_fingerprint(
            prompt=prompt,
            clarification_choice_id=clarification_choice_id,
            answer_detail=answer_detail,
            session_filters=session_filters,
        )
        scope_fp = compute_scope_fingerprint(eff_scope)
        resolved_eval_id = (
            eval_id
            if eval_id is not None
            else (
                f"{evaluation_cache_identity(self.db)}"
                f":d{CacheInvalidationService.get_data_version()}"
                f":c{CacheInvalidationService.get_config_version()}"
            )
        )

        turn_row, is_completed = self.repo.claim_or_get_turn(
            conversation_id=str(conv.id),
            client_request_id=eff_req_id,
            user_prompt_redacted=sanitize_prompt_for_router_training(
                prompt, known_employee_names=known_employee_names, db=self.db
            ),
            request_fingerprint=req_fp,
            scope_fingerprint=scope_fp,
            eval_id=resolved_eval_id,
        )
        if is_completed and turn_row.response_payload:
            return turn_row, dict(turn_row.response_payload)

        reclaimed_completed = bool((turn_row.evidence_summary or {}).get("reclaimed_from_completed"))
        if (
            expected_context_version is not None
            and int(expected_context_version) > 0
            and int(conv.context_version) != int(expected_context_version)
            and not (reclaimed_completed and int(conv.context_version) == int(expected_context_version) + 1)
        ):
            raise ConversationStaleContextError(
                f"Stale context_version {expected_context_version}; current is {conv.context_version}."
            )
        return turn_row, None

    def complete_turn(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        expected_context_version: int | None = None,
        claim_token: str | None = None,
        scope: dict[str, Any] | None = None,
        outcome: str,
        turn_kind: str,
        route_used: str,
        validated_plan: dict[str, Any],
        evidence_envelope: list[dict[str, Any]],
        response_payload: dict[str, Any],
        session_state: SessionFilterContext,
        confirmed_context: ConfirmedQueryContext | None,
        provider_calls: int,
        total_ms: float,
    ) -> int:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, _ = self._resolve_owner(eff_scope)
        ctx_dict = confirmed_context.model_dump() if confirmed_context is not None else {}
        pending_clar = response_payload.get("clarification") if isinstance(response_payload, dict) else None
        return self.repo.complete_turn_and_advance_context(
            conversation_id=conversation_id,
            owner_user_id=owner_id,
            expected_context_version=expected_context_version,
            turn_id=turn_id,
            claim_token=claim_token,
            validated_plan=validated_plan,
            evidence_summary={"turn_kind": turn_kind, "items": evidence_envelope},
            response_payload=response_payload,
            outcome=outcome,
            route_used=route_used,
            provider_calls=provider_calls,
            total_ms=total_ms,
            new_confirmed_context=ctx_dict,
            pending_clarification=pending_clar if isinstance(pending_clar, dict) else None,
            last_subject_employee_id=confirmed_context.last_subject_employee_id if confirmed_context else None,
            last_subject_employee_name=confirmed_context.last_subject_employee_name if confirmed_context else None,
            last_operation_kind=confirmed_context.last_operation_kind if confirmed_context else None,
        )

    def delete_conversation(self, conversation_id: str, *, scope: dict[str, Any] | None = None) -> bool:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, _ = self._resolve_owner(eff_scope)
        return self.repo.soft_delete_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_id,
        )
