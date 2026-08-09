import io
from pathlib import Path

import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers import upload as upload_router
from api.routers.config import get_team_config
from config.loader import load_team_config
from models.schemas import Employee, EvaluationData, PerformanceRecord
from models.models import (
    Base,
    Employee as DBEmployee,
    KPIValue,
    PerformanceRecord as DBPerformanceRecord,
    Team,
    TeamKPIConfig,
)
import services.marketing_import_service as marketing_import_module
from repositories import json_repos
from repositories.json_repos import JSONPerformanceRepository
from services.marketing_import_service import (
    MarketingImportService,
    MarketingImportValidationError,
)
from services.seeding_service import DatabaseSeeder, UploadProcessingError


REAL_WORKBOOK = Path(r"D:\Trend\PMS_Trend_All.xlsx")


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
    ]
    assert sum(len(value["kpis"]) for value in positions.values()) == 27
    assert {
        "Social Media Head",
        "Media Buyer & SEO Manager",
        "Creative Director",
    }.isdisjoint(positions)
    assert all(sum(kpi["weight"] for kpi in value["kpis"]) == pytest.approx(1.0) for value in positions.values())
    account_manager_by_key = {
        kpi["key"]: kpi
        for kpi in positions["Account Manager"]["kpis"]
    }
    assert account_manager_by_key["am_requests"]["label"] == "Requests Delivery Rate"
    assert account_manager_by_key["am_requests"]["aliases"] == ["Requests"]
    assert account_manager_by_key["am_modifications"]["label"] == "Modification Rate"
    assert account_manager_by_key["am_modifications"]["aliases"] == ["Modifications"]


def test_all_marketing_positions_and_directions_are_calculated():
    result = MarketingImportService().parse_frame(_valid_frame())

    assert result.report["employees"] == 6
    assert result.report["performance_records"] == 6
    assert result.report["warnings"] == []
    assert {record.position for record in result.records} == {
        "Media Buyer",
        "Graphic Designer",
        "Social Media Specialist",
        "Account Manager",
        "Web Developer",
        "Content Writer",
    }
    assert all(record.evaluation.score == 100.0 for record in result.records)
    assert {
        value["direction"]
        for record in result.records
        for value in record.kpi_values
    } == {"higher_better", "lower_better"}


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


@pytest.mark.skipif(not REAL_WORKBOOK.exists(), reason="User acceptance workbook is not available")
def test_real_marketing_workbook_matches_reference_counts_and_scores():
    result = MarketingImportService().parse_excel(pd.ExcelFile(REAL_WORKBOOK))
    scores = {
        (record.employee_name, record.month): record.evaluation.score
        for record in result.records
    }

    assert result.report["total_rows"] == 60
    assert result.report["employee_rows"] == 60
    assert result.report["excluded_non_employee_rows"] == 0
    assert result.report["employees"] == 8
    assert result.report["performance_records"] == 13
    assert result.report["months"] == ["May", "June"]
    assert result.report["years"] == [2026]
    assert len(result.report["warnings"]) == 14
    assert {
        (warning["column"], warning["code"])
        for warning in result.report["warnings"]
    } == {("Performance Score", "DERIVED_VALUE_MISMATCH")}
    assert scores[("Bahy Hamed Amer", "June")] == 51.10
    assert scores[("Abdelrahman Yousry", "May")] == 97.25
    assert scores[("Asser Mohamed", "June")] == 93.50
    assert scores[("Dina Samir", "May")] == 90.37
    assert scores[("Dina Samir", "June")] == 97.59


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


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (lambda frame: frame.__setitem__("Region", "Mars"), "INVALID_REGION"),
        (lambda frame: frame.__setitem__("Position", "Unknown Role"), "UNKNOWN_POSITION"),
        (lambda frame: frame.__setitem__("Actual Value", None), "INVALID_NUMBER"),
        (lambda frame: frame.__setitem__("Perspective", "Customer"), "CONFIG_MISMATCH"),
    ],
)
def test_invalid_marketing_rows_return_structured_errors(mutator, code):
    frame = _valid_frame(positions=["Media Buyer"])
    mutator(frame)

    with pytest.raises(MarketingImportValidationError) as exc_info:
        MarketingImportService().parse_frame(frame)

    assert any(error["code"] == code for error in exc_info.value.errors)
    assert all(error["sheet"] == "Marketing" for error in exc_info.value.errors)


def test_duplicate_missing_and_inconsistent_group_rows_are_rejected():
    service = MarketingImportService()

    duplicate = _valid_frame(positions=["Media Buyer"])
    duplicate = pd.concat([duplicate, duplicate.iloc[[0]]], ignore_index=True)
    with pytest.raises(MarketingImportValidationError) as duplicate_error:
        service.parse_frame(duplicate)
    assert any(error["code"] == "DUPLICATE_KPI" for error in duplicate_error.value.errors)

    missing = _valid_frame(positions=["Media Buyer"]).iloc[1:].reset_index(drop=True)
    with pytest.raises(MarketingImportValidationError) as missing_error:
        service.parse_frame(missing)
    assert any(error["code"] == "MISSING_KPI" for error in missing_error.value.errors)

    inconsistent = _valid_frame(positions=["Media Buyer"])
    inconsistent.loc[0, "Employee Name"] = "Different Name"
    with pytest.raises(MarketingImportValidationError) as inconsistent_error:
        service.parse_frame(inconsistent)
    assert any(error["code"] == "INCONSISTENT_GROUP" for error in inconsistent_error.value.errors)


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


def test_json_reupload_replaces_same_employee_period_and_preserves_other_rows(monkeypatch):
    existing = PerformanceRecord(
        id="EMP1_May",
        employee_id="EMP1",
        employee_name="Old",
        team="Marketing",
        month="May",
        year=2026,
        evaluation=EvaluationData(score=40, grade="E"),
    )
    other = PerformanceRecord(
        id="EMP2_2026_May",
        employee_id="EMP2",
        employee_name="Other",
        team="Marketing",
        month="May",
        year=2026,
        evaluation=EvaluationData(score=80, grade="C"),
    )
    state = [existing.model_dump(), other.model_dump()]

    monkeypatch.setattr(json_repos, "_load_json", lambda filename, default: list(state))
    monkeypatch.setattr(
        json_repos,
        "_save_json",
        lambda filename, data: state.__setitem__(slice(None), list(data)),
    )
    replacement = existing.model_copy(
        update={
            "id": "EMP1_2026_May",
            "employee_name": "New",
            "evaluation": EvaluationData(score=90, grade="B"),
        }
    )

    JSONPerformanceRepository().save_all([replacement])
    records = [PerformanceRecord(**item) for item in state]

    assert len(records) == 2
    assert next(record for record in records if record.employee_id == "EMP1").employee_name == "New"
    assert next(record for record in records if record.employee_id == "EMP2").employee_name == "Other"


def test_json_repository_filters_marketing_by_year_position_and_region(monkeypatch):
    parsed = MarketingImportService().parse_frame(
        _valid_frame(positions=["Media Buyer", "Graphic Designer"])
    )
    repo = JSONPerformanceRepository()
    monkeypatch.setattr(repo, "get_all", lambda: parsed.records)

    records = repo.get_filtered(
        team="Marketing",
        year=2026,
        position="Media Buyer",
        region="EGY",
    )

    assert len(records) == 1
    assert records[0].position == "Media Buyer"


def test_dry_run_performs_no_repository_or_database_writes(monkeypatch):
    seeder = DatabaseSeeder()
    fail = lambda *args, **kwargs: pytest.fail("dry run attempted a write")
    monkeypatch.setattr(seeder.employee_repo, "save_all", fail)
    monkeypatch.setattr(seeder.performance_repo, "save_all", fail)
    monkeypatch.setattr(seeder.uploads_repo, "save", fail)
    monkeypatch.setattr(seeder, "_sync_to_database", fail)

    result = seeder.process_uploaded_file(
        "marketing.xlsx",
        _workbook_bytes(_valid_frame(positions=["Media Buyer"])),
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["marketing"]["performance_records"] == 1


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
        assert session.query(TeamKPIConfig).count() == 27

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


def test_failed_publish_leaves_json_snapshots_untouched_and_rolls_back_database(monkeypatch):
    seeder = DatabaseSeeder()
    existing_employee = Employee(id="OLD", name="Old", team="Inbound")
    existing_record = PerformanceRecord(
        id="OLD_2026_May",
        employee_id="OLD",
        employee_name="Old",
        team="Inbound",
        month="May",
        year=2026,
        evaluation=EvaluationData(score=80, grade="C"),
    )
    restored = {}

    monkeypatch.setattr(seeder.employee_repo, "get_all", lambda: [existing_employee])
    monkeypatch.setattr(seeder.performance_repo, "get_all", lambda: [existing_record])
    monkeypatch.setattr(seeder.uploads_repo, "get_all", lambda: [])
    monkeypatch.setattr(seeder.employee_repo, "replace_all", lambda rows: restored.setdefault("employees", rows))
    monkeypatch.setattr(seeder.performance_repo, "replace_all", lambda rows: restored.setdefault("records", rows))
    monkeypatch.setattr(seeder.uploads_repo, "replace_all", lambda rows: restored.setdefault("uploads", rows))
    monkeypatch.setattr(seeder.employee_repo, "save_all", lambda rows: rows)
    monkeypatch.setattr(seeder.performance_repo, "save_all", lambda rows: rows)
    monkeypatch.setattr(seeder.uploads_repo, "save", lambda row: row)
    monkeypatch.setattr(
        seeder,
        "_sync_to_database",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("database failure")),
    )

    class DummySession:
        def __init__(self):
            self.rolled_back = False

        def add(self, _row):
            pass

        def flush(self):
            pass

        def commit(self):
            pytest.fail("failed upload must not commit")

        def rollback(self):
            self.rolled_back = True

        def close(self):
            pass

    session = DummySession()
    monkeypatch.setattr("services.seeding_service.SessionLocal", lambda: session)

    with pytest.raises(UploadProcessingError):
        seeder.process_uploaded_file(
            "marketing.xlsx",
            _workbook_bytes(_valid_frame(positions=["Media Buyer"])),
        )

    assert session.rolled_back is True
    # Hosted runtime persistence is database-only. A failed transaction must
    # not write to or rewrite the legacy JSON snapshots.
    assert restored == {}


@pytest.mark.asyncio
async def test_upload_router_returns_422_for_marketing_validation_errors(monkeypatch):
    async def noop_notify(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "services.socket_service.SocketNotificationService.notify_file_upload",
        noop_notify,
    )
    frame = _valid_frame(positions=["Media Buyer"])
    frame["Region"] = "Mars"
    upload = UploadFile(filename="marketing.xlsx", file=io.BytesIO(_workbook_bytes(frame)))

    with pytest.raises(HTTPException) as exc_info:
        await upload_router.upload_pms_file(file=upload, dry_run=True, _user=object())

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["errors"][0]["sheet"] == "Marketing"
    assert any(error["code"] == "INVALID_REGION" for error in exc_info.value.detail["errors"])
