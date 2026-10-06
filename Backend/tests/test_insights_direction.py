"""KPI direction must drive every Insights gap, change, driver and status.

Lower-is-better KPIs (Rejection Rate, Initial Rejection %) are good when they
fall and bad when they rise; being under the target (maximum allowed) is good.
"""
from __future__ import annotations

import pytest

from models.schemas import EvaluationData, PerformanceRecord
from services.insights_service import (
    InsightsService,
    _configured_kpi_values,
    _directional_fields,
    _resolve_kpi_direction,
    _target_achievement,
)
from services.planning_service import PlanningService


LOWER = "initial_rejection_rate"
HIGHER = "submission_within_due_date"
MONTHS = ["January", "February", "March", "April", "May", "June"]


class _Repo:
    def __init__(self, records):
        self.records = records

    def get_all(self):
        return self.records


def _service(records):
    repository = _Repo(records)
    service = InsightsService(repository, PlanningService(repository))
    service._authorized_records = lambda _scope: (records, 0)
    return service


def _scope():
    return {
        "role": "Admin",
        "has_unrestricted_team_access": True,
        "legacy_unscoped": False,
        "accessible_teams": [],
        "accessible_team_levels": [],
    }


def _kpi(key, label, actual, target, weight, direction, *, unit="%"):
    if direction == "lower_better":
        ratio = 1.0 if actual <= 0 else min(target / actual, 1.0)
    else:
        ratio = min(actual / target, 1.0)
    row = {
        "kpi_key": key,
        "label": label,
        "unit": unit,
        "actual_value": actual,
        "target_value": target,
        "weight_applied": weight,
        "contribution": ratio * weight,
    }
    if direction is not None:
        row["direction"] = direction
    return row


def _record(month, kpis, *, employee_id="E1", team="Submission", position="Submission Officer", score=80.0):
    return PerformanceRecord(
        id=f"{employee_id}_{team}_2026_{month}",
        employee_id=employee_id,
        employee_name=employee_id,
        team=team,
        month=month,
        year=2026,
        region="UAE",
        position=position,
        performance_level="Employee",
        status="Below",
        evaluation=EvaluationData(score=score, grade="C"),
        kpi_values=kpis,
    )


def _submission(month, rejection, on_time, *, employee_id="E1", persisted_direction="lower_better"):
    return _record(month, [
        _kpi(LOWER, "Initial Rejection Rate", rejection, .05, .6, persisted_direction),
        _kpi(HIGHER, "Submission Within Due Date", on_time, .9, .4, "higher_better"),
    ], employee_id=employee_id)


def _analysis(workspace, key):
    return next(item for item in workspace.team_analyses if item.kpi_key == key)


def _driver(workspace, key):
    item = _analysis(workspace, key)
    return next(driver for driver in workspace.performance_drivers if driver.insight_id == item.id)


# --- achievement formula -----------------------------------------------------

def test_lower_better_achievement_is_target_over_actual_capped_like_higher_better():
    # Lower is better: target / actual, capped to 0..1 (same cap as actual / target).
    assert _target_achievement(.08, .05, "lower_better") == pytest.approx(.625)
    assert _target_achievement(.04, .05, "lower_better") == 1.0
    assert _target_achievement(0, .05, "lower_better") == 1.0
    # Higher is better control.
    assert _target_achievement(.81, .9, "higher_better") == pytest.approx(.9)
    assert _target_achievement(.95, .9, "higher_better") == 1.0
    fields = _directional_fields(.08, .04, .05, "lower_better")
    assert fields["gap_value"] == pytest.approx(-.03)
    assert fields["achievement_percent"] == 62.5
    assert fields["raw_change"] == pytest.approx(.04)
    assert fields["change_value"] == pytest.approx(-.04)
    assert fields["trend_status"] == "declining"
    assert fields["target_status"] == "missed"


# --- gap, achievement, change, driver, recommended action ---------------------

def test_lower_better_increase_is_negative_gap_change_and_driver_with_higher_control():
    workspace = _service([
        _submission("May", .04, .85),
        _submission("June", .08, .95),
    ]).generate_workspace(_scope(), month="June", year=2026)

    rejection = _analysis(workspace, LOWER)
    assert rejection.detail.direction == "lower_better"
    assert rejection.detail.gap_value == pytest.approx(-.03)
    assert rejection.detail.achievement_percent == 62.5
    assert rejection.detail.raw_change == pytest.approx(.04)
    assert rejection.detail.change_value == pytest.approx(-.04)
    assert rejection.detail.trend_status == "declining"
    assert rejection.detail.target_status == "missed"
    assert rejection.impact_points == pytest.approx(-22.5)
    assert rejection.severity == "critical"
    assert rejection.insight_type == "kpi_driver"
    assert rejection.title == "Initial Rejection Rate contributed to the performance gap"
    assert "declined by 4.0%" in rejection.explanation
    assert rejection.detail.recommended_focus.startswith("Reduce Initial Rejection Rate")
    assert any(e.label == "Target achievement" and e.value == "62.5%" for e in rejection.detail.evidence)
    driver = _driver(workspace, LOWER)
    assert driver.direction == "negative"
    assert driver.impact_points == pytest.approx(-22.5)
    assert driver.kpi_direction == "lower_better"

    # Higher-is-better control in the same workspace.
    on_time = _analysis(workspace, HIGHER)
    assert on_time.detail.direction == "higher_better"
    assert on_time.detail.gap_value == pytest.approx(.05)
    assert on_time.detail.achievement_percent == 100.0
    assert on_time.detail.change_value == pytest.approx(.10)
    assert on_time.detail.raw_change == pytest.approx(.10)
    assert on_time.detail.trend_status == "improving"
    assert on_time.detail.target_status == "met"
    assert _driver(workspace, HIGHER).direction == "positive"
    assert _driver(workspace, HIGHER).impact_points > 0
    assert workspace.summary.negative_weighted_drivers == 1
    assert workspace.summary.positive_weighted_drivers == 1


def test_lower_better_decrease_is_positive_driver():
    workspace = _service([
        _submission("May", .08, .9),
        _submission("June", .04, .9),
    ]).generate_workspace(_scope(), month="June", year=2026)

    rejection = _analysis(workspace, LOWER)
    assert rejection.detail.gap_value == pytest.approx(.01)
    assert rejection.detail.achievement_percent == 100.0
    assert rejection.detail.change_value == pytest.approx(.04)
    assert rejection.detail.raw_change == pytest.approx(-.04)
    assert rejection.detail.trend_status == "improving"
    assert rejection.detail.target_status == "met"
    assert rejection.impact_points == pytest.approx(22.5)
    assert rejection.title == "Initial Rejection Rate is a positive score driver"
    assert _driver(workspace, LOWER).direction == "positive"


def test_rising_lower_better_kpi_within_target_is_a_watch_item_not_an_opportunity():
    workspace = _service([
        _submission("May", .02, .99),
        _submission("June", .04, .95),
    ]).generate_workspace(_scope(), month="June", year=2026)

    rejection = _analysis(workspace, LOWER)
    # Under the maximum allowed is good (positive gap) but the rise is a decline.
    assert rejection.detail.gap_value == pytest.approx(.01)
    assert rejection.detail.target_status == "met"
    assert rejection.detail.trend_status == "declining"
    assert rejection.title == "Initial Rejection Rate is on target but worsening"
    assert rejection.severity == "information"
    assert rejection.insight_type == "kpi_driver"
    assert "rising toward its maximum allowed" in rejection.detail.recommended_focus
    assert rejection.id not in {item.id for item in workspace.opportunities}

    on_time = _analysis(workspace, HIGHER)
    assert on_time.title == "Submission Within Due Date is on target but worsening"
    assert "falling toward its target" in on_time.detail.recommended_focus


# --- team gap, people impact, trend status ------------------------------------

def test_team_summary_and_kpi_overview_count_a_lower_better_miss_as_critical():
    workspace = _service([
        _submission("May", .04, .9),
        _submission("June", .08, .9),
    ]).generate_workspace(_scope(), month="June", year=2026)

    team = workspace.team_summaries[0]
    assert team.team == "Submission"
    assert team.critical == 1
    assert team.main_cause == "Initial Rejection Rate contributed to the performance gap"
    assert workspace.kpi_overview.critical == 1
    assert workspace.kpi_overview.on_track == 1


def test_people_contribution_is_direction_aware_for_lower_better_kpi():
    records = [
        _submission("May", .04, .9, employee_id="E1"),
        _submission("June", .08, .9, employee_id="E1"),
        _submission("May", .05, .9, employee_id="E2"),
        _submission("June", .03, .9, employee_id="E2"),
    ]
    analysis = _service(records).generate_workspace(
        _scope(), month="June", year=2026, kpi=LOWER
    ).people_contribution_analysis

    assert analysis.direction == "lower_better"
    worse = next(row for row in analysis.rows if row.employee_id == "E1")
    better = next(row for row in analysis.rows if row.employee_id == "E2")
    assert worse.gap == pytest.approx(-3.0)
    assert worse.achievement_percent == 62.5
    assert worse.trend == pytest.approx(4.0)  # raw delta keeps its existing contract
    assert worse.change_value == pytest.approx(-4.0)
    assert worse.trend_status == "declining"
    assert worse.target_status == "missed"
    assert worse.classification == "negative"
    assert worse.weighted_impact < 0
    assert worse.severity == "High"
    assert better.gap == pytest.approx(2.0)
    assert better.achievement_percent == 100.0
    assert better.change_value == pytest.approx(2.0)
    assert better.trend_status == "improving"
    assert better.target_status == "met"
    assert better.classification != "negative"
    assert analysis.negative_contributors == 1


def test_kpi_trend_status_follows_direction():
    rejection = [.03, .04, .05, .06, .06, .08]
    on_time = [.80, .82, .85, .88, .90, .95]
    records = [_submission(month, rejection[index], on_time[index]) for index, month in enumerate(MONTHS)]
    service = _service(records)

    lower = service.generate_workspace(_scope(), month="June", year=2026, kpi=LOWER).kpi_trend
    assert lower.direction == "lower_better"
    assert [point.achievement_percent for point in lower.points] == [100.0, 100.0, 100.0, 83.33, 83.33, 62.5]
    assert [point.status for point in lower.points] == ["on_track", "on_track", "on_track", "at_risk", "at_risk", "critical"]
    assert [point.trend_status for point in lower.points] == [None, "declining", "declining", "declining", "stable", "declining"]
    assert lower.points[-1].change_value == pytest.approx(-.02)
    assert lower.trend_status == "declining"

    higher = service.generate_workspace(_scope(), month="June", year=2026, kpi=HIGHER).kpi_trend
    assert higher.direction == "higher_better"
    assert higher.points[-1].status == "on_track"
    assert higher.points[0].status == "at_risk"
    assert higher.trend_status == "improving"


# --- direction resolution ------------------------------------------------------

def test_configured_direction_overrides_a_defaulted_persisted_direction():
    """Regression: the dashboard resolver writes ``higher_better`` when its exact-key
    config lookup misses; that default made rising rejection look positive."""
    workspace = _service([
        _submission("May", .04, .9, persisted_direction="higher_better"),
        _submission("June", .08, .9, persisted_direction="higher_better"),
    ]).generate_workspace(_scope(), month="June", year=2026)

    rejection = _analysis(workspace, LOWER)
    assert rejection.detail.direction == "lower_better"
    assert rejection.detail.direction_defaulted is False
    assert rejection.impact_points < 0
    assert _driver(workspace, LOWER).direction == "negative"


@pytest.mark.parametrize("team,position", [
    ("Pre-Approvals OP Final SHJAJM", "Unconfigured Role"),  # position not in config
    ("Pre-Approvals OP Final", "OP Final"),  # merged logical team, no config file
])
def test_initial_rejection_percent_uses_team_config_when_record_config_cannot_resolve(team, position):
    def row(month, actual):
        return _record(month, [
            _kpi(LOWER, "Initial Rejection %", actual, .05, .5, "higher_better"),
        ], team=team, position=position)

    values = _configured_kpi_values(row("June", .08))
    assert values[0]["direction"] == "lower_better"
    assert values[0]["direction_source"] == "team_config"

    workspace = _service([row("May", .04), row("June", .08)]).generate_workspace(_scope(), month="June", year=2026)
    item = _analysis(workspace, LOWER)
    assert item.detail.direction == "lower_better"
    assert item.detail.gap_value == pytest.approx(-.03)
    assert item.impact_points < 0


def test_missing_direction_defaults_to_higher_better_and_is_flagged():
    def row(month, actual):
        return _record(month, [
            _kpi("legacy_unmapped_metric", "Legacy Unmapped Metric", actual, 10, 1.0, None, unit="count"),
        ], team="Legacy Unconfigured Team", position="Agent")

    workspace = _service([row("May", 8), row("June", 9)]).generate_workspace(_scope(), month="June", year=2026)

    item = _analysis(workspace, "legacy_unmapped_metric")
    assert item.detail.direction == "higher_better"
    assert item.detail.direction_defaulted is True
    assert item.detail.change_value == pytest.approx(1)
    assert item.detail.trend_status == "improving"
    issue = next(issue for issue in workspace.data_issues if issue.title == "KPI direction is missing or invalid")
    assert "treated as higher-is-better" in issue.explanation


def test_persisted_direction_aliases_are_normalized():
    assert _resolve_kpi_direction(
        "Legacy Unconfigured Team", {"kpi_key": "custom_metric_xyz", "direction": "Lower is better"}, None
    ) == ("lower_better", "persisted")
    assert _resolve_kpi_direction(
        "Legacy Unconfigured Team", {"kpi_key": "custom_metric_xyz", "direction": "higher-is-better"}, None
    ) == ("higher_better", "persisted")
    # Unconfigured team, no persisted direction: an unambiguous configured KPI elsewhere wins.
    assert _resolve_kpi_direction(
        "Legacy Unconfigured Team", {"kpi_key": "Initial Rejection Rate"}, None
    ) == ("lower_better", "global_config")
