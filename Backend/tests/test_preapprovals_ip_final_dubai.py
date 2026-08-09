import io
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers import router as api_router
from config.database import Base
from config.loader import load_team_config
from data_cleaning.cleaner_factory import get_process_function
from Data_Cleaning_Teams.preapprovals_ip_final_dubai import (
    COMBINED,
    IP_APPROVAL,
    IP_DISCHARGE,
    process_preapprovals_ip_final_dubai,
)
from services.kpi_service import KPIService
from services.seeding_service import DatabaseSeeder
from models.models import Employee as DBEmployee, KPIValue, PerformanceRecord as DBPerformanceRecord, Team, TeamKPIConfig
from models.schemas import Employee, EvaluationData, PerformanceRecord


app = FastAPI()
app.include_router(api_router, prefix="/api")
client = TestClient(app)


def _source_rows() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Date": "2026-02-28", "HR ID": "COMBINED-1", "Agent Name": "Combined Agent", "Status": "Active", "Team": "Dubai",
            "Assigned Request": 274, "Approved Requests": 274, "Submitted Within Month (Untill 3rd of next month)": 271,
            "Discharge Requests": 612, "Discharge Within Hour": 578,
            "A.Acceptance Rate": 1.0, "A.Submission Within Month %": 0.96, "A.Discharge % Within 1 Hour": 0.93,
            "Performance Score": 1.0766930251419302,
            "Performance Grade": "Excellent",
        },
        {
            "Date": "2026-02-28", "HR ID": "APPROVAL-1", "Agent Name": "Approval Agent", "Status": "Active", "Team": "Dubai",
            "Assigned Request": 53, "Approved Requests": 53, "Submitted Within Month (Untill 3rd of next month)": 49,
            "Discharge Requests": None, "Discharge Within Hour": None,
            "A.Acceptance Rate": 1.0, "A.Submission Within Month %": 0.96, "A.Discharge % Within 1 Hour": None,
            "Performance Score": 0.9113207547169813,
            "Performance Grade": "Meet Expectations",
        },
        {
            "Date": "2026-05-31", "HR ID": "DISCHARGE-1", "Agent Name": "Discharge Agent", "Status": "Active", "Team": "Dubai",
            "Assigned Request": 0, "Approved Requests": 0, "Submitted Within Month (Untill 3rd of next month)": 0,
            "Discharge Requests": 494, "Discharge Within Hour": 472,
            "A.Acceptance Rate": 1.0, "A.Submission Within Month %": 1.0, "A.Discharge % Within 1 Hour": 0.945054945054945,
            "Performance Score": 1.0717703349282302,
            "Performance Grade": "Excellent",
        },
        {"Date": "2026-05-31", "HR ID": "LEAVE-1", "Agent Name": "Leave Agent", "Status": "Leave", "Performance Grade": "Leave"},
    ])


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    with patch("Data_Cleaning_Teams.preapprovals_ip_final_dubai.pd.read_excel", return_value=frame), patch(
        "Data_Cleaning_Teams.preapprovals_ip_final_dubai.clean_sheet_data", side_effect=lambda value, sheet_name=None: value.copy()
    ):
        return process_preapprovals_ip_final_dubai("source.xlsx")


def test_config_and_cleaner_are_registered_with_three_weight_sets():
    config = load_team_config("Pre-Approvals IP Final Dubai")
    positions = config["performance_levels"]["Employee"]["positions"]
    assert set(positions) == {COMBINED, IP_APPROVAL, IP_DISCHARGE}
    assert [sum(kpi["weight"] for kpi in value["kpis"]) for value in positions.values()] == pytest.approx([1.0, 1.0, 1.0])
    assert all(value["capping"] == "capped_at_100" for value in positions.values())
    assert get_process_function("Pre-Approvals IP Final Dubai").__name__ == process_preapprovals_ip_final_dubai.__name__


def test_cleaner_derives_activity_and_baseline_achievements():
    cleaned = _clean(_source_rows())
    assert cleaned["Position"].tolist() == [COMBINED, IP_APPROVAL, IP_DISCHARGE]
    assert cleaned["Region"].tolist() == ["UAE", "UAE", "UAE"]
    assert cleaned.iloc[0]["T.%ofSubmissionWithinDuedate"] == pytest.approx(1.0)
    assert cleaned.iloc[1]["T.AcceptanceRate%"] == pytest.approx(1.0)
    assert cleaned.iloc[2]["T.Discharge%Within1Hour"] == pytest.approx(1.0)


def test_scoring_matches_source_workbook_and_caps_achievement():
    cleaned = _clean(_source_rows())
    service = KPIService(None, None, initialize_defaults=False)
    scores = {}
    for _, row in cleaned.iterrows():
        score, _, kpis = service.calculate_performance_multi_team(
            "Pre-Approvals IP Final Dubai", row.to_dict(), "Employee", row["Position"]
        )
        scores[row["Position"]] = score
        assert sum(item["contribution"] for item in kpis) == pytest.approx(score / 100, abs=0.0001)

    assert scores[COMBINED] == pytest.approx(100.0)
    assert scores[IP_APPROVAL] == pytest.approx(91.1320755)
    assert scores[IP_DISCHARGE] == pytest.approx(100.0)


def test_dry_run_imports_only_active_rows():
    workbook = io.BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        _source_rows().to_excel(writer, sheet_name="Pre-Approvals IP Final Dubai", index=False)
    result = DatabaseSeeder().process_uploaded_file("PMS_Trend_All.xlsx", workbook.getvalue(), dry_run=True)
    assert result["records_imported"] == 3
    assert result["employees_imported"] == 3
    assert result["teams"] == ["Pre-Approvals IP Final Dubai"]
    assert result["failed_teams"] == []


def test_team_is_discoverable_from_config_api():
    response = client.get("/api/config/teams")
    assert response.status_code == 200
    payload = response.json()
    team = next(item for item in payload["data"] if item["team"] == "Pre-Approvals IP Final Dubai")
    assert team["db_name"] == "Pre-Approvals IP Final Dubai"
    assert team["region"] == "UAE"
    assert set(team["performance_levels"]["Employee"]["positions"]) == {COMBINED, IP_APPROVAL, IP_DISCHARGE}


def test_database_sync_creates_team_and_position_configuration_atomically():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine, tables=[Team.__table__, DBEmployee.__table__, DBPerformanceRecord.__table__, KPIValue.__table__, TeamKPIConfig.__table__])
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        row = _clean(_source_rows()).iloc[0]
        score, grade, kpis = KPIService(None, None, initialize_defaults=False).calculate_performance_multi_team(
            "Pre-Approvals IP Final Dubai", row.to_dict(), "Employee", row["Position"]
        )
        employee = Employee(id=row["HRID"], name=row["AgentName"], team="Pre-Approvals IP Final Dubai", region="UAE", performance_level="Employee", position=row["Position"])
        record = PerformanceRecord(
            id=f"{row['HRID']}_2026_January", employee_id=row["HRID"], employee_name=row["AgentName"],
            team="Pre-Approvals IP Final Dubai", month="January", year=2026, region="UAE",
            performance_level="Employee", position=row["Position"], evaluation=EvaluationData(score=score, grade=grade), kpi_values=kpis,
        )
        DatabaseSeeder()._sync_to_database([record], [employee], db_session=session)
        session.flush()
        assert session.query(Team).one().display_name == "Pre-Approvals IP Final Dubai"
        assert session.query(TeamKPIConfig).count() == 6
        assert session.query(DBPerformanceRecord).one().position_name == COMBINED
        assert session.query(KPIValue).count() == 3
    finally:
        session.rollback()
        session.close()
