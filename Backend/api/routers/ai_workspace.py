from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Literal

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from api.dependencies import require_authenticated_scope, require_role
from services.ai.feature_gate import (
    read_ai_access_tier,
    read_ai_enabled,
    require_ai_access,
    require_ai_admin,
    require_ai_diagnostic_session,
    require_ai_enabled,
)
from config.database import get_db, release_read_transaction
from models.ai_schemas import (
    AiApprovedPatternListResponse,
    AiApprovePatternRequest,
    AiApprovePatternResponse,
    AiPatternPreviewResponse,
    AiPreviewPatternRequest,
    AiCatalogResponse,
    AiChatRequest,
    AiChatResponse,
    AiClusterAnalysisResponse,
    AiClusterAnalyzeRequest,
    AiConversationCreateRequest,
    AiConversationDetailResponse,
    AiConversationListResponse,
    AiConversationResponse,
    AiCorrectiveActionConfirmRequest,
    AiCorrectiveActionConfirmResponse,
    AiDeidentifiedExportBundleResponse,
    AiDiagnosticsPayload,
    AiDiagnosticsResponse,
    AiDistillationExportResponse,
    AiFeedbackAnalyzerStatusResponse,
    AiFeedbackClustersResponse,
    AiFeedbackPurgeRequest,
    AiFeedbackPurgeResponse,
    AiFeedbackRegressionTemplateResponse,
    AiFeedbackRequest,
    AiFeedbackResponse,
    AiPilotFeedbackRequest,
    AiTraceAnalyzeRequest,
    AiTraceReviewRequest,
    AiTraceReviewResponse,
    AiWatchingResponse,
    NemotronFeedbackAnalysisResult,
    SessionFilterContext,
)
from services.ai.config import get_ai_runtime_config
from services.ai.catalog import get_ai_catalog
from services.ai.approved_patterns import ApprovedPatternMatcher
from services.ai.feedback_service import FeedbackGovernanceService, FeedbackIdempotencyConflictError
from services.ai.shared_feedback_learning import shared_learning_families
from services.ai.nemotron_analyzer import NemotronFeedbackAnalyzerService, get_analyzer_status
from services.ai.llm_client import (
    configured_providers,
    get_recent_fallback_reason,
    local_exploration_enabled,
    local_intent_enabled,
    local_synthesis_enabled,
    provider_status,
    record_live_verification,
)
from services.ai.contextual_assistant import (
    ProposalStaleEvidenceError,
    confirm_corrective_action_proposal,
)
from services.ai.conversation_service import (
    AiConversationService,
    ConversationDeletedError,
    ConversationMigrationUnavailableError,
    ConversationOriginMismatchError,
    ConversationOwnershipError,
    ConversationStaleContextError,
    RequestIdReuseConflictError,
    TurnAlreadyInFlightError,
)
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.providers import ProviderUnavailableError
from services.ai.router import AiProviderUnavailableError
from services.ai.usage_budget import (
    AiBudgetExceededError,
    acquire_chat_concurrency_slot,
    check_request_token_budget,
    check_user_daily_budget,
    estimate_tokens,
    get_budget_health_snapshot,
    is_existing_completed_replay,
    record_user_tokens,
)
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
    dependencies=[Depends(require_ai_enabled), Depends(require_ai_access)],
)

# Admin-only governance routes (traces, pattern approval, exports, purges).
# Always restricted to Admin regardless of ai_access_tier; mounted under router below.
admin_governance_router = APIRouter(
    tags=["PMS AI Governance"],
    dependencies=[Depends(require_ai_enabled), Depends(require_ai_admin)],
)

# Diagnostics stay available when the product switch is off so an Admin can see why.
diagnostics_router = APIRouter(
    prefix="/ai",
    tags=["PMS AI Diagnostics"],
)

# Default pilot roles (admin_only tier). Widened dynamically by require_ai_access via ai_access_tier.
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


_live_verify_flight_lock = threading.RLock()
_live_verify_in_flight: bool = False

# Atomic and shared across all backend workers; keys expire after their UTC day.
_LIVE_VERIFY_BUDGET_LUA = """
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
local limit = tonumber(ARGV[1])
if count >= limit then return 0 end
count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], 172800) end
return 1
"""


def _is_live_verify_endpoint_enabled() -> bool:
    raw = os.environ.get("PMS_AI_LIVE_VERIFY_ENDPOINT_ENABLED", "false").strip().casefold()
    return raw in ("true", "1", "yes", "on", "enabled")


def _check_and_increment_daily_budget(daily_budget: int) -> bool:
    """Shared UTC-day quota with fail-closed Redis availability.

    No in-memory fallback: per-worker counters can exceed the global quota.
    Use the standalone non-production CLI when Redis cannot be reached.
    """
    if not 1 <= daily_budget <= 10:
        raise HTTPException(status_code=503, detail="Invalid live verification budget configuration")
    today = time.strftime("%Y-%m-%d", time.gmtime())
    key = f"pms:ai:live_verify:budget:{today}"
    try:
        from services.redis_provider import redis_client
        if not redis_client:
            raise RuntimeError("Shared Redis unavailable")
        allowed = redis_client.eval(_LIVE_VERIFY_BUDGET_LUA, 1, key, daily_budget)
        return int(allowed) == 1
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Shared live verification budget unavailable; use the non-production CLI",
        ) from None


@diagnostics_router.post("/diagnostics/verify-live", response_model=AiDiagnosticsResponse)
def verify_ai_live(
    request: Request,
    db: Session = Depends(get_db),
    _session: None = Depends(require_ai_diagnostic_session),
    _role: str = Depends(require_ai_admin),
) -> AiDiagnosticsResponse:
    """Explicit Admin-only diagnostic action: runs bounded synthetic live connectivity check.

    Never called during routine health checks or normal page loads. Never consumes tokens
    unless explicitly triggered by an authenticated Administrator.
    Guarded by:
    1. Mandatory Admin role and diagnostic session.
    2. PMS_AI_LIVE_VERIFY_ENDPOINT_ENABLED switch (default: false).
    3. Production environment blocking (unless PMS_AI_ALLOW_PRODUCTION_LIVE_VERIFY=true).
    4. Atomic Redis-backed daily budget (max 10/day); fail closed if Redis is unavailable.
    5. Non-blocking concurrency lock (rejects concurrent calls with HTTP 429).
    6. One shared five-second deadline for both synthetic calls.
    """
    global _live_verify_in_flight

    # 1. Feature Switch Check
    if not _is_live_verify_endpoint_enabled():
        raise HTTPException(
            status_code=403,
            detail="Live verification endpoint is disabled by configuration (PMS_AI_LIVE_VERIFY_ENDPOINT_ENABLED=false)",
        )

    # 2. Environment Protection Check
    app_env = os.environ.get("APP_ENV", "").strip().casefold()
    allow_prod = os.environ.get("PMS_AI_ALLOW_PRODUCTION_LIVE_VERIFY", "false").strip().casefold() in ("true", "1")
    if app_env == "production" and not allow_prod:
        raise HTTPException(
            status_code=403,
            detail="Live verification endpoint is disabled in production environments",
        )

    # 3. Concurrency Lock Check (do NOT hold lock during network calls!)
    with _live_verify_flight_lock:
        if _live_verify_in_flight:
            raise HTTPException(
                status_code=429,
                detail="A live verification check is already in progress. Please wait for completion.",
            )
        # 4. Daily Budget Check
        try:
            daily_budget = int(os.environ.get("PMS_AI_LIVE_VERIFY_DAILY_BUDGET", "10"))
        except ValueError:
            raise HTTPException(status_code=503, detail="Invalid live verification budget configuration") from None
        if not _check_and_increment_daily_budget(daily_budget):
            raise HTTPException(
                status_code=429,
                detail=f"Live verification daily budget exceeded (maximum {daily_budget} calls/day).",
            )
        _live_verify_in_flight = True

    try:
        from services.ai.provider_engine import load_unified_provider_config
        from services.ai.provider_probe import probe_nvidia

        try:
            total_timeout = float(os.environ.get("PMS_AI_LIVE_VERIFY_TIMEOUT_SECONDS", "5.0"))
            if not (0 < total_timeout <= 5.0):
                raise ValueError("Total deadline must be between 0 and 5 seconds")
        except ValueError:
            raise HTTPException(status_code=503, detail="Invalid live verification timeout configuration") from None
        config = load_unified_provider_config()
        providers = configured_providers(config)
        active_provider = providers[0] if providers else config.effective_primary_provider
        if active_provider == "nvidia":
            probe = probe_nvidia(
                api_key=config.nvidia_api_key, model=config.nvidia_model, timeout=total_timeout
            )
            live_result = {
                "verified": probe["ok"], "provider": "nvidia", "model": config.nvidia_model,
                "total_latency_ms": probe["latency_ms"],
                "error": None if probe["ok"] else probe["message"],
            }
        else:
            from scripts.verify_cloudflare_ai import run_live_verification
            live_result = run_live_verification(
                account_id=config.cloudflare_account_id,
                api_token=config.cloudflare_api_token,
                model=config.cloudflare_model,
                timeout=total_timeout,
            )
        record_live_verification(live_result, config)
        payload = build_ai_diagnostics_payload(db)
        release_read_transaction(db)
        success = bool(live_result.get("verified"))
        msg = (
            "Live AI verification succeeded"
            if success
            else f"Live AI verification failed: {live_result.get('error') or 'check details'}"
        )
        return AiDiagnosticsResponse(success=success, message=msg, data=payload)
    finally:
        with _live_verify_flight_lock:
            _live_verify_in_flight = False


@router.get("/watching", response_model=AiWatchingResponse)
def get_ai_watching_workspace(
    request: Request,
    db: Session = Depends(get_db),
    function: str | None = Query(default=None),
    team: str | None = Query(default=None),
    position: str | None = Query(default=None),
    branch: str | None = Query(default=None),
    region: str | None = Query(default=None),
    performance_level: str | None = Query(default=None),
    month: str | None = Query(default=None),
    year: int | None = Query(default=None, ge=2000, le=2100),
    _role: str = Depends(require_ai_access),
) -> AiWatchingResponse:
    scope = require_authenticated_scope(db, request)
    session_state = SessionFilterContext(
        function=function,
        team=team,
        position=position,
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


_traffic_logger = logging.getLogger("pms.ai.traffic")
_LABEL_RE = re.compile(r"[^a-z0-9_\-]")


def _label(value: object) -> str:
    """Enum-like label safe for logs: lowercase letters, digits, _ and - only, max 40 chars."""
    text = _LABEL_RE.sub("", str(value or "none").strip().lower())
    return text[:40] or "none"


def log_ai_chat_traffic(payload: object) -> None:
    """One metrics line per chat turn: how it was answered and what kind of question it was.

    Only enum-like labels are logged. Never the question, answer, names, ids or scope.
    """
    try:
        plan = getattr(payload, "structured_query", None)
        _traffic_logger.info(
            "ai_chat_traffic answer_source=%s outcome=%s intent=%s operation=%s turn_kind=%s capability=%s cache_hit=%s latency_ms=%d",
            _label(getattr(payload, "answer_source", None)),
            _label(getattr(payload, "outcome", None)),
            _label(getattr(plan, "intent", None)),
            _label(getattr(plan, "operation_kind_v2", None)),
            _label(getattr(plan, "turn_kind_v2", None)),
            _label(getattr(payload, "capability_mode", None)),
            bool(getattr(payload, "cache_hit", False)),
            int(getattr(payload, "latency_ms", 0) or 0),
        )
    except Exception:  # metrics must never break a chat turn
        pass


@router.post("/chat", response_model=AiChatResponse)
def post_ai_chat_turn(
    body: AiChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_ai_access),
) -> AiChatResponse:
    scope = require_authenticated_scope(db, request)
    user_id = str(scope.get("user_id") or "") or None
    user_role = str(scope.get("role") or "") or None
    is_replay = is_existing_completed_replay(
        db,
        conversation_id=body.conversation_id,
        client_request_id=body.client_request_id,
        owner_user_id=user_id,
    )
    try:
        with acquire_chat_concurrency_slot():
            if not is_replay:
                check_request_token_budget(estimate_tokens(body.prompt))
                check_user_daily_budget(
                    user_id,
                    user_role,
                    increment_request=True,
                    access_tier=read_ai_access_tier(db),
                )
            payload = PmsAiOrchestrator(db, scope).run_chat_turn(body)
    except AiBudgetExceededError as exc:
        release_read_transaction(db)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=exc.detail,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except (ConversationOwnershipError, ConversationDeletedError) as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (
        ConversationStaleContextError,
        ConversationOriginMismatchError,
        RequestIdReuseConflictError,
        TurnAlreadyInFlightError,
    ) as exc:
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
    if not is_replay and not getattr(payload, "cache_hit", False):
        usage = getattr(payload, "provider_usage", None)
        total_tokens = int(getattr(usage, "input_tokens", 0) or 0) + int(getattr(usage, "output_tokens", 0) or 0)
        if total_tokens > 0:
            record_user_tokens(user_id, total_tokens)
    log_ai_chat_traffic(payload)
    if payload.answer_source == "model_synthesis":
        resp_msg = "AI analytical response generated"
    elif payload.answer_source == "fallback":
        resp_msg = "Deterministic fallback response generated"
    else:
        resp_msg = "Deterministic PMS response generated"
    return AiChatResponse(success=True, message=resp_msg, data=payload)


@router.post("/proposals/confirm", response_model=AiCorrectiveActionConfirmResponse)
def post_confirm_corrective_action_proposal(
    body: AiCorrectiveActionConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_ai_access),
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
    _role: str = Depends(require_ai_access),
) -> AiConversationResponse:
    scope = require_authenticated_scope(db, request)
    svc = AiConversationService(db, scope)
    try:
        data = svc.create_conversation(
            session_state=body.session_state if body is not None else None,
            origin=body.origin if body is not None else "workspace",
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


@router.get("/conversations", response_model=AiConversationListResponse)
def list_ai_conversations(
    request: Request,
    limit: int = Query(default=30, ge=1, le=50),
    origin: Literal["workspace", "page_assistant", "legacy", "all"] = Query(default="workspace"),
    db: Session = Depends(get_db),
    _role: str = Depends(require_ai_access),
) -> AiConversationListResponse:
    scope = require_authenticated_scope(db, request)
    svc = AiConversationService(db, scope)
    try:
        conversations = svc.list_conversations(limit=limit, origin=origin)
    except ConversationMigrationUnavailableError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except InsightAccessError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    release_read_transaction(db)
    return AiConversationListResponse(
        success=True,
        message="Conversations loaded",
        conversations=conversations,
    )


@router.get("/conversations/{conversation_id}", response_model=AiConversationDetailResponse)
def get_ai_conversation_detail(
    conversation_id: str,
    request: Request,
    origin: Literal["workspace", "page_assistant", "legacy"] = Query(default="workspace"),
    db: Session = Depends(get_db),
    _role: str = Depends(require_ai_access),
) -> AiConversationDetailResponse:
    scope = require_authenticated_scope(db, request)
    svc = AiConversationService(db, scope)
    try:
        data = svc.get_conversation_detail(conversation_id, expected_origin=origin)
    except (ConversationOwnershipError, ConversationDeletedError) as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConversationOriginMismatchError as exc:
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
    return AiConversationDetailResponse(
        success=True,
        message="Conversation loaded",
        data=data,
    )


@router.get("/conversations/{conversation_id}/context", response_model=AiConversationResponse)
def get_ai_conversation_context(
    conversation_id: str,
    request: Request,
    origin: Literal["workspace", "page_assistant", "legacy"] = Query(default="workspace"),
    db: Session = Depends(get_db),
    _role: str = Depends(require_ai_access),
) -> AiConversationResponse:
    scope = require_authenticated_scope(db, request)
    svc = AiConversationService(db, scope)
    try:
        data = svc.get_conversation_context(conversation_id, expected_origin=origin)
    except (ConversationOwnershipError, ConversationDeletedError) as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConversationOriginMismatchError as exc:
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


@router.post("/conversations/{conversation_id}/promote", response_model=AiConversationResponse)
def promote_ai_conversation(
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_ai_access),
) -> AiConversationResponse:
    scope = require_authenticated_scope(db, request)
    svc = AiConversationService(db, scope)
    try:
        data = svc.promote_conversation(conversation_id)
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
    return AiConversationResponse(
        success=True,
        message="Conversation promoted to workspace",
        data=data,
    )


@router.delete("/conversations/{conversation_id}")
def delete_ai_conversation(
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_ai_access),
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
    _role: str = Depends(require_ai_access),
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
    _role: str = Depends(require_ai_access),
) -> AiFeedbackResponse:
    scope = require_authenticated_scope(db, request)
    caller_role = str(scope.get("role") or "")
    if body.reviewer_verified and caller_role != "Admin":
        release_read_transaction(db)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Administrators can certify reviewed traces",
        )
    if db is None:
        try:
            ok, elig = TrainingTraceLogger(db).record_feedback(
                trace_id=body.trace_id,
                rating=body.rating,
                category=body.category,
                reason=body.reason,
                caller_user_id=str(scope.get("user_id") or ""),
                caller_role=caller_role,
                reviewer_verified=body.reviewer_verified,
            )
        except TraceOwnershipError as exc:
            release_read_transaction(db)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        if not ok:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interaction trace not found")
        verified = bool(body.reviewer_verified and caller_role == "Admin")
        return AiFeedbackResponse(
            success=True,
            message="Feedback recorded",
            trace_id=body.trace_id,
            rating=body.rating,
            category=body.category,
            is_distillation_eligible=bool(elig and verified),
            reviewer_verified=verified,
        )
    try:
        feedback = FeedbackGovernanceService(db).record_workspace_or_pilot_feedback(
            payload=AiPilotFeedbackRequest(
                trace_id=body.trace_id,
                idempotency_key=(
                    body.idempotency_key
                    or request.headers.get("idempotency-key")
                    or request.headers.get("x-request-id")
                ),
                surface="workspace_chat",
                rating=body.rating,
                reason_tag=body.category,
                comment=body.reason,
            ),
            caller_user_id=str(scope.get("user_id") or ""),
            caller_role=caller_role,
        )
    except TraceOwnershipError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FeedbackIdempotencyConflictError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LookupError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AiFeedbackResponse(
        success=True,
        message="Feedback recorded for administrator review",
        trace_id=feedback.trace_id,
        rating=feedback.rating,
        category=feedback.reason_tag,
        is_distillation_eligible=False,
        reviewer_verified=False,
    )


@admin_governance_router.post("/traces/{trace_id}/review", response_model=AiTraceReviewResponse)
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
    client_host = request.client.host if request.client else None
    req_id = request.headers.get("x-request-id")
    try:
        result = FeedbackGovernanceService(db).review_feedback(
            trace_id=trace_id,
            reviewer_verified=body.reviewer_verified,
            decision=body.decision,
            reviewer_id=reviewer_id,
            caller_role=caller_role,
            notes=body.notes,
            proposed_action=body.proposed_action,
            replay_trace_id=body.replay_trace_id,
            review_route=body.review_route,
            reviewer_usability=body.reviewer_usability,
            ip_address=client_host,
            request_id=req_id,
        )
    except PermissionError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FeedbackIdempotencyConflictError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result is None:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interaction trace not found")
    return result


@admin_governance_router.get("/feedback/quality")
def get_feedback_quality(db: Session = Depends(get_db)):
    from services.ai.quality_summary import sampled_quality

    payload = sampled_quality(db)
    release_read_transaction(db)
    return payload


@admin_governance_router.get("/quality/summary")
def get_answer_quality_summary(db: Session = Depends(get_db)):
    from services.ai.quality_admin import quality_summary

    payload = quality_summary(db)
    release_read_transaction(db)
    return payload


@admin_governance_router.get("/quality/failures")
def get_answer_quality_failures(db: Session = Depends(get_db), limit: int = Query(default=30, ge=1, le=100)):
    from services.ai.quality_admin import judged_failures

    payload = {"failures": judged_failures(db, limit=limit)}
    release_read_transaction(db)
    return payload


@admin_governance_router.get("/quality/regressions")
def get_answer_quality_regressions(db: Session = Depends(get_db)):
    from services.ai.quality_lessons import regression_cases

    payload = {"cases": regression_cases(db)}
    release_read_transaction(db)
    return payload


class _LessonStatusBody(BaseModel):
    status: Literal["approved", "rejected", "pending"]


@admin_governance_router.post("/quality/lessons/{trace_id}")
def set_answer_quality_lesson(trace_id: str, body: _LessonStatusBody, db: Session = Depends(get_db)):
    from services.ai.quality_lessons import set_lesson_status

    if not set_lesson_status(db, trace_id, body.status):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    return {"trace_id": trace_id, "status": body.status}


@admin_governance_router.get("/feedback/clusters", response_model=AiFeedbackClustersResponse)
def get_ai_feedback_clusters(
    request: Request,
    db: Session = Depends(get_db),
    surface: str | None = Query(default=None),
    rating: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=50),
    _role: str = Depends(require_role(["Admin"])),
) -> AiFeedbackClustersResponse:
    scope = require_authenticated_scope(db, request)
    caller_role = str(scope.get("role") or "")
    try:
        payload = FeedbackGovernanceService(db).cluster_failures(
            caller_role=caller_role,
            surface=surface,
            rating=rating,
            review_status=review_status,
            page=page,
            page_size=page_size,
        )
        payload.shared_learning = shared_learning_families(db)
    except PermissionError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    release_read_transaction(db)
    return payload


@admin_governance_router.get("/feedback/analyzer/status", response_model=AiFeedbackAnalyzerStatusResponse)
def get_ai_feedback_analyzer_status(
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(["Admin"])),
) -> AiFeedbackAnalyzerStatusResponse:
    require_authenticated_scope(db, request)
    release_read_transaction(db)
    return get_analyzer_status()


@admin_governance_router.post("/traces/{trace_id}/analyze", response_model=NemotronFeedbackAnalysisResult)
def post_analyze_ai_trace(
    trace_id: str,
    request: Request,
    body: AiTraceAnalyzeRequest | None = None,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(["Admin"])),
) -> NemotronFeedbackAnalysisResult:
    scope = require_authenticated_scope(db, request)
    caller_role = str(scope.get("role") or "")
    caller_user_id = str(scope.get("user_id") or "") or None
    client_host = request.client.host if request.client else None
    req_id = request.headers.get("x-request-id")
    req_body = body or AiTraceAnalyzeRequest()
    try:
        result = NemotronFeedbackAnalyzerService(db).analyze_trace(
            trace_id=trace_id,
            caller_role=caller_role,
            caller_user_id=caller_user_id,
            force_refresh=req_body.force_refresh,
            screenshot_data_url=req_body.screenshot_data_url,
            screenshot_pii_free_attested=req_body.screenshot_pii_free_attested,
            ip_address=client_host,
            request_id=req_id,
        )
    except PermissionError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except LookupError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if result.outcome == "rate_limited":
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=result.message or "Daily budget reached")
    return result


@admin_governance_router.post("/feedback/clusters/analyze", response_model=AiClusterAnalysisResponse)
def post_analyze_ai_feedback_cluster(
    request: Request,
    body: AiClusterAnalyzeRequest | None = None,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(["Admin"])),
) -> AiClusterAnalysisResponse:
    scope = require_authenticated_scope(db, request)
    caller_role = str(scope.get("role") or "")
    caller_user_id = str(scope.get("user_id") or "") or None
    client_host = request.client.host if request.client else None
    req_id = request.headers.get("x-request-id")
    req_body = body or AiClusterAnalyzeRequest()
    try:
        result = NemotronFeedbackAnalyzerService(db).analyze_cluster(
            caller_role=caller_role,
            caller_user_id=caller_user_id,
            surface=req_body.surface,
            operation_family=req_body.operation_family,
            scope_team=req_body.scope_team,
            reason_tag=req_body.reason_tag,
            rating=req_body.rating,
            review_status=req_body.review_status,
            ip_address=client_host,
            request_id=req_id,
        )
    except PermissionError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if result.outcome == "rate_limited":
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=result.message or "Daily budget reached")
    return result


@admin_governance_router.get("/feedback/patterns", response_model=AiApprovedPatternListResponse)
def get_ai_approved_patterns(
    request: Request,
    db: Session = Depends(get_db),
    include_inactive: bool = Query(default=False),
    _role: str = Depends(require_role(["Admin"])),
) -> AiApprovedPatternListResponse:
    require_authenticated_scope(db, request)
    patterns = ApprovedPatternMatcher(db).list_patterns(active_only=not include_inactive)
    release_read_transaction(db)
    return AiApprovedPatternListResponse(success=True, patterns=patterns)


@admin_governance_router.post("/traces/{trace_id}/preview-pattern", response_model=AiPatternPreviewResponse)
def post_preview_ai_pattern(
    trace_id: str,
    body: AiPreviewPatternRequest,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(["Admin"])),
) -> AiPatternPreviewResponse:
    scope = require_authenticated_scope(db, request)
    try:
        return ApprovedPatternMatcher(db).preview_pattern(trace_id=trace_id, payload=body, scope=scope)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    finally:
        release_read_transaction(db)


@admin_governance_router.post("/traces/{trace_id}/approve-pattern", response_model=AiApprovePatternResponse)
def post_approve_ai_pattern(
    trace_id: str,
    body: AiApprovePatternRequest,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(["Admin"])),
) -> AiApprovePatternResponse:
    scope = require_authenticated_scope(db, request)
    approver_id = str(scope.get("user_id") or "admin")
    caller_role = str(scope.get("role") or "")
    client_host = request.client.host if request.client else None
    req_id = request.headers.get("x-request-id")
    try:
        pattern, review_res = ApprovedPatternMatcher(db).approve_pattern_from_trace(
            trace_id=trace_id,
            payload=body,
            approver_user_id=approver_id,
            caller_role=caller_role,
            ip_address=client_host,
            request_id=req_id,
        )
    except PermissionError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except LookupError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AiApprovePatternResponse(
        success=True,
        message="Pattern verified against live PMS data and saved",
        pattern=pattern,
        trace_review=review_res,
    )


@admin_governance_router.delete("/feedback/patterns/{pattern_id}")
def delete_ai_approved_pattern(
    pattern_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(["Admin"])),
) -> dict[str, object]:
    scope = require_authenticated_scope(db, request)
    actor_id = str(scope.get("user_id") or "admin")
    caller_role = str(scope.get("role") or "")
    client_host = request.client.host if request.client else None
    req_id = request.headers.get("x-request-id")
    try:
        removed = ApprovedPatternMatcher(db).deactivate_pattern(
            pattern_id=pattern_id,
            actor_user_id=actor_id,
            caller_role=caller_role,
            ip_address=client_host,
            request_id=req_id,
        )
    except PermissionError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if not removed:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approved pattern not found")
    return {
        "success": True,
        "message": "Approved pattern removed",
        "pattern_id": pattern_id,
    }


@admin_governance_router.post("/traces/purge", response_model=AiFeedbackPurgeResponse)
def post_purge_ai_traces(
    request: Request,
    body: AiFeedbackPurgeRequest | None = None,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(["Admin"])),
) -> AiFeedbackPurgeResponse:
    scope = require_authenticated_scope(db, request)
    caller_role = str(scope.get("role") or "")
    caller_user_id = str(scope.get("user_id") or "") or None
    client_host = request.client.host if request.client else None
    req_id = request.headers.get("x-request-id")
    req_body = body or AiFeedbackPurgeRequest()
    try:
        return FeedbackGovernanceService(db).purge_expired_feedback(
            caller_role=caller_role,
            caller_user_id=caller_user_id,
            retention_days=req_body.retention_days,
            dry_run=req_body.dry_run,
            ip_address=client_host,
            request_id=req_id,
        )
    except PermissionError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@admin_governance_router.delete("/traces/{trace_id}")
def delete_ai_trace(
    trace_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(["Admin"])),
) -> dict[str, object]:
    scope = require_authenticated_scope(db, request)
    caller_role = str(scope.get("role") or "")
    caller_user_id = str(scope.get("user_id") or "") or None
    client_host = request.client.host if request.client else None
    req_id = request.headers.get("x-request-id")
    try:
        deleted = FeedbackGovernanceService(db).delete_feedback_trace(
            trace_id=trace_id,
            caller_role=caller_role,
            caller_user_id=caller_user_id,
            ip_address=client_host,
            request_id=req_id,
        )
    except PermissionError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if not deleted:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interaction trace not found")
    return {
        "success": True,
        "message": "Interaction trace deleted",
        "trace_id": trace_id,
    }


@admin_governance_router.get("/feedback/export-bundle", response_model=AiDeidentifiedExportBundleResponse)
def export_ai_feedback_bundle(
    request: Request,
    db: Session = Depends(get_db),
    approved_only: bool = Query(default=True),
    min_cohort_size: int = Query(default=5),
    limit: int = Query(default=500, ge=1, le=2000),
    _role: str = Depends(require_role(["Admin"])),
) -> AiDeidentifiedExportBundleResponse:
    scope = require_authenticated_scope(db, request)
    caller_role = str(scope.get("role") or "")
    caller_user_id = str(scope.get("user_id") or "") or None
    client_host = request.client.host if request.client else None
    req_id = request.headers.get("x-request-id")
    try:
        bundle = FeedbackGovernanceService(db).build_deidentified_export_bundle(
            caller_role=caller_role,
            caller_user_id=caller_user_id,
            approved_only=approved_only,
            min_cohort_size=min_cohort_size,
            limit=limit,
            ip_address=client_host,
            request_id=req_id,
        )
    except PermissionError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    release_read_transaction(db)
    return bundle


@admin_governance_router.get(
    "/feedback/traces/{trace_id}/regression-template",
    response_model=AiFeedbackRegressionTemplateResponse,
)
def get_feedback_regression_template(
    trace_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(["Admin"])),
) -> AiFeedbackRegressionTemplateResponse:
    scope = require_authenticated_scope(db, request)
    caller_role = str(scope.get("role") or "")
    try:
        tmpl = FeedbackGovernanceService(db).build_regression_case_from_trace(
            trace_id=trace_id,
            caller_role=caller_role,
        )
    except PermissionError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if tmpl is None:
        release_read_transaction(db)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interaction trace not found")
    release_read_transaction(db)
    return tmpl


@admin_governance_router.get("/traces/export", response_model=AiDistillationExportResponse)
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
    if active_provider not in ("cloudflare", "nvidia"):
        active_provider = "cloudflare"
    intent_on = local_intent_enabled()
    synthesis_on = local_synthesis_enabled()
    live_ver = model_health.get("live_verification") or {}
    status_code = str(model_health.get("status_code") or "unavailable")
    is_live_verified = bool(model_health.get("live_verified"))
    budget_snapshot = get_budget_health_snapshot()
    return AiDiagnosticsPayload(
        feature_enabled=feature_enabled,
        pilot_role_restricted=True,
        model_configured_name=str(model_health.get("configured_model") or ""),
        model_endpoint_configured=bool(model_health.get("endpoint_configured")),
        model_endpoint_host=_safe_host(model_health.get("endpoint_host")),
        model_available=model_up,
        inference_verified=bool(is_live_verified and model_up),
        provider_status_code=status_code,
        live_verified_at=live_ver.get("timestamp"),
        live_verification_latency_ms=live_ver.get("latency_ms"),
        live_verification_error=live_ver.get("error"),
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
        model_led_pilot_enabled=bool(cfg.model_led_pilot_enabled),
        max_concurrent_requests=int(budget_snapshot["max_concurrent_requests"]),
        active_concurrent_requests=int(budget_snapshot["active_concurrent_requests"]),
        daily_user_request_limit=int(budget_snapshot["daily_user_request_limit"]),
        daily_user_token_limit=int(budget_snapshot["daily_user_token_limit"]),
        max_request_input_tokens=int(budget_snapshot["max_request_input_tokens"]),
        router_timeout_seconds=float(budget_snapshot["router_timeout_seconds"]),
        synthesis_timeout_seconds=float(budget_snapshot["synthesis_timeout_seconds"]),
        rejected_budget_requests=int(budget_snapshot["rejected_budget_requests"]),
        data_freshness=freshness,
    )


router.include_router(admin_governance_router)
