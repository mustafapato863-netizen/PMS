from __future__ import annotations

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
)
from services.ai.domain_policies import (
    disambiguate_call_center_kpi_label,
    sanitize_untrusted_text,
)
from services.corrective_action_service import CorrectiveActionService
from services.database_record_source import DatabaseRecordSource
from services.insights_service import InsightsService
from services.planning_service import MONTH_ORDER, PlanningService
from utils.branch_scope import (
    BRANCH_KEYS,
    project_record_for_branch,
    record_matches_branch,
)
from utils.report_scope import filter_records_by_scope

logger = logging.getLogger(__name__)


def build_verified_deep_link(
    base_path: str,
    *,
    month: str | None = None,
    year: int | None = None,
    function: str | None = None,
    team: str | None = None,
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
        self.source = DatabaseRecordSource(db)
        self.planning_service = PlanningService(self.source, db=db)
        self.insights_service = InsightsService(self.source, self.planning_service, db=db)

    def resolve_filters(
        self,
        *,
        team: str | None = None,
        function: str | None = None,
        branch: str | None = None,
        performance_level: str | None = None,
        month: str | None = None,
        year: int | None = None,
    ) -> dict[str, Any]:
        eff_team = team if team not in (None, "", "All") else (
            self.session_state.team if self.session_state.team not in (None, "", "All") else None
        )
        eff_fn = function if function not in (None, "", "All") else (
            self.session_state.function if self.session_state.function not in (None, "", "All") else "Call Center"
        )
        if eff_team and eff_team.casefold() not in ("inbound", "outbound", "call center"):
            if eff_fn and eff_fn.casefold() == "call center":
                eff_fn = None

        eff_branch = branch if branch not in (None, "", "all", "All") else (
            self.session_state.branch if self.session_state.branch not in (None, "", "all", "All") else None
        )
        if eff_branch:
            eff_branch = eff_branch.strip().casefold()
            if eff_branch not in BRANCH_KEYS:
                eff_branch = None

        allowed_branches = self.scope.get("allowed_branches")
        if isinstance(allowed_branches, (list, set, tuple)) and len(allowed_branches) == 1:
            eff_branch = next(iter(allowed_branches)).strip().casefold()

        eff_level = performance_level if performance_level not in (None, "", "All") else (
            self.session_state.performance_level
            if self.session_state.performance_level not in (None, "", "All")
            else None
        )

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
            records = filter_records_by_scope(self.source.get_all(), self.scope)
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

    def execute_executive_and_priority_insights(
        self,
        *,
        team: str | None = None,
        function: str | None = None,
        branch: str | None = None,
        performance_level: str | None = None,
        month: str | None = None,
        year: int | None = None,
    ) -> ToolExecutionResult:
        resolved = self.ctx.resolve_filters(
            team=team,
            function=function,
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
            performance_level=resolved["performance_level"],
            branch=resolved["branch"],
        )

        res_month = ws.comparison.current.month if ws.comparison and ws.comparison.current else resolved["month"]
        res_year = ws.comparison.current.year if ws.comparison and ws.comparison.current else resolved["year"]
        period_label = f"{res_month} {res_year}" if res_month and res_year else "Latest Period"
        scope_label = resolved["team"] or resolved["function"] or "Call Center"
        branch_label = resolved["branch"].capitalize() if resolved["branch"] else "All Branches"

        total_employees = sum(int(t.total_employees or 0) for t in (ws.team_summaries or []))
        impacted_employees = sum(int(t.impacted_employees or 0) for t in (ws.team_summaries or []))
        avg_score = ws.executive_story.current_score if ws.executive_story else None

        cards: list[StructuredVisualCard] = []
        if ws.team_summaries:
            bars: list[AiBarItem] = []
            sorted_teams = sorted(
                ws.team_summaries,
                key=lambda t: (t.current_score if t.current_score is not None else 999.0),
            )
            for t in sorted_teams[:8]:
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
                        label=t.team,
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
                items.append(
                    AiEntityListItem(
                        id=ins.id,
                        title=ins.title,
                        subtitle=sanitize_untrusted_text(focus_text, 180),
                        badge_text=ins.team or scope_label,
                        severity=sev_map.get(str(ins.severity).casefold(), "warning"),  # type: ignore[arg-type]
                        metric_value=f"{ins.impact_points:+.1f} pts" if ins.impact_points is not None else None,
                        route_link=build_verified_deep_link(
                            "/insights",
                            month=res_month,
                            year=res_year,
                            function=resolved["function"],
                            team=ins.team or resolved["team"],
                            branch=resolved["branch"],
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
                    branch=resolved["branch"],
                    performance_level=resolved["performance_level"],
                ),
                icon_key="insights",
            )
        ]
        if resolved["team"]:
            team_slug = resolved["team"].strip().lower().replace(" ", "-")
            deep_links.append(
                DeepLinkCta(
                    label=f"Open {resolved['team']} Dashboard →",
                    route=build_verified_deep_link(
                        f"/team/{team_slug}",
                        month=res_month,
                        year=res_year,
                        branch=resolved["branch"],
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
            w_score_capped = min(100.0, round(float(worst_team_obj.current_score or 0.0), 1))
            w_gap = max(0.0, round(100.0 - w_score_capped, 1))
            worst_team = {
                "team": worst_team_obj.team,
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
                    title=f"Prioritize Root-Cause Intervention in {worst_team_obj.team} ({w_score_capped:.1f}%)",
                    rationale=(
                        f"{worst_team_obj.team} shows the largest gap to 100% (-{w_gap:.1f} pts across "
                        f"{worst_team_obj.total_employees} evaluated agents). Primary driver: "
                        f"{worst_team_obj.main_cause or 'High-weight KPI deficit'}."
                    ),
                    expected_impact=f"Closing 50% of the {worst_team_obj.team} KPI gap adds +{round(w_gap * 0.5, 1):.1f} pts to the team average.",
                    target_label=f"{worst_team_obj.team} Team ({worst_team_obj.total_employees} agents)",
                    route_link=build_verified_deep_link(
                        "/insights",
                        month=res_month,
                        year=res_year,
                        function=resolved["function"],
                        team=worst_team_obj.team,
                        branch=resolved["branch"],
                    ),
                    cta_label=f"Diagnose {worst_team_obj.team} →",
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
                            team=worst_team_obj.team,
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
                    "team": t.team,
                    "score": min(100.0, round(float(t.current_score or 0.0), 1)),
                    "change": t.score_change,
                    "impacted": t.impacted_employees,
                    "total": t.total_employees,
                    "main_cause": t.main_cause,
                }
                for t in ws.team_summaries[:6]
            ],
        }

        return ToolExecutionResult(
            tool_name="get_executive_and_priority_insights",
            arguments=resolved,
            records_evaluated=max(total_employees, len(ws.priority_insights or [])),
            digest=digest,
            visual_cards=cards,
            citations=citations,
            deep_links=deep_links,
            resolved_month=res_month,
            resolved_year=res_year,
            basis_warning=basis_warn,
        )

    def execute_kpi_diagnosis_and_trends(
        self,
        *,
        team: str | None = None,
        function: str | None = None,
        branch: str | None = None,
        compare_branch: str | None = None,
        asks_branch_comparison: bool = False,
        performance_level: str | None = None,
        kpi: str | None = None,
        month: str | None = None,
        year: int | None = None,
    ) -> ToolExecutionResult:
        # When comparing branches (e.g., Dubai vs Sharjah or all branches), keep the main KPI diagnosis
        # across All Branches unless the session filter explicitly locked a single branch without comparison.
        is_comparing_branches = bool(compare_branch or asks_branch_comparison)
        kpi_table_branch = None if is_comparing_branches else branch
        resolved = self.ctx.resolve_filters(
            team=team,
            function=function,
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
            performance_level=resolved["performance_level"],
            branch=resolved["branch"],
        )

        res_month = ws.comparison.current.month if ws.comparison and ws.comparison.current else resolved["month"]
        res_year = ws.comparison.current.year if ws.comparison and ws.comparison.current else resolved["year"]
        period_label = f"{res_month} {res_year}" if res_month and res_year else "Latest Period"
        scope_label = resolved["team"] or resolved["function"] or "Call Center"
        branch_label = resolved["branch"].capitalize() if resolved["branch"] else "All Branches"
        total_employees = sum(int(t.total_employees or 0) for t in (ws.team_summaries or []))

        cards: list[StructuredVisualCard] = []

        branch_comparison_digest: list[dict[str, Any]] = []
        if is_comparing_branches:
            branches_to_compare = list(BRANCH_KEYS)
            if branch and compare_branch and branch.casefold() != compare_branch.casefold():
                # Put the two requested branches first, followed by the remaining UAE branches for full context
                b_first = branch.strip().casefold()
                b_second = compare_branch.strip().casefold()
                ordered = [b for b in (b_first, b_second) if b in BRANCH_KEYS]
                for bk in BRANCH_KEYS:
                    if bk not in ordered:
                        ordered.append(bk)
                branches_to_compare = ordered

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
                raw_s = float((ws_b.executive_story.current_score if ws_b.executive_story else 0.0) or 0.0)
                capped_s = min(100.0, round(raw_s, 1))
                b_vols = self._compute_operational_volumes(
                    month=res_month,
                    year=res_year,
                    team=resolved["team"],
                    function=resolved["function"],
                    branch=bk,
                )
                b_book = int(b_vols.get("total_bookings") or 0)
                b_att = int(b_vols.get("total_attended") or 0)
                b_noshows = max(0, b_book - b_att)
                b_att_pct = round((b_att / b_book) * 100.0, 1) if b_book > 0 else 0.0
                sec_lbl = (
                    f"Attended {b_att_pct:.1f}% ({b_att:,}/{b_book:,}) · {b_noshows:,} No-Shows"
                    if b_book > 0
                    else f"Score {capped_s:.1f}%"
                )
                sev = "critical" if capped_s < 75 or (b_book > 0 and b_att_pct < 60) else (
                    "warning" if capped_s < 90 or (b_book > 0 and b_att_pct < 70) else "good"
                )
                bars.append(
                    AiBarItem(
                        label=f"{scope_label} · {b_name}",
                        value=capped_s,
                        display_value=f"{capped_s:.1f}%",
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
                    }
                )

            title_prefix = (
                f"UAE Branch Comparison: {branch.capitalize()} vs {compare_branch.capitalize()} + All Branches"
                if (branch and compare_branch)
                else f"UAE 4-Branch Performance & Conversion Matrix · {scope_label}"
            )
            cards.append(
                StructuredVisualCard(
                    card_type="horizontal_bar",
                    title=f"{title_prefix} ({period_label})",
                    subtitle="Scores capped at 100% · Shows actual patient Attended / Bookings conversion & No-Show volume per branch",
                    bars=bars,
                )
            )

        kpi_rows: list[AiKpiTableRow] = []
        kpi_bars: list[AiBarItem] = []
        raw_diag = list(ws.kpi_diagnosis or [])

        for row in raw_diag:
            row_team = resolved["team"] or (str(row.teams[0]) if getattr(row, "teams", None) else scope_label)
            clean_label = disambiguate_call_center_kpi_label(row_team, row.key, row.label)
            unit = row.unit or "%"
            actual_val = row.actual
            target_val = row.target
            if unit == "%" and actual_val is not None and actual_val <= 1.5 and (target_val is None or target_val <= 1.5):
                act_str = f"{actual_val * 100:.1f}%"
                tgt_str = f"{(target_val or 0.0) * 100:.1f}%" if target_val is not None else "—"
            elif unit == "%":
                act_str = f"{actual_val:.1f}%" if actual_val is not None else "—"
                tgt_str = f"{target_val:.1f}%" if target_val is not None else "—"
            else:
                act_str = f"{actual_val:.2f} {unit}".strip() if actual_val is not None else "—"
                tgt_str = f"{target_val:.2f} {unit}".strip() if target_val is not None else "—"

            ach_pct = min(100.0, round(float(row.achievement_percent or 0.0), 1)) if row.achievement_percent is not None else 0.0
            weight_pct = round(float((row.weight or 0.0) * 100 if (row.weight or 0.0) <= 1.0 else (row.weight or 0.0)), 1)
            status_val = "critical" if ach_pct < 75 else ("warning" if ach_pct < 92 else "good")

            kpi_rows.append(
                AiKpiTableRow(
                    kpi_key=row.key,
                    kpi_label=clean_label,
                    weight_percent=weight_pct,
                    actual_display=act_str,
                    target_display=tgt_str,
                    achievement_percent=ach_pct,
                    direction=row.direction or "higher_better",
                    people_below_target=int(row.people_below_target or 0),
                    status=status_val,  # type: ignore[arg-type]
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

        if kpi_rows:
            cards.append(
                StructuredVisualCard(
                    card_type="kpi_table",
                    title=f"KPI Diagnosis & Target Gap · {scope_label}",
                    subtitle=f"{period_label} · {branch_label} (Achievement capped at 100%)",
                    kpi_rows=kpi_rows,
                )
            )
        if kpi_bars and not branch_comparison_digest:
            cards.append(
                StructuredVisualCard(
                    card_type="horizontal_bar",
                    title=f"KPI Achievement Breakdown · {scope_label}",
                    subtitle="Weighted KPI achievement against target",
                    bars=kpi_bars[:6],
                )
            )

        volume_summary = self._compute_operational_volumes(
            month=res_month,
            year=res_year,
            team=resolved["team"],
            function=resolved["function"],
            branch=resolved["branch"],
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
        if volume_summary.get("total_bookings"):
            citations.append(
                SourceCitationPill(
                    label=f"Bookings · {int(volume_summary['total_bookings']):,} | Attended · {int(volume_summary['total_attended']):,}",
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
                    branch=resolved["branch"],
                    kpi=kpi,
                ),
                icon_key="insights",
            )
        ]

        lowest_kpi = min(kpi_rows, key=lambda r: (r.achievement_percent or 0.0)) if kpi_rows else None
        digest = {
            "period": period_label,
            "scope": scope_label,
            "branch": branch_label,
            "branch_comparison": branch_comparison_digest,
            "operational_volumes": volume_summary,
            "lowest_kpi": lowest_kpi.model_dump() if lowest_kpi else None,
            "kpis": [r.model_dump() for r in kpi_rows[:8]],
            "decisions": [d.model_dump() for d in kpi_decisions],
        }

        return ToolExecutionResult(
            tool_name="get_kpi_diagnosis_and_trends",
            arguments={**resolved, "compare_branch": compare_branch, "kpi": kpi},
            records_evaluated=max(total_employees, len(kpi_rows)),
            digest=digest,
            visual_cards=cards,
            citations=citations,
            deep_links=deep_links,
            resolved_month=res_month,
            resolved_year=res_year,
        )

    def execute_people_contribution_and_rankings(
        self,
        *,
        team: str | None = None,
        function: str | None = None,
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
            branch=branch,
            performance_level=performance_level,
            month=month,
            year=year,
        )
        ws = self.ctx.insights_service.generate_workspace(
            self.ctx.scope,
            sections="summary,team_summaries,people_contribution_analysis,comparison",
            month=resolved["month"],
            year=resolved["year"],
            region=resolved["region"],
            team=resolved["team"],
            function=resolved["function"],
            performance_level=resolved["performance_level"],
            kpi=kpi,
            branch=resolved["branch"],
        )

        res_month = ws.comparison.current.month if ws.comparison and ws.comparison.current else resolved["month"]
        res_year = ws.comparison.current.year if ws.comparison and ws.comparison.current else resolved["year"]
        period_label = f"{res_month} {res_year}" if res_month and res_year else "Latest Period"
        scope_label = resolved["team"] or resolved["function"] or "Call Center"
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

    def execute_agent_spotlight_and_trend(
        self,
        *,
        team: str | None = None,
        function: str | None = None,
        branch: str | None = None,
        month: str | None = None,
        year: int | None = None,
        employee_query: str | None = None,
        ranking_direction: str = "best",
        single_person: bool = True,
        months_window: int = 6,
    ) -> ToolExecutionResult:
        resolved = self.ctx.resolve_filters(
            team=team,
            function=function,
            branch=branch,
            month=month,
            year=year,
        )
        all_records = filter_records_by_scope(self.ctx.source.get_all(), self.ctx.scope)

        # Filter to Employee-level records in the requested team/function
        target_team = resolved["team"]
        target_fn = (resolved["function"] or "Call Center").casefold()
        scoped_recs = []
        for rec in all_records:
            lvl = str(getattr(rec, "performance_level", None) or "Employee")
            if lvl != "Employee":
                continue
            r_team = str(getattr(rec, "team", "") or "")
            if target_team and r_team.casefold() != target_team.casefold():
                continue
            elif not target_team and target_fn == "call center" and r_team.casefold() not in ("inbound", "outbound"):
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
        if not period_recs and scoped_recs:
            period_recs = list(scoped_recs)

        period_recs.sort(
            key=lambda r: float(getattr(getattr(r, "evaluation", None), "score", 0.0) or 0.0),
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
            if not selected_rec:
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
                arguments={**resolved, "employee_query": employee_query, "ranking_direction": ranking_direction},
                records_evaluated=0,
                digest={"period": period_label, "scope": target_team or "Call Center", "spotlight": None},
                visual_cards=[],
                citations=[SourceCitationPill(label=f"Period · {period_label}", category="period")],
                deep_links=[],
                resolved_month=res_month,
                resolved_year=res_year,
            )

        emp_id_resolved = str(getattr(selected_rec, "employee_id", "") or "").strip()
        raw_name = str(getattr(selected_rec, "employee_name", "") or emp_id_resolved).strip()
        emp_display_name = raw_name.title() if raw_name == raw_name.lower() else raw_name
        emp_team = str(getattr(selected_rec, "team", "") or target_team or "Call Center").strip()

        # Compute exact rank within that agent's team in the current period
        team_period_recs = [
            r
            for r in period_recs
            if str(getattr(r, "team", "")).casefold() == emp_team.casefold()
        ]
        team_period_recs.sort(
            key=lambda r: float(getattr(getattr(r, "evaluation", None), "score", 0.0) or 0.0),
            reverse=True,
        )
        rank_idx = next(
            (i + 1 for i, r in enumerate(team_period_recs) if str(getattr(r, "employee_id", "")) == emp_id_resolved),
            1,
        )
        total_in_team = max(len(team_period_recs), 1)
        rank_label = f"Rank #{rank_idx} of {total_in_team} in {emp_team}"

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
        window_records = emp_history_recs[-max(1, min(months_window, 12)) :]

        trend_points: list[AiTrendPoint] = []
        history_digest: list[dict[str, Any]] = []
        for r in window_records:
            ev = getattr(r, "evaluation", None)
            sc = min(100.0, round(float(getattr(ev, "score", 0.0) or 0.0), 1))
            gr = str(getattr(ev, "grade", "") or self._grade_for_score(sc))
            m_str = str(getattr(r, "month", "") or "").strip()
            y_int = int(getattr(r, "year", 2026) or 2026)
            p_lbl = f"{m_str[:3]} {y_int}"
            trend_points.append(
                AiTrendPoint(
                    month=m_str,
                    year=y_int,
                    period_label=p_lbl,
                    score=sc,
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
        curr_score = min(100.0, round(float(getattr(curr_ev, "score", 0.0) or 0.0), 1))
        curr_grade = self._grade_for_score(curr_score)

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
                r_sc = min(100.0, round(float(getattr(getattr(r, "evaluation", None), "score", 0.0) or 0.0), 1))
                r_gr = self._grade_for_score(r_sc)
                extra_items.append(
                    AiEntityListItem(
                        id=r_id,
                        title=f"#{idx} · {r_nm} ({r_id})",
                        subtitle=f"{emp_team} · {period_label}",
                        badge_text=f"Grade {r_gr} · {r_sc:.1f}%",
                        severity="good" if r_sc >= 90 else ("warning" if r_sc >= 80 else "critical"),
                        metric_value=f"{r_sc:.1f}%",
                        route_link=build_verified_deep_link(f"/employee/{r_id}", month=res_month, year=res_year, branch=resolved["branch"]),
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
                f"{emp_display_name} ranks #{rank_idx} of {total_in_team} in {emp_team} ({period_label})."
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

        citations = [
            SourceCitationPill(label=f"Period · {period_label}", category="period"),
            SourceCitationPill(label=f"Agent · {emp_display_name}", category="scope"),
            SourceCitationPill(label=f"Team · {emp_team} ({rank_label})", category="metric"),
        ]
        deep_links = [
            DeepLinkCta(
                label=f"Open {emp_display_name} Profile →",
                route=build_verified_deep_link(
                    f"/employee/{emp_id_resolved}",
                    month=res_month,
                    year=res_year,
                    branch=resolved["branch"],
                ),
                icon_key="employee",
            ),
            DeepLinkCta(
                label=f"Open {emp_team} Team Deep Dive →",
                route=build_verified_deep_link(
                    f"/team/{emp_team.lower()}",
                    month=res_month,
                    year=res_year,
                    branch=resolved["branch"],
                ),
                icon_key="team",
            ),
        ]

        digest = {
            "period": period_label,
            "scope": emp_team,
            "branch": branch_label,
            "employee_id": emp_id_resolved,
            "employee_name": emp_display_name,
            "team": emp_team,
            "history": history_digest,
            "spotlight": {
                "entity_name": emp_display_name,
                "entity_id": emp_id_resolved,
                "team": emp_team,
                "rank_label": rank_label,
                "rank": rank_idx,
                "total_in_team": total_in_team,
                "ranking_direction": ranking_direction,
                "score": curr_score,
                "grade": curr_grade,
                "change_vs_prev": change_vs_prev,
                "previous_month_label": prev_month_label,
                "six_month_delta": six_month_delta,
                "months_tracked": len(trend_points),
                "first_month_label": first_month_label,
            },
        }

        return ToolExecutionResult(
            tool_name="get_agent_spotlight_and_trend",
            arguments={
                "team": emp_team,
                "branch": resolved["branch"],
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

    def execute_team_trend_spotlight(
        self,
        *,
        team: str | None = None,
        function: str | None = None,
        branch: str | None = None,
        month: str | None = None,
        year: int | None = None,
        months_window: int = 6,
    ) -> ToolExecutionResult:
        resolved = self.ctx.resolve_filters(
            team=team,
            function=function,
            branch=branch,
            month=month,
            year=year,
        )
        all_records = filter_records_by_scope(self.ctx.source.get_all(), self.ctx.scope)
        target_team = resolved["team"]
        target_fn = (resolved["function"] or "Call Center").casefold()

        by_period: dict[tuple[int, int, str], list[float]] = {}
        for rec in all_records:
            if str(getattr(rec, "performance_level", None) or "Employee") != "Employee":
                continue
            r_team = str(getattr(rec, "team", "") or "")
            if target_team and r_team.casefold() != target_team.casefold():
                continue
            elif not target_team and target_fn == "call center" and r_team.casefold() not in ("inbound", "outbound"):
                continue
            if resolved["branch"]:
                if not record_matches_branch(rec, resolved["branch"]):
                    continue
                rec = project_record_for_branch(rec, resolved["branch"])
            y_val = int(getattr(rec, "year", 0) or 0)
            m_str = str(getattr(rec, "month", "") or "").strip()
            m_ord = MONTH_ORDER.get(m_str, 0)
            sc = float(getattr(getattr(rec, "evaluation", None), "score", 0.0) or 0.0)
            if y_val and m_ord and sc > 0:
                by_period.setdefault((y_val, m_ord, m_str), []).append(sc)

        sorted_periods = sorted(by_period.keys())[-max(1, min(months_window, 12)) :]
        trend_points: list[AiTrendPoint] = []
        for y_val, _, m_str in sorted_periods:
            scores = by_period[(y_val, MONTH_ORDER.get(m_str, 0), m_str)]
            avg_sc = min(100.0, round(sum(scores) / len(scores), 1))
            trend_points.append(
                AiTrendPoint(
                    month=m_str,
                    year=y_val,
                    period_label=f"{m_str[:3]} {y_val}",
                    score=avg_sc,
                    target=100.0,
                    grade=self._grade_for_score(avg_sc),
                )
            )

        scope_label = target_team or resolved["function"] or "Call Center"
        branch_label = resolved["branch"].capitalize() if resolved["branch"] else "All Branches"
        latest_pt = trend_points[-1] if trend_points else AiTrendPoint(month="September", year=2026, period_label="Sep 2026", score=90.0, target=100.0, grade="B")
        curr_score = latest_pt.score
        curr_grade = self._grade_for_score(curr_score)
        prev_pt = trend_points[-2] if len(trend_points) >= 2 else None
        change_vs_prev = round(curr_score - prev_pt.score, 1) if prev_pt else None
        six_month_delta = round(curr_score - trend_points[0].score, 1) if len(trend_points) >= 2 else None
        gap_val = round(curr_score - 100.0, 1)

        tiles = [
            AiSpotlightMetricTile(
                label="Current",
                value=f"{curr_score:.1f}%",
                sublabel=f"Grade {curr_grade} · {latest_pt.month} {latest_pt.year}",
                tone="good" if curr_score >= 90 else ("warning" if curr_score >= 80 else "critical"),
            ),
            AiSpotlightMetricTile(
                label="Target",
                value="100.0%",
                sublabel="Official PMS Benchmark",
                tone="neutral",
            ),
            AiSpotlightMetricTile(
                label="Gap",
                value=f"{gap_val:+.1f}%",
                sublabel=f"{change_vs_prev:+.1f}% vs {prev_pt.month}" if prev_pt and change_vs_prev is not None else "vs 100% target",
                tone="warning" if gap_val < 0 else "good",
            ),
        ]

        spotlight_meta = AiSpotlightMetadata(
            kicker=f"6-MONTH SCORE TREND · {scope_label.upper()}",
            entity_name=f"{scope_label} Performance Trajectory",
            entity_id=None,
            team=scope_label,
            rank_label=f"{len(trend_points)} Months Tracked",
            score=curr_score,
            grade=curr_grade,  # type: ignore[arg-type]
            change_vs_prev=change_vs_prev,
            previous_month_label=prev_pt.month if prev_pt else "Prior Month",
            six_month_delta=six_month_delta,
            target=100.0,
            headline_note=f"{scope_label} moved from {trend_points[0].month} ({trend_points[0].score:.1f}%) to {latest_pt.month} ({curr_score:.1f}%)." if trend_points else None,
            tiles=tiles,
            kpi_chips=[],
            trend_points=trend_points,
        )

        card = StructuredVisualCard(
            card_type="trend_spotlight",
            title=f"{scope_label} · 6-Month Score Trend",
            subtitle=f"{latest_pt.month} {latest_pt.year} · {branch_label}",
            spotlight=spotlight_meta,
        )

        return ToolExecutionResult(
            tool_name="get_team_trend_spotlight",
            arguments=resolved,
            records_evaluated=sum(len(v) for v in by_period.values()),
            digest={
                "period": f"{latest_pt.month} {latest_pt.year}",
                "scope": scope_label,
                "branch": branch_label,
                "spotlight": {
                    "entity_name": scope_label,
                    "entity_id": None,
                    "team": scope_label,
                    "rank_label": f"{len(trend_points)} Months Tracked",
                    "ranking_direction": "team_trend",
                    "score": curr_score,
                    "grade": curr_grade,
                    "change_vs_prev": change_vs_prev,
                    "previous_month_label": prev_pt.month if prev_pt else "Prior Month",
                    "six_month_delta": six_month_delta,
                    "months_tracked": len(trend_points),
                    "first_month_label": trend_points[0].month if trend_points else latest_pt.month,
                },
            },
            visual_cards=[card],
            citations=[
                SourceCitationPill(label=f"Period · {latest_pt.month} {latest_pt.year}", category="period"),
                SourceCitationPill(label=f"Scope · {scope_label}", category="scope"),
                SourceCitationPill(label=f"Trajectory · {len(trend_points)} Months", category="metric"),
            ],
            deep_links=[
                DeepLinkCta(
                    label="Open Monthly Presentation →",
                    route="/monthly-presentation",
                    icon_key="insights",
                )
            ],
            resolved_month=latest_pt.month,
            resolved_year=latest_pt.year,
        )

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
        scope_label = resolved["team"] or resolved["function"] or "Call Center"
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

    def execute_management_balanced_scorecard(
        self,
        *,
        team: str | None = None,
        performance_level: str | None = None,
        month: str | None = None,
        year: int | None = None,
    ) -> ToolExecutionResult:
        resolved = self.ctx.resolve_filters(
            team=team,
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
        cfg = find_team_config_by_db_name(target_team) or load_team_config("inbound")
        lvl_cfg = (cfg.get("performance_levels") or {}).get(lvl) or {}
        kpis_cfg = lvl_cfg.get("kpis") or []

        bars: list[AiBarItem] = []
        bsc_digest: list[dict[str, Any]] = []
        for k in kpis_cfg:
            w_pct = round(float(k.get("weight", 0.0)) * 100, 1)
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
                title=f"{target_team} · {lvl} Balanced Scorecard Structure",
                subtitle="Four-perspective strategic governance scorecard (Financial, Customer, Internal Process, Learning & Growth)",
                bars=bars,
            )
        ]
        citations = [
            SourceCitationPill(label=f"Team · {target_team}", category="scope"),
            SourceCitationPill(label=f"Level · {lvl} BSC", category="policy"),
        ]
        deep_links = [
            DeepLinkCta(
                label=f"Open {target_team} {lvl} Scorecard →",
                route=build_verified_deep_link(f"/team/{target_team.lower()}", performance_level=lvl),
                icon_key="bsc",
            )
        ]

        return ToolExecutionResult(
            tool_name="get_management_balanced_scorecard",
            arguments={**resolved, "team": target_team, "performance_level": lvl},
            records_evaluated=len(bsc_digest),
            digest={"team": target_team, "level": lvl, "bsc_kpis": bsc_digest},
            visual_cards=cards,
            citations=citations,
            deep_links=deep_links,
        )

    def _compute_operational_volumes(
        self,
        *,
        month: str | None,
        year: int | None,
        team: str | None,
        function: str | None,
        branch: str | None,
    ) -> dict[str, float]:
        records = filter_records_by_scope(self.ctx.source.get_all(), self.ctx.scope)
        total_bookings = 0.0
        total_attended = 0.0
        total_calls = 0.0

        for rec in records:
            r_month = str(getattr(rec, "month", "") or "").strip()
            r_year = int(getattr(rec, "year", 0) or 0)
            if month and r_month.casefold() != month.casefold():
                continue
            if year and r_year != int(year):
                continue
            emp = getattr(rec, "employee", None)
            r_team = str(getattr(emp, "team", "") or getattr(rec, "team", "") or "").strip()
            if team and r_team.casefold() != team.casefold():
                continue
            if not team and (function or "").casefold() == "call center":
                if r_team.casefold() not in ("inbound", "outbound", "call center"):
                    continue
            if branch and not record_matches_branch(rec, branch):
                continue

            geo = getattr(rec, "geo", None)
            if geo:
                b_obj = getattr(geo, "bookings", None)
                a_obj = getattr(geo, "attended", None)
                if branch and branch in BRANCH_KEYS:
                    total_bookings += float(getattr(b_obj, branch, 0.0) or 0.0) if b_obj else 0.0
                    total_attended += float(getattr(a_obj, branch, 0.0) or 0.0) if a_obj else 0.0
                else:
                    if b_obj:
                        for bk in BRANCH_KEYS:
                            total_bookings += float(getattr(b_obj, bk, 0.0) or 0.0)
                    if a_obj:
                        for bk in BRANCH_KEYS:
                            total_attended += float(getattr(a_obj, bk, 0.0) or 0.0)

            calls = getattr(rec, "calls", None)
            if calls:
                total_calls += float(getattr(calls, "total_handled", 0.0) or getattr(calls, "inbound", 0.0) or 0.0)

        return {
            "total_bookings": round(total_bookings, 1),
            "total_attended": round(total_attended, 1),
            "total_calls_handled": round(total_calls, 1),
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

        total_book = int(volume_summary.get("total_bookings") or 0)
        total_att = int(volume_summary.get("total_attended") or 0)
        no_shows = max(0, total_book - total_att)
        plus5_patients = max(1, int(round(total_book * 0.05))) if total_book > 0 else 0

        # 1. Branch-Specific Conversion Decision (if branch comparison active)
        if len(branch_comparison_digest) >= 2:
            with_vol = [b for b in branch_comparison_digest if int(b.get("bookings") or 0) > 0]
            if len(with_vol) >= 2:
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
                if total_book > 0
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
