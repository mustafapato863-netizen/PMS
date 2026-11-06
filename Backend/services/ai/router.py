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
    user_can_access_branch,
    user_can_access_team,
)
from services.ai.classifier import LocalIntentClassifier
from services.ai.config import get_ai_runtime_config
from services.ai.domain_policies import BRANCH_ALIASES, MONTH_ALIASES
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
        "Pre-Approvals OP Dubai",
        ("pre-approvals op dubai", "pre approvals op dubai"),
    ),
    (
        "Pre-Approvals IP Final Dubai",
        ("pre-approvals ip final dubai", "pre approvals ip final dubai"),
    ),
    (
        "Pre-Approvals IP Elective Dubai",
        ("pre-approvals ip elective dubai", "pre approvals ip elective dubai"),
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
    ("Re-Submission", ("re-submission", "resubmission", "re submission")),
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
        ),
    ),
    ("Marketing", ("marketing", "ماركتنج", "التسويق")),
    ("Pharmacy", ("pharmacy",)),
    ("CSR", ("csr",)),
    ("Sales", ("sales",)),
    ("Finance", ("finance",)),
    ("Human Resources", ("human resources", "hr team")),
    ("IT", ("it team", "information technology")),
    ("Offshore Admin & Management", ("offshore admin & management", "offshore admin")),
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
    ("Pharmacy", "AJM Pharmacy Manager", ("ajm pharmacy manager",)),
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
    year_matches = [int(y) for y in re.findall(r"\b(202[4-9])\b", text_lower)]
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
    # Strip team names like "Pre-Approvals OP Dubai" before scanning branch aliases so "Dubai" inside a team name
    # is not mistaken for a branch filter unless separately specified.
    cleaned = text_lower
    if detected_team and "dubai" in detected_team.casefold():
        cleaned = cleaned.replace(detected_team.casefold(), " ")

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


class HybridQueryRouter:
    """Local-first query router and pre-read validator for PMS AI."""

    def __init__(
        self,
        *,
        scope: dict[str, Any],
        published_periods: Iterable[str] | None = None,
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

    def resolve_and_validate(
        self,
        *,
        prompt: str,
        session_state: SessionFilterContext,
        provider_override: str = "auto",
    ) -> RouterValidationResult:
        cfg = get_ai_runtime_config()
        text = (prompt or "").strip()
        lower = text.casefold()
        prior = session_state.last_confirmed_query

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
        teams_in_prompt = _detect_teams_in_prompt(lower)
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
        if "corporate" in lower:
            explicit_level = "Corporate"
        elif any(k in lower for k in ("managerial", "team sla", "attendance compliance")):
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
        is_short_followup = bool(
            prior
            and (
                lower.startswith("and ")
                or lower.startswith("what about ")
                or "compare it with" in lower
                or len(text.split()) <= 5
            )
        )

        eff_team = explicit_team
        if not eff_team and not asks_team_comparison:
            if is_short_followup and prior and prior.team:
                eff_team = prior.team
                inherited_filters.append("team")
            elif session_state.team and session_state.team not in ("All", "all"):
                eff_team = session_state.team

        eff_pos = detected_pos
        if not eff_pos:
            if is_short_followup and prior and prior.position:
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

        eff_branch = explicit_branch
        if not eff_branch and not asks_branch_comparison:
            if is_short_followup and prior and prior.branch:
                eff_branch = prior.branch
                inherited_filters.append("branch")
            elif (
                session_state.branch
                and session_state.branch.casefold() not in ("all", "")
                and not explicit_team
            ):
                # Note: only inherit session_state.branch if prompt didn't explicitly ask a global team question
                pass

        eff_level = explicit_level or (
            prior.performance_level
            if (is_short_followup and prior and prior.performance_level)
            else (
                session_state.performance_level
                if session_state.performance_level not in (None, "", "All", "all")
                else "Employee"
            )
        )

        eff_metric = _detect_metric_id(
            lower,
            team=eff_team,
            position=eff_pos,
            performance_level=eff_level,
        )
        if not eff_metric and is_short_followup and prior and prior.metric_id:
            # Inherit metric only if team did not switch to an incompatible team
            prior_metric_team = prior.metric_id.split(":")[0]
            if not eff_team or eff_team.casefold().startswith(prior_metric_team):
                eff_metric = prior.metric_id
                inherited_filters.append("metric")

        # Infer team from unambiguous Call Center metric if team not yet set
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

        # 4. Clarification Checks (Ambiguous Attendance, Ambiguous "Other" KPI, or Ambiguous Ranking Metric)
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
                clarification_code="AMBIGUOUS_ATTENDANCE_DEFINITION",
            )
            preserved_ctx = (
                prior.model_copy(update={"pending_clarification_code": "AMBIGUOUS_ATTENDANCE_DEFINITION"})
                if prior is not None
                else ConfirmedQueryContext(
                    intent="clarify",
                    function=eff_fn,
                    periods=eff_periods,
                    pending_clarification_code="AMBIGUOUS_ATTENDANCE_DEFINITION",
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
                clarification_code="AMBIGUOUS_ABANDON_METRIC",
            )
            preserved_other_ctx = (
                prior.model_copy(update={"pending_clarification_code": "AMBIGUOUS_ABANDON_METRIC"})
                if prior is not None
                else ConfirmedQueryContext(
                    intent="clarify",
                    function=eff_fn,
                    periods=eff_periods,
                    pending_clarification_code="AMBIGUOUS_ABANDON_METRIC",
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
            )

        if re.search(r"\b(?:new\s+joiners?|join(?:ed)?\b.*\brecently|hire\s+date|tenure)\b", lower):
            target_t = eff_team or "Inbound"
            latest_lbl = _format_period_label(eff_periods[-1] if eff_periods else self.latest_published_period)
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
            )

        # 5. Determine Intent
        emp_id_match = re.search(r"\b(sghd\d+|emp[-_ ]?\d+|e[-_]\d+)\b", lower)
        possessive_person_match = re.search(r"\b([a-z]+(?:\s+[a-z]+)?)'s\s+position\b", lower)
        asks_trend = any(
            w in lower
            for w in ("6-month", "trend", "trajectory", "progression", "over time", "multi-month", "history")
        )
        asks_ranking_person = bool(
            possessive_person_match
            or any(
                phrase in lower
                for phrase in (
                    "best agent",
                    "better agent",
                    "best inbound",
                    "best outbound",
                    "best support",
                    "#1 top performer",
                    "top performer",
                    "top inbound",
                    "top outbound",
                    "top support",
                    "lowest agent",
                    "lowest performer",
                    "lowest inbound",
                    "lowest outbound",
                    "lowest support",
                    "worst inbound",
                    "worst outbound",
                    "worst support",
                    "worst performing agent",
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
            for w in ("lowest", "worst", "bottom", "negative contributors", "caused")
        )
        asks_single_person = bool(
            emp_id_match
            or possessive_person_match
            or any(
                phrase in lower
                for phrase in (
                    "best agent",
                    "better agent",
                    "best inbound",
                    "best outbound",
                    "best support",
                    "#1 top performer",
                    "top performer",
                    "top inbound",
                    "top outbound",
                    "top support",
                    "lowest agent",
                    "lowest performer",
                    "lowest inbound",
                    "lowest outbound",
                    "lowest support",
                    "worst inbound",
                    "worst outbound",
                    "worst support",
                    "worst performing agent",
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
                performance_level=eff_level,
                periods=eff_periods,
                clarification_code="AMBIGUOUS_KPI_SCOPE",
            )
            preserved_rank_ctx = (
                prior.model_copy(update={"pending_clarification_code": "AMBIGUOUS_KPI_SCOPE"})
                if prior is not None
                else ConfirmedQueryContext(
                    intent="clarify",
                    team=eff_team,
                    function=eff_fn,
                    position=eff_pos,
                    branch=eff_branch,
                    performance_level=eff_level,
                    periods=eff_periods,
                    pending_clarification_code="AMBIGUOUS_KPI_SCOPE",
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
            )

        is_multi_part_trend_and_ranking = bool(
            asks_trend
            and asks_ranking_person
            and not re.search(r"\b(?:his|her|their|agent'?s)\s+(?:\d+-month\s+)?trend\b", lower)
        )

        intent: RouterIntentType = "current_value"
        if (
            is_short_followup
            and prior
            and prior.intent
            and prior.intent not in ("clarify", "unsupported")
            and "compare it with" not in lower
        ):
            intent = prior.intent
            if intent == "ranking" and not asks_ranking_person:
                asks_worst = prior.ranking_direction == "worst"
                asks_single_person = bool(prior.single_person)
            if "intent" not in inherited_filters:
                inherited_filters.append("intent")
        elif len(eff_periods) >= 2:
            intent = "compare_periods"
        elif asks_branch_comparison:
            intent = "compare_branches"
        elif asks_team_comparison:
            intent = "compare_teams"
        elif any(
            k in lower
            for k in ("corrective action", "corrective actions", "overdue corrective", "sip/pi")
        ):
            intent = "corrective_actions"
        elif (
            eff_level in ("Managerial", "Corporate")
            and not eff_metric
            and any(k in lower for k in ("balanced scorecard", "bsc", "scorecard"))
        ):
            intent = "scorecard_structure"
        elif asks_ranking_person:
            intent = "ranking"
        elif asks_trend and not asks_ranking_person:
            intent = "trend"
        elif any(
            phrase in lower
            for phrase in (
                "diagnose ",
                "score drivers",
                "kpi gaps",
                "drove the score gap",
                "why did ",
                "kpi bottlenecks",
            )
        ):
            intent = "score_drivers"
        elif eff_metric is not None or any(
            phrase in lower for phrase in ("vs target", "versus target", "against target", "meet its")
        ):
            intent = "actual_vs_target"
        else:
            intent = "current_value"

        requested_parts: list[str] = (
            ["trend", "ranking"] if is_multi_part_trend_and_ranking else [intent]
        )

        plan = StructuredQueryPlan(
            intent=intent,
            requested_parts=requested_parts,
            team=eff_team,
            function=eff_fn,
            position=eff_pos,
            branch=eff_branch,
            compare_branch=explicit_compare_branch,
            performance_level=eff_level,
            metric=eff_metric,
            periods=eff_periods,
            ranking_direction="worst" if asks_worst else "best",
            single_person=asks_single_person,
            employee_placeholder="[EMPLOYEE_ID]" if emp_id_match else None,
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
            unauthorized_team = next(
                (t for t in teams_to_check if not user_can_access_team(self.scope, t)),
                None,
            )
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

        route_used = "local_rules"
        provider_metrics = ProviderCallMetrics()
        shadow_plan: dict[str, Any] | None = None

        pre_cloud_rbac = _check_rbac()
        if pre_cloud_rbac is not None:
            return pre_cloud_rbac

        # Optional classifier & shadow/fallback Gemini call if forced or configured
        if cfg.classifier_mode in ("shadow", "enabled"):
            try:
                clf = LocalIntentClassifier.from_fixture_train_split(confidence_threshold=0.35)
                clf_pred = clf.predict(text)
                if cfg.classifier_mode == "enabled" and not clf_pred.abstain and intent == "current_value":
                    plan.intent = clf_pred.intent
                    route_used = "local_classifier"
            except Exception:
                pass

        has_explicit_local_action = bool(
            eff_metric is not None
            or intent != "current_value"
            or eff_pos is not None
            or is_short_followup
            or bool(inherited_filters)
            or any(
                kw in lower
                for kw in (
                    "score",
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
                )
                provider_metrics = gem_res.metrics
                if gem_res.plan is not None:
                    shadow_plan = gem_res.plan.model_dump()
                    if provider_override == "gemini" or cfg.router_mode == "hybrid":
                        route_used = "gemini_router"
                        if gem_res.plan.intent:
                            plan.intent = gem_res.plan.intent
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
                            if cand_b in BRANCH_KEYS:
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
            pending_clarification_code=None,
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
