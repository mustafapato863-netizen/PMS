from __future__ import annotations

import difflib
import os
import re
from time import perf_counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from models.models import AiApprovedPattern

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
    BARE_CROSS_COUNTRY_TEAMS,
    function_for_team,
    get_ai_catalog,
    resolve_canonical_team_name,
    user_can_access_branch,
    user_can_access_team,
)
from services.ai.config import get_ai_runtime_config
from services.ai.llm_client import configured_model_name
from services.ai.prompt_versions import MODEL_LED_PLANNER_PROMPT_VERSION
from services.ai.local_model_router import (
    BoundedIntentContext,
    LocalIntentResult,
    call_suggest_intent,
    local_intent_enabled,
    suggest_intent,
)
from services.ai.domain_policies import (
    BRANCH_ALIASES,
    MONTH_ALIASES,
    parse_query_rankings_spec,
    asks_cohort_score,
    asks_group_leader,
    detect_explicit_score_measure,
    explicit_kpi_question_kind,
    has_pms_performance_signal,
    is_arabic_text,
    is_bare_scope_or_period_refinement,
    is_broad_overview_prompt,
    is_explicit_correction_prompt,
    is_off_topic_prompt,
    is_ranked_action_request,
    is_topic_switch_prompt,
    is_vague_dataless_prompt,
    normalize_prompt_lexical,
)
from services.ai.entity_resolver import (
    EmployeeHistoryCandidate,
    resolve_employee_from_candidates,
)
from services.ai.providers import (
    NvidiaStructuredRouterAdapter,
    ProviderCallMetrics,
    ProviderUnavailableError,
    is_prompt_safe_for_external_projection,
    metrics_from_provider_response,
)
from services.ai.compound_parts_planner import (
    CompoundQueryPlan,
    compound_parts_enabled,
    contains_arabic,
    detect_arabic_country,
    detect_arabic_periods,
    detect_arabic_team_hint,
    detect_arabic_teams,
    detect_bilingual_kpi_ids,
    match_arabic_person_candidate,
    normalize_bilingual_text,
    plan_compound_parts,
)
from utils.branch_scope import BRANCH_KEYS
from utils.report_scope import function_for_team, user_can_access_team_level
from utils.regions import ksa_region_hint_from_prompt

AiProviderUnavailableError = ProviderUnavailableError


def build_pass1_identity_context(scope: dict[str, Any] | None, *, max_chars: int = 8000) -> str:
    """Build compact XML identity + memory context for Pass 1 (256k budget)."""
    if not isinstance(scope, dict):
        return ""
    parts: list[str] = []
    passport_xml = str(scope.get("passport_xml") or "").strip()
    if not passport_xml:
        try:
            from services.ai.identity_service import build_passport

            passport_obj = scope.get("passport") or build_passport(scope)
            if hasattr(passport_obj, "to_xml"):
                passport_xml = str(passport_obj.to_xml()).strip()
        except Exception:
            passport_xml = ""
    if passport_xml:
        parts.append(passport_xml[:800])

    memory_text = str(scope.get("user_memory_text") or "").strip()
    if memory_text:
        parts.append(memory_text[:5800])

    combined = "\n".join(parts)
    if len(combined) > max_chars:
        combined = combined[:max_chars]
    return combined


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
            "egypt support",
            "support in egypt",
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
    ("Quality Management", ("quality management", "quality department", "quality team")),
    ("Administration", ("administration", "admin department")),
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
    ("Quality Management", "Infection Control Consultant", ("infection control consultant", "infection control")),
    ("Quality Management", "Senior Quality Specialist", ("senior quality specialist",)),
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


_DET_FIRST_RE = re.compile(
    r"^\W*(?:(?:how\s+(?:is|are)|what(?:'s|\s+is)|show(?:\s+me)?|give\s+me)\s+)?(?:the\s+)?"
    r"(?:company(?:\s+wide)?|overall|(?:lowest|highest|best|worst|top|bottom)\s+(?:\d+\s+|two\s+|three\s+|five\s+)?"
    r"(?:scoring\s+)?(?:employees?|people))\b[^?]*\??\W*$",
    re.I,
)


def _deterministic_first_question(lower: str) -> bool:
    """Short company-wide and ranking questions that the rule router answers exactly; skip the slow model planner."""
    if os.getenv("PMS_AI_DETERMINISTIC_FIRST", "on").strip().casefold() in {"off", "false", "0"}:
        return False
    text = (lower or "").strip()
    if len(text) > 90 or re.search(r"\b(?:why|compare|versus|vs|trend|and then|also)\b", text):
        return False
    return bool(_DET_FIRST_RE.match(text) or re.match(r"^\W*how\s+is\s+the\s+(?:whole\s+|entire\s+)?company\s+doing\b", text))

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
    matched_pattern_id: str | None = None


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


def clean_planner_tool_arguments(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    filters = {"region", "country", "department", "team", "position", "branch", "performance_level",
               "employee_name", "employee_id", "metric_id", "metric", "period"}
    return {key: arg for key, arg in value.items() if arg is not None and not (
        key in filters and isinstance(arg, str) and arg.strip().casefold() in {"", "none", "null", "undefined"}
    )}


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
    norm_ar_text = normalize_bilingual_text(text_lower)
    for alias, canonical_month in sorted_aliases:
        is_ascii_alias = alias.isascii()
        haystack = text_lower if is_ascii_alias else norm_ar_text
        target_alias = alias if is_ascii_alias else normalize_bilingual_text(alias)
        pattern = (
            rf"(?<![a-z0-9]){re.escape(target_alias)}(?![a-z0-9])"
            if is_ascii_alias
            else rf"(?<!\w){re.escape(target_alias)}(?!\w)"
        )
        for m in re.finditer(pattern, haystack):
            span = m.span()
            if is_ascii_alias and any(not (span[1] <= s[0] or span[0] >= s[1]) for s in used_spans):
                continue
            if is_ascii_alias:
                used_spans.append(span)
            found_months.append((span[0], canonical_month))

    found_months.sort(key=lambda item: item[0])
    periods: list[str] = []
    for _, m_name in found_months:
        pk = _period_key_from_month_year(m_name, default_yr)
        if pk not in periods:
            periods.append(pk)

    if not periods and re.search(r"\b(?:last|prev(?:ious)?|prior)\s+month\b", text_lower):
        anchor_m = MONTHS.get(default_month) if default_month and default_month in MONTHS else None
        anchor_y = default_yr
        if anchor_m is None and re.match(r"^(20\d{2})-(0[1-9]|1[0-2])$", fallback_period):
            anchor_y, anchor_m = map(int, fallback_period.split("-"))
        if anchor_m is not None:
            prev_y, prev_m = (anchor_y - 1, 12) if anchor_m == 1 else (anchor_y, anchor_m - 1)
            periods.append(f"{prev_y:04d}-{prev_m:02d}")

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
                # Exclude teams that are explicitly negated in the prompt (e.g. "not Outbound", "instead of Outbound")
                preceding_text = text_lower[: span[0]]
                if re.search(r"\b(?:not|instead\s+of|rather\s+than)\s+(?:the\s+)?$", preceding_text):
                    used_spans.append(span)
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


_OVERALL_SCORE_REQUEST_RE = re.compile(
    r"\b(?:overall\s+pms(?:\s+scores?)?|overall\s+(?:pms\s+)?scores?|overall\s+performance|overall\s+trend|score\s+pattern|scores?\s+pattern|"
    r"score\s+trend|score\s+history|scores?\s+across|scores?)\b"
)
_SPECIFIC_KPI_CUE_RE = re.compile(
    r"\b(?:quality\s+score|qa\s+score|qa\s+quality|bookings?|attended|attendance|"
    r"abandon|abondan|abandoned|reachability|aht|handle\s+time|rejection|"
    r"wait(?:ing)?\s+time|cpl|leads|rework|team\s+sla|sla|atv|leakage|tender\s+compliance)\b"
)


def _is_explicit_overall_score_request(text_lower: str) -> bool:
    return bool(
        _OVERALL_SCORE_REQUEST_RE.search(text_lower or "")
        and not _SPECIFIC_KPI_CUE_RE.search(text_lower or "")
    )


def _detect_discussed_metrics(
    text_lower: str,
    *,
    team: str | None,
    position: str | None,
    performance_level: str,
) -> list[str]:
    """Identify distinct KPI IDs explicitly mentioned together in a multi-metric prompt."""
    found = detect_bilingual_kpi_ids(text_lower or "", team=team)
    return list(dict.fromkeys(found))


def _detect_metric_id(
    text_lower: str,
    *,
    team: str | None,
    position: str | None,
    performance_level: str,
    prior_metric_id: str | None = None,
) -> str | None:
    if _is_explicit_overall_score_request(text_lower):
        return None
    if team in ("Coding", "Coding EGY") and re.search(r"\bquality\s+errors?\b", text_lower):
        metric = get_ai_catalog().find_metric_definition(
            team=team, kpi_key_or_label="Quality Errors", position=position,
            performance_level=performance_level,
        )
        if metric:
            return metric.metric_id
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
    if t_norm == "pharmacy" or re.search(r"\bwait(?:ing)?\s+time\b", text_lower) or "انتظار" in normalize_bilingual_text(text_lower):
        if "iv cost saving" in text_lower:
            return "pharmacy:ajm_pharmacy_man_iv_cost_saving"
        if re.search(r"\bwait(?:ing)?\s+time\b", text_lower) or any(
            k in normalize_bilingual_text(text_lower) for k in ("وقت الانتظار", "مده الانتظار", "فتره الانتظار", "الانتظار")
        ):
            if t_norm in {"inbound", "outbound"}:
                return f"{t_norm}:waitingtime"
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
    if t_norm in {"inbound", "outbound"} and re.search(r"\bwait(?:ing)?\s+time\b", text_lower):
        return f"{t_norm}:waitingtime"
    if any(k in text_lower for k in ("abandon", "abondan", "abandoned")):
        return "inbound:abandon_rate"
    if "reachability" in text_lower:
        return "outbound:reachability"
    if any(k in text_lower for k in ("aht", "handle time")):
        prefix = "outbound" if t_norm == "outbound" else "inbound"
        return f"{prefix}:aht"
    if any(
        k in text_lower
        for k in ("booking rate", "booking-rate", "booking conversion", "by booking", "on booking")
    ):
        prefix = "outbound" if t_norm == "outbound" else "inbound"
        return f"{prefix}:booking_rate"
    if (
        "bookings trend" in text_lower
        or (
            "booking trend" in text_lower
            and prior_metric_id
            and prior_metric_id.endswith(":bookings_count")
            and "rate" not in text_lower
            and "conversion" not in text_lower
        )
    ):
        prefix = "outbound" if t_norm == "outbound" else "inbound"
        return f"{prefix}:bookings_count"
    if "booking trend" in text_lower:
        prefix = "outbound" if t_norm == "outbound" else "inbound"
        return f"{prefix}:booking_rate"
    # NOTE (Task 2): a bare "bookings" noun is a count, not a rate. The old
    # fallback sent any bare "bookings" ("How many Clinics bookings?",
    # "What is the Inbound booking count?") to booking_rate, so count
    # questions were answered with a percentage. Count phrasing wins first,
    # explicit rate phrasing second, and a bare bookings noun resolves to
    # the authorised booking counter.
    if (
        any(
            k in text_lower
            for k in (
                "more bookings",
                "most bookings",
                "fewer bookings",
                "least bookings",
                "bookings count",
                "booking count",
                "total bookings",
                "number of bookings",
                "booking volume",
                "how many bookings",
            )
        )
        or (
            re.search(r"how many\b.{0,50}\bbookings?\b", text_lower)
            and not re.search(r"\bbooking[\s-]+(?:rate|conversion)\b", text_lower)
        )
    ):
        prefix = "outbound" if t_norm == "outbound" else "inbound"
        return f"{prefix}:bookings_count"
    # Plural "bookings" without count/rate cues resolves to bookings_count
    if (
        t_norm in ("inbound", "outbound", "call center", "")
        and re.search(r"\bbookings\b", text_lower)
        and "attendance" not in text_lower
        and "attended" not in text_lower
    ):
        prefix = "outbound" if t_norm == "outbound" else "inbound"
        return f"{prefix}:bookings_count"
    # Singular "booking" without count cues resolves to the primary rate KPI (e.g. "Inbound booking")
    if (
        t_norm in ("inbound", "outbound", "call center", "")
        and re.search(r"\bbooking\b", text_lower)
        and "attendance" not in text_lower
        and "attended" not in text_lower
    ):
        prefix = "outbound" if t_norm == "outbound" else "inbound"
        return f"{prefix}:booking_rate"
    if any(k in text_lower for k in ("quality score", "qa quality", "quality achievement")):
        prefix = "outbound" if t_norm == "outbound" else "inbound"
        return f"{prefix}:quality_score"
    if (
        any(
            k in text_lower
            for k in (
                "attendance rate",
                "patient attendance",
                "patient attended",
            )
        )
        or (
            t_norm in ("inbound", "outbound")
            and re.search(r"\battendance\b", text_lower)
            and "attendance compliance" not in text_lower
        )
    ):
        prefix = "outbound" if t_norm == "outbound" else "inbound"
        return f"{prefix}:attendance_rate"

    return None


_SCORE_THRESHOLD_QUERY_RE = re.compile(
    r"\bhow\s+many\b.*\b(?:employees?|agents?|people|staff)\b.*\b"
    r"(?P<op>above|over|exceed(?:ing)?|more\s+than|at\s+least|below|under|less\s+than)\s+"
    r"(?P<val>\d+(?:\.\d+)?)\s*%?",
    re.IGNORECASE,
)


def parse_score_threshold_query(prompt: str) -> tuple[str, float] | None:
    """Parse score/KPI threshold count queries such as 'How many Finance employees had a score above 85%?'."""
    match = _SCORE_THRESHOLD_QUERY_RE.search(prompt or "")
    if not match:
        return None
    op_raw = " ".join(match.group("op").casefold().split())
    if op_raw.startswith("exceed"):
        op_raw = "above"
    return op_raw, float(match.group("val"))


def _extract_person_query_from_prompt(text: str) -> str | None:
    lower = (text or "").strip().casefold()
    emp_id_match = re.search(r"\b(sghd\d+|emp[-_ ]?\d+|e[-_]\d+)\b", lower)
    if emp_id_match:
        return emp_id_match.group(1).upper()

    name_token = r"[a-z]+(?:[-\u2010\u2011][a-z]+)*"
    name_patterns = [
        rf"\b({name_token}(?:\s+{name_token}){{0,3}})['’]s\b",
        r"\b(?:is|was|did)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,3})\s+(?:(?:a\s+)?new\s+joiner|new\s+in|(?:just\s+)?join\b)",
        r"\b([a-zA-Z]+(?:\s+[a-zA-Z]+){0,3})\s+(?:is|was)\s+(?:a\s+)?new\s+joiner\b",
        r"\bwhen\s+did\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,3})\s+join\b",
        r"\b(?:how\s+did|what\s+did|how\s+is|how\s+was)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2})\s+(?:score|perform|do|doing|rank)\b",
        r"\b(?:employee|agent)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,3})",
        r"\b(?:for|about|trend of|trend for|score of|profile of|show me|check|look at)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,3})",
        r"\bdid\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2})\s+(?:have|had|record|recorded|make|made|generate|generated|deliver|delivered|meet|met|miss|missed|hit|exceed|exceeded|pass|passed|fail|failed|achieve|achieved|reach|reached|improve|improved|drop|dropped|change|changed)\b",
    ]
    stop_words = {
        "inbound", "outbound", "call", "center", "dubai", "sharjah", "ajman", "clinics",
        "dxb", "shj", "ajm", "uae", "egy", "egypt",
        "rcm", "finance", "marketing", "pharmacy", "human", "resources", "hr", "it",
        "nursing", "crm", "csr", "sales",
        "coding", "submission", "resubmission", "pre", "approvals", "preapprovals",
        "pre-approvals", "re-submission", "call-center",
        "prior", "auth", "authorization",
        "all", "team", "teams", "department", "departments", "division", "divisions",
        "branch", "branches", "the", "his", "her", "and", "in",
        "on", "at", "to", "from", "with", "who", "what", "which", "better", "best", "worst",
        "lowest", "top", "bottom", "trend", "month", "months", "overall",
        "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
        "january", "february", "march", "april", "june", "july", "august", "september", "october", "november", "december",
        "had", "has", "have", "was", "were", "is", "are", "led", "leads", "leading",
        "scored", "scores", "scoring", "performed", "performing", "performance", "score", "result", "results",
        "rate", "by", "for", "of", "support", "positions", "position", "employee", "employees",
        "agent", "agents", "performer", "performers", "person", "people", "individual", "highest", "there", "anyone", "somebody",
        "recently", "new", "joiner", "joiners", "a", "an", "just",
        "booking", "bookings", "attendance", "attended", "abandon", "abandoned",
        "reachability", "aht", "quality", "pms", "kpi", "kpis", "metric", "metrics",
        "target", "targets", "gap", "gaps", "action", "actions", "corrective", "coaching",
        "plan", "proposal", "this", "page", "view", "dashboard", "scorecard",
        "presentation", "monthly", "summary", "executive", "managerial", "corporate",
        "structure", "leakage", "rejection", "drivers", "bottlenecks",
        "during", "across", "between", "against", "over", "under", "about",
        "media", "buyer", "specialist", "re", "time", "trajectory",
        # Closed-class leftovers. A wide match such as "Show Marketing's" or
        # "for the month that" used to drop the real head ("Marketing",
        # "month") and return the residue ("Show", "that") as a person.
        "show", "tell", "give", "list", "find", "get", "display", "open",
        "please", "can", "me", "you", "my", "your", "our", "we",
        "that", "those", "these", "same", "last", "latest", "first", "next",
        "previous", "current", "published", "unpublished", "selected",
        "not", "been", "did", "does", "do", "would", "could", "should",
        "generated", "achieved", "recorded", "delivered", "leader", "leaders",
        "role", "roles", "weakest", "strongest", "most", "fewest", "more", "less",
        "emirates", "their", "its", "it", "down", "missing", "miss", "missed",
        "within", "check", "evaluate", "instead", "him",
        "let", "lets", "she", "he", "there", "here", "where", "how", "when", "why",
        "workforce", "analyst", "trainer", "quality", "assurance", "company", "everything", "things", "we", "they",
        "waiting", "wait", "cpl", "leads", "rework", "average", "avg", "mean", "cohort", "entire", "whole",
        "reporting", "review", "management", "monthly", "quarterly", "weekly", "daily", "summary", "overview", "analysis",
        "human", "resources", "administration", "offshore",
        "compare", "comparing", "comparison", "versus", "vs", "between", "calculate", "explain", "describe", "summarize",
        "share", "send", "email", "mail", "notify", "draft", "propose", "suggest", "recommend", "create", "make",
        "analyze", "analyse", "examine", "inspect", "evaluate", "assess", "identify", "determine", "compute", "count",
        "detail", "details", "breakdown", "also", "then", "both", "either", "actual", "variance", "distance",
        "difference", "change", "delta", "movement",
    }
    person_search_text = re.sub(
        r"^\s*not\s+[a-zA-Z]+(?:\s+[a-zA-Z]+)?\s*(?:,|—|-)+\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Pattern 0 is the possessive span. Its head is the token glued to "'s".
    # The other patterns introduce a name after a cue ("for", "employee", ...).
    for index, pat in enumerate(name_patterns):
        for m in re.finditer(pat, person_search_text, flags=re.IGNORECASE):
            # "Which Inbound employee got …" ranks an unknown employee.
            # The word after "employee" in that clause is not a supplied name.
            if re.match(r"(?:employee|agent)\s", m.group(0), flags=re.IGNORECASE) and re.search(
                r"\bwhich(?:\s+[\w-]+){0,4}\s+$",
                person_search_text[:m.start()],
                flags=re.IGNORECASE,
            ):
                continue
            if m.end() < len(person_search_text) and person_search_text[m.end()] == "-":
                continue
            if index == 0 and re.match(
                r"^(?:switch|go|see|check|look|review|be|been|got|have|is|are|was|were)\b",
                person_search_text[m.end():].strip(),
                flags=re.IGNORECASE,
            ):
                continue
            name = _person_name_from_span(m.group(1), stop_words, possessive=index == 0)
            if name:
                if " " not in name and difflib.get_close_matches(
                    name.casefold(),
                    ("inbound", "outbound", "marketing", "pharmacy", "finance", "nursing", "coding", "submission", "resubmission", "support", "collections"),
                    n=1,
                    cutoff=0.78,
                ):
                    continue
                return name
    return None


def _person_name_from_span(span: str, stop_words: set[str], *, possessive: bool) -> str | None:
    """Return a name span, or None when the match is only leftover wording.

    Stopword filtering used to keep whatever tokens remained inside a wider
    phrase. "Show Marketing's" became "Show", "for the month that" became
    "that", and "selected team's" became "selected". A person span is the
    contiguous non-stopword tokens at the possessive head, or the contiguous
    name that begins the cue. A stopword head or a stopword where the name
    should start means this match is not a person.
    """
    tokens = [tok for tok in span.strip().split() if tok and not tok.isdigit()]
    if not tokens:
        return None
    folded = [tok.casefold() for tok in tokens]
    if possessive:
        if folded[-1] in stop_words:
            return None
        kept = [tokens[-1]]
        for tok, fold in zip(reversed(tokens[:-1]), reversed(folded[:-1])):
            if fold in stop_words:
                break
            kept.append(tok)
        kept.reverse()
        return " ".join(kept)
    index = 0
    while index < len(tokens) and folded[index] in {"a", "an", "the"}:
        index += 1
    if index >= len(tokens) or folded[index] in stop_words:
        return None
    kept: list[str] = []
    for tok, fold in zip(tokens[index:], folded[index:]):
        if fold in stop_words:
            break
        kept.append(tok)
    return " ".join(kept) if kept else None


_COUNT_WORDS: dict[int, str] = {
    2: "two",
    3: "three",
    4: "four",
    5: "five",
}


def _shared_region_accessible(scope: dict[str, Any], team_name: str) -> bool:
    """Whether `scope` can see the shared region='All' rows of `team_name`.

    Mirrors the record filter (``utils.report_scope.filter_records_by_scope``),
    which is the enforcement point: a Regional Manager only ever sees rows
    whose region is in their grant, and 'All' is in that grant only when the
    grant itself is 'All'; a Branch Director only ever sees rows carrying one
    of their branches, and shared rows carry no branch. Every other role is
    decided by the catalog team check.
    """
    if not user_can_access_team(scope, team_name, performance_level="Employee"):
        return False
    role = str(scope.get("role") or "")
    if role == "Branch Director":
        return False
    if role == "Regional Manager":
        regions = {
            str(r).strip().upper()
            for r in (scope.get("accessible_regions") or scope.get("allowed_regions") or [])
            if str(r).strip()
        }
        return "ALL" in regions
    return True


class HybridQueryRouter:
    """Local-first query router and pre-read validator for PMS AI."""

    def __init__(
        self,
        *,
        scope: dict[str, Any],
        published_periods: Iterable[str] | None = None,
        employee_candidates: Iterable[EmployeeHistoryCandidate] | None = None,
        db: Any = None,
        preview_pattern: AiApprovedPattern | None = None,
    ) -> None:
        self.scope = scope
        self.db = db
        self.preview_pattern = preview_pattern
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

    @staticmethod
    def _normalize_role_tokens(text: str) -> list[str]:
        """Normalize punctuation, common role abbreviations, and simple plurals for flexible position matching."""
        cleaned = re.sub(r"[&/+_-]+", " ", (text or "").casefold())
        cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
        abbrev = {
            "ops": "operation",
            "operations": "operation",
            "sr": "senior",
            "jr": "junior",
            "mgmt": "management",
            "mgr": "manager",
            "dev": "developer",
            "devs": "developer",
            "sup": "supervisor",
            "spec": "specialist",
            "rep": "representative",
        }
        tokens: list[str] = []
        for raw in cleaned.split():
            tok = abbrev.get(raw, raw)
            if len(tok) > 4 and tok.endswith("s") and not tok.endswith("ss"):
                tok = tok[:-1]
            if tok and tok not in {"and", "of", "the", "for", "in"}:
                tokens.append(tok)
        return tokens

    def _detect_position_in_prompt(
        self,
        text_lower: str,
        *,
        preferred_team: str | None = None,
    ) -> tuple[str | None, str | None]:
        """Resolve a position/role name from static aliases, the live catalog, or authorized records."""
        static_team, static_pos = _detect_position(text_lower)
        if static_pos:
            return static_team, static_pos

        candidates: dict[str, tuple[str, str]] = {}
        for t_def in self.catalog.teams.values():
            team_name = str(getattr(t_def, "team", "") or "").strip()
            for pos in getattr(t_def, "positions", ()) or ():
                pos_clean = str(pos or "").strip()
                pos_cf = pos_clean.casefold()
                if len(pos_cf) >= 4 and pos_cf not in candidates:
                    candidates[pos_cf] = (team_name, pos_clean)
        for emp in self.employee_candidates:
            pos_clean = str(getattr(emp, "position", "") or "").strip()
            team_name = str(getattr(emp, "team", "") or "").strip()
            pos_cf = pos_clean.casefold()
            if len(pos_cf) >= 4 and team_name and pos_cf not in candidates:
                candidates[pos_cf] = (team_name, pos_clean)

        # Exclude ambiguous single-word labels (e.g. "Calls" in Pre-Approvals OP Dubai) unless the user is already scoped to that exact team.
        generic_single_words = {
            "call", "calls", "chat", "email", "mail", "admin", "sales", "support",
            "agent", "agents", "manager", "managers", "lead", "leads", "supervisor",
            "specialist", "team", "teams", "staff", "employee", "employees", "role",
            "position", "pharmacy", "marketing", "finance", "inbound", "outbound",
            "dubai", "sharjah", "ajman", "clinics", "coding", "submission",
        }
        pref_cf = (preferred_team or "").strip().casefold()

        def _single_word_allowed(pos_cf_val: str, t_name: str) -> bool:
            words = re.findall(r"[a-z0-9]+", pos_cf_val)
            if len(words) > 1:
                return True
            if not words:
                return False
            if words[0] in generic_single_words:
                return bool(pref_cf and t_name.casefold() == pref_cf)
            return True

        # 1. Exact word-boundary match (longest first)
        for pos_cf in sorted(candidates.keys(), key=len, reverse=True):
            t_name, p_name = candidates[pos_cf]
            if not _single_word_allowed(pos_cf, t_name):
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(pos_cf)}(?![a-z0-9])", text_lower):
                return t_name, p_name

        # 2. Normalized contiguous token-sequence match (handles plurals & abbreviations like "HR Operations Supervisor" / "HR Ops Supervisor" / "Media Buyers")
        prompt_tokens = self._normalize_role_tokens(text_lower)
        if not prompt_tokens:
            return None, None
        prompt_joined = " " + " ".join(prompt_tokens) + " "

        norm_candidates: list[tuple[list[str], str, str]] = []
        for pos_cf, (t_name, p_name) in candidates.items():
            if not _single_word_allowed(pos_cf, t_name):
                continue
            p_toks = self._normalize_role_tokens(p_name)
            if p_toks:
                norm_candidates.append((p_toks, t_name, p_name))
        norm_candidates.sort(key=lambda item: len(item[0]), reverse=True)

        for p_toks, t_name, p_name in norm_candidates:
            if len(p_toks) < 2 and (not pref_cf or t_name.casefold() != pref_cf):
                continue
            needle = " " + " ".join(p_toks) + " "
            if needle in prompt_joined:
                return t_name, p_name

        # 3. Unique contiguous distinctive partial role match (e.g. "assessment center trend" -> "Assessment Center Lead")
        # Require at least 2 contiguous non-team/non-branch/non-generic tokens from the role name.
        non_distinctive_tokens = {
            "what", "how", "show", "give", "tell", "who", "which", "why", "did", "does", "was", "were",
            "are", "is", "been", "trend", "score", "scores", "kpi", "kpis", "performance", "month",
            "months", "progress", "moving", "movement", "change", "changed", "driving", "driver",
            "drivers", "drop", "dropped", "best", "worst", "top", "lowest", "highest", "compare",
            "team", "department", "role", "position", "employee", "agent", "manager", "lead",
            "supervisor", "specialist", "average", "official", "last", "recent", "past", "over",
            "time", "overall", "leading", "leader", "performer", "rate", "booking", "attendance",
            "attended", "location", "branch", "inbound", "outbound", "call", "center", "pharmacy",
            "marketing", "finance", "sales", "support", "coding", "submission", "resubmission",
            "pre", "approval", "dubai", "sharjah", "ajman", "clinic", "egypt", "uae", "rcm", "crm",
            "csr", "pmo", "nursing", "human", "resource",
            "august", "september", "october", "january", "february", "march", "april", "may",
            "june", "july", "november", "december", "2026", "2025",
        }
        scoped_pool = [
            item for item in norm_candidates
            if pref_cf and item[1].casefold() == pref_cf
        ] or norm_candidates
        partial_matches: list[tuple[int, str, str]] = []
        for p_toks, t_name, p_name in scoped_pool:
            if len(p_toks) < 3:
                continue
            best_contig = 0
            for i in range(len(p_toks)):
                for j in range(i + 2, len(p_toks) + 1):
                    sub = p_toks[i:j]
                    distinctive_count = sum(1 for tok in sub if tok not in non_distinctive_tokens and len(tok) >= 3)
                    if distinctive_count < 1:
                        continue
                    if (" " + " ".join(sub) + " ") in prompt_joined:
                        if len(sub) > best_contig:
                            best_contig = len(sub)
            if best_contig >= 2 and best_contig / len(p_toks) >= 0.5:
                partial_matches.append((best_contig, t_name, p_name))
        if len(partial_matches) == 1:
            return partial_matches[0][1], partial_matches[0][2]
        if len(partial_matches) > 1:
            partial_matches.sort(key=lambda x: x[0], reverse=True)
            if partial_matches[0][0] > partial_matches[1][0]:
                return partial_matches[0][1], partial_matches[0][2]
        return None, None

    @staticmethod
    def _resolve_ranked_ordinal_reference(
        text_lower: str,
        prior: ConfirmedQueryContext | None,
    ) -> Any | None:
        """Resolve ordinal follow-ups ('second one', '#2', 'runner up', 'third one', 'lowest one') against prior.ranking_results."""
        if not prior or not getattr(prior, "ranking_results", None):
            return None
        results = list(prior.ranking_results)
        idx: int | None = None
        if re.search(r"(?:(?<!\w)#\s*1|\b(?:first\s+one|1st\s+one|number\s+1|top\s+one))\b", text_lower):
            idx = 0
        elif re.search(r"(?:(?<!\w)#\s*2|\b(?:second\s+one|2nd\s+one|the\s+second|the\s+2nd|number\s+2|runner[- ]?up))\b", text_lower):
            idx = 1
        elif re.search(r"(?:(?<!\w)#\s*3|\b(?:third\s+one|3rd\s+one|the\s+third|the\s+3rd|number\s+3))\b", text_lower):
            idx = 2
        elif re.search(r"(?:(?<!\w)#\s*4|\b(?:fourth\s+one|4th\s+one|the\s+fourth|the\s+4th|number\s+4))\b", text_lower):
            idx = 3
        elif re.search(r"(?:(?<!\w)#\s*5|\b(?:fifth\s+one|5th\s+one|the\s+fifth|the\s+5th|number\s+5))\b", text_lower):
            idx = 4
        elif re.search(r"\b(?:last\s+one|lowest\s+one|worst\s+one|bottom\s+one)\b", text_lower):
            idx = len(results) - 1
        if idx is not None and 0 <= idx < len(results):
            return results[idx]
        return None

    def resolve_and_validate(
        self,
        *,
        prompt: str,
        session_state: SessionFilterContext,
        provider_override: str = "auto",
        clarification_choice_id: str | None = None,
        bounded_context: BoundedIntentContext | None = None,
        precomputed_intent: LocalIntentResult | None = None,
        history: list[Any] | None = None,
        turn_deadline: float | None = None,
    ) -> RouterValidationResult:
        cfg = get_ai_runtime_config()
        text = normalize_prompt_lexical((prompt or "").strip())
        prior = session_state.last_confirmed_query
        if prior and prior.periods:
            from services.ai.contextual_assistant import parse_period_to_month_year

            period_keys = [
                key for period in prior.periods
                if (key := parse_period_to_month_year(period)[2])
            ]
            prior = prior.model_copy(update={"periods": period_keys})
        def _is_selection_only_prompt(raw_text: str, choice: ClarificationChoice) -> bool:
            raw_cf = (raw_text or "").strip().casefold()
            explicit_tokens = {
                "",
                choice.id.casefold(),
                (choice.label or "").strip().casefold(),
                (choice.employee_id or "").strip().casefold(),
                (choice.employee_name or "").strip().casefold(),
                "yes",
                "ok",
                "okay",
                "this one",
                "that one",
                "first one",
                "second one",
                "select",
                "choose",
                "egypt",
                "uae",
                "shared",
            }
            if raw_cf in explicit_tokens:
                return True
            if choice.employee_name and "?" not in raw_cf:
                txt_words = re.findall(r"[a-z0-9]+", raw_cf)
                emp_words = set(re.findall(r"[a-z0-9]+", choice.employee_name.casefold()))
                if 1 <= len(txt_words) <= 4 and all(w in emp_words for w in txt_words):
                    return True
            return False

        matched_choice: ClarificationChoice | None = None
        if clarification_choice_id and prior and prior.pending_clarification_choices:
            matched_choice = next(
                (c for c in prior.pending_clarification_choices if c.id == clarification_choice_id),
                None,
            )
            if matched_choice:
                if matched_choice.employee_id and not session_state.employee_id:
                    session_state = session_state.model_copy(update={"employee_id": matched_choice.employee_id})
                if matched_choice.prompt_to_send and (
                    _is_selection_only_prompt(text, matched_choice)
                    or not text
                    or (matched_choice.employee_name and any(part.casefold() in text.casefold() for part in matched_choice.employee_name.split() if len(part) > 2))
                    or (matched_choice.employee_id and matched_choice.employee_id.casefold() in text.casefold())
                ):
                    text = matched_choice.prompt_to_send.strip()
        elif (
            not clarification_choice_id
            and prior
            and prior.pending_clarification_code == "AMBIGUOUS_PERSON"
            and prior.pending_clarification_choices
            and text
            and len(text.split()) <= 5
        ):
            text_cf = text.casefold()
            plain_matches = [
                c
                for c in prior.pending_clarification_choices
                if text_cf
                in {
                    (c.employee_id or "").strip().casefold(),
                    (c.employee_name or "").strip().casefold(),
                    (c.label or "").strip().casefold(),
                }
            ]
            if not plain_matches and "?" not in text_cf:
                txt_words = re.findall(r"[a-z0-9]+", text_cf)
                if 1 <= len(txt_words) <= 4:
                    plain_matches = [
                        c
                        for c in prior.pending_clarification_choices
                        if c.employee_name
                        and all(
                            w in set(re.findall(r"[a-z0-9]+", c.employee_name.casefold()))
                            for w in txt_words
                        )
                    ]
            if len(plain_matches) == 1:
                matched_choice = plain_matches[0]
                if matched_choice.prompt_to_send:
                    text = matched_choice.prompt_to_send.strip()
        lower = text.casefold()

        if matched_choice and matched_choice.id in {"choice-shared-rcm", "choice-shared-finance"}:
            # Shared All-region scorecard (PR #84): an authorised choice
            # resolves to a read-only answer plan below instead of
            # "not available". Shared records (region='All') are
            # authoritative PMS rows, aggregable on their own by the single
            # averaging rule, and never folded into an Egypt-only or
            # UAE-only total — no approved attribution rule exists for that,
            # and none is invented here. Access is gated to scopes that can
            # actually see region='All' rows (see _shared_region_accessible):
            # the record filter drops 'All' rows for single-region Regional
            # Managers and branchless rows for Branch Directors, so those
            # roles get a scoped denial here instead of an empty answer
            # downstream.
            shared_team = "RCM" if matched_choice.id == "choice-shared-rcm" else "Finance"
            if not _shared_region_accessible(self.scope, shared_team):
                allowed_fns = ", ".join(self.scope.get("accessible_functions") or []) or "your assigned teams"
                return RouterValidationResult(
                    outcome="restricted_access",
                    plan=StructuredQueryPlan(intent="current_value", team=shared_team, function=shared_team),
                    confirmed_context=prior or ConfirmedQueryContext(),
                    headline=(
                        f"Access restricted: your role does not have permission to view the shared All-region {shared_team} scorecard."
                    ),
                    narrative_bullets=[
                        f"Your account is scoped to {allowed_fns}.",
                        "Shared records have region 'All' and are only visible to scopes that include the shared region.",
                    ],
                    suggested_followups=[
                        f"Show performance summary for my authorized scope in {_format_period_label(self.latest_published_period)}"
                    ],
                    route_used="local_rules",
                )
            # Authorised: fall through to normal plan building. The
            # shared-scope clarification below is skipped for a matched
            # choice so the answer is produced instead of looping.

        # 1. Unsupported Write / Mutation Guardrail
        if any(
            re.search(pat, lower)
            for pat in (
                r"\bdelete\b.*\bevaluation\b",
                r"\b(?:update|change|edit|set|reset)\b.*\b(?:target|score|evaluation)s?\b",
                r"\brecalculate\s+scores\b",
                r"\bapprove\b.*\bevaluation\b",
                r"\bapprove\s+and\s+close\b",
                r"\bmodify\s+score\b",
                r"\bdrop\s+table\b",
            )
        ) or any(
            re.search(pat, normalize_bilingual_text(text))
            for pat in (
                r"حذف.*تقييم",
                r"(?:تعديل|تغيير).*(?:تارجت|السكور|التقييم|سكور|هدف)",
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

        # 1b. Prompt Injection / Malicious Prompt Detection Guardrail
        if any(
            re.search(pat, lower)
            for pat in (
                r"\bignore\b.*\b(?:instructions?|policy|policies|rules|guidelines|permissions?)\b",
                r"\bdisregard\b.*\b(?:instructions?|policy|policies|rules|guidelines|permissions?)\b",
                r"\bforget\b.*\b(?:instructions?|policy|policies|rules|guidelines|permissions?|access\s+rules|previous)\b",
                r"\b(?:system\s+prompt|developer\s+mode|jailbreak|system\s+override|unrestricted)\b",
                r"\blist\s+every\s+employee\s+score\b",
                r"\bprint\s+.*employee\s+scores\b",
                r"\b(?:include|show|list|export|dump|add|display|what|get)\b.*\b(?:salar(?:y|ies)|payroll|compensation|other\s+country)\b",
                r"\bother\s+departments?'?\s+salaries\b",
                r"\bdump\s+the\s+other\s+country\b",
            )
        ) or any(
            re.search(pat, normalize_bilingual_text(text))
            for pat in (
                r"تجاهل.*التعليمات",
                r"(?:رواتب|مرتبات|مرتب|راتب)",
            )
        ):
            plan = StructuredQueryPlan(intent="unsupported", turn_kind_v2="unsupported")
            return RouterValidationResult(
                outcome="unsupported_request",
                plan=plan,
                confirmed_context=ConfirmedQueryContext(intent="unsupported"),
                headline="I cannot follow instructions to override system policies or disclose restricted data.",
                narrative_bullets=[
                    "Requests to bypass system instructions, security boundaries, or access unauthorized data are rejected."
                ],
                suggested_followups=["Show performance summary for my authorized scope"],
                route_used="local_rules",
            )


        # 2. Extract explicit entities from the prompt
        raw_teams_in_prompt = _detect_teams_in_prompt(lower)
        if not raw_teams_in_prompt and is_off_topic_prompt(text):
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
        # Bare cross-country aliases (Coding / Submission / Re-Submission /
        # Resubmission) with no country context are ambiguous: they are
        # recorded here and clarified in section 4b instead of silently
        # defaulting to one country. Scoped session context resolves them:
        # an explicit session team, or a short follow-up to a prior turn
        # about one side of the pair, is that context.
        ambiguous_bare_teams: list[str] = []
        resolved_alias_region: str | None = None
        # Two or more distinct team mentions make this a team comparison:
        # comparisons skip the bare-alias clarification (section 4b) and are
        # handled downstream, so the bare names stay in teams_in_prompt.
        ar_teams_hint = detect_arabic_teams(text) if contains_arabic(text) else []
        for _at in ar_teams_hint:
            if _at not in raw_teams_in_prompt:
                raw_teams_in_prompt.append(_at)
        is_multi_team_prompt = len(set(raw_teams_in_prompt)) >= 2
        ar_country_hint = detect_arabic_country(text)
        has_egy_hint = bool(re.search(r"\b(?:egy|egypt)\b", lower)) or ar_country_hint == "EGY"
        has_uae_hint = bool(re.search(r"\buae\b", lower)) or ar_country_hint == "UAE"
        has_ksa_hint = bool(ksa_region_hint_from_prompt(text)) or ar_country_hint == "KSA"
        for raw_t in raw_teams_in_prompt:
            # The "Re-Submission" spelling with an unhyphenated
            # "resubmission" elsewhere in the prompt is the same bare
            # alias as "resubmission": resolve it through the bare-alias
            # path below, never through a silent country default.
            bare_t = raw_t
            if raw_t == "Re-Submission" and "resubmission" in lower and "re-submission" not in lower and not has_uae_hint:
                bare_t = "Resubmission"
            if has_egy_hint:
                resolved_t = (
                    BARE_CROSS_COUNTRY_TEAMS[bare_t][0]
                    if bare_t in BARE_CROSS_COUNTRY_TEAMS
                    else (resolve_canonical_team_name(raw_t, prompt=lower, scope=self.scope) or raw_t)
                )
            elif has_uae_hint and bare_t in BARE_CROSS_COUNTRY_TEAMS:
                resolved_t = BARE_CROSS_COUNTRY_TEAMS[bare_t][1]
            elif has_ksa_hint:
                resolved_t = raw_t
            elif bare_t in BARE_CROSS_COUNTRY_TEAMS:
                resolved_t = resolve_canonical_team_name(bare_t, prompt=lower, scope=self.scope)
                if resolved_t is None:
                    pair = BARE_CROSS_COUNTRY_TEAMS[bare_t]
                    session_team = (session_state.team or "").strip()
                    prior_team = (prior.team or "").strip() if prior else ""
                    is_followup_like = (
                        lower.startswith("and ")
                        or lower.startswith("what about ")
                        or "compare it with" in lower
                        or any(phrase in lower for phrase in ("this team", "this score", "about this", "for this"))
                    )
                    if session_team in pair:
                        resolved_t = session_team
                        resolved_alias_region = "EGY" if session_team == pair[0] else "UAE"
                    elif is_followup_like and prior_team in pair:
                        resolved_t = prior_team
                        resolved_alias_region = "EGY" if prior_team == pair[0] else "UAE"
                    elif (region_hint := (prior.region if prior else None) or session_state.region) in ("EGY", "UAE"):
                        resolved_t = pair[0] if region_hint == "EGY" else pair[1]
                        resolved_alias_region = region_hint
                    elif is_multi_team_prompt or not (
                        user_can_access_team(self.scope, pair[0])
                        or user_can_access_team(self.scope, pair[1])
                    ):
                        # Team comparison, or a caller who cannot access
                        # either side of the pair: keep the bare name the
                        # caller used so the comparison and the final access
                        # guard see it. The guard denies the unauthorised
                        # caller; the comparison proceeds downstream. This
                        # is not a silent country default: no answer is ever
                        # produced for one country from a bare name.
                        resolved_t = bare_t
                    else:
                        if bare_t not in ambiguous_bare_teams:
                            ambiguous_bare_teams.append(bare_t)
                        continue
            else:
                resolved_t = raw_t
            if resolved_t not in teams_in_prompt:
                teams_in_prompt.append(resolved_t)
        preferred_pos_team = (
            teams_in_prompt[0]
            if teams_in_prompt
            else (prior.team if prior and prior.team else session_state.team)
        )
        pos_team, detected_pos = self._detect_position_in_prompt(lower, preferred_team=preferred_pos_team)
        resolved_from_ordinal = False
        if not detected_pos and not teams_in_prompt and prior:
            ord_item = self._resolve_ranked_ordinal_reference(lower, prior)
            if ord_item is not None:
                if ord_item.entity == "position" and ord_item.name:
                    detected_pos = ord_item.name
                    pos_team = prior.team or prior.function
                    resolved_from_ordinal = True
                elif ord_item.entity == "team" and ord_item.name:
                    teams_in_prompt = [ord_item.name]
                    resolved_from_ordinal = True
        if pos_team and not teams_in_prompt:
            teams_in_prompt = [pos_team]

        comparison_teams = list(teams_in_prompt) if len(teams_in_prompt) == 2 else []
        if (
            not teams_in_prompt
            and prior
            and prior.comparison_teams
            and re.search(r"\b(?:both teams|those two teams|same two teams|the two teams)\b", lower)
            and re.search(r"\b(?:compare|higher|lower|difference)\b", lower)
        ):
            comparison_teams = list(prior.comparison_teams)
            teams_in_prompt = list(comparison_teams)

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

        norm_ar_month = normalize_bilingual_text(text)
        has_explicit_month = any(
            (
                re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lower)
                if alias.isascii()
                else bool(re.search(rf"(?<!\w){re.escape(normalize_bilingual_text(alias))}(?!\w)", norm_ar_month))
            )
            for alias in MONTH_ALIASES
        )
        explicit_periods = _extract_periods(
            lower,
            session_state.month,
            session_state.year,
            fallback_period=self.latest_published_period,
        )
        if contains_arabic(text):
            ar_periods = detect_arabic_periods(text, default_year=int(session_state.year or 2026))
            if ar_periods:
                explicit_periods = list(dict.fromkeys([*ar_periods] if not has_explicit_month else [*explicit_periods, *ar_periods]))
                has_explicit_month = True

        # 3. Context Inheritance, Corrections, and Topic Switches
        inherited_filters: list[str] = []
        has_active_prior = bool(
            prior and prior.intent not in (None, "clarify", "unsupported")
        )
        is_explicit_correction = bool(
            has_active_prior and is_explicit_correction_prompt(text)
        )
        is_ranking_correction = bool(
            prior
            and (prior.intent == "ranking" or prior.last_operation_kind in ("ranking", "person_summary"))
            and re.search(
                r"\b(?:no\b|i\s+mean(?:t)?\b|instead\b|actually\b|what\s+about\s+the\s+(?:lowest|worst|highest|best|top))",
                lower,
            )
            and any(w in lower for w in ("lowest", "worst", "bottom", "highest", "best", "top"))
        )
        explicit_fn_from_prompt = (
            ("Pre-Approvals" if (explicit_team.startswith("Pre-Approvals") and (session_state.function or "").casefold() == "pre-approvals" and not re.search(r"\brcm\b", lower)) else function_for_team(explicit_team))
            if explicit_team
            else (
                "RCM"
                if re.search(r"\brcm\b", lower)
                else ("Call Center" if re.search(r"\bcall\s*center\b", lower) else None)
            )
        )
        early_candidate_name_match: str | None = None
        if self.employee_candidates and not (matched_choice and matched_choice.employee_id):
            seen_early_names: set[str] = set()
            unique_early_names: list[str] = []
            for cand in self.employee_candidates:
                cname = str(getattr(cand, "employee_name", "") or "").strip()
                if len(cname.split()) >= 2 and cname.casefold() not in seen_early_names:
                    seen_early_names.add(cname.casefold())
                    unique_early_names.append(cname)
            unique_early_names.sort(key=len, reverse=True)
            for cname in unique_early_names:
                c_cf = cname.casefold()
                if c_cf in lower and re.search(rf"(?<![a-z0-9]){re.escape(c_cf)}(?![a-z0-9])", lower):
                    early_candidate_name_match = cname
                    break
            if early_candidate_name_match is None and contains_arabic(text):
                early_candidate_name_match = match_arabic_person_candidate(text, self.employee_candidates)

        compound_plan_early = (
            plan_compound_parts(
                text,
                team=explicit_team,
                explicit_periods=explicit_periods if has_explicit_month else [],
                prior_metric_id=prior.metric_id if prior else None,
                prior_candidate_metrics=list(prior.candidate_metrics or []) if prior else None,
            )
            if compound_parts_enabled()
            else CompoundQueryPlan()
        )

        has_named_person_reference = bool(
            (matched_choice and matched_choice.employee_id)
            or _extract_person_query_from_prompt(text)
            or early_candidate_name_match
        )
        is_cohort_followup_turn = bool(
            prior
            and lower.startswith(("what about ", "how about ", "and ", "and for ", "what of "))
            and not is_topic_switch_prompt(text)
            and prior.intent == "current_value"
            and not prior.metric_id
            and not prior.last_subject_employee_id
            and (explicit_team or explicit_fn_from_prompt or has_explicit_month or detect_explicit_score_measure(text))
        )
        requests_cohort_score = bool(
            (asks_cohort_score(lower) or is_cohort_followup_turn)
            and (_is_explicit_overall_score_request(lower) or is_cohort_followup_turn)
            and not has_named_person_reference
        )
        ranks_cohort_roles = bool(
            explicit_team
            and re.search(r"\b(?:roles?|positions?)\b", lower)
            and re.search(r"\b(?:rank(?:ed|ing)?|highest|lowest|best|worst|top|bottom)\b", lower)
            and not re.search(r"\b(?:who|their|his|her)\b", lower)
        )
        has_standalone_analytical_cue = bool(
            re.search(
                r"\b(?:score|scores|trend|trends|trajectory|ranking|rank|who\s+(?:is|was|leads|performed)|"
                r"why\s+(?:did|is|are|was|were)|compare|versus|\bvs\b|rejection|abandon|aht|reachability|booking|attendance|quality)\b",
                lower,
            )
        )
        is_refinement_phrase = bool(
            is_explicit_correction
            or lower.startswith("and ")
            or lower.startswith("what about ")
            or lower.startswith("how about ")
            or "compare it with" in lower
            or "same for" in lower
        )
        switched_function = bool(
            explicit_fn_from_prompt
            and has_active_prior
            and prior
            and prior.function
            and explicit_fn_from_prompt.casefold() != prior.function.casefold()
            and not is_explicit_correction
        )
        switched_team_as_new_topic = bool(
            explicit_team
            and has_active_prior
            and prior
            and prior.team
            and explicit_team != prior.team
            and not is_refinement_phrase
            and (has_standalone_analytical_cue or is_topic_switch_prompt(text))
        )
        is_topic_switch = bool(
            has_active_prior
            and (
                is_topic_switch_prompt(text)
                or switched_function
                or switched_team_as_new_topic
            )
            and not is_explicit_correction
        )
        prior_eff = None if is_topic_switch else prior
        explicit_score_measure = detect_explicit_score_measure(text)
        eff_score_measure = (
            explicit_score_measure
            or (prior_eff.score_measure if (prior_eff is not None and prior_eff.score_measure) else None)
            or "official"
        )
        ranked_action_request = is_ranked_action_request(text)
        refers_prior_period_pair = bool(
            prior_eff and prior_eff.comparison_type == "period" and len(prior_eff.periods) == 2
            and re.search(r"\b(?:those|same|the)\s+two\s+(?:months|periods)\b", lower)
        )
        is_deictic_context_ref = any(
            phrase in lower
            for phrase in (
                "this person",
                "that person",
                "this individual",
                "that individual",
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
            prior_eff
            and not is_topic_switch
            and (
                is_explicit_correction
                or is_ranking_correction
                or is_deictic_context_ref
                or lower.startswith("and ")
                or lower.startswith("what about ")
                or lower.startswith("how about ")
                or "compare it with" in lower
                or refers_prior_period_pair
                or ranked_action_request
                or (compound_plan_early.is_arabic_followup and not _extract_person_query_from_prompt(text) and not early_candidate_name_match)
                or (
                    contains_arabic(text)
                    and not has_named_person_reference
                    and not explicit_team
                    and not explicit_fn_from_prompt
                    and (
                        compound_plan_early.asks_target_gap
                        or compound_plan_early.asks_causal_hypothesis
                        or compound_plan_early.asks_corrective_plan
                        or compound_plan_early.asks_unsupported_action
                        or compound_plan_early.asks_period_comparison
                    )
                )
                or (compound_plan_early.asks_target_gap and not has_named_person_reference and not explicit_team)
                or bool(re.search(r"\b(?:he|she|his|her|hers|they|them|their|theirs|that\s+agent|that\s+employee|this\s+person|that\s+person|that\s+team|it)\b", lower) and not has_named_person_reference and not explicit_team and len(text.split()) <= 45)
                or bool(explicit_score_measure and not explicit_team and not explicit_fn_from_prompt)
                or len(text.split()) <= 5
            )
        )

        refers_to_prior_country_scope = bool(
            prior_eff
            and re.search(r"\b(?:same|that|this|result|review|view|instead|again)\b", lower)
        )
        is_country_switch_uae = bool(
            prior_eff
            and (is_short_followup or refers_to_prior_country_scope)
            and re.search(r"\b(?:uae|emirates)\b", lower)
            and not explicit_branches
            and not explicit_team
        )
        is_country_switch_egy = bool(
            prior_eff
            and (is_short_followup or refers_to_prior_country_scope)
            and re.search(r"\b(?:egy|egypt)\b", lower)
            and not explicit_branches
            and not explicit_team
        )
        is_country_followup = is_country_switch_uae or is_country_switch_egy or has_ksa_hint

        # Ignore stale session_state team/branch/position/employee when user switches function or topic explicitly.
        session_fn_conflict = bool(
            explicit_fn_from_prompt
            and session_state.function
            and explicit_fn_from_prompt.casefold() != session_state.function.casefold()
        )
        allow_session_scope_fallback = not is_topic_switch and not session_fn_conflict

        eff_region: str | None = None
        if has_ksa_hint:
            eff_region = "KSA"
        elif is_country_switch_uae or has_uae_hint:
            eff_region = "UAE"
        elif is_country_switch_egy or has_egy_hint:
            eff_region = "EGY"
        elif resolved_alias_region and not asks_team_comparison:
            eff_region = resolved_alias_region
        elif (
            not has_named_person_reference
            and is_short_followup
            and prior_eff
            and prior_eff.region
            and not explicit_team
            and not explicit_branches
        ):
            eff_region = prior_eff.region
        elif (
            not has_named_person_reference
            and
            allow_session_scope_fallback
            and session_state.region
            and session_state.region.strip().casefold() not in ("all", "")
            and not explicit_branches
        ):
            eff_region = session_state.region.strip().upper()

        eff_team = explicit_team
        if not eff_team and not asks_team_comparison:
            if matched_choice and matched_choice.team:
                eff_team = matched_choice.team
            elif (
                not has_named_person_reference
                and explicit_fn_from_prompt is None
                and is_short_followup
                and prior_eff
                and prior_eff.team
            ):
                prior_team_val = prior_eff.team
                if is_country_switch_uae:
                    egy_to_uae = {
                        "Coding EGY": "Coding",
                        "Submission EGY": "Submission",
                        "Resubmission": "Re-Submission",
                        "Pre-Approvals IP Offshore": "Pre-Approvals IP Final",
                    }
                    eff_team = egy_to_uae.get(prior_team_val, prior_team_val)
                    inherited_filters.append("region")
                elif is_country_switch_egy:
                    uae_to_egy = {
                        "Coding": "Coding EGY",
                        "Submission": "Submission EGY",
                        "Re-Submission": "Resubmission",
                        "Pre-Approvals IP Final": "Pre-Approvals IP Offshore",
                        "Pre-Approvals IP Final Dubai": "Pre-Approvals IP Offshore",
                        "Pre-Approvals IP Final SHJAJM": "Pre-Approvals IP Offshore",
                    }
                    eff_team = uae_to_egy.get(prior_team_val, prior_team_val)
                    inherited_filters.append("region")
                else:
                    eff_team = prior_team_val
                    inherited_filters.append("team")
            elif (
                not has_named_person_reference
                and explicit_fn_from_prompt is None
                and allow_session_scope_fallback
                and session_state.team
                and session_state.team.strip().casefold() not in ("all", "")
            ):
                eff_team = session_state.team

        eff_pos = detected_pos
        expands_roles = bool((explicit_team or explicit_fn_from_prompt) and (requests_cohort_score or ranks_cohort_roles))
        if not eff_pos and not expands_roles and not is_country_followup and not has_named_person_reference:
            if matched_choice and matched_choice.position:
                eff_pos = matched_choice.position
            elif is_short_followup and prior_eff and prior_eff.position:
                if not explicit_team or explicit_team == prior_eff.team:
                    eff_pos = prior_eff.position
                    inherited_filters.append("position")
            elif (
                allow_session_scope_fallback
                and session_state.position
                and session_state.position.strip().casefold() not in ("all", "")
                and (not explicit_team or explicit_team in (session_state.team, "Support Positions", "Call Center"))
            ):
                eff_pos = session_state.position
                if not eff_team:
                    eff_team = "Support Positions"

        prior_was_branch_comparison = bool(
            prior_eff
            and (
                prior_eff.intent == "compare_branches"
                or prior_eff.comparison_type == "branch"
                or len(prior_eff.branches or []) >= 2
            )
        )
        team_allows_prior_branch = (
            (not explicit_team)
            or (
                explicit_team in ("Inbound", "Outbound")
                and (not prior_eff or prior_eff.team in (None, "Inbound", "Outbound"))
            )
        )
        eff_branch = explicit_branch
        if not eff_branch and not asks_branch_comparison and not is_country_followup:
            if matched_choice and matched_choice.branch:
                eff_branch = matched_choice.branch
            elif not has_named_person_reference and is_short_followup and prior_eff and prior_eff.branch and team_allows_prior_branch and (
                not prior_was_branch_comparison or (has_explicit_month and not explicit_branches)
            ):
                eff_branch = prior_eff.branch
                inherited_filters.append("branch")
            elif (
                not has_named_person_reference
                and
                allow_session_scope_fallback
                and session_state.branch
                and session_state.branch.casefold() not in ("all", "")
                and team_allows_prior_branch
            ):
                pass

        eff_branches: list[str] = list(explicit_branches)
        if not eff_branches and not is_country_followup:
            if not has_named_person_reference and is_short_followup and prior_eff and prior_eff.branches and team_allows_prior_branch and (
                not prior_was_branch_comparison or (has_explicit_month and not explicit_branches)
            ):
                eff_branches = list(prior_eff.branches)
            elif eff_branch:
                eff_branches = [eff_branch]

        eff_level = explicit_level or (
            matched_choice.performance_level
            if (matched_choice and matched_choice.performance_level)
            else (
                "Corporate"
                if eff_team in ("CRM", "Nursing", "PMO")
                else (
                    prior_eff.performance_level
                    if (is_short_followup and prior_eff and prior_eff.performance_level)
                    else (
                        session_state.performance_level
                        if allow_session_scope_fallback and session_state.performance_level not in (None, "", "All", "all")
                        else "Employee"
                    )
                )
            )
        )

        explicit_overall_score_request = _is_explicit_overall_score_request(lower)
        asks_pure_role_attribute = bool(
            re.search(r"\b(?:position|role|job\s+title|title)\b", lower)
            and not _SPECIFIC_KPI_CUE_RE.search(lower)
        )
        prior_metric_hint = prior_eff.metric_id if (is_short_followup and prior_eff) else None
        discussed_metrics = _detect_discussed_metrics(
            lower,
            team=eff_team,
            position=eff_pos,
            performance_level=eff_level,
        )
        if compound_parts_enabled() and (
            contains_arabic(text)
            or (
                eff_team is not None
                and len([m for m in compound_plan_early.requested_metrics if m != "overall_score"]) >= 2
            )
        ):
            for _cm in compound_plan_early.requested_metrics:
                if _cm not in discussed_metrics:
                    discussed_metrics.append(_cm)
        explicit_metric = (
            matched_choice.metric_id
            if (matched_choice and matched_choice.metric_id)
            else _detect_metric_id(
                lower,
                team=eff_team,
                position=eff_pos,
                performance_level=eff_level,
                prior_metric_id=prior_metric_hint,
            )
        )
        specific_discussed = [m for m in discussed_metrics if m != "overall_score"]
        if not explicit_metric and len(specific_discussed) == 1 and not is_explicit_correction and contains_arabic(text):
            explicit_metric = specific_discussed[0]
        if explicit_metric and (is_explicit_correction or len(discussed_metrics) <= 1):
            discussed_metrics = [explicit_metric]
        elif (
            len(specific_discussed) == 1
            and "overall_score" in discussed_metrics
            and not is_explicit_correction
        ):
            # Compound KPI + Overall PMS (e.g. "Waiting Time and overall PMS"): keep specific KPI for lookup
            # while retaining both items in discussed_metrics for the compound renderer.
            if not explicit_metric:
                explicit_metric = specific_discussed[0]
        elif len(discussed_metrics) >= 2 and not is_explicit_correction and not (matched_choice and matched_choice.metric_id):
            explicit_metric = None
        eff_metric = explicit_metric
        prior_specific_candidates = [
            m for m in (prior_eff.candidate_metrics or []) if m != "overall_score"
        ] if prior_eff else []
        if (
            not eff_metric
            and not explicit_overall_score_request
            and not asks_pure_role_attribute
            and len(discussed_metrics) < 2
            and is_short_followup
            and prior_eff
            and prior_eff.metric_id
            and (
                len(prior_eff.candidate_metrics or []) < 2
                or (
                    len(prior_specific_candidates) <= 1
                    and (compound_plan_early.asks_target_gap or compound_plan_early.asks_target or compound_plan_early.asks_corrective_plan)
                )
            )
        ):
            # Inherit metric if cross-team, same team, or cleanly mappable to the newly corrected team (e.g. bookings_count)
            prior_metric_team = prior_eff.metric_id.split(":")[0]
            canonical_team = re.sub(r"[^a-z0-9]", "", (eff_team or "").casefold())
            prior_team_key = re.sub(r"[^a-z0-9]", "", prior_metric_team.casefold())
            if ":" not in prior_eff.metric_id or not eff_team or canonical_team == prior_team_key:
                eff_metric = prior_eff.metric_id
                inherited_filters.append("metric")
            elif eff_team:
                metric_suffix = prior_eff.metric_id.rsplit(":", 1)[-1]
                if eff_team in ("Inbound", "Outbound") and metric_suffix in (
                    "bookings_count",
                    "attended_count",
                    "handled_calls_count",
                    "abandoned_calls_count",
                ):
                    eff_metric = f"{eff_team.casefold()}:{metric_suffix}"
                    inherited_filters.append("metric")
                else:
                    prior_metric = self.catalog.metrics.get(prior_eff.metric_id)
                    remapped_def = self.catalog.find_metric_definition(
                        team=eff_team,
                        kpi_key_or_label=prior_metric.display_name if prior_metric else metric_suffix.replace("_", " "),
                        position=eff_pos,
                        performance_level=eff_level,
                    )
                    if remapped_def is not None:
                        eff_metric = remapped_def.metric_id
                        inherited_filters.append("metric")

        # Infer or correct team from unambiguous Call Center metric (e.g. reachability -> Outbound, abandon_rate -> Inbound)
        if not explicit_team and explicit_metric:
            if explicit_metric == "outbound:reachability":
                eff_team = "Outbound"
            elif explicit_metric == "inbound:abandon_rate":
                eff_team = "Inbound"
        if not eff_team and eff_metric:
            if eff_metric in ("inbound:abandon_rate", "inbound:fcr"):
                eff_team = "Inbound"
            elif eff_metric in ("outbound:reachability", "outbound:aht"):
                eff_team = "Outbound"

        eff_fn = (
            explicit_fn_from_prompt
            or (
                session_state.function
                if allow_session_scope_fallback
                and not has_named_person_reference
                and session_state.team == eff_team
                else None
            )
            or (function_for_team(eff_team) if eff_team else None)
            or (
                session_state.function
                if allow_session_scope_fallback and not has_named_person_reference
                else None
            )
        )
        if eff_team:
            if (
                eff_team.startswith("Pre-Approvals")
                and (session_state.function or "").casefold() == "pre-approvals"
                and not re.search(r"\brcm\b", lower)
                and not is_topic_switch
            ):
                eff_fn = "Pre-Approvals"
            elif (
                not explicit_team
                and session_state.team == eff_team
                and allow_session_scope_fallback
                and session_state.function
            ):
                eff_fn = session_state.function
            else:
                inferred_fn = function_for_team(eff_team)
                if inferred_fn:
                    eff_fn = inferred_fn

        eff_periods = list(explicit_periods)
        if is_short_followup and prior_eff and prior_eff.periods:
            is_cmp_followup = bool(
                has_explicit_month
                and not asks_team_comparison
                and not (prior_eff.comparison_teams and not explicit_team)
                and (
                    "compare it with" in lower
                    or "قارنها" in normalize_bilingual_text(text)
                    or "قارنه" in normalize_bilingual_text(text)
                    or "مقارنه ب" in normalize_bilingual_text(text)
                )
            )
            if is_cmp_followup:
                combined = sorted(set(prior_eff.periods + explicit_periods))
                eff_periods = combined
                inherited_filters.append("periods")
            elif not has_explicit_month:
                eff_periods = list(prior_eff.periods)
                inherited_filters.append("periods")

        # 4. Clarification Checks

        # 4a. Teamless Branch Booking Comparison (fz-009, fz-010)
        asks_booking_count_prompt = bool(
            re.search(r"\bbookings?\b", lower)
            and not re.search(r"\b(?:rate|ratio|conversion|attended|attendance)\b", lower)
        )
        if asks_branch_comparison and asks_booking_count_prompt and not eff_team and not matched_choice:
            booking_choices = [
                ClarificationChoice(
                    id="choice-bookings-inbound",
                    label="Inbound Bookings by Branch",
                    prompt_to_send=text,
                    team="Inbound",
                ),
                ClarificationChoice(
                    id="choice-bookings-outbound",
                    label="Outbound Bookings by Branch",
                    prompt_to_send=text,
                    team="Outbound",
                ),
            ]
            clar_booking = AiClarificationPrompt(
                code="AMBIGUOUS_TEAM_SCOPE",
                question="Which team's bookings would you like to compare across branches (e.g. Inbound or Outbound)?",
                choices=booking_choices,
            )
            return RouterValidationResult(
                outcome="clarification",
                plan=StructuredQueryPlan(
                    intent="clarify",
                    branches=explicit_branches,
                    turn_kind_v2="clarification",
                    clarification_code="AMBIGUOUS_TEAM_SCOPE",
                ),
                confirmed_context=ConfirmedQueryContext(
                    intent="clarify",
                    branches=explicit_branches,
                    pending_clarification_code="AMBIGUOUS_TEAM_SCOPE",
                    pending_clarification_choices=booking_choices,
                ),
                clarification=clar_booking,
                headline=clar_booking.question,
                narrative_bullets=[
                    "Please specify which team the bookings belong to. Booking counts are tracked separately by team."
                ],
                route_used="local_rules",
            )

        # 4b. Country-Ambiguous Team Clarifications (fz-005, fz-013, fz-014, fz-035, fz-037..040, ho-038..041, ho-058..061)
        has_egy_country = bool(re.search(r"\b(?:egy|egypt)\b", lower))
        has_uae_country = bool(re.search(r"\b(?:uae|dubai|sharjah|ajman)\b", lower))
        user_regions: set[str] = set()
        if self.scope:
            for r in (self.scope.get("accessible_regions") or self.scope.get("allowed_regions") or []):
                user_regions.add(str(r).strip().upper())
        is_multi_region_user = self.scope.get("role") == "Admin" or "ALL" in user_regions or len(user_regions) >= 2 or not user_regions

        # Shared All Finance / RCM in Egypt total (fz-035, fz-036, ho-058, ho-059)
        # Skipped for a matched clarification choice: choosing "Shared
        # All-region ..." must answer, not ask the same question again.
        if not matched_choice and re.search(
            r"\bshared\s+(?:rcm|finance)\b"
            r"|\b(?:include|roll|combine)\b.*\b(?:shared|all-region)\s+(?:rcm|finance)\b"
            r"|\ball-region\s+(?:rcm|finance)\b"
            r"|\begypt.*(?:shared|all-region)\s+(?:rcm|finance)\b",
            lower,
        ):
            team_label = "Finance" if "finance" in lower else "RCM"
            shared_choices = [
                ClarificationChoice(
                    id=f"choice-egypt-{team_label.lower()}",
                    label=f"Egypt {team_label} only",
                    prompt_to_send=f"What is the Egypt {team_label} score?",
                    team=team_label,
                ),
                ClarificationChoice(
                    id=f"choice-shared-{team_label.lower()}",
                    label=f"Shared All-region {team_label}",
                    prompt_to_send=f"What is the shared {team_label} score?",
                    team=team_label,
                ),
            ]
            clar_shared = AiClarificationPrompt(
                code="AMBIGUOUS_TEAM_SCOPE",
                question=f"{team_label} records with region 'All' are shared across countries and cannot be folded into an Egypt-only total without an approved attribution rule. Would you like to view Egypt {team_label} or the shared {team_label} scorecard?",
                choices=shared_choices,
            )
            return RouterValidationResult(
                outcome="clarification",
                plan=StructuredQueryPlan(
                    intent="clarify",
                    team=team_label,
                    function=team_label,
                    turn_kind_v2="clarification",
                    clarification_code="AMBIGUOUS_TEAM_SCOPE",
                ),
                confirmed_context=ConfirmedQueryContext(
                    intent="clarify",
                    team=team_label,
                    function=team_label,
                    pending_clarification_code="AMBIGUOUS_TEAM_SCOPE",
                    pending_clarification_choices=shared_choices,
                ),
                clarification=clar_shared,
                headline=clar_shared.question,
                narrative_bullets=[
                    f"Shared {team_label} records have region 'All' and are not attributed to a single country without an approved attribution rule."
                ],
                route_used="local_rules",
            )

        # Ambiguous follow-ups without context ("Which one is doing better?", "Who is ahead?") (ho-038, ho-039)
        if lower.strip().rstrip("?.") in ("which one is doing better", "who is ahead", "which one is better", "who is doing better") and not eff_team:
            scope_choices = [
                ClarificationChoice(
                    id="choice-compare-inbound-outbound",
                    label="Compare Inbound vs Outbound",
                    prompt_to_send="Compare Inbound and Outbound performance",
                    function="Call Center",
                ),
                ClarificationChoice(
                    id="choice-compare-branches",
                    label="Compare UAE Branches",
                    prompt_to_send="Compare Dubai and Sharjah performance",
                ),
            ]
            clar_ahead = AiClarificationPrompt(
                code="AMBIGUOUS_TEAM_SCOPE",
                question="Which teams, branches, or performers would you like to compare?",
                choices=scope_choices,
            )
            return RouterValidationResult(
                outcome="clarification",
                plan=StructuredQueryPlan(intent="clarify", turn_kind_v2="clarification", clarification_code="AMBIGUOUS_TEAM_SCOPE"),
                confirmed_context=ConfirmedQueryContext(intent="clarify", pending_clarification_code="AMBIGUOUS_TEAM_SCOPE", pending_clarification_choices=scope_choices),
                clarification=clar_ahead,
                headline=clar_ahead.question,
                narrative_bullets=["Please specify which entities you would like to compare."],
                route_used="local_rules",
            )

        # Bare cross-country team ambiguity (Phase 2; fz-013, fz-014, ho-060, ho-061).
        # A bare Coding / Submission / Re-Submission / Resubmission with no
        # country word, no single-region scope and no scoped session team
        # must not silently default to one country. The resolver returns
        # None for such names and the team loop records them in
        # ambiguous_bare_teams; ask here instead of answering for the
        # wrong country. Team comparisons are excluded: comparing the two
        # countries (or a restricted-access answer for an unauthorised
        # scope) is handled downstream, not by this clarification.
        # Single-region users never reach this block: the resolver already
        # resolved the bare name to their one authorised country.
        if ambiguous_bare_teams and not asks_team_comparison and not has_egy_country and not has_uae_country and is_multi_region_user and not matched_choice:
            bare_t = ambiguous_bare_teams[0]
            egy_team, uae_team = BARE_CROSS_COUNTRY_TEAMS[bare_t]
            bare_slugs = {
                "Coding": ("choice-coding-egy", "choice-coding-uae", "Coding"),
                "Submission": ("choice-sub-egy", "choice-sub-uae", "Submission"),
                "Re-Submission": ("choice-resub-egy", "choice-resub-uae", "Re-Submission"),
                "Resubmission": ("choice-resub-egy", "choice-resub-uae", "Resubmission"),
            }
            egy_id, uae_id, bare_label = bare_slugs[bare_t]
            bare_choices = [
                ClarificationChoice(
                    id=egy_id,
                    label=f"{bare_label} (Egypt — {egy_team})",
                    prompt_to_send=f"What is the {egy_team} score?",
                    team=egy_team,
                ),
                ClarificationChoice(
                    id=uae_id,
                    label=f"{bare_label} (UAE — {uae_team})",
                    prompt_to_send=f"What is the {uae_team} score?",
                    team=uae_team,
                ),
            ]
            clar_bare = AiClarificationPrompt(
                code="AMBIGUOUS_TEAM_SCOPE",
                question=f"Would you like to review {bare_label} performance for Egypt ({egy_team}) or UAE ({uae_team})?",
                choices=bare_choices,
            )
            return RouterValidationResult(
                outcome="clarification",
                plan=StructuredQueryPlan(
                    intent="clarify",
                    function="RCM",
                    turn_kind_v2="clarification",
                    clarification_code="AMBIGUOUS_TEAM_SCOPE",
                ),
                confirmed_context=ConfirmedQueryContext(
                    intent="clarify",
                    function="RCM",
                    pending_clarification_code="AMBIGUOUS_TEAM_SCOPE",
                    pending_clarification_choices=bare_choices,
                ),
                clarification=clar_bare,
                headline=clar_bare.question,
                narrative_bullets=[
                    f"PMS maintains separate {bare_label} teams and scorecards for Egypt ({egy_team}) and UAE ({uae_team})."
                ],
                route_used="local_rules",
            )

        # Collapsed Pre-Approvals presentation names (Phase 2). "Pre-Approvals
        # IP Final" / "Pre-Approvals OP Final" are presentation merges of two
        # distinct config teams (Dubai and SHJAJM); without a city qualifier
        # the name must not silently answer for one of them. Ask which source
        # team is meant. "Pre-Approvals IP Elective" has a single source team
        # (IP Elective Dubai) and needs no clarification.
        collapsed_pa = None
        if re.search(r"\bpre-approvals ip final\b", lower) and not re.search(r"\b(?:dubai|sharjah|shjajm|shj|ajman|ajm)\b", lower):
            collapsed_pa = ("Pre-Approvals IP Final", "Pre-Approvals IP Final Dubai", "Pre-Approvals IP Final SHJAJM")
        elif re.search(r"\bpre-approvals op final\b", lower) and not re.search(r"\b(?:dubai|sharjah|shjajm|shj|ajman|ajm)\b", lower):
            collapsed_pa = ("Pre-Approvals OP Final", "Pre-Approvals OP Dubai", "Pre-Approvals OP Final SHJAJM")
        if collapsed_pa and not matched_choice and (session_state.team or "").strip() not in (collapsed_pa[1], collapsed_pa[2]):
            pa_label, pa_dubai, pa_shjajm = collapsed_pa
            pa_choices = [
                ClarificationChoice(
                    id="choice-pa-final-dubai",
                    label=f"{pa_label} — Dubai ({pa_dubai})",
                    prompt_to_send=f"What is the {pa_dubai} score?",
                    team=pa_dubai,
                ),
                ClarificationChoice(
                    id="choice-pa-final-shjajm",
                    label=f"{pa_label} — Sharjah & Ajman ({pa_shjajm})",
                    prompt_to_send=f"What is the {pa_shjajm} score?",
                    team=pa_shjajm,
                ),
            ]
            clar_pa_collapsed = AiClarificationPrompt(
                code="AMBIGUOUS_TEAM_SCOPE",
                question=f"{pa_label} merges two separate teams. Would you like Dubai ({pa_dubai}) or Sharjah & Ajman ({pa_shjajm})?",
                choices=pa_choices,
            )
            return RouterValidationResult(
                outcome="clarification",
                plan=StructuredQueryPlan(
                    intent="clarify",
                    function="RCM",
                    turn_kind_v2="clarification",
                    clarification_code="AMBIGUOUS_TEAM_SCOPE",
                ),
                confirmed_context=ConfirmedQueryContext(
                    intent="clarify",
                    function="RCM",
                    pending_clarification_code="AMBIGUOUS_TEAM_SCOPE",
                    pending_clarification_choices=pa_choices,
                ),
                clarification=clar_pa_collapsed,
                headline=clar_pa_collapsed.question,
                narrative_bullets=[
                    f"{pa_label} is a presentation name for {pa_dubai} and {pa_shjajm}, which have separate config teams and scorecards."
                ],
                route_used="local_rules",
            )
        elif collapsed_pa and not matched_choice:
            # Scoped session team is one of the source teams: answer for
            # that source team, not for the merged presentation name (which
            # has no team JSON and no scorecard of its own).
            _pa_session_team = (session_state.team or "").strip()
            if _pa_session_team in (collapsed_pa[1], collapsed_pa[2]):
                teams_in_prompt = [
                    _pa_session_team if t == collapsed_pa[0] else t for t in teams_in_prompt
                ]
                if explicit_team == collapsed_pa[0]:
                    explicit_team = _pa_session_team
                eff_team = _pa_session_team

        # RCM team scope ambiguity (fz-037..fz-040)
        if re.search(r"\b(?:what is the rcm score|what is rcm score|rcm score|rcm performance|how did rcm perform)\b", lower) and not (has_egy_country or has_uae_country or "corporate" in lower or "bsc" in lower) and not matched_choice:
            rcm_choices = [
                ClarificationChoice(
                    id="choice-rcm-egy",
                    label="RCM Egypt Teams",
                    prompt_to_send="What is the Egypt RCM performance?",
                    function="RCM",
                ),
                ClarificationChoice(
                    id="choice-rcm-uae",
                    label="RCM UAE Teams",
                    prompt_to_send="What is the UAE RCM score?",
                    function="RCM",
                ),
                ClarificationChoice(
                    id="choice-rcm-corp",
                    label="RCM Corporate BSC",
                    prompt_to_send="What is the RCM Corporate Balanced Scorecard score?",
                    team="RCM",
                    performance_level="Corporate",
                ),
            ]
            clar_rcm = AiClarificationPrompt(
                code="AMBIGUOUS_TEAM_SCOPE",
                question="Which RCM scope would you like to review (Egypt RCM teams, UAE RCM, or Corporate BSC)?",
                choices=rcm_choices,
            )
            return RouterValidationResult(
                outcome="clarification",
                plan=StructuredQueryPlan(intent="clarify", function="RCM", turn_kind_v2="clarification", clarification_code="AMBIGUOUS_TEAM_SCOPE"),
                confirmed_context=ConfirmedQueryContext(intent="clarify", function="RCM", pending_clarification_code="AMBIGUOUS_TEAM_SCOPE", pending_clarification_choices=rcm_choices),
                clarification=clar_rcm,
                headline=clar_rcm.question,
                narrative_bullets=["RCM encompasses Egypt operational teams, UAE hospital RCM units, and Corporate Balanced Scorecard."],
                route_used="local_rules",
            )

        # Pre-Approvals team scope ambiguity (fz-039, fz-040)
        is_generic_preapprovals = bool(
            re.search(r"\bpre-?approvals?\b", lower)
            and not re.search(r"\b(?:offshore|op|ip|final|dubai|sharjah|elective)\b", lower)
        )
        if is_generic_preapprovals and not (has_egy_country or has_uae_country) and not matched_choice:
            pa_choices = [
                ClarificationChoice(
                    id="choice-pa-egy",
                    label="Pre-Approvals Egypt (Offshore IP)",
                    prompt_to_send="What is the Pre-Approvals IP Offshore score?",
                    team="Pre-Approvals IP Offshore",
                ),
                ClarificationChoice(
                    id="choice-pa-uae",
                    label="Pre-Approvals UAE (OP Final)",
                    prompt_to_send="What is the UAE Pre-Approvals score?",
                    team="Pre-Approvals OP Final",
                ),
            ]
            clar_pa = AiClarificationPrompt(
                code="AMBIGUOUS_TEAM_SCOPE",
                question="Would you like to review Pre-Approvals performance for Egypt (Pre-Approvals IP Offshore) or UAE (OP/IP Final)?",
                choices=pa_choices,
            )
            return RouterValidationResult(
                outcome="clarification",
                plan=StructuredQueryPlan(
                    intent="clarify",
                    function="RCM",
                    turn_kind_v2="clarification",
                    clarification_code="AMBIGUOUS_TEAM_SCOPE",
                ),
                confirmed_context=ConfirmedQueryContext(
                    intent="clarify",
                    function="RCM",
                    pending_clarification_code="AMBIGUOUS_TEAM_SCOPE",
                    pending_clarification_choices=pa_choices,
                ),
                clarification=clar_pa,
                headline=clar_pa.question,
                narrative_bullets=[
                    "Pre-Approvals teams are separate across Egypt offshore operations and UAE hospital facilities."
                ],
                route_used="local_rules",
            )

        # Support positions lowest person ambiguity (fz-005)
        if re.search(r"\blowest\s+person\s+in\s+support\s+team\b", lower) and not has_egy_country and not has_uae_country and is_multi_region_user and not matched_choice and not has_explicit_month:
            supp_choices = [
                ClarificationChoice(
                    id="choice-support-egy",
                    label="Support Positions (Egypt) — Latest Period",
                    prompt_to_send="Who is the lowest performer in Support Positions for Egypt?",
                    team="Support Positions",
                ),
                ClarificationChoice(
                    id="choice-support-uae",
                    label="Support Positions (UAE) — Latest Period",
                    prompt_to_send="Who is the lowest performer in Support Positions for UAE?",
                    team="Support Positions",
                ),
            ]
            clar_supp = AiClarificationPrompt(
                code="AMBIGUOUS_TEAM_SCOPE",
                question="Which country and period would you like to review for the lowest performer in Support Positions?",
                choices=supp_choices,
            )
            return RouterValidationResult(
                outcome="clarification",
                plan=StructuredQueryPlan(intent="clarify", team="Support Positions", function="Call Center", turn_kind_v2="clarification", clarification_code="AMBIGUOUS_TEAM_SCOPE"),
                confirmed_context=ConfirmedQueryContext(intent="clarify", team="Support Positions", function="Call Center", pending_clarification_code="AMBIGUOUS_TEAM_SCOPE", pending_clarification_choices=supp_choices),
                clarification=clar_supp,
                headline=clar_supp.question,
                narrative_bullets=["Support Positions exist across regions and require an explicit country and period to rank."],
                route_used="local_rules",
            )

        if (
            re.search(r"\battendance\b", lower)
            and not eff_team
            and not eff_metric
            and (not eff_fn or eff_fn.casefold() == "call center")
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
            ]
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
                narrative_bullets=[],
                route_used="clarification_choice" if matched_choice else "local_rules",
            )

        if re.search(r"\bother\s+(?:kpi|metric)\b", lower) and not eff_team and (not eff_fn or eff_fn.casefold() == "call center"):
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
            ]
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
                narrative_bullets=[],
                route_used="clarification_choice" if matched_choice else "local_rules",
            )

        if re.search(r"\b(?:new\s+joiners?|(?:just\s+)?join(?:ed|ing)?\b|when\s+did\b.*\bjoin|hire\s+date|joining\s+date|tenure)\b", lower):
            target_t = eff_team or eff_fn or "your authorized scope"
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
                        team=eff_team,
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
            prior_eff is not None
            and prior_eff.last_operation_kind
            in ("person_best_period", "person_worst_period", "employee_best_period", "employee_worst_period")
        )
        has_person_context_early = bool(
            explicit_person_early
            or emp_id_match
            or (prior_eff is not None and prior_eff.last_subject_employee_id and (is_short_followup or has_subject_pronoun_early))
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
                and prior_eff is not None
                and prior_eff.last_operation_kind in ("person_worst_period", "employee_worst_period")
            )
        )
        asks_best_month = bool(
            explicit_best_month
            or (
                not explicit_worst_month
                and not asks_plain_month_score
                and is_short_followup
                and not is_ranking_correction
                and prior_eff is not None
                and prior_eff.last_operation_kind in ("person_best_period", "employee_best_period")
            )
        )
        asks_month_extremum = asks_best_month or asks_worst_month
        has_subject_pronoun = bool(re.search(r"\b(?:his|her|their|him|he|she|they|them)\b", lower))
        explicit_person_query = (
            matched_choice.employee_id
            if (matched_choice and matched_choice.employee_id)
            else (early_candidate_name_match or _extract_person_query_from_prompt(text))
        )
        if not explicit_person_query and self.employee_candidates:
            seen_names: set[str] = set()
            unique_names: list[str] = []
            for cand in self.employee_candidates:
                cname = str(getattr(cand, "employee_name", "") or "").strip()
                if len(cname.split()) >= 2 and cname.casefold() not in seen_names:
                    seen_names.add(cname.casefold())
                    unique_names.append(cname)
            unique_names.sort(key=len, reverse=True)
            for cname in unique_names:
                c_cf = cname.casefold()
                if c_cf in lower and re.search(rf"(?<![a-z0-9]){re.escape(c_cf)}(?![a-z0-9])", lower):
                    explicit_person_query = cname
                    break
        candidate_level_filter = explicit_level or (
            matched_choice.performance_level
            if matched_choice and matched_choice.performance_level
            else (
                None
                if has_named_person_reference
                else (
                    prior_eff.performance_level
                    if is_short_followup and prior_eff and prior_eff.performance_level
                    else (
                        session_state.performance_level
                        if allow_session_scope_fallback
                        and session_state.performance_level not in (None, "", "All", "all")
                        else ("Corporate" if eff_team in ("CRM", "Nursing", "PMO") else None)
                    )
                )
            )
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
                performance_level=candidate_level_filter,
            )
            if emp_res.status in ("none", "not_found"):
                unscoped_emp_res = resolve_employee_from_candidates(
                    explicit_person_query,
                    self.employee_candidates,
                    explicit_employee_id=matched_choice.employee_id if matched_choice else None,
                )
                if unscoped_emp_res.status == "unique":
                    emp_res = unscoped_emp_res
            if emp_res.status == "ambiguous":
                target_t = eff_team or eff_fn or "your authorized scope"
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
                selected_candidate = emp_res.selected
                mismatch_labels: list[str] = []
                prompt_pinned_team = explicit_team or (matched_choice.team if matched_choice and matched_choice.team else None)
                prompt_pinned_fn = explicit_fn_from_prompt
                if prompt_pinned_team and selected_candidate.team.casefold() != prompt_pinned_team.casefold():
                    mismatch_labels.append(
                        f"the person belongs to {selected_candidate.team}"
                    )
                if prompt_pinned_fn and selected_candidate.function.casefold() != prompt_pinned_fn.casefold():
                    mismatch_labels.append(
                        f"the person belongs to {selected_candidate.function}"
                    )
                if detected_pos and selected_candidate.position and selected_candidate.position.casefold() != detected_pos.casefold():
                    mismatch_labels.append(
                        f"the person works as {selected_candidate.position}"
                    )
                if explicit_level and (
                    selected_candidate.performance_level or "Employee"
                ).casefold() != explicit_level.casefold():
                    mismatch_labels.append(
                        f"the person is tracked at {selected_candidate.performance_level} level"
                    )
                if explicit_person_query and mismatch_labels:
                    requested_scope = prompt_pinned_team or prompt_pinned_fn or "the current scope"
                    detail = "; ".join(dict.fromkeys(mismatch_labels))
                    question = (
                        f"{selected_candidate.employee_name} does not match {requested_scope}: {detail}. "
                        "Should I use the employee's scope or keep the requested scope?"
                    )
                    mismatch_clarification = AiClarificationPrompt(
                        code="AMBIGUOUS_PERSON",
                        question=question,
                        choices=[],
                    )
                    return RouterValidationResult(
                        outcome="clarification",
                        plan=StructuredQueryPlan(
                            intent="clarify",
                            team=eff_team,
                            function=eff_fn,
                            periods=eff_periods,
                            turn_kind_v2="clarification",
                            clarification_code="AMBIGUOUS_PERSON",
                        ),
                        confirmed_context=ConfirmedQueryContext(
                            intent="clarify",
                            team=eff_team,
                            function=eff_fn,
                            periods=eff_periods,
                            region=eff_region,
                            pending_clarification_code="AMBIGUOUS_PERSON",
                        ),
                        clarification=mismatch_clarification,
                        headline=question,
                        narrative_bullets=[
                            "Choose whether to follow the employee's recorded team and role or the scope named in your request."
                        ],
                        route_used="local_rules",
                    )
                resolved_employee_id = emp_res.selected.employee_id
                resolved_employee_name = emp_res.selected.employee_name
                if not candidate_level_filter:
                    eff_level = emp_res.selected.performance_level or eff_level
                if not eff_team and emp_res.selected.team:
                    eff_team = emp_res.selected.team
                    if not eff_metric and len(discussed_metrics) < 2:
                        eff_metric = _detect_metric_id(
                            lower, team=eff_team, position=eff_pos, performance_level=eff_level,
                        )

        if (
            explicit_person_query
            and resolved_employee_id
            and prior_eff
            and prior_eff.last_subject_employee_id
            and resolved_employee_id != prior_eff.last_subject_employee_id
            and not has_explicit_month
        ):
            # A newly named employee starts at the latest published period;
            # the prior employee's month may not exist for the new subject.
            eff_periods = [self.latest_published_period]
            inherited_filters = [item for item in inherited_filters if item != "periods"]

        # If person query is a single first name and was not uniquely resolved, clarify instead of guessing (fz-027, fz-028)
        if (
            not resolved_employee_id
            and explicit_person_query
            and len(explicit_person_query.split()) == 1
            and not re.search(r"\b(sghd\d+|emp[-_ ]?\d+|e[-_]\d+)\b", lower)
            and not matched_choice
            and not (is_short_followup and prior and prior.last_subject_employee_id)
            and (self.scope.get("role") == "Admin" or self.scope.get("has_unrestricted_team_access", False) or user_can_access_team(self.scope, eff_team or session_state.team or "Inbound"))
        ):
            tok_title = explicit_person_query.strip().title()
            clar_single_name = AiClarificationPrompt(
                code="AMBIGUOUS_PERSON",
                question=f"Which {tok_title} would you like to review? Please specify their team or full name.",
                choices=[
                    ClarificationChoice(
                        id=f"choice-specify-{tok_title.lower()}",
                        label=f"Specify team or role for {tok_title}",
                        prompt_to_send=f"What is {tok_title}'s score and team?",
                    )
                ],
            )
            return RouterValidationResult(
                outcome="clarification",
                plan=StructuredQueryPlan(
                    intent="clarify",
                    team=eff_team,
                    function=eff_fn,
                    periods=eff_periods,
                    turn_kind_v2="clarification",
                    clarification_code="AMBIGUOUS_PERSON",
                ),
                confirmed_context=ConfirmedQueryContext(
                    intent="clarify",
                    team=eff_team,
                    function=eff_fn,
                    periods=eff_periods,
                    pending_clarification_code="AMBIGUOUS_PERSON",
                    pending_clarification_choices=clar_single_name.choices,
                ),
                clarification=clar_single_name,
                headline=clar_single_name.question,
                narrative_bullets=[
                    f"Multiple employees may match the name {tok_title}. Please specify their team or full name."
                ],
                route_used="local_rules",
            )


        if ranked_action_request and not resolved_employee_id:
            ranked_people = [
                item for item in (prior_eff.ranking_results if prior_eff else [])
                if item.entity == "employee" and item.id
            ]
            if ranked_people and prior_eff and prior_eff.ranking_direction == "worst":
                worst = ranked_people[0]
                tied = [item for item in ranked_people if item.score == worst.score]
                if len(tied) > 1:
                    choices = [
                        ClarificationChoice(id=f"ranked-action-{i}", label=item.name, prompt_to_send=text,
                                            employee_id=item.id, employee_name=item.name, period=item.period,
                                            team=prior_eff.team)
                        for i, item in enumerate(tied[:5])
                    ]
                    clarification = AiClarificationPrompt(code="AMBIGUOUS_PERSON",
                        question="These employees tied for the lowest score. Who should the action be for?",
                        choices=choices)
                    return RouterValidationResult(
                        outcome="clarification", plan=StructuredQueryPlan(intent="clarify"),
                        confirmed_context=prior_eff.model_copy(update={
                            "pending_clarification_code": "AMBIGUOUS_PERSON",
                            "pending_clarification_choices": choices,
                        }),
                        clarification=clarification, headline=clarification.question, route_used="local_rules",
                    )
                resolved_employee_id, resolved_employee_name = worst.id, worst.name
                inherited_filters.append("employee")
            if not resolved_employee_id:
                clarification = AiClarificationPrompt(code="AMBIGUOUS_PERSON",
                    question="Which employee should I draft an action for? Give me their name or list the lowest performers first.")
                return RouterValidationResult(
                    outcome="clarification", plan=StructuredQueryPlan(intent="clarify"),
                    confirmed_context=prior_eff or ConfirmedQueryContext(), clarification=clarification,
                    headline=clarification.question, route_used="local_rules",
                )

        asks_person_role_or_ref = bool(
            re.search(r"\b(?:top\s+agent|top\s+performer|that\s+agent|that\s+employee|that\s+person|this\s+person|the\s+leader)\b", lower)
        )
        prior_was_ranking = bool(
            prior_eff
            and prior_eff.intent == "ranking"
            and prior_eff.last_operation_kind
            not in (
                "person_summary",
                "person_best_period",
                "person_worst_period",
                "employee_best_period",
                "employee_worst_period",
            )
        )
        is_person_attribute_followup = bool(
            has_subject_pronoun
            or asks_person_role_or_ref
            or re.search(r"\b(?:position|role|title|score|trend|history)\b", lower)
        )
        if (
            not resolved_employee_id
            and not explicit_person_query
            and not is_country_followup
            and not is_topic_switch
            and (is_short_followup or has_subject_pronoun or asks_person_role_or_ref)
            and not is_ranking_correction
            and prior_eff
            and (not explicit_team or explicit_team == prior_eff.team)
        ):
            prior_cands = list(prior_eff.candidate_employees or [])
            if len(prior_cands) > 1 and (
                has_subject_pronoun or re.search(r"\b(?:position|role|title|score|trend|history)\b", lower)
            ):
                cand_choices = [
                    ClarificationChoice(
                        id=f"choice-person-{c.get('employee_id')}",
                        label=f"{c.get('employee_name')} ({c.get('employee_id')})" + (f" · {c.get('position')}" if c.get("position") else ""),
                        # The selected choice carries the employee ID; keep the
                        # user's actual follow-up intact so trend, position,
                        # score, and other requests resolve the same way.
                        prompt_to_send=text,
                        team=c.get("team") or eff_team,
                        position=c.get("position"),
                        performance_level=eff_level,
                        employee_id=c.get("employee_id"),
                        employee_name=c.get("employee_name"),
                    )
                    for c in prior_cands[:4]
                    if c.get("employee_id") and c.get("employee_name")
                ]
                if len(cand_choices) >= 2:
                    clar_multi = AiClarificationPrompt(
                        code="AMBIGUOUS_PERSON",
                        question="Multiple agents were listed in the previous turn. Which agent would you like to inspect?",
                        choices=cand_choices,
                    )
                    return RouterValidationResult(
                        outcome="clarification",
                        plan=StructuredQueryPlan(
                            intent="clarify",
                            team=eff_team,
                            function=eff_fn,
                            periods=eff_periods,
                            turn_kind_v2="clarification",
                            clarification_code="AMBIGUOUS_PERSON",
                        ),
                        confirmed_context=ConfirmedQueryContext(
                            intent="clarify",
                            team=eff_team,
                            function=eff_fn,
                            periods=eff_periods,
                            region=eff_region,
                            candidate_employees=prior_cands,
                            pending_clarification_code="AMBIGUOUS_PERSON",
                            pending_clarification_choices=cand_choices,
                        ),
                        clarification=clar_multi,
                        headline=clar_multi.question,
                        narrative_bullets=["Select which employee you would like to view."],
                        route_used="local_rules",
                    )
            is_team_or_kpi_correction = bool(
                is_explicit_correction
                and (explicit_team is not None or explicit_metric is not None)
                and not has_subject_pronoun
                and not asks_person_role_or_ref
            )
            if prior_eff.last_subject_employee_id and not is_team_or_kpi_correction and (not prior_was_ranking or is_person_attribute_followup):
                resolved_employee_id = prior_eff.last_subject_employee_id
                resolved_employee_name = prior_eff.last_subject_employee_name
                inherited_filters.append("employee")

        if (
            (has_subject_pronoun or asks_person_role_or_ref)
            and not resolved_employee_id
            and not explicit_person_query
            and not explicit_team
            and not asks_team_comparison
            and not asks_branch_comparison
            and "corrective action" not in lower
            and "owners" not in lower
            and ("position" in lower or "role" in lower or "title" in lower or has_subject_pronoun)
            and not re.search(r"\b(?:top|best|worst|lowest|highest)\b", lower)
        ):
            clar_unres_p = AiClarificationPrompt(
                code="AMBIGUOUS_PERSON",
                question="Which employee would you like me to check? Please specify their name.",
                choices=[],
            )
            return RouterValidationResult(
                outcome="clarification",
                plan=StructuredQueryPlan(
                    intent="clarify",
                    team=eff_team,
                    function=eff_fn,
                    periods=eff_periods,
                    turn_kind_v2="clarification",
                    clarification_code="AMBIGUOUS_PERSON",
                ),
                confirmed_context=ConfirmedQueryContext(
                    intent="clarify",
                    team=eff_team,
                    function=eff_fn,
                    periods=eff_periods,
                    pending_clarification_code="AMBIGUOUS_PERSON",
                ),
                clarification=clar_unres_p,
                headline=clar_unres_p.question,
                narrative_bullets=["Specify the employee name or team so I can look up their record."],
                route_used="local_rules",
            )

        asks_trend = (
            (len(explicit_periods) >= 2 and bool(re.search(r"\b(?:change[ds]?|movement|move[ds]?)\b", lower)))
            or any(
                w in lower
                for w in (
                    "6-month",
                    "trend",
                    "trends",
                    "trajectory",
                    "progression",
                    "progress",
                    "over time",
                    "multi-month",
                    "month by month",
                    "month-by-month",
                    "month over month",
                    "month-over-month",
                    "history",
                    "score pattern",
                    "monthly pattern",
                    "trend pattern",
                    "evolution",
                    "last 3 months",
                    "last few months",
                    "past months",
                    "over recent months",
                    "changed over",
                    "been moving",
                )
            )
            or bool(
                re.search(
                    r"\b(?:across|over)\s+(?:the\s+|all\s+)?(?:available\s+|recent\s+|past\s+|same\s+)?months\b",
                    lower,
                )
            )
        )
        if asks_trend and not has_explicit_month and not refers_prior_period_pair:
            # A trend follow-up inherits the employee and metric, but its
            # window ends at the latest published period rather than the
            # single month used by the previous direct read.
            eff_periods = [self.latest_published_period]
            inherited_filters = [item for item in inherited_filters if item != "periods"]
        asks_plural_ranking = any(
            phrase in lower
            for phrase in (
                "top 3 agents",
                "top 5 agents",
                "top agents",
                "top employees",
                "best performers",
                "bottom agents",
                "lowest scoring employees",
                "top negative contributors",
                "which employees",
            )
        )
        inherited_ranking_followup = bool(
            is_short_followup
            and prior_was_ranking
            and not is_person_attribute_followup
            and not explicit_person_query
            and not asks_team_comparison
            and not asks_branch_comparison
            and not asks_trend
        )
        asks_ranking_person = bool(
            is_ranking_correction
            or inherited_ranking_followup
            or asks_month_extremum
            or asks_plural_ranking
            or re.search(r"\b(?:ranks?|ranked|ranking)\s*(?:#\s*1|first|lowest|highest)\b", lower)
            or re.search(r"\b(?:best|top|highest(?:\s+scoring)?|lowest(?:\s+scoring)?|bottom|worst|weakest)\s+(?:performers?|persons?|people|employees?|agents?|staff|members?)\b", lower)
            or re.search(r"\b(?:leading|leads)\b.{0,25}\bbookings?\b", lower)
            or any(
                phrase in lower
                for phrase in (
                    "bookings leader",
                    "booking leader",
                    "top bookings",
                    "top booking",
                    "most bookings",
                    "highest bookings",
                    "best agent",
                    "better agent",
                    "best inbound",
                    "best outbound",
                    "best support",
                    "best in support",
                    "#1 top performer",
                    "top performer",
                    "top agent",
                    "top inbound",
                    "top outbound",
                    "top support",
                    "top in support",
                    "lowest agent",
                    "lowest performer",
                    "bottom performer",
                    "weakest performer",
                    "weakest result",
                    "leading agent",
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
                    "achieved the highest",
                    "highest score",
                    "lowest score",
                    "generated the most",
                    "achieved the most",
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
                    "who needs coaching",
                    "needs coaching most",
                    "who needs help",
                    "who is struggling",
                    "most at risk",
                    "meen aswa",
                    "min aswa",
                    "meen a7san",
                    "min a7san",
                    "meen a7sn",
                    "مين أسوأ",
                    "مين اسوأ",
                    "مين اسوا",
                    "أقل موظف",
                    "اقل موظف",
                    "مين أقل",
                    "مين اقل",
                    "مين أحسن",
                    "مين احسن",
                    "أفضل موظف",
                    "افضل موظف",
                    "أعلى موظف",
                    "اعلى موظف",
                    "role of the top",
                    "position of the top",
                )
            )
        )
        if (
            asks_ranking_person and not asks_branch_comparison and not asks_team_comparison
            and not explicit_team and not resolved_employee_id and not explicit_person_query
            and not matched_choice and explicit_fn_from_prompt == "Call Center"
        ):
            eff_team = "Call Center"
            eff_fn = "Call Center"
            eff_pos = detected_pos

        asks_worst = any(
            w in lower
            for w in (
                "lowest",
                "worst",
                "weakest",
                "bottom",
                "negative contributors",
                "caused",
                "needs coaching",
                "needs help",
                "struggling",
                "at risk",
                "aswa",
                "أسوأ",
                "اسوأ",
                "اسوا",
                "أقل",
                "اقل",
            )
        )
        if inherited_ranking_followup and prior and not re.search(
            r"\b(?:lowest|worst|weakest|bottom|highest|best|top)\b", lower
        ):
            asks_worst = prior.ranking_direction == "worst"
        asks_single_person = bool(
            not asks_plural_ranking
            and not (inherited_ranking_followup and prior and len(prior.candidate_employees or []) > 1)
            and (
                is_ranking_correction
                or inherited_ranking_followup
                or emp_id_match
                or possessive_person_match
                or asks_month_extremum
                or resolved_employee_id
                or re.search(r"\b(?:best|top|highest(?:\s+scoring)?|lowest(?:\s+scoring)?|bottom|worst|weakest)\s+(?:performers?|persons?|people|employees?|agents?|staff|members?)\b", lower)
                or re.search(r"\b(?:leading|leads)\b.{0,25}\bbookings?\b", lower)
                or any(
                    phrase in lower
                    for phrase in (
                        "bookings leader",
                        "booking leader",
                        "top bookings",
                        "top booking",
                        "most bookings",
                        "highest bookings",
                        "best agent",
                        "better agent",
                        "best inbound",
                        "best outbound",
                        "best support",
                        "best in support",
                        "#1 top performer",
                        "top performer",
                        "top agent",
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
                        "achieved the highest",
                        "highest score",
                        "lowest score",
                        "generated the most",
                        "achieved the most",
                        "scored lowest",
                        "scored highest",
                        "had the lowest",
                        "had the highest",
                        "has the lowest",
                        "has the highest",
                        "led performance",
                        "who leads",
                        "who needs coaching",
                        "needs coaching most",
                        "who needs help",
                        "who is struggling",
                        "most at risk",
                        "meen aswa",
                        "min aswa",
                        "meen a7san",
                        "min a7san",
                        "meen a7sn",
                        "مين أسوأ",
                        "مين اسوأ",
                        "مين اسوا",
                        "أقل موظف",
                        "اقل موظف",
                        "مين أقل",
                        "مين اقل",
                        "مين أحسن",
                        "مين احسن",
                        "أفضل موظف",
                        "افضل موظف",
                        "أعلى موظف",
                        "اعلى موظف",
                        "role of the top",
                        "position of the top",
                    )
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
            target_t = eff_team or eff_fn or "your authorized scope"
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
            if eff_team not in ("Inbound", "Outbound") or not user_can_access_team(self.scope, eff_team):
                metrics = self.catalog.get_metrics_for_team(eff_team, position=eff_pos, performance_level=eff_level or "Employee") if eff_team and user_can_access_team_level(self.scope, eff_team, eff_level or "Employee") else []
                ranking_choices = [
                    ClarificationChoice(
                        id=f"rank-{m.metric_id}", label=m.display_name, team=eff_team, metric_id=m.metric_id,
                        prompt_to_send=f"Rank employees in {target_t} by {m.display_name} in {latest_lbl}.",
                    )
                    for m in metrics if m.performance_level.casefold() == (eff_level or "Employee").casefold()
                ][:3]
            clar_rank = AiClarificationPrompt(
                code="AMBIGUOUS_KPI_SCOPE",
                question=f"Which ranking metric should be used to rank {target_t} performers?",
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
                narrative_bullets=[],
                route_used="clarification_choice" if matched_choice else "local_rules",
            )

        has_ambiguous_trend_metric = bool(
            asks_trend
            and not eff_metric
            and not explicit_overall_score_request
            and not matched_choice
            and prior_eff is not None
            and len(prior_eff.candidate_metrics or []) >= 2
        )
        if has_ambiguous_trend_metric and prior_eff is not None:
            trend_choices: list[ClarificationChoice] = []
            for m_id in (prior_eff.candidate_metrics or [])[:3]:
                if m_id == "overall_score":
                    trend_choices.append(
                        ClarificationChoice(
                            id="choice-trend-overall-score",
                            label="Overall Weighted PMS Score",
                            prompt_to_send="What was the overall score trend?",
                            team=eff_team,
                            performance_level=eff_level,
                            employee_id=resolved_employee_id,
                            employee_name=resolved_employee_name,
                        )
                    )
                else:
                    m_short = m_id.split(":")[-1]
                    m_lbl = m_short.replace("_", " ").title()
                    trend_choices.append(
                        ClarificationChoice(
                            id=f"choice-trend-{m_short}",
                            label=m_lbl,
                            prompt_to_send=f"What was the {m_lbl} trend?",
                            team=eff_team,
                            metric_id=m_id,
                            performance_level=eff_level,
                            employee_id=resolved_employee_id,
                            employee_name=resolved_employee_name,
                        )
                    )
            if len(trend_choices) >= 2:
                clar_trend = AiClarificationPrompt(
                    code="AMBIGUOUS_KPI_SCOPE",
                    question="Multiple metrics were discussed in the previous turn. Which metric's trend would you like to review?",
                    choices=trend_choices,
                )
                return RouterValidationResult(
                    outcome="clarification",
                    plan=StructuredQueryPlan(
                        intent="clarify",
                        team=eff_team,
                        function=eff_fn,
                        position=eff_pos,
                        branch=eff_branch,
                        branches=eff_branches,
                        performance_level=eff_level,
                        periods=eff_periods,
                        employee_id=resolved_employee_id,
                        employee_name=resolved_employee_name,
                        turn_kind_v2="clarification",
                        clarification_code="AMBIGUOUS_KPI_SCOPE",
                    ),
                    confirmed_context=prior.model_copy(
                        update={
                            "pending_clarification_code": "AMBIGUOUS_KPI_SCOPE",
                            "pending_clarification_choices": trend_choices,
                        }
                    )
                    if prior is not None
                    else ConfirmedQueryContext(
                        intent="clarify",
                        team=eff_team,
                        pending_clarification_code="AMBIGUOUS_KPI_SCOPE",
                        pending_clarification_choices=trend_choices,
                    ),
                    clarification=clar_trend,
                    headline=clar_trend.question,
                    narrative_bullets=[
                        "Specify which KPI or overall score trend you would like to inspect."
                    ],
                    route_used="local_rules",
                )

        has_ambiguous_gap_metric = bool(
            (compound_plan_early.asks_target_gap or compound_plan_early.asks_target)
            and not eff_metric
            and not explicit_overall_score_request
            and not matched_choice
            and prior_eff is not None
            and len(prior_specific_candidates) >= 2
        )
        if has_ambiguous_gap_metric and prior_eff is not None:
            gap_choices: list[ClarificationChoice] = []
            for m_id in prior_specific_candidates[:3]:
                m_short = m_id.split(":")[-1]
                m_lbl = m_short.replace("_", " ").title()
                gap_choices.append(
                    ClarificationChoice(
                        id=f"choice-gap-{m_short}",
                        label=m_lbl,
                        prompt_to_send=f"How far off target was {m_lbl}?",
                        team=eff_team,
                        metric_id=m_id,
                        performance_level=eff_level,
                        employee_id=resolved_employee_id,
                        employee_name=resolved_employee_name,
                    )
                )
            if len(gap_choices) >= 2:
                clar_gap = AiClarificationPrompt(
                    code="AMBIGUOUS_KPI_SCOPE",
                    question="Multiple KPIs were discussed in the previous turn. Which KPI should I compare against its target?",
                    choices=gap_choices,
                )
                return RouterValidationResult(
                    outcome="clarification",
                    plan=StructuredQueryPlan(
                        intent="clarify",
                        team=eff_team,
                        function=eff_fn,
                        position=eff_pos,
                        branch=eff_branch,
                        branches=eff_branches,
                        performance_level=eff_level,
                        periods=eff_periods,
                        employee_id=resolved_employee_id,
                        employee_name=resolved_employee_name,
                        turn_kind_v2="clarification",
                        clarification_code="AMBIGUOUS_KPI_SCOPE",
                    ),
                    confirmed_context=prior.model_copy(
                        update={
                            "pending_clarification_code": "AMBIGUOUS_KPI_SCOPE",
                            "pending_clarification_choices": gap_choices,
                        }
                    )
                    if prior is not None
                    else ConfirmedQueryContext(
                        intent="clarify",
                        team=eff_team,
                        pending_clarification_code="AMBIGUOUS_KPI_SCOPE",
                        pending_clarification_choices=gap_choices,
                    ),
                    clarification=clar_gap,
                    headline=clar_gap.question,
                    narrative_bullets=[
                        "Select which KPI you want compared against its target."
                    ],
                    route_used="local_rules",
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
            (session_state.team and session_state.team.strip().casefold() not in ("all", ""))
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
            ranked_action_request or re.search(
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
                for k in (
                    "corrective action",
                    "corrective actions",
                    "overdue corrective",
                    "sip/pi",
                    "action we did",
                    "actions we did",
                    "action did we",
                    "actions did we",
                    "saved action",
                    "assigned action",
                    "إجراء تصحيحي",
                    "إجراءات تصحيحية",
                    "الاجراءات التصحيحية",
                )
            )
        )
        asks_scorecard_structure = bool(
            eff_level in ("Managerial", "Corporate")
            and not eff_metric
            and not requests_cohort_score
            and any(k in lower for k in ("balanced scorecard", "bsc", "scorecard"))
        )
        asks_score_drivers = is_proposal_request or any(
            phrase in lower
            for phrase in (
                "diagnose ",
                "score drivers",
                "what is driving",
                "what's driving",
                "whats driving",
                "kpi gaps",
                "drove the score gap",
                "why did ",
                "why is ",
                "why are ",
                "why was ",
                "why were ",
                "kpi bottlenecks",
                "dragging",
                "missing target",
                "miss target",
                "missed target",
                "what is pulling",
                "what pulled",
            )
        ) or bool(
            re.search(
                r"\b(?:why|how\s+come|what\s+caused|what\s+drove)\b.*\b(?:down|low|drop|dropped|dropping|below|weak|bad|decline|declined|fell|fall|behind|miss|missed|gap|bottleneck|poor|worse)\b",
                lower,
            )
        )
        asks_vs_target = any(
            phrase in lower for phrase in ("vs target", "versus target", "against target", "meet its")
        ) or bool(re.search(r"\b(?:did|does|whether)\b.*\b(?:meet|met|hit|reach|achieve)\b.*\btarget\b", lower))
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

        fell_into_default_current_value = False
        intent: RouterIntentType = "current_value"
        if is_person_attribute_followup and resolved_employee_id and not asks_ranking_person and not asks_trend:
            intent = "current_value"
        elif (
            prior_eff
            and (prior_eff.intent == "ranking" or prior_eff.prior_ranking_intent)
            and is_explicit_correction
            and not explicit_person_query
            and not has_standalone_analytical_cue
        ):
            intent = "ranking"
            asks_single_person = True
            if "intent" not in inherited_filters:
                inherited_filters.append("intent")
        elif is_ranking_correction and prior_eff:
            intent = "ranking"
            asks_single_person = bool(prior_eff.single_person or True)
            if "intent" not in inherited_filters:
                inherited_filters.append("intent")
        elif (
            is_short_followup
            and not has_explicit_new_intent
            and prior_eff
            and prior_eff.intent
            and prior_eff.intent not in ("clarify", "unsupported")
            and "compare it with" not in lower
        ):
            intent = prior_eff.intent
            has_explicit_direction_word = any(
                w in lower for w in ("lowest", "worst", "bottom", "highest", "best", "top")
            )
            if intent == "ranking" and not asks_ranking_person:
                if not has_explicit_direction_word:
                    asks_worst = prior_eff.ranking_direction == "worst"
                asks_single_person = bool(prior_eff.single_person)
            if prior_was_branch_comparison and len(explicit_branches) == 1 and not asks_branch_comparison:
                if intent == "compare_branches":
                    intent = "actual_vs_target" if eff_metric else "current_value"
                explicit_compare_branch = None
            elif intent == "compare_branches" and not eff_branches and prior_eff.branches and not is_country_followup:
                eff_branches = list(prior_eff.branches)
                if not eff_branch and prior_eff.branch:
                    eff_branch = prior_eff.branch
                if not explicit_compare_branch and len(prior_eff.branches) >= 2:
                    explicit_compare_branch = prior_eff.branches[1]
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
        elif resolved_from_ordinal and asks_trend:
            intent = "trend"
        elif resolved_from_ordinal and asks_score_drivers:
            intent = "score_drivers"
        elif asks_ranking_person or (
            asks_group_leader(lower)
            and not (resolved_from_ordinal and not re.search(r"\b(?:who|employees?|agents?|staff|people)\b", lower))
        ):
            intent = "ranking"
        elif asks_trend and not asks_ranking_person:
            intent = "trend"
        elif asks_score_drivers and (
            explicit_metric is None or "dragging" in lower or "missing target" in lower or "why " in lower
        ):
            intent = "score_drivers"
        elif eff_metric is not None or asks_vs_target:
            intent = "actual_vs_target"
        else:
            intent = "current_value"
            fell_into_default_current_value = True

        matched_pattern = None
        if (
            self.db is not None
            and not (is_short_followup and prior_eff and prior_eff.intent)
            and not matched_choice
            and not resolved_employee_id
            and not asks_best_month
            and not asks_worst_month
            and not is_multi_part_trend_and_ranking
            and not is_multi_part_score_and_ranking
        ):
            from services.ai.approved_patterns import ApprovedPatternMatcher
            from services.ai.identity_service import build_passport

            _passport = self.scope.get("passport") or build_passport(self.scope)
            matched_pattern = ApprovedPatternMatcher(self.db).match_prompt(
                text,
                known_employee_names=[c.employee_name for c in self.employee_candidates if c.employee_name],
                persona_tier=_passport.persona_tier.value if hasattr(_passport, "persona_tier") else None,
                candidate=self.preview_pattern,
            )
        if matched_pattern is not None and matched_pattern.intent in (
            "current_value", "actual_vs_target", "score_drivers", "trend", "compare_periods",
            "compare_branches", "compare_teams", "ranking", "scorecard_structure", "corrective_actions",
        ):
            intent = matched_pattern.intent  # type: ignore[assignment]
            if matched_pattern.metric_hint and not eff_metric:
                if matched_pattern.metric_hint in ("bookings_count", "attended_count") and eff_team in ("Inbound", "Outbound"):
                    eff_metric = f"{eff_team.casefold()}:{matched_pattern.metric_hint}"
                else:
                    eff_metric = matched_pattern.metric_hint
            if intent == "ranking":
                if matched_pattern.operation_kind == "ranking_bottom":
                    asks_worst = True
                if matched_pattern.operation_kind == "ranking_plural" or matched_pattern.tool_choice in (
                    "get_people_contribution_and_rankings",
                ):
                    asks_single_person = False
                else:
                    asks_single_person = True
        else:
            matched_pattern = None

        bare_refinement_without_prior = bool(
            is_bare_scope_or_period_refinement(text) and not has_active_prior and matched_choice is None
        )
        has_valid_current_value_signal = bool(
            not bare_refinement_without_prior
            and (
                eff_metric is not None
                or explicit_team is not None
                or eff_pos is not None
                or explicit_branch is not None
                or resolved_employee_id is not None
                or explicit_person_query is not None
                or asks_plain_month_score
                or matched_choice is not None
                or is_broad_overview_prompt(text)
                or has_pms_performance_signal(text)
                or (
                    (
                        (session_state.team and session_state.team.strip().casefold() not in ("all", ""))
                        or (session_state.function and session_state.function.strip().casefold() not in ("all", ""))
                        or eff_region is not None
                    )
                    and any(
                        w in lower
                        for w in (
                            "score",
                            "scores",
                            "performance",
                            "summary",
                            "summarize",
                            "overview",
                            "status",
                            "result",
                            "results",
                            "analyze",
                            "analysis",
                            "review",
                            "wrong",
                            "issue",
                            "issues",
                            "problem",
                            "problems",
                            "gap",
                            "gaps",
                            "drag",
                            "dragging",
                            "coach",
                            "coaching",
                            "focus",
                            "priority",
                            "priorities",
                            "insight",
                            "insights",
                            "weak",
                            "weakest",
                            "diagnose",
                            "diagnosis",
                            "brief",
                            "doing",
                            "looking",
                            "happening",
                            "ملخص",
                            "مشاكل",
                            "تحليل",
                            "أداء",
                            "اداء",
                        )
                    )
                )
                or (
                    is_short_followup
                    and prior_eff is not None
                    and prior_eff.intent not in (None, "clarify", "unsupported")
                )
            )
        )
        model_led_admin_active = cfg.can_use_model_led_planner(self.scope.get("role"), provider_override)
        needs_semantic_plan = (
            (fell_into_default_current_value and not has_valid_current_value_signal)
            or (
                intent == "compare_periods"
                and not (explicit_metric or explicit_team or explicit_fn_from_prompt or resolved_employee_id)
                and not (is_short_followup and has_active_prior)
                and not re.search(r"\b(?:performance|scores?|kpis?|targets?|overview|summary)\b", lower)
            )
        )
        if (
            fell_into_default_current_value
            and matched_pattern is None
            and not has_valid_current_value_signal
            and not (model_led_admin_active and not bare_refinement_without_prior and not is_vague_dataless_prompt(text))
        ):
            if bare_refinement_without_prior or is_vague_dataless_prompt(text) or re.search(
                r"\b(?:check|look|show|data|numbers?|stats|figures|analyze|review|summary|overview|anything|update|status)\b",
                lower,
            ):
                q_txt = (
                    f"What metric, team, or performance question would you like me to inspect for {text.rstrip('?.!')}?"
                    if bare_refinement_without_prior
                    else "Which team, KPI, person, or performance overview would you like me to inspect?"
                )
                return RouterValidationResult(
                    outcome="clarification",
                    plan=StructuredQueryPlan(
                        intent="clarify",
                        team=eff_team,
                        function=eff_fn,
                        turn_kind_v2="clarification",
                        clarification_code="AMBIGUOUS_TEAM_SCOPE",
                    ),
                    confirmed_context=prior or ConfirmedQueryContext(intent="clarify"),
                    clarification=AiClarificationPrompt(
                        code="AMBIGUOUS_TEAM_SCOPE",
                        question=q_txt,
                        choices=[],
                    ),
                    headline=q_txt,
                    narrative_bullets=[
                        "Specify a team, department, KPI, employee, or time period—or ask for an overall performance overview."
                    ],
                    route_used="local_rules",
                )
            return RouterValidationResult(
                outcome="unsupported_request",
                plan=StructuredQueryPlan(intent="unsupported", turn_kind_v2="unsupported"),
                confirmed_context=prior or ConfirmedQueryContext(intent="unsupported"),
                headline=(
                    "I can only help with PMS performance scorecards, KPIs, trends, comparisons, and corrective actions."
                ),
                narrative_bullets=[
                    "Try asking about overall performance, a team or KPI target, or branch comparisons."
                ],
                suggested_followups=["How are we doing overall?"],
                route_used="local_rules",
            )

        requested_parts: list[str] = (
            ["trend", "ranking"]
            if is_multi_part_trend_and_ranking
            else (["current_value", "ranking"] if is_multi_part_score_and_ranking else [intent])
        )
        if (
            requested_parts == [intent]
            and compound_plan_early.is_compound
            and compound_plan_early.part_kinds
        ):
            for part_k in compound_plan_early.part_kinds:
                tag = f"part:{part_k}"
                if tag not in requested_parts:
                    requested_parts.append(tag)

        if matched_pattern and matched_pattern.requested_parts:
            parts = list(matched_pattern.requested_parts)
            if parts in ([intent], ["trend", "ranking"], ["current_value", "ranking"]):
                requested_parts = parts

        if asks_worst_month:
            asks_worst = True
            op_kind_v2 = "person_worst_period"
        elif asks_best_month:
            asks_worst = False
            op_kind_v2 = "person_best_period"
        elif asks_trend and not asks_ranking_person:
            op_kind_v2 = "trend"
        elif intent == "actual_vs_target" and not asks_vs_target and not asks_score_drivers:
            op_kind_v2 = "current_value"
        elif resolved_employee_id:
            op_kind_v2 = "person_summary"
        else:
            op_kind_v2 = intent

        # When the requested team has records at exactly one authorized level,
        # use that level for team analytics. Do not combine unlike Employee,
        # Managerial, or Corporate scorecards, and leave mixed-level scopes at
        # the established Employee default unless the user chose a level.
        if not candidate_level_filter and not resolved_employee_id:
            if eff_team:
                scoped_candidates = [
                    candidate
                    for candidate in self.employee_candidates
                    if candidate.team.casefold() == eff_team.casefold()
                    or (eff_team.casefold() == "call center" and candidate.function.casefold() == "call center")
                ]
            elif eff_fn:
                scoped_candidates = [
                    candidate
                    for candidate in self.employee_candidates
                    if candidate.function.casefold() == eff_fn.casefold()
                ]
            else:
                scoped_candidates = []
            available_levels = {
                str(candidate.performance_level or "Employee")
                for candidate in scoped_candidates
            }
            if len(available_levels) == 1:
                eff_level = next(iter(available_levels))

        # Direction-aware ranking polarity: for lower_better KPIs (e.g. Waiting Time,
        # Quality Errors, Abandon Rate), "lowest/shortest/fewest" asks for the smallest
        # value (= best performance), while "highest/longest/most" asks for the largest
        # value (= worst performance).
        if intent == "ranking":
            _m_def = None
            if eff_metric:
                _m_def = self.catalog.find_metric_definition(
                    team=eff_team,
                    kpi_key_or_label=eff_metric,
                    position=eff_pos,
                    performance_level=eff_level,
                )
                if _m_def is None:
                    _m_def = self.catalog.find_metric_definition(
                        team=None,
                        kpi_key_or_label=eff_metric,
                        position=eff_pos,
                        performance_level=eff_level,
                    )
                if _m_def is None:
                    _compact_metric = re.sub(r"[^a-z0-9]", "", str(eff_metric).casefold())
                    _m_def = self.catalog.find_metric_definition(
                        team=None,
                        kpi_key_or_label=_compact_metric,
                        position=eff_pos,
                        performance_level=eff_level,
                    )
            _compact_m = re.sub(r"[^a-z0-9]", "", str(eff_metric or "").casefold())
            _prompt_has_lower_better = bool(
                re.search(
                    r"\b(?:waiting\s+time|wait\s+time|abandon(?:ed|ment)?\s+rate|quality\s+errors?|rework(?:\s+percentage|\s+rate)?|response\s+time|rejection\s+rate|policy\s+rejection|no[- ]?shows?|cost\s+per\s+lead|\bcpl\b)\b",
                    lower,
                )
            )
            _is_lower_better = (
                (_m_def is not None and getattr(_m_def, "direction", "higher_better") == "lower_better")
                or any(
                    tok in _compact_m
                    for tok in (
                        "waitingtime",
                        "waittime",
                        "abandonrate",
                        "qualityerror",
                        "rework",
                        "responsetime",
                        "rejectionrate",
                        "noshow",
                    )
                )
                or _prompt_has_lower_better
            )
            if _is_lower_better:
                if re.search(r"\b(?:lowest|shortest|fewest|least|minimum|min)\b", lower) and not re.search(r"\b(?:worst|weakest|bottom)\b", lower):
                    asks_worst = False
                elif re.search(r"\b(?:highest|longest|most|maximum|max)\b", lower) and not re.search(r"\b(?:best|top)\b", lower):
                    asks_worst = True

        # Self-only first-person binding ("my Waiting Time", "how am I doing")
        if (
            (bool(self.scope.get("is_self_only")) or str(self.scope.get("role") or "") in {"Agent", "Employee"})
            and not resolved_employee_id
            and re.search(r"\b(?:my|me|i|myself)\b", lower)
            and self.scope.get("employee_id")
        ):
            self_emp_id = str(self.scope.get("employee_id")).strip()
            resolved_employee_id = self_emp_id
            matched_self = next(
                (c for c in self.employee_candidates if str(c.employee_id).strip().casefold() == self_emp_id.casefold()),
                None,
            )
            if matched_self:
                resolved_employee_name = matched_self.employee_name
                if not eff_team and matched_self.team:
                    eff_team = matched_self.team

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
            score_measure=eff_score_measure,
        )
        plan.verified_cohort_score = bool(
            requests_cohort_score and (plan.team or plan.function)
            and plan.intent == "current_value" and len(plan.periods) == 1
            and not (plan.employee_id or plan.metric or plan.asks_decisions or plan.position)
            and parse_score_threshold_query(text) is None
            and plan.requested_parts == ["current_value"]
            and not (
                compound_parts_enabled()
                and (
                    compound_plan_early.is_compound
                    or compound_plan_early.asks_target_gap
                    or compound_plan_early.asks_causal_hypothesis
                    or compound_plan_early.asks_corrective_plan
                    or compound_plan_early.asks_unsupported_action
                )
            )
        )
        # Keep explicit, fully scoped score comparisons on the exact PMS read path.
        # Named KPI questions and compound requests continue through the planner.
        overall_metric = str(explicit_metric or "").rsplit(":", 1)[-1] in ("", "overall_score")
        has_compound_comparison_extras = bool(
            compound_parts_enabled()
            and (
                compound_plan_early.asks_target_gap
                or compound_plan_early.asks_causal_hypothesis
                or compound_plan_early.asks_corrective_plan
            )
        )
        if overall_metric and not ((asks_ranking_person and not (comparison_teams and not re.search(r"\b(?:agent|employee|person|who)\b", lower))) or asks_branch_comparison) and not has_compound_comparison_extras:
            if (
                not plan.employee_id
                and (not asks_ranking_person or not re.search(r"\b(?:agent|employee|person|who)\b", lower))
                and comparison_teams
                and len(eff_periods) == 1
                and re.search(r"\b(?:compare|compares|comparison|vs\.?|versus|against|ahead|difference|higher|better|stronger|lower|worst|highest|best|or)\b", lower)
                and (
                    re.search(r"\b(?:scores?|scored|performance|points?|higher|better|lower|highest|best|worst)\b|two teams|اعلى|افضل|اقل", lower + " " + normalize_bilingual_text(text))
                    # An explicit two-team compare with no metric named is a comparison of overall scores.
                    or re.search(r"\b(?:compare|compares|comparison|vs\.?|versus|against|ahead)\b", lower)
                )
                and not re.search(r"\b(?:why|drivers?|recommend|decisions?|target)\b", lower)
            ):
                plan.comparison_teams = comparison_teams
                plan.verified_comparison = "team_scores"
                plan.team = plan.position = None
                first_function, second_function = map(function_for_team, comparison_teams)
                plan.function = first_function if first_function == second_function else None
                plan.intent = plan.operation_kind_v2 = "compare_teams"
            elif (
                not asks_team_comparison
                and (plan.team or plan.function or plan.employee_id)
                and len(eff_periods) == 2
                and (
                    re.search(r"\b(?:overall (?:pms )?score|average score|pms score|team score)\b", lower)
                    or (
                        plan.position
                        and re.search(r"\b(?:compare|comparison|vs\.?|versus|difference|between)\b", lower)
                    )
                )
                and not re.search(r"\b(?:why|drivers?|recommend|decisions?|target)\b", lower)
            ):
                plan.verified_comparison = "employee_scores" if plan.employee_id else "period_scores"
                plan.include_employee_position = bool(
                    plan.employee_id and re.search(r"\b(?:positions?|titles?|job roles?)\b", lower)
                )
                plan.intent = "compare_periods"
                plan.operation_kind_v2 = "trend" if plan.employee_id else "compare_periods"
            if plan.verified_comparison:
                plan.requested_parts = [plan.intent]
        if ranked_action_request and plan.employee_id:
            plan.intent = "score_drivers"
            plan.requested_parts = ["score_drivers"]
            plan.operation_kind_v2 = "score_drivers"
            plan.single_person = True

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
            check_reg = eff_region or ("UAE" if has_uae_hint else ("EGY" if has_egy_hint else None))
            unauthorized_team = next(
                (t for t in teams_to_check if not user_can_access_team(self.scope, t, performance_level=check_lvl, region=check_reg)),
                None,
            )
            if not unauthorized_team:
                acc_regions = {
                    str(r or "").strip().upper()
                    for r in (self.scope.get("accessible_regions") or self.scope.get("allowed_regions") or [])
                    if r
                }
                if acc_regions and "ALL" not in acc_regions and len(acc_regions) < 2:
                    if (has_uae_hint or eff_region == "UAE") and "UAE" not in acc_regions:
                        unauthorized_team = "UAE"
                    elif (has_egy_hint or eff_region == "EGY") and "EGY" not in acc_regions:
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
                if plan.intent == "ranking" or "ranking" in plan.requested_parts:
                    return RouterValidationResult(
                        outcome="restricted_access",
                        plan=plan,
                        confirmed_context=prior or ConfirmedQueryContext(),
                        inherited_filters=inherited_filters,
                        route_used=route_used,
                        provider_metrics=provider_metrics,
                        headline="Access restricted: your role is restricted to viewing your own employee scorecard.",
                        narrative_bullets=[
                            "Self-scoped accounts cannot rank team employees or view peer performance records."
                        ],
                        suggested_followups=["Show my performance summary"],
                    )
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

        scoped_overview = (
            plan.intent == "current_value"
            and len(explicit_periods) == 1
            and bool(has_uae_country or has_egy_country or has_ksa_hint)
            and not (plan.employee_id or explicit_person_query or explicit_metric or explicit_team)
            and bool(re.search(r"\b(?:performance|overview|summary)\b", lower))
        )

        # Phase 2: Model-led pilot path - structured tool calling when enabled for Admins
        if (
            model_led_admin_active
            and not plan.verified_comparison
            and not ranked_action_request
            and not explicit_kpi_question_kind(text)
            and not (asks_corrective_actions and re.search(r"\bopen\s+corrective\s+actions?\b", lower))
            and matched_pattern is None
            and not _deterministic_first_question(lower)
        ):
            from services.ai.roster_comparison import ROSTER_TOOL_NAME, ROSTER_TOOL_SCHEMA
            from services.ai.tool_registry import DeterministicToolRegistry

            tool_schemas = {
                **DeterministicToolRegistry.AUTHORIZED_MODEL_LED_TOOLS,
                ROSTER_TOOL_NAME: ROSTER_TOOL_SCHEMA,
            }
            tool_spec_lines = []
            for t_name, t_schema in tool_schemas.items():
                props = t_schema.get("properties") or {}
                req_fields = set(t_schema.get("required") or [])
                arg_parts = []
                for p_name, p_meta in props.items():
                    p_enum = p_meta.get("enum")
                    p_type = "|".join(str(x) for x in p_enum) if isinstance(p_enum, list) else str(p_meta.get("type") or "any")
                    star = "*" if p_name in req_fields else ""
                    arg_parts.append(f"{p_name}{star}:{p_type}")
                t_desc = str(t_schema.get("description") or "").strip()
                tool_spec_lines.append(f"- {t_name}({', '.join(arg_parts)}): {t_desc}")
            tools_catalog_block = "\n".join(tool_spec_lines)

            # Build bounded authorized catalog summary (departments, teams, latest period)
            try:
                auth_catalog = self.catalog.get_authorized_catalog_payload(scope=self.scope)
                auth_funcs = sorted({str(t.function) for t in auth_catalog.eligible_teams if getattr(t, "function", None)})
                auth_teams = sorted({
                    str(getattr(t, "value", None) or getattr(t, "label", None) or getattr(t, "team", None))
                    for t in auth_catalog.eligible_teams
                    if getattr(t, "value", None) or getattr(t, "label", None) or getattr(t, "team", None)
                })
            except Exception:
                auth_funcs, auth_teams = [], []
            catalog_summary_lines = []
            if auth_funcs:
                catalog_summary_lines.append(f"Authorized departments: {', '.join(auth_funcs[:20])}")
            if auth_teams:
                catalog_summary_lines.append(f"Authorized teams: {', '.join(auth_teams[:35])}")
            if self.latest_published_period:
                catalog_summary_lines.append(f"Latest published period: {self.latest_published_period}")
            catalog_summary_block = ("\n" + "\n".join(catalog_summary_lines)) if catalog_summary_lines else ""

            # Phase 5: Supply active, de-identified Admin-approved guidance to the model-led planner.
            # Never injects static scores/answers; PMS always computes fresh verified evidence.
            approved_guidance_block = ""
            shared_guidance_block = ""
            if self.db is not None:
                try:
                    active_guidance = ApprovedPatternMatcher(self.db).list_active_planner_guidance(limit=8)
                    if active_guidance:
                        g_lines = [
                            f"- When phrasing resembles '{g['example']}': intent={g['intent']}"
                            + (f", operation={g['operation']}" if g.get("operation") else "")
                            + (f", tool={g['tool']}" if g.get("tool") else "")
                            + (f", metric={g['metric_hint']}" if g.get("metric_hint") else "")
                            + (f" ({g['note']})" if g.get("note") else "")
                            for g in active_guidance
                        ]
                        approved_guidance_block = (
                            "\nAdmin-approved interpretation guidance (apply only when intent matches; "
                            "preserve contrasting intents and compute all scores fresh via PMS tools):\n"
                            + "\n".join(g_lines)
                        )
                except Exception:
                    approved_guidance_block = ""
                from services.ai.shared_feedback_learning import shared_planner_guidance

                shared_guidance_block = shared_planner_guidance(self.db)
                try:
                    from services.ai.quality_lessons import lessons_prompt_block

                    shared_guidance_block += lessons_prompt_block(self.db)
                except Exception:
                    pass

            # Call provider with structured tool schemas
            from services.ai.provider_engine import ProviderMessage, ProviderRequest, get_unified_provider_engine

            # Build bounded identity + memory context for Pass 1 (<= 500 tokens / 2000 chars)
            # Strip raw employee_code from external planner prompts unless self_only requires caller binding.
            identity_prefix = build_pass1_identity_context(self.scope)
            if identity_prefix and not bool(self.scope.get("is_self_only")):
                identity_prefix = re.sub(r'\s+employee_code="[^"]*"', "", identity_prefix)
            # Build bounded context for the model
            system_prompt = (
                f"[PromptVersion: {MODEL_LED_PLANNER_PROMPT_VERSION}]\n"
                + (f"{identity_prefix}\n" if identity_prefix else "")
                + "You are the PMS AI Assistant planner. Understand the user's English performance question, "
                "resolve conversational references from Context and Recent Dialogue, and select the right read-only PMS tool(s) with exact typed arguments.\n"
                f"Authorized tools (* = required):\n{tools_catalog_block}{catalog_summary_block}{approved_guidance_block}{shared_guidance_block}\n"
                "Tool selection rules:\n"
                "Resolve four things before choosing a tool: requested entity or population, exact KPI or overall score, "
                "explicit country/branch/level, and exact month(s). An explicit field overrides that field from memory. "
                "If the question zooms out from a person or role to the entire team or department, clear the old person and role. "
                "A cohort, staff average, or division is a group; never interpret these words as employee names.\n"
                "1. Use 'query_rankings' for aggregate and overall-score rankings of departments, teams, positions (roles), branches, or employees. "
                "Pass entity ('department'|'team'|'position'|'branch'|'employee'), sort_order ('desc'|'asc'), limit, region ('EGY'|'UAE'), department, team, position, period ('YYYY-MM'), group_by, performance_level, score_threshold, threshold_operator as applicable.\n"
                "2. Follow-up drill-downs: when the user refers to 'in it', 'that department', 'the leading team', 'the top team', 'the second one', '#2', 'runner up', 'third one', or 'lowest one', resolve the exact entity name from Remembered Ranking Winner / Ranking Results in Context, and carry forward region and period unless the user explicitly changes country, month, team, person, or KPI. "
                "When the user asks for a position/role trend (e.g. 'HR Operation Supervisor trend' or 'second one trend'), call 'get_score_trend' with both team and position set to the canonical names. "
                "When the user asks what is driving a position/role's score or why it dropped, call 'get_kpi_diagnosis' with team and position. "
                "NEVER invent a country/region or branch filter if the user did not mention one and Context does not have one. "
                "When the user pivots to a different department ('what about Marketing?'), drop the old team/position and keep the same analytical intent. "
                "When the user asks to re-order or reverse the previous list ('arrange them from lowest to top', 'reverse order'), keep the SAME Prior Ranking Entity (e.g. entity='department' with NO department/team filter), flip sort_order ('asc' vs 'desc'), and pass limit=20.\n"
                "3. For Marketing when asked about its internal teams, pass entity='team' with department='Marketing' (or entity='position' with team='Marketing'); PMS ranks its measured roles.\n"
                "For a cohort's mean or overall score use 'get_kpi_diagnosis' with metric_id='overall_score', "
                "the requested team or department, period and performance_level. A dated Corporate or Managerial score is an actual evaluation. "
                "For the person with the shortest/longest value of a named KPI use 'rank_employees' with that KPI, "
                "the given team and period and limit=1. Choose direction by the raw extreme requested and the metric's polarity. "
                "Retain the department in site comparisons. Report a missing figure for its requested month rather than borrowing a nearby month.\n"
                "4. Use 'search_pms_guide' for general PMS system knowledge questions (what Grades A–E mean, Gap vs Gap Share, Teams at Risk status badges, Balanced Scorecard & performance levels, user roles/RBAC, regions/branches, KPI glossary, or how to find screens/workflows). "
                "Use 'explain_scoring_rules_and_targets' when asked about live team KPI weights, targets, caps, or scorecard configuration.\n"
                "5. Use 'simulate_kpi_improvement' for What-If projections. "
                "Use 'get_corrective_actions' whenever asked what corrective action(s) were done, assigned, saved, open, or overdue for an employee or team (pass employee_id/employee_name, team, and period if specified).\n"
                "6. For persona='self_only', bind first-person questions ('my score', 'how am I doing') to the caller's employee_code.\n"
                "7. For changes in who or what appears between evaluation periods, use 'compare_evaluation_rosters' "
                "with entity, baseline_period and target_period. Roster presence is independent of scores. "
                "Use the dates and direction from the question or verified context and call it on its own.\n"
                "8. Return 'tool_call' for supported data questions, even if the wording is unfamiliar. "
                "Use catalog discovery when the unresolved detail can be found in PMS. "
                "Ask one specific 'clarification' only when a missing user choice would change the result. "
                "Return 'unsupported' if the question cannot be answered from the available tools. "
                "Never give data, scores, or other PMS factual answers in a conversational response.\n"
                'For two independent analytical parts, return {"response_type":"tool_call","tool_calls":[{"tool_name":"...","tool_arguments":{...}},{"tool_name":"...","tool_arguments":{...}}]}. '
                'For a single analytical part, return {"response_type":"tool_call","tool_name":"<tool>","tool_arguments":{...}}. '
                'Or {"response_type":"conversational","direct_response":"..."} or {"response_type":"clarification","clarification_prompt":"...","clarification_choices":[...]}.'
            )

            # Include rich conversation context to enable follow-up resolution
            context_parts = []
            for label, value in (
                ("Team", plan.team),
                ("Function", plan.function),
                ("Position", plan.position),
                ("Country", eff_region),
                ("Branch", plan.branch),
                ("Performance level", plan.performance_level),
            ):
                if value and value.casefold() != "all":
                    context_parts.append(f"{label}: {value}")

            # Check if an explicit employee was resolved from prompt vs inherited pronoun
            eff_emp_name = (matched_choice.employee_name if matched_choice else None) or resolved_employee_name or plan.employee_name or (prior.last_subject_employee_name if (prior and has_subject_pronoun) else None)
            eff_emp_id = (matched_choice.employee_id if matched_choice else None) or resolved_employee_id or plan.employee_id or (session_state.employee_id if has_subject_pronoun else None) or (prior.last_subject_employee_id if (prior and has_subject_pronoun) else None)
            if eff_emp_name or eff_emp_id:
                emp_desc = f"{eff_emp_name} ({eff_emp_id})" if (eff_emp_name and eff_emp_id) else (eff_emp_name or eff_emp_id)
                context_parts.append(f"Subject Employee: {emp_desc}")
            prompt_metric = None
            if re.search(r"\b(?:overall\s+score|score|pms\s+score|performance)\b", lower):
                prompt_metric = "overall_score"
            elif re.search(r"\b(?:waiting\s+time|wait\s+time)\b", lower):
                prompt_metric = "waitingtime"
            elif re.search(r"\b(?:quality\s+errors?|errors?)\b", lower):
                prompt_metric = "quality_errors"
            elif re.search(r"\b(?:job\s+title|position|role)\b", lower):
                prompt_metric = "job_title"
            elif re.search(r"\b(?:booking|bookings)\b", lower):
                prompt_metric = "bookings_count"
            elif re.search(r"\b(?:attendance|attend)\b", lower):
                prompt_metric = "attendance"
            elif re.search(r"\b(?:abandon|abandonment)\b", lower):
                prompt_metric = "abandon_rate"

            context_metric = plan.metric or prompt_metric
            if context_metric:
                context_parts.append(f"Metric: {context_metric}")
            if plan.periods:
                context_parts.append(f"Period: {', '.join(plan.periods)}")
            if prior and prior.last_operation_kind == "roster_comparison" and len(prior.periods) == 2:
                baseline_period, target_period = prior.periods
                context_parts.append(f"Prior roster comparison: baseline {baseline_period}, target {target_period}")
            if prior and prior.ranking_winner:
                context_parts.append(
                    f"Prior Ranking Entity: {prior.ranking_winner.entity}; Remembered Ranking Winner: {prior.ranking_winner.entity}={prior.ranking_winner.name}"
                )
            if prior and getattr(prior, "ranking_results", None):
                ranked_items = ", ".join(
                    f"#{item.rank} {item.entity}={item.name}" + (f" ({item.score:.1f}%)" if item.score is not None else "")
                    for item in prior.ranking_results[:5]
                )
                if ranked_items:
                    context_parts.append(f"Remembered Ranking Results: [{ranked_items}]")
            context_summary = "; ".join(context_parts)

            recent_dialogue = []
            if history:
                for msg in history[-8:]:
                    r_lbl = "User" if getattr(msg, "role", "") == "user" else "Assistant"
                    c_snip = (getattr(msg, "content", "") or "")[:320].replace("\n", " ").strip()
                    c_snip = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[EMAIL]", c_snip)
                    c_snip = re.sub(r"\b(?:SGHD\d+|EMP[-_]?\d+)\b", "[EMPLOYEE_ID]", c_snip, flags=re.IGNORECASE)
                    if c_snip:
                        recent_dialogue.append(f"{r_lbl}: {c_snip}")
            dialogue_str = ("\nRecent Dialogue:\n" + "\n".join(recent_dialogue)) if recent_dialogue else ""

            # Build explicit union of tool argument properties so structured JSON
            # decoders populate typed arguments
            # cleanly instead of emitting empty objects.
            merged_tool_arg_props: dict[str, Any] = {}
            for _t_schema in tool_schemas.values():
                for _p_name, _p_meta in (_t_schema.get("properties") or {}).items():
                    if _p_name not in merged_tool_arg_props:
                        _p_copy = dict(_p_meta)
                        _p_type = _p_copy.get("type")
                        if isinstance(_p_type, str):
                            _p_copy["type"] = [_p_type, "null"]
                        # Avoid conflicting narrow enums across different tools sharing a field name
                        if _p_name in ("region", "threshold_operator", "performance_level", "direction", "entity", "sort_order", "group_by"):
                            merged_tool_arg_props[_p_name] = _p_copy
                        else:
                            _p_copy.pop("enum", None)
                            merged_tool_arg_props[_p_name] = _p_copy

            engine = get_unified_provider_engine()
            planner_timeout = max(cfg.provider_timeout_seconds, 24.0)
            if turn_deadline is not None:
                planner_timeout = min(planner_timeout, turn_deadline - perf_counter())
            req = ProviderRequest(
                system_instruction=system_prompt,
                messages=[
                    ProviderMessage(role="user", content=f"Question: {text}\nContext: {context_summary}{dialogue_str}"),
                ],
                response_format="json",
                json_schema={
                    "type": "object",
                    "properties": {
                        "response_type": {
                            "type": "string",
                            "enum": ["tool_call", "conversational", "clarification", "unsupported"],
                        },
                        "tool_name": {"type": ["string", "null"]},
                        "tool_arguments": {
                            "type": ["object", "string", "null"],
                            "properties": merged_tool_arg_props,
                        },
                        "tool_calls": {
                            "type": "array",
                            "maxItems": 2,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "tool_name": {"type": "string"},
                                    "tool_arguments": {
                                        "type": ["object", "string"],
                                        "properties": merged_tool_arg_props,
                                    },
                                },
                                "required": ["tool_name", "tool_arguments"],
                                "additionalProperties": False,
                            },
                        },
                        "direct_response": {"type": ["string", "null"]},
                        "clarification_prompt": {"type": ["string", "null"]},
                        "clarification_choices": {"type": ["array", "string", "null"], "items": {"type": "string"}},
                    },
                    "required": ["response_type"],
                },
                temperature=0.0,
                max_tokens=None,
                timeout_seconds=planner_timeout,
                purpose="model_led_router",
                task_role="investigation" if (
                    needs_semantic_plan or asks_ranking_person or asks_trend or (prior and is_short_followup)
                    or bool(plan.position) or asks_score_drivers or asks_team_comparison or asks_branch_comparison
                    or len(text.split()) >= 8
                    or parse_query_rankings_spec(text) is not None or is_broad_overview_prompt(text)
                    or plan.operation_kind_v2 in {"ranking", "trend", "compare_periods", "compare_branches",
                                                  "compare_teams", "score_drivers", "person_best_period", "person_worst_period"}
                ) else "routine",
                user_id=str(self.scope.get("user_id") or "") or None,
                user_role=str(self.scope.get("role") or "") or None,
            )

            try:
                if planner_timeout <= 0:
                    raise TimeoutError
                resp = engine.generate(req)
                if not resp.is_success:
                    provider_metrics = metrics_from_provider_response(
                        resp,
                        provider_calls=max(len(resp.attempts), 1 if resp.usage.total_tokens > 0 else 0),
                        fallback_outcome=resp.outcome or "provider_unavailable",
                    )
                    if resp.outcome == "safety_refusal":
                        return RouterValidationResult(
                            outcome="unsupported_request",
                            plan=plan,
                            confirmed_context=prior.model_copy() if prior else ConfirmedQueryContext(),
                            route_used="model_led_pilot",
                            provider_metrics=provider_metrics,
                            headline="I cannot fulfill that request because it was blocked by the provider safety policy.",
                            narrative_bullets=[],
                            suggested_followups=["Ask about authorized PMS scorecards, KPIs, or team rankings."],
                        )
                    route_used = "local_rules"
                if resp.is_success and plan.verified_cohort_score:
                    # The planner has seen the question and scope; execution uses
                    # the authoritative cohort and period resolved before the call.
                    route_used = "model_led_pilot"
                    provider_metrics = metrics_from_provider_response(resp, provider_calls=1)
                elif resp.is_success:
                    import json
                    model_output = json.loads(resp.content)
                    route_used = "model_led_pilot"
                    provider_metrics = metrics_from_provider_response(
                        resp,
                        provider_calls=max(len(resp.attempts), 1),
                    )

                    confirmed_ctx = prior.model_copy() if prior else ConfirmedQueryContext()
                    confirmed_ctx.score_measure = eff_score_measure

                    # Parse tool calls from model output
                    if model_output.get("response_type") == "tool_call":
                        raw_calls = model_output.get("tool_calls")
                        parsed_calls: list[dict[str, Any]] = []
                        if isinstance(raw_calls, list):
                            for raw_call in raw_calls[:2]:
                                if not isinstance(raw_call, dict):
                                    continue
                                raw_name = str(raw_call.get("tool_name") or "").strip()
                                raw_args = raw_call.get("tool_arguments", {})
                                if isinstance(raw_args, str):
                                    try:
                                        raw_args = json.loads(raw_args)
                                    except Exception:
                                        raw_args = {}
                                if not isinstance(raw_args, dict):
                                    raw_args = {}
                                else:
                                    raw_args = clean_planner_tool_arguments(raw_args)
                                parsed_calls.append({"tool_name": raw_name, "tool_arguments": raw_args})
                        if not parsed_calls:
                            raw_args = model_output.get("tool_arguments", {})
                            if isinstance(raw_args, str):
                                try:
                                    raw_args = json.loads(raw_args)
                                except Exception:
                                    raw_args = {}
                            clean_args = clean_planner_tool_arguments(raw_args)
                            parsed_calls = [{
                                "tool_name": str(model_output.get("tool_name") or "").strip(),
                                "tool_arguments": clean_args,
                            }]
                        for call in parsed_calls:
                            call_args = call["tool_arguments"]
                            if "metric_id" not in call_args:
                                m_val = (
                                    call_args.get("metric") or call_args.get("metric_name")
                                    or call_args.get("metric_type") or call_args.get("kpi")
                                    or call_args.get("kpi_key")
                                )
                                if m_val:
                                    call_args["metric_id"] = m_val
                            if str(call_args.get("metric_id") or "").strip().casefold() in ("performance", "score", "overall score", "pms score", "overall"):
                                call_args["metric_id"] = "overall_score"
                        tool_name = parsed_calls[0]["tool_name"]
                        tool_args = parsed_calls[0]["tool_arguments"]
                        plan.model_led_tool_call = {
                            "tool_name": tool_name,
                            "tool_arguments": tool_args,
                        }
                        plan.model_led_tool_calls = parsed_calls
                        if len(parsed_calls) > 1 and any(call["tool_name"] == ROSTER_TOOL_NAME for call in parsed_calls):
                            return RouterValidationResult(
                                outcome="unsupported_request",
                                plan=StructuredQueryPlan(intent="unsupported", turn_kind_v2="unsupported"),
                                confirmed_context=confirmed_ctx,
                                route_used="model_led_pilot",
                                provider_metrics=provider_metrics,
                                headline="PMS can compare evaluation rosters in a separate question.",
                            )
                        if tool_name == ROSTER_TOOL_NAME:
                            plan.intent = "compare_periods"
                            plan.operation_kind_v2 = "roster_comparison"
                            plan.requested_parts = ["roster_comparison"]
                            plan.single_person = False
                        elif tool_name == "query_rankings" and not (asks_branch_comparison and asks_booking_count_prompt):
                            plan.intent = "ranking"
                            plan.operation_kind_v2 = "ranking"
                            plan.single_person = False
                            if isinstance(tool_args, dict):
                                # Normalize country/region and enforce explicit user constraints
                                raw_reg = str(tool_args.get("region") or tool_args.get("country") or "").strip().casefold()
                                norm_reg = {"egypt": "EGY", "egy": "EGY", "uae": "UAE", "emirates": "UAE", "ksa": "KSA"}.get(raw_reg)
                                has_any_country_constraint = bool(has_egy_country or has_uae_country or has_ksa_hint or (eff_region and eff_region in ("EGY", "UAE", "KSA")))
                                if not has_any_country_constraint:
                                    # Never let a structured decoder invent a country filter the user did not ask for.
                                    tool_args.pop("region", None)
                                    tool_args.pop("country", None)
                                elif norm_reg:
                                    tool_args["region"] = norm_reg
                                elif eff_region and eff_region in ("EGY", "UAE", "KSA") and not tool_args.get("region"):
                                    tool_args["region"] = eff_region
                                if explicit_periods and not tool_args.get("period"):
                                    tool_args["period"] = explicit_periods[-1]
                                elif explicit_periods and tool_args.get("period") not in explicit_periods:
                                    tool_args["period"] = explicit_periods[-1]
                                elif not tool_args.get("period") and plan.periods:
                                    tool_args["period"] = plan.periods[-1]
                                if has_egy_country:
                                    tool_args["region"] = "EGY"
                                elif has_uae_country:
                                    tool_args["region"] = "UAE"
                                if not tool_args.get("entity"):
                                    tool_args["entity"] = "department"
                                tool_args.setdefault("score_measure", eff_score_measure)
                                if explicit_score_measure is not None:
                                    tool_args["score_measure"] = explicit_score_measure
                                try:
                                    from models.ai_schemas import QueryRankingsArgs
                                    allowed_qr_fields = set(QueryRankingsArgs.model_fields.keys())
                                    qr_payload = {k: v for k, v in tool_args.items() if k in allowed_qr_fields and v is not None}
                                    plan.query_rankings_args = QueryRankingsArgs(**qr_payload)
                                except Exception:
                                    pass
                        else:
                            if isinstance(tool_args, dict):
                                raw_br = str(tool_args.get("branch") or "").strip().casefold()
                                if raw_br in ("uae", "egy", "egypt", "ksa", "emirates", "all", "all branches"):
                                    tool_args.pop("branch", None)
                                if tool_name in ("get_kpi_diagnosis", "get_score_trend"):
                                    if plan.position and not tool_args.get("position"):
                                        tool_args["position"] = plan.position
                                    if plan.team and not tool_args.get("team"):
                                        tool_args["team"] = plan.team
                                if tool_name in ("get_kpi_diagnosis", "get_score_trend", "compare_branches"):
                                    tool_args.setdefault("score_measure", eff_score_measure)
                                    if explicit_score_measure is not None:
                                        tool_args["score_measure"] = explicit_score_measure
                            plan.intent = "trend" if tool_name == "get_score_trend" else "current_value"
                            confirmed_ctx.team = plan.team or confirmed_ctx.team
                            confirmed_ctx.function = plan.function or confirmed_ctx.function
                            confirmed_ctx.position = plan.position
                            confirmed_ctx.region = eff_region
                            if tool_name == "get_score_trend":
                                confirmed_ctx.intent = "trend"
                                confirmed_ctx.prior_ranking_intent = False
                                confirmed_ctx.ranking_winner = None
                                same_scope_as_prior = bool(
                                    prior_eff
                                    and (plan.team or "").casefold() == (prior_eff.team or "").casefold()
                                )
                                if not same_scope_as_prior:
                                    confirmed_ctx.ranking_results = []
                        return RouterValidationResult(
                            outcome="answer",
                            plan=plan,
                            confirmed_context=confirmed_ctx,
                            route_used="model_led_pilot",
                            provider_metrics=provider_metrics,
                            headline="",
                            narrative_bullets=[],
                            suggested_followups=[],
                        )
                    elif model_output.get("response_type") == "conversational":
                        # Recover the verified person lookup for an explicit employee question.
                        is_perf_q = any(
                            kw in lower for kw in (
                                "score", "performance", "kpi", "target", "trend", "rank",
                                "waiting", "error", "booking", "attend", "rate",
                                "august", "september", "october", "november", "december",
                                "january", "february", "march", "april", "may", "june", "july",
                                "what was", "what is", "how did", "and in", "her ", "his "
                            )
                        )
                        if is_perf_q and (eff_emp_id or eff_emp_name):
                            period_for_tool = plan.periods[-1] if plan.periods else None
                            if not period_for_tool:
                                fallback_year = int(session_state.year or 2026)
                                for m_kw in MONTHS:
                                    if m_kw.casefold() in lower:
                                        period_for_tool = f"{fallback_year:04d}-{MONTHS[m_kw]:02d}"
                                        break
                            plan.model_led_tool_call = {
                                "tool_name": "read_employee_metric",
                                "tool_arguments": {
                                    "employee_id": eff_emp_id,
                                    "employee_name": eff_emp_name,
                                    "period": period_for_tool or eff_period or f"{int(session_state.year or 2026):04d}-09",
                                    "metric_id": eff_metric or "overall_score",
                                },
                            }
                            plan.intent = "current_value"
                            return RouterValidationResult(
                                outcome="answer",
                                plan=plan,
                                confirmed_context=confirmed_ctx,
                                route_used="model_led_pilot",
                                provider_metrics=provider_metrics,
                                headline="",
                                narrative_bullets=[],
                                suggested_followups=[],
                            )
                        provider_metrics.fallback_outcome = "invalid_response"
                        route_used = "local_rules"
                    elif model_output.get("response_type") == "unsupported":
                        return RouterValidationResult(
                            outcome="unsupported_request",
                            plan=StructuredQueryPlan(intent="unsupported", turn_kind_v2="unsupported"),
                            confirmed_context=confirmed_ctx,
                            route_used="model_led_pilot",
                            provider_metrics=provider_metrics,
                            headline="The available PMS reports do not provide the information needed to answer this question.",
                        )
                    elif model_output.get("response_type") == "clarification" and not scoped_overview:
                        question = model_output.get("clarification_prompt")
                        if isinstance(question, str) and question.strip():
                            focused_question = question.strip()[:300]
                            plan.turn_kind_v2 = "clarification"
                            plan.clarification_code = "AMBIGUOUS_KPI_SCOPE"
                            return RouterValidationResult(
                                outcome="clarification",
                                plan=plan,
                                confirmed_context=confirmed_ctx,
                                route_used="model_led_pilot",
                                provider_metrics=provider_metrics,
                                headline=focused_question,
                                clarification=AiClarificationPrompt(
                                    code=plan.clarification_code, question=focused_question, choices=[],
                                ),
                            )
                        provider_metrics.fallback_outcome = "invalid_response"
                        route_used = "local_rules"
                    elif model_output.get("response_type") == "clarification":
                        # The validated country and month are enough for an overall review.
                        route_used = "local_rules"
                    else:
                        provider_metrics.fallback_outcome = "invalid_response"
                        route_used = "local_rules"
            except Exception as e:
                # Preserve failure attribution when falling back to deterministic path
                if provider_metrics is None or provider_metrics.fallback_outcome in ("none", "", "not_called"):
                    provider_metrics = ProviderCallMetrics(
                        provider_used="none",
                        model_used="none",
                        provider_calls=max(1, getattr(provider_metrics, "provider_calls", 0) if provider_metrics else 0),
                        fallback_outcome="error",
                    )
                route_used = "local_rules"

            if needs_semantic_plan:
                return RouterValidationResult(
                    outcome="unavailable_data",
                    plan=StructuredQueryPlan(intent="clarify", turn_kind_v2="clarification"),
                    confirmed_context=prior or ConfirmedQueryContext(),
                    route_used="local_rules",
                    provider_metrics=provider_metrics,
                    headline="I couldn't verify a PMS lookup for this question. Please try again in a moment.",
                )

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
        if precomputed_intent is not None:
            provider_metrics = ProviderCallMetrics(
                provider_used=getattr(precomputed_intent, "provider", None) or "cloudflare",
                model_used=precomputed_intent.model or configured_model_name(),
                provider_calls=1,
                provider_ms=precomputed_intent.elapsed_ms,
                input_tokens=int(getattr(precomputed_intent, "input_tokens", 0) or 0),
                output_tokens=int(getattr(precomputed_intent, "output_tokens", 0) or 0),
                neurons=int(getattr(precomputed_intent, "neurons", 0) or 0),
                estimated_cost_usd=float(getattr(precomputed_intent, "estimated_cost_usd", 0.0) or 0.0),
                cost_status=getattr(precomputed_intent, "cost_status", "not_applicable"),
                fallback_outcome="none" if precomputed_intent.reason == "ok" else precomputed_intent.reason,
            )
            if precomputed_intent.intent in ("trend", "ranking", "score_drivers", "actual_vs_target") and plan.intent in ("current_value", "actual_vs_target"):
                plan.intent = precomputed_intent.intent  # type: ignore[assignment]
                plan.requested_parts = [precomputed_intent.intent]
                plan.operation_kind_v2 = precomputed_intent.intent
                route_used = "local_model_router"
        elif (
            not model_led_admin_active
            and provider_override == "auto"
            and local_intent_enabled()
            and matched_pattern is None
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
            local_result = call_suggest_intent(
                suggest_intent,
                text,
                context=bounded_context,
                user_id=str(self.scope.get("user_id") or "") or None,
                user_role=str(self.scope.get("role") or "") or None,
            )
            provider_metrics = ProviderCallMetrics(
                provider_used=getattr(local_result, "provider", None) or "cloudflare",
                model_used=local_result.model or configured_model_name(),
                provider_calls=1,
                provider_ms=local_result.elapsed_ms,
                input_tokens=int(getattr(local_result, "input_tokens", 0) or 0),
                output_tokens=int(getattr(local_result, "output_tokens", 0) or 0),
                neurons=int(getattr(local_result, "neurons", 0) or 0),
                estimated_cost_usd=float(getattr(local_result, "estimated_cost_usd", 0.0) or 0.0),
                cost_status=getattr(local_result, "cost_status", "not_applicable"),
                fallback_outcome="none" if local_result.reason == "ok" else local_result.reason,
            )
            if local_result.intent == "trend":
                plan.intent = "trend"
                plan.requested_parts = ["trend"]
                plan.operation_kind_v2 = "trend"
                route_used = "local_model_router"

        should_call_nvidia = provider_override != "deterministic" and (
            provider_override == "nvidia"
            or (cfg.router_mode == "shadow" and cfg.nvidia_routing_enabled)
            or (
                cfg.router_mode == "hybrid"
                and cfg.nvidia_routing_enabled
                and not has_explicit_local_action
                and cfg.is_scope_allowed_for_cloud(eff_team or eff_fn)
            )
        )
        if (should_call_nvidia and not plan.verified_comparison and not plan.verified_cohort_score and not ranked_action_request
            and not explicit_kpi_question_kind(text) and (turn_deadline is None or turn_deadline > perf_counter())):
            if is_prompt_safe_for_external_projection(text):
                eligible_team_names = [
                    t.value for t in self.catalog.get_eligible_scope_options(self.scope)["eligible_teams"]
                ]
                known_emp_names = [c.employee_name for c in self.employee_candidates if c.employee_name]
                provider_result = NvidiaStructuredRouterAdapter().propose_query_plan(
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
                    timeout=max(0.001, turn_deadline - perf_counter()) if turn_deadline else None,
                )
                provider_metrics = provider_result.metrics
                if provider_result.plan is not None:
                    shadow_plan = provider_result.plan.model_dump()
                    if provider_override == "nvidia" or cfg.router_mode == "hybrid":
                        route_used = "nvidia_router"
                        if provider_result.plan.intent:
                            cand_intent = provider_result.plan.intent
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
                        if provider_result.plan.requested_parts:
                            cleaned_parts = [
                                str(p).strip()
                                for p in provider_result.plan.requested_parts
                                if str(p).strip() in valid_parts
                            ]
                            if cleaned_parts:
                                plan.requested_parts = cleaned_parts[:2]
                        elif plan.intent and plan.requested_parts == [intent]:
                            plan.requested_parts = [plan.intent]
                        if provider_result.plan.team and not plan.team:
                            cand_team = provider_result.plan.team.strip()
                            if cand_team in self.catalog.teams or cand_team in eligible_team_names:
                                plan.team = cand_team
                                plan.function = function_for_team(cand_team) or plan.function
                        if provider_result.plan.position and not plan.position:
                            plan.position = provider_result.plan.position.strip()
                        if provider_result.plan.branch and not plan.branch:
                            cand_b = provider_result.plan.branch.strip().casefold()
                            if cand_b in BRANCH_KEYS and not (plan.team and cand_b in plan.team.casefold()):
                                plan.branch = cand_b
                        if provider_result.plan.compare_branch and not plan.compare_branch:
                            cand_cb = provider_result.plan.compare_branch.strip().casefold()
                            if cand_cb in BRANCH_KEYS:
                                plan.compare_branch = cand_cb
                        if provider_result.plan.metric and not plan.metric:
                            cand_m = self.catalog.find_metric_definition(
                                team=plan.team,
                                kpi_key_or_label=provider_result.plan.metric,
                                position=plan.position,
                                performance_level=plan.performance_level,
                            )
                            if cand_m is not None:
                                plan.metric = cand_m.metric_id
                            elif provider_result.plan.metric in self.catalog.metrics:
                                plan.metric = provider_result.plan.metric
                        if provider_result.plan.periods:
                            valid_periods = [
                                p
                                for p in provider_result.plan.periods[:6]
                                if re.match(r"^\d{4}-(0[1-9]|1[0-2])$", str(p))
                            ]
                            if valid_periods:
                                plan.periods = valid_periods
                                eff_periods = valid_periods
                        plan.single_person = bool(plan.single_person or provider_result.plan.single_person)
                        if provider_result.plan.ranking_direction in ("best", "worst"):
                            plan.ranking_direction = provider_result.plan.ranking_direction
                elif provider_override == "nvidia":
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
        has_any_available_period = any(not _is_period_unavailable(p) for p in eff_periods)
        if unavail_p is not None and not (
            compound_parts_enabled()
            and len(eff_periods) >= 2
            and has_any_available_period
        ):
            unavail_human = _format_period_label(unavail_p)
            latest_human = _format_period_label(self.latest_published_period)
            return RouterValidationResult(
                outcome="unavailable_data",
                plan=plan,
                confirmed_context=prior or ConfirmedQueryContext(),
                inherited_filters=inherited_filters,
                route_used=route_used,
                provider_metrics=provider_metrics,
                headline=(
                    f"No published PMS evaluation records are available for {plan.employee_name} in {unavail_human} ({unavail_p})."
                    if plan.employee_name
                    else f"No published PMS evaluation records are available for {unavail_human} ({unavail_p})."
                ),
                narrative_bullets=[
                    f"The latest published period with verified PMS data is {latest_human} ({self.latest_published_period})."
                ],
                suggested_followups=[
                    f"Show {plan.team or plan.function or 'overall'} performance in {latest_human}."
                ],
            )

        confirmed = ConfirmedQueryContext(
            intent=plan.intent,
            team=plan.team,
            function=plan.function,
            position=plan.position,
            branch=plan.branch,
            branches=plan.branches,
            region=eff_region,
            performance_level=plan.performance_level,
            metric_id="overall_score" if plan.verified_comparison else plan.metric,
            candidate_metrics=discussed_metrics,
            periods=plan.periods,
            comparison_teams=plan.comparison_teams,
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
            ranking_results=(
                list(prior_eff.ranking_results)
                if (
                    prior_eff is not None
                    and prior_eff.ranking_results
                    and plan.intent != "ranking"
                    and (plan.team or "").casefold() == (prior_eff.team or "").casefold()
                )
                else []
            ),
            prior_ranking_intent=bool(
                plan.intent == "ranking"
                or (
                    plan.intent != "trend"
                    and plan.employee_id is not None
                    and is_person_attribute_followup
                    and prior_eff is not None
                    and (prior_eff.intent == "ranking" or prior_eff.prior_ranking_intent)
                )
            ),
            score_measure=eff_score_measure,
        )

        return RouterValidationResult(
            outcome="answer",
            plan=plan,
            confirmed_context=confirmed,
            inherited_filters=inherited_filters,
            route_used=route_used,
            provider_metrics=provider_metrics,
            shadow_plan=shadow_plan,
            matched_pattern_id=matched_pattern.pattern_id if matched_pattern else None,
        )
