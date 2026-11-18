"""Shared Contextual AI Assistant engine for PMS pages (Monthly Presentation, Team Dashboard, AI Workspace).

Provides:
1. PageContextV1 normalization, precedence merging, and server-side scope pre-authorization.
2. Capability routing across page_help, navigation, performance_query, clarification, proposal, and unsupported.
3. Curated, role-aware page help and navigation catalog (zero performance record reads).
4. Fallback/sample data guardrails (never treating sample data as verified PMS facts or action evidence).
5. Evidence-grounded corrective action proposal builder and live-revalidated confirmation via CorrectiveActionService / TeamActionService.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from models.ai_schemas import (
    AiChatRequest,
    AiChatResponsePayload,
    AiCorrectiveActionConfirmRequest,
    AiCorrectiveActionConfirmResponse,
    AiCorrectiveActionProposal,
    AiNavigationTarget,
    AiPageHelpSection,
    ConfirmedQueryContext,
    ContextualCapabilityMode,
    DeepLinkCta,
    PageContextV1,
    QueryOperationV2,
    QueryScopeV2,
    SessionFilterContext,
    SourceCitationPill,
    TypedMetricEvidence,
    ValidatedQueryPlanV2,
)
from models.models import Employee, Team
from services.ai.catalog import evaluation_cache_identity, function_for_team, get_ai_catalog
from services.ai.conversation_service import AiConversationService
from services.ai.prompt_versions import EXPLAIN_PREVIOUS_PROMPT_VERSION
from services.ai.domain_policies import (
    has_pms_performance_signal,
    is_bare_scope_or_period_refinement,
    is_capabilities_help_prompt,
    is_explain_previous_prompt,
    is_explicit_correction_prompt,
    is_greeting_or_thanks_prompt,
    is_off_topic_prompt,
    is_vague_dataless_prompt,
)
from services.ai.llm_client import local_synthesis_enabled, synthesis_timeout_seconds
from services.ai.local_model_router import (
    BoundedIntentContext,
    LocalIntentResult,
    call_suggest_intent,
    local_intent_enabled,
    suggest_intent,
)
from services.ai.provider_engine import ProviderMessage, ProviderRequest, get_unified_provider_engine
from services.ai.providers import resolve_variation_index
from services.cache_invalidation_service import CacheInvalidationService
from services.corrective_action_service import (
    ACTION_PRIORITIES,
    ACTION_TYPES,
    CorrectiveActionAccessError,
    CorrectiveActionNotFoundError,
    CorrectiveActionService,
    CorrectiveActionValidationError,
)
from services.team_action_service import TeamActionService
from utils.report_scope import user_can_access_team, user_can_access_team_level


def is_self_only(scope: dict[str, Any]) -> bool:
    return bool(
        scope.get("self_only")
        or scope.get("is_self_only")
        or str(scope.get("role") or "").strip().casefold() in {"employee", "agent"}
    )


ACTION_WRITE_ROLES: frozenset[str] = frozenset(
    {"Admin", "General Manager", "Manager", "Performance Team"}
)

UPLOAD_WRITE_ROLES: frozenset[str] = frozenset({"Admin", "Manager"})
SETTINGS_ADMIN_ROLES: frozenset[str] = frozenset({"Admin"})

_TEAM_SLUG_TO_CANONICAL: dict[str, str] = {
    "inbound": "Inbound",
    "outbound": "Outbound",
    "support": "Support Positions",
    "support-positions": "Support Positions",
    "support_positions": "Support Positions",
    "coding": "Coding",
    "coding-egy": "Coding EGY",
    "submission": "Submission",
    "submission-egy": "Submission EGY",
    "re-submission": "Re-Submission",
    "resubmission": "Resubmission",
    "collections": "Collections",
    "denial-management": "Denial Management",
    "pre-approvals-ip": "Pre-Approvals IP",
    "pre-approvals-ip-offshore": "Pre-Approvals IP Offshore",
    "pre-approvals": "Pre-Approvals IP Offshore",
    "pre-approvals-op-dubai": "Pre-Approvals OP Dubai",
    "pre-approvals-op-final": "Pre-Approvals OP Dubai",
    "pre-approvals-ip-final-dubai": "Pre-Approvals IP Final Dubai",
    "pre-approvals-ip-final": "Pre-Approvals IP Final Dubai",
    "pre-approvals-ip-elective": "Pre-Approvals IP Elective Dubai",
    "pre-approvals-ip-elective-dubai": "Pre-Approvals IP Elective Dubai",
    "marketing": "Marketing",
    "pharmacy": "Pharmacy",
    "csr": "CSR",
    "sales": "Sales",
}

_FUNCTION_SLUG_TO_CANONICAL: dict[str, str] = {
    "call-center": "Call Center",
    "call_center": "Call Center",
    "call center": "Call Center",
    "rcm": "RCM",
    "pre-approvals": "Pre-Approvals",
    "pre-approvals-uae": "Pre-Approvals",
    "pre_approvals": "Pre-Approvals",
    "marketing": "Marketing",
    "pharmacy": "Pharmacy",
    "csr": "CSR",
    "sales": "Sales",
}

_MONTH_NUM_TO_NAME: dict[int, str] = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}

_MONTH_NAME_TO_NUM: dict[str, int] = {name.casefold(): num for num, name in _MONTH_NUM_TO_NAME.items()}
_MONTH_NAME_TO_NUM.update({name[:3].casefold(): num for num, name in _MONTH_NUM_TO_NAME.items()})
_MONTH_NAME_TO_NUM["sept"] = 9


class ProposalStaleEvidenceError(RuntimeError):
    """Raised when underlying PMS evaluations changed after a proposal was generated."""


def _current_evidence_revision(db: Session) -> str:
    return f"{evaluation_cache_identity(db)}:d{CacheInvalidationService.get_data_version()}"


def normalize_team_name(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip()
    if not cleaned or cleaned.casefold() in {"all", "all teams", "none"}:
        return None
    slug = cleaned.casefold().replace("_", "-").replace(" ", "-")
    if slug in {"call-center", "rcm", "pre-approvals-uae"}:
        return None
    if slug in _TEAM_SLUG_TO_CANONICAL:
        return _TEAM_SLUG_TO_CANONICAL[slug]
    return cleaned


def normalize_function_name(raw: str | None, team: str | None = None) -> str | None:
    if raw:
        cleaned = raw.strip()
        if cleaned and cleaned.casefold() not in {"all", "all functions", "none"}:
            slug = cleaned.casefold().replace("_", "-")
            if slug in _FUNCTION_SLUG_TO_CANONICAL:
                return _FUNCTION_SLUG_TO_CANONICAL[slug]
            return cleaned
    if team:
        return function_for_team(team)
    return None


def parse_period_to_month_year(
    period: str | None,
    month: str | None = None,
    year: int | None = None,
) -> tuple[str | None, int | None, str | None]:
    res_month = month.strip().capitalize() if month and month.strip() and month.strip().casefold() not in {"all", "latest"} else None
    res_year = year
    if period and period.strip():
        raw_p = period.strip()
        m_iso = re.match(r"^(\d{4})-(\d{1,2})$", raw_p)
        if m_iso:
            y_val = int(m_iso.group(1))
            m_num = int(m_iso.group(2))
            if 1 <= m_num <= 12:
                res_month = _MONTH_NUM_TO_NAME[m_num]
                res_year = y_val
        else:
            for token in raw_p.replace("-", " ").split():
                low_tok = token.casefold()
                if low_tok in _MONTH_NAME_TO_NUM:
                    res_month = _MONTH_NUM_TO_NAME[_MONTH_NAME_TO_NUM[low_tok]]
                elif re.match(r"^20\d{2}$", low_tok):
                    res_year = int(low_tok)
    if res_month and res_month.casefold() in _MONTH_NAME_TO_NUM:
        m_num = _MONTH_NAME_TO_NUM[res_month.casefold()]
        res_month = _MONTH_NUM_TO_NAME[m_num]
        eff_year = res_year or 2026
        return res_month, eff_year, f"{eff_year:04d}-{m_num:02d}"
    return res_month, res_year, None


def normalize_page_id(page_context: PageContextV1 | None) -> str:
    if page_context is None:
        return "ai_workspace"
    raw_id = (page_context.page_id or "").strip().casefold().replace("-", "_")
    route = (page_context.route_id or "").strip().casefold()
    if raw_id in {"monthly_presentation", "presentation"} or "monthly-presentation" in route or "/presentation" in route:
        return "monthly_presentation"
    if raw_id in {"executive_summary", "executive", "executive_overview"} or route.startswith("/executive"):
        return "executive_summary"
    if raw_id in {"function_summary", "function", "function_dashboard"} or route.startswith("/function"):
        return "function_summary"
    if raw_id in {"employee_profile", "employee_scorecard", "scorecard", "employee"} or route.startswith("/employee"):
        return "employee_profile"
    if raw_id in {"insights", "performance_insights"} or route.startswith("/insights"):
        return "insights"
    if raw_id in {"corrective_actions", "corrective_action", "actions"} or "corrective-actions" in route or route.startswith("/actions"):
        return "corrective_actions"
    if raw_id in {"team_dashboard", "departmental_summary", "team"} or route.startswith("/team") or "department" in route:
        return "team_dashboard"
    return raw_id or "ai_workspace"


def build_effective_context_label(
    *,
    page_context: PageContextV1 | None,
    session_state: SessionFilterContext,
    selected_metric_display: str | None = None,
) -> str:
    page_id = normalize_page_id(page_context)
    page_label = {
        "monthly_presentation": "Monthly Presentation",
        "team_dashboard": "Team Dashboard",
        "executive_summary": "Executive Summary",
        "function_summary": "Function Summary",
        "employee_profile": "Employee Scorecard",
        "insights": "Performance Insights",
        "corrective_actions": "Corrective Actions",
        "ai_workspace": "AI Workspace",
    }.get(page_id, "PMS Assistant")

    parts: list[str] = [page_label]
    scope_name = session_state.team or session_state.function or "All Authorized Departments"
    if session_state.position and session_state.position.casefold() not in {"all", ""}:
        scope_name = f"{scope_name} ({session_state.position})"
    parts.append(scope_name)

    if session_state.branch and session_state.branch.casefold() not in {"all", ""}:
        parts.append(session_state.branch.capitalize())

    if session_state.performance_level and session_state.performance_level.casefold() not in {"all", ""}:
        parts.append(session_state.performance_level)

    if session_state.month and session_state.year:
        parts.append(f"{session_state.month} {session_state.year}")
    elif session_state.month:
        parts.append(session_state.month)
    else:
        parts.append("Latest Period")

    if selected_metric_display:
        parts.append(selected_metric_display)
    elif page_context and page_context.selected_metric_id:
        parts.append(page_context.selected_metric_id)

    if page_context and page_context.is_fallback_data:
        parts.append("Sample Preview Data")

    return " · ".join(parts)


def can_user_write_corrective_action(
    scope: dict[str, Any],
    *,
    team: str | None = None,
    performance_level: str | None = "Employee",
    branch: str | None = None,
) -> bool:
    role = str(scope.get("role") or "").strip()
    if role not in ACTION_WRITE_ROLES:
        return False
    if is_self_only(scope):
        return False
    if role in {"Admin", "General Manager", "Performance Team"} or scope.get("has_unrestricted_team_access"):
        return True
    if not team:
        return True
    return bool(user_can_access_team_level(scope, team, performance_level or "Employee"))


def apply_page_context_to_request(req: AiChatRequest) -> tuple[AiChatRequest, str | None]:
    """Merge PageContextV1 into SessionFilterContext using strict precedence.

    Precedence:
    1. Explicit user entity/filter in prompt (handled by router)
    2. Selected entity/card in PageContextV1
    3. Active page filters in PageContextV1
    4. Confirmed conversation context
    5. Authorized defaults
    """
    pc = req.page_context
    lower_prompt = (req.prompt or "").casefold()
    explicit_egy_in_prompt = bool(re.search(r"\b(?:egy|egypt)\b", lower_prompt))
    explicit_uae_in_prompt = bool(re.search(r"\buae\b", lower_prompt))
    if pc is None:
        if explicit_egy_in_prompt or explicit_uae_in_prompt:
            ss_no_pc = req.session_state.model_copy(deep=True)
            if explicit_egy_in_prompt:
                ss_no_pc.region = "EGY"
                ss_no_pc.branch = None
            elif explicit_uae_in_prompt:
                ss_no_pc.region = "UAE"
            return req.model_copy(update={"session_state": ss_no_pc}), None
        return req, None

    ss = req.session_state.model_copy(deep=True)
    norm_team = normalize_team_name(
        pc.selected_entity_id if pc.selected_entity_type == "team" and pc.selected_entity_id else pc.team_id
    )
    norm_fn = normalize_function_name(pc.function_id, norm_team)
    norm_pos = (
        pc.selected_entity_id
        if pc.selected_entity_type == "position" and pc.selected_entity_id
        else (pc.position_id.strip() if pc.position_id and pc.position_id.strip().casefold() not in {"all", ""} else None)
    )
    norm_emp = (
        pc.selected_entity_id.strip()
        if pc.selected_entity_type == "employee" and pc.selected_entity_id
        else (pc.employee_id.strip() if pc.employee_id and pc.employee_id.strip() else None)
    )
    norm_branch = (
        pc.selected_entity_id.strip().casefold()
        if pc.selected_entity_type == "branch" and pc.selected_entity_id
        else (pc.branch.strip().casefold() if pc.branch and pc.branch.strip().casefold() not in {"all", ""} else None)
    )
    norm_level = (
        pc.performance_level.strip().capitalize()
        if pc.performance_level and pc.performance_level.strip().casefold() in {"employee", "managerial", "corporate"}
        else None
    )
    norm_region = (
        pc.region.strip().upper()
        if pc.region and pc.region.strip().casefold() not in {"all", ""}
        else None
    )
    p_month, p_year, p_key = parse_period_to_month_year(pc.period, pc.month, pc.year)

    if norm_team:
        ss.team = norm_team
    if norm_fn:
        ss.function = norm_fn
    elif ss.team:
        ss.function = function_for_team(ss.team)
    if norm_pos:
        ss.position = norm_pos
    if norm_emp:
        ss.employee_id = norm_emp
    if norm_branch and not explicit_egy_in_prompt:
        ss.branch = norm_branch
    elif explicit_egy_in_prompt:
        ss.branch = None
    if norm_level:
        ss.performance_level = norm_level
    if explicit_egy_in_prompt:
        ss.region = "EGY"
    elif explicit_uae_in_prompt:
        ss.region = "UAE"
    elif norm_region:
        ss.region = norm_region
    if p_month:
        ss.month = p_month
    if p_year:
        ss.year = p_year

    # Resolve selected_metric_id from PageContextV1 if present
    raw_metric = pc.selected_metric_id or (pc.selected_entity_id if pc.selected_entity_type == "metric" else None)
    resolved_metric_id: str | None = None
    resolved_metric_display: str | None = None
    if raw_metric and raw_metric.strip():
        raw_m = raw_metric.strip()
        cat = get_ai_catalog()
        if ":" in raw_m:
            m_def = cat.get_metric_by_id(raw_m)
            if m_def is not None:
                resolved_metric_id = m_def.metric_id
                resolved_metric_display = m_def.display_name
            else:
                resolved_metric_id = raw_m
                resolved_metric_display = raw_m.split(":")[-1].replace("_", " ").title()
        else:
            m_def = cat.find_metric_definition(
                team=ss.team or "Inbound",
                position=ss.position,
                kpi_key_or_label=raw_m,
                performance_level=ss.performance_level or "Employee",
            )
            if m_def is not None:
                resolved_metric_id = m_def.metric_id
                resolved_metric_display = m_def.display_name

    # Synchronize confirmed context when page filters changed so stale filters do not override current page state
    if ss.last_confirmed_query is not None:
        lcq = ss.last_confirmed_query.model_copy(deep=True)
        if norm_team and lcq.team and lcq.team.casefold() != norm_team.casefold():
            lcq.team = norm_team
            lcq.position = norm_pos
            lcq.metric_id = resolved_metric_id
            lcq.metric_display_name = resolved_metric_display
        if norm_fn and lcq.function and lcq.function.casefold() != norm_fn.casefold():
            lcq.function = norm_fn
        if norm_branch != lcq.branch:
            lcq.branch = norm_branch
            lcq.branches = [norm_branch] if norm_branch else []
        if norm_level and lcq.performance_level != norm_level:
            lcq.performance_level = norm_level
        if p_key and lcq.periods != [p_key]:
            lcq.periods = [p_key]
        if resolved_metric_id:
            lcq.metric_id = resolved_metric_id
            lcq.metric_display_name = resolved_metric_display
        ss.last_confirmed_query = lcq
    elif resolved_metric_id:
        ss.last_confirmed_query = ConfirmedQueryContext(
            team=ss.team,
            function=ss.function,
            position=ss.position,
            branch=ss.branch,
            branches=[ss.branch] if ss.branch else [],
            performance_level=ss.performance_level or "Employee",
            metric_id=resolved_metric_id,
            metric_display_name=resolved_metric_display,
            periods=[p_key] if p_key else [],
        )

    updated_req = req.model_copy(update={"session_state": ss})
    return updated_req, resolved_metric_display


def validate_page_context_scope(
    req: AiChatRequest,
    scope: dict[str, Any],
    auth_service: AiConversationService,
) -> tuple[bool, str | None, str | None]:
    """Verify that the active PageContextV1 does not request unauthorized scope when prompt relies on page context.

    Returns (is_authorized, restricted_headline, restricted_bullet).
    """
    pc = req.page_context
    if pc is None:
        return True, None, None

    lower = (req.prompt or "").casefold()
    # Check if prompt relies on page context rather than naming a different explicit team
    norm_team = normalize_team_name(
        pc.selected_entity_id if pc.selected_entity_type == "team" and pc.selected_entity_id else pc.team_id
    )
    norm_fn = normalize_function_name(pc.function_id, norm_team)
    norm_level = (
        pc.performance_level.strip().capitalize()
        if pc.performance_level and pc.performance_level.strip().casefold() in {"employee", "managerial", "corporate"}
        else "Employee"
    )
    norm_branch = (
        pc.selected_entity_id.strip().casefold()
        if pc.selected_entity_type == "branch" and pc.selected_entity_id
        else (pc.branch.strip().casefold() if pc.branch and pc.branch.strip().casefold() not in {"all", ""} else None)
    )
    norm_emp = (
        pc.selected_entity_id.strip()
        if pc.selected_entity_type == "employee" and pc.selected_entity_id
        else (pc.employee_id.strip() if pc.employee_id and pc.employee_id.strip() else None)
    )

    if is_self_only(scope):
        caller_emp = str(scope.get("employee_id") or "").strip()
        if norm_emp and (not caller_emp or norm_emp.casefold() != caller_emp.casefold()):
            return (
                False,
                "Access restricted: your role is restricted to viewing your own employee scorecard.",
                "Self-scoped accounts cannot inspect or request actions for another employee's record.",
            )
        if norm_level in {"Managerial", "Corporate"}:
            return (
                False,
                f"Access restricted: your role does not have permission to view {norm_level} level data.",
                f"Self-scoped accounts cannot access {norm_level} scorecards.",
            )

    if norm_branch and not auth_service._is_branch_authorized(norm_branch, scope):
        return (
            False,
            f"Access restricted: your role does not have permission to view {norm_branch.capitalize()} branch data.",
            f"Your branch assignment does not include {norm_branch.capitalize()}.",
        )

    # Only enforce page_context team/function restriction if the prompt didn't explicitly ask about an authorized team
    from services.ai.router import _detect_teams_in_prompt

    explicit_prompt_teams = _detect_teams_in_prompt(lower)
    if not explicit_prompt_teams:
        if norm_team and not auth_service._is_team_and_level_authorized(norm_team, norm_level, scope):
            return (
                False,
                f"Access restricted: your account does not have permission to view {norm_team} ({norm_level}) data.",
                f"Your current scope assignment does not include {norm_team} at the {norm_level} level.",
            )
        if norm_fn and not norm_team and not auth_service._is_function_authorized(norm_fn, scope):
            return (
                False,
                f"Access restricted: your role does not have permission to view {norm_fn} data.",
                f"Your current function assignment does not include {norm_fn}.",
            )

    return True, None, None


_PAGE_HELP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bwhat\s+does\s+this\s+(?:page|view|dashboard|screen|slide|card|chart|table)\s+(?:show|mean|do|display)\b", re.I),
    re.compile(r"\b(?:explain|describe)\s+this\s+(?:page|view|dashboard|screen|slide|metric|card)\b", re.I),
    re.compile(r"\bhow\s+(?:do\s+i\s+use|to\s+use|to\s+read|does\s+this\s+(?:page|view|dashboard|screen)\s+work)\b", re.I),
    re.compile(r"\bwhat\s+is\s+(?:shown\s+on|on)\s+this\s+(?:page|view|dashboard)\b", re.I),
    re.compile(r"\bwhat\s+is\s+(?:the\s+)?(?:monthly\s+presentation|team\s+dashboard)\s+(?:page|view)?\b", re.I),
    re.compile(r"\bhow\s+are\s+scores?\s+calculated\s+on\s+this\s+(?:page|view|dashboard)\b", re.I),
)

_NAVIGATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:how\s+do\s+i\s+find|where\s+can\s+i\s+(?:find|see|view|open|check)|where\s+do\s+i\s+go|where\s+can\s+i\s+go|where\s+is|where\s+are)\b.*\b(?:scorecards?|profiles?|corrective\s+actions?|action\s+plans?|balanced\s+scorecard|bsc|monthly\s+presentation|monthly\s+review|presentation|team\s+dashboard|executive\s+summary|insights|uploads?|settings|users)\b", re.I),
    re.compile(r"\b(?:take\s+me\s+to|navigate\s+to|go\s+to|open)\s+(?:the\s+)?(?:my\s+scorecard|employee\s+scorecard|agent\s+scorecards?|corrective\s+actions?|balanced\s+scorecard|monthly\s+presentation|monthly\s+review|team\s+dashboard|executive\s+summary|insights|uploads?|settings)\b", re.I),
    re.compile(r"^\s*how\s+do\s+i\s+find\s+my\s+scorecard\s*\??\s*$", re.I),
    re.compile(r"^\s*where\s+can\s+i\s+see\s+corrective\s+actions\s*\??\s*$", re.I),
)

_PROPOSAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:propose|create|draft|suggest|recommend|build|write|generate)\s+(?:a\s+|an\s+)?(?:corrective\s+action|action\s+plan|coaching\s+action|improvement\s+action|pip|training\s+action)\b", re.I),
    re.compile(r"\bwhat\s+(?:corrective\s+)?action\s+should\s+(?:we|i)\s+(?:take|create|assign)\b", re.I),
    re.compile(r"^\s*what\s+should\s+(?:we|i)\s+do(?:\s+about\s+this|\s+for\s+this|\s+here|\s+next)?\s*\??\s*$", re.I),
    re.compile(r"\bwhat\s+should\s+(?:we|i)\s+do\s+to\s+(?:improve|fix|address)\b", re.I),
)


_AMBIGUOUS_DATA_WORD_RE = re.compile(
    r"\b(?:check|look|show|data|numbers?|stats|figures|analyze|review|summary|overview|anything|update|status|this|that|it)\b",
    re.I,
)


_FOLLOWUP_DISCOURSE_RE = re.compile(
    r"^(?:and|what\s+about|how\s+about|compare\s+it\s+with|same\s+for|now\s+(?:show|check|for|in)|switch\s+to)\b"
    r"|\b(?:his|her|their|him|that\s+agent|that\s+employee|top\s+agent|top\s+performer|the\s+leader|position|role|title)\b",
    re.I,
)


def _has_specific_entity_context(req: AiChatRequest) -> bool:
    """True when the conversation already has an active analytical query or page entity."""
    lcq = req.session_state.last_confirmed_query
    if lcq is not None and lcq.intent not in (None, "clarify", "unsupported") and any(
        (
            lcq.team,
            lcq.function,
            lcq.metric_id,
            lcq.last_subject_employee_id,
            lcq.branch,
            lcq.branches,
        )
    ):
        return True
    pc = req.page_context
    if pc is not None and any((pc.selected_metric_id, pc.selected_entity_id, pc.employee_id)):
        return True
    return False


def _has_active_analytical_query(req: AiChatRequest) -> bool:
    """True only when an established analytical query or pending clarification exists."""
    lcq = req.session_state.last_confirmed_query
    if lcq is not None:
        if lcq.pending_clarification_code:
            return True
        if lcq.intent not in (None, "clarify", "unsupported"):
            return True
    pc = req.page_context
    if pc is not None and any((pc.selected_metric_id, pc.selected_entity_id, pc.employee_id)):
        return True
    return False


def _has_grounded_followup_context(req: AiChatRequest) -> bool:
    """True only when the current prompt actually follows up or corrects an active query."""
    if not _has_active_analytical_query(req):
        return False
    prompt = (req.prompt or "").strip()
    if not prompt:
        return False
    if is_explicit_correction_prompt(prompt) or is_bare_scope_or_period_refinement(prompt):
        return True
    return bool(_FOLLOWUP_DISCOURSE_RE.search(prompt))


def detect_contextual_capability(
    req: AiChatRequest,
    *,
    intent_context: BoundedIntentContext | None = None,
    out_intent_result: list[LocalIntentResult] | None = None,
) -> tuple[ContextualCapabilityMode, str, float]:
    """Classify a turn safely BEFORE any performance DB read or exploration.

    Returns (capability_mode, resolution_source, provider_ms).
    """
    if req.capability_hint in ("page_help", "navigation", "proposal", "performance_query"):
        return req.capability_hint, "local_rules", 0.0
    if req.clarification_choice_id:
        return "performance_query", "local_rules", 0.0

    prompt = (req.prompt or "").strip()
    lower = prompt.casefold()
    if is_explain_previous_prompt(prompt):
        return "explain_previous", "local_rules", 0.0

    # Phase 2: Pilot flag check - if enabled, skip lexical gates and route to model
    from services.ai.config import get_ai_runtime_config
    config = get_ai_runtime_config()
    if config.model_led_pilot_enabled:
        return "performance_query", "model_led_pilot", 0.0

    if is_greeting_or_thanks_prompt(prompt) is not None:
        return "greeting", "local_rules", 0.0

    for pat in _PAGE_HELP_PATTERNS:
        if pat.search(lower):
            return "page_help", "local_rules", 0.0

    for pat in _NAVIGATION_PATTERNS:
        if pat.search(lower):
            return "navigation", "local_rules", 0.0

    if is_capabilities_help_prompt(prompt):
        return "capabilities_help", "local_rules", 0.0

    if is_off_topic_prompt(prompt):
        return "off_topic", "local_rules", 0.0

    # If prompt asks to list/show existing overdue/open corrective actions, it is a performance_query, not a new proposal
    if re.search(r"\b(?:show|list|view|check|count|how\s+many|overdue)\b.*\bcorrective\s+actions?\b", lower):
        return "performance_query", "local_rules", 0.0

    for pat in _PROPOSAL_PATTERNS:
        if pat.search(lower):
            return "proposal", "local_rules", 0.0

    # Vague data-less requests without grounded follow-up context -> clarification (0 DB reads)
    if is_vague_dataless_prompt(prompt):
        if _has_grounded_followup_context(req):
            return "performance_query", "local_rules", 0.0
        if _has_specific_entity_context(req) and any(
            w in lower for w in ("this", "it", "analyze", "review", "inspect")
        ):
            return "performance_query", "local_rules", 0.0
        return "clarification", "local_rules", 0.0

    # Bare period/country/branch tokens ("October", "UAE", "Dubai") only refine an active analytical query.
    if is_bare_scope_or_period_refinement(prompt):
        if _has_active_analytical_query(req):
            return "performance_query", "local_rules", 0.0
        return "clarification", "local_rules", 0.0

    # Contextual help/navigation/proposal cues without explicit analytical data query keywords
    has_contextual_cue = any(
        cue in lower
        for cue in (
            "this page",
            "this view",
            "this screen",
            "this dashboard",
            "this chart",
            "this card",
            "how do i",
            "how can i",
            "where can i",
            "where do i",
            "navigate",
            "propose",
            "draft",
            "suggest",
            "recommend",
            "action plan",
            "coaching action",
            "what should we do",
            "what action",
        )
    )
    has_analytical_kw = any(
        kw in lower
        for kw in (
            "score",
            "rate",
            "target",
            "gap",
            "compare",
            "vs ",
            "versus",
            "trend",
            "best",
            "worst",
            "lowest",
            "highest",
            "top ",
            "rank",
            "why ",
            "who ",
            "how many",
            "overdue",
            "focus",
            "bookings",
            "attended",
            "abandon",
            "reachability",
            "aht",
            "quality",
            "joiner",
            "2025",
            "2026",
        )
    )
    if (
        (req.provider_override or "auto") == "auto"
        and local_intent_enabled()
        and has_contextual_cue
        and not has_analytical_kw
    ):
        local_res = call_suggest_intent(suggest_intent, prompt, context=intent_context)
        if out_intent_result is not None:
            out_intent_result.append(local_res)
        if local_res.reason == "ok" and local_res.intent in (
            "page_help",
            "navigation",
            "proposal",
            "capabilities_help",
            "explain_previous",
            "off_topic",
            "clarification",
        ):
            return local_res.intent, "local_model_router", local_res.elapsed_ms  # type: ignore[return-value]

    if has_pms_performance_signal(prompt):
        return "performance_query", "local_rules", 0.0

    if _has_grounded_followup_context(req):
        return "performance_query", "local_rules", 0.0

    # Unrecognized prompt with zero PMS signals and zero grounded follow-up cues:
    # ask the configured intent classifier (with bounded context) once; never default to current_value.
    if (req.provider_override or "auto") == "auto" and local_intent_enabled():
        local_res = call_suggest_intent(suggest_intent, prompt, context=intent_context)
        if out_intent_result is not None:
            out_intent_result.append(local_res)
        if local_res.reason == "ok" and local_res.intent is not None:
            mapped: dict[str, ContextualCapabilityMode] = {
                "greeting": "greeting",
                "capabilities_help": "capabilities_help",
                "explain_previous": "explain_previous",
                "page_help": "page_help",
                "navigation": "navigation",
                "off_topic": "off_topic",
                "clarification": "clarification",
                "clarify": "clarification",
                "proposal": "proposal",
                "performance_query": "performance_query",
                "current_value": "performance_query",
                "actual_vs_target": "performance_query",
                "trend": "performance_query",
                "ranking": "performance_query",
                "score_drivers": "performance_query",
            }
            if local_res.intent in mapped:
                return mapped[local_res.intent], "local_model_router", local_res.elapsed_ms
        # Provider unavailable, timed out, or returned invalid structured output: never guess performance_query.
        return "clarification", "local_model_router", local_res.elapsed_ms

    if _AMBIGUOUS_DATA_WORD_RE.search(lower):
        return "clarification", "local_rules", 0.0

    return "off_topic", "local_rules", 0.0


def _describe_authorized_scope(scope: dict[str, Any], session_state: SessionFilterContext) -> str:
    if is_self_only(scope):
        return "your own Employee Scorecard"
    is_unrestricted = bool(scope.get("has_unrestricted_team_access")) or str(scope.get("role") or "").strip() in {
        "Admin",
        "General Manager",
        "Performance Team",
        "Viewer",
    }
    if session_state.team and session_state.team.strip().casefold() not in {"all", ""}:
        t_cand = session_state.team.strip()
        if is_unrestricted or user_can_access_team(scope, t_cand):
            return t_cand
    if not is_unrestricted:
        teams = [str(t).strip() for t in (scope.get("accessible_teams") or []) if str(t).strip()]
        if len(teams) == 1:
            return teams[0]
    if session_state.function and session_state.function.strip().casefold() not in {"all", ""}:
        fn_cand = session_state.function.strip()
        allowed_fns = {str(f).strip().casefold() for f in (scope.get("accessible_functions") or []) if f}
        if is_unrestricted or fn_cand.casefold() in allowed_fns:
            return fn_cand
    if not is_unrestricted:
        fns = [str(f).strip() for f in (scope.get("accessible_functions") or []) if str(f).strip()]
        if len(fns) == 1:
            return f"{fns[0]} teams"
    return "your authorized teams and departments"


def _build_role_aware_starter_followups(scope: dict[str, Any], session_state: SessionFilterContext) -> list[str]:
    if is_self_only(scope):
        return [
            "Show my performance summary",
            "How did my score trend over recent months?",
            "How do I find my scorecard?",
        ]
    active_team = session_state.team if session_state.team and session_state.team.strip().casefold() not in {"all", ""} else None
    if active_team and not user_can_access_team(scope, active_team):
        active_team = None
    if not active_team and not scope.get("has_unrestricted_team_access"):
        teams = [str(t).strip() for t in (scope.get("accessible_teams") or []) if str(t).strip()]
        if len(teams) == 1:
            active_team = teams[0]
    if active_team:
        return [
            f"What is {active_team} score vs target?",
            f"Why did {active_team} have KPI gaps?",
            "How are we doing overall?",
        ]
    return [
        "How are we doing overall?",
        "Which teams or KPIs need attention?",
        "Compare performance across my authorized teams",
    ]


def build_capabilities_help_payload(
    *,
    scope: dict[str, Any],
    session_state: SessionFilterContext,
    prompt: str = "",
) -> tuple[str, list[str], list[str]]:
    """Return concise, role-aware, scope-aware capabilities help without fake numbers or DB queries."""
    from services.ai.router import _detect_teams_in_prompt

    followups = _build_role_aware_starter_followups(scope, session_state)[:3]
    if is_self_only(scope):
        headline = "I can help you review your own PMS scorecard, KPI targets, monthly trends, and assigned actions."
        bullets = [
            "Ask about your latest weighted score, KPI gaps, or how your metrics moved across published months.",
            "Ask for page explanations or direct navigation to your Employee Scorecard.",
        ]
        return headline, bullets, followups

    lower = (prompt or "").casefold()
    mentioned_teams = _detect_teams_in_prompt(lower)
    is_unrestricted = bool(scope.get("has_unrestricted_team_access")) or str(scope.get("role") or "").strip() in {
        "Admin",
        "General Manager",
        "Performance Team",
        "Viewer",
    }
    allowed_fns = {str(f).strip().casefold() for f in (scope.get("accessible_functions") or []) if str(f).strip()}
    allowed_teams = {str(t).strip().casefold() for t in (scope.get("accessible_teams") or []) if str(t).strip()}

    requested_fn: str | None = None
    if re.search(r"\brcm\b", lower):
        requested_fn = "RCM"
    elif re.search(r"\bcall\s+center\b", lower):
        requested_fn = "Call Center"
    elif len(mentioned_teams) == 1:
        t_name = mentioned_teams[0]
        if not user_can_access_team(scope, t_name):
            scope_desc = _describe_authorized_scope(scope, session_state)
            headline = f"{t_name} is outside your current access permissions, so I can only assist with {scope_desc}."
            bullets = [
                f"Ask about overall scores, KPI targets, trends, or drivers within {scope_desc}.",
            ]
            return headline, bullets, followups
        headline = f"For {t_name}, I can summarize scores vs. targets, diagnose KPI drivers, track trends, and review employee or action status."
        bullets = [
            f"Ask for {t_name} monthly scores, KPI gaps against target, or top/lowest performers in a period.",
            "You can also follow up to drill into a specific KPI, branch, or corrective action.",
        ]
        return headline, bullets, [
            f"What is {t_name} score vs target?",
            f"Show {t_name} trends",
            "How are we doing overall?",
        ][:3]

    if requested_fn:
        has_fn_access = is_unrestricted or requested_fn.casefold() in allowed_fns or any(
            (function_for_team(t) or "").casefold() == requested_fn.casefold()
            for t in (scope.get("accessible_teams") or [])
        )
        if not has_fn_access:
            scope_desc = _describe_authorized_scope(scope, session_state)
            headline = f"{requested_fn} is outside your current access permissions, so I can only assist with {scope_desc}."
            bullets = [
                f"Ask about scores, KPI targets, or trends within {scope_desc}.",
            ]
            return headline, bullets, followups
        if requested_fn == "RCM":
            headline = "For your authorized RCM scope, I can inspect Coding, Submission, Re-Submission, Pre-Approvals, rejection trends, and KPI targets."
            bullets = [
                "Ask for RCM team scores, rejection or SLA trends across published months, or compare Egypt and UAE RCM units within your scope.",
                "Ask which KPIs are missing target or review open corrective actions.",
            ]
            return headline, bullets, [
                "Show RCM rejection trends",
                "Compare RCM team scores",
                "Which RCM KPIs missed target?",
            ]

    scope_desc = _describe_authorized_scope(scope, session_state)
    can_write = can_user_write_corrective_action(
        scope,
        team=session_state.team,
        performance_level=session_state.performance_level,
        branch=session_state.branch,
    )
    headline = (
        f"I can analyze verified PMS performance for {scope_desc}—scores, KPI targets, trends, comparisons, and root causes."
    )
    bullets = [
        "Ask for an overall overview, KPI actuals vs. targets, team or branch comparisons, or top/lowest contributors.",
        (
            "Ask me to diagnose KPI drops or draft an Open corrective action proposal for review."
            if can_write
            else "Inspect KPI drivers and corrective action follow-up status within your authorized scope (read-only)."
        ),
    ]
    return headline, bullets, followups


_NUM_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])([+-]?\d+(?:\.\d+)?)")
_UNGROUNDED_CAUSE_RE = re.compile(
    r"\b(?:staffing\s+shortage|shortage|illness|sick\s+leave|holiday|outage|system\s+crash|training\s+gap|attrition|turnover)\b",
    re.I,
)


def _extract_numeric_magnitudes(text: str) -> set[float]:
    vals: set[float] = set()
    for m in _NUM_TOKEN_RE.finditer(text or ""):
        try:
            v = abs(float(m.group(1)))
            if v < 2000:  # exclude years/IDs/large years handled separately
                vals.add(round(v, 2))
                vals.add(round(v, 1))
        except ValueError:
            pass
    return vals


def _build_allowed_explanation_numbers(summary: dict[str, Any]) -> set[float]:
    parts = [
        str(summary.get("headline") or ""),
        *[str(b) for b in (summary.get("narrative_bullets") or [])],
        *[str(b) for b in (summary.get("detail_bullets") or [])],
        str(summary.get("basis_warning") or ""),
        str(summary.get("scope_banner") or ""),
    ]
    for ev in summary.get("evidence_items") or []:
        if isinstance(ev, dict):
            parts.append(str(ev.get("value") or ""))
            parts.append(str(ev.get("target") or ""))
    joined = " ".join(parts)
    base_nums = _extract_numeric_magnitudes(joined)
    allowed = set(base_nums)
    # Allow exact arithmetic differences & reconstructions (e.g., 12% - 8% = 4 pp; 12 - 4 = 8)
    sorted_nums = sorted(base_nums)
    for a in sorted_nums:
        for b in sorted_nums:
            diff = round(abs(a - b), 2)
            tot = round(a + b, 2)
            allowed.add(diff)
            allowed.add(round(diff, 1))
            allowed.add(tot)
            allowed.add(round(tot, 1))
    return allowed


def _is_provider_explanation_grounded(
    headline: str,
    bullets: list[str],
    summary: dict[str, Any],
) -> bool:
    hl = headline.strip()
    if not hl or hl.casefold().startswith("in my previous answer"):
        return False
    prev_hl = str(summary.get("headline") or "").strip()
    if hl.casefold() == prev_hl.casefold():
        return False
    candidate_text = " ".join([hl, *bullets])
    source_text = " ".join(
        [
            prev_hl,
            *[str(b) for b in (summary.get("narrative_bullets") or [])],
            *[str(b) for b in (summary.get("detail_bullets") or [])],
            str(summary.get("basis_warning") or ""),
        ]
    )
    if _UNGROUNDED_CAUSE_RE.search(candidate_text) and not _UNGROUNDED_CAUSE_RE.search(source_text):
        return False
    allowed_nums = _build_allowed_explanation_numbers(summary)
    for m in _NUM_TOKEN_RE.finditer(candidate_text):
        try:
            v = abs(float(m.group(1)))
        except ValueError:
            continue
        if v >= 2000:
            if str(int(v)) not in source_text and f"{v:g}" not in source_text:
                return False
            continue
        if v in (1.0, 2.0, 3.0):
            # Ordinal rank / simple English count ("1st", "2 months")
            continue
        if not any(abs(v - a) <= 0.11 for a in allowed_nums):
            return False
    return True


def _detect_explain_ambiguity(prompt: str, summary: dict[str, Any]) -> str | None:
    lower = (prompt or "").casefold()
    ev_items = [
        ev for ev in (summary.get("evidence_items") or [])
        if isinstance(ev, dict) and ev.get("label")
    ]
    metric_labels: list[str] = []
    for ev in ev_items:
        lbl = str(ev.get("label") or "").strip()
        if lbl and lbl not in metric_labels:
            metric_labels.append(lbl)
    if re.search(r"\b(?:which\s+(?:number|metric|figure|one)|the\s+other\s+(?:metric|number|one)|that\s+other\s+(?:metric|number))\b", lower):
        if len(metric_labels) >= 2:
            return f"Multiple metrics appeared in that answer ({', '.join(metric_labels[:3])}). Which one would you like me to explain?"
        return "Which specific figure or phrase from my previous answer would you like me to clarify?"
    return None


def _build_deterministic_plain_explanation(
    *,
    prompt: str,
    summary: dict[str, Any],
    provider_failure_reason: str | None = None,
) -> tuple[str, list[str], list[str]]:
    """Build a plain-language grounded explanation without parroting the previous headline."""
    lower = (prompt or "").casefold()
    prev_hl = str(summary.get("headline") or "").strip()
    prev_bullets = [str(b).strip() for b in (summary.get("narrative_bullets") or []) if str(b).strip()]
    prev_details = [str(b).strip() for b in (summary.get("detail_bullets") or []) if str(b).strip()]
    prev_scope = str(summary.get("scope_banner") or "").strip()
    prev_warn = str(summary.get("basis_warning") or "").strip()
    sq = summary.get("structured_query") if isinstance(summary.get("structured_query"), dict) else {}
    ev_items = [ev for ev in (summary.get("evidence_items") or []) if isinstance(ev, dict)]

    team_or_fn = str(sq.get("team") or sq.get("function") or prev_scope or "this scope").strip()
    period_match = re.search(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+202\d\b",
        prev_hl,
    )
    period_str = period_match.group(0) if period_match else ""
    scope_period = f"{team_or_fn}{f' in {period_str}' if period_str else ''}"

    pcts = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)%", prev_hl)]
    delta_m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*pp\b(?:\s+vs\s+([A-Za-z]+))?", prev_hl, re.I)

    bullets: list[str] = []
    detail_bullets: list[str] = []

    if provider_failure_reason:
        bullets.append(
            f"Note: the live explanation model was unavailable ({provider_failure_reason}), so this explanation uses only the verified figures from the previous answer."
        )

    if re.search(r"\b(?:percentage\s+points?|pts|pp)\b", lower):
        if delta_m:
            raw_d = float(delta_m.group(1))
            vs_month = delta_m.group(2) or "the prior month"
            if len(pcts) >= 1:
                cur_v = pcts[0]
                prev_v = round(cur_v - raw_d, 1)
                direction_word = "up" if raw_d >= 0 else "down"
                headline = (
                    f"In plain terms, {abs(raw_d):.1f} percentage points (pp) means the rate in {scope_period} moved "
                    f"{direction_word} from {prev_v:.1f}% in {vs_month} to {cur_v:.1f}% (a direct arithmetic difference of {raw_d:+.1f} percentage points, not a {abs(raw_d):.1f}% relative jump)."
                )
            else:
                headline = (
                    f"Percentage points (pp) measure the direct subtraction between two percentages in {scope_period} "
                    f"({raw_d:+.1f} pp vs {vs_month}), rather than a relative percentage ratio."
                )
        else:
            headline = (
                f"Percentage points (pp) show the straight numerical difference between two percentages in {scope_period}, "
                "rather than a relative percent change."
            )
    elif re.search(r"\b(?:declin\w*|drop\w*|fell|lower|worse|decrease\w*)\b", lower):
        if delta_m and len(pcts) >= 1:
            raw_d = float(delta_m.group(1))
            vs_month = delta_m.group(2) or "the comparison month"
            cur_v = pcts[0]
            prev_v = round(cur_v - raw_d, 1)
            if raw_d < 0:
                headline = (
                    f"It is called a decline because the verified score in {scope_period} fell from {prev_v:.1f}% "
                    f"({vs_month}) to {cur_v:.1f}%—a drop of {abs(raw_d):.1f} percentage points."
                )
            else:
                headline = (
                    f"Performance worsened because the rate moved by {raw_d:+.1f} percentage points (from {prev_v:.1f}% in {vs_month} to {cur_v:.1f}%) "
                    f"on a lower-is-better metric in {scope_period}."
                )
        elif prev_hl:
            headline = (
                f"The comparison showed a decline because the measured result in {scope_period} was lower than its prior-period benchmark."
            )
        else:
            headline = "The result moved down compared with the prior period in the stored evidence."
    elif re.search(r"\b(?:which\s+part|supports|evidence|conclusion|prove|backs?\s+up|lowest|bottom)\b", lower):
        if ev_items:
            ev_summary = "; ".join(
                f"{e['label']}: {e['value']}" + (f" (target {e['target']})" if e.get("target") else "")
                for e in ev_items[:3]
                if e.get("value")
            )
            headline = (
                f"That conclusion is directly supported by the verified PMS metrics for {scope_period}: {ev_summary}."
                if ev_summary
                else f"That conclusion comes from the published evaluation records for {scope_period}."
            )
        elif prev_bullets:
            headline = f"The conclusion for {scope_period} is supported by these recorded facts: {prev_bullets[0]}"
        elif pcts:
            vals_str = ", ".join(f"{v:.1f}%" for v in pcts[:3])
            headline = f"The conclusion for {scope_period} rests directly on the published PMS evaluation figures ({vals_str}) compared across all eligible records in that scope."
        else:
            headline = f"That finding comes directly from the verified evaluation records for {scope_period}."
    else:
        # Plain-language simplification preserving original figures, scope, period, and caveats
        if delta_m and len(pcts) >= 1:
            raw_d = float(delta_m.group(1))
            vs_month = delta_m.group(2) or "the previous month"
            cur_v = pcts[0]
            prev_v = round(cur_v - raw_d, 1)
            if abs(raw_d) < 0.05:
                headline = (
                    f"Simply put, for {scope_period}, the measured figure stayed unchanged at {cur_v:.1f}% "
                    f"compared with {vs_month} ({prev_v:.1f}%)."
                )
            else:
                dir_txt = "higher" if raw_d > 0 else "lower"
                headline = (
                    f"Simply put, for {scope_period}, the measured figure is {cur_v:.1f}%, which is {abs(raw_d):.1f} percentage points "
                    f"{dir_txt} than {vs_month} ({prev_v:.1f}%)."
                )
        elif pcts:
            headline = (
                f"Simply put, {scope_period} recorded {pcts[0]:.1f}% based on the published PMS evaluation records for that scope."
            )
        elif ev_items:
            top_ev = ev_items[0]
            headline = f"Simply put, for {scope_period}, {top_ev.get('label', 'the metric')} measured {top_ev.get('value', 'the reported figure')}."
        else:
            headline = f"In plain terms, the previous result reflects published evaluation records strictly for {scope_period}."

    # Add non-redundant supporting points (preserving evidence & uncertainty without repeating prev_hl verbatim)
    for b in prev_bullets:
        if b.casefold() != prev_hl.casefold() and len(bullets) < 2:
            bullets.append(b)
    if prev_warn and len(bullets) < 3:
        bullets.append(f"Caveat to keep in mind: {prev_warn}")
    if prev_details:
        detail_bullets.extend(prev_details[:3])
    if prev_hl and prev_hl not in detail_bullets:
        detail_bullets.append(f"Original summary: {prev_hl}")
    if not bullets:
        bullets.append(f"Scope covered: {prev_scope or scope_period}. Figures reflect published records without extrapolation.")
    return headline, bullets[:3], detail_bullets[:4]


def build_explain_previous_payload(
    *,
    last_turn_summary: dict[str, Any] | None,
    scope: dict[str, Any],
    session_state: SessionFilterContext,
    prompt: str = "",
    provider_override: str = "auto",
) -> tuple[str, list[str], list[str], list[str], str, dict[str, Any]]:
    """Explain or clarify the previous assistant response without running a new performance query.

    Returns (headline, bullets, detail_bullets, followups, outcome, explain_meta).
    """
    followups = _build_role_aware_starter_followups(scope, session_state)[:2]
    meta: dict[str, Any] = {
        "provider_used": "deterministic",
        "model_used": "intent-gate-v1",
        "prompt_version": EXPLAIN_PREVIOUS_PROMPT_VERSION,
        "provider_calls": 0,
        "provider_ms": 0.0,
        "fallback_outcome": "none",
    }
    if last_turn_summary is None:
        return (
            "I haven't shared an analysis in this conversation yet. Which team, KPI, or period would you like me to inspect?",
            ["Specify a team, metric, or ask how performance looks overall so I have an answer to explain."],
            [],
            followups,
            "clarification",
            meta,
        )
    if last_turn_summary.get("restricted"):
        return (
            "Access restricted: your permissions changed and no longer include the scope of that earlier answer.",
            ["Ask a question within your current authorized scope."],
            [],
            followups,
            "restricted_access",
            meta,
        )

    ambig_q = _detect_explain_ambiguity(prompt, last_turn_summary)
    if ambig_q is not None:
        return (
            ambig_q,
            ["Name the specific figure, metric, or comparison you want me to break down."],
            [],
            followups,
            "clarification",
            meta,
        )

    provider_failure_reason: str | None = None
    use_provider = (provider_override or "auto") != "deterministic" and local_synthesis_enabled()
    if use_provider:
        schema = {
            "type": "object",
            "properties": {
                "headline": {"type": "string"},
                "bullets": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["headline", "bullets"],
            "additionalProperties": False,
        }
        prev_hl_str = str(last_turn_summary.get("headline") or "")
        pcts_hl = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)%", prev_hl_str)]
        delta_hl = re.search(r"([+-]?\d+(?:\.\d+)?)\s*pp\b(?:\s+vs\s+([A-Za-z]+))?", prev_hl_str, re.I)
        verified_math: str | None = None
        if delta_hl and pcts_hl:
            d_val = float(delta_hl.group(1))
            vs_m = delta_hl.group(2) or "prior month"
            cur_v = pcts_hl[0]
            verified_math = f"current={cur_v:.1f}%, {vs_m}={round(cur_v - d_val, 1):.1f}%, change={d_val:+.1f} percentage points"
        bounded_prior = {
            "scope_banner": last_turn_summary.get("scope_banner"),
            "headline": last_turn_summary.get("headline"),
            "narrative_bullets": last_turn_summary.get("narrative_bullets") or [],
            "detail_bullets": (last_turn_summary.get("detail_bullets") or [])[:3],
            "basis_warning": last_turn_summary.get("basis_warning"),
            "verified_math": verified_math,
            "evidence_items": (last_turn_summary.get("evidence_items") or [])[:4],
        }
        sys_inst = (
            "You explain a prior PMS analytics answer in simpler, clearer language.\n"
            "Rules:\n"
            "1. Directly answer what the user asked about the prior response (e.g. meaning of percentage points vs relative %, why it is called a decline, or which verified numbers support the conclusion).\n"
            "2. Preserve exact numbers, periods, scope, and any uncertainty/caveats from the authorized prior answer.\n"
            "3. Never confuse a change value ('+X pp since April') with an absolute monthly score; use verified_math for prior vs current values.\n"
            "4. NEVER invent causes, staff issues, numbers, recommendations, or targets not present in the JSON.\n"
            "5. NEVER start with 'In my previous answer' or repeat the prior headline word-for-word.\n"
            "6. Keep the headline concise (1-2 sentences) and at most 2 short supporting bullets.\n"
            f"Authorized prior answer JSON: {json.dumps(bounded_prior, ensure_ascii=False)}"
        )
        p_req = ProviderRequest(
            messages=[ProviderMessage(role="user", content=(prompt or "Explain the previous answer more simply.").strip())],
            system_instruction=sys_inst,
            temperature=0.0,
            max_tokens=420,
            response_format="json",
            json_schema=schema,
            timeout_seconds=synthesis_timeout_seconds(),
            purpose="explain_previous",
            user_id=str(scope.get("user_id") or "") or None,
            user_role=str(scope.get("role") or "") or None,
        )
        p_resp = get_unified_provider_engine().generate(p_req)
        meta["provider_calls"] = 1
        meta["provider_ms"] = round(float(p_resp.latency_ms or 0.0), 2)
        if p_resp.outcome in ("ok", "success", "fallback_success") and p_resp.content:
            try:
                raw_txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", p_resp.content.strip(), flags=re.IGNORECASE)
                parsed = json.loads(raw_txt)
                cand_hl = str(parsed.get("headline") or "").strip()
                cand_bullets = [str(b).strip() for b in (parsed.get("bullets") or []) if str(b).strip()][:2]
                if _is_provider_explanation_grounded(cand_hl, cand_bullets, last_turn_summary):
                    prev_warn = str(last_turn_summary.get("basis_warning") or "").strip()
                    if prev_warn and prev_warn.casefold() not in " ".join([cand_hl, *cand_bullets]).casefold():
                        cand_bullets.append(f"Caveat: {prev_warn}")
                    det_lines = [str(b).strip() for b in (last_turn_summary.get("detail_bullets") or []) if str(b).strip()]
                    prev_hl = str(last_turn_summary.get("headline") or "").strip()
                    if prev_hl and prev_hl not in det_lines:
                        det_lines.append(f"Original summary: {prev_hl}")
                    meta["provider_used"] = p_resp.provider
                    meta["model_used"] = p_resp.model
                    return cand_hl, cand_bullets[:3], det_lines[:4], followups, "answer", meta
                provider_failure_reason = "validation_rejected"
            except Exception:
                provider_failure_reason = "invalid_json"
        else:
            provider_failure_reason = p_resp.outcome or "provider_unavailable"
        meta["fallback_outcome"] = provider_failure_reason
        meta["provider_used"] = p_resp.provider if p_resp.provider != "none" else "deterministic"

    headline, bullets, detail_bullets = _build_deterministic_plain_explanation(
        prompt=prompt,
        summary=last_turn_summary,
        provider_failure_reason=provider_failure_reason,
    )
    return headline, bullets, detail_bullets, followups, "answer", meta


def build_clarification_gate_payload(
    *,
    scope: dict[str, Any],
    session_state: SessionFilterContext,
    prompt: str = "",
    provider_reason: str | None = None,
) -> tuple[str, list[str], list[str]]:
    """Return a concise clarification prompt for vague data-less requests or unresolved provider failures (0 DB reads)."""
    followups = _build_role_aware_starter_followups(scope, session_state)[:3]
    if is_self_only(scope):
        headline = "Which part of your scorecard or which KPI or month would you like me to inspect?"
        bullets = [
            "Specify a KPI, a published month, or ask for your overall performance summary.",
        ]
        return headline, bullets, followups
    if is_bare_scope_or_period_refinement(prompt):
        token = (prompt or "").strip().rstrip("?.!")
        headline = f"What metric, team, or performance question would you like me to inspect for {token}?"
        bullets = [
            f"Specify what you want to see for {token}—such as a team score, KPI target, or overall overview.",
        ]
        return headline, bullets, followups
    if provider_reason and provider_reason not in ("ok", "disabled"):
        headline = "I couldn't classify that request automatically right now. Could you specify which team, KPI, or period you'd like to inspect?"
        bullets = [
            "The intent classification provider is temporarily unavailable, so please name a specific team, metric, employee, or ask for an overall summary.",
        ]
        return headline, bullets, followups
    headline = "Which team, KPI, person, or performance overview would you like me to inspect?"
    bullets = [
        "Specify a team, department, KPI, employee, or time period—or ask for an overall performance overview.",
    ]
    return headline, bullets, followups


def build_off_topic_gate_payload(
    *,
    scope: dict[str, Any],
    session_state: SessionFilterContext,
) -> tuple[str, list[str], list[str]]:
    """Return a concise domain-boundary response for non-PMS prompts (0 DB reads)."""
    followups = _build_role_aware_starter_followups(scope, session_state)[:3]
    headline = (
        "I can only help with PMS performance scorecards, KPIs, trends, comparisons, and corrective actions."
    )
    bullets = [
        "Try asking about overall performance, a team or KPI target, branch comparisons, or how I can help.",
    ]
    return headline, bullets, followups


def get_authorized_navigation_targets(
    scope: dict[str, Any],
    session_state: SessionFilterContext,
) -> list[AiNavigationTarget]:
    """Return role- and scope-filtered navigation destinations in PMS."""
    role = str(scope.get("role") or "Manager").strip()
    self_scoped = is_self_only(scope)
    emp_id = str(scope.get("employee_id") or session_state.employee_id or "").strip()
    team_name = session_state.team or "Inbound"
    team_slug = team_name.casefold().replace(" ", "-")
    period_qs = ""
    if session_state.month and session_state.year:
        period_qs = f"?month={session_state.month}&year={session_state.year}"

    targets: list[AiNavigationTarget] = []

    if self_scoped:
        scorecard_route = f"/employee/{emp_id}" if emp_id else f"/team/{team_slug}"
        targets.append(
            AiNavigationTarget(
                id="nav-my-scorecard",
                label="Open My Employee Scorecard →",
                route=scorecard_route,
                description="View your individual monthly KPI actuals, targets, grade, and assigned corrective actions.",
                icon_key="employee",
            )
        )
        return targets

    nav_fn_cf = (session_state.function or "").strip().casefold()
    nav_team_cf = (session_state.team or "").strip().casefold()
    nav_region_cf = (session_state.region or "").strip().casefold()
    is_uae_cc_nav = (
        (nav_fn_cf == "call center" or nav_team_cf in ("inbound", "outbound"))
        and nav_team_cf != "support positions"
        and "egy" not in nav_team_cf
        and "offshore" not in nav_team_cf
        and nav_region_cf in ("", "uae")
    )

    targets.append(
        AiNavigationTarget(
            id="nav-monthly-presentation",
            label=(
                f"Open Monthly Presentation ({session_state.function}) →"
                if session_state.function
                else "Open Monthly Presentation →"
            ),
            route=f"/monthly-presentation{period_qs}",
            description=(
                "Executive deck showing monthly KPI achievement, UAE 4-branch conversion, and top/bottom contributors."
                if is_uae_cc_nav
                else "Executive deck showing monthly KPI achievement, authorized branch breakdown, and top/bottom contributors."
            ),
            icon_key="presentation",
        )
    )
    targets.append(
        AiNavigationTarget(
            id="nav-team-dashboard",
            label=f"Open {team_name} Team Dashboard →",
            route=f"/team/{team_slug}{period_qs}",
            description=f"Inspect {team_name} employee scorecards, KPI breakdowns, grade distribution, and 6-month trends.",
            icon_key="team",
        )
    )
    targets.append(
        AiNavigationTarget(
            id="nav-insights",
            label="Open Executive Insights →",
            route=f"/insights{period_qs}",
            description="Cross-team priority insights, KPI diagnosis, and risk indicators for your authorized scope.",
            icon_key="insights",
        )
    )

    if role in {
        "Admin",
        "General Manager",
        "Manager",
        "Performance Team",
        "Executive",
        "Regional Manager",
        "Branch Director",
        "Function Director",
    }:
        targets.append(
            AiNavigationTarget(
                id="nav-corrective-actions",
                label="Open Corrective Actions Follow-Up →",
                route=f"/corrective-actions{period_qs}",
                description=(
                    "Review and create Open corrective actions, owners, and due dates."
                    if role in ACTION_WRITE_ROLES
                    else "Review corrective action follow-up status and overdue items (read-only for your role)."
                ),
                icon_key="actions",
            )
        )

    if role != "Branch Director" and user_can_access_team_level(scope, team_name, "Managerial"):
        targets.append(
            AiNavigationTarget(
                id="nav-balanced-scorecard",
                label="Open Balanced Scorecard (Managerial / Corporate) →",
                route=f"/executive{period_qs}",
                description="Inspect Managerial and Corporate Balanced Scorecard objectives and weights.",
                icon_key="bsc",
            )
        )

    return targets


def build_page_help_payload(
    *,
    req: AiChatRequest,
    scope: dict[str, Any],
    session_state: SessionFilterContext,
    selected_metric_display: str | None,
) -> tuple[str, list[str], AiPageHelpSection, list[AiNavigationTarget], list[str], str | None]:
    """Build curated, role-aware page explanation without reading employee performance rows."""
    page_id = normalize_page_id(req.page_context)
    role = str(scope.get("role") or "Manager").strip()
    can_write_actions = can_user_write_corrective_action(
        scope,
        team=session_state.team,
        performance_level=session_state.performance_level,
        branch=session_state.branch,
    )
    is_fallback = bool(req.page_context and req.page_context.is_fallback_data)
    fallback_warning = (
        "This page is currently displaying sample/fallback preview data because verified backend records were not loaded for this filter selection."
        if is_fallback
        else None
    )

    scope_label = session_state.team or session_state.function or "your authorized scope"
    period_label = (
        f"{session_state.month} {session_state.year}"
        if session_state.month and session_state.year
        else (session_state.month or "the active period")
    )
    variant_idx = resolve_variation_index(req.prompt, req.history, req.variation_seed)

    metric_explanation: str | None = None
    raw_metric = req.page_context.selected_metric_id if req.page_context else None
    if raw_metric or (session_state.last_confirmed_query and session_state.last_confirmed_query.metric_id):
        lookup_key = raw_metric or session_state.last_confirmed_query.metric_id  # type: ignore[union-attr]
        cat = get_ai_catalog()
        m_def = (
            cat.get_metric_by_id(lookup_key)
            if lookup_key and ":" in lookup_key
            else cat.find_metric_definition(
                team=session_state.team or "Inbound",
                position=session_state.position,
                kpi_key_or_label=lookup_key or "",
                performance_level=session_state.performance_level or "Employee",
            )
        )
        if m_def is not None:
            dir_text = "higher is better" if m_def.direction == "higher_better" else "lower is better"
            score_text = (
                f"carries a {m_def.weight_percent:.0f}% weight in the {m_def.team} ({m_def.performance_level}) scorecard"
                if m_def.contributes_to_score
                else "is tracked as a 0%-weight diagnostic indicator (does not change the overall PMS score)"
            )
            metric_explanation = f"{m_def.display_name} ({dir_text}) {score_text}."

    pc_fn = (req.page_context.function_id if req.page_context else None) or ""
    pc_team = (req.page_context.team_id if req.page_context else None) or ""
    pc_region = (req.page_context.region if req.page_context else None) or ""
    help_fn_cf = (session_state.function or pc_fn or "").strip().casefold()
    help_team_cf = (session_state.team or pc_team or "").strip().casefold()
    help_region_cf = (session_state.region or pc_region or "").strip().casefold()
    is_uae_cc_help = (
        (help_fn_cf == "call center" or help_team_cf in ("inbound", "outbound"))
        and help_team_cf != "support positions"
        and "egy" not in help_team_cf
        and "offshore" not in help_team_cf
        and help_region_cf in ("", "uae")
    )

    if page_id == "monthly_presentation":
        page_title = "Monthly Presentation"
        if is_uae_cc_help:
            summary = (
                f"Monthly Presentation summarizes {scope_label} KPI achievement against target, UAE 4-branch conversion, "
                f"and top/bottom score contributors for {period_label}."
            )
            key_elements = [
                "Executive KPI Summary Cards: Shows weighted achievement, actual vs. target values, and month-over-month movement.",
                "UAE 4-Branch Conversion Matrix: Compares Dubai, Sharjah, Ajman, and Clinics patient attendance and booking volumes.",
                "Contributor & Root-Cause Breakdown: Highlights which KPIs and records drove the monthly team score.",
            ]
        else:
            summary = (
                f"Monthly Presentation summarizes {scope_label} KPI achievement against target, authorized branch/team breakdown, "
                f"and top/bottom score contributors for {period_label}."
            )
            key_elements = [
                "Executive KPI Summary Cards: Shows weighted achievement, actual vs. target values, and month-over-month movement.",
                "Authorized Scope Breakdown: Compares KPI attainment and volume performance across authorized branches or sub-teams.",
                "Contributor & Root-Cause Breakdown: Highlights which KPIs and records drove the monthly team score.",
            ]
        if can_write_actions:
            available_actions = [
                "Switch function, team, performance level, branch, or month filters to inspect authorized performance.",
                "Select any KPI card and ask 'Why is this metric below target?' or 'Propose a corrective action' to review and save an Open corrective action.",
                "Export the presentation deck or drill down into the Team Dashboard.",
            ]
        else:
            available_actions = [
                f"Switch authorized filters to inspect {scope_label} KPI achievement and score drivers (your role '{role}' has read-only access to corrective actions).",
                "Select any KPI card and ask 'Why is this metric below target?' for a deterministic KPI diagnosis.",
            ]
        followups = [
            f"Why is {selected_metric_display or (scope_label + ' score')} below target in {period_label}?",
            f"Compare Dubai and Sharjah performance for {scope_label}"
            if is_uae_cc_help
            else f"Compare branches or sub-teams for {scope_label} in {period_label}",
            "What should we do to improve this metric?",
        ]
        if variant_idx == 1:
            summary = (
                f"Use Monthly Presentation to spot KPI target gaps in {scope_label}, pinpoint "
                + ("branch conversion slippage" if is_uae_cc_help else "score-driver slippage")
                + f", and move directly into corrective action planning for {period_label}."
            )
            followups = [followups[2], followups[0], followups[1]]
        elif variant_idx == 2:
            summary = (
                f"Monthly Presentation pairs weighted scorecard achievement with root-cause contributor breakdowns across "
                f"{scope_label} in {period_label} so managers can validate where recovery effort has the highest impact."
            )
            followups = [followups[1], followups[2], followups[0]]
    elif page_id == "team_dashboard":
        page_title = f"{scope_label} Team Dashboard"
        summary = (
            f"The Team Dashboard displays {scope_label} KPI achievement, individual employee scorecards, grade distributions, "
            f"and 6-month trends for {period_label}."
        )
        key_elements = [
            "Team KPI Header: Weighted team score, active employee count, and KPI actual vs. target achievement.",
            "Employee Roster & Scorecards: Individual agent scores, grades (A–E), and primary KPI gaps.",
            "Corrective Action Tracking: Open and In-Progress corrective actions linked to team members.",
        ]
        if can_write_actions:
            available_actions = [
                "Filter by position, performance level, branch, or month.",
                "Click an employee row to open their full scorecard or ask the assistant to draft an evidence-based Open corrective action.",
            ]
        else:
            available_actions = [
                f"Filter by authorized position, branch, or month and inspect employee scorecards (your role '{role}' is read-only for action creation).",
            ]
        followups = [
            f"Who is the lowest performer in {scope_label} in {period_label}?",
            f"Show {scope_label} KPI gaps against target in {period_label}",
            "Propose a corrective action for the biggest KPI gap",
        ]
        if variant_idx == 1:
            summary = (
                f"From the {scope_label} Team Dashboard, you can isolate bottom-quartile KPI drivers, inspect individual "
                f"scorecards, and track open corrective actions for {period_label}."
            )
            followups = [followups[1], followups[2], followups[0]]
        elif variant_idx == 2:
            summary = (
                f"The {scope_label} Team Dashboard tracks monthly score trajectory, grade spread (A–E), and action follow-through "
                f"across {period_label}."
            )
            followups = [followups[2], followups[0], followups[1]]
    elif page_id == "executive_summary":
        page_title = "Executive Summary & Balanced Scorecard"
        summary = (
            f"Executive Summary consolidates organization-wide performance scores, branch benchmarks, and Managerial/Corporate "
            f"Balanced Scorecard achievement for {scope_label} in {period_label}."
        )
        key_elements = [
            "Executive KPI Overview: Overall weighted score, month-over-month delta, and department/team leaderboard.",
            "Balanced Scorecard Matrix: Managerial and Corporate KPI weights, targets, and threshold bands.",
            "Risk & Governance Signals: Highlights underperforming teams, branch gaps, and open corrective actions.",
        ]
        available_actions = [
            "Switch between Managerial and Corporate performance levels or filter by branch and period.",
            "Drill down into any team dashboard or ask which KPIs dropped most versus target.",
        ]
        followups = [
            f"Which team in {scope_label} dropped most in {period_label}?",
            f"Compare branches in {scope_label} for {period_label}",
            f"Show KPI achievement vs target for {scope_label}",
        ]
        if variant_idx == 1:
            summary = (
                f"Use Executive Summary to pinpoint which teams and KPIs dragged down {scope_label} achievement "
                f"and where branch performance diverged in {period_label}."
            )
            followups = [followups[2], followups[0], followups[1]]
        elif variant_idx == 2:
            summary = (
                f"Executive Summary aligns Managerial and Corporate KPI weights with branch conversion benchmarks for "
                f"{scope_label} during {period_label}."
            )
            followups = [followups[1], followups[2], followups[0]]
    elif page_id == "function_summary":
        page_title = f"{scope_label} Function Summary"
        summary = (
            f"Function Summary compares sub-teams, KPI weights, and multi-month score trends within {scope_label} for {period_label}."
        )
        key_elements = [
            "Sub-Team Comparison: Ranks teams inside the function by weighted score and month-over-month change.",
            "KPI Contribution Matrix: Shows which weighted KPIs explain the function's current achievement.",
            "Historical Trajectory: Plots consecutive monthly movement across the active review window.",
        ]
        available_actions = [
            "Select a sub-team to inspect employee scorecards and team-level KPI diagnostics.",
            "Compare period-over-period drops to prioritize coaching or corrective actions.",
        ]
        followups = [
            f"Which team in {scope_label} dropped most in {period_label}?",
            f"Show 6-month performance trend for {scope_label}",
            f"What are the largest KPI gaps in {scope_label}?",
        ]
        if variant_idx == 1:
            summary = (
                f"Function Summary helps isolate which sub-team and weighted KPI caused {scope_label} movement in {period_label}."
            )
            followups = [followups[2], followups[0], followups[1]]
        elif variant_idx == 2:
            summary = (
                f"Review cross-team consistency and 6-month trend stability across {scope_label} in {period_label}."
            )
            followups = [followups[1], followups[2], followups[0]]
    elif page_id == "employee_profile":
        page_title = "Employee Scorecard"
        summary = (
            f"Employee Scorecard presents individual KPI actuals against targets, weighted score contributions, "
            f"grade history, and assigned corrective actions for {period_label}."
        )
        key_elements = [
            "Individual KPI Table: Displays each weighted KPI's actual, target, weight percentage, and achievement score.",
            "Score Trend & Grade History: Tracks month-over-month movement and grade transitions (A–E).",
            "Coaching & Corrective Actions: Lists active follow-ups and target completion dates.",
        ]
        available_actions = (
            [
                "Review below-target KPI drivers and inspect historical trend shifts.",
                "Draft or update an Open corrective action tied to a specific below-target KPI.",
            ]
            if can_write_actions
            else [
                "Inspect personal KPI weights, target gaps, and monthly score progression.",
                "Review assigned corrective actions and due dates.",
            ]
        )
        followups = [
            f"Why did performance change in {period_label}?",
            f"Which KPI has the largest gap in {period_label}?",
            "Show active corrective actions",
        ]
        if variant_idx == 1:
            summary = (
                f"Use Employee Scorecard to trace which weighted KPI drove score changes in {period_label} and verify coaching progress."
            )
            followups = [followups[1], followups[0], followups[2]]
        elif variant_idx == 2:
            summary = (
                f"Employee Scorecard connects monthly KPI achievement and multi-month consistency to active follow-up plans in {period_label}."
            )
            followups = [followups[2], followups[1], followups[0]]
    elif page_id == "insights":
        page_title = "Performance Insights"
        summary = (
            f"Performance Insights surfaces significant score drops, below-target KPI anomalies, branch variances, "
            f"and action priorities for {scope_label} in {period_label}."
        )
        key_elements = [
            "Automated Risk Signals: Flags material month-over-month declines and threshold breaches.",
            "KPI & Branch Outliers: Highlights where specific branches or metrics deviate from benchmark.",
            "Actionable Drill-Downs: Links each insight directly to the relevant team dashboard or corrective action flow.",
        ]
        available_actions = [
            "Filter insights by team, severity, or period within your authorized scope.",
            "Ask the assistant to explain a flagged drop or propose a corrective action.",
        ]
        followups = [
            f"Which team in {scope_label} dropped most in {period_label}?",
            f"What are the largest KPI gaps in {scope_label}?",
            "Show overdue corrective actions",
        ]
        if variant_idx == 1:
            summary = (
                f"Performance Insights prioritizes immediate operational risks and KPI outliers in {scope_label} for {period_label}."
            )
            followups = [followups[1], followups[2], followups[0]]
        elif variant_idx == 2:
            summary = (
                f"Review cross-branch anomalies and unresolved follow-up risks surfaced across {scope_label} in {period_label}."
            )
            followups = [followups[2], followups[0], followups[1]]
    elif page_id == "corrective_actions":
        page_title = "Corrective Actions Follow-Up"
        summary = (
            f"Corrective Actions Follow-Up tracks open, due-soon, overdue, and completed action plans across {scope_label} for {period_label}."
        )
        key_elements = [
            "Status & SLA Queue: Separates Open, In-Progress, Overdue, and Closed corrective actions.",
            "Evidence-Linked Targets: Ties each action to the underperforming KPI, owner, and deadline.",
            "Audit & Ownership Tracking: Shows reviewer notes, due dates, and completion status.",
        ]
        available_actions = (
            [
                "Filter by overdue or open status and drill into owner scorecards.",
                "Create or update an Open corrective action anchored to verified KPI gaps.",
            ]
            if can_write_actions
            else [
                f"Monitor open and overdue follow-up status across {scope_label} (your role '{role}' is read-only).",
            ]
        )
        followups = [
            "Show overdue corrective actions",
            f"Which team in {scope_label} dropped most in {period_label}?",
            "Propose a corrective action for the biggest KPI gap",
        ]
        if variant_idx == 1:
            summary = (
                f"Use Corrective Actions Follow-Up to clear overdue items first and verify that open actions target the largest KPI gaps in {scope_label}."
            )
            followups = [followups[2], followups[0], followups[1]]
        elif variant_idx == 2:
            summary = (
                f"Corrective Actions Follow-Up maintains accountability from KPI diagnosis through closure across {scope_label} in {period_label}."
            )
            followups = [followups[1], followups[2], followups[0]]
    else:
        page_title = "PMS AI Workspace"
        summary = (
            f"PMS AI Workspace answers analytical questions for {scope_label} in {period_label} using verified PMS calculation services."
        )
        key_elements = [
            "Deterministic KPI & Score Engine: All scores, targets, rankings, and branch comparisons come from PMS services.",
            "Scope & Permission Guardrails: Every answer is filtered to your authorized role, function, team, branch, and level.",
        ]
        available_actions = [
            "Ask about KPI gaps, period or branch comparisons, 6-month trends, top/bottom performers, or corrective action proposals.",
        ]
        followups = [
            f"What is {scope_label} score in {period_label}?",
            f"Show verified KPI score drivers for {scope_label}",
            "Where can I see corrective actions?",
        ]
        if variant_idx == 1:
            summary = (
                f"Ask PMS AI Workspace to diagnose KPI misses, compare authorized branches, or draft evidence-backed corrective actions for {scope_label} in {period_label}."
            )
            followups = [followups[1], followups[2], followups[0]]
        elif variant_idx == 2:
            summary = (
                f"Every answer in PMS AI Workspace is grounded in scoped PMS calculation records for {scope_label} ({period_label}) with full source citations."
            )
            followups = [followups[2], followups[0], followups[1]]

    if variant_idx == 2 and len(key_elements) > 1:
        key_elements = [key_elements[-1], *key_elements[:-1]]

    headline = summary
    if metric_explanation:
        headline = f"{summary} {metric_explanation}"

    bullets = list(key_elements[:2])
    if fallback_warning:
        bullets.insert(0, fallback_warning)

    help_section = AiPageHelpSection(
        page_id=page_id,
        page_title=page_title,
        summary=summary,
        key_elements=key_elements,
        available_actions=available_actions,
        metric_explanation=metric_explanation,
        fallback_data_warning=fallback_warning,
    )
    nav_targets = get_authorized_navigation_targets(scope, session_state)
    return headline, bullets, help_section, nav_targets, followups, fallback_warning


def build_navigation_payload(
    *,
    req: AiChatRequest,
    scope: dict[str, Any],
    session_state: SessionFilterContext,
) -> tuple[str, list[str], list[AiNavigationTarget], list[str]]:
    """Build role-aware navigation guidance without reading employee performance rows."""
    lower = (req.prompt or "").casefold()
    role = str(scope.get("role") or "Manager").strip()
    self_scoped = is_self_only(scope)
    emp_id = str(scope.get("employee_id") or session_state.employee_id or "").strip()
    team_name = session_state.team or session_state.function or "your authorized scope"
    team_slug = team_name.casefold().replace(" ", "-")
    targets = get_authorized_navigation_targets(scope, session_state)
    variant_idx = resolve_variation_index(req.prompt, req.history, req.variation_seed)

    if any(k in lower for k in ("upload", "import", "excel", "workbook")):
        if role in UPLOAD_WRITE_ROLES:
            upload_target = AiNavigationTarget(
                id="nav-uploads",
                label="Open Data Uploads →",
                route="/uploads",
                description="Upload and validate monthly PMS performance workbooks.",
                icon_key="planning",
            )
            return (
                "You can upload and validate monthly PMS workbooks in Data Uploads (/uploads).",
                ["Only Admin and authorized Manager accounts can upload performance workbooks."],
                [upload_target, *targets[:2]],
                ["What does this page show?", f"What is {team_name} score in the latest period?"],
            )
        return (
            f"Your role ({role}) has read-only analytics access and cannot upload workbooks.",
            ["Workbook uploads are restricted to Admin and authorized Manager accounts."],
            targets[:3],
            ["What does this page show?", "How do I find my scorecard?"],
        )

    if any(k in lower for k in ("setting", "manage user", "permission")):
        if role in SETTINGS_ADMIN_ROLES:
            settings_target = AiNavigationTarget(
                id="nav-settings",
                label="Open System Settings →",
                route="/settings",
                description="Manage user accounts, role permissions, and team assignments.",
                icon_key="planning",
            )
            return (
                "You can manage users, roles, and team permissions in System Settings (/settings).",
                ["System Settings is restricted to Admin accounts."],
                [settings_target, *targets[:2]],
                ["What does this page show?"],
            )
        return (
            f"System Settings is restricted to Admin accounts; your role ({role}) cannot modify user permissions.",
            ["Use the navigation links below to open your authorized dashboards and scorecards."],
            targets[:3],
            ["What does this page show?", "How do I find my scorecard?"],
        )

    if any(k in lower for k in ("balanced scorecard", "bsc", "managerial scorecard", "corporate scorecard")):
        if self_scoped or role == "Branch Director" or not user_can_access_team_level(scope, team_name, "Managerial"):
            return (
                f"Your current scope ({role}) does not include Managerial or Corporate Balanced Scorecards.",
                [
                    "Balanced Scorecards are evaluated at the team/function level for roles with Managerial or Corporate level access."
                ],
                targets[:3],
                [f"Show Employee performance for {team_name}", "What does this page show?"],
            )
        bsc_targets = [t for t in targets if t.id == "nav-balanced-scorecard"] + [
            t for t in targets if t.id != "nav-balanced-scorecard"
        ]
        return (
            "You can inspect Managerial and Corporate KPI weights and achievement in the Executive Summary Balanced Scorecard view (/executive).",
            ["Use the link below to open the Balanced Scorecard for your authorized scope."],
            bsc_targets[:3],
            [f"Show Managerial Balanced Scorecard for {team_name}", "What does this page show?"],
        )

    if any(k in lower for k in ("corrective action", "action plan", "follow-up", "follow up", "overdue")):
        if self_scoped:
            return (
                "You can view corrective actions assigned to you on your Employee Scorecard profile.",
                ["Self-scoped accounts view their assigned actions directly inside their scorecard."],
                targets,
                ["What is my performance score?"],
            )
        act_targets = [t for t in targets if t.id == "nav-corrective-actions"] + [
            t for t in targets if t.id != "nav-corrective-actions"
        ]
        write_note = (
            "Your role can review and create Open corrective actions."
            if role in ACTION_WRITE_ROLES
            else f"Your role ({role}) can view corrective action follow-ups in read-only mode."
        )
        return (
            "You can track open, due-soon, and overdue corrective actions in Corrective Actions Follow-Up (/corrective-actions).",
            [write_note],
            act_targets[:3],
            ["Show overdue corrective actions", "Propose a corrective action for the biggest KPI gap"],
        )

    if any(k in lower for k in ("my scorecard", "scorecard", "employee profile")):
        if self_scoped:
            return (
                "Open your Employee Scorecard using the link below to view your monthly KPI actuals, targets, and grade.",
                ["Your scorecard displays your personal KPI breakdown and historical trend."],
                targets,
                ["What is my performance score?"],
            )
        return (
            f"You can view {team_name} employee scorecards in the {team_name} Team Dashboard (/team/{team_slug}) or click any employee row to open their individual profile.",
            ["Use the Team Dashboard link below to browse authorized employee scorecards."],
            [t for t in targets if t.id == "nav-team-dashboard"] + [t for t in targets if t.id != "nav-team-dashboard"][:2],
            [f"Who is the lowest performer in {team_name}?", "What does this page show?"],
        )

    if variant_idx == 1:
        return (
            f"Use these authorized views to inspect {team_name} KPI drivers, team trends, and follow-up tasks for your {role} role.",
            ["Each destination preserves your active period and scope filters."],
            targets[:4],
            [f"What is {team_name} score in the latest period?", "What does this page show?"],
        )
    if variant_idx == 2:
        return (
            f"Available PMS dashboards for {team_name} ({role} scope) are listed below for direct drill-down.",
            ["Jump straight to scorecards, executive summaries, or corrective actions with your permissions enforced."],
            targets[:4],
            ["Show overdue corrective actions", "What does this page show?"],
        )
    return (
        f"Here are the authorized PMS views available for your {role} account in {team_name}.",
        ["Select a destination below to navigate directly with your current filters."],
        targets[:4],
        ["What does this page show?", f"What is {team_name} score in the latest period?"],
    )


def build_corrective_action_proposal_from_evidence(
    *,
    db: Session,
    scope: dict[str, Any],
    session_state: SessionFilterContext,
    typed_evidence: list[TypedMetricEvidence],
    records: list[Any],
    selected_metric_id: str | None = None,
    primary_source_link: DeepLinkCta | None = None,
) -> AiCorrectiveActionProposal | None:
    """Build an evidence-grounded corrective action proposal from verified PMS records and typed KPI evidence.

    Never invents causes, owners, deadlines, or guaranteed numeric impacts.
    """
    if not typed_evidence and not records:
        return None

    team_name = (
        session_state.team
        or (typed_evidence[0].team if typed_evidence else None)
        or (getattr(records[0], "team", None) if records else None)
        or "Inbound"
    )
    fn_name = session_state.function or function_for_team(team_name)
    level = session_state.performance_level or (typed_evidence[0].performance_level if typed_evidence else "Employee")
    branch = session_state.branch if session_state.branch and session_state.branch.casefold() != "all" else None
    month = session_state.month or (getattr(records[0], "month", "September") if records else "September")
    year = int(session_state.year or (getattr(records[0], "year", 2026) if records else 2026))
    period_label = f"{month} {year}"

    # Select target KPI evidence: prefer explicitly requested/selected metric, otherwise the scored metric with lowest achievement
    chosen_ev: TypedMetricEvidence | None = None
    if selected_metric_id and typed_evidence:
        sel_low = selected_metric_id.casefold()
        for ev in typed_evidence:
            if (
                ev.metric_id.casefold() == sel_low
                or ev.kpi_key.casefold() == sel_low
                or ev.display_name.casefold() == sel_low
                or sel_low in ev.metric_id.casefold()
            ):
                chosen_ev = ev
                break
    if chosen_ev is None and typed_evidence:
        scored_evs = [e for e in typed_evidence if e.contributes_to_score and e.achievement_percent is not None]
        if scored_evs:
            chosen_ev = min(scored_evs, key=lambda e: float(e.achievement_percent or 100.0))
        else:
            chosen_ev = typed_evidence[0]

    # Identify target employee if scoped to a single employee or find the most impacted employee in the scoped records
    target_emp_id: str | None = session_state.employee_id
    target_emp_name: str | None = None
    target_emp_score: float | None = None
    scoped_records = [
        r for r in records
        if str(getattr(r, "team", "")).casefold() == team_name.casefold()
        and (not month or str(getattr(r, "month", "")).casefold() == month.casefold())
    ] or list(records)

    if target_emp_id and scoped_records:
        for r in scoped_records:
            if str(getattr(r, "employee_id", "")).casefold() == target_emp_id.casefold():
                target_emp_id = str(r.employee_id)
                target_emp_name = str(r.employee_name)
                target_emp_score = float(r.evaluation.score) if getattr(r, "evaluation", None) and r.evaluation.score is not None else None
                break
    elif scoped_records:
        scored_recs = [
            r for r in scoped_records
            if getattr(r, "evaluation", None) is not None and r.evaluation.score is not None
        ]
        if scored_recs:
            lowest_rec = min(scored_recs, key=lambda r: (float(r.evaluation.score), str(r.employee_id)))
            target_emp_id = str(lowest_rec.employee_id)
            target_emp_name = str(lowest_rec.employee_name)
            target_emp_score = float(lowest_rec.evaluation.score)

    if chosen_ev is not None:
        metric_id = chosen_ev.metric_id
        linked_kpi_key = chosen_ev.kpi_key
        metric_display = chosen_ev.display_name
        actual_display = chosen_ev.actual_display
        target_display = chosen_ev.target_display
        ach = chosen_ev.achievement_percent
        sample_size = int(chosen_ev.sample_size or len(scoped_records))
        if ach is not None:
            gap_pts = round(max(0.0, 100.0 - float(ach)), 1)
            gap_display = f"{ach:.1f}% achievement ({gap_pts:.1f} pts below 100% target attainment)" if gap_pts > 0 else f"{ach:.1f}% achievement (on target)"
        else:
            gap_display = f"Actual {actual_display} vs. Target {target_display}"
        weight_note = f"{chosen_ev.weight_percent:.0f}% scorecard weight" if chosen_ev.contributes_to_score else "0% weight (tracking indicator)"
        observed_facts = [
            f"Observed PMS metric ({period_label}): {team_name} {metric_display} actual is {actual_display} vs. target {target_display} ({gap_display}, {weight_note}, n={sample_size} records)."
        ]
    else:
        metric_id = f"{team_name.casefold().replace(' ', '_')}:overall_score"
        linked_kpi_key = "OverallScore"
        metric_display = "Overall PMS Score"
        avg_score = (
            round(sum(float(r.evaluation.score) for r in scoped_records if getattr(r, "evaluation", None) and r.evaluation.score is not None) / max(1, len(scoped_records)), 1)
            if scoped_records
            else 0.0
        )
        actual_display = f"{avg_score:.1f}%"
        target_display = "100.0%"
        gap_display = f"{max(0.0, round(100.0 - avg_score, 1)):.1f} pts below 100%"
        sample_size = len(scoped_records)
        observed_facts = [
            f"Observed PMS score ({period_label}): {team_name} average score is {actual_display} across {sample_size} evaluated records."
        ]

    if target_emp_name and target_emp_id and target_emp_score is not None:
        observed_facts.append(
            f"Lowest evaluated record in scope: {target_emp_name} ({target_emp_id}) scored {target_emp_score:.1f}% in {period_label}."
        )

    ach_val = float(chosen_ev.achievement_percent) if (chosen_ev and chosen_ev.achievement_percent is not None) else (target_emp_score or 85.0)
    if ach_val < 75.0:
        priority: str = "High"
        action_type: str = "Coaching"
    elif ach_val < 95.0:
        priority = "Medium"
        action_type = "Coaching"
    else:
        priority = "Low"
        action_type = "Monitor"

    hypothesis = (
        f"Hypothesis (unverified — confirm with call/case logs before saving): "
        f"The gap on {metric_display} ({actual_display} vs. {target_display} target) may be driven by workflow adherence or volume spikes during {period_label}."
    )
    suggested_steps = [
        f"Review {period_label} sample records for {metric_display} ({actual_display} vs. {target_display} target) with the team supervisor.",
        f"Conduct targeted coaching focused on {metric_display} execution criteria and document agreed checkpoints.",
        f"Monitor {metric_display} weekly before the next monthly PMS evaluation.",
    ]
    success_measure = (
        f"Close the {metric_display} gap from {actual_display} toward the {target_display} PMS target in the next published monthly evaluation."
    )

    scope_parts = [team_name]
    if branch:
        scope_parts.append(branch.capitalize())
    scope_parts.append(level)
    scope_parts.append(period_label)
    if target_emp_name and target_emp_id:
        scope_parts.append(f"{target_emp_name} ({target_emp_id})")
    scope_summary = " · ".join(scope_parts)

    proposed_action_text = (
        f"Targeted coaching and sample review on {metric_display} ({actual_display} vs. {target_display} target in {period_label}); "
        f"track progress toward {target_display} in the next evaluation period."
    )
    proposed_root_cause_note = (
        f"PMS Evidence ({period_label}): {metric_display} at {actual_display} vs. {target_display} target ({gap_display}). "
        f"{hypothesis}"
    )

    ev_rev = _current_evidence_revision(db)
    can_write = can_user_write_corrective_action(
        scope,
        team=team_name,
        performance_level=level,
        branch=branch,
    )

    owners: list[dict[str, str]] = []
    if can_write:
        try:
            owners = CorrectiveActionService(db).list_owners(scope)[:15]
        except Exception:
            owners = []

    caller_uid = str(scope.get("user_id") or "").strip()
    caller_role = str(scope.get("role") or "Manager").strip()
    period_key = f"{year:04d}-{_MONTH_NAME_TO_NUM.get(month.casefold(), 9):02d}"
    proposal_seed = (
        f"{caller_uid}:{team_name}:{level}:{branch or 'all'}:{month}:{year}:"
        f"{metric_id}:{target_emp_id or 'team'}:{ev_rev}"
    )
    proposal_id = "prop-" + hashlib.sha256(proposal_seed.encode("utf-8")).hexdigest()[:12]

    eligible_owner_ids = {
        str(o.get("id") or o.get("user_id") or "").strip()
        for o in owners
        if isinstance(o, dict) and str(o.get("id") or o.get("user_id") or "").strip()
    }
    now_ts = time.time()
    with _ISSUED_PROPOSALS_LOCK:
        existing_issued = _ISSUED_PROPOSALS.get(proposal_id)
        if existing_issued is None or existing_issued.status != "confirmed":
            _ISSUED_PROPOSALS[proposal_id] = _IssuedProposalRecord(
                proposal_id=proposal_id,
                caller_user_id=caller_uid,
                caller_role=caller_role,
                team=team_name,
                performance_level=level,
                branch_key=branch,
                period=period_key,
                month=month,
                year=int(year),
                employee_id=target_emp_id,
                metric_id=metric_id,
                linked_kpi_key=linked_kpi_key,
                evidence_revision=ev_rev,
                issued_at=now_ts,
                expires_at=now_ts + PROPOSAL_TTL_SECONDS,
                status="issued",
                eligible_owner_ids=eligible_owner_ids,
            )

    return AiCorrectiveActionProposal(
        proposal_id=proposal_id,
        title=f"{action_type}: Improve {team_name} {metric_display} ({period_label})",
        scope_summary=scope_summary,
        team=team_name,
        function=fn_name,
        position=session_state.position,
        performance_level=level,
        branch_key=branch,
        period=period_key,
        month=month,
        year=year,
        employee_id=target_emp_id,
        employee_name=target_emp_name,
        metric_id=metric_id,
        linked_kpi_key=linked_kpi_key,
        metric_display_name=metric_display,
        actual_display=actual_display,
        target_display=target_display,
        gap_display=gap_display,
        sample_size=sample_size,
        observed_facts=observed_facts,
        hypothesis=hypothesis,
        suggested_steps=suggested_steps,
        success_measure=success_measure,
        action_type=action_type,  # type: ignore[arg-type]
        priority=priority,  # type: ignore[arg-type]
        proposed_action_text=proposed_action_text,
        proposed_root_cause_note=proposed_root_cause_note,
        evidence_revision=ev_rev,
        source_link=primary_source_link.route if primary_source_link else (chosen_ev.source_link if chosen_ev else None),
        can_user_create_action=can_write,
        persisted_status_on_save="Open",
        assignable_owners=owners,
    )


PROPOSAL_TTL_SECONDS = 3600.0


@dataclass
class _IssuedProposalRecord:
    proposal_id: str
    caller_user_id: str
    caller_role: str
    team: str
    performance_level: str
    branch_key: str | None
    period: str
    month: str
    year: int
    employee_id: str | None
    metric_id: str
    linked_kpi_key: str | None
    evidence_revision: str
    issued_at: float
    expires_at: float
    status: str = "issued"
    confirmed_response: dict[str, Any] | None = None
    confirmed_responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    eligible_owner_ids: set[str] = field(default_factory=set)


_ISSUED_PROPOSALS: dict[str, _IssuedProposalRecord] = {}
_ISSUED_PROPOSALS_LOCK = threading.RLock()


def cancel_corrective_action_proposal(proposal_id: str) -> bool:
    """Cancel an issued proposal so subsequent confirmation attempts fail closed."""
    with _ISSUED_PROPOSALS_LOCK:
        rec = _ISSUED_PROPOSALS.get((proposal_id or "").strip())
        if rec is None:
            return False
        rec.status = "cancelled"
        return True


def confirm_corrective_action_proposal(
    db: Session,
    scope: dict[str, Any],
    body: AiCorrectiveActionConfirmRequest,
) -> AiCorrectiveActionConfirmResponse:
    """Validate server-issued proposal, live permissions, scope, and evidence revision, then create an Open corrective action."""
    if body.is_fallback_data:
        raise CorrectiveActionValidationError(
            "Cannot create a corrective action from sample or fallback preview data."
        )

    prop_id = (body.proposal_id or "").strip()
    with _ISSUED_PROPOSALS_LOCK:
        issued = _ISSUED_PROPOSALS.get(prop_id)
        if issued is None:
            raise CorrectiveActionValidationError(
                "Unknown or unissued proposal_id. Corrective-action proposals must be generated by PMS AI before confirmation."
            )
        if issued.status == "cancelled":
            raise CorrectiveActionValidationError(
                "This corrective-action proposal has been cancelled and cannot be confirmed."
            )
        if time.time() > issued.expires_at:
            raise CorrectiveActionValidationError(
                "This corrective-action proposal has expired. Please refresh and generate a new proposal."
            )

        live_scope = AiConversationService(db, scope).validate_live_account_and_scope(scope)
        live_uid = str(live_scope.get("user_id") or "").strip()
        if issued.caller_user_id and live_uid != issued.caller_user_id:
            raise CorrectiveActionAccessError(
                "This corrective-action proposal was issued to a different user session."
            )

        norm_team = normalize_team_name(body.team) or body.team.strip()
        emp_id = (body.employee_id or "").strip() or None
        if (
            norm_team.casefold() != issued.team.casefold()
            or body.month.strip().casefold() != issued.month.casefold()
            or int(body.year) != int(issued.year)
            or (emp_id is not None and emp_id != (issued.employee_id or ""))
        ):
            raise CorrectiveActionValidationError(
                "Confirmation payload subject, team, or period does not match the server-issued proposal."
            )
        if (
            body.linked_kpi_key
            and issued.linked_kpi_key
            and body.linked_kpi_key.strip() != issued.linked_kpi_key
        ):
            raise CorrectiveActionValidationError(
                "Confirmation payload KPI key does not match the server-issued proposal."
            )

        if not can_user_write_corrective_action(
            live_scope,
            team=issued.team,
            performance_level=issued.performance_level,
            branch=issued.branch_key,
        ):
            raise CorrectiveActionAccessError(
                f"Your role ({live_scope.get('role') or 'Unknown'}) does not have write permission to create corrective actions for {issued.team}."
            )

        current_revision = _current_evidence_revision(db)
        if (
            body.evidence_revision.strip() != current_revision
            or issued.evidence_revision != current_revision
        ):
            raise ProposalStaleEvidenceError(
                "Underlying performance evidence has changed since this proposal was generated. Please refresh the proposal before saving."
            )

        scope_key = emp_id or "__team__"
        if scope_key in issued.confirmed_responses:
            return AiCorrectiveActionConfirmResponse.model_validate(issued.confirmed_responses[scope_key])

        if body.action_type not in ACTION_TYPES:
            raise CorrectiveActionValidationError(f"Unsupported action_type '{body.action_type}'.")
        if body.priority not in ACTION_PRIORITIES:
            raise CorrectiveActionValidationError(f"Unsupported priority '{body.priority}'.")
        if body.owner_user_id and body.owner_user_id.strip():
            owner_cand = body.owner_user_id.strip()
            if issued.eligible_owner_ids and owner_cand not in issued.eligible_owner_ids:
                raise CorrectiveActionValidationError(
                    "Selected owner_user_id is not an eligible owner for this scope."
                )

        user_id = live_uid or None

        if emp_id:
            svc = CorrectiveActionService(db)
            emp_row = db.query(Employee).filter(Employee.employee_id == emp_id).first()
            if emp_row is None:
                raise CorrectiveActionValidationError(
                    f"Employee '{emp_id}' does not exist in the canonical employee directory."
                )
            svc.ensure_employee_scope(emp_id, live_scope)

            act_type = body.action_type
            manager_action = f"{act_type}: {body.action_text.strip()}"
            kwargs: dict[str, Any] = {}
            if body.due_date and body.due_date.strip():
                kwargs["due_date"] = dt.date.fromisoformat(body.due_date.strip()[:10])
            if body.priority and body.priority in ACTION_PRIORITIES and "due_date" in kwargs:
                kwargs["priority"] = body.priority
            if body.owner_user_id and body.owner_user_id.strip() and "due_date" in kwargs:
                kwargs["owner_user_id"] = body.owner_user_id.strip()
            if body.linked_kpi_key and body.linked_kpi_key.strip():
                kwargs["linked_kpi_key"] = body.linked_kpi_key.strip()

            saved_action, _ = svc.save(
                employee_identifier=emp_id,
                month=issued.month,
                year=issued.year,
                manager_action=manager_action,
                manager_notes=body.root_cause_note.strip(),
                user_id=user_id,
                scope=live_scope,
                **kwargs,
            )
            resp = AiCorrectiveActionConfirmResponse(
                success=True,
                message=f"Corrective action saved with status {saved_action.get('status', 'Open')}",
                persisted_status="Open",
                action_scope="employee",
                action=saved_action,
            )
            issued.status = "confirmed"
            issued.confirmed_response = resp.model_dump()
            issued.confirmed_responses[scope_key] = resp.model_dump()
            return resp

        # Team-level action via TeamActionService — never create a Team row during confirmation
        team_row = (
            db.query(Team)
            .filter(
                Team.team_level == "employee",
                (Team.name.ilike(issued.team) | Team.display_name.ilike(issued.team)),
            )
            .first()
        )
        if team_row is None:
            raise CorrectiveActionValidationError(
                f"Team '{issued.team}' does not exist in the canonical team directory."
            )

        act_type = body.action_type
        overall_text = f"{act_type}: {body.action_text.strip()}"
        if body.root_cause_note.strip():
            overall_text = f"{overall_text} | Evidence: {body.root_cause_note.strip()}"

        try:
            saved_team_action = TeamActionService(db).save(
                team_reference=issued.team,
                month=issued.month,
                year=issued.year,
                overall_action=overall_text,
                scope=live_scope,
                user_id=user_id,
            )
        except PermissionError as exc:
            raise CorrectiveActionAccessError(str(exc)) from exc
        except ValueError as exc:
            raise CorrectiveActionValidationError(str(exc)) from exc

        saved_team_action["status"] = "Open"
        resp = AiCorrectiveActionConfirmResponse(
            success=True,
            message="Team corrective action saved with status Open",
            persisted_status="Open",
            action_scope="team",
            action=saved_team_action,
        )
        issued.status = "confirmed"
        issued.confirmed_response = resp.model_dump()
        issued.confirmed_responses[scope_key] = resp.model_dump()
        return resp
