import math
from unittest.mock import patch

import pandas as pd

from config.loader import load_team_config
from data_cleaning.cleaner_factory import get_process_function
from models.schemas import KPIWeight, Target
from repositories.base import KPIWeightsRepository, TargetsRepository
from services.kpi_service import KPIService


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


def _service() -> KPIService:
    return KPIService(MockWeightsRepo(), MockTargetsRepo())


def test_re_submission_config_validity():
    config = load_team_config("Re-Submission")
    assert config["team"] == "Re-Submission"
    assert config["region"] == "UAE"
    assert len(config["kpis"]) == 3
    assert abs(sum(kpi["weight"] for kpi in config["kpis"]) - 1.0) < 0.001
    assert len({kpi["key"] for kpi in config["kpis"]}) == 3

    kpis = {kpi["key"]: kpi for kpi in config["kpis"]}
    assert kpis["quality_errors_rate"]["direction"] == "lower_better"
    assert kpis["quality_errors_rate"]["target_col"] == "T.QualityErrorsRate"
    assert kpis["rejection_rate_after_resubmission"]["direction"] == "lower_better"
    assert kpis["tat"]["direction"] == "higher_better"


def test_re_submission_cleaner_available():
    process = get_process_function("Re-Submission")
    assert callable(process)


def test_re_submission_cleaner_calculates_business_formulas():
    process_re_submission = get_process_function("Re-Submission")
    df_raw = pd.DataFrame({
        "HRID": ["EMP001", "EMP002", "EMP003"],
        "AgentName": ["Alice", "Bob", "Cara"],
        "Allocated Claims": [100, 100, 0],
        "Quality Samples": [100, 100, 0],
        "Final Errors Claims raised by Quality in the same month": [0, 10, 1],
        "Total Submitted Within TAT": [100, 80, 0],
        "Remittance Amount": [100, 100, 0],
        "Rejected Claims from the previous 3 months by insurance": [30, 90, 0],
        "Performance Grade": ["A", "B", "A"],
    })

    with patch("pandas.read_excel") as mock_read, patch(
        "cleaned.clean_sheet_data",
        side_effect=lambda df, sheet_name=None: df,
    ):
        mock_read.return_value = df_raw
        df = process_re_submission("dummy.xlsx")

    first = df.iloc[0]
    second = df.iloc[1]
    third = df.iloc[2]

    assert first["A.QualityErrorsRate"] == 0.0
    assert first["QualityErrorsRateAch%"] == 1.0
    assert first["A.RejectionRateAfterResubmission"] == 0.30
    assert first["RejectionRateAfterResubmissionAch%"] == 1.0
    assert first["A.TAT"] == 1.0
    assert first["TATAch%"] == 1.0

    assert round(second["A.QualityErrorsRate"], 4) == 0.10
    assert round(second["QualityErrorsRateAch%"], 4) == 0.50
    assert round(second["A.RejectionRateAfterResubmission"], 4) == 0.90
    assert round(second["RejectionRateAfterResubmissionAch%"], 4) == round(0.60 / 0.90, 4)
    assert round(second["A.TAT"], 4) == 0.80
    assert round(second["TATAch%"], 4) == 0.80

    assert math.isnan(third["A.QualityErrorsRate"])
    assert math.isnan(third["RejectionRateAfterResubmissionAch%"])
    assert math.isnan(third["A.TAT"])


def test_re_submission_scoring_quality_errors_zero_errors():
    service = _service()
    row = {
        "A.QualityErrorsRate": 0.0,
        "T.QualityErrorsRate": 0.05,
        "QualityErrorsRateAch%": 1.0,
        "A.RejectionRateAfterResubmission": 0.30,
        "T.RejectionRateAfterResubmission": 0.60,
        "RejectionRateAfterResubmissionAch%": 1.0,
        "A.TAT": 1.0,
        "T.TAT": 1.0,
        "TATAch%": 1.0,
    }
    score, _, kpis = service.calculate_performance_multi_team("Re-Submission", row)
    values = {item["kpi_key"]: item for item in kpis}
    assert values["quality_errors_rate"]["actual_value"] == 0.0
    assert values["quality_errors_rate"]["achievement_ratio"] == 1.0
    assert values["quality_errors_rate"]["contribution"] == 0.2
    assert score == 100.0


def test_re_submission_scoring_quality_errors_ten_percent():
    service = _service()
    row = {
        "A.QualityErrorsRate": 0.10,
        "T.QualityErrorsRate": 0.05,
        "QualityErrorsRateAch%": 0.50,
        "A.RejectionRateAfterResubmission": 0.60,
        "T.RejectionRateAfterResubmission": 0.60,
        "RejectionRateAfterResubmissionAch%": 1.0,
        "A.TAT": 1.0,
        "T.TAT": 1.0,
        "TATAch%": 1.0,
    }
    _, _, kpis = service.calculate_performance_multi_team("Re-Submission", row)
    values = {item["kpi_key"]: item for item in kpis}
    assert values["quality_errors_rate"]["achievement_ratio"] == 0.5
    assert values["quality_errors_rate"]["contribution"] == 0.1


def test_re_submission_quality_errors_zero_samples_is_no_data():
    service = _service()
    row = {
        "A.QualityErrorsRate": 0.0,
        "T.QualityErrorsRate": 0.05,
        "QualityErrorsRateAch%": float("nan"),
        "A.RejectionRateAfterResubmission": 0.60,
        "T.RejectionRateAfterResubmission": 0.60,
        "RejectionRateAfterResubmissionAch%": 1.0,
        "A.TAT": 1.0,
        "T.TAT": 1.0,
        "TATAch%": 1.0,
    }
    _, _, kpis = service.calculate_performance_multi_team("Re-Submission", row)
    values = {item["kpi_key"]: item for item in kpis}
    assert values["quality_errors_rate"]["achievement_ratio"] == 0.0
    assert values["quality_errors_rate"]["contribution"] == 0.0


def test_re_submission_scoring_rejection_rate_examples():
    service = _service()
    row = {
        "A.QualityErrorsRate": 0.0,
        "T.QualityErrorsRate": 0.05,
        "QualityErrorsRateAch%": 1.0,
        "A.RejectionRateAfterResubmission": 0.30,
        "T.RejectionRateAfterResubmission": 0.60,
        "RejectionRateAfterResubmissionAch%": 1.0,
        "A.TAT": 1.0,
        "T.TAT": 1.0,
        "TATAch%": 1.0,
    }
    _, _, low_row_kpis = service.calculate_performance_multi_team("Re-Submission", row)
    low_values = {item["kpi_key"]: item for item in low_row_kpis}
    assert low_values["rejection_rate_after_resubmission"]["actual_value"] == 0.3
    assert low_values["rejection_rate_after_resubmission"]["achievement_ratio"] == 1.0

    row["A.RejectionRateAfterResubmission"] = 0.90
    row["RejectionRateAfterResubmissionAch%"] = 0.60 / 0.90
    _, _, high_row_kpis = service.calculate_performance_multi_team("Re-Submission", row)
    high_values = {item["kpi_key"]: item for item in high_row_kpis}
    assert round(high_values["rejection_rate_after_resubmission"]["achievement_ratio"], 4) == round(0.60 / 0.90, 4)


def test_re_submission_zero_actual_rejection_is_no_data():
    service = _service()
    row = {
        "A.QualityErrorsRate": 0.0,
        "T.QualityErrorsRate": 0.05,
        "QualityErrorsRateAch%": 1.0,
        "A.RejectionRateAfterResubmission": 0.0,
        "T.RejectionRateAfterResubmission": 0.60,
        "RejectionRateAfterResubmissionAch%": float("nan"),
        "A.TAT": 1.0,
        "T.TAT": 1.0,
        "TATAch%": 1.0,
    }
    _, _, kpis = service.calculate_performance_multi_team("Re-Submission", row)
    values = {item["kpi_key"]: item for item in kpis}
    assert values["rejection_rate_after_resubmission"]["achievement_ratio"] == 0.0
    assert values["rejection_rate_after_resubmission"]["contribution"] == 0.0


def test_re_submission_scoring_tat_examples():
    service = _service()
    row = {
        "A.QualityErrorsRate": 0.0,
        "T.QualityErrorsRate": 0.05,
        "QualityErrorsRateAch%": 1.0,
        "A.RejectionRateAfterResubmission": 0.60,
        "T.RejectionRateAfterResubmission": 0.60,
        "RejectionRateAfterResubmissionAch%": 1.0,
        "A.TAT": 1.0,
        "T.TAT": 1.0,
        "TATAch%": 1.0,
    }
    _, _, full_tat_kpis = service.calculate_performance_multi_team("Re-Submission", row)
    full_values = {item["kpi_key"]: item for item in full_tat_kpis}
    assert full_values["tat"]["achievement_ratio"] == 1.0
    assert full_values["tat"]["contribution"] == 0.3

    row["A.TAT"] = 0.80
    row["TATAch%"] = 0.80
    _, _, partial_tat_kpis = service.calculate_performance_multi_team("Re-Submission", row)
    partial_values = {item["kpi_key"]: item for item in partial_tat_kpis}
    assert partial_values["tat"]["achievement_ratio"] == 0.8
    assert partial_values["tat"]["contribution"] == 0.24


def test_re_submission_zero_allocated_is_no_data():
    service = _service()
    row = {
        "A.QualityErrorsRate": 0.0,
        "T.QualityErrorsRate": 0.05,
        "QualityErrorsRateAch%": 1.0,
        "A.RejectionRateAfterResubmission": 0.60,
        "T.RejectionRateAfterResubmission": 0.60,
        "RejectionRateAfterResubmissionAch%": 1.0,
        "A.TAT": 0.0,
        "T.TAT": 1.0,
        "TATAch%": float("nan"),
    }
    _, _, kpis = service.calculate_performance_multi_team("Re-Submission", row)
    values = {item["kpi_key"]: item for item in kpis}
    assert values["tat"]["achievement_ratio"] == 0.0
    assert values["tat"]["contribution"] == 0.0


def test_re_submission_final_score_capped_and_submission_unchanged():
    service = _service()
    row = {
        "A.QualityErrorsRate": 0.0,
        "T.QualityErrorsRate": 0.05,
        "QualityErrorsRateAch%": 1.0,
        "A.RejectionRateAfterResubmission": 0.10,
        "T.RejectionRateAfterResubmission": 0.60,
        "RejectionRateAfterResubmissionAch%": 1.0,
        "A.TAT": 2.0,
        "T.TAT": 1.0,
        "TATAch%": 1.0,
    }
    score, _, _ = service.calculate_performance_multi_team("Re-Submission", row)
    assert score == 100.0

    submission_config = load_team_config("Submission")
    assert submission_config["team"] == "Submission"
    assert len(submission_config["kpis"]) == 2
