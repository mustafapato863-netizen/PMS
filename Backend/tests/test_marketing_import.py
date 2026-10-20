import io
import math
import os
from pathlib import Path

import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers import upload as upload_router
from api.routers.config import get_team_config
from config.loader import load_team_config
from models.schemas import Employee, EvaluationData, PerformanceRecord
from models.models import (
    Action,
    Base,
    Employee as DBEmployee,
    KPIValue,
    PerformanceRecord as DBPerformanceRecord,
    Team,
    TeamKPIConfig,
)
import services.marketing_import_service as marketing_import_module
from services.marketing_import_service import MarketingImportService
from services.seeding_service import DatabaseSeeder, UploadProcessingError


REAL_WORKBOOK = Path(r"D:\Trend\PMS_Trend_All.xlsx")


@pytest.fixture(autouse=True)
def _upload_database(monkeypatch):
    """Uploads read the database (including the Action table). Tests that do not bring their own session get this one."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("services.seeding_service.SessionLocal", sessionmaker(bind=engine))
    yield engine
    engine.dispose()


def _valid_frame(*, positions: list[str] | None = None) -> pd.DataFrame:
    config = load_team_config("Marketing")
    position_configs = config["performance_levels"]["Employee"]["positions"]
    selected = positions or list(position_configs)
    rows = []
    for position_index, position in enumerate(selected, start=1):
        definitions = position_configs[position]["kpis"]
        contributions = []
        position_rows = []
        for definition in definitions:
            target = 100.0
            actual = 50.0 if definition["direction"] == "lower_better" else 120.0
            achievement = target / actual if definition["direction"] == "lower_better" else actual / target
            effective = min(achievement, 1.0)
            contribution = effective * definition["weight"]
            contributions.append(contribution)
            position_rows.append(
                {
                    "Employee ID": f"SGHD90{position_index:03d}",
                    "Region": "EGY",
                    "Team": "Marketing",
                    "Employee Name": f"Employee {position_index}",
                    "Position": position,
                    "Performance Level": "Employee",
                    "Date": pd.Timestamp("2026-07-01"),
                    "Perspective": definition["perspective"],
                    "KPI": definition["label"],
                    "Direction": definition["direction"].replace("_", " ").title(),
                    "Weight": definition["weight"],
                    "Target Value": target,
                    "Target Unit": definition["unit"],
                    "Actual Value": actual,
                    "Actual Unit": definition["unit"],
                    "Achievement %": effective,
                    "Weighted Score %": contribution,
                }
            )
        score = min(sum(contributions), 1.0)
        for row in position_rows:
            row["Performance Score"] = score
        rows.extend(position_rows)
    return pd.DataFrame(rows)


def _workbook_bytes(frame: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Marketing", index=False)
    return output.getvalue()


def test_marketing_config_covers_all_employee_positions_and_kpis():
    config = load_team_config("Marketing")
    positions = config["performance_levels"]["Employee"]["positions"]

    assert list(positions) == [
        "Media Buyer",
        "Graphic Designer",
        "Social Media Specialist",
        "Account Manager",
        "Web Developer",
        "Content Writer",
        "Creative Director",
        "Media Buyer & SEO Manager",
        "Social Media Head",
    ]
    assert sum(len(value["kpis"]) for value in positions.values()) == 45
    assert {
        "Social Media Head",
        "Media Buyer & SEO Manager",
        "Creative Director",
    } <= set(positions)
    assert all(sum(kpi["weight"] for kpi in value["kpis"]) == pytest.approx(1.0) for value in positions.values())
    account_manager_by_key = {
        kpi["key"]: kpi
        for kpi in positions["Account Manager"]["kpis"]
    }
    assert account_manager_by_key["am_requests"]["label"] == "Requests Delivery Rate"
    assert account_manager_by_key["am_requests"]["aliases"] == ["Requests"]
    assert account_manager_by_key["am_modifications"]["label"] == "Modification Rate"
    assert account_manager_by_key["am_modifications"]["aliases"] == ["Modifications"]
    period_variant = positions["Account Manager"]["period_variants"][0]
    assert period_variant["id"] == "may_2026_onward"
    assert period_variant["effective_from"] == "2026-05-01"
    assert [kpi["key"] for kpi in period_variant["kpis"]] == [
        "am_requests",
        "am_edit_rate",
        "am_projects_ontime",
    ]
    assert sum(kpi["weight"] for kpi in period_variant["kpis"]) == pytest.approx(1.0)
    assert positions["Web Developer"]["kpis"][0]["direction"] == "higher_better"
    assert positions["Web Developer"]["kpis"][3]["direction"] == "higher_better"
    assert positions["Content Writer"]["kpis"][0]["unit"] == "%"
    content_writer_directions = {
        kpi["key"]: kpi["direction"]
        for kpi in positions["Content Writer"]["kpis"]
    }
    assert content_writer_directions["cw_error_free"] == "higher_better"
    web_developer_by_key = {kpi["key"]: kpi for kpi in positions["Web Developer"]["kpis"]}
    assert web_developer_by_key["wd_page_speed"]["label"] == "Page load time"
    assert web_developer_by_key["wd_page_speed"]["direction"] == "lower_better"


def test_all_marketing_positions_and_directions_are_calculated():
    result = MarketingImportService().parse_frame(_valid_frame())

    assert result.report["employees"] == 9
    assert result.report["performance_records"] == 9
    assert result.report["warnings"] == []
    assert {record.position for record in result.records} == {
        "Media Buyer",
        "Graphic Designer",
        "Social Media Specialist",
        "Account Manager",
        "Web Developer",
        "Content Writer",
        "Creative Director",
        "Media Buyer & SEO Manager",
        "Social Media Head",
    }
    assert all(record.evaluation.score == 100.0 for record in result.records)
    assert {
        value["direction"]
        for record in result.records
        for value in record.kpi_values
    } == {"higher_better", "lower_better"}


def test_rows_with_no_kpi_measurements_are_excluded_with_warning():
    frame = _valid_frame(positions=["Media Buyer"])
    frame.loc[:, ["Target Value", "Actual Value"]] = float("nan")

    result = MarketingImportService().parse_frame(frame)

    assert result.report["employee_rows"] == 6
    assert result.report["excluded_incomplete_rows"] == 6
    assert result.report["employees"] == 0
    assert result.report["performance_records"] == 0
    assert {warning["code"] for warning in result.report["warnings"]} == {"INCOMPLETE_KPI_ROW"}
    assert {warning["row"] for warning in result.report["warnings"]} == set(range(2, 8))


@pytest.mark.asyncio
async def test_config_api_resolves_one_marketing_position_without_mixing_kpis():
    response = await get_team_config(
        "Marketing",
        performance_level="Employee",
        position="Media Buyer",
    )

    assert response["data"]["position_name"] == "Media Buyer"
    assert len(response["data"]["kpis"]) == 6
    assert all(kpi["key"].startswith("mb_") for kpi in response["data"]["kpis"])


@pytest.mark.skipif(
    os.environ.get("CI") == "true" or not REAL_WORKBOOK.exists(),
    reason="User acceptance workbook is only available in the local acceptance environment",
)
def test_real_marketing_workbook_imports_and_rejects_only_the_bad_employee_month():
    """The acceptance workbook is a live file: months are added and earlier rows are corrected.

    A frozen snapshot of its counts and scores goes stale on the next edit, so this checks
    what must hold for any version of the workbook. The one employee-month the current
    workbook gets wrong (September 2026: weights sum to 0.8 and two configured KPIs are
    missing) is rejected alone, and the rest still imports. Exact scoring is pinned by the
    synthetic-frame tests in this module. No employee names or IDs are asserted.
    """
    result = MarketingImportService().parse_excel(pd.ExcelFile(REAL_WORKBOOK))
    report = result.report
    warning_codes = [warning["code"] for warning in report["warnings"]]
    record_keys = {(record.employee_id, record.month, record.year) for record in result.records}
    calendar = ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"]

    assert report["total_rows"] > 0
    assert report["employee_rows"] + report["excluded_non_employee_rows"] == report["total_rows"]
    assert report["excluded_incomplete_rows"] == warning_codes.count("INCOMPLETE_KPI_ROW")
    assert set(warning_codes) <= {
        "INCOMPLETE_KPI_ROW",
        "DERIVED_VALUE_MISMATCH",
        "DIRECTION_MISMATCH",
        "PERSPECTIVE_MISMATCH",
        "EMPLOYEE_MONTH_REJECTED",
    }
    # One rejected employee-month, with its rows and reasons, and one warning for it.
    rejected = report["rejected_employee_months"]
    assert [(entry["year"], entry["month"]) for entry in rejected] == [(2026, "September")]
    assert rejected[0]["rows"] == [133, 134, 135, 136, 137]
    assert {reason["code"] for reason in rejected[0]["reasons"]} == {"WEIGHT_SUM", "MISSING_KPI"}
    assert warning_codes.count("EMPLOYEE_MONTH_REJECTED") == len(rejected)
    # The error-free content rule is configured higher-better; sheet rows that say Lower Better only warn.
    assert warning_codes.count("DIRECTION_MISMATCH") == 3
    # A rejected employee-month is never stored.
    rejected_key = (rejected[0]["employee_id"], rejected[0]["year"], rejected[0]["month"])
    assert all((record.employee_id, record.year, record.month) != rejected_key for record in result.records)
    assert report["performance_records"] == len(result.records) == len(record_keys)
    # Employees are keyed by ID. One ID can carry different names in different months, so names are not counted.
    assert report["employees"] == len({record.employee_id for record in result.records})
    assert report["months"] == [month for month in calendar if month in {record.month for record in result.records}]
    assert report["years"] == sorted({record.year for record in result.records})
    assert all(math.isfinite(record.evaluation.score) and record.evaluation.score >= 0 for record in result.records)


def test_zero_target_and_actual_produce_zero_higher_better_contribution():
    frame = _valid_frame(positions=["Media Buyer"])
    target_row = frame["KPI"] == "# App installs"
    frame.loc[target_row, ["Target Value", "Actual Value", "Achievement %", "Weighted Score %"]] = 0
    frame["Performance Score"] = 0.9

    record = MarketingImportService().parse_frame(frame).records[0]
    app_installs = next(value for value in record.kpi_values if value["kpi_key"] == "mb_app_installs")

    assert app_installs["achievement_ratio"] == 0
    assert app_installs["contribution"] == 0
    assert record.evaluation.score == 90.0


def _reason_codes(result) -> set[str]:
    return {reason["code"] for entry in result.report["rejected_employee_months"] for reason in entry["reasons"]}


# Old: each of these raised MarketingImportValidationError for the whole upload.
# New: each rejects only its employee-month, and the report carries the reason.
@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (lambda frame: frame.__setitem__("Region", "Mars"), "INVALID_REGION"),
        (lambda frame: frame.__setitem__("Position", "Unknown Role"), "UNKNOWN_POSITION"),
        (lambda frame: frame.__setitem__("Actual Value", None), "INVALID_NUMBER"),
    ],
)
def test_invalid_marketing_rows_reject_their_employee_month(mutator, code):
    frame = _valid_frame(positions=["Media Buyer"])
    mutator(frame)

    result = MarketingImportService().parse_frame(frame)

    assert result.records == []
    assert _reason_codes(result) == {code}
    assert {warning["code"] for warning in result.report["warnings"]} == {"EMPLOYEE_MONTH_REJECTED"}


# Old: a Perspective that differed from config raised CONFIG_MISMATCH for the whole upload.
# New: it is a warning, and the row's own perspective is stored.
def test_perspective_that_differs_from_config_is_a_warning_and_the_row_value_is_kept():
    frame = _valid_frame(positions=["Media Buyer"])
    frame["Perspective"] = "Customer"

    result = MarketingImportService().parse_frame(frame)

    assert len(result.records) == 1
    assert result.report["rejected_employee_months"] == []
    assert any(warning["code"] == "PERSPECTIVE_MISMATCH" for warning in result.report["warnings"])
    assert {value["perspective"] for value in result.records[0].kpi_values} == {"Customer"}


# Old: a duplicate KPI, a missing KPI and an inconsistent group each raised for the whole upload.
# New: each rejects only its employee-month, and the report lists the reasons.
def test_duplicate_missing_and_inconsistent_group_rows_reject_only_their_employee_month():
    service = MarketingImportService()

    duplicate = _valid_frame(positions=["Media Buyer"])
    duplicate = pd.concat([duplicate, duplicate.iloc[[0]]], ignore_index=True)
    result = service.parse_frame(duplicate)
    assert result.records == []
    assert "DUPLICATE_KPI" in _reason_codes(result)

    missing = _valid_frame(positions=["Media Buyer"]).iloc[1:].reset_index(drop=True)
    result = service.parse_frame(missing)
    assert result.records == []
    assert {"WEIGHT_SUM", "MISSING_KPI"} <= _reason_codes(result)

    inconsistent = _valid_frame(positions=["Media Buyer"])
    inconsistent.loc[0, "Employee Name"] = "Different Name"
    result = service.parse_frame(inconsistent)
    assert result.records == []
    assert _reason_codes(result) == {"INCONSISTENT_GROUP"}


def test_non_employee_rows_are_excluded_and_derived_mismatch_is_warning():
    frame = _valid_frame(positions=["Media Buyer"])
    management_row = frame.iloc[[0]].copy()
    frame.loc[0, "Achievement %"] = 0.5
    management_row["Performance Level"] = "Managerial"
    combined = pd.concat([frame, management_row], ignore_index=True)

    result = MarketingImportService().parse_frame(combined)

    assert result.report["employee_rows"] == 6
    assert result.report["excluded_non_employee_rows"] == 1
    assert any(warning["code"] == "DERIVED_VALUE_MISMATCH" for warning in result.report["warnings"])


def test_account_manager_is_an_employee_position_like_social_media():
    frame = _valid_frame(positions=["Account Manager"])
    frame["Performance Level"] = "Managerial"

    result = MarketingImportService().parse_frame(frame)

    assert result.report["employee_rows"] == 7
    assert result.report["excluded_non_employee_rows"] == 0
    assert len(result.records) == 1
    assert result.records[0].position == "Account Manager"
    assert result.records[0].performance_level == "Employee"
    assert {value["kpi_key"] for value in result.records[0].kpi_values} == {
        "am_campaign_delivery",
        "am_campaign_delivery_ontime",
        "am_deficit",
        "am_requests",
        "am_modifications",
        "am_edit_rate",
        "am_projects_ontime",
    }


def test_account_manager_legacy_kpi_names_remain_upload_compatible():
    frame = _valid_frame(positions=["Account Manager"])
    frame["KPI"] = frame["KPI"].replace({
        "Requests Delivery Rate": "Requests",
        "Modification Rate": "Modifications",
    })

    result = MarketingImportService().parse_frame(frame)

    assert len(result.records) == 1
    assert {value["kpi_key"] for value in result.records[0].kpi_values} == {
        "am_campaign_delivery",
        "am_campaign_delivery_ontime",
        "am_deficit",
        "am_requests",
        "am_modifications",
        "am_edit_rate",
        "am_projects_ontime",
    }


def _content_writer_frame(error_free_actual: float, error_free_direction: str) -> pd.DataFrame:
    frame = _valid_frame(positions=["Content Writer"])
    mask = frame["KPI"] == "Error-free content ratio"
    frame.loc[mask, "Actual Value"] = error_free_actual
    frame.loc[mask, "Direction"] = error_free_direction
    frame["Achievement %"] = None
    frame["Weighted Score %"] = None
    frame["Performance Score"] = None
    return frame


@pytest.mark.parametrize("uploaded_direction", ["Higher Better", "Lower Better"])
def test_cw_error_free_is_scored_higher_better(uploaded_direction):
    # 80% error-free content against a 100% target is 0.8 achievement when
    # higher is better (the old lower_better rule gave 1.0 = full credit).
    frame = _content_writer_frame(80.0, uploaded_direction)

    result = MarketingImportService().parse_frame(frame)

    assert len(result.records) == 1
    value = next(v for v in result.records[0].kpi_values if v["kpi_key"] == "cw_error_free")
    assert value["direction"] == "higher_better"
    assert value["achievement_ratio"] == pytest.approx(0.8)
    assert value["contribution"] == pytest.approx(0.8 * 0.30)
    # cw_organic_traffic 0.40 + cw_delivery_timeliness 0.30 (both 120/100 capped) + 0.24
    assert result.records[0].evaluation.score == pytest.approx(94.0)


def test_cw_error_free_rewards_more_error_free_content():
    low = MarketingImportService().parse_frame(_content_writer_frame(60.0, "Higher Better"))
    high = MarketingImportService().parse_frame(_content_writer_frame(95.0, "Higher Better"))

    assert high.records[0].evaluation.score > low.records[0].evaluation.score


def test_web_developer_old_page_load_speed_label_remains_upload_compatible():
    frame = _valid_frame(positions=["Web Developer"])
    assert "Page load time" in set(frame["KPI"])
    frame["KPI"] = frame["KPI"].replace({"Page load time": "Page load speed"})

    result = MarketingImportService().parse_frame(frame)

    assert len(result.records) == 1
    value = next(v for v in result.records[0].kpi_values if v["kpi_key"] == "wd_page_speed")
    assert value["label"] == "Page load time"
    assert value["direction"] == "lower_better"


def test_marketing_grade_uses_the_canonical_system_rule_not_uploaded_data(monkeypatch):
    frame = _valid_frame(positions=["Account Manager"])
    frame["Grade"] = "E"
    monkeypatch.setattr(
        marketing_import_module,
        "calculate_grade",
        lambda score, thresholds: "D",
    )

    result = MarketingImportService().parse_frame(frame)

    assert result.records[0].evaluation.grade == "D"
    assert result.records[0].status == "Below"


def test_dry_run_performs_no_repository_or_database_writes(monkeypatch, tmp_path):
    seeder = DatabaseSeeder()
    fail = lambda *args, **kwargs: pytest.fail("dry run attempted a write")
    monkeypatch.setattr(seeder, "_sync_to_database", fail)

    result = seeder.process_uploaded_file(
        "marketing.xlsx",
        _workbook_bytes(_valid_frame(positions=["Media Buyer"])),
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["marketing"]["performance_records"] == 1
    assert list(tmp_path.iterdir()) == []


def _good_july_and_bad_august_frame() -> pd.DataFrame:
    good = _valid_frame(positions=["Media Buyer"])
    bad = _valid_frame(positions=["Media Buyer"])
    bad["Date"] = pd.Timestamp("2026-08-01")
    bad.loc[0, "Weight"] = bad.loc[0, "Weight"] + 0.5  # August's weights now sum to more than 1
    return pd.concat([good, bad], ignore_index=True)


def test_dry_run_and_commit_reject_the_same_employee_month(monkeypatch):
    workbook = _workbook_bytes(_good_july_and_bad_august_frame())
    seeder = DatabaseSeeder()

    dry_run = seeder.process_uploaded_file("marketing.xlsx", workbook, dry_run=True)

    assert dry_run["marketing"]["performance_records"] == 1
    assert [(entry["year"], entry["month"]) for entry in dry_run["marketing"]["rejected_employee_months"]] == [
        (2026, "August"),
    ]
    assert any(warning["code"] == "EMPLOYEE_MONTH_REJECTED" for warning in dry_run["marketing"]["warnings"])

    # The commit path reads the same parse result, so it must reject the same month and store the rest.
    monkeypatch.setattr(seeder, "_sync_to_database", lambda *args, **kwargs: None)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine, autoflush=False)
    monkeypatch.setattr("services.seeding_service.SessionLocal", lambda: session)

    committed = seeder.process_uploaded_file("marketing.xlsx", workbook)

    assert committed["marketing"]["performance_records"] == dry_run["marketing"]["performance_records"]
    assert committed["marketing"]["rejected_employee_months"] == dry_run["marketing"]["rejected_employee_months"]
    engine.dispose()


def test_database_sync_upserts_marketing_period_and_position_config():
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
            Action.__table__,
        ],
    )
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        parsed = MarketingImportService().parse_frame(_valid_frame(positions=["Media Buyer"]))
        seeder = DatabaseSeeder()
        seeder._sync_to_database(parsed.records, parsed.employees, db_session=session)
        session.flush()

        assert session.query(Team).filter(Team.name == "Marketing").count() == 1
        assert session.query(Team).filter(Team.name == "Marketing").one().team_level == "employee"
        assert session.query(DBEmployee).count() == 1
        assert session.query(DBEmployee).one().position_name == "Media Buyer"
        assert session.query(DBPerformanceRecord).count() == 1
        assert session.query(DBPerformanceRecord).one().year == 2026
        assert session.query(DBPerformanceRecord).one().region == "EGY"
        assert session.query(KPIValue).count() == 6
        assert session.query(TeamKPIConfig).count() == 45

        parsed.records[0].evaluation.score = 88.0
        parsed.records[0].evaluation.grade = "B"
        parsed.records[0].status = "Meets"
        for value in parsed.records[0].kpi_values:
            value["contribution"] = float(value["contribution"]) * 0.88
        seeder._sync_to_database(parsed.records, parsed.employees, db_session=session)
        session.flush()

        assert session.query(DBPerformanceRecord).count() == 1
        assert float(session.query(DBPerformanceRecord).one().score) == 88.0
        assert session.query(KPIValue).count() == 6
    finally:
        session.close()


def test_failed_publish_rolls_back_database_and_writes_no_data_file(monkeypatch, tmp_path):
    seeder = DatabaseSeeder()
    monkeypatch.setattr(
        seeder,
        "_sync_to_database",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("database failure")),
    )

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    class TrackingSession(Session):
        def __init__(self):
            super().__init__(bind=engine, autoflush=False)
            self.rolled_back = False

        def commit(self):
            pytest.fail("failed upload must not commit")

        def rollback(self):
            self.rolled_back = True
            super().rollback()

    session = TrackingSession()
    monkeypatch.setattr("services.seeding_service.SessionLocal", lambda: session)

    with pytest.raises(UploadProcessingError, match="database failure"):
        seeder.process_uploaded_file(
            "marketing.xlsx",
            _workbook_bytes(_valid_frame(positions=["Media Buyer"])),
        )

    assert session.rolled_back is True
    # Runtime persistence is database-only. A failed transaction writes no data file at all.
    assert list(tmp_path.iterdir()) == []
    # A real transaction also proves that the staged upload batch was removed.
    from models.models import EmployeeUploadBatch

    with Session(bind=engine) as verification:
        assert verification.query(EmployeeUploadBatch).count() == 0
        assert verification.query(DBPerformanceRecord).count() == 0
        assert verification.query(KPIValue).count() == 0
    engine.dispose()


@pytest.mark.asyncio
async def test_upload_router_returns_422_for_a_missing_marketing_column(monkeypatch):
    # Old: a Region of "Mars" returned 422 for the whole upload. New: that is a rejected employee-month,
    # covered by the tests above. Only a missing required column still fails the whole upload.
    async def noop_notify(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "services.socket_service.SocketNotificationService.notify_file_upload",
        noop_notify,
    )
    frame = _valid_frame(positions=["Media Buyer"]).drop(columns=["Weight"])
    upload = UploadFile(filename="marketing.xlsx", file=io.BytesIO(_workbook_bytes(frame)))

    with pytest.raises(HTTPException) as exc_info:
        await upload_router.upload_pms_file(file=upload, dry_run=True, _user=object())

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["errors"][0]["sheet"] == "Marketing"
    assert any(error["code"] == "MISSING_COLUMN" for error in exc_info.value.detail["errors"])
