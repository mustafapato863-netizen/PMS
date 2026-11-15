"""Privacy-preserving feedback governance, clustering, retention, and de-identified export (#101).

Stores structured governance metadata inside ``AiInteractionTrace.tool_digest`` and
``AiInteractionTrace.structured_response`` under ``feedback_governance`` so zero DB schema
migration is required while keeping ``feedback_reason`` within ``String(120)``.
"""

from __future__ import annotations

import copy
import logging
import os
import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models.ai_schemas import (
    AiDeidentifiedExportBundleResponse,
    AiDeidentifiedExportItem,
    AiFeedbackClusterItem,
    AiFeedbackClustersResponse,
    AiFeedbackPurgeResponse,
    AiPilotFeedbackRequest,
    AiPilotFeedbackResponse,
    AiTraceReviewResponse,
)
from models.models import AiInteractionTrace, AuditLog, Employee, PerformanceRecord, Team
from services.ai.config import redact_secrets
from services.ai.llm_client import configured_model_name
from services.ai.trace_logger import (
    TraceOwnershipError,
    TrainingTraceLogger,
    _build_name_token_set,
    assess_pii_quarantine,
    ensure_trace_schema_once,
    redact_nested_payload,
    sanitize_prompt_for_router_training,
)
from services.audit_service import AuditService

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 90
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 365
MIN_EXPORT_COHORT_SIZE = 5
_FEEDBACK_REASON_MAX_LEN = 120
_COMMENT_MAX_LEN = 500
_NOTES_MAX_LEN = 240
_TRUTHY = {"1", "true", "yes", "on", "enabled"}
_SHA_SAFE_RE = re.compile(r"[^0-9A-Za-z._\-]")


def _parse_optional_uuid(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(uuid.UUID(str(value).strip()))
    except (TypeError, ValueError, AttributeError):
        return None


def _resolve_retention_days(requested_days: int | None = None) -> int:
    if requested_days is not None:
        return max(MIN_RETENTION_DAYS, min(MAX_RETENTION_DAYS, int(requested_days)))
    raw = os.environ.get("PMS_AI_FEEDBACK_RETENTION_DAYS", str(DEFAULT_RETENTION_DAYS)).strip()
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = DEFAULT_RETENTION_DAYS
    return max(MIN_RETENTION_DAYS, min(MAX_RETENTION_DAYS, parsed))


def _resolve_candidate_sha(explicit_sha: str | None = None) -> str:
    raw = (
        explicit_sha
        or os.environ.get("PMS_CANDIDATE_SHA")
        or os.environ.get("GIT_SHA")
        or os.environ.get("GITHUB_SHA")
        or "unknown"
    )
    cleaned = _SHA_SAFE_RE.sub("", redact_secrets(str(raw).strip()))
    return (cleaned[:40] or "unknown")


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ensure_audit_table_in_nonprod(db: Session) -> None:
    app_env = os.environ.get("APP_ENV", "").strip().casefold()
    disable_ddl = os.environ.get("PMS_DISABLE_RUNTIME_DDL", "").strip().casefold() in _TRUTHY
    if app_env in ("production", "staging", "prod", "stage") or disable_ddl:
        return
    try:
        bind = db.get_bind()
        AuditLog.__table__.create(bind=bind, checkfirst=True)
    except Exception:
        pass


class FeedbackGovernanceService:
    """Manages PMS AI feedback lifecycle across workspace chat and corrective-action pilot."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _name_tokens(self) -> tuple[list[str], set[str]]:
        names = TrainingTraceLogger(self.db)._collect_known_employee_names()
        return names, _build_name_token_set(names)

    def _sanitize_text(
        self,
        text: str | None,
        *,
        tokens: set[str],
        max_len: int,
    ) -> str | None:
        if text is None:
            return None
        cleaned = sanitize_prompt_for_router_training(
            str(text),
            run_syntactic_extraction=True,
            _precomputed_tokens=tokens,
        )
        cleaned = redact_secrets(cleaned).strip()
        if not cleaned:
            return None
        return cleaned[:max_len]

    def _sanitize_scope_label(self, value: str | None, *, tokens: set[str], max_len: int = 120) -> str | None:
        if not value:
            return None
        cleaned = sanitize_prompt_for_router_training(
            str(value),
            run_syntactic_extraction=False,
            _precomputed_tokens=tokens,
        )
        cleaned = redact_secrets(cleaned).strip()[:max_len]
        if not cleaned or cleaned in ("<EMPLOYEE_NAME>", "<EMPLOYEE_ID>", "<EMAIL>", "<PHONE>"):
            return None
        return cleaned

    def _sanitize_evidence_ids(self, evidence_ids: list[str] | None, *, tokens: set[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in (evidence_ids or [])[:50]:
            item = self._sanitize_text(str(raw), tokens=tokens, max_len=100)
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned

    def _extract_gov_meta(self, row: AiInteractionTrace) -> dict[str, Any]:
        td = row.tool_digest if isinstance(row.tool_digest, dict) else {}
        sr = row.structured_response if isinstance(row.structured_response, dict) else {}
        meta = td.get("feedback_governance") or sr.get("feedback_governance") or {}
        return dict(meta) if isinstance(meta, dict) else {}

    def _write_gov_meta(self, row: AiInteractionTrace, meta: dict[str, Any]) -> None:
        td = copy.deepcopy(row.tool_digest) if isinstance(row.tool_digest, dict) else {}
        td["feedback_governance"] = copy.deepcopy(meta)
        row.tool_digest = td

        sr = copy.deepcopy(row.structured_response) if isinstance(row.structured_response, dict) else {}
        sr["feedback_governance"] = copy.deepcopy(meta)
        if meta.get("reason_tag"):
            sr["feedback_category"] = meta["reason_tag"]
        sr["reviewer_verified"] = bool(row.reviewer_verified)
        row.structured_response = sr

    def record_workspace_or_pilot_feedback(
        self,
        *,
        payload: AiPilotFeedbackRequest,
        caller_user_id: str | None,
        caller_role: str | None,
    ) -> AiPilotFeedbackResponse:
        """Record feedback for an existing workspace trace or a de-identified pilot suggestion."""
        ensure_trace_schema_once(self.db)
        _names, tokens = self._name_tokens()

        comment_redacted = self._sanitize_text(
            payload.comment,
            tokens=tokens,
            max_len=_COMMENT_MAX_LEN,
        )
        quarantined, q_reasons = assess_pii_quarantine(
            comment_redacted or "",
            original_text=payload.comment or "",
            _precomputed_tokens=tokens,
        )

        scope_team = self._sanitize_scope_label(payload.scope_team, tokens=tokens, max_len=120)
        scope_country = self._sanitize_scope_label(payload.scope_country, tokens=tokens, max_len=80)
        performance_level = self._sanitize_scope_label(payload.performance_level, tokens=tokens, max_len=40)
        operation_family = self._sanitize_scope_label(
            payload.operation_family or (
                "corrective_action_draft" if payload.surface == "corrective_action_pilot" else "workspace_chat"
            ),
            tokens=tokens,
            max_len=80,
        ) or ("corrective_action_draft" if payload.surface == "corrective_action_pilot" else "workspace_chat")
        fallback_reason = self._sanitize_scope_label(payload.fallback_reason or "none", tokens=tokens, max_len=120) or "none"
        provider_name = self._sanitize_scope_label(payload.provider_name or "deterministic", tokens=tokens, max_len=60) or "deterministic"
        model_version = self._sanitize_scope_label(
            payload.model_version or configured_model_name(),
            tokens=tokens,
            max_len=100,
        ) or configured_model_name()
        candidate_sha = _resolve_candidate_sha(payload.candidate_sha)
        evidence_ids = self._sanitize_evidence_ids(payload.evidence_ids, tokens=tokens)

        reason_parts: list[str] = []
        if payload.reason_tag:
            reason_parts.append(f"[{payload.reason_tag}]")
        if comment_redacted:
            reason_parts.append(comment_redacted)
        compact_reason = " ".join(reason_parts).strip()[:_FEEDBACK_REASON_MAX_LEN] or None

        caller_id = str(caller_user_id or "").strip()

        if payload.trace_id:
            parsed_id = _parse_optional_uuid(payload.trace_id)
            if not parsed_id:
                raise LookupError("Interaction trace not found")
            row = (
                self.db.query(AiInteractionTrace)
                .filter(AiInteractionTrace.id == uuid.UUID(parsed_id))
                .first()
            )
            if not row:
                raise LookupError("Interaction trace not found")

            owner_id = str(row.user_id or "").strip()
            if owner_id and owner_id != caller_id and str(caller_role or "") != "Admin":
                raise TraceOwnershipError("Cannot submit feedback for another user's interaction trace")
            if owner_id and not caller_id and caller_role is not None and str(caller_role) != "Admin":
                raise TraceOwnershipError("Cannot submit feedback for another user's interaction trace")
        else:
            if payload.surface == "workspace_chat":
                raise ValueError("trace_id is required for workspace_chat feedback")
            deidentified_prompt = (
                f"[corrective_action_pilot] op={operation_family} "
                f"team={scope_team or 'unspecified'} "
                f"country={scope_country or 'unspecified'} "
                f"level={performance_level or 'unspecified'}"
            )
            row = AiInteractionTrace(
                id=uuid.uuid4(),
                user_id=caller_id or None,
                role=str(caller_role or "Admin"),
                prompt=deidentified_prompt,
                sanitized_prompt=deidentified_prompt,
                session_state={
                    "surface": payload.surface,
                    "team": scope_team,
                    "region": scope_country,
                    "performance_level": performance_level,
                },
                tool_calls=[],
                tool_digest={},
                structured_response={},
                provider_name=provider_name,
                model_name=model_version[:100],
                latency_ms=0,
                non_empty_evidence=bool(evidence_ids),
                guardrail_triggered=False,
                is_distillation_eligible=False,
                reviewer_verified=False,
            )
            self.db.add(row)

        existing_meta = self._extract_gov_meta(row)
        session_dict = row.session_state if isinstance(row.session_state, dict) else {}
        resolved_team = scope_team or self._sanitize_scope_label(session_dict.get("team"), tokens=tokens)
        resolved_country = scope_country or self._sanitize_scope_label(session_dict.get("region"), tokens=tokens)
        resolved_level = performance_level or self._sanitize_scope_label(session_dict.get("performance_level"), tokens=tokens)

        gov_meta: dict[str, Any] = {
            "surface": payload.surface,
            "candidate_sha": candidate_sha,
            "model_version": model_version,
            "provider_name": provider_name,
            "fallback_reason": fallback_reason,
            "operation_family": operation_family,
            "scope_team": resolved_team,
            "scope_country": resolved_country,
            "performance_level": resolved_level,
            "evidence_ids": evidence_ids,
            "rating": payload.rating,
            "reason_tag": payload.reason_tag,
            "comment_redacted": comment_redacted,
            "pii_quarantined": bool(quarantined),
            "pii_quarantine_reasons": list(q_reasons),
            "review_status": "pending",
            "reviewer_verified": False,
            "proposed_action": None,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }
        if isinstance(existing_meta.get("cohort_size"), int) and not isinstance(existing_meta.get("cohort_size"), bool):
            gov_meta["cohort_size"] = existing_meta["cohort_size"]

        row.feedback_rating = payload.rating
        row.feedback_reason = compact_reason
        row.is_distillation_eligible = bool(
            payload.rating == "up" and row.non_empty_evidence and not row.guardrail_triggered
        )
        # New feedback always resets prior approval so human gate must re-verify.
        row.reviewer_verified = False
        row.reviewer_id = None
        row.reviewed_at = None
        self._write_gov_meta(row, gov_meta)
        self.db.commit()

        return AiPilotFeedbackResponse(
            success=True,
            message="Feedback recorded for administrator review",
            trace_id=str(row.id),
            surface=payload.surface,
            rating=payload.rating,
            reason_tag=payload.reason_tag,
            review_status="pending",
            reviewer_verified=False,
            pii_quarantined=bool(quarantined),
        )

    def review_feedback(
        self,
        *,
        trace_id: str,
        reviewer_id: str,
        caller_role: str,
        reviewer_verified: bool | None = None,
        decision: str | None = None,
        notes: str | None = None,
        proposed_action: str | None = None,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> AiTraceReviewResponse | None:
        """Admin-only explicit approval/rejection transition with AuditService trail."""
        if str(caller_role or "") != "Admin":
            raise PermissionError("Only Admin reviewers can review AI feedback traces.")

        ensure_trace_schema_once(self.db)
        parsed_id = _parse_optional_uuid(trace_id)
        if not parsed_id:
            return None

        row = (
            self.db.query(AiInteractionTrace)
            .filter(AiInteractionTrace.id == uuid.UUID(parsed_id))
            .first()
        )
        if not row:
            return None

        if decision in ("approved", "rejected"):
            resolved_decision = decision
            resolved_verified = decision == "approved"
        else:
            resolved_verified = bool(True if reviewer_verified is None else reviewer_verified)
            resolved_decision = "approved" if resolved_verified else "rejected"

        _names, tokens = self._name_tokens()
        clean_notes = self._sanitize_text(notes, tokens=tokens, max_len=_NOTES_MAX_LEN)
        clean_action = self._sanitize_text(proposed_action, tokens=tokens, max_len=_NOTES_MAX_LEN)

        prev_meta = self._extract_gov_meta(row)
        old_values = {
            "reviewer_verified": bool(row.reviewer_verified),
            "review_status": prev_meta.get("review_status", "pending"),
            "is_distillation_eligible": bool(row.is_distillation_eligible),
        }

        now_dt = datetime.now(timezone.utc)
        row.reviewer_verified = resolved_verified
        row.reviewer_id = str(reviewer_id or "admin")[:100]
        row.reviewed_at = now_dt
        if resolved_verified:
            row.is_distillation_eligible = bool(
                row.feedback_rating == "up" and row.non_empty_evidence and not row.guardrail_triggered
            )
        else:
            row.is_distillation_eligible = False
        if clean_notes:
            row.feedback_reason = clean_notes[:_FEEDBACK_REASON_MAX_LEN]

        gov_meta = dict(prev_meta)
        gov_meta.update(
            {
                "review_status": resolved_decision,
                "reviewer_verified": resolved_verified,
                "reviewed_at": now_dt.isoformat(),
                "review_notes": clean_notes,
                "proposed_action": clean_action,
            }
        )
        self._write_gov_meta(row, gov_meta)
        self.db.commit()

        eligible = bool(row.is_distillation_eligible and row.reviewer_verified)
        actor_uuid = _parse_optional_uuid(reviewer_id)
        new_values: dict[str, Any] = {
            "decision": resolved_decision,
            "review_status": resolved_decision,
            "reviewer_verified": resolved_verified,
            "is_distillation_eligible": eligible,
            "proposed_action": clean_action,
        }
        if actor_uuid is None:
            new_values["actor_user_id"] = str(reviewer_id or "admin")

        _ensure_audit_table_in_nonprod(self.db)
        AuditService.log_operation(
            self.db,
            table_name="ai_interaction_traces",
            operation="AI_FEEDBACK_REVIEW",
            record_id=str(row.id),
            old_values=old_values,
            new_values=new_values,
            performed_by_user_id=actor_uuid,
            ip_address=ip_address,
            request_id=request_id,
        )

        return AiTraceReviewResponse(
            success=True,
            message="Trace review updated",
            trace_id=str(row.id),
            reviewer_verified=resolved_verified,
            reviewer_id=str(reviewer_id or "admin"),
            reviewed_at=now_dt.isoformat(),
            is_distillation_eligible=eligible,
            decision=resolved_decision,  # type: ignore[arg-type]
            review_status=resolved_decision,  # type: ignore[arg-type]
            proposed_action=clean_action,
        )

    def cluster_failures(
        self,
        *,
        caller_role: str,
        surface: str | None = None,
        rating: str | None = None,
        review_status: str | None = None,
    ) -> AiFeedbackClustersResponse:
        """Deterministic failure clustering by (surface, fallback_reason, operation_family, scope_team, reason_tag)."""
        if str(caller_role or "") != "Admin":
            raise PermissionError("Only Admin reviewers can view AI feedback clusters.")

        ensure_trace_schema_once(self.db)
        _names, tokens = self._name_tokens()
        rows = self.db.query(AiInteractionTrace).all()

        grouped: dict[tuple[str, str, str, str, str], dict[str, int]] = defaultdict(
            lambda: {
                "total": 0,
                "up": 0,
                "down": 0,
                "pending": 0,
                "approved": 0,
                "rejected": 0,
            }
        )
        matched_total = 0

        for row in rows:
            meta = self._extract_gov_meta(row)
            has_feedback = row.feedback_rating is not None or bool(meta)
            if not has_feedback:
                continue

            row_surface = str(meta.get("surface") or "workspace_chat")
            row_rating = str(row.feedback_rating or meta.get("rating") or "")
            row_status = str(
                meta.get("review_status")
                or ("approved" if row.reviewer_verified else "pending")
            )
            if surface and row_surface != surface:
                continue
            if rating and row_rating != rating:
                continue
            if review_status and row_status != review_status:
                continue

            session_dict = row.session_state if isinstance(row.session_state, dict) else {}
            fallback_reason = (
                self._sanitize_scope_label(str(meta.get("fallback_reason") or "none"), tokens=tokens, max_len=80)
                or "none"
            )
            operation_family = (
                self._sanitize_scope_label(
                    str(meta.get("operation_family") or session_dict.get("operation") or row_surface),
                    tokens=tokens,
                    max_len=80,
                )
                or row_surface
            )
            scope_team = (
                self._sanitize_scope_label(
                    str(meta.get("scope_team") or session_dict.get("team") or "unspecified"),
                    tokens=tokens,
                    max_len=120,
                )
                or "unspecified"
            )
            reason_tag = str(meta.get("reason_tag") or "")
            if not reason_tag and isinstance(row.structured_response, dict):
                reason_tag = str(row.structured_response.get("feedback_category") or "")
            if not reason_tag:
                reason_tag = "unspecified"
            reason_tag = self._sanitize_scope_label(reason_tag, tokens=tokens, max_len=60) or "unspecified"

            key = (row_surface, fallback_reason, operation_family, scope_team, reason_tag)
            bucket = grouped[key]
            bucket["total"] += 1
            if row_rating == "up":
                bucket["up"] += 1
            elif row_rating == "down":
                bucket["down"] += 1
            if row_status == "approved":
                bucket["approved"] += 1
            elif row_status == "rejected":
                bucket["rejected"] += 1
            else:
                bucket["pending"] += 1
            matched_total += 1

        clusters = [
            AiFeedbackClusterItem(
                surface=key[0],
                fallback_reason=key[1],
                operation_family=key[2],
                scope_team=key[3],
                reason_tag=key[4],
                total_count=counts["total"],
                up_count=counts["up"],
                down_count=counts["down"],
                pending_count=counts["pending"],
                approved_count=counts["approved"],
                rejected_count=counts["rejected"],
            )
            for key, counts in sorted(
                grouped.items(),
                key=lambda item: (-item[1]["total"], item[0]),
            )
        ]
        return AiFeedbackClustersResponse(
            success=True,
            total_traces=matched_total,
            clusters=clusters,
        )

    def purge_expired_feedback(
        self,
        *,
        caller_role: str,
        caller_user_id: str | None,
        retention_days: int | None = None,
        dry_run: bool = False,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> AiFeedbackPurgeResponse:
        """Delete feedback/trace rows older than the configured retention window (default 90d, clamped 1..365)."""
        if str(caller_role or "") != "Admin":
            raise PermissionError("Only Admin reviewers can purge expired AI feedback traces.")

        ensure_trace_schema_once(self.db)
        days = _resolve_retention_days(retention_days)
        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - timedelta(days=days)

        rows = self.db.query(AiInteractionTrace).all()
        expired_rows = [
            row for row in rows
            if (created_utc := _as_utc(row.created_at)) is not None and created_utc < cutoff
        ]
        matched_count = len(expired_rows)
        purged_count = 0

        if not dry_run and expired_rows:
            for row in expired_rows:
                self.db.delete(row)
            self.db.commit()
            purged_count = matched_count

        actor_uuid = _parse_optional_uuid(caller_user_id)
        new_values: dict[str, Any] = {
            "retention_days": days,
            "dry_run": bool(dry_run),
            "cutoff_iso": cutoff.isoformat(),
            "matched_count": matched_count,
            "purged_count": purged_count,
        }
        if actor_uuid is None and caller_user_id:
            new_values["actor_user_id"] = str(caller_user_id)

        _ensure_audit_table_in_nonprod(self.db)
        AuditService.log_operation(
            self.db,
            table_name="ai_interaction_traces",
            operation="AI_FEEDBACK_PURGE",
            record_id=str(uuid.uuid4()),
            old_values=None,
            new_values=new_values,
            performed_by_user_id=actor_uuid,
            ip_address=ip_address,
            request_id=request_id,
        )

        return AiFeedbackPurgeResponse(
            success=True,
            retention_days=days,
            dry_run=bool(dry_run),
            matched_count=matched_count,
            purged_count=purged_count,
            cutoff_iso=cutoff.isoformat(),
        )

    def delete_feedback_trace(
        self,
        *,
        trace_id: str,
        caller_role: str,
        caller_user_id: str | None,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> bool:
        """Admin-only hard deletion of a single AI feedback trace with audit record."""
        if str(caller_role or "") != "Admin":
            raise PermissionError("Only Admin reviewers can delete AI feedback traces.")

        ensure_trace_schema_once(self.db)
        parsed_id = _parse_optional_uuid(trace_id)
        if not parsed_id:
            return False

        row = (
            self.db.query(AiInteractionTrace)
            .filter(AiInteractionTrace.id == uuid.UUID(parsed_id))
            .first()
        )
        if not row:
            return False

        meta = self._extract_gov_meta(row)
        old_values = {
            "surface": meta.get("surface", "workspace_chat"),
            "rating": row.feedback_rating,
            "review_status": meta.get("review_status", "pending"),
        }
        self.db.delete(row)
        self.db.commit()

        actor_uuid = _parse_optional_uuid(caller_user_id)
        new_values: dict[str, Any] = {"deleted": True}
        if actor_uuid is None and caller_user_id:
            new_values["actor_user_id"] = str(caller_user_id)

        _ensure_audit_table_in_nonprod(self.db)
        AuditService.log_operation(
            self.db,
            table_name="ai_interaction_traces",
            operation="AI_FEEDBACK_DELETE",
            record_id=parsed_id,
            old_values=old_values,
            new_values=new_values,
            performed_by_user_id=actor_uuid,
            ip_address=ip_address,
            request_id=request_id,
        )
        return True

    def _compute_cohort_size(
        self,
        *,
        scope_country: str | None,
        scope_team: str | None,
        performance_level: str | None,
        gov_meta: dict[str, Any],
    ) -> int:
        if not (scope_team or scope_country or performance_level):
            meta_size = gov_meta.get("cohort_size")
            if isinstance(meta_size, int) and not isinstance(meta_size, bool) and meta_size >= 0:
                return meta_size
            return 0

        try:
            q = (
                self.db.query(func.count(func.distinct(Employee.id)))
                .join(Team, Employee.team_id == Team.id)
            )
            if scope_team:
                team_cf = scope_team.strip().casefold()
                q = q.filter(or_(func.lower(Team.name) == team_cf, func.lower(Team.display_name) == team_cf))
            if scope_country:
                q = q.filter(func.lower(Employee.region) == scope_country.strip().casefold())
            if performance_level:
                q = q.filter(func.lower(Employee.performance_level) == performance_level.strip().casefold())
            emp_count = int(q.scalar() or 0)
            if emp_count > 0:
                return emp_count

            pq = (
                self.db.query(func.count(func.distinct(PerformanceRecord.employee_id)))
                .join(Team, PerformanceRecord.team_id == Team.id)
            )
            if scope_team:
                team_cf = scope_team.strip().casefold()
                pq = pq.filter(or_(func.lower(Team.name) == team_cf, func.lower(Team.display_name) == team_cf))
            if scope_country:
                pq = pq.filter(func.lower(PerformanceRecord.region) == scope_country.strip().casefold())
            if performance_level:
                pq = pq.filter(func.lower(PerformanceRecord.performance_level) == performance_level.strip().casefold())
            perf_count = int(pq.scalar() or 0)
            if perf_count > 0:
                return perf_count
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass

        meta_size = gov_meta.get("cohort_size")
        if isinstance(meta_size, int) and not isinstance(meta_size, bool) and meta_size >= 0:
            return meta_size
        return 0

    def build_deidentified_export_bundle(
        self,
        *,
        caller_role: str,
        caller_user_id: str | None,
        approved_only: bool = True,
        min_cohort_size: int = MIN_EXPORT_COHORT_SIZE,
        limit: int = 500,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> AiDeidentifiedExportBundleResponse:
        """Export Admin-approved feedback items while enforcing k>=5 cohort anonymity and PII quarantine."""
        if str(caller_role or "") != "Admin":
            raise PermissionError("Only Admin reviewers can export AI feedback bundles.")
        if not approved_only:
            raise ValueError("Only administrator-approved feedback items may be exported.")
        if min_cohort_size < MIN_EXPORT_COHORT_SIZE:
            raise ValueError(f"min_cohort_size must be at least {MIN_EXPORT_COHORT_SIZE} to prevent small-cohort re-identification.")

        ensure_trace_schema_once(self.db)
        _names, tokens = self._name_tokens()
        rows = (
            self.db.query(AiInteractionTrace)
            .filter(AiInteractionTrace.reviewer_verified.is_(True))
            .order_by(AiInteractionTrace.created_at.desc())
            .limit(max(1, min(limit, 2000)))
            .all()
        )

        items: list[AiDeidentifiedExportItem] = []
        blocked_small_cohort = 0
        blocked_pii = 0

        for row in rows:
            meta = self._extract_gov_meta(row)
            review_status = str(meta.get("review_status") or ("approved" if row.reviewer_verified else "pending"))
            if review_status != "approved":
                continue

            session_dict = row.session_state if isinstance(row.session_state, dict) else {}
            scope_team = self._sanitize_scope_label(
                meta.get("scope_team") or session_dict.get("team"),
                tokens=tokens,
                max_len=120,
            )
            scope_country = self._sanitize_scope_label(
                meta.get("scope_country") or session_dict.get("region"),
                tokens=tokens,
                max_len=80,
            )
            performance_level = self._sanitize_scope_label(
                meta.get("performance_level") or session_dict.get("performance_level"),
                tokens=tokens,
                max_len=40,
            )

            cohort_size = self._compute_cohort_size(
                scope_country=scope_country,
                scope_team=scope_team,
                performance_level=performance_level,
                gov_meta=meta,
            )
            if cohort_size < min_cohort_size:
                blocked_small_cohort += 1
                continue

            raw_comment = meta.get("comment_redacted") or row.feedback_reason or ""
            sanitized_comment = self._sanitize_text(raw_comment, tokens=tokens, max_len=_COMMENT_MAX_LEN)
            quarantined, q_reasons = assess_pii_quarantine(
                sanitized_comment or "",
                original_text=str(raw_comment),
                _precomputed_tokens=tokens,
            )
            has_residual = any(r.startswith("residual_") for r in q_reasons)
            if quarantined or has_residual or bool(meta.get("pii_quarantined")):
                blocked_pii += 1
                continue

            clean_evidence = self._sanitize_evidence_ids(
                meta.get("evidence_ids") if isinstance(meta.get("evidence_ids"), list) else [],
                tokens=tokens,
            )
            clean_action = self._sanitize_text(meta.get("proposed_action"), tokens=tokens, max_len=_NOTES_MAX_LEN)

            items.append(
                AiDeidentifiedExportItem(
                    trace_id=str(row.id),
                    created_at=row.created_at.isoformat() if row.created_at else "",
                    surface=str(meta.get("surface") or "workspace_chat"),
                    rating=row.feedback_rating or meta.get("rating"),
                    reason_tag=meta.get("reason_tag"),
                    comment=sanitized_comment,
                    candidate_sha=meta.get("candidate_sha"),
                    model_version=meta.get("model_version") or row.model_name,
                    provider_name=str(meta.get("provider_name") or row.provider_name or "deterministic"),
                    fallback_reason=meta.get("fallback_reason"),
                    operation_family=meta.get("operation_family"),
                    scope_team=scope_team,
                    scope_country=scope_country,
                    performance_level=performance_level,
                    cohort_size=cohort_size,
                    evidence_ids=clean_evidence,
                    review_status="approved",
                    proposed_action=clean_action,
                )
            )

        actor_uuid = _parse_optional_uuid(caller_user_id)
        new_values: dict[str, Any] = {
            "approved_only": True,
            "min_cohort_size": min_cohort_size,
            "exported_count": len(items),
            "blocked_small_cohort_count": blocked_small_cohort,
            "blocked_pii_count": blocked_pii,
        }
        if actor_uuid is None and caller_user_id:
            new_values["actor_user_id"] = str(caller_user_id)

        _ensure_audit_table_in_nonprod(self.db)
        AuditService.log_operation(
            self.db,
            table_name="ai_interaction_traces",
            operation="AI_FEEDBACK_EXPORT_BUNDLE",
            record_id=str(uuid.uuid4()),
            old_values=None,
            new_values=new_values,
            performed_by_user_id=actor_uuid,
            ip_address=ip_address,
            request_id=request_id,
        )

        return AiDeidentifiedExportBundleResponse(
            success=True,
            approved_only=True,
            min_cohort_size=min_cohort_size,
            exported_count=len(items),
            blocked_small_cohort_count=blocked_small_cohort,
            blocked_pii_count=blocked_pii,
            items=items,
        )


def classify_bundle_offline_optional(
    bundle: AiDeidentifiedExportBundleResponse | list[dict[str, Any]],
    *,
    policy_attested: bool = False,
    classifier_fn: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """CLI/batch-only optional offline classification helper.

    Disabled by default unless ``PMS_AI_EXTERNAL_REVIEW_ENABLED=true``,
    ``policy_attested=True``, and ``APP_ENV != "production"``.
    Rejects non-deidentified items and never auto-applies classifications.
    """
    enabled = os.environ.get("PMS_AI_EXTERNAL_REVIEW_ENABLED", "false").strip().casefold() in _TRUTHY
    app_env = os.environ.get("APP_ENV", "").strip().casefold()

    if not enabled or not policy_attested or app_env == "production":
        return {
            "status": "disabled_by_policy",
            "reason": "External offline bundle classification requires PMS_AI_EXTERNAL_REVIEW_ENABLED=true, policy_attested=True, and non-production APP_ENV.",
            "review_required": True,
            "auto_applied": False,
            "classified": [],
        }

    raw_items = (
        [item.model_dump() for item in bundle.items]
        if isinstance(bundle, AiDeidentifiedExportBundleResponse)
        else list(bundle)
    )

    clean_items: list[dict[str, Any]] = []
    rejected_items: list[str] = []
    forbidden_keys = {"employee_id", "employee_name", "user_id", "email", "phone"}

    for item in raw_items:
        if any(k in item and item[k] for k in forbidden_keys):
            rejected_items.append(str(item.get("trace_id") or "unknown"))
            continue
        cohort_size = item.get("cohort_size", 0)
        if not isinstance(cohort_size, int) or cohort_size < MIN_EXPORT_COHORT_SIZE:
            rejected_items.append(str(item.get("trace_id") or "unknown"))
            continue
        text_blob = " ".join(str(item.get(f) or "") for f in ("comment", "proposed_action", "scope_team"))
        quarantined, _reasons = assess_pii_quarantine(text_blob, original_text=text_blob)
        if quarantined:
            rejected_items.append(str(item.get("trace_id") or "unknown"))
            continue
        clean_items.append(redact_nested_payload(item))

    if rejected_items:
        return {
            "status": "rejected_non_deidentified",
            "reason": "Bundle contained non-deidentified or small-cohort items.",
            "rejected_trace_ids": rejected_items,
            "review_required": True,
            "auto_applied": False,
            "classified": [],
        }

    if classifier_fn is not None:
        proposals = classifier_fn(clean_items)
    else:
        proposals = [
            {
                "trace_id": item.get("trace_id"),
                "suggested_cluster": item.get("reason_tag") or "other",
                "suggested_action": item.get("proposed_action") or "human_review_required",
            }
            for item in clean_items
        ]

    tagged = [
        {
            **dict(p),
            "review_required": True,
            "auto_applied": False,
        }
        for p in proposals
    ]

    return {
        "status": "completed",
        "review_required": True,
        "auto_applied": False,
        "classified": tagged,
    }
