"""People to review: each person row carries the employee's stored performance score for the period.

Synthetic employee-months only. The field is additive and optional: the same stored score on every KPI
row of that employee, None when no score is stored (never 0), and responses cached before the field
existed still parse. Ranking and classification do not read the field.
"""
from models.insight_schemas import InsightPersonContribution
from models.schemas import EvaluationData, PerformanceRecord
from services.insights_service import InsightsService

TEAM = "Pre-Approvals IP Offshore"


def _record(employee: str, *, score: float, rejected_rate: float) -> PerformanceRecord:
    return PerformanceRecord(
        id=f"{employee}_2026_September",
        employee_id=employee,
        employee_name=f"Agent {employee}",
        team=TEAM,
        month="September",
        year=2026,
        region="UAE",
        position="Agent L1",
        performance_level="Employee",
        evaluation=EvaluationData(score=score, grade="B"),
        raw_data={"RejectedRequests": rejected_rate},
        kpi_values=[{
            "kpi_key": "Rejection",
            "label": "Rejection Rate",
            "direction": "lower_better",
            "unit": "%",
            "actual_value": rejected_rate,
            "target_value": 0.01,
            "weight_applied": 0.5,
            "achievement_ratio": 1.0,
            "contribution": 50.0,
        }],
    )


def test_each_person_row_carries_the_stored_period_score():
    records = [_record("E1", score=81.44, rejected_rate=0.05), _record("E2", score=62.0, rejected_rate=0.08)]

    analysis = InsightsService._people_contribution_analysis("Rejection", records, [])

    assert analysis is not None
    assert {row.employee_id: row.performance_score for row in analysis.rows} == {"E1": 81.44, "E2": 62.0}


def test_a_person_without_a_stored_score_is_none_not_zero():
    missing = _record("E3", score=70.0, rejected_rate=0.05).model_copy(update={"evaluation": None})

    analysis = InsightsService._people_contribution_analysis("Rejection", [missing], [])

    assert analysis is not None
    assert [row.performance_score for row in analysis.rows] == [None]


def test_responses_cached_before_the_field_existed_still_parse():
    cached = {
        "employee_id": "E1",
        "employee_name": "Agent E1",
        "team": TEAM,
        "performance_level": "Employee",
        "position": "Agent L1",
        "kpi_key": "Rejection",
        "kpi_label": "Rejection Rate",
        "severity": "High",
        "classification": "negative",
    }

    row = InsightPersonContribution.model_validate(cached)

    assert row.performance_score is None
    assert row.weighted_impact is None
