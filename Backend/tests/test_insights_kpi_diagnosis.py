"""Insights KPI diagnosis: one row per scored KPI in scope, from the workspace's own rollups.

Synthetic records only.
"""

import pytest

from models.schemas import EvaluationData, PerformanceRecord
from services.insights_service import InsightsService
from services.planning_service import PlanningService


class StubRepository:
    def __init__(self, records):
        self.records = records

    def get_all(self):
        return self.records


def _kpi(key, label, actual, target, weight, direction="higher_better", unit="%"):
    if direction == "lower_better":
        achievement = 1.0 if actual <= 0 else min(target / actual, 1.0)
    else:
        achievement = min(actual / target, 1.0) if target else 0.0
    return {
        "kpi_key": key,
        "label": label,
        "direction": direction,
        "unit": unit,
        "actual_value": actual,
        "target_value": target,
        "weight_applied": weight,
        "contribution": achievement * weight,
    }


def _record(employee_id, team, kpis, month="June"):
    return PerformanceRecord(
        id=f"{employee_id}_2026_{month}",
        employee_id=employee_id,
        employee_name=f"Synthetic {employee_id}",
        team=team,
        month=month,
        year=2026,
        region="EGY",
        position="Synthetic Position",
        performance_level="Employee",
        status="Below",
        evaluation=EvaluationData(score=50.0, grade="C"),
        kpi_values=kpis,
    )


def _scope():
    return {
        "role": "Admin",
        "has_unrestricted_team_access": True,
        "legacy_unscoped": False,
        "accessible_teams": [],
        "accessible_team_levels": [],
    }


def _service(records):
    repository = StubRepository(records)
    service = InsightsService(repository, PlanningService(repository))
    service._authorized_records = lambda _scope: (records, 0)
    return service


def _fixture_records():
    """Three KPIs at 100%, 80% and 50% team achievement, a zero-weight tracking indicator, two teams."""
    on_track = {"key": "on_track", "label": "On track KPI", "target": 1.0, "weight": 0.4}
    at_risk = {"key": "at_risk", "label": "At risk KPI", "target": 1.0, "weight": 0.4}
    critical = {"key": "critical", "label": "Critical KPI", "target": 1.0, "weight": 0.2}
    tracking = {"key": "tracking", "label": "Tracking only", "target": 100.0, "weight": 0.0}

    def kpis(on, risk, crit, track):
        return [
            _kpi(on_track["key"], on_track["label"], on, on_track["target"], on_track["weight"]),
            _kpi(at_risk["key"], at_risk["label"], risk, at_risk["target"], at_risk["weight"]),
            _kpi(critical["key"], critical["label"], crit, critical["target"], critical["weight"]),
            _kpi(tracking["key"], tracking["label"], track, tracking["target"], tracking["weight"], unit="count"),
        ]

    return [
        _record("E1", "Synthetic Alpha", kpis(1.2, 0.5, 0.4, 40.0)),
        _record("E2", "Synthetic Alpha", kpis(1.1, 1.0, 0.6, 60.0)),
        _record("E3", "Synthetic Beta", kpis(1.0, 0.7, 0.6, 50.0)),
    ]


def _rows_by_key(workspace):
    return {row.key: row for row in workspace.kpi_diagnosis}


def test_every_scored_kpi_gets_a_row_including_on_target_ones():
    workspace = _service(_fixture_records()).generate_workspace(_scope(), month="June", year=2026)

    rows = _rows_by_key(workspace)
    assert set(rows) == {"on_track", "at_risk", "critical"}
    assert rows["on_track"].status == "on_track"
    assert rows["on_track"].achievement_percent == pytest.approx(100.0)
    assert rows["at_risk"].status == "at_risk"
    assert rows["critical"].status == "critical"


def test_tracking_only_indicators_never_become_rows():
    workspace = _service(_fixture_records()).generate_workspace(_scope(), month="June", year=2026)

    assert "tracking" not in _rows_by_key(workspace)
    assert all(row.weight > 0 for row in workspace.kpi_diagnosis)


def test_effect_is_negative_below_target_and_zero_on_target():
    workspace = _service(_fixture_records()).generate_workspace(_scope(), month="June", year=2026)

    rows = _rows_by_key(workspace)
    assert rows["on_track"].effect_points == pytest.approx(0.0, abs=0.01)
    assert rows["at_risk"].effect_points < 0
    assert rows["critical"].effect_points < 0


def test_rows_are_sorted_by_the_largest_negative_effect_first():
    workspace = _service(_fixture_records()).generate_workspace(_scope(), month="June", year=2026)

    effects = [row.effect_points for row in workspace.kpi_diagnosis]
    assert effects == sorted(effects)
    assert workspace.kpi_diagnosis[-1].key == "on_track"


def test_effect_is_the_sum_of_people_to_review_weighted_impact_over_the_scope():
    records = _fixture_records()
    workspace = _service(records).generate_workspace(_scope(), month="June", year=2026)

    for row in workspace.kpi_diagnosis:
        people = InsightsService._people_contribution_analysis(row.key, records, [])
        expected = round(sum(item.weighted_impact for item in people.rows if item.weighted_impact is not None), 2)
        assert row.effect_points == pytest.approx(expected, abs=0.01)


def test_each_row_has_six_months_and_the_current_month_matches_the_row_status():
    workspace = _service(_fixture_records()).generate_workspace(_scope(), month="June", year=2026)

    for row in workspace.kpi_diagnosis:
        assert len(row.six_months) == 6
        assert row.six_months[-1].month == "June"
        assert row.six_months[-1].status == row.status
        assert row.six_months[-1].actual_value == pytest.approx(row.actual, abs=1e-3)


def test_one_pass_six_months_equal_the_single_kpi_trend_for_every_kpi():
    # The diagnosis reads every KPI's six months in one pass over the records. It must match the trend
    # built for one KPI at a time, which the Executive and reference views still use.
    records = _fixture_records()
    window = InsightsService._six_month_window((2026, 6))
    index = InsightsService._six_month_values(records, window)

    for key in ("on_track", "at_risk", "critical", "tracking"):
        label, values_by_period = index.get(key, [key, {}])
        one_pass = InsightsService._kpi_trend_from_values(key, label, values_by_period, (2026, 6), window)
        single = InsightsService._kpi_trend(key, records, (2026, 6))
        assert one_pass.model_dump() == single.model_dump()


def test_people_below_target_counts_the_employees_losing_points_on_that_kpi():
    records = _fixture_records()
    workspace = _service(records).generate_workspace(_scope(), month="June", year=2026)

    rows = _rows_by_key(workspace)
    assert rows["on_track"].people_below_target == 0
    assert rows["at_risk"].people_below_target == 2
    assert rows["critical"].people_below_target == 3
    for row in workspace.kpi_diagnosis:
        people = InsightsService._people_contribution_analysis(row.key, records, [])
        assert row.people_below_target == people.negative_contributors


def test_each_row_names_the_teams_that_hold_its_kpi_and_a_team_filter_narrows_it():
    workspace = _service(_fixture_records()).generate_workspace(_scope(), month="June", year=2026)
    assert _rows_by_key(workspace)["critical"].teams == ["Synthetic Alpha", "Synthetic Beta"]

    filtered = _service(_fixture_records()).generate_workspace(_scope(), month="June", year=2026, team="Synthetic Alpha")
    assert _rows_by_key(filtered)["critical"].teams == ["Synthetic Alpha"]


def test_most_below_team_is_named_when_the_scope_has_more_than_one_team():
    workspace = _service(_fixture_records()).generate_workspace(_scope(), month="June", year=2026)

    most_below = _rows_by_key(workspace)["critical"].most_below_team
    assert most_below is not None
    # Alpha averages 40% and 60% (50%); Beta is at 60%.
    assert most_below.team == "Synthetic Alpha"
    assert most_below.achievement_percent == pytest.approx(50.0)
    assert most_below.status == "critical"


def test_scope_filter_limits_the_row_to_the_filtered_team_and_drops_the_comparison():
    workspace = _service(_fixture_records()).generate_workspace(_scope(), month="June", year=2026, team="Synthetic Alpha")

    critical = _rows_by_key(workspace)["critical"]
    assert critical.actual == pytest.approx((0.4 + 0.6) / 2)
    assert critical.most_below_team is None


def test_a_kpi_with_no_stored_weight_is_not_a_row():
    records = [_record("E4", "Synthetic Alpha", [_kpi("no_weight", "No weight KPI", 0.9, 1.0, 0.0)])]

    workspace = _service(records).generate_workspace(_scope(), month="June", year=2026)

    assert workspace.kpi_diagnosis == []
