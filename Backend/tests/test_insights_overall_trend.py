"""overall_trend: six-month overall score trend for the Insights workspace.

The last point must always equal ``executive_story.current_score`` because both
come from the same filtered, access-checked record set and averaging rule.
"""
from datetime import date

import pytest

import services.insights_service as insights_service_module
from models.schemas import EvaluationData, PerformanceRecord
from services.insights_service import InsightAccessError, InsightsService
from services.planning_service import PlanningService
from utils.report_scope import filter_records_by_scope, filter_records_by_team_levels


MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


class StubRepository:
    def __init__(self, records):
        self.records = records

    def get_all(self):
        return self.records


def _record(
    employee_id: str,
    team: str,
    score: float,
    *,
    month: str = "June",
    year: int = 2026,
    region: str = "EGY",
    level: str = "Employee",
) -> PerformanceRecord:
    record = PerformanceRecord(
        id=f"{employee_id}_{year}_{month}",
        employee_id=employee_id,
        employee_name=employee_id,
        team=team,
        month=month,
        year=year,
        region=region,
        position="Agent",
        performance_level=level,
        status="Below",
        evaluation=EvaluationData(score=score, grade="C"),
        kpi_values=[{
            "kpi_key": "Attendance",
            "label": "Attendance",
            "direction": "higher_better",
            "unit": "%",
            "actual_value": .9,
            "target_value": .95,
            "weight_applied": .25,
            "contribution": .2,
        }],
    )
    return record


def _admin_scope(role: str = "Admin") -> dict:
    return {
        "role": role,
        "has_unrestricted_team_access": True,
        "legacy_unscoped": False,
        "accessible_teams": [],
        "accessible_team_levels": [],
    }


def _manager_scope(*teams: str, levels: list[tuple[str, str]] | None = None) -> dict:
    return _admin_scope("Manager") | {
        "has_unrestricted_team_access": False,
        "accessible_teams": list(teams),
        "accessible_team_levels": levels or [],
    }


def _service(records):
    """Service whose authorized records go through the real scope filters."""
    repository = StubRepository(records)
    service = InsightsService(repository, PlanningService(repository))

    def authorized(scope):
        scoped = filter_records_by_scope(records, scope)
        return filter_records_by_team_levels(scoped, scope), 0

    service._authorized_records = authorized
    return service


def _freeze_today(monkeypatch, year: int = 2026, month: int = 10, day: int = 6) -> None:
    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(year, month, day)

    monkeypatch.setattr(insights_service_module, "date", FakeDate)


def _scores(workspace) -> list[float | None]:
    return [point.score for point in workspace.overall_trend]


def _assert_last_point_matches_story(workspace) -> None:
    assert len(workspace.overall_trend) == 6
    last = workspace.overall_trend[-1]
    assert workspace.executive_story is not None
    assert last.score == workspace.executive_story.current_score
    assert last.period == workspace.comparison.current


def _mixed_records() -> list[PerformanceRecord]:
    return [
        _record("I1", "Inbound", 80, month="May", region="EGY", level="Employee"),
        _record("I1", "Inbound", 70, month="June", region="EGY", level="Employee"),
        _record("I2", "Inbound", 90, month="June", region="EGY", level="Managerial"),
        _record("O1", "Outbound", 60, month="June", region="UAE", level="Employee"),
        _record("C1", "Coding", 50, month="April", region="UAE", level="Employee"),
        _record("C1", "Coding", 40, month="June", region="UAE", level="Employee"),
        _record("M1", "Marketing", 100, month="June", region="EGY", level="Corporate"),
    ]


def test_last_point_equals_executive_story_current_score_and_current_period():
    workspace = _service(_mixed_records()).generate_workspace(_admin_scope(), month="June", year=2026)

    _assert_last_point_matches_story(workspace)
    assert workspace.executive_story.current_score == 72.0
    last = workspace.overall_trend[-1]
    assert last.period.month == "June" and last.period.year == 2026
    assert last.measured_records == 5
    assert last.target == 100.0


def test_default_period_trend_ends_at_the_resolved_current_period(monkeypatch):
    _freeze_today(monkeypatch)
    records = _mixed_records() + [_record("I1", "Inbound", 10, month="October")]

    workspace = _service(records).generate_workspace(_admin_scope())

    # October 2026 is the in-progress month, so the workspace resolves June.
    assert workspace.comparison.current.month == "June"
    _assert_last_point_matches_story(workspace)
    assert [point.period.month for point in workspace.overall_trend] == [
        "January", "February", "March", "April", "May", "June"
    ]


def test_months_without_data_are_none_with_zero_measured_records():
    workspace = _service(_mixed_records()).generate_workspace(_admin_scope(), month="June", year=2026)

    assert len(workspace.overall_trend) == 6
    assert _scores(workspace) == [None, None, None, 50.0, 80.0, 72.0]
    assert [point.measured_records for point in workspace.overall_trend] == [0, 0, 0, 1, 1, 5]
    assert all(point.target == 100.0 for point in workspace.overall_trend)


def test_selected_month_with_no_data_still_returns_six_points():
    workspace = _service(_mixed_records()).generate_workspace(_admin_scope(), month="August", year=2026)

    assert len(workspace.overall_trend) == 6
    assert workspace.overall_trend[-1].period.month == "August"
    assert workspace.overall_trend[-1].score is None
    assert workspace.overall_trend[-1].measured_records == 0
    assert workspace.executive_story.current_score is None
    assert _scores(workspace) == [None, 50.0, 80.0, 72.0, None, None]


def test_unscored_records_are_excluded_like_current_score():
    # Management BSC records are plain dicts and may carry no overall score yet.
    unscored = {
        "id": "X1_2026_June", "employee_id": "X1", "employee_name": "X1", "team": "Inbound",
        "month": "June", "year": 2026, "region": "EGY", "position": "Agent",
        "performance_level": "Employee", "evaluation": {"score": None}, "kpi_values": [],
    }
    records = _mixed_records() + [unscored]

    workspace = _service(records).generate_workspace(_admin_scope(), month="June", year=2026)

    _assert_last_point_matches_story(workspace)
    # The unscored record is in scope (counted as a team member) but not measured.
    inbound = next(summary for summary in workspace.team_summaries if summary.team == "Inbound")
    assert inbound.total_employees == 3
    assert workspace.overall_trend[-1].score == 72.0
    assert workspace.overall_trend[-1].measured_records == 5


@pytest.mark.parametrize(
    ("filters", "expected_scores", "expected_last_count"),
    [
        ({"region": "EGY"}, [None, None, None, None, 80.0, 86.7], 3),
        ({"region": "UAE"}, [None, None, None, 50.0, None, 50.0], 2),
        ({"team": "Inbound"}, [None, None, None, None, 80.0, 80.0], 2),
        ({"team": "Call Center"}, [None, None, None, None, 80.0, 73.3], 3),
        ({"function": "RCM"}, [None, None, None, 50.0, None, 40.0], 1),
        ({"function": "Call Center"}, [None, None, None, None, 80.0, 73.3], 3),
        ({"performance_level": "Employee"}, [None, None, None, 50.0, 80.0, 56.7], 3),
        ({"performance_level": "Managerial"}, [None, None, None, None, None, 90.0], 1),
        ({"team": "Inbound", "performance_level": "Employee"}, [None, None, None, None, 80.0, 70.0], 1),
    ],
)
def test_trend_respects_region_function_team_and_level_filters(filters, expected_scores, expected_last_count):
    service = _service(_mixed_records())

    workspace = service.generate_workspace(_admin_scope(), month="June", year=2026, **filters)

    _assert_last_point_matches_story(workspace)
    assert _scores(workspace) == expected_scores
    assert workspace.overall_trend[-1].measured_records == expected_last_count


def test_manager_trend_is_limited_to_accessible_teams():
    service = _service(_mixed_records())

    workspace = service.generate_workspace(_manager_scope("Coding"), month="June", year=2026)

    _assert_last_point_matches_story(workspace)
    assert _scores(workspace) == [None, None, None, 50.0, None, 40.0]
    assert [point.measured_records for point in workspace.overall_trend] == [0, 0, 0, 1, 0, 1]


def test_manager_trend_is_limited_to_accessible_team_levels():
    service = _service(_mixed_records())
    manager = _manager_scope("Inbound", levels=[("Inbound", "Managerial")])

    workspace = service.generate_workspace(manager, month="June", year=2026)

    _assert_last_point_matches_story(workspace)
    # The Employee-level Inbound rows (May 80, June 70) are outside the manager's levels.
    assert _scores(workspace) == [None, None, None, None, None, 90.0]


def test_manager_cannot_widen_trend_with_an_unassigned_team():
    service = _service(_mixed_records())

    with pytest.raises(InsightAccessError):
        service.generate_workspace(_manager_scope("Coding"), month="June", year=2026, team="Inbound")


@pytest.mark.parametrize("role", ["General Manager", "Admin"])
def test_gm_and_admin_trend_covers_every_team(role):
    service = _service(_mixed_records())

    workspace = service.generate_workspace(_admin_scope(role), month="June", year=2026)

    _assert_last_point_matches_story(workspace)
    assert _scores(workspace) == [None, None, None, 50.0, 80.0, 72.0]


def test_trend_is_oldest_first_and_crosses_the_year_boundary():
    records = [
        _record("I1", "Inbound", 55, month="August", year=2025),
        _record("I1", "Inbound", 60, month="September", year=2025),
        _record("I1", "Inbound", 65, month="November", year=2025),
        _record("I1", "Inbound", 70, month="December", year=2025),
        _record("I1", "Inbound", 75, month="January", year=2026),
        _record("I1", "Inbound", 99, month="February", year=2026),
    ]

    workspace = _service(records).generate_workspace(_admin_scope(), month="January", year=2026)

    _assert_last_point_matches_story(workspace)
    periods = [(point.period.year, point.period.month) for point in workspace.overall_trend]
    assert periods == [
        (2025, "August"), (2025, "September"), (2025, "October"),
        (2025, "November"), (2025, "December"), (2026, "January"),
    ]
    assert _scores(workspace) == [55.0, 60.0, None, 65.0, 70.0, 75.0]
    keys = [point.period.key for point in workspace.overall_trend]
    assert keys == sorted(keys)


def test_trend_point_schema_defaults_and_workspace_backward_compatibility():
    from models.insight_schemas import (
        InsightComparison,
        InsightFilterOptions,
        InsightOverallTrendPoint,
        InsightPeriod,
        InsightSummary,
        InsightsWorkspace,
    )

    point = InsightOverallTrendPoint(period=InsightPeriod(year=2026, month="June", key="2026-06"), score=None)
    assert point.target == 100.0
    assert point.measured_records == 0
    workspace = InsightsWorkspace(
        summary=InsightSummary(),
        priority_insights=[],
        performance_drivers=[],
        risks=[],
        opportunities=[],
        data_issues=[],
        options=InsightFilterOptions(),
        comparison=InsightComparison(),
    )
    assert workspace.overall_trend == []
    assert "overall_trend" in workspace.model_dump()
