"""Deterministic admin-approved routing patterns derived from verified PMS feedback."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from models.ai_schemas import AiApprovedPatternItem, AiApprovePatternRequest
from models.models import AiApprovedPattern, AiInteractionTrace, AuditLog
from services.ai.config import redact_secrets
from services.ai.domain_policies import MONTH_ALIASES
from services.ai.feedback_service import FeedbackGovernanceService
from services.ai.trace_logger import (
    _build_name_token_set,
    assess_pii_quarantine,
    sanitize_prompt_for_router_training,
)
from services.audit_service import AuditService

_CANONICAL_TEAM_PHRASES: tuple[str, ...] = (
    "pre-approvals ip offshore",
    "pre-approvals op final shjajm",
    "pre-approvals ip final shjajm",
    "pre-approvals op dubai",
    "pre-approvals ip final dubai",
    "pre-approvals ip elective dubai",
    "pre-approvals op final",
    "pre-approvals ip final",
    "pre-approvals ip elective",
    "support positions",
    "quality assurance",
    "submission egy",
    "coding egy",
    "re-submission",
    "resubmission",
    "pre-approvals",
    "call center",
    "inbound",
    "outbound",
    "submission",
    "coding",
    "workforce",
    "trainer",
    "rcm",
    "csr",
    "pharmacy",
    "marketing",
    "sales",
    "finance",
    "nursing",
    "crm",
    "pmo",
)

_CANONICAL_BRANCH_PHRASES: tuple[str, ...] = (
    "dubai",
    "sharjah",
    "ajman",
    "clinics",
    "clinic",
    "al ain",
    "shj",
    "dxb",
    "ajm",
)

_CANONICAL_REGION_PHRASES: tuple[str, ...] = (
    "uae",
    "emirates",
    "egy",
    "egypt",
)

_FILLER_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "give",
        "how",
        "i",
        "in",
        "is",
        "it",
        "let",
        "me",
        "of",
        "on",
        "or",
        "our",
        "please",
        "show",
        "tell",
        "that",
        "the",
        "their",
        "there",
        "this",
        "to",
        "us",
        "was",
        "we",
        "were",
        "what",
        "whats",
        "which",
        "who",
        "whos",
        "would",
        "you",
    }
)

_STEM_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:top\s+performers?|best\s+agents?|best\s+performers?|#?1\s+top\s+performer|highest\s+scoring\s+(?:agent|employee|person)|leading\s+(?:agent|person)?|star\s+performer|standout\s+agent|most\s+bookings?\s+(?:agent|leader)?|bookings?\s+leader)\b"), " <RANK_TOP> "),
    (re.compile(r"\b(?:weakest|worst|lowest\s+scoring|bottom\s+(?:agent|performer)|underperforming|lagging\s+(?:agent|performer)|trailing\s+(?:agent|performer))\b"), " <RANK_BOTTOM> "),
    (re.compile(r"\b(?:why\s+did|what\s+caused|what\s+drove|what\s+pulled|dragging|pulling\s+down|reasons?\s+for|factors?\s+behind|behind\s+the\s+drop|explain\s+why|explain\s+the\s+drop)\b"), " <CAUSE_DRIVERS> "),
    (re.compile(r"\b(?:scorecard|kpi\s+breakdown|kpi\s+weights?|weighted\s+metrics?|metrics?\s+included|kpi\s+structure|evaluation\s+criteria)\b"), " <SCORECARD_STRUCTURE> "),
    (re.compile(r"\b(?:compare|comparison|versus|vs\.?|against|difference\s+between)\b"), " <COMPARE> "),
    (re.compile(r"\b(?:6[\-\s]?month|six[\-\s]?month|trend|trajectory|progression|over\s+time|month\s+by\s+month|multi[\-\s]?month)\b"), " <TREND> "),
    (re.compile(r"\b(?:drop|dropped|dropping|declined|decline|fell|fall|dip|dipped|slipped|decrease|decreased)\b"), " <DROP> "),
    (re.compile(r"\b(?:total\s+bookings?|booking\s+count|appointments?\s+booked|bookings?)\b"), " <METRIC_BOOKINGS> "),
    (re.compile(r"\b(?:overall\s+pms\s+score|overall\s+score|pms\s+score|score|performance|evaluation|rating)\b"), " <SCORE> "),
)

_ANCHOR_TOKENS: tuple[str, ...] = (
    "<RANK_TOP>",
    "<RANK_BOTTOM>",
    "<CAUSE_DRIVERS>",
    "<SCORECARD_STRUCTURE>",
    "<COMPARE>",
    "<TREND>",
    "<METRIC_BOOKINGS>",
)


@dataclass
class PatternMatchResult:
    pattern_id: str
    intent: str
    operation_kind: str | None
    requested_parts: list[str]
    tool_choice: str | None
    metric_hint: str | None
    normalized_pattern: str
    score: float


def normalize_pattern_prompt(
    prompt: str,
    known_employee_names: list[str] | None = None,
) -> str:
    """Redact PII/entities and canonicalize PMS phrasing into a reusable deterministic pattern."""
    raw = str(prompt or "").strip()
    if not raw:
        return ""
    tokens = _build_name_token_set(known_employee_names or [])
    sanitized = sanitize_prompt_for_router_training(
        raw,
        known_employee_names=known_employee_names,
        run_syntactic_extraction=False,
        _precomputed_tokens=tokens,
    )
    sanitized = sanitized.replace("<EMPLOYEE_NAME>", " <PERSON> ").replace("<EMPLOYEE_ID>", " <PERSON> ")
    text = sanitized.casefold()

    for team_phrase in sorted(_CANONICAL_TEAM_PHRASES, key=len, reverse=True):
        text = re.sub(rf"(?<![a-z0-9\-]){re.escape(team_phrase)}(?![a-z0-9\-])", " <TEAM> ", text)

    for branch_phrase in sorted(_CANONICAL_BRANCH_PHRASES, key=len, reverse=True):
        text = re.sub(rf"(?<![a-z0-9]){re.escape(branch_phrase)}(?![a-z0-9])", " <BRANCH> ", text)

    for region_phrase in sorted(_CANONICAL_REGION_PHRASES, key=len, reverse=True):
        text = re.sub(rf"(?<![a-z0-9]){re.escape(region_phrase)}(?![a-z0-9])", " <REGION> ", text)

    for month_alias in sorted(MONTH_ALIASES.keys(), key=len, reverse=True):
        text = re.sub(rf"(?<![a-z0-9]){re.escape(month_alias)}(?![a-z0-9])", " <MONTH> ", text)

    text = re.sub(r"\b20\d{2}\b", " <YEAR> ", text)
    text = re.sub(r"\b(?:agents?|employees?|staff|reps?|people)\b", " <AGENT> ", text)

    for pat, repl in _STEM_REPLACEMENTS:
        text = pat.sub(repl, text)

    text = re.sub(r"\b\d+(?:\.\d+)?\b", " <NUM> ", text)
    text = re.sub(r"[?!.,:;\"'()\[\]{}]+", " ", text)

    out_tokens: list[str] = []
    for tok in text.split():
        if tok in _FILLER_WORDS:
            continue
        if out_tokens and out_tokens[-1] == tok and tok.startswith("<"):
            continue
        out_tokens.append(tok)
    return " ".join(out_tokens)


def _pattern_to_schema(row: AiApprovedPattern) -> AiApprovedPatternItem:
    parts = list(row.requested_parts) if isinstance(row.requested_parts, list) else None
    return AiApprovedPatternItem(
        id=str(row.id),
        source_trace_id=row.source_trace_id,
        normalized_pattern=row.normalized_pattern,
        example_prompt_redacted=row.example_prompt_redacted,
        intent=row.intent,
        operation_kind=row.operation_kind,
        requested_parts=parts,
        tool_choice=row.tool_choice,
        metric_hint=row.metric_hint,
        failure_category=row.failure_category,
        verified_against_pms=bool(row.verified_against_pms),
        approved_by_user_id=row.approved_by_user_id,
        review_notes=row.review_notes,
        is_active=bool(row.is_active),
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


def _ensure_pattern_tables_in_nonprod(db: Session) -> None:
    import os

    app_env = os.environ.get("APP_ENV", "").strip().casefold()
    disable_ddl = os.environ.get("PMS_DISABLE_RUNTIME_DDL", "").strip().casefold() in {"1", "true", "yes", "on", "enabled"}
    if app_env in ("production", "staging", "prod", "stage") or disable_ddl:
        return
    try:
        bind = db.get_bind()
        AiApprovedPattern.__table__.create(bind=bind, checkfirst=True)
        AuditLog.__table__.create(bind=bind, checkfirst=True)
    except Exception:
        pass


class ApprovedPatternMatcher:
    """Matches incoming user prompts against Admin-approved, PMS-verified routing patterns."""

    def __init__(self, db: Session | None) -> None:
        self.db = db

    def list_patterns(self, *, active_only: bool = True) -> list[AiApprovedPatternItem]:
        if self.db is None:
            return []
        try:
            q = self.db.query(AiApprovedPattern)
            if active_only:
                q = q.filter(AiApprovedPattern.is_active.is_(True))
            rows = q.order_by(AiApprovedPattern.created_at.desc()).all()
            return [_pattern_to_schema(r) for r in rows]
        except Exception:
            return []

    def match_prompt(
        self,
        prompt: str,
        *,
        known_employee_names: list[str] | None = None,
        persona_tier: str | None = None,
    ) -> PatternMatchResult | None:
        if self.db is None or not str(prompt or "").strip():
            return None
        norm_in = normalize_pattern_prompt(prompt, known_employee_names=known_employee_names)
        if not norm_in:
            return None
        in_tokens = set(norm_in.split())
        in_anchors = {t for t in in_tokens if t in _ANCHOR_TOKENS}
        in_core = {
            t for t in in_tokens
            if t not in {"<PERSON>", "<TEAM>", "<BRANCH>", "<REGION>", "<MONTH>", "<YEAR>", "<NUM>", "<AGENT>"}
        }

        try:
            rows = (
                self.db.query(AiApprovedPattern)
                .filter(
                    AiApprovedPattern.is_active.is_(True),
                    AiApprovedPattern.verified_against_pms.is_(True),
                )
                .order_by(AiApprovedPattern.created_at.desc())
                .all()
            )
        except Exception:
            return None

        best: PatternMatchResult | None = None
        for row in rows:
            row_tier = getattr(row, "persona_tier", None)
            if row_tier:
                if not persona_tier or str(row_tier) != str(persona_tier):
                    continue
            pat_str = str(row.normalized_pattern or "").strip()
            if not pat_str:
                continue
            if pat_str == norm_in:
                return PatternMatchResult(
                    pattern_id=str(row.id),
                    intent=str(row.intent),
                    operation_kind=row.operation_kind,
                    requested_parts=list(row.requested_parts) if isinstance(row.requested_parts, list) else [str(row.intent)],
                    tool_choice=row.tool_choice,
                    metric_hint=row.metric_hint,
                    normalized_pattern=pat_str,
                    score=1.0,
                )

            pat_tokens = set(pat_str.split())
            pat_anchors = {t for t in pat_tokens if t in _ANCHOR_TOKENS}
            if pat_anchors and in_anchors and not (pat_anchors & in_anchors):
                continue
            # Never confuse top vs bottom or drivers vs scorecard
            if ("<RANK_TOP>" in pat_anchors and "<RANK_BOTTOM>" in in_anchors) or (
                "<RANK_BOTTOM>" in pat_anchors and "<RANK_TOP>" in in_anchors
            ):
                continue

            pat_core = {
                t for t in pat_tokens
                if t not in {"<PERSON>", "<TEAM>", "<BRANCH>", "<REGION>", "<MONTH>", "<YEAR>", "<NUM>", "<AGENT>"}
            }
            if not in_core or not pat_core:
                continue

            inter_core = len(in_core & pat_core)
            union_core = len(in_core | pat_core)
            core_jaccard = inter_core / union_core if union_core else 0.0
            full_union = len(in_tokens | pat_tokens)
            full_jaccard = len(in_tokens & pat_tokens) / full_union if full_union else 0.0
            score = round(0.65 * core_jaccard + 0.35 * full_jaccard, 4)

            if score >= 0.72 and (best is None or score > best.score):
                best = PatternMatchResult(
                    pattern_id=str(row.id),
                    intent=str(row.intent),
                    operation_kind=row.operation_kind,
                    requested_parts=list(row.requested_parts) if isinstance(row.requested_parts, list) else [str(row.intent)],
                    tool_choice=row.tool_choice,
                    metric_hint=row.metric_hint,
                    normalized_pattern=pat_str,
                    score=score,
                )
        return best

    def approve_pattern_from_trace(
        self,
        *,
        trace_id: str,
        payload: AiApprovePatternRequest,
        approver_user_id: str,
        caller_role: str,
        known_employee_names: list[str] | None = None,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> tuple[AiApprovedPatternItem, Any]:
        if caller_role != "Admin":
            raise PermissionError("Only Admin reviewers can approve AI routing patterns.")
        if not payload.verified_against_pms:
            raise ValueError("Patterns must be explicitly verified against live PMS data (verified_against_pms=True).")

        _ensure_pattern_tables_in_nonprod(self.db)
        try:
            parsed_uuid = uuid.UUID(str(trace_id).strip())
        except (TypeError, ValueError, AttributeError) as exc:
            raise LookupError("Interaction trace not found") from exc

        row = (
            self.db.query(AiInteractionTrace)
            .filter(AiInteractionTrace.id == parsed_uuid)
            .with_for_update()
            .first()
        )
        if not row:
            raise LookupError("Interaction trace not found")

        all_names = list(known_employee_names or [])
        try:
            from services.ai.trace_logger import TrainingTraceLogger
            all_names = TrainingTraceLogger(self.db)._collect_known_employee_names(all_names)
        except Exception:
            pass
        name_tokens = _build_name_token_set(all_names)

        raw_example = (
            payload.corrected_pattern_prompt
            or row.sanitized_prompt
            or row.prompt
            or ""
        ).strip()
        if not raw_example:
            raise ValueError("A non-empty pattern prompt is required.")

        example_redacted = sanitize_prompt_for_router_training(
            raw_example,
            known_employee_names=all_names,
            run_syntactic_extraction=True,
            _precomputed_tokens=name_tokens,
        )
        example_redacted = redact_secrets(example_redacted).strip()
        if "<EMAIL>" in example_redacted or "<PHONE>" in example_redacted:
            raise ValueError(
                "Pattern prompt contains email or phone PII; remove personal contact details before approving."
            )
        quarantined, q_reasons = assess_pii_quarantine(
            example_redacted,
            original_text=example_redacted,
            _precomputed_tokens=name_tokens,
        )
        if quarantined:
            raise ValueError(
                f"Pattern prompt failed PII check ({', '.join(q_reasons)}); remove personal identifiers before approving."
            )

        normalized_pat = normalize_pattern_prompt(example_redacted, known_employee_names=all_names)
        if not normalized_pat:
            raise ValueError("Pattern normalized to empty text; provide descriptive query wording.")
        norm_quarantined, norm_reasons = assess_pii_quarantine(
            normalized_pat,
            original_text=normalized_pat,
            _precomputed_tokens=name_tokens,
        )
        if norm_quarantined:
            raise ValueError(
                f"Normalized pattern failed PII check ({', '.join(norm_reasons)})."
            )

        if row.feedback_rating not in ("up", "down"):
            raise ValueError("Collect feedback on this answer before approving a pattern.")

        existing = (
            self.db.query(AiApprovedPattern)
            .filter_by(source_trace_id=str(row.id), normalized_pattern=normalized_pat, is_active=True)
            .first()
        )
        if existing is not None:
            raise ValueError("An active pattern already exists for this feedback. Deactivate it before replacing it.")

        review_res = FeedbackGovernanceService(self.db).review_feedback(
            trace_id=str(row.id),
            reviewer_verified=True,
            decision="approved",
            reviewer_id=approver_user_id,
            caller_role=caller_role,
            notes=payload.review_notes or f"Approved routing pattern ({payload.intent})",
            proposed_action=f"pattern:{payload.intent}",
            ip_address=ip_address,
            request_id=request_id,
            commit=False,
        )

        pat_row = AiApprovedPattern(
            id=str(uuid.uuid4()),
            source_trace_id=str(row.id),
            normalized_pattern=normalized_pat,
            example_prompt_redacted=example_redacted,
            intent=payload.intent.strip()[:64],
            operation_kind=payload.operation_kind.strip()[:64] if payload.operation_kind else None,
            requested_parts=list(payload.requested_parts) if payload.requested_parts else [payload.intent.strip()[:64]],
            tool_choice=payload.tool_choice.strip()[:80] if payload.tool_choice else None,
            metric_hint=payload.metric_hint.strip()[:120] if payload.metric_hint else None,
            failure_category=payload.failure_category.strip()[:64] if payload.failure_category else None,
            verified_against_pms=True,
            approved_by_user_id=str(approver_user_id or "admin")[:100],
            review_notes=(
                redact_secrets(sanitize_prompt_for_router_training(
                    payload.review_notes,
                    known_employee_names=all_names,
                    _precomputed_tokens=name_tokens,
                ))[:240]
                if payload.review_notes else None
            ),
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(pat_row)

        try:
            actor_uuid = uuid.UUID(str(approver_user_id).strip())
        except Exception:
            actor_uuid = None
        AuditService.log_operation(
            self.db,
            table_name="ai_approved_patterns",
            operation="AI_APPROVED_PATTERN_CREATE",
            record_id=str(pat_row.id),
            old_values=None,
            new_values={
                "source_trace_id": pat_row.source_trace_id,
                "intent": pat_row.intent,
                "operation_kind": pat_row.operation_kind,
                "metric_hint": pat_row.metric_hint,
                "verified_against_pms": True,
            },
            performed_by_user_id=actor_uuid,
            ip_address=ip_address,
            request_id=request_id,
        )

        return _pattern_to_schema(pat_row), review_res

    def deactivate_pattern(
        self,
        *,
        pattern_id: str,
        actor_user_id: str,
        caller_role: str,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> bool:
        if caller_role != "Admin":
            raise PermissionError("Only Admin reviewers can delete AI routing patterns.")
        _ensure_pattern_tables_in_nonprod(self.db)
        row = self.db.query(AiApprovedPattern).filter(AiApprovedPattern.id == pattern_id).first()
        if not row:
            return False
        old_active = bool(row.is_active)
        if not old_active:
            return True
        row.is_active = False

        try:
            actor_uuid = uuid.UUID(str(actor_user_id).strip())
        except Exception:
            actor_uuid = None
        AuditService.log_operation(
            self.db,
            table_name="ai_approved_patterns",
            operation="AI_APPROVED_PATTERN_DELETE",
            record_id=str(row.id),
            old_values={"is_active": old_active},
            new_values={"is_active": False},
            performed_by_user_id=actor_uuid,
            ip_address=ip_address,
            request_id=request_id,
        )
        return True
