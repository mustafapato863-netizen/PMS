from __future__ import annotations

import functools
import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from config.loader import find_team_config_by_db_name, load_team_config
from models.ai_schemas import (
    AiBarItem,
    AiDecisionItem,
    AiEntityListItem,
    AiKpiTableRow,
    AiSpotlightMetadata,
    AiSpotlightMetricTile,
    AiTrendPoint,
    DeepLinkCta,
    SessionFilterContext,
    SourceCitationPill,
    StructuredVisualCard,
    TypedMetricEvidence,
)
from services.ai.catalog import canonical_team_region, get_ai_catalog, user_can_access_branch
from services.ai.domain_policies import (
    disambiguate_call_center_kpi_label,
    sanitize_untrusted_text,
)
from services.ai.read_only_guard import ReadOnlySessionGuard
from services.corrective_action_service import CorrectiveActionService
from services.database_record_source import DatabaseRecordSource
from services.insights_service import InsightsService
from services.planning_service import MONTH_ORDER, PlanningService
from utils.branch_scope import (
    BRANCH_KEYS,
    project_record_for_branch,
    record_matches_branch,
)
from utils.regions import first_region
from utils.report_scope import filter_records_by_scope, selection_team_keys

logger = logging.getLogger(__name__)


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
                self.session_state.region if self.session_state.region not in (None, "", "All") else None
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

    def __init__(self, ctx: ToolExecutionContext) -> None:
        self.ctx = ctx

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
        avg_score = (
            ws.executive_story.current_score
            if ws.executive_story and (not resolved["team"] or scoped_summaries)
            else None
        )

        cards: list[StructuredVisualCard] = []
        if scoped_summaries:
            bars: list[AiBarItem] = []
            sorted_teams = sorted(
                scoped_summaries,
                key=lambda t: (t.current_score if t.current_score is not None else 999.0),
            )
            for t in sorted_teams[:8]:
                t_disp = _display_team_name(t.team)
                score_val = min(100.0, round(float(t.current_score or 0.0), 1))
                delta = t.score_change
                gap_val = max(0.0, round(100.0 - score_val, 1))
                delta_str = (
                    f"{delta:+.1f}% vs prev · {t.total_employees} agents"
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
                    subtitle=f"Scope: {scope_label} ({branch_label}) — Ordered from lowest score to highest",
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
        if ws.team_summaries:
            worst_team_obj = min(
                ws.team_summaries,
                key=lambda t: (t.current_score if t.current_score is not None else 999.0),
            )
            w_team_disp = _display_team_name(worst_team_obj.team)
            w_score_capped = min(100.0, round(float(worst_team_obj.current_score or 0.0), 1))
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
                        f"{worst_team_obj.total_employees} evaluated agents). Primary driver: "
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

        digest = {
            "period": period_label,
            "scope": scope_label,
            "branch": branch_label,
            "average_score": avg_score,
            "score_change": ws.executive_story.score_change if ws.executive_story else None,
            "total_records": total_employees,
            "employees_below_target": impacted_employees,
            "primary_driver": ws.executive_story.primary_driver if ws.executive_story else None,
            "recommended_focus": ws.executive_story.recommended_focus if ws.executive_story else None,
            "worst_team": worst_team,
            "teams": [
                {
                    "team": _display_team_name(t.team),
                    "score": min(100.0, round(float(t.current_score or 0.0), 1)),
                    "change": t.score_change,
                    "impacted": t.impacted_employees,
                    "total": t.total_employees,
                    "main_cause": t.main_cause,
                }
                for t in scoped_summaries[:6]
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
        return ToolExecutionResult(
            tool_name="get_shared_region_scorecard",
            arguments={"team": team_name, "month": res_month, "year": res_year, "region": "All"},
            records_evaluated=len(period_records),
            digest=digest,
            visual_cards=cards,
            citations=citations,
            deep_links=[],
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

        branch_comparison_digest: list[dict[str, Any]] = []
        if is_comparing_branches:
            branches_to_compare = list(BRANCH_KEYS)
            if len(requested_branches) >= 2:
                ordered = list(requested_branches)
                for bk in BRANCH_KEYS:
                    if bk not in ordered:
                        ordered.append(bk)
                branches_to_compare = ordered
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
                        else:
                            vol_val = None
                            act_disp_val = "Data Missing or Unpublished"
                            tgt_disp_val = "—"
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
                }

        period_comparison_payload: dict[str, Any] | None = None
        if asks_period_comparison and ws.comparison and ws.comparison.previous and ws.comparison.current:
            to_sc = ws.executive_story.current_score if ws.executive_story else None
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
        avg_score_val = round(float(ws.executive_story.current_score), 1) if (ws.executive_story and ws.executive_story.current_score is not None) else None
        score_chg_val = round(float(ws.executive_story.score_change), 1) if (ws.executive_story and ws.executive_story.score_change is not None) else None
        digest = {
            "period": period_label,
            "scope": scope_label,
            "branch": branch_label,
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

        return ToolExecutionResult(
            tool_name="get_kpi_diagnosis_and_trends",
            arguments={**resolved, "compare_branch": compare_branch, "branches": requested_branches, "kpi": kpi},
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
        month: str | None = None,
        year: int | None = None,
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
            performance_level=resolved["performance_level"],
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
        cards: list[StructuredVisualCard] = []
        top_negative_rows: list[dict[str, Any]] = []
        pareto_summary: dict[str, Any] = {}

        if pca and pca.rows:
            neg_rows = [r for r in pca.rows if r.classification in ("negative", "affected")]
            if not neg_rows:
                neg_rows = list(pca.rows)
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
        if top_negative_rows:
            first_emp_id = top_negative_rows[0]["employee_id"]
            deep_links.append(
                DeepLinkCta(
                    label=f"Open {top_negative_rows[0]['employee_name']} Profile →",
                    route=build_verified_deep_link(f"/employee/{first_emp_id}", month=res_month, year=res_year),
                    icon_key="employee",
                )
            )

        digest = {
            "period": period_label,
            "scope": scope_label,
            "branch": branch_label,
            "kpi_analyzed": disambiguate_call_center_kpi_label(resolved["team"], pca.kpi_key, pca.kpi_label) if pca else kpi,
            "total_employees": pca.total_employees if pca else total_employees,
            "negative_contributors": pca.negative_contributors if pca else 0,
            "top_contributors": top_negative_rows,
            "pareto_summary": pareto_summary,
        }

        return ToolExecutionResult(
            tool_name="get_people_contribution_and_rankings",
            arguments={**resolved, "kpi": kpi},
            records_evaluated=pca.total_employees if pca else total_employees,
            digest=digest,
            visual_cards=cards,
            citations=citations,
            deep_links=deep_links,
            resolved_month=res_month,
            resolved_year=res_year,
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

    def _extract_record_kpi_snapshot(
        self,
        rec: Any,
        kpi_query: str | None,
        team_hint: str | None = None,
        position_hint: str | None = None,
    ) -> dict[str, Any] | None:
        if not kpi_query:
            return None
        q_norm = kpi_query.strip().casefold()
        r_team = str(getattr(rec, "team", "") or team_hint or "Inbound")
        r_pos = str(getattr(rec, "position", "") or position_hint or "")
        cat_def = get_ai_catalog().find_metric_definition(
            team="Support Positions" if r_team.casefold() == "call center" and r_pos else r_team,
            kpi_key_or_label=kpi_query,
            position=r_pos or None,
        )
        target_key = cat_def.kpi_key.casefold() if cat_def else None
        target_display = cat_def.display_name if cat_def else kpi_query.strip()

        raw_kpis = getattr(rec, "kpi_values", None) or []
        for kv in raw_kpis:
            k_key = str((kv.get("kpi_key") if isinstance(kv, dict) else getattr(kv, "kpi_key", "")) or "")
            k_lbl_raw = str((kv.get("label") if isinstance(kv, dict) else getattr(kv, "label", "")) or k_key)
            k_lbl = disambiguate_call_center_kpi_label(r_team, k_key, k_lbl_raw)
            matched = False
            if target_key and k_key.casefold() == target_key:
                matched = True
            elif q_norm in k_key.casefold() or q_norm in k_lbl_raw.casefold() or q_norm in k_lbl.casefold():
                matched = True
            if not matched:
                continue

            unit = str((kv.get("unit") if isinstance(kv, dict) else getattr(kv, "unit", "%")) or "%")
            act_v = float((kv.get("actual_value") if isinstance(kv, dict) else getattr(kv, "actual_value", 0.0)) or 0.0)
            tgt_v = float((kv.get("target_value") if isinstance(kv, dict) else getattr(kv, "target_value", 0.0)) or 0.0)
            ach_r = float((kv.get("achievement_ratio") if isinstance(kv, dict) else getattr(kv, "achievement_ratio", 0.0)) or 0.0)
            direction = str((kv.get("direction") if isinstance(kv, dict) else getattr(kv, "direction", "higher_better")) or "higher_better")

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
        month: str | None = None,
        year: int | None = None,
        kpi: str | None = None,
        employee_query: str | None = None,
        ranking_direction: str = "best",
        single_person: bool = True,
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

        # Filter to Employee-level records in the requested team/position/function
        target_team = resolved["team"]
        target_pos = resolved["position"]
        target_fn = (resolved["function"] or "").casefold()
        scoped_recs = []
        for rec in all_records:
            lvl = str(getattr(rec, "performance_level", None) or "Employee")
            if lvl != "Employee":
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
                digest={"period": period_label, "scope": target_team or "Call Center", "spotlight": None, "agent_spotlight": None},
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
        for r in team_period_recs:
            r_id = str(getattr(r, "employee_id", "") or "").strip()
            if r_id == emp_id_resolved:
                continue
            rk = _rank_key(r)
            if abs(rk[0] - selected_rank_key[0]) < 1e-4:
                r_nm = str(getattr(r, "employee_name", "") or r_id).strip()
                r_pos_val = str(getattr(r, "position", "") or "").strip()
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
        all_history_points: list[dict[str, Any]] = []
        missing_months: list[str] = []
        for r in emp_history_recs:
            ev_all = getattr(r, "evaluation", None)
            raw_sc_all = getattr(ev_all, "score", None) if ev_all is not None else None
            if raw_sc_all is None:
                raw_sc_all = getattr(r, "overall_score", None)
            m_all = str(getattr(r, "month", "") or "").strip()
            y_all = int(getattr(r, "year", 2026) or 2026)
            p_all = f"{m_all} {y_all}"
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
            for r in emp_history_recs
            if (getattr(getattr(r, "evaluation", None), "score", None) is not None or getattr(r, "overall_score", None) is not None)
        ][-max(1, min(months_window, 12)) :]

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
            f"{selected_kpi_snap['actual_display']} {ranking_metric_label} (Overall Score {curr_score:.1f}%)"
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
            direction = str((kv.get("direction") if isinstance(kv, dict) else getattr(kv, "direction", "higher_better")) or "higher_better")

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
                    f"{change_vs_prev:+.1f}% vs {prev_month_label}"
                    if change_vs_prev is not None
                    else f"{emp_team} · {period_label}"
                ),
                tone="good" if (change_vs_prev or 0) >= 0 else "critical",
            ),
            AiSpotlightMetricTile(
                label=f"{len(trend_points)}-Month Trajectory",
                value=f"{six_month_delta:+.1f}%" if six_month_delta is not None else f"{curr_score:.1f}%",
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
        if not single_person and not employee_query and len(team_period_recs) > 1:
            ordered = team_period_recs if ranking_direction != "worst" else list(reversed(team_period_recs))
            for idx, r in enumerate(ordered[:3], start=1):
                r_id = str(getattr(r, "employee_id", "") or "")
                r_nm = str(getattr(r, "employee_name", "") or r_id).title()
                r_sc = round(float(getattr(getattr(r, "evaluation", None), "score", 0.0) or 0.0), 2)
                r_gr = self._grade_for_score(r_sc)
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

        agent_spotlight_dict = {
            "entity_name": emp_display_name,
            "entity_id": emp_id_resolved,
            "team": emp_team,
            "position": emp_pos,
            "rank_label": rank_label,
            "rank": rank_idx,
            "total_in_team": total_in_team,
            "ranking_direction": ranking_direction,
            "ranking_metric_label": ranking_metric_label,
            "ranking_metric_display": ranking_metric_display,
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
                team=target_team or "Inbound",
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
        state: str | None = None,
    ) -> ToolExecutionResult:
        resolved = self.ctx.resolve_filters(team=team, function=function, month=month, year=year)
        ca_service = CorrectiveActionService(self.ctx.db)
        follow_up = ca_service.list_follow_up(
            self.ctx.scope,
            state=state,
            team=resolved["team"],
            month=resolved["month"],
        )
        actions = list(follow_up.get("actions") or [])
        if not resolved["team"] and (resolved["function"] or "").casefold() == "call center":
            actions = [
                a for a in actions if str(a.get("team") or "").casefold() in ("inbound", "outbound", "call center")
            ]

        items: list[AiEntityListItem] = []
        action_digest: list[dict[str, Any]] = []
        for act in actions[:8]:
            emp_name = act.get("employee_name") or act.get("team") or "Team Action"
            f_state = str(act.get("follow_up_state") or "open")
            sev = "critical" if f_state == "overdue" else ("warning" if f_state in ("due_soon", "upcoming") else "good")
            action_text = sanitize_untrusted_text(act.get("action_text") or act.get("plan_title") or "", 150)
            items.append(
                AiEntityListItem(
                    id=str(act.get("id") or emp_name),
                    title=f"{emp_name} · {act.get('action_type') or 'Action'}",
                    subtitle=f"{act.get('team', '')} · {action_text}",
                    badge_text=f_state.replace("_", " ").title(),
                    severity=sev,  # type: ignore[arg-type]
                    metric_value=str(act.get("status") or "Open"),
                    route_link=build_verified_deep_link("/corrective-actions", team=resolved["team"], month=resolved["month"]),
                )
            )
            action_digest.append(
                {
                    "employee_name": emp_name,
                    "team": act.get("team"),
                    "action_type": act.get("action_type"),
                    "status": act.get("status"),
                    "follow_up_state": f_state,
                    "action_text": action_text,
                }
            )

        cards: list[StructuredVisualCard] = []
        if items:
            cards.append(
                StructuredVisualCard(
                    card_type="entity_list",
                    title="Corrective Actions & Decisions Follow-Up",
                    subtitle=f"{len(actions)} active/tracked corrective actions in scope",
                    items=items,
                )
            )
        else:
            cards.append(
                StructuredVisualCard(
                    card_type="guardrail_notice",
                    title="No Corrective Actions Recorded for Active Filter",
                    subtitle="Read-only governance check",
                    notice_text="No open or historical corrective actions matched the current team/period filter.",
                )
            )

        citations = [
            SourceCitationPill(label=f"Scope · {resolved['team'] or resolved['function'] or 'Call Center'}", category="scope"),
            SourceCitationPill(label=f"Actions Tracked · {len(actions)}", category="metric"),
        ]
        deep_links = [
            DeepLinkCta(
                label="Open Corrective Actions →",
                route=build_verified_deep_link("/corrective-actions", team=resolved["team"], month=resolved["month"]),
                icon_key="actions",
            )
        ]

        return ToolExecutionResult(
            tool_name="get_corrective_actions_status",
            arguments=resolved,
            records_evaluated=len(actions),
            digest={"total_actions": len(actions), "summary": follow_up.get("summary"), "actions": action_digest},
            visual_cards=cards,
            citations=citations,
            deep_links=deep_links,
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
                deep_links=[
                    DeepLinkCta(label="Open Inbound Managerial BSC →", route="/team/inbound?performance_level=Managerial", icon_key="bsc")
                ],
                guardrail_triggered=True,
            )

        target_team = resolved["team"] or "Inbound"
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

            cfg = find_team_config_by_db_name(target_team) or load_team_config("inbound")
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
        total_bookings = 0.0
        total_attended = 0.0
        total_calls = 0.0

        # Scope-aware period publication: only set True if a record matches scope (team/function & period)
        has_period_records = False
        matching_branch_records = 0
        bookings_present_count = 0
        bookings_missing_count = 0
        attended_present_count = 0
        attended_missing_count = 0
        calls_present_count = 0

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
                for bk in BRANCH_KEYS:
                    vb = _extract_metric_val(b_obj, bk)
                    va = _extract_metric_val(a_obj, bk)
                    if vb is None and va is None:
                        continue
                    rec_has_branch_data = True
                    try:
                        if vb is None:
                            raise ValueError
                        total_bookings += float(vb)
                        bookings_present_count += 1
                    except (ValueError, TypeError):
                        bookings_missing_count += 1
                    try:
                        if va is None:
                            raise ValueError
                        total_attended += float(va)
                        attended_present_count += 1
                    except (ValueError, TypeError):
                        attended_missing_count += 1
                if not rec_has_branch_data:
                    bookings_missing_count += 1
                    attended_missing_count += 1

            # Calls metric presence
            calls = getattr(rec, "calls", None)
            if calls is not None:
                val_c = _extract_metric_val(calls, "total_handled") or _extract_metric_val(calls, "inbound")
                if val_c is not None:
                    try:
                        total_calls += float(val_c)
                        calls_present_count += 1
                    except (ValueError, TypeError):
                        pass

        booking_present = bookings_present_count > 0
        attended_present = attended_present_count > 0
        calls_present = calls_present_count > 0
        has_partial_evidence = (bookings_present_count > 0 and bookings_missing_count > 0)
        booking_complete = (bookings_present_count > 0 and bookings_missing_count == 0)

        return {
            "total_bookings": round(total_bookings, 1) if booking_present else None,
            "total_attended": round(total_attended, 1) if attended_present and attended_missing_count == 0 else None,
            "total_calls_handled": round(total_calls, 1) if calls_present else None,
            "booking_present": booking_present,
            "booking_complete": booking_complete,
            "has_partial_evidence": has_partial_evidence,
            "attended_present": attended_present,
            "attendance_complete": attended_present and attended_missing_count == 0,
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
                        team=resolved["team"] or "Inbound",
                        kpi="AHT",
                    ),
                    cta_label="View AHT Contributors →",
                )
            )

        return decisions[:3]
