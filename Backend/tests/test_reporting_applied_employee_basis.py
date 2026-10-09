"""Trusted applied Employee pins stay authoritative in report evidence.

The static Outbound file is the legacy template: Attendance weight 0.70 and
no Productivity. An applied pin keeps its own KPI set, weight, direction, and
stored contribution. An unpinned KPI that the file does not define stays
fail-visible.
"""
from types import SimpleNamespace

from models.schemas import EvaluationData, PerformanceRecord
from services.dashboard_record_service import _pinned_schema_record
from services.reporting_evidence_service import ReportingEvidenceService


ATTENDANCE_CONTRIBUTION = (0.46 / 0.7) * 0.5
PRODUCTIVITY_CONTRIBUTION = (0.78 / 0.8) * 0.2


def _probe_kpis():
    return [
        {
            "kpi_key": "Attendance", "label": "Attendance Rate", "unit": "%",
            "actual_value": 0.46, "target_value": 0.7, "weight_applied": 0.5,
            "contribution": ATTENDANCE_CONTRIBUTION, "direction": "lower_better",
            "evaluation_pinned": True,
        },
        {
            "kpi_key": "Productivity", "label": "Productivity", "unit": "%",
            "actual_value": 0.78, "target_value": 0.8, "weight_applied": 0.2,
            "contribution": PRODUCTIVITY_CONTRIBUTION, "direction": "higher_better",
            "evaluation_pinned": True,
        },
    ]


def _assert_applied_rows(rows, issues):
    attendance = next(row for row in rows if row["key"] == "Attendance")
    productivity = next(row for row in rows if row["key"] == "Productivity")
    assert attendance["direction"] == "lower_better"
    assert attendance["weight"] == 50
    assert attendance["weighted_contribution"] == ATTENDANCE_CONTRIBUTION * 100
    assert productivity["direction"] == "higher_better"
    assert productivity["weight"] == 20
    assert productivity["weighted_contribution"] == PRODUCTIVITY_CONTRIBUTION * 100
    assert [issue["code"] for issue in issues if issue["code"] in {
        "weight_mismatch", "persisted_kpi_missing_configuration", "configured_kpi_missing_evidence",
    }] == []


def test_pinned_employee_dict_keeps_applied_productivity_weight_and_contribution():
    row = {
        "employee_id": "SYNTHETIC-REVIEW", "employee_name": "Synthetic review",
        "team": "Outbound", "month": "August", "year": 2026,
        "performance_level": "Employee", "position": "", "score": 79.93,
        "evaluation_basis": {"pinned": True, "version_id": "synthetic-approved-revision"},
        "kpi_values": _probe_kpis(),
    }
    rows, issues = ReportingEvidenceService()._normalized_record_kpis(row)
    _assert_applied_rows(rows, issues)


def test_pinned_schema_record_from_the_dashboard_mapper_keeps_the_applied_basis():
    basis = {
        "pinned": True,
        "version_id": "synthetic-approved-revision",
        "lines": [
            {"kpi_key": "Attendance", "label": "Attendance Rate", "direction": "lower_better", "unit": "%"},
            {"kpi_key": "Productivity", "label": "Productivity", "direction": "higher_better", "unit": "%"},
        ],
    }
    payload = {
        "id": "synthetic-review-row",
        "employee_id": "SYNTHETIC-REVIEW",
        "employee_name": "Synthetic review",
        "team": "Outbound",
        "month": "August",
        "year": 2026,
        "performance_level": "Employee",
        "position": "",
        "evaluation": {"score": 79.93, "grade": "C"},
        "raw_data": {"T.Attend%": 0.65, "A.Attend%": 0.46},
        "kpi_values": _probe_kpis(),
        "evaluation_basis": basis,
    }
    item = SimpleNamespace(
        id="synthetic-review-row",
        record_payload=payload,
        score=79.93,
        grade="C",
        month="August",
        year=2026,
        region="EGY",
        branch_key=None,
        performance_level="Employee",
        position_name="",
        status="Meets",
        upload_id=None,
        kpi_values=[
            SimpleNamespace(
                kpi_key="Attendance", actual_value=0.46, target_value=0.7,
                achievement_ratio=0.46 / 0.7, weight_applied=0.5,
                contribution=ATTENDANCE_CONTRIBUTION,
            ),
            SimpleNamespace(
                kpi_key="Productivity", actual_value=0.78, target_value=0.8,
                achievement_ratio=0.78 / 0.8, weight_applied=0.2,
                contribution=PRODUCTIVITY_CONTRIBUTION,
            ),
        ],
    )
    employee = SimpleNamespace(
        employee_id="SYNTHETIC-REVIEW", name="Synthetic review", region="EGY", position_name="",
    )
    record = _pinned_schema_record(item, employee, "Outbound", basis)
    assert isinstance(record, PerformanceRecord)
    assert record.performance_level == "Employee"
    assert all(kpi["evaluation_pinned"] is True for kpi in record.kpi_values)
    rows, issues = ReportingEvidenceService()._normalized_record_kpis(record)
    _assert_applied_rows(rows, issues)


def test_pinned_kpi_object_attributes_reach_the_reporting_service():
    record = SimpleNamespace(
        employee_id="SYNTHETIC-OBJECT",
        employee_name="Synthetic object",
        team="Outbound",
        month="August",
        year=2026,
        performance_level="Employee",
        position="",
        score=79.93,
        kpi_values=[
            SimpleNamespace(
                kpi_key="Productivity", label="Productivity", unit="%",
                actual_value=0.78, target_value=0.8, weight_applied=0.2,
                contribution=PRODUCTIVITY_CONTRIBUTION, direction="higher_better",
                evaluation_pinned=True,
            ),
        ],
    )
    rows, issues = ReportingEvidenceService()._normalized_record_kpis(record)
    productivity = next(row for row in rows if row["key"] == "Productivity")
    assert productivity["weighted_contribution"] == PRODUCTIVITY_CONTRIBUTION * 100
    assert not any(issue["code"] == "persisted_kpi_missing_configuration" for issue in issues)


def test_unpinned_unknown_kpi_stays_fail_visible_against_the_static_file():
    record = PerformanceRecord(
        id="legacy-1",
        employee_id="SYNTHETIC-LEGACY",
        employee_name="Synthetic legacy",
        team="Outbound",
        month="August",
        year=2026,
        performance_level="Employee",
        position="",
        evaluation=EvaluationData(score=70, grade="C"),
        kpi_values=[
            {
                "kpi_key": "NotARealKpi", "label": "Not A Real KPI", "unit": "%",
                "actual_value": 0.5, "target_value": 0.8, "weight_applied": 0.2,
                "contribution": 0.1, "direction": "higher_better",
            },
            {
                "kpi_key": "Attendance", "label": "Attendance Rate", "unit": "%",
                "actual_value": 0.46, "target_value": 0.65, "weight_applied": 0.5,
                "contribution": 0.3, "direction": "higher_better",
            },
        ],
    )
    rows, issues = ReportingEvidenceService()._normalized_record_kpis(record)
    assert [row["key"] for row in rows] == ["Attendance"]
    assert any(
        issue["code"] == "persisted_kpi_missing_configuration" and issue["kpi"] == "NotARealKpi"
        for issue in issues
    )
    mismatch = next(issue for issue in issues if issue["code"] == "weight_mismatch" and issue["kpi"] == "Attendance")
    assert mismatch["expected"] == 70
    assert mismatch["actual"] == 50
    assert next(row for row in rows if row["key"] == "Attendance")["direction"] == "higher_better"
