import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from config.loader import load_team_config, ConfigurationError
from data_cleaning.cleaner_factory import get_process_function
from services.kpi_service import KPIService
from api.routers import router as api_router
from fastapi import FastAPI
from models.schemas import KPIWeight, Target
from repositories.base import KPIWeightsRepository, TargetsRepository

app = FastAPI()
app.include_router(api_router, prefix="/api")
client = TestClient(app)


# Mock Repositories for KPIService
class MockWeightsRepo(KPIWeightsRepository):
    def __init__(self):
        self._teams = {}

    def get_by_team(self, team):
        return self._teams.get(team)

    def get_all(self):
        return list(self._teams.values())

    def save(self, record):
        self._teams[record.team] = record
        return record


class MockTargetsRepo(TargetsRepository):
    def __init__(self):
        self._teams = {}

    def get_by_team(self, team):
        return self._teams.get(team)

    def get_all(self):
        return list(self._teams.values())

    def save(self, record):
        self._teams[record.team] = record
        return record


# ============================================================
# CONFIG TESTS
# ============================================================

def test_submission_config_loads_successfully():
    """Verify submission.json loads successfully and validates."""
    config = load_team_config("Submission")
    assert config is not None
    assert config["team"] == "Submission"
    assert config["db_name"] == "Submission"
    assert config["region"] == "UAE"


def test_submission_kpi_weights_sum_to_one():
    """Verify submission team weights sum to exactly 1.0."""
    config = load_team_config("Submission")
    total_weight = sum(kpi["weight"] for kpi in config["kpis"])
    assert abs(total_weight - 1.0) < 0.001


def test_submission_kpi_directions_and_columns():
    """Verify KPI directions and required columns are configured correctly."""
    config = load_team_config("Submission")
    kpis = {kpi["key"]: kpi for kpi in config["kpis"]}
    
    assert "initial_rejection_rate" in kpis
    assert kpis["initial_rejection_rate"]["direction"] == "lower_better"
    assert kpis["initial_rejection_rate"]["actual_col"] == "A.InitialRejectionRate"
    assert kpis["initial_rejection_rate"]["target_col"] == "T.InitialRejectionRate"
    
    assert "submission_within_due_date" in kpis
    assert kpis["submission_within_due_date"]["direction"] == "higher_better"
    assert kpis["submission_within_due_date"]["actual_col"] == "A.TAT48Hours"
    assert kpis["submission_within_due_date"]["target_col"] == "T.%ofSubmissionWithinDuedate"


# ============================================================
# CALCULATION TESTS
# ============================================================

def test_submission_cleaner_calculates_rejection_rate_correctly():
    """Verify that A.InitialRejectionRate is calculated correctly."""
    process_submission = get_process_function("Submission")
    
    # Mock dataframe/excel data
    mock_data = {
        "Employee ID": ["EMP001", "EMP002"],
        "Employee Name": ["Alice", "Bob"],
        "Rejected Claims Amount 3 Month Previous": [5, 10],
        "RA Claims Amount (3 Month Previous)": [100, 200],
        "A.TAT 48 Hours": [0.90, 0.80],
        "T.% of Submission Within Due date": [0.85, 0.85],
        "T.Initial Rejection Rate": [0.04, 0.04],
        "Date": ["2024-01-01", "2024-01-01"]
    }
    
    df_raw = pd.DataFrame(mock_data)
    
    with patch("pandas.read_excel") as mock_read:
        mock_read.return_value = df_raw
        df_cleaned = process_submission("dummy_path.xlsx")
        
        # Verify calculated A.InitialRejectionRate
        assert df_cleaned.iloc[0]["A.InitialRejectionRate"] == 5 / 100
        assert df_cleaned.iloc[1]["A.InitialRejectionRate"] == 10 / 200


def test_submission_cleaner_handles_division_by_zero():
    """Verify division by zero for rejection rate returns 0.0 safely."""
    process_submission = get_process_function("Submission")
    
    mock_data = {
        "Employee ID": ["EMP001"],
        "Employee Name": ["Alice"],
        "Rejected Claims Amount 3 Month Previous": [5],
        "RA Claims Amount (3 Month Previous)": [0],  # zero denominator
        "A.TAT 48 Hours": [0.90],
        "T.% of Submission Within Due date": [0.85],
        "T.Initial Rejection Rate": [0.04],
        "Date": ["2024-01-01"]
    }
    
    df_raw = pd.DataFrame(mock_data)
    
    with patch("pandas.read_excel") as mock_read:
        mock_read.return_value = df_raw
        df_cleaned = process_submission("dummy_path.xlsx")
        
        # Verify no crash and result is 0.0
        assert df_cleaned.iloc[0]["A.InitialRejectionRate"] == 0.0


def test_submission_cleaner_excludes_non_active_performance_grades():
    """Verify raw sheet rows with excluded Performance Grade values are ignored."""
    process_submission = get_process_function("Submission")

    mock_data = {
        "Employee ID": ["EMP001", "EMP002", "EMP003"],
        "Employee Name": ["Alice", "Bob", "Charlie"],
        "Performance Grade": ["A", "New Staff", "Leave"],
        "Rejected Claims Amount 3 Month Previous": [5, 10, 15],
        "RA Claims Amount (3 Month Previous)": [100, 200, 300],
        "A.TAT 48 Hours": [0.90, 0.80, 0.70],
        "T.% of Submission Within Due date": [0.85, 0.85, 0.85],
        "T.Initial Rejection Rate": [0.04, 0.04, 0.04],
        "Date": ["2024-01-01", "2024-01-01", "2024-01-01"]
    }

    df_raw = pd.DataFrame(mock_data)

    with patch("pandas.read_excel") as mock_read, patch(
        "cleaned.clean_sheet_data",
        side_effect=lambda df, sheet_name=None: df,
    ):
        mock_read.return_value = df_raw
        df_cleaned = process_submission("dummy_path.xlsx")

        assert len(df_cleaned) == 1
        assert df_cleaned.iloc[0]["EmployeeID"] == "EMP001"


def test_submission_scoring_unified_model():
    """Verify performance scoring and KPI capping rules."""
    service = KPIService(MockWeightsRepo(), MockTargetsRepo())
    
    # Example calculation:
    # Rejected Claims = 5, RA Claims = 100 -> A.InitialRejectionRate = 5%
    # Target Rejection Rate = 4% (lower_better)
    # Achievement = 4 / 5 = 80%
    # Contribution = 80% * 0.60 = 48%
    
    # A.TAT 48 Hours = 90%, Target Submission = 85% (higher_better)
    # Achievement = 90 / 85 = 105.88%
    # Effective Achievement = 100%
    # Contribution = 100% * 0.40 = 40%
    
    # Final Score = 48 + 40 = 88%
    row = {
        "RejectedClaimsAmount3MonthPrevious": 5,
        "RAClaimsAmount(3MonthPrevious)": 100,
        "A.TAT48Hours": 0.90,
        "T.%ofSubmissionWithinDuedate": 0.85,
        "T.InitialRejectionRate": 0.04
    }
    
    # Make sure calculated A.InitialRejectionRate is in row (simulating cleaner output)
    row["A.InitialRejectionRate"] = 5 / 100
    
    score, grade, kpis = service.calculate_performance_multi_team("Submission", row)
    
    contributions = {k["kpi_key"]: k for k in kpis}
    
    # Verify achievements and contributions
    assert abs(contributions["initial_rejection_rate"]["achievement_ratio"] - 0.80) < 0.001
    assert abs(contributions["initial_rejection_rate"]["contribution"] - 0.48) < 0.001
    
    assert abs(contributions["submission_within_due_date"]["achievement_ratio"] - 1.0) < 0.001
    assert abs(contributions["submission_within_due_date"]["contribution"] - 0.40) < 0.001  # capped at weight (0.4)
    
    assert abs(score - 88.0) < 0.001
    assert grade == "B"


def test_submission_final_score_never_exceeds_100():
    """Verify that final performance score never exceeds 100 even if both KPIs exceed target."""
    service = KPIService(MockWeightsRepo(), MockTargetsRepo())
    
    row = {
        "A.InitialRejectionRate": 0.02, # Target is 0.04 (inverse, so 200% achievement)
        "T.InitialRejectionRate": 0.04,
        "A.TAT48Hours": 0.95,          # Target is 0.85 (direct, so 111.7% achievement)
        "T.%ofSubmissionWithinDuedate": 0.85
    }
    
    score, grade, kpis = service.calculate_performance_multi_team("Submission", row)
    
    assert score == 100.0
    assert grade == "A"


# ============================================================
# API / INTEGRATION TESTS
# ============================================================

def test_submission_appears_in_config_teams_endpoint():
    """Verify that Submission team config is loaded and returned by configuration API."""
    response = client.get("/api/config/teams")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    # Check that Submission is in the list
    teams = [t["team"] for t in data["data"]]
    assert "Submission" in teams
    
    # Check detail of Submission config
    sub_config = next(t for t in data["data"] if t["team"] == "Submission")
    assert sub_config["db_name"] == "Submission"
    assert len(sub_config["kpis"]) == 2


def test_submission_appears_in_settings_weights_endpoint():
    """Verify Submission team weights can be loaded from settings router."""
    with patch("api.routers.settings.KPIConfigurationService") as mock_service:
        mock_service.return_value.list_weights.return_value = [
            {"team": "Submission", "weights": {"initial_rejection_rate": 0.60, "submission_within_due_date": 0.40}}
        ]
        
        response = client.get("/api/settings/weights")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # Verify Submission exists
        teams = [w["team"] for w in data["data"]]
        assert "Submission" in teams
