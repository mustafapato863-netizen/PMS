from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from api.dependencies import require_authenticated_scope, require_role
from config.database import get_db, release_read_transaction
from models.ai_schemas import (
    AiChatRequest,
    AiChatResponse,
    AiDistillationExportResponse,
    AiFeedbackRequest,
    AiFeedbackResponse,
    AiWatchingResponse,
    SessionFilterContext,
)
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.trace_logger import TrainingTraceLogger
from services.insights_service import InsightAccessError, InsightValidationError

router = APIRouter(prefix="/ai", tags=["PMS AI Workspace"])

AI_WORKSPACE_ROLES = [
    "Admin",
    "General Manager",
    "Manager",
    "Executive",
    "Performance Team",
    "Regional Manager",
    "Branch Director",
    "Function Director",
    "Function Viewer",
]


@router.get("/watching", response_model=AiWatchingResponse)
def get_ai_watching_workspace(
    request: Request,
    db: Session = Depends(get_db),
    function: str | None = Query(default="Call Center"),
    team: str | None = Query(default=None),
    branch: str | None = Query(default=None),
    region: str | None = Query(default=None),
    performance_level: str | None = Query(default=None),
    month: str | None = Query(default=None),
    year: int | None = Query(default=None, ge=2000, le=2100),
    _role: str = Depends(require_role(AI_WORKSPACE_ROLES)),
) -> AiWatchingResponse:
    scope = require_authenticated_scope(db, request)
    session_state = SessionFilterContext(
        function=function,
        team=team,
        branch=branch,
        region=region,
        performance_level=performance_level,
        month=month,
        year=year,
    )
    try:
        payload = PmsAiOrchestrator(db, scope).build_watching_workspace(session_state)
    except InsightAccessError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except InsightValidationError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AiWatchingResponse(success=True, message="AI watching workspace loaded", data=payload)


@router.post("/chat", response_model=AiChatResponse)
def post_ai_chat_turn(
    body: AiChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(AI_WORKSPACE_ROLES)),
) -> AiChatResponse:
    scope = require_authenticated_scope(db, request)
    try:
        payload = PmsAiOrchestrator(db, scope).run_chat_turn(body)
    except InsightAccessError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except InsightValidationError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AiChatResponse(success=True, message="AI analytical response generated", data=payload)


@router.post("/feedback", response_model=AiFeedbackResponse)
def post_ai_trace_feedback(
    body: AiFeedbackRequest,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(AI_WORKSPACE_ROLES)),
) -> AiFeedbackResponse:
    require_authenticated_scope(db, request)
    found, eligible = TrainingTraceLogger(db).record_feedback(
        trace_id=body.trace_id,
        rating=body.rating,
        reason=body.reason,
    )
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interaction trace not found")
    return AiFeedbackResponse(
        success=True,
        message="Feedback recorded for model distillation",
        trace_id=body.trace_id,
        rating=body.rating,
        is_distillation_eligible=eligible,
    )


@router.get("/traces/export", response_model=AiDistillationExportResponse)
def export_ai_distillation_traces(
    request: Request,
    db: Session = Depends(get_db),
    verified_only: bool = Query(default=True),
    limit: int = Query(default=500, ge=1, le=2000),
    _role: str = Depends(require_role(["Admin", "General Manager", "Performance Team"])),
) -> AiDistillationExportResponse:
    require_authenticated_scope(db, request)
    records = TrainingTraceLogger(db).export_distillation_dataset(
        verified_only=verified_only,
        limit=limit,
    )
    release_read_transaction(db)
    return AiDistillationExportResponse(
        success=True,
        total_exported=len(records),
        records=records,
    )
