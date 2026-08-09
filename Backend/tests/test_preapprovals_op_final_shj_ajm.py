from unittest.mock import patch

import pandas as pd
import pytest

from config.loader import load_team_config
from data_cleaning.cleaner_factory import get_process_function
from Data_Cleaning_Teams.preapprovals_op_final_shj_ajm import (
    SHEET_NAME,
    process_preapprovals_op_final_shj_ajm,
)
from services.kpi_service import KPIService


TEAM = "Pre-Approvals OP Final SHJAJM"


def _source_rows() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Date": "2026-06-30", "HR ID": "SHJ-1", "Agent Name": "SHJ Agent",
            "Status": "Active", "Team": "SHJ", "Submitted Requests": 100,
            "Manual Request": 5, "Submitted Within Hour": 90, "Rejected Requests": 5,
            "T.Initial Rejection": 0.05, "T.Submission Within Hour %": 0.70,
            "Performance Grade": "B",
        },
        {
            "Date": "2026-06-30", "HR ID": "AJM-1", "Agent Name": "AJM Agent",
            "Status": "Active", "Team": "AJM", "Submitted Requests": 100,
            "Manual Request": 2, "Submitted Within Hour": "-", "Rejected Requests": 10,
            "T.Initial Rejection": 0.05, "T.Submission Within Hour %": 0.70,
            "Performance Grade": "D",
        },
        {
            "HR ID": "LEAVE-1", "Agent Name": "Leave Agent", "Status": "Leave",
            "Team": "AJM", "Performance Grade": "Leave",
        },
        {
            "HR ID": None, "Agent Name": None, "Status": None,
            "Team": None, "Performance Grade": None,
        },
    ])


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    with patch(
        "Data_Cleaning_Teams.preapprovals_op_final_shj_ajm.pd.read_excel",
        return_value=frame.copy(),
    ), patch(
        "Data_Cleaning_Teams.preapprovals_op_final_shj_ajm.clean_sheet_data",
        side_effect=lambda value, sheet_name=None: value.copy(),
    ):
        return process_preapprovals_op_final_shj_ajm("source.xlsx")


def test_config_and_cleaner_are_registered_with_60_40_weights():
    config = load_team_config(TEAM)
    assert config["team"] == SHEET_NAME
    position = config["performance_levels"]["Employee"]["positions"]["OP Final"]
    assert [kpi["key"] for kpi in position["kpis"]] == [
        "initial_rejection_rate",
        "submission_within_tat",
    ]
    assert sum(kpi["weight"] for kpi in position["kpis"]) == pytest.approx(1.0)
    assert position["capping"] == "capped_at_100"
    assert all(kpi["cap_achievement"] is True for kpi in position["kpis"])
    assert config["missing_actual_exception"] == "initial_rejection_only"
    assert get_process_function(TEAM).__name__ == process_preapprovals_op_final_shj_ajm.__name__


def test_cleaner_uses_submitted_denominators_and_excludes_non_measurable_rows():
    cleaned = _clean(_source_rows())

    assert cleaned["HRID"].tolist() == ["SHJ-1", "AJM-1"]
    assert cleaned["Team"].tolist() == ["SHJ", "AJM"]
    assert cleaned.iloc[0]["A.InitialRejectionRate"] == pytest.approx(0.05)
    assert cleaned.iloc[0]["A.SubmissionWithinTATRate"] == pytest.approx(90 / 95)
    assert cleaned.iloc[0]["SubmittedRequestsExcludingManual"] == pytest.approx(95)
    assert pd.isna(cleaned.iloc[1]["A.SubmissionWithinTATRate"])
    assert bool(cleaned.iloc[1]["SubmissionWithinTATAvailable"]) is False


def test_missing_tat_exception_uses_initial_rejection_achievement_as_final_score():
    cleaned = _clean(_source_rows())
    service = KPIService(None, None, initialize_defaults=False)

    normal_score, _, normal_kpis = service.calculate_performance_multi_team(
        TEAM, cleaned.iloc[0].to_dict(), "Employee", "OP Final"
    )
    missing_tat_score, _, missing_tat_kpis = service.calculate_performance_multi_team(
        TEAM, cleaned.iloc[1].to_dict(), "Employee", "OP Final"
    )

    # 5% / 5% = 100% rejection achievement; TAT exceeds target but is capped
    # at 100% before its 40% contribution is calculated.
    assert normal_score == pytest.approx(100.0)
    assert normal_kpis[0]["achievement_ratio"] == pytest.approx(1.0)
    assert normal_kpis[1]["achievement_ratio"] == pytest.approx(1.0)
    assert [item["contribution"] for item in normal_kpis] == pytest.approx([0.6, 0.4])
    # 10% actual rejection against a 5% target => 50% final score by exception.
    assert missing_tat_score == pytest.approx(50.0)
    assert {item["kpi_key"] for item in normal_kpis} == {
        "initial_rejection_rate",
        "submission_within_tat",
    }
    assert missing_tat_kpis[1]["actual_value"] == pytest.approx(0.0)
