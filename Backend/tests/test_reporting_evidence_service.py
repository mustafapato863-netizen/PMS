from types import SimpleNamespace

from models.schemas import EvaluationData, PerformanceRecord
from services import reporting_evidence_service as module
from services.reporting_evidence_service import DIAGNOSTIC_LABEL, ReportingEvidenceService, previous_calendar_period


def make_record(employee: str, month: str, score: float, *, grade: str = "B", status: str = "Meets", kpis=None):
    return PerformanceRecord(
        id=f"{employee}-2026-{month}", employee_id=employee, employee_name=employee,
        team="Inbound", month=month, year=2026, region="EGY", performance_level="Employee",
        position="Agent", status=status, evaluation=EvaluationData(score=score, grade=grade),
        kpi_values=kpis or [],
    )


def config(weight=.4):
    return {"grade_thresholds": {"A": 95, "B": 85, "C": 75, "D": 65}, "kpis": [
        {"key": "Quality", "label": "Quality Score", "weight": weight, "direction": "higher_better", "unit": "%"}
    ]}


def value(*, actual=80, target=90, contribution=.32, weight=.4, key="Quality"):
    return {"kpi_key": key, "actual_value": actual, "target_value": target, "contribution": contribution, "weight_applied": weight}


def test_previous_period_is_immediately_adjacent():
    assert previous_calendar_period((2026, 6)) == (2026, 5)
    assert previous_calendar_period((2026, 1)) == (2025, 12)


def test_missing_previous_month_is_explicitly_unavailable(monkeypatch):
    monkeypatch.setattr(module, "_config", lambda _record: config())
    result = ReportingEvidenceService().build([make_record("A", "June", 80, kpis=[value()])], (2026, 6))
    assert result["comparison_state"] == "unavailable"
    assert result["movement"]["total_score_point_change"] is None


def test_zero_target_requires_configuration_review(monkeypatch):
    monkeypatch.setattr(module, "_config", lambda _record: config())
    rows, warnings = ReportingEvidenceService().kpi_evidence([make_record("A", "June", 80, kpis=[value(target=0)])], [])
    assert rows[0]["state"] == "configuration_requires_review"
    assert rows[0]["achievement"] is rows[0]["lost_points"] is rows[0]["target"] is None
    assert warnings


def test_real_zero_is_preserved_when_target_is_valid(monkeypatch):
    monkeypatch.setattr(module, "_config", lambda _record: config())
    rows, _ = ReportingEvidenceService().kpi_evidence([make_record("A", "June", 0, kpis=[value(actual=0)])], [])
    assert rows[0]["actual"] == 0
    assert rows[0]["state"] == "ready"


def test_stale_kpi_is_not_scored(monkeypatch):
    monkeypatch.setattr(module, "_config", lambda _record: config())
    rows, warnings = ReportingEvidenceService().kpi_evidence([make_record("A", "June", 80, kpis=[value(key="Stale")])], [])
    assert rows == []
    assert "mismatch" in warnings[0].lower()


def test_operational_diagnostic_has_zero_weight_and_no_lost_points(monkeypatch):
    monkeypatch.setattr(module, "_config", lambda _record: config(weight=0))
    rows, _ = ReportingEvidenceService().kpi_evidence([make_record("A", "June", 80, kpis=[value(weight=0)])], [])
    assert rows[0]["included_in_score"] is False
    assert rows[0]["weight"] == 0
    assert rows[0]["lost_points"] is None
    assert rows[0]["diagnostic_label"] == DIAGNOSTIC_LABEL


def test_persisted_grade_and_status_are_authoritative():
    grade, status, source = ReportingEvidenceService().effective_grade_status(make_record("A", "June", 99, grade="D", status="Below Target"))
    assert (grade, status, source) == ("D", "Below Target", "persisted")


def test_top_and_bottom_never_duplicate_small_population():
    result = ReportingEvidenceService().rankings([make_record("A", "June", 80)])
    assert [row["employee_id"] for row in result["top"]] == ["A"]
    assert result["bottom"] == []


def test_trend_title_reflects_actual_period_count():
    result = ReportingEvidenceService().trend([make_record("A", "May", 70), make_record("A", "June", 80)], (2026, 6))
    assert result["period_count"] == 2
    assert result["title"] == "Score Trend — 2 Available Periods"


def test_matched_bridge_reconciles_and_separates_population(monkeypatch):
    monkeypatch.setattr(module, "_config", lambda _record: config())
    records = [
        make_record("A", "May", 70, kpis=[value(actual=70, contribution=.28)]),
        make_record("A", "June", 80, kpis=[value(actual=80, contribution=.38)]),
        make_record("B", "June", 90, kpis=[value(actual=90, contribution=.4)]),
        make_record("C", "May", 60, kpis=[value(actual=60, contribution=.24)]),
    ]
    result = ReportingEvidenceService().build(records, (2026, 6))["movement"]
    explained = sum(item["score_point_change"] for item in result["kpi_contribution_movements"])
    explained += result["joiner_effect"] + result["leaver_effect"] + result["population_scope_mix_effect"]
    explained += result["configuration_mismatch_effect"] + result["missing_evidence_effect"] + result["residual"]
    assert abs(result["total_score_point_change"] - explained) <= result["rounding_tolerance"]
    assert result["current_only_employee_count"] == result["previous_only_employee_count"] == 1


def test_lowest_kpis_rank_by_weighted_lost_points_and_exclude_invalid_targets(monkeypatch):
    monkeypatch.setattr(module, "_config", lambda _record: {"grade_thresholds": config()["grade_thresholds"], "kpis": [
        {"key": "A", "label": "KPI A", "weight": .6, "direction": "higher_better", "unit": "%"},
        {"key": "B", "label": "KPI B", "weight": .4, "direction": "higher_better", "unit": "%"},
        {"key": "Zero", "label": "Zero Target", "weight": .2, "direction": "higher_better", "unit": "%"},
    ]})
    current = [make_record("A", "June", 60, grade="D", status="Below Target", kpis=[
        value(key="A", actual=70, target=100, contribution=.2, weight=.6),
        value(key="B", actual=50, target=100, contribution=.3, weight=.4),
        value(key="Zero", actual=0, target=0, contribution=0, weight=.2),
    ])]
    result = ReportingEvidenceService().lowest_kpis(current, [])
    assert [row["key"] for row in result["rows"]] == ["A", "B"]
    assert result["rows"][0]["lost_points"] == 40
    assert [row["key"] for row in result["configuration_issues_excluded"]] == ["Zero"]


def test_lowest_employee_ordering_uses_current_score_then_weighted_loss(monkeypatch):
    monkeypatch.setattr(module, "_config", lambda _record: config())
    current = [
        make_record("A", "June", 60, grade="D", status="Below Target", kpis=[value(contribution=.1)]),
        make_record("B", "June", 50, grade="D", status="Below Target", kpis=[value(contribution=.2)]),
    ]
    result = ReportingEvidenceService().lowest_employees(current, [], current, [], True)
    assert [row["employee_id"] for row in result["rows"]] == ["B", "A"]
    assert result["rows"][0]["rank"] == 1


def test_three_month_rule_requires_exact_consecutive_valid_months(monkeypatch):
    monkeypatch.setattr(module, "_config", lambda _record: config())
    service = ReportingEvidenceService()
    exact = [make_record("A", month, 60, grade="D", status="Below Target", kpis=[value()]) for month in ["April", "May", "June"]]
    missing_middle = [make_record("B", month, 55, grade="D", status="Below Target", kpis=[value()]) for month in ["April", "June"]]
    result = service.three_month_low(exact + missing_middle, (2026, 6), [], True)
    assert [row["employee_id"] for row in result["rows"]] == ["A"]
    assert result["insufficient_history"][0]["employee_id"] == "B"
    assert result["required_periods"] == ["April 2026", "May 2026", "June 2026"]


def test_three_month_configuration_change_is_disclosed(monkeypatch):
    monkeypatch.setattr(module, "_config", lambda _record: config())
    rows = [
        make_record("A", "April", 60, grade="D", status="Below Target", kpis=[value(weight=.4)]),
        make_record("A", "May", 58, grade="D", status="Below Target", kpis=[value(weight=.5)]),
        make_record("A", "June", 55, grade="D", status="Below Target", kpis=[value(weight=.5)]),
    ]
    result = ReportingEvidenceService().three_month_low(rows, (2026, 6), [], True)["rows"][0]
    assert result["configuration_continuity_state"] == "changed_configuration_disclosed"
    assert result["warnings"]


def test_applied_configuration_audit_detects_zero_target_without_repair(monkeypatch):
    monkeypatch.setattr(module, "_config", lambda _record: config())
    rows = [make_record("A", "June", 60, grade="D", status="Below Target", kpis=[value(target=0)])]
    result = ReportingEvidenceService().configuration_audit(rows, (2026, 6))
    issue = next(row for row in result["rows"] if row["code"] == "zero_target")
    assert issue["blocks_ranking_or_reconciliation"] is True
    assert "non-zero" in issue["recommended_correction"]


def test_confirmed_root_cause_requires_persisted_evidence_and_frequency_is_not_impact(monkeypatch):
    monkeypatch.setattr(module, "_config", lambda _record: config())
    employee = SimpleNamespace(employee_id="A", employee_name="Employee A")
    likely = SimpleNamespace(id="1", employee=employee, team="Inbound", root_cause_note="Attendance coaching required", evidence_reference=None, linked_kpi_key="Quality", action_type="Coaching", status="Open", created_at=None, created_by=None)
    confirmed = SimpleNamespace(id="2", employee=employee, team="Inbound", root_cause_note="Workflow SLA issue", evidence_reference="audit-42", linked_kpi_key="Quality", action_type="Process", status="Open", created_at=None, created_by=None)
    current = [make_record("A", "June", 60, grade="D", status="Below Target", kpis=[value()])]
    audit = {"rows": []}
    result = ReportingEvidenceService().root_cause_matrix(current, [likely, confirmed], audit, True)
    assert {row["confidence"] for row in result["rows"]} >= {"Likely", "Confirmed"}
    assert all(row["impact_type"] != "Score impact" for row in result["rows"])
    assert result["impact_label"] == "Evidence mentions / linked action records"


def test_root_cause_matrix_keeps_process_staff_and_data_separate(monkeypatch):
    monkeypatch.setattr(module, "_config", lambda _record: config())
    employee = SimpleNamespace(employee_id="A", employee_name="Employee A")
    actions = [
        SimpleNamespace(id="1", employee=employee, team="Inbound", root_cause_note="System workflow failure", evidence_reference=None, linked_kpi_key=None, created_at=None, created_by=None),
        SimpleNamespace(id="2", employee=employee, team="Inbound", root_cause_note="Employee attendance issue", evidence_reference=None, linked_kpi_key=None, created_at=None, created_by=None),
        SimpleNamespace(id="3", employee=employee, team="Inbound", root_cause_note="Process capacity and staff training", evidence_reference=None, linked_kpi_key=None, created_at=None, created_by=None),
    ]
    audit = {"rows": [{"severity": "high", "issue": "Zero target", "scope": "Inbound", "kpi": "Quality", "employee": "Employee A", "code": "zero_target", "current_period": "June 2026", "effect_on_analysis": "Excluded"}]}
    result = ReportingEvidenceService().root_cause_matrix([], actions, audit, True)
    assert all(result["groups"][group] for group in ["Process", "Staff", "Both", "Data / Configuration"])


def test_managerial_dictionary_uses_period_applied_kpi_metadata_over_employee_yaml():
    record = {
        "employee_id": "M1", "employee_name": "Manager", "team": "Inbound", "position": "Manager",
        "performance_level": "Managerial", "year": 2026, "month": "June", "status": "Meets",
        "evaluation": {"score": 88, "grade": "B"},
        "kpi_values": [{"key": "Manager KPI", "label": "Manager KPI", "actual": 80, "target": 90,
                        "weight": 50, "contribution": 40, "direction": "higher_better", "unit": "%"}],
    }
    rows, warnings = ReportingEvidenceService().kpi_evidence([record], [])
    assert warnings == []
    assert rows[0]["key"] == "Manager KPI"
    assert rows[0]["configuration_state"] == "period_applied_record_configuration"
    assert rows[0]["lost_points"] == 10
