from __future__ import annotations

import functools
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from config.loader import find_team_config_by_db_name
from models.ai_schemas import (
    AiBarItem,
    AiDecisionItem,
    AiEntityListItem,
    AiKpiTableRow,
    AiSpotlightMetadata,
    AiSpotlightMetricTile,
    AiTrendPoint,
    DeepLinkCta,
    QueryRankingsArgs,
    SessionFilterContext,
    SourceCitationPill,
    StructuredVisualCard,
    TypedMetricEvidence,
)
from services.ai.catalog import CatalogMetricDefinition, canonical_team_region, get_ai_catalog, user_can_access_branch
from services.ai.domain_policies import (
    disambiguate_call_center_kpi_label,
    sanitize_untrusted_text,
)
from services.ai.read_only_guard import ReadOnlySessionGuard
from services.corrective_action_service import CorrectiveActionService, OPEN_ACTION_STATUSES
from services.database_record_source import DatabaseRecordSource
from services.insights_service import InsightsService
from services.kpi_aggregation import aggregate_kpi_metric
from services.planning_service import MONTH_ORDER, PlanningService
from services.scoring.monthly_official_scores import (
    OfficialScoreResult,
    ScoreMeasure,
    official_department_score,
    official_team_score,
    round1,
)
from utils.branch_scope import (
    BRANCH_KEYS,
    project_record_for_branch,
    record_matches_branch,
)
from utils.regions import first_region
from utils.report_scope import filter_records_by_scope, function_for_team, function_team_keys, selection_team_keys, user_can_access_team

logger = logging.getLogger(__name__)

_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _period_key_to_month_year(period_key: str) -> tuple[str | None, int | None]:
    match = re.match(r"^(\d{4})-(\d{2})$", str(period_key or "").strip())
    if not match:
        return None, None
    year, month_num = int(match.group(1)), int(match.group(2))
    return (_MONTH_NAMES[month_num - 1] if 1 <= month_num <= 12 else None), year


def is_excluded_by_threshold(threshold: float | None, operator: str | None, value: float | None) -> bool:
    """True when a row fails the requested score filter (unknown scores pass)."""
    if threshold is None or value is None:
        return False
    op = str(operator or "").strip().casefold()
    if op in ("<", "<=", "under", "below", "less than", "at most"):
        return value >= threshold
    if op in (">", ">=", "over", "above", "more than", "exceed", "exceeds", "exceeding", "at least"):
        return value <= threshold
    return False


def _read_only_tool(fn):
    """Run one registry entrypoint under the Phase 3 read-only guard.

    Every public ``execute_*`` tool runs its reads inside
    :class:`services.ai.read_only_guard.ReadOnlySessionGuard`, so a tool
    that tried to flush or stage ORM writes fails with
    ``RuntimeError("AI read tools cannot write to the database")`` instead
    of mutating rows. Contexts without a real session (unit-test doubles)
    leave the guard inactive.
    """

    @functools.wraps(fn)
    def _wrapped(self, *args, **kwargs):
        db = getattr(getattr(self, "ctx", None), "db", None)
        with ReadOnlySessionGuard(db):
            return fn(self, *args, **kwargs)

    return _wrapped


def _team_route_slug(team_name: str | None) -> str:
    norm = str(team_name or "").strip().casefold()
    if norm in ("support positions", "call center", "call center support positions"):
        return "call-center"
    if norm == "offshore admin & management":
        return "administration"
    if norm == "pre-approvals ip offshore":
        return "pre-approvals"
    return norm.replace(" ", "-")


def _display_team_name(team_name: str | None, position: str | None = None) -> str:
    norm = str(team_name or "").strip()
    if norm.casefold() in ("call center", "support positions", "call center support positions"):
        return "Support Positions"
    return norm


def _record_field(record: Any, key: str, default: Any = None) -> Any:
    """Read one field from a scoped record whether it is a dict or an object."""
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


def _record_evaluation_score(record: Any) -> float | None:
    """The stored overall evaluation score of one scoped record, if any."""
    evaluation = _record_field(record, "evaluation", None)
    if evaluation is not None:
        raw = _record_field(evaluation, "score", None)
        try:
            value = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            value = None
        if value is not None and value == value:  # drop NaN, keep real scores
            return value
    raw_direct = _record_field(record, "score", None)
    try:
        direct = float(raw_direct)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return direct if direct == direct else None


def _shared_record_region(record: Any, team_name: str | None) -> str:
    """Effective region of one record: record, then employee, then team.

    Mirrors the DB-row rule (utils.regions.first_region /
    PerformanceRepository._row_region). For the shared teams the team
    fallback is 'All' (catalog.TEAM_DEFAULT_REGION), so a shared record
    with a blank stored region still resolves to the shared region.
    """
    employee = _record_field(record, "employee", None)
    employee_region = _record_field(employee, "region", None) if employee is not None else None
    return first_region(
        _record_field(record, "region", None),
        employee_region,
        canonical_team_region(team_name),
    )


def build_verified_deep_link(
    base_path: str,
    *,
    month: str | None = None,
    year: int | None = None,
    function: str | None = None,
    team: str | None = None,
    position: str | None = None,
    branch: str | None = None,
    performance_level: str | None = None,
    kpi: str | None = None,
    region: str | None = None,
) -> str:
    """Deterministic deep-link builder matching Frontend URL query contracts."""
    params: dict[str, str] = {}
    if month and month != "All":
        params["month"] = str(month)
    if year:
        params["year"] = str(year)
    if function and function != "All":
        params["function"] = str(function)
    if team and team != "All":
        params["team"] = str(team)
    if position and position != "All":
        params["position"] = str(position)
    if branch and branch.casefold() != "all":
        params["branch"] = str(branch).casefold()
    if performance_level and performance_level != "All":
        params["performance_level"] = str(performance_level)
    if kpi:
        params["kpi"] = str(kpi)
    if base_path == "/monthly-presentation":
        params = {}
        if month in MONTH_ORDER and year:
            params["period"] = f"{int(year):04d}-{MONTH_ORDER[month]:02d}"
        if region and region.casefold() in {"egy", "egypt", "uae"}:
            params["region"] = "uae" if region.casefold() == "uae" else "egy"
        parent = function or (function_for_team(team) if team else None)
        if parent:
            params["deepDive"] = re.sub(r"[^a-z0-9]+", "-", parent.casefold()).strip("-")
        if team and parent:
            params["team"] = team
        if position and team:
            params["role"] = position

    query = urlencode(params)
    return f"{base_path}?{query}" if query else base_path


@dataclass
class ToolExecutionResult:
    tool_name: str
    arguments: dict[str, Any]
    records_evaluated: int = 0
    digest: dict[str, Any] = field(default_factory=dict)
    visual_cards: list[StructuredVisualCard] = field(default_factory=list)
    citations: list[SourceCitationPill] = field(default_factory=list)
    deep_links: list[DeepLinkCta] = field(default_factory=list)
    typed_evidence: list[TypedMetricEvidence] = field(default_factory=list)
    resolved_month: str | None = None
    resolved_year: int | None = None
    basis_warning: str | None = None
    guardrail_triggered: bool = False


class ToolExecutionContext:
    """Closed-over security and database execution context. Never exposed to the LLM as an argument."""

    def __init__(
        self,
        *,
        db: Session,
        scope: dict[str, Any],
        session_state: SessionFilterContext,
    ) -> None:
        self.db = db
        self.scope = scope
        self.session_state = session_state
        self.source = DatabaseRecordSource(db, scope=scope)
        self.planning_service = PlanningService(self.source, db=db)
        self.insights_service = InsightsService(self.source, self.planning_service, db=db)
        self._scoped_records: list[Any] | None = None

    def get_scoped_records(self) -> list[Any]:
        if self._scoped_records is None:
            self._scoped_records = filter_records_by_scope(
                self.source.get_all(scope=self.scope),
                self.scope,
            )
        return self._scoped_records

    def resolve_filters(
        self,
        *,
        team: str | None = None,
        function: str | None = None,
        position: str | None = None,
        branch: str | None = None,
        performance_level: str | None = None,
        month: str | None = None,
        year: int | None = None,
    ) -> dict[str, Any]:
        eff_team = team if team not in (None, "", "All") else (
            self.session_state.team if self.session_state.team not in (None, "", "All") else None
        )
        eff_pos = position if position not in (None, "", "All", "all") else (
            self.session_state.position if self.session_state.position not in (None, "", "All", "all") else None
        )
        eff_fn = function if function not in (None, "", "All") else (
            self.session_state.function if self.session_state.function not in (None, "", "All") else None
        )
        if eff_team and not eff_fn:
            from services.ai.catalog import function_for_team
            eff_fn = function_for_team(eff_team)
        if eff_team and eff_team.casefold() not in ("inbound", "outbound", "call center", "support positions"):
            if eff_fn and eff_fn.casefold() == "call center":
                eff_fn = None

        eff_branch = branch if branch not in (None, "", "all", "All") else (
            self.session_state.branch if self.session_state.branch not in (None, "", "all", "All") else None
        )
        if eff_branch:
            eff_branch = eff_branch.strip().casefold()
            if eff_branch not in BRANCH_KEYS:
                eff_branch = None

        allowed_branches = self.scope.get("accessible_branches")
        if allowed_branches is None:
            allowed_branches = self.scope.get("allowed_branches")
        if eff_branch is None and isinstance(allowed_branches, (list, set, tuple)) and len(allowed_branches) == 1:
            eff_branch = next(iter(allowed_branches)).strip().casefold()

        eff_level = performance_level if performance_level not in (None, "", "All") else (
            self.session_state.performance_level
            if self.session_state.performance_level not in (None, "", "All")
            else None
        )
        if eff_team and eff_team.casefold() in ("crm", "nursing", "pmo") and eff_level in (None, "", "Employee"):
            eff_level = "Corporate"

        eff_month = month if month not in (None, "", "All") else (
            self.session_state.month if self.session_state.month not in (None, "", "All") else None
        )
        eff_year = year if year is not None else self.session_state.year

        if eff_month and not eff_year:
            eff_year = self._infer_latest_year_for_month(eff_month)
        elif eff_year and not eff_month:
            eff_year = None

        return {
            "team": eff_team,
            "function": eff_fn,
            "position": eff_pos,
            "branch": eff_branch,
            "performance_level": eff_level,
            "month": eff_month,
            "year": eff_year,
            "region": None if eff_branch else (
                self.session_state.region
                if self.session_state.region and self.session_state.region.strip().casefold() not in ("all", "")
                else None
            ),
        }

    def _infer_latest_year_for_month(self, month_name: str) -> int:
        try:
            records = self.get_scoped_records()
            years = [
                int(getattr(r, "year", 0) or (r.get("year") if isinstance(r, dict) else 0) or 0)
                for r in records
                if str(getattr(r, "month", "") or (r.get("month") if isinstance(r, dict) else "")).casefold()
                == month_name.casefold()
            ]
            valid_years = [y for y in years if y >= 2000]
            if valid_years:
                return max(valid_years)
        except Exception:
            pass
        return 2026


class DeterministicToolRegistry:
    """Executes read-only domain tools and builds zero-hallucination StructuredVisualCards."""

    AUTHORIZED_MODEL_LED_TOOLS: dict[str, dict[str, Any]] = {
        "discover_pms_catalog": {
            "type": "object",
            "description": (
                "Search the live, authorized PMS catalog for canonical departments, teams, positions (roles), "
                "branches, KPI metrics/aliases, authorized employees, and available published periods. "
                "Use when a name/alias is unfamiliar or ambiguous, or to verify available periods before querying."
            ),
            "properties": {
                "query": {"type": "string", "description": "Optional search term, entity name, or KPI alias"},
                "kind": {
                    "type": "string",
                    "enum": ["all", "department", "team", "position", "branch", "metric", "employee", "periods"],
                },
                "region": {"type": "string", "enum": ["UAE", "EGY", "KSA"]},
                "department": {"type": "string"},
                "team": {"type": "string"},
                "performance_level": {"type": "string", "enum": ["Employee", "Managerial", "Corporate"]},
            },
            "required": [],
            "additionalProperties": False,
        },
        "query_rankings": {
            "type": "object",
            "description": (
                "Composable ranking engine. Use for best/worst/top/bottom/arrange questions "
                "about departments, teams, positions, branches or employees, with region, grouping, "
                "counts, sort order and score thresholds."
            ),
            "properties": {
                "entity": {"type": "string", "enum": ["department", "team", "position", "branch", "employee"]},
                "sort_order": {"type": "string", "enum": ["desc", "asc"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "group_by": {"type": "string", "enum": ["none", "department", "team", "branch"]},
                "per_group_limit": {"type": "integer", "minimum": 1, "maximum": 20},
                "region": {"type": "string", "enum": ["UAE", "EGY", "KSA"]},
                "department": {"type": "string"},
                "team": {"type": "string"},
                "position": {"type": "string"},
                "branch": {"type": "string"},
                "performance_level": {"type": "string", "enum": ["Employee", "Managerial", "Corporate"]},
                "metric_id": {"type": "string"},
                "period": {"type": "string", "pattern": r"^20\d{2}-(0[1-9]|1[0-2])$"},
                "score_threshold": {"type": "number"},
                "threshold_operator": {"type": "string", "enum": ["<", "<=", ">", ">="]},
            },
            "required": ["entity"],
            "additionalProperties": False,
        },
        "read_employee_metric": {
            "type": "object",
            "description": "Read a specific KPI metric or score for an employee in a given period.",
            "properties": {
                "employee_id": {"type": "string", "description": "PMS employee ID (e.g., EMP101) or employee name"},
                "employee_name": {"type": "string", "description": "Employee full name (e.g., Nadia Fadel)"},
                "metric_id": {"type": "string", "description": "Metric ID from catalog or name (e.g., inbound:waitingtime, waitingtime, bookings_count)"},
                "period": {"type": "string", "pattern": r"^20\d{2}-(0[1-9]|1[0-2])$", "description": "Period key like 2026-09"},
                "team": {"type": "string", "description": "Team name (e.g., Inbound, Coding)"},
                "branch": {"type": "string", "description": "Branch name (e.g., dubai, sharjah)"},
            },
            "required": ["metric_id"],
            "additionalProperties": False,
        },
        "get_employee_history": {
            "type": "object",
            "description": "Retrieve multi-month historical trend records for an employee.",
            "properties": {
                "employee_id": {"type": "string", "description": "PMS employee ID or employee name"},
                "employee_name": {"type": "string", "description": "Employee full name"},
                "metric_id": {"type": "string", "description": "Metric ID from catalog or name (e.g., inbound:waitingtime, waitingtime)"},
                "periods": {"type": "array", "items": {"type": "string", "pattern": r"^20\d{2}-(0[1-9]|1[0-2])$"}, "description": "Optional list of period keys"},
                "team": {"type": "string"},
                "branch": {"type": "string"},
            },
            "required": [],
            "additionalProperties": False,
        },
        "compare_branches": {
            "type": "object",
            "description": "Read a metric for one branch or compare metrics, booking counts, or overall scores across UAE branches.",
            "properties": {
                "team": {"type": "string", "description": "Team/function name"},
                "branches": {"type": "array", "items": {"type": "string", "enum": ["dubai", "sharjah", "ajman", "clinics"]}, "minItems": 1, "maxItems": 4},
                "period": {"type": "string", "pattern": r"^20\d{2}-(0[1-9]|1[0-2])$"},
                "metric": {"type": "string", "description": "Metric ID for comparison (e.g., bookings_count, overall_score)"},
            },
            "required": ["team", "period"],
            "additionalProperties": False,
        },
        "get_score_trend": {
            "type": "object",
            "description": "Retrieve historical trend trajectory across months for an employee, position/role, or team.",
            "properties": {
                "team": {"type": "string"},
                "position": {"type": "string", "description": "Optional position/role name within the team"},
                "metric_id": {"type": "string"},
                "periods": {"type": "array", "items": {"type": "string", "pattern": r"^20\d{2}-(0[1-9]|1[0-2])$"}, "minItems": 2, "maxItems": 12},
                "branch": {"type": "string"},
                "employee_id": {"type": "string"},
                "employee_name": {"type": "string"},
                "performance_level": {"type": "string", "enum": ["Employee", "Managerial", "Corporate"]},
            },
            "required": [],
            "additionalProperties": False,
        },
        "rank_employees": {
            "type": "object",
            "description": "Rank and compare employee contributions on a metric or overall score within a team.",
            "properties": {
                "team": {"type": "string"},
                "metric_id": {"type": "string"},
                "period": {"type": "string", "pattern": r"^20\d{2}-(0[1-9]|1[0-2])$"},
                "branch": {"type": "string"},
                "performance_level": {"type": "string", "enum": ["Employee", "Managerial", "Corporate"]},
                "direction": {"type": "string", "enum": ["best", "worst"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                "include_ties": {"type": "boolean"},
                "score_threshold": {"type": "number"},
                "threshold_operator": {
                    "type": "string",
                    "enum": [">", ">=", "<", "above", "over", "exceed", "exceeding", "more than", "at least", "below", "under", "less than"],
                },
            },
            "required": ["team", "period"],
            "additionalProperties": False,
        },
        "get_kpi_diagnosis": {
            "type": "object",
            "description": "Diagnose an employee's, position's, or team's KPI achievement and operational volume breakdowns.",
            "properties": {
                "employee_id": {"type": "string", "description": "PMS employee ID when diagnosing one employee"},
                "employee_name": {"type": "string", "description": "Employee full name when diagnosing one employee"},
                "team": {"type": "string"},
                "position": {"type": "string", "description": "Optional position/role name within the team"},
                "metric_id": {"type": "string"},
                "period": {"type": "string", "pattern": r"^20\d{2}-(0[1-9]|1[0-2])$"},
                "branch": {"type": "string"},
                "compare_branch": {"type": "string"},
                "performance_level": {"type": "string", "enum": ["Employee", "Managerial", "Corporate"]},
            },
            "required": ["team", "period"],
            "additionalProperties": False,
        },
        "explain_scoring_rules_and_targets": {
            "type": "object",
            "description": "Explain canonical KPI scoring rules, weights, targets, achievement cap, and grade thresholds scoped to the caller.",
            "properties": {
                "kpi_name": {"type": "string", "description": "Optional KPI name to focus on"},
            },
            "required": [],
            "additionalProperties": False,
        },
        "search_pms_guide": {
            "type": "object",
            "description": "Search the local PMS System Guide markdown knowledge base for general system concepts: Grade A–E definitions, KPI scoring formula and 100% cap, Gap vs Gap Share, Executive Summary vs Monthly Review, Teams at Risk status badges, Balanced Scorecard and performance levels, RBAC roles/regions/branches, KPI glossary, and screen workflows.",
            "properties": {
                "query": {"type": "string", "description": "User question or PMS concept to look up in the system guide"},
                "page_id": {"type": "string", "description": "Optional guide page_id filter"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "simulate_kpi_improvement": {
            "type": "object",
            "description": "Deterministic What-If simulation: project score and grade change if a KPI improves by a given amount, respecting GLOBAL_KPI_ACHIEVEMENT_CAP and lower_better formulas.",
            "properties": {
                "employee_id": {"type": "string", "description": "Employee ID (auto-bound to caller for self-only users)"},
                "kpi_name": {"type": "string", "description": "KPI name or key to simulate"},
                "improvement_pct": {"type": "number", "description": "Improvement amount in KPI units / percentage points"},
            },
            "required": ["kpi_name", "improvement_pct"],
            "additionalProperties": False,
        },
        "get_corrective_actions": {
            "type": "object",
            "description": (
                "Inspect saved corrective actions and follow-up plans recorded in PMS for a specific employee, team, or function. "
                "Use whenever the user asks what corrective action was done, assigned, saved, open, or overdue for an employee or team."
            ),
            "properties": {
                "employee_id": {"type": "string", "description": "PMS employee ID when checking one employee's saved actions"},
                "employee_name": {"type": "string", "description": "Employee full or partial name when checking one employee's saved actions"},
                "team": {"type": "string", "description": "Team name (e.g., Outbound, Inbound)"},
                "function": {"type": "string", "description": "Function/department name"},
                "period": {"type": "string", "pattern": r"^20\d{2}-(0[1-9]|1[0-2])$", "description": "Optional period key like 2026-10"},
                "state": {"type": "string", "enum": ["open", "overdue", "due_soon", "upcoming", "completed", "closed"]},
                "open_only": {"type": "boolean"},
            },
            "required": [],
            "additionalProperties": False,
        },
    }

    def __init__(self, ctx: ToolExecutionContext) -> None:
        self.ctx = ctx

    @_read_only_tool
    def execute_model_led_tool(
        self,
        tool_name: str,
        tool_arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        if tool_name in ("get_employee_metric", "read_metric"):
            tool_name = "read_employee_metric"
        elif tool_name in ("read_employee_history", "get_history"):
            tool_name = "get_employee_history"

        if tool_name not in self.AUTHORIZED_MODEL_LED_TOOLS:
            raise ValueError(f"Unknown model-led tool '{tool_name}'")

        if "metric_id" not in tool_arguments:
            m_val = tool_arguments.get("metric") or tool_arguments.get("metric_type") or tool_arguments.get("kpi") or tool_arguments.get("kpi_key")
            if m_val:
                tool_arguments["metric_id"] = m_val
        for metric_arg in ("metric_id", "requested_metric_id"):
            metric_leaf = str(tool_arguments.get(metric_arg) or "").strip().casefold().rsplit(":", 1)[-1]
            if metric_leaf in ("performance", "score", "overall score", "overall_score", "pms score", "overall"):
                tool_arguments[metric_arg] = "overall_score"

        schema = self.AUTHORIZED_MODEL_LED_TOOLS[tool_name]
        for req_field in schema.get("required", []):
            if req_field not in tool_arguments or tool_arguments[req_field] is None:
                raise ValueError(f"Missing required argument '{req_field}' for tool '{tool_name}'")

        # Parse period if provided
        period_str = str(tool_arguments.get("period") or "").strip()
        month_str = None
        year_int = None
        if period_str:
            iso_m = re.match(r"^(20\d{2})-(0[1-9]|1[0-2])$", period_str)
            if iso_m:
                year_int = int(iso_m.group(1))
                m_num = int(iso_m.group(2))
                from services.ai.entity_resolver import REVERSE_MONTHS_BY_NUM
                month_str = REVERSE_MONTHS_BY_NUM.get(m_num)
            elif any(m in period_str for m in MONTH_ORDER):
                for m in MONTH_ORDER:
                    if m.casefold() in period_str.casefold():
                        month_str = m
                        break
                yr_m = re.search(r"20\d{2}", period_str)
                year_int = int(yr_m.group(0)) if yr_m else None

        # Pre-query RBAC checks
        scope = self.ctx.scope
        # 1. is_self_only check
        if scope.get("is_self_only"):
            caller_emp_id = str(scope.get("employee_id") or "").strip()
            if tool_name in ("explain_scoring_rules_and_targets", "discover_pms_catalog", "search_pms_guide"):
                pass  # Strictly scoped to caller's own authorized catalog/guide/employee record; never exposes peer data
            elif tool_name == "simulate_kpi_improvement":
                req_emp = str(tool_arguments.get("employee_id") or "").strip()
                if req_emp and req_emp.casefold() != caller_emp_id.casefold():
                    raise PermissionError("Self-only scope restriction: cannot simulate another employee's KPIs.")
                if not caller_emp_id:
                    raise PermissionError("Your account isn't linked to an employee profile yet. Please contact your manager.")
                tool_arguments["employee_id"] = caller_emp_id
            elif tool_name == "get_corrective_actions":
                req_emp = str(tool_arguments.get("employee_id") or "").strip()
                if req_emp and req_emp.casefold() != caller_emp_id.casefold():
                    raise PermissionError("Self-only scope restriction: cannot inspect another employee's corrective actions.")
                if not caller_emp_id:
                    raise PermissionError("Your account isn't linked to an employee profile yet. Please contact your manager.")
                tool_arguments["employee_id"] = caller_emp_id
            else:
                target_emp_id = str(tool_arguments.get("employee_id") or "").strip()
                if not target_emp_id or target_emp_id.casefold() != caller_emp_id.casefold():
                    raise PermissionError("Self-only scope restriction: cannot access records of other employees or aggregate team metrics.")
                if tool_name in ("compare_branches", "rank_employees") or (
                    tool_name == "get_kpi_diagnosis"
                    and not (tool_arguments.get("employee_id") or tool_arguments.get("employee_name"))
                ):
                    raise PermissionError("Self-only scope restriction: employee cannot access organizational analytics tools.")

        # 2. Branch restriction check
        acc_branches = scope.get("accessible_branches") or scope.get("allowed_branches")
        if acc_branches:
            acc_set = {str(b).strip().casefold() for b in acc_branches if str(b).strip()}
            req_branch = str(tool_arguments.get("branch") or "").strip().casefold()
            if req_branch and req_branch not in acc_set and req_branch != "all":
                raise PermissionError(f"Branch access restriction: cannot access branch '{req_branch}'.")
            if tool_name == "compare_branches":
                req_branches = [str(b).strip().casefold() for b in tool_arguments.get("branches", [])]
                disallowed = [b for b in req_branches if b not in acc_set]
                if disallowed:
                    raise PermissionError(f"Branch access restriction: branches {disallowed} are not accessible.")

        # 3. Team access check
        req_team = str(tool_arguments.get("team") or "").strip()
        if req_team and not user_can_access_team(scope, req_team):
            raise PermissionError(f"Team access restriction: user cannot access team '{req_team}'.")

        # Dispatch
        if tool_name == "discover_pms_catalog":
            return self.execute_discover_pms_catalog(
                query=tool_arguments.get("query"),
                kind=tool_arguments.get("kind") or "all",
                region=tool_arguments.get("region"),
                department=tool_arguments.get("department"),
                team=tool_arguments.get("team"),
                performance_level=tool_arguments.get("performance_level"),
            )
        if tool_name == "query_rankings":
            return self.execute_query_rankings(
                entity=tool_arguments.get("entity") or "department",
                sort_order=tool_arguments.get("sort_order") or "desc",
                limit=int(tool_arguments.get("limit") or 10),
                group_by=tool_arguments.get("group_by") or "none",
                per_group_limit=int(tool_arguments.get("per_group_limit") or 5),
                region=tool_arguments.get("region"),
                department=tool_arguments.get("department"),
                team=tool_arguments.get("team"),
                position=tool_arguments.get("position"),
                branch=tool_arguments.get("branch"),
                performance_level=tool_arguments.get("performance_level"),
                metric_id=tool_arguments.get("metric_id") or tool_arguments.get("metric"),
                period=period_str or None,
                score_threshold=tool_arguments.get("score_threshold"),
                threshold_operator=tool_arguments.get("threshold_operator"),
                score_measure=tool_arguments.get("score_measure"),
            )
        if tool_name == "read_employee_metric":
            emp_q = str(tool_arguments.get("employee_name") or tool_arguments.get("employee_id") or "").strip()
            return self.execute_agent_spotlight_and_trend(
                team=tool_arguments.get("team") or self.ctx.session_state.team,
                branch=tool_arguments.get("branch"),
                performance_level=tool_arguments.get("performance_level"),
                month=month_str,
                year=year_int,
                kpi=tool_arguments.get("requested_metric_id") or tool_arguments.get("metric_id"),
                employee_query=emp_q,
                single_person=True,
                months_window=1,
            )
        elif tool_name == "get_employee_history":
            emp_q = str(tool_arguments.get("employee_name") or tool_arguments.get("employee_id") or "").strip()
            return self.execute_agent_spotlight_and_trend(
                team=tool_arguments.get("team") or self.ctx.session_state.team,
                branch=tool_arguments.get("branch"),
                performance_level=tool_arguments.get("performance_level"),
                month=month_str,
                year=year_int,
                kpi=tool_arguments.get("requested_metric_id") or tool_arguments.get("metric_id"),
                employee_query=emp_q,
                single_person=True,
                months_window=6,
            )
        elif tool_name == "compare_branches":
            brs = tool_arguments.get("branches") or [
                value for value in (tool_arguments.get("branch"), tool_arguments.get("compare_branch")) if value
            ] or ["dubai", "sharjah", "ajman", "clinics"]
            return self.execute_kpi_diagnosis_and_trends(
                team=tool_arguments.get("team") or self.ctx.session_state.team,
                branches=brs,
                asks_branch_comparison=True,
                kpi=tool_arguments.get("metric") or "overall_score",
                month=month_str,
                year=year_int,
            )
        elif tool_name == "get_score_trend":
            emp_q = str(tool_arguments.get("employee_name") or tool_arguments.get("employee_id") or "").strip()
            pos_arg = tool_arguments.get("position") or self.ctx.session_state.position
            raw_br = tool_arguments.get("branch")
            clean_br = None if str(raw_br or "").strip().casefold() in {"uae", "egy", "egypt", "ksa", "emirates", "all", "all branches"} else raw_br
            if emp_q:
                return self.execute_agent_spotlight_and_trend(
                    team=tool_arguments.get("team") or self.ctx.session_state.team,
                    position=pos_arg,
                    branch=clean_br,
                    performance_level=tool_arguments.get("performance_level"),
                    month=month_str,
                    year=year_int,
                    kpi=tool_arguments.get("requested_metric_id") or tool_arguments.get("metric_id"),
                    employee_query=emp_q,
                    single_person=True,
                    months_window=6,
                )
            else:
                return self.execute_team_metric_trend(
                    team=tool_arguments.get("team") or self.ctx.session_state.team,
                    position=pos_arg,
                    branch=clean_br,
                    performance_level=tool_arguments.get("performance_level"),
                    kpi=tool_arguments.get("requested_metric_id") or tool_arguments.get("metric_id"),
                    period=tool_arguments.get("period"),
                    periods=tool_arguments.get("periods"),
                    score_measure=tool_arguments.get("score_measure"),
                )
        elif tool_name == "rank_employees":
            return self.execute_people_contribution_and_rankings(
                team=tool_arguments.get("team") or self.ctx.session_state.team,
                branch=tool_arguments.get("branch"),
                performance_level=tool_arguments.get("performance_level"),
                kpi=tool_arguments.get("metric_id"),
                limit=tool_arguments.get("limit", 6),
                include_ties=tool_arguments.get("include_ties", True),
                direction=tool_arguments.get("direction") or "best",
                raw_sort_order=tool_arguments.get("raw_sort_order"),
                month=month_str,
                year=year_int,
                direct_rank_fallback=True,
                score_threshold=tool_arguments.get("score_threshold"),
                threshold_operator=tool_arguments.get("threshold_operator"),
            )
        elif tool_name == "get_kpi_diagnosis":
            employee_query = str(tool_arguments.get("employee_name") or tool_arguments.get("employee_id") or "").strip()
            pos_arg = tool_arguments.get("position") or self.ctx.session_state.position
            raw_br = tool_arguments.get("branch")
            clean_br = None if str(raw_br or "").strip().casefold() in {"uae", "egy", "egypt", "ksa", "emirates", "all", "all branches"} else raw_br
            if employee_query:
                result = self.execute_agent_spotlight_and_trend(
                    team=tool_arguments.get("team") or self.ctx.session_state.team,
                    position=pos_arg,
                    branch=clean_br,
                    performance_level=tool_arguments.get("performance_level"),
                    month=month_str,
                    year=year_int,
                    kpi=tool_arguments.get("requested_metric_id") or tool_arguments.get("metric_id"),
                    employee_query=employee_query,
                    single_person=True,
                    months_window=1,
                )
                result.tool_name = "get_kpi_diagnosis"
                result.arguments = {
                    "employee_id": tool_arguments.get("employee_id"),
                    "employee_name": tool_arguments.get("employee_name"),
                    "team": tool_arguments.get("team"),
                    "position": pos_arg,
                    "branch": clean_br,
                    "metric_id": tool_arguments.get("metric_id"),
                    "period": period_str or None,
                }
                return result
            return self.execute_kpi_diagnosis_and_trends(
                team=tool_arguments.get("team") or self.ctx.session_state.team,
                position=pos_arg,
                branch=clean_br,
                compare_branch=tool_arguments.get("compare_branch"),
                kpi=tool_arguments.get("metric_id"),
                month=month_str,
                year=year_int,
                performance_level=tool_arguments.get("performance_level"),
                score_measure=tool_arguments.get("score_measure"),
            )
        elif tool_name == "get_corrective_actions":
            return self.execute_corrective_actions_status(
                team=tool_arguments.get("team") or self.ctx.session_state.team,
                function=tool_arguments.get("function") or self.ctx.session_state.function,
                month=month_str,
                year=year_int,
                state=tool_arguments.get("state"),
                open_only=bool(tool_arguments.get("open_only")),
                employee_id=tool_arguments.get("employee_id"),
                employee_name=tool_arguments.get("employee_name"),
                apply_period_filter=bool(month_str or year_int),
            )
        elif tool_name == "explain_scoring_rules_and_targets":
            from services.ai.identity_service import build_passport
            from services.ai.scoring_rules_explainer import ScoreRulesExplainer

            passport = scope.get("passport") or build_passport(scope, db=self.ctx.db)
            kpi_filter = str(tool_arguments.get("kpi_name") or "").strip() or None
            explainer = ScoreRulesExplainer(self.ctx.db)
            rules_data = explainer.explain(passport, kpi_name=kpi_filter)
            return ToolExecutionResult(
                tool_name="explain_scoring_rules_and_targets",
                arguments={"kpi_name": kpi_filter},
                records_evaluated=len(rules_data.get("weights") or []),
                digest={
                    **rules_data,
                    "summary": f"Loaded canonical scoring rules (cap={rules_data.get('achievement_cap')}, grades={rules_data.get('grade_thresholds')}).",
                },
            )
        elif tool_name == "search_pms_guide":
            query_str = str(tool_arguments.get("query") or "").strip()
            page_filter = str(tool_arguments.get("page_id") or "").strip() or None
            return self.execute_guide_lookup(query=query_str, page_id=page_filter)
        elif tool_name == "simulate_kpi_improvement":
            from services.ai.agent_360_service import Agent360Service

            emp_code = str(tool_arguments.get("employee_id") or scope.get("employee_id") or "").strip()
            kpi_name = str(tool_arguments.get("kpi_name") or "").strip()
            imp_pct = float(tool_arguments.get("improvement_pct") or 0.0)
            sim = Agent360Service(self.ctx.db).simulate_what_if(emp_code, kpi_name, imp_pct) if emp_code else None
            if sim is None:
                return ToolExecutionResult(
                    tool_name="simulate_kpi_improvement",
                    arguments={"employee_id": emp_code, "kpi_name": kpi_name, "improvement_pct": imp_pct},
                    records_evaluated=0,
                    digest={
                        "error": "Unable to simulate the requested KPI for this employee profile.",
                        "summary": f"No simulatable KPI '{kpi_name}' found for employee '{emp_code}'.",
                    },
                )
            return ToolExecutionResult(
                tool_name="simulate_kpi_improvement",
                arguments={"employee_id": emp_code, "kpi_name": kpi_name, "improvement_pct": imp_pct},
                records_evaluated=1,
                digest={
                    **sim,
                    "summary": (
                        f"Simulating {kpi_name} by {imp_pct}: score {sim['current_score']}% ({sim['current_grade']}) "
                        f"-> {sim['projected_score']}% ({sim['projected_grade']}, delta {sim['score_delta']:+.2f} pts)."
                    ),
                },
            )
        raise ValueError(f"Unhandled tool '{tool_name}'")

    def _resolve_cohort_score_result(
        self,
        *,
        region: str | None,
        month: str | None,
        year: int | None,
        team: str | None,
        function: str | None,
        position: str | None,
        branch: str | None,
        performance_level: str | None,
        score_measure: str | None = None,
    ) -> OfficialScoreResult | None:
        """Compute official Monthly Review OR employee-average score for a scoped cohort."""
        if position or (not team and not function):
            return None
        measure: ScoreMeasure = "employee_average" if score_measure == "employee_average" else "official"
        locked_teams = selection_team_keys(team) if team else None
        locked_function = function_team_keys(function) if (function and not team) else None
        req_level = str(performance_level or "Employee").casefold()
        cohort = []
        for record in self.ctx.get_scoped_records():
            rec_team = str(_record_field(record, "team", "") or "")
            if locked_teams is not None and rec_team.casefold() not in locked_teams:
                continue
            if locked_function is not None and rec_team.casefold() not in locked_function:
                continue
            if region and _shared_record_region(record, rec_team).casefold() != str(region).casefold():
                continue
            if month and str(_record_field(record, "month", "") or "").casefold() != str(month).casefold():
                continue
            if year and int(_record_field(record, "year", 0) or 0) != int(year):
                continue
            if str(_record_field(record, "performance_level", "Employee") or "Employee").casefold() != req_level:
                continue
            if branch and not record_matches_branch(record, branch):
                continue
            cohort.append(project_record_for_branch(record, branch))
        if not cohort:
            return None
        loc = branch or "all"
        if team:
            return official_team_score(cohort, team, measure=measure, location=loc)
        return official_department_score(str(function), cohort, measure=measure, location=loc)

    def execute_team_metric_trend(
        self,
        *,
        team: str,
        position: str | None = None,
        branch: str | None,
        performance_level: str | None,
        kpi: str | None,
        period: str | None,
        periods: list[str] | None = None,
        score_measure: str | None = None,
    ) -> ToolExecutionResult:
        """Return team-level or position-level evidence for each requested or recently available period."""
        resolved = self.ctx.resolve_filters(
            team=team,
            position=position,
            branch=branch,
            performance_level=performance_level,
        )

        def _parse_period(raw: str) -> tuple[int, int, str] | None:
            text = str(raw or "").strip()
            iso = re.match(r"^(20\d{2})-(\d{1,2})$", text)
            if iso:
                year_val, month_num = int(iso.group(1)), int(iso.group(2))
                month_name = next((name for name, number in MONTH_ORDER.items() if number == month_num), None)
                return (year_val, month_num, month_name) if month_name else None
            human = re.match(r"^([A-Za-z]+)\s+(20\d{2})$", text)
            if human:
                month_name = next((name for name in MONTH_ORDER if name.casefold() == human.group(1).casefold()), None)
                if month_name:
                    return (int(human.group(2)), MONTH_ORDER[month_name], month_name)
            return None

        scoped_records = self.ctx.get_scoped_records()
        available: set[tuple[int, int, str]] = set()
        team = resolved["team"]
        if not team:
            return ToolExecutionResult(tool_name="get_score_trend", arguments=resolved,
                                       digest={"unavailable_reason": "Choose a team for its performance trend."})
        team_keys = selection_team_keys(team)
        target_pos = resolved.get("position")
        for record in scoped_records:
            record_team = str(_record_field(record, "team", "") or "").strip().casefold()
            if record_team != team.casefold() and record_team not in {key.casefold() for key in team_keys}:
                continue
            record_level = str(_record_field(record, "performance_level", "Employee") or "Employee").casefold()
            if performance_level and record_level != performance_level.casefold():
                continue
            if target_pos:
                record_pos = str(_record_field(record, "position", "") or "").strip().casefold()
                if record_pos != str(target_pos).strip().casefold():
                    continue
            if resolved["region"]:
                record_region = _shared_record_region(record, record_team).strip().casefold()
                if record_region != str(resolved["region"]).strip().casefold():
                    continue
            if resolved["branch"] and not record_matches_branch(record, resolved["branch"]):
                continue
            month_name = str(_record_field(record, "month", "") or "").strip()
            year_value = int(_record_field(record, "year", 0) or 0)
            month_num = next((number for name, number in MONTH_ORDER.items() if name.casefold() == month_name.casefold()), 0)
            if month_num and year_value:
                available.add((year_value, month_num, month_name))

        requested_periods = [parsed for parsed in (_parse_period(value) for value in (periods or [])) if parsed]
        if len(requested_periods) < 2:
            current = _parse_period(period or "")
            if current is None and resolved["month"] and resolved["year"]:
                current = _parse_period(f"{resolved['month']} {resolved['year']}")
            if current:
                eligible = sorted(item for item in available if (item[0], item[1]) <= (current[0], current[1]))
                requested_periods = eligible[-6:] if eligible else [current]
        requested_periods = sorted(set(requested_periods))
        if not requested_periods:
            fallback = _parse_period(period or "")
            if fallback:
                requested_periods = [fallback]

        period_results: list[tuple[tuple[int, int, str], ToolExecutionResult]] = []
        for year_value, _month_num, month_name in requested_periods:
            period_results.append(
                (
                    (year_value, _month_num, month_name),
                    self.execute_kpi_diagnosis_and_trends(
                        team=team,
                        position=target_pos,
                        branch=branch,
                        performance_level=performance_level,
                        asks_period_comparison=False,
                        kpi=kpi,
                        month=month_name,
                        year=year_value,
                        score_measure=score_measure,
                    ),
                )
            )
        if not period_results:
            return self.execute_kpi_diagnosis_and_trends(
                team=team,
                position=target_pos,
                branch=branch,
                performance_level=performance_level,
                asks_period_comparison=True,
                kpi=kpi,
                score_measure=score_measure,
            )

        target_norm = re.sub(r"[^a-z0-9]", "", str(kpi or "").casefold().rsplit(":", 1)[-1])

        def _matches_requested_metric(evidence: TypedMetricEvidence) -> bool:
            values = (
                evidence.metric_id.rsplit(":", 1)[-1],
                evidence.kpi_key,
                evidence.display_name,
            )
            return any(
                target_norm == re.sub(r"[^a-z0-9]", "", value.casefold())
                or target_norm in re.sub(r"[^a-z0-9]", "", value.casefold())
                or re.sub(r"[^a-z0-9]", "", value.casefold()) in target_norm
                for value in values
                if value
            )

        history_evidence: list[TypedMetricEvidence] = []
        for (_year_value, _month_num, _month_name), result in period_results:
            match = next(
                (
                    evidence
                    for evidence in result.typed_evidence
                    if evidence.actual is not None
                    and not evidence.employee_id
                    and _matches_requested_metric(evidence)
                ),
                None,
            )
            if match:
                history_evidence.append(match)

        latest_result = period_results[-1][1]
        latest_result.typed_evidence = [
            evidence
            for evidence in latest_result.typed_evidence
            if not _matches_requested_metric(evidence)
        ] + history_evidence
        latest_result.tool_name = "get_score_trend"
        latest_result.arguments = {
            "team": team,
            "position": target_pos,
            "branch": branch,
            "performance_level": performance_level,
            "metric_id": kpi,
            "periods": [f"{year_value:04d}-{month_num:02d}" for year_value, month_num, _ in requested_periods],
        }
        if not kpi or str(kpi).strip().casefold() in {"overall_score", "score", "overall"}:
            spotlight_res = self.execute_team_trend_spotlight(
                team=team,
                position=target_pos,
                branch=branch,
                month=requested_periods[-1][2] if requested_periods else None,
                year=requested_periods[-1][0] if requested_periods else None,
                kpi=None,
                months_window=max(6, len(requested_periods)),
            )
            if spotlight_res.visual_cards:
                latest_result.visual_cards = spotlight_res.visual_cards
            if isinstance(spotlight_res.digest, dict) and spotlight_res.digest.get("scope"):
                if isinstance(latest_result.digest, dict):
                    latest_result.digest["scope"] = spotlight_res.digest["scope"]
                    latest_result.digest["team_trend_spotlight"] = spotlight_res.digest.get("team_trend_spotlight")
        latest_result.digest = {
            **(latest_result.digest if isinstance(latest_result.digest, dict) else {}),
            "team_metric_history": [
                {
                    "period": evidence.period,
                    "metric_id": evidence.metric_id,
                    "display_name": evidence.display_name,
                    "actual": evidence.actual,
                    "actual_display": evidence.actual_display,
                    "unit": evidence.unit,
                    "sample_size": evidence.sample_size,
                }
                for evidence in history_evidence
            ],
        }
        return latest_result

    @_read_only_tool
    def execute_executive_and_priority_insights(
        self,
        *,
        team: str | None = None,
        function: str | None = None,
        position: str | None = None,
        branch: str | None = None,
        performance_level: str | None = None,
        month: str | None = None,
        year: int | None = None,
        score_measure: str | None = None,
    ) -> ToolExecutionResult:
        resolved = self.ctx.resolve_filters(
            team=team,
            function=function,
            position=position,
            branch=branch,
            performance_level=performance_level,
            month=month,
            year=year,
        )
        sections = "summary,executive_story,priority_insights,team_summaries,performance_drivers,comparison"
        ws = self.ctx.insights_service.generate_workspace(
            self.ctx.scope,
            sections=sections,
            month=resolved["month"],
            year=resolved["year"],
            region=resolved["region"],
            team=resolved["team"],
            function=resolved["function"],
            position=resolved["position"],
            performance_level=resolved["performance_level"],
            branch=resolved["branch"],
        )

        res_month = ws.comparison.current.month if ws.comparison and ws.comparison.current else resolved["month"]
        res_year = ws.comparison.current.year if ws.comparison and ws.comparison.current else resolved["year"]
        period_label = f"{res_month} {res_year}" if res_month and res_year else "Latest Period"
        base_scope = resolved["team"] or resolved["function"] or "All authorized departments"
        scope_label = (
            f"{base_scope} · {resolved['position']}"
            if resolved["position"] and resolved["position"].casefold() not in base_scope.casefold()
            else base_scope
        )
        branch_label = resolved["branch"].capitalize() if resolved["branch"] else "All Branches"

        scoped_summaries = list(ws.team_summaries or [])
        if resolved["team"]:
            req_team_cf = _display_team_name(resolved["team"]).strip().casefold()
            raw_team_cf = str(resolved["team"]).strip().casefold()
            t_keys_cf = selection_team_keys(resolved["team"])
            scoped_summaries = [
                t
                for t in scoped_summaries
                if _display_team_name(t.team).strip().casefold() == req_team_cf
                or str(t.team or "").strip().casefold() == raw_team_cf
                or str(t.team or "").strip().casefold() in t_keys_cf
            ]
        total_employees = sum(int(t.total_employees or 0) for t in scoped_summaries)
        impacted_employees = sum(int(t.impacted_employees or 0) for t in scoped_summaries)
        eff_measure: ScoreMeasure = "employee_average" if score_measure == "employee_average" else "official"
        avg_score = (
            ws.executive_story.current_score
            if ws.executive_story and (not resolved["team"] or scoped_summaries)
            else None
        )
        exec_score_basis = "average employee score" if eff_measure == "employee_average" else "official score"
        exec_unavailable_reason = None

        def _team_summary_score(t_obj: Any) -> float | None:
            raw = getattr(t_obj, "current_score", None)
            return min(100.0, round(float(raw), 1)) if raw is not None else None

        cards: list[StructuredVisualCard] = []
        if scoped_summaries:
            bars: list[AiBarItem] = []
            sorted_teams = sorted(
                scoped_summaries,
                key=lambda t: (s if (s := _team_summary_score(t)) is not None else -1.0),
                reverse=True,
            )
            for t in sorted_teams[:8]:
                t_disp = _display_team_name(t.team)
                s_val = _team_summary_score(t)
                if s_val is None:
                    continue
                score_val = min(100.0, round(float(s_val), 1))
                delta = t.score_change
                gap_val = max(0.0, round(100.0 - score_val, 1))
                delta_str = (
                    f"{delta:+.1f} pp vs prev · {t.total_employees} agents"
                    if delta is not None
                    else f"{t.total_employees} agents · Gap -{gap_val:.1f} pts"
                )
                sev = "critical" if score_val < 75 else ("warning" if score_val < 88 else "good")
                bars.append(
                    AiBarItem(
                        label=t_disp,
                        value=score_val,
                        display_value=f"{score_val:.1f}%",
                        target_value=100.0,
                        secondary_label=delta_str,
                        severity=sev,  # type: ignore[arg-type]
                    )
                )
            cards.append(
                StructuredVisualCard(
                    card_type="horizontal_bar",
                    title=f"Team Performance Breakdown · {period_label}",
                    subtitle=f"Scope: {scope_label} ({branch_label}) — Ordered from highest score to lowest",
                    bars=bars,
                )
            )

        if ws.priority_insights:
            items: list[AiEntityListItem] = []
            for ins in ws.priority_insights[:5]:
                sev_map = {"critical": "critical", "risk": "warning", "opportunity": "good", "information": "info"}
                focus_text = ins.explanation or (ins.detail.recommended_focus if ins.detail else "")
                ins_team_disp = _display_team_name(ins.team) if ins.team else scope_label
                items.append(
                    AiEntityListItem(
                        id=ins.id,
                        title=ins.title,
                        subtitle=sanitize_untrusted_text(focus_text, 180),
                        badge_text=ins_team_disp,
                        severity=sev_map.get(str(ins.severity).casefold(), "warning"),  # type: ignore[arg-type]
                        metric_value=f"{ins.impact_points:+.1f} pts" if ins.impact_points is not None else None,
                        route_link=build_verified_deep_link(
                            "/insights",
                            month=res_month,
                            year=res_year,
                            function=resolved["function"],
                            team=ins_team_disp if ins.team else resolved["team"],
                            position=resolved["position"],
                            branch=resolved["branch"],
                            performance_level=resolved["performance_level"],
                        ),
                    )
                )
            cards.append(
                StructuredVisualCard(
                    card_type="entity_list",
                    title="Top Diagnostic Findings",
                    subtitle="Evidence-backed anomalies ranked by negative impact",
                    items=items,
                )
            )

        basis_warn = None
        if ws.executive_story and ws.executive_story.basis_context and not ws.executive_story.basis_context.like_for_like:
            basis_warn = "; ".join(ws.executive_story.basis_context.reasons[:2]) or "Month-over-month scoring basis changed"

        citations = [
            SourceCitationPill(label=f"Period · {period_label}", category="period"),
            SourceCitationPill(label=f"Scope · {scope_label}", category="scope"),
            SourceCitationPill(label=f"Branch · {branch_label}", category="branch"),
            SourceCitationPill(label=f"Evaluated · {total_employees}", category="metric"),
        ]
        if basis_warn:
            citations.append(SourceCitationPill(label="Basis Shift Note", category="basis", warning=True))

        deep_links = [
            DeepLinkCta(
                label="Open Insights →",
                route=build_verified_deep_link(
                    "/insights",
                    month=res_month,
                    year=res_year,
                    function=resolved["function"],
                    team=resolved["team"],
                    position=resolved["position"],
                    branch=resolved["branch"],
                    performance_level=resolved["performance_level"],
                ),
                icon_key="insights",
            )
        ]
        if resolved["team"]:
            team_slug = _team_route_slug(resolved["team"])
            deep_links.append(
                DeepLinkCta(
                    label=f"Open {scope_label} Dashboard →",
                    route=build_verified_deep_link(
                        f"/team/{team_slug}",
                        month=res_month,
                        year=res_year,
                        function=resolved["function"],
                        team=resolved["team"],
                        position=resolved["position"],
                        branch=resolved["branch"],
                        performance_level=resolved["performance_level"],
                    ),
                    icon_key="team",
                )
            )

        worst_team = None
        scored_ws_teams = [t for t in (ws.team_summaries or []) if _team_summary_score(t) is not None]
        if scored_ws_teams:
            worst_team_obj = min(
                scored_ws_teams,
                key=lambda t: float(_team_summary_score(t) or 999.0),
            )
            w_team_disp = _display_team_name(worst_team_obj.team)
            w_score_capped = min(100.0, round(float(_team_summary_score(worst_team_obj) or 0.0), 1))
            w_gap = max(0.0, round(100.0 - w_score_capped, 1))
            worst_team = {
                "team": w_team_disp,
                "current_score": w_score_capped,
                "score_change": worst_team_obj.score_change,
                "gap_points": worst_team_obj.gap_points,
                "impacted_employees": worst_team_obj.impacted_employees,
                "total_employees": worst_team_obj.total_employees,
                "main_cause": worst_team_obj.main_cause,
            }
            exec_decisions: list[AiDecisionItem] = [
                AiDecisionItem(
                    id="dec-exec-worst-team",
                    priority="immediate" if w_score_capped < 88 else "high",
                    priority_label="Immediate Action",
                    title=f"Prioritize Root-Cause Intervention in {w_team_disp} ({w_score_capped:.1f}%)",
                    rationale=(
                        f"{w_team_disp} shows the largest gap to 100% (-{w_gap:.1f} pts across "
                        f"{worst_team_obj.total_employees} evaluated agents). Top contributing factor: "
                        f"{worst_team_obj.main_cause or 'High-weight KPI deficit'}."
                    ),
                    expected_impact=f"Closing 50% of the {w_team_disp} KPI gap adds +{round(w_gap * 0.5, 1):.1f} pts to the team average.",
                    target_label=f"{w_team_disp} Team ({worst_team_obj.total_employees} agents)",
                    route_link=build_verified_deep_link(
                        "/insights",
                        month=res_month,
                        year=res_year,
                        function=resolved["function"],
                        team=w_team_disp,
                        position=resolved["position"],
                        branch=resolved["branch"],
                    ),
                    cta_label=f"Diagnose {w_team_disp} →",
                )
            ]
            if ws.executive_story and ws.executive_story.recommended_focus:
                exec_decisions.append(
                    AiDecisionItem(
                        id="dec-exec-focus",
                        priority="coaching",
                        priority_label="Supervisory Focus",
                        title=sanitize_untrusted_text(ws.executive_story.recommended_focus, 110),
                        rationale=f"Primary department driver flagged by scoring engine: {ws.executive_story.primary_driver or 'Weighted KPI variance'}.",
                        expected_impact="Prevents single-KPI slippage from dragging down multi-branch SLA.",
                        target_label=f"{scope_label} Supervisors & Team Leaders",
                        route_link=build_verified_deep_link(
                            "/planning",
                            month=res_month,
                            year=res_year,
                            team=w_team_disp,
                            position=resolved["position"],
                        ),
                        cta_label="Open Planning →",
                    )
                )
            cards.append(
                StructuredVisualCard(
                    card_type="decision_playbook",
                    title=f"Recommended Executive Decisions ({scope_label})",
                    subtitle=f"Data-driven managerial playbook for {period_label} ({branch_label})",
                    decisions=exec_decisions,
                )
            )

        best_team = None
        scored_scoped = [t for t in scoped_summaries if _team_summary_score(t) is not None]
        if len(scored_scoped) > 1:
            best_team_obj = max(
                scored_scoped,
                key=lambda t: float(_team_summary_score(t) or -1.0),
            )
            best_team = {
                "team": _display_team_name(best_team_obj.team),
                "current_score": min(100.0, round(float(_team_summary_score(best_team_obj) or 0.0), 1)),
                "score_change": best_team_obj.score_change,
                "total_employees": best_team_obj.total_employees,
            }
        teams_on_track = sum(
            1 for t in scored_scoped if float(_team_summary_score(t) or 0.0) >= 85.0
        )

        digest = {
            "period": period_label,
            "scope": scope_label,
            "region": resolved["region"],
            "branch": branch_label,
            "score_measure": eff_measure,
            "score_basis": exec_score_basis,
            "score_unavailable_reason": exec_unavailable_reason,
            "average_score": avg_score,
            "score_change": ws.executive_story.score_change if ws.executive_story else None,
            "total_records": total_employees,
            "employees_below_target": impacted_employees,
            "total_teams": len(scoped_summaries),
            "teams_on_track": teams_on_track,
            "primary_driver": ws.executive_story.primary_driver if ws.executive_story else None,
            "recommended_focus": ws.executive_story.recommended_focus if ws.executive_story else None,
            "worst_team": worst_team,
            "best_team": best_team,
            "teams": [
                {
                    "team": _display_team_name(t.team),
                    "score": min(100.0, round(float(_team_summary_score(t) or 0.0), 1)),
                    "change": t.score_change,
                    "impacted": t.impacted_employees,
                    "total": t.total_employees,
                    "main_cause": t.main_cause,
                }
                for t in sorted(
                    scored_scoped,
                    key=lambda t: float(_team_summary_score(t) or -1.0),
                    reverse=True,
                )[:6]
            ],
        }

        scoped_insights = [
            ins
            for ins in (ws.priority_insights or [])
            if not resolved["team"]
            or not ins.team
            or str(ins.team).strip().casefold() == str(resolved["team"]).strip().casefold()
        ]
        records_eval = (
            total_employees
            if resolved["team"]
            else max(total_employees, len(scoped_insights))
        )

        return ToolExecutionResult(
            tool_name="get_executive_and_priority_insights",
            arguments=resolved,
            records_evaluated=records_eval,
            digest=digest,
            visual_cards=cards,
            citations=citations,
            deep_links=deep_links,
            resolved_month=res_month,
            resolved_year=res_year,
            basis_warning=basis_warn,
        )

    @_read_only_tool
    def execute_shared_region_scorecard(
        self,
        *,
        team: str | None = None,
        month: str | None = None,
        year: int | None = None,
    ) -> ToolExecutionResult:
        """Shared All-region scorecard for one shared team (Finance / RCM).

        The scorecard averages the stored overall evaluation scores of that
        team's own region='All' Employee records for one period, using the
        same single averaging rule as ``executive_story.current_score``.
        It is deliberately NOT built on ``generate_workspace``: a team=RCM
        call there expands to the whole RCM function rollup (Coding,
        Submission, Pre-Approvals, ...), and ``resolve_filters`` drops a
        session region of 'All' to "no region filter", so the existing tools
        cannot express "region='All' only".

        Attribution boundary (PR #84): shared records are reported only as
        their own All-region scorecard. They are never folded into an
        Egypt-only or UAE-only total — no approved attribution rule exists
        for that, and none is invented here. The record filter is exact:
        team name must match the requested team (not the function rollup)
        and the effective region must be 'All'. The scope filter in
        ``get_scoped_records`` has already removed every row the caller may
        not see, so a restricted scope can only ever average its own
        authorised shared rows.
        """
        team_name = str(team or "").strip()
        resolved = self.ctx.resolve_filters(
            team=team_name or None,
            month=month,
            year=year,
        )
        scope_label = f"Shared All-region {team_name}" if team_name else "Shared All-region"
        # Only teams whose canonical region is 'All' have a shared
        # scorecard (Finance, RCM). Anything else has no shared rows by
        # definition, so it reports no data rather than a wrong average.
        is_shared_team = bool(team_name) and canonical_team_region(team_name) == "All"

        matched: list[Any] = []
        if is_shared_team:
            for record in self.ctx.get_scoped_records():
                if str(_record_field(record, "team", "") or "").strip().casefold() != team_name.casefold():
                    continue
                if _shared_record_region(record, team_name).casefold() != "all":
                    continue
                level = str(_record_field(record, "performance_level", "") or "Employee").strip().casefold()
                if level != "employee":
                    continue
                matched.append(record)

        req_month = resolved["month"]
        req_year = resolved["year"]
        period_records = matched
        if req_month and req_year:
            period_records = [
                r
                for r in matched
                if str(_record_field(r, "month", "") or "").strip().casefold() == str(req_month).strip().casefold()
                and int(_record_field(r, "year", 0) or 0) == int(req_year)
            ]
            res_month, res_year = str(req_month).strip(), int(req_year)
        else:
            # No explicit period: latest period that actually has shared
            # records for this team (same "latest present period" rule the
            # workspace uses when no month is selected).
            dated = [
                (int(_record_field(r, "year", 0) or 0), MONTH_ORDER.get(str(_record_field(r, "month", "") or "").strip(), 0), r)
                for r in matched
            ]
            dated = [d for d in dated if d[0] >= 2000 and d[1] >= 1]
            if dated:
                latest_year, latest_month_num, _ = max(dated, key=lambda d: (d[0], d[1]))
                res_month = next(name for name, num in MONTH_ORDER.items() if num == latest_month_num)
                res_year = latest_year
                period_records = [
                    r
                    for r in matched
                    if int(_record_field(r, "year", 0) or 0) == latest_year
                    and MONTH_ORDER.get(str(_record_field(r, "month", "") or "").strip(), 0) == latest_month_num
                ]
            else:
                res_month, res_year = None, None

        period_label = f"{res_month} {res_year}" if res_month and res_year else "Latest Period"
        scores = [
            s for s in (_record_evaluation_score(r) for r in period_records)
            if s is not None
        ]
        avg_score: float | None = None
        if scores:
            avg_score = min(100.0, round(sum(scores) / len(scores), 1))

        cards: list[StructuredVisualCard] = []
        if avg_score is not None:
            cards.append(
                StructuredVisualCard(
                    card_type="horizontal_bar",
                    title=f"Shared All-region {team_name} Scorecard · {period_label}",
                    subtitle=(
                        "Region 'All' records only — shared records are not attributed to a single "
                        "country and are never folded into an Egypt-only or UAE-only total."
                    ),
                    bars=[
                        AiBarItem(
                            label=f"Shared All-region {team_name}",
                            value=avg_score,
                            display_value=f"{avg_score:.1f}%",
                            target_value=100.0,
                            secondary_label=f"{len(period_records)} evaluated records",
                            severity="good" if avg_score >= 88 else ("warning" if avg_score >= 75 else "critical"),  # type: ignore[arg-type]
                        )
                    ],
                )
            )

        citations = [
            SourceCitationPill(label=f"Period · {period_label}", category="period"),
            SourceCitationPill(label=f"Scope · {scope_label}", category="scope"),
            SourceCitationPill(label="Region · All (shared)", category="scope"),
            SourceCitationPill(label=f"Evaluated · {len(period_records)}", category="metric"),
        ]

        # Same digest shape as the executive insights tool, so the
        # deterministic synthesizer renders it truthfully: a score headline
        # when records exist, "No performance records matched the selected
        # filters" when the shared team has no rows in the period.
        digest = {
            "period": period_label,
            "scope": scope_label,
            "branch": "All Branches",
            "average_score": avg_score,
            "score_change": None,
            "total_records": len(period_records),
        }
        typed_evidence: list[TypedMetricEvidence] = []
        if avg_score is not None:
            typed_evidence.append(
                TypedMetricEvidence(
                    metric_id=f"shared_scorecard:{team_name.lower().replace(' ', '_')}:overall_score",
                    kpi_key="overall_score",
                    display_name=f"{scope_label} Overall Score",
                    team=team_name,
                    performance_level="Employee",
                    branch="all",
                    period=period_label,
                    actual=avg_score,
                    actual_display=f"{avg_score:.1f}%",
                    unit="%",
                    direction="higher_better",
                    sample_size=len(period_records),
                    source_link=build_verified_deep_link("/insights", month=res_month, year=res_year, team=team_name),
                )
            )

        return ToolExecutionResult(
            tool_name="get_shared_region_scorecard",
            arguments={"team": team_name, "month": res_month, "year": res_year, "region": "All"},
            records_evaluated=len(period_records),
            digest=digest,
            visual_cards=cards,
            citations=citations,
            deep_links=[],
            typed_evidence=typed_evidence,
            resolved_month=res_month,
            resolved_year=res_year,
        )

    @_read_only_tool
    def execute_kpi_diagnosis_and_trends(
        self,
        *,
        team: str | None = None,
        function: str | None = None,
        position: str | None = None,
        branch: str | None = None,
        compare_branch: str | None = None,
        branches: list[str] | None = None,
        asks_branch_comparison: bool = False,
        asks_period_comparison: bool = False,
        performance_level: str | None = None,
        kpi: str | None = None,
        month: str | None = None,
        year: int | None = None,
        score_measure: str | None = None,
    ) -> ToolExecutionResult:
        requested_branches: list[str] = []
        if branches:
            for b in branches:
                b_clean = str(b).strip().casefold()
                if b_clean in BRANCH_KEYS and b_clean not in requested_branches:
                    requested_branches.append(b_clean)
        if branch and compare_branch and branch.casefold() != compare_branch.casefold():
            for b in (branch, compare_branch):
                b_clean = str(b).strip().casefold()
                if b_clean in BRANCH_KEYS and b_clean not in requested_branches:
                    requested_branches.append(b_clean)

        # When comparing branches (e.g., Dubai vs Sharjah or all branches), keep the main KPI diagnosis
        # across All Branches unless the session filter explicitly locked a single branch without comparison.
        is_comparing_branches = bool(compare_branch or asks_branch_comparison or len(requested_branches) >= 2)
        kpi_table_branch = None if is_comparing_branches else branch
        resolved = self.ctx.resolve_filters(
            team=team,
            function=function,
            position=position,
            branch=kpi_table_branch,
            performance_level=performance_level,
            month=month,
            year=year,
        )
        ws = self.ctx.insights_service.generate_workspace(
            self.ctx.scope,
            sections="summary,executive_story,team_summaries,kpi_diagnosis,kpi_overview,geography_summaries,comparison",
            month=resolved["month"],
            year=resolved["year"],
            region=resolved["region"],
            team=resolved["team"],
            function=resolved["function"],
            position=resolved["position"],
            performance_level=resolved["performance_level"],
            branch=resolved["branch"],
        )

        res_month = ws.comparison.current.month if ws.comparison and ws.comparison.current else resolved["month"]
        res_year = ws.comparison.current.year if ws.comparison and ws.comparison.current else resolved["year"]
        period_label = f"{res_month} {res_year}" if res_month and res_year else "Latest Period"
        base_scope = resolved["team"] or resolved["function"] or "All authorized departments"
        scope_label = (
            f"{base_scope} · {resolved['position']}"
            if resolved["position"] and resolved["position"].casefold() not in base_scope.casefold()
            else base_scope
        )
        branch_label = resolved["branch"].capitalize() if resolved["branch"] else "All Branches"
        total_employees = sum(int(t.total_employees or 0) for t in (ws.team_summaries or []))

        cards: list[StructuredVisualCard] = []

        # NOTE (Task 2): when the comparison is about a booking (or
        # attended) count, the branch bars must show counts, not performance
        # scores as percentages. The old code always rendered the branch
        # score ("66.7%") as the bar value, so a branch booking-count
        # question was answered with performance percentages. A branch with
        # no recorded count is labelled Unavailable, never 0%.
        count_field: str | None = None
        count_label = ""
        count_title = ""
        if kpi:
            _count_def = get_ai_catalog().find_metric_definition(
                team=resolved["team"],
                kpi_key_or_label=kpi,
                performance_level=resolved["performance_level"] or "Employee",
            )
            if _count_def is not None and _count_def.value_kind == "count":
                if _count_def.kpi_key == "TotalBookings":
                    count_field, count_label, count_title = "bookings", "bookings", "Booking Counts"
                elif _count_def.kpi_key == "AttendedPatients":
                    count_field, count_label, count_title = "attended", "attended", "Attended Counts"
            elif is_comparing_branches and kpi == "bookings_count" and resolved["function"] == "Call Center":
                count_field, count_label, count_title = "bookings", "bookings", "Booking Counts"

        branch_comparison_digest: list[dict[str, Any]] = []
        if is_comparing_branches:
            branches_to_compare = requested_branches or list(BRANCH_KEYS)
            branches_to_compare = [b for b in branches_to_compare if user_can_access_branch(self.ctx.scope, b)]

            bars: list[AiBarItem] = []
            for bk in branches_to_compare:
                ws_b = self.ctx.insights_service.generate_workspace(
                    self.ctx.scope,
                    sections="summary,executive_story,team_summaries,comparison",
                    month=res_month,
                    year=res_year,
                    team=resolved["team"],
                    function=resolved["function"],
                    performance_level=resolved["performance_level"],
                    branch=bk,
                )
                b_name = bk.capitalize()
                has_score = (
                    ws_b.executive_story is not None
                    and ws_b.executive_story.current_score is not None
                    and getattr(ws_b.executive_story, "period_records_count", 1) > 0
                )
                capped_s = min(100.0, round(float(ws_b.executive_story.current_score), 1)) if has_score else None
                b_vols = self._compute_operational_volumes(
                    month=res_month,
                    year=res_year,
                    team=resolved["team"],
                    function=resolved["function"],
                    branch=bk,
                )
                data_present = bool(b_vols.get("data_present"))
                period_published = bool(b_vols.get("period_published", True))
                b_book = int(b_vols["total_bookings"]) if b_vols.get("total_bookings") is not None else None
                b_att = int(b_vols["total_attended"]) if b_vols.get("attendance_complete") and b_vols.get("total_attended") is not None else None
                if not b_vols.get("booking_complete"):
                    b_att = None
                b_noshows = max(0, b_book - b_att) if (b_book is not None and b_att is not None) else None
                b_att_pct = (
                    round((b_att / b_book) * 100.0, 1)
                    if (b_book is not None and b_book > 0 and b_att is not None)
                    else None
                )
                if b_book is not None and b_att is not None and b_noshows is not None and b_book > 0 and b_att_pct is not None:
                    sec_lbl = f"Attended {b_att_pct:.1f}% ({b_att:,}/{b_book:,}) · {b_noshows:,} No-Shows"
                elif b_book is not None and b_book == 0:
                    sec_lbl = "Bookings: 0"
                elif b_book is not None and b_att is None:
                    sec_lbl = f"Bookings: {b_book:,} · Attendance unrecorded"
                elif capped_s is not None:
                    # NOTE (Task 2): never answer a count comparison with a
                    # performance score — an unrecorded count stays unrecorded.
                    sec_lbl = (
                        f"Score {capped_s:.1f}%"
                        if count_field is None
                        else f"{count_label.capitalize()} unrecorded"
                    )
                else:
                    sec_lbl = (
                        "Performance score unavailable"
                        if count_field is None
                        else f"{count_label.capitalize()} unrecorded"
                    )

                if count_field is not None:
                    count_val = b_book if count_field == "bookings" else b_att
                    bars.append(
                        AiBarItem(
                            label=f"{scope_label} · {b_name}",
                            # Unrecorded count: null, never a fake 0.0.
                            value=float(count_val) if count_val is not None else None,
                            display_value=f"{int(count_val):,} {count_label}" if count_val is not None else "Unavailable",
                            target_value=None,
                            secondary_label=sec_lbl,
                            severity="neutral",
                        )
                    )
                else:
                    sev = (
                        "critical" if (capped_s is not None and capped_s < 75) or (b_att_pct is not None and b_att_pct < 60)
                        else ("warning" if (capped_s is not None and capped_s < 90) or (b_att_pct is not None and b_att_pct < 70) else "good")
                    )
                    bars.append(
                        AiBarItem(
                            label=f"{scope_label} · {b_name}",
                            # Unrecorded score: null, never a fake 0.0.
                            value=capped_s,
                            display_value=f"{capped_s:.1f}%" if capped_s is not None else "Unavailable",
                            target_value=100.0,
                            secondary_label=sec_lbl,
                            severity=sev,  # type: ignore[arg-type]
                        )
                    )
                branch_comparison_digest.append(
                    {
                        "branch": b_name,
                        "score": capped_s,
                        "bookings": b_book,
                        "attended": b_att,
                        "no_shows": b_noshows,
                        "attendance_rate_pct": b_att_pct,
                        "data_present": data_present,
                        "booking_present": bool(b_vols.get("booking_present")),
                        "booking_complete": bool(b_vols.get("booking_complete")),
                        "has_partial_evidence": bool(b_vols.get("has_partial_evidence")),
                        "attended_present": bool(b_vols.get("attended_present")),
                        "calls_present": bool(b_vols.get("calls_present")),
                        "period_published": period_published,
                    }
                )

            if count_field is not None:
                title_prefix = f"UAE Branch {count_title} · {scope_label}"
                card_subtitle = (
                    "Booking counts per branch · Attendance shown where recorded; unrecorded branches are labelled Unavailable, never 0%"
                    if count_field == "bookings"
                    else "Attended counts per branch · Unrecorded branches are labelled Unavailable, never 0%"
                )
            elif branch and compare_branch:
                title_prefix = f"UAE Branch Comparison: {branch.capitalize()} vs {compare_branch.capitalize()} + All Branches"
                card_subtitle = "Scores capped at 100% · Shows actual patient Attended / Bookings conversion & No-Show volume per branch"
            else:
                title_prefix = f"UAE 4-Branch Performance & Conversion Matrix · {scope_label}"
                card_subtitle = "Scores capped at 100% · Shows actual patient Attended / Bookings conversion & No-Show volume per branch"
            cards.append(
                StructuredVisualCard(
                    card_type="horizontal_bar",
                    title=f"{title_prefix} ({period_label})",
                    subtitle=card_subtitle,
                    bars=bars,
                )
            )

        kpi_rows: list[AiKpiTableRow] = []
        kpi_bars: list[AiBarItem] = []
        typed_evidence: list[TypedMetricEvidence] = []
        if is_comparing_branches:
            for b_entry in branch_comparison_digest:
                bk_lower = str(b_entry["branch"]).strip().lower()
                val = (
                    b_entry["bookings"]
                    if count_field == "bookings"
                    else (b_entry["attended"] if count_field == "attended" else b_entry["score"])
                )
                val_unit = "count" if count_field in ("bookings", "attended") else "%"
                m_key = count_field or "overall_score"
                evidence_kpi_key = (
                    "bookings_count" if count_field == "bookings"
                    else ("attended_count" if count_field == "attended" else m_key)
                )
                typed_evidence.append(
                    TypedMetricEvidence(
                        metric_id=f"branch_comparison:{bk_lower}:{evidence_kpi_key}",
                        kpi_key=evidence_kpi_key,
                        display_name=f"{b_entry['branch']} {count_title or 'Overall Score'}",
                        team=resolved["team"] or "Call Center",
                        branch=bk_lower,
                        period=period_label,
                        actual=float(val) if val is not None else None,
                        actual_display=f"{val} {val_unit}" if val is not None else "Unavailable",
                        unit=val_unit,
                        direction="higher_better",
                        is_missing=val is None,
                        source_link=build_verified_deep_link(
                            "/insights",
                            month=res_month,
                            year=res_year,
                            team=resolved["team"],
                            branch=bk_lower,
                        ),
                    )
                )

        raw_diag = list(ws.kpi_diagnosis or [])
        catalog = get_ai_catalog()

        basis_status = "unchanged"
        basis_note: str | None = None
        if ws.executive_story and ws.executive_story.basis_context and not ws.executive_story.basis_context.like_for_like:
            basis_status = "changed"
            basis_note = "; ".join(ws.executive_story.basis_context.reasons[:2]) or "Month-over-month scoring basis changed"
        elif (resolved["team"] or "").casefold() == "pre-approvals ip offshore":
            basis_note = (
                "Effective June 2026 (2026-06), Pre-Approvals IP Offshore scores Controllable Rejection Rate "
                "(50% weight) while Policy Rejection Rate is tracked as a 0% weight non-scored indicator."
            )

        primary_route = build_verified_deep_link(
            f"/team/{_team_route_slug(resolved['team'])}" if resolved["team"] else "/insights",
            month=res_month,
            year=res_year,
            function=resolved["function"],
            team=resolved["team"],
            position=resolved["position"],
            branch=resolved["branch"],
            performance_level=resolved["performance_level"],
        )

        pooled_cc_vols: dict[str, Any] | None = None
        if (resolved["team"] or "").strip().casefold() in ("inbound", "outbound") and not resolved["branch"]:
            pooled_cc_vols = self._compute_operational_volumes(
                month=res_month,
                year=res_year,
                team=resolved["team"],
                function=resolved["function"],
                branch=None,
            )

        for row in raw_diag:
            row_team = resolved["team"] or (str(row.teams[0]) if getattr(row, "teams", None) else scope_label)
            clean_label = disambiguate_call_center_kpi_label(row_team, row.key, row.label)
            cat_def = catalog.find_metric_definition(
                team=row_team,
                kpi_key_or_label=row.key,
                performance_level=resolved["performance_level"] or "Employee",
            )
            unit = row.unit or (cat_def.unit if cat_def else "%")
            actual_val = row.actual
            target_val = row.target
            pooled_override_ratio: float | None = None
            if pooled_cc_vols is not None:
                row_key_cf = str(row.key or "").strip().casefold()
                team_cf = str(resolved["team"] or "").strip().casefold()
                if (
                    row_key_cf in ("booking", "booking_rate", "bookingrate")
                    and pooled_cc_vols.get("booking_complete")
                    and pooled_cc_vols.get("booking_ratio_consistent")
                ):
                    denom = (
                        pooled_cc_vols.get("total_inbound_calls") or pooled_cc_vols.get("total_calls_handled")
                        if team_cf == "inbound"
                        else pooled_cc_vols.get("total_calls_handled")
                    )
                    if pooled_cc_vols.get("total_bookings") is not None and denom and float(denom) > 0:
                        pooled_override_ratio = float(pooled_cc_vols["total_bookings"]) / float(denom)
                elif (
                    row_key_cf in ("attendance", "attendance_rate", "attendancerate")
                    and pooled_cc_vols.get("attendance_complete")
                    and pooled_cc_vols.get("attendance_ratio_consistent")
                ):
                    b_tot = pooled_cc_vols.get("total_bookings")
                    a_tot = pooled_cc_vols.get("total_attended")
                    if a_tot is not None and b_tot and float(b_tot) > 0:
                        pooled_override_ratio = float(a_tot) / float(b_tot)
                elif (
                    "abandon" in clean_label.casefold()
                    and pooled_cc_vols.get("abandon_ratio_consistent")
                    and pooled_cc_vols.get("total_abandoned") is not None
                    and pooled_cc_vols.get("total_calls_handled")
                    and float(pooled_cc_vols["total_calls_handled"]) > 0
                ):
                    pooled_override_ratio = float(pooled_cc_vols["total_abandoned"]) / float(pooled_cc_vols["total_calls_handled"])

            if pooled_override_ratio is not None and unit == "%":
                if target_val is not None and target_val > 1.5:
                    actual_val = round(pooled_override_ratio * 100.0, 4)
                else:
                    actual_val = round(pooled_override_ratio, 6)

            if unit == "%" and actual_val is not None and actual_val <= 1.5 and (target_val is None or target_val <= 1.5):
                act_str = f"{actual_val * 100:.1f}%"
                tgt_str = f"{(target_val or 0.0) * 100:.1f}%" if target_val is not None else "—"
                norm_actual = round(float(actual_val) * 100.0, 2)
                norm_target = round(float(target_val) * 100.0, 2) if target_val is not None else None
            elif unit == "%":
                act_str = f"{actual_val:.1f}%" if actual_val is not None else "—"
                tgt_str = f"{target_val:.1f}%" if target_val is not None else "—"
                norm_actual = round(float(actual_val), 2) if actual_val is not None else None
                norm_target = round(float(target_val), 2) if target_val is not None else None
            else:
                act_str = f"{actual_val:.2f} {unit}".strip() if actual_val is not None else "—"
                tgt_str = f"{target_val:.2f} {unit}".strip() if target_val is not None else "—"
                norm_actual = round(float(actual_val), 2) if actual_val is not None else None
                norm_target = round(float(target_val), 2) if target_val is not None else None

            if pooled_override_ratio is not None and norm_actual is not None and norm_target is not None and norm_target > 0:
                if str(row.direction or "higher_better").casefold().startswith("lower"):
                    ach_pct = 100.0 if norm_actual <= 0 else min(100.0, round((norm_target / norm_actual) * 100.0, 1))
                else:
                    ach_pct = min(100.0, round((norm_actual / norm_target) * 100.0, 1))
            else:
                ach_pct = min(100.0, round(float(row.achievement_percent or 0.0), 1)) if row.achievement_percent is not None else 0.0
            weight_pct = round(float((row.weight or 0.0) * 100 if (row.weight or 0.0) <= 1.0 else (row.weight or 0.0)), 1)
            contributes = bool(weight_pct > 0.0 and (cat_def.contributes_to_score if cat_def else True))
            tracking_note = cat_def.tracking_only_note if (cat_def and not contributes) else None
            status_val = "critical" if ach_pct < 75 else ("warning" if ach_pct < 92 else "good")

            kpi_rows.append(
                AiKpiTableRow(
                    kpi_key=row.key,
                    kpi_label=clean_label,
                    weight_percent=weight_pct,
                    actual_display=act_str,
                    target_display=tgt_str,
                    achievement_percent=ach_pct if contributes else None,
                    direction=row.direction or "higher_better",
                    people_below_target=int(row.people_below_target or 0),
                    status=status_val if contributes else "info",  # type: ignore[arg-type]
                    contributes_to_score=contributes,
                    tracking_only_badge="Tracking Only" if not contributes else None,
                )
            )
            kpi_bars.append(
                AiBarItem(
                    label=clean_label,
                    value=ach_pct,
                    display_value=f"{ach_pct:.1f}% ach ({act_str} / {tgt_str})",
                    target_value=100.0,
                    secondary_label=f"Weight {weight_pct:.0f}% · {row.people_below_target} below target",
                    severity=status_val,  # type: ignore[arg-type]
                )
            )
            typed_evidence.append(
                TypedMetricEvidence(
                    metric_id=cat_def.metric_id if cat_def else f"{row_team.casefold().replace(' ', '_')}:{row.key.casefold()}",
                    kpi_key=row.key,
                    display_name=clean_label,
                    team=row_team,
                    position=cat_def.position if cat_def else None,
                    performance_level=resolved["performance_level"] or "Employee",
                    branch=resolved["branch"] or "all",
                    period=period_label,
                    actual=norm_actual,
                    target=norm_target,
                    actual_display=act_str,
                    target_display=tgt_str,
                    achievement_percent=ach_pct if contributes else None,
                    weight_percent=weight_pct,
                    unit=unit,
                    direction=row.direction or "higher_better",
                    contributes_to_score=contributes,
                    tracking_only_note=tracking_note,
                    sample_size=total_employees,
                    source_link=primary_route,
                    scoring_basis_status=basis_status,
                    scoring_basis_note=basis_note,
                )
            )

        volume_summary = self._compute_operational_volumes(
            month=res_month,
            year=res_year,
            team=resolved["team"],
            function=resolved["function"],
            branch=resolved["branch"],
        )

        # If a tracking-only or count KPI was explicitly requested (e.g. outbound:aht, PolicyRejection, or bookings_count)
        unavailable_count_metric: dict[str, Any] | None = None
        if kpi:
            req_cat = catalog.find_metric_definition(
                team=resolved["team"],
                kpi_key_or_label=kpi,
                performance_level=resolved["performance_level"] or "Employee",
            )
            if req_cat and not req_cat.contributes_to_score:
                already_present = any(ev.metric_id == req_cat.metric_id for ev in typed_evidence)
                if not already_present:
                    vol_val: float | None = None
                    act_disp_val = "Tracking Only"
                    tgt_disp_val = "0% Weight"
                    skip_missing_count_evidence = False
                    if getattr(req_cat, "value_kind", None) == "count":
                        vol_map = {
                            "bookings_count": volume_summary.get("total_bookings"),
                            "TotalBookings": volume_summary.get("total_bookings"),
                            "attended_count": volume_summary.get("total_attended"),
                            "AttendedPatients": volume_summary.get("total_attended"),
                            "handled_calls_count": volume_summary.get("total_calls_handled"),
                            "HandledCalls": volume_summary.get("total_calls_handled"),
                            "abandoned_calls_count": volume_summary.get("total_abandoned"),
                            "AbandonedCalls": volume_summary.get("total_abandoned"),
                        }
                        raw_cnt = vol_map.get(req_cat.kpi_key)
                        if raw_cnt is not None:
                            cnt_v = int(raw_cnt)
                            vol_val = float(cnt_v)
                            act_disp_val = f"{cnt_v:,} {req_cat.unit}".strip()
                            tgt_disp_val = "Volume Count"
                        elif total_employees == 0:
                            skip_missing_count_evidence = True
                            unavailable_count_metric = {
                                "display_name": req_cat.display_name,
                                "team": resolved["team"],
                                "branch": resolved["branch"],
                                "period": period_label,
                            }
                        else:
                            vol_val = None
                            act_disp_val = "Data Missing or Unpublished"
                            tgt_disp_val = "—"
                    if not skip_missing_count_evidence:
                        typed_evidence.insert(
                            0,
                            TypedMetricEvidence(
                                metric_id=req_cat.metric_id,
                                kpi_key=req_cat.kpi_key,
                                display_name=req_cat.display_name,
                                team=req_cat.team,
                                position=req_cat.position,
                                performance_level=req_cat.performance_level,
                                branch=resolved["branch"] or "all",
                                period=period_label,
                                actual=vol_val,
                                target=None,
                                actual_display=act_disp_val,
                                target_display=tgt_disp_val,
                                achievement_percent=None,
                                weight_percent=0.0,
                                unit=req_cat.unit,
                                direction=req_cat.direction,
                                contributes_to_score=False,
                                tracking_only_note=req_cat.tracking_only_note,
                                sample_size=total_employees,
                                source_link=primary_route,
                                scoring_basis_status=basis_status,
                                scoring_basis_note=req_cat.tracking_only_note or basis_note,
                            ),
                        )
                        if req_cat.tracking_only_note:
                            basis_note = (
                                f"{req_cat.tracking_only_note} · {basis_note}"
                                if basis_note
                                else req_cat.tracking_only_note
                            )

        if kpi_rows:
            cards.append(
                StructuredVisualCard(
                    card_type="kpi_table",
                    title=f"KPI Diagnosis & Target Gap · {scope_label}",
                    subtitle=f"{period_label} · {branch_label} (Achievement capped at 100%)",
                    kpi_rows=kpi_rows,
                )
            )
        # A count question (bookings count, attended count, ...) has no
        # achievement to break down: the asked metric carries no target or
        # achievement, so these bars would be unrelated rate achievements
        # sitting next to a count headline. Omit the card for count-kind
        # questions; rate questions keep it. The diagnosis table above is
        # labelled per KPI (actual vs target) and stays as context.
        asked_count_metric = False
        if kpi:
            asked_cat = catalog.find_metric_definition(
                team=resolved["team"],
                kpi_key_or_label=kpi,
                performance_level=resolved["performance_level"] or "Employee",
            )
            asked_count_metric = bool(
                asked_cat and getattr(asked_cat, "value_kind", None) == "count"
            )
        if kpi_bars and not branch_comparison_digest and not asked_count_metric:
            cards.append(
                StructuredVisualCard(
                    card_type="horizontal_bar",
                    title=f"KPI Achievement Breakdown · {scope_label}",
                    subtitle="Weighted KPI achievement against target",
                    bars=kpi_bars[:6],
                )
            )

        # Build Data-Analyst Decision Playbook & What-If ROI based on KPI & Branch patterns
        kpi_decisions = self._build_kpi_and_branch_decisions(
            scope_label=scope_label,
            period_label=period_label,
            res_month=res_month,
            res_year=res_year,
            resolved=resolved,
            kpi_rows=kpi_rows,
            volume_summary=volume_summary,
            branch_comparison_digest=branch_comparison_digest,
        )
        if kpi_decisions:
            cards.append(
                StructuredVisualCard(
                    card_type="decision_playbook",
                    title=f"Recommended Decisions & What-If Impact ({scope_label})",
                    subtitle="Quantified operational interventions derived from KPI weights, conversion ratios, and branch volumes",
                    decisions=kpi_decisions,
                )
            )

        citations = [
            SourceCitationPill(label=f"Period · {period_label}", category="period"),
            SourceCitationPill(label=f"Scope · {scope_label}", category="scope"),
            SourceCitationPill(label=f"Branch · {branch_label}", category="branch"),
        ]
        if volume_summary.get("total_bookings") is not None:
            att_txt = f"{int(volume_summary['total_attended']):,}" if volume_summary.get("total_attended") is not None else "Unrecorded"
            citations.append(
                SourceCitationPill(
                    label=f"Bookings · {int(volume_summary['total_bookings']):,} | Attended · {att_txt}",
                    category="metric",
                )
            )

        deep_links = [
            DeepLinkCta(
                label="Open KPI Diagnosis in Insights →",
                route=build_verified_deep_link(
                    "/insights",
                    month=res_month,
                    year=res_year,
                    function=resolved["function"],
                    team=resolved["team"],
                    position=resolved["position"],
                    branch=resolved["branch"],
                    performance_level=resolved["performance_level"],
                    kpi=kpi,
                ),
                icon_key="insights",
            )
        ]
        if resolved["team"]:
            team_slug = _team_route_slug(resolved["team"])
            deep_links.insert(
                0,
                DeepLinkCta(
                    label=f"Open {scope_label} Scorecard →",
                    route=build_verified_deep_link(
                        f"/team/{team_slug}",
                        month=res_month,
                        year=res_year,
                        function=resolved["function"],
                        team=resolved["team"],
                        position=resolved["position"],
                        branch=resolved["branch"],
                        performance_level=resolved["performance_level"],
                    ),
                    icon_key="team",
                ),
            )

        requested_kpi_payload: dict[str, Any] | None = None
        if kpi:
            req_cat = catalog.find_metric_definition(
                team=resolved["team"],
                kpi_key_or_label=kpi,
                performance_level=resolved["performance_level"] or "Employee",
            )
            matched_ev = next(
                (
                    ev
                    for ev in typed_evidence
                    if (req_cat and ev.metric_id == req_cat.metric_id)
                    or ev.kpi_key.casefold() == kpi.strip().casefold()
                    or kpi.strip().casefold() in ev.display_name.casefold()
                ),
                None,
            )
            single_published_sample = False
            if matched_ev is None and req_cat and not is_comparing_branches:
                matched_ev = self._single_published_team_kpi(resolved, req_cat, primary_route)
                if matched_ev:
                    typed_evidence.append(matched_ev)
                    single_published_sample = True
            if matched_ev is not None:
                matched_row = next(
                    (r for r in kpi_rows if r.kpi_key.casefold() == matched_ev.kpi_key.casefold()),
                    None,
                )
                requested_kpi_payload = {
                    "metric_id": matched_ev.metric_id,
                    "kpi_key": matched_ev.kpi_key,
                    "kpi_label": matched_ev.display_name,
                    "actual_display": matched_ev.actual_display,
                    "target_display": matched_ev.target_display,
                    "achievement_percent": matched_ev.achievement_percent,
                    "weight_percent": matched_ev.weight_percent,
                    "people_below_target": matched_row.people_below_target if matched_row else 0,
                    "contributes_to_score": matched_ev.contributes_to_score,
                    "tracking_only_note": matched_ev.tracking_only_note,
                    "single_published_sample": single_published_sample,
                }

        eff_measure: ScoreMeasure = "employee_average" if score_measure == "employee_average" else "official"
        curr_score_res = self._resolve_cohort_score_result(
            region=resolved["region"],
            month=res_month,
            year=res_year,
            team=resolved["team"],
            function=resolved["function"],
            position=resolved["position"],
            branch=resolved["branch"],
            performance_level=resolved["performance_level"],
            score_measure=eff_measure,
        )
        period_comparison_payload: dict[str, Any] | None = None
        if asks_period_comparison and ws.comparison and ws.comparison.previous and ws.comparison.current:
            to_sc = curr_score_res.score if curr_score_res is not None else (ws.executive_story.current_score if ws.executive_story else None)
            prev_score_res = self._resolve_cohort_score_result(
                region=resolved["region"],
                month=ws.comparison.previous.month,
                year=ws.comparison.previous.year,
                team=resolved["team"],
                function=resolved["function"],
                position=resolved["position"],
                branch=resolved["branch"],
                performance_level=resolved["performance_level"],
                score_measure=eff_measure,
            )
            if prev_score_res is not None and to_sc is not None and prev_score_res.score is not None:
                from_sc = prev_score_res.score
                chg_sc = round1(to_sc - from_sc)
            elif curr_score_res is not None:
                from_sc = None
                chg_sc = None
            else:
                chg_sc = ws.executive_story.score_change if ws.executive_story else None
                from_sc = (
                    round(float(to_sc) - float(chg_sc), 1)
                    if to_sc is not None and chg_sc is not None
                    else None
                )
            period_comparison_payload = {
                "from_period": f"{ws.comparison.previous.month} {ws.comparison.previous.year}",
                "to_period": f"{ws.comparison.current.month} {ws.comparison.current.year}",
                "from_score": from_sc,
                "to_score": to_sc,
                "delta": chg_sc,
            }

        scored_rows = [r for r in kpi_rows if r.contributes_to_score]
        lowest_kpi = (
            min(scored_rows or kpi_rows, key=lambda r: (r.achievement_percent if r.achievement_percent is not None else 100.0))
            if kpi_rows
            else None
        )
        if curr_score_res is not None:
            avg_score_val = curr_score_res.score
            cohort_score_basis = curr_score_res.score_basis
            cohort_unavailable_reason = curr_score_res.unavailable_reason
            cohort_emp_avg = curr_score_res.employee_average
            if period_comparison_payload and period_comparison_payload.get("delta") is not None:
                score_chg_val = period_comparison_payload["delta"]
            else:
                score_chg_val = None
        else:
            avg_score_val = round(float(ws.executive_story.current_score), 1) if (ws.executive_story and ws.executive_story.current_score is not None) else None
            cohort_score_basis = "average employee score" if eff_measure == "employee_average" else "official score"
            cohort_unavailable_reason = None
            cohort_emp_avg = avg_score_val
            score_chg_val = round(float(ws.executive_story.score_change), 1) if (ws.executive_story and ws.executive_story.score_change is not None) else None
        if kpi and kpi.casefold().rsplit(":", 1)[-1] == "overall_score" and avg_score_val is not None and total_employees:
            typed_evidence.append(TypedMetricEvidence(
                metric_id="overall_score",
                kpi_key="overall_score",
                display_name="Overall PMS Score" if eff_measure == "official" else "Average Employee Score",
                team=base_scope,
                performance_level=resolved["performance_level"] or "Employee",
                branch=resolved["branch"] or "all",
                period=period_label,
                actual=avg_score_val,
                actual_display=f"{avg_score_val:.1f}%",
                unit="%",
                direction="higher_better",
                sample_size=curr_score_res.sample_size if curr_score_res is not None else total_employees,
                source_link=primary_route,
                scoring_basis_status=basis_status,
                scoring_basis_note=basis_note or cohort_score_basis,
            ))
        digest = {
            "period": period_label,
            "scope": scope_label,
            "region": resolved["region"],
            "branch": branch_label,
            "score_measure": eff_measure,
            "score_basis": cohort_score_basis,
            "score_unavailable_reason": cohort_unavailable_reason,
            "employee_average": cohort_emp_avg,
            "average_score": avg_score_val,
            "score_change": score_chg_val,
            "total_records": total_employees,
            "requested_branches": [b.capitalize() for b in requested_branches if user_can_access_branch(self.ctx.scope, b)],
            "branch_comparison": branch_comparison_digest,
            "period_comparison": period_comparison_payload,
            "operational_volumes": volume_summary,
            "requested_kpi": requested_kpi_payload,
            "lowest_kpi": lowest_kpi.model_dump() if lowest_kpi else None,
            "kpis": [r.model_dump() for r in kpi_rows[:8]],
            "decisions": [d.model_dump() for d in kpi_decisions],
        }
        if unavailable_count_metric is not None:
            digest["unavailable_count_metric"] = unavailable_count_metric

        return ToolExecutionResult(
            tool_name="get_kpi_diagnosis_and_trends",
            arguments={
                **resolved,
                "compare_branch": compare_branch,
                "branches": requested_branches,
                "kpi": kpi,
                "score_measure": eff_measure,
            },
            records_evaluated=max(total_employees, len(kpi_rows)),
            digest=digest,
            visual_cards=cards,
            citations=citations,
            deep_links=deep_links,
            typed_evidence=typed_evidence,
            resolved_month=res_month,
            resolved_year=res_year,
            basis_warning=basis_note,
        )

    @_read_only_tool
    def execute_people_contribution_and_rankings(
        self,
        *,
        team: str | None = None,
        function: str | None = None,
        position: str | None = None,
        branch: str | None = None,
        performance_level: str | None = None,
        kpi: str | None = None,
        limit: int = 6,
        include_ties: bool = True,
        direction: str = "best",
        raw_sort_order: str | None = None,
        month: str | None = None,
        year: int | None = None,
        direct_rank_fallback: bool = False,
        score_threshold: float | None = None,
        threshold_operator: str | None = None,
    ) -> ToolExecutionResult:
        resolved = self.ctx.resolve_filters(
            team=team,
            function=function,
            position=position,
            branch=branch,
            performance_level=performance_level,
            month=month,
            year=year,
        )
        cat_kpi_def = (
            get_ai_catalog().find_metric_definition(
                team=resolved["team"],
                kpi_key_or_label=kpi,
                performance_level=resolved["performance_level"] or "Employee",
            )
            if kpi
            else None
        )
        effective_kpi_key = cat_kpi_def.kpi_key if cat_kpi_def else kpi
        ws = self.ctx.insights_service.generate_workspace(
            self.ctx.scope,
            sections="summary,team_summaries,people_contribution_analysis,comparison",
            month=resolved["month"],
            year=resolved["year"],
            region=resolved["region"],
            team=resolved["team"],
            function=resolved["function"],
            position=resolved["position"],
            performance_level=resolved["performance_level"] or "Employee",
            kpi=effective_kpi_key,
            branch=resolved["branch"],
        )

        res_month = ws.comparison.current.month if ws.comparison and ws.comparison.current else resolved["month"]
        res_year = ws.comparison.current.year if ws.comparison and ws.comparison.current else resolved["year"]
        period_label = f"{res_month} {res_year}" if res_month and res_year else "Latest Period"
        scope_label = resolved["team"] or resolved["function"] or "All authorized departments"
        branch_label = resolved["branch"].capitalize() if resolved["branch"] else "All Branches"
        total_employees = sum(int(t.total_employees or 0) for t in (ws.team_summaries or []))

        pca = ws.people_contribution_analysis
        requested_kpi_norm = re.sub(r"[^a-z0-9]", "", str(effective_kpi_key or "").casefold().rsplit(":", 1)[-1])
        if score_threshold is not None or (
            direct_rank_fallback
            and requested_kpi_norm
            and requested_kpi_norm not in {"overallscore", "score", "pmsscore", "overall"}
        ):
            # Contribution analysis ranks score impact. A requested KPI ranking or threshold count
            # must evaluate the requested records directly rather than returning below-target score order.
            pca = None
        if (not pca or not pca.rows) and total_employees == 0:
            direct_rank_fallback = True
        cards: list[StructuredVisualCard] = []
        top_negative_rows: list[dict[str, Any]] = []
        top_positive_rows: list[dict[str, Any]] = []
        pareto_summary: dict[str, Any] = {}
        show_best = str(direction).strip().casefold() == "best"

        if pca and pca.rows:
            neg_rows = [r for r in pca.rows if r.classification in ("negative", "affected")]
            if not neg_rows:
                neg_rows = list(pca.rows)

            # Always build the root-cause (negative contributor) rows for the
            # digest. Downstream headline synthesis in providers.py relies on
            # ``top_contributors`` even for "best"/"why did it drop" answers,
            # so this must not be gated on ``show_best``.
            neg_rows.sort(
                key=lambda r: (
                    r.weighted_impact if r.weighted_impact is not None else 0.0,
                    r.performance_score or 100.0,
                )
            )
            for r in neg_rows[: max(1, min(limit, 10))]:
                clean_kpi = disambiguate_call_center_kpi_label(r.team, r.kpi_key, r.kpi_label)
                top_negative_rows.append(
                    {
                        "employee_id": r.employee_id,
                        "employee_name": r.employee_name,
                        "team": r.team,
                        "kpi": clean_kpi,
                        "performance_score": r.performance_score,
                        "achievement_percent": r.achievement_percent,
                        "weighted_impact": r.weighted_impact,
                    }
                )

            if show_best:
                # "Best" direction: rank employees by performance score, highest first.
                pos_rows = [r for r in pca.rows if r.performance_score is not None]
                pos_rows.sort(key=lambda r: (r.performance_score or 0.0), reverse=True)

                total_pos_impact = sum(float(r.weighted_impact or 0.0) for r in pos_rows)
                top3_pos_impact = sum(float(r.weighted_impact or 0.0) for r in pos_rows[:3])

                entity_items: list[AiEntityListItem] = []
                for r in pos_rows[: max(1, min(limit, 10))]:
                    clean_kpi = disambiguate_call_center_kpi_label(r.team, r.kpi_key, r.kpi_label)
                    score_txt = f"Score {r.performance_score:.1f}%" if r.performance_score is not None else ""
                    ach_txt = f"KPI Ach {r.achievement_percent:.1f}%" if r.achievement_percent is not None else ""
                    impact_txt = f"Impact {r.weighted_impact:+.2f} pts" if r.weighted_impact is not None else ""
                    sub_parts = [p for p in (r.team, clean_kpi, ach_txt, impact_txt) if p]
                    sev = "good" if (r.performance_score or 0.0) >= 85 else ("warning" if (r.performance_score or 0.0) >= 70 else "critical")

                    entity_items.append(
                        AiEntityListItem(
                            id=r.employee_id,
                            title=f"{r.employee_name} ({r.employee_id})",
                            subtitle=" · ".join(sub_parts),
                            badge_text=score_txt,
                            severity=sev,  # type: ignore[arg-type]
                            metric_value=score_txt,
                            route_link=build_verified_deep_link(
                                f"/employee/{r.employee_id}",
                                month=res_month,
                                year=res_year,
                                branch=resolved["branch"],
                            ),
                        )
                    )
                    top_positive_rows.append(
                        {
                            "employee_id": r.employee_id,
                            "employee_name": r.employee_name,
                            "team": r.team,
                            "kpi": clean_kpi,
                            "performance_score": r.performance_score,
                            "achievement_percent": r.achievement_percent,
                            "weighted_impact": r.weighted_impact,
                        }
                    )

                kpi_focus_title = disambiguate_call_center_kpi_label(resolved["team"], pca.kpi_key, pca.kpi_label)
                cards.append(
                    StructuredVisualCard(
                        card_type="entity_list",
                        title=f"Top Performing Employees · {kpi_focus_title}",
                        subtitle=f"{min(limit, len(pos_rows))} of {pca.total_employees} employees ranked by score in {period_label} ({branch_label})",
                        items=entity_items,
                    )
                )

                pareto_summary = {
                    "total_positive_impact_pts": round(total_pos_impact, 2),
                    "top3_positive_impact_pts": round(top3_pos_impact, 2),
                }

                if top_positive_rows:
                    top3_names = ", ".join(r["employee_name"] for r in top_positive_rows[:3])
                    people_decisions: list[AiDecisionItem] = [
                        AiDecisionItem(
                            id="dec-people-recognize",
                            priority="coaching",
                            priority_label="Recognition & Retention",
                            title=f"Recognize Top 3 Performers ({top3_names}) on {kpi_focus_title}",
                            rationale=(
                                f"The top 3 agents lead the team on {kpi_focus_title} with scores "
                                + ", ".join(
                                    f'{r["employee_name"]} {r["performance_score"]:.1f}%'
                                    for r in top_positive_rows[:3]
                                )
                                + ". "
                                f"Protect these high performers and replicate their practices."
                            ),
                            expected_impact=f"Recognizing top performers supports retention across {scope_label}.",
                            target_label=top3_names,
                            route_link=build_verified_deep_link(
                                f"/employee/{top_positive_rows[0]['employee_id']}",
                                month=res_month,
                                year=res_year,
                            ),
                            cta_label="Inspect Top Performer →",
                        ),
                    ]
                    cards.append(
                        StructuredVisualCard(
                            card_type="decision_playbook",
                            title=f"People Recognition Playbook ({scope_label})",
                            subtitle="Top performers and recommended recognition actions",
                            decisions=people_decisions,
                        )
                    )
            else:
                # "Worst" direction: rank negative contributors by impact, lowest first.
                neg_rows.sort(key=lambda r: (r.weighted_impact if r.weighted_impact is not None else 0.0, r.performance_score or 100.0))

                total_neg_impact = sum(abs(float(r.weighted_impact or 0.0)) for r in neg_rows)
                top3_impact = sum(abs(float(r.weighted_impact or 0.0)) for r in neg_rows[:3])
                pareto_share_pct = round((top3_impact / total_neg_impact) * 100.0, 0) if total_neg_impact > 0 else 0.0

                entity_items: list[AiEntityListItem] = []
                for r in neg_rows[: max(1, min(limit, 10))]:
                    clean_kpi = disambiguate_call_center_kpi_label(r.team, r.kpi_key, r.kpi_label)
                    score_txt = f"Score {r.performance_score:.1f}%" if r.performance_score is not None else ""
                    ach_txt = f"KPI Ach {r.achievement_percent:.1f}%" if r.achievement_percent is not None else ""
                    impact_txt = f"Impact {r.weighted_impact:+.2f} pts" if r.weighted_impact is not None else ""
                    sub_parts = [p for p in (r.team, clean_kpi, ach_txt, impact_txt) if p]
                    sev = "critical" if (r.performance_score or 100.0) < 82 or r.severity == "critical" else "warning"

                    entity_items.append(
                        AiEntityListItem(
                            id=r.employee_id,
                            title=f"{r.employee_name} ({r.employee_id})",
                            subtitle=" · ".join(sub_parts),
                            badge_text=score_txt or r.severity.capitalize(),
                            severity=sev,  # type: ignore[arg-type]
                            metric_value=impact_txt or score_txt,
                            route_link=build_verified_deep_link(
                                f"/employee/{r.employee_id}",
                                month=res_month,
                                year=res_year,
                                branch=resolved["branch"],
                            ),
                        )
                    )

                kpi_focus_title = disambiguate_call_center_kpi_label(resolved["team"], pca.kpi_key, pca.kpi_label)
                cards.append(
                    StructuredVisualCard(
                        card_type="entity_list",
                        title=f"Root-Cause Employee Contributors · {kpi_focus_title}",
                        subtitle=f"{pca.negative_contributors} of {pca.total_employees} employees below target in {period_label} ({branch_label})",
                        items=entity_items,
                    )
                )

                pareto_summary = {
                    "total_negative_impact_pts": round(total_neg_impact, 2),
                    "top3_negative_impact_pts": round(top3_impact, 2),
                    "top3_pareto_share_pct": pareto_share_pct,
                }

                if top_negative_rows:
                    top3_names = ", ".join(r["employee_name"] for r in top_negative_rows[:3])
                    low_score_agents = [r for r in top_negative_rows if (r.get("performance_score") or 100.0) < 85.0]
                    people_decisions: list[AiDecisionItem] = [
                        AiDecisionItem(
                            id="dec-people-pareto",
                            priority="immediate",
                            priority_label=f"Pareto 80/20 Focus · {pareto_share_pct:.0f}% of Loss",
                            title=f"Target Top 3 Contributors ({top3_names}) on {kpi_focus_title}",
                            rationale=(
                                f"The top 3 agents account for {pareto_share_pct:.0f}% (-{top3_impact:.2f} pts out of -{total_neg_impact:.2f} pts) "
                                f"of the team's weighted loss on {kpi_focus_title}."
                            ),
                            expected_impact=(
                                f"What-If ROI: Coaching only these 3 agents to target recovers +{top3_impact:.2f} pts "
                                f"on the {scope_label} team score immediately."
                            ),
                            target_label=top3_names,
                            route_link=build_verified_deep_link(
                                f"/employee/{top_negative_rows[0]['employee_id']}",
                                month=res_month,
                                year=res_year,
                            ),
                            cta_label="Inspect Top Contributor →",
                        ),
                        AiDecisionItem(
                            id="dec-people-coaching-tier",
                            priority="coaching",
                            priority_label="14-Day Coaching Plan",
                            title=(
                                f"Launch Call & Booking Qualification Review for {len(low_score_agents) or len(top_negative_rows[:3])} Flagged Agents"
                            ),
                            rationale=(
                                f"{pca.negative_contributors} of {pca.total_employees} agents missed target on {kpi_focus_title}. "
                                "Audit sample calls and appointment confirmation scripts to close execution gaps."
                            ),
                            expected_impact=f"Full team recovery to target adds +{total_neg_impact:.2f} pts across {scope_label}.",
                            target_label=f"{pca.negative_contributors} Below-Target Agents in {scope_label}",
                            route_link=build_verified_deep_link(
                                "/planning",
                                month=res_month,
                                year=res_year,
                                team=resolved["team"],
                            ),
                            cta_label="Open Coaching & Planning →",
                        ),
                    ]
                    cards.append(
                        StructuredVisualCard(
                            card_type="decision_playbook",
                            title=f"People Coaching & What-If Playbook ({scope_label})",
                            subtitle="Pareto impact concentration and recommended supervisory interventions",
                            decisions=people_decisions,
                        )
                    )

        citations = [
            SourceCitationPill(label=f"Period · {period_label}", category="period"),
            SourceCitationPill(label=f"Scope · {scope_label}", category="scope"),
            SourceCitationPill(label=f"Branch · {branch_label}", category="branch"),
            SourceCitationPill(
                label=f"Below Target · {pca.negative_contributors if pca else 0}/{pca.total_employees if pca else total_employees}",
                category="metric",
            ),
        ]

        deep_links = [
            DeepLinkCta(
                label="Open People Contribution in Insights →",
                route=build_verified_deep_link(
                    "/insights",
                    month=res_month,
                    year=res_year,
                    function=resolved["function"],
                    team=resolved["team"],
                    branch=resolved["branch"],
                    kpi=kpi or (pca.kpi_key if pca else None),
                ),
                icon_key="insights",
            )
        ]
        ranked_rows = top_positive_rows if show_best else top_negative_rows
        if ranked_rows:
            first_emp_id = ranked_rows[0]["employee_id"]
            deep_links.append(
                DeepLinkCta(
                    label=f"Open {ranked_rows[0]['employee_name']} Profile →",
                    route=build_verified_deep_link(f"/employee/{first_emp_id}", month=res_month, year=res_year),
                    icon_key="employee",
                )
            )

        digest = {
            "period": period_label,
            "scope": scope_label,
            "region": resolved["region"],
            "branch": branch_label,
            "kpi_analyzed": disambiguate_call_center_kpi_label(resolved["team"], pca.kpi_key, pca.kpi_label) if pca else kpi,
            "total_employees": pca.total_employees if pca else total_employees,
            "direction": direction,
            # ``top_contributors`` keeps its original root-cause (worst-first,
            # negative impact) meaning because downstream headline synthesis in
            # providers.py relies on it. Best-performer results are exposed
            # separately so "top N" answers never flip a root-cause headline.
            "top_contributors": top_negative_rows,
            "negative_contributors": pca.negative_contributors if pca else 0,
            "pareto_summary": pareto_summary,
        }
        if show_best:
            digest["top_performers"] = top_positive_rows

        # Per-department top-N breakdown: when no single team is filtered and the
        # user asks for "best" employees, return the top N within each department.
        if show_best and pca and pca.rows and not resolved["team"]:
            by_department: dict[str, list[dict[str, Any]]] = {}
            for row in top_positive_rows:
                dept = row.get("team") or resolved["team"] or "All Departments"
                by_department.setdefault(dept, []).append(row)
            # Keep only top N per department (limit is per-department when grouped).
            by_department = {
                dept: rows[: max(1, min(limit, 10))] for dept, rows in by_department.items()
            }
            digest["by_department"] = by_department

        typed_evidence: list[TypedMetricEvidence] = []
        if pca and pca.rows:
            target_rows = neg_rows[: max(1, min(limit, 10))]
            for r in target_rows:
                score_val = r.performance_score
                impact_val = r.weighted_impact
                val = score_val if score_val is not None else impact_val
                clean_kpi = disambiguate_call_center_kpi_label(r.team, r.kpi_key, r.kpi_label)
                typed_evidence.append(
                    TypedMetricEvidence(
                        metric_id=f"ranking:{r.employee_id}",
                        kpi_key=r.kpi_key or "overall_score",
                        display_name=clean_kpi or "Overall Score",
                        team=r.team or resolved["team"] or "Call Center",
                        performance_level=resolved["performance_level"] or "Employee",
                        branch=resolved["branch"] or "all",
                        period=period_label,
                        actual=round(float(val), 2) if val is not None else None,
                        actual_display=f"{val:.1f}%" if val is not None else "Unavailable",
                        unit="%",
                        direction="higher_better",
                        employee_id=r.employee_id,
                        employee_name=r.employee_name,
                        source_link=build_verified_deep_link(
                            f"/employee/{r.employee_id}",
                            month=res_month,
                            year=res_year,
                            branch=resolved["branch"],
                        ),
                    )
                )

        ranked_recs_count = 0
        if (direct_rank_fallback or score_threshold is not None) and not typed_evidence:
            eff_rank_level = str(resolved["performance_level"] or "Employee")
            period_recs = [
                r for r in self.ctx.get_scoped_records()
                if (
                    not resolved["team"]
                    or str(_record_field(r, "team", "")).casefold() == str(resolved["team"]).casefold()
                    or str(_record_field(r, "team", "")).casefold() in {key.casefold() for key in selection_team_keys(resolved["team"])}
                )
                and (not res_month or str(_record_field(r, "month", "")).casefold() == str(res_month).casefold())
                and (not res_year or int(_record_field(r, "year", 0) or 0) == int(res_year))
                and (
                    str(_record_field(r, "performance_level", "Employee") or "Employee").casefold()
                    == eff_rank_level.casefold()
                )
                and (
                    not resolved["region"]
                    or _shared_record_region(r, str(_record_field(r, "team", ""))).casefold()
                    == str(resolved["region"]).casefold()
                )
                and (not resolved["branch"] or record_matches_branch(r, resolved["branch"]))
            ]
            ranked_recs_count = len(period_recs)
            if score_threshold is not None:
                op_norm = " ".join(str(threshold_operator or "above").casefold().split())
                if op_norm in ("at least", ">="):
                    op_cmp = lambda v, t: v >= t
                    op_label = "at least"
                elif op_norm in ("below", "under", "less than", "<"):
                    op_cmp = lambda v, t: v < t
                    op_label = op_norm if op_norm in ("below", "under", "less than") else "below"
                else:
                    op_cmp = lambda v, t: v > t
                    op_label = op_norm if op_norm in ("above", "over", "more than") else "above"

                use_specific_kpi = bool(
                    effective_kpi_key
                    and requested_kpi_norm not in {"", "overallscore", "score", "pmsscore", "overall"}
                )
                qualifying_rows: list[tuple[Any, float, dict[str, Any] | None]] = []
                evaluated_count = 0
                for record in period_recs:
                    snap: dict[str, Any] | None = None
                    val: float | None = None
                    if use_specific_kpi and effective_kpi_key:
                        snap = self._extract_record_kpi_snapshot(
                            record,
                            effective_kpi_key,
                            team_hint=resolved["team"],
                            position_hint=resolved["position"],
                        )
                        if snap and snap.get("numeric_value") is not None:
                            val = float(snap["numeric_value"])
                    else:
                        val = _record_evaluation_score(record)
                    if val is None:
                        continue
                    evaluated_count += 1
                    if op_cmp(val, float(score_threshold)):
                        qualifying_rows.append((record, val, snap))

                qualifying_rows.sort(key=lambda item: item[1], reverse=True)
                team_label_for_ev = resolved["team"] or scope_label
                team_slug = re.sub(r"[^a-z0-9]+", "_", team_label_for_ev.casefold()).strip("_") or "team"
                team_route = build_verified_deep_link(
                    f"/team/{_team_route_slug(team_label_for_ev)}",
                    month=res_month,
                    year=res_year,
                    function=resolved["function"],
                    team=resolved["team"],
                    branch=resolved["branch"],
                    performance_level=eff_rank_level,
                )
                typed_evidence.append(
                    TypedMetricEvidence(
                        metric_id=f"{team_slug}:qualifying_employee_count",
                        kpi_key="qualifying_employee_count",
                        display_name="Qualifying Employees",
                        team=team_label_for_ev,
                        performance_level=eff_rank_level,
                        branch=resolved["branch"] or "all",
                        period=period_label,
                        actual=float(len(qualifying_rows)),
                        actual_display=f"{len(qualifying_rows)} count",
                        unit="count",
                        direction="higher_better",
                        sample_size=evaluated_count or ranked_recs_count,
                        employee_id=None,
                        employee_name=None,
                        source_link=team_route,
                    )
                )
                qualifying_summary_list: list[dict[str, Any]] = []
                for record, val, snap in qualifying_rows:
                    emp_id_val = str(_record_field(record, "employee_id", ""))
                    emp_name_val = str(_record_field(record, "employee_name", "") or emp_id_val)
                    r_team = str(_record_field(record, "team", "") or team_label_for_ev)
                    r_level = str(_record_field(record, "performance_level", "") or eff_rank_level)
                    emp_route = build_verified_deep_link(
                        f"/employee/{emp_id_val}",
                        month=res_month,
                        year=res_year,
                        branch=resolved["branch"],
                    )
                    qualifying_summary_list.append(
                        {
                            "employee_id": emp_id_val,
                            "employee_name": emp_name_val,
                            "score": round(float(val), 2),
                            "unit": str(snap.get("unit") or "%") if snap else "%",
                        }
                    )
                    if snap is not None:
                        typed_evidence.append(
                            TypedMetricEvidence(
                                metric_id=f"ranking:{emp_id_val}:{snap.get('kpi_key') or effective_kpi_key}",
                                kpi_key=str(snap.get("kpi_key") or effective_kpi_key),
                                display_name=str(snap.get("kpi_label") or snap.get("kpi_key") or effective_kpi_key),
                                team=r_team,
                                performance_level=r_level,
                                branch=str(_record_field(record, "branch", "") or "all"),
                                period=period_label,
                                actual=round(float(val), 2),
                                target=float(snap["target_numeric"]) if snap.get("target_numeric") is not None else None,
                                actual_display=str(snap.get("actual_display") or val),
                                target_display=None,
                                unit=str(snap.get("unit") or ""),
                                direction=str(snap.get("direction") or "higher_better"),
                                sample_size=evaluated_count or ranked_recs_count,
                                employee_id=emp_id_val,
                                employee_name=emp_name_val,
                                source_link=emp_route,
                            )
                        )
                    else:
                        typed_evidence.append(
                            TypedMetricEvidence(
                                metric_id=f"ranking:{emp_id_val}",
                                kpi_key="overall_score",
                                display_name="Overall Score",
                                team=r_team,
                                performance_level=r_level,
                                branch=str(_record_field(record, "branch", "") or "all"),
                                period=period_label,
                                actual=round(float(val), 2),
                                actual_display=f"{val:.1f}%",
                                unit="%",
                                direction="higher_better",
                                sample_size=evaluated_count or ranked_recs_count,
                                employee_id=emp_id_val,
                                employee_name=emp_name_val,
                                source_link=emp_route,
                            )
                        )
                digest["threshold_count_summary"] = {
                    "count": len(qualifying_rows),
                    "total_evaluated": evaluated_count or ranked_recs_count,
                    "operator_label": op_label,
                    "threshold": float(score_threshold),
                    "team": scope_label,
                    "period": period_label,
                    "qualifying_employees": qualifying_summary_list,
                }
                digest["total_employees"] = evaluated_count or ranked_recs_count
                eval_records = evaluated_count or ranked_recs_count
            elif effective_kpi_key:
                ranked_snapshots: list[tuple[Any, dict[str, Any]]] = []
                for record in period_recs:
                    snapshot = self._extract_record_kpi_snapshot(
                        record,
                        effective_kpi_key,
                        team_hint=resolved["team"],
                        position_hint=resolved["position"],
                    )
                    if snapshot and snapshot.get("numeric_value") is not None:
                        ranked_snapshots.append((record, snapshot))
                metric_direction = str(
                    ranked_snapshots[0][1].get("direction") if ranked_snapshots else "higher_better"
                )
                wants_high = str(direction or "best").casefold() not in ("worst", "lowest", "lower")
                reverse = (
                    raw_sort_order == "desc" if raw_sort_order in ("asc", "desc")
                    else wants_high != (metric_direction == "lower_better")
                )
                ranked_snapshots.sort(
                    key=lambda pair: float(pair[1].get("numeric_value") or 0.0),
                    reverse=reverse,
                )
                selected_snapshots = ranked_snapshots[: max(1, min(limit, 10))]
                if include_ties and selected_snapshots:
                    cutoff_value = float(selected_snapshots[-1][1].get("numeric_value") or 0.0)
                    next_idx = len(selected_snapshots)
                    while next_idx < len(ranked_snapshots):
                        next_value = float(ranked_snapshots[next_idx][1].get("numeric_value") or 0.0)
                        if abs(next_value - cutoff_value) > 1e-9:
                            break
                        selected_snapshots.append(ranked_snapshots[next_idx])
                        next_idx += 1
                for record, snapshot in selected_snapshots:
                    emp_id_val = str(_record_field(record, "employee_id", ""))
                    emp_name_val = str(_record_field(record, "employee_name", "") or emp_id_val)
                    r_team = str(_record_field(record, "team", "") or resolved["team"] or "Call Center")
                    typed_evidence.append(
                        TypedMetricEvidence(
                            metric_id=f"ranking:{emp_id_val}:{snapshot.get('kpi_key') or effective_kpi_key}",
                            kpi_key=str(snapshot.get("kpi_key") or effective_kpi_key),
                            display_name=str(snapshot.get("kpi_label") or snapshot.get("kpi_key") or effective_kpi_key),
                            team=r_team,
                            performance_level=str(_record_field(record, "performance_level", "") or "Employee"),
                            branch=str(_record_field(record, "branch", "") or "all"),
                            period=period_label,
                            actual=float(snapshot["numeric_value"]),
                            target=float(snapshot["target_numeric"]) if snapshot.get("target_numeric") is not None else None,
                            actual_display=str(snapshot.get("actual_display") or snapshot["numeric_value"]),
                            target_display=None,
                            unit=str(snapshot.get("unit") or ""),
                            direction=str(snapshot.get("direction") or "higher_better"),
                            sample_size=ranked_recs_count,
                            employee_id=emp_id_val,
                            employee_name=emp_name_val,
                            source_link=build_verified_deep_link(
                                f"/employee/{emp_id_val}",
                                month=res_month,
                                year=res_year,
                                branch=resolved["branch"],
                            ),
                        )
                    )
            else:
                wants_high = str(direction or "best").casefold() not in ("worst", "lowest", "lower")
                if raw_sort_order in ("asc", "desc"):
                    wants_high = raw_sort_order == "desc"
                period_recs.sort(key=lambda r: _record_evaluation_score(r) or 0.0, reverse=wants_high)
                selected_records = period_recs[: max(1, min(limit, 10))]
                if include_ties and selected_records:
                    cutoff_score = _record_evaluation_score(selected_records[-1])
                    next_idx = len(selected_records)
                    while cutoff_score is not None and next_idx < len(period_recs):
                        next_score = _record_evaluation_score(period_recs[next_idx])
                        if next_score is None or abs(next_score - cutoff_score) > 1e-9:
                            break
                        selected_records.append(period_recs[next_idx])
                        next_idx += 1
                for record in selected_records:
                    score = _record_evaluation_score(record)
                    emp_id_val = str(_record_field(record, "employee_id", ""))
                    emp_name_val = str(_record_field(record, "employee_name", "") or emp_id_val)
                    r_team = str(_record_field(record, "team", "") or resolved["team"] or "Call Center")
                    typed_evidence.append(
                        TypedMetricEvidence(
                            metric_id=f"ranking:{emp_id_val}",
                            kpi_key="overall_score",
                            display_name="Overall Score",
                            team=r_team,
                            performance_level=str(_record_field(record, "performance_level", "") or "Employee"),
                            branch=str(_record_field(record, "branch", "") or "all"),
                            period=period_label,
                            actual=round(float(score), 2) if score is not None else None,
                            actual_display=f"{score:.1f}%" if score is not None else "Unavailable",
                            unit="%",
                            direction="higher_better",
                            employee_id=emp_id_val,
                            employee_name=emp_name_val,
                            source_link=build_verified_deep_link(
                                f"/employee/{emp_id_val}",
                                month=res_month,
                                year=res_year,
                                branch=resolved["branch"],
                            ),
                        )
                    )

        eval_records = (
            digest["threshold_count_summary"]["total_evaluated"]
            if "threshold_count_summary" in digest
            else (
                pca.total_employees
                if (pca and pca.total_employees)
                else (total_employees or ranked_recs_count)
            )
        )

        return ToolExecutionResult(
            tool_name="get_people_contribution_and_rankings",
            arguments={**resolved, "kpi": kpi},
            records_evaluated=eval_records,
            digest=digest,
            visual_cards=cards,
            citations=citations,
            deep_links=deep_links,
            typed_evidence=typed_evidence,
            resolved_month=res_month,
            resolved_year=res_year,
        )

    @_read_only_tool
    def execute_discover_pms_catalog(
        self,
        *,
        query: str | None = None,
        kind: str = "all",
        region: str | None = None,
        department: str | None = None,
        team: str | None = None,
        performance_level: str | None = None,
    ) -> ToolExecutionResult:
        """Scoped, read-only catalog discovery over live authorized PMS entities and published periods.

        Strictly enforces caller RBAC: inaccessible departments, teams, branches,
        positions, KPIs, and employees are never returned.
        """
        q_norm = str(query or "").strip().casefold()
        kind_norm = str(kind or "all").strip().casefold()
        reg_norm = str(region or "").strip().upper() or None
        dept_norm = str(department or "").strip().casefold() or None
        team_norm = str(team or "").strip().casefold() or None
        lvl_norm = str(performance_level or "").strip().casefold() or None

        # 1. Authorized records (already filtered by caller's RBAC scope)
        scoped_records = self.ctx.get_scoped_records()
        is_self_only = bool(self.ctx.scope.get("is_self_only"))
        caller_emp_id = str(self.ctx.scope.get("employee_id") or "").strip().casefold()

        departments: dict[str, set[str]] = {}
        team_periods: dict[str, set[str]] = {}
        team_regions: dict[str, set[str]] = {}
        team_positions: dict[str, set[str]] = {}
        branches_seen: set[str] = set()
        levels_seen: set[str] = set()
        periods_by_region: dict[str, set[str]] = {}
        employees_seen: dict[str, dict[str, Any]] = {}

        for record in scoped_records:
            rec_team = str(_record_field(record, "team", "") or "").strip()
            if not rec_team:
                continue
            rec_dept = function_for_team(rec_team) or rec_team
            rec_reg = _shared_record_region(record, rec_team)
            rec_lvl = str(_record_field(record, "performance_level", "Employee") or "Employee")
            rec_pos = str(_record_field(record, "position", "") or "").strip()
            rec_branch = str(_record_field(record, "branch_key") or _record_field(record, "branch") or "").strip().casefold()
            rec_month = str(_record_field(record, "month", "") or "").strip()
            rec_year = _record_field(record, "year", None)
            m_num = MONTH_ORDER.get(rec_month)
            period_key = f"{int(rec_year):04d}-{int(m_num):02d}" if (m_num and rec_year) else None

            if reg_norm and rec_reg.upper() != reg_norm:
                continue
            if dept_norm and rec_dept.casefold() != dept_norm and rec_team.casefold() != dept_norm:
                continue
            if team_norm and rec_team.casefold() != team_norm and _display_team_name(rec_team).casefold() != team_norm:
                continue
            if lvl_norm and rec_lvl.casefold() != lvl_norm:
                continue

            disp_team = _display_team_name(rec_team)
            departments.setdefault(rec_dept, set()).add(disp_team)
            team_regions.setdefault(disp_team, set()).add(rec_reg)
            levels_seen.add(rec_lvl)
            if period_key:
                team_periods.setdefault(disp_team, set()).add(period_key)
                periods_by_region.setdefault(rec_reg, set()).add(period_key)
            if rec_pos:
                team_positions.setdefault(disp_team, set()).add(rec_pos)
            if rec_branch and rec_branch in BRANCH_KEYS and user_can_access_branch(self.ctx.scope, rec_branch):
                branches_seen.add(rec_branch)

            emp_id = str(_record_field(_record_field(record, "employee"), "id") or _record_field(record, "employee_id") or "").strip()
            emp_name = str(_record_field(_record_field(record, "employee"), "name") or _record_field(record, "employee_name") or "").strip()
            if emp_id and emp_name:
                if is_self_only and emp_id.casefold() != caller_emp_id:
                    continue
                if emp_id not in employees_seen:
                    employees_seen[emp_id] = {
                        "employee_id": emp_id,
                        "employee_name": emp_name,
                        "team": disp_team,
                        "department": rec_dept,
                        "position": rec_pos or None,
                        "region": rec_reg,
                        "periods": set(),
                    }
                if period_key:
                    employees_seen[emp_id]["periods"].add(period_key)

        # 2. Authorized KPI catalog metrics (filtered to authorized teams, region, and level)
        auth_catalog = get_ai_catalog().get_authorized_catalog_payload(scope=self.ctx.scope)
        auth_team_keys = {
            str(getattr(t, "value", None) or getattr(t, "label", None) or getattr(t, "team", None)).casefold()
            for t in auth_catalog.eligible_teams
            if getattr(t, "value", None) or getattr(t, "label", None) or getattr(t, "team", None)
        }
        scoped_region_team_keys = {t.casefold() for t in team_periods}
        matched_metrics: list[dict[str, Any]] = []
        if kind_norm in ("all", "metric"):
            for m in auth_catalog.metrics:
                m_team = str(getattr(m, "team", "") or "")
                m_level = str(getattr(m, "performance_level", "") or "")
                if team_norm and m_team.casefold() != team_norm:
                    continue
                if dept_norm and (function_for_team(m_team) or m_team).casefold() != dept_norm:
                    continue
                if reg_norm and m_team and scoped_region_team_keys and m_team.casefold() not in scoped_region_team_keys:
                    continue
                if lvl_norm and m_level and m_level.casefold() != lvl_norm:
                    continue
                if m_team and auth_team_keys and m_team.casefold() not in auth_team_keys and not self.ctx.scope.get("has_unrestricted_team_access"):
                    continue
                searchable = " ".join(
                    [
                        str(getattr(m, "metric_id", "")),
                        str(getattr(m, "kpi_key", "")),
                        str(getattr(m, "display_name", "")),
                        m_team,
                        " ".join(getattr(m, "aliases", []) or []),
                    ]
                ).casefold()
                if not q_norm or q_norm in searchable or any(tok in searchable for tok in q_norm.split() if len(tok) >= 3):
                    matched_metrics.append(
                        {
                            "metric_id": getattr(m, "metric_id", ""),
                            "kpi_key": getattr(m, "kpi_key", ""),
                            "display_name": getattr(m, "display_name", ""),
                            "team": m_team,
                            "unit": getattr(m, "unit", "%"),
                            "direction": getattr(m, "direction", "higher_better"),
                        }
                    )

        def _matches_query(text_val: str) -> bool:
            if not q_norm:
                return True
            tv = text_val.casefold()
            return q_norm in tv or any(tok in tv for tok in q_norm.split() if len(tok) >= 3)

        dept_list = [
            {
                "department": d,
                "teams": sorted(ts),
                "role_based_single_team": (
                    len(ts) == 1
                    and next(iter(ts)).casefold() == d.casefold()
                    and len(team_positions.get(next(iter(ts)), set())) > 1
                ),
            }
            for d, ts in sorted(departments.items())
            if kind_norm in ("all", "department", "periods") and (_matches_query(d) or any(_matches_query(t) for t in ts))
        ]
        team_list = [
            {
                "team": t,
                "department": next((d for d, ts in departments.items() if t in ts), t),
                "regions": sorted(team_regions.get(t, set())),
                "positions": sorted(team_positions.get(t, set()))[:12],
                "published_periods": sorted(team_periods.get(t, set())),
            }
            for t in sorted(team_periods.keys())
            if kind_norm in ("all", "team", "periods") and _matches_query(t)
        ]
        position_list = [
            {"position": p, "team": t}
            for t, ps in sorted(team_positions.items())
            for p in sorted(ps)
            if kind_norm in ("all", "position") and (_matches_query(p) or _matches_query(t))
        ]
        emp_list = [
            {
                "employee_id": e["employee_id"],
                "employee_name": e["employee_name"],
                "team": e["team"],
                "department": e["department"],
                "position": e["position"],
                "region": e["region"],
                "published_periods": sorted(e["periods"]),
            }
            for e in sorted(employees_seen.values(), key=lambda x: x["employee_name"].casefold())
            if kind_norm in ("all", "employee") and (_matches_query(e["employee_name"]) or _matches_query(e["employee_id"]))
        ][:15]

        all_periods = sorted({p for ps in periods_by_region.values() for p in ps})
        discovery_payload = {
            "query": query,
            "kind": kind_norm,
            "region_filter": reg_norm,
            "departments": dept_list[:20],
            "teams": team_list[:25],
            "positions": position_list[:25],
            "branches": sorted(branches_seen) if kind_norm in ("all", "branch") else [],
            "performance_levels": sorted(levels_seen),
            "metrics": matched_metrics[:20],
            "employees": emp_list,
            "published_periods_by_region": {r: sorted(ps) for r, ps in sorted(periods_by_region.items())},
            "all_published_periods": all_periods,
        }
        return ToolExecutionResult(
            tool_name="discover_pms_catalog",
            arguments={
                "query": query,
                "kind": kind_norm,
                "region": reg_norm,
                "department": department,
                "team": team,
                "performance_level": performance_level,
            },
            records_evaluated=len(dept_list) + len(team_list) + len(matched_metrics) + len(emp_list),
            digest={"catalog_discovery": discovery_payload},
            citations=[SourceCitationPill(label="Authorized PMS Catalog", category="scope")],
        )

    @_read_only_tool
    def execute_query_rankings(
        self,
        *,
        entity: str = "department",
        sort_order: str = "desc",
        limit: int = 10,
        group_by: str = "none",
        per_group_limit: int = 5,
        region: str | None = None,
        department: str | None = None,
        team: str | None = None,
        position: str | None = None,
        branch: str | None = None,
        performance_level: str | None = None,
        metric_id: str | None = None,
        period: str | None = None,
        score_threshold: float | None = None,
        threshold_operator: str | None = None,
        score_measure: str | None = None,
    ) -> ToolExecutionResult:
        """One composable engine for entity/sort/N/region/grouping/threshold rankings.

        All reads go through the RBAC-scoped context. "Department" is resolved
        from the record's function (falling back to its team), so a scoped
        manager can only ever see the departments their role authorizes.
        """
        eff_measure: ScoreMeasure = "employee_average" if score_measure == "employee_average" else "official"
        spec = QueryRankingsArgs(
            entity=entity,  # type: ignore[arg-type]
            sort_order=sort_order,  # type: ignore[arg-type]
            limit=max(1, min(int(limit), 50)),
            group_by=group_by,  # type: ignore[arg-type]
            per_group_limit=max(1, min(int(per_group_limit), 20)),
            region=region,
            department=department,
            team=team,
            position=position,
            branch=branch,
            performance_level=performance_level,
            metric_id=metric_id,
            period=period,
            score_threshold=score_threshold,
            threshold_operator=threshold_operator,
            score_measure=eff_measure,
        )
        reverse = spec.sort_order == "desc"
        month, year = _period_key_to_month_year(spec.period) if spec.period else (None, None)
        resolved = self.ctx.resolve_filters(
            team=spec.team,
            function=spec.department,
            position=spec.position,
            branch=spec.branch,
            performance_level=spec.performance_level,
            month=month,
            year=year,
        )
        # Prevent stale session_state drill-down filters from leaking into broader rankings.
        if spec.entity == "department":
            if spec.team is None:
                resolved["team"] = None
            if spec.department is None:
                resolved["function"] = None
            if spec.position is None:
                resolved["position"] = None
        elif spec.entity == "team":
            if spec.position is None:
                resolved["position"] = None
            if spec.team is None and spec.department is not None:
                resolved["team"] = None
        elif spec.entity == "position" and spec.position is None:
            resolved["position"] = None
        rank_region = spec.region or resolved["region"]
        scope_parts = list(dict.fromkeys(filter(None, (
            spec.team or spec.department or resolved["team"] or resolved["function"],
            resolved["position"],
            {"EGY": "Egypt", "UAE": "UAE"}.get(rank_region, rank_region),
        ))))
        scope_label = " · ".join(scope_parts) or "All authorized departments"
        branch_label = (spec.branch or resolved["branch"] or "all").capitalize()
        period_label = f"{resolved['month']} {resolved['year']}" if resolved["month"] and resolved["year"] else "Latest Period"

        cards: list[StructuredVisualCard] = []
        rows: list[dict[str, Any]] = []
        groups: dict[str, list[dict[str, Any]]] = {}
        citations = [
            SourceCitationPill(label=f"Scope · {scope_label}", category="scope"),
            SourceCitationPill(label=f"Period · {period_label}", category="period"),
            SourceCitationPill(label=f"Order · {'High → Low' if reverse else 'Low → High'}", category="metric"),
        ]

        locked_teams = selection_team_keys(resolved["team"]) if resolved["team"] else None
        locked_function = function_team_keys(resolved["function"]) if resolved["function"] else None
        level = str(resolved["performance_level"] or "Employee").casefold()
        cohort = []
        for record in self.ctx.get_scoped_records():
            rec_team = str(_record_field(record, "team", "") or "")
            if locked_teams is not None and rec_team.casefold() not in locked_teams:
                continue
            if locked_function is not None and rec_team.casefold() not in locked_function:
                continue
            if rank_region and _shared_record_region(record, rec_team).casefold() != rank_region.casefold():
                continue
            if resolved["month"] and _record_field(record, "month") != resolved["month"]:
                continue
            if resolved["year"] and _record_field(record, "year") != resolved["year"]:
                continue
            if str(_record_field(record, "performance_level", "Employee") or "Employee").casefold() != level:
                continue
            if resolved["position"] and str(_record_field(record, "position", "") or "").casefold() != resolved["position"].casefold():
                continue
            if resolved["branch"] and not record_matches_branch(record, resolved["branch"]):
                continue
            cohort.append(project_record_for_branch(record, resolved["branch"]))

        role_scope_target = spec.department or spec.team or resolved["team"] or resolved["function"]
        if spec.entity == "team" and role_scope_target and not resolved["position"]:
            source_teams = {str(_record_field(record, "team", "")).casefold() for record in cohort}
            source_positions = {value for record in cohort if (value := _record_field(record, "position"))}
            if source_teams == {role_scope_target.casefold()} and len(source_positions) > 1:
                # Some standalone departments are uploaded as one team with
                # separate role scorecards. Rank those measured roles.
                spec = spec.model_copy(update={"entity": "position"})

        overall = (spec.metric_id or "overall_score").rsplit(":", 1)[-1].casefold() in {
            "overall_score", "pms_score", "score", "overall_pms_score", "average_score", "job_title", "position", "role",
        }
        if spec.entity == "kpi" or (not overall and spec.entity != "employee"):
            return ToolExecutionResult(
                tool_name="get_query_rankings", arguments=spec.model_dump(),
                digest={"unavailable_reason": "This grouping needs a verified KPI aggregation."},
                citations=citations,
            )
        excluded_unverified: list[dict[str, str]] = []
        total_candidates = 0
        if spec.entity == "employee":
            source_rows = []
            for record in cohort:
                metric = self._extract_record_kpi_snapshot(record, spec.metric_id) if not overall else None
                if not overall and metric is None:
                    continue
                source_rows.append({
                    "employee_id": _record_field(_record_field(record, "employee"), "id") or _record_field(record, "employee_id"),
                    "employee_name": _record_field(_record_field(record, "employee"), "name") or _record_field(record, "employee_name"),
                    "team": _record_field(record, "team"),
                    "position": _record_field(record, "position"),
                    "performance_score": metric["numeric_value"] if metric else _record_evaluation_score(record),
                    "unit": metric["unit"] if metric else "%",
                    "actual_display": metric["actual_display"] if metric else None,
                    "direction": metric["direction"] if metric else "higher_better",
                })
            for r in source_rows:
                score = r.get("performance_score")
                score_val = float(score) if score is not None else None
                if score_val is None or is_excluded_by_threshold(spec.score_threshold, spec.threshold_operator, score_val):
                    continue
                rows.append({
                    "id": r.get("employee_id"),
                    "name": r.get("employee_name"),
                    "team": r.get("team"),
                    "position": r.get("position"),
                    "score": score_val,
                    "actual_display": r.get("actual_display") or f"{score_val:.2f}%",
                    "unit": r["unit"],
                    "direction": r["direction"],
                    "weighted_impact": r.get("weighted_impact"),
                    "kpi": r.get("kpi"),
                    "route": build_verified_deep_link(
                        f"/employee/{r.get('employee_id')}", month=resolved["month"], year=resolved["year"]
                    ),
                })
            # Re-sort by score for the requested order (source rows may be impact-ranked).
            rows.sort(key=lambda r: ((-1 if reverse else 1) * r["score"], str(r.get("name") or "").casefold()))

            def _slice_with_ties(items: list[dict[str, Any]], cap: int) -> list[dict[str, Any]]:
                if cap <= 0 or len(items) <= cap:
                    return items[: max(cap, 0)]
                cutoff = round(float(items[cap - 1].get("score") or 0.0), 2)
                out = list(items[:cap])
                for nxt in items[cap : cap + 10]:
                    if abs(round(float(nxt.get("score") or 0.0), 2) - cutoff) < 1e-6:
                        out.append(nxt)
                    else:
                        break
                return out

            if spec.group_by != "none":
                for row in rows:
                    key = (
                        (function_for_team(row.get("team") or "") if spec.group_by == "department" else row.get("team"))
                        or resolved["team"]
                        or resolved["function"]
                        or "All Departments"
                    )
                    groups.setdefault(str(key), []).append(row)
                groups = {k: _slice_with_ties(v, spec.per_group_limit) for k, v in groups.items()}
                for gname, grows in list(groups.items())[:6]:
                    cards.append(
                        StructuredVisualCard(
                            card_type="entity_list",
                            title=f"{'Top' if reverse else 'Bottom'} {len(grows)} · {gname}",
                            subtitle=f"{spec.entity.replace('_', ' ').title()} ranking in {gname} · {period_label}",
                            items=[
                                AiEntityListItem(
                                    id=str(r.get("id") or ""),
                                    title=str(r.get("name") or "Unknown"),
                                    subtitle=r["actual_display"],
                                    badge_text=r["actual_display"],
                                    route_link=r.get("route"),
                                )
                                for r in grows
                            ],
                        )
                    )
            else:
                rows = _slice_with_ties(rows, spec.limit)
                cards.append(
                    StructuredVisualCard(
                        card_type="entity_list",
                        title=f"{'Top' if reverse else 'Bottom'} {len(rows)} {spec.entity.replace('_', ' ').title()}s",
                        subtitle=f"Ranked {'high → low' if reverse else 'low → high'} · {period_label} ({branch_label})",
                        items=[
                            AiEntityListItem(
                                id=str(r.get("id") or ""),
                                title=str(r.get("name") or "Unknown"),
                                subtitle=(f"· {r.get('team')}" if r.get("team") else ""),
                                badge_text=r["actual_display"],
                                route_link=r.get("route"),
                            )
                            for r in rows
                        ],
                    )
                )
        else:
            # Department / team / branch / position: compute official Monthly Review
            # score or average employee score strictly from RBAC-scoped cohort.
            record_buckets: dict[str, list[Any]] = {}
            raw_team_names: dict[str, str] = {}
            for record in cohort:
                rec_team = str(_record_field(record, "team", "") or "")
                if spec.entity == "branch":
                    key = str(_record_field(record, "branch_key") or _record_field(record, "branch") or branch_label).capitalize()
                elif spec.entity == "team":
                    key = _display_team_name(rec_team)
                    if key and rec_team and key not in raw_team_names:
                        raw_team_names[key] = rec_team
                elif spec.entity == "position":
                    key = str(_record_field(record, "position", "") or "")
                else:
                    key = function_for_team(rec_team) or rec_team
                if key:
                    record_buckets.setdefault(key, []).append(record)

            loc_filter = resolved["branch"] or "all"
            total_candidates = len(record_buckets)
            for key, bucket_records in record_buckets.items():
                if spec.entity == "team":
                    score_res = official_team_score(
                        bucket_records,
                        raw_team_names.get(key, key),
                        measure=eff_measure,
                        location=loc_filter,
                    )
                    score_val = score_res.score
                    sample_count = score_res.sample_size
                    unavail_reason = score_res.unavailable_reason
                elif spec.entity == "department":
                    score_res = official_department_score(
                        key,
                        bucket_records,
                        measure=eff_measure,
                        location=loc_filter,
                    )
                    score_val = score_res.score
                    sample_count = score_res.sample_size
                    unavail_reason = score_res.unavailable_reason
                else:
                    scores = [s for rec in bucket_records if (s := _record_evaluation_score(rec)) is not None]
                    score_val = round1(min(100.0, sum(scores) / len(scores))) if scores else None
                    sample_count = len(scores)
                    unavail_reason = "No measured records available." if score_val is None else None
                if score_val is None:
                    excluded_unverified.append({
                        "name": key,
                        "reason": unavail_reason or "Official score unavailable.",
                    })
                    continue
                if is_excluded_by_threshold(spec.score_threshold, spec.threshold_operator, score_val):
                    continue
                rows.append({"id": key, "name": key, "score": float(score_val), "total": sample_count})
            rows.sort(key=lambda r: ((-1 if reverse else 1) * r["score"], str(r.get("name") or "").casefold()))

            if spec.group_by == "branch":
                for record in cohort:
                    b = str(getattr(record, "branch", None) or "all")
                    key = str(getattr(record, "team", None) or getattr(record, "function", None) or "")
                    bucket = groups.setdefault(b, [])
                    for row in rows:
                        if row.get("name") == key and row not in bucket:
                            bucket.append(row)
                groups = {k: v[: spec.per_group_limit] for k, v in groups.items() if v}

            all_ranked_rows = list(rows[:10])
            if spec.limit > 0 and len(rows) > spec.limit:
                cutoff = round(float(rows[spec.limit - 1].get("score") or 0.0), 2)
                visible = list(rows[: spec.limit])
                for nxt in rows[spec.limit : spec.limit + 10]:
                    if abs(round(float(nxt.get("score") or 0.0), 2) - cutoff) < 1e-6:
                        visible.append(nxt)
                    else:
                        break
            else:
                visible = rows[: spec.limit]
            basis_subtitle = (
                "Average employee score"
                if eff_measure == "employee_average"
                else ("Monthly Review department score" if spec.entity == "department" else "Monthly Review team score")
            )
            cards.append(
                StructuredVisualCard(
                    card_type="horizontal_bar",
                    title=f"{'Best' if reverse else 'Lowest'} {spec.entity.replace('_', ' ').title()}s · {period_label}",
                    subtitle=f"{basis_subtitle} · {scope_label} ({branch_label})",
                    bars=[
                        AiBarItem(
                            label=str(r["name"]),
                            value=float(r["score"]),
                            display_value=f"{r['score']:.1f}%",
                            target_value=100.0,
                            severity="good" if r["score"] >= 85 else ("warning" if r["score"] >= 70 else "critical"),
                        )
                        for r in visible
                    ],
                )
            )
            rows = visible

        source_link = build_verified_deep_link(
            "/monthly-presentation",
            region=rank_region,
            month=resolved["month"],
            year=resolved["year"],
            function=spec.department or resolved["function"],
            team=spec.team or resolved["team"],
            position=spec.position or resolved["position"],
            branch=spec.branch or resolved["branch"],
            performance_level=resolved["performance_level"],
        )
        deep_links = [
            DeepLinkCta(
                label=f"Open Monthly Review ({scope_label} · {period_label})",
                route=source_link,
                description="Inspect the underlying PMS evaluation records.",
            )
        ]
        typed_ev: list[TypedMetricEvidence] = []
        ev_metric_id = spec.metric_id or "overall_score"
        ev_kpi_key = ev_metric_id.rsplit(":", 1)[-1]
        ev_display_name = "Overall PMS Score" if ev_kpi_key in ("overall_score", "pms_score", "score") else ev_kpi_key.replace("_", " ").title()
        for r in rows:
            score_val = r.get("score")
            if score_val is None:
                continue
            r_name = str(r.get("name") or "")
            r_team = (
                str(r.get("team") or spec.team or resolved["team"] or "")
                if spec.entity == "employee"
                else (r_name if spec.entity == "team" else (spec.team or resolved["team"] or r_name))
            )
            r_emp_id = str(r.get("id") or "") if spec.entity == "employee" else None
            r_emp_name = r_name if spec.entity == "employee" else None
            r_pos = (
                str(r.get("position") or "")
                if spec.entity == "employee"
                else (r_name if spec.entity == "position" else (spec.position or resolved["position"]))
            )
            r_branch = (r_name.casefold() if spec.entity == "branch" else (spec.branch or resolved["branch"])) or "all"
            r_link = str(r.get("route") or source_link)
            actual_rounded = round(float(score_val), 2)
            display_str = f"{float(score_val):.2f}%" if spec.entity == "employee" else f"{float(score_val):.1f}%"
            typed_ev.append(
                TypedMetricEvidence(
                    metric_id=ev_metric_id,
                    kpi_key=ev_kpi_key,
                    display_name=ev_display_name,
                    actual=actual_rounded,
                    actual_display=r.get("actual_display") or display_str,
                    unit=r.get("unit") or "%",
                    direction=r.get("direction") or "higher_better",
                    period=period_label,
                    team=r_team or None,
                    position=r_pos or None,
                    branch=r_branch,
                    performance_level=resolved["performance_level"] or "Employee",
                    employee_id=r_emp_id,
                    employee_name=r_emp_name,
                    source_link=r_link,
                )
            )

        qr_score_basis = (
            "individual measurement"
            if spec.entity == "employee"
            else (
                "average employee score"
                if eff_measure == "employee_average"
                else (
                    "Monthly Review department score"
                    if spec.entity == "department"
                    else ("Monthly Review team score" if spec.entity == "team" else "official score")
                )
            )
        )
        digest = {
            "query_rankings": {
                "entity": spec.entity,
                "score_measure": eff_measure,
                "score_basis": qr_score_basis,
                "excluded_unverified": excluded_unverified,
                "coverage": {
                    "ranked": len(rows),
                    "total_candidates": total_candidates,
                    "excluded_count": len(excluded_unverified),
                },
                "metric_id": ev_metric_id,
                "metric_label": ev_display_name,
                "sort_order": spec.sort_order,
                "limit": spec.limit,
                "group_by": spec.group_by,
                "per_group_limit": spec.per_group_limit,
                "region": rank_region,
                "department": spec.department or resolved["function"],
                "team": spec.team or resolved["team"],
                "position": spec.position or resolved["position"],
                "performance_level": resolved["performance_level"] or "Employee",
                "scope": scope_label,
                "period": period_label,
                "period_key": (
                    f"{int(resolved['year']):04d}-{int(MONTH_ORDER[resolved['month']]):02d}"
                    if resolved["month"] in MONTH_ORDER and resolved["year"]
                    else spec.period
                ),
                "rows": rows,
                "all_ranked_rows": all_ranked_rows if "all_ranked_rows" in locals() else rows[:10],
                "groups": groups or None,
                "total": len(rows),
            },
            "scope": scope_label,
            "branch": branch_label,
            "period": period_label,
            "teams": [{"team": r.get("name"), "score": r.get("score")} for r in rows],
            "best_team": rows[0] if rows and reverse else None,
            "worst_team": rows[-1] if rows else None,
        }
        if spec.entity in {"team", "department", "branch", "position"}:
            citations.append(SourceCitationPill(label=f"Basis · {qr_score_basis}", category="metric"))
        return ToolExecutionResult(
            tool_name="get_query_rankings",
            arguments=spec.model_dump(),
            records_evaluated=len(rows),
            resolved_month=resolved["month"],
            resolved_year=resolved["year"],
            digest=digest,
            visual_cards=cards,
            citations=citations,
            deep_links=deep_links,
            typed_evidence=typed_ev,
        )

    @staticmethod
    def _grade_for_score(score: float) -> str:
        if score >= 95.0:
            return "A"
        if score >= 90.0:
            return "B"
        if score >= 80.0:
            return "C"
        if score >= 70.0:
            return "D"
        return "E"

    def _single_published_team_kpi(
        self, resolved: dict[str, Any], metric: CatalogMetricDefinition, source_link: str,
    ) -> TypedMetricEvidence | None:
        """Use a single persisted measurement if the scored rollup omitted it."""
        team, month, year = resolved["team"], resolved["month"], resolved["year"]
        if not (team and month and year) or resolved["branch"] or metric.value_kind != "rate":
            return None
        if metric.team.casefold() != team.casefold():
            return None
        level = resolved["performance_level"] or "Employee"
        records = [
            record for record in self.ctx.get_scoped_records()
            if str(_record_field(record, "team", "")).casefold() == team.casefold()
            and _record_field(record, "month") == month and _record_field(record, "year") == year
            and str(_record_field(record, "performance_level") or "Employee").casefold() == level.casefold()
            and (not resolved["position"] or _record_field(record, "position") == resolved["position"])
            and (not resolved["region"] or _shared_record_region(record, team).casefold() == resolved["region"].casefold())
        ]
        if len(records) != 1:
            return None

        def key(value: str) -> str:
            return re.sub(r"[^a-z0-9]", "", value.casefold())

        label_key = key(metric.display_name)
        aliases = {key(metric.kpi_key), label_key, label_key.removesuffix("rate")}
        matches = [
            value for value in _record_field(records[0], "kpi_values", []) or []
            if _record_field(value, "unit") == metric.unit
            and any(key(str(_record_field(value, name) or "")) in aliases for name in ("kpi_key", "label"))
        ]
        if len(matches) != 1:
            return None
        reading = aggregate_kpi_metric(matches, {"unit": metric.unit})
        actual, target = reading.actual, reading.target
        if actual is None or not math.isfinite(actual):
            return None
        if target is not None and not math.isfinite(target):
            target = None
        if metric.unit == "%" and metric.storage_scale == "ratio_0_1" and abs(actual) <= 1 and (target is None or abs(target) <= 1):
            actual, target = actual * 100, target * 100 if target is not None else None
        return TypedMetricEvidence(
            metric_id=metric.metric_id, kpi_key=str(_record_field(matches[0], "kpi_key")),
            display_name=metric.display_name, team=team, performance_level=level,
            period=f"{month} {year}", branch="all", actual=round(actual, 2), target=target,
            actual_display=f"{actual:g} {metric.unit}".strip(),
            target_display=f"{target:g} {metric.unit}".strip() if target is not None else "—",
            unit=metric.unit, direction=metric.direction, contributes_to_score=False,
            sample_size=1, source_link=source_link,
        )

    def _extract_record_kpi_snapshot(
        self,
        rec: Any,
        kpi_query: str | None,
        team_hint: str | None = None,
        position_hint: str | None = None,
    ) -> dict[str, Any] | None:
        if not kpi_query:
            return None
        # Structured plans carry the team-qualified metric ID, while record
        # snapshots are keyed by the short catalogue key (e.g.
        # ``outbound:bookings_count`` -> ``bookings_count``).
        q_norm = kpi_query.strip().casefold().rsplit(":", 1)[-1]
        r_team = str(getattr(rec, "team", "") or team_hint or "")
        r_pos = str(getattr(rec, "position", "") or position_hint or "")
        cat_def = get_ai_catalog().find_metric_definition(
            team="Support Positions" if r_team.casefold() == "call center" and r_pos else r_team,
            kpi_key_or_label=q_norm,
            position=r_pos or None,
        )
        target_key = cat_def.kpi_key.casefold() if cat_def else None
        target_display = cat_def.display_name if cat_def else q_norm.replace("_", " ").title()

        if target_key == "overall_score" or q_norm in (
            "overall_score",
            "score",
            "pms_score",
            "performance",
            "overall",
        ):
            score_value = _record_evaluation_score(rec)
            if score_value is None:
                try:
                    raw_score = _record_field(rec, "overall_score", None)
                    score_value = float(raw_score) if raw_score is not None else None
                except (TypeError, ValueError):
                    score_value = None
            if score_value is not None:
                ov_tgt = 100.0
                for _kv in (getattr(rec, "kpi_values", None) or []):
                    _kk = str((_kv.get("kpi_key") if isinstance(_kv, dict) else getattr(_kv, "kpi_key", "")) or "").casefold()
                    if _kk == "overall_score":
                        _tv = _kv.get("target_value") if isinstance(_kv, dict) else getattr(_kv, "target_value", None)
                        if _tv is not None:
                            ov_tgt = float(_tv)
                        break
                return {
                    "kpi_key": "overall_score",
                    "kpi_label": cat_def.display_name if cat_def else "Overall PMS Score",
                    "unit": "%",
                    "numeric_value": float(score_value),
                    "target_numeric": ov_tgt,
                    "actual_display": f"{float(score_value):.1f}%",
                    "achievement_percent": float(score_value),
                    "direction": "higher_better",
                    "sort_metric": float(score_value),
                }

        if (target_key in ("totalbookings", "bookings_count")) or q_norm in (
            "bookings_count",
            "totalbookings",
            "bookings",
            "booking count",
        ):
            geo = getattr(rec, "geo", None)
            b_obj = getattr(geo, "bookings", None) if geo is not None else (geo.get("bookings") if isinstance(geo, dict) else None)
            if b_obj is not None:
                if isinstance(b_obj, dict):
                    cnt = sum(int(b_obj.get(k, 0) or 0) for k in ("dubai", "sharjah", "ajman", "clinics"))
                else:
                    cnt = (
                        int(getattr(b_obj, "dubai", 0) or 0)
                        + int(getattr(b_obj, "sharjah", 0) or 0)
                        + int(getattr(b_obj, "ajman", 0) or 0)
                        + int(getattr(b_obj, "clinics", 0) or 0)
                    )
                return {
                    "kpi_key": "bookings_count",
                    "kpi_label": cat_def.display_name if cat_def else "Bookings Count",
                    "unit": "bookings",
                    "numeric_value": float(cnt),
                    "target_numeric": 0.0,
                    "actual_display": f"{cnt:,} bookings",
                    "achievement_percent": 100.0,
                    "direction": "higher_better",
                    "sort_metric": float(cnt),
                }

        if (target_key in ("attendedpatients", "attended_count")) or q_norm in (
            "attended_count",
            "attendedpatients",
            "attended",
        ):
            geo = getattr(rec, "geo", None)
            a_obj = getattr(geo, "attended", None) if geo is not None else (geo.get("attended") if isinstance(geo, dict) else None)
            if a_obj is not None:
                if isinstance(a_obj, dict):
                    cnt = sum(int(a_obj.get(k, 0) or 0) for k in ("dubai", "sharjah", "ajman", "clinics"))
                else:
                    cnt = (
                        int(getattr(a_obj, "dubai", 0) or 0)
                        + int(getattr(a_obj, "sharjah", 0) or 0)
                        + int(getattr(a_obj, "ajman", 0) or 0)
                        + int(getattr(a_obj, "clinics", 0) or 0)
                    )
                return {
                    "kpi_key": "attended_count",
                    "kpi_label": cat_def.display_name if cat_def else "Attended Patients",
                    "unit": "attended",
                    "numeric_value": float(cnt),
                    "target_numeric": 0.0,
                    "actual_display": f"{cnt:,} attended",
                    "achievement_percent": 100.0,
                    "direction": "higher_better",
                    "sort_metric": float(cnt),
                }

        raw_kpis = getattr(rec, "kpi_values", None) or []
        q_clean = q_norm.replace("_", "").replace(" ", "").casefold()
        picked_kv = None
        # Pass 1: exact match on target_key, kpi_key, or raw label (prevents 'booking' hitting 'Attendance Rate (... / Bookings)')
        for kv in raw_kpis:
            k_key = str((kv.get("kpi_key") if isinstance(kv, dict) else getattr(kv, "kpi_key", "")) or "")
            k_lbl_raw = str((kv.get("label") if isinstance(kv, dict) else getattr(kv, "label", "")) or k_key)
            k_clean = k_key.replace("_", "").replace(" ", "").casefold()
            lbl_clean = k_lbl_raw.replace("_", "").replace(" ", "").casefold()
            if (target_key and k_key.casefold() == target_key) or (q_clean and (q_clean == k_clean or q_clean == lbl_clean)):
                picked_kv = kv
                break
        # Pass 2: controlled substring fallback against k_key and raw label only
        if picked_kv is None:
            for kv in raw_kpis:
                k_key = str((kv.get("kpi_key") if isinstance(kv, dict) else getattr(kv, "kpi_key", "")) or "")
                k_lbl_raw = str((kv.get("label") if isinstance(kv, dict) else getattr(kv, "label", "")) or k_key)
                k_clean = k_key.replace("_", "").replace(" ", "").casefold()
                lbl_clean = k_lbl_raw.replace("_", "").replace(" ", "").casefold()
                if (q_norm in k_key.casefold() or q_norm in k_lbl_raw.casefold()) or (
                    q_clean and (q_clean in k_clean or q_clean in lbl_clean or (len(k_clean) >= 4 and k_clean in q_clean))
                ):
                    picked_kv = kv
                    break

        for kv in ([picked_kv] if picked_kv is not None else []):
            k_key = str((kv.get("kpi_key") if isinstance(kv, dict) else getattr(kv, "kpi_key", "")) or "")
            k_lbl_raw = str((kv.get("label") if isinstance(kv, dict) else getattr(kv, "label", "")) or k_key)
            k_lbl = disambiguate_call_center_kpi_label(r_team, k_key, k_lbl_raw)

            unit = str((kv.get("unit") if isinstance(kv, dict) else getattr(kv, "unit", "%")) or "%")
            actual = _record_field(kv, "actual_value", None)
            if actual is None:
                continue
            act_v = float(actual)
            tgt_v = float((kv.get("target_value") if isinstance(kv, dict) else getattr(kv, "target_value", 0.0)) or 0.0)
            achievement = _record_field(kv, "achievement_ratio", None)
            direction = str(
                (kv.get("direction") if isinstance(kv, dict) else getattr(kv, "direction", None))
                or ("lower_better" if "abandon" in (k_key + " " + k_lbl_raw).casefold() or "waiting" in (k_key + " " + k_lbl_raw).casefold() or "rejection" in (k_key + " " + k_lbl_raw).casefold() or "cpl" in (k_key + " " + k_lbl_raw).casefold() or "error" in (k_key + " " + k_lbl_raw).casefold() else "higher_better")
            )

            if unit == "%":
                numeric_val = round(act_v * 100.0 if act_v <= 1.5 else act_v, 1)
                target_num = round(tgt_v * 100.0 if tgt_v <= 1.5 else tgt_v, 1)
                act_disp = f"{numeric_val:.1f}%"
            elif unit == "min":
                numeric_val = round(act_v, 2)
                target_num = round(tgt_v, 2)
                act_disp = f"{act_v:.2f} min"
            else:
                numeric_val = round(act_v, 1)
                target_num = round(tgt_v, 1)
                act_disp = f"{act_v:.1f}"

            ach_pct = None
            if achievement is not None:
                ach_r = float(achievement)
                ach_pct = min(100.0, round(ach_r * 100.0 if ach_r <= 2.0 else ach_r, 1))
            sort_metric = -numeric_val if direction == "lower_better" else numeric_val
            return {
                "kpi_key": k_key or target_display,
                "kpi_label": target_display if cat_def else k_lbl,
                "unit": unit,
                "numeric_value": numeric_val,
                "target_numeric": target_num,
                "actual_display": act_disp,
                "achievement_percent": ach_pct,
                "direction": direction,
                "sort_metric": sort_metric,
            }
        return None

    @_read_only_tool
    def execute_agent_spotlight_and_trend(
        self,
        *,
        team: str | None = None,
        position: str | None = None,
        function: str | None = None,
        branch: str | None = None,
        performance_level: str | None = None,
        month: str | None = None,
        year: int | None = None,
        kpi: str | None = None,
        employee_query: str | None = None,
        ranking_direction: str = "best",
        single_person: bool = True,
        months_window: int = 6,
        require_ranked_kpi: bool = False,
    ) -> ToolExecutionResult:
        resolved = self.ctx.resolve_filters(
            team=team,
            position=position,
            function=function,
            branch=branch,
            performance_level=performance_level,
            month=month,
            year=year,
        )
        all_records = self.ctx.get_scoped_records()

        # Filter to records matching the requested level (defaults to Employee)
        req_level = performance_level or resolved.get("performance_level") or "Employee"
        target_team = resolved["team"]
        target_pos = resolved["position"]
        target_fn = (resolved["function"] or "").casefold()
        scoped_recs = []
        for rec in all_records:
            lvl = str(getattr(rec, "performance_level", None) or "Employee")
            if lvl.casefold() != req_level.casefold():
                continue
            r_team = str(getattr(rec, "team", "") or "")
            r_pos = str(getattr(rec, "position", "") or "").strip()
            if target_team:
                if target_team.casefold() in ("support positions", "call center support positions"):
                    if r_team.casefold() not in ("call center", "support positions", "call center support positions") or (
                        r_team.casefold() == "call center" and not r_pos
                    ):
                        continue
                elif r_team.casefold() != target_team.casefold() and r_team.casefold() not in selection_team_keys(target_team):
                    continue
            elif target_fn:
                from services.ai.catalog import function_for_team
                r_fn = (function_for_team(r_team) or ("call center" if r_team.casefold() in ("inbound", "outbound", "call center", "support positions") else "")).casefold()
                if r_fn != target_fn:
                    continue
            if target_pos and r_pos.casefold() != target_pos.casefold():
                continue
            if resolved["region"]:
                rec_reg = _shared_record_region(rec, r_team).strip().casefold()
                if rec_reg != str(resolved["region"]).strip().casefold():
                    continue
            if resolved["branch"]:
                if not record_matches_branch(rec, resolved["branch"]):
                    continue
                rec = project_record_for_branch(rec, resolved["branch"])
            scoped_recs.append(rec)

        # Determine latest available month/year if not explicitly specified
        res_month = resolved["month"]
        res_year = resolved["year"]
        if not res_month or not res_year:
            avail_periods = sorted(
                {
                    (
                        int(getattr(r, "year", 0) or 0),
                        MONTH_ORDER.get(str(getattr(r, "month", "")).strip(), 0),
                        str(getattr(r, "month", "")).strip(),
                    )
                    for r in scoped_recs
                    if getattr(r, "year", None) and getattr(r, "month", None)
                }
            )
            if avail_periods:
                res_year, _, res_month = avail_periods[-1]
            else:
                res_month = res_month or "September"
                res_year = res_year or 2026

        period_label = f"{res_month} {res_year}"
        branch_label = resolved["branch"].capitalize() if resolved["branch"] else "All Branches"

        # Current period records for ranking
        period_recs = [
            r
            for r in scoped_recs
            if str(getattr(r, "month", "")).casefold() == str(res_month).casefold()
            and int(getattr(r, "year", 0) or 0) == int(res_year)
        ]
        # An explicitly pinned period with no records is an honest empty
        # result, never a substitution: falling back to other months here
        # used to spotlight a person from a different period (with a
        # "0.0%" display for the missing score) under the requested
        # period's label. The fallback below survives only when no period
        # was pinned at all (latest-period behaviour).
        if not period_recs and scoped_recs and not (resolved["month"] and resolved["year"]):
            period_recs = list(scoped_recs)
        if require_ranked_kpi and kpi:
            period_recs = [
                record for record in period_recs
                if self._extract_record_kpi_snapshot(record, kpi, target_team, target_pos) is not None
            ]

        def _rank_key(r: Any) -> tuple[float, float]:
            raw_sc = getattr(getattr(r, "evaluation", None), "score", None)
            if raw_sc is None:
                raw_sc = getattr(r, "overall_score", None)
            if raw_sc is None:
                fallback = float("inf") if ranking_direction == "worst" else float("-inf")
                return (fallback, fallback)
            sc = float(raw_sc)
            if kpi:
                snap = self._extract_record_kpi_snapshot(r, kpi, target_team, target_pos)
                if snap is not None:
                    return (float(snap["sort_metric"]), sc)
            return (sc, sc)

        period_recs.sort(
            key=_rank_key,
            reverse=(ranking_direction != "worst"),
        )

        selected_rec = None
        q_norm = (employee_query or "").strip().casefold()
        if q_norm:
            for r in period_recs:
                emp_id = str(getattr(r, "employee_id", "") or "").strip()
                emp_name = str(getattr(r, "employee_name", "") or "").strip()
                if q_norm == emp_id.casefold() or q_norm in emp_name.casefold() or q_norm in emp_id.casefold():
                    selected_rec = r
                    break
            if not selected_rec and not (resolved["month"] and resolved["year"]):
                for r in reversed(scoped_recs):
                    emp_id = str(getattr(r, "employee_id", "") or "").strip()
                    emp_name = str(getattr(r, "employee_name", "") or "").strip()
                    if q_norm == emp_id.casefold() or q_norm in emp_name.casefold() or q_norm in emp_id.casefold():
                        selected_rec = r
                        break
        elif period_recs:
            selected_rec = period_recs[0]

        if not selected_rec:
            return ToolExecutionResult(
                tool_name="get_agent_spotlight_and_trend",
                arguments={**resolved, "employee_query": employee_query, "ranking_direction": ranking_direction, "kpi": kpi},
                records_evaluated=0,
                digest={
                    "period": period_label,
                    "scope": target_team or resolved["function"] or "All authorized departments",
                    "region": resolved["region"],
                    "selected_period_has_score": False,
                    "spotlight": None,
                    "agent_spotlight": None,
                },
                visual_cards=[],
                citations=[SourceCitationPill(label=f"Period · {period_label}", category="period")],
                deep_links=[],
                resolved_month=res_month,
                resolved_year=res_year,
            )

        emp_id_resolved = str(getattr(selected_rec, "employee_id", "") or "").strip()
        raw_name = str(getattr(selected_rec, "employee_name", "") or emp_id_resolved).strip()
        emp_display_name = raw_name.title() if raw_name == raw_name.lower() else raw_name
        raw_emp_team = str(getattr(selected_rec, "team", "") or target_team or "Call Center").strip()
        emp_pos = str(getattr(selected_rec, "position", "") or target_pos or "").strip() or None
        emp_team = _display_team_name(raw_emp_team, emp_pos)

        # Compute exact rank within that agent's team in the current period
        team_period_recs = [
            r
            for r in period_recs
            if str(getattr(r, "team", "")).casefold() == raw_emp_team.casefold()
        ]
        team_period_recs.sort(
            key=_rank_key,
            reverse=True,
        )
        rank_idx = next(
            (i + 1 for i, r in enumerate(team_period_recs) if str(getattr(r, "employee_id", "")) == emp_id_resolved),
            1,
        )
        total_in_team = max(len(team_period_recs), 1)
        rank_label = f"Rank #{rank_idx} of {total_in_team} in {emp_team}"

        selected_rank_key = _rank_key(selected_rec)
        ties_list: list[str] = []
        tied_agents: list[dict[str, str]] = []
        tied_records: list[Any] = []
        for r in team_period_recs:
            r_id = str(getattr(r, "employee_id", "") or "").strip()
            if r_id == emp_id_resolved:
                continue
            rk = _rank_key(r)
            if abs(rk[0] - selected_rank_key[0]) < 1e-4:
                tied_records.append(r)
                r_nm = str(getattr(r, "employee_name", "") or r_id).strip()
                r_pos_val = str(getattr(r, "position", "") or "").strip()
                tied_agents.append(
                    {
                        "employee_id": r_id,
                        "employee_name": r_nm,
                        "team": emp_team,
                        "position": r_pos_val,
                        "performance_level": str(resolved["performance_level"] or "Employee"),
                    }
                )
                ties_list.append(
                    f"{r_nm} ({r_id} · {r_pos_val})"
                    if r_pos_val and r_pos_val.casefold() not in ("agent", "call center agent")
                    else f"{r_nm} ({r_id})"
                )

        selected_kpi_snap = self._extract_record_kpi_snapshot(selected_rec, kpi, emp_team, emp_pos) if kpi else None
        ranking_metric_label = str(selected_kpi_snap["kpi_label"]) if selected_kpi_snap else "Overall PMS Score"

        # Multi-month history for this employee across all scoped records
        emp_history_recs = [
            r for r in all_records if str(getattr(r, "employee_id", "")).strip() == emp_id_resolved
        ]
        if resolved["branch"]:
            emp_history_recs = [
                project_record_for_branch(r, resolved["branch"])
                for r in emp_history_recs
                if record_matches_branch(r, resolved["branch"])
            ]
        emp_history_recs.sort(
            key=lambda r: (
                int(getattr(r, "year", 0) or 0),
                MONTH_ORDER.get(str(getattr(r, "month", "")).strip(), 0),
            )
        )
        selected_period_key = (
            int(getattr(selected_rec, "year", 0) or 0),
            MONTH_ORDER.get(str(getattr(selected_rec, "month", "")).strip(), 0),
        )
        window_period_recs = [
            r
            for r in emp_history_recs
            if (
                int(getattr(r, "year", 0) or 0),
                MONTH_ORDER.get(str(getattr(r, "month", "")).strip(), 0),
            ) <= selected_period_key
        ][-max(1, min(months_window, 12)) :]
        window_period_ids = {id(r) for r in window_period_recs}
        all_history_points: list[dict[str, Any]] = []
        missing_months: list[str] = []
        kpi_history_points: list[dict[str, Any]] = []
        kpi_missing_months: list[str] = []
        for r in emp_history_recs:
            ev_all = getattr(r, "evaluation", None)
            raw_sc_all = getattr(ev_all, "score", None) if ev_all is not None else None
            if raw_sc_all is None:
                raw_sc_all = getattr(r, "overall_score", None)
            m_all = str(getattr(r, "month", "") or "").strip()
            y_all = int(getattr(r, "year", 2026) or 2026)
            p_all = f"{m_all} {y_all}"
            if kpi:
                kpi_snap = self._extract_record_kpi_snapshot(r, kpi, emp_team, emp_pos)
                if kpi_snap is None:
                    kpi_missing_months.append(p_all)
                elif id(r) in window_period_ids:
                    kpi_history_points.append(
                        {
                            "month": m_all,
                            "year": y_all,
                            "period": p_all,
                            "value": float(kpi_snap["numeric_value"]),
                            "actual_display": str(kpi_snap["actual_display"]),
                            "target": kpi_snap["target_numeric"],
                            "achievement_percent": kpi_snap["achievement_percent"],
                            "direction": kpi_snap["direction"],
                            "unit": str(kpi_snap.get("unit") or ""),
                        }
                    )
            if raw_sc_all is None:
                missing_months.append(p_all)
                continue
            sc_exact = float(raw_sc_all)
            all_history_points.append(
                {
                    "month": m_all,
                    "year": y_all,
                    "period": p_all,
                    "raw_score": sc_exact,
                    "score": sc_exact,
                }
            )
        kpi_change_vs_prev: float | None = None
        kpi_window_delta: float | None = None
        if len(kpi_history_points) >= 2:
            kpi_change_vs_prev = round(
                float(kpi_history_points[-1]["value"]) - float(kpi_history_points[-2]["value"]),
                2,
            )
            kpi_window_delta = round(
                float(kpi_history_points[-1]["value"]) - float(kpi_history_points[0]["value"]),
                2,
            )
        best_score: float | None = None
        best_months: list[str] = []
        best_period_label: str | None = None
        worst_score: float | None = None
        worst_months: list[str] = []
        worst_period_label: str | None = None
        searched_window_label: str = period_label
        is_asked_period_best: bool = False
        is_asked_period_worst: bool = False
        if all_history_points:
            best_score = max(float(pt["raw_score"]) for pt in all_history_points)
            best_months = [
                str(pt["period"])
                for pt in all_history_points
                if abs(float(pt["raw_score"]) - best_score) < 1e-9
            ]
            best_period_label = best_months[-1] if best_months else None
            worst_score = min(float(pt["raw_score"]) for pt in all_history_points)
            worst_months = [
                str(pt["period"])
                for pt in all_history_points
                if abs(float(pt["raw_score"]) - worst_score) < 1e-9
            ]
            worst_period_label = worst_months[0] if worst_months else None
            first_pt = all_history_points[0]
            last_pt = all_history_points[-1]
            if len(all_history_points) >= 2:
                searched_window_label = (
                    f"{first_pt['month']}–{last_pt['month']} {last_pt['year']}"
                    if first_pt["year"] == last_pt["year"]
                    else f"{first_pt['period']}–{last_pt['period']}"
                )
            else:
                searched_window_label = str(first_pt["period"])
            is_asked_period_best = any(p.casefold() == period_label.casefold() for p in best_months)
            is_asked_period_worst = any(p.casefold() == period_label.casefold() for p in worst_months)

        window_records = [
            r
            for r in window_period_recs
            if (getattr(getattr(r, "evaluation", None), "score", None) is not None or getattr(r, "overall_score", None) is not None)
        ]

        trend_points: list[AiTrendPoint] = []
        history_digest: list[dict[str, Any]] = []
        for r in window_records:
            ev = getattr(r, "evaluation", None)
            raw_sc_w = getattr(ev, "score", None) if ev is not None else None
            if raw_sc_w is None:
                raw_sc_w = getattr(r, "overall_score", 0.0)
            sc = float(raw_sc_w or 0.0)
            gr = str(getattr(ev, "grade", "") or self._grade_for_score(sc))
            m_str = str(getattr(r, "month", "") or "").strip()
            y_int = int(getattr(r, "year", 2026) or 2026)
            p_lbl = f"{m_str[:3]} {y_int}"
            trend_points.append(
                AiTrendPoint(
                    month=m_str,
                    year=y_int,
                    period_label=p_lbl,
                    score=round(sc, 2),
                    target=100.0,
                    grade=gr,
                )
            )
            history_digest.append(
                {
                    "month": m_str,
                    "year": y_int,
                    "period": f"{m_str} {y_int}",
                    "score": sc,
                    "grade": gr,
                    "team": emp_team,
                }
            )

        curr_ev = getattr(selected_rec, "evaluation", None)
        raw_curr = getattr(curr_ev, "score", None) if curr_ev is not None else None
        if raw_curr is None:
            raw_curr = getattr(selected_rec, "overall_score", None)
        selected_rec_in_requested_period = bool(
            str(getattr(selected_rec, "month", "")).strip().casefold() == str(res_month).strip().casefold()
            and int(getattr(selected_rec, "year", 0) or 0) == int(res_year)
        )
        selected_period_has_score = bool(selected_rec_in_requested_period and raw_curr is not None)
        curr_score = float(raw_curr) if selected_period_has_score and raw_curr is not None else 0.0
        curr_grade = self._grade_for_score(curr_score)
        ranking_metric_display = (
            f"{selected_kpi_snap['actual_display']} (Overall Score {curr_score:.1f}%)"
            if selected_kpi_snap
            else f"{curr_score:.1f}% Overall PMS Score"
        )

        prev_month_label = "Prior Month"
        change_vs_prev: float | None = None
        prev_score_val: float | None = None
        if len(trend_points) >= 2:
            prev_pt = trend_points[-2]
            prev_month_label = prev_pt.month
            prev_score_val = prev_pt.score
            change_vs_prev = round(curr_score - prev_pt.score, 1)

        six_month_delta: float | None = None
        first_month_label = trend_points[0].month if trend_points else res_month
        if len(trend_points) >= 2:
            six_month_delta = round(curr_score - trend_points[0].score, 1)

        # Extract compact KPI rows for this agent
        kpi_chips: list[AiKpiTableRow] = []
        raw_kpis = getattr(selected_rec, "kpi_values", None) or []
        for kv in raw_kpis[:5]:
            k_key = str(kv.get("kpi_key") if isinstance(kv, dict) else getattr(kv, "kpi_key", "") or "")
            k_lbl_raw = str(kv.get("label") if isinstance(kv, dict) else getattr(kv, "label", "") or k_key)
            k_lbl = disambiguate_call_center_kpi_label(emp_team, k_key, k_lbl_raw)
            unit = str(kv.get("unit") if isinstance(kv, dict) else getattr(kv, "unit", "%") or "%")
            act_v = float((kv.get("actual_value") if isinstance(kv, dict) else getattr(kv, "actual_value", 0.0)) or 0.0)
            tgt_v = float((kv.get("target_value") if isinstance(kv, dict) else getattr(kv, "target_value", 0.0)) or 0.0)
            ach_r = float((kv.get("achievement_ratio") if isinstance(kv, dict) else getattr(kv, "achievement_ratio", 0.0)) or 0.0)
            w_app = float((kv.get("weight_applied") if isinstance(kv, dict) else getattr(kv, "weight_applied", 0.0)) or 0.0)
            direction = str(
                (kv.get("direction") if isinstance(kv, dict) else getattr(kv, "direction", None))
                or ("lower_better" if "abandon" in (k_key + " " + k_lbl_raw).casefold() or "waiting" in (k_key + " " + k_lbl_raw).casefold() or "rejection" in (k_key + " " + k_lbl_raw).casefold() or "cpl" in (k_key + " " + k_lbl_raw).casefold() or "error" in (k_key + " " + k_lbl_raw).casefold() else "higher_better")
            )

            if unit == "%":
                act_disp = f"{act_v * 100:.1f}%" if act_v <= 1.5 else f"{act_v:.1f}%"
                tgt_disp = f"{tgt_v * 100:.1f}%" if tgt_v <= 1.5 else f"{tgt_v:.1f}%"
            elif unit == "min":
                act_disp = f"{act_v:.2f} min"
                tgt_disp = f"{tgt_v:.2f} min"
            else:
                act_disp = f"{act_v:.1f}"
                tgt_disp = f"{tgt_v:.1f}"

            ach_pct = min(100.0, round(ach_r * 100.0 if ach_r <= 2.0 else ach_r, 1))
            st = "good" if ach_pct >= 99.5 else ("warning" if ach_pct >= 85.0 else "critical")
            kpi_chips.append(
                AiKpiTableRow(
                    kpi_key=k_key or k_lbl,
                    kpi_label=k_lbl,
                    weight_percent=round(w_app * 100.0 if w_app <= 1.0 else w_app, 0),
                    actual_display=act_disp,
                    target_display=tgt_disp,
                    achievement_percent=ach_pct,
                    direction=direction,
                    people_below_target=0 if ach_pct >= 99.5 else 1,
                    status=st,  # type: ignore[arg-type]
                )
            )

        tiles: list[AiSpotlightMetricTile] = [
            AiSpotlightMetricTile(
                label="Current Score",
                value=f"{curr_score:.1f}%",
                sublabel=f"Grade {curr_grade} · {rank_label}",
                tone="good" if curr_score >= 90 else ("warning" if curr_score >= 80 else "critical"),
            ),
            AiSpotlightMetricTile(
                label=f"Prior Month ({prev_month_label[:3]})" if prev_score_val is not None else "Team Rank",
                value=f"{prev_score_val:.1f}%" if prev_score_val is not None else f"#{rank_idx} of {total_in_team}",
                sublabel=(
                    f"{change_vs_prev:+.1f} pp vs {prev_month_label}"
                    if change_vs_prev is not None
                    else f"{emp_team} · {period_label}"
                ),
                tone="good" if (change_vs_prev or 0) >= 0 else "critical",
            ),
            AiSpotlightMetricTile(
                label=f"{len(trend_points)}-Month Trajectory",
                value=f"{six_month_delta:+.1f} pp" if six_month_delta is not None else f"{curr_score:.1f}%",
                sublabel=(
                    f"{first_month_label[:3]} {trend_points[0].score:.1f}% → {res_month[:3]} {curr_score:.1f}%"
                    if len(trend_points) >= 2
                    else f"Single period tracked ({period_label})"
                ),
                tone="good" if (six_month_delta or 0) >= 0 else "warning",
            ),
        ]

        if employee_query:
            kicker = f"AGENT PERFORMANCE & TREND · {emp_team.upper()}"
        elif ranking_direction == "worst":
            kicker = f"LOWEST PERFORMER & TREND · {emp_team.upper()}"
        else:
            kicker = f"TOP PERFORMER & TREND · {emp_team.upper()}"

        # Optional compact top-3 list ONLY if user asked plural ("who are the best agents")
        extra_items: list[AiEntityListItem] = []
        top_agents_list: list[dict[str, Any]] = []
        if not single_person and not employee_query and len(team_period_recs) > 1:
            ordered = team_period_recs if ranking_direction != "worst" else list(reversed(team_period_recs))
            for idx, r in enumerate(ordered[:5], start=1):
                r_id = str(getattr(r, "employee_id", "") or "")
                r_nm_raw = str(getattr(r, "employee_name", "") or r_id).strip()
                r_nm = r_nm_raw.title() if r_nm_raw == r_nm_raw.lower() else r_nm_raw
                r_pos_val = str(getattr(r, "position", "") or "").strip() or None
                r_sc = round(float(getattr(getattr(r, "evaluation", None), "score", 0.0) or 0.0), 2)
                r_gr = self._grade_for_score(r_sc)
                top_agents_list.append(
                    {
                        "rank": idx,
                        "employee_id": r_id,
                        "employee_name": r_nm,
                        "team": emp_team,
                        "position": r_pos_val,
                        "score": r_sc,
                        "grade": r_gr,
                    }
                )
                if idx <= 3:
                    extra_items.append(
                        AiEntityListItem(
                            id=r_id,
                            title=f"#{idx} · {r_nm} ({r_id})",
                            subtitle=f"{emp_team} · {period_label}",
                            badge_text=f"Grade {r_gr} · {r_sc:.1f}%",
                            severity="good" if r_sc >= 90 else ("warning" if r_sc >= 80 else "critical"),
                            metric_value=f"{r_sc:.1f}%",
                            route_link=build_verified_deep_link(
                                f"/employee/{r_id}",
                                month=res_month,
                                year=res_year,
                                branch=resolved["branch"],
                                function=resolved["function"],
                                team=emp_team,
                                position=emp_pos,
                                performance_level=resolved["performance_level"],
                            ),
                        )
                    )

        spotlight_meta = AiSpotlightMetadata(
            kicker=kicker,
            entity_name=emp_display_name,
            entity_id=emp_id_resolved,
            team=emp_team,
            rank_label=rank_label,
            score=curr_score,
            grade=curr_grade,  # type: ignore[arg-type]
            change_vs_prev=change_vs_prev,
            previous_month_label=prev_month_label,
            six_month_delta=six_month_delta,
            target=100.0,
            headline_note=(
                f"{emp_display_name} ranks #{rank_idx} of {total_in_team} in {emp_team} by {ranking_metric_label} ({period_label})."
            ),
            tiles=tiles,
            kpi_chips=kpi_chips,
            trend_points=trend_points,
        )

        card = StructuredVisualCard(
            card_type="trend_spotlight",
            title=f"{emp_display_name} ({emp_id_resolved})",
            subtitle=f"{emp_team} · {period_label} · {branch_label}",
            spotlight=spotlight_meta,
            items=extra_items,
        )

        primary_emp_route = build_verified_deep_link(
            f"/employee/{emp_id_resolved}",
            month=res_month,
            year=res_year,
            branch=resolved["branch"],
            function=resolved["function"],
            team=emp_team,
            position=emp_pos,
            performance_level=resolved["performance_level"],
        )
        team_route_slug = _team_route_slug(emp_team)

        citations = [
            SourceCitationPill(label=f"Period · {period_label}", category="period"),
            SourceCitationPill(label=f"Agent · {emp_display_name}", category="scope"),
            SourceCitationPill(label=f"Metric · {ranking_metric_label} ({rank_label})", category="metric"),
        ]
        deep_links = [
            DeepLinkCta(
                label=f"Open {emp_display_name} Profile →",
                route=primary_emp_route,
                icon_key="employee",
            ),
            DeepLinkCta(
                label=f"Open {emp_team} Team Deep Dive →",
                route=build_verified_deep_link(
                    f"/team/{team_route_slug}",
                    month=res_month,
                    year=res_year,
                    branch=resolved["branch"],
                    function=resolved["function"],
                    team=emp_team,
                    position=emp_pos,
                    performance_level=resolved["performance_level"],
                ),
                icon_key="team",
            ),
        ]

        # Build normalized per-KPI snapshots for multi-KPI compound queries
        all_kpi_snapshots: list[dict[str, Any]] = []
        seen_snap_labels: set[str] = set()
        for kv in raw_kpis:
            k_lbl_c = str((kv.get("label") if isinstance(kv, dict) else getattr(kv, "label", "")) or "").strip()
            k_key_c = str((kv.get("kpi_key") if isinstance(kv, dict) else getattr(kv, "kpi_key", "")) or "").strip()
            q_try = k_lbl_c or k_key_c
            if not q_try:
                continue
            snap_c = self._extract_record_kpi_snapshot(selected_rec, q_try, emp_team, emp_pos)
            if snap_c and str(snap_c.get("kpi_label") or "").casefold() not in seen_snap_labels:
                seen_snap_labels.add(str(snap_c.get("kpi_label") or "").casefold())
                all_kpi_snapshots.append(snap_c)
        if emp_team in ("Inbound", "Outbound"):
            for cnt_q in ("bookings_count", "attended_count"):
                snap_cnt = self._extract_record_kpi_snapshot(selected_rec, cnt_q, emp_team, emp_pos)
                if snap_cnt and str(snap_cnt.get("kpi_label") or "").casefold() not in seen_snap_labels:
                    seen_snap_labels.add(str(snap_cnt.get("kpi_label") or "").casefold())
                    all_kpi_snapshots.append(snap_cnt)

        agent_spotlight_dict = {
            "entity_name": emp_display_name,
            "entity_id": emp_id_resolved,
            "team": emp_team,
            "position": emp_pos,
            "rank_label": rank_label,
            "rank": rank_idx,
            "total_in_team": total_in_team,
            "ranking_direction": ranking_direction,
            "single_person": single_person,
            "top_agents": top_agents_list,
            "ranking_metric_label": ranking_metric_label,
            "ranking_metric_display": ranking_metric_display,
            "ranking_metric_actual_display": (
                str(selected_kpi_snap["actual_display"]) if selected_kpi_snap else None
            ),
            "ranking_metric_actual": (
                float(selected_kpi_snap["numeric_value"])
                if selected_kpi_snap and selected_kpi_snap.get("numeric_value") is not None
                else None
            ),
            "ranking_metric_target": selected_kpi_snap.get("target_numeric") if selected_kpi_snap else None,
            "ranking_metric_unit": selected_kpi_snap.get("unit") if selected_kpi_snap else None,
            "ranking_metric_target_display": (
                f"{selected_kpi_snap['target_numeric']:g} {selected_kpi_snap.get('unit') or ''}".strip()
                if selected_kpi_snap and selected_kpi_snap.get("target_numeric") is not None
                else None
            ),
            "ranking_metric_direction": selected_kpi_snap.get("direction") if selected_kpi_snap else None,
            "region": resolved["region"],
            "period": period_label,
            "scope": f"{emp_team} ({branch_label})",
            "source_route": primary_emp_route,
            "score": curr_score if selected_period_has_score else None,
            "raw_score": curr_score if selected_period_has_score else None,
            "selected_period_has_score": selected_period_has_score,
            "requested_period": period_label,
            "grade": curr_grade,
            "change_vs_prev": change_vs_prev,
            "previous_month_label": prev_month_label,
            "six_month_delta": six_month_delta,
            "months_tracked": len(trend_points),
            "first_month_label": first_month_label,
            "ties": ties_list,
            "tied_agents": tied_agents,
            "best_score": best_score,
            "best_period": best_period_label,
            "best_months": best_months,
            "worst_score": worst_score,
            "worst_period": worst_period_label,
            "worst_months": worst_months,
            "missing_months": missing_months,
            "searched_window": searched_window_label,
            "is_asked_period_best": is_asked_period_best,
            "is_asked_period_worst": is_asked_period_worst,
            "all_history": all_history_points,
            "kpi_history": kpi_history_points,
            "kpi_missing_months": kpi_missing_months,
            "kpi_change_vs_prev": kpi_change_vs_prev,
            "kpi_window_delta": kpi_window_delta,
            "all_kpi_snapshots": all_kpi_snapshots,
        }

        digest = {
            "period": period_label,
            "scope": emp_team,
            "position": emp_pos,
            "branch": branch_label,
            "employee_id": emp_id_resolved,
            "employee_name": emp_display_name,
            "team": emp_team,
            "history": history_digest,
            "spotlight": agent_spotlight_dict,
            "agent_spotlight": agent_spotlight_dict,
        }

        typed_evidence: list[TypedMetricEvidence] = []
        selected_metric_id = str(kpi or "").strip()
        if selected_kpi_snap:
            requested_metric_leaf = selected_metric_id.rsplit(":", 1)[-1]
            source_metric_key = str(selected_kpi_snap["kpi_key"])
            normalize_metric_key = lambda value: re.sub(r"[^a-z0-9]", "", str(value or "").casefold())
            same_team_prefix = ":" in selected_metric_id and (
                normalize_metric_key(selected_metric_id.split(":", 1)[0]) == normalize_metric_key(emp_team)
            )
            if same_team_prefix and normalize_metric_key(requested_metric_leaf) != normalize_metric_key(source_metric_key):
                pass
            else:
                evidence_metric_leaf = (
                    source_metric_key
                    if normalize_metric_key(requested_metric_leaf) == normalize_metric_key(source_metric_key)
                    else (requested_metric_leaf or source_metric_key)
                )
                selected_metric_id = (
                    f"{emp_team.casefold().replace(' ', '_')}:{evidence_metric_leaf}"
                )
        eff_ev_level = str(getattr(selected_rec, "performance_level", None) or req_level or "Employee")
        if kpi and selected_kpi_snap:
            if kpi_history_points:
                for pt in kpi_history_points:
                    m_pt = pt.get("month") or res_month
                    y_pt = pt.get("year") or res_year
                    p_pt = f"{m_pt} {y_pt}"
                    typed_evidence.append(
                        TypedMetricEvidence(
                            metric_id=selected_metric_id or f"{emp_team.casefold().replace(' ', '_')}:{selected_kpi_snap['kpi_key']}",
                            kpi_key=str(selected_kpi_snap["kpi_key"]),
                            display_name=str(selected_kpi_snap["kpi_label"]),
                            team=emp_team,
                            position=emp_pos,
                            performance_level=eff_ev_level,
                            branch=resolved["branch"] or "all",
                            period=p_pt,
                            actual=float(pt["value"]),
                            target=pt["target"],
                            actual_display=str(pt.get("actual_display") or f"{pt['value']} {pt.get('unit', '')}"),
                            target_display=f"{pt['target']} {pt['unit']}" if pt["target"] is not None else None,
                            achievement_percent=pt["achievement_percent"],
                            unit=str(pt.get("unit") or selected_kpi_snap.get("unit") or ""),
                            direction=pt["direction"],
                            contributes_to_score=True,
                            employee_id=emp_id_resolved,
                            employee_name=emp_display_name,
                            source_link=primary_emp_route,
                        )
                    )
            elif selected_period_has_score and selected_kpi_snap:
                typed_evidence.append(
                    TypedMetricEvidence(
                        metric_id=selected_metric_id or f"{emp_team.casefold().replace(' ', '_')}:{selected_kpi_snap['kpi_key']}",
                        kpi_key=str(selected_kpi_snap["kpi_key"]),
                        display_name=str(selected_kpi_snap["kpi_label"]),
                        team=emp_team,
                        position=emp_pos,
                        performance_level=eff_ev_level,
                        branch=resolved["branch"] or "all",
                        period=period_label,
                        actual=float(selected_kpi_snap["numeric_value"]),
                        target=float(selected_kpi_snap.get("target_numeric")) if selected_kpi_snap.get("target_numeric") is not None else None,
                        actual_display=str(selected_kpi_snap.get("actual_display") or f"{selected_kpi_snap['numeric_value']} {selected_kpi_snap.get('unit', '')}"),
                        target_display=f"{selected_kpi_snap.get('target_numeric')} {selected_kpi_snap.get('unit')}" if selected_kpi_snap.get("target_numeric") is not None else "",
                        achievement_percent=selected_kpi_snap["achievement_percent"],
                        unit=str(selected_kpi_snap.get("unit") or ""),
                        direction=str(selected_kpi_snap.get("direction") or "higher_better"),
                        contributes_to_score=True,
                        employee_id=emp_id_resolved,
                        employee_name=emp_display_name,
                        source_link=primary_emp_route,
                    )
                )

        if window_records:
            for r_w in window_records:
                ev_w = getattr(r_w, "evaluation", None)
                raw_w = getattr(ev_w, "score", None) if ev_w is not None else None
                if raw_w is None:
                    raw_w = getattr(r_w, "overall_score", None)
                if raw_w is not None:
                    m_w = str(getattr(r_w, "month", "") or "").strip()
                    y_w = int(getattr(r_w, "year", 2026) or 2026)
                    p_w = f"{m_w} {y_w}"
                    if any(
                        evidence.kpi_key == "overall_score"
                        and evidence.period.casefold() == p_w.casefold()
                        for evidence in typed_evidence
                    ):
                        continue
                    typed_evidence.append(
                        TypedMetricEvidence(
                            metric_id=f"{emp_team.casefold().replace(' ', '_')}:overall_score",
                            kpi_key="overall_score",
                            display_name="Overall PMS Score",
                            team=emp_team,
                            position=emp_pos,
                            performance_level=eff_ev_level,
                            branch=resolved["branch"] or "all",
                            period=p_w,
                            actual=float(raw_w),
                            target=100.0,
                            actual_display=f"{float(raw_w):.1f}%",
                            target_display="100.0%",
                            achievement_percent=float(raw_w),
                            unit="%",
                            direction="higher_better",
                            contributes_to_score=True,
                            employee_id=emp_id_resolved,
                            employee_name=emp_display_name,
                            source_link=primary_emp_route,
                        )
                    )
        elif selected_period_has_score:
            typed_evidence.append(
                TypedMetricEvidence(
                    metric_id=f"{emp_team.casefold().replace(' ', '_')}:overall_score",
                    kpi_key="overall_score",
                    display_name="Overall PMS Score",
                    team=emp_team,
                    position=emp_pos,
                    performance_level=eff_ev_level,
                    branch=resolved["branch"] or "all",
                    period=period_label,
                    actual=float(curr_score),
                    target=100.0,
                    actual_display=f"{curr_score:.1f}%",
                    target_display="100.0%",
                    achievement_percent=float(curr_score),
                    unit="%",
                    direction="higher_better",
                    contributes_to_score=True,
                    employee_id=emp_id_resolved,
                    employee_name=emp_display_name,
                    source_link=primary_emp_route,
                )
            )

        if not employee_query and tied_records:
            for t_rec in tied_records:
                t_id = str(getattr(t_rec, "employee_id", "") or "").strip()
                t_raw_name = str(getattr(t_rec, "employee_name", "") or t_id).strip()
                t_name = t_raw_name.title() if t_raw_name == t_raw_name.lower() else t_raw_name
                t_pos = str(getattr(t_rec, "position", "") or "").strip() or None
                t_level = str(getattr(t_rec, "performance_level", None) or req_level or "Employee")
                t_route = build_verified_deep_link(
                    f"/employee/{t_id}",
                    month=res_month,
                    year=res_year,
                    branch=resolved["branch"],
                    function=resolved["function"],
                    team=emp_team,
                    position=t_pos,
                    performance_level=resolved["performance_level"],
                )
                t_snap = self._extract_record_kpi_snapshot(t_rec, kpi, emp_team, t_pos) if kpi else None
                if kpi and t_snap:
                    typed_evidence.append(
                        TypedMetricEvidence(
                            metric_id=selected_metric_id or f"{emp_team.casefold().replace(' ', '_')}:{t_snap['kpi_key']}",
                            kpi_key=str(t_snap["kpi_key"]),
                            display_name=str(t_snap["kpi_label"]),
                            team=emp_team,
                            position=t_pos,
                            performance_level=t_level,
                            branch=resolved["branch"] or "all",
                            period=period_label,
                            actual=float(t_snap["numeric_value"]),
                            target=float(t_snap.get("target_numeric")) if t_snap.get("target_numeric") is not None else None,
                            actual_display=str(t_snap.get("actual_display") or f"{t_snap['numeric_value']} {t_snap.get('unit', '')}"),
                            target_display=f"{t_snap.get('target_numeric')} {t_snap.get('unit')}" if t_snap.get("target_numeric") is not None else "",
                            achievement_percent=t_snap["achievement_percent"],
                            unit=str(t_snap.get("unit") or ""),
                            direction=str(t_snap.get("direction") or "higher_better"),
                            contributes_to_score=True,
                            employee_id=t_id,
                            employee_name=t_name,
                            source_link=t_route,
                        )
                    )
                else:
                    t_score = _record_evaluation_score(t_rec)
                    if t_score is not None:
                        typed_evidence.append(
                            TypedMetricEvidence(
                                metric_id=f"{emp_team.casefold().replace(' ', '_')}:overall_score",
                                kpi_key="overall_score",
                                display_name="Overall PMS Score",
                                team=emp_team,
                                position=t_pos,
                                performance_level=t_level,
                                branch=resolved["branch"] or "all",
                                period=period_label,
                                actual=float(t_score),
                                target=100.0,
                                actual_display=f"{float(t_score):.1f}%",
                                target_display="100.0%",
                                achievement_percent=float(t_score),
                                unit="%",
                                direction="higher_better",
                                contributes_to_score=True,
                                employee_id=t_id,
                                employee_name=t_name,
                                source_link=t_route,
                            )
                        )

        return ToolExecutionResult(
            tool_name="get_agent_spotlight_and_trend",
            arguments={
                "team": emp_team,
                "position": emp_pos,
                "branch": resolved["branch"],
                "kpi": kpi,
                "employee_query": employee_query,
                "ranking_direction": ranking_direction,
            },
            records_evaluated=max(len(team_period_recs), len(window_records)),
            digest=digest,
            visual_cards=[card],
            citations=citations,
            deep_links=deep_links,
            typed_evidence=typed_evidence,
            resolved_month=res_month,
            resolved_year=res_year,
        )

    @_read_only_tool
    def execute_team_trend_spotlight(
        self,
        *,
        team: str | None = None,
        position: str | None = None,
        function: str | None = None,
        branch: str | None = None,
        month: str | None = None,
        year: int | None = None,
        kpi: str | None = None,
        months_window: int = 6,
    ) -> ToolExecutionResult:
        resolved = self.ctx.resolve_filters(
            team=team,
            position=position,
            function=function,
            branch=branch,
            month=month,
            year=year,
        )
        all_records = self.ctx.get_scoped_records()
        target_team = resolved["team"]
        target_pos = resolved["position"]
        target_fn = (resolved["function"] or "").casefold()

        cat_def = (
            get_ai_catalog().find_metric_definition(
                team=target_team,
                kpi_key_or_label=kpi,
                position=target_pos,
            )
            if kpi
            else None
        )
        metric_label = cat_def.display_name if cat_def else (kpi.strip() if kpi else "Overall Score")

        by_period: dict[tuple[int, int, str], list[float]] = {}
        targets_by_period: dict[tuple[int, int, str], list[float]] = {}
        for rec in all_records:
            if str(getattr(rec, "performance_level", None) or "Employee") != "Employee":
                continue
            r_team = str(getattr(rec, "team", "") or "")
            r_pos = str(getattr(rec, "position", "") or "").strip()
            if target_team:
                if target_team.casefold() in ("support positions", "call center support positions"):
                    if r_team.casefold() not in ("call center", "support positions", "call center support positions") or (
                        r_team.casefold() == "call center" and not r_pos
                    ):
                        continue
                elif r_team.casefold() != target_team.casefold() and r_team.casefold() not in selection_team_keys(target_team):
                    continue
            elif target_fn:
                from services.ai.catalog import function_for_team
                r_fn = (function_for_team(r_team) or ("call center" if r_team.casefold() in ("inbound", "outbound", "call center", "support positions") else "")).casefold()
                if r_fn != target_fn:
                    continue
            if target_pos and r_pos.casefold() != target_pos.casefold():
                continue
            if resolved["region"]:
                rec_reg = _shared_record_region(rec, r_team).strip().casefold()
                if rec_reg != str(resolved["region"]).strip().casefold():
                    continue
            if resolved["branch"]:
                if not record_matches_branch(rec, resolved["branch"]):
                    continue
                rec = project_record_for_branch(rec, resolved["branch"])
            y_val = int(getattr(rec, "year", 0) or 0)
            m_str = str(getattr(rec, "month", "") or "").strip()
            m_ord = MONTH_ORDER.get(m_str, 0)
            if not (y_val and m_ord):
                continue

            if kpi:
                snap = self._extract_record_kpi_snapshot(rec, kpi, target_team, target_pos)
                if snap is not None:
                    by_period.setdefault((y_val, m_ord, m_str), []).append(float(snap["numeric_value"]))
                    targets_by_period.setdefault((y_val, m_ord, m_str), []).append(float(snap["target_numeric"]))
                    continue

            ev = getattr(rec, "evaluation", None)
            raw_sc = getattr(ev, "score", None) if ev is not None else None
            sc = float(raw_sc) if raw_sc is not None else None
            if sc is not None:
                by_period.setdefault((y_val, m_ord, m_str), []).append(sc)
                targets_by_period.setdefault((y_val, m_ord, m_str), []).append(100.0)

        sorted_periods = sorted(by_period.keys())[-max(1, min(months_window, 12)) :]
        trend_points: list[AiTrendPoint] = []
        for y_val, _, m_str in sorted_periods:
            key = (y_val, MONTH_ORDER.get(m_str, 0), m_str)
            scores = by_period[key]
            tgts = targets_by_period.get(key) or [100.0]
            avg_sc = min(100.0, round(sum(scores) / len(scores), 1))
            avg_tgt = round(sum(tgts) / len(tgts), 1)
            trend_points.append(
                AiTrendPoint(
                    month=m_str,
                    year=y_val,
                    period_label=f"{m_str[:3]} {y_val}",
                    score=avg_sc,
                    target=avg_tgt,
                    grade=self._grade_for_score(avg_sc),
                )
            )

        scope_label = (
            _display_team_name(target_team, target_pos)
            if target_team
            else (resolved["function"] or "All authorized departments")
        )
        if target_pos:
            scope_label = f"{scope_label} · {target_pos}"
        branch_label = resolved["branch"].capitalize() if resolved["branch"] else "All Branches"
        if not trend_points:
            fallback_month = resolved["month"] or "Latest Period"
            fallback_year = resolved["year"] or 2026
            return ToolExecutionResult(
                tool_name="get_team_trend_spotlight",
                arguments=resolved,
                records_evaluated=0,
                digest={
                    "period": f"{fallback_month} {fallback_year}",
                    "scope": scope_label,
                    "branch": branch_label,
                    "spotlight": None,
                    "team_trend_spotlight": None,
                },
                visual_cards=[],
                citations=[SourceCitationPill(label=f"Scope · {scope_label}", category="scope")],
                deep_links=[],
                resolved_month=resolved["month"],
                resolved_year=resolved["year"],
            )
        latest_pt = trend_points[-1]
        curr_score = latest_pt.score
        curr_target = latest_pt.target or 100.0
        curr_grade = self._grade_for_score(curr_score)
        prev_pt = trend_points[-2] if len(trend_points) >= 2 else None
        change_vs_prev = round(curr_score - prev_pt.score, 1) if prev_pt else None
        six_month_delta = round(curr_score - trend_points[0].score, 1) if len(trend_points) >= 2 else None
        gap_val = round(curr_score - curr_target, 1)

        tiles = [
            AiSpotlightMetricTile(
                label="Current",
                value=f"{curr_score:.1f}%",
                sublabel=f"{metric_label} · {latest_pt.month} {latest_pt.year}",
                tone="good" if curr_score >= curr_target else ("warning" if curr_score >= curr_target * 0.85 else "critical"),
            ),
            AiSpotlightMetricTile(
                label="Target",
                value=f"{curr_target:.1f}%",
                sublabel="Official PMS Benchmark",
                tone="neutral",
            ),
            AiSpotlightMetricTile(
                label="Gap",
                value=f"{gap_val:+.1f}%",
                sublabel=f"{change_vs_prev:+.1f}% vs {prev_pt.month}" if prev_pt and change_vs_prev is not None else f"vs {curr_target:.1f}% target",
                tone="warning" if gap_val < 0 else "good",
            ),
        ]

        spotlight_meta = AiSpotlightMetadata(
            kicker=f"6-MONTH {metric_label.upper()} TREND · {scope_label.upper()}",
            entity_name=f"{scope_label} {metric_label} Trajectory",
            entity_id=None,
            team=scope_label,
            rank_label=f"{len(trend_points)} Months Tracked",
            score=curr_score,
            grade=curr_grade,  # type: ignore[arg-type]
            change_vs_prev=change_vs_prev,
            previous_month_label=prev_pt.month if prev_pt else "Prior Month",
            six_month_delta=six_month_delta,
            target=curr_target,
            headline_note=f"{scope_label} {metric_label} moved from {trend_points[0].month} ({trend_points[0].score:.1f}%) to {latest_pt.month} ({curr_score:.1f}%)." if trend_points else None,
            tiles=tiles,
            kpi_chips=[],
            trend_points=trend_points,
        )

        card = StructuredVisualCard(
            card_type="trend_spotlight",
            title=f"{scope_label} · 6-Month {metric_label} Trend",
            subtitle=f"{latest_pt.month} {latest_pt.year} · {branch_label}",
            spotlight=spotlight_meta,
        )

        selected_period_has_score = True
        period_label = f"{latest_pt.month} {latest_pt.year}"
        team_trend_dict = {
            "entity_name": scope_label,
            "entity_id": None,
            "team": scope_label,
            "metric_label": metric_label,
            "rank_label": f"{len(trend_points)} Months Tracked",
            "ranking_direction": "team_trend",
            "score": curr_score if selected_period_has_score else None,
            "raw_score": curr_score if selected_period_has_score else None,
            "selected_period_has_score": selected_period_has_score,
            "requested_period": period_label,
            "first_score": trend_points[0].score if trend_points else curr_score,
            "target": curr_target,
            "grade": curr_grade,
            "change_vs_prev": change_vs_prev,
            "previous_month_label": prev_pt.month if prev_pt else "Prior Month",
            "six_month_delta": six_month_delta,
            "months_tracked": len(trend_points),
            "first_month_label": trend_points[0].month if trend_points else latest_pt.month,
            "latest_month_label": f"{latest_pt.month} {latest_pt.year}",
        }

        team_slug = _team_route_slug(target_team or "Call Center")
        primary_route = build_verified_deep_link(
            f"/team/{team_slug}" if target_team else "/monthly-presentation",
            month=latest_pt.month,
            year=latest_pt.year,
            branch=resolved["branch"],
            function=resolved["function"],
            team=target_team,
            position=target_pos,
            performance_level=resolved["performance_level"],
        )

        return ToolExecutionResult(
            tool_name="get_team_trend_spotlight",
            arguments={**resolved, "kpi": kpi},
            records_evaluated=sum(len(v) for v in by_period.values()),
            digest={
                "period": f"{latest_pt.month} {latest_pt.year}",
                "scope": scope_label,
                "branch": branch_label,
                "spotlight": team_trend_dict,
                "team_trend_spotlight": team_trend_dict,
            },
            visual_cards=[card],
            citations=[
                SourceCitationPill(label=f"Period · {latest_pt.month} {latest_pt.year}", category="period"),
                SourceCitationPill(label=f"Scope · {scope_label}", category="scope"),
                SourceCitationPill(label=f"Trajectory · {metric_label} ({len(trend_points)} Months)", category="metric"),
            ],
            deep_links=[
                DeepLinkCta(
                    label=f"Open {scope_label} Sheet →" if target_team else "Open Monthly Presentation →",
                    route=primary_route,
                    icon_key="team" if target_team else "insights",
                )
            ],
            resolved_month=latest_pt.month,
            resolved_year=latest_pt.year,
        )

    @_read_only_tool
    def execute_employee_multi_month_history(
        self,
        *,
        employee_query: str,
        branch: str | None = None,
        months_window: int = 6,
    ) -> ToolExecutionResult:
        return self.execute_agent_spotlight_and_trend(
            employee_query=employee_query,
            branch=branch,
            months_window=months_window,
            single_person=True,
        )

    @_read_only_tool
    def execute_governance_candidates_and_plans(
        self,
        *,
        team: str | None = None,
        function: str | None = None,
        branch: str | None = None,
        month: str | None = None,
        year: int | None = None,
    ) -> ToolExecutionResult:
        resolved = self.ctx.resolve_filters(
            team=team,
            function=function,
            branch=branch,
            month=month,
            year=year,
        )
        ws = self.ctx.insights_service.generate_workspace(
            self.ctx.scope,
            sections="summary,team_summaries,risks,comparison",
            month=resolved["month"],
            year=resolved["year"],
            team=resolved["team"],
            function=resolved["function"],
            branch=resolved["branch"],
        )
        res_month = ws.comparison.current.month if ws.comparison and ws.comparison.current else (resolved["month"] or "September")
        res_year = ws.comparison.current.year if ws.comparison and ws.comparison.current else (resolved["year"] or 2026)
        period_label = f"{res_month} {res_year}"
        scope_label = resolved["team"] or resolved["function"] or "All authorized departments"
        total_employees = sum(int(t.total_employees or 0) for t in (ws.team_summaries or []))

        items: list[AiEntityListItem] = []
        risk_digest: list[dict[str, Any]] = []
        for r in (ws.risks or [])[:8]:
            sev = "critical" if int(r.count or 0) > 2 else "warning"
            items.append(
                AiEntityListItem(
                    id=r.key,
                    title=f"{r.label} ({r.count} employees)",
                    subtitle=sanitize_untrusted_text(r.explanation, 180),
                    badge_text=f"{r.count} flagged",
                    severity=sev,  # type: ignore[arg-type]
                    metric_value=str(r.count),
                    route_link=build_verified_deep_link(
                        "/planning",
                        month=res_month,
                        year=res_year,
                        team=resolved["team"],
                    ),
                )
            )
            risk_digest.append(
                {
                    "key": r.key,
                    "label": r.label,
                    "count": r.count,
                    "explanation": sanitize_untrusted_text(r.explanation, 140),
                }
            )

        cards: list[StructuredVisualCard] = []
        if items:
            cards.append(
                StructuredVisualCard(
                    card_type="entity_list",
                    title=f"Governance & SIP / Attrition Risk Buckets · {scope_label}",
                    subtitle=f"Risk classification summary for {period_label}",
                    items=items,
                )
            )

        citations = [
            SourceCitationPill(label=f"Period · {period_label}", category="period"),
            SourceCitationPill(label=f"Scope · {scope_label}", category="scope"),
            SourceCitationPill(label=f"Risk Categories · {len(items)}", category="metric"),
        ]
        deep_links = [
            DeepLinkCta(
                label="Open Performance Planning →",
                route=build_verified_deep_link(
                    "/planning",
                    month=res_month,
                    year=res_year,
                    team=resolved["team"],
                ),
                icon_key="planning",
            )
        ]

        return ToolExecutionResult(
            tool_name="get_governance_candidates_and_plans",
            arguments=resolved,
            records_evaluated=total_employees,
            digest={"period": period_label, "scope": scope_label, "risk_candidates": risk_digest},
            visual_cards=cards,
            citations=citations,
            deep_links=deep_links,
            resolved_month=res_month,
            resolved_year=res_year,
        )

    @_read_only_tool
    def execute_corrective_actions_status(
        self,
        *,
        team: str | None = None,
        function: str | None = None,
        month: str | None = None,
        year: int | None = None,
        region: str | None = None,
        state: str | None = None,
        open_only: bool = False,
        today: Any = None,
        apply_period_filter: bool = True,
        employee_id: str | None = None,
        employee_name: str | None = None,
    ) -> ToolExecutionResult:
        # Preserve optional period rule: when month and year are not explicitly
        # requested for a guided follow-up read, query across the authorized scope.
        req_month = month if apply_period_filter else None
        req_year = year if apply_period_filter else None
        resolved = self.ctx.resolve_filters(
            team=team,
            function=function,
            month=req_month,
            year=req_year,
        )
        effective_region = region or resolved.get("region")
        effective_month = resolved["month"] if (apply_period_filter and (month or year)) else None
        effective_year = resolved["year"] if (apply_period_filter and (month or year)) else None
        effective_state = (state or "").strip().casefold() or None
        emp_id_filter = str(employee_id or "").strip() or None
        emp_name_filter = str(employee_name or "").strip() or None

        def _matches_employee_action(act: dict[str, Any]) -> bool:
            if not emp_id_filter and not emp_name_filter:
                return True
            act_eid = str(act.get("employee_id") or "").strip().casefold()
            act_ename = str(act.get("employee_name") or "").strip().casefold()
            if emp_id_filter and act_eid and act_eid == emp_id_filter.casefold():
                return True
            if emp_name_filter and act_ename:
                q_norm = emp_name_filter.casefold()
                if q_norm in act_ename or act_ename in q_norm:
                    return True
                q_tokens = [tok for tok in re.findall(r"[a-z0-9\u0600-\u06FF]+", q_norm) if len(tok) >= 2]
                if q_tokens and all(tok in act_ename for tok in q_tokens):
                    return True
            return False

        try:
            ca_service = CorrectiveActionService(self.ctx.db, today=today) if today is not None else CorrectiveActionService(self.ctx.db)
            follow_up = ca_service.list_follow_up(
                self.ctx.scope,
                state=effective_state,
                team=resolved["team"],
                month=effective_month,
                region=effective_region,
            )
        except Exception as exc:
            logger.warning("CorrectiveActionService.list_follow_up failed: %s", exc)
            return ToolExecutionResult(
                tool_name="get_corrective_actions_status",
                arguments={
                    **resolved,
                    "month": effective_month,
                    "year": effective_year,
                    "state": effective_state,
                    "employee_id": emp_id_filter,
                    "employee_name": emp_name_filter,
                },
                records_evaluated=0,
                digest={
                    "status": "unavailable",
                    "error": "corrective_actions_read_failed",
                    "total_actions": 0,
                    "actions": [],
                    "record_ids": [],
                    "action_state": effective_state,
                    "scope": resolved["team"] or resolved["function"] or "your authorized scope",
                    "period": f"{effective_month} {effective_year}" if effective_month and effective_year else None,
                    "open_actions_only": open_only,
                    "employee_filter": emp_name_filter or emp_id_filter,
                },
                visual_cards=[],
                citations=[],
                deep_links=[],
                resolved_month=effective_month,
                resolved_year=effective_year,
            )

        actions = list(follow_up.get("actions") or [])
        if open_only:
            actions = [action for action in actions if action.get("status") in OPEN_ACTION_STATUSES]
        if effective_year:
            actions = [action for action in actions if action.get("year") == effective_year]
        if not resolved["team"] and resolved["function"]:
            fn_keys = function_team_keys(resolved["function"])
            if fn_keys:
                actions = [
                    a for a in actions if str(a.get("team") or "").strip().casefold() in fn_keys
                ]
            elif (resolved["function"] or "").casefold() == "call center":
                actions = [
                    a for a in actions if str(a.get("team") or "").casefold() in ("inbound", "outbound", "call center")
                ]
        if emp_id_filter or emp_name_filter:
            actions = [a for a in actions if _matches_employee_action(a)]
            # Also include active saved individual Action rows without a due_date
            # (list_follow_up only includes follow-up actions with due_date set).
            try:
                from models.models import Action as ActionModel, Employee as EmployeeModel, Team as TeamModel
                from utils.report_scope import user_can_access_team_level

                seen_ids = {str(a.get("id")) for a in actions if a.get("id") is not None}
                q_acts = (
                    self.ctx.db.query(ActionModel, EmployeeModel, TeamModel)
                    .join(EmployeeModel, ActionModel.employee_id == EmployeeModel.id)
                    .join(TeamModel, ActionModel.team_id == TeamModel.id)
                    .filter(ActionModel.is_active.is_(True))
                )
                if effective_month:
                    q_acts = q_acts.filter(ActionModel.month.ilike(effective_month))
                if effective_year:
                    q_acts = q_acts.filter(ActionModel.year == int(effective_year))
                for act_row, emp_row, team_row in q_acts.all():
                    if str(act_row.id) in seen_ids:
                        continue
                    t_name = str(team_row.display_name or team_row.name or "").strip()
                    if not user_can_access_team_level(self.ctx.scope, t_name, emp_row.performance_level):
                        continue
                    if self.ctx.scope.get("role") == "Branch Director":
                        acc_b = self.ctx.scope.get("accessible_branches") or []
                        if act_row.branch_key not in acc_b:
                            continue
                    if open_only and act_row.status not in OPEN_ACTION_STATUSES:
                        continue
                    cand_dict = {
                        "id": str(act_row.id),
                        "employee_id": emp_row.employee_id,
                        "employee_name": emp_row.name,
                        "team": t_name,
                        "month": act_row.month,
                        "year": act_row.year,
                        "action_type": act_row.action_type,
                        "action_text": act_row.action_text,
                        "plan_title": act_row.plan_title,
                        "status": act_row.status,
                        "due_date": act_row.due_date.isoformat() if act_row.due_date else None,
                        "follow_up_state": "open" if act_row.status in OPEN_ACTION_STATUSES else str(act_row.status or "closed").casefold(),
                    }
                    if _matches_employee_action(cand_dict):
                        seen_ids.add(str(act_row.id))
                        actions.append(cand_dict)
            except Exception as direct_exc:
                logger.debug("Direct employee action lookup skipped: %s", direct_exc)

        # When filtering for a specific employee and 0 actions matched the requested month,
        # also check across all periods so we tell the manager whether any prior saved action exists,
        # and attach a compact read-only scorecard snapshot (score + biggest KPI drag).
        other_period_actions: list[dict[str, Any]] = []
        employee_context: dict[str, Any] | None = None
        if emp_id_filter or emp_name_filter:
            if not actions and effective_month:
                try:
                    all_follow_up = ca_service.list_follow_up(
                        self.ctx.scope,
                        state=effective_state,
                        team=resolved["team"],
                        month=None,
                        region=effective_region,
                    )
                    for act in (all_follow_up.get("actions") or []):
                        if _matches_employee_action(act):
                            other_period_actions.append(
                                {
                                    "month": act.get("month"),
                                    "year": act.get("year"),
                                    "status": act.get("status"),
                                    "action_type": act.get("action_type"),
                                    "action_text": sanitize_untrusted_text(
                                        act.get("manager_action") or act.get("action_text") or act.get("plan_title") or "",
                                        140,
                                    ),
                                }
                            )
                except Exception:
                    pass
            try:
                scoped_recs = self.ctx.get_scoped_records()
                matched_recs: list[Any] = []
                for rec in scoped_recs:
                    r_eid = str(_record_field(rec, "employee_id", "") or "").strip()
                    r_ename = str(_record_field(rec, "employee_name", "") or "").strip()
                    id_ok = bool(emp_id_filter and r_eid.casefold() == emp_id_filter.casefold())
                    name_ok = False
                    if emp_name_filter and r_ename:
                        qn = emp_name_filter.casefold()
                        rn = r_ename.casefold()
                        q_toks = [t for t in re.findall(r"[a-z0-9\u0600-\u06FF]+", qn) if len(t) >= 2]
                        name_ok = qn in rn or rn in qn or (bool(q_toks) and all(t in rn for t in q_toks))
                    if not (id_ok or name_ok):
                        continue
                    if effective_month and str(_record_field(rec, "month", "") or "").strip().casefold() != effective_month.casefold():
                        continue
                    if effective_year and int(_record_field(rec, "year", 0) or 0) != int(effective_year):
                        continue
                    matched_recs.append(rec)
                if matched_recs:
                    matched_recs.sort(
                        key=lambda r: (
                            int(_record_field(r, "year", 0) or 0),
                            MONTH_ORDER.get(str(_record_field(r, "month", "") or "").strip(), 0),
                        )
                    )
                    rec_pick = matched_recs[-1]
                    sc_val = _record_evaluation_score(rec_pick)
                    rec_name = str(_record_field(rec_pick, "employee_name", "") or emp_name_filter or "").strip()
                    rec_id = str(_record_field(rec_pick, "employee_id", "") or emp_id_filter or "").strip()
                    rec_team = str(_record_field(rec_pick, "team", "") or resolved["team"] or "").strip()
                    rec_month = str(_record_field(rec_pick, "month", "") or "").strip()
                    rec_year = int(_record_field(rec_pick, "year", 0) or 0)
                    ev_obj = getattr(rec_pick, "evaluation", None)
                    rec_grade = str((ev_obj.get("grade") if isinstance(ev_obj, dict) else getattr(ev_obj, "grade", "")) or "").strip()
                    drags: list[dict[str, Any]] = []
                    for kv in (getattr(rec_pick, "kpi_values", None) or []):
                        kk = str((kv.get("kpi_key") if isinstance(kv, dict) else getattr(kv, "kpi_key", "")) or "")
                        if kk.casefold() in ("overall_score", "bookings_count", "attended_count"):
                            continue
                        kl = str((kv.get("label") if isinstance(kv, dict) else getattr(kv, "label", "")) or kk)
                        ach_raw = kv.get("achievement_ratio") if isinstance(kv, dict) else getattr(kv, "achievement_ratio", None)
                        act_raw = kv.get("actual_value") if isinstance(kv, dict) else getattr(kv, "actual_value", None)
                        tgt_raw = kv.get("target_value") if isinstance(kv, dict) else getattr(kv, "target_value", None)
                        unit_raw = str((kv.get("unit") if isinstance(kv, dict) else getattr(kv, "unit", "%")) or "%")
                        if ach_raw is None or act_raw is None:
                            continue
                        ach_pct_v = min(100.0, round(float(ach_raw) * 100.0 if float(ach_raw) <= 2.0 else float(ach_raw), 1))
                        if ach_pct_v >= 95.0:
                            continue
                        if unit_raw == "%":
                            act_d = f"{(float(act_raw) * 100.0 if float(act_raw) <= 1.5 else float(act_raw)):.1f}%"
                            tgt_d = f"{(float(tgt_raw) * 100.0 if float(tgt_raw) <= 1.5 else float(tgt_raw)):.1f}%" if tgt_raw is not None else None
                        else:
                            act_d = f"{float(act_raw):g} {unit_raw}".strip()
                            tgt_d = f"{float(tgt_raw):g} {unit_raw}".strip() if tgt_raw is not None else None
                        drags.append({"label": kl, "actual": act_d, "target": tgt_d, "achievement_pct": ach_pct_v})
                    drags.sort(key=lambda d: d["achievement_pct"])
                    employee_context = {
                        "employee_name": rec_name,
                        "employee_id": rec_id,
                        "team": rec_team,
                        "period": f"{rec_month} {rec_year}".strip() if rec_month and rec_year else None,
                        "score": round(float(sc_val), 1) if sc_val is not None else None,
                        "grade": rec_grade or None,
                        "top_drags": drags[:2],
                    }
            except Exception:
                pass

        # Count all matching authorized records BEFORE limiting displayed rows.
        total_matching = len(actions)
        all_record_ids = [str(act.get("id")) for act in actions if act.get("id") is not None]

        items: list[AiEntityListItem] = []
        action_digest: list[dict[str, Any]] = []
        for act in actions[:8]:
            emp_name = act.get("employee_name") or act.get("team") or "Team Action"
            f_state = str(act.get("follow_up_state") or "open")
            sev = "critical" if f_state == "overdue" else ("warning" if f_state in ("due_soon", "upcoming") else "good")
            action_text = sanitize_untrusted_text(
                act.get("manager_action") or act.get("action_text") or act.get("plan_title") or "",
                150,
            )
            due_str = str(act.get("due_date") or "").strip() or None
            team_str = str(act.get("team") or "").strip()
            subtitle_parts = [p for p in (team_str, f"Due {due_str}" if due_str else None, action_text) if p]
            items.append(
                AiEntityListItem(
                    id=str(act.get("id") or emp_name),
                    title=f"{emp_name} · {act.get('action_type') or 'Action'}",
                    subtitle=" · ".join(subtitle_parts),
                    badge_text=f_state.replace("_", " ").title(),
                    severity=sev,  # type: ignore[arg-type]
                    metric_value=str(act.get("status") or "Open"),
                    route_link=build_verified_deep_link("/corrective-actions", team=resolved["team"], month=effective_month),
                )
            )
            action_digest.append(
                {
                    "id": str(act.get("id")) if act.get("id") is not None else None,
                    "employee_name": emp_name,
                    "team": team_str or None,
                    "due_date": due_str,
                    "owner": (act.get("owner") or {}).get("name") if isinstance(act.get("owner"), dict) else None,
                    "action_type": act.get("action_type"),
                    "status": act.get("status"),
                    "follow_up_state": f_state,
                    "action_text": action_text,
                    "month": act.get("month"),
                    "year": act.get("year"),
                }
            )

        state_display = effective_state.replace("_", " ") if effective_state else "tracked"
        cards: list[StructuredVisualCard] = []
        if items:
            cards.append(
                StructuredVisualCard(
                    card_type="entity_list",
                    title=f"Corrective Actions Follow-Up ({state_display.title()})",
                    subtitle=f"{total_matching} matching {state_display} corrective actions in scope",
                    items=items,
                )
            )
        else:
            cards.append(
                StructuredVisualCard(
                    card_type="guardrail_notice",
                    title="No Matching Corrective Actions",
                    subtitle="Read-only governance check",
                    notice_text=f"0 {state_display} corrective actions matched your authorized scope and filters.",
                )
            )

        scope_text = resolved["team"] or resolved["function"] or "All authorized teams"
        citations = [
            SourceCitationPill(label=f"Scope · {scope_text}", category="scope"),
            SourceCitationPill(label=f"Actions ({state_display}) · {total_matching}", category="metric"),
        ]
        deep_links = [
            DeepLinkCta(
                label="Open Corrective Actions →",
                route=build_verified_deep_link("/corrective-actions", team=resolved["team"], month=effective_month),
                icon_key="actions",
            )
        ]

        emp_filter_display = (
            (employee_context or {}).get("employee_name")
            or emp_name_filter
            or emp_id_filter
        )
        return ToolExecutionResult(
            tool_name="get_corrective_actions_status",
            arguments={
                **resolved,
                "month": effective_month,
                "year": effective_year,
                "state": effective_state,
                "employee_id": emp_id_filter,
                "employee_name": emp_name_filter,
            },
            records_evaluated=total_matching,
            digest={
                "status": "ok",
                "total_actions": total_matching,
                "displayed_actions": len(action_digest),
                "record_ids": all_record_ids,
                "action_state": effective_state,
                "summary": follow_up.get("summary"),
                "actions": action_digest,
                "scope": resolved["team"] or resolved["function"] or "your authorized scope",
                "period": f"{effective_month} {effective_year}" if effective_month and effective_year else None,
                "open_actions_only": open_only,
                "employee_filter": emp_filter_display,
                "employee_id_filter": (employee_context or {}).get("employee_id") or emp_id_filter,
                "other_period_actions": other_period_actions[:3],
                "employee_context": employee_context,
            },
            visual_cards=cards,
            citations=citations,
            deep_links=deep_links,
            resolved_month=effective_month,
            resolved_year=effective_year,
        )

    @_read_only_tool
    def execute_guide_lookup(
        self,
        *,
        query: str,
        page_id: str | None = None,
        team: str | None = None,
        function: str | None = None,
        month: str | None = None,
        year: int | None = None,
        max_results: int = 3,
    ) -> ToolExecutionResult:
        """Retrieve verified, authorization-filtered PMS product guide sections locally."""
        from services.ai.product_guide import get_product_guide, search_product_guide

        ss_for_nav = self.ctx.session_state.model_copy(
            update={
                "team": team if team is not None else self.ctx.session_state.team,
                "function": function if function is not None else self.ctx.session_state.function,
                "month": month if month is not None else self.ctx.session_state.month,
                "year": year if year is not None else self.ctx.session_state.year,
            }
        )
        try:
            loaded = get_product_guide()
            matches = search_product_guide(
                query,
                scope=self.ctx.scope,
                session_state=ss_for_nav,
                max_results=max_results,
                page_id=page_id,
                guide=loaded,
            )
        except Exception as exc:
            logger.warning("Product guide lookup failed: %s", exc)
            return ToolExecutionResult(
                tool_name="guide_lookup",
                arguments={"query": query, "page_id": page_id, "team": team},
                records_evaluated=0,
                digest={
                    "status": "unavailable",
                    "error": "guide_unavailable",
                    "guide_version": None,
                    "sections": [],
                },
                visual_cards=[],
                citations=[],
                deep_links=[],
            )

        sections_payload: list[dict[str, Any]] = []
        nav_targets: list[dict[str, Any]] = []
        seen_routes: set[str] = set()
        deep_links: list[DeepLinkCta] = []
        citations: list[SourceCitationPill] = []

        for m in matches:
            sec = m.section
            nav = m.navigation_target
            sections_payload.append(
                {
                    "id": sec.id,
                    "title": sec.title,
                    "page_id": sec.page_id,
                    "version": sec.version,
                    "summary": sec.summary,
                    "steps": list(sec.steps),
                    "score": m.score,
                    "route": nav.route if nav else None,
                    "label": nav.label if nav else None,
                }
            )
            citations.append(
                SourceCitationPill(label=f"Guide · {sec.title} (v{sec.version})", category="scope")
            )
            if nav and nav.route not in seen_routes:
                seen_routes.add(nav.route)
                nav_targets.append(nav.model_dump())
                dl_icon = nav.icon_key if nav.icon_key in ("insights", "team", "employee", "planning", "actions", "bsc") else "insights"
                deep_links.append(
                    DeepLinkCta(label=nav.label, route=nav.route, icon_key=dl_icon)
                )

        return ToolExecutionResult(
            tool_name="guide_lookup",
            arguments={"query": query, "page_id": page_id, "team": team},
            records_evaluated=len(sections_payload),
            digest={
                "status": "ok" if sections_payload else "empty",
                "guide_version": loaded.guide_version,
                "sections": sections_payload,
                "navigation_targets": nav_targets,
            },
            visual_cards=[],
            citations=citations[:3],
            deep_links=deep_links[:3],
        )

    @_read_only_tool
    def execute_reachability_target_assessment(
        self,
        *,
        team: str = "Outbound",
        region: str | None = None,
        branch: str | None = None,
        month: str | None = None,
        year: int | None = None,
        hypothetical_target: float | None = None,
    ) -> ToolExecutionResult:
        """Assess Outbound Reachability target vs actuals, scoring basis, coverage, and optional hypothetical target."""
        from config.loader import GLOBAL_KPI_ACHIEVEMENT_CAP
        from models.models import EvaluationRevision, Team as OrmTeam, TeamConfigurationVersion

        resolved = self.ctx.resolve_filters(
            team=team,
            function="Call Center",
            branch=branch,
            month=month,
            year=year,
        )
        eff_region = region or resolved.get("region")
        cat_def = get_ai_catalog().find_metric_definition(
            team="Outbound",
            kpi_key_or_label="Reachability",
            performance_level="Employee",
        )
        kpi_weight = float(getattr(cat_def, "weight_percent", 10.0) or 10.0)
        kpi_unit = str(getattr(cat_def, "unit", "%") or "%")
        kpi_direction = str(getattr(cat_def, "direction", "higher_better") or "higher_better")

        # Gather all authorized Outbound Employee records across published periods
        all_records = self.ctx.get_scoped_records()
        outbound_keys = selection_team_keys("Outbound") | {"outbound"}
        by_period: dict[tuple[int, int, str], dict[str, Any]] = {}

        for rec in all_records:
            r_team = str(_record_field(rec, "team", "") or "").strip()
            if r_team.casefold() not in outbound_keys:
                continue
            if str(_record_field(rec, "performance_level", "Employee") or "Employee").casefold() != "employee":
                continue
            if eff_region and _shared_record_region(rec, r_team).casefold() != str(eff_region).casefold():
                continue
            if resolved["branch"]:
                if not record_matches_branch(rec, resolved["branch"]):
                    continue
                rec = project_record_for_branch(rec, resolved["branch"])
            y_val = int(_record_field(rec, "year", 0) or 0)
            m_str = str(_record_field(rec, "month", "") or "").strip()
            m_ord = MONTH_ORDER.get(m_str, 0)
            if not (y_val and m_ord):
                continue
            bucket = by_period.setdefault(
                (y_val, m_ord, m_str),
                {"total_records": 0, "actuals": [], "targets": [], "achievements": []},
            )
            bucket["total_records"] += 1
            snap = self._extract_record_kpi_snapshot(rec, "reachability", "Outbound", None)
            if snap is not None and snap.get("numeric_value") is not None:
                bucket["actuals"].append(float(snap["numeric_value"]))
                if snap.get("target_numeric") is not None:
                    bucket["targets"].append(float(snap["target_numeric"]))
                if snap.get("achievement") is not None:
                    bucket["achievements"].append(float(snap["achievement"]))

        # Inspect TeamConfigurationVersion vs EvaluationRevision for approved-not-yet-applied Outbound targets
        pending_approved_targets: list[dict[str, Any]] = []
        applied_revisions_by_period: dict[tuple[int, int], str] = {}
        try:
            orm_teams = self.ctx.db.query(OrmTeam).all()
            out_team_ids = [t.id for t in orm_teams if str(t.name or "").strip().casefold() in outbound_keys]
            if out_team_ids:
                active_revs = (
                    self.ctx.db.query(EvaluationRevision)
                    .filter(
                        EvaluationRevision.team_id.in_(out_team_ids),
                        EvaluationRevision.status == "active",
                    )
                    .all()
                )
                active_ver_ids = {r.version_id for r in active_revs}
                for r in active_revs:
                    applied_revisions_by_period[(int(r.year), int(r.month))] = f"Applied revision (version {str(r.version_id)[:8]})"

                approved_vers = (
                    self.ctx.db.query(TeamConfigurationVersion)
                    .filter(
                        TeamConfigurationVersion.team_id.in_(out_team_ids),
                        TeamConfigurationVersion.status.in_(["approved", "published"]),
                        TeamConfigurationVersion.is_active.is_(True),
                    )
                    .all()
                )
                for ver in approved_vers:
                    if ver.id in active_ver_ids:
                        continue
                    snap_cfg = ver.config_snapshot if isinstance(ver.config_snapshot, dict) else {}
                    t_map = snap_cfg.get("targets") if isinstance(snap_cfg.get("targets"), dict) else {}
                    raw_other = t_map.get("Other") if "Other" in t_map else t_map.get("Reachability")
                    if raw_other is not None:
                        target_pct = float(raw_other) * 100.0 if float(raw_other) <= 1.0 else float(raw_other)
                        pending_approved_targets.append(
                            {
                                "period": f"{ver.effective_month} {ver.effective_year}",
                                "version_number": ver.version_number,
                                "approved_target_pct": round(target_pct, 1),
                                "applied": False,
                            }
                        )
        except Exception as exc:
            logger.debug("Optional monthly evaluation version lookup skipped: %s", exc)

        period_rows: list[dict[str, Any]] = []
        for (y_val, m_ord, m_str) in sorted(by_period.keys()):
            b = by_period[(y_val, m_ord, m_str)]
            actuals = b["actuals"]
            targets = b["targets"]
            sample_size = len(actuals)
            total_recs = b["total_records"]
            avg_actual = round(sum(actuals) / sample_size, 1) if sample_size else None
            avg_target = round(sum(targets) / len(targets), 1) if targets else None
            if avg_actual is not None and avg_target and avg_target > 0:
                attainment = round(min((avg_actual / avg_target) * 100.0, GLOBAL_KPI_ACHIEVEMENT_CAP * 100.0), 1)
            else:
                attainment = None
            period_rows.append(
                {
                    "period": f"{m_str} {y_val}",
                    "period_key": f"{y_val}-{m_ord:02d}",
                    "actual": avg_actual,
                    "applied_target": avg_target,
                    "measured_attainment": attainment,
                    "sample_size": sample_size,
                    "total_records": total_recs,
                    "coverage_pct": round((sample_size / total_recs) * 100.0, 1) if total_recs else 0.0,
                    "scoring_basis": applied_revisions_by_period.get((y_val, m_ord), "Published workbook / baseline rules"),
                }
            )

        # Evaluate hypothetical target impact on the latest period with verified actuals
        latest_with_data = next((row for row in reversed(period_rows) if row["actual"] is not None), None)
        hypothetical_calc: dict[str, Any] | None = None
        if hypothetical_target is not None and hypothetical_target > 0 and latest_with_data is not None:
            actual_val = float(latest_with_data["actual"])
            current_tgt = latest_with_data["applied_target"]
            current_att = latest_with_data["measured_attainment"]
            new_att = round(min((actual_val / float(hypothetical_target)) * 100.0, GLOBAL_KPI_ACHIEVEMENT_CAP * 100.0), 1)
            hypothetical_calc = {
                "period": latest_with_data["period"],
                "actual_reachability_pct": actual_val,
                "current_applied_target_pct": current_tgt,
                "current_measured_attainment_pct": current_att,
                "hypothetical_target_pct": round(float(hypothetical_target), 1),
                "hypothetical_measured_attainment_pct": new_att,
                "attainment_delta_pp": round(new_att - float(current_att), 1) if current_att is not None else None,
                "cap_pct": round(GLOBAL_KPI_ACHIEVEMENT_CAP * 100.0, 1),
            }

        # Compare explanations (target change vs underlying performance decline) & note missing evidence
        missing_evidence: list[str] = []
        valid_periods = [r for r in period_rows if r["actual"] is not None]
        if len(valid_periods) < 2:
            missing_evidence.append(
                "At least two comparable published periods with Outbound Reachability actuals and targets are needed to separate a target change from a performance decline."
            )
        if not valid_periods or all(r["applied_target"] is None for r in valid_periods):
            missing_evidence.append("Verified applied target values are missing in the stored Outbound records.")

        explanation_comparison = ""
        if len(valid_periods) >= 2:
            prev_p, curr_p = valid_periods[-2], valid_periods[-1]
            actual_diff = round(float(curr_p["actual"]) - float(prev_p["actual"]), 1)
            target_changed = (
                prev_p["applied_target"] is not None
                and curr_p["applied_target"] is not None
                and abs(float(curr_p["applied_target"]) - float(prev_p["applied_target"])) >= 0.1
            )
            if target_changed and abs(actual_diff) < 1.0:
                explanation_comparison = (
                    f"Target change explanation fits better: actual Reachability stayed near {curr_p['actual']:.1f}% "
                    f"({actual_diff:+.1f} pp vs {prev_p['period']}) while the applied target shifted from "
                    f"{prev_p['applied_target']:.1f}% to {curr_p['applied_target']:.1f}%."
                )
            elif not target_changed and actual_diff < -0.5:
                explanation_comparison = (
                    f"Performance decline explanation fits better: applied target stayed constant at "
                    f"{curr_p['applied_target']:.1f}%, while actual Reachability fell by {abs(actual_diff):.1f} pp "
                    f"from {prev_p['actual']:.1f}% ({prev_p['period']}) to {curr_p['actual']:.1f}% ({curr_p['period']})."
                )
            elif target_changed and actual_diff < -0.5:
                explanation_comparison = (
                    f"Both factors contributed: applied target changed ({prev_p['applied_target']:.1f}% → {curr_p['applied_target']:.1f}%) "
                    f"AND actual Reachability declined by {abs(actual_diff):.1f} pp ({prev_p['actual']:.1f}% → {curr_p['actual']:.1f}%)."
                )
            else:
                explanation_comparison = (
                    f"Actual Reachability moved {actual_diff:+.1f} pp ({prev_p['actual']:.1f}% → {curr_p['actual']:.1f}%) "
                    f"against applied target {curr_p['applied_target']:.1f}%."
                    if curr_p["applied_target"] is not None
                    else f"Actual Reachability moved {actual_diff:+.1f} pp ({prev_p['actual']:.1f}% → {curr_p['actual']:.1f}%)."
                )

        citations = [
            SourceCitationPill(label="KPI · Outbound Reachability (Other · 10% weight)", category="metric"),
            SourceCitationPill(label=f"Periods Evaluated · {len(valid_periods)}", category="period"),
        ]
        deep_links = [
            DeepLinkCta(
                label="Open Outbound Team Dashboard →",
                route=build_verified_deep_link("/team/outbound", team="Outbound", month=resolved["month"]),
                icon_key="team",
            )
        ]

        return ToolExecutionResult(
            tool_name="assess_reachability_target",
            arguments={
                "team": "Outbound",
                "region": resolved["region"],
                "branch": resolved["branch"],
                "hypothetical_target": hypothetical_target,
            },
            records_evaluated=sum(r["sample_size"] for r in valid_periods),
            digest={
                "status": "ok" if valid_periods else "insufficient_evidence",
                "kpi_definition": {
                    "kpi_key": "Other",
                    "display_name": "Reachability",
                    "team": "Outbound",
                    "weight_percent": kpi_weight,
                    "unit": kpi_unit,
                    "direction": kpi_direction,
                    "aggregation": "average",
                },
                "periods": period_rows,
                "pending_approved_targets": pending_approved_targets,
                "hypothetical_assessment": hypothetical_calc,
                "explanation_comparison": explanation_comparison,
                "missing_evidence": missing_evidence,
            },
            visual_cards=[],
            citations=citations,
            deep_links=deep_links,
            resolved_month=resolved["month"],
            resolved_year=resolved["year"],
        )

    @_read_only_tool
    def execute_management_balanced_scorecard(
        self,
        *,
        team: str | None = None,
        function: str | None = None,
        performance_level: str | None = None,
        month: str | None = None,
        year: int | None = None,
    ) -> ToolExecutionResult:
        resolved = self.ctx.resolve_filters(
            team=team,
            function=function,
            performance_level=performance_level or "Managerial",
            month=month,
            year=year,
        )
        role = str(self.ctx.scope.get("role") or "")
        if role == "Branch Director" or resolved["branch"]:
            card = StructuredVisualCard(
                card_type="guardrail_notice",
                title="Balanced Scorecard Scope Notice (Managerial / Corporate)",
                subtitle="Team-level governance boundary",
                notice_text=(
                    "Managerial and Corporate Balanced Scorecards (Team SLA, Team Quality, Coaching Completion, "
                    "Attendance Compliance, Cost Efficiency) are evaluated at the team level and are not partitioned "
                    "by individual UAE hospital branches (Dubai/Sharjah)."
                ),
            )
            return ToolExecutionResult(
                tool_name="get_management_balanced_scorecard",
                arguments=resolved,
                records_evaluated=0,
                digest={"guardrail": card.notice_text},
                visual_cards=[card],
                citations=[
                    SourceCitationPill(label="Level · Managerial/Corporate BSC", category="policy", warning=True)
                ],
                deep_links=[],
                guardrail_triggered=True,
            )

        target_team = resolved["team"]
        if not target_team:
            return ToolExecutionResult(tool_name="get_management_balanced_scorecard", arguments=resolved,
                                       digest={"unavailable_reason": "Select an authorized team for a balanced scorecard."})
        lvl = resolved["performance_level"] if resolved["performance_level"] in ("Managerial", "Corporate") else "Managerial"
        if target_team.casefold() in ("crm", "nursing", "pmo"):
            lvl = "Corporate"

        bsc_score: float | None = None
        bsc_period_label: str | None = None
        typed_evidence: list[TypedMetricEvidence] = []
        bars: list[AiBarItem] = []
        bsc_digest: list[dict[str, Any]] = []
        bsc_route = build_verified_deep_link(
            "/executive" if lvl == "Corporate" else f"/team/{_team_route_slug(target_team)}",
            team=target_team,
            performance_level=lvl,
            month=resolved["month"],
            year=resolved["year"],
        )

        if lvl == "Corporate":
            try:
                from services.management_bsc_service import ManagementBSCService

                ds = ManagementBSCService(self.ctx.db).build_scorecard_dataset(
                    team_name=target_team,
                    performance_level="Corporate",
                    month=resolved["month"] or "All",
                    year=resolved["year"],
                    employee_ids=None,
                    history_months=6,
                    selected_kpi=None,
                    base_config={},
                )
                sc_meta = ds.get("scorecard") or {}
                if sc_meta.get("score") is not None and ds.get("kpi_table"):
                    bsc_score = round(float(sc_meta["score"]), 1)
                    sel = ds.get("selection") or {}
                    eff_m = sel.get("effective_month") or resolved["month"] or "Latest"
                    eff_y = sel.get("effective_year") or resolved["year"] or 2026
                    bsc_period_label = f"{eff_m} {eff_y}"
                    for row in ds.get("kpi_table") or []:
                        raw_w = float(row.get("weight") or 0.0)
                        is_track = raw_w <= 0.0005
                        w_pct = 0.0 if is_track else round(raw_w * 100.0, 1)
                        k_key = str(row.get("kpi_key") or "")
                        label = str(row.get("kpi_label") or k_key)
                        persp = str(row.get("perspective") or "Internal Process")
                        k_score = round(float(row.get("score") or 0.0), 1) if row.get("score") is not None else None
                        act_v = row.get("actual_value")
                        tgt_v = row.get("target_value")
                        unit_s = str(row.get("unit") or "%")
                        if unit_s == "%" and isinstance(act_v, (int, float)) and abs(act_v) <= 1.5:
                            act_disp = f"{act_v * 100.0:.1f}%"
                            tgt_disp = f"{(tgt_v or 0.0) * 100.0:.1f}%" if tgt_v is not None else "—"
                        else:
                            act_disp = f"{act_v} {unit_s}".strip() if act_v is not None else "—"
                            tgt_disp = f"{tgt_v} {unit_s}".strip() if tgt_v is not None else "—"
                        bars.append(
                            AiBarItem(
                                label=f"{label} ({persp})",
                                value=k_score if (k_score is not None and not is_track) else w_pct,
                                display_value=f"{k_score:.1f}% ach" if (k_score is not None and not is_track) else f"Weight {w_pct:.0f}%",
                                target_value=100.0,
                                secondary_label=f"{act_disp} vs {tgt_disp} · Weight {w_pct:.0f}%",
                                severity="good" if (k_score or 0.0) >= 85 else ("warning" if (k_score or 0.0) >= 75 else "critical"),
                            )
                        )
                        bsc_digest.append(
                            {
                                "key": k_key,
                                "label": label,
                                "weight_percent": w_pct,
                                "perspective": persp,
                                "actual_display": act_disp,
                                "target_display": tgt_disp,
                                "achievement_percent": k_score if not is_track else None,
                            }
                        )
                        typed_evidence.append(
                            TypedMetricEvidence(
                                metric_id=f"{target_team.casefold().replace(' ', '_')}:corporate:{k_key}",
                                kpi_key=k_key,
                                display_name=label,
                                team=target_team,
                                performance_level="Corporate",
                                branch="all",
                                period=bsc_period_label,
                                actual=float(act_v) if isinstance(act_v, (int, float)) else None,
                                target=float(tgt_v) if isinstance(tgt_v, (int, float)) else None,
                                actual_display=act_disp,
                                target_display=tgt_disp,
                                achievement_percent=k_score if not is_track else None,
                                weight_percent=w_pct,
                                unit=unit_s,
                                direction=str(row.get("direction") or "higher_better"),
                                contributes_to_score=not is_track,
                                sample_size=int(sc_meta.get("record_count") or 1),
                                source_link=bsc_route,
                            )
                        )
            except Exception:
                pass
        elif lvl == "Managerial":
            try:
                from utils.report_scope import selection_team_keys
                t_keys = selection_team_keys(target_team)
                mgr_recs = [
                    r for r in self.ctx.get_scoped_records()
                    if str(getattr(r, "team", "") or "").casefold() in t_keys
                    and str(getattr(r, "performance_level", "") or "").casefold() == "managerial"
                    and (not resolved["month"] or str(getattr(r, "month", "") or "").casefold() == str(resolved["month"]).casefold())
                    and (not resolved["year"] or int(getattr(r, "year", 0) or 0) == int(resolved["year"]))
                ]
                if mgr_recs:
                    scores = []
                    for r in mgr_recs:
                        ev = getattr(r, "evaluation", None)
                        raw_sc = getattr(ev, "score", None) if ev is not None else getattr(r, "score", None)
                        if raw_sc is not None:
                            scores.append(float(raw_sc))
                    if scores:
                        bsc_score = round(sum(scores) / len(scores), 1)
                        bsc_period_label = f"{getattr(mgr_recs[0], 'month', 'Latest')} {getattr(mgr_recs[0], 'year', 2026)}"
            except Exception:
                pass

        if not bsc_digest:
            from services.ai.corporate_bsc_catalog_data import CORPORATE_BSC_CATALOG_TEAMS

            cfg = find_team_config_by_db_name(target_team) or {}
            lvl_cfg = (cfg.get("performance_levels") or {}).get(lvl) or {}
            kpis_cfg = list(lvl_cfg.get("kpis") or [])
            if not kpis_cfg and isinstance(lvl_cfg.get("positions"), dict):
                for pos_cfg in lvl_cfg["positions"].values():
                    if isinstance(pos_cfg, dict) and pos_cfg.get("kpis"):
                        kpis_cfg.extend(pos_cfg["kpis"])
            if not kpis_cfg and lvl == "Corporate" and target_team in CORPORATE_BSC_CATALOG_TEAMS:
                kpis_cfg = list(CORPORATE_BSC_CATALOG_TEAMS[target_team].get("kpis") or [])

            for k in kpis_cfg:
                raw_w = float(k.get("weight", 0.0))
                w_pct = 0.0 if raw_w <= 0.0005 else round(raw_w * 100, 1)
                label = disambiguate_call_center_kpi_label(target_team, k.get("key", ""), k.get("label", ""))
                persp = k.get("perspective", "Internal Process")
                bars.append(
                    AiBarItem(
                        label=f"{label} ({persp})",
                        value=w_pct,
                        display_value=f"Weight {w_pct:.0f}%",
                        target_value=100.0,
                        secondary_label=f"Perspective: {persp}",
                        severity="neutral",
                    )
                )
                bsc_digest.append({"key": k.get("key"), "label": label, "weight_percent": w_pct, "perspective": persp})

        cards = [
            StructuredVisualCard(
                card_type="horizontal_bar",
                title=f"{target_team} · {lvl} Balanced Scorecard" + (f" ({bsc_period_label})" if bsc_period_label else " Structure"),
                subtitle=(
                    f"Overall {lvl} Score: {bsc_score:.1f}% · Four-perspective strategic governance scorecard"
                    if bsc_score is not None
                    else "Four-perspective strategic governance scorecard (Financial, Customer, Internal Process, Learning & Growth)"
                ),
                bars=bars[:10],
            )
        ]
        citations = [
            SourceCitationPill(label=f"Team · {target_team}", category="scope"),
            SourceCitationPill(label=f"Level · {lvl} BSC", category="policy"),
        ]
        if bsc_period_label:
            citations.insert(0, SourceCitationPill(label=f"Period · {bsc_period_label}", category="period"))
        deep_links = [
            DeepLinkCta(
                label=f"Open {target_team} {lvl} Scorecard →",
                route=bsc_route,
                icon_key="bsc",
            )
        ]

        return ToolExecutionResult(
            tool_name="get_management_balanced_scorecard",
            arguments={**resolved, "team": target_team, "performance_level": lvl},
            records_evaluated=len(bsc_digest),
            digest={
                "team": target_team,
                "scope": target_team,
                "level": lvl,
                "period": bsc_period_label or "Latest Period",
                "average_score": bsc_score,
                "bsc_kpis": bsc_digest,
            },
            visual_cards=cards,
            citations=citations,
            deep_links=deep_links,
            typed_evidence=typed_evidence,
        )

    def _compute_operational_volumes(
        self,
        *,
        month: str | None,
        year: int | None,
        team: str | None,
        function: str | None,
        branch: str | None,
    ) -> dict[str, Any]:
        records = self.ctx.get_scoped_records()
        sess_state = getattr(self.ctx, "session_state", None)
        requested_region = (getattr(sess_state, "region", None) or "").strip().casefold()
        total_bookings = 0.0
        total_attended = 0.0
        total_calls = 0.0
        total_inbound_calls = 0.0
        total_abandoned = 0.0

        # Scope-aware period publication: only set True if a record matches scope (team/function & period)
        has_period_records = False
        matching_branch_records = 0
        bookings_present_count = 0
        bookings_missing_count = 0
        attended_present_count = 0
        attended_missing_count = 0
        calls_present_count = 0
        inbound_calls_present_count = 0
        abandoned_present_count = 0
        booking_consistency_checks = 0
        booking_consistency_ok = True
        attendance_consistency_checks = 0
        attendance_consistency_ok = True
        abandon_consistency_checks = 0
        abandon_consistency_ok = True

        def _extract_metric_val(container: Any, field_name: str) -> Any:
            if container is None:
                return None
            if isinstance(container, dict):
                return container.get(field_name)
            return getattr(container, field_name, None)

        for rec in records:
            # 1. Period check
            r_month = str(getattr(rec, "month", "") or "").strip()
            r_year = int(getattr(rec, "year", 0) or 0)
            if month and r_month.casefold() != month.casefold():
                continue
            if year and r_year != int(year):
                continue

            # 2. Team & function check (publication is scope-aware)
            emp = getattr(rec, "employee", None)
            r_team = str(getattr(emp, "team", "") or getattr(rec, "team", "") or "").strip()
            if requested_region and requested_region != "all" and _shared_record_region(rec, r_team).casefold() != requested_region:
                continue
            if team and r_team.casefold() != team.casefold():
                continue
            if not team and function:
                from services.ai.catalog import function_for_team
                r_fn = function_for_team(r_team) or ("Call Center" if r_team.casefold() in ("inbound", "outbound", "call center") else r_team)
                if r_fn.casefold() != function.casefold():
                    continue

            # If we reached here, this record belongs to the requested month, year, and team/function scope!
            has_period_records = True

            # 3. Branch matching & volume extraction
            geo = getattr(rec, "geo", None)
            b_obj = getattr(geo, "bookings", None) if geo else None
            a_obj = getattr(geo, "attended", None) if geo else None

            norm_branch = branch.strip().casefold() if branch else None
            if norm_branch and norm_branch in BRANCH_KEYS:
                r_bk = str(getattr(rec, "branch_key", "") or "").strip().casefold()
                val_b = _extract_metric_val(b_obj, norm_branch)
                val_a = _extract_metric_val(a_obj, norm_branch)

                is_branch_match = False
                if r_bk and r_bk == norm_branch:
                    is_branch_match = True
                elif val_b is not None or val_a is not None:
                    is_branch_match = True
                elif not r_bk and not geo:
                    is_branch_match = record_matches_branch(rec, norm_branch)

                if not is_branch_match:
                    continue

                matching_branch_records += 1

                # Bookings metric presence
                if val_b is not None:
                    try:
                        total_bookings += float(val_b)
                        bookings_present_count += 1
                    except (ValueError, TypeError):
                        bookings_missing_count += 1
                else:
                    bookings_missing_count += 1

                # Attended metric presence
                if val_a is not None:
                    try:
                        total_attended += float(val_a)
                        attended_present_count += 1
                    except (ValueError, TypeError):
                        attended_missing_count += 1
                else:
                    attended_missing_count += 1

            elif norm_branch:
                if not record_matches_branch(rec, norm_branch):
                    continue
                matching_branch_records += 1

                val_b = getattr(rec, "bookings", None)
                if val_b is not None:
                    try:
                        total_bookings += float(val_b)
                        bookings_present_count += 1
                    except (ValueError, TypeError):
                        bookings_missing_count += 1
                else:
                    bookings_missing_count += 1

                val_a = getattr(rec, "attended", None)
                if val_a is not None:
                    try:
                        total_attended += float(val_a)
                        attended_present_count += 1
                    except (ValueError, TypeError):
                        attended_missing_count += 1
                else:
                    attended_missing_count += 1

            else:
                # All branches
                matching_branch_records += 1
                rec_has_branch_data = False
                rec_b_sum = 0.0
                rec_a_sum = 0.0
                for bk in BRANCH_KEYS:
                    vb = _extract_metric_val(b_obj, bk)
                    va = _extract_metric_val(a_obj, bk)
                    if vb is None and va is None:
                        continue
                    rec_has_branch_data = True
                    try:
                        if vb is None:
                            raise ValueError
                        fb = float(vb)
                        total_bookings += fb
                        rec_b_sum += fb
                        bookings_present_count += 1
                    except (ValueError, TypeError):
                        bookings_missing_count += 1
                    try:
                        if va is None:
                            raise ValueError
                        fa = float(va)
                        total_attended += fa
                        rec_a_sum += fa
                        attended_present_count += 1
                    except (ValueError, TypeError):
                        attended_missing_count += 1
                if not rec_has_branch_data:
                    bookings_missing_count += 1
                    attended_missing_count += 1

            # Calls metric presence
            calls = getattr(rec, "calls", None)
            rec_calls_v: float | None = None
            rec_inb_v: float | None = None
            rec_ab_v: float | None = None
            if calls is not None:
                val_c = _extract_metric_val(calls, "total_handled") or _extract_metric_val(calls, "inbound")
                if val_c is not None:
                    try:
                        rec_calls_v = float(val_c)
                        total_calls += rec_calls_v
                        calls_present_count += 1
                    except (ValueError, TypeError):
                        pass
                val_inb = _extract_metric_val(calls, "inbound")
                if val_inb is not None:
                    try:
                        rec_inb_v = float(val_inb)
                        total_inbound_calls += rec_inb_v
                        inbound_calls_present_count += 1
                    except (ValueError, TypeError):
                        pass
                val_ab = _extract_metric_val(calls, "abandoned")
                if val_ab is not None:
                    try:
                        rec_ab_v = float(val_ab)
                        total_abandoned += rec_ab_v
                        abandoned_present_count += 1
                    except (ValueError, TypeError):
                        pass

            # Verify per-record volume ratios match kpi_values (all-branch only) so
            # pooled ratios only apply when raw geo/calls volumes are internally consistent.
            if not norm_branch and rec_has_branch_data:
                r_team_cf = r_team.casefold()
                for kv in (getattr(rec, "kpi_values", None) or []):
                    kk = str((kv.get("kpi_key") if isinstance(kv, dict) else getattr(kv, "kpi_key", "")) or "").strip().casefold()
                    kl = str((kv.get("label") if isinstance(kv, dict) else getattr(kv, "label", "")) or "").strip().casefold()
                    raw_act = kv.get("actual_value") if isinstance(kv, dict) else getattr(kv, "actual_value", None)
                    if raw_act is None:
                        continue
                    try:
                        act_ratio = float(raw_act)
                    except (ValueError, TypeError):
                        continue
                    if act_ratio > 1.5:
                        act_ratio = act_ratio / 100.0
                    if kk in ("booking", "booking_rate", "bookingrate"):
                        r_den = (rec_inb_v or rec_calls_v) if r_team_cf == "inbound" else rec_calls_v
                        if r_den and r_den > 0:
                            booking_consistency_checks += 1
                            if abs((rec_b_sum / r_den) - act_ratio) > 0.025:
                                booking_consistency_ok = False
                    elif kk in ("attendance", "attendance_rate", "attendancerate"):
                        if rec_b_sum > 0:
                            attendance_consistency_checks += 1
                            if abs((rec_a_sum / rec_b_sum) - act_ratio) > 0.025:
                                attendance_consistency_ok = False
                    elif "abandon" in kl and rec_ab_v is not None and rec_calls_v and rec_calls_v > 0:
                        abandon_consistency_checks += 1
                        if abs((rec_ab_v / rec_calls_v) - act_ratio) > 0.025:
                            abandon_consistency_ok = False

        booking_present = bookings_present_count > 0
        attended_present = attended_present_count > 0
        calls_present = calls_present_count > 0
        has_partial_evidence = (bookings_present_count > 0 and bookings_missing_count > 0)
        booking_complete = (bookings_present_count > 0 and bookings_missing_count == 0)

        return {
            "total_bookings": round(total_bookings, 1) if booking_present else None,
            "total_attended": round(total_attended, 1) if attended_present and attended_missing_count == 0 else None,
            "total_calls_handled": round(total_calls, 1) if calls_present else None,
            "total_inbound_calls": round(total_inbound_calls, 1) if inbound_calls_present_count > 0 else None,
            "total_abandoned": round(total_abandoned, 1) if abandoned_present_count > 0 else None,
            "booking_present": booking_present,
            "booking_complete": booking_complete,
            "booking_ratio_consistent": booking_consistency_checks > 0 and booking_consistency_ok,
            "has_partial_evidence": has_partial_evidence,
            "attended_present": attended_present,
            "attendance_complete": attended_present and attended_missing_count == 0,
            "attendance_ratio_consistent": attendance_consistency_checks > 0 and attendance_consistency_ok,
            "abandon_ratio_consistent": abandon_consistency_checks > 0 and abandon_consistency_ok,
            "calls_present": calls_present,
            "data_present": booking_present,
            "period_published": has_period_records,
            "records_matched": matching_branch_records,
            "bookings_present_count": bookings_present_count,
            "bookings_missing_count": bookings_missing_count,
        }

    def _build_kpi_and_branch_decisions(
        self,
        *,
        scope_label: str,
        period_label: str,
        res_month: str | None,
        res_year: int | None,
        resolved: dict[str, Any],
        kpi_rows: list[AiKpiTableRow],
        volume_summary: dict[str, float],
        branch_comparison_digest: list[dict[str, Any]],
    ) -> list[AiDecisionItem]:
        decisions: list[AiDecisionItem] = []
        by_key = {r.kpi_key.casefold(): r for r in kpi_rows}

        att_row = by_key.get("attendance")
        book_row = by_key.get("booking")
        other_row = by_key.get("other")
        aht_row = by_key.get("aht")

        total_book = int(volume_summary["total_bookings"]) if volume_summary.get("total_bookings") is not None else None
        total_att = int(volume_summary["total_attended"]) if volume_summary.get("total_attended") is not None else None
        no_shows = max(0, total_book - total_att) if (total_book is not None and total_att is not None) else None
        plus5_patients = max(1, int(round(total_book * 0.05))) if (total_book is not None and total_book > 0) else 0

        # 1. Branch-Specific Conversion Decision (if branch comparison active and all requested have valid data)
        if len(branch_comparison_digest) >= 2:
            with_vol = [
                b for b in branch_comparison_digest
                if b.get("bookings") is not None
                and int(b.get("bookings") or 0) > 0
                and b.get("attendance_rate_pct") is not None
            ]
            if len(with_vol) >= 2 and all(b.get("data_present") is not False for b in branch_comparison_digest):
                best_b = max(with_vol, key=lambda b: float(b.get("attendance_rate_pct") or 0.0))
                most_noshows_b = max(with_vol, key=lambda b: int(b.get("no_shows") or 0))
                lowest_rate_b = min(with_vol, key=lambda b: float(b.get("attendance_rate_pct") or 0.0))
                recover_5pct = max(1, int(round(int(most_noshows_b["bookings"]) * 0.05)))
                decisions.append(
                    AiDecisionItem(
                        id="dec-branch-conversion",
                        priority="immediate",
                        priority_label="Branch Conversion Playbook",
                        title=(
                            f"Deploy T-24h Confirmation Protocol on {most_noshows_b['branch']} & {lowest_rate_b['branch']} Queues"
                        ),
                        rationale=(
                            f"{best_b['branch']} leads conversion at {best_b['attendance_rate_pct']:.1f}% Attended, whereas "
                            f"{lowest_rate_b['branch']} converts at {lowest_rate_b['attendance_rate_pct']:.1f}% and "
                            f"{most_noshows_b['branch']} accounts for {most_noshows_b['no_shows']:,} un-attended bookings."
                        ),
                        expected_impact=(
                            f"What-If ROI: Lifting {most_noshows_b['branch']} attendance by +5% recovers "
                            f"+{recover_5pct:,} attended patients/month without adding marketing spend."
                        ),
                        target_label=f"{most_noshows_b['branch']} & {lowest_rate_b['branch']} Booking Queues",
                        route_link=build_verified_deep_link(
                            "/insights",
                            month=res_month,
                            year=res_year,
                            function=resolved["function"],
                            team=resolved["team"],
                            branch=str(most_noshows_b["branch"]).lower(),
                        ),
                        cta_label=f"Open {most_noshows_b['branch']} Insights →",
                    )
                )

        # 2. Booking Quality vs. Attendance No-Show Paradox
        if att_row and (att_row.achievement_percent or 100.0) < 94.0:
            att_ach = float(att_row.achievement_percent or 0.0)
            att_w = float(att_row.weight_percent or 60.0)
            pts_lost = round(((100.0 - att_ach) / 100.0) * att_w, 2)
            book_ach = float(book_row.achievement_percent or 0.0) if book_row else 0.0

            paradox_note = (
                f"Booking Rate is at {book_row.actual_display} ({book_ach:.1f}% ach) while Attendance Rate is "
                f"{att_row.actual_display} vs {att_row.target_display} target ({att_row.people_below_target} agents below target)."
                if book_row and book_ach >= 92.0
                else f"Attendance Rate is at {att_row.actual_display} vs {att_row.target_display} target ({att_row.people_below_target} agents below target)."
            )
            vol_impact = (
                f" Recovers +{plus5_patients:,} attended visits from {no_shows:,} monthly No-Shows and"
                if (no_shows is not None and total_book is not None and total_book > 0)
                else " Closing this gap"
            )
            decisions.append(
                AiDecisionItem(
                    id="dec-attendance-paradox",
                    priority="immediate",
                    priority_label=f"High-Weight KPI ({att_w:.0f}% Weight)",
                    title="Audit Booking Qualification & Enforce Appointment Confirmation",
                    rationale=(
                        f"{paradox_note} Because Attendance carries {att_w:.0f}% weight, this gap costs "
                        f"-{pts_lost:.2f} pts on the {scope_label} overall score."
                    ),
                    expected_impact=(
                        f"What-If ROI:{vol_impact} adds up to +{pts_lost:.2f} pts to {scope_label} team score at target."
                    ),
                    target_label=f"{att_row.people_below_target} Agents Below Attendance Target in {scope_label}",
                    route_link=build_verified_deep_link(
                        "/insights",
                        month=res_month,
                        year=res_year,
                        function=resolved["function"],
                        team=resolved["team"],
                        kpi="Attendance",
                    ),
                    cta_label="Inspect Attendance Contributors →",
                )
            )

        # 3. Outbound Reachability or Inbound Abandon Rate Bottleneck
        if other_row and (other_row.achievement_percent or 100.0) < 90.0:
            oth_ach = float(other_row.achievement_percent or 0.0)
            oth_w = float(other_row.weight_percent or 10.0)
            oth_pts = round(((100.0 - oth_ach) / 100.0) * oth_w, 2)
            is_reach = "reachability" in other_row.kpi_label.casefold()
            decisions.append(
                AiDecisionItem(
                    id="dec-other-kpi",
                    priority="high",
                    priority_label="Operational SLA",
                    title=(
                        "Re-Slot Outbound Calling Windows & Audit Lead Freshness"
                        if is_reach
                        else "Re-Balance Peak-Hour Shift Adherence to Cut Abandon Rate"
                    ),
                    rationale=(
                        f"{other_row.kpi_label} is at {other_row.actual_display} vs {other_row.target_display} target "
                        f"({oth_ach:.1f}% achievement across {other_row.people_below_target} agents below target)."
                    ),
                    expected_impact=f"What-If ROI: Bringing {other_row.kpi_label} to target recovers +{oth_pts:.2f} pts on team score.",
                    target_label=f"{other_row.people_below_target} Agents in {scope_label}",
                    route_link=build_verified_deep_link(
                        "/planning",
                        month=res_month,
                        year=res_year,
                        team=resolved["team"],
                    ),
                    cta_label="Open Action Planning →",
                )
            )

        # 4. Inbound AHT Bottleneck
        if aht_row and (aht_row.achievement_percent or 100.0) < 90.0:
            aht_ach = float(aht_row.achievement_percent or 0.0)
            aht_w = float(aht_row.weight_percent or 5.0)
            aht_pts = round(((100.0 - aht_ach) / 100.0) * aht_w, 2)
            decisions.append(
                AiDecisionItem(
                    id="dec-aht-coaching",
                    priority="coaching",
                    priority_label="Call Control Coaching",
                    title=f"Run Focused AHT Wrap-Up Coaching for {aht_row.people_below_target} Agents",
                    rationale=(
                        f"Average Handle Time is {aht_row.actual_display} vs {aht_row.target_display} target "
                        f"({aht_ach:.1f}% ach). Quality Score remains high, indicating wrap-up/hold delays rather than script issues."
                    ),
                    expected_impact=(
                        f"What-If ROI: Trimming AHT to {aht_row.target_display} recovers +{aht_pts:.2f} pts and increases inbound queue capacity by ~15%."
                    ),
                    target_label=f"{aht_row.people_below_target} Agents Exceeding Target AHT",
                    route_link=build_verified_deep_link(
                        "/insights",
                        month=res_month,
                        year=res_year,
                        function=resolved["function"],
                        team=resolved["team"],
                        kpi="AHT",
                    ),
                    cta_label="View AHT Contributors →",
                )
            )

        return decisions[:3]
