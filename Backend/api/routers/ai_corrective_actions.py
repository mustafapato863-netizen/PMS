"""Corrective-action suggestion pilot API (#98).

``POST /api/ai/corrective-action-suggestions`` returns an *unapproved* draft
for one authorized subject and period. It never creates, approves or edits an
``Action``; saving stays a separate, explicit step in the existing
corrective-action workflow.

Gates, in order (all server-side):

1. An authenticated session (401 otherwise).
2. Admin only during the pilot (403).
3. The separate, default-off corrective-action pilot switch (403). The
   standalone chat switch (``ai_enabled``) is deliberately *not* required and
   enabling this pilot does not expose chat.
4. The resolved session scope must itself be Admin, and the evidence service
   re-checks role/data scope for the requested employee or team (403).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from api.dependencies import require_authenticated_scope
from config.database import get_db, release_read_transaction
from models.ai_schemas import (
    AiCorrectiveActionSuggestionRequest,
    AiCorrectiveActionSuggestionResponse,
)
from services.ai.corrective_action_drafter import CorrectiveActionDrafter
from services.ai.feature_gate import (
    AI_PILOT_ROLE,
    require_ai_admin,
    require_ai_corrective_action_pilot_enabled,
    require_ai_diagnostic_session,
)

router = APIRouter(
    prefix="/ai",
    tags=["PMS AI Corrective-Action Pilot"],
    dependencies=[
        Depends(require_ai_diagnostic_session),
        Depends(require_ai_admin),
        Depends(require_ai_corrective_action_pilot_enabled),
    ],
)

_OUTCOME_MESSAGES = {
    "suggested": "Draft suggestion generated for review. It is not saved or approved.",
    "insufficient_evidence": "There is not enough evidence to draft a suggestion for this selection.",
    "model_unavailable": "The local AI model is unavailable. Retry later or enter the action manually.",
    "draft_rejected": "The AI draft did not match the evidence and was discarded. Retry or enter the action manually.",
}


@router.post("/corrective-action-suggestions", response_model=AiCorrectiveActionSuggestionResponse)
def post_corrective_action_suggestion(
    body: AiCorrectiveActionSuggestionRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AiCorrectiveActionSuggestionResponse:
    scope = require_authenticated_scope(db, request)
    if str(scope.get("role") or "") != AI_PILOT_ROLE:
        # The header/session role passed require_ai_admin, but the authoritative
        # scope did not resolve to Admin: refuse rather than widen access.
        release_read_transaction(db)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PMS AI is limited to administrators during the pilot.",
        )
    try:
        payload = CorrectiveActionDrafter(db).suggest(user_scope=scope, request=body)
    except PermissionError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    release_read_transaction(db)
    return AiCorrectiveActionSuggestionResponse(
        success=True,
        message=_OUTCOME_MESSAGES[payload.outcome],
        data=payload,
    )
