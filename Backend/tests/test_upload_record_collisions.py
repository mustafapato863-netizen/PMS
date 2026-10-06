"""One performance record per employee per month (PR #15 merge fix).

Production (live check #2, B1/B2): 16 Pre-Approvals IP Elective Dubai records
were saved as one merged record per agent carrying both sheets' KPI rows, with
an unscaled summed score (1.51-2.72, grade E); a May record carried both
Elective workstreams (171.77 when scaled).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import Employee as DBEmployee, KPIValue, PerformanceRecord as DBPerformanceRecord, Team, TeamKPIConfig
from models.schemas import Employee, EvaluationData, PerformanceRecord
from services.seeding_service import DatabaseSeeder
from services.upload_record_collisions import (
    WARNING_CODE,
    colliding_employee_ids,
    resolve_employee_month_collisions,
)

ELECTIVE = "Pre-Approvals IP Elective Dubai"
FINAL_DUBAI = "Pre-Approvals IP Final Dubai"


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine, tables=[
        Team.__table__, DBEmployee.__table__, DBPerformanceRecord.__table__, KPIValue.__table__, TeamKPIConfig.__table__,
    ])
    db = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


def _kpi(key, weight, achievement=1.0):
    return {"kpi_key": key, "label": key, "direction": "higher_better", "actual_value": achievement,
            "target_value": 1.0, "achievement_ratio": achievement, "weight_applied": weight,
            "contribution": achievement * weight}


def _record(team, position, kpis, *, employee_id="DUAL-1", month="May", score=100.0, grade="A"):
    return PerformanceRecord(
        id=f"{employee_id}_2026_{month}", employee_id=employee_id, employee_name="Dual Agent", team=team,
        month=month, year=2026, region="UAE", performance_level="Employee", position=position,
        evaluation=EvaluationData(score=score, grade=grade), kpi_values=kpis,
    )


def _employee(team, position, employee_id="DUAL-1"):
    return Employee(id=employee_id, name="Dual Agent", team=team, region="UAE", performance_level="Employee",
                    position=position)


def _final():
    return _record(FINAL_DUBAI, "Combined", [
        _kpi("combined_acceptance_rate", .5), _kpi("combined_submission_within_month", .3),
        _kpi("combined_discharge_within_one_hour", .2),
    ])


def _elective(position="IP Elective", achievement=.9):
    keys = {"IP Elective": ("ip_initial_rejection_rate", "approval_within_48_hours"),
            "ER / IP Approval": ("er_initial_rejection_rate", "approval_within_1_5_hours")}[position]
    return _record(ELECTIVE, position, [_kpi(keys[0], .6, achievement), _kpi(keys[1], .4, achievement)],
                   score=achievement * 100, grade="B")


def _stored(db):
    record = db.query(DBPerformanceRecord).one()
    team = db.query(Team).filter(Team.id == record.team_id).one()
    keys = {value.kpi_key for value in db.query(KPIValue).filter(KPIValue.record_id == record.id)}
    return record, team.name, keys


# ------------------------------------------------------------ pure resolver

def test_colliding_ids_only_flags_same_month_duplicates():
    may, june = _final(), _record(FINAL_DUBAI, "Combined", [], month="June")
    assert colliding_employee_ids([may, june]) == set()
    assert colliding_employee_ids([may, _elective()]) == {"DUAL-1"}


def test_no_collision_returns_input_unchanged():
    records = [_final(), _record(ELECTIVE, "IP Elective", [], employee_id="OTHER")]
    employees = [_employee(FINAL_DUBAI, "Combined")]
    assert resolve_employee_month_collisions(records, employees) == (records, employees, [])


def test_assigned_team_from_the_employee_master_wins():
    final, elective = _final(), _elective()
    kept, employees, warnings = resolve_employee_month_collisions(
        [final, elective], [_employee(FINAL_DUBAI, "Combined"), _employee(ELECTIVE, "IP Elective")],
        {"DUAL-1": (FINAL_DUBAI, "Combined")},
    )
    assert kept == [final]
    assert [employee.team for employee in employees] == [FINAL_DUBAI]
    [warning] = warnings
    assert warning["code"] == WARNING_CODE
    assert (warning["kept_team"], warning["ignored_sheet"], warning["reason"]) == (FINAL_DUBAI, ELECTIVE, "other_team_sheet")
    assert "DUAL-1" in warning["message"] and ELECTIVE in warning["message"]


def test_new_employee_is_scored_on_the_team_the_upload_assigns():
    # No stored assignment: employee sync keeps the last row's team (Elective).
    final, elective = _final(), _elective()
    kept, _employees, [warning] = resolve_employee_month_collisions(
        [final, elective], [_employee(FINAL_DUBAI, "Combined"), _employee(ELECTIVE, "IP Elective")], {},
    )
    assert kept == [elective]
    assert warning["ignored_sheet"] == FINAL_DUBAI


def test_same_sheet_duplicate_keeps_the_stored_position():
    # The 171.77 shape: one agent on both IP Elective workstream tables.
    er, ip = _elective("ER / IP Approval", .95), _elective("IP Elective", .8)
    kept, _employees, [warning] = resolve_employee_month_collisions(
        [er, ip], [_employee(ELECTIVE, "ER / IP Approval"), _employee(ELECTIVE, "IP Elective")],
        {"DUAL-1": (ELECTIVE, "ER / IP Approval")},
    )
    assert kept == [er]
    assert warning["reason"] == "same_sheet_duplicate"
    assert warning["ignored_position"] == "IP Elective"


# ------------------------------------------------------- DB sync (upload path)

def test_final_and_elective_rows_in_one_upload_are_not_merged(session):
    warnings = DatabaseSeeder()._sync_to_database(
        [_final(), _elective(achievement=.9)],
        [_employee(FINAL_DUBAI, "Combined"), _employee(ELECTIVE, "IP Elective")],
        db_session=session,
    )
    session.flush()
    record, team, keys = _stored(session)

    assert team == ELECTIVE
    assert keys == {"ip_initial_rejection_rate", "approval_within_48_hours"}
    # Elective KPIs only, on the 0-100 scale (was an unscaled 1.9 / E).
    assert float(record.score) == pytest.approx(90.0)
    assert record.grade == "B"
    assert [w["ignored_sheet"] for w in warnings] == [FINAL_DUBAI]


def test_stored_final_dubai_employee_keeps_final_dubai_and_drops_the_elective_row(session):
    team = Team(id=uuid.uuid4(), name=FINAL_DUBAI, db_name=FINAL_DUBAI, display_name=FINAL_DUBAI, region="UAE",
                team_level="employee", is_active=True)
    session.add(team)
    session.flush()
    session.add(DBEmployee(id=uuid.uuid4(), employee_id="DUAL-1", name="Dual Agent", team_id=team.id, region="UAE",
                           performance_level="Employee", position_name="Combined", is_active=True))
    session.flush()

    warnings = DatabaseSeeder()._sync_to_database(
        [_final(), _elective()],
        [_employee(FINAL_DUBAI, "Combined"), _employee(ELECTIVE, "IP Elective")],
        db_session=session,
    )
    session.flush()
    record, team_name, keys = _stored(session)

    assert team_name == FINAL_DUBAI
    assert keys == {"combined_acceptance_rate", "combined_submission_within_month", "combined_discharge_within_one_hour"}
    assert float(record.score) == pytest.approx(100.0)
    assert [w["ignored_sheet"] for w in warnings] == [ELECTIVE]


def test_two_elective_workstreams_never_sum_past_100(session):
    DatabaseSeeder()._sync_to_database(
        [_elective("ER / IP Approval", .95), _elective("IP Elective", .8)],
        [_employee(ELECTIVE, "ER / IP Approval"), _employee(ELECTIVE, "IP Elective")],
        db_session=session,
    )
    session.flush()
    record, _team, keys = _stored(session)
    assert len(keys) == 2
    assert 0 <= float(record.score) <= 100


# ------------------------------------------------------------ score scaling

class _KV:
    def __init__(self, contribution, weight):
        self.contribution, self.weight_applied = contribution, weight


def test_score_from_ratio_scale_rows_is_capped_at_100_not_stored_unscaled():
    # Merged rows summed to 1.92 on the ratio scale used to be stored as 1.92.
    rows = [_KV(.6, .6), _KV(.4, .4), _KV(.5, .5), _KV(.3, .3), _KV(.12, .2)]
    assert DatabaseSeeder._score_from_kpi_rows(rows) == 100.0
    assert DatabaseSeeder._score_from_kpi_rows([_KV(.54, .6), _KV(.36, .4)]) == pytest.approx(90.0)


def test_score_from_percent_scale_rows_stays_percent():
    assert DatabaseSeeder._score_from_kpi_rows([_KV(54.0, .6), _KV(36.0, .4)]) == pytest.approx(90.0)
    assert DatabaseSeeder._score_from_kpi_rows([_KV(0, .6), _KV(0, .4)]) == 0.0


# ------------------------------------------------------------- data-fix script

def _seed_merged(session, *, status="Below"):
    elective = Team(id=uuid.uuid4(), name=ELECTIVE, db_name=ELECTIVE, display_name=ELECTIVE, region="UAE",
                    team_level="employee", is_active=True)
    session.add(elective)
    session.flush()
    employee = DBEmployee(id=uuid.uuid4(), employee_id="TEST-EL-01", name="Agent", team_id=elective.id, region="UAE",
                          performance_level="Employee", position_name="ER / IP Approval", is_active=True)
    session.add(employee)
    session.flush()
    record = DBPerformanceRecord(
        id=uuid.uuid4(), year=2026, employee_id=employee.id, team_id=elective.id, month="April",
        performance_level="Employee", position_name="ER / IP Approval", region="UAE", score=1.92, grade="E",
        status=status, record_payload={"status": status, "evaluation": {"score": 1.92, "grade": "E"}, "kpi_values": [
            {"kpi_key": "er_initial_rejection_rate"}, {"kpi_key": "approval_within_1_5_hours"},
            {"kpi_key": "combined_acceptance_rate"},
        ]},
    )
    session.add(record)
    session.flush()
    for key, weight, contribution in (("er_initial_rejection_rate", .6, .6), ("approval_within_1_5_hours", .4, .34),
                                      ("combined_acceptance_rate", .5, .5)):
        session.add(KPIValue(id=uuid.uuid4(), record_id=record.id, record_year=2026, kpi_key=key, actual_value=1,
                             target_value=1, achievement_ratio=contribution / weight, weight_applied=weight,
                             contribution=contribution))
    session.flush()
    return record


def test_fix_script_dry_run_apply_idempotent_and_recomputes_status(session):
    from scripts.fix_merged_ip_elective_records import run

    record = _seed_merged(session)
    dry = run(session, apply=False)
    assert dry["records_to_fix"] == 1
    [change] = dry["changes"]
    assert change["score"] == [pytest.approx(1.92), pytest.approx(94.0)]
    assert change["grade"] == ["E", "B"]
    assert change["status"] == ["Below", "Meets"]
    assert change["reference_keys"] == ["combined_acceptance_rate"]
    assert float(session.get(DBPerformanceRecord, (record.id, 2026)).score) == pytest.approx(1.92)  # nothing written

    applied = run(session, apply=True)
    assert applied["records_to_fix"] == 1
    stored = session.get(DBPerformanceRecord, (record.id, 2026))
    assert (float(stored.score), stored.grade, stored.status) == (pytest.approx(94.0), "B", "Meets")
    assert {v.kpi_key for v in session.query(KPIValue)} == {"er_initial_rejection_rate", "approval_within_1_5_hours"}
    [reference] = stored.record_payload["reference_kpi_values"]
    assert reference["kpi_key"] == "combined_acceptance_rate" and reference["scoring"] is False
    assert all(v["kpi_key"] != "combined_acceptance_rate" for v in stored.record_payload["kpi_values"])

    again = run(session, apply=True)
    assert again["records_to_fix"] == 0
    assert again["already_clean"] == 1


# ------------------------------------------------- full upload (dry-run preflight)

def test_upload_with_agent_on_both_dubai_sheets_reports_a_warning_and_one_record():
    import io

    import pandas as pd

    final_rows = pd.DataFrame([{
        "Date": "2026-06-30", "HR ID": "DUAL-1", "Agent Name": "Dual Agent", "Status": "Active", "Team": "Dubai",
        "Assigned Request": 100, "Approved Requests": 100, "Submitted Within Month (Untill 3rd of next month)": 95,
        "Discharge Requests": 200, "Discharge Within Hour": 190,
        "A.Acceptance Rate": 1.0, "A.Submission Within Month %": 0.95, "A.Discharge % Within 1 Hour": 0.95,
        "Performance Score": 1.0, "Performance Grade": "Excellent",
    }])
    elective_rows = pd.DataFrame([{
        "Date": "2026-06-30", "Region": "UAE", "Role": "Emp", "HR ID": "DUAL-1", "Agent Name": "Dual Agent",
        "Status": "Active", "Assigned Requests": 100, "Approved Requests": 80, "Rejected Requests": 3,
        "Approval Within 48 HR": 60, "Approval Within 1.5 HR": "N/A", "Performance Grade": "C",
    }])
    workbook = io.BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        final_rows.to_excel(writer, sheet_name=FINAL_DUBAI, index=False)
        elective_rows.to_excel(writer, sheet_name=ELECTIVE, index=False)

    result = DatabaseSeeder().process_uploaded_file("PMS_Trend_All.xlsx", workbook.getvalue(), dry_run=True)

    assert result["records_imported"] == 1
    assert result["employees_imported"] == 1
    [warning] = result["warnings"]
    assert warning["code"] == WARNING_CODE
    assert warning["employee_id"] == "DUAL-1"
    assert {warning["kept_team"], warning["ignored_sheet"]} == {FINAL_DUBAI, ELECTIVE}
