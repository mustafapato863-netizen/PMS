import io
from unittest.mock import patch

import pandas as pd
import pytest

from config.loader import load_team_config
from data_cleaning.cleaner_factory import get_process_function
from Data_Cleaning_Teams.preapprovals_ip_final_shj_ajm import (
    POSITION,
    SHEET_NAME,
    process_preapprovals_ip_final_shj_ajm,
)
from services.kpi_service import KPIService
from services.seeding_service import DatabaseSeeder


TEAM = "Pre-Approvals IP Final SHJAJM"


def _source_rows() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Date": "2026-06-30", "HR ID": "SHJ-1", "Agent Name": "SHJ Agent",
            "Status": "Active", "Team": "SHJ", "Assigned Request": 100,
            "Approved Requests": 95, "Rejected Requests": 5,
            "Submitted Within Month (Untill 3rd of next month)": 90,
            "T.Acceptance Rate": 1.0, "T.Submission Within Month %": 1.0,
            "Performance Grade": "B",
        },
        {
            "Date": "2026-06-30", "HR ID": "AJM-1", "Agent Name": "AJM Agent",
            "Status": "Active", "Team": "AJM", "Assigned Request": 100,
            "Approved Requests": 90, "Rejected Requests": 10,
            "Submitted Within Month (Untill 3rd of next month)": 82,
            "T.Acceptance Rate": 1.0, "T.Submission Within Month %": 1.0,
            "Performance Grade": "C",
        },
        {
            "HR ID": "LEAVE-1", "Agent Name": "Leave Agent", "Status": "Leave",
            "Team": "SHJ", "Performance Grade": "Leave",
        },
        {
            "HR ID": None, "Agent Name": None, "Status": None,
            "Team": None, "Performance Grade": None,
        },
    ])


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    with patch(
        "Data_Cleaning_Teams.preapprovals_ip_final_shj_ajm.pd.read_excel",
        return_value=frame.copy(),
    ), patch(
        "Data_Cleaning_Teams.preapprovals_ip_final_shj_ajm.clean_sheet_data",
        side_effect=lambda value, sheet_name=None: value.copy(),
    ):
        return process_preapprovals_ip_final_shj_ajm("source.xlsx")


def test_config_and_cleaner_are_registered_with_40_60_weights():
    config = load_team_config(TEAM)
    position = config["performance_levels"]["Employee"]["positions"][POSITION]

    assert config["team"] == SHEET_NAME
    assert [kpi["key"] for kpi in position["kpis"]] == [
        "ip_final_acceptance_rate",
        "ip_final_submission_within_month",
    ]
    assert [kpi["weight"] for kpi in position["kpis"]] == pytest.approx([0.4, 0.6])
    assert position["capping"] == "capped_at_100"
    assert get_process_function(TEAM).__name__ == process_preapprovals_ip_final_shj_ajm.__name__


def test_cleaner_uses_raw_counters_and_excludes_non_measurable_rows():
    cleaned = _clean(_source_rows())

    assert cleaned["HRID"].tolist() == ["SHJ-1", "AJM-1"]
    assert cleaned["Team"].tolist() == ["SHJ", "AJM"]
    assert cleaned["Position"].tolist() == [POSITION, POSITION]
    assert cleaned.iloc[0]["AcceptanceRate"] == pytest.approx(0.95)
    assert cleaned.iloc[0]["SubmissionWithinMonth%"] == pytest.approx(0.90)
    assert cleaned.iloc[0]["AcceptanceRateAchievement"] == pytest.approx(0.75)
    assert cleaned.iloc[0]["SubmissionWithinMonthAchievement"] == pytest.approx(0.5)


def test_scoring_matches_the_80_percent_baseline_formula():
    cleaned = _clean(_source_rows())
    service = KPIService(None, None, initialize_defaults=False)

    first_score, _, first_kpis = service.calculate_performance_multi_team(
        TEAM, cleaned.iloc[0].to_dict(), "Employee", POSITION
    )
    second_score, _, _ = service.calculate_performance_multi_team(
        TEAM, cleaned.iloc[1].to_dict(), "Employee", POSITION
    )

    assert first_score == pytest.approx((0.75 * 0.4 + 0.5 * 0.6) * 100)
    assert second_score == pytest.approx(
        (((0.90 - 0.80) / 0.20) * 0.4 + ((0.82 - 0.80) / 0.20) * 0.6) * 100
    )
    assert sum(item["contribution"] for item in first_kpis) == pytest.approx(first_score / 100)


def test_dry_run_imports_only_active_shj_ajm_rows():
    workbook = io.BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        _source_rows().to_excel(writer, sheet_name=SHEET_NAME, index=False)

    result = DatabaseSeeder().process_uploaded_file(
        "PMS_Trend_All.xlsx", workbook.getvalue(), dry_run=True
    )
    assert result["records_imported"] == 2
    assert result["employees_imported"] == 2
    assert result["teams"] == [TEAM]
    assert result["failed_teams"] == []
