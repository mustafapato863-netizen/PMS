import io
from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.loader import load_team_config, resolve_team_config
from data_cleaning.cleaner_factory import get_process_function
from Data_Cleaning_Teams.preapprovals_op_dubai import (
    CALLS,
    FINAL_SUBMISSION,
    INITIAL_SUBMISSION,
    process_preapprovals_op_dubai,
)
from services.kpi_service import KPIService
from services.seeding_service import DatabaseSeeder
from config.database import Base
from models.models import (
    Employee as DBEmployee,
    KPIValue,
    PerformanceRecord as DBPerformanceRecord,
    Team,
    TeamKPIConfig,
)
from models.schemas import Employee, EvaluationData, PerformanceRecord


def _source_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Date": "2026-05-31",
                "Region": "UAE",
                "Role": "Emp",
                "HR ID": "INITIAL-1",
                "Agent Name": "Initial Agent",
                "Status": "Active",
                "Assigned Request": 100,
                "Submitted Requests": 100,
                "Submitted Within Day": "N/A",
                "Submitted Within Hour": 80,
                "Rejected Requests": 10,
                "Total Number Of Calls per Day ": "N/A",
                "Total Attended Calls Per Day ": "N/A",
                "Total Abandoned Calls Per Day": "N/A",
                "T.Initial Rejection": 0.05,
                "T.Submission Within Hour %": 0.70,
                "T. % Abandoned Calls": "N/A",
                "T.% of Attended Calls ": "N/A",
            },
            {
                "Date": "2026-05-31",
                "Region": "UAE",
                "Role": "Emp",
                "HR ID": "FINAL-1",
                "Agent Name": "Final Agent",
                "Status": "Active",
                "Assigned Request": 100,
                "Submitted Requests": 100,
                "Submitted Within Day": 80,
                "Submitted Within Hour": "N/A",
                "Rejected Requests": 5,
                "Total Number Of Calls per Day ": "N/A",
                "Total Attended Calls Per Day ": "N/A",
                "Total Abandoned Calls Per Day": "N/A",
                "T.Initial Rejection": 0.10,
                "T.Submission Within Hour %": 1.0,
                "T. % Abandoned Calls": "N/A",
                "T.% of Attended Calls ": "N/A",
            },
            {
                "Date": "2026-05-31",
                "Region": "UAE",
                "Role": "Emp",
                "HR ID": "CALLS-1",
                "Agent Name": "Calls Agent",
                "Status": "Active",
                "Assigned Request": "N/A",
                "Submitted Requests": "N/A",
                "Submitted Within Day": "N/A",
                "Submitted Within Hour": "N/A",
                "Rejected Requests": "N/A",
                "Total Number Of Calls per Day ": 100,
                "Total Attended Calls Per Day ": 80,
                "Total Abandoned Calls Per Day": 0,
                "T.Initial Rejection": "N/A",
                "T.Submission Within Hour %": "N/A",
                "T. % Abandoned Calls": 0.01,
                "T.% of Attended Calls ": 0.90,
            },
            {
                "Date": "2026-05-31",
                "Region": "UAE",
                "Role": "Emp",
                "HR ID": "LEAVE-1",
                "Agent Name": "Leave Agent",
                "Status": "Leave",
            },
        ]
    )


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    with patch(
        "Data_Cleaning_Teams.preapprovals_op_dubai.pd.read_excel",
        return_value=frame,
    ), patch(
        "Data_Cleaning_Teams.preapprovals_op_dubai.clean_sheet_data",
        side_effect=lambda value, sheet_name=None: value.copy(),
    ):
        return process_preapprovals_op_dubai("source.xlsx")


def test_config_defines_independent_position_weight_sets():
    config = load_team_config("Pre-Approvals OP Dubai")
    positions = config["performance_levels"]["Employee"]["positions"]

    assert set(positions) == {INITIAL_SUBMISSION, FINAL_SUBMISSION, CALLS}
    for position, definition in positions.items():
        assert sum(kpi["weight"] for kpi in definition["kpis"]) == pytest.approx(1.0), position
        assert definition["capping"] == "capped_at_100"

    final_keys = {kpi["key"] for kpi in positions[FINAL_SUBMISSION]["kpis"]}
    assert final_keys == {"submission_within_due_date"}
    assert "Final Rejection Rate is excluded" in config["configuration_notes"][1]
    assert get_process_function("Pre-Approvals OP Dubai").__name__ == process_preapprovals_op_dubai.__name__


def test_cleaner_derives_workstreams_rates_and_excludes_leave():
    cleaned = _clean(_source_rows())

    assert cleaned["Position"].tolist() == [INITIAL_SUBMISSION, FINAL_SUBMISSION, CALLS]
    assert cleaned["HRID"].tolist() == ["INITIAL-1", "FINAL-1", "CALLS-1"]

    initial, final, calls = [row for _, row in cleaned.iterrows()]
    assert initial["A.InitialRejectionRate"] == pytest.approx(0.10)
    assert initial["A.SubmissionWithinHourRate"] == pytest.approx(0.80)
    assert final["A.SubmissionWithinDueDateRate"] == pytest.approx(0.80)
    assert final["T.SubmissionWithinDueDateRate"] == pytest.approx(1.0)
    assert calls["A.AbandonedCallsRate"] == pytest.approx(0.0)
    assert calls["A.AttendedCallsRate"] == pytest.approx(0.80)


def test_cleaner_rejects_active_rows_without_a_workstream():
    frame = _source_rows().iloc[[0]].copy()
    frame.loc[:, "Submitted Requests"] = "N/A"
    frame.loc[:, "Submitted Within Hour"] = "N/A"

    with pytest.raises(ValueError, match="Cannot determine.*INITIAL-1"):
        _clean(frame)


def test_position_scoring_uses_capped_canonical_formulas():
    cleaned = _clean(_source_rows())
    service = KPIService(None, None, initialize_defaults=False)
    results = {}

    for _, row in cleaned.iterrows():
        score, grade, kpis = service.calculate_performance_multi_team(
            "Pre-Approvals OP Dubai",
            row.to_dict(),
            "Employee",
            row["Position"],
        )
        results[row["Position"]] = (score, grade, kpis)

    initial_score, _, initial_kpis = results[INITIAL_SUBMISSION]
    assert initial_score == pytest.approx(70.0)
    assert {item["kpi_key"] for item in initial_kpis} == {
        "initial_rejection_rate",
        "submission_within_hour",
    }

    final_score, _, final_kpis = results[FINAL_SUBMISSION]
    assert final_score == pytest.approx(80.0)
    assert [item["kpi_key"] for item in final_kpis] == ["submission_within_due_date"]

    calls_score, calls_grade, _ = results[CALLS]
    assert calls_score == pytest.approx(95.5556, abs=0.01)
    assert calls_grade == "A"


def test_score_is_capped_at_100():
    service = KPIService(None, None, initialize_defaults=False)
    config = resolve_team_config(
        load_team_config("Pre-Approvals OP Dubai"),
        "Employee",
        INITIAL_SUBMISSION,
    )
    row = {
        "A.InitialRejectionRate": 0.01,
        "T.InitialRejectionRate": 0.05,
        "A.SubmissionWithinHourRate": 1.0,
        "T.SubmissionWithinHourRate": 0.7,
    }

    score, grade, kpis = service.calculate_performance_multi_team(
        config["team"], row, "Employee", INITIAL_SUBMISSION
    )

    assert score == 100.0
    assert grade == "A"
    assert sum(item["contribution"] for item in kpis) == pytest.approx(1.0)


def test_dry_run_detects_and_processes_only_active_rows():
    workbook = io.BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        _source_rows().to_excel(writer, sheet_name="Pre-Approvals OP Dubai", index=False)

    result = DatabaseSeeder().process_uploaded_file(
        "PMS_Trend_All.xlsx",
        workbook.getvalue(),
        dry_run=True,
    )

    assert result["records_imported"] == 3
    assert result["employees_imported"] == 3
    assert result["teams"] == ["Pre-Approvals OP Dubai"]
    assert result["persisted_teams"] == ["Pre-Approvals OP Dubai"]
    assert result["failed_teams"] == []


def test_database_sync_reactivates_team_and_persists_position_configuration():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Team.__table__,
            DBEmployee.__table__,
            DBPerformanceRecord.__table__,
            KPIValue.__table__,
            TeamKPIConfig.__table__,
        ],
    )
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        existing_team = Team(
            name="pre_approvals_op_dubai",
            db_name="Pre-Approvals OP Dubai",
            region="UAE",
            team_level="employee",
            is_active=False,
        )
        session.add(existing_team)
        session.flush()

        cleaned = _clean(_source_rows()).iloc[[0]]
        row = cleaned.iloc[0]
        service = KPIService(None, None, initialize_defaults=False)
        score, grade, kpis = service.calculate_performance_multi_team(
            "Pre-Approvals OP Dubai",
            row.to_dict(),
            "Employee",
            row["Position"],
        )
        employee = Employee(
            id=row["HRID"],
            name=row["AgentName"],
            team="Pre-Approvals OP Dubai",
            region="UAE",
            performance_level="Employee",
            position=row["Position"],
        )
        record = PerformanceRecord(
            id=f"{row['HRID']}_2026_May",
            employee_id=row["HRID"],
            employee_name=row["AgentName"],
            team="Pre-Approvals OP Dubai",
            month="May",
            year=2026,
            region="UAE",
            performance_level="Employee",
            position=row["Position"],
            status="Meets",
            evaluation=EvaluationData(score=score, grade=grade),
            kpi_values=kpis,
        )

        DatabaseSeeder()._sync_to_database([record], [employee], db_session=session)
        session.flush()

        assert session.query(Team).count() == 1
        persisted_team = session.query(Team).one()
        assert persisted_team.id == existing_team.id
        assert persisted_team.display_name == "Pre-Approvals OP Dubai"
        assert persisted_team.is_active is True
        assert session.query(TeamKPIConfig).count() == 5
        weights_by_position = {}
        for config in session.query(TeamKPIConfig).all():
            weights_by_position.setdefault(config.position_name, 0.0)
            weights_by_position[config.position_name] += float(config.weight)
        assert weights_by_position == {
            INITIAL_SUBMISSION: pytest.approx(1.0),
            FINAL_SUBMISSION: pytest.approx(1.0),
            CALLS: pytest.approx(1.0),
        }
        assert session.query(DBEmployee).one().position_name == INITIAL_SUBMISSION
        assert session.query(DBPerformanceRecord).one().position_name == INITIAL_SUBMISSION
        assert session.query(KPIValue).count() == 2
    finally:
        session.rollback()
        session.close()
