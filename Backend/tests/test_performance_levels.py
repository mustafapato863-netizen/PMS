import pandas as pd
import pytest

from config.loader import ConfigurationError, resolve_team_config, validate_team_config
from models.schemas import EvaluationData, PerformanceRecord
from repositories.json_repos import JSONPerformanceRepository
from services.seeding_service import DatabaseSeeder, UploadProcessingError
from utils.performance_levels import normalize_performance_level


def test_normalize_performance_level_accepts_aliases_and_all():
    assert normalize_performance_level("emp") == "Employee"
    assert normalize_performance_level(" Manager ") == "Managerial"
    assert normalize_performance_level("corp") == "Corporate"
    assert normalize_performance_level("All", allow_all=True) == "All"


def test_normalize_performance_level_rejects_unknown_value():
    with pytest.raises(ValueError, match="Invalid performance level 'Director'"):
        normalize_performance_level("Director")


def test_resolve_team_config_uses_selected_level_and_validation_is_scoped():
    config = {
        "team": "Inbound",
        "db_name": "inbound",
        "region": "EGY",
        "employee_id_col": "EmployeeID",
        "employee_name_col": "EnglishName",
        "grade_thresholds": {"A": 90, "B": 80, "C": 70, "D": 60},
        "kpis": [
            {"key": "booking", "label": "Booking", "weight": 0.6, "direction": "up", "unit": "%", "color": "#000", "actual_col": "booking_actual", "target_col": "booking_target", "aggregation": {"method": "average"}},
            {"key": "quality", "label": "Quality", "weight": 0.4, "direction": "up", "unit": "%", "color": "#111", "actual_col": "quality_actual", "target_col": "quality_target", "aggregation": {"method": "average"}},
        ],
        "performance_levels": {
            "Managerial": {
                "kpis": [
                    {"key": "revenue", "label": "Revenue", "weight": 0.8, "direction": "up", "unit": "%", "color": "#222", "actual_col": "revenue_actual", "target_col": "revenue_target"},
                    {"key": "ops", "label": "Ops", "weight": 0.2, "direction": "up", "unit": "%", "color": "#333", "actual_col": "ops_actual", "target_col": "ops_target"},
                ]
            }
        },
    }

    resolved = resolve_team_config(config, "manager")

    assert resolved["performance_level"] == "Managerial"
    assert [kpi["key"] for kpi in resolved["kpis"]] == ["revenue", "ops"]

    is_valid, errors = validate_team_config(config)
    assert is_valid is True
    assert errors == []


def test_employee_kpis_require_an_explicit_team_aggregation_method():
    config = {
        "team": "Future Team",
        "db_name": "Future Team",
        "region": "UAE",
        "employee_id_col": "EmployeeID",
        "employee_name_col": "EmployeeName",
        "grade_thresholds": {"A": 90, "B": 80, "C": 70, "D": 60},
        "kpis": [{
            "key": "rate",
            "label": "Rate",
            "weight": 1,
            "direction": "higher_better",
            "unit": "%",
            "color": "#000000",
            "actual_col": "Actual",
            "target_col": "Target",
        }],
    }

    is_valid, errors = validate_team_config(config)

    assert is_valid is False
    assert errors == ["Employee KPI 0 (rate): missing field 'aggregation'"]


def test_resolve_team_config_requires_non_employee_override():
    with pytest.raises(ConfigurationError, match="No Corporate KPI configuration"):
        resolve_team_config(
            {
                "team": "Inbound",
                "db_name": "inbound",
                "region": "EGY",
                "employee_id_col": "EmployeeID",
                "employee_name_col": "EnglishName",
                "grade_thresholds": {"A": 90, "B": 80, "C": 70, "D": 60},
                "kpis": [],
            },
            "Corporate",
        )


def test_json_performance_repository_filters_by_performance_level(monkeypatch):
    records = [
        PerformanceRecord(
            id="1_January",
            employee_id="1",
            employee_name="Emp",
            team="Inbound",
            month="January",
            performance_level="Employee",
            evaluation=EvaluationData(score=82, grade="B"),
        ),
        PerformanceRecord(
            id="2_January",
            employee_id="2",
            employee_name="Mgr",
            team="Inbound",
            month="January",
            performance_level="Managerial",
            evaluation=EvaluationData(score=91, grade="A"),
        ),
    ]

    repo = JSONPerformanceRepository()
    monkeypatch.setattr(repo, "get_all", lambda: records)

    assert [r.employee_id for r in repo.get_filtered(performance_level="Employee")] == ["1"]
    assert [r.employee_id for r in repo.get_filtered(performance_level="Managerial")] == ["2"]


def test_normalize_sheet_levels_defaults_missing_role_to_employee():
    df = pd.DataFrame([{"EmployeeID": "E-1"}])

    levels = DatabaseSeeder._normalize_sheet_levels(df, "EmployeeID", "Inbound")

    assert levels == ["Employee"]
    assert df["performance_level"].tolist() == ["Employee"]


def test_normalize_sheet_levels_raises_useful_error_for_invalid_role():
    df = pd.DataFrame([{"EmployeeID": "E-9", "Role": "Director"}])

    with pytest.raises(UploadProcessingError, match="Row 2, employee E-9: invalid Role 'Director'"):
        DatabaseSeeder._normalize_sheet_levels(df, "EmployeeID", "Inbound")
