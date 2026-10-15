"""Ordinary Outbound upload headers: notices, and one source-proven target alias.

Synthetic workbooks only. The pasted ordinary header row has no Productivity
column. An extra column is reported and is not registered as a scored KPI.
"""
from __future__ import annotations

import inspect
import io
import json
import uuid
from datetime import datetime, time

import pandas as pd
import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers import upload as upload_router
from models.models import (
    Action,
    Employee,
    EmployeeUploadBatch,
    EvaluationRevision,
    EvaluationScope,
    KPIValue,
    PerformanceRecord,
    Team,
    TeamConfigurationVersion,
    TeamKPIConfig,
    UploadLog,
)
from processors.excel_processor import ExcelProcessor
from services.kpi_service import KPIService
from services.outbound_period_basis import KNOWN_PERCENT_COLUMNS
from services.seeding_service import DatabaseSeeder, UploadProcessingError
from services.upload_header_notices import (
    ORDINARY_OUTBOUND_HEADERS,
    apply_outbound_quality_target_alias,
    classify_raw_headers,
)


WHEN = datetime(2026, 9, 15)
ATTEND_ACTUAL, ATTEND_TARGET = 0.40, 0.80
BOOKING_ACTUAL, BOOKING_TARGET = 0.60, 0.30
QUALITY_ACTUAL, QUALITY_TARGET = 0.40, 0.80
REACH_ACTUAL, REACH_TARGET = 0.25, 0.50
LEAKED_MARKERS = ("ANON-1", "ANON-2", "Anonymous Agent", "do-not-leak", "also-secret", "0.95")


@pytest.fixture(autouse=True)
def _no_external_cache(monkeypatch):
    monkeypatch.setattr("services.cache_service.redis_client", None, raising=False)
    monkeypatch.setattr("services.cache_invalidation_service.redis_client", None, raising=False)
    monkeypatch.setattr(
        "services.cache_invalidation_service.CacheInvalidationService.bump_data_version",
        staticmethod(lambda: 0),
    )
    monkeypatch.setattr(
        "services.cache_invalidation_service.CacheInvalidationService.bump_config_version",
        staticmethod(lambda: 0),
    )


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from config.database import Base

    Base.metadata.create_all(
        bind=engine,
        tables=[
            Team.__table__,
            Employee.__table__,
            PerformanceRecord.__table__,
            KPIValue.__table__,
            TeamKPIConfig.__table__,
            TeamConfigurationVersion.__table__,
            EvaluationScope.__table__,
            EvaluationRevision.__table__,
            EmployeeUploadBatch.__table__,
            UploadLog.__table__,
            Action.__table__,
        ],
    )
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()


def _seeder() -> DatabaseSeeder:
    seeder = DatabaseSeeder()
    return seeder


def _workbook(headers: list, rows: list[list], sheet: str = "Outbound") -> bytes:
    book = Workbook()
    worksheet = book.active
    worksheet.title = sheet
    worksheet.append(list(headers))
    for row in rows:
        worksheet.append(list(row))
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _ordinary_row(employee_id: str = "ANON-1", *, target: object = QUALITY_TARGET) -> list:
    return [
        WHEN,
        "EGY",
        "Employee",
        employee_id,
        "Anonymous Agent",
        "",
        10,
        4,
        6,
        0,
        4,
        0.25,
        time(0, 2, 30),
        1,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        BOOKING_ACTUAL,
        ATTEND_ACTUAL,
        2.5,
        REACH_ACTUAL,
        QUALITY_ACTUAL,
        BOOKING_TARGET,
        ATTEND_TARGET,
        2.5,
        REACH_TARGET,
        target,
        None,
        None,
        None,
        None,
        None,
        None,
        "C",
    ]


def _ordinary_bytes(**kwargs) -> bytes:
    return _workbook(list(ORDINARY_OUTBOUND_HEADERS), [_ordinary_row(**kwargs)])


def _headers_with(*extra_before_grade: str, after_grade: tuple[str, ...] = ()) -> list[str]:
    headers = list(ORDINARY_OUTBOUND_HEADERS)
    grade_at = headers.index("Performance Grade")
    for name in reversed(extra_before_grade):
        headers.insert(grade_at, name)
    headers.extend(after_grade)
    return headers


def _row_with(headers: list[str], values: dict, employee_id: str = "ANON-1") -> list:
    base = dict(zip(ORDINARY_OUTBOUND_HEADERS, _ordinary_row(employee_id), strict=True))
    base.update(values)
    return [base.get(header) for header in headers]


def _dry(db, contents: bytes) -> dict:
    return _seeder().process_uploaded_file(
        "ordinary-headers.xlsx",
        contents,
        dry_run=True,
        db_session=db,
    )


def _commit(db, contents: bytes) -> dict:
    return _seeder().process_uploaded_file(
        "ordinary-headers.xlsx",
        contents,
        dry_run=False,
        db_session=db,
    )


def _score(result: dict) -> float:
    return float(result["scored_rows"][0]["score"])


def _notice(result: dict, code: str) -> dict | None:
    matches = [item for item in result["column_warnings"] if item["code"] == code]
    if not matches:
        return None
    assert len(matches) == 1
    return matches[0]


def _warning_text(result: dict) -> str:
    return json.dumps(result["column_warnings"])


def _assert_no_cell_values(result: dict) -> None:
    text = _warning_text(result)
    for marker in LEAKED_MARKERS:
        assert marker not in text


def _quality(db, employee_code: str = "ANON-1") -> KPIValue:
    employee = db.query(Employee).filter(Employee.employee_id == employee_code).one()
    record = db.query(PerformanceRecord).filter(PerformanceRecord.employee_id == employee.id).one()
    return (
        db.query(KPIValue)
        .filter(KPIValue.record_id == record.id, KPIValue.kpi_key == "Quality")
        .one()
    )


def _stored_raw(db, employee_code: str = "ANON-1") -> dict:
    employee = db.query(Employee).filter(Employee.employee_id == employee_code).one()
    record = db.query(PerformanceRecord).filter(PerformanceRecord.employee_id == employee.id).one()
    return dict(record.record_payload["raw_data"])


def _kpi_map(db, employee_code: str = "ANON-1") -> dict[str, KPIValue]:
    employee = db.query(Employee).filter(Employee.employee_id == employee_code).one()
    record = db.query(PerformanceRecord).filter(PerformanceRecord.employee_id == employee.id).one()
    return {row.kpi_key: row for row in db.query(KPIValue).filter(KPIValue.record_id == record.id)}


def test_original_header_fixture_has_no_false_unknown_warning(db):
    header_only = _dry(db, _workbook(list(ORDINARY_OUTBOUND_HEADERS), []))
    assert header_only["records_imported"] == 0
    assert header_only["column_warnings"] == []
    assert header_only["warnings"] == []

    scored = _dry(db, _ordinary_bytes())
    assert scored["records_imported"] == 1
    assert scored["column_warnings"] == []
    assert scored["warnings"] == []
    assert "Productivity" not in _processed_columns(_ordinary_bytes())


def test_whitespace_and_case_aliases_are_known_and_still_read(db):
    headers = [
        "date",
        " Region ",
        "ROLE",
        "SGH  Code",
        "English  Name",
        "Out Team",
        "Num Of Leads",
        "Reached",
        "Not Reached",
        "Trails",
        "Connected",
        "avail time",
        "aht",
        "Dubai _Booking",
        "Sharjah_Booking",
        "Ajman_Booking",
        "Clinics _Booking",
        "Dubai _Attend",
        "Sharjah_Attend",
        "Ajman_Attend",
        "clinics_Attend",
        "A. Booking %",
        "A. Attend %",
        "A.AHT",
        "A. Reachability %",
        "A. Quality Score",
        "T. Booking %",
        "T. Attend %",
        "T.AHT",
        "T. Reachability %",
        "  T. Quality Target  ",
        "Booking C.R Ach%",
        "Attend C.R Ach%",
        "AHT Ach%",
        "Reachability % Ach%",
        "Quality Ach%",
        "Performance Score",
        "Performance Grade",
        "Unnamed: 4",
        " ",
    ]
    values = _ordinary_row()
    values.extend([None, None])
    result = _dry(db, _workbook(headers, [values]))

    assert result["column_warnings"] == []
    assert _score(result) == pytest.approx(_score(_dry(db, _ordinary_bytes())))


def test_new_columns_before_and_after_grade_are_named_without_changing_the_total(db):
    headers = _headers_with("Side Note", after_grade=("Clinic Surprise", "Unnamed: 19"))
    row = _row_with(
        headers,
        {"Side Note": "also-secret", "Clinic Surprise": "do-not-leak", "Unnamed: 19": "padding"},
        employee_id="ANON-2",
    )
    preview = _dry(db, _workbook(headers, [row]))
    baseline = _dry(db, _ordinary_bytes())

    assert _score(preview) == pytest.approx(_score(baseline))
    assert preview["warnings"] == []
    notice = _notice(preview, "unmapped_columns")
    assert notice is not None
    assert notice["sheet"] == "Outbound"
    assert notice["headers"] == ["Side Note", "Clinic Surprise"]
    assert notice["truncated"] is False
    _assert_no_cell_values(preview)

    columns = _processed_columns(_workbook(headers, [row]))
    assert "SideNote" in columns
    assert "ClinicSurprise" not in columns
    assert "Productivity" not in columns

    _commit(db, _ordinary_bytes())
    _commit(db, _workbook(headers, [row]))
    kept = _stored_raw(db, "ANON-2")
    assert kept["SideNote"] == "also-secret"
    assert "ClinicSurprise" not in kept
    assert "do-not-leak" not in json.dumps(kept)
    assert _quality(db, "ANON-1").target_value == _quality(db, "ANON-2").target_value
    assert float(db.query(PerformanceRecord).filter(PerformanceRecord.employee_id == db.query(Employee).filter(Employee.employee_id == "ANON-1").one().id).one().score) == pytest.approx(
        float(db.query(PerformanceRecord).filter(PerformanceRecord.employee_id == db.query(Employee).filter(Employee.employee_id == "ANON-2").one().id).one().score)
    )


def test_quality_target_alias_is_read_and_original_column_stays(db):
    frame = _processed_frame(_ordinary_bytes())
    assert float(frame.iloc[0]["T.Quality%"]) == pytest.approx(QUALITY_TARGET)
    assert float(frame.iloc[0]["T.QualityTarget"]) == pytest.approx(QUALITY_TARGET)
    assert "Productivity" not in frame.columns

    canonical_headers = [
        "T.Quality%" if header == "T.Quality Target" else header
        for header in ORDINARY_OUTBOUND_HEADERS
    ]
    canonical = _dry(db, _workbook(canonical_headers, [_ordinary_row()]))
    alias = _dry(db, _ordinary_bytes())
    assert canonical["column_warnings"] == []
    assert alias["column_warnings"] == []
    assert _score(alias) == pytest.approx(_score(canonical))

    _commit(db, _ordinary_bytes())
    quality = _quality(db)
    kpis = _kpi_map(db)
    raw = _stored_raw(db)
    assert float(quality.target_value) == pytest.approx(0.8)
    assert float(quality.achievement_ratio) == pytest.approx(0.5)
    assert float(quality.actual_value) == pytest.approx(0.4)
    assert float(quality.weight_applied) == pytest.approx(0.10)
    assert raw["T.QualityTarget"] == pytest.approx(0.8)
    assert raw["T.Quality%"] == pytest.approx(0.8)
    assert "Productivity" not in kpis
    assert "AHT" not in kpis
    assert sum(float(row.weight_applied) for row in kpis.values()) == pytest.approx(1.0)


def test_equivalent_percent_spellings_are_not_a_conflict(db):
    headers = _headers_with("T.Quality%")
    row = _row_with(headers, {"T.Quality%": 80, "T.Quality Target": "80%"})
    result = _dry(db, _workbook(headers, [row]))

    assert result["column_warnings"] == []
    _commit(db, _workbook(headers, [row]))
    quality = _quality(db)
    raw = _stored_raw(db)
    assert float(quality.target_value) == pytest.approx(0.8)
    assert float(quality.achievement_ratio) == pytest.approx(0.5)
    assert raw["T.QualityTarget"] == "80%"


def test_numeric_alias_above_two_uses_the_existing_percent_scale(db):
    contents = _ordinary_bytes(target=80)
    result = _dry(db, contents)
    assert result["column_warnings"] == []
    _commit(db, contents)
    quality = _quality(db)
    raw = _stored_raw(db)
    assert float(quality.target_value) == pytest.approx(0.8)
    assert float(quality.achievement_ratio) == pytest.approx(0.5)
    assert raw["T.QualityTarget"] == pytest.approx(80)


def test_optional_productivity_is_detected_and_does_not_change_the_ordinary_total(db):
    headers = _headers_with(after_grade=("Productivity", "T.Productivity%"))
    row = _row_with(headers, {"Productivity": 0.55, "T.Productivity%": 0.80})
    preview = _dry(db, _workbook(headers, [row]))
    baseline = _dry(db, _ordinary_bytes())

    assert _score(preview) == pytest.approx(_score(baseline))
    notice = _notice(preview, "optional_columns")
    assert notice is not None
    assert notice["headers"] == ["Productivity", "T.Productivity%"]
    assert _notice(preview, "unmapped_columns") is None
    _assert_no_cell_values(preview)

    _commit(db, _workbook(headers, [row]))
    productivity = _kpi_map(db)["Productivity"]
    assert float(productivity.weight_applied) == pytest.approx(0.0)
    assert float(productivity.contribution) == pytest.approx(0.0)
    assert float(_quality(db).achievement_ratio) == pytest.approx(0.5)


def test_conflicting_target_columns_are_explicit_and_unsaved(db):
    headers = _headers_with("T.Quality%")
    row = _row_with(headers, {"T.Quality%": 0.95, "T.Quality Target": 0.80})
    contents = _workbook(headers, [row])
    frame = _processed_frame(contents)
    assert float(frame.iloc[0]["T.Quality%"]) == pytest.approx(0.95)
    assert float(frame.iloc[0]["T.QualityTarget"]) == pytest.approx(0.80)
    conflict = next(item for item in frame.attrs["column_warnings"] if item["code"] == "ambiguous_alias")
    assert conflict["headers"] == ["T.Quality%", "T.Quality Target"]

    with pytest.raises(UploadProcessingError) as dry_error:
        _dry(db, contents)
    with pytest.raises(UploadProcessingError) as commit_error:
        _commit(db, contents)

    for caught in (dry_error.value, commit_error.value):
        assert "T.Quality%" in str(caught)
        assert "T.Quality Target" in str(caught)
        assert "Neither value was used as the quality target." in str(caught)
        text = str(caught) + json.dumps(caught.report)
        for marker in ("0.95", "0.8", "0.80", "ANON-1", "Anonymous"):
            assert marker not in text
        assert caught.report["column_warnings"][0]["code"] == "ambiguous_alias"
        assert caught.report["failed_teams"] == []
    assert db.query(PerformanceRecord).count() == 0
    assert db.query(KPIValue).count() == 0


def test_two_alias_spellings_are_named_and_neither_value_is_copied():
    frame = pd.DataFrame(
        [["ANON-1", 0.40, 0.80]],
        columns=["SGHCode", "T.Quality Target", "T. Quality Target"],
    )
    notices = apply_outbound_quality_target_alias(
        frame,
        ["SGHCode", "T.Quality Target", "T. Quality Target"],
        "Outbound",
    )
    assert notices[0]["headers"] == ["T.Quality Target", "T. Quality Target"]
    assert "T.Quality%" not in frame.columns
    assert float(frame.iloc[0]["T.Quality Target"]) == pytest.approx(0.40)
    assert float(frame.iloc[0]["T. Quality Target"]) == pytest.approx(0.80)


def test_direct_scorer_still_falls_back_when_only_the_alias_is_present():
    service = KPIService(_EmptyConfigRepository(), _EmptyConfigRepository())
    row = {
        "Date": WHEN,
        "A.Attend%": ATTEND_ACTUAL,
        "T.Attend%": ATTEND_TARGET,
        "A.Booking%": BOOKING_ACTUAL,
        "T.Booking%": BOOKING_TARGET,
        "A.Reachability%": REACH_ACTUAL,
        "T.Reachability%": REACH_TARGET,
        "A.QualityScore": QUALITY_ACTUAL,
        "T.QualityTarget": QUALITY_TARGET,
    }
    _score_value, _grade, achievements, weights = service.calculate_performance("Outbound", row)
    assert float(row["T.Quality%"]) == pytest.approx(0.95)
    assert achievements["Quality"] == pytest.approx(QUALITY_ACTUAL / 0.95)
    assert weights["Quality"] == pytest.approx(0.10)
    assert "Productivity" not in weights
    assert "AHT" not in weights


def test_other_team_headers_use_only_that_teams_configured_names():
    notices = classify_raw_headers(
        "Coding",
        ["Date", "Role", "A.QualityErrorsRate", "Mystery Column", "Unnamed: 0", None, ""],
    )
    assert notices == [
        {
            "sheet": "Coding",
            "code": "unmapped_columns",
            "headers": ["Mystery Column"],
            "truncated": False,
        }
    ]


def test_notices_are_bounded_deduped_and_ignore_padding():
    headers = [f"Extra {index:02d}" for index in range(1, 31)]
    headers.insert(3, "extra  01")
    headers.extend(["Unnamed: 3", "  ", None])
    notices = classify_raw_headers("Outbound", [*ORDINARY_OUTBOUND_HEADERS, *headers])
    unmapped = next(item for item in notices if item["code"] == "unmapped_columns")
    assert unmapped["truncated"] is True
    assert len(unmapped["headers"]) == 25
    assert unmapped["headers"][0] == "Extra 01"
    assert "Extra 26" not in unmapped["headers"]
    assert all(not str(header).casefold().startswith("unnamed:") for header in unmapped["headers"])


def test_upload_permission_is_unchanged():
    source = inspect.getsource(upload_router.upload_pms_file)
    assert 'require_permission("upload_data")' in source


def test_sync_response_preserves_column_warnings_beside_existing_warnings(monkeypatch):
    class _NoticingSeeder:
        def process_uploaded_file(self, filename: str, contents: bytes, **_metadata):
            return {
                "records_imported": 1,
                "teams": ["Outbound"],
                "warnings": [{"code": "duplicate_employee_month", "message": "One row was kept."}],
                "column_warnings": [
                    {
                        "sheet": "Outbound",
                        "code": "unmapped_columns",
                        "headers": ["Side Note"],
                        "truncated": False,
                    }
                ],
            }

    monkeypatch.setattr(upload_router, "DatabaseSeeder", _NoticingSeeder)
    monkeypatch.setattr(upload_router.CacheInvalidationService, "flush_all", staticmethod(lambda: None))

    async def _noop_notify(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "services.socket_service.SocketNotificationService.notify_file_upload",
        staticmethod(_noop_notify),
    )
    from fastapi import UploadFile

    response = _run(
        upload_router.upload_pms_file(
            file=UploadFile(filename="ordinary.xlsx", file=io.BytesIO(_ordinary_bytes())),
            _user={"user_id": str(uuid.uuid4()), "username": "admin"},
        )
    )
    assert response.success is True
    assert response.data["warnings"][0]["code"] == "duplicate_employee_month"
    assert response.data["column_warnings"][0]["headers"] == ["Side Note"]


def test_job_result_keeps_success_and_ambiguous_notices(monkeypatch, tmp_path):
    from config import settings
    from config.database import Base
    from models.models import ProcessingJob, User
    from sqlalchemy.pool import NullPool
    import worker

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Team.__table__,
            Employee.__table__,
            PerformanceRecord.__table__,
            KPIValue.__table__,
            TeamKPIConfig.__table__,
            EmployeeUploadBatch.__table__,
            UploadLog.__table__,
            Action.__table__,
            User.__table__,
            ProcessingJob.__table__,
        ],
    )
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = sessions()
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    monkeypatch.setattr("services.seeding_service.SessionLocal", sessions)
    def _close_notify(coro):
        if hasattr(coro, "close"):
            coro.close()

    monkeypatch.setattr(worker, "_notify", _close_notify)
    monkeypatch.setattr(worker.JobLeaseHeartbeat, "start", lambda self: None)
    monkeypatch.setattr(worker.JobLeaseHeartbeat, "stop", lambda self: None)
    monkeypatch.setattr(worker, "clear_serialization_cache", lambda: None)
    previous_jobs = settings.PMS_JOB_DATA_DIR
    settings.PMS_JOB_DATA_DIR = str(tmp_path / "jobs")
    try:
        success = _run_job(db, _ordinary_bytes(), dry_run=True)
        assert success.status == "succeeded"
        assert success.result_json["records_imported"] == 1
        assert success.result_json["column_warnings"] == []
        assert success.result_json["warnings"] == []

        headers = _headers_with("T.Quality%")
        conflict = _workbook(headers, [_row_with(headers, {"T.Quality%": 0.95, "T.Quality Target": 0.80})])
        failed = _run_job(db, conflict, dry_run=True)
        assert failed.status == "failed"
        assert failed.result_json["column_warnings"][0]["code"] == "ambiguous_alias"
        assert failed.result_json["column_warnings"][0]["headers"] == ["T.Quality%", "T.Quality Target"]
        assert "T.Quality Target" in failed.safe_error_message
        assert db.query(PerformanceRecord).count() == 0
    finally:
        settings.PMS_JOB_DATA_DIR = previous_jobs
        db.close()
        engine.dispose()


def test_known_percent_columns_include_the_ordinary_target_header():
    assert "T.Quality Target" in KNOWN_PERCENT_COLUMNS
    assert "T.Quality%" in KNOWN_PERCENT_COLUMNS


class _EmptyConfigRepository:
    def get_by_team(self, _team):
        return None


def _processed_frame(contents: bytes) -> pd.DataFrame:
    return ExcelProcessor().process_sheet_outbound(pd.ExcelFile(io.BytesIO(contents)))


def _processed_columns(contents: bytes) -> list[str]:
    return list(_processed_frame(contents).columns)


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)


def _run_job(db, contents: bytes, *, dry_run: bool):
    from services.job_storage import stage_upload
    from services.processing_job_service import ProcessingJobService
    import worker

    job_id = uuid.uuid4()
    relative = stage_upload(job_id, "ordinary.xlsx", contents)
    ProcessingJobService.create(
        db,
        kind="pms_upload",
        job_id=job_id,
        input_path=relative,
        requested_by_user_id=None,
        requested_by_name="Admin",
        request_json={"filename": "ordinary.xlsx", "dry_run": dry_run},
        max_attempts=1,
    )
    assert ProcessingJobService.claim_next(db, "header-worker") == str(job_id)
    worker.process_job_once(str(job_id), "header-worker")
    db.expire_all()
    return ProcessingJobService.get(db, job_id)
