from datetime import date

import services.insights_service as insights_service_module
from api.routers.insights import _priority_workspace
from models.schemas import CallsData, EvaluationData, GeoBreakdown, GeoData, PerformanceRecord
from services.insights_service import InsightAccessError, InsightsService
from services.planning_service import PlanningService


class StubRepository:
    def __init__(self, records):
        self.records = records

    def get_all(self):
        return self.records


def _record(month: str, score: float, actual: float, target: float, contribution: float) -> PerformanceRecord:
    return PerformanceRecord(
        id=f"E1_2026_{month}",
        employee_id="E1",
        employee_name="Analyst One",
        team="Marketing",
        month=month,
        year=2026,
        region="EGY",
        position="Media Buyer",
        performance_level="Employee",
        status="Below",
        evaluation=EvaluationData(score=score, grade="C"),
        kpi_values=[{
            "kpi_key": "cpl",
            "label": "CPL",
            "direction": "lower_better",
            "unit": "AED",
            "actual_value": actual,
            "target_value": target,
            "weight_applied": .1,
            "contribution": contribution,
        }],
    )


def _service(records):
    repository = StubRepository(records)
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


def test_lower_better_kpi_narrative_uses_real_values_and_weighted_impact():
    service = _service([
        _record("May", 90, 55, 60, .1),
        _record("June", 69.9, 136, 60, .044),
    ])

    workspace = service.generate_workspace(_scope(), month="June", year=2026)

    cpl = next(item for item in workspace.priority_insights if item.kpi_key == "cpl")
    assert cpl.impact_points == -5.59
    assert "declined by 81.00 AED" in cpl.explanation
    assert "moving from 55.00 AED to 136.00 AED" in cpl.explanation
    assert "76.00 AED above target" in cpl.explanation
    assert cpl.detail.recommended_focus == "Reduce CPL and review the affected employees with the largest gap."
    assert workspace.performance_drivers[0].impact_points == -5.59
    assert any(item.kpi_key == "cpl" for item in workspace.team_analyses)
    assert workspace.summary.critical_issues == 1
    assert workspace.summary.negative_weighted_drivers == 1
    assert workspace.summary.weighted_net_impact == -5.59
    assert workspace.summary.coverage_percent == 100
    assert workspace.team_summaries[0].team == "Marketing"
    assert workspace.team_summaries[0].score_change == -20.1
    assert workspace.executive_story is not None
    assert workspace.executive_story.current_score == 69.9
    assert workspace.executive_story.gap_points == -30.1
    assert workspace.geography_summaries[0].scope == "EGY"
    assert workspace.geography_summaries[0].gap_contribution_percent == 100.0
    assert workspace.role_summaries[0].role == "Media Buyer"
    assert workspace.role_summaries[0].team == "Marketing"
    assert workspace.kpi_overview.total_kpis == 1
    assert workspace.kpi_overview.critical == 1
    assert len(workspace.kpi_overview.points) == 2
    assert cpl.planning_context["baseline_value"] == 55
    assert cpl.planning_context["current_value"] == 136
    assert cpl.planning_context["target_value"] == 60
    assert cpl.planning_context["suggested_action"] == cpl.detail.recommended_focus


def test_marketing_insights_use_configured_volume_rollup_and_average_scores():
    first = _record("June", 60, 150, 100, .4)
    second = _record("June", 90, 100, 100, .4)
    second.employee_id = "E2"
    first.position = second.position = "Graphic Designer"
    for record, actual in ((first, 150), (second, 100)):
        record.kpi_values = [{
            "kpi_key": "gd_on_schedule",
            "label": "Projects delivered on schedule",
            "direction": "higher_better",
            "unit": "count",
            "actual_value": actual,
            "target_value": 100,
            "weight_applied": .4,
            "contribution": .4,
        }]

    workspace = _service([first, second]).generate_workspace(
        _scope(), month="June", year=2026, team="Marketing"
    )

    kpi = next(item for item in workspace.team_analyses if item.kpi_key == "gd_on_schedule")
    assert kpi.detail.current_value == 250
    assert kpi.detail.target_value == 200
    assert any(
        evidence.label == "Target achievement" and evidence.value == "100.0%"
        for evidence in kpi.detail.evidence
    )
    assert workspace.team_summaries[0].current_score == 75.0


def test_priority_workspace_is_compact_and_does_not_mutate_full_workspace():
    full = _service([
        _record("May", 90, 55, 60, .1),
        _record("June", 69.9, 136, 60, .044),
    ]).generate_workspace(_scope(), month="June", year=2026)

    compact = _priority_workspace(full, limit=1)

    assert len(compact.priority_insights) == 1
    assert compact.team_analyses == []
    assert compact.performance_drivers == []
    assert compact.risks == []
    assert compact.opportunities == []
    assert compact.data_issues == []
    assert compact.team_summaries == []
    assert compact.people_contribution_analysis is None
    assert compact.kpi_trend is None
    assert compact.role_summaries == []
    assert compact.kpi_overview.total_kpis == 0
    assert compact.options.periods == []
    assert full.team_analyses
    assert full.performance_drivers


def test_priority_only_generation_matches_full_priority_order():
    service = _service([
        _record("May", 90, 55, 60, .1),
        _record("June", 69.9, 136, 60, .044),
    ])
    full = service.generate_workspace(_scope(), month="June", year=2026)
    compact = service.generate_workspace(
        _scope(),
        month="June",
        year=2026,
        priority_only=True,
    )

    assert [item.id for item in compact.priority_insights] == [
        item.id for item in full.priority_insights[:10]
    ]
    assert compact.summary == full.summary
    assert compact.team_analyses == []
    assert compact.performance_drivers == []
    assert compact.team_summaries == []
    assert compact.options.periods == []


def test_priority_only_generation_skips_unused_planning_classification():
    service = _service([
        _record("May", 90, 55, 60, .1),
        _record("June", 69.9, 136, 60, .044),
    ])

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("priority Insights must not classify planning records")

    service.planning_service.classify_records = fail_if_called

    compact = service.generate_workspace(
        _scope(),
        month="June",
        year=2026,
        priority_only=True,
    )

    assert compact.priority_insights


def test_single_period_planning_context_uses_the_only_measurement_for_baseline_and_current():
    workspace = _service([
        _record("June", 69.9, 136, 60, .044),
    ]).generate_workspace(_scope(), month="June", year=2026)

    cpl = next(item for item in workspace.priority_insights if item.kpi_key == "cpl")

    assert cpl.detail.previous_value is None
    assert cpl.planning_context["baseline_value"] == 136
    assert cpl.planning_context["current_value"] == 136


def test_near_target_high_weight_kpi_is_at_risk_not_critical():
    previous = _record("May", 90, 57.7, 65, .621)
    current = _record("June", 89, 58, 65, .625)
    for record in (previous, current):
        record.kpi_values[0]["direction"] = "higher_better"
        record.kpi_values[0]["weight_applied"] = .7

    workspace = _service([previous, current]).generate_workspace(_scope(), month="June", year=2026)

    cpl = next(item for item in workspace.team_analyses if item.kpi_key == "cpl")
    assert cpl.severity == "risk"
    assert workspace.summary.critical_issues == 0
    assert workspace.summary.positive_weighted_drivers == 1
    assert workspace.summary.weighted_positive_impact == .32
    assert any(evidence.label == "Target achievement" and evidence.value == "89.2%" for evidence in cpl.detail.evidence)


def test_weighted_impact_uses_global_capped_contribution_values():
    service = _service([
        _record("May", 90, 55, 60, .1),
        _record("June", 69.9, 136, 60, .044),
    ])

    workspace = service.generate_workspace(_scope(), month="June", year=2026)

    cpl = next(item for item in workspace.priority_insights if item.kpi_key == "cpl")
    assert cpl.impact_points == -5.59
    assert workspace.performance_drivers[0].impact_points == -5.59


def test_zero_target_suppresses_percentage_and_surfaces_data_issue():
    record = _record("June", 80, 5, 0, 0)
    record.kpi_values[0]["direction"] = "higher_better"
    service = _service([record])

    workspace = service.generate_workspace(_scope(), month="June", year=2026)

    kpi = next(item for item in workspace.priority_insights if item.kpi_key == "cpl")
    assert "configured target is zero" in kpi.explanation
    assert "no target percentage is reported" in kpi.explanation
    assert any("Zero KPI targets" in item.title for item in workspace.data_issues)
    assert workspace.summary.expected_kpis == 1
    assert workspace.summary.analyzed_kpis == 0
    assert workspace.summary.coverage_percent == 0


def test_current_month_is_excluded_from_default_period_options(monkeypatch):
    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 17)

    monkeypatch.setattr(insights_service_module, "date", FakeDate)
    service = _service([
        _record("May", 90, 55, 60, .1),
        _record("June", 88, 54, 59, .1),
        _record("July", 87, 53, 58, .1),
    ])

    workspace = service.generate_workspace(_scope())

    assert [period.month for period in workspace.options.periods] == ["June", "May"]
    assert workspace.comparison.current.month == "June"
    assert workspace.comparison.previous.month == "May"


def test_team_options_follow_selected_region():
    records = [
        _record("June", 90, 55, 60, .1),
        _record("June", 88, 54, 59, .1),
    ]
    records[0].team = "Inbound"
    records[0].region = "EGY"
    records[1].team = "Outbound"
    records[1].region = "UAE"

    service = _service(records)

    eg_workspace = service.generate_workspace(_scope(), month="June", year=2026, region="EGY")
    uae_workspace = service.generate_workspace(_scope(), month="June", year=2026, region="UAE")

    assert eg_workspace.options.teams == ["Inbound"]
    assert uae_workspace.options.teams == ["Outbound"]


def test_kpi_options_follow_selected_team_and_period():
    outbound_may = _record("May", 90, 55, 60, .1)
    outbound_may.team = "Alpha"
    outbound_may.kpi_values[0]["kpi_key"] = "outbound_may"
    outbound_may.kpi_values[0]["label"] = "Outbound May KPI"

    outbound_june = _record("June", 88, 54, 59, .1)
    outbound_june.team = "Alpha"
    outbound_june.kpi_values[0]["kpi_key"] = "outbound_june"
    outbound_june.kpi_values[0]["label"] = "Outbound June KPI"

    inbound_june = _record("June", 80, 50, 55, .1)
    inbound_june.team = "Beta"
    inbound_june.kpi_values[0]["kpi_key"] = "inbound_june"
    inbound_june.kpi_values[0]["label"] = "Inbound June KPI"

    workspace = _service([outbound_may, outbound_june, inbound_june]).generate_workspace(
        _scope(), month="June", year=2026, team="Alpha"
    )

    assert workspace.options.kpis == [
        {"key": "outbound_june", "label": "Outbound June KPI"},
    ]


def test_performance_level_options_follow_selected_team_and_period():
    alpha_employee = _record("June", 90, 55, 60, .1)
    alpha_employee.team = "Alpha"
    alpha_employee.performance_level = "Employee"

    alpha_managerial = _record("June", 88, 54, 59, .1)
    alpha_managerial.team = "Alpha"
    alpha_managerial.performance_level = "Managerial"

    beta_corporate = _record("June", 80, 50, 55, .1)
    beta_corporate.team = "Beta"
    beta_corporate.performance_level = "Corporate"

    alpha_workspace = _service([alpha_employee, alpha_managerial, beta_corporate]).generate_workspace(
        _scope(), month="June", year=2026, team="Alpha"
    )
    beta_workspace = _service([alpha_employee, alpha_managerial, beta_corporate]).generate_workspace(
        _scope(), month="June", year=2026, team="Beta"
    )

    assert alpha_workspace.options.performance_levels == ["Employee", "Managerial"]
    assert beta_workspace.options.performance_levels == ["Corporate"]


def test_position_options_follow_selected_team_and_performance_level():
    media_buyer = _record("June", 90, 55, 60, .1)
    media_buyer.team = "Alpha"
    media_buyer.position = "Media Buyer"
    media_buyer.performance_level = "Employee"

    manager = _record("June", 88, 54, 59, .1)
    manager.team = "Alpha"
    manager.position = "Team Lead"
    manager.performance_level = "Managerial"

    workspace = _service([media_buyer, manager]).generate_workspace(
        _scope(), month="June", year=2026, team="Alpha", performance_level="Employee"
    )

    assert workspace.options.positions == ["Media Buyer"]


def test_people_contribution_analysis_defaults_to_the_leading_kpi_and_respects_selection():
    previous_one = _record("May", 90, 55, 60, .1)
    previous_one.employee_id = "E1"
    previous_one.employee_name = "Analyst One"

    current_one = _record("June", 69.9, 136, 60, .044)
    current_one.employee_id = "E1"
    current_one.employee_name = "Analyst One"

    previous_two = _record("May", 90, 65, 60, .092)
    previous_two.employee_id = "E2"
    previous_two.employee_name = "Analyst Two"

    current_two = _record("June", 82, 75, 60, .08)
    current_two.employee_id = "E2"
    current_two.employee_name = "Analyst Two"

    service = _service([previous_one, current_one, previous_two, current_two])

    unfiltered = service.generate_workspace(_scope(), month="June", year=2026)
    filtered = service.generate_workspace(_scope(), month="June", year=2026, kpi="cpl")

    assert unfiltered.people_contribution_analysis is not None
    assert unfiltered.people_contribution_analysis.kpi_key == "cpl"
    assert unfiltered.people_contribution_analysis.total_employees == 2
    assert filtered.people_contribution_analysis is not None
    assert filtered.people_contribution_analysis.kpi_key == "cpl"
    assert filtered.people_contribution_analysis.total_employees == 2
    assert filtered.people_contribution_analysis.negative_contributors == 2
    assert [row.employee_id for row in filtered.people_contribution_analysis.rows] == ["E1", "E2"]
    assert filtered.people_contribution_analysis.rows[0].weighted_impact == -2.8
    assert filtered.people_contribution_analysis.rows[0].gap == -76
    assert filtered.people_contribution_analysis.rows[0].trend == 81


def test_people_contribution_analysis_surfaces_invalid_target_as_data_issue():
    current = _record("June", 80, 5, 0, 0)

    workspace = _service([current]).generate_workspace(
        _scope(), month="June", year=2026, kpi="cpl"
    )

    analysis = workspace.people_contribution_analysis
    assert analysis is not None
    assert analysis.data_issues == 1
    assert analysis.rows[0].classification == "data_issue"
    assert analysis.rows[0].weighted_impact is None


def test_kpi_trend_returns_six_calendar_months_for_the_reference_kpi():
    records = [
        _record("January", 80, 45, 60, .075),
        _record("March", 82, 50, 60, .083),
        _record("June", 90, 55, 60, .092),
    ]
    second_june = _record("June", 88, 65, 70, .093)
    second_june.employee_id = "E2"
    records.append(second_june)

    unfiltered = _service(records).generate_workspace(_scope(), month="June", year=2026)
    filtered = _service(records).generate_workspace(
        _scope(), month="June", year=2026, kpi="cpl"
    )

    assert unfiltered.kpi_trend is not None
    assert unfiltered.kpi_trend.kpi_key == "cpl"
    assert filtered.kpi_trend is not None
    assert [point.period.key for point in filtered.kpi_trend.points] == [
        "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06",
    ]
    assert filtered.kpi_trend.points[1].actual_value is None
    assert filtered.kpi_trend.points[1].measured_records == 0
    assert filtered.kpi_trend.points[-1].actual_value == 60.3846
    assert filtered.kpi_trend.points[-1].target_value == 65.3846
    assert filtered.kpi_trend.points[-1].measured_records == 2


def test_ratio_kpi_trend_keeps_raw_actual_and_target_instead_of_achievement():
    def offshore_record(employee_id: str, actual: float) -> PerformanceRecord:
        return PerformanceRecord(
            id=f"{employee_id}_2026_June",
            employee_id=employee_id,
            employee_name=employee_id,
            team="Pre-Approvals IP Offshore",
            month="June",
            year=2026,
            region="EGY",
            position="Agent",
            performance_level="Employee",
            status="Below",
            evaluation=EvaluationData(score=80, grade="B"),
            kpi_values=[{
                "kpi_key": "Rejection",
                "label": "Rejection Rate",
                "direction": "lower_better",
                "unit": "%",
                "actual_value": actual,
                "target_value": .03,
                "weight_applied": .5,
                "achievement_ratio": min(.03 / actual if actual else 1.0, 1.0),
                "contribution": .5,
            }],
        )

    records = [offshore_record("E1", .01), offshore_record("E2", .09)]

    workspace = _service(records).generate_workspace(
        _scope(), month="June", year=2026, kpi="Rejection"
    )

    assert workspace.kpi_trend is not None
    point = workspace.kpi_trend.points[-1]
    assert point.actual_value == .05
    assert point.target_value == .03
    assert point.target_value != 1.0


def test_missing_requested_period_does_not_fallback_and_order_is_deterministic():
    service = _service([_record("May", 90, 55, 60, .1)])

    first = service.generate_workspace(_scope(), month="June", year=2026)
    second = service.generate_workspace(_scope(), month="June", year=2026)

    assert first.comparison.current.month == "June"
    assert any(item.title == "Required period data is missing" for item in first.data_issues)
    assert [item.id for item in first.priority_insights] == [item.id for item in second.priority_insights]


def test_selected_team_outside_scope_is_rejected():
    service = _service([_record("June", 80, 55, 60, .08)])
    manager_scope = _scope() | {
        "role": "Manager",
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Sales"],
    }

    try:
        service.generate_workspace(manager_scope, team="Marketing")
    except InsightAccessError:
        pass
    else:
        raise AssertionError("Expected the unauthorized team filter to be rejected")


def test_call_center_operational_analyses_are_available_without_score_impact():
    previous = _record("May", 80, 55, 60, .08)
    current = _record("June", 80, 55, 60, .08)
    for record in (previous, current):
        record.team = "Outbound"
        record.raw_data = {"T.AHT": "00:02:30"}
    previous.geo = GeoData(
        bookings=GeoBreakdown(dubai=100),
        attended=GeoBreakdown(dubai=48),
    )
    current.geo = GeoData(
        bookings=GeoBreakdown(dubai=100),
        attended=GeoBreakdown(dubai=49),
    )
    previous.calls = CallsData(total_handled=100, aht_raw="00:03:00")
    current.calls = CallsData(total_handled=100, aht_raw="00:02:00")

    workspace = _service([previous, current]).generate_workspace(_scope(), month="June", year=2026)
    analyses = {item.kpi_key: item for item in workspace.team_analyses}

    no_show = analyses["no_show_rate"]
    assert no_show.detail.current_value == .51
    assert no_show.detail.previous_value == .52
    assert no_show.detail.target_value == .2
    assert no_show.detail.direction == "lower_better"
    assert no_show.impact_points is None
    assert no_show.trend_label == "Improving · Still above target"
    assert "31.0% above target" in no_show.explanation
    assert "calculated" not in no_show.explanation.casefold()

    aht = analyses["aht"]
    assert aht.detail.current_value == 2
    assert aht.detail.previous_value == 3
    assert aht.detail.target_value == 2.5
    assert aht.severity == "opportunity"
    assert aht.impact_points is None
    assert {option["key"] for option in workspace.options.kpis} >= {"no_show_rate", "aht"}


def test_legacy_call_center_records_resolve_configured_weighted_kpis():
    current = _record("June", 80, 55, 60, .08)
    current.team = "Outbound"
    current.kpi_values = []
    current.raw_data = {
        "A.Attend%": 58,
        "T.Attend%": 55,
        "A.Booking%": 40,
        "T.Booking%": 46,
        "A.QualityScore": 96,
        "T.Quality%": 95,
        "A.Reachability%": 62,
        "T.Reachability%": 75,
    }

    workspace = _service([current]).generate_workspace(_scope(), month="June", year=2026)
    analyses = {item.kpi_key: item for item in workspace.team_analyses}

    assert set(analyses) >= {"Attendance", "Booking", "Quality", "Other"}
    assert any(evidence.value == "0.0%" for evidence in analyses["Quality"].detail.evidence if evidence.label == "Applied KPI weight")
    assert any(evidence.value == "20.0%" for evidence in analyses["Other"].detail.evidence if evidence.label == "Applied KPI weight")

def _call_center_record(
    employee_id: str,
    team: str,
    level: str,
    score: float,
    *,
    month: str = "June",
    actual: float = .9,
    target: float = .95,
    contribution: float = .2,
) -> PerformanceRecord:
    return PerformanceRecord(
        id=f"{employee_id}_2026_{month}",
        employee_id=employee_id,
        employee_name=employee_id,
        team=team,
        month=month,
        year=2026,
        region="EGY",
        position="Agent",
        performance_level=level,
        status="Below",
        evaluation=EvaluationData(score=score, grade="C"),
        kpi_values=[{
            "kpi_key": "Attendance",
            "label": "Attendance",
            "direction": "higher_better",
            "unit": "%",
            "actual_value": actual,
            "target_value": target,
            "weight_applied": .25,
            "contribution": contribution,
        }],
    )


def test_call_center_domain_rolls_up_all_teams_and_levels():
    """Call Center parent filter must average every channel and every level."""
    records = [
        _call_center_record("I1", "Inbound", "Employee", 80),
        _call_center_record("I2", "Inbound", "Managerial", 90),
        _call_center_record("O1", "Outbound", "Employee", 70),
        _call_center_record("O2", "Outbound", "Corporate", 100),
        _call_center_record("I1", "Inbound", "Employee", 75, month="May"),
        _call_center_record("I2", "Inbound", "Managerial", 85, month="May"),
        _call_center_record("O1", "Outbound", "Employee", 65, month="May"),
        _call_center_record("O2", "Outbound", "Corporate", 95, month="May"),
    ]

    workspace = _service(records).generate_workspace(
        _scope(), month="June", year=2026, team="Call Center"
    )

    # Domain avg = (80 + 90 + 70 + 100) / 4 across Inbound+Outbound and all levels.
    assert workspace.executive_story is not None
    assert workspace.executive_story.current_score == 85.0
    assert {summary.team for summary in workspace.team_summaries} == {"Inbound", "Outbound"}
    assert {summary.current_score for summary in workspace.team_summaries} == {85.0}
    assert sum(summary.total_employees for summary in workspace.team_summaries) == 4
    assert workspace.options.performance_levels == ["Corporate", "Employee", "Managerial"]
    assert not any(item.title == "Required period data is missing" for item in workspace.data_issues)


def test_call_center_domain_level_filter_still_narrows_to_one_level():
    records = [
        _call_center_record("I1", "Inbound", "Employee", 80),
        _call_center_record("I2", "Inbound", "Managerial", 90),
        _call_center_record("O1", "Outbound", "Employee", 70),
        _call_center_record("O2", "Outbound", "Corporate", 100),
    ]

    workspace = _service(records).generate_workspace(
        _scope(),
        month="June",
        year=2026,
        team="Call Center",
        performance_level="Employee",
    )

    # Only the Employee rows under Call Center: (80 + 70) / 2 = 75.
    assert workspace.executive_story is not None
    assert workspace.executive_story.current_score == 75.0
    assert sum(summary.total_employees for summary in workspace.team_summaries) == 2


def test_all_teams_view_rolls_up_every_team_and_level():
    records = [
        _call_center_record("I1", "Inbound", "Employee", 80),
        _call_center_record("I2", "Inbound", "Managerial", 90),
        _call_center_record("O1", "Outbound", "Employee", 70),
        _call_center_record("M1", "Marketing", "Employee", 60),
    ]

    workspace = _service(records).generate_workspace(_scope(), month="June", year=2026)

    assert workspace.executive_story is not None
    assert workspace.executive_story.current_score == 75.0
    assert {summary.team for summary in workspace.team_summaries} == {"Inbound", "Outbound", "Marketing"}



# --- Dependent (cascading) filter options, functions and the function param ---

from fastapi import HTTPException

import api.routers.insights as insights_router_module
from utils.report_scope import (
    filter_records_by_scope,
    filter_records_by_team_levels,
    function_for_team,
    functions_for_team,
)


def _scoped_record(
    employee_id: str,
    team: str,
    *,
    region: str = "UAE",
    level: str = "Employee",
    month: str = "June",
    score: float = 80,
) -> PerformanceRecord:
    record = _call_center_record(employee_id, team, level, score, month=month)
    record.region = region
    return record


def _scope_enforcing_service(records):
    """Service whose authorized records go through the real scope filters."""
    repository = StubRepository(records)
    service = InsightsService(repository, PlanningService(repository))

    def authorized(scope):
        scoped = filter_records_by_scope(records, scope)
        return filter_records_by_team_levels(scoped, scope), 0

    service._authorized_records = authorized
    return service


def _manager_scope(*teams: str, levels: list[tuple[str, str]] | None = None) -> dict:
    return _scope() | {
        "role": "Manager",
        "has_unrestricted_team_access": False,
        "accessible_teams": list(teams),
        "accessible_team_levels": levels or [],
    }


def _cascade_records() -> list[PerformanceRecord]:
    return [
        _scoped_record("I1", "Inbound", region="EGY", level="Employee"),
        _scoped_record("O1", "Outbound", region="EGY", level="Managerial"),
        _scoped_record("C1", "Coding", region="UAE", level="Employee"),
        _scoped_record("P1", "Pre-Approvals OP Dubai", region="UAE", level="Corporate"),
        _scoped_record("M1", "Marketing", region="EGY", level="Corporate"),
    ]


def _freeze_today(monkeypatch, year: int = 2026, month: int = 10, day: int = 6) -> None:
    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(year, month, day)

    monkeypatch.setattr(insights_service_module, "date", FakeDate)


def test_function_for_team_maps_source_teams_to_parent_domains():
    assert function_for_team("Inbound") == "Call Center"
    assert function_for_team("Outbound") == "Call Center"
    assert function_for_team("Call Center") == "Call Center"
    assert function_for_team("Coding") == "RCM"
    assert function_for_team("Re-Submission") == "RCM"
    assert function_for_team("Pre-Approvals IP Offshore") == "RCM"
    assert function_for_team("Pre-Approvals OP Dubai") == "RCM"
    assert function_for_team("Marketing") == "Marketing"
    assert function_for_team("") is None
    # UAE pre-approvals roll up into RCM and the narrower Pre-Approvals function.
    assert functions_for_team("pre-approvals ip final dubai") == ["RCM", "Pre-Approvals"]
    assert functions_for_team("Pre-Approvals IP Offshore") == ["RCM"]
    assert functions_for_team("Inbound UAE") == ["Inbound UAE"]


def test_region_options_follow_selected_team_and_level():
    service = _service(_cascade_records())

    unfiltered = service.generate_workspace(_scope(), month="June", year=2026)
    by_team = service.generate_workspace(_scope(), month="June", year=2026, team="Coding")
    by_level = service.generate_workspace(_scope(), month="June", year=2026, performance_level="Corporate")
    own_region = service.generate_workspace(_scope(), month="June", year=2026, region="EGY")

    assert unfiltered.options.regions == ["EGY", "UAE"]
    assert by_team.options.regions == ["UAE"]
    assert by_level.options.regions == ["EGY", "UAE"]
    # The region list ignores its own selection so the user can switch regions.
    assert own_region.options.regions == ["EGY", "UAE"]
    level_and_team = service.generate_workspace(
        _scope(), month="June", year=2026, team="Call Center", performance_level="Managerial"
    )
    assert level_and_team.options.regions == ["EGY"]


def test_team_options_follow_selected_region_and_level_but_not_team():
    service = _service(_cascade_records())

    by_region_level = service.generate_workspace(
        _scope(), month="June", year=2026, region="EGY", performance_level="Corporate"
    )
    by_level = service.generate_workspace(_scope(), month="June", year=2026, performance_level="Employee")
    own_team = service.generate_workspace(_scope(), month="June", year=2026, team="Coding")

    assert by_region_level.options.teams == ["Marketing"]
    assert by_level.options.teams == ["Coding", "Inbound"]
    assert own_team.options.teams == ["Coding", "Inbound", "Marketing", "Outbound", "Pre-Approvals OP Dubai"]


def test_level_options_follow_selected_region_and_team_but_not_level():
    service = _service(_cascade_records())

    by_region = service.generate_workspace(_scope(), month="June", year=2026, region="UAE")
    by_region_team = service.generate_workspace(
        _scope(), month="June", year=2026, region="EGY", team="Call Center"
    )
    own_level = service.generate_workspace(_scope(), month="June", year=2026, performance_level="Employee")

    assert by_region.options.performance_levels == ["Corporate", "Employee"]
    assert by_region_team.options.performance_levels == ["Employee", "Managerial"]
    assert own_level.options.performance_levels == ["Corporate", "Employee", "Managerial"]


def test_options_are_limited_to_current_period_while_periods_stay_unrestricted(monkeypatch):
    _freeze_today(monkeypatch)
    records = [
        _scoped_record("I1", "Inbound", region="EGY", level="Employee", month="May"),
        _scoped_record("S1", "Sales", region="UAE", level="Managerial", month="May"),
        _scoped_record("I1", "Inbound", region="EGY", level="Employee", month="June"),
    ]
    records[1].position = "Closer"
    service = _service(records)

    default_period = service.generate_workspace(_scope())
    may = service.generate_workspace(_scope(), month="May", year=2026)

    # Default period resolves to the latest completed month, like the workspace body.
    assert default_period.comparison.current.month == "June"
    assert [period.month for period in default_period.options.periods] == ["June", "May"]
    assert default_period.options.regions == ["EGY"]
    assert default_period.options.teams == ["Inbound"]
    assert default_period.options.performance_levels == ["Employee"]
    assert default_period.options.positions == ["Agent"]
    assert default_period.options.functions == ["Call Center"]
    assert [item["id"] for item in default_period.options.employees] == ["I1"]

    assert [period.month for period in may.options.periods] == ["June", "May"]
    assert may.options.regions == ["EGY", "UAE"]
    assert may.options.teams == ["Inbound", "Sales"]
    assert may.options.performance_levels == ["Employee", "Managerial"]
    assert may.options.positions == ["Agent", "Closer"]
    assert may.options.functions == ["Call Center", "Sales"]


def test_default_period_follows_selected_scope_like_the_workspace(monkeypatch):
    _freeze_today(monkeypatch)
    records = [
        _scoped_record("S1", "Sales", region="UAE", level="Managerial", month="May"),
        _scoped_record("I1", "Inbound", region="EGY", level="Employee", month="June"),
    ]

    workspace = _service(records).generate_workspace(_scope(), team="Sales")

    assert workspace.comparison.current.month == "May"
    assert workspace.options.performance_levels == ["Managerial"]
    assert workspace.options.regions == ["UAE"]


def test_functions_and_team_functions_are_reported_for_available_teams():
    workspace = _service(_cascade_records()).generate_workspace(_scope(), month="June", year=2026)

    assert workspace.options.functions == ["Call Center", "Marketing", "Pre-Approvals", "RCM"]
    assert workspace.options.team_functions == {
        "Coding": ["RCM"],
        "Inbound": ["Call Center"],
        "Marketing": ["Marketing"],
        "Outbound": ["Call Center"],
        "Pre-Approvals OP Dubai": ["RCM", "Pre-Approvals"],
    }
    assert set(workspace.options.team_functions) == set(workspace.options.teams)


def test_functions_follow_region_and_level_but_not_team_or_function():
    service = _service(_cascade_records())

    by_region = service.generate_workspace(_scope(), month="June", year=2026, region="EGY")
    by_level = service.generate_workspace(_scope(), month="June", year=2026, performance_level="Employee")
    by_team = service.generate_workspace(_scope(), month="June", year=2026, team="Coding")
    by_function = service.generate_workspace(_scope(), month="June", year=2026, function="RCM")

    assert by_region.options.functions == ["Call Center", "Marketing"]
    assert by_level.options.functions == ["Call Center", "RCM"]
    assert by_team.options.functions == ["Call Center", "Marketing", "Pre-Approvals", "RCM"]
    assert by_function.options.functions == ["Call Center", "Marketing", "Pre-Approvals", "RCM"]


def test_function_param_filters_workspace_and_narrows_dependent_options():
    service = _service(_cascade_records())

    workspace = service.generate_workspace(_scope(), month="June", year=2026, function="Call Center")

    assert {summary.team for summary in workspace.team_summaries} == {"Inbound", "Outbound"}
    assert workspace.options.teams == ["Inbound", "Outbound"]
    assert workspace.options.regions == ["EGY"]
    assert workspace.options.performance_levels == ["Employee", "Managerial"]
    assert {item["id"] for item in workspace.options.employees} == {"I1", "O1"}

    rcm = service.generate_workspace(_scope(), month="June", year=2026, function="RCM")
    assert {summary.team for summary in rcm.team_summaries} == {"Coding", "Pre-Approvals OP Dubai"}

    pre_approvals = service.generate_workspace(_scope(), month="June", year=2026, function="Pre-Approvals")
    assert {summary.team for summary in pre_approvals.team_summaries} == {"Pre-Approvals OP Dubai"}

    # A team and a function combine as an intersection.
    coding_in_rcm = service.generate_workspace(
        _scope(), month="June", year=2026, function="RCM", team="Coding"
    )
    assert {summary.team for summary in coding_in_rcm.team_summaries} == {"Coding"}
    mismatch = service.generate_workspace(
        _scope(), month="June", year=2026, function="Call Center", team="Coding"
    )
    assert mismatch.team_summaries == []


def test_manager_function_param_is_limited_to_assigned_teams():
    service = _scope_enforcing_service(_cascade_records())
    manager = _manager_scope("Coding")

    workspace = service.generate_workspace(manager, month="June", year=2026, function="RCM")

    # RCM also covers Pre-Approvals OP Dubai, but the manager only owns Coding.
    assert {summary.team for summary in workspace.team_summaries} == {"Coding"}
    assert workspace.options.teams == ["Coding"]
    assert workspace.options.functions == ["RCM"]
    assert workspace.options.team_functions == {"Coding": ["RCM"]}
    assert {item["id"] for item in workspace.options.employees} == {"C1"}
    assert all(item.team in {None, "Coding"} for item in workspace.priority_insights)


def test_manager_function_outside_assigned_teams_is_rejected():
    service = _scope_enforcing_service(_cascade_records())

    for blocked in ("Call Center", "Marketing", "Pre-Approvals"):
        try:
            service.generate_workspace(_manager_scope("Coding"), month="June", year=2026, function=blocked)
        except InsightAccessError:
            continue
        raise AssertionError(f"Expected function {blocked!r} to be rejected for a Coding manager")


def test_manager_function_respects_assigned_team_levels():
    records = [
        _scoped_record("C1", "Coding", level="Employee"),
        _scoped_record("C2", "Coding", level="Managerial"),
        _scoped_record("P1", "Pre-Approvals OP Dubai", level="Employee"),
    ]
    service = _scope_enforcing_service(records)
    manager = _manager_scope("Coding", levels=[("Coding", "Employee")])

    workspace = service.generate_workspace(manager, month="June", year=2026, function="RCM")

    assert sum(summary.total_employees for summary in workspace.team_summaries) == 1
    assert workspace.options.performance_levels == ["Employee"]
    assert {item["id"] for item in workspace.options.employees} == {"C1"}


def test_unrestricted_users_see_every_team_in_a_function():
    service = _scope_enforcing_service(_cascade_records())
    general_manager = _scope() | {"role": "General Manager", "has_unrestricted_team_access": True}
    unrestricted_manager = _manager_scope("Coding") | {"has_unrestricted_team_access": True}

    for scope in (general_manager, unrestricted_manager):
        workspace = service.generate_workspace(scope, month="June", year=2026, function="RCM")
        assert {summary.team for summary in workspace.team_summaries} == {"Coding", "Pre-Approvals OP Dubai"}
        assert workspace.options.functions == ["Call Center", "Marketing", "Pre-Approvals", "RCM"]
        call_center = service.generate_workspace(scope, month="June", year=2026, function="Call Center")
        assert {summary.team for summary in call_center.team_summaries} == {"Inbound", "Outbound"}


def test_filter_options_new_fields_default_empty_for_backward_compatibility():
    from models.insight_schemas import InsightFilterOptions

    options = InsightFilterOptions()

    assert options.functions == []
    assert options.team_functions == {}
    assert {"periods", "regions", "teams", "performance_levels", "positions", "employees", "kpis"} <= set(options.model_dump())


def test_router_forwards_function_and_maps_scope_errors(monkeypatch):
    captured: dict = {}

    class FakeService:
        def __init__(self, *_args, **_kwargs):
            pass

        def generate_workspace(self, scope, **filters):
            captured.update(filters)
            if filters.get("function") == "Call Center":
                raise InsightAccessError("The selected function is outside the authorized insights scope")
            return _service(_cascade_records()).generate_workspace(_scope(), **filters)

    monkeypatch.setattr(insights_router_module, "InsightsService", FakeService)
    monkeypatch.setattr(insights_router_module, "require_authenticated_scope", lambda _db, _request: _manager_scope("Coding"))
    params = dict(
        month="June", year=2026, region=None, team=None, performance_level=None, position=None,
        employee_id=None, kpi=None, severity=None, insight_type=None, status_filter=None,
        view="full", _role="Manager",
    )

    response = insights_router_module.get_insights_workspace(request=None, db=None, function="RCM", **params)

    assert captured["function"] == "RCM"
    assert response.data.options.functions
    try:
        insights_router_module.get_insights_workspace(request=None, db=None, function="Call Center", **params)
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected a 403 for a function outside the caller's scope")
