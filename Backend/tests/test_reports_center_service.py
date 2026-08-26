from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from models.insight_schemas import InsightDetail, InsightFilterOptions, InsightItem, InsightSummary, InsightsWorkspace
from models.report_center_schemas import ReportCenterFilters
from services.reports_center_service import ReportsCenterService


def _insight(*, insight_type: str = "kpi_driver", employee_id: str | None = None) -> InsightItem:
    return InsightItem(
        id="insight-1",
        severity="risk",
        insight_type=insight_type,
        title="Quality is below target",
        explanation="The selected KPI needs attention.",
        scope="Inbound",
        trend_label="down",
        priority_reason="Largest gap",
        team="Inbound",
        employee_id=employee_id,
        kpi_key="quality",
        detail=InsightDetail(
            current_value=70,
            target_value=90,
            affected_employees=["EMP-1"],
            evidence=[{"label": "Employee", "value": "Alice"}, {"label": "Gap", "value": "20"}],
            recommended_focus="Review quality evidence.",
        ),
        planning_context={"employee_id": employee_id, "suggested_action": "Coach"},
    )


def _workspace() -> InsightsWorkspace:
    return InsightsWorkspace(
        summary=InsightSummary(data_issues=1, coverage_percent=75),
        priority_insights=[_insight(insight_type="employee_risk", employee_id="EMP-1"), _insight()],
        team_analyses=[_insight()],
        performance_drivers=[],
        risks=[],
        opportunities=[],
        data_issues=[],
        options=InsightFilterOptions(),
        comparison={"is_adjacent": True},
    )


class FakeReports:
    def options(self, _scope):
        return {
            "periods": [
                {"key": "2026-06", "year": 2026, "month": "June"},
                {"key": "2026-05", "year": 2026, "month": "May"},
            ],
            "teams": ["Inbound", "Outbound"],
            "regions": ["EGY"],
            "performance_levels": ["Employee"],
            "positions": ["Agent"],
            "employees": [{"id": "EMP-1", "name": "Alice", "team": "Inbound"}],
            "grades": ["A", "B"],
            "statuses": ["Meets"],
        }


class FakePerformance:
    def summary(self, *, period, team=None, **_filters):
        if team:
            score = 80 if team == "Inbound" else 95
            total = 2 if team == "Inbound" else 1
            return {
                "current": {
                    "total_records": total,
                    "average_score": score,
                    "on_track_count": 1 if score >= 95 else 0,
                    "at_risk_count": 1 if score < 95 else 0,
                    "critical_count": 0,
                },
                "trend": [],
            }
        return {
            "current": {
                "total_records": 3,
                "average_score": 85,
                "on_track_count": 1,
                "at_risk_count": 2,
                "critical_count": 0,
            },
            "previous_period": {"key": "2026-05", "year": 2026, "month": "May"},
            "trend": [{"key": "2026-06", "label": "June 2026", "average_score": 85, "total_records": 3}],
            "team_breakdown": [{"teamName": "Inbound"}, {"teamName": "Outbound"}],
            "data_version": 4,
        }

    def records_page(self, **kwargs):
        assert kwargs["page_size"] == 1
        return {
            "items": [
                {"id": "row-1", "employee_id": "EMP-1", "employee_name": "Alice", "team": "Inbound", "score": 80},
                {"id": "row-2", "employee_id": "EMP-2", "employee_name": "Bob", "team": "Inbound", "score": 90},
            ],
            "next_cursor": "after" if kwargs["cursor"] == "next" else None,
            "has_more": kwargs["cursor"] == "next",
            "total": 2,
            "data_version": 4,
        }


def _service(role: str) -> ReportsCenterService:
    scope = {
        "role": role,
        "user_id": "user-1",
        "employee_id": "EMP-1",
        "active_team_names": ["Inbound", "Outbound"],
        "accessible_teams": ["Inbound"] if role == "Manager" else [],
        "accessible_team_levels": [("Inbound", "Employee")],
        "is_general_manager": False,
        "is_self_only": False,
        "legacy_unscoped": False,
    }
    service = ReportsCenterService(None, scope)
    service.reports = FakeReports()
    service.performance = FakePerformance()
    service._workspace = lambda *_args, **_kwargs: _workspace()
    return service


def test_viewer_center_redacts_person_insights_and_people_options():
    service = _service("Viewer")
    result = service.center(ReportCenterFilters(period="2026-06"))

    assert result["capabilities"]["can_export"] is False
    assert result["capabilities"]["can_view_people"] is False
    assert result["options"]["employees"] == []
    assert all(item.get("employee_id") is None for item in result["insights"]["priority"])
    assert all("detail" not in item for item in result["insights"]["priority"])
    assert "Alice" not in str(result)
    assert result["summary"]["population_size"] == 3


def test_all_level_center_filter_is_normalized_to_aggregate_scope():
    filters = ReportCenterFilters(period="2026-06", performance_level="All")

    assert filters.performance_level is None


def test_viewer_records_are_team_aggregates_and_cursor_is_forwarded():
    service = _service("Viewer")
    result = service.records(ReportCenterFilters(period="2026-06", cursor="next", page_size=1))

    assert result["next_cursor"] == "after"
    assert result["items"] == [{
        "team": "Inbound",
        "record_count": 2,
        "average_score": 85.0,
        "target_gap": -15.0,
        "on_track_count": 0,
        "at_risk_count": 2,
        "critical_count": 0,
    }]
    assert "employee_name" not in str(result)


def test_admin_can_view_actions_and_people_in_center_capabilities():
    service = _service("Admin")

    assert service.capabilities.can_view_people is True
    assert service.capabilities.can_view_actions is True
    assert service.capabilities.can_export is True


def test_aggregate_roles_cannot_select_employee_and_manager_keeps_people_rows():
    with pytest.raises(HTTPException) as error:
        _service("Executive").center(ReportCenterFilters(period="2026-06", employee_id="EMP-1"))
    assert error.value.status_code == 403

    manager = _service("Manager")
    result = manager.records(ReportCenterFilters(period="2026-06", page_size=1))
    assert result["items"][0]["employee_name"] == "Alice"
    assert result["capabilities"]["can_view_people"] is True
