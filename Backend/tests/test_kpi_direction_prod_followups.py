"""PR #15 follow-ups from the production read-only check (2026-10-06).

1. Inbound ``Other``: 157 records saved as Utilization / higher_better although
   they were scored on Abandon Rate (lower_better).
2. Pre-Approvals IP Elective Dubai records carrying IP Final Dubai KPI keys.
"""
from __future__ import annotations

import datetime
import math
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import utils.kpi_direction as kd
from config.database import Base
from config.loader import load_team_config
from models.models import Employee as DBEmployee, KPIValue, PerformanceRecord as DBPerformanceRecord, Team, TeamKPIConfig
from models.schemas import Employee, EvaluationData, PerformanceRecord
from services.dashboard_record_service import DashboardRecordService
from services.kpi_service import KPIService
from services.legacy_kpi_evidence import build_legacy_employee_kpi_values
from services.seeding_service import DatabaseSeeder


ELECTIVE = "Pre-Approvals IP Elective Dubai"
FINAL_DUBAI = "Pre-Approvals IP Final Dubai"


@pytest.fixture(autouse=True)
def _fresh_direction_cache():
    kd.clear_kpi_direction_cache()
    yield
    kd.clear_kpi_direction_cache()


class _EmptyRepo:
    def get_by_team(self, _team):
        return None


def _kpi_service():
    return KPIService(_EmptyRepo(), _EmptyRepo())


def _inbound_row(**extra):
    row = {
        "Date": datetime.datetime(2026, 5, 1),
        "TotalHandledCalls": 100,
        "Dubai_Booking": 45,
        "Dubai_Attend": 30,
        "InboundCalls": 100,
        "AbandonedCalls": 3,  # 3% abandon vs 1% target -> achievement 1/3
        "A.QualityScore": 0.97,
        "AHT_Minutes": 2.7,
    }
    row.update(extra)
    return row


def _inbound_grade(score):
    thresholds = load_team_config("Inbound")["grade_thresholds"]
    return next((grade for grade in ("A", "B", "C", "D") if score >= thresholds[grade]), "E")


def _json_safe(row):
    return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()}


def _legacy_saved_inbound_record(row, achievements, weights):
    """Recreate what pre-fix uploads persisted for an Inbound row without UTZ.

    The old ``KPIService`` wrote ``A.UTZ% = 0.0`` / ``UTZ%Ach% = 0.0`` into the
    row and the evidence builder then labelled ``Other`` as Utilization /
    higher_better while keeping the Abandon achievement and contribution.
    """
    raw = _json_safe(row)
    raw["A.UTZ%"] = 0.0
    raw["UTZ%Ach%"] = 0.0
    config = load_team_config("Inbound")
    values = build_legacy_employee_kpi_values("Inbound", raw, achievements=achievements, weights=weights, config=config)
    for value in values:
        if value["kpi_key"] == "Other":
            value.update({
                "label": "Utilization",
                "direction": "higher_better",
                "actual_value": 0.0,
                "target_value": 0.0,
            })
    return raw, values


def _sql_row(team_name, payload, kpi_values, *, score, grade, position=None):
    team = SimpleNamespace(name=team_name, db_name=team_name, display_name=None)
    employee = SimpleNamespace(employee_id="EMP-1", name="Agent", team=team, region="EGY", position_name=position)
    return SimpleNamespace(
        id="sql-1",
        employee=employee,
        team=team,
        month="May",
        year=2026,
        region="EGY",
        performance_level="Employee",
        position_name=position,
        status="Meets",
        score=score,
        grade=grade,
        upload_id=None,
        record_payload=payload,
        kpi_values=[
            SimpleNamespace(
                kpi_key=value["kpi_key"],
                actual_value=value["actual_value"],
                target_value=value["target_value"],
                achievement_ratio=value["achievement_ratio"],
                weight_applied=value["weight_applied"],
                contribution=value["contribution"],
            )
            for value in kpi_values
        ],
    )


class _Repo:
    rows: list = []

    def __init__(self, _db, _model):
        pass

    def get_dashboard_records(self, **_filters):
        return list(type(self).rows)


def _resolve(rows):
    _Repo.rows = rows
    return DashboardRecordService(object(), sql_repository_cls=_Repo).list_records()


def _inbound_payload(raw, kpi_values, score, grade):
    return PerformanceRecord(
        id="legacy", employee_id="EMP-1", employee_name="Agent", team="Inbound", month="May", year=2026,
        raw_data=raw, kpi_values=kpi_values, evaluation=EvaluationData(score=score, grade=grade),
    ).model_dump(mode="json")


# ------------------------------------------------------- Inbound Other: source

def test_kpi_service_no_longer_injects_a_placeholder_utz_value():
    row = _inbound_row()
    _score, _grade, achievements, _weights = _kpi_service().calculate_performance("Inbound", row)

    assert achievements["Other"] == pytest.approx(1 / 3)
    assert math.isnan(row["A.UTZ%"])
    assert math.isnan(row["UTZ%Ach%"])
    assert row["AbandonRate%Ach%"] == pytest.approx(1 / 3)


def test_new_upload_without_utz_saves_other_as_abandon_rate_lower_better():
    row = _inbound_row()
    _score, _grade, achievements, weights = _kpi_service().calculate_performance("Inbound", row)
    values = build_legacy_employee_kpi_values(
        "Inbound", row, achievements=achievements, weights=weights, config=load_team_config("Inbound")
    )
    other = next(value for value in values if value["kpi_key"] == "Other")

    assert other["label"] == "Abandon Rate"
    assert other["direction"] == "lower_better"
    assert other["actual_value"] == pytest.approx(0.03)
    assert other["contribution"] == pytest.approx(0.1 / 3, abs=1e-4)


def test_new_upload_with_utz_still_saves_other_as_utilization_higher_better():
    row = _inbound_row(**{"A.UTZ%": 0.80})
    _score, _grade, achievements, weights = _kpi_service().calculate_performance("Inbound", row)
    values = build_legacy_employee_kpi_values(
        "Inbound", row, achievements=achievements, weights=weights, config=load_team_config("Inbound")
    )
    other = next(value for value in values if value["kpi_key"] == "Other")

    assert other["label"] == "Utilization"
    assert other["direction"] == "higher_better"
    assert other["achievement_ratio"] == pytest.approx(0.80 / 0.85, abs=1e-4)


# --------------------------------------------- Inbound Other: existing records

def test_old_record_with_placeholder_utz_is_read_back_as_abandon_rate():
    row = _inbound_row()
    score, grade, achievements, weights = _kpi_service().calculate_performance("Inbound", row)
    raw, saved = _legacy_saved_inbound_record(row, achievements, weights)
    stored_score = round(sum(value["contribution"] for value in saved) * 100, 2)

    [record] = _resolve([
        _sql_row("Inbound", _inbound_payload(raw, saved, stored_score, grade), saved, score=stored_score, grade=grade)
    ])
    other = next(value for value in record.kpi_values if value["kpi_key"] == "Other")

    assert other["label"] == "Abandon Rate"
    assert other["direction"] == "lower_better"
    assert other["actual_value"] == pytest.approx(0.03)
    assert other["contribution"] == pytest.approx(0.1 / 3, abs=1e-4)
    # The stored (SQL) score was already Abandon-based; the dashboard now agrees
    # with it instead of zeroing the Other contribution.
    assert record.evaluation.score == pytest.approx(stored_score, abs=0.15)
    assert record.evaluation.grade == _inbound_grade(stored_score)


def test_old_record_without_kpi_rows_uses_the_row_abandon_achievement():
    row = _inbound_row()
    _score, grade, achievements, weights = _kpi_service().calculate_performance("Inbound", row)
    raw, _saved = _legacy_saved_inbound_record(row, achievements, weights)
    raw["AbandonRate%Ach%"] = achievements["Other"]

    values = build_legacy_employee_kpi_values("Inbound", raw, weights=weights, config=load_team_config("Inbound"))
    other = next(value for value in values if value["kpi_key"] == "Other")

    assert other["label"] == "Abandon Rate"
    assert other["direction"] == "lower_better"


def test_genuine_utilization_record_is_not_flipped_at_read_time():
    row = _inbound_row(**{"A.UTZ%": 0.80})
    _score, grade, achievements, weights = _kpi_service().calculate_performance("Inbound", row)
    raw = _json_safe(row)
    saved = build_legacy_employee_kpi_values(
        "Inbound", raw, achievements=achievements, weights=weights, config=load_team_config("Inbound")
    )
    stored_score = round(sum(value["contribution"] for value in saved) * 100, 2)

    [record] = _resolve([
        _sql_row("Inbound", _inbound_payload(raw, saved, stored_score, grade), saved, score=stored_score, grade=grade)
    ])
    other = next(value for value in record.kpi_values if value["kpi_key"] == "Other")

    assert other["label"] == "Utilization"
    assert other["direction"] == "higher_better"
    assert other["direction_source"] == "config"
    assert not other.get("direction_corrected")
    assert other["contribution"] == pytest.approx(0.1 * 0.80 / 0.85, abs=1e-4)


def test_genuine_zero_utilization_stays_utilization():
    # A real 0% UTZ scores 0, unlike an Abandon achievement which is never 0.
    row = _inbound_row(**{"A.UTZ%": 0.0})
    _score, _grade, achievements, weights = _kpi_service().calculate_performance("Inbound", row)
    assert achievements["Other"] == 0

    values = build_legacy_employee_kpi_values(
        "Inbound", _json_safe(row), weights=weights, config=load_team_config("Inbound"),
        persisted_achievements={"Other": 0.0},
    )
    other = next(value for value in values if value["kpi_key"] == "Other")
    assert other["label"] == "Utilization"
    assert other["direction"] == "higher_better"


def test_resolver_keeps_utilization_higher_and_abandon_lower():
    assert kd.resolve_kpi_direction("Inbound", {"kpi_key": "Other", "label": "Utilization", "direction": "higher_better"}) == (
        "higher_better", "config")
    assert kd.resolve_kpi_direction("Inbound", {"kpi_key": "Other", "label": "Abandon Rate", "direction": "higher_better"})[0] == (
        "lower_better")


# --------------------------------------- Elective records with Final Dubai keys

@pytest.mark.parametrize(
    ("kpi_key", "expected"),
    [
        ("combined_acceptance_rate", "higher_better"),
        ("combined_submission_within_month", "higher_better"),
        ("combined_discharge_within_one_hour", "higher_better"),
        ("ip_approval_acceptance_rate", "higher_better"),
        ("ip_approval_submission_within_month", "higher_better"),
        ("ip_discharge_within_one_hour", "higher_better"),
    ],
)
def test_elective_records_resolve_final_dubai_keys_through_the_configured_source_team(kpi_key, expected):
    assert load_team_config(ELECTIVE)["kpi_direction_source_teams"] == [FINAL_DUBAI]
    assert kd.resolve_kpi_direction(ELECTIVE, {"kpi_key": kpi_key}) == (expected, "team_config")


def test_elective_source_team_never_overrides_elective_definitions(monkeypatch):
    elective = load_team_config(ELECTIVE)
    fake_source = {
        "team": "Fake Source",
        "performance_levels": {"Employee": {"kpis": [
            {"key": "ip_initial_rejection_rate", "direction": "higher_better"},
            {"key": "fake_only_key", "direction": "lower_better"},
        ]}},
    }
    configs = {ELECTIVE: {**elective, "kpi_direction_source_teams": ["Fake Source"]}, "Fake Source": fake_source}
    monkeypatch.setattr(kd, "_load_config", lambda name: configs.get(name))

    assert kd.resolve_kpi_direction(ELECTIVE, {"kpi_key": "ip_initial_rejection_rate"}) == ("lower_better", "team_config")
    assert kd.resolve_kpi_direction(ELECTIVE, {"kpi_key": "fake_only_key"}) == ("lower_better", "team_config")


def test_same_upload_final_dubai_and_elective_rows_collapse_into_one_elective_record():
    """Characterises the root cause of the Elective records with Final Dubai keys.

    ``_sync_to_database`` keys records by (employee, month, year), so an agent on
    both sheets of one upload becomes one record whose team is the later sheet
    (Elective) and whose KPI rows include both teams' keys.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine, tables=[
        Team.__table__, DBEmployee.__table__, DBPerformanceRecord.__table__, KPIValue.__table__, TeamKPIConfig.__table__,
    ])
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()

    def kpi(key, weight):
        return {"kpi_key": key, "label": key, "direction": "higher_better", "actual_value": 1.0, "target_value": 1.0,
                "achievement_ratio": 1.0, "weight_applied": weight, "contribution": weight}

    final_record = PerformanceRecord(
        id="DUAL-1_2026_May", employee_id="DUAL-1", employee_name="Dual Agent", team=FINAL_DUBAI, month="May",
        year=2026, region="UAE", performance_level="Employee", position="Combined",
        evaluation=EvaluationData(score=100, grade="A"),
        kpi_values=[kpi("combined_acceptance_rate", 0.4), kpi("combined_submission_within_month", 0.3),
                    kpi("combined_discharge_within_one_hour", 0.3)],
    )
    elective_record = PerformanceRecord(
        id="DUAL-1_2026_May", employee_id="DUAL-1", employee_name="Dual Agent", team=ELECTIVE, month="May",
        year=2026, region="UAE", performance_level="Employee", position="IP Elective",
        evaluation=EvaluationData(score=50, grade="E"),
        kpi_values=[kpi("ip_initial_rejection_rate", 0.25), kpi("approval_within_48_hours", 0.25)],
    )
    employee = Employee(id="DUAL-1", name="Dual Agent", team=ELECTIVE, region="UAE", performance_level="Employee",
                        position="IP Elective")
    try:
        DatabaseSeeder()._sync_to_database([final_record, elective_record], [employee], db_session=session)
        session.flush()
        record = session.query(DBPerformanceRecord).one()
        team = session.query(Team).filter(Team.id == record.team_id).one()
        keys = {value.kpi_key for value in session.query(KPIValue).all()}

        assert team.name == ELECTIVE
        assert {"combined_acceptance_rate", "combined_submission_within_month", "combined_discharge_within_one_hour",
                "ip_initial_rejection_rate", "approval_within_48_hours"} == keys
        # Every inherited key now resolves from the source team, never a default.
        assert all(kd.resolve_kpi_direction(ELECTIVE, {"kpi_key": key})[1] == "team_config" for key in keys)
    finally:
        session.rollback()
        session.close()
