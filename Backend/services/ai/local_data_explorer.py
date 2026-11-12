"""Opt-in, bounded AI data exploration loop over permission-scoped PMS tools.

Security & Architecture Invariants:
1. Opt-in only (`PMS_AI_EXPLORATION_ENABLED` or `PMS_AI_LOCAL_EXPLORATION_ENABLED`, disabled by default and in production).
2. All model calls go through the unified provider engine (Cloudflare Workers AI primary, Gemini fallback); `provider_used` is `cloudflare` or `gemini`.
3. Zero raw SQL, zero dynamic filter expressions, zero model-computed scores.
4. Strictly scoped concept catalog: the model only sees teams, functions, branches,
   performance levels, periods, and KPI definitions authorized for the caller's live RBAC scope.
5. Pre-execution & post-execution RBAC enforcement on every tool call (`0` unauthorized record reads).
6. Explicit unknown disclosures (`missing_hr_join_date`, `unsupported_compensation_data`,
   `call_center_revenue_not_tracked`, `unpublished_period`, `unverified_scope_calculation`,
   `missing_metric_evidence`) instead of guessing or fabricating data.
7. Bounded step count (`max_steps` 1..3, default 2) and bounded tool count (`max 2` per step,
   `max 3` total), with automatic deterministic fallback on timeout, provider unavailability, or invalid output.
"""

from __future__ import annotations

import json
import os
import re
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy.orm import Session

from config.database import release_read_transaction
from models.ai_schemas import (
    AiClarificationPrompt,
    AiToolCallRecord,
    ClarificationChoice,
    ConfirmedQueryContext,
    DeepLinkCta,
    EvidenceItemV2,
    QueryOperationV2,
    QueryScopeV2,
    SessionFilterContext,
    SourceCitationPill,
    StructuredQueryPlan,
    StructuredVisualCard,
    TurnOutcomeType,
    TypedMetricEvidence,
    ValidatedQueryPlanV2,
)
from models.report_schemas import MONTHS
from services.ai.catalog import (
    get_ai_catalog,
    user_can_access_branch,
    user_can_access_team,
)
from services.ai.contextual_assistant import is_self_only, normalize_team_name
from services.ai.conversation_service import AiConversationService
from services.ai.domain_policies import extract_prompt_signals
from services.ai.entity_resolver import (
    EmployeeHistoryCandidate,
    resolve_employee_from_candidates,
)
from services.ai.llm_client import (
    exploration_timeout_seconds,
    local_exploration_enabled,
    synthesis_timeout_seconds,
)
from services.ai.provider_engine import (
    ProviderMessage,
    ProviderRequest,
    get_unified_provider_engine,
)
from services.ai.providers import DeterministicLocalProviderAdapter
from services.ai.router import (
    UNAVAILABLE_FUTURE_PERIODS,
    _detect_branches_in_prompt,
    _detect_teams_in_prompt,
    _extract_person_query_from_prompt,
    _format_period_label,
)
from services.ai.tool_registry import (
    DeterministicToolRegistry,
    ToolExecutionContext,
    ToolExecutionResult,
)
from utils.branch_scope import BRANCH_KEYS
from utils.report_scope import function_for_team, user_can_access_team_level

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_last_exploration_provider: ContextVar[str] = ContextVar("last_exploration_provider", default="cloudflare")
_last_exploration_model: ContextVar[str] = ContextVar("last_exploration_model", default="")

# Reject any parameter value that resembles raw SQL, script injection, path traversal, or control chars
_UNSAFE_PARAM_RE = re.compile(
    r"(?:[\x00-\x08\x0b\x0c\x0e-\x1f]|[;<>`]|--|/\*|\*/|\.\./|\.\.\\|"
    r"\b(?:select|union|insert|update|delete|drop|alter|create|truncate|exec|execute|pragma|xp_|sp_|sleep|benchmark)\b|"
    r"\bor\s+1\s*=\s*1\b)",
    re.IGNORECASE,
)

DISCOVERY_EXPLORATION_TOOLS: frozenset[str] = frozenset(
    {
        "inspect_authorized_concepts",
        "find_concepts",
        "describe_metric",
        "list_available_periods",
    }
)

ALLOWED_EXPLORATION_TOOLS: frozenset[str] = frozenset(
    {
        *DISCOVERY_EXPLORATION_TOOLS,
        "get_team_score_summary",
        "get_kpi_diagnosis",
        "compare_branches",
        "compare_periods",
        "get_trend",
        "rank_employees",
        "get_employee_summary",
        "get_corrective_actions",
        "get_management_balanced_scorecard",
    }
)

ALLOWED_EXPLORATION_ACTIONS: frozenset[str] = frozenset(
    {
        "call_tools",
        "finish",
        "unknown",
    }
)

ALLOWED_UNKNOWN_CODES: frozenset[str] = frozenset(
    {
        "none",
        "missing_hr_join_date",
        "unsupported_compensation_data",
        "call_center_revenue_not_tracked",
        "unpublished_period",
        "unverified_scope_calculation",
        "missing_metric_evidence",
        "ambiguous_request",
    }
)

ALLOWED_TOOL_PARAM_KEYS: frozenset[str] = frozenset(
    {
        "tool",
        "team",
        "metric",
        "metric_id",
        "branch",
        "compare_branch",
        "period",
        "compare_period",
        "performance_level",
        "direction",
        "employee_query",
        "limit",
    }
)

REVERSE_MONTHS_BY_NUM: dict[int, str] = {v: k for k, v in MONTHS.items()}

_MONTH_ABBR_MAP: dict[str, int] = {
    **{k.casefold(): v for k, v in MONTHS.items()},
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _extract_explicit_periods_from_prompt(prompt: str, default_year: int = 2026) -> list[str]:
    """Extract all explicit period mentions (`YYYY-MM` or `<Month> <Year>`) from `prompt` in appearance order."""
    lower = (prompt or "").casefold()
    found: list[tuple[int, str]] = []

    for m in re.finditer(r"\b(20\d{2}|2100)-(0[1-9]|1[0-2])\b", lower):
        found.append((m.start(), f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"))

    month_names_pattern = "|".join(sorted(_MONTH_ABBR_MAP.keys(), key=len, reverse=True))
    for m in re.finditer(rf"\b({month_names_pattern})\b(?:\s+(20\d{{2}}|2100))?", lower):
        m_num = _MONTH_ABBR_MAP[m.group(1)]
        yr_str = m.group(2)
        if not yr_str:
            tail = lower[m.end() : m.end() + 32]
            yr_tail = re.search(r"\b(20\d{2}|2100)\b", tail)
            yr_val = int(yr_tail.group(1)) if yr_tail else default_year
        else:
            yr_val = int(yr_str)
        found.append((m.start(), f"{yr_val:04d}-{m_num:02d}"))

    found.sort(key=lambda item: item[0])
    deduped: list[str] = []
    for _, p_key in found:
        if p_key not in deduped:
            deduped.append(p_key)
    return deduped


def _extract_required_question_parts(prompt: str) -> list[str]:
    """Determine the required analytical question parts from the user prompt."""
    lower = (prompt or "").casefold()
    explicit_periods = _extract_explicit_periods_from_prompt(prompt)
    parts: list[str] = []

    asks_branch_cmp = bool(
        re.search(r"\b(?:which\s+branch|compare\s+branches|branch\s+comparison)\b", lower)
        or len(_detect_branches_in_prompt(lower, None)) >= 2
    )
    if asks_branch_cmp:
        parts.append("compare_branches")

    asks_period_cmp = bool(
        len(explicit_periods) >= 2
        and re.search(r"\b(?:compare|between|vs\.?|versus|change\s+from)\b", lower)
    )
    if asks_period_cmp:
        parts.append("compare_periods")

    asks_trend = bool(
        re.search(r"\b(?:trend|6-month|six\s+months|over\s+time|evolved|improved\s+over\s+time)\b", lower)
    )
    if asks_trend and "compare_periods" not in parts:
        parts.append("trend")

    asks_ranking = bool(
        re.search(
            r"\b(?:who\s+is\s+the\s+(?:lowest|worst|best|top|highest|weakest)|"
            r"who\s+(?:performed|was)\s+(?:best|worst|lowest|highest)|"
            r"(?:lowest|worst|best|top|highest|weakest)[- ](?:scoring\s+)?(?:person|performer|employee|agent|team\s+member)|"
            r"which\s+(?:[a-z]+\s+)?(?:employee|person|agent)\s+(?:has|had)\s+the\s+(?:lowest|highest|best|worst))\b",
            lower,
        )
    )
    if asks_ranking:
        parts.append("ranking")

    asks_kpi_diag = bool(
        re.search(
            r"\b(?:kpi\s+gap|kpi\s+gaps|bottleneck|score\s+driver|score\s+drivers|why\s+did\s+.*drop|"
            r"abandon\s+rate|attendance\s+rate|reachability|booking\s+rate|quality\s+score|no[- ]show\s+rate)\b",
            lower,
        )
    )
    if asks_kpi_diag and "compare_branches" not in parts:
        parts.append("kpi_diagnosis")

    asks_team_score = bool(
        re.search(r"\b(?:score|perform|performance|performing|percentage)\b", lower)
        and not asks_branch_cmp
        and not asks_period_cmp
    )
    if asks_team_score:
        # Only add a distinct "score" part when "score" is not solely describing the ranked person or trend
        if not asks_ranking and not asks_trend and not asks_kpi_diag:
            parts.append("score")
        elif asks_ranking and re.search(
            r"\b(?:what\s+is\s+(?:the\s+)?[a-z\s]+score\s+and\s+who|and\s+what\s+is\s+the\s+team\s+score)\b",
            lower,
        ):
            parts.insert(0, "score")

    if not parts:
        parts.append("score")
    return parts


@dataclass(frozen=True)
class ValidatedExplorationToolCall:
    tool: str
    team: str | None = None
    function: str | None = None
    position: str | None = None
    metric_id: str | None = None
    kpi_key: str | None = None
    branch: str | None = None
    compare_branch: str | None = None
    branches: tuple[str, ...] = ()
    period: str | None = None
    month: str | None = None
    year: int | None = None
    performance_level: str = "Employee"
    direction: str = "best"
    single_person: bool = False
    employee_query: str | None = None
    limit: int = 3


@dataclass
class ExplorationStepTrace:
    step: int
    action: str
    unknown_code: str
    requested_tools: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0
    status: str = "ok"


@dataclass
class LocalExplorationResult:
    handled: bool
    outcome: TurnOutcomeType = "answer"
    headline: str = ""
    narrative_bullets: list[str] = field(default_factory=list)
    visual_cards: list[StructuredVisualCard] = field(default_factory=list)
    citations: list[SourceCitationPill] = field(default_factory=list)
    deep_links: list[DeepLinkCta] = field(default_factory=list)
    primary_source_link: DeepLinkCta | None = None
    suggested_followups: list[str] = field(default_factory=list)
    clarification: AiClarificationPrompt | None = None
    structured_query: StructuredQueryPlan | None = None
    validated_plan_v2: ValidatedQueryPlanV2 | None = None
    typed_evidence: list[TypedMetricEvidence] = field(default_factory=list)
    evidence_envelope_v2: list[EvidenceItemV2] = field(default_factory=list)
    tool_calls: list[AiToolCallRecord] = field(default_factory=list)
    tool_digests: list[dict[str, Any]] = field(default_factory=list)
    resolved_session_state: SessionFilterContext | None = None
    basis_warning: str | None = None
    unknown_code: str = "none"
    steps_taken: int = 0
    step_traces: list[ExplorationStepTrace] = field(default_factory=list)
    provider_calls: int = 0
    provider_ms: float = 0.0
    planner_calls: int = 0
    planner_ms: float = 0.0
    synthesis_calls: int = 0
    synthesis_ms: float = 0.0
    synthesis_validated: bool = False
    synthesis_fallback_reason: str = "not_requested"
    database_ms: float = 0.0
    records_evaluated: int = 0
    fallback_reason: str = "none"
    provider_name: str = ""
    provider_used: str = ""
    model_name: str = ""

    def __post_init__(self) -> None:
        if not self.provider_name:
            if self.provider_calls > 0:
                self.provider_name = _last_exploration_provider.get()
            else:
                self.provider_name = "local"
        if not self.provider_used:
            if self.provider_calls > 0:
                self.provider_used = _last_exploration_provider.get()
            else:
                self.provider_used = "deterministic"
        if not self.model_name:
            if self.provider_calls > 0:
                self.model_name = _last_exploration_model.get()


def get_max_exploration_steps() -> int:
    try:
        raw = int(os.environ.get("PMS_AI_LOCAL_EXPLORATION_MAX_STEPS", "2"))
        return max(1, min(raw, 3))
    except (TypeError, ValueError):
        return 2


def build_exploration_step_json_schema() -> dict[str, object]:
    """Production-shaped JSON Schema for bounded local-model exploration steps.

    Matches the exact `{"action", "unknown_code", "tools"}` payload used by both
    live model exploration and unit test mocks.
    """
    return {
        "name": "pms_bounded_exploration_step",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": sorted(ALLOWED_EXPLORATION_ACTIONS),
                },
                "unknown_code": {
                    "type": "string",
                    "enum": sorted(ALLOWED_UNKNOWN_CODES),
                },
                "tools": {
                    "type": "array",
                    "maxItems": 2,
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool": {
                                "type": "string",
                                "enum": sorted(ALLOWED_EXPLORATION_TOOLS),
                            },
                            "team": {"type": "string"},
                            "period": {"type": "string"},
                            "compare_period": {"type": "string"},
                            "metric": {"type": "string"},
                            "metric_id": {"type": "string"},
                            "direction": {
                                "type": "string",
                                "enum": ["best", "worst"],
                            },
                            "branch": {"type": "string"},
                            "compare_branch": {"type": "string"},
                            "performance_level": {
                                "type": "string",
                                "enum": ["Employee", "Managerial", "Corporate"],
                            },
                            "employee_query": {"type": "string"},
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 5,
                            },
                        },
                        "required": ["tool"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["action", "unknown_code", "tools"],
            "additionalProperties": False,
        },
    }


def build_authorized_concept_summary(
    *,
    scope: dict[str, Any],
    session_state: SessionFilterContext,
    published_periods: Iterable[str] | None = None,
    employee_candidates: Iterable[EmployeeHistoryCandidate] | None = None,
) -> dict[str, Any]:
    """Project only the PMS concepts, teams, branches, levels, periods, and metrics permitted for `scope`.

    Never leaks unauthorized teams, branches, levels, or peer employee identities.
    """
    catalog = get_ai_catalog()
    eligible = catalog.get_eligible_scope_options(scope)
    raw_explicit_teams = [
        str(t).strip().casefold()
        for t in (scope.get("accessible_teams") or scope.get("allowed_teams") or [])
        if str(t).strip()
    ]
    authorized_teams = [
        item.value
        for item in eligible["eligible_teams"]
        if not raw_explicit_teams
        or scope.get("has_unrestricted_team_access")
        or item.value.casefold() in raw_explicit_teams
    ]
    authorized_teams_cf = {t.casefold() for t in authorized_teams}
    authorized_branches = list(eligible["eligible_branches"])
    authorized_levels = list(eligible["eligible_levels"])
    self_scoped = is_self_only(scope)
    caller_emp_id = str(scope.get("employee_id") or "").strip() or None

    cert_rows = [
        row
        for row in catalog.get_scope_certification_registry()
        if str(row.get("team") or "").casefold() in authorized_teams_cf
    ]
    def _scope_passes(row: dict[str, Any]) -> bool:
        return (
            row.get("passes") is True
            and row.get("certified") is True
            and row.get("evidence_state") in {"verified", "verified_no_data"}
        )

    certified_teams = [row["team"] for row in cert_rows if _scope_passes(row)]
    unverified_teams = [row["team"] for row in cert_rows if not _scope_passes(row)]

    active_team = session_state.team if session_state.team in authorized_teams else (
        authorized_teams[0] if len(authorized_teams) == 1 else None
    )
    metric_Filter_teams = (
        {active_team.casefold()}
        if active_team
        else ({t.casefold() for t in certified_teams} or authorized_teams_cf)
    )
    authorized_levels_cf = {lvl.casefold() for lvl in authorized_levels}

    compact_metrics: list[dict[str, Any]] = []
    for m in catalog.metrics.values():
        t_cf = m.team.casefold()
        if t_cf not in authorized_teams_cf and not (t_cf == "call center" and "support positions" in authorized_teams_cf):
            continue
        if t_cf not in metric_Filter_teams and len(compact_metrics) >= 16:
            continue
        if m.performance_level.casefold() not in authorized_levels_cf:
            continue
        compact_metrics.append(
            {
                "metric_id": m.metric_id,
                "label": m.display_name,
                "team": "Support Positions" if (t_cf == "call center" and m.position) else m.team,
                "level": m.performance_level,
                "unit": m.unit,
                "weight_pct": m.weight_percent,
                "tracking_only": not m.contributes_to_score,
            }
        )
        if len(compact_metrics) >= 24:
            break

    periods_sorted = sorted(
        {
            str(p).strip()
            for p in (published_periods or ["2026-08", "2026-09"])
            if re.match(r"^\d{4}-(0[1-9]|1[0-2])$", str(p).strip())
        }
    ) or ["2026-09"]

    allowed_tools = [
        t
        for t in sorted(ALLOWED_EXPLORATION_TOOLS)
        if not (self_scoped and t in {"rank_employees", "compare_branches"})
    ]

    return {
        "role": str(scope.get("role") or "Manager"),
        "is_self_only": self_scoped,
        "self_employee_id": caller_emp_id if self_scoped else None,
        "authorized_teams": authorized_teams,
        "certified_teams": certified_teams,
        "unverified_or_partial_teams": unverified_teams,
        "authorized_branches": authorized_branches,
        "authorized_levels": authorized_levels,
        "published_periods": periods_sorted,
        "latest_published_period": periods_sorted[-1],
        "authorized_metrics": compact_metrics,
        "allowed_tools": allowed_tools,
        "known_schema_unknowns": [
            "missing_hr_join_date: PMS does not store HR hire/joining dates or onboarding timestamps.",
            "unsupported_compensation_data: PMS does not store salaries, payroll, bonuses, or commissions.",
            "call_center_revenue_not_tracked: Call Center tracks Bookings, Attended Visits, and Calls rather than financial revenue.",
            "unpublished_period: Periods outside published_periods have no uploaded PMS records.",
            "unverified_scope_calculation: Teams in unverified_or_partial_teams without verified records cannot compute certified KPI scores.",
        ],
    }


def _is_safe_string_param(val: Any, *, max_len: int = 120) -> bool:
    if val is None:
        return True
    if not isinstance(val, str):
        return False
    cleaned = val.strip()
    if len(cleaned) > max_len:
        return False
    if _UNSAFE_PARAM_RE.search(cleaned):
        return False
    return True


def _parse_and_validate_step_payload(raw_content: str) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(raw_content, str) or not raw_content.strip():
        return None, "empty_content"
    cleaned = _JSON_FENCE_RE.sub("", raw_content.strip()).strip()
    try:
        parsed = json.loads(cleaned)
    except (ValueError, TypeError):
        return None, "invalid_json"
    if not isinstance(parsed, dict):
        return None, "not_an_object"
    keys = set(parsed.keys())
    if keys != {"action", "unknown_code", "tools"}:
        return None, "invalid_top_level_keys"
    action = parsed.get("action")
    unknown_code = parsed.get("unknown_code")
    tools = parsed.get("tools")
    if not isinstance(action, str) or action not in ALLOWED_EXPLORATION_ACTIONS:
        return None, "invalid_action"
    if not isinstance(unknown_code, str) or unknown_code not in ALLOWED_UNKNOWN_CODES:
        return None, "invalid_unknown_code"
    if not isinstance(tools, list) or len(tools) > 2:
        return None, "invalid_tools_list"
    for item in tools:
        if not isinstance(item, dict):
            return None, "tool_item_not_dict"
        extra = set(item.keys()) - ALLOWED_TOOL_PARAM_KEYS
        if extra or "tool" not in item:
            return None, "invalid_tool_keys"
        t_name = item.get("tool")
        if not isinstance(t_name, str) or t_name not in ALLOWED_EXPLORATION_TOOLS:
            return None, "unknown_tool_name"
        for str_key in (
            "team",
            "metric",
            "metric_id",
            "branch",
            "compare_branch",
            "period",
            "compare_period",
            "performance_level",
            "direction",
            "employee_query",
        ):
            if not _is_safe_string_param(item.get(str_key)):
                return None, f"unsafe_or_invalid_{str_key}"
        lim = item.get("limit")
        if lim is not None and (isinstance(lim, bool) or not isinstance(lim, int) or lim < 1 or lim > 5):
            return None, "invalid_limit"
    return parsed, "ok"


def _call_local_exploration_model(
    *,
    question: str,
    step: int,
    max_steps: int,
    active_context: dict[str, Any],
    authorized_concepts: dict[str, Any],
    collected_evidence: list[dict[str, Any]],
    required_parts: list[str] | None = None,
    missing_parts: list[str] | None = None,
) -> tuple[dict[str, Any] | None, float, str]:
    """Ask the configured model for one bounded exploration step. PMS executes the tools."""
    instruction = (
        'PMS AI Explorer. Never invent numbers. Return compact single-line JSON: '
        '{"action":"call_tools","unknown_code":"none","tools":[{"tool":"...","team":"...","period":"..."}]}. '
        "Omit unused optional keys.\n"
        "1. If question asks about unrecorded_unknowns (hire/join date/new joiner -> missing_hr_join_date; "
        "salary/bonus/payroll -> unsupported_compensation_data; Call Center revenue -> call_center_revenue_not_tracked; "
        "period not in published_periods -> unpublished_period), return action='unknown', that unknown_code, and tools=[].\n"
        "2. If collected_evidence already covers all required_parts (missing_parts is empty), return action='finish', unknown_code='none', tools=[].\n"
        "3. Otherwise return action='call_tools', unknown_code='none', and include 1 or 2 data tools in tools[] to cover missing_parts:\n"
        "- get_team_score_summary: overall team score/performance\n"
        "- get_kpi_diagnosis: KPI actual/target/gaps/bottleneck/score drivers\n"
        "- rank_employees: best/lowest/top/worst performers (set direction='worst' for lowest/worst/weakest, 'best' for best/top/highest)\n"
        "- compare_branches: compare branches (e.g. Dubai vs Sharjah bookings or score)\n"
        "- compare_periods: compare 2 periods (e.g. August vs September)\n"
        "- get_trend: multi-month score trend / evolved over time\n"
        "- get_employee_summary: specific named employee\n"
        "- get_corrective_actions: corrective action plan\n"
        "- get_management_balanced_scorecard: Corporate BSC scorecard\n"
        "- find_concepts / describe_metric / list_available_periods / inspect_authorized_concepts: metadata discovery only."
    )
    compact_evidence: list[dict[str, Any]] = []
    for ev in collected_evidence:
        t_name = str(ev.get("tool") or "")
        if t_name in DISCOVERY_EXPLORATION_TOOLS:
            summary_txt = "Metadata discovered; now call data tool(s) for missing_parts."
        elif t_name == "get_kpi_diagnosis":
            low = ev.get("lowest_kpi") or {}
            summary_txt = f"avg={ev.get('average_score')}; lowest_kpi={low.get('label')} ({low.get('achievement_pct')}%)"
        elif t_name in ("rank_employees", "get_employee_summary"):
            summary_txt = f"{ev.get('entity_name')} ({ev.get('entity_id')}) score={ev.get('score')}"
        else:
            summary_txt = f"scope={ev.get('scope')} avg={ev.get('average_score') or ev.get('score')}"
        compact_evidence.append(
            {
                "tool": t_name,
                "records": int(ev.get("records_evaluated") or ev.get("total_records") or 0),
                "summary": summary_txt[:96],
            }
        )
    user_payload = {
        "question": question.strip()[:240],
        "step": step,
        "max_steps": max_steps,
        "team": active_context.get("team")
        or (authorized_concepts["authorized_teams"][0] if authorized_concepts["authorized_teams"] else None),
        "period": active_context.get("period") or authorized_concepts["latest_published_period"],
        "published_periods": authorized_concepts["published_periods"][-4:],
        "required_parts": required_parts or ["score"],
        "missing_parts": missing_parts if missing_parts is not None else (required_parts or ["score"]),
        "collected_evidence": compact_evidence,
    }
    user_payload_str = json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))
    step_schema_wrap = build_exploration_step_json_schema()
    step_schema = step_schema_wrap.get("schema", step_schema_wrap)
    req = ProviderRequest(
        messages=[
            ProviderMessage(role="user", content=user_payload_str),
        ],
        system_instruction=instruction,
        response_format="json",
        json_schema=step_schema,
        temperature=0.0,
        max_tokens=140,
        timeout_seconds=exploration_timeout_seconds(),
        purpose="exploration",
    )
    engine = get_unified_provider_engine()
    resp = engine.generate(req)
    provider = resp.provider if resp.provider in ("cloudflare", "gemini") else "cloudflare"
    _last_exploration_provider.set(provider)
    _last_exploration_model.set(resp.model or provider)
    if not resp.is_success:
        reason = resp.outcome or "unavailable_or_invalid"
        return None, resp.latency_ms, reason
    parsed, status = _parse_and_validate_step_payload(resp.content or "")
    if parsed is None:
        return None, resp.latency_ms, status
    return parsed, resp.latency_ms, "ok"


def _build_unknown_response(
    *,
    unknown_code: str,
    team: str | None,
    function: str | None,
    period_key: str,
    latest_published_period: str,
    session_state: SessionFilterContext,
    step_traces: list[ExplorationStepTrace],
    provider_calls: int,
    provider_ms: float,
) -> LocalExplorationResult:
    target_team = team or session_state.team or None
    target_fn = function or session_state.function or (function_for_team(target_team) if target_team else None)
    latest_human = _format_period_label(latest_published_period)

    if unknown_code == "missing_hr_join_date":
        question = (
            "PMS tracks monthly evaluation scores and KPIs rather than employee hire or joining dates. "
            "Would you like to inspect their tracked evaluation history instead?"
        )
        disp_team = target_team or "your team"
        choices = [
            ClarificationChoice(
                id="choice-explore-history",
                label=f"Show tracked evaluation history in {disp_team}",
                prompt_to_send=f"Who is the best agent in {disp_team} in {latest_human}?",
                team=target_team,
                performance_level="Employee",
            )
        ]
        clar = AiClarificationPrompt(
            code="MISSING_HR_JOIN_DATE",
            question=question,
            choices=choices,
        )
        plan = StructuredQueryPlan(
            intent="clarify",
            team=target_team,
            function=target_fn,
            periods=[period_key],
            turn_kind_v2="clarification",
            operation_kind_v2="person_tenure_check",
            clarification_code="MISSING_HR_JOIN_DATE",
        )
        v2 = ValidatedQueryPlanV2(
            turn_kind="clarification",
            scope=QueryScopeV2(function=target_fn, team=target_team, periods=[period_key]),
            operations=[QueryOperationV2(operation_id="op_1", kind="person_tenure_check")],
            clarification_code="MISSING_HR_JOIN_DATE",
            resolution_source="local_model_router",
        )
        return LocalExplorationResult(
            handled=True,
            outcome="clarification",
            headline=question,
            narrative_bullets=[
                "Unknown in PMS schema: Employee onboarding/hire dates (`join_date`) are not stored in the PMS scorecard database."
            ],
            suggested_followups=[f"Who is the best agent in {target_team} in {latest_human}?"],
            clarification=clar,
            structured_query=plan,
            validated_plan_v2=v2,
            resolved_session_state=session_state,
            unknown_code=unknown_code,
            steps_taken=len(step_traces),
            step_traces=step_traces,
            provider_calls=provider_calls,
            provider_ms=provider_ms,
            planner_calls=provider_calls,
            planner_ms=provider_ms,
        )

    if unknown_code == "unsupported_compensation_data":
        headline = (
            "Compensation, salary, payroll, and bonus data are not tracked in the PMS performance database."
        )
        bullets = [
            "Unknown in PMS schema: PMS only records KPI actuals, targets, weights, evaluation scores, grades, and corrective actions.",
            f"You can inspect {target_team} KPI achievement, score drivers, or employee rankings for {latest_human}.",
        ]
        plan = StructuredQueryPlan(
            intent="unsupported",
            team=target_team,
            function=target_fn,
            periods=[period_key],
            turn_kind_v2="unsupported",
        )
        v2 = ValidatedQueryPlanV2(
            turn_kind="unsupported",
            scope=QueryScopeV2(function=target_fn, team=target_team, periods=[period_key]),
            operations=[QueryOperationV2(operation_id="op_1", kind="current_value")],
            resolution_source="local_model_router",
        )
        return LocalExplorationResult(
            handled=True,
            outcome="unsupported_request",
            headline=headline,
            narrative_bullets=bullets,
            suggested_followups=[f"Show {target_team} KPI score drivers in {latest_human}"],
            structured_query=plan,
            validated_plan_v2=v2,
            resolved_session_state=session_state,
            unknown_code=unknown_code,
            steps_taken=len(step_traces),
            step_traces=step_traces,
            provider_calls=provider_calls,
            provider_ms=provider_ms,
            planner_calls=provider_calls,
            planner_ms=provider_ms,
        )

    if unknown_code == "call_center_revenue_not_tracked":
        headline = (
            f"{target_team} (Call Center) measures operational patient volume (Bookings, Attended Visits, and Handled Calls) "
            "rather than financial revenue."
        )
        bullets = [
            "Unknown in Call Center schema: Financial revenue is tracked under Marketing and RCM rather than Call Center agent scorecards.",
            f"Ask for {target_team} Bookings (Count), Booking Rate, or Patient Attendance Rate in {latest_human}.",
        ]
        plan = StructuredQueryPlan(
            intent="current_value",
            team=target_team,
            function="Call Center",
            periods=[period_key],
            turn_kind_v2="clarification",
        )
        v2 = ValidatedQueryPlanV2(
            turn_kind="clarification",
            scope=QueryScopeV2(function="Call Center", team=target_team, periods=[period_key]),
            operations=[QueryOperationV2(operation_id="op_1", kind="current_value")],
            resolution_source="local_model_router",
        )
        return LocalExplorationResult(
            handled=True,
            outcome="unavailable_data",
            headline=headline,
            narrative_bullets=bullets,
            suggested_followups=[
                f"Compare Dubai and Sharjah {target_team} bookings in {latest_human}",
                f"What is {target_team} Patient Attendance Rate vs target in {latest_human}?",
            ],
            structured_query=plan,
            validated_plan_v2=v2,
            resolved_session_state=session_state,
            unknown_code=unknown_code,
            steps_taken=len(step_traces),
            step_traces=step_traces,
            provider_calls=provider_calls,
            provider_ms=provider_ms,
            planner_calls=provider_calls,
            planner_ms=provider_ms,
        )

    if unknown_code == "unpublished_period":
        period_human = _format_period_label(period_key)
        headline = f"No published PMS evaluation records are available for {period_human} (period {period_key})."
        bullets = [
            f"The latest published period with verified PMS data is {latest_human} ({latest_published_period})."
        ]
        plan = StructuredQueryPlan(
            intent="current_value",
            team=target_team,
            function=target_fn,
            periods=[period_key],
            turn_kind_v2="clarification",
            clarification_code="UNAVAILABLE_PERIOD_SUGGESTION",
        )
        v2 = ValidatedQueryPlanV2(
            turn_kind="clarification",
            scope=QueryScopeV2(function=target_fn, team=target_team, periods=[period_key]),
            operations=[QueryOperationV2(operation_id="op_1", kind="current_value")],
            clarification_code="UNAVAILABLE_PERIOD_SUGGESTION",
            resolution_source="local_model_router",
        )
        return LocalExplorationResult(
            handled=True,
            outcome="unavailable_data",
            headline=headline,
            narrative_bullets=bullets,
            suggested_followups=[f"What is {target_team} score in {latest_human}?"],
            structured_query=plan,
            validated_plan_v2=v2,
            resolved_session_state=session_state,
            unknown_code=unknown_code,
            steps_taken=len(step_traces),
            step_traces=step_traces,
            provider_calls=provider_calls,
            provider_ms=provider_ms,
            planner_calls=provider_calls,
            planner_ms=provider_ms,
        )

    if unknown_code == "unverified_scope_calculation":
        headline = (
            f"Verified AI evidence calculations are not yet certified for {target_team} in { _format_period_label(period_key) }."
        )
        bullets = [
            f"{target_team} does not have certified KPI calculation evidence for this query; PMS AI refuses to guess or fabricate unverified figures."
        ]
        plan = StructuredQueryPlan(
            intent="current_value",
            team=target_team,
            function=target_fn,
            periods=[period_key],
            turn_kind_v2="clarification",
        )
        v2 = ValidatedQueryPlanV2(
            turn_kind="clarification",
            scope=QueryScopeV2(function=target_fn, team=target_team, periods=[period_key]),
            operations=[QueryOperationV2(operation_id="op_1", kind="current_value")],
            resolution_source="local_model_router",
        )
        return LocalExplorationResult(
            handled=True,
            outcome="unavailable_data",
            headline=headline,
            narrative_bullets=bullets,
            suggested_followups=[f"What is Inbound score in {latest_human}?"],
            structured_query=plan,
            validated_plan_v2=v2,
            resolved_session_state=session_state,
            unknown_code=unknown_code,
            steps_taken=len(step_traces),
            step_traces=step_traces,
            provider_calls=provider_calls,
            provider_ms=provider_ms,
        )

    # Default missing_metric_evidence / ambiguous_request
    headline = (
        f"No verified PMS evaluation records matched the requested scope ({target_team} · {_format_period_label(period_key)})."
    )
    bullets = [
        "PMS AI only reports figures backed by published evaluation records within your authorized scope."
    ]
    plan = StructuredQueryPlan(
        intent="current_value",
        team=target_team,
        function=target_fn,
        periods=[period_key],
        turn_kind_v2="clarification",
    )
    v2 = ValidatedQueryPlanV2(
        turn_kind="clarification",
        scope=QueryScopeV2(function=target_fn, team=target_team, periods=[period_key]),
        operations=[QueryOperationV2(operation_id="op_1", kind="current_value")],
        resolution_source="local_model_router",
    )
    return LocalExplorationResult(
        handled=True,
        outcome="unavailable_data",
        headline=headline,
        narrative_bullets=bullets,
        suggested_followups=[f"Show performance summary for my authorized scope in {latest_human}"],
        structured_query=plan,
        validated_plan_v2=v2,
        resolved_session_state=session_state,
        unknown_code=unknown_code if unknown_code != "none" else "missing_metric_evidence",
        steps_taken=len(step_traces),
        step_traces=step_traces,
        provider_calls=provider_calls,
        provider_ms=provider_ms,
    )


def _validate_and_normalize_tool_call(
    *,
    raw_tool: dict[str, Any],
    prompt: str,
    scope: dict[str, Any],
    session_state: SessionFilterContext,
    published_periods: set[str],
    latest_published_period: str,
    employee_candidates: list[EmployeeHistoryCandidate],
) -> tuple[ValidatedExplorationToolCall | None, LocalExplorationResult | None, str]:
    """Validate one model-proposed tool call against RBAC scope, period availability, and catalog semantics.

    Returns (validated_call, early_termination_result, status_reason).
    If the tool call violates RBAC, returns an immediate `restricted_access` `LocalExplorationResult`
    before any database records are read.
    """
    catalog = get_ai_catalog()
    tool_name = str(raw_tool.get("tool") or "").strip()
    if tool_name not in ALLOWED_EXPLORATION_TOOLS:
        return None, None, "unknown_tool_name"

    lower_prompt = (prompt or "").casefold()
    explicit_teams = _detect_teams_in_prompt(lower_prompt)

    raw_team = raw_tool.get("team")
    norm_team = (
        normalize_team_name(raw_team)
        if isinstance(raw_team, str)
        and raw_team.strip()
        and raw_team.strip().casefold() not in ("none", "all", "all teams", "call center")
        else None
    )
    # Preserve unauthorized raw_team so RBAC check blocks it; otherwise bind explicit prompt team first
    if norm_team and not user_can_access_team(scope, norm_team):
        pass
    elif len(explicit_teams) == 1:
        norm_team = explicit_teams[0]
    elif not norm_team and session_state.team and session_state.team not in ("All", "all"):
        norm_team = normalize_team_name(session_state.team) or session_state.team
    elif not norm_team and session_state.last_confirmed_query and session_state.last_confirmed_query.team:
        norm_team = normalize_team_name(session_state.last_confirmed_query.team) or session_state.last_confirmed_query.team

    raw_level = raw_tool.get("performance_level")
    if isinstance(raw_level, str) and raw_level.strip() and raw_level.strip().casefold() != "none":
        lvl_clean = raw_level.strip().capitalize()
        if lvl_clean not in ("Employee", "Managerial", "Corporate"):
            return None, None, "invalid_performance_level"
        eff_level = lvl_clean
    elif re.search(r"\b(?:corporate|balanced\s+scorecard|bsc)\b", lower_prompt) or norm_team in ("CRM", "Nursing", "PMO"):
        eff_level = "Corporate"
    elif re.search(r"\bmanagerial\b", lower_prompt):
        eff_level = "Managerial"
    elif session_state.performance_level in ("Employee", "Managerial", "Corporate"):
        eff_level = str(session_state.performance_level)
    else:
        eff_level = "Employee"

    raw_branch = raw_tool.get("branch")
    eff_branch: str | None = None
    if isinstance(raw_branch, str) and raw_branch.strip() and raw_branch.strip().casefold() not in ("all", "all branches", "none"):
        b_cand = raw_branch.strip().casefold()
        if b_cand not in BRANCH_KEYS:
            return None, None, "invalid_branch"
        eff_branch = b_cand
    elif session_state.branch and session_state.branch.casefold() in BRANCH_KEYS:
        eff_branch = session_state.branch.casefold()

    raw_comp_branch = raw_tool.get("compare_branch")
    eff_comp_branch: str | None = None
    if isinstance(raw_comp_branch, str) and raw_comp_branch.strip() and raw_comp_branch.strip().casefold() not in ("all", "all branches", "none"):
        cb_cand = raw_comp_branch.strip().casefold()
        if cb_cand not in BRANCH_KEYS:
            return None, None, "invalid_compare_branch"
        eff_comp_branch = cb_cand

    prompt_branches = _detect_branches_in_prompt(lower_prompt, norm_team)
    if len(prompt_branches) >= 2 and tool_name in ("get_team_score_summary", "get_kpi_diagnosis", "compare_branches"):
        tool_name = "compare_branches"

    if tool_name == "compare_branches":
        branches_list = list(prompt_branches)
        for b_item in (eff_branch, eff_comp_branch):
            if b_item and b_item not in branches_list:
                branches_list.append(b_item)
        if not eff_branch and len(branches_list) >= 1:
            eff_branch = branches_list[0]
        if not eff_comp_branch and len(branches_list) >= 2:
            eff_comp_branch = branches_list[1]
    else:
        if len(prompt_branches) == 1 and not eff_branch:
            eff_branch = prompt_branches[0]
        branches_list = [eff_branch] if eff_branch else []

    # 1. Cross-Scope Isolation Check: Branches
    branches_to_verify = list(branches_list)
    if tool_name == "compare_branches" and len(branches_to_verify) < 2:
        branches_to_verify = list(BRANCH_KEYS)
    for b_check in branches_to_verify:
        if b_check and not user_can_access_branch(scope, b_check):
            allowed_b = sorted(
                str(b).capitalize()
                for b in (scope.get("accessible_branches") or scope.get("allowed_branches") or [])
            )
            allowed_str = ", ".join(allowed_b) if allowed_b else "your assigned branch"
            restr_plan = StructuredQueryPlan(
                intent="compare_branches" if tool_name == "compare_branches" else "current_value",
                team=norm_team,
                branch=b_check,
                branches=branches_to_verify,
                performance_level=eff_level,
            )
            return (
                None,
                LocalExplorationResult(
                    handled=True,
                    outcome="restricted_access",
                    headline=f"Access restricted: your role does not have permission to view {b_check.capitalize()} branch data.",
                    narrative_bullets=[
                        f"Your current access scope is restricted to {allowed_str}.",
                        "Local data exploration enforces branch isolation before reading any performance records.",
                    ],
                    suggested_followups=[
                        f"Show performance summary for {allowed_b[0]}" if allowed_b else "Show performance for my authorized scope"
                    ],
                    structured_query=restr_plan,
                    resolved_session_state=session_state,
                ),
                "restricted_branch",
            )

    # 2. Cross-Scope Isolation Check: Team & Performance Level
    if norm_team:
        if not user_can_access_team(scope, norm_team):
            allowed_fns = ", ".join(scope.get("accessible_functions") or []) or "your assigned teams"
            restr_plan = StructuredQueryPlan(
                intent="current_value",
                team=norm_team,
                performance_level=eff_level,
            )
            return (
                None,
                LocalExplorationResult(
                    handled=True,
                    outcome="restricted_access",
                    headline=f"Access restricted: your role does not have permission to view {norm_team} data.",
                    narrative_bullets=[
                        f"Your account is scoped to {allowed_fns}.",
                        "Local data exploration blocked an unauthorized team tool request with zero record reads.",
                    ],
                    suggested_followups=["Show performance summary for my authorized scope"],
                    structured_query=restr_plan,
                    resolved_session_state=session_state,
                ),
                "restricted_team",
            )
        if not user_can_access_team_level(scope, norm_team, eff_level):
            restr_plan = StructuredQueryPlan(
                intent="current_value",
                team=norm_team,
                performance_level=eff_level,
            )
            return (
                None,
                LocalExplorationResult(
                    handled=True,
                    outcome="restricted_access",
                    headline=f"Access restricted: your account does not have permission to view {norm_team} {eff_level} data.",
                    narrative_bullets=[
                        f"Your team assignment for {norm_team} does not include the {eff_level} performance level."
                    ],
                    suggested_followups=[f"Show Employee performance for {norm_team}"],
                    structured_query=restr_plan,
                    resolved_session_state=session_state,
                ),
                "restricted_team_level",
            )

    caller_role = str(scope.get("role") or "")
    self_scoped = is_self_only(scope)
    if eff_level in ("Corporate", "Managerial") and (self_scoped or caller_role in {"Agent", "Employee", "Executive", "Branch Director"}):
        restr_plan = StructuredQueryPlan(
            intent="current_value",
            team=norm_team,
            performance_level=eff_level,
        )
        return (
            None,
            LocalExplorationResult(
                handled=True,
                outcome="restricted_access",
                headline=f"Access restricted: your role does not have permission to view {eff_level} level data.",
                narrative_bullets=[f"Your current access scope does not include {eff_level} scorecards."],
                suggested_followups=["Show Employee performance for my authorized scope"],
                structured_query=restr_plan,
                resolved_session_state=session_state,
            ),
            "restricted_level",
        )

    # 3. Cross-Scope Isolation Check: Self-Only Employee Isolation
    raw_emp_q = raw_tool.get("employee_query")
    emp_query = (
        raw_emp_q.strip()
        if isinstance(raw_emp_q, str) and raw_emp_q.strip() and raw_emp_q.strip().casefold() != "none"
        else _extract_person_query_from_prompt(prompt)
    )
    if emp_query and norm_team and emp_query.casefold() == norm_team.casefold():
        emp_query = None
    caller_emp_id = str(scope.get("employee_id") or "").strip()

    if self_scoped:
        if tool_name == "rank_employees":
            return (
                None,
                LocalExplorationResult(
                    handled=True,
                    outcome="restricted_access",
                    headline="Access restricted: your role is restricted to viewing your own employee scorecard.",
                    narrative_bullets=["Self-scoped accounts cannot rank or view peer employees' evaluation records."],
                    suggested_followups=["Show my performance summary"],
                    structured_query=StructuredQueryPlan(intent="ranking", team=norm_team),
                    resolved_session_state=session_state,
                ),
                "restricted_self_only_ranking",
            )
        if emp_query and (not caller_emp_id or emp_query.casefold() != caller_emp_id.casefold()):
            return (
                None,
                LocalExplorationResult(
                    handled=True,
                    outcome="restricted_access",
                    headline="Access restricted: your role is restricted to viewing your own employee scorecard.",
                    narrative_bullets=["Self-scoped accounts cannot inspect another employee's evaluation record."],
                    suggested_followups=["Show my performance summary"],
                    structured_query=StructuredQueryPlan(intent="current_value", team=norm_team),
                    resolved_session_state=session_state,
                ),
                "restricted_self_only_employee",
            )
        if not emp_query and caller_emp_id:
            emp_query = caller_emp_id

    if emp_query and employee_candidates:
        emp_res = resolve_employee_from_candidates(
            emp_query,
            employee_candidates,
            team=norm_team,
            function=session_state.function,
            position=session_state.position,
        )
        if emp_res.status == "unique" and emp_res.selected is not None:
            if emp_res.selected.team and not user_can_access_team(scope, emp_res.selected.team):
                return (
                    None,
                    LocalExplorationResult(
                        handled=True,
                        outcome="restricted_access",
                        headline=f"Access restricted: your role does not have permission to view {emp_res.selected.team} employee data.",
                        narrative_bullets=["The requested employee belongs to a team outside your authorized scope."],
                        suggested_followups=["Show performance summary for my authorized scope"],
                        structured_query=StructuredQueryPlan(intent="current_value", team=emp_res.selected.team),
                        resolved_session_state=session_state,
                    ),
                    "restricted_employee_team",
                )
            emp_query = emp_res.selected.employee_id
            if not norm_team and emp_res.selected.team:
                norm_team = emp_res.selected.team

    # 4. Period Validation (bind explicit prompt periods ahead of session defaults)
    explicit_periods = _extract_explicit_periods_from_prompt(prompt, session_state.year or 2026)
    raw_period = raw_tool.get("period")
    eff_period_key = latest_published_period
    eff_month = session_state.month
    eff_year = session_state.year or 2026

    parsed_raw_period: str | None = None
    if isinstance(raw_period, str) and raw_period.strip() and raw_period.strip().casefold() != "none":
        rp = raw_period.strip()
        if re.match(r"^\d{4}-(0[1-9]|1[0-2])$", rp):
            parsed_raw_period = rp
        else:
            rp_extracted = _extract_explicit_periods_from_prompt(rp, session_state.year or 2026)
            if rp_extracted:
                parsed_raw_period = rp_extracted[0]

    # If the model explicitly requested an unpublished period, preserve it so we return unpublished_period
    if parsed_raw_period and published_periods and parsed_raw_period not in published_periods and (
        parsed_raw_period > latest_published_period or parsed_raw_period in UNAVAILABLE_FUTURE_PERIODS
    ):
        eff_period_key = parsed_raw_period
    elif explicit_periods:
        if len(explicit_periods) >= 2 and parsed_raw_period in explicit_periods:
            eff_period_key = parsed_raw_period
        else:
            eff_period_key = explicit_periods[-1]
    elif parsed_raw_period:
        eff_period_key = parsed_raw_period
    elif eff_month and eff_month in MONTHS:
        eff_period_key = f"{eff_year:04d}-{MONTHS[eff_month]:02d}"
    else:
        eff_period_key = latest_published_period

    yr_s, mo_s = eff_period_key.split("-", 1)
    eff_year = int(yr_s)
    eff_month = REVERSE_MONTHS_BY_NUM.get(int(mo_s), "September")

    if published_periods and eff_period_key not in published_periods and (
        eff_period_key > latest_published_period or eff_period_key in UNAVAILABLE_FUTURE_PERIODS
    ):
        return (
            None,
            _build_unknown_response(
                unknown_code="unpublished_period",
                team=norm_team,
                function=session_state.function,
                period_key=eff_period_key,
                latest_published_period=latest_published_period,
                session_state=session_state,
                step_traces=[],
                provider_calls=0,
                provider_ms=0.0,
            ),
            "unpublished_period",
        )

    # 5. Metric Validation & Explicit Metric Binding
    raw_metric = raw_tool.get("metric") or raw_tool.get("metric_id")
    resolved_metric_id: str | None = None
    resolved_kpi_key: str | None = None
    if isinstance(raw_metric, str) and raw_metric.strip() and raw_metric.strip().casefold() not in ("none", "all", "overall_score", "performance_level"):
        m_def = catalog.find_metric_definition(
            team=norm_team,
            kpi_key_or_label=raw_metric.strip(),
            position=session_state.position,
            performance_level=eff_level,
        )
        if m_def is not None:
            if m_def.team and m_def.team != "Call Center" and not user_can_access_team(scope, m_def.team):
                return (
                    None,
                    LocalExplorationResult(
                        handled=True,
                        outcome="restricted_access",
                        headline=f"Access restricted: your role does not have permission to view {m_def.team} metrics.",
                        narrative_bullets=["The requested metric belongs to a team outside your authorized scope."],
                        suggested_followups=["Show performance summary for my authorized scope"],
                        structured_query=StructuredQueryPlan(intent="actual_vs_target", team=m_def.team),
                        resolved_session_state=session_state,
                    ),
                    "restricted_metric_team",
                )
            resolved_metric_id = m_def.metric_id
            resolved_kpi_key = m_def.kpi_key or m_def.metric_id.split(":")[-1]
            if not norm_team and m_def.team and m_def.team != "Call Center":
                # NOTE (Task 2): only infer a team from the metric when the
                # label belongs to exactly one team. A shared Call Center
                # metric (Booking Rate is tracked by both Inbound and
                # Outbound) used to narrow the scope to whichever team the
                # catalog lists first, so a function-wide Clinics booking
                # question was answered with the Inbound-only count (20)
                # instead of the authorised function-wide count (30).
                # Ambiguous metrics leave the team unset (function scope),
                # matching the rules-only path.
                label_needle = raw_metric.strip().casefold()
                label_teams = {
                    cand.team
                    for cand in catalog.metrics.values()
                    if cand.team
                    and (
                        cand.kpi_key.casefold() == label_needle
                        or cand.display_name.casefold() == label_needle
                        or label_needle in cand.aliases
                        or cand.metric_id == label_needle
                    )
                }
                if len(label_teams) == 1:
                    norm_team = next(iter(label_teams))

    # NOTE (Task 2): a bookings question without rate language asks for the
    # authorised booking counter, whatever metric label the model supplied.
    # The old code only forced bookings_count for compare_branches, so a
    # single-branch Clinics booking question kept the model's "Booking Rate" and
    # was answered with an unrelated percentage. This override applies to
    # every tool and wins over a model-supplied rate label; explicit rate,
    # attendance, or trend wording is left alone.
    asks_booking_count = bool(re.search(r"\bbookings?\b", lower_prompt)) and not re.search(
        r"\b(?:rate|ratio|conversion|attendance|attended|percent|percentage|trend)\b", lower_prompt
    )
    if asks_booking_count:
        count_def = catalog.find_metric_definition(
            team=norm_team,
            kpi_key_or_label="bookings count",
            position=session_state.position,
            performance_level=eff_level,
        )
        resolved_metric_id = (
            count_def.metric_id
            if count_def is not None
            else f"{(norm_team or 'inbound').casefold().replace(' ', '_')}:bookings_count"
        )
        resolved_kpi_key = count_def.kpi_key if count_def is not None else "TotalBookings"
    elif not resolved_metric_id and norm_team:
        prompt_m_def = catalog.find_metric_definition(
            team=norm_team,
            kpi_key_or_label=prompt,
            position=session_state.position,
            performance_level=eff_level,
        )
        if prompt_m_def is not None and not prompt_m_def.metric_id.endswith(":overall_score"):
            resolved_metric_id = prompt_m_def.metric_id
            resolved_kpi_key = prompt_m_def.kpi_key or prompt_m_def.metric_id.split(":")[-1]

    req_parts = _extract_required_question_parts(prompt)
    if len(explicit_periods) >= 2 and "compare_periods" in req_parts and tool_name in (
        "get_team_score_summary",
        "get_kpi_diagnosis",
        "get_trend",
        "compare_periods",
    ):
        tool_name = "compare_periods"
    elif eff_level == "Corporate" and tool_name in ("get_team_score_summary", "get_kpi_diagnosis"):
        tool_name = "get_management_balanced_scorecard"
    elif req_parts == ["trend"] and tool_name in ("get_team_score_summary", "get_kpi_diagnosis"):
        tool_name = "get_trend"
    elif req_parts == ["score"] and eff_level != "Corporate" and tool_name == "get_trend":
        tool_name = "get_team_score_summary"
    elif req_parts == ["ranking"] and not self_scoped and tool_name in (
        "get_team_score_summary",
        "get_kpi_diagnosis",
        "get_employee_summary",
    ):
        if tool_name != "get_employee_summary" or not emp_query:
            tool_name = "rank_employees"
    elif req_parts == ["kpi_diagnosis"] and resolved_metric_id and tool_name == "get_team_score_summary":
        tool_name = "get_kpi_diagnosis"

    eff_fn = (
        function_for_team(norm_team)
        if norm_team
        else (session_state.function or None)
    )
    direction_raw = str(raw_tool.get("direction") or "").strip().casefold()
    if any(w in lower_prompt for w in ("worst", "lowest", "bottom", "weakest")):
        direction_raw = "worst"
    elif any(w in lower_prompt for w in ("best", "highest", "top", "strongest")):
        direction_raw = "best"
    elif direction_raw not in ("best", "worst"):
        direction_raw = "best"

    single_person = bool(
        tool_name == "get_employee_summary"
        or emp_query
        or any(
            phrase in lower_prompt
            for phrase in (
                "who is the best",
                "who is the lowest",
                "who is the worst",
                "who performed best",
                "who performed worst",
                "who was the best",
                "who was the lowest",
                "best agent",
                "lowest agent",
                "top performer",
                "lowest performer",
                "lowest person",
                "lowest employee",
                "weakest",
                "highest",
            )
        )
    )
    limit_val = int(raw_tool.get("limit") or (1 if single_person else 3))

    return (
        ValidatedExplorationToolCall(
            tool=tool_name,
            team=norm_team,
            function=eff_fn,
            position=session_state.position,
            metric_id=resolved_metric_id,
            kpi_key=resolved_kpi_key,
            branch=eff_branch,
            compare_branch=eff_comp_branch,
            branches=tuple(branches_list),
            period=eff_period_key,
            month=eff_month,
            year=eff_year,
            performance_level=eff_level,
            direction=direction_raw,
            single_person=single_person,
            employee_query=emp_query,
            limit=limit_val,
        ),
        None,
        "ok",
    )


def _execute_validated_exploration_tool(
    *,
    call: ValidatedExplorationToolCall,
    registry: DeterministicToolRegistry,
    authorized_concepts: dict[str, Any],
) -> tuple[ToolExecutionResult, dict[str, Any]]:
    """Execute one validated exploration tool via `DeterministicToolRegistry` and return a compact digest for the model."""
    if call.tool in DISCOVERY_EXPLORATION_TOOLS:
        res = ToolExecutionResult(
            tool_name=call.tool,
            arguments={"team": call.team, "function": call.function, "metric": call.metric_id},
            records_evaluated=0,
            digest={
                "authorized_teams": authorized_concepts["authorized_teams"],
                "certified_teams": authorized_concepts["certified_teams"],
                "authorized_branches": authorized_concepts["authorized_branches"],
                "authorized_levels": authorized_concepts["authorized_levels"],
                "published_periods": authorized_concepts["published_periods"],
                "authorized_metrics": authorized_concepts["authorized_metrics"][:12],
            },
            resolved_month=call.month,
            resolved_year=call.year,
        )
        return res, {"tool": call.tool, **res.digest}

    if call.tool == "get_management_balanced_scorecard":
        res = registry.execute_management_balanced_scorecard(
            team=call.team,
            function=call.function,
            performance_level=call.performance_level,
            month=call.month,
            year=call.year,
        )
        compact = {
            "tool": call.tool,
            "scope": res.digest.get("scope"),
            "period": res.digest.get("period"),
            "average_score": res.digest.get("average_score"),
            "total_records": res.digest.get("total_records"),
            "records_evaluated": res.records_evaluated,
        }
        return res, compact

    if call.tool == "get_team_score_summary":
        res = registry.execute_executive_and_priority_insights(
            team=call.team,
            function=call.function,
            position=call.position,
            branch=call.branch,
            performance_level=call.performance_level,
            month=call.month,
            year=call.year,
        )
        compact = {
            "tool": call.tool,
            "scope": res.digest.get("scope"),
            "period": res.digest.get("period"),
            "branch": res.digest.get("branch"),
            "average_score": res.digest.get("average_score"),
            "total_records": res.digest.get("total_records"),
            "employees_below_target": res.digest.get("employees_below_target"),
            "primary_driver": res.digest.get("primary_driver"),
        }
        return res, compact

    if call.tool == "compare_periods":
        res = registry.execute_kpi_diagnosis_and_trends(
            team=call.team,
            function=call.function,
            position=call.position,
            branch=call.branch,
            asks_period_comparison=True,
            performance_level=call.performance_level,
            kpi=call.kpi_key,
            month=call.month,
            year=call.year,
        )
        compact = {
            "tool": call.tool,
            "scope": res.digest.get("scope"),
            "period": res.digest.get("period"),
            "period_comparison": res.digest.get("period_comparison"),
            "records_evaluated": res.records_evaluated,
        }
        return res, compact

    if call.tool == "compare_branches":
        res = registry.execute_kpi_diagnosis_and_trends(
            team=call.team,
            function=call.function,
            position=call.position,
            branch=call.branch,
            compare_branch=call.compare_branch,
            branches=list(call.branches),
            asks_branch_comparison=True,
            performance_level=call.performance_level,
            kpi=call.kpi_key,
            month=call.month,
            year=call.year,
        )
        compact = {
            "tool": call.tool,
            "scope": res.digest.get("scope"),
            "period": res.digest.get("period"),
            "branch_comparison": res.digest.get("branch_comparison") or [],
            "records_evaluated": res.records_evaluated,
        }
        return res, compact

    if call.tool == "get_trend":
        res = registry.execute_team_trend_spotlight(
            team=call.team,
            function=call.function,
            position=call.position,
            branch=call.branch,
            month=call.month,
            year=call.year,
            kpi=call.kpi_key,
        )
        tt = res.digest.get("team_trend_spotlight") or res.digest.get("spotlight") or {}
        compact = {
            "tool": call.tool,
            "scope": tt.get("team") or res.digest.get("scope"),
            "period": res.digest.get("period"),
            "metric_label": tt.get("metric_label"),
            "score": tt.get("score"),
            "six_month_delta": tt.get("six_month_delta"),
            "records_evaluated": res.records_evaluated,
        }
        return res, compact

    if call.tool in ("rank_employees", "get_employee_summary"):
        res = registry.execute_agent_spotlight_and_trend(
            team=call.team,
            function=call.function,
            position=call.position,
            branch=call.branch,
            month=call.month,
            year=call.year,
            kpi=call.kpi_key,
            employee_query=call.employee_query if call.tool == "get_employee_summary" else None,
            ranking_direction="worst" if call.direction == "worst" else "best",
            single_person=True if call.tool == "get_employee_summary" else call.single_person,
        )
        sp = res.digest.get("spotlight") or res.digest.get("agent_spotlight") or {}
        compact = {
            "tool": call.tool,
            "entity_id": sp.get("entity_id"),
            "entity_name": sp.get("entity_name"),
            "team": sp.get("team"),
            "period": res.digest.get("period"),
            "score": sp.get("score"),
            "grade": sp.get("grade"),
            "rank": sp.get("rank"),
            "total_in_team": sp.get("total_in_team"),
            "ranking_direction": sp.get("ranking_direction"),
            "ranking_metric_label": sp.get("ranking_metric_label"),
            "records_evaluated": res.records_evaluated,
        }
        return res, compact

    if call.tool == "get_corrective_actions":
        res = registry.execute_corrective_actions_status(
            team=call.team,
            month=call.month,
            year=call.year,
        )
        compact = {
            "tool": call.tool,
            "scope": res.digest.get("scope"),
            "total_actions": res.digest.get("total_actions", 0),
            "records_evaluated": res.records_evaluated,
        }
        return res, compact

    # Default: get_kpi_diagnosis
    res = registry.execute_kpi_diagnosis_and_trends(
        team=call.team,
        function=call.function,
        position=call.position,
        branch=call.branch,
        performance_level=call.performance_level,
        kpi=call.kpi_key,
        month=call.month,
        year=call.year,
    )
    low_kpi = res.digest.get("lowest_kpi") or {}
    req_kpi = res.digest.get("requested_kpi") or {}
    compact = {
        "tool": "get_kpi_diagnosis",
        "scope": res.digest.get("scope"),
        "period": res.digest.get("period"),
        "branch": res.digest.get("branch"),
        "average_score": res.digest.get("average_score"),
        "total_records": res.digest.get("total_records"),
        "lowest_kpi": {
            "label": low_kpi.get("kpi_label"),
            "actual": low_kpi.get("actual_display"),
            "target": low_kpi.get("target_display"),
            "achievement_pct": low_kpi.get("achievement_percent"),
            "people_below_target": low_kpi.get("people_below_target"),
        }
        if low_kpi
        else None,
        "requested_kpi": {
            "label": req_kpi.get("kpi_label"),
            "actual": req_kpi.get("actual_display"),
            "target": req_kpi.get("target_display"),
            "achievement_pct": req_kpi.get("achievement_percent"),
            "contributes_to_score": req_kpi.get("contributes_to_score"),
        }
        if req_kpi
        else None,
        "records_evaluated": res.records_evaluated,
    }
    return res, compact


def _build_evidence_items_from_results(
    *,
    executed_calls: list[ValidatedExplorationToolCall],
    tool_results: list[ToolExecutionResult],
) -> list[EvidenceItemV2]:
    """Build EvidenceItemV2 envelopes covering every executed exploration tool."""
    catalog = get_ai_catalog()
    envelope: list[EvidenceItemV2] = []

    for idx, (call, tr) in enumerate(zip(executed_calls, tool_results), start=1):
        op_id = f"op_{idx}"
        perf_lvl = call.performance_level if call.performance_level in ("Employee", "Managerial", "Corporate") else "Employee"
        scope_v2 = QueryScopeV2(
            function=call.function or (function_for_team(call.team) if call.team else None),
            team=call.team,
            position=call.position,
            performance_level=perf_lvl,  # type: ignore[arg-type]
            branches=list(call.branches) if call.branches else ([call.branch] if call.branch else []),
            periods=[call.period] if call.period else [],
            employee_id=call.employee_query if call.tool == "get_employee_summary" else None,
        )
        src_cta = tr.deep_links[0] if tr.deep_links else None

        if tr.typed_evidence:
            ev = tr.typed_evidence[0]
            cat_def = catalog.find_metric_definition(
                team=ev.team,
                kpi_key_or_label=ev.metric_id,
                performance_level=ev.performance_level,
            )
            val_kind = getattr(cat_def, "value_kind", None) or ("rate" if ev.unit == "%" else "score")
            envelope.append(
                EvidenceItemV2(
                    operation_id=op_id,
                    outcome="ok" if tr.records_evaluated > 0 else "empty",
                    scope=scope_v2,
                    metric_id=ev.metric_id,
                    metric_display_name=ev.display_name,
                    value_kind=str(val_kind),
                    unit=ev.unit,
                    headline_value=ev.actual,
                    headline_display=ev.actual_display,
                    target_value=ev.target,
                    target_display=ev.target_display,
                    achievement_percent=ev.achievement_percent,
                    weight_percent=ev.weight_percent,
                    contributes_to_score=ev.contributes_to_score,
                    record_count=max(ev.sample_size, tr.records_evaluated),
                    source_link=src_cta,
                )
            )
            continue

        sp = tr.digest.get("spotlight") or tr.digest.get("agent_spotlight")
        if isinstance(sp, dict) and sp.get("entity_id"):
            emp_team = str(sp.get("team") or call.team or "")
            envelope.append(
                EvidenceItemV2(
                    operation_id=op_id,
                    outcome="ok",
                    scope=scope_v2.model_copy(update={"team": emp_team, "employee_id": str(sp.get("entity_id"))}),
                    metric_id=call.metric_id or f"{emp_team.casefold().replace(' ', '_')}:overall_score",
                    metric_display_name=str(sp.get("ranking_metric_label") or "Overall PMS Score"),
                    value_kind="score",
                    unit="%",
                    headline_value=float(sp.get("score") or 0.0),
                    headline_display=f"{float(sp.get('score') or 0.0):.1f}%",
                    target_value=100.0,
                    target_display="100.0%",
                    rows=list(sp.get("all_history") or []),
                    ties=[str(t) for t in (sp.get("ties") or [])],
                    record_count=int(sp.get("total_in_team") or tr.records_evaluated or 1),
                    source_link=src_cta,
                )
            )
            continue

        tt = tr.digest.get("team_trend_spotlight")
        if isinstance(tt, dict):
            t_team = str(tt.get("team") or call.team or "Inbound")
            sc_val = float(tt.get("score") or 0.0)
            envelope.append(
                EvidenceItemV2(
                    operation_id=op_id,
                    outcome="ok" if tr.records_evaluated > 0 else "empty",
                    scope=scope_v2,
                    metric_id=call.metric_id or f"{t_team.casefold().replace(' ', '_')}:overall_score",
                    metric_display_name=str(tt.get("metric_label") or "Overall Score"),
                    value_kind="score",
                    unit="%",
                    headline_value=sc_val,
                    headline_display=f"{sc_val:.1f}%",
                    target_value=100.0,
                    target_display="100.0%",
                    record_count=tr.records_evaluated,
                    source_link=src_cta,
                )
            )
            continue

        avg_sc = tr.digest.get("average_score")
        envelope.append(
            EvidenceItemV2(
                operation_id=op_id,
                outcome="ok" if tr.records_evaluated > 0 else "empty",
                scope=scope_v2,
                metric_id=call.metric_id or f"{(call.team or 'call_center').casefold().replace(' ', '_')}:overall_score",
                metric_display_name="Overall Weighted PMS Score",
                value_kind="score",
                unit="%",
                headline_value=round(float(avg_sc), 1) if isinstance(avg_sc, (int, float)) else None,
                headline_display=f"{float(avg_sc):.1f}%" if isinstance(avg_sc, (int, float)) else None,
                target_value=100.0,
                target_display="100.0%",
                record_count=tr.records_evaluated,
                source_link=src_cta,
            )
        )

    return envelope


def _synthesize_explored_evidence(
    *,
    prompt: str,
    session_state: SessionFilterContext,
    executed_calls: list[ValidatedExplorationToolCall],
    tool_results: list[ToolExecutionResult],
) -> tuple[str, list[str], list[str]]:
    """Synthesize a deterministic, zero-hallucination answer across 1 or more explored evidence items."""
    if executed_calls and all(c.tool in DISCOVERY_EXPLORATION_TOOLS for c in executed_calls):
        d = tool_results[0].digest if tool_results else {}
        teams = ", ".join(d.get("authorized_teams") or []) or "None"
        branches = ", ".join(d.get("authorized_branches") or []) or "All authorized branches"
        periods = ", ".join(d.get("published_periods") or []) or "Latest period"
        headline = f"Your authorized PMS scope covers teams ({teams}) across periods ({periods})."
        bullets = [
            f"Authorized branches: {branches}.",
            f"Authorized performance levels: {', '.join(d.get('authorized_levels') or ['Employee'])}.",
        ]
        t0 = (d.get("authorized_teams") or ["Inbound"])[0]
        return headline, bullets, [f"Show {t0} KPI score drivers", f"Who is the best agent in {t0}?"]

    data_pairs = [
        (c, tr)
        for c, tr in zip(executed_calls, tool_results)
        if c.tool not in DISCOVERY_EXPLORATION_TOOLS
    ]
    if not data_pairs:
        data_pairs = list(zip(executed_calls, tool_results))
    data_calls = [c for c, _ in data_pairs]
    data_results = [tr for _, tr in data_pairs]

    adapter = DeterministicLocalProviderAdapter()
    base_signals = extract_prompt_signals(prompt, session_state)
    if data_calls:
        first_c = data_calls[0]
        if first_c.team:
            base_signals.detected_team = first_c.team
        if first_c.branch:
            base_signals.detected_branch = first_c.branch
        if first_c.kpi_key:
            base_signals.detected_kpi = first_c.kpi_key
        if any(c.tool == "compare_branches" for c in data_calls):
            base_signals.asks_branch_comparison = True
        if any(c.tool == "compare_periods" for c in data_calls):
            base_signals.asks_period_comparison = True
        if any(c.direction == "worst" for c in data_calls):
            base_signals.asks_worst_agent = True

    digests = [tr.digest for tr in data_results if tr.digest]
    combined = adapter.synthesize(
        prompt=prompt,
        signals=base_signals,
        tool_digests=digests,
        guardrail_notes=[],
    )
    headline = combined.headline
    bullets = list(combined.narrative_bullets)

    # When 2 distinct data tools were executed (e.g. get_team_score_summary + rank_employees, or get_trend + rank_employees),
    # ensure both parts of the multi-part evidence are explicitly represented in the headline and bullets.
    if len(data_results) >= 2:
        part_headlines: list[str] = []
        for call, tr in zip(data_calls, data_results):
            part_sig = extract_prompt_signals(prompt, session_state)
            if call.team:
                part_sig.detected_team = call.team
            if call.branch:
                part_sig.detected_branch = call.branch
            if call.kpi_key:
                part_sig.detected_kpi = call.kpi_key
            part_sig.asks_branch_comparison = call.tool == "compare_branches"
            part_sig.asks_period_comparison = call.tool == "compare_periods"
            part_sig.asks_worst_agent = call.direction == "worst"
            if call.tool in (
                "get_team_score_summary",
                "get_kpi_diagnosis",
                "compare_branches",
                "compare_periods",
                "get_management_balanced_scorecard",
            ):
                part_sig.asks_agent_ranking = False
                part_sig.asks_team_trend = False
            elif call.tool in ("rank_employees", "get_employee_summary"):
                part_sig.asks_agent_ranking = True
            elif call.tool == "get_trend":
                part_sig.asks_team_trend = True
                part_sig.asks_agent_ranking = False
            part_syn = adapter.synthesize(
                prompt=prompt,
                signals=part_sig,
                tool_digests=[tr.digest],
                guardrail_notes=[],
            )
            if part_syn.headline and part_syn.headline not in part_headlines:
                part_headlines.append(part_syn.headline)
            for b in part_syn.narrative_bullets:
                if b not in bullets:
                    bullets.append(b)
        if len(part_headlines) >= 2:
            headline = f"{part_headlines[0]} {part_headlines[1]}"

    return headline, bullets[:4], combined.suggested_followups


def build_fact_ledger_from_evidence(
    *,
    executed_calls: list[ValidatedExplorationToolCall],
    tool_results: list[ToolExecutionResult],
    default_headline: str,
) -> list[dict[str, Any]]:
    """Build a verifiable fact ledger with `fact_id` handles from executed PMS tool results."""
    ledger: list[dict[str, Any]] = []
    fact_idx = 1
    for call, tr in zip(executed_calls, tool_results):
        if call.tool in DISCOVERY_EXPLORATION_TOOLS:
            continue
        d = tr.digest or {}
        if call.tool in ("rank_employees", "get_employee_summary"):
            sp = d.get("spotlight") or d.get("agent_spotlight") or {}
            if sp.get("entity_name"):
                sc = round(float(sp.get("score") or 0.0), 1)
                ledger.append(
                    {
                        "fact_id": f"F{fact_idx}",
                        "part": "ranking",
                        "subject": str(sp.get("entity_name")),
                        "employee_id": str(sp.get("entity_id") or ""),
                        "team": str(sp.get("team") or call.team or ""),
                        "period": str(d.get("period") or call.period or ""),
                        "direction": str(call.direction),
                        "value": sc,
                        "display": f"{sc:.1f}%",
                        "unit": "%",
                    }
                )
                fact_idx += 1
                continue
        if call.tool == "compare_branches":
            bc = d.get("branch_comparison") or []
            req_branches_cf = {b.casefold() for b in call.branches if b}
            if isinstance(bc, list) and bc:
                for b_row in bc:
                    if isinstance(b_row, dict) and b_row.get("branch"):
                        b_name = str(b_row.get("branch"))
                        if req_branches_cf and b_name.casefold() not in req_branches_cf:
                            continue
                        b_val = b_row.get("bookings") if call.kpi_key == "TotalBookings" else b_row.get("average_score")
                        if isinstance(b_val, (int, float)):
                            ledger.append(
                                {
                                    "fact_id": f"F{fact_idx}",
                                    "part": "compare_branches",
                                    "subject": b_name,
                                    "team": str(d.get("scope") or call.team or ""),
                                    "period": str(d.get("period") or call.period or ""),
                                    "value": int(b_val) if call.kpi_key == "TotalBookings" else round(float(b_val), 1),
                                    "display": str(int(b_val)) if call.kpi_key == "TotalBookings" else f"{float(b_val):.1f}%",
                                    "unit": "count" if call.kpi_key == "TotalBookings" else "%",
                                }
                            )
                            fact_idx += 1
                continue
        if call.tool == "get_trend":
            tt = d.get("team_trend_spotlight") or d.get("spotlight") or {}
            if isinstance(tt, dict) and tt.get("score") is not None:
                sc = round(float(tt.get("score") or 0.0), 1)
                ledger.append(
                    {
                        "fact_id": f"F{fact_idx}",
                        "part": "trend",
                        "subject": str(tt.get("team") or d.get("scope") or call.team or ""),
                        "period": str(d.get("period") or call.period or ""),
                        "value": sc,
                        "display": f"{sc:.1f}%",
                        "unit": "%",
                    }
                )
                fact_idx += 1
                continue
        avg_sc = d.get("average_score")
        if isinstance(avg_sc, (int, float)):
            sc = round(float(avg_sc), 1)
            ledger.append(
                {
                    "fact_id": f"F{fact_idx}",
                    "part": "score",
                    "subject": str(d.get("scope") or call.team or ""),
                    "period": str(d.get("period") or call.period or ""),
                    "value": sc,
                    "display": f"{sc:.1f}%",
                    "unit": "%",
                }
            )
            fact_idx += 1
    if not ledger and default_headline:
        ledger.append({"fact_id": "F1", "part": "summary", "statement": default_headline})
    return ledger


def validate_grounded_synthesis(
    *,
    draft_payload: dict[str, Any] | None,
    fact_ledger: list[dict[str, Any]],
) -> tuple[str | None, str]:
    """Validate a model-authored synthesis response against the authoritative fact ledger."""
    if not isinstance(draft_payload, dict):
        return None, "not_dict"
    fact_ids = draft_payload.get("fact_ids")
    headline = draft_payload.get("headline")
    if not isinstance(fact_ids, list) or not fact_ids or not isinstance(headline, str) or not headline.strip():
        return None, "missing_fields"
    text = headline.strip()
    if len(text) > 360 or _UNSAFE_PARAM_RE.search(text):
        return None, "unsafe_or_too_long"

    known_by_id = {str(f.get("fact_id")): f for f in fact_ledger if f.get("fact_id")}
    if any(not isinstance(fid, str) or fid not in known_by_id for fid in fact_ids):
        return None, "unknown_fact_id"
    if set(known_by_id.keys()) - set(fact_ids):
        return None, "incomplete_fact_coverage"

    text_lower = text.casefold()
    allowed_numbers: set[float] = set()
    allowed_months: set[str] = set()
    subject_value_positions: list[tuple[str, float, int, int, str]] = []

    all_canonical_months = {m.casefold() for m in MONTHS}
    for f in fact_ledger:
        val = f.get("value")
        unit = str(f.get("unit") or "").strip()
        if isinstance(val, (int, float)):
            allowed_numbers.add(round(float(val), 1))
        per = str(f.get("period") or "")
        per_lower = per.casefold()
        for m_name in all_canonical_months:
            if m_name in per_lower:
                allowed_months.add(m_name)
        m_iso = re.match(r"^(20\d{2})-(0[1-9]|1[0-2])$", per.strip())
        if m_iso:
            m_human = REVERSE_MONTHS_BY_NUM.get(int(m_iso.group(2)))
            if m_human:
                allowed_months.add(m_human.casefold())
        for num_tok in re.findall(r"\d+(?:\.\d+)?", per):
            allowed_numbers.add(round(float(num_tok), 1))
        emp_id = str(f.get("employee_id") or "")
        for num_tok in re.findall(r"\d+", emp_id):
            allowed_numbers.add(round(float(num_tok), 1))

        subj = str(f.get("subject") or "").strip()
        subj_pos = -1
        if subj:
            subj_cf = subj.casefold()
            subj_pos = text_lower.find(subj_cf)
            if subj_pos < 0:
                first_word = subj.split()[0].casefold()
                subj_pos = text_lower.find(first_word)
                if subj_pos < 0:
                    return None, "missing_subject"

        if isinstance(val, (int, float)):
            fval = float(val)
            val_str_1 = f"{fval:.1f}"
            val_str_0 = str(int(fval)) if fval.is_integer() else val_str_1
            val_str_comma = f"{int(fval):,}" if fval.is_integer() else val_str_1
            val_candidates = []
            for cand in (val_str_1, val_str_0, val_str_comma):
                if cand not in val_candidates:
                    val_candidates.append(cand)

            val_match_pos = -1
            for cand in val_candidates:
                m_val = re.search(rf"(?<![\d.]){re.escape(cand)}(?![\d.])", text)
                if m_val:
                    val_match_pos = m_val.start()
                    break
            if val_match_pos < 0:
                return None, "missing_fact_value"

            # Unit fidelity check: count values must not be rendered with '%', and '%' values must have '%'
            if unit == "count":
                for cand in val_candidates:
                    if re.search(rf"(?<![\d.]){re.escape(cand)}\s*%", text):
                        return None, "mismatched_unit"
            elif unit == "%":
                has_pct = any(
                    re.search(rf"(?<![\d.]){re.escape(cand)}\s*%", text)
                    for cand in val_candidates
                )
                if not has_pct:
                    return None, "mismatched_unit"

            if subj_pos >= 0:
                subject_value_positions.append((subj.casefold(), round(fval, 1), subj_pos, val_match_pos, unit))

    # Period month fidelity check: reject any month name in text that does not appear in fact_ledger
    if allowed_months:
        for m_name in all_canonical_months:
            if re.search(rf"\b{re.escape(m_name)}\b", text_lower) and m_name not in allowed_months:
                return None, "mismatched_period"

    # Reject any numeric token if allowed_numbers is empty or if the number is not in allowed_numbers
    for token in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        num_val = round(float(token.replace(",", "")), 1)
        if not allowed_numbers or num_val not in allowed_numbers:
            return None, "invented_number"

    # Subject-to-value binding and comparison direction check across distinct facts
    for i in range(len(subject_value_positions)):
        s_i, v_i, s_pos_i, v_pos_i, _ = subject_value_positions[i]
        for j in range(i + 1, len(subject_value_positions)):
            s_j, v_j, s_pos_j, v_pos_j, _ = subject_value_positions[j]
            if s_i == s_j or v_i == v_j or s_pos_i == s_pos_j or v_pos_i == v_pos_j:
                continue
            # Relative order of subjects and their bound values must match
            if (s_pos_i < s_pos_j) != (v_pos_i < v_pos_j):
                return None, "swapped_fact_values"

            # Check winner / loser comparison verbs between the two subjects
            low_subj = s_i if v_i < v_j else s_j
            high_subj = s_j if v_i < v_j else s_i
            low_pos = s_pos_i if v_i < v_j else s_pos_j
            high_pos = s_pos_j if v_i < v_j else s_pos_i
            if low_pos < high_pos:
                between = text_lower[low_pos:high_pos]
                if re.search(
                    r"\b(?:led|leads|leading|outperformed|beat|exceeded|topped|higher\s+than|more\s+(?:[a-z]+\s+)?than|ahead\s+of)\b",
                    between,
                ):
                    return None, "contradictory_comparison"
            else:
                between = text_lower[high_pos:low_pos]
                if re.search(
                    r"\b(?:trailed|trails|trailing|lagged|behind|lower\s+than|fewer\s+(?:[a-z]+\s+)?than|less\s+(?:[a-z]+\s+)?than)\b",
                    between,
                ):
                    return None, "contradictory_comparison"

    return text, "ok"


def _compose_grounded_answer(
    *,
    question: str,
    fact_ledger: list[dict[str, Any]],
) -> tuple[str | None, float, str]:
    """Ask the configured model for a short headline. The fact-ledger validator must accept it."""
    schema = {
        "name": "pms_grounded_synthesis",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "fact_ids": {"type": "array", "items": {"type": "string"}},
                "headline": {"type": "string"},
            },
            "required": ["fact_ids", "headline"],
            "additionalProperties": False,
        },
    }
    sys_msg = (
        'Compose a concise 1-2 sentence English answer using ONLY the supplied facts. '
        'Include every fact_id in fact_ids and state each subject, period, and exact display value in headline. '
        'Never invent numbers. Return compact JSON: {"fact_ids":["F1"],"headline":"..."}.'
    )
    user_payload_str = json.dumps(
        {"question": question[:240], "facts": fact_ledger},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    syn_schema = schema.get("schema", schema)
    req = ProviderRequest(
        messages=[
            ProviderMessage(role="user", content=user_payload_str),
        ],
        system_instruction=sys_msg,
        response_format="json",
        json_schema=syn_schema,
        temperature=0.0,
        max_tokens=96,
        timeout_seconds=synthesis_timeout_seconds(),
        purpose="exploration_synthesis",
    )
    engine = get_unified_provider_engine()
    resp = engine.generate(req)
    provider = resp.provider if resp.provider in ("cloudflare", "gemini") else "cloudflare"
    _last_exploration_provider.set(provider)
    _last_exploration_model.set(resp.model or provider)
    if not resp.is_success:
        reason = resp.outcome or "unavailable_or_invalid"
        return None, resp.latency_ms, reason
    try:
        content = _JSON_FENCE_RE.sub("", (resp.content or "").strip()).strip()
        draft = json.loads(content)
    except (ValueError, TypeError):
        return None, resp.latency_ms, "invalid_response"
    validated_text, v_status = validate_grounded_synthesis(draft_payload=draft, fact_ledger=fact_ledger)
    if validated_text is None:
        return None, resp.latency_ms, v_status
    return validated_text, resp.latency_ms, "ok"


def _covered_parts_for_calls(calls: list[ValidatedExplorationToolCall]) -> set[str]:
    covered: set[str] = set()
    for c in calls:
        if c.tool in DISCOVERY_EXPLORATION_TOOLS:
            continue
        if c.tool in ("get_team_score_summary", "get_management_balanced_scorecard"):
            covered.add("score")
        elif c.tool == "get_kpi_diagnosis":
            covered.add("kpi_diagnosis")
            covered.add("score")
        elif c.tool in ("rank_employees", "get_employee_summary"):
            covered.add("ranking")
        elif c.tool == "compare_branches":
            covered.add("compare_branches")
        elif c.tool == "compare_periods":
            covered.add("compare_periods")
        elif c.tool == "get_trend":
            covered.add("trend")
    return covered


def run_bounded_exploration(
    *,
    db: Session,
    scope: dict[str, Any],
    prompt: str,
    session_state: SessionFilterContext,
    published_periods: set[str],
    employee_candidates: list[EmployeeHistoryCandidate],
    live_auth_service: AiConversationService | None = None,
) -> LocalExplorationResult:
    """Run an opt-in, bounded multi-step exploration loop with permission-scoped PMS tools.

    If disabled, busy, unreachable, or given malformed/unsafe model output, returns
    `LocalExplorationResult(handled=False, fallback_reason=...)` so the caller falls back
    seamlessly to deterministic PMS routing.
    """
    if not local_exploration_enabled():
        return LocalExplorationResult(handled=False, fallback_reason="disabled")

    clean_prompt = (prompt or "").strip()
    if not clean_prompt or len(clean_prompt) > 600:
        return LocalExplorationResult(handled=False, fallback_reason="invalid_prompt")

    # Pre-check: never send explicit unauthorized teams or branches in the user prompt to the local model
    lower = clean_prompt.casefold()
    explicit_teams = _detect_teams_in_prompt(lower)
    for t_cand in explicit_teams:
        if not user_can_access_team(scope, t_cand):
            allowed_fns = ", ".join(scope.get("accessible_functions") or []) or "your assigned teams"
            return LocalExplorationResult(
                handled=True,
                outcome="restricted_access",
                headline=f"Access restricted: your role does not have permission to view {t_cand} data.",
                narrative_bullets=[f"Your account is scoped to {allowed_fns}."],
                suggested_followups=["Show performance summary for my authorized scope"],
                structured_query=StructuredQueryPlan(intent="current_value", team=t_cand),
                resolved_session_state=session_state,
            )

    explicit_branches = _detect_branches_in_prompt(lower, explicit_teams[0] if explicit_teams else session_state.team)
    for b_cand in explicit_branches:
        if not user_can_access_branch(scope, b_cand):
            allowed_b = sorted(
                str(b).capitalize()
                for b in (scope.get("accessible_branches") or scope.get("allowed_branches") or [])
            )
            allowed_str = ", ".join(allowed_b) if allowed_b else "your assigned branch"
            return LocalExplorationResult(
                handled=True,
                outcome="restricted_access",
                headline=f"Access restricted: your role does not have permission to view {b_cand.capitalize()} branch data.",
                narrative_bullets=[
                    f"Your current access scope is restricted to {allowed_str}.",
                    "PMS AI never substitutes another branch when a restricted branch is requested.",
                ],
                suggested_followups=[
                    f"Show performance summary for {allowed_b[0]}" if allowed_b else "Show performance for my authorized scope"
                ],
                structured_query=StructuredQueryPlan(intent="current_value", branch=b_cand),
                resolved_session_state=session_state,
            )

    # Pre-check: off-topic / non-PMS requests (e.g. weather, poem, football)
    if re.search(r"\b(?:weather|poem|football|soccer|recipe|joke|horoscope|movie|song|capital\s+of)\b", lower) and not explicit_teams:
        return LocalExplorationResult(
            handled=True,
            outcome="unsupported_request",
            headline="I cannot answer that request — PMS AI only analyzes PMS performance scorecards, KPIs, trends, branches, and corrective actions.",
            narrative_bullets=[
                "Ask about team performance scores, KPI targets and gaps, branch comparisons, or employee rankings."
            ],
            suggested_followups=["What is the Inbound score in September 2026?"],
            structured_query=StructuredQueryPlan(intent="unsupported", turn_kind_v2="unsupported"),
            resolved_session_state=session_state,
            unknown_code="ambiguous_request",
        )

    # Pre-check: contextless comparison ("Which one is doing better?") or team-ambiguous metric ("What is the attendance?")
    has_prior_team = bool(
        (session_state.team and session_state.team not in ("All", "all"))
        or (session_state.last_confirmed_query and session_state.last_confirmed_query.team)
    )
    if not explicit_teams and not explicit_branches and not has_prior_team:
        if re.search(r"\b(?:which\s+one|doing\s+better|compare\s+them|who\s+is\s+better)\b", lower):
            q_txt = "Which teams, branches, or employees would you like to compare? Please specify the scope and metric."
            return LocalExplorationResult(
                handled=True,
                outcome="clarification",
                headline=q_txt,
                narrative_bullets=["Specify at least two teams or branches and the performance measure to compare."],
                suggested_followups=[
                    "Compare Dubai and Sharjah Inbound bookings in September 2026",
                    "What is the Inbound score in September 2026?",
                ],
                clarification=AiClarificationPrompt(
                    code="AMBIGUOUS_TEAM_SCOPE",
                    question=q_txt,
                    choices=[],
                ),
                structured_query=StructuredQueryPlan(intent="clarify", turn_kind_v2="clarification", clarification_code="AMBIGUOUS_TEAM_SCOPE"),
                resolved_session_state=session_state,
                unknown_code="ambiguous_request",
            )
        if re.fullmatch(r"\s*what\s+is\s+(?:the\s+)?(?:attendance|abandon\s+rate|quality|reachability|booking\s+rate)\s*\??\s*", lower):
            q_txt = "Which team would you like to check? Please specify a team such as Inbound or Outbound."
            return LocalExplorationResult(
                handled=True,
                outcome="clarification",
                headline=q_txt,
                narrative_bullets=["Multiple teams track this KPI; specify the team to view exact figures."],
                suggested_followups=[
                    "What is Inbound Attendance Rate in September 2026?",
                    "What is Outbound Attendance Rate in September 2026?",
                ],
                clarification=AiClarificationPrompt(
                    code="AMBIGUOUS_KPI_SCOPE",
                    question=q_txt,
                    choices=[],
                ),
                structured_query=StructuredQueryPlan(intent="clarify", turn_kind_v2="clarification", clarification_code="AMBIGUOUS_KPI_SCOPE"),
                resolved_session_state=session_state,
                unknown_code="ambiguous_request",
            )

    def _restricted_revoked_result(
        *,
        step_traces_now: list[ExplorationStepTrace],
        prov_calls_now: int,
        prov_ms_now: float,
        plan_calls_now: int,
        plan_ms_now: float,
        db_ms_now: float,
    ) -> LocalExplorationResult:
        return LocalExplorationResult(
            handled=True,
            outcome="restricted_access",
            headline="Access restricted: your permissions changed during execution and no longer allow viewing this scope.",
            narrative_bullets=[
                "Live permission revalidation detected that access to the requested team, level, branch, function, or employee was revoked."
            ],
            suggested_followups=["Show performance summary for my authorized scope"],
            resolved_session_state=session_state,
            steps_taken=len(step_traces_now),
            step_traces=step_traces_now,
            provider_calls=prov_calls_now,
            provider_ms=prov_ms_now,
            planner_calls=plan_calls_now,
            planner_ms=plan_ms_now,
            database_ms=db_ms_now,
        )

    def _revalidate_live_scope_and_evidence(
        current_scope: dict[str, Any],
        calls_to_check: list[ValidatedExplorationToolCall],
        results_to_check: list[ToolExecutionResult],
    ) -> tuple[bool, dict[str, Any]]:
        if live_auth_service is None:
            return True, current_scope
        refreshed = live_auth_service.validate_live_account_and_scope(current_scope)
        release_read_transaction(db)
        for c_item in calls_to_check:
            if not live_auth_service.is_plan_and_context_authorized(
                scope=refreshed,
                team=c_item.team,
                function=c_item.function,
                branch=c_item.branch,
                branches=list(c_item.branches),
                performance_level=c_item.performance_level,
                employee_id=c_item.employee_query if c_item.tool == "get_employee_summary" else None,
            ):
                return False, refreshed
        all_tev = [ev for tr in results_to_check for ev in tr.typed_evidence]
        all_digests = [tr.digest for tr in results_to_check if isinstance(tr.digest, dict)]
        if (all_tev or all_digests) and hasattr(live_auth_service, "is_returned_evidence_authorized"):
            if not live_auth_service.is_returned_evidence_authorized(
                scope=refreshed,
                typed_evidence=all_tev,
                tool_digests=all_digests,
                fallback_branch=session_state.branch,
                fallback_level=session_state.performance_level,
            ):
                release_read_transaction(db)
                return False, refreshed
            release_read_transaction(db)
        return True, refreshed

    max_steps = get_max_exploration_steps()
    if live_auth_service is not None:
        scope = live_auth_service.validate_live_account_and_scope(scope)
        release_read_transaction(db)
    authorized_concepts = build_authorized_concept_summary(
        scope=scope,
        session_state=session_state,
        published_periods=published_periods,
        employee_candidates=employee_candidates,
    )
    latest_pub = str(authorized_concepts["latest_published_period"])
    explicit_periods = _extract_explicit_periods_from_prompt(clean_prompt, session_state.year or 2026)

    # Pre-check explicit unpublished future periods in the user prompt
    for exp_p in explicit_periods:
        if published_periods and exp_p not in published_periods and (
            exp_p > latest_pub or exp_p in UNAVAILABLE_FUTURE_PERIODS
        ):
            return _build_unknown_response(
                unknown_code="unpublished_period",
                team=explicit_teams[0] if explicit_teams else session_state.team,
                function=session_state.function,
                period_key=exp_p,
                latest_published_period=latest_pub,
                session_state=session_state,
                step_traces=[],
                provider_calls=0,
                provider_ms=0.0,
            )

    required_parts = _extract_required_question_parts(clean_prompt)
    active_context = {
        "function": session_state.function or (function_for_team(explicit_teams[0]) if len(explicit_teams) == 1 else None),
        "team": (explicit_teams[0] if len(explicit_teams) == 1 else None) or session_state.team,
        "branch": session_state.branch,
        "performance_level": session_state.performance_level or "Employee",
        "period": explicit_periods[-1] if explicit_periods else None,
        "month": session_state.month,
        "year": session_state.year or 2026,
    }

    step_traces: list[ExplorationStepTrace] = []
    collected_evidence: list[dict[str, Any]] = []
    executed_calls: list[ValidatedExplorationToolCall] = []
    tool_results: list[ToolExecutionResult] = []
    seen_tool_signatures: set[tuple[Any, ...]] = set()
    total_provider_calls = 0
    total_provider_ms = 0.0
    total_db_ms = 0.0

    is_schema_unknown_prompt = bool(
        re.search(
            r"\b(?:salary|salaries|payroll|bonus|bonuses|commission|commissions|compensation|wage|wages|paycheck|"
            r"hire\s+date|joining\s+date|join\s+date|date\s+of\s+joining|onboarded\s+date|new\s+joiner|"
            r"when\s+did\s+[a-z]+\s+join)\b",
            lower,
        )
    )

    for step_num in range(1, max_steps + 1):
        covered_now = _covered_parts_for_calls(executed_calls)
        missing_parts = [p for p in required_parts if p not in covered_now]

        # Revalidate live grants before sending evidence or metadata to the model
        ok_pre_model, scope = _revalidate_live_scope_and_evidence(scope, executed_calls, tool_results)
        if not ok_pre_model:
            return _restricted_revoked_result(
                step_traces_now=step_traces,
                prov_calls_now=total_provider_calls,
                prov_ms_now=total_provider_ms,
                plan_calls_now=total_provider_calls,
                plan_ms_now=total_provider_ms,
                db_ms_now=total_db_ms,
            )

        parsed, step_ms, status = _call_local_exploration_model(
            question=clean_prompt,
            step=step_num,
            max_steps=max_steps,
            active_context=active_context,
            authorized_concepts=authorized_concepts,
            collected_evidence=collected_evidence,
            required_parts=required_parts,
            missing_parts=missing_parts,
        )
        total_provider_calls += 1
        total_provider_ms = round(total_provider_ms + step_ms, 2)

        # Revalidate live grants immediately after the model call
        ok_post_model, scope = _revalidate_live_scope_and_evidence(scope, executed_calls, tool_results)
        if not ok_post_model:
            return _restricted_revoked_result(
                step_traces_now=step_traces,
                prov_calls_now=total_provider_calls,
                prov_ms_now=total_provider_ms,
                plan_calls_now=total_provider_calls,
                plan_ms_now=total_provider_ms,
                db_ms_now=total_db_ms,
            )

        if parsed is None:
            step_traces.append(
                ExplorationStepTrace(
                    step=step_num,
                    action="error",
                    unknown_code="none",
                    elapsed_ms=step_ms,
                    status=status,
                )
            )
            return LocalExplorationResult(
                handled=False,
                steps_taken=len(step_traces),
                step_traces=step_traces,
                provider_calls=total_provider_calls,
                provider_ms=total_provider_ms,
                planner_calls=total_provider_calls,
                planner_ms=total_provider_ms,
                database_ms=total_db_ms,
                fallback_reason=status,
            )

        action = str(parsed["action"])
        unknown_code = str(parsed["unknown_code"])
        raw_tools = list(parsed.get("tools") or [])

        step_traces.append(
            ExplorationStepTrace(
                step=step_num,
                action=action,
                unknown_code=unknown_code,
                requested_tools=[str(t.get("tool") or "") for t in raw_tools],
                elapsed_ms=step_ms,
                status="ok",
            )
        )

        if action == "unknown":
            eff_code = unknown_code if unknown_code != "none" else "missing_metric_evidence"
            return _build_unknown_response(
                unknown_code=eff_code,
                team=active_context.get("team"),
                function=active_context.get("function"),
                period_key=latest_pub,
                latest_published_period=latest_pub,
                session_state=session_state,
                step_traces=step_traces,
                provider_calls=total_provider_calls,
                provider_ms=total_provider_ms,
            )

        if is_schema_unknown_prompt:
            if re.search(r"\b(?:hire\s+date|joining\s+date|join\s+date|date\s+of\s+joining|onboarded\s+date|new\s+joiner|when\s+did\s+[a-z]+\s+join)\b", lower):
                return _build_unknown_response(
                    unknown_code="missing_hr_join_date",
                    team=active_context.get("team"),
                    function=active_context.get("function"),
                    period_key=latest_pub,
                    latest_published_period=latest_pub,
                    session_state=session_state,
                    step_traces=step_traces,
                    provider_calls=total_provider_calls,
                    provider_ms=total_provider_ms,
                )
            if re.search(r"\b(?:salary|salaries|payroll|bonus|bonuses|commission|commissions|compensation|wage|wages|paycheck)\b", lower):
                return _build_unknown_response(
                    unknown_code="unsupported_compensation_data",
                    team=active_context.get("team"),
                    function=active_context.get("function"),
                    period_key=latest_pub,
                    latest_published_period=latest_pub,
                    session_state=session_state,
                    step_traces=step_traces,
                    provider_calls=total_provider_calls,
                    provider_ms=total_provider_ms,
                )

        if action == "finish":
            if not tool_results:
                return LocalExplorationResult(
                    handled=False,
                    steps_taken=len(step_traces),
                    step_traces=step_traces,
                    provider_calls=total_provider_calls,
                    provider_ms=total_provider_ms,
                    planner_calls=total_provider_calls,
                    planner_ms=total_provider_ms,
                    fallback_reason="finish_without_evidence",
                )
            break

        # action == "call_tools"
        if not raw_tools:
            if tool_results:
                break
            return LocalExplorationResult(
                handled=False,
                steps_taken=len(step_traces),
                step_traces=step_traces,
                provider_calls=total_provider_calls,
                provider_ms=total_provider_ms,
                planner_calls=total_provider_calls,
                planner_ms=total_provider_ms,
                fallback_reason="empty_tool_calls",
            )

        validated_step_calls: list[ValidatedExplorationToolCall] = []
        for raw_t in raw_tools[:2]:
            if len(executed_calls) + len(validated_step_calls) >= 4:
                break
            v_call, early_res, v_status = _validate_and_normalize_tool_call(
                raw_tool=raw_t,
                prompt=clean_prompt,
                scope=scope,
                session_state=session_state,
                published_periods=published_periods,
                latest_published_period=latest_pub,
                employee_candidates=employee_candidates,
            )
            if early_res is not None:
                early_res.steps_taken = len(step_traces)
                early_res.step_traces = step_traces
                early_res.provider_calls = total_provider_calls
                early_res.provider_ms = total_provider_ms
                early_res.planner_calls = total_provider_calls
                early_res.planner_ms = total_provider_ms
                return early_res
            if v_call is None:
                return LocalExplorationResult(
                    handled=False,
                    steps_taken=len(step_traces),
                    step_traces=step_traces,
                    provider_calls=total_provider_calls,
                    provider_ms=total_provider_ms,
                    planner_calls=total_provider_calls,
                    planner_ms=total_provider_ms,
                    fallback_reason=v_status,
                )
            sig = (
                v_call.tool,
                v_call.team,
                v_call.metric_id,
                v_call.branch,
                v_call.compare_branch,
                v_call.period,
                v_call.performance_level,
                v_call.direction,
                v_call.employee_query,
            )
            if sig not in seen_tool_signatures:
                seen_tool_signatures.add(sig)
                validated_step_calls.append(v_call)

        if not validated_step_calls:
            break

        # Revalidate live grants before executing protected tool queries
        ok_pre_tools, scope = _revalidate_live_scope_and_evidence(
            scope,
            [*executed_calls, *validated_step_calls],
            tool_results,
        )
        if not ok_pre_tools:
            return _restricted_revoked_result(
                step_traces_now=step_traces,
                prov_calls_now=total_provider_calls,
                prov_ms_now=total_provider_ms,
                plan_calls_now=total_provider_calls,
                plan_ms_now=total_provider_ms,
                db_ms_now=total_db_ms,
            )

        t_db0 = time.perf_counter()
        ctx = ToolExecutionContext(db=db, scope=scope, session_state=session_state)
        registry = DeterministicToolRegistry(ctx)
        for v_call in validated_step_calls:
            tr, compact_ev = _execute_validated_exploration_tool(
                call=v_call,
                registry=registry,
                authorized_concepts=authorized_concepts,
            )
            executed_calls.append(v_call)
            tool_results.append(tr)
            collected_evidence.append(compact_ev)
        release_read_transaction(db)
        total_db_ms = round(total_db_ms + (time.perf_counter() - t_db0) * 1000.0, 2)

        # Revalidate actual returned evidence immediately after tool execution
        ok_post_tools, scope = _revalidate_live_scope_and_evidence(scope, executed_calls, tool_results)
        if not ok_post_tools:
            return _restricted_revoked_result(
                step_traces_now=step_traces,
                prov_calls_now=total_provider_calls,
                prov_ms_now=total_provider_ms,
                plan_calls_now=total_provider_calls,
                plan_ms_now=total_provider_ms,
                db_ms_now=total_db_ms,
            )

        if len(executed_calls) >= 4:
            break
        covered_after = _covered_parts_for_calls(executed_calls)
        still_missing = [p for p in required_parts if p not in covered_after]
        is_compound_prompt = bool(len(required_parts) >= 2 or re.search(r"\b(?:and|also|plus|both|as well as)\b|;", lower))
        # If only discovery tools have been called so far, continue to next step so the model can issue a data tool
        if all(c.tool in DISCOVERY_EXPLORATION_TOOLS for c in executed_calls):
            if is_schema_unknown_prompt:
                break
            continue
        if not still_missing and not is_compound_prompt:
            break
        if not still_missing and len([c for c in executed_calls if c.tool not in DISCOVERY_EXPLORATION_TOOLS]) >= len(required_parts):
            break

    # Ensure multi-part compound requests that completed at least 1 data read do not drop a required second part
    covered_final = _covered_parts_for_calls(executed_calls)
    remaining_parts = [p for p in required_parts if p not in covered_final]
    if remaining_parts and executed_calls and len(executed_calls) < 4:
        ok_pre_extra, scope = _revalidate_live_scope_and_evidence(scope, executed_calls, tool_results)
        if not ok_pre_extra:
            return _restricted_revoked_result(
                step_traces_now=step_traces,
                prov_calls_now=total_provider_calls,
                prov_ms_now=total_provider_ms,
                plan_calls_now=total_provider_calls,
                plan_ms_now=total_provider_ms,
                db_ms_now=total_db_ms,
            )
        part_to_tool = {
            "score": "get_team_score_summary",
            "kpi_diagnosis": "get_kpi_diagnosis",
            "ranking": "rank_employees",
            "compare_branches": "compare_branches",
            "compare_periods": "compare_periods",
            "trend": "get_trend",
        }
        t_db_extra = time.perf_counter()
        ctx = ToolExecutionContext(db=db, scope=scope, session_state=session_state)
        registry = DeterministicToolRegistry(ctx)
        for rem_p in remaining_parts:
            mapped_tool = part_to_tool.get(rem_p)
            if not mapped_tool or len(executed_calls) >= 4:
                continue
            v_call, early_res, _ = _validate_and_normalize_tool_call(
                raw_tool={"tool": mapped_tool},
                prompt=clean_prompt,
                scope=scope,
                session_state=session_state,
                published_periods=published_periods,
                latest_published_period=latest_pub,
                employee_candidates=employee_candidates,
            )
            if early_res is not None:
                return early_res
            if v_call is not None:
                sig = (
                    v_call.tool,
                    v_call.team,
                    v_call.metric_id,
                    v_call.branch,
                    v_call.compare_branch,
                    v_call.period,
                    v_call.performance_level,
                    v_call.direction,
                    v_call.employee_query,
                )
                if sig not in seen_tool_signatures:
                    seen_tool_signatures.add(sig)
                    tr, compact_ev = _execute_validated_exploration_tool(
                        call=v_call,
                        registry=registry,
                        authorized_concepts=authorized_concepts,
                    )
                    executed_calls.append(v_call)
                    tool_results.append(tr)
                    collected_evidence.append(compact_ev)
        release_read_transaction(db)
        total_db_ms = round(total_db_ms + (time.perf_counter() - t_db_extra) * 1000.0, 2)

    if not tool_results:
        return LocalExplorationResult(
            handled=False,
            steps_taken=len(step_traces),
            step_traces=step_traces,
            provider_calls=total_provider_calls,
            provider_ms=total_provider_ms,
            planner_calls=total_provider_calls,
            planner_ms=total_provider_ms,
            database_ms=total_db_ms,
            fallback_reason="no_tools_executed",
        )

    total_records = sum(tr.records_evaluated for tr in tool_results)
    only_concept_inspection = all(c.tool in DISCOVERY_EXPLORATION_TOOLS for c in executed_calls)
    if only_concept_inspection:
        first_c = executed_calls[0]
        if re.search(
            r"\b(?:salary|salaries|payroll|bonus|bonuses|commission|commissions|compensation|wage|wages|paycheck)\b",
            lower,
        ):
            return _build_unknown_response(
                unknown_code="unsupported_compensation_data",
                team=first_c.team,
                function=first_c.function,
                period_key=first_c.period or latest_pub,
                latest_published_period=latest_pub,
                session_state=session_state,
                step_traces=step_traces,
                provider_calls=total_provider_calls,
                provider_ms=total_provider_ms,
            )
        if re.search(
            r"\b(?:hire\s+date|joining\s+date|join\s+date|date\s+of\s+joining|onboarded\s+date|new\s+joiner|when\s+did\s+[a-z]+\s+join)\b",
            lower,
        ):
            return _build_unknown_response(
                unknown_code="missing_hr_join_date",
                team=first_c.team,
                function=first_c.function,
                period_key=first_c.period or latest_pub,
                latest_published_period=latest_pub,
                session_state=session_state,
                step_traces=step_traces,
                provider_calls=total_provider_calls,
                provider_ms=total_provider_ms,
            )
        if re.search(r"\brevenue\b", lower) and (
            first_c.function == "Call Center" or first_c.team in ("Inbound", "Outbound", "Telemarketing")
        ):
            return _build_unknown_response(
                unknown_code="call_center_revenue_not_tracked",
                team=first_c.team,
                function=first_c.function,
                period_key=first_c.period or latest_pub,
                latest_published_period=latest_pub,
                session_state=session_state,
                step_traces=step_traces,
                provider_calls=total_provider_calls,
                provider_ms=total_provider_ms,
            )
    if total_records == 0 and not only_concept_inspection:
        first_c = executed_calls[0]
        return _build_unknown_response(
            unknown_code="missing_metric_evidence",
            team=first_c.team,
            function=first_c.function,
            period_key=first_c.period or latest_pub,
            latest_published_period=latest_pub,
            session_state=session_state,
            step_traces=step_traces,
            provider_calls=total_provider_calls,
            provider_ms=total_provider_ms,
        )

    # Post-execution live permission revalidation (before synthesis)
    ok_pre_syn, scope = _revalidate_live_scope_and_evidence(scope, executed_calls, tool_results)
    if not ok_pre_syn:
        return _restricted_revoked_result(
            step_traces_now=step_traces,
            prov_calls_now=total_provider_calls,
            prov_ms_now=total_provider_ms,
            plan_calls_now=total_provider_calls,
            plan_ms_now=total_provider_ms,
            db_ms_now=total_db_ms,
        )

    visual_cards: list[StructuredVisualCard] = []
    citations: list[SourceCitationPill] = []
    deep_links: list[DeepLinkCta] = []
    typed_evidence: list[TypedMetricEvidence] = []
    tool_call_records: list[AiToolCallRecord] = []
    tool_digests: list[dict[str, Any]] = []
    seen_cit: set[str] = set()
    seen_dl: set[str] = set()
    res_month = session_state.month
    res_year = session_state.year
    basis_warning: str | None = None

    for tr in tool_results:
        if tr.resolved_month:
            res_month = tr.resolved_month
        if tr.resolved_year:
            res_year = tr.resolved_year
        if tr.basis_warning and not basis_warning:
            basis_warning = tr.basis_warning
        tool_call_records.append(
            AiToolCallRecord(
                tool_name=tr.tool_name,
                arguments=tr.arguments,
                records_evaluated=tr.records_evaluated,
            )
        )
        tool_digests.append(tr.digest)
        visual_cards.extend(tr.visual_cards)
        typed_evidence.extend(tr.typed_evidence)
        for c_pill in tr.citations:
            if c_pill.label not in seen_cit:
                seen_cit.add(c_pill.label)
                citations.append(c_pill)
        for dl in tr.deep_links:
            if dl.route not in seen_dl:
                seen_dl.add(dl.route)
                deep_links.append(dl)

    headline, bullets, followups = _synthesize_explored_evidence(
        prompt=clean_prompt,
        session_state=session_state,
        executed_calls=executed_calls,
        tool_results=tool_results,
    )

    planner_calls = total_provider_calls
    planner_ms = total_provider_ms
    synthesis_calls = 0
    synthesis_ms = 0.0
    synthesis_validated = False
    synthesis_fallback_reason = "not_requested"

    truthy_syn = {"1", "true", "yes", "on", "enabled"}
    falsy_syn = {"0", "false", "no", "off", "disabled"}
    exp_syn_val = os.environ.get("PMS_AI_LOCAL_EXPLORATION_SYNTHESIS_ENABLED", "").strip().casefold()
    ev_syn_val = os.environ.get("PMS_AI_LOCAL_EVIDENCE_SYNTHESIS_ENABLED", "").strip().casefold()
    legacy_syn_val = os.environ.get("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "").strip().casefold()
    if exp_syn_val in falsy_syn or ev_syn_val in falsy_syn:
        should_run_synthesis = False
    elif exp_syn_val in truthy_syn or ev_syn_val in truthy_syn or legacy_syn_val in truthy_syn:
        should_run_synthesis = True
    else:
        should_run_synthesis = planner_ms <= 6000.0
    if should_run_synthesis:
        # Revalidate live grants immediately before sending fact_ledger to synthesis
        ok_before_syn, scope = _revalidate_live_scope_and_evidence(scope, executed_calls, tool_results)
        if not ok_before_syn:
            return _restricted_revoked_result(
                step_traces_now=step_traces,
                prov_calls_now=total_provider_calls,
                prov_ms_now=total_provider_ms,
                plan_calls_now=planner_calls,
                plan_ms_now=planner_ms,
                db_ms_now=total_db_ms,
            )
        fact_ledger = build_fact_ledger_from_evidence(
            executed_calls=executed_calls,
            tool_results=tool_results,
            default_headline=headline,
        )
        composed_h, syn_ms, syn_status = _compose_grounded_answer(
            question=clean_prompt,
            fact_ledger=fact_ledger,
        )
        synthesis_calls = 1
        synthesis_ms = syn_ms
        total_provider_calls += 1
        total_provider_ms = round(total_provider_ms + syn_ms, 2)
        # Revalidate live grants immediately after synthesis returns
        ok_after_syn, scope = _revalidate_live_scope_and_evidence(scope, executed_calls, tool_results)
        if not ok_after_syn:
            return _restricted_revoked_result(
                step_traces_now=step_traces,
                prov_calls_now=total_provider_calls,
                prov_ms_now=total_provider_ms,
                plan_calls_now=planner_calls,
                plan_ms_now=planner_ms,
                db_ms_now=total_db_ms,
            )
        if composed_h is not None and syn_status == "ok":
            headline = composed_h
            synthesis_validated = True
            synthesis_fallback_reason = "none"
        else:
            synthesis_validated = False
            synthesis_fallback_reason = syn_status

    data_exec_calls = [c for c in executed_calls if c.tool not in DISCOVERY_EXPLORATION_TOOLS] or executed_calls
    primary_call = data_exec_calls[0]
    tool_to_intent = {
        "inspect_authorized_concepts": "current_value",
        "find_concepts": "current_value",
        "describe_metric": "scorecard_structure",
        "list_available_periods": "current_value",
        "get_team_score_summary": "current_value",
        "get_management_balanced_scorecard": "current_value",
        "get_kpi_diagnosis": "actual_vs_target" if primary_call.metric_id else "score_drivers",
        "compare_branches": "compare_branches",
        "compare_periods": "compare_periods",
        "get_trend": "trend",
        "rank_employees": "ranking",
        "get_employee_summary": "ranking",
        "get_corrective_actions": "corrective_actions",
    }
    primary_intent = tool_to_intent.get(primary_call.tool, "actual_vs_target")
    requested_parts = [tool_to_intent.get(c.tool, "actual_vs_target") for c in data_exec_calls[:2]]

    ops_v2: list[QueryOperationV2] = []
    for idx, c_item in enumerate(data_exec_calls[:2], start=1):
        op_kind = (
            "person_summary"
            if c_item.tool == "get_employee_summary"
            else tool_to_intent.get(c_item.tool, "actual_vs_target")
        )
        ops_v2.append(
            QueryOperationV2(
                operation_id=f"op_{idx}",
                kind=op_kind,  # type: ignore[arg-type]
                metric_id=c_item.metric_id,
                direction=c_item.direction if op_kind == "ranking" else None,  # type: ignore[arg-type]
                limit=c_item.limit,
            )
        )

    perf_lvl = primary_call.performance_level if primary_call.performance_level in ("Employee", "Managerial", "Corporate") else "Employee"
    scope_v2 = QueryScopeV2(
        function=primary_call.function or (function_for_team(primary_call.team) if primary_call.team else session_state.function),
        team=primary_call.team,
        position=primary_call.position,
        performance_level=perf_lvl,  # type: ignore[arg-type]
        branches=list(primary_call.branches) if primary_call.branches else ([primary_call.branch] if primary_call.branch else []),
        periods=[primary_call.period] if primary_call.period else [],
        employee_id=primary_call.employee_query if primary_call.tool == "get_employee_summary" else None,
    )
    validated_plan_v2 = ValidatedQueryPlanV2(
        turn_kind="analytical",
        scope=scope_v2,
        operations=ops_v2,
        clarification_code="NONE",
        resolution_source="local_model_router",
        confidence=1.0,
    )
    structured_plan = StructuredQueryPlan(
        intent=primary_intent,  # type: ignore[arg-type]
        requested_parts=requested_parts,
        team=primary_call.team,
        function=primary_call.function,
        position=primary_call.position,
        branch=primary_call.branch,
        compare_branch=primary_call.compare_branch,
        branches=list(primary_call.branches),
        performance_level=primary_call.performance_level,
        metric=primary_call.metric_id,
        periods=[primary_call.period] if primary_call.period else [],
        ranking_direction=primary_call.direction,  # type: ignore[arg-type]
        single_person=primary_call.single_person,
        employee_id=primary_call.employee_query if primary_call.tool == "get_employee_summary" else None,
    )
    confirmed = ConfirmedQueryContext(
        intent=primary_intent,  # type: ignore[arg-type]
        team=primary_call.team,
        function=primary_call.function,
        position=primary_call.position,
        branch=primary_call.branch,
        branches=list(primary_call.branches),
        performance_level=primary_call.performance_level,
        metric_id=primary_call.metric_id,
        periods=[primary_call.period] if primary_call.period else [],
        ranking_direction=primary_call.direction,  # type: ignore[arg-type]
        single_person=primary_call.single_person,
    )
    resolved_state = SessionFilterContext(
        function=primary_call.function or (function_for_team(primary_call.team) if primary_call.team else session_state.function),
        team=primary_call.team or session_state.team,
        position=primary_call.position or session_state.position,
        branch=None if primary_call.tool == "compare_branches" else (primary_call.branch or session_state.branch),
        region=session_state.region,
        performance_level=primary_call.performance_level or session_state.performance_level,
        month=res_month,
        year=res_year,
        employee_id=structured_plan.employee_id or session_state.employee_id,
        last_confirmed_query=confirmed,
    )
    evidence_envelope_v2 = _build_evidence_items_from_results(
        executed_calls=data_exec_calls,
        tool_results=[tr for c, tr in zip(executed_calls, tool_results) if c.tool not in DISCOVERY_EXPLORATION_TOOLS] or tool_results,
    )
    primary_link = next(
        (dl for dl in deep_links if dl.icon_key in ("team", "employee", "bsc")),
        deep_links[0] if deep_links else None,
    )

    return LocalExplorationResult(
        handled=True,
        outcome="answer",
        headline=headline,
        narrative_bullets=bullets,
        visual_cards=visual_cards[:3],
        citations=citations,
        deep_links=deep_links[:3],
        primary_source_link=primary_link,
        suggested_followups=followups,
        structured_query=structured_plan,
        validated_plan_v2=validated_plan_v2,
        typed_evidence=typed_evidence,
        evidence_envelope_v2=evidence_envelope_v2,
        tool_calls=tool_call_records,
        tool_digests=tool_digests,
        resolved_session_state=resolved_state,
        basis_warning=basis_warning,
        unknown_code="none",
        steps_taken=len(step_traces),
        step_traces=step_traces,
        provider_calls=total_provider_calls,
        provider_ms=total_provider_ms,
        planner_calls=planner_calls,
        planner_ms=planner_ms,
        synthesis_calls=synthesis_calls,
        synthesis_ms=synthesis_ms,
        synthesis_validated=synthesis_validated,
        synthesis_fallback_reason=synthesis_fallback_reason,
        database_ms=total_db_ms,
        records_evaluated=total_records,
        # A handled turn still used the rules headline when synthesis could
        # not reach the model, or when the model answered but the draft
        # failed validation. "none" would report that fallback as success,
        # so any synthesis reason other than "none" (accepted) or
        # "not_requested" (never attempted) is reported as-is: transport
        # failures ("timeout", "connection_refused",
        # "unavailable_or_invalid") and unusable drafts
        # ("invalid_response", "invented_number", ...).
        fallback_reason=(
            synthesis_fallback_reason
            if synthesis_fallback_reason not in {"none", "not_requested"}
            else "none"
        ),
    )
