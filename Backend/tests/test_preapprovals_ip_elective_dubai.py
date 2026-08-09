import io
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import router as api_router
from config.loader import load_team_config, resolve_team_config
from data_cleaning.cleaner_factory import get_process_function
from Data_Cleaning_Teams.preapprovals_ip_elective_dubai import (
    ER_IP_APPROVAL,
    IP_ELECTIVE,
    process_preapprovals_ip_elective_dubai,
)
from services.kpi_service import KPIService
from services.seeding_service import DatabaseSeeder


TEAM = "Pre-Approvals IP Elective Dubai"


def _source_rows() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Date": "2026-06-30", "Region": "UAE", "Role": "Emp",
            "HR ID": "IP-1", "Agent Name": "IP Agent", "Status": "Active",
            "Assigned Requests": 100, "Approved Requests": 80, "Rejected Requests": 3,
            "Approval Within 48 HR": 60, "Approval Within 1.5 HR": "N/A",
            "Performance Grade": "C",
        },
        {
            "Date": "2026-06-30", "Region": "UAE", "Role": "Emp",
            "HR ID": "ER-1", "Agent Name": "ER Agent", "Status": "Active",
            "Assigned Requests": 100, "Approved Requests": 100, "Rejected Requests": 0,
            "Approval Within 48 HR": "N/A", "Approval Within 1.5 HR": 90,
            "Performance Grade": "A",
        },
        {
            "HR ID": "LEAVE-1", "Agent Name": "Leave Agent", "Status": "Leave",
            "Performance Grade": "Leave",
        },
        {
            "HR ID": "NEW-1", "Agent Name": "New Agent", "Status": "New Staff",
            "Performance Grade": "New Staff",
        },
        {
            "HR ID": "DASH-1", "Agent Name": "Dash Agent", "Status": "Active",
            "Assigned Requests": 10, "Approved Requests": 10, "Rejected Requests": 0,
            "Approval Within 48 HR": 10, "Approval Within 1.5 HR": "N/A",
            "Performance Grade": "-",
        },
    ])


def _combined_source_rows() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Date": "2026-06-30", "Region": "UAE", "Role": "Emp",
            "HR ID": "COMBINED-IP", "Agent Name": "Combined IP", "Status": "Active",
            "Assigned Request": 100, "Approved Requests": 80, "Rejected Requests": 3,
            "Approval Within 48 HR/1.5 HR": 60,
            "T.Initial Rejection %": 0.06,
            "T.% Of Approval within 48 HR/1.5 HR": 0.75,
            "Performance Grade": "C",
        },
        {
            "Date": "2026-06-30", "Region": "UAE", "Role": "Emp",
            "HR ID": "COMBINED-ER", "Agent Name": "Combined ER", "Status": "Active",
            "Assigned Request": 100, "Approved Requests": 100, "Rejected Requests": 1,
            "Approval Within 48 HR/1.5 HR": 90,
            "T.Initial Rejection %": 0.03,
            "T.% Of Approval within 48 HR/1.5 HR": 1.0,
            "Performance Grade": "B",
        },
    ])


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    with patch(
        "Data_Cleaning_Teams.preapprovals_ip_elective_dubai.pd.read_excel",
        return_value=frame.copy(),
    ), patch(
        "Data_Cleaning_Teams.preapprovals_ip_elective_dubai.clean_sheet_data",
        side_effect=lambda value, sheet_name=None: value.copy(),
    ):
        return process_preapprovals_ip_elective_dubai("source.xlsx")


def test_config_and_cleaner_are_registered_with_two_capped_workstreams():
    config = load_team_config(TEAM)
    positions = config["performance_levels"]["Employee"]["positions"]

    assert set(positions) == {IP_ELECTIVE, ER_IP_APPROVAL}
    assert all(sum(kpi["weight"] for kpi in definition["kpis"]) == pytest.approx(1.0) for definition in positions.values())
    assert all(definition["capping"] == "capped_at_100" for definition in positions.values())
    assert config["configuration_notes"][2].find("1.5 hours") >= 0
    assert get_process_function(TEAM).__name__ == process_preapprovals_ip_elective_dubai.__name__


def test_cleaner_selects_workstream_and_excludes_status_or_grade_rows():
    cleaned = _clean(_source_rows())

    assert cleaned["HRID"].tolist() == ["IP-1", "ER-1"]
    assert cleaned["Position"].tolist() == [IP_ELECTIVE, ER_IP_APPROVAL]
    assert cleaned.iloc[0]["A.IPInitialRejectionRate"] == pytest.approx(0.03)
    assert cleaned.iloc[0]["A.ApprovalWithin48HoursRate"] == pytest.approx(0.75)
    assert cleaned.iloc[1]["A.ERInitialRejectionRate"] == pytest.approx(0.0)
    assert cleaned.iloc[1]["A.ApprovalWithin1.5HoursRate"] == pytest.approx(0.90)
    assert cleaned.iloc[0]["T.ApprovalWithin48HoursRate"] == pytest.approx(0.75)
    assert cleaned.iloc[1]["T.ApprovalWithin1.5HoursRate"] == pytest.approx(1.0)


def test_cleaner_supports_real_combined_turnaround_column_and_historical_targets():
    cleaned = _clean(_combined_source_rows())

    assert cleaned["Position"].tolist() == [IP_ELECTIVE, ER_IP_APPROVAL]
    assert cleaned.iloc[0]["T.IPInitialRejectionRate"] == pytest.approx(0.06)
    assert cleaned.iloc[0]["T.ApprovalWithin48HoursRate"] == pytest.approx(0.75)
    assert cleaned.iloc[1]["T.ERInitialRejectionRate"] == pytest.approx(0.03)
    assert cleaned.iloc[1]["T.ApprovalWithin1.5HoursRate"] == pytest.approx(1.0)


def test_cleaner_uses_both_target_columns_and_rejects_unknown_pairs():
    source = _combined_source_rows().iloc[[0]].copy()
    source.loc[:, "T.Initial Rejection %"] = 0.03
    source.loc[:, "T.% Of Approval within 48 HR/1.5 HR"] = 0.75
    cleaned = _clean(source)
    assert cleaned.iloc[0]["Position"] == IP_ELECTIVE

    unsupported = source.copy()
    unsupported.loc[:, "T.Initial Rejection %"] = 0.02
    with pytest.raises(ValueError, match="Unsupported target pair"):
        _clean(unsupported)

    mismatched = source.copy()
    mismatched.loc[:, "T.Initial Rejection %"] = 0.06
    mismatched.loc[:, "T.% Of Approval within 48 HR/1.5 HR"] = 1.0
    with pytest.raises(ValueError, match="Unsupported target pair"):
        _clean(mismatched)


def test_real_header_row_is_read_from_second_excel_row():
    workbook = io.BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        pd.DataFrame([["Updated Pre-Approvals IP Elective KPI Table"]]).to_excel(
            writer,
            sheet_name=TEAM,
            index=False,
            header=False,
            startrow=0,
        )
        _combined_source_rows().to_excel(
            writer,
            sheet_name=TEAM,
            index=False,
            startrow=1,
        )

    cleaned = process_preapprovals_ip_elective_dubai(workbook.getvalue())
    assert len(cleaned) == 2
    assert cleaned["Position"].tolist() == [IP_ELECTIVE, ER_IP_APPROVAL]


def test_cleaner_rejects_ambiguous_or_missing_workstream():
    ambiguous = _source_rows().iloc[[0]].copy()
    ambiguous.loc[:, "Approval Within 1.5 HR"] = 40
    with pytest.raises(ValueError, match=r"IP-1.*both turnaround numerators"):
        _clean(ambiguous)

    missing = _source_rows().iloc[[0]].copy()
    missing.loc[:, "Approval Within 48 HR"] = "N/A"
    missing.loc[:, "Approval Within 1.5 HR"] = "N/A"
    with pytest.raises(ValueError, match=r"IP-1.*no turnaround numerator"):
        _clean(missing)


def test_scoring_matches_both_formula_variants_and_caps_scores():
    cleaned = _clean(_source_rows())
    service = KPIService(None, None, initialize_defaults=False)
    scores = {}
    for _, row in cleaned.iterrows():
        score, _, kpis = service.calculate_performance_multi_team(TEAM, row.to_dict(), "Employee", row["Position"])
        scores[row["Position"]] = (score, kpis)

    assert scores[IP_ELECTIVE][0] == pytest.approx(100.0)
    assert scores[ER_IP_APPROVAL][0] == pytest.approx(96.0)

    config = resolve_team_config(load_team_config(TEAM), "Employee", IP_ELECTIVE)
    assert config["capping"] == "capped_at_100"
    above_target = {
        "A.IPInitialRejectionRate": 0.01,
        "T.IPInitialRejectionRate": 0.03,
        "A.ApprovalWithin48HoursRate": 1.0,
        "T.ApprovalWithin48HoursRate": 0.75,
    }
    score, _, kpis = service.calculate_performance_multi_team(TEAM, above_target, "Employee", IP_ELECTIVE)
    assert score == pytest.approx(100.0)
    assert sum(item["contribution"] for item in kpis) == pytest.approx(score / 100, abs=0.0001)


def test_dry_run_imports_only_active_rows_for_the_new_sheet():
    workbook = io.BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        _source_rows().to_excel(writer, sheet_name=TEAM, index=False)

    result = DatabaseSeeder().process_uploaded_file("PMS_Trend_All.xlsx", workbook.getvalue(), dry_run=True)

    assert result["records_imported"] == 2
    assert result["employees_imported"] == 2
    assert result["teams"] == [TEAM]
    assert result["persisted_teams"] == [TEAM]
    assert result["failed_teams"] == []


def test_team_is_discoverable_from_config_api():
    app = FastAPI()
    app.include_router(api_router, prefix="/api")
    response = TestClient(app).get("/api/config/teams")

    assert response.status_code == 200
    payload = response.json()
    team = next(item for item in payload["data"] if item["team"] == TEAM)
    assert team["db_name"] == TEAM
    assert set(team["performance_levels"]["Employee"]["positions"]) == {IP_ELECTIVE, ER_IP_APPROVAL}
