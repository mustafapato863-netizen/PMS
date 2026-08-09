from datetime import datetime
from io import BytesIO

from openpyxl import Workbook

from services.bsc_template_service import BSCTemplateService
from services.balanced_scorecard_service import BalancedScorecardService


def test_template_rows_convert_into_balanced_scorecard_dataset():
    service = BSCTemplateService()
    rows = [
        {
            "employee_id": "FIN-AM-001",
            "employee_name": "Ahmed Hassan",
            "position": "Account Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Financial",
            "kpi_label": "Revenue Achievement %",
            "direction": "higher_better",
            "weight": 0.30,
            "target_value": 43.1,
            "target_unit": "M",
            "actual_value": 44.0,
        },
        {
            "employee_id": "FIN-AM-001",
            "employee_name": "Ahmed Hassan",
            "position": "Account Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Learning & Growth",
            "kpi_label": "Process Improvement Initiatives Delivered",
            "direction": "higher_better",
            "weight": 0.10,
            "target_value": 3.0,
            "target_unit": "initiatives",
            "actual_value": 2.0,
        },
        {
            "employee_id": "FIN-AM-001",
            "employee_name": "Ahmed Hassan",
            "position": "Account Manager",
            "performance_level": "Managerial",
            "month": "April",
            "year": 2025,
            "perspective": "Financial",
            "kpi_label": "Revenue Achievement %",
            "direction": "higher_better",
            "weight": 0.30,
            "target_value": 42.0,
            "target_unit": "M",
            "actual_value": 43.0,
        },
    ]
    base_config = {
        "grade_thresholds": {"A": 90, "B": 80, "C": 70, "D": 60},
        "balanced_scorecard": {"enabled": True, "perspectives": [], "strategy_map_links": []},
    }

    records = service._rows_to_records(rows, team="Sales", performance_level="Managerial")
    config = service._rows_to_config(rows, team="Sales", performance_level="Managerial", base_config=base_config)
    data = BalancedScorecardService.build(records, config, "Sales", "Managerial", "May", 2025)

    assert len(records) == 2
    assert data["selection"]["year"] == 2025
    assert data["history"][-1]["month"] == "May"
    revenue = next(row for row in data["kpi_table"] if row["kpi_key"] == "revenue_achievement")
    assert revenue["score"] == 44.0 / 43.1 * 100


def test_parse_upload_accepts_excel_date_period():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "KPI's Data"
    sheet.append([
        "Employee ID", "Team", "Employee Name", "Position", "Performance Level", "Period",
        "Perspective", "KPI", "Direction", "Weight", "Target Value", "Target Unit", "Actual Value",
    ])
    sheet.append([
        "EMP-1", "Sales", "Ahmed", "Sales Manager", "Managerial", datetime(2025, 5, 1),
        "Financial", "Revenue Achievement %", "Higher", 30, 95, "%", 99,
    ])
    payload = BytesIO()
    workbook.save(payload)

    rows = BSCTemplateService().parse_upload(payload.getvalue())

    assert rows[0]["month"] == "May"
    assert rows[0]["year"] == 2025
    assert rows[0]["team"] == "Sales"


def test_parse_upload_accepts_view_weight():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "KPI's Data"
    sheet.append([
        "Employee ID", "Team", "Employee Name", "Position", "Performance Level", "Period",
        "Perspective", "KPI", "Direction", "Weight", "Target Value", "Target Unit", "Actual Value",
    ])
    sheet.append([
        "EMP-1", "Management", "Dina", "General Manager", "Corporate", datetime(2025, 5, 1),
        "Financial", "View Metric", "Higher", "View", 100, "%", 95,
    ])
    payload = BytesIO()
    workbook.save(payload)

    rows = BSCTemplateService().parse_upload(payload.getvalue())

    assert len(rows) == 1
    assert rows[0]["weight"] == 0.0001
    assert rows[0]["kpi_label"] == "View Metric"


def test_parse_upload_rejects_invalid_or_zero_weight():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "KPI's Data"
    sheet.append([
        "Employee ID", "Team", "Employee Name", "Position", "Performance Level", "Period",
        "Perspective", "KPI", "Direction", "Weight", "Target Value", "Target Unit", "Actual Value",
    ])
    sheet.append([
        "EMP-1", "Management", "Dina", "General Manager", "Corporate", datetime(2025, 5, 1),
        "Financial", "Zero Weight Metric", "Higher", 0, 100, "%", 95,
    ])
    payload = BytesIO()
    workbook.save(payload)

    import pytest
    with pytest.raises(ValueError, match="invalid Weight '0'"):
        BSCTemplateService().parse_upload(payload.getvalue())

