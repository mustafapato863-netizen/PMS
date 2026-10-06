"""PR #15 follow-ups from the production read-only checks (2026-10-06).

1. Inbound ``Other``: live check #2 showed all 157 records saved as
   Utilization / higher_better carry a real UTZ (0.68-0.93) and matching stored
   scores, so they are correct. The zero-UTZ read-time rule from e0d1c77 was
   unnecessary and is reverted; the KPIService no-placeholder fix stays (a
   future upload without UTZ must save Abandon Rate / lower_better).
2. Pre-Approvals IP Elective Dubai records carrying IP Final Dubai KPI keys:
   source-team directions plus the upload merge fix (one record per
   employee-month, scored on the assigned team).
"""
from __future__ import annotations

import datetime
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

import utils.kpi_direction as kd
from config.loader import load_team_config
from models.schemas import EvaluationData, PerformanceRecord
from services.dashboard_record_service import DashboardRecordService
from services.kpi_service import KPIService
from services.legacy_kpi_evidence import build_legacy_employee_kpi_values


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

PROD_UTILIZATION_ROWS = json.loads(
    (Path(__file__).parent / "fixtures" / "inbound_prod_utilization_rows.json").read_text()
)["rows"]


def _prod_sql_row(fixture):
    payload = PerformanceRecord(
        id="prod-like", employee_id="EMP-1", employee_name="Agent", team="Inbound", month=fixture["month"],
        year=fixture["year"], raw_data=fixture["raw_data"], kpi_values=fixture["payload_kpi_values"],
        evaluation=EvaluationData(score=fixture["stored_score"], grade=fixture["stored_grade"]),
    ).model_dump(mode="json")
    row = _sql_row("Inbound", payload, fixture["kpi_value_rows"], score=fixture["stored_score"],
                   grade=fixture["stored_grade"])
    row.month = fixture["month"]
    row.status = "Meets"
    return row


@pytest.mark.parametrize("fixture", PROD_UTILIZATION_ROWS, ids=[row["label"] for row in PROD_UTILIZATION_ROWS])
def test_prod_like_genuine_utilization_rows_stay_utilization_with_the_stored_score(fixture):
    utz = fixture["raw_data"]["A.UTZ%"]
    assert 0.68 <= utz <= 0.94

    [record] = _resolve([_prod_sql_row(fixture)])
    other = next(value for value in record.kpi_values if value["kpi_key"] == "Other")
    saved = next(value for value in fixture["payload_kpi_values"] if value["kpi_key"] == "Other")

    assert other["label"] == "Utilization"
    assert other["direction"] == "higher_better"
    assert other["direction_source"] == "config"
    assert not other.get("direction_corrected")  # never flipped / rescored
    assert other["actual_value"] == pytest.approx(utz, abs=1e-4)
    assert other["contribution"] == pytest.approx(saved["contribution"], abs=1e-3)
    # The dashboard shows the stored score and grade: not a mismatch.
    assert record.evaluation.score == pytest.approx(fixture["stored_score"], abs=0.05)
    assert record.evaluation.grade == fixture["stored_grade"]
    assert record.status == "Meets"


@pytest.mark.parametrize("fixture", PROD_UTILIZATION_ROWS, ids=[row["label"] for row in PROD_UTILIZATION_ROWS])
def test_prod_like_utilization_rows_rebuild_as_utilization_from_the_raw_row(fixture):
    values = build_legacy_employee_kpi_values("Inbound", fixture["raw_data"], config=load_team_config("Inbound"))
    other = next(value for value in values if value["kpi_key"] == "Other")
    assert (other["label"], other["direction"]) == ("Utilization", "higher_better")
    saved = next(value for value in fixture["payload_kpi_values"] if value["kpi_key"] == "Other")
    direction = kd.resolve_kpi_direction("Inbound", saved)[0]
    assert direction == "higher_better"
    # The read-time flip correction has no evidence to act on.
    assert kd.flipped_contribution_fix(
        saved["actual_value"], saved["target_value"], saved["weight_applied"], saved["contribution"],
        direction, saved["direction"],
    ) is None


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


def test_stored_zero_utz_is_read_as_utilization_zero_utz_rule_reverted():
    # e0d1c77 reinterpreted a stored 0 UTZ as Abandon Rate using the scored
    # achievement. Prod has no such rows (A4: utz_zero = 0 in every upload), so
    # the rule is reverted: a present UTZ value always means Utilization.
    row = _inbound_row(**{"A.UTZ%": 0.0})
    _score, _grade, achievements, weights = _kpi_service().calculate_performance("Inbound", row)
    assert achievements["Other"] == 0

    raw = _json_safe(row)
    raw["AbandonRate%Ach%"] = 1.0
    values = build_legacy_employee_kpi_values("Inbound", raw, weights=weights, config=load_team_config("Inbound"))
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


# The upload merge itself (one record per employee-month, assigned team only,
# upload warning, score scaling) is covered in tests/test_upload_record_collisions.py.
