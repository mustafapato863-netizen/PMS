"""PR #15 follow-ups: shared KPI direction resolver and read-time correction."""
from __future__ import annotations

import copy
import io
import logging
from datetime import datetime
from io import BytesIO

import pytest
from fastapi import UploadFile
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import utils.kpi_direction as kd
from config.loader import load_team_config
from models.models import Base, Employee as DBEmployee, KPIValue, PerformanceRecord as DBPerformanceRecord, Team, TeamKPIConfig
from services.balanced_scorecard_service import BalancedScorecardService
from services.bsc_template_service import BSCTemplateService
from services.dashboard_record_service import DashboardRecordService, _normalise_kpi_values
from services.insights_report_service import _definition_for, _normalize_record
from services.marketing_import_service import MarketingImportService
from services.reporting_evidence_service import ReportingEvidenceService
from services.seeding_service import DatabaseSeeder
from services.uae_executive_summary import _normalize_record as uae_normalize_record
from tests.test_marketing_import import _valid_frame


@pytest.fixture(autouse=True)
def _fresh_direction_cache():
    kd.clear_kpi_direction_cache()
    yield
    kd.clear_kpi_direction_cache()


# ---------------------------------------------------------------- resolver order

def test_record_config_wins_over_everything():
    value = {"kpi_key": "AHT", "direction": "higher_better"}
    assert kd.resolve_kpi_direction("Inbound", value, {"direction": "lower_better"}) == ("lower_better", "config")


def test_team_config_beats_a_stale_persisted_direction():
    # Old readers saved higher_better on a config-lookup miss.
    value = {"kpi_key": "AHT", "label": "AHT (Handle Time)", "direction": "higher_better"}
    assert kd.resolve_kpi_direction("Inbound", value) == ("lower_better", "team_config")


def test_merged_team_resolves_through_its_source_teams():
    assert kd.resolve_kpi_direction("Call Center", {"kpi_key": "AHT"}) == ("lower_better", "team_config")
    assert kd.resolve_kpi_direction("RCM", {"kpi_key": "Rejection"}) == ("lower_better", "team_config")


def test_persisted_direction_is_used_before_the_global_match():
    value = {"kpi_key": "cw_error_free", "direction": "lower_better"}
    assert kd.resolve_kpi_direction("Unknown Team", value) == ("lower_better", "persisted")


def test_single_unambiguous_global_match():
    assert kd.resolve_kpi_direction("Unknown Team", {"kpi_key": "cw_error_free"}) == ("higher_better", "global_config")
    assert kd.resolve_kpi_direction(None, {"label": "Page load time"}) == ("lower_better", "global_config")


def test_unresolved_direction_defaults_flagged_and_logged(caplog):
    with caplog.at_level(logging.WARNING, logger="utils.kpi_direction"):
        result = kd.resolve_kpi_direction("Unknown Team", {"kpi_key": "made_up_kpi"})
        kd.resolve_kpi_direction("Unknown Team", {"kpi_key": "made_up_kpi"})
    assert result == ("higher_better", "default")
    messages = [record.getMessage() for record in caplog.records if "made_up_kpi" in record.getMessage()]
    assert len(messages) == 1  # logged once, not per row
    assert "direction_source=default" in messages[0]


# ------------------------------------------------------------- collision keys

@pytest.mark.parametrize(
    ("team", "value", "expected"),
    [
        ("Coding", {"kpi_key": "TAT"}, "lower_better"),
        ("Re-Submission", {"kpi_key": "tat"}, "higher_better"),
        ("Re-Submission", {"kpi_key": "tat", "label": "TAT"}, "higher_better"),
        ("Inbound", {"kpi_key": "Other", "label": "Abandon Rate"}, "lower_better"),
        ("Inbound UAE", {"kpi_key": "Other"}, "lower_better"),
        ("Outbound", {"kpi_key": "Other"}, "higher_better"),
    ],
)
def test_collision_keys_resolve_by_team(team, value, expected):
    direction, source = kd.resolve_kpi_direction(team, value)
    assert direction == expected
    assert source == "team_config"


@pytest.mark.parametrize("key", ["TAT", "tat", "Other", "other"])
def test_collision_keys_never_resolve_by_key_alone(key):
    assert key.casefold() not in kd.global_direction_index()
    assert kd.resolve_kpi_direction("Unknown Team", {"kpi_key": key}) == ("higher_better", "default")
    assert kd.resolve_kpi_direction("Unknown Team", {"kpi_key": key, "direction": "lower_better"}) == ("lower_better", "persisted")


def test_merged_team_does_not_guess_a_collision_key():
    # Call Center contains both Inbound (abandon, lower) and Outbound (reachability, higher).
    assert "other" not in kd.team_direction_index("Call Center")
    assert kd.resolve_kpi_direction("Call Center", {"kpi_key": "Other", "direction": "higher_better"})[1] == "persisted"


def test_inbound_utilization_legacy_variant_is_higher_better():
    value = {"kpi_key": "Other", "label": "Utilization"}
    inbound_other = next(k for k in load_team_config("Inbound")["kpis"] if k["key"] == "Other")
    assert kd.resolve_kpi_direction("Inbound", value, inbound_other) == ("higher_better", "config")


def test_config_labels_and_directions():
    marketing = load_team_config("Marketing")["performance_levels"]["Employee"]["positions"]
    by_key = {k["key"]: k for position in marketing.values() for k in position["kpis"]}
    assert by_key["cw_error_free"]["direction"] == "higher_better"
    assert by_key["wd_page_speed"]["label"] == "Page load time"
    assert by_key["wd_page_speed"]["direction"] == "lower_better"
    resub = {k["key"]: k for k in load_team_config("Re-Submission")["kpis"]}
    assert resub["tat"]["label"] == "TAT compliance %"
    assert resub["tat"]["direction"] == "higher_better"


# ------------------------------------------------------ flipped contribution fix

def test_flipped_contribution_fix_requires_evidence_and_is_idempotent():
    # actual 80 vs target 100: lower_better scored 1.0, higher_better 0.8.
    assert kd.flipped_contribution_fix(80, 100, 0.3, 0.3, "higher_better", "lower_better") == pytest.approx(0.24)
    assert kd.flipped_contribution_fix(80, 100, 0.3, 0.24, "higher_better", "lower_better") is None
    assert kd.flipped_contribution_fix(80, 100, 0.3, 0.3, "higher_better", None) is None
    assert kd.flipped_contribution_fix(80, 100, 0.3, 0.3, "higher_better", "higher_better") is None
    assert kd.flipped_contribution_fix(80, 100, 0.0, 0.0, "higher_better", "lower_better") is None


# ------------------------------------------- old wrongly-saved Marketing records

def _old_lower_better_marketing_config() -> dict:
    config = copy.deepcopy(load_team_config("Marketing"))
    for kpi in config["performance_levels"]["Employee"]["positions"]["Content Writer"]["kpis"]:
        if kpi["key"] == "cw_error_free":
            kpi["direction"] = "lower_better"
    return config


def _content_writer_frame(error_free_actual: float, direction: str):
    frame = _valid_frame(positions=["Content Writer"])
    mask = frame["KPI"] == "Error-free content ratio"
    frame.loc[mask, "Actual Value"] = error_free_actual
    frame["Direction"] = frame["Direction"].where(~mask, direction)
    frame["Achievement %"] = None
    frame["Weighted Score %"] = None
    frame["Performance Score"] = None
    return frame


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(
        bind=engine,
        tables=[Team.__table__, DBEmployee.__table__, DBPerformanceRecord.__table__, KPIValue.__table__, TeamKPIConfig.__table__],
    )
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        yield session
    finally:
        session.close()


def _seed_old_record(session, error_free_actual: float = 80.0):
    """Import a Content Writer row exactly as the old lower_better config did."""
    parsed = MarketingImportService(config=_old_lower_better_marketing_config()).parse_frame(
        _content_writer_frame(error_free_actual, "Lower Better")
    )
    DatabaseSeeder()._sync_to_database(parsed.records, parsed.employees, db_session=session)
    session.flush()
    return parsed.records[0]


def _fresh_score(error_free_actual: float = 80.0) -> float:
    parsed = MarketingImportService().parse_frame(_content_writer_frame(error_free_actual, "Higher Better"))
    return parsed.records[0].evaluation.score


def test_old_record_was_saved_with_the_wrong_score(db_session):
    old = _seed_old_record(db_session)
    assert old.evaluation.score == pytest.approx(100.0)
    assert _fresh_score() == pytest.approx(94.0)
    stored = db_session.query(DBPerformanceRecord).one()
    assert float(stored.score) == pytest.approx(100.0)


def test_dashboard_records_correct_old_saved_scores_at_read_time(db_session):
    _seed_old_record(db_session)

    records = DashboardRecordService(db_session).list_records(team="Marketing")

    assert len(records) == 1
    record = records[0]
    value = next(v for v in record.kpi_values if v["kpi_key"] == "cw_error_free")
    assert value["direction"] == "higher_better"
    assert value["direction_source"] == "config"
    assert value["direction_corrected"] is True
    assert value["achievement_ratio"] == pytest.approx(0.8)
    assert value["contribution"] == pytest.approx(0.24)
    assert record.evaluation.score == pytest.approx(_fresh_score())
    assert record.evaluation.grade == "B"
    # Other KPIs are untouched and carry a resolved, non-default direction.
    assert all(v["direction_source"] != "default" for v in record.kpi_values)
    assert sum(1 for v in record.kpi_values if v.get("direction_corrected")) == 1


def test_dashboard_read_time_correction_recomputes_status_with_score_and_grade(db_session):
    # QA BUG-1: QA-MKT-COW-01 read back as 94 / B but still "Exceeds".
    _seed_old_record(db_session)
    stored = db_session.query(DBPerformanceRecord).one()
    assert (stored.grade, stored.status) == ("A", "Exceeds")

    record = DashboardRecordService(db_session).list_records(team="Marketing")[0]

    assert record.evaluation.grade == "B"
    assert record.status == "Meets"
    # Same rule as a record imported with the fixed config.
    fresh = MarketingImportService().parse_frame(_content_writer_frame(80.0, "Higher Better")).records[0]
    assert (record.evaluation.score, record.evaluation.grade) == (fresh.evaluation.score, fresh.evaluation.grade)
    assert record.status == (fresh.status or "Meets")


def test_dashboard_read_time_correction_keeps_a_custom_status(db_session):
    _seed_old_record(db_session)
    db_session.query(DBPerformanceRecord).one().status = "Under Review"
    db_session.flush()

    record = DashboardRecordService(db_session).list_records(team="Marketing")[0]

    assert record.evaluation.grade == "B"
    assert record.status == "Under Review"


def test_dashboard_does_not_touch_correctly_saved_records(db_session):
    parsed = MarketingImportService().parse_frame(_content_writer_frame(80.0, "Higher Better"))
    DatabaseSeeder()._sync_to_database(parsed.records, parsed.employees, db_session=db_session)
    db_session.flush()

    record = DashboardRecordService(db_session).list_records(team="Marketing")[0]

    assert record.evaluation.score == pytest.approx(94.0)
    assert not any(v.get("direction_corrected") for v in record.kpi_values)


def test_dashboard_normalise_flags_an_unresolvable_direction(caplog):
    with caplog.at_level(logging.WARNING, logger="utils.kpi_direction"):
        values = _normalise_kpi_values(
            [{"kpi_key": "mystery", "actual_value": 1, "target_value": 2, "achievement_ratio": 0.5, "weight_applied": 1, "contribution": 0.5}],
            None,
            {},
            "Unknown Team",
        )
    assert values[0]["direction"] == "higher_better"
    assert values[0]["direction_source"] == "default"
    assert any("mystery" in record.getMessage() for record in caplog.records)


def test_dashboard_normalise_uses_team_direction_on_config_miss():
    # Coding TAT row on a record whose resolved config missed the key.
    values = _normalise_kpi_values(
        [{"kpi_key": "TAT", "actual_value": 3, "target_value": 2.5, "achievement_ratio": 0.83, "weight_applied": 0.3, "contribution": 0.25}],
        None,
        {},
        "Coding",
    )
    assert values[0]["direction"] == "lower_better"
    assert values[0]["direction_source"] == "team_config"


def _old_cw_record_dict() -> dict:
    return {
        "employee_id": "SGHD90001",
        "employee_name": "Writer",
        "team": "Marketing",
        "position": "Content Writer",
        "performance_level": "Employee",
        "year": 2026,
        "month": "July",
        "score": 100.0,
        "kpi_values": [
            {"kpi_key": "cw_error_free", "label": "Error-free content ratio", "direction": "lower_better",
             "unit": "%", "actual_value": 80.0, "target_value": 100.0, "achievement_ratio": 1.0,
             "weight_applied": 0.3, "contribution": 0.3},
        ],
    }


def test_reporting_evidence_corrects_old_saved_rows():
    rows, issues = ReportingEvidenceService()._normalized_record_kpis(_old_cw_record_dict())

    row = rows[0]
    assert row["direction"] == "higher_better"
    assert row["achievement"] == pytest.approx(80.0)
    assert row["weighted_contribution"] == pytest.approx(24.0)
    assert row["lost_points"] == pytest.approx(6.0)
    assert not any(issue["code"] == "invalid_direction" for issue in issues)


def test_reporting_evidence_keeps_unresolved_direction_excluded():
    record = _old_cw_record_dict()
    record["team"] = "Unknown Team"
    record["kpi_values"][0].update({"kpi_key": "mystery", "label": "Mystery", "direction": None})
    rows, issues = ReportingEvidenceService()._normalized_record_kpis(record)
    # No configuration at all -> not interpreted (existing behaviour).
    assert rows == [] or rows[0]["included_in_score"] is False


def test_insights_report_resolves_stale_directions_per_team():
    record = _normalize_record({
        "team": "Coding", "employee_id": "1", "year": 2026, "month": "July",
        "kpi_values": [{"kpi_key": "TAT", "label": "Turnaround Time", "direction": "higher_better", "actual_value": 3, "target_value": 2.5}],
    })
    assert record["kpis"][0]["direction"] == "lower_better"
    assert record["kpis"][0]["direction_source"] == "team_config"


def test_insights_report_definition_lookup_is_team_safe_for_shared_keys():
    inbound = next(k for k in load_team_config("Inbound")["kpis"] if k["key"] == "Other")
    outbound = next(k for k in load_team_config("Outbound")["kpis"] if k["key"] == "Other")
    definitions = [dict(inbound), dict(outbound)]
    outbound_row = _normalize_record({
        "team": "Outbound", "employee_id": "2", "year": 2026, "month": "July",
        "kpi_values": [{"kpi_key": "Other", "label": outbound["label"], "actual_value": 0.8, "target_value": 0.9}],
    })["kpis"][0]

    definition = _definition_for(outbound_row, definitions)

    assert definition["label"] == outbound["label"]
    assert definition["direction"] == "higher_better"


def test_insights_report_keeps_managerial_db_direction():
    record = _normalize_record({
        "team": "Inbound", "performance_level": "Managerial", "employee_id": "3", "year": 2026, "month": "July",
        "kpi_values": [{"kpi_key": "AHT", "label": "AHT", "direction": "higher_better", "actual_value": 3, "target_value": 2}],
    })
    assert record["kpis"][0]["direction"] == "higher_better"


def test_uae_executive_summary_resolves_stale_directions():
    record = uae_normalize_record({
        "team": "Inbound UAE", "employee_id": "4", "year": 2026, "month": "July",
        "evaluation": {"score": 80},
        "kpi_values": [{"kpi_key": "Other", "label": "Abandon Rate", "direction": "higher_better", "actual_value": 0.1, "target_value": 0.05}],
    })
    assert record["kpis"][0]["direction"] == "lower_better"


def test_balanced_scorecard_resolves_a_missing_definition_direction():
    config = {
        "team": "Inbound",
        "grade_thresholds": {"A": 90, "B": 80, "C": 70, "D": 60},
        "balanced_scorecard": {"enabled": True, "perspectives": [{"key": "Internal Process", "label": "Internal Process", "display_order": 1}]},
        "kpis": [{"key": "AHT", "label": "AHT (Handle Time)", "perspective": "Internal Process", "weight": 1.0, "unit": "min"}],
    }
    summary = BalancedScorecardService._summarize([], config)
    rows = [row for perspective in summary.get("perspectives", []) for row in perspective.get("kpis", [])] or summary.get("kpis", [])
    assert rows and rows[0]["direction"] == "lower_better"


# --------------------------------------------------------------- data-fix script

def test_data_fix_script_dry_run_apply_and_idempotent(db_session):
    from scripts.fix_cw_error_free_direction import run

    _seed_old_record(db_session)
    mirrors = db_session.query(TeamKPIConfig).filter(TeamKPIConfig.kpi_key == "cw_error_free").all()
    if not mirrors:
        mirrors = [TeamKPIConfig(
            team_id=db_session.query(Team).one().id, performance_level="Employee", position_name="Content Writer",
            kpi_key="cw_error_free", kpi_label="Error-free content ratio", weight=0.3, direction="lower_better",
            unit="%", color="#000000", actual_col="Actual Value", target_col="Target Value", display_order=3,
        )]
        db_session.add_all(mirrors)
    for mirror in mirrors:
        mirror.direction = "lower_better"  # the stale DB mirror of the old config
    db_session.flush()

    dry = run(db_session, apply=False)
    assert dry["records_checked"] == 1
    assert dry["records_to_fix"] == 1
    assert dry["changes"][0]["score"] == [pytest.approx(100.0), pytest.approx(94.0)]
    assert dry["team_kpi_config_to_fix"] == len(mirrors) >= 1
    assert float(db_session.query(DBPerformanceRecord).one().score) == pytest.approx(100.0)  # nothing written
    assert all(m.direction == "lower_better" for m in db_session.query(TeamKPIConfig).filter(TeamKPIConfig.kpi_key == "cw_error_free"))

    applied = run(db_session, apply=True)
    assert applied["records_to_fix"] == 1
    stored = db_session.query(DBPerformanceRecord).one()
    assert float(stored.score) == pytest.approx(94.0)
    assert stored.grade == "B"
    assert stored.status == "Meets"  # the script recomputes status too (BUG-1)
    value = db_session.query(KPIValue).filter(KPIValue.kpi_key == "cw_error_free").one()
    assert float(value.contribution) == pytest.approx(0.24)
    assert float(value.achievement_ratio) == pytest.approx(0.8)
    payload_value = next(v for v in stored.record_payload["kpi_values"] if v["kpi_key"] == "cw_error_free")
    assert payload_value["direction"] == "higher_better"
    assert all(row.direction == "higher_better" for row in db_session.query(TeamKPIConfig).filter(TeamKPIConfig.kpi_key == "cw_error_free"))

    again = run(db_session, apply=True)
    assert again["records_to_fix"] == 0
    assert again["already_correct"] == 1
    assert again["team_kpi_config_to_fix"] == 0

    # Read path agrees with the rewritten data and does not double-correct.
    record = DashboardRecordService(db_session).list_records(team="Marketing")[0]
    assert record.evaluation.score == pytest.approx(94.0)
    assert not any(v.get("direction_corrected") for v in record.kpi_values)


# -------------------------------------------------- management blank direction

def _management_workbook(direction_cell) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "KPI's Data"
    sheet.append([
        "Employee ID", "Team", "Employee Name", "Position", "Performance Level", "Period",
        "Perspective", "KPI", "Direction", "Weight", "Target Value", "Target Unit", "Actual Value",
    ])
    sheet.append([
        "EMP-1", "Sales", "Ahmed", "Sales Manager", "Managerial", datetime(2025, 5, 1),
        "Financial", "Revenue Achievement %", "Higher Better", 60, 95, "%", 99,
    ])
    sheet.append([
        "EMP-1", "Sales", "Ahmed", "Sales Manager", "Managerial", datetime(2025, 5, 1),
        "Customer", "Complaint Rate", direction_cell, 40, 5, "%", 4,
    ])
    payload = BytesIO()
    workbook.save(payload)
    return payload.getvalue()


def test_blank_management_direction_defaults_with_visible_warning():
    rows, warnings = BSCTemplateService().parse_upload_with_warnings(_management_workbook(None))

    assert rows[1]["direction"] == "higher_better"  # default kept
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning["code"] == "BLANK_DIRECTION"
    assert warning["row"] == 3
    assert warning["kpi"] == "Complaint Rate"
    assert warning["column"] == "Direction"
    assert "Row 3" in warning["message"] and "Complaint Rate" in warning["message"]


def test_filled_management_direction_has_no_warning():
    rows, warnings = BSCTemplateService().parse_upload_with_warnings(_management_workbook("Lower Better"))
    assert rows[1]["direction"] == "lower_better"
    assert warnings == []


@pytest.mark.asyncio
async def test_management_upload_response_lists_direction_warnings(monkeypatch):
    from types import SimpleNamespace

    from api.routers.performance import upload_balanced_scorecard_template

    monkeypatch.setattr(
        "api.routers.performance.ManagementBSCService",
        lambda db: SimpleNamespace(import_template_rows=lambda **kwargs: {"teams": ["Sales"], "periods": ["May 2025"]}),
    )
    file = UploadFile(filename="management.xlsx", file=io.BytesIO(_management_workbook("  ")))

    response = await upload_balanced_scorecard_template(db=SimpleNamespace(rollback=lambda: None), file=file, _user={"username": "tester"})

    assert response.success is True
    assert [w["code"] for w in response.data["warnings"]] == ["BLANK_DIRECTION"]
    assert response.data["warnings"][0]["kpi"] == "Complaint Rate"
