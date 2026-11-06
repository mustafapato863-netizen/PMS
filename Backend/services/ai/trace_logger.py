from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import re
import threading
import uuid
from typing import Any

from sqlalchemy.orm import Session

from models.ai_schemas import AiDistillationRecord, SessionFilterContext
from models.models import AiConversation, AiInteractionTrace, AiTurn
from services.ai.config import get_ai_runtime_config, redact_secrets
from services.audit_service import AuditService

logger = logging.getLogger(__name__)

_PII_ID_RE = re.compile(r"\b(?:EMP[-_ ]?\d+|SGHD\d+|SGHA\d+|\d{5,8})\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-])\d{3,4}[\s-]\d{4}\b|\b05\d[\s-]?\d{3}[\s-]?\d{4}\b")

_ENGINE_INIT_LOCK = threading.Lock()
_INITIALIZED_ENGINE_KEYS: set[str] = set()

PRIVILEGED_REVIEWER_ROLES: frozenset[str] = frozenset(
    {"Admin", "General Manager", "Performance Team"}
)


def sanitize_prompt_for_router_training(
    prompt: str,
    *,
    known_employee_names: list[str] | None = None,
) -> str:
    """Replace concrete employee IDs, emails, phones, keys, and known employee names with canonical tokens."""
    cleaned = redact_secrets(prompt or "")
    cleaned = _EMAIL_RE.sub("<EMAIL>", cleaned)
    cleaned = _PHONE_RE.sub("<PHONE>", cleaned)
    cleaned = _PII_ID_RE.sub("<EMPLOYEE_ID>", cleaned)
    if known_employee_names:
        for name in sorted({n.strip() for n in known_employee_names if n and len(n.strip()) >= 3}, key=len, reverse=True):
            cleaned = re.sub(rf"\b{re.escape(name)}\b", "<EMPLOYEE_NAME>", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def redact_nested_payload(value: Any, *, known_employee_names: list[str] | None = None) -> Any:
    """Recursively redact PII and secrets from trace digests and exported training structures."""
    if isinstance(value, str):
        return sanitize_prompt_for_router_training(value, known_employee_names=known_employee_names)
    if isinstance(value, list):
        return [redact_nested_payload(item, known_employee_names=known_employee_names) for item in value]
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for k, v in value.items():
            key_lower = str(k).casefold()
            if key_lower in ("raw_data", "workbook_bytes", "api_key", "password", "token"):
                continue
            if key_lower in ("employee_id", "emp_id") and v:
                redacted[k] = "<EMPLOYEE_ID>"
            elif key_lower in ("employee_name", "agent_name") and v:
                redacted[k] = "<EMPLOYEE_NAME>"
            else:
                redacted[k] = redact_nested_payload(v, known_employee_names=known_employee_names)
        return redacted
    return value


def ensure_trace_schema_once(db: Session) -> None:
    """Ensure AI tables exist once per database engine in non-production environments (never run DDL in production)."""
    if os.environ.get("APP_ENV", "").strip().casefold() == "production":
        return
    try:
        bind = db.get_bind()
        root_engine = getattr(bind, "engine", bind)
        engine_key = f"{id(root_engine)}:{getattr(root_engine, 'url', '')}"
        if engine_key in _INITIALIZED_ENGINE_KEYS:
            return
        with _ENGINE_INIT_LOCK:
            if engine_key in _INITIALIZED_ENGINE_KEYS:
                return
            AiConversation.__table__.create(bind=bind, checkfirst=True)
            AiTurn.__table__.create(bind=bind, checkfirst=True)
            AiInteractionTrace.__table__.create(bind=bind, checkfirst=True)
            _INITIALIZED_ENGINE_KEYS.add(engine_key)
    except Exception as exc:
        logger.debug("AI schema one-time check skipped: %s", exc)


class TraceOwnershipError(PermissionError):
    """Raised when a user attempts to modify feedback on another user's trace."""


class TrainingTraceLogger:
    """Persists AI turns with redaction and curates verified, anonymized training pairs."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def record_turn(
        self,
        *,
        user_id: str | None,
        role: str,
        prompt: str,
        session_state: SessionFilterContext,
        tool_calls: list[dict[str, Any]],
        tool_digest: dict[str, Any],
        structured_response: dict[str, Any],
        provider_name: str,
        model_name: str,
        latency_ms: int,
        non_empty_evidence: bool,
        guardrail_triggered: bool,
        known_employee_names: list[str] | None = None,
        turn_id: str | None = None,
    ) -> str:
        trace_uuid = uuid.uuid4()
        cfg = get_ai_runtime_config()
        sanitized = sanitize_prompt_for_router_training(
            prompt, known_employee_names=known_employee_names
        )
        stored_prompt = sanitized if cfg.redact_raw_prompts else redact_secrets(prompt)
        redacted_session = redact_nested_payload(
            session_state.model_dump(), known_employee_names=known_employee_names
        )
        redacted_digest = redact_nested_payload(
            tool_digest, known_employee_names=known_employee_names
        )
        redacted_calls = redact_nested_payload(
            tool_calls, known_employee_names=known_employee_names
        )
        try:
            ensure_trace_schema_once(self.db)
            row = AiInteractionTrace(
                id=trace_uuid,
                turn_id=str(turn_id) if turn_id else None,
                user_id=str(user_id) if user_id else None,
                role=role or "Manager",
                prompt=stored_prompt,
                sanitized_prompt=sanitized,
                session_state=redacted_session,
                tool_calls=redacted_calls,
                tool_digest=redacted_digest,
                structured_response=redact_nested_payload(
                    structured_response, known_employee_names=known_employee_names
                ),
                provider_name=provider_name,
                model_name=model_name,
                latency_ms=max(0, int(latency_ms)),
                non_empty_evidence=bool(non_empty_evidence),
                guardrail_triggered=bool(guardrail_triggered),
                is_distillation_eligible=False,
                reviewer_verified=False,
            )
            self.db.add(row)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            logger.warning("Failed to persist AI interaction trace: %s", redact_secrets(str(exc)))
        return str(trace_uuid)

    def record_feedback(
        self,
        *,
        trace_id: str,
        rating: str,
        reason: str | None = None,
        caller_user_id: str | None = None,
        caller_role: str | None = None,
        reviewer_verified: bool | None = None,
    ) -> tuple[bool, bool]:
        """Upsert user ✓/✕ feedback on an existing trace. Enforces trace ownership and never self-certifies non-Admin users."""
        try:
            ensure_trace_schema_once(self.db)
            parsed_id = uuid.UUID(str(trace_id))
        except (ValueError, TypeError):
            return False, False

        try:
            row = self.db.query(AiInteractionTrace).filter(AiInteractionTrace.id == parsed_id).first()
            if not row:
                return False, False

            owner_id = str(row.user_id or "").strip()
            caller_id = str(caller_user_id or "").strip()
            is_admin_reviewer = str(caller_role or "") == "Admin" and reviewer_verified is not None
            if owner_id and caller_id and owner_id != caller_id and not is_admin_reviewer:
                raise TraceOwnershipError("Cannot submit feedback for another user's interaction trace")
            if owner_id and not caller_id and not is_admin_reviewer and caller_role is not None:
                raise TraceOwnershipError("Cannot submit feedback for another user's interaction trace")

            row.feedback_rating = rating
            row.feedback_reason = sanitize_prompt_for_router_training(reason or "") if reason else None
            row.is_distillation_eligible = bool(
                rating == "up" and row.non_empty_evidence and not row.guardrail_triggered
            )
            if is_admin_reviewer:
                row.reviewer_verified = bool(reviewer_verified)
                row.reviewer_id = caller_id or "admin"
                row.reviewed_at = datetime.now(timezone.utc)
                if isinstance(row.structured_response, dict):
                    updated_resp = dict(row.structured_response)
                    updated_resp["reviewer_verified"] = bool(reviewer_verified)
                    row.structured_response = updated_resp
            self.db.commit()
            return True, bool(row.is_distillation_eligible)
        except TraceOwnershipError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            logger.warning("Failed to update feedback on trace %s: %s", trace_id, redact_secrets(str(exc)))
            return False, False

    def review_trace(
        self,
        *,
        trace_id: str,
        reviewer_verified: bool,
        reviewer_id: str,
        caller_role: str,
        notes: str | None = None,
    ) -> tuple[bool, bool, str]:
        """Admin-only trace verification for distillation curation."""
        if str(caller_role or "") != "Admin":
            raise PermissionError("Only Admin reviewers can verify AI traces for distillation.")
        try:
            ensure_trace_schema_once(self.db)
            parsed_id = uuid.UUID(str(trace_id))
        except (ValueError, TypeError):
            return False, False, ""

        try:
            row = self.db.query(AiInteractionTrace).filter(AiInteractionTrace.id == parsed_id).first()
            if not row:
                return False, False, ""
            now_dt = datetime.now(timezone.utc)
            row.reviewer_verified = bool(reviewer_verified)
            row.reviewer_id = str(reviewer_id or "admin")
            row.reviewed_at = now_dt
            if notes:
                row.feedback_reason = sanitize_prompt_for_router_training(notes)
            if isinstance(row.structured_response, dict):
                updated_resp = dict(row.structured_response)
                updated_resp["reviewer_verified"] = bool(reviewer_verified)
                row.structured_response = updated_resp
            self.db.commit()
            return True, bool(row.is_distillation_eligible), now_dt.isoformat()
        except Exception as exc:
            self.db.rollback()
            logger.warning("Failed to review trace %s: %s", trace_id, redact_secrets(str(exc)))
            return False, False, ""

    def export_distillation_dataset(
        self,
        *,
        verified_only: bool = True,
        limit: int = 500,
        performed_by_user_id: str | None = None,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> list[AiDistillationRecord]:
        try:
            ensure_trace_schema_once(self.db)
            query = self.db.query(AiInteractionTrace)
            if verified_only:
                query = query.filter(AiInteractionTrace.is_distillation_eligible.is_(True))
            rows = query.order_by(AiInteractionTrace.created_at.desc()).limit(max(1, min(limit, 2000))).all()
        except Exception as exc:
            logger.warning("Failed to export distillation dataset: %s", redact_secrets(str(exc)))
            return []

        records: list[AiDistillationRecord] = []
        for r in rows:
            clean_session = redact_nested_payload(r.session_state or {})
            if isinstance(clean_session, dict):
                clean_session.pop("employee_id", None)
            clean_calls = redact_nested_payload(r.tool_calls or [])
            router_pair = {
                "schema_version": "pms-ai-router-v1",
                "sanitized_prompt": sanitize_prompt_for_router_training(r.sanitized_prompt or ""),
                "session_filter_state": clean_session,
                "expected_tool_calls": clean_calls,
            }
            narrative_pair = None
            rev_verified = False
            if isinstance(r.structured_response, dict):
                rev_verified = bool(r.structured_response.get("reviewer_verified", False))
            if r.is_distillation_eligible and isinstance(r.structured_response, dict):
                narrative_pair = {
                    "schema_version": "pms-ai-narrative-v1",
                    "headline": sanitize_prompt_for_router_training(
                        str(r.structured_response.get("headline") or "")
                    ),
                    "narrative_bullets": [
                        sanitize_prompt_for_router_training(str(b))
                        for b in (r.structured_response.get("narrative_bullets") or [])
                    ],
                }
            records.append(
                AiDistillationRecord(
                    trace_id=str(r.id),
                    created_at=r.created_at.isoformat() if r.created_at else "",
                    role=r.role,
                    router_training_pair=router_pair,
                    narrative_training_pair=narrative_pair,
                    provider_name=r.provider_name,
                    model_name=r.model_name,
                    reviewer_verified=rev_verified,
                )
            )

        # Audit the distillation export
        try:
            AuditService.log_operation(
                self.db,
                table_name="ai_interaction_traces",
                operation="EXPORT",
                record_id=str(uuid.uuid4()),
                old_values=None,
                new_values={
                    "verified_only": verified_only,
                    "limit": limit,
                    "exported_count": len(records),
                },
                performed_by_user_id=performed_by_user_id if performed_by_user_id else None,
                ip_address=ip_address,
                request_id=request_id,
            )
        except Exception as exc:
            logger.debug("Audit log for AI trace export skipped: %s", redact_secrets(str(exc)))

        return records
