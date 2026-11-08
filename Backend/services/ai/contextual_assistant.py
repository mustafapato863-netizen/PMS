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
from services.ai.local_model_router import local_intent_enabled, suggest_intent
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
        "ai_workspace": "AI Workspace",
    }.get(page_id, "PMS Assistant")

    parts: list[str] = [page_label]
    scope_name = session_state.team or session_state.function or "Call Center"
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


def detect_contextual_capability(
    req: AiChatRequest,
) -> tuple[ContextualCapabilityMode, str, float]:
    """Classify whether the turn is page_help, navigation, proposal, or performance_query.

    Returns (capability_mode, resolution_source, provider_ms).
    """
    if req.capability_hint in ("page_help", "navigation", "proposal", "performance_query"):
        return req.capability_hint, "local_rules", 0.0

    prompt = (req.prompt or "").strip()
    lower = prompt.casefold()

    for pat in _PAGE_HELP_PATTERNS:
        if pat.search(lower):
            return "page_help", "local_rules", 0.0

    for pat in _NAVIGATION_PATTERNS:
        if pat.search(lower):
            return "navigation", "local_rules", 0.0

    # If prompt asks to list/show existing overdue/open corrective actions, it is a performance_query, not a new proposal
    if re.search(r"\b(?:show|list|view|check|count|how\s+many|overdue)\b.*\bcorrective\s+actions?\b", lower):
        return "performance_query", "local_rules", 0.0

    for pat in _PROPOSAL_PATTERNS:
        if pat.search(lower):
            return "proposal", "local_rules", 0.0

    # If local model router is enabled and prompt contains contextual help/navigation/proposal cues without
    # explicit analytical data query keywords, allow Qwen3 4B to classify page_help / navigation / proposal intents.
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
        and not req.clarification_choice_id
    ):
        local_res = suggest_intent(prompt)
        if local_res.reason == "ok" and local_res.intent in ("page_help", "navigation", "proposal"):
            return local_res.intent, "local_model_router", local_res.elapsed_ms  # type: ignore[return-value]

    return "performance_query", "local_rules", 0.0


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

    targets.append(
        AiNavigationTarget(
            id="nav-monthly-presentation",
            label=f"Open Monthly Presentation ({session_state.function or 'Call Center'}) →",
            route=f"/monthly-presentation{period_qs}",
            description="Executive deck showing monthly KPI achievement, UAE 4-branch conversion, and top/bottom contributors.",
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

    scope_label = session_state.team or session_state.function or "Call Center"
    period_label = (
        f"{session_state.month} {session_state.year}"
        if session_state.month and session_state.year
        else (session_state.month or "the active period")
    )

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

    if page_id == "monthly_presentation":
        page_title = "Monthly Presentation"
        summary = (
            f"Monthly Presentation summarizes {scope_label} KPI achievement against target, UAE 4-branch conversion, "
            f"and top/bottom score contributors for {period_label}."
        )
        key_elements = [
            "Executive KPI Summary Cards: Shows weighted achievement, actual vs. target values, and month-over-month movement.",
            "UAE 4-Branch Conversion Matrix: Compares Dubai, Sharjah, Ajman, and Clinics patient attendance and booking volumes.",
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
                f"Switch authorized filters to inspect {scope_label} KPI achievement and branch conversion (your role '{role}' has read-only access to corrective actions).",
                "Select any KPI card and ask 'Why is this metric below target?' for a deterministic KPI diagnosis.",
            ]
        followups = [
            f"Why is {selected_metric_display or (scope_label + ' score')} below target in {period_label}?",
            f"Compare Dubai and Sharjah performance for {scope_label}",
            "What should we do to improve this metric?",
        ]
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
    team_name = session_state.team or "Inbound"
    team_slug = team_name.casefold().replace(" ", "-")
    targets = get_authorized_navigation_targets(scope, session_state)

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
