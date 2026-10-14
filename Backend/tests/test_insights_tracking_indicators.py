"""Tracking-only indicators in the Insights workspace.

Synthetic employee-months only. The Pre-Approvals IP Offshore policy indicator is
declared in the team config (weight 0, from June 2026). It is reported as its own
section and never enters a scored list, summary count or on-track / at-risk count.
"""
import json

import pytest

from models.schemas import EvaluationData, PerformanceRecord
from services.insights_service import InsightsService
from services.planning_service import PlanningService

TEAM = "Pre-Approvals IP Offshore"


class StubRepository:
    def __init__(self, records):
        self.records = records

    def get_all(self):
        return self.records


def _scope():
    return {
        "role": "Admin",
        "has_unrestricted_team_access": True,
        "legacy_unscoped": False,
        "accessible_teams": [],
        "accessible_team_levels": [],
    }


def _service(records, authorized=None):
    repository = StubRepository(records)
    service = InsightsService(repository, PlanningService(repository))
    service._authorized_records = lambda _scope: ((records if authorized is None else authorized), 0)
    return service


def _offshore(employee: str, month: str, *, policy: float, rejected: float, assigned: float,
              region: str = "UAE", year: int = 2026, stored_row: bool = True) -> PerformanceRecord:
    kpi_values = [{
        "kpi_key": "Rejection",
        "label": "Rejection Rate",
        "direction": "lower_better",
        "unit": "%",
        "actual_value": rejected / assigned,
        "target_value": 0.01,
        "weight_applied": 0.5,
        "achievement_ratio": 1.0,
        "contribution": 50.0,
    }]
    if stored_row:
        kpi_values.append({
            "kpi_key": "PolicyRejection",
            "label": "PolicyRejection",
            "direction": "lower_better",
            "unit": "%",
            "actual_value": policy / assigned,
            "target_value": 0,
            "weight_applied": 0,
            "achievement_ratio": 0,
            "contribution": 0,
            "tracking_only": True,
        })
    return PerformanceRecord(
        id=f"{employee}_{year}_{month}",
        employee_id=employee,
        employee_name=f"Agent {employee}",
        team=TEAM,
        month=month,
        year=year,
        region=region,
        position=None,
        performance_level="Employee",
        evaluation=EvaluationData(score=80, grade="B"),
        raw_data={
            "PolicyRej": policy,
            "RejectedRequests": rejected,
            "AssignedRequest": assigned,
            "PolicyRejectionRate": policy / assigned,
        },
        kpi_values=kpi_values,
    )


def _september(*, region: str = "UAE") -> list[PerformanceRecord]:
    # Totals: 25 policy rejections of 381 assigned requests; 26 rejections, so a 96.2% policy share.
    return [
        _offshore("E1", "September", policy=10, rejected=11, assigned=150, region=region),
        _offshore("E2", "September", policy=15, rejected=15, assigned=231, region=region),
    ]


def _history() -> list[PerformanceRecord]:
    # Earlier months, one employee each: policy 8 of 300 in August, 6 of 240 in July, 4 of 200 in June.
    return [
        _offshore("E1", "June", policy=4, rejected=5, assigned=200),
        _offshore("E1", "July", policy=6, rejected=7, assigned=240),
        _offshore("E1", "August", policy=8, rejected=9, assigned=300),
    ]


def _indicator(workspace, key="PolicyRejection"):
    matches = [item for item in workspace.tracking_indicators if item.key == key]
    assert len(matches) <= 1
    return matches[0] if matches else None


def test_policy_indicator_values_come_from_the_raw_counts_as_ratios_of_sums():
    records = _history() + _september()
    workspace = _service(records).generate_workspace(_scope(), month="September", year=2026)

    indicator = _indicator(workspace)
    assert indicator is not None
    assert indicator.label == "Policy Rejection Rate"
    assert indicator.team == TEAM
    assert indicator.effective_from == "2026-06"
    assert indicator.unit == "%"
    assert indicator.numerator == pytest.approx(25)
    assert indicator.denominator == pytest.approx(381)
    assert indicator.share_denominator == pytest.approx(26)
    assert indicator.denominator_label == "assigned requests"
    assert indicator.share_denominator_label == "rejections"
    assert indicator.value == pytest.approx(25 / 381)
    assert indicator.policy_share == pytest.approx(25 / 26)
    assert indicator.record_count == 2
    assert indicator.period.month == "September"

    assert indicator.previous_period is not None
    assert indicator.previous_period.month == "August"
    assert indicator.previous_value == pytest.approx(8 / 300)
    assert indicator.change == pytest.approx(25 / 381 - 8 / 300)


def test_trend_has_one_point_per_effective_month_in_the_window():
    workspace = _service(_history() + _september()).generate_workspace(_scope(), month="September", year=2026)

    indicator = _indicator(workspace)
    assert [point.period.month for point in indicator.trend] == ["June", "July", "August", "September"]
    values = {point.period.month: point.value for point in indicator.trend}
    assert values["June"] == pytest.approx(4 / 200)
    assert values["July"] == pytest.approx(6 / 240)
    assert values["August"] == pytest.approx(8 / 300)
    assert values["September"] == pytest.approx(25 / 381)


def test_a_month_before_the_effective_date_is_omitted_not_shown_as_zero():
    records = [
        _offshore("E1", "May", policy=3, rejected=4, assigned=100),
        _offshore("E1", "June", policy=4, rejected=5, assigned=200),
    ]
    may = _service(records).generate_workspace(_scope(), month="May", year=2026)
    assert _indicator(may) is None
    assert may.tracking_indicators == []

    june = _service(records).generate_workspace(_scope(), month="June", year=2026)
    indicator = _indicator(june)
    assert indicator is not None
    assert [point.period.month for point in indicator.trend] == ["June"]
    assert indicator.previous_value is None


def test_scope_filter_is_applied_before_the_sums():
    records = _history() + _september(region="UAE") + [
        _offshore("E9", "September", policy=2, rejected=3, assigned=40, region="EGY"),
    ]
    workspace = _service(records).generate_workspace(_scope(), month="September", year=2026, region="EGY")

    indicator = _indicator(workspace)
    assert indicator is not None
    assert indicator.numerator == pytest.approx(2)
    assert indicator.denominator == pytest.approx(40)
    assert indicator.record_count == 1


def test_a_team_without_a_tracking_indicator_gets_an_empty_list():
    marketing = PerformanceRecord(
        id="M1_2026_September",
        employee_id="M1",
        employee_name="Buyer",
        team="Marketing",
        month="September",
        year=2026,
        region="UAE",
        performance_level="Employee",
        position="Media Buyer",
        evaluation=EvaluationData(score=70, grade="C"),
        kpi_values=[{"kpi_key": "cpl", "label": "CPL", "direction": "lower_better", "unit": "AED",
                     "actual_value": 90, "target_value": 80, "weight_applied": 0.2, "contribution": 0.1}],
    )
    workspace = _service([marketing]).generate_workspace(_scope(), month="September", year=2026)
    assert workspace.tracking_indicators == []


def test_the_permission_scope_limits_the_sums():
    everything = _history() + _september()
    authorized = [record for record in everything if record.employee_id == "E1"]
    workspace = _service(everything, authorized=authorized).generate_workspace(_scope(), month="September", year=2026)

    indicator = _indicator(workspace)
    assert indicator is not None
    assert indicator.numerator == pytest.approx(10)
    assert indicator.denominator == pytest.approx(150)
    assert indicator.record_count == 1


def test_the_tracking_row_never_enters_a_scored_list_or_count():
    with_row = _history() + _september()
    without_row = [
        _offshore("E1", "June", policy=4, rejected=5, assigned=200, stored_row=False),
        _offshore("E1", "July", policy=6, rejected=7, assigned=240, stored_row=False),
        _offshore("E1", "August", policy=8, rejected=9, assigned=300, stored_row=False),
        _offshore("E1", "September", policy=10, rejected=11, assigned=150, stored_row=False),
        _offshore("E2", "September", policy=15, rejected=15, assigned=231, stored_row=False),
    ]
    with_tracking = _service(with_row).generate_workspace(_scope(), month="September", year=2026)
    without_tracking = _service(without_row).generate_workspace(_scope(), month="September", year=2026)

    assert with_tracking.summary == without_tracking.summary
    assert [item.model_dump() for item in with_tracking.priority_insights] == [
        item.model_dump() for item in without_tracking.priority_insights
    ]
    body = with_tracking.model_dump(exclude={"tracking_indicators"})
    assert "PolicyRejection" not in json.dumps(body, default=str)


def test_the_tracking_indicator_has_no_target_achievement_grade_or_status():
    workspace = _service(_history() + _september()).generate_workspace(_scope(), month="September", year=2026)
    fields = set(_indicator(workspace).model_dump())
    for forbidden in ("target", "target_value", "achievement", "achievement_ratio", "grade", "status", "target_status"):
        assert forbidden not in fields


def test_priority_view_stays_compact_and_has_no_tracking_section():
    workspace = _service(_history() + _september()).generate_workspace(
        _scope(), month="September", year=2026, priority_only=True,
    )
    assert workspace.tracking_indicators == []


def test_one_definition_of_the_tracking_keys_for_every_caller():
    from services.tracking_indicators import tracking_indicator_keys

    assert tracking_indicator_keys(TEAM) == frozenset({"PolicyRejection"})
    assert tracking_indicator_keys("Marketing") == frozenset()
    assert tracking_indicator_keys("") == frozenset()


def test_the_report_builder_never_lists_the_tracking_row_as_a_kpi():
    from services.insights_report_service import _normalize_record

    normalized = _normalize_record(_offshore("E1", "September", policy=10, rejected=11, assigned=150))
    keys = {row["kpi_key"] for row in normalized["kpis"]}
    assert "PolicyRejection" not in keys
    assert "Rejection" in keys
