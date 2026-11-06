from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from models.ai_schemas import (
    AiClarificationPrompt,
    AiConversationContextPayload,
    ConfirmedQueryContext,
    SessionFilterContext,
)
from models.models import AiConversation
from repositories.ai_conversation_repository import (
    AiConversationRepository,
    ConversationOwnershipError,
    ConversationStaleContextError,
    TurnAlreadyInFlightError,
)

__all__ = [
    "AiConversationService",
    "ConversationOwnershipError",
    "ConversationStaleContextError",
    "TurnAlreadyInFlightError",
]


class AiConversationService:
    """Service layer for managing server-owned AI conversations and context state."""

    def __init__(self, db: Session, scope: dict[str, Any]) -> None:
        self.db = db
        self.scope = scope
        self.repo = AiConversationRepository(db)
        self.owner_user_id = str(scope.get("user_id") or "anonymous")
        self.owner_role = str(scope.get("role") or "Manager")

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
            context_version=int(row.context_version or 0),
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
        session_state: SessionFilterContext | None = None,
    ) -> AiConversationContextPayload:
        initial_ctx: dict[str, Any] = {}
        if session_state is not None:
            if session_state.last_confirmed_query is not None:
                initial_ctx = session_state.last_confirmed_query.model_dump()
            else:
                initial_ctx = ConfirmedQueryContext(
                    team=session_state.team,
                    function=session_state.function,
                    position=session_state.position,
                    branch=session_state.branch,
                    performance_level=session_state.performance_level,
                ).model_dump()
        row = self.repo.create_conversation(
            owner_user_id=self.owner_user_id,
            owner_role=self.owner_role,
            initial_confirmed_context=initial_ctx,
        )
        return self._row_to_payload(row)

    def get_conversation_context(self, conversation_id: str) -> AiConversationContextPayload | None:
        row = self.repo.get_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=self.owner_user_id,
        )
        if row is None:
            return None
        return self._row_to_payload(row)

    def delete_conversation(self, conversation_id: str) -> bool:
        return self.repo.soft_delete_conversation(
            conversation_id=conversation_id,
            owner_user_id=self.owner_user_id,
        )
