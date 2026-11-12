from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from api.dependencies import require_authenticated_scope, require_role
from services.ai.feature_gate import read_ai_enabled, require_ai_admin, require_ai_diagnostic_session, require_ai_enabled
from config.database import get_db, release_read_transaction
from models.ai_schemas import (
    AiCatalogResponse,
    AiChatRequest,
    AiChatResponse,
    AiConversationCreateRequest,
    AiConversationResponse,
    AiCorrectiveActionConfirmRequest,
    AiCorrectiveActionConfirmResponse,
    AiDiagnosticsPayload,
    AiDiagnosticsResponse,
    AiDistillationExportResponse,
    AiFeedbackRequest,
    AiFeedbackResponse,
    AiTraceReviewRequest,
    AiTraceReviewResponse,
    AiWatchingResponse,
    SessionFilterContext,
)
from services.ai.config import get_ai_runtime_config
from services.ai.catalog import get_ai_catalog
from services.ai.llm_client import (
    get_recent_fallback_reason,
    local_exploration_enabled,
    local_intent_enabled,
    local_synthesis_enabled,
    provider_status,
)
from services.ai.contextual_assistant import (
    ProposalStaleEvidenceError,
    confirm_corrective_action_proposal,
)
from services.ai.conversation_service import (
    AiConversationService,
    ConversationDeletedError,
    ConversationMigrationUnavailableError,
    ConversationOwnershipError,
    ConversationStaleContextError,
    RequestIdReuseConflictError,
    TurnAlreadyInFlightError,
)
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.providers import ProviderUnavailableError
from services.ai.router import AiProviderUnavailableError
from services.ai.trace_logger import TraceOwnershipError, TrainingTraceLogger
from services.corrective_action_service import (
    CorrectiveActionAccessError,
    CorrectiveActionNotFoundError,
    CorrectiveActionValidationError,
)
from services.insights_service import InsightAccessError, InsightValidationError

router = APIRouter(
    prefix="/ai",
    tags=["PMS AI Workspace"],
    dependencies=[Depends(require_ai_enabled), Depends(require_ai_admin)],
)

# Diagnostics stay available when the product switch is off so an Admin can see why.
diagnostics_router = APIRouter(
    prefix="/ai",
    tags=["PMS AI Diagnostics"],
)

# The router dependency is the pilot boundary. This list stays Admin-only so a
# route-level check cannot admit a wider role if the router dependency is copied.
AI_WORKSPACE_ROLES = [
    "Admin",
]


@diagnostics_router.get("/diagnostics", response_model=AiDiagnosticsResponse)
def get_ai_diagnostics(
    request: Request,
    db: Session = Depends(get_db),
    _session: None = Depends(require_ai_diagnostic_session),
    _role: str = Depends(require_ai_admin),
) -> AiDiagnosticsResponse:
    """Admin diagnostics. Available while AI is off so an Admin can see why."""
    payload = build_ai_diagnostics_payload(db)
    release_read_transaction(db)
    return AiDiagnosticsResponse(success=True, message="Admin AI diagnostics loaded", data=payload)


@router.get("/watching", response_model=AiWatchingResponse)
def get_ai_watching_workspace(
    request: Request,
    db: Session = Depends(get_db),
    function: str | None = Query(default=None),
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
    except (ConversationOwnershipError, ConversationDeletedError) as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ConversationStaleContextError, RequestIdReuseConflictError, TurnAlreadyInFlightError) as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (ProviderUnavailableError, AiProviderUnavailableError, ConversationMigrationUnavailableError) as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except InsightAccessError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except InsightValidationError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AiChatResponse(success=True, message="AI analytical response generated", data=payload)


@router.post("/proposals/confirm", response_model=AiCorrectiveActionConfirmResponse)
def post_confirm_corrective_action_proposal(
    body: AiCorrectiveActionConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(AI_WORKSPACE_ROLES)),
) -> AiCorrectiveActionConfirmResponse:
    scope = require_authenticated_scope(db, request)
    try:
        return confirm_corrective_action_proposal(db, scope, body)
    except (CorrectiveActionAccessError, InsightAccessError, PermissionError) as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except CorrectiveActionNotFoundError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ProposalStaleEvidenceError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (CorrectiveActionValidationError, InsightValidationError, ValueError) as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/conversations", response_model=AiConversationResponse)
def create_ai_conversation(
    request: Request,
    body: AiConversationCreateRequest | None = None,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(AI_WORKSPACE_ROLES)),
) -> AiConversationResponse:
    scope = require_authenticated_scope(db, request)
    svc = AiConversationService(db, scope)
    try:
        data = svc.create_conversation(
            session_state=body.session_state if body is not None else None
        )
    except ConversationMigrationUnavailableError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except InsightAccessError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    release_read_transaction(db)
    return AiConversationResponse(
        success=True,
        message="Conversation created",
        data=data,
    )


@router.get("/conversations/{conversation_id}/context", response_model=AiConversationResponse)
def get_ai_conversation_context(
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(AI_WORKSPACE_ROLES)),
) -> AiConversationResponse:
    scope = require_authenticated_scope(db, request)
    svc = AiConversationService(db, scope)
    try:
        data = svc.get_conversation_context(conversation_id)
    except (ConversationOwnershipError, ConversationDeletedError) as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConversationMigrationUnavailableError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except InsightAccessError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    release_read_transaction(db)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return AiConversationResponse(
        success=True,
        message="Conversation context loaded",
        data=data,
    )


@router.delete("/conversations/{conversation_id}")
def delete_ai_conversation(
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(AI_WORKSPACE_ROLES)),
) -> dict[str, object]:
    scope = require_authenticated_scope(db, request)
    svc = AiConversationService(db, scope)
    try:
        deleted = svc.delete_conversation(conversation_id)
    except (ConversationOwnershipError, ConversationDeletedError) as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConversationMigrationUnavailableError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except InsightAccessError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    release_read_transaction(db)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return {
        "success": True,
        "message": "Conversation reset",
        "conversation_id": conversation_id,
    }


@router.get("/catalog", response_model=AiCatalogResponse)
def get_ai_authorized_catalog(
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(AI_WORKSPACE_ROLES)),
) -> AiCatalogResponse:
    scope = require_authenticated_scope(db, request)
    payload = get_ai_catalog().get_authorized_catalog_payload(scope)
    release_read_transaction(db)
    return AiCatalogResponse(
        success=True,
        message="Authorized AI catalog loaded",
        data=payload,
    )


@router.post("/feedback", response_model=AiFeedbackResponse)
def post_ai_trace_feedback(
    body: AiFeedbackRequest,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(AI_WORKSPACE_ROLES)),
) -> AiFeedbackResponse:
    scope = require_authenticated_scope(db, request)
    caller_role = str(scope.get("role") or "")
    try:
        found, eligible = TrainingTraceLogger(db).record_feedback(
            trace_id=body.trace_id,
            rating=body.rating,
            category=body.category,
            reason=body.reason,
            caller_user_id=str(scope.get("user_id") or ""),
            caller_role=caller_role,
            reviewer_verified=body.reviewer_verified if caller_role == "Admin" else None,
        )
    except TraceOwnershipError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if not found:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interaction trace not found")
    return AiFeedbackResponse(
        success=True,
        message="Feedback recorded for administrator review",
        trace_id=body.trace_id,
        rating=body.rating,
        category=body.category,
        is_distillation_eligible=bool(eligible and body.reviewer_verified and caller_role == "Admin"),
        reviewer_verified=bool(body.reviewer_verified and caller_role == "Admin"),
    )


@router.post("/traces/{trace_id}/review", response_model=AiTraceReviewResponse)
def post_ai_trace_review(
    trace_id: str,
    body: AiTraceReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(["Admin"])),
) -> AiTraceReviewResponse:
    scope = require_authenticated_scope(db, request)
    reviewer_id = str(scope.get("user_id") or "admin")
    caller_role = str(scope.get("role") or "")
    try:
        found, eligible, reviewed_at = TrainingTraceLogger(db).review_trace(
            trace_id=trace_id,
            reviewer_verified=body.reviewer_verified,
            reviewer_id=reviewer_id,
            caller_role=caller_role,
            notes=body.notes,
        )
    except PermissionError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if not found:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interaction trace not found")
    return AiTraceReviewResponse(
        success=True,
        message="Trace review updated",
        trace_id=trace_id,
        reviewer_verified=body.reviewer_verified,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        is_distillation_eligible=eligible,
    )


@router.get("/traces/export", response_model=AiDistillationExportResponse)
def export_ai_distillation_traces(
    request: Request,
    db: Session = Depends(get_db),
    verified_only: bool = Query(default=True),
    limit: int = Query(default=500, ge=1, le=2000),
    _role: str = Depends(require_role(["Admin"])),
) -> AiDistillationExportResponse:
    scope = require_authenticated_scope(db, request)
    if not verified_only:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only administrator-reviewed examples can be exported for training.")
    client_host = request.client.host if request.client else None
    req_id = request.headers.get("x-request-id")
    records = TrainingTraceLogger(db).export_distillation_dataset(
        verified_only=verified_only,
        limit=limit,
        performed_by_user_id=str(scope.get("user_id") or "") or None,
        ip_address=client_host,
        request_id=req_id,
    )
    release_read_transaction(db)
    return AiDistillationExportResponse(
        success=True,
        total_exported=len(records),
        records=records,
    )


def _safe_host(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    host = value.strip()
    if "://" in host or "@" in host or "/" in host or " " in host:
        return None
    return host


def build_ai_diagnostics_payload(db: Session | None) -> AiDiagnosticsPayload:
    cfg = get_ai_runtime_config()
    model_health = provider_status()

    freshness: dict[str, object] = {}
    try:
        if db is not None:
            from datetime import datetime

            from models.models import PerformanceRecord, UploadLog
            from sqlalchemy import func
            count = db.query(func.count(PerformanceRecord.id)).scalar()
            freshness["performance_records_count"] = int(count) if count is not None else 0
            latest_upload = db.query(func.max(UploadLog.uploaded_at)).scalar()
            latest_record = db.query(func.max(PerformanceRecord.uploaded_at)).scalar()
            if isinstance(latest_upload, datetime):
                freshness["latest_upload_at"] = latest_upload.isoformat()
            if isinstance(latest_record, datetime):
                freshness["latest_performance_record_at"] = latest_record.isoformat()
            if count and count > 0:
                rows = db.query(PerformanceRecord.year, PerformanceRecord.month).distinct().all()
                month_order = {
                    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
                    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
                }
                def _sort_key(item: tuple[Any, Any]) -> tuple[int, int]:
                    yr = int(item[0] or 0)
                    mo = month_order.get(str(item[1]).strip().casefold(), 0)
                    return yr, mo
                sorted_rows = sorted(rows, key=_sort_key)
                if sorted_rows:
                    latest = sorted_rows[-1]
                    freshness["latest_published_period"] = f"{latest[1]} {latest[0]}"
    except Exception:
        freshness = {"performance_records_count": None, "database_status": "read_failed"}

    feature_enabled = False
    try:
        if db is not None:
            feature_enabled = read_ai_enabled(db)
    except Exception:
        feature_enabled = False

    model_up = bool(model_health.get("available"))
    active_provider = str(model_health.get("active_provider") or "deterministic")
    if active_provider not in ("cloudflare", "gemini"):
        active_provider = "cloudflare"
    intent_on = local_intent_enabled()
    synthesis_on = local_synthesis_enabled()
    return AiDiagnosticsPayload(
        feature_enabled=feature_enabled,
        pilot_role_restricted=True,
        model_configured_name=str(model_health.get("configured_model") or ""),
        model_endpoint_configured=bool(model_health.get("endpoint_configured")),
        model_endpoint_host=_safe_host(model_health.get("endpoint_host")),
        model_available=model_up,
        inference_verified=False,
        model_availability_reason=str(model_health.get("reason") or "unavailable"),
        router_mode=cfg.router_mode,
        intent_routing_enabled=intent_on,
        synthesis_enabled=synthesis_on,
        exploration_enabled=local_exploration_enabled(),
        routing_provider=active_provider if intent_on and model_up else "deterministic",
        synthesis_provider=active_provider if synthesis_on and model_up else "deterministic",
        brief_default_enabled=cfg.brief_default_enabled,
        conversation_state_enabled=cfg.conversation_state_enabled,
        provider_timeout_seconds=cfg.provider_timeout_seconds,
        recent_fallback_reason=get_recent_fallback_reason(),
        fallback_scope="process_local",
        data_freshness=freshness,
    )
