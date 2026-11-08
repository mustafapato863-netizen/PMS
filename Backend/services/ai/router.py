from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from models.ai_schemas import (
    AiClarificationPrompt,
    ClarificationChoice,
    ClarificationCodeType,
    ConfirmedQueryContext,
    RouterIntentType,
    SessionFilterContext,
    StructuredQueryPlan,
    TurnOutcomeType,
)
from models.report_schemas import MONTHS
from services.ai.catalog import (
    get_ai_catalog,
    resolve_canonical_team_name,
    user_can_access_branch,
    user_can_access_team,
)
from services.ai.config import get_ai_runtime_config
from services.ai.local_model_router import local_intent_enabled, suggest_intent
from services.ai.domain_policies import BRANCH_ALIASES, MONTH_ALIASES
from services.ai.entity_resolver import (
    EmployeeHistoryCandidate,
    resolve_employee_from_candidates,
)
from services.ai.providers import (
    GeminiStructuredRouterAdapter,
    ProviderCallMetrics,
    ProviderUnavailableError,
    is_prompt_safe_for_external_projection,
)
from utils.branch_scope import BRANCH_KEYS
from utils.report_scope import function_for_team, user_can_access_team_level

AiProviderUnavailableError = ProviderUnavailableError


UNAVAILABLE_FUTURE_PERIODS: frozenset[str] = frozenset(
    {"2026-10", "2026-11", "2026-12", "2027-01", "2027-02", "2027-03"}
)

ORDERED_TEAM_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Pre-Approvals IP Offshore",
        (
            "pre-approvals ip offshore",
            "offshore pre-approvals",
            "pre-approvals offshore",
            "pre approvals ip offshore",
        ),
    ),
    (
        "Pre-Approvals OP Final SHJAJM",
        (
            "pre-approvals op final shjajm",
            "pre approvals op final shjajm",
            "op final shjajm",
            "op final shj",
            "op sharjah",
        ),
    ),
    (
        "Pre-Approvals IP Final SHJAJM",
        (
            "pre-approvals ip final shjajm",
            "pre approvals ip final shjajm",
            "ip final shjajm",
            "ip final shj",
            "ip sharjah",
        ),
    ),
    (
        "Pre-Approvals OP Dubai",
        ("pre-approvals op dubai", "pre approvals op dubai", "op dubai"),
    ),
    (
        "Pre-Approvals IP Final Dubai",
        ("pre-approvals ip final dubai", "pre approvals ip final dubai", "ip final dubai"),
    ),
    (
        "Pre-Approvals IP Elective Dubai",
        ("pre-approvals ip elective dubai", "pre approvals ip elective dubai", "ip elective dubai"),
    ),
    (
        "Pre-Approvals OP Final",
        ("pre-approvals op final", "pre approvals op final"),
    ),
    (
        "Pre-Approvals IP Final",
        ("pre-approvals ip final", "pre approvals ip final"),
    ),
    (
        "Pre-Approvals IP Elective",
        ("pre-approvals ip elective", "pre approvals ip elective"),
    ),
    (
        "Pre-Approvals IP",
        (
            "pre-approvals ip",
            "pre approvals ip",
            "pre-authorization",
            "pre authorization",
            "ip pre-approvals",
        ),
    ),
    ("Coding EGY", ("coding egy", "egypt coding", "coding in egypt", "coding egypt")),
    ("Submission EGY", ("submission egy", "egypt submission", "submission in egypt", "submission egypt")),
    ("Resubmission", ("resubmission egy", "egypt resubmission", "resubmission in egypt", "resubmission egypt", "resubmission")),
    ("Re-Submission", ("re-submission", "re submission")),
    ("Submission", ("submission",)),
    ("Coding", ("coding",)),
    ("Inbound", ("inbound", "inboud", "انباوند", "إنباوند")),
    ("Outbound", ("outbound", "outboud", "اوتباوند", "أوتباوند")),
    (
        "Support Positions",
        (
            "support positions",
            "call center support positions",
            "call center support",
            "support roles",
            "support position",
            "support team",
            "support employee",
            "support employees",
            "support staff",
            "support agent",
            "support agents",
            "lowest in support",
            "best in support",
            "top in support",
            "worst in support",
            "in support",
            "from support",
            "for support",
        ),
    ),
    ("Marketing", ("marketing", "ماركتنج", "التسويق")),
    ("Pharmacy", ("pharmacy",)),
    ("CSR", ("csr",)),
    ("Sales", ("sales",)),
    ("Finance", ("finance",)),
    ("Human Resources", ("human resources", "hr team", "hr department", "in hr", "for hr")),
    ("IT", ("it team", "information technology", "it department", "in it", "for it")),
    ("Offshore Admin & Management", ("offshore admin & management", "offshore admin", "admin & management")),
    ("CRM", ("crm", "customer relationship management", "crm corporate", "crm bsc", "crm management")),
    ("Nursing", ("nursing", "nursing corporate", "nursing bsc", "nursing management")),
    ("PMO", ("pmo", "project management office", "pmo corporate", "pmo bsc", "pmo management")),
    (
        "RCM",
        (
            "rcm corporate",
            "rcm bsc",
            "rcm management",
            "rcm leadership",
            "group rcm",
            "rcm scorecard",
            "rcm team",
        ),
    ),
)

POSITION_PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Support Positions", "Call Center trainer", ("call center trainer", "trainer")),
    (
        "Support Positions",
        "Quality Assurance",
        ("quality assurance", "quality specialist", "qa specialist"),
    ),
    ("Support Positions", "Workforce analyst", ("workforce analyst", "wfm analyst")),
    ("Support Positions", "Inbound Team Leader", ("inbound team leader",)),
    ("Support Positions", "Outbound Team Leader", ("outbound team leader",)),
    ("Marketing", "Media Buyer", ("media buyer", "media buyers")),
    ("Marketing", "Graphic Designer", ("graphic designer", "graphic designers")),
    ("Marketing", "Social Media Specialist", ("social media specialist",)),
    ("Marketing", "Account Manager", ("account manager", "account managers")),
    ("Marketing", "Digital Marketing Manager", ("digital marketing manager",)),
    ("Pharmacy", "AJM Pharmacy Manager", ("ajm pharmacy manager",)),
    ("Pharmacy", "SGH UAE Group Pharmacy Director", ("group pharmacy director",)),
    (
        "Pre-Approvals IP",
        "Pre-Authorization Senior Specialist",
        ("pre-authorization senior specialist", "pre authorization senior specialist"),
    ),
    (
        "Pre-Approvals IP",
        "Pre-Authorization Specialist",
        ("pre-authorization specialist", "pre authorization specialist"),
    ),
    (
        "Pre-Approvals IP",
        "Pre-Authorization Supervisor",
        ("pre-authorization supervisor", "pre authorization supervisor"),
    ),
    ("Coding EGY", "RCM -SHJ- OP CODING", ("rcm -shj- op coding", "op coding")),
    ("Submission EGY", "Claim & Audit Specialist", ("claim & audit specialist", "claim and audit specialist")),
    ("Resubmission", "Resubmission Analyst", ("resubmission analyst",)),
    ("Human Resources", "Personnel Certified", ("personnel certified",)),
    ("Human Resources", "Recruitment Organic", ("recruitment organic",)),
    ("IT", "IT Help Desk", ("it help desk", "help desk")),
    ("IT", "System Administrator", ("system administrator", "sysadmin")),
    ("Offshore Admin & Management", "Office Admin", ("office admin",)),
    ("Offshore Admin & Management", "Operations Director", ("operations director",)),
    ("Finance", "FP&A Manager", ("fp&a manager", "fpa manager")),
    ("Finance", "Finance Controller", ("finance controller",)),
    ("Finance", "General Accountant", ("general accountant",)),
    ("Finance", "Head of Accounts Payable", ("head of accounts payable",)),
    ("Finance", "Head of Accounts Receivable", ("head of accounts receivable",)),
    ("Finance", "Head of Taxation", ("head of taxation",)),
    ("Finance", "Head of Treasury", ("head of treasury",)),
    ("Finance", "CFO", ("cfo", "chief financial officer")),
    ("RCM", "Group Claims Operations Manager", ("group claims operations manager",)),
    ("RCM", "Group Clinical Revenue Manager", ("group clinical revenue manager",)),
    ("RCM", "RCM Manager SHJ, AJM", ("rcm manager shj, ajm", "rcm manager shj ajm")),
    ("RCM", "Group RCM Director", ("group rcm director",)),
    ("CRM", "Group CRM Director", ("group crm director",)),
    ("Nursing", "SGH UAE Group Nursing Director", ("group nursing director",)),
    ("PMO", "Enterprise Project Management Office Manager", ("enterprise project management office manager", "pmo manager")),
)


@dataclass
class RouterValidationResult:
    outcome: TurnOutcomeType
    plan: StructuredQueryPlan
    confirmed_context: ConfirmedQueryContext
    inherited_filters: list[str] = field(default_factory=list)
    clarification: AiClarificationPrompt | None = None
    headline: str | None = None
    narrative_bullets: list[str] = field(default_factory=list)
    suggested_followups: list[str] = field(default_factory=list)
    route_used: str = "local_rules"
    provider_metrics: ProviderCallMetrics = field(default_factory=ProviderCallMetrics)
    shadow_plan: dict[str, Any] | None = None


REVERSE_MONTHS_BY_NUM: dict[int, str] = {v: k for k, v in MONTHS.items()}


def _period_key_from_month_year(month_name: str, year: int = 2026) -> str:
    m_num = MONTHS.get(month_name, 9)
    return f"{year:04d}-{m_num:02d}"


def _format_period_label(period_key: str) -> str:
    try:
        yr_s, mo_s = period_key.split("-", 1)
        m_name = REVERSE_MONTHS_BY_NUM.get(int(mo_s), "September")
        return f"{m_name} {int(yr_s)}"
    except Exception:
        return "September 2026"


def _extract_periods(
    text_lower: str,
    default_month: str | None,
    default_year: int | None,
    fallback_period: str = "2026-09",
) -> list[str]:
    year_matches = [int(y) for y in re.findall(r"\b(20\d{2}|2100)\b", text_lower)]
    default_yr = year_matches[0] if year_matches else (default_year or 2026)

    found_months: list[tuple[int, str]] = []
    # Match longest aliases first to avoid 'sep' matching inside 'september' twice
    sorted_aliases = sorted(MONTH_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True)
    used_spans: list[tuple[int, int]] = []
    for alias, canonical_month in sorted_aliases:
        for m in re.finditer(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text_lower):
            span = m.span()
            if any(not (span[1] <= s[0] or span[0] >= s[1]) for s in used_spans):
                continue
            used_spans.append(span)
            found_months.append((span[0], canonical_month))

    found_months.sort(key=lambda item: item[0])
    periods: list[str] = []
    for _, m_name in found_months:
        pk = _period_key_from_month_year(m_name, default_yr)
        if pk not in periods:
            periods.append(pk)

    if not periods and default_month and default_month in MONTHS:
        periods.append(_period_key_from_month_year(default_month, default_yr))
    elif not periods:
        periods.append(fallback_period)

    if len(periods) > 1:
        periods.sort()
    return periods


def _detect_teams_in_prompt(text_lower: str) -> list[str]:
    detected: list[tuple[int, str]] = []
    used_spans: list[tuple[int, int]] = []
    for canonical, aliases in ORDERED_TEAM_PATTERNS:
        for alias in aliases:
            m = re.search(rf"(?<![a-z0-9\-]){re.escape(alias)}(?![a-z0-9\-])", text_lower)
            if m:
                span = m.span()
                if any(not (span[1] <= s[0] or span[0] >= s[1]) for s in used_spans):
                    continue
                used_spans.append(span)
                detected.append((span[0], canonical))
                break
    detected.sort(key=lambda x: x[0])
    return [t for _, t in detected]


def _detect_position(text_lower: str) -> tuple[str | None, str | None]:
    for team_name, pos_name, aliases in POSITION_PATTERNS:
        for alias in aliases:
            if alias in text_lower:
                return team_name, pos_name
    return None, None


def _detect_branches_in_prompt(text_lower: str, detected_team: str | None) -> list[str]:
    # Strip team names like "Pre-Approvals OP Dubai" / "OP Dubai" / "IP Sharjah" before scanning branch aliases
    # so "Dubai" or "Sharjah" inside a team name is not mistaken for a branch filter unless separately specified.
    cleaned = text_lower
    if detected_team:
        cleaned = cleaned.replace(detected_team.casefold(), " ")
        for canonical, aliases in ORDERED_TEAM_PATTERNS:
            if canonical.casefold() == detected_team.casefold():
                for alias in aliases:
                    cleaned = cleaned.replace(alias.casefold(), " ")

    found: list[tuple[int, str]] = []
    used_spans: list[tuple[int, int]] = []
    sorted_aliases = sorted(BRANCH_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True)
    for alias, canonical in sorted_aliases:
        for m in re.finditer(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", cleaned):
            span = m.span()
            if any(not (span[1] <= s[0] or span[0] >= s[1]) for s in used_spans):
                continue
            used_spans.append(span)
            found.append((span[0], canonical))
    found.sort(key=lambda x: x[0])
    unique_branches: list[str] = []
    for _, b in found:
        if b not in unique_branches:
            unique_branches.append(b)
    return unique_branches


def _detect_metric_id(
    text_lower: str,
    *,
    team: str | None,
    position: str | None,
    performance_level: str,
) -> str | None:
    # Do not assign a single metric when the prompt lists multiple KPIs in parentheses or asks for overall KPI gaps/drivers
    if "(" in text_lower and "," in text_lower and "kpis" in text_lower:
        return None
    if any(
        phrase in text_lower
        for phrase in (
            "kpi gaps",
            "score drivers",
            "kpi bottlenecks",
            "main kpi driver",
            "which kpis drove",
            "attendance and booking conversion",
        )
    ):
        return None

    t_norm = (team or "").strip().casefold()
    lvl_norm = (performance_level or "Employee").strip().casefold()

    # Managerial / Corporate BSC metrics
    if lvl_norm == "managerial":
        if "team sla" in text_lower or "sla" in text_lower:
            return f"{t_norm or 'inbound'}:team_sla"
        if "attendance compliance" in text_lower:
            return f"{t_norm or 'inbound'}:attendance_compliance"

    # Marketing position metrics
    if t_norm == "marketing" or position:
        if "cpl" in text_lower:
            return "marketing:mb_cpl"
        if "leads" in text_lower:
            return "marketing:mb_leads"
        if "rework" in text_lower:
            return "marketing:gd_rework"
        if "response time" in text_lower:
            return "marketing:sms_response_time"

    # Pharmacy metrics
    if t_norm == "pharmacy":
        if "iv cost saving" in text_lower:
            return "pharmacy:ajm_pharmacy_man_iv_cost_saving"
        if "waiting time" in text_lower:
            return "pharmacy:waitingtime"
        if "leakage" in text_lower:
            return "pharmacy:leakage"
        if "tender compliance" in text_lower:
            return "pharmacy:tendercompliance"
        if "average transaction value" in text_lower or "atv" in text_lower:
            return "pharmacy:atv"

    # Pre-Approvals IP Offshore metrics
    if "offshore" in t_norm:
        if "policy rejection" in text_lower:
            return "pre_approvals_ip_offshore:policyrejection"
        if "rejection" in text_lower:
            return "pre_approvals_ip_offshore:rejection"

    # Call Center metrics
    if any(k in text_lower for k in ("abandon", "abondan", "abandoned")):
        return "inbound:abandon_rate"
    if "reachability" in text_lower:
        return "outbound:reachability"
    if any(k in text_lower for k in ("aht", "handle time")):
        prefix = "outbound" if t_norm == "outbound" else "inbound"
        return f"{prefix}:aht"
    if any(
        k in text_lower
        for k in (
            "more bookings",
            "most bookings",
            "fewer bookings",
            "least bookings",
            "bookings count",
            "total bookings",
            "number of bookings",
            "booking volume",
            "how many bookings",
        )
    ):
        prefix = "outbound" if t_norm == "outbound" else "inbound"
        return f"{prefix}:bookings_count"
    if any(
        k in text_lower
        for k in ("booking rate", "booking conversion", "booking trend", "by booking", "on booking")
    ) or (
        t_norm in ("inbound", "outbound", "call center", "")
        and re.search(r"\bbookings?\b", text_lower)
        and "attendance" not in text_lower
        and "attended" not in text_lower
    ):
        prefix = "outbound" if t_norm == "outbound" else "inbound"
        return f"{prefix}:booking_rate"
    if any(k in text_lower for k in ("quality score", "qa quality", "quality achievement")):
        prefix = "outbound" if t_norm == "outbound" else "inbound"
        return f"{prefix}:quality_score"
    if any(
        k in text_lower
        for k in (
            "attendance rate",
            "patient attendance",
            "patient attended",
        )
    ):
        prefix = "outbound" if t_norm == "outbound" else "inbound"
        return f"{prefix}:attendance_rate"

    return None


def _extract_person_query_from_prompt(text: str) -> str | None:
    lower = (text or "").strip().casefold()
    emp_id_match = re.search(r"\b(sghd\d+|emp[-_ ]?\d+|e[-_]\d+)\b", lower)
    if emp_id_match:
        return emp_id_match.group(1).upper()

    name_patterns = [
        r"\b([a-zA-Z]+(?:\s+[a-zA-Z]+){0,3})'s\b",
        r"\b(?:is|was|did)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,3})\s+(?:(?:a\s+)?new\s+joiner|new\s+in|join\b)",
        r"\b([a-zA-Z]+(?:\s+[a-zA-Z]+){0,3})\s+(?:is|was)\s+(?:a\s+)?new\s+joiner\b",
        r"\bwhen\s+did\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,3})\s+join\b",
        r"(?:employee|agent|for|about|trend of|trend for|score of|profile of)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,3})",
    ]
    stop_words = {
        "inbound", "outbound", "call", "center", "dubai", "sharjah", "ajman", "clinics",
        "all", "team", "teams", "branch", "branches", "the", "his", "her", "and", "in",
        "on", "at", "to", "from", "with", "who", "what", "which", "better", "best", "worst",
        "lowest", "top", "bottom", "trend", "month", "january", "february", "march", "april",
        "may", "june", "july", "august", "september", "october", "november", "december",
        "had", "has", "have", "was", "were", "is", "are", "led", "leads", "leading",
        "scored", "scores", "scoring", "performed", "performing", "performance", "score",
        "rate", "by", "for", "of", "support", "positions", "position", "employee", "employees",
        "agent", "agents", "performer", "performers", "highest", "there", "anyone", "somebody",
        "recently", "new", "joiner", "joiners", "a", "an",
        "booking", "bookings", "attendance", "attended", "abandon", "abandoned",
        "reachability", "aht", "quality", "kpi", "kpis", "metric", "metrics",
        "target", "targets", "gap", "action", "actions", "corrective", "coaching",
        "plan", "proposal", "this", "page", "view", "dashboard", "scorecard",
        "presentation", "monthly", "summary", "executive", "managerial", "corporate",
    }
    for pat in name_patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            raw_tokens = [
                tok for tok in m.group(1).strip().split()
                if tok.casefold() not in stop_words
            ]
            if raw_tokens:
                return " ".join(raw_tokens)
    return None


_COUNT_WORDS: dict[int, str] = {
    2: "two",
    3: "three",
    4: "four",
    5: "five",
}


class HybridQueryRouter:
    """Local-first query router and pre-read validator for PMS AI."""

    def __init__(
        self,
        *,
        scope: dict[str, Any],
        published_periods: Iterable[str] | None = None,
        employee_candidates: Iterable[EmployeeHistoryCandidate] | None = None,
    ) -> None:
        self.scope = scope
        self.catalog = get_ai_catalog()
        self.published_periods: set[str] | None = (
            {str(p).strip() for p in published_periods if re.match(r"^\d{4}-(0[1-9]|1[0-2])$", str(p).strip())}
            if published_periods is not None
            else None
        )
        self.latest_published_period: str = (
            max(self.published_periods) if self.published_periods else "2026-09"
        )
        self.employee_candidates: list[EmployeeHistoryCandidate] = (
            list(employee_candidates) if employee_candidates is not None else []
        )

    def resolve_and_validate(
        self,
        *,
        prompt: str,
        session_state: SessionFilterContext,
        provider_override: str = "auto",
        clarification_choice_id: str | None = None,
    ) -> RouterValidationResult:
        cfg = get_ai_runtime_config()
        text = (prompt or "").strip()
        prior = session_state.last_confirmed_query
        matched_choice: ClarificationChoice | None = None
        if clarification_choice_id and prior and prior.pending_clarification_choices:
            matched_choice = next(
                (c for c in prior.pending_clarification_choices if c.id == clarification_choice_id),
                None,
            )
            if matched_choice and matched_choice.prompt_to_send:
                text = matched_choice.prompt_to_send.strip()
        lower = text.casefold()

        # 1. Unsupported Write / Mutation Guardrail
        if any(
            re.search(pat, lower)
            for pat in (
                r"\bdelete\b.*\bevaluation\b",
                r"\bupdate\b.*\btarget\b",
                r"\brecalculate\s+scores\b",
                r"\bapprove\s+and\s+close\b",
                r"\bmodify\s+score\b",
                r"\bdrop\s+table\b",
            )
        ):
            plan = StructuredQueryPlan(intent="unsupported")
            return RouterValidationResult(
                outcome="unsupported_request",
                plan=plan,
                confirmed_context=ConfirmedQueryContext(intent="unsupported"),
                headline=(
                    "PMS AI is a read-only diagnostic workspace and cannot modify evaluations, "
                    "targets, or corrective action statuses directly."
                ),
                narrative_bullets=[
                    "Use the Evaluation Engine or Corrective Actions page to submit authorized changes."
                ],
                suggested_followups=[
                    "Show overdue corrective actions and their owners for Call Center",
                    "Analyze Inbound KPI gaps in September 2026",
                ],
            )

        # 2. Extract explicit entities from the prompt
        raw_teams_in_prompt = _detect_teams_in_prompt(lower)
        if not raw_teams_in_prompt and re.search(
            r"\b(?:weather|poem|football|soccer|recipe|joke|horoscope|movie|song|capital\s+of)\b",
            lower,
        ):
            plan = StructuredQueryPlan(intent="unsupported", turn_kind_v2="unsupported")
            return RouterValidationResult(
                outcome="unsupported_request",
                plan=plan,
                confirmed_context=ConfirmedQueryContext(intent="unsupported"),
                headline=(
                    "I cannot answer that request — PMS AI only analyzes PMS performance scorecards, "
                    "KPIs, trends, branches, and corrective actions."
                ),
                narrative_bullets=[
                    "Ask about team performance scores, KPI targets and gaps, branch comparisons, or employee rankings."
                ],
                suggested_followups=["What is the Inbound score in September 2026?"],
            )
        teams_in_prompt: list[str] = []
        has_egy_hint = bool(re.search(r"\b(?:egy|egypt)\b", lower))
        has_uae_hint = bool(re.search(r"\buae\b", lower))
        for raw_t in raw_teams_in_prompt:
            resolved_t = raw_t
            if has_egy_hint:
                resolved_t = resolve_canonical_team_name(raw_t, prompt=lower, scope=self.scope) or raw_t
            elif raw_t == "Re-Submission" and "resubmission" in lower and "re-submission" not in lower and not has_uae_hint:
                resolved_t = resolve_canonical_team_name("resubmission", prompt=lower, scope=self.scope) or raw_t
            if resolved_t not in teams_in_prompt:
                teams_in_prompt.append(resolved_t)
        pos_team, detected_pos = _detect_position(lower)
        if pos_team and not teams_in_prompt:
            teams_in_prompt = [pos_team]

        asks_team_comparison = (
            len(teams_in_prompt) >= 2
            or "which call center team" in lower
            or "which rcm team" in lower
            or "compare call center teams" in lower
            or "which team dropped" in lower
        )
        explicit_team = None if asks_team_comparison else (teams_in_prompt[0] if teams_in_prompt else None)

        explicit_branches = _detect_branches_in_prompt(lower, explicit_team)
        asks_branch_comparison = (
            len(explicit_branches) >= 2
            or "all uae branches" in lower
            or "across all branches" in lower
            or "branch comparison" in lower
            or "compare all branches" in lower
            or "which branch" in lower
            or "what branch" in lower
        )
        explicit_branch = explicit_branches[0] if explicit_branches else None
        explicit_compare_branch = explicit_branches[1] if len(explicit_branches) >= 2 else None

        explicit_level: str | None = None
        if "corporate" in lower or detected_pos in (
            "CFO",
            "Digital Marketing Manager",
            "SGH UAE Group Pharmacy Director",
            "Group RCM Director",
            "Group CRM Director",
            "SGH UAE Group Nursing Director",
            "Enterprise Project Management Office Manager",
        ):
            explicit_level = "Corporate"
        elif any(k in lower for k in ("managerial", "team sla", "attendance compliance")) or detected_pos == "Pre-Authorization Supervisor":
            explicit_level = "Managerial"

        has_explicit_month = any(
            re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lower)
            for alias in MONTH_ALIASES
        )
        explicit_periods = _extract_periods(
            lower,
            session_state.month,
            session_state.year,
            fallback_period=self.latest_published_period,
        )

        # 3. Context Inheritance for Follow-Up Questions
        inherited_filters: list[str] = []
        is_ranking_correction = bool(
            prior
            and (prior.intent == "ranking" or prior.last_operation_kind in ("ranking", "person_summary"))
            and re.search(
                r"\b(?:no\b|i\s+mean(?:t)?\b|instead\b|actually\b|what\s+about\s+the\s+(?:lowest|worst|highest|best|top))",
                lower,
            )
            and any(w in lower for w in ("lowest", "worst", "bottom", "highest", "best", "top"))
        )
        is_deictic_context_ref = any(
            phrase in lower
            for phrase in (
                "this metric",
                "this kpi",
                "this score",
                "this card",
                "this team",
                "about this",
                "for this",
                "improve this",
                "fix this",
            )
        )
        is_short_followup = bool(
            prior
            and (
                is_ranking_correction
                or is_deictic_context_ref
                or lower.startswith("and ")
                or lower.startswith("what about ")
                or "compare it with" in lower
                or len(text.split()) <= 5
            )
        )

        eff_team = explicit_team
        if not eff_team and not asks_team_comparison:
            if matched_choice and matched_choice.team:
                eff_team = matched_choice.team
            elif is_short_followup and prior and prior.team:
                eff_team = prior.team
                inherited_filters.append("team")
            elif session_state.team and session_state.team not in ("All", "all"):
                eff_team = session_state.team

        eff_pos = detected_pos
        if not eff_pos:
            if matched_choice and matched_choice.position:
                eff_pos = matched_choice.position
            elif is_short_followup and prior and prior.position:
                if not explicit_team or explicit_team == prior.team:
                    eff_pos = prior.position
                    inherited_filters.append("position")
            elif (
                session_state.position
                and session_state.position not in ("All", "all", "")
                and (not explicit_team or explicit_team in (session_state.team, "Support Positions", "Call Center"))
            ):
                eff_pos = session_state.position
                if not eff_team:
                    eff_team = "Support Positions"

        prior_was_branch_comparison = bool(
            prior
            and (
                prior.intent == "compare_branches"
                or prior.comparison_type == "branch"
                or len(prior.branches or []) >= 2
            )
        )
        eff_branch = explicit_branch
        if not eff_branch and not asks_branch_comparison:
            if matched_choice and matched_choice.branch:
                eff_branch = matched_choice.branch
            elif is_short_followup and prior and prior.branch and not prior_was_branch_comparison:
                eff_branch = prior.branch
                inherited_filters.append("branch")
            elif (
                session_state.branch
                and session_state.branch.casefold() not in ("all", "")
                and not explicit_team
            ):
                # Note: only inherit session_state.branch if prompt didn't explicitly ask a global team question
                pass

        eff_branches: list[str] = list(explicit_branches)
        if not eff_branches:
            if is_short_followup and prior and prior.branches and not prior_was_branch_comparison:
                eff_branches = list(prior.branches)
            elif eff_branch:
                eff_branches = [eff_branch]

        eff_level = explicit_level or (
            matched_choice.performance_level
            if (matched_choice and matched_choice.performance_level)
            else (
                "Corporate"
                if eff_team in ("CRM", "Nursing", "PMO")
                else (
                    prior.performance_level
                    if (is_short_followup and prior and prior.performance_level)
                    else (
                        session_state.performance_level
                        if session_state.performance_level not in (None, "", "All", "all")
                        else "Employee"
                    )
                )
            )
        )

        explicit_metric = (
            matched_choice.metric_id
            if (matched_choice and matched_choice.metric_id)
            else _detect_metric_id(
                lower,
                team=eff_team,
                position=eff_pos,
                performance_level=eff_level,
            )
        )
        eff_metric = explicit_metric
        if not eff_metric and is_short_followup and prior and prior.metric_id:
            # Inherit metric only if team did not switch to an incompatible team
            prior_metric_team = prior.metric_id.split(":")[0]
            if not eff_team or eff_team.casefold().startswith(prior_metric_team):
                eff_metric = prior.metric_id
                inherited_filters.append("metric")

        # Infer or correct team from unambiguous Call Center metric (e.g. reachability -> Outbound, abandon_rate -> Inbound)
        if not explicit_team and explicit_metric:
            if explicit_metric == "outbound:reachability":
                eff_team = "Outbound"
            elif explicit_metric == "inbound:abandon_rate":
                eff_team = "Inbound"
        if not eff_team and eff_metric:
            if eff_metric.startswith("inbound:"):
                eff_team = "Inbound"
            elif eff_metric.startswith("outbound:"):
                eff_team = "Outbound"

        eff_fn = session_state.function or (function_for_team(eff_team) if eff_team else "Call Center")
        if eff_team:
            inferred_fn = function_for_team(eff_team)
            if inferred_fn and (not session_state.function or session_state.function == "Call Center" and inferred_fn != "Call Center"):
                eff_fn = inferred_fn

        eff_periods = list(explicit_periods)
        if is_short_followup and prior and prior.periods:
            if "compare it with" in lower and has_explicit_month:
                combined = sorted(set(prior.periods + explicit_periods))
                eff_periods = combined
                inherited_filters.append("periods")
            elif not has_explicit_month:
                eff_periods = list(prior.periods)
                inherited_filters.append("periods")

        # 4. Clarification Checks (Ambiguous Attendance, Ambiguous "Other" KPI, Joiner/Tenure, or Ambiguous Ranking Metric)
        if (
            re.search(r"\battendance\b", lower)
            and not eff_team
            and not eff_metric
            and "compliance" not in lower
            and "patient" not in lower
            and "booking" not in lower
        ):
            raw_choices = [
                ClarificationChoice(
                    id="choice-patient-attendance-inbound",
                    label="Inbound Patient Attendance Rate (Attended / Bookings)",
                    prompt_to_send="What is Inbound Patient Attendance Rate vs target in September 2026?",
                    team="Inbound",
                    metric_id="inbound:attendance_rate",
                    performance_level="Employee",
                ),
                ClarificationChoice(
                    id="choice-patient-attendance-outbound",
                    label="Outbound Patient Attendance Rate (Attended / Bookings)",
                    prompt_to_send="What is Outbound Patient Attendance Rate vs target in September 2026?",
                    team="Outbound",
                    metric_id="outbound:attendance_rate",
                    performance_level="Employee",
                ),
                ClarificationChoice(
                    id="choice-managerial-attendance",
                    label="Managerial Attendance Compliance (Balanced Scorecard)",
                    prompt_to_send="Show Inbound Attendance Compliance on the Managerial scorecard for Sep 2026",
                    team="Inbound",
                    metric_id="inbound:attendance_compliance",
                    performance_level="Managerial",
                ),
            ]
            caller_role = str(self.scope.get("role") or "")
            filtered_choices = [
                c
                for c in raw_choices
                if (not c.team or user_can_access_team(self.scope, c.team))
                and (
                    c.performance_level != "Managerial"
                    or (caller_role != "Branch Director" and user_can_access_team_level(self.scope, c.team or "Inbound", "Managerial"))
                )
            ] or raw_choices[:2]
            clar_prompt = AiClarificationPrompt(
                code="AMBIGUOUS_ATTENDANCE_DEFINITION",
                question=(
                    "Which attendance metric would you like to inspect for Call Center?"
                ),
                choices=filtered_choices,
            )
            plan = StructuredQueryPlan(
                intent="clarify",
                function=eff_fn,
                periods=eff_periods,
                turn_kind_v2="clarification",
                clarification_code="AMBIGUOUS_ATTENDANCE_DEFINITION",
            )
            preserved_ctx = (
                prior.model_copy(
                    update={
                        "pending_clarification_code": "AMBIGUOUS_ATTENDANCE_DEFINITION",
                        "pending_clarification_choices": filtered_choices,
                    }
                )
                if prior is not None
                else ConfirmedQueryContext(
                    intent="clarify",
                    function=eff_fn,
                    periods=eff_periods,
                    pending_clarification_code="AMBIGUOUS_ATTENDANCE_DEFINITION",
                    pending_clarification_choices=filtered_choices,
                )
            )
            return RouterValidationResult(
                outcome="clarification",
                plan=plan,
                confirmed_context=preserved_ctx,
                clarification=clar_prompt,
                headline=clar_prompt.question,
                narrative_bullets=[
                    "Call Center tracks Patient Attendance Rate (Attended / Bookings, 70% weight) on Employee scorecards and Attendance Compliance (15% weight) on Managerial scorecards."
                ],
                route_used="clarification_choice" if matched_choice else "local_rules",
            )

        if re.search(r"\bother\s+(?:kpi|metric)\b", lower) and not eff_team:
            raw_other_choices = [
                ClarificationChoice(
                    id="choice-inbound-abandon",
                    label="Abandon Rate (Inbound — 10% weight)",
                    prompt_to_send="What is Inbound Abandon Rate vs target in September 2026?",
                    team="Inbound",
                    metric_id="inbound:abandon_rate",
                ),
                ClarificationChoice(
                    id="choice-outbound-reachability",
                    label="Reachability (Outbound — 10% weight)",
                    prompt_to_send="How is Outbound Reachability against target in September 2026?",
                    team="Outbound",
                    metric_id="outbound:reachability",
                ),
            ]
            filtered_other = [
                c for c in raw_other_choices if not c.team or user_can_access_team(self.scope, c.team)
            ] or raw_other_choices
            clar_prompt = AiClarificationPrompt(
                code="AMBIGUOUS_ABANDON_METRIC",
                question=(
                    "In Call Center, the 'Other' KPI slot represents different metrics in Inbound and Outbound. Which one would you like to view?"
                ),
                choices=filtered_other,
            )
            plan = StructuredQueryPlan(
                intent="clarify",
                function=eff_fn,
                periods=eff_periods,
                turn_kind_v2="clarification",
                clarification_code="AMBIGUOUS_ABANDON_METRIC",
            )
            preserved_other_ctx = (
                prior.model_copy(
                    update={
                        "pending_clarification_code": "AMBIGUOUS_ABANDON_METRIC",
                        "pending_clarification_choices": filtered_other,
                    }
                )
                if prior is not None
                else ConfirmedQueryContext(
                    intent="clarify",
                    function=eff_fn,
                    periods=eff_periods,
                    pending_clarification_code="AMBIGUOUS_ABANDON_METRIC",
                    pending_clarification_choices=filtered_other,
                )
            )
            return RouterValidationResult(
                outcome="clarification",
                plan=plan,
                confirmed_context=preserved_other_ctx,
                clarification=clar_prompt,
                headline=clar_prompt.question,
                narrative_bullets=[
                    "Select Inbound Abandon Rate or Outbound Reachability below to continue."
                ],
                route_used="clarification_choice" if matched_choice else "local_rules",
            )

        if re.search(r"\b(?:new\s+joiners?|join(?:ed)?\b.*\brecently|when\s+did\b.*\bjoin|hire\s+date|joining\s+date|tenure)\b", lower):
            target_t = eff_team or "Inbound"
            latest_lbl = _format_period_label(eff_periods[-1] if eff_periods else self.latest_published_period)
            person_q = (
                matched_choice.employee_id
                if (matched_choice and matched_choice.employee_id)
                else _extract_person_query_from_prompt(text)
            )
            if person_q and self.employee_candidates:
                emp_res = resolve_employee_from_candidates(
                    person_q,
                    self.employee_candidates,
                    team=eff_team,
                    function=eff_fn,
                    position=eff_pos,
                )
                if emp_res.status == "ambiguous":
                    cnt_word = _COUNT_WORDS.get(len(emp_res.matches), str(len(emp_res.matches)))
                    tok_title = person_q.strip().title()
                    question = f"I found {cnt_word} {tok_title}s in {target_t}. Which one do you mean?"
                    person_choices = [
                        ClarificationChoice(
                            id=f"choice-person-{cand.employee_id}",
                            label=f"{cand.employee_name} ({cand.employee_id}) · {cand.position or cand.team}",
                            description=f"Tracked {cand.earliest_period_label} – {cand.latest_period_label} ({cand.months_tracked} months)",
                            prompt_to_send=f"Is {cand.employee_name} ({cand.employee_id}) a new joiner in {cand.team}?",
                            team=cand.team,
                            position=cand.position,
                            performance_level=eff_level,
                            employee_id=cand.employee_id,
                            employee_name=cand.employee_name,
                        )
                        for cand in emp_res.matches[:4]
                    ]
                    clar_ambig = AiClarificationPrompt(
                        code="AMBIGUOUS_PERSON",
                        question=question,
                        choices=person_choices,
                    )
                    plan_ambig = StructuredQueryPlan(
                        intent="clarify",
                        team=eff_team,
                        function=eff_fn,
                        periods=eff_periods,
                        turn_kind_v2="clarification",
                        operation_kind_v2="person_tenure_check",
                        clarification_code="AMBIGUOUS_PERSON",
                    )
                    ctx_ambig = ConfirmedQueryContext(
                        intent="clarify",
                        team=eff_team,
                        function=eff_fn,
                        periods=eff_periods,
                        last_operation_kind="person_tenure_check",
                        pending_clarification_code="AMBIGUOUS_PERSON",
                        pending_clarification_choices=person_choices,
                    )
                    return RouterValidationResult(
                        outcome="clarification",
                        plan=plan_ambig,
                        confirmed_context=ctx_ambig,
                        clarification=clar_ambig,
                        headline=question,
                        narrative_bullets=[
                            f"Matching employees in {target_t}: "
                            + ", ".join(
                                f"{c.employee_name} ({c.employee_id}, earliest record {c.earliest_period_label})"
                                for c in emp_res.matches[:4]
                            )
                            + "."
                        ],
                        route_used="clarification_choice" if matched_choice else "local_rules",
                    )
                if emp_res.status == "unique" and emp_res.selected is not None:
                    cand = emp_res.selected
                    headline_msg = (
                        f"{cand.employee_name}'s first available {cand.team} record is {cand.earliest_period_label}. "
                        f"PMS has no verified joining date, so I can't confirm whether they joined that month."
                    )
                    hist_choices = [
                        ClarificationChoice(
                            id=f"choice-history-{cand.employee_id}",
                            label=f"Show {cand.employee_name}'s evaluation history ({cand.earliest_period_label} – {cand.latest_period_label})",
                            prompt_to_send=f"Show trend for employee {cand.employee_id} across tracked months",
                            team=cand.team,
                            performance_level=eff_level,
                            employee_id=cand.employee_id,
                            employee_name=cand.employee_name,
                        )
                    ]
                    clar_unique = AiClarificationPrompt(
                        code="MISSING_HR_JOIN_DATE",
                        question=headline_msg,
                        choices=hist_choices,
                    )
                    plan_unique = StructuredQueryPlan(
                        intent="clarify",
                        team=cand.team,
                        function=eff_fn,
                        periods=eff_periods,
                        employee_id=cand.employee_id,
                        employee_name=cand.employee_name,
                        turn_kind_v2="clarification",
                        operation_kind_v2="person_tenure_check",
                        clarification_code="MISSING_HR_JOIN_DATE",
                    )
                    ctx_unique = ConfirmedQueryContext(
                        intent="clarify",
                        team=cand.team,
                        function=eff_fn,
                        periods=eff_periods,
                        last_subject_employee_id=cand.employee_id,
                        last_subject_employee_name=cand.employee_name,
                        last_operation_kind="person_tenure_check",
                        pending_clarification_code="MISSING_HR_JOIN_DATE",
                        pending_clarification_choices=hist_choices,
                    )
                    return RouterValidationResult(
                        outcome="clarification",
                        plan=plan_unique,
                        confirmed_context=ctx_unique,
                        clarification=clar_unique,
                        headline=headline_msg,
                        narrative_bullets=[
                            f"{cand.employee_name} ({cand.employee_id}) has {cand.months_tracked} published evaluation month(s) in {cand.team} ({cand.earliest_period_label} to {cand.latest_period_label})."
                        ],
                        route_used="clarification_choice" if matched_choice else "local_rules",
                    )

            clar_joiner = AiClarificationPrompt(
                code="AMBIGUOUS_KPI_SCOPE",
                question=(
                    "PMS tracks monthly evaluation scores and KPIs rather than employee hire dates. "
                    "Would you like to inspect their tracked evaluation history instead?"
                ),
                choices=[
                    ClarificationChoice(
                        id="choice-employee-history",
                        label=f"Show tracked evaluation history in {target_t}",
                        prompt_to_send=f"Who is the best agent in {target_t} in {latest_lbl}?",
                        team=target_t,
                        performance_level=eff_level,
                    )
                ],
            )
            plan_joiner = StructuredQueryPlan(
                intent="clarify",
                team=eff_team,
                function=eff_fn,
                periods=eff_periods,
                turn_kind_v2="clarification",
                operation_kind_v2="person_tenure_check",
                clarification_code="AMBIGUOUS_KPI_SCOPE",
            )
            return RouterValidationResult(
                outcome="clarification",
                plan=plan_joiner,
                confirmed_context=prior or ConfirmedQueryContext(intent="clarify", team=eff_team, function=eff_fn),
                clarification=clar_joiner,
                headline=clar_joiner.question,
                narrative_bullets=[
                    "Employee onboarding dates and new-joiner flags are not part of the published PMS scorecard dataset."
                ],
                route_used="clarification_choice" if matched_choice else "local_rules",
            )

        # 5. Determine Intent
        emp_id_match = re.search(r"\b(sghd\d+|emp[-_ ]?\d+|e[-_]\d+)\b", lower)
        has_subject_pronoun_early = bool(re.search(r"\b(?:his|her|their|him)\b", lower))
        explicit_person_early = (
            matched_choice.employee_id
            if (matched_choice and matched_choice.employee_id)
            else _extract_person_query_from_prompt(text)
        )
        prior_is_person_extremum = bool(
            prior is not None
            and prior.last_operation_kind
            in ("person_best_period", "person_worst_period", "employee_best_period", "employee_worst_period")
        )
        has_person_context_early = bool(
            explicit_person_early
            or emp_id_match
            or (prior is not None and prior.last_subject_employee_id and (is_short_followup or has_subject_pronoun_early))
        )
        explicit_worst_month = bool(
            re.search(
                r"\b(?:worst|lowest|weakest|poorest|bottom)\s+month\b|\b(?:which|what)\s+month\b.*\b(?:worst|lowest|weakest|poorest|bottom)\b",
                lower,
            )
            or (
                (has_person_context_early or prior_is_person_extremum)
                and (has_subject_pronoun_early or is_short_followup or prior_is_person_extremum)
                and not is_ranking_correction
                and re.search(r"\b(?:worst|lowest|weakest|poorest|bottom)\b", lower)
            )
        )
        explicit_best_month = bool(
            re.search(
                r"\b(?:best|highest|peak|strongest)\s+month\b|\b(?:which|what)\s+month\b.*\b(?:best|highest|peak|strongest)\b",
                lower,
            )
            or (
                (has_person_context_early or prior_is_person_extremum)
                and (has_subject_pronoun_early or is_short_followup or prior_is_person_extremum)
                and not is_ranking_correction
                and re.search(r"\b(?:best|highest|peak|strongest)\b", lower)
            )
        )
        asks_plain_month_score = bool(
            has_explicit_month
            and not explicit_worst_month
            and not explicit_best_month
            and re.search(r"\b(?:score|performance|result|evaluation|scored|perform)\b", lower)
        )
        asks_worst_month = bool(
            explicit_worst_month
            or (
                not explicit_best_month
                and not asks_plain_month_score
                and is_short_followup
                and not is_ranking_correction
                and prior is not None
                and prior.last_operation_kind in ("person_worst_period", "employee_worst_period")
            )
        )
        asks_best_month = bool(
            explicit_best_month
            or (
                not explicit_worst_month
                and not asks_plain_month_score
                and is_short_followup
                and not is_ranking_correction
                and prior is not None
                and prior.last_operation_kind in ("person_best_period", "employee_best_period")
            )
        )
        asks_month_extremum = asks_best_month or asks_worst_month
        has_subject_pronoun = bool(re.search(r"\b(?:his|her|their|him)\b", lower))
        explicit_person_query = (
            matched_choice.employee_id
            if (matched_choice and matched_choice.employee_id)
            else _extract_person_query_from_prompt(text)
        )
        possessive_person_match = bool(
            explicit_person_query
            and re.search(
                r"\b([a-z]+(?:\s+[a-z]+)?)'s\s+(?:position|score|performance|best\s+month|worst\s+month|highest\s+month|lowest\s+month|trend)\b",
                lower,
            )
        )
        resolved_employee_id: str | None = matched_choice.employee_id if matched_choice else None
        resolved_employee_name: str | None = matched_choice.employee_name if matched_choice else None

        if explicit_person_query and self.employee_candidates and not resolved_employee_id:
            emp_res = resolve_employee_from_candidates(
                explicit_person_query,
                self.employee_candidates,
                team=eff_team,
                function=eff_fn,
                position=eff_pos,
            )
            if emp_res.status == "ambiguous":
                target_t = eff_team or eff_fn or "Call Center"
                cnt_word = _COUNT_WORDS.get(len(emp_res.matches), str(len(emp_res.matches)))
                tok_title = explicit_person_query.strip().title()
                question = f"I found {cnt_word} {tok_title}s in {target_t}. Which one do you mean?"
                person_choices = [
                    ClarificationChoice(
                        id=f"choice-person-{cand.employee_id}",
                        label=f"{cand.employee_name} ({cand.employee_id}) · {cand.position or cand.team}",
                        description=f"Tracked {cand.earliest_period_label} – {cand.latest_period_label}",
                        prompt_to_send=re.sub(
                            re.escape(explicit_person_query),
                            cand.employee_id,
                            text,
                            flags=re.IGNORECASE,
                        ),
                        team=cand.team,
                        position=cand.position,
                        performance_level=eff_level,
                        employee_id=cand.employee_id,
                        employee_name=cand.employee_name,
                    )
                    for cand in emp_res.matches[:4]
                ]
                clar_ambig_p = AiClarificationPrompt(
                    code="AMBIGUOUS_PERSON",
                    question=question,
                    choices=person_choices,
                )
                plan_ambig_p = StructuredQueryPlan(
                    intent="clarify",
                    team=eff_team,
                    function=eff_fn,
                    periods=eff_periods,
                    turn_kind_v2="clarification",
                    clarification_code="AMBIGUOUS_PERSON",
                )
                return RouterValidationResult(
                    outcome="clarification",
                    plan=plan_ambig_p,
                    confirmed_context=ConfirmedQueryContext(
                        intent="clarify",
                        team=eff_team,
                        function=eff_fn,
                        periods=eff_periods,
                        pending_clarification_code="AMBIGUOUS_PERSON",
                        pending_clarification_choices=person_choices,
                    ),
                    clarification=clar_ambig_p,
                    headline=question,
                    narrative_bullets=[
                        f"Select which {tok_title} you would like to inspect."
                    ],
                )
            if emp_res.status == "unique" and emp_res.selected is not None:
                resolved_employee_id = emp_res.selected.employee_id
                resolved_employee_name = emp_res.selected.employee_name
                if not eff_team and emp_res.selected.team:
                    eff_team = emp_res.selected.team

        if (
            not resolved_employee_id
            and not explicit_person_query
            and (is_short_followup or has_subject_pronoun)
            and not is_ranking_correction
            and prior
            and prior.last_subject_employee_id
            and not explicit_team
        ):
            resolved_employee_id = prior.last_subject_employee_id
            resolved_employee_name = prior.last_subject_employee_name
            inherited_filters.append("employee")

        asks_trend = any(
            w in lower
            for w in ("6-month", "trend", "trajectory", "progression", "over time", "multi-month", "history")
        )
        asks_ranking_person = bool(
            is_ranking_correction
            or possessive_person_match
            or asks_month_extremum
            or any(
                phrase in lower
                for phrase in (
                    "best agent",
                    "better agent",
                    "best inbound",
                    "best outbound",
                    "best support",
                    "best in support",
                    "#1 top performer",
                    "top performer",
                    "top inbound",
                    "top outbound",
                    "top support",
                    "top in support",
                    "lowest agent",
                    "lowest performer",
                    "lowest inbound",
                    "lowest outbound",
                    "lowest support",
                    "lowest in support",
                    "worst inbound",
                    "worst outbound",
                    "worst support",
                    "worst in support",
                    "worst performing agent",
                    "weakest",
                    "who is lowest",
                    "who is the lowest",
                    "who was lowest",
                    "who was the lowest",
                    "who is worst",
                    "who is the worst",
                    "who was worst",
                    "who was the worst",
                    "who is best",
                    "who is the best",
                    "who was best",
                    "who was the best",
                    "who performed best",
                    "who performed worst",
                    "who is highest",
                    "who is the highest",
                    "who is top",
                    "who is the top",
                    "top negative contributors",
                    "which employees caused",
                    "bottom agents",
                    "lowest scoring employees",
                    "scored lowest",
                    "scored highest",
                    "had the lowest",
                    "had the highest",
                    "has the lowest",
                    "has the highest",
                    "led performance",
                    "rank ",
                    "who leads",
                )
            )
        )
        asks_worst = any(
            w in lower
            for w in ("lowest", "worst", "weakest", "bottom", "negative contributors", "caused")
        )
        asks_single_person = bool(
            is_ranking_correction
            or emp_id_match
            or possessive_person_match
            or asks_month_extremum
            or resolved_employee_id
            or any(
                phrase in lower
                for phrase in (
                    "best agent",
                    "better agent",
                    "best inbound",
                    "best outbound",
                    "best support",
                    "best in support",
                    "#1 top performer",
                    "top performer",
                    "top inbound",
                    "top outbound",
                    "top support",
                    "top in support",
                    "lowest agent",
                    "lowest performer",
                    "lowest inbound",
                    "lowest outbound",
                    "lowest support",
                    "lowest in support",
                    "worst inbound",
                    "worst outbound",
                    "worst support",
                    "worst in support",
                    "worst performing agent",
                    "weakest",
                    "who is lowest",
                    "who is the lowest",
                    "who was lowest",
                    "who was the lowest",
                    "who is worst",
                    "who is the worst",
                    "who was worst",
                    "who was the worst",
                    "who is best",
                    "who is the best",
                    "who was best",
                    "who was the best",
                    "who performed best",
                    "who performed worst",
                    "who is highest",
                    "who is the highest",
                    "who is top",
                    "who is the top",
                    "scored lowest",
                    "scored highest",
                    "had the lowest",
                    "had the highest",
                    "has the lowest",
                    "has the highest",
                    "led performance",
                    "who leads",
                )
            )
        )

        # Focused clarification when the ranking metric is ambiguous (e.g., "by conversion", "by rate", "by metric")
        has_ambiguous_ranking_metric = bool(
            asks_ranking_person
            and not eff_metric
            and (
                re.search(r"\b(?:by|on|in)\s+(?:conversion(?:\s+rate)?|rate|kpi|metric|efficiency)\b", lower)
                or ("conversion" in lower and "booking" not in lower)
            )
        )
        if has_ambiguous_ranking_metric:
            target_t = eff_team if eff_team in ("Inbound", "Outbound") else "Inbound"
            t_prefix = target_t.casefold()
            latest_lbl = _format_period_label(eff_periods[-1] if eff_periods else self.latest_published_period)
            ranking_choices = [
                ClarificationChoice(
                    id=f"choice-rank-{t_prefix}-booking",
                    label=f"{target_t} Booking Rate (Bookings / Handled Calls)",
                    prompt_to_send=f"Who is the top performer in {target_t} by Booking Rate in {latest_lbl}?",
                    team=target_t,
                    metric_id=f"{t_prefix}:booking_rate",
                    performance_level=eff_level,
                ),
                ClarificationChoice(
                    id=f"choice-rank-{t_prefix}-attendance",
                    label=f"{target_t} Patient Attendance Rate (Attended / Bookings)",
                    prompt_to_send=f"Who is the top performer in {target_t} by Patient Attendance Rate in {latest_lbl}?",
                    team=target_t,
                    metric_id=f"{t_prefix}:attendance_rate",
                    performance_level=eff_level,
                ),
                ClarificationChoice(
                    id=f"choice-rank-{t_prefix}-score",
                    label=f"{target_t} Overall Weighted PMS Score",
                    prompt_to_send=f"Who is the top performer in {target_t} in {latest_lbl}?",
                    team=target_t,
                    performance_level=eff_level,
                ),
            ]
            clar_rank = AiClarificationPrompt(
                code="AMBIGUOUS_KPI_SCOPE",
                question=f"Which ranking metric should be used to rank {eff_team or eff_fn or 'Call Center'} performers?",
                choices=ranking_choices,
            )
            plan_clar_rank = StructuredQueryPlan(
                intent="clarify",
                team=eff_team,
                function=eff_fn,
                position=eff_pos,
                branch=eff_branch,
                branches=eff_branches,
                performance_level=eff_level,
                periods=eff_periods,
                turn_kind_v2="clarification",
                clarification_code="AMBIGUOUS_KPI_SCOPE",
            )
            preserved_rank_ctx = (
                prior.model_copy(
                    update={
                        "pending_clarification_code": "AMBIGUOUS_KPI_SCOPE",
                        "pending_clarification_choices": ranking_choices,
                    }
                )
                if prior is not None
                else ConfirmedQueryContext(
                    intent="clarify",
                    team=eff_team,
                    function=eff_fn,
                    position=eff_pos,
                    branch=eff_branch,
                    branches=eff_branches,
                    performance_level=eff_level,
                    periods=eff_periods,
                    pending_clarification_code="AMBIGUOUS_KPI_SCOPE",
                    pending_clarification_choices=ranking_choices,
                )
            )
            return RouterValidationResult(
                outcome="clarification",
                plan=plan_clar_rank,
                confirmed_context=preserved_rank_ctx,
                clarification=clar_rank,
                headline=clar_rank.question,
                narrative_bullets=[
                    f"Specify whether to rank {eff_team or 'Call Center'} agents by Booking Rate, Patient Attendance Rate, or Overall Weighted PMS Score."
                ],
                route_used="clarification_choice" if matched_choice else "local_rules",
            )

        is_multi_part_trend_and_ranking = bool(
            asks_trend
            and asks_ranking_person
            and not re.search(r"\b(?:his|her|their|agent'?s)\s+(?:\d+-month\s+)?trend\b", lower)
        )
        is_multi_part_score_and_ranking = bool(
            not is_multi_part_trend_and_ranking
            and asks_ranking_person
            and re.search(r"\b(?:what|how|give|show)\b.*\b(?:score|performance)\b.*\b(?:and|also|plus|both|as well as)\b", lower)
        )

        has_prior_team_ctx = bool(
            (session_state.team and session_state.team not in ("All", "all"))
            or (prior and prior.team)
        )
        if (
            not explicit_team
            and not explicit_branches
            and not has_prior_team_ctx
            and not resolved_employee_id
            and re.search(r"\b(?:which\s+one|doing\s+better|compare\s+them|who\s+is\s+better)\b", lower)
        ):
            q_txt = "Which teams, branches, or employees would you like to compare? Please specify the scope and metric."
            clar_cmp = AiClarificationPrompt(
                code="AMBIGUOUS_TEAM_SCOPE",
                question=q_txt,
                choices=[],
            )
            plan_cmp = StructuredQueryPlan(
                intent="clarify",
                turn_kind_v2="clarification",
                clarification_code="AMBIGUOUS_TEAM_SCOPE",
            )
            return RouterValidationResult(
                outcome="clarification",
                plan=plan_cmp,
                confirmed_context=prior or ConfirmedQueryContext(intent="clarify"),
                clarification=clar_cmp,
                headline=q_txt,
                narrative_bullets=["Specify at least two teams or branches and the performance measure to compare."],
            )

        is_proposal_request = bool(
            re.search(
                r"\b(?:propose|create|draft|suggest|recommend|build|write|generate)\s+(?:a\s+|an\s+)?(?:corrective\s+action|action\s+plan|coaching\s+action|improvement\s+action|pip|training\s+action)\b",
                lower,
            )
            or re.search(r"\bwhat\s+(?:corrective\s+)?action\s+should\s+(?:we|i)\s+(?:take|create|assign)\b", lower)
            or re.search(r"\bwhat\s+should\s+(?:we|i)\s+do\b", lower)
        )
        asks_corrective_actions = (
            not is_proposal_request
            and any(
                k in lower
                for k in ("corrective action", "corrective actions", "overdue corrective", "sip/pi")
            )
        )
        asks_scorecard_structure = bool(
            eff_level in ("Managerial", "Corporate")
            and not eff_metric
            and any(k in lower for k in ("balanced scorecard", "bsc", "scorecard"))
        )
        asks_score_drivers = is_proposal_request or any(
            phrase in lower
            for phrase in (
                "diagnose ",
                "score drivers",
                "kpi gaps",
                "drove the score gap",
                "why did ",
                "why is ",
                "why are ",
                "why was ",
                "why were ",
                "kpi bottlenecks",
            )
        ) or bool(
            re.search(
                r"\b(?:why|how\s+come|what\s+caused|what\s+drove)\b.*\b(?:down|low|drop|dropped|dropping|below|weak|bad|decline|declined|fell|fall|behind|miss|missed|gap|bottleneck|poor|worse)\b",
                lower,
            )
        )
        asks_vs_target = any(
            phrase in lower for phrase in ("vs target", "versus target", "against target", "meet its")
        )
        has_explicit_new_intent = bool(
            len(explicit_periods) >= 2
            or "compare it with" in lower
            or asks_branch_comparison
            or asks_team_comparison
            or asks_corrective_actions
            or asks_scorecard_structure
            or asks_ranking_person
            or asks_trend
            or asks_score_drivers
            or explicit_metric is not None
            or asks_vs_target
            or asks_plain_month_score
        )

        intent: RouterIntentType = "current_value"
        if is_ranking_correction:
            intent = "ranking"
            asks_single_person = bool((prior and prior.single_person) or True)
            if "intent" not in inherited_filters:
                inherited_filters.append("intent")
        elif (
            is_short_followup
            and not has_explicit_new_intent
            and prior
            and prior.intent
            and prior.intent not in ("clarify", "unsupported")
            and "compare it with" not in lower
        ):
            intent = prior.intent
            has_explicit_direction_word = any(
                w in lower for w in ("lowest", "worst", "bottom", "highest", "best", "top")
            )
            if intent == "ranking" and not asks_ranking_person:
                if not has_explicit_direction_word:
                    asks_worst = prior.ranking_direction == "worst"
                asks_single_person = bool(prior.single_person)
            if intent == "compare_branches" and not eff_branches and prior.branches:
                eff_branches = list(prior.branches)
                if not eff_branch and prior.branch:
                    eff_branch = prior.branch
                if not explicit_compare_branch and len(prior.branches) >= 2:
                    explicit_compare_branch = prior.branches[1]
            if "intent" not in inherited_filters:
                inherited_filters.append("intent")
        elif len(eff_periods) >= 2:
            intent = "compare_periods"
        elif asks_branch_comparison:
            intent = "compare_branches"
        elif asks_team_comparison:
            intent = "compare_teams"
        elif asks_corrective_actions:
            intent = "corrective_actions"
        elif asks_scorecard_structure:
            intent = "scorecard_structure"
        elif asks_ranking_person:
            intent = "ranking"
        elif asks_trend and not asks_ranking_person:
            intent = "trend"
        elif asks_score_drivers and explicit_metric is None:
            intent = "score_drivers"
        elif eff_metric is not None or asks_vs_target:
            intent = "actual_vs_target"
        else:
            intent = "current_value"

        requested_parts: list[str] = (
            ["trend", "ranking"]
            if is_multi_part_trend_and_ranking
            else (["current_value", "ranking"] if is_multi_part_score_and_ranking else [intent])
        )

        if asks_worst_month:
            asks_worst = True
            op_kind_v2 = "person_worst_period"
        elif asks_best_month:
            asks_worst = False
            op_kind_v2 = "person_best_period"
        elif False:
            op_kind_v2 = "person_worst_period"
        elif asks_best_month:
            op_kind_v2 = "person_best_period"
        elif resolved_employee_id:
            op_kind_v2 = "person_summary"
        else:
            op_kind_v2 = intent

        plan = StructuredQueryPlan(
            intent=intent,
            requested_parts=requested_parts,
            team=eff_team,
            function=eff_fn,
            position=eff_pos,
            branch=eff_branch,
            compare_branch=explicit_compare_branch,
            branches=eff_branches,
            performance_level=eff_level,
            metric=eff_metric,
            periods=eff_periods,
            ranking_direction="worst" if asks_worst else "best",
            single_person=asks_single_person,
            employee_id=resolved_employee_id,
            employee_name=resolved_employee_name,
            employee_placeholder="[EMPLOYEE_ID]" if (emp_id_match or resolved_employee_id) else None,
            turn_kind_v2="correction" if is_ranking_correction else "analytical",
            operation_kind_v2=op_kind_v2,  # type: ignore[arg-type]
            clarification_code="NONE",
            asks_decisions=any(w in lower for w in ("decision", "decisions", "recommend", "what happens if")),
        )

        # 6. Pre-Cloud & Pre-Read RBAC Access Validation (NEVER substitute Dubai when Sharjah is requested!)
        def _check_rbac() -> RouterValidationResult | None:
            branches_to_check: list[str] = []
            for b_cand in [*explicit_branches, plan.branch, plan.compare_branch]:
                if b_cand and b_cand not in branches_to_check:
                    branches_to_check.append(b_cand)
            if asks_branch_comparison and not explicit_compare_branch:
                for b_key in BRANCH_KEYS:
                    if b_key not in branches_to_check:
                        branches_to_check.append(b_key)

            unauthorized_branch = next(
                (b for b in branches_to_check if not user_can_access_branch(self.scope, b)),
                None,
            )
            if unauthorized_branch:
                allowed_b = sorted(
                    str(b).capitalize()
                    for b in (self.scope.get("accessible_branches") or self.scope.get("allowed_branches") or [])
                )
                allowed_str = ", ".join(allowed_b) if allowed_b else "your assigned branch"
                return RouterValidationResult(
                    outcome="restricted_access",
                    plan=plan,
                    confirmed_context=prior or ConfirmedQueryContext(),
                    inherited_filters=inherited_filters,
                    route_used=route_used,
                    provider_metrics=provider_metrics,
                    headline=(
                        f"Access restricted: your role does not have permission to view {unauthorized_branch.capitalize()} branch data."
                    ),
                    narrative_bullets=[
                        f"Your current access scope is restricted to {allowed_str}.",
                        "PMS AI never substitutes another branch when a restricted branch is requested.",
                    ],
                    suggested_followups=[
                        f"What is {eff_team or 'Inbound'} performance in {allowed_b[0]} for {_format_period_label(self.latest_published_period)}?"
                        if allowed_b
                        else "Show performance for my authorized scope"
                    ],
                )

            teams_to_check: list[str] = []
            for t_cand in [*teams_in_prompt, explicit_team, plan.team]:
                if t_cand and t_cand not in teams_to_check:
                    teams_to_check.append(t_cand)
            check_lvl = plan.performance_level or eff_level
            unauthorized_team = next(
                (t for t in teams_to_check if not user_can_access_team(self.scope, t, performance_level=check_lvl)),
                None,
            )
            if not unauthorized_team:
                acc_regions = {
                    str(r or "").strip().upper()
                    for r in (self.scope.get("accessible_regions") or self.scope.get("allowed_regions") or [])
                    if r
                }
                if acc_regions and "ALL" not in acc_regions and len(acc_regions) < 2:
                    if has_uae_hint and "UAE" not in acc_regions:
                        unauthorized_team = "UAE"
                    elif has_egy_hint and "EGY" not in acc_regions:
                        unauthorized_team = "Egypt"
            if unauthorized_team:
                allowed_fns = ", ".join(self.scope.get("accessible_functions") or []) or "your assigned teams"
                return RouterValidationResult(
                    outcome="restricted_access",
                    plan=plan,
                    confirmed_context=prior or ConfirmedQueryContext(),
                    inherited_filters=inherited_filters,
                    route_used=route_used,
                    provider_metrics=provider_metrics,
                    headline=(
                        f"Access restricted: your role does not have permission to view {unauthorized_team} data."
                    ),
                    narrative_bullets=[
                        f"Your account is scoped to {allowed_fns}.",
                    ],
                    suggested_followups=[
                        f"Show performance summary for my authorized scope in {_format_period_label(self.latest_published_period)}"
                    ],
                )
            return None

        route_used = "clarification_choice" if matched_choice else "local_rules"
        provider_metrics = ProviderCallMetrics()
        shadow_plan: dict[str, Any] | None = None

        _orig_check_rbac = _check_rbac

        def _check_rbac() -> RouterValidationResult | None:
            base_res = _orig_check_rbac()
            if base_res is not None:
                return base_res
            target_level = plan.performance_level or eff_level or "Employee"
            caller_role_now = str(self.scope.get("role") or "")
            is_caller_self_only = bool(self.scope.get("is_self_only")) or caller_role_now in {
                "Agent",
                "Employee",
                "Executive",
            }
            if target_level in ("Corporate", "Managerial") and (
                is_caller_self_only
            ):
                return RouterValidationResult(
                    outcome="restricted_access",
                    plan=plan,
                    confirmed_context=prior or ConfirmedQueryContext(),
                    inherited_filters=inherited_filters,
                    route_used=route_used,
                    provider_metrics=provider_metrics,
                    headline=f"Access restricted: your role does not have permission to view {target_level} level data.",
                    narrative_bullets=[f"Your current access scope does not include {target_level} scorecards."],
                    suggested_followups=[
                        f"Show Employee performance for {eff_team or 'Inbound'} in {_format_period_label(self.latest_published_period)}"
                    ],
                )
            levels_teams: list[str] = []
            for t_cand in [*teams_in_prompt, explicit_team, plan.team, eff_team]:
                if t_cand and t_cand not in levels_teams:
                    levels_teams.append(t_cand)
            for t_lvl in levels_teams:
                if t_lvl and not user_can_access_team_level(self.scope, t_lvl, target_level):
                    return RouterValidationResult(
                        outcome="restricted_access",
                        plan=plan,
                        confirmed_context=prior or ConfirmedQueryContext(),
                        inherited_filters=inherited_filters,
                        route_used=route_used,
                        provider_metrics=provider_metrics,
                        headline=f"Access restricted: your account does not have permission to view {t_lvl} {target_level} data.",
                        narrative_bullets=[
                            f"Your team assignment for {t_lvl} does not include the {target_level} performance level."
                        ],
                        suggested_followups=[
                            f"Show Employee performance for {t_lvl} in {_format_period_label(self.latest_published_period)}"
                        ],
                    )
            if not levels_teams and target_level in ("Corporate", "Managerial"):
                if not self.scope.get("has_unrestricted_team_access") and caller_role_now not in {
                    "Admin",
                    "General Manager",
                    "Performance Team",
                    "Viewer",
                }:
                    team_levels = self.scope.get("accessible_team_levels") or []
                    if team_levels and not any(
                        isinstance(item, (list, tuple))
                        and len(item) >= 2
                        and str(item[1]).strip().casefold() == target_level.casefold()
                        for item in team_levels
                    ):
                        return RouterValidationResult(
                            outcome="restricted_access",
                            plan=plan,
                            confirmed_context=prior or ConfirmedQueryContext(),
                            inherited_filters=inherited_filters,
                            route_used=route_used,
                            provider_metrics=provider_metrics,
                            headline=f"Access restricted: your account does not have permission to view {target_level} level data.",
                            narrative_bullets=[f"Your current assignments do not include {target_level} scorecards."],
                            suggested_followups=[
                                f"Show Employee performance in {_format_period_label(self.latest_published_period)}"
                            ],
                        )
            if is_caller_self_only:
                caller_emp = str(self.scope.get("employee_id") or "").strip()
                if plan.employee_id and (
                    not caller_emp or str(plan.employee_id).strip().casefold() != caller_emp.casefold()
                ):
                    return RouterValidationResult(
                        outcome="restricted_access",
                        plan=plan,
                        confirmed_context=prior or ConfirmedQueryContext(),
                        inherited_filters=inherited_filters,
                        route_used=route_used,
                        provider_metrics=provider_metrics,
                        headline="Access restricted: your role is restricted to viewing your own employee scorecard.",
                        narrative_bullets=["Self-scoped accounts cannot view other employees' evaluation records."],
                        suggested_followups=["Show my performance summary"],
                    )
                if explicit_person_query and not plan.employee_id:
                    return RouterValidationResult(
                        outcome="restricted_access",
                        plan=plan,
                        confirmed_context=prior or ConfirmedQueryContext(),
                        inherited_filters=inherited_filters,
                        route_used=route_used,
                        provider_metrics=provider_metrics,
                        headline="Access restricted: your role is restricted to viewing your own employee scorecard.",
                        narrative_bullets=["Self-scoped accounts cannot view other employees' evaluation records."],
                        suggested_followups=["Show my performance summary"],
                    )
            return None

        pre_cloud_rbac = _check_rbac()
        if pre_cloud_rbac is not None:
            return pre_cloud_rbac

        # Experimental TF-IDF classifier is offline-only and never trained from test fixtures during live requests.

        has_explicit_local_action = bool(
            eff_metric is not None
            or intent != "current_value"
            or eff_pos is not None
            or is_short_followup
            or bool(inherited_filters)
            or matched_choice is not None
            or any(
                kw in lower
                for kw in (
                    "score",
                    "performance",
                    "kpi",
                    "target",
                    "gap",
                    "driver",
                    "trend",
                    "rank",
                    "top ",
                    "best ",
                    "lowest ",
                    "worst ",
                    "compare",
                    "vs ",
                    "versus",
                    "branch",
                    "corrective",
                    "scorecard",
                    "revenue",
                    "ايرادات",
                    "إيرادات",
                    "واقع",
                    "السبب",
                )
            )
        )

        # The local model suggests an intent only; PMS resolves scope and facts.
        # It may also recognize a trend in an overall performance question where
        # no KPI is named. Compound requests need a complete plan, not one intent.
        overall_score_question = bool(
            eff_metric is None
            and re.search(r"\b(?:performance|scores?)\b", lower)
            and not re.search(r"\b(?:and|also|then|plus|or)\b", lower)
        )
        if (
            provider_override == "auto"
            and local_intent_enabled()
            and plan.intent in ("current_value", "actual_vs_target")
            and (eff_metric is not None or overall_score_question)
            and not is_short_followup
            and matched_choice is None
            and not plan.employee_id
            and not plan.single_person
            and not has_explicit_month
            and len(plan.periods) <= 1
            and not any(word in lower for word in ("worst", "lowest", "best", "highest", "compare", "versus", " vs ", "why", "target", "trend"))
        ):
            local_result = suggest_intent(text)
            provider_metrics = ProviderCallMetrics(
                provider_used="llama_cpp",
                model_used="local-intent-model",
                provider_calls=1,
                provider_ms=local_result.elapsed_ms,
                fallback_outcome="none" if local_result.reason == "ok" else local_result.reason,
            )
            if local_result.intent == "trend":
                plan.intent = "trend"
                plan.requested_parts = ["trend"]
                plan.operation_kind_v2 = "trend"
                route_used = "local_model_router"

        should_call_gemini = provider_override != "deterministic" and (
            provider_override == "gemini"
            or (cfg.router_mode == "shadow" and cfg.can_call_gemini)
            or (
                cfg.router_mode == "hybrid"
                and cfg.can_call_gemini
                and not has_explicit_local_action
                and cfg.is_scope_allowed_for_cloud(eff_team or eff_fn)
            )
        )
        if should_call_gemini:
            if is_prompt_safe_for_external_projection(text):
                eligible_team_names = [
                    t.value for t in self.catalog.get_eligible_scope_options(self.scope)["eligible_teams"]
                ]
                known_emp_names = [c.employee_name for c in self.employee_candidates if c.employee_name]
                gem_res = GeminiStructuredRouterAdapter().propose_query_plan(
                    prompt=text,
                    current_view={
                        "function": eff_fn,
                        "team": eff_team,
                        "position": eff_pos,
                        "branch": eff_branch,
                        "performance_level": eff_level,
                    },
                    candidate_teams=eligible_team_names,
                    candidate_metrics=list(self.catalog.metrics.keys())[:40],
                    candidate_branches=["dubai", "sharjah", "ajman", "clinics"],
                    known_employee_names=known_emp_names,
                )
                provider_metrics = gem_res.metrics
                if gem_res.plan is not None:
                    shadow_plan = gem_res.plan.model_dump()
                    if provider_override == "gemini" or cfg.router_mode == "hybrid":
                        route_used = "gemini_router"
                        if gem_res.plan.intent:
                            cand_intent = gem_res.plan.intent
                            if (
                                cand_intent == "scorecard_structure"
                                and eff_level not in ("Managerial", "Corporate")
                                and not any(k in lower for k in ("balanced scorecard", "bsc", "scorecard"))
                            ):
                                cand_intent = "current_value"
                            if (
                                cand_intent in ("actual_vs_target", "score_drivers")
                                and "performance" in lower
                                and eff_metric is None
                                and not any(k in lower for k in ("target", "gap", "driver", "why", "kpi", "focus"))
                            ):
                                cand_intent = "current_value"
                            plan.intent = cand_intent
                        valid_parts = {
                            "current_value",
                            "actual_vs_target",
                            "compare_periods",
                            "compare_branches",
                            "compare_teams",
                            "trend",
                            "ranking",
                            "score_drivers",
                            "scorecard_structure",
                            "corrective_actions",
                        }
                        if gem_res.plan.requested_parts:
                            cleaned_parts = [
                                str(p).strip()
                                for p in gem_res.plan.requested_parts
                                if str(p).strip() in valid_parts
                            ]
                            if cleaned_parts:
                                plan.requested_parts = cleaned_parts[:2]
                        elif plan.intent and plan.requested_parts == [intent]:
                            plan.requested_parts = [plan.intent]
                        if gem_res.plan.team and not plan.team:
                            cand_team = gem_res.plan.team.strip()
                            if cand_team in self.catalog.teams or cand_team in eligible_team_names:
                                plan.team = cand_team
                                plan.function = function_for_team(cand_team) or plan.function
                        if gem_res.plan.position and not plan.position:
                            plan.position = gem_res.plan.position.strip()
                        if gem_res.plan.branch and not plan.branch:
                            cand_b = gem_res.plan.branch.strip().casefold()
                            if cand_b in BRANCH_KEYS and not (plan.team and cand_b in plan.team.casefold()):
                                plan.branch = cand_b
                        if gem_res.plan.compare_branch and not plan.compare_branch:
                            cand_cb = gem_res.plan.compare_branch.strip().casefold()
                            if cand_cb in BRANCH_KEYS:
                                plan.compare_branch = cand_cb
                        if gem_res.plan.metric and not plan.metric:
                            cand_m = self.catalog.find_metric_definition(
                                team=plan.team,
                                kpi_key_or_label=gem_res.plan.metric,
                                position=plan.position,
                                performance_level=plan.performance_level,
                            )
                            if cand_m is not None:
                                plan.metric = cand_m.metric_id
                            elif gem_res.plan.metric in self.catalog.metrics:
                                plan.metric = gem_res.plan.metric
                        if gem_res.plan.periods:
                            valid_periods = [
                                p
                                for p in gem_res.plan.periods[:6]
                                if re.match(r"^\d{4}-(0[1-9]|1[0-2])$", str(p))
                            ]
                            if valid_periods:
                                plan.periods = valid_periods
                                eff_periods = valid_periods
                        plan.single_person = bool(plan.single_person or gem_res.plan.single_person)
                        if gem_res.plan.ranking_direction in ("best", "worst"):
                            plan.ranking_direction = gem_res.plan.ranking_direction
                elif provider_override == "gemini":
                    raise AiProviderUnavailableError(
                        "The AI routing provider is temporarily unavailable. Please retry your request."
                    )

        # Re-verify RBAC after any provider-suggested scope updates
        post_cloud_rbac = _check_rbac()
        if post_cloud_rbac is not None:
            return post_cloud_rbac

        # 7. Pre-Read Period Availability Validation (derived from authorized published evidence)
        def _is_period_unavailable(period_key: str) -> bool:
            if self.published_periods is not None and len(self.published_periods) > 0:
                if period_key in self.published_periods:
                    return False
                if period_key > self.latest_published_period or period_key in UNAVAILABLE_FUTURE_PERIODS:
                    return True
                return False
            return period_key in UNAVAILABLE_FUTURE_PERIODS

        unavail_p = next((p for p in eff_periods if _is_period_unavailable(p)), None)
        if unavail_p is not None:
            latest_human = _format_period_label(self.latest_published_period)
            return RouterValidationResult(
                outcome="unavailable_data",
                plan=plan,
                confirmed_context=prior or ConfirmedQueryContext(),
                inherited_filters=inherited_filters,
                route_used=route_used,
                provider_metrics=provider_metrics,
                headline=(
                    f"No published PMS evaluation records are available for period {unavail_p}."
                ),
                narrative_bullets=[
                    f"The latest published period with verified PMS data is {latest_human} ({self.latest_published_period})."
                ],
                suggested_followups=[
                    f"What is {plan.team or eff_team or 'Inbound'} score in {latest_human}?"
                ],
            )

        confirmed = ConfirmedQueryContext(
            intent=plan.intent,
            team=plan.team,
            function=plan.function,
            position=plan.position,
            branch=plan.branch,
            branches=plan.branches,
            performance_level=plan.performance_level,
            metric_id=plan.metric,
            periods=plan.periods,
            comparison_type=(
                "period"
                if plan.intent == "compare_periods"
                else ("branch" if plan.intent == "compare_branches" else ("team" if plan.intent == "compare_teams" else "none"))
            ),
            ranking_direction=plan.ranking_direction,
            single_person=plan.single_person,
            last_subject_employee_id=plan.employee_id,
            last_subject_employee_name=plan.employee_name,
            last_operation_kind=plan.operation_kind_v2 or plan.intent,
            pending_clarification_code=None,
            pending_clarification_choices=[],
            inherited_filters=inherited_filters,
        )

        return RouterValidationResult(
            outcome="answer",
            plan=plan,
            confirmed_context=confirmed,
            inherited_filters=inherited_filters,
            route_used=route_used,
            provider_metrics=provider_metrics,
            shadow_plan=shadow_plan,
        )
