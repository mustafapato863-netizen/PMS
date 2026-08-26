from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.report_center_schemas import (
    ReportCenterCapabilities,
    ReportCenterFilters,
    ReportCenterRecordsResponse,
    ReportCenterResponse,
)
from models.report_schemas import MONTHS, ReportConfiguration
from services.cache_invalidation_service import CacheInvalidationService
from services.corrective_action_service import CorrectiveActionService
from services.performance_dashboard_read_service import PerformanceDashboardReadService, parse_period, period_key
from services.permission_seed import PERMISSION_MATRIX
from services.report_service import ReportService
from utils.report_scope import user_can_access_team, user_can_access_team_level


class ReportsCenterService:
    """Role-aware orchestration for the preview-first Reports Center.

    The service deliberately composes the bounded performance read service,
    deterministic Insights service, existing report options, and corrective
    action service.  It owns the final redaction boundary so an aggregate role
    can never receive person-level data merely because a downstream service
    returned it.
    """

    _AGGREGATE_ROLES = {"Executive", "Viewer"}
    _PEOPLE_ROLES = {"Admin", "Manager"}

    def __init__(self, db: Session, scope: dict[str, Any]):
        self.db = db
        self.scope = scope
        self.role = str(scope.get("role") or "Viewer")
        self.capabilities = self._capabilities()
        self.data_scope = self._data_scope()
        self.performance = PerformanceDashboardReadService(db, self.data_scope)
        self.reports = ReportService(db)

    def _capabilities(self) -> ReportCenterCapabilities:
        permissions = set(PERMISSION_MATRIX.get(self.role, []))
        return ReportCenterCapabilities(
            role=self.role,
            can_export="export_data" in permissions,
            can_view_people=self.role in self._PEOPLE_ROLES,
            can_view_actions=self.role == "Admin" or "view_actions" in permissions,
            allowed_formats=["pdf", "pptx", "excel"] if "export_data" in permissions else [],
        )

    def _data_scope(self) -> dict[str, Any]:
        if self.role not in self._AGGREGATE_ROLES:
            return self.scope
        # Executive and Viewer are intentionally aggregate roles in the new
        # center.  The legacy scope helper treats Executive as self-only and
        # Viewer as a broad compatibility role; normalize both to an internal
        # all-authorized aggregate query, then redact before returning data.
        return {
            **self.scope,
            "role": "Admin",
            "is_general_manager": True,
            "is_self_only": False,
            "accessible_teams": list(self.scope.get("active_team_names") or self.scope.get("accessible_teams") or []),
            "accessible_team_levels": [],
        }

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            if value is None:
                return None
            number = float(value)
            return number if number == number else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _period_ref(value: str | None) -> dict[str, Any] | None:
        if not value:
            return None
        year, month = parse_period(value)
        return {"key": period_key(year, month), "year": year, "month": month}

    @staticmethod
    def _score(summary: dict[str, Any] | None) -> float | None:
        if not summary or not summary.get("total_records"):
            return None
        return ReportsCenterService._number(summary.get("average_score"))

    def _validate_filters(self, filters: ReportCenterFilters) -> None:
        if filters.period:
            self._period_ref(filters.period)
        if filters.comparison_period:
            self._period_ref(filters.comparison_period)
        if filters.period and filters.comparison_period and filters.period == filters.comparison_period:
            raise HTTPException(status_code=422, detail="comparison_period must differ from period")
        if filters.employee_id and not self.capabilities.can_view_people:
            raise HTTPException(status_code=403, detail="This role can only view aggregate reporting data")
        if filters.team:
            if self.role in self._AGGREGATE_ROLES:
                active_teams = {str(team).casefold() for team in self.scope.get("active_team_names") or []}
                if active_teams and filters.team.casefold() not in active_teams:
                    raise HTTPException(status_code=403, detail="The selected team is outside the authorized reporting scope")
            elif not user_can_access_team(self.scope, filters.team):
                raise HTTPException(status_code=403, detail="The selected team is outside the authorized reporting scope")
            if filters.performance_level and not user_can_access_team_level(
                self.scope,
                filters.team,
                filters.performance_level,
            ) and self.role not in self._AGGREGATE_ROLES:
                raise HTTPException(status_code=403, detail="The selected performance level is outside the authorized reporting scope")

    def _options(self) -> dict[str, Any]:
        options = dict(self.reports.options(self.data_scope))
        if not self.capabilities.can_view_people:
            options["employees"] = []
        options.update(self.capabilities.model_dump(mode="json", exclude={"role"}))
        options["role"] = self.role
        options["allowed_formats"] = list(self.capabilities.allowed_formats)
        return options

    def _latest_period(self, options: dict[str, Any]) -> str | None:
        periods = options.get("periods") or []
        return str(periods[0].get("key")) if periods and periods[0].get("key") else None

    def _workspace(self, filters: ReportCenterFilters, period: dict[str, Any]):
        # Imports are local to keep the router/dependency import graph acyclic.
        from api.dependencies import performance_repo, planning_service
        from services.insights_service import InsightsService

        return InsightsService(performance_repo, planning_service, db=self.db).generate_workspace(
            self.data_scope,
            month=period["month"],
            year=period["year"],
            region=filters.region,
            team=filters.team,
            performance_level=filters.performance_level,
            position=filters.position,
            employee_id=filters.employee_id,
            kpi=filters.kpi,
            status=filters.status,
        )

    def _team_comparison(
        self,
        current_summary: dict[str, Any],
        *,
        period: str,
        comparison_period: str | None,
        filters: ReportCenterFilters,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for team_row in current_summary.get("team_breakdown") or []:
            team = str(team_row.get("teamName") or "Unknown")
            current_result = self.performance.summary(
                period=period,
                team=team,
                performance_level=filters.performance_level,
                region=filters.region,
                position=filters.position,
                employee_id=filters.employee_id,
                grade=filters.grade,
                status=filters.status,
                kpi=filters.kpi,
                trend_months=2,
            )
            previous_result = (
                self.performance.summary(
                    period=comparison_period,
                    team=team,
                    performance_level=filters.performance_level,
                    region=filters.region,
                    position=filters.position,
                    employee_id=filters.employee_id,
                    grade=filters.grade,
                    status=filters.status,
                    kpi=filters.kpi,
                    trend_months=1,
                )
                if comparison_period
                else None
            )
            current = current_result.get("current") or {}
            previous = previous_result.get("current") if previous_result else None
            score = self._score(current)
            previous_score = self._score(previous)
            rows.append({
                "team": team,
                "score": score,
                "previous_score": previous_score,
                "movement": round(score - previous_score, 2) if score is not None and previous_score is not None else None,
                "target_gap": round(score - 100, 2) if score is not None else None,
                "affected_employees": int(current.get("at_risk_count", 0) or 0) + int(current.get("critical_count", 0) or 0),
                "population_size": int(current.get("total_records", 0) or 0),
                "on_track_count": int(current.get("on_track_count", 0) or 0),
                "at_risk_count": int(current.get("at_risk_count", 0) or 0),
                "critical_count": int(current.get("critical_count", 0) or 0),
            })
        return sorted(rows, key=lambda row: (row["score"] is None, -(row["score"] or 0), row["team"]))

    @staticmethod
    def _kpi_health(workspace) -> list[dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for insight in [*(workspace.team_analyses or []), *(workspace.priority_insights or [])]:
            if not insight.kpi_key or not insight.detail:
                continue
            current = ReportsCenterService._number(insight.detail.current_value)
            target = ReportsCenterService._number(insight.detail.target_value)
            key = str(insight.kpi_key)
            if key not in rows:
                rows[key] = {
                    "kpi": key,
                    "label": key,
                    "actual": current,
                    "target": target,
                    "gap": round(current - target, 2) if current is not None and target is not None else None,
                    "status": insight.severity,
                    "affected_employees": 0,
                    "teams": [],
                }
            row = rows[key]
            row["label"] = row["label"] if row["label"] != key else str(insight.title or key)
            row["affected_employees"] += len(insight.detail.affected_employees or [])
            if insight.team and insight.team not in row["teams"]:
                row["teams"].append(insight.team)
            if insight.severity == "critical" or (insight.severity == "risk" and row["status"] not in {"critical"}):
                row["status"] = insight.severity
        return sorted(rows.values(), key=lambda row: (row["status"] not in {"critical", "risk"}, row["gap"] is None, row["gap"] or 0))

    def _safe_insight(self, insight, *, viewer: bool = False) -> dict[str, Any]:
        item = insight.model_dump(mode="json")
        item["employee_id"] = None
        item["planning_context"] = {
            key: value for key, value in item.get("planning_context", {}).items()
            if key not in {"employee_id", "suggested_action"}
        }
        detail = item.get("detail") or {}
        detail["affected_employees"] = []
        detail["evidence"] = [evidence for evidence in detail.get("evidence", []) if evidence.get("label") not in {"Employee", "Employee ID"}]
        if viewer:
            return {
                key: item.get(key)
                for key in (
                    "id", "severity", "insight_type", "title", "scope", "impact_points",
                    "trend_label", "team", "performance_level", "position", "kpi_key", "status",
                )
            }
        item["detail"] = detail
        return item

    def _insights_payload(self, workspace) -> dict[str, Any]:
        aggregate_only = self.role in self._AGGREGATE_ROLES
        priority = [
            self._safe_insight(item, viewer=self.role == "Viewer")
            for item in workspace.priority_insights
            if not aggregate_only or item.insight_type != "employee_risk"
        ]
        team_analysis = [
            self._safe_insight(item, viewer=self.role == "Viewer")
            for item in workspace.team_analyses[:50]
            if not aggregate_only or item.insight_type != "employee_risk"
        ]
        recommendations = []
        if self.role != "Viewer" and workspace.executive_story:
            recommendations.append(workspace.executive_story.recommended_focus)
        if self.role != "Viewer":
            recommendations.extend(
                item["detail"]["recommended_focus"]
                for item in priority[:5]
                if item.get("detail", {}).get("recommended_focus")
            )
        return {
            "summary": workspace.summary.model_dump(mode="json"),
            "priority": priority,
            "team_analysis": team_analysis,
            "team_summaries": [item.model_dump(mode="json") for item in workspace.team_summaries],
            "role_summaries": [item.model_dump(mode="json") for item in workspace.role_summaries],
            "performance_drivers": [item.model_dump(mode="json") for item in workspace.performance_drivers],
            "executive_story": workspace.executive_story.model_dump(mode="json") if workspace.executive_story else None,
            "recommendations": list(dict.fromkeys(recommendations)),
            "data_quality": [
                self._safe_insight(item, viewer=self.role == "Viewer")
                for item in workspace.data_issues
            ],
        }

    def _filtered_action_items(
        self,
        filters: ReportCenterFilters,
        period: dict[str, Any] | None,
    ) -> list[dict[str, Any]] | None:
        """Serialize actions from the same filtered evidence as the center.

        The corrective-action service has a deliberately small legacy payload,
        so filtering only its serialized fields would silently lose region,
        position, level, and KPI boundaries.  Reuse the report service's
        normalized performance/action contract when this is the real service;
        test doubles and older integrations can still use the legacy fallback
        in ``_actions_payload``.
        """

        if not period:
            return None
        list_records = getattr(self.reports, "_performance_records", None)
        filter_actions = getattr(self.reports, "_presentation_actions", None)
        if not callable(list_records) or not callable(filter_actions):
            return None

        configuration = ReportConfiguration(
            report_type="team",
            report_name="Reports Center action scope",
            start_month=str(period["month"]),
            start_year=int(period["year"]),
            region=filters.region,
            team=filters.team,
            position=filters.position,
            performance_level=filters.performance_level,
            employee_id=filters.employee_id,
            grade=filters.grade,
            status=filters.status,
            kpi=filters.kpi,
        )
        records = list_records(configuration, self.data_scope)
        actions = filter_actions(configuration, self.data_scope, records)
        records_by_employee_period: dict[tuple[str, tuple[int, int]], list[Any]] = {}
        month_numbers = MONTHS
        for record in records:
            employee_id = str(getattr(record, "employee_id", "") or "")
            month_number = month_numbers.get(str(getattr(record, "month", "")))
            year = getattr(record, "year", None)
            if employee_id and month_number and year is not None:
                records_by_employee_period.setdefault((employee_id, (int(year), month_number)), []).append(record)

        result: list[dict[str, Any]] = []
        for action in actions:
            employee = getattr(action, "employee", None)
            team = getattr(action, "team", None)
            team_name = str(getattr(team, "display_name", None) or getattr(team, "name", None) or "Unknown")
            employee_id = str(getattr(employee, "employee_id", "") or "")
            month_number = month_numbers.get(str(getattr(action, "month", "")))
            evidence = records_by_employee_period.get(
                (employee_id, (int(action.year), month_number)),
                [],
            ) if month_number else []
            record = evidence[0] if evidence else None
            evaluation = getattr(record, "evaluation", None)
            owner = getattr(action, "owner", None)
            created_by = getattr(action, "created_by_user", None)
            result.append({
                "id": str(getattr(action, "id", "")),
                "employee_id": employee_id or None,
                "employee_name": getattr(employee, "name", None),
                "team": team_name,
                "region": getattr(employee, "region", None) or getattr(team, "region", None) or getattr(record, "region", None),
                "position": getattr(employee, "position_name", None) or getattr(record, "position", None),
                "performance_level": getattr(employee, "performance_level", None) or getattr(record, "performance_level", None),
                "month": getattr(action, "month", None),
                "year": getattr(action, "year", None),
                "score": getattr(evaluation, "score", None),
                "grade": getattr(evaluation, "grade", None),
                "root_cause": getattr(action, "root_cause_note", None) or "None",
                "suggested_action": getattr(action, "action_type", None),
                "manager_action": f"{getattr(action, 'action_type', 'Coaching')}: {getattr(action, 'action_text', '')}",
                "manager_notes": getattr(action, "root_cause_note", None) or "",
                "timestamp": (getattr(action, "created_at", None).isoformat() if getattr(action, "created_at", None) else None),
                "created_by_name": getattr(created_by, "username", None),
                "created_by_role": getattr(created_by, "role", None),
                "owner": getattr(owner, "username", None) or getattr(owner, "full_name", None),
                "due_date": getattr(action, "due_date", None).isoformat() if getattr(action, "due_date", None) else None,
                "priority": getattr(action, "priority", None),
                "linked_kpi_key": getattr(action, "linked_kpi_key", None),
                "status": getattr(action, "status", None),
            })
        return result

    def _actions_payload(
        self,
        period: dict[str, Any] | None,
        filters: ReportCenterFilters | None = None,
    ) -> dict[str, Any] | None:
        if not self.capabilities.can_view_actions:
            return None
        filters = filters or ReportCenterFilters()
        actions = self._filtered_action_items(filters, period)
        if actions is None:
            actions = (
                CorrectiveActionService(self.db).list_all()
                if self.role == "Admin"
                else CorrectiveActionService(self.db).list_scoped(self.scope)
            )
            if period:
                actions = [
                    action for action in actions
                    if str(action.get("year") or "") == str(period["year"])
                    and str(action.get("month") or "").casefold() == str(period["month"]).casefold()
                    and (not filters.team or str(action.get("team") or "").casefold() == filters.team.casefold())
                    and (not filters.region or ReportService._regions_match(action.get("region"), filters.region))
                    and (not filters.position or str(action.get("position") or "").casefold() == filters.position.casefold())
                    and (not filters.performance_level or str(action.get("performance_level") or "").casefold() == filters.performance_level.casefold())
                    and (not filters.employee_id or str(action.get("employee_id") or "") == filters.employee_id)
                    and (not filters.grade or str(action.get("grade") or "").casefold() == filters.grade.casefold())
                    and (not filters.status or str(action.get("status") or "").casefold() == filters.status.casefold())
                    and (not filters.kpi or str(action.get("linked_kpi_key") or "").casefold() == filters.kpi.casefold())
                ]
        by_status: dict[str, int] = defaultdict(int)
        by_team: dict[str, int] = defaultdict(int)
        for action in actions:
            by_status[str(action.get("status") or "Unknown")] += 1
            by_team[str(action.get("team") or "Unknown")] += 1
        return {
            "total": len(actions),
            "open": sum(count for status, count in by_status.items() if status.casefold() not in {"completed", "closed"}),
            "by_status": dict(sorted(by_status.items())),
            "by_team": dict(sorted(by_team.items())),
            "items": actions[:100],
        }

    def _base_filters(self, filters: ReportCenterFilters, period: str) -> dict[str, Any]:
        data = filters.model_dump(exclude_none=True)
        data["period"] = period
        data.pop("cursor", None)
        data.pop("page_size", None)
        data.pop("include_total", None)
        return data

    def center(self, filters: ReportCenterFilters) -> dict[str, Any]:
        self._validate_filters(filters)
        options = self._options()
        period = filters.period or self._latest_period(options)
        if not period:
            now = datetime.now(timezone.utc).isoformat()
            empty = ReportCenterResponse(
                role=self.role,
                filters=filters.as_query(),
                summary={"current_score": None, "previous_score": None, "movement": None, "target_gap": None, "population_size": 0, "on_track_count": 0, "at_risk_count": 0, "critical_count": 0, "data_quality_count": 0},
                options=options,
                capabilities=self.capabilities,
                as_of=now,
                data_version=CacheInvalidationService.get_data_version(),
            )
            return empty.model_dump(mode="json")

        period_ref = self._period_ref(period)
        current_result = self.performance.summary(
            period=period,
            team=filters.team,
            performance_level=filters.performance_level,
            region=filters.region,
            position=filters.position,
            employee_id=filters.employee_id,
            grade=filters.grade,
            status=filters.status,
            kpi=filters.kpi,
            trend_months=12,
        )
        comparison_period = filters.comparison_period or (current_result.get("previous_period") or {}).get("key")
        comparison_ref = self._period_ref(comparison_period) if comparison_period else None
        comparison_result = (
            self.performance.summary(
                period=comparison_period,
                team=filters.team,
                performance_level=filters.performance_level,
                region=filters.region,
                position=filters.position,
                employee_id=filters.employee_id,
                grade=filters.grade,
                status=filters.status,
                kpi=filters.kpi,
                trend_months=1,
            )
            if comparison_period
            else None
        )
        current = current_result.get("current") or {}
        previous = comparison_result.get("current") if comparison_result else None
        current_score = self._score(current)
        previous_score = self._score(previous)
        workspace = self._workspace(filters, period_ref)
        data = ReportCenterResponse(
            role=self.role,
            filters=self._base_filters(filters, period),
            period=period_ref,
            comparison_period=comparison_ref,
            summary={
                "current_score": current_score,
                "previous_score": previous_score,
                "movement": round(current_score - previous_score, 2) if current_score is not None and previous_score is not None else None,
                "target": 100.0,
                "target_gap": round(current_score - 100, 2) if current_score is not None else None,
                "population_size": int(current.get("total_records", 0) or 0),
                "on_track_count": int(current.get("on_track_count", 0) or 0),
                "at_risk_count": int(current.get("at_risk_count", 0) or 0),
                "critical_count": int(current.get("critical_count", 0) or 0),
                "data_quality_count": int(workspace.summary.data_issues or 0),
                "kpi_coverage_percent": workspace.summary.coverage_percent,
            },
            trend=[
                {
                    **point,
                    "actual": point.get("average_score"),
                    "target": 100.0,
                    "gap": round(float(point["average_score"]) - 100, 2) if point.get("average_score") is not None else None,
                }
                for point in current_result.get("trend") or []
            ],
            team_comparison=self._team_comparison(current_result, period=period, comparison_period=comparison_period, filters=filters),
            kpi_health=self._kpi_health(workspace),
            insights=self._insights_payload(workspace),
            corrective_actions=self._actions_payload(period_ref, filters),
            options=options,
            capabilities=self.capabilities,
            as_of=datetime.now(timezone.utc).isoformat(),
            data_version=int(current_result.get("data_version") or CacheInvalidationService.get_data_version()),
        )
        return data.model_dump(mode="json")

    def records(self, filters: ReportCenterFilters) -> dict[str, Any]:
        self._validate_filters(filters)
        options = self._options()
        period = filters.period or self._latest_period(options)
        if not period:
            return ReportCenterRecordsResponse(
                role=self.role,
                filters=filters.as_query(),
                items=[],
                page_size=filters.page_size,
                capabilities=self.capabilities,
                as_of=datetime.now(timezone.utc).isoformat(),
                data_version=CacheInvalidationService.get_data_version(),
            ).model_dump(mode="json")
        period_ref = self._period_ref(period)
        comparison_period = filters.comparison_period
        result = self.performance.records_page(
            period=period,
            team=filters.team,
            performance_level=filters.performance_level,
            region=filters.region,
            position=filters.position,
            employee_id=filters.employee_id,
            grade=filters.grade,
            status=filters.status,
            kpi=filters.kpi,
            cursor=filters.cursor,
            page_size=filters.page_size,
            include_total=filters.include_total,
        )
        items = result.get("items") or []
        if not self.capabilities.can_view_people:
            groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for item in items:
                groups[str(item.get("team") or "Unknown")].append(item)
            items = []
            for team, rows in sorted(groups.items()):
                scores = [self._number(row.get("score")) for row in rows]
                measured = [score for score in scores if score is not None]
                on_track = sum(score >= 100 for score in measured)
                at_risk = sum(70 <= score < 100 for score in measured)
                critical = sum(score < 70 for score in measured)
                average = sum(measured) / len(measured) if measured else None
                items.append({
                    "team": team,
                    "record_count": len(rows),
                    "average_score": round(average, 2) if average is not None else None,
                    "target_gap": round(average - 100, 2) if average is not None else None,
                    "on_track_count": on_track,
                    "at_risk_count": at_risk,
                    "critical_count": critical,
                })
        return ReportCenterRecordsResponse(
            role=self.role,
            period=period_ref,
            comparison_period=self._period_ref(comparison_period) if comparison_period else None,
            filters=self._base_filters(filters, period),
            items=items,
            page_size=filters.page_size,
            next_cursor=result.get("next_cursor"),
            has_more=bool(result.get("has_more")),
            total=result.get("total"),
            capabilities=self.capabilities,
            as_of=datetime.now(timezone.utc).isoformat(),
            data_version=int(result.get("data_version") or CacheInvalidationService.get_data_version()),
        ).model_dump(mode="json")
