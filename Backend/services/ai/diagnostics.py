"""Non-secret Admin view of PMS AI runtime state.

The product switch can be off. This module only reads flags, a short model
probe, the last fallback code, and upload timestamps. It does not read
prompts, messages, scores, or employee rows.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models.ai_schemas import (
    AiDiagnosticsDataset,
    AiDiagnosticsFallback,
    AiDiagnosticsFeature,
    AiDiagnosticsModel,
    AiDiagnosticsProviders,
    AiDiagnosticsResponse,
)
from models.models import PerformanceRecord, UploadLog
from services.ai.feature_gate import read_ai_enabled
from services.ai.llm_client import (
    configured_model_name,
    local_exploration_enabled,
    local_intent_enabled,
    local_synthesis_enabled,
    probe_model_availability,
)
from services.ai.runtime_status import last_fallback
from services.cache_invalidation_service import CacheInvalidationService
from services.ai.config import redact_secrets

_SECRET_ENV_NAMES = (
    "PMS_AI_LLM_API_KEY",
    "PMS_AI_LLM_BASE_URL",
    "PMS_AI_LOCAL_ROUTER_URL",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "DATABASE_URL",
    "JWT_SECRET",
    "REDIS_PASSWORD",
)
_USERINFO_URL = re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:]+:[^/\s@]+@", re.IGNORECASE)
_BEARER = re.compile(r"Bearer\s+\S+", re.IGNORECASE)


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def _dataset_freshness(db: Session | None) -> AiDiagnosticsDataset:
    data_version = CacheInvalidationService.get_data_version()
    config_version = CacheInvalidationService.get_config_version()
    if db is None:
        return AiDiagnosticsDataset(data_version=data_version, config_version=config_version, status="unavailable")
    try:
        latest_upload = db.query(func.max(UploadLog.uploaded_at)).scalar()
        latest_record = db.query(func.max(PerformanceRecord.uploaded_at)).scalar()
    except SQLAlchemyError:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        return AiDiagnosticsDataset(data_version=data_version, config_version=config_version, status="unavailable")
    return AiDiagnosticsDataset(
        latest_upload_at=_iso(latest_upload),
        latest_performance_record_at=_iso(latest_record),
        data_version=data_version,
        config_version=config_version,
        status="ok",
    )


def _scrub_text(value: str) -> str:
    cleaned = redact_secrets(value)
    for name in _SECRET_ENV_NAMES:
        secret = os.environ.get(name, "")
        if secret and len(secret) >= 8 and secret in cleaned:
            cleaned = cleaned.replace(secret, "[REDACTED]")
    cleaned = _USERINFO_URL.sub("[REDACTED]", cleaned)
    cleaned = _BEARER.sub("[REDACTED]", cleaned)
    return cleaned


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return _scrub_text(value)
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items()}
    return value


def build_ai_diagnostics(db: Session | None) -> AiDiagnosticsResponse:
    """Assemble the diagnostic. Model probes are capped inside the client."""
    try:
        enabled = False if db is None else bool(read_ai_enabled(db))
    except SQLAlchemyError:
        enabled = False
    intent_on = local_intent_enabled()
    synthesis_on = local_synthesis_enabled()
    exploration_on = local_exploration_enabled()
    probe = probe_model_availability()
    model_up = bool(probe.get("available"))
    fallback = last_fallback()
    payload = AiDiagnosticsResponse(
        data={
            "feature": AiDiagnosticsFeature(
                ai_enabled=enabled,
                intent_enabled=intent_on,
                synthesis_enabled=synthesis_on,
                exploration_enabled=exploration_on,
            ),
            "model": AiDiagnosticsModel(
                available=model_up,
                name=_scrub_text(str(probe.get("name") or configured_model_name())),
                version=_scrub_text(probe["version"]) if isinstance(probe.get("version"), str) else None,
                probe=str(probe.get("probe") or "not_sent"),
                reason=str(probe.get("reason") or "unavailable"),
                last_known=probe.get("last_known") if isinstance(probe.get("last_known"), dict) else None,
            ),
            "providers": AiDiagnosticsProviders(
                routing="llama_cpp" if intent_on and model_up else "deterministic",
                synthesis="llama_cpp" if synthesis_on and model_up else "deterministic",
            ),
            "last_fallback": AiDiagnosticsFallback(
                reason=fallback.get("reason"),
                source=fallback.get("source"),
                recorded_at=fallback.get("recorded_at"),
            ),
            "dataset": _dataset_freshness(db),
        }
    )
    return AiDiagnosticsResponse.model_validate(_scrub(payload.model_dump()))
