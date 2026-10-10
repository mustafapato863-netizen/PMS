"""Pinned score movement carries a basis note without rewriting the score."""
import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REDIS_URL"] = ""
os.environ.pop("CI", None)

from models.schemas import EvaluationData, PerformanceRecord
from services.insights_service import InsightsService
from services.planning_service import PlanningService
from utils.report_scope import filter_records_by_scope, filter_records_by_team_levels


def _record(employee, team, month, score, target, *, version=None):
    kpi = {
        "kpi_key": "Attendance",
        "label": "Attendance",
        "direction": "higher_better",
        "unit": "%",
        "actual_value": 0.60,
        "target_value": target,
        "weight_applied": 0.70,
        "contribution": 0.2,
        "evaluation_pinned": True,
    }
    if version:
        kpi["version_id"] = version
    return PerformanceRecord(
        id=f"{employee}-{team}-{month}",
        employee_id=employee,
        employee_name=employee,
        team=team,
        month=month,
        year=2026,
        region="EGY",
        position="Agent",
        performance_level="Employee",
        status="Below",
        evaluation=EvaluationData(score=score, grade="C"),
        kpi_values=[kpi],
    )


def _service(records):
    service = InsightsService(None, PlanningService(None))

    def authorized(scope):
        scoped = filter_records_by_scope(records, scope)
        return filter_records_by_team_levels(scoped, scope), 0

    service._authorized_records = authorized
    return service


def _scope():
    return {
        "role": "Admin",
        "has_unrestricted_team_access": True,
        "legacy_unscoped": False,
        "accessible_teams": [],
        "accessible_team_levels": [],
    }


def _workspace(records, **filters):
    return _service(records).generate_workspace(_scope(), year=2026, month="August", **filters)


def test_target_change_adds_a_basis_note_without_changing_the_score_story():
    records = [
        _record("A", "Outbound", "July", 80, 0.55),
        _record("A", "Outbound", "August", 70, 0.65),
    ]
    workspace = _workspace(records)
    story = workspace.executive_story
    score_items = [item for item in workspace.priority_insights if item.insight_type == "performance"]

    assert story.current_score == 70.0
    assert story.score_change == -10.0
    assert story.basis_context.state == "changed"
    assert story.basis_context.raw_performance == "unchanged"
    assert "Scores can be affected by evaluation settings." in story.basis_context.message
    assert "caused" not in story.basis_context.message.casefold()
    assert score_items
    assert score_items[0].planning_context["source_insight_id"] == score_items[0].id
    assert "declined" in score_items[0].explanation or "moved" in score_items[0].explanation
    assert "evaluation settings" not in score_items[0].explanation.casefold()
    assert score_items[0].detail.basis_note
    assert "caused" not in score_items[0].detail.basis_note.casefold()
    july = next(point for point in workspace.overall_trend if point.period.month == "July")
    august = next(point for point in workspace.overall_trend if point.period.month == "August")
    assert july.basis_context.state == "unavailable"
    assert august.basis_context.state == "changed"
    assert august.score == story.current_score


def test_same_rules_with_a_different_version_keep_the_same_insight_identity():
    first = _workspace([
        _record("A", "Outbound", "July", 80, 0.65, version="july"),
        _record("A", "Outbound", "August", 70, 0.65, version="august"),
    ])
    second = _workspace([
        _record("A", "Outbound", "July", 80, 0.65, version="other-july"),
        _record("A", "Outbound", "August", 70, 0.65, version="other-august"),
    ])

    assert first.executive_story.basis_context.state == "unchanged"
    assert first.executive_story.basis_context.message is None
    assert first.executive_story.score_change == second.executive_story.score_change == -10.0
    assert [item.id for item in first.priority_insights] == [item.id for item in second.priority_insights]


def test_another_team_target_change_does_not_leak_into_the_filtered_story():
    records = [
        _record("A", "Outbound", "July", 80, 0.65),
        _record("A", "Outbound", "August", 70, 0.65),
        _record("B", "Inbound", "July", 80, 0.20),
        _record("B", "Inbound", "August", 70, 0.80),
    ]
    workspace = _workspace(records, team="Outbound")

    assert workspace.executive_story.basis_context.state == "unchanged"
    assert workspace.executive_story.basis_context.reasons == []
    assert "Inbound" not in (workspace.executive_story.basis_context.message or "")
