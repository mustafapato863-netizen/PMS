from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from models.ai_schemas import AiDistillationRecord, SessionFilterContext
from models.models import AiInteractionTrace

logger = logging.getLogger(__name__)

_PII_ID_RE = re.compile(r"\b(?:EMP[-_ ]?\d+|SGHD\d+|SGHA\d+|\d{4,8})\b", re.IGNORECASE)


def sanitize_prompt_for_router_training(prompt: str) -> str:
    """Replace concrete employee IDs with a canonical <EMPLOYEE_ID> token for PII-free router training."""
    cleaned = _PII_ID_RE.sub("<EMPLOYEE_ID>", prompt or "")
    return cleaned.strip()


class TrainingTraceLogger:
    """Persists AI turns and curates verified training pairs for local LLM distillation."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _ensure_table(self) -> None:
        try:
            bind = self.db.get_bind()
            AiInteractionTrace.__table__.create(bind=bind, checkfirst=True)
        except Exception as exc:
            logger.debug("AiInteractionTrace table check skipped: %s", exc)

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
    ) -> str:
        trace_uuid = uuid.uuid4()
        try:
            self._ensure_table()
            row = AiInteractionTrace(
                id=trace_uuid,
                user_id=str(user_id) if user_id else None,
                role=role or "Manager",
                prompt=prompt,
                sanitized_prompt=sanitize_prompt_for_router_training(prompt),
                session_state=session_state.model_dump(),
                tool_calls=tool_calls,
                tool_digest=tool_digest,
                structured_response=structured_response,
                provider_name=provider_name,
                model_name=model_name,
                latency_ms=max(0, int(latency_ms)),
                non_empty_evidence=bool(non_empty_evidence),
                guardrail_triggered=bool(guardrail_triggered),
                is_distillation_eligible=False,
            )
            self.db.add(row)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            logger.warning("Failed to persist AI interaction trace: %s", exc)
        return str(trace_uuid)

    def record_feedback(
        self,
        *,
        trace_id: str,
        rating: str,
        reason: str | None = None,
    ) -> tuple[bool, bool]:
        """Upsert user ✓/✕ feedback on an existing trace. Returns (found, is_distillation_eligible)."""
        try:
            self._ensure_table()
            parsed_id = uuid.UUID(str(trace_id))
        except (ValueError, TypeError):
            return False, False

        try:
            row = self.db.query(AiInteractionTrace).filter(AiInteractionTrace.id == parsed_id).first()
            if not row:
                return False, False

            row.feedback_rating = rating
            row.feedback_reason = reason
            row.is_distillation_eligible = bool(
                rating == "up" and row.non_empty_evidence and not row.guardrail_triggered
            )
            self.db.commit()
            return True, bool(row.is_distillation_eligible)
        except Exception as exc:
            self.db.rollback()
            logger.warning("Failed to update feedback on trace %s: %s", trace_id, exc)
            return False, False

    def export_distillation_dataset(
        self,
        *,
        verified_only: bool = True,
        limit: int = 500,
    ) -> list[AiDistillationRecord]:
        try:
            self._ensure_table()
            query = self.db.query(AiInteractionTrace)
            if verified_only:
                query = query.filter(AiInteractionTrace.is_distillation_eligible.is_(True))
            rows = query.order_by(AiInteractionTrace.created_at.desc()).limit(max(1, min(limit, 2000))).all()
        except Exception as exc:
            logger.warning("Failed to export distillation dataset: %s", exc)
            return []

        records: list[AiDistillationRecord] = []
        for r in rows:
            router_pair = {
                "schema_version": "pms-ai-router-v1",
                "sanitized_prompt": r.sanitized_prompt,
                "session_filter_state": r.session_state,
                "expected_tool_calls": r.tool_calls,
            }
            narrative_pair = None
            if r.is_distillation_eligible and isinstance(r.structured_response, dict):
                narrative_pair = {
                    "schema_version": "pms-ai-narrative-v1",
                    "headline": r.structured_response.get("headline"),
                    "narrative_bullets": r.structured_response.get("narrative_bullets"),
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
                )
            )
        return records
