"""Monthly evaluation settings use the real resolver, approval, upload pin, and reads."""

import io
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers.evaluation_settings import router as evaluation_router
from config.database import get_db
from openpyxl import Workbook

from models.models import (
    Action,
    Base,
    Employee,
    EmployeeUploadBatch,
    EvaluationRevision,
    EvaluationScope,
    GeneratedReport,
    KPIValue,
    PerformancePlan,
    PerformanceRecord,
    Team,
    TeamConfigurationVersion,
    TeamKPIConfig,
    UploadLog,
    User,
    UserTeamAssignment,
)
from services.dashboard_record_service import DashboardRecordService
from services.evaluation.access import TargetConflict
from services.evaluation.resolver import overlay_pinned_kpis, score_basis
from services.evaluation.workflow import EvaluationWorkflow
from services.management_bsc_service import ManagementBSCService
from services.seeding_service import DatabaseSeeder
from utils.kpi_direction import resolve_kpi_direction
from models.models import ManagementKPIConfig


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Team.__table__,
            User.__table__,
            Employee.__table__,
            UserTeamAssignment.__table__,
            PerformanceRecord.__table__,
            KPIValue.__table__,
            Action.__table__,
            PerformancePlan.__table__,
            GeneratedReport.__table__,
            TeamConfigurationVersion.__table__,
            EvaluationScope.__table__,
            EvaluationRevision.__table__,
            ManagementKPIConfig.__table__,
            TeamKPIConfig.__table__,
            EmployeeUploadBatch.__table__,
            UploadLog.__table__,
        ],
    )
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield session
    session.close()


def _user(role: str, name: str) -> User:
    return User(
        id=uuid.uuid4(),
        full_name=name,
        username=name,
        email=f"{name}@example.com",
        password_hash="test-hash",
        role=role,
    )


def _actor(user: User, **extra) -> dict:
    return {
        "user_id": str(user.id),
        "role": user.role,
        "employee_id": user.employee_id or "",
        "accessible_teams": extra.get("accessible_teams", []),
        "accessible_functions": extra.get("accessible_functions", []),
        "accessible_regions": extra.get("accessible_regions", []),
        "accessible_branches": extra.get("accessible_branches", []),
        "has_unrestricted_team_access": user.role in {"Admin", "General Manager", "Performance Team"},
        "legacy_unscoped": False,
    }


def _coding_scope(workflow: EvaluationWorkflow, actor: dict) -> dict:
    catalog = workflow.sync_catalog(actor)
    scope = next(
        item for item in catalog["scopes"]
        if item["display_name"].casefold() == "coding" and item["performance_level"] == "Employee" and item["position_name"] == ""
    )
    assert scope["readiness"] == "supported", scope
    return scope


def _line_edit(lines: list[dict], target: float) -> list[dict]:
    edited = []
    for index, line in enumerate(lines):
        edited.append({
            **line,
            "weight": 1 if index == 0 else 0,
            "direction": "higher_better",
            "target_mode": "fixed",
            "target": target if index == 0 else 1,
        })
    return edited


def test_july_and_august_stay_independent_until_explicit_apply(db):
    admin = _user("Admin", "eval-admin")
    owner = admin
    coding = Team(id=uuid.uuid4(), name="Coding", db_name="Coding", display_name="Coding", region="UAE", team_level="employee")
    other = Team(id=uuid.uuid4(), name="Future Desk", db_name="Future Desk", display_name="Future Desk", region="UAE", team_level="employee")
    employee = Employee(id=uuid.uuid4(), employee_id="C-1", name="Coder", team=coding, region="UAE", performance_level="Employee")
    july = PerformanceRecord(
        id=uuid.uuid4(), year=2026, employee_id=employee.id, team_id=coding.id, month="July",
        performance_level="Employee", score=Decimal("70.00"), grade="D", status="Below",
        record_payload={"manager_notes": "keep the july note", "evaluation": {"score": 70, "grade": "D"}},
    )
    august = PerformanceRecord(
        id=uuid.uuid4(), year=2026, employee_id=employee.id, team_id=coding.id, month="August",
        performance_level="Employee", score=Decimal("71.00"), grade="D", status="Below",
        record_payload={"manager_notes": "keep the august note", "evaluation": {"score": 71, "grade": "D"}},
    )
    other_record = PerformanceRecord(
        id=uuid.uuid4(), year=2026, employee_id=employee.id, team_id=other.id, month="August",
        performance_level="Employee", score=Decimal("88.00"), grade="B", status="Meets",
        record_payload={"evaluation": {"score": 88, "grade": "B"}},
    )
    db.add_all([admin, coding, other, employee, july, august, other_record])
    db.flush()
    july_kpi = KPIValue(id=uuid.uuid4(), record_id=july.id, record_year=2026, kpi_key="placeholder", actual_value=60, target_value=40, achievement_ratio=1, weight_applied=1, contribution=1)
    august_kpi = KPIValue(id=uuid.uuid4(), record_id=august.id, record_year=2026, kpi_key="placeholder", actual_value=60, target_value=40, achievement_ratio=1, weight_applied=1, contribution=1)
    db.add_all([july_kpi, august_kpi])
    plan = PerformancePlan(
        id=uuid.uuid4(), name="July coaching plan", scope_type="Team", team_id=coding.id,
        performance_level="Employee", period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
        due_date=date(2026, 7, 31), owner_user_id=owner.id, baseline_value=1, target_value=10,
        outcome_unit="%", outcome_direction="higher_better", status="Draft",
    )
    action = Action(id=uuid.uuid4(), team_id=coding.id, month="July", year=2026, action_type="Coaching", action_text="Coach the queue", status="Open")
    report = GeneratedReport(
        id=uuid.uuid4(), name="July pack", report_type="team", scope_summary="Coding", period_label="July 2026",
        created_by_name="eval-admin", output_format="pdf", status="ready", file_name="july.pdf",
        content_type="application/pdf", file_data=b"saved-report", configuration={}, scope_json={},
        final_definition_json={}, narrative_snapshot_json={"text": "original narrative"},
        data_snapshot_json={"score": 70}, validation_json={},
    )
    db.add_all([plan, action, report])
    db.commit()

    actor = _actor(admin)
    workflow = EvaluationWorkflow(db)
    scope = _coding_scope(workflow, actor)
    blocked = next(item for item in workflow.sync_catalog(actor)["scopes"] if item["display_name"] == "Future Desk")
    assert blocked["readiness"] == "blocked"
    assert blocked["block_reason"]
    with pytest.raises(Exception) as blocked_edit:
        workflow.open_draft(actor, blocked["id"], 2026, 7)
    assert getattr(blocked_edit.value, "status_code", 422) in {422, 409}

    july_draft = workflow.open_draft(actor, scope["id"], 2026, 7)
    edited = _line_edit(july_draft["lines"], 55)
    july_kpi.kpi_key = edited[0]["kpi_key"]
    august_kpi.kpi_key = edited[0]["kpi_key"]
    db.commit()
    workflow.edit_draft(actor, july_draft["id"], edited)
    with pytest.raises(Exception):
        workflow.edit_draft(actor, july_draft["id"], [{**edited[0], "direction": "custom_formula"}])
    weighted = _line_edit(july_draft["lines"], 55)
    weighted[0]["weight"] = 0.5
    weighted[1]["weight"] = 0.5
    for line in weighted[2:]:
        line["weight"] = 0
    saved_weights = workflow.edit_draft(actor, july_draft["id"], weighted, weight_only=False)
    assert saved_weights["lines"][0]["weight"] == 0.5
    workflow.edit_draft(actor, july_draft["id"], edited)
    approved = workflow.approve(actor, july_draft["id"])
    assert approved["status"] == "approved"
    db.refresh(july)
    assert float(july.score) == 70.0

    august_draft = workflow.open_draft(actor, scope["id"], 2026, 8, copy_previous=True)
    assert august_draft["lines"][0]["target"] == 55
    august_lines = _line_edit(august_draft["lines"], 65)
    workflow.edit_draft(actor, august_draft["id"], august_lines)
    workflow.approve(actor, august_draft["id"])
    reads = workflow.reads(actor, scope["id"], 2026, [7, 8])
    july_body, august_body = reads["periods"]
    assert july_body["lines"][0]["target"] == 55
    assert august_body["lines"][0]["target"] == 65
    assert july_body["stored_score"] == 70.0
    assert august_body["stored_score"] == 71.0
    again = workflow.reads(actor, scope["id"], 2026, [7, 8])
    assert again == reads

    version = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(approved["id"])).one()
    july_period = workflow.period(actor, scope["id"], 2026, 7)
    assert july_period["stored_actuals"][edited[0]["kpi_key"]] == 60.0
    august_version = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.status == "approved", TeamConfigurationVersion.effective_from_month == 8).one()
    august_scored = score_basis(august_version, [{"kpi_key": edited[0]["kpi_key"], "actual": 60, "workbook_target": 65}])
    assert abs(august_scored["rows"][0]["achievement"] - (60 / 65)) < 1e-9

    with pytest.raises(TargetConflict) as conflict:
        score_basis(version, [{"kpi_key": edited[0]["kpi_key"], "actual": 60, "workbook_target": 50, "precomputed_achievement": 100}])
    assert conflict.value.data["conflicts"][0]["workbook_target"] == 50
    assert conflict.value.data["conflicts"][0]["approved_target"] == 55
    before_target = july_kpi.target_value
    with pytest.raises(TargetConflict):
        DatabaseSeeder()._pin_approved_evaluation(db, {(employee.id, "July", 2026): july}, [july_kpi])
    assert july_kpi.target_value == before_target
    assert float(july.score) == 70.0

    protected = workflow.protected_texts()
    applied = workflow.apply(actor, scope["id"], 2026, 8)
    db.refresh(july)
    db.refresh(august)
    db.refresh(other_record)
    assert float(july.score) == 70.0
    assert july.record_payload["manager_notes"] == "keep the july note"
    assert float(august.score) == round((60 / 65) * 100, 2)
    assert august.record_payload["evaluation_basis"]["pinned"] is True
    assert august.record_payload["manager_notes"] == "keep the august note"
    assert float(other_record.score) == 88.0
    assert workflow.protected_texts() == protected

    resolved = DashboardRecordService(db).resolve_records(
        db.query(PerformanceRecord).options(joinedload(PerformanceRecord.employee), joinedload(PerformanceRecord.team), joinedload(PerformanceRecord.kpi_values)).filter(PerformanceRecord.id == august.id).all()
    )
    assert resolved[0].evaluation.score == float(august.score)
    assert resolved[0].kpi_values[0]["target_value"] == 65
    assert resolved[0].kpi_values[0]["evaluation_pinned"] is True
    direction, source = resolve_kpi_direction("Coding", resolved[0].kpi_values[0], {"direction": "lower_better"})
    assert (direction, source) == ("higher_better", "pinned")

    workflow.rollback(actor, applied["revision_id"])
    db.refresh(august)
    assert float(august.score) == 71.0
    assert august.record_payload["manager_notes"] == "keep the august note"

    duplicate = TeamConfigurationVersion(
        id=uuid.uuid4(), team_id=coding.id, version_number=99, status="approved",
        effective_month="July", effective_year=2026, config_snapshot={"lines": edited}, config_checksum="b" * 64,
        effective_from_month=7, effective_from_year=2026, effective_until_month=7, effective_until_year=2026,
        performance_level="Employee", position_name="",
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_authorization_denies_non_admin_and_revoked_grants(db):
    admin = _user("Admin", "auth-admin")
    manager = _user("Manager", "auth-manager")
    coding = Team(id=uuid.uuid4(), name="Coding", db_name="Coding", display_name="Coding", region="UAE", team_level="employee")
    secret = Team(id=uuid.uuid4(), name="Pharmacy", db_name="Pharmacy", display_name="Pharmacy", region="UAE", team_level="employee")
    db.add_all([admin, manager, coding, secret])
    db.flush()
    grant = UserTeamAssignment(id=uuid.uuid4(), user_id=manager.id, team_id=coding.id, access_level="read", assigned_by="Admin")
    db.add(grant)
    db.commit()

    admin_actor = _actor(admin)
    workflow = EvaluationWorkflow(db)
    scope = _coding_scope(workflow, admin_actor)
    draft = workflow.open_draft(admin_actor, scope["id"], 2026, 7)
    manager_actor = _actor(manager, accessible_teams=["Coding"])
    with pytest.raises(Exception) as denied:
        workflow.approve(manager_actor, draft["id"])
    assert denied.value.status_code == 403
    with pytest.raises(Exception) as preview_denied:
        workflow.preview(manager_actor, draft["id"], [])
    assert preview_denied.value.status_code == 403
    with pytest.raises(Exception) as export_denied:
        workflow.export_version(manager_actor, draft["id"])
    assert export_denied.value.status_code == 403

    app = FastAPI()
    app.include_router(evaluation_router, prefix="/api/settings/evaluation")
    holder = {"user": {"user_id": str(manager.id), "role": "Admin"}}

    @app.middleware("http")
    async def attach_user(request, call_next):
        if holder["user"]:
            request.state.user = holder["user"]
        return await call_next(request)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    spoofed = client.post(f"/api/settings/evaluation/drafts/{draft['id']}/approve")
    assert spoofed.status_code == 403
    holder["user"] = None
    assert client.post(f"/api/settings/evaluation/drafts/{draft['id']}/approve").status_code == 401

    holder["user"] = {"user_id": str(manager.id), "role": "Manager"}
    db.delete(grant)
    db.commit()
    revoked = _actor(manager, accessible_teams=[])
    with pytest.raises(Exception) as revoked_read:
        workflow.reads(revoked, scope["id"], 2026, [7])
    assert revoked_read.value.status_code == 403
    assert "Coding" not in str(revoked_read.value)


def test_pinned_basis_does_not_cross_management_level(db):
    admin = _user("Admin", "bsc-admin")
    coding = Team(id=uuid.uuid4(), name="Coding", db_name="Coding", display_name="Coding", region="UAE", team_level="employee")
    db.add_all([admin, coding])
    db.commit()
    actor = _actor(admin)
    workflow = EvaluationWorkflow(db)
    scope = _coding_scope(workflow, actor)
    draft = workflow.open_draft(actor, scope["id"], 2026, 7)
    edited = _line_edit(draft["lines"], 55)
    workflow.edit_draft(actor, draft["id"], edited)
    workflow.approve(actor, draft["id"])
    config_row = ManagementKPIConfig(
        id=uuid.uuid4(), team_id=coding.id, performance_level="Managerial", position_name="Lead",
        perspective_key="Financial", kpi_key=edited[0]["kpi_key"], kpi_label="Quality",
        direction="lower_better", weight=Decimal("0.30"), effective_month="July", effective_year=2026,
    )
    db.add(config_row)
    db.commit()
    runtime = ManagementBSCService(db)._build_runtime_config([config_row], {}, "Coding", "Managerial", (2026, 7))
    assert runtime["kpis"][0]["weight"] == 0.3
    assert runtime["kpis"][0].get("target") is None
    overlaid = overlay_pinned_kpis(db, "Coding", "Employee", "", 2026, 7, [{"key": edited[0]["kpi_key"], "weight": 0.3, "direction": "lower_better"}])
    assert overlaid[0]["aggregation_weight"] == 0.3
    assert overlaid[0]["target"] == 55
    assert overlaid[0]["evaluation_pinned"] is True


def test_catalog_covers_live_scopes_without_guessing_history(db):
    """Every live team/level/position is classified. Missing history is listed, not invented."""
    from sqlalchemy import inspect, text

    from config.loader import get_configured_performance_levels, load_all_team_configs
    from services.evaluation.access import SchemaIncomplete
    from services.evaluation.catalog import HISTORY_NOTE, classify_readiness
    from services.evaluation.resolver import approved_version, assert_schema, schema_ready

    configs = load_all_team_configs()
    assert len(configs) >= 16
    csr_file = next(config for config in configs if config.get("team") == "CSR")
    coding_file = next(config for config in configs if config.get("team") == "Coding")
    marketing_file = next(config for config in configs if config.get("team") == "Marketing")
    admin = _user("Admin", "inventory-admin")
    live_teams = []
    for config in configs:
        if config is csr_file:
            continue
        label = str(config.get("db_name") or config.get("team"))
        live_teams.append(
            Team(
                id=uuid.uuid4(),
                name=label,
                db_name=label,
                display_name=str(config.get("team") or label),
                region="UAE",
                team_level="employee",
                is_active=True,
            )
        )
    created = Team(
        id=uuid.uuid4(), name="After Release Desk", db_name="After Release Desk",
        display_name="After Release Desk", region="UAE", team_level="employee", is_active=True,
    )
    retired = Team(
        id=uuid.uuid4(), name="Retired Desk", db_name="Retired Desk",
        display_name="Retired Desk", region="UAE", team_level="employee", is_active=False,
    )
    coding = next(team for team in live_teams if team.display_name == "Coding")
    employee = Employee(id=uuid.uuid4(), employee_id="INV-1", name="Historian", team=coding, region="UAE", performance_level="Employee")
    record = PerformanceRecord(
        id=uuid.uuid4(), year=2026, employee_id=employee.id, team_id=coding.id, month="July",
        performance_level="Employee", score=Decimal("70.00"), grade="D", status="Below",
        record_payload={"manager_notes": "historical note"},
    )
    kpi = KPIValue(
        id=uuid.uuid4(), record_id=record.id, record_year=2026, kpi_key="QualityErrors",
        actual_value=60, target_value=40, achievement_ratio=1, weight_applied=1, contribution=1,
    )
    legacy = TeamConfigurationVersion(
        id=uuid.uuid4(), team_id=coding.id, version_number=1, status="published",
        effective_month="July", effective_year=2026,
        config_snapshot={"lines": [{"kpi_key": "QualityErrors", "direction": "invented_formula", "weight": 1, "target": 10}]},
        config_checksum="c" * 64,
        effective_from_month=7, effective_from_year=2026,
        performance_level=None, position_name=None,
    )
    db.add_all([admin, *live_teams, created, retired, employee, record, kpi, legacy])
    db.commit()

    blocked, blocked_reason = classify_readiness(
        has_team=True, team_active=True, has_config=True, has_kpis=True,
        ambiguous=["MysteryKPI"], employee_importer=True,
    )
    assert blocked == "blocked"
    assert "MysteryKPI" in blocked_reason
    unlinked, _unlinked_reason = classify_readiness(
        has_team=False, team_active=False, has_config=True, has_kpis=True,
        ambiguous=[], employee_importer=True,
    )
    assert unlinked == "unlinked_baseline"

    actor = _actor(admin)
    workflow = EvaluationWorkflow(db)
    catalog = workflow.sync_catalog(actor)
    scopes = catalog["scopes"]
    gap_text = " ".join(catalog["schema_gaps"])
    assert "KPIValue does not store direction" in gap_text
    assert "not treated as monthly bindings" in gap_text
    assert "not backfilled" in gap_text

    identities = {(item["display_name"].casefold(), item["performance_level"], item["position_name"]) for item in scopes}
    for config in configs:
        if config is csr_file:
            continue
        display = str(config.get("team") or config.get("db_name")).casefold()
        for level in get_configured_performance_levels(config):
            assert any(row[0] == display and row[1] == level for row in identities), (display, level)
        for level in ("Employee", "Managerial", "Corporate"):
            assert any(row[0] == display and row[1] == level for row in identities), (display, level)

    marketing_positions = set(marketing_file["performance_levels"]["Employee"]["positions"])
    found_positions = {
        item["position_name"]
        for item in scopes
        if item["display_name"] == "Marketing" and item["performance_level"] == "Employee"
    }
    assert marketing_positions <= found_positions
    media_buyer = next(item for item in scopes if item["display_name"] == "Marketing" and item["position_name"] == "Media Buyer")
    assert media_buyer["readiness"] == "blocked"
    assert media_buyer["block_reason"]
    assert media_buyer["supported"] is False

    for level in ("Employee", "Managerial", "Corporate"):
        created_scope = next(item for item in scopes if item["display_name"] == "After Release Desk" and item["performance_level"] == level)
        assert created_scope["readiness"] == "blocked"
        assert "baseline" in created_scope["block_reason"].casefold()
    retired_scopes = [item for item in scopes if item["display_name"] == "Retired Desk"]
    assert {item["performance_level"] for item in retired_scopes} == {"Employee", "Managerial", "Corporate"}
    assert all(item["readiness"] == "blocked" and "inactive" in item["block_reason"].casefold() for item in retired_scopes)
    csr_scopes = [item for item in scopes if item["display_name"] == "CSR"]
    assert csr_scopes
    assert all(item["readiness"] == "unlinked_baseline" for item in csr_scopes)

    for item in scopes:
        assert item["history_note"] == HISTORY_NOTE
        assert "guessed" in item["history_note"]
        if item["readiness"] == "supported":
            assert item["performance_level"] == "Employee"
            assert item["importer_name"]
            assert item["ambiguous_kpis"] == []
        if item["readiness"] != "supported":
            assert item["block_reason"]

    coding_employee = next(
        item for item in scopes
        if item["display_name"] == "Coding" and item["performance_level"] == "Employee" and item["position_name"] == ""
    )
    assert coding_employee["readiness"] == "supported"
    managerial = next(item for item in scopes if item["display_name"] == "Coding" and item["performance_level"] == "Managerial")
    assert managerial["readiness"] == "blocked"
    draft = workflow.open_draft(actor, coding_employee["id"], 2026, 7)
    assert {line["kpi_key"]: line["direction"] for line in draft["lines"]} == {
        kpi_row["key"]: kpi_row["direction"] for kpi_row in coding_file["kpis"]
    }
    db.refresh(record)
    assert float(record.score) == 70.0
    assert record.record_payload == {"manager_notes": "historical note"}
    assert approved_version(db, team_id=coding.id, level="Employee", position="", year=2026, month=7) is None
    period = workflow.period(actor, coding_employee["id"], 2026, 7)
    assert str(legacy.id) not in {item["id"] for item in period["versions"]}
    assert all("invented_formula" not in str(item) for item in period["versions"])
    reads = workflow.reads(actor, coding_employee["id"], 2026, [7])
    assert reads["periods"][0]["pinned"] is False
    assert reads["periods"][0]["lines"] == []
    assert reads["periods"][0]["stored_score"] == 70.0

    db.delete(created)
    db.commit()
    removed = [item for item in workflow.sync_catalog(actor)["scopes"] if item["display_name"] == "After Release Desk"]
    assert len(removed) == 3
    assert all(item["readiness"] == "blocked" and "no longer" in item["block_reason"].casefold() for item in removed)

    db.execute(text("PRAGMA foreign_keys=OFF"))
    db.execute(text(
        "CREATE TABLE team_configuration_versions_legacy AS "
        "SELECT id, team_id, version_number, status, effective_month, effective_year, "
        "config_snapshot, config_checksum, created_by_user_id, published_by_user_id, "
        "created_at, published_at, superseded_at, notes, effective_from_month, effective_from_year, "
        "effective_until_month, effective_until_year, position_name "
        "FROM team_configuration_versions"
    ))
    db.execute(text("DROP TABLE team_configuration_versions"))
    db.execute(text("ALTER TABLE team_configuration_versions_legacy RENAME TO team_configuration_versions"))
    db.execute(text("DROP TABLE evaluation_scopes"))
    db.commit()
    inspect(db.bind).clear_cache()
    assert schema_ready(db) is False
    with pytest.raises(SchemaIncomplete):
        assert_schema(db)
    DatabaseSeeder()._pin_approved_evaluation(db, {(employee.id, "July", 2026): record}, [kpi])
    db.refresh(record)
    assert float(record.score) == 70.0
    assert record.record_payload == {"manager_notes": "historical note"}


def _coding_workbook(
    *,
    quality_actual: float,
    quality_target: float,
    rejection_actual: float,
    rejection_target: float,
    tat_actual: float,
    tat_target: float,
) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Coding"
    sheet.append([
        "HRID", "AgentName", "Role", "Date", "Status",
        "A.QualityErrorsRate", "T.QualityErrorsRate",
        "A.RejectionRate", "T.RejectionRate",
        "A.TAT", "T.TAT",
    ])
    sheet.append([
        "C-9", "Coder", "Employee", datetime(2026, 7, 15), "Active",
        quality_actual, quality_target,
        rejection_actual, rejection_target,
        tat_actual, tat_target,
    ])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_upload_dry_run_and_commit_share_the_approved_pin(db, monkeypatch):
    """Dry-run and commit both pin the approved basis, including a D-003 block."""
    monkeypatch.setattr(
        "services.seeding_service.SessionLocal",
        sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False),
    )
    admin = _user("Admin", "upload-admin")
    coding = Team(id=uuid.uuid4(), name="Coding", db_name="Coding", display_name="Coding", region="UAE", team_level="employee")
    db.add_all([admin, coding])
    db.commit()

    actor = _actor(admin)
    workflow = EvaluationWorkflow(db)
    scope = _coding_scope(workflow, actor)
    draft = workflow.open_draft(actor, scope["id"], 2026, 7)
    workflow.edit_draft(actor, draft["id"], [{**line, "target_mode": "fixed", "target": 55} for line in draft["lines"]])
    workflow.approve(actor, draft["id"])

    seeder = DatabaseSeeder()
    # The optional JSON trend file is not the pin. Keep this test off the workspace copy.
    seeder.performance_repo.get_all = lambda: []

    conflict = _coding_workbook(
        quality_actual=60, quality_target=50,
        rejection_actual=55, rejection_target=55,
        tat_actual=55, tat_target=55,
    )
    for dry_run in (True, False):
        with pytest.raises(TargetConflict) as caught:
            seeder.process_uploaded_file("coding-conflict.xlsx", conflict, dry_run=dry_run)
        quality = next(item for item in caught.value.data["conflicts"] if item["kpi_key"] == "QualityErrors")
        assert quality["workbook_target"] == 50
        assert quality["approved_target"] == 55
    db.rollback()
    assert db.query(PerformanceRecord).count() == 0
    db.rollback()

    matched = _coding_workbook(
        quality_actual=60, quality_target=55,
        rejection_actual=55, rejection_target=55,
        tat_actual=55, tat_target=55,
    )
    preview = seeder.process_uploaded_file("coding-match.xlsx", matched, dry_run=True)
    db.rollback()
    assert db.query(PerformanceRecord).count() == 0
    db.rollback()
    committed = seeder.process_uploaded_file("coding-match.xlsx", matched, dry_run=False)
    assert preview["scored_rows"] == committed["scored_rows"]
    quality_row = next(row for row in committed["scored_rows"][0]["rows"] if row["kpi_key"] == "QualityErrors")
    assert abs(quality_row["achievement"] - (55 / 60)) < 1e-9
    assert quality_row["target"] == 55
    db.rollback()
    stored = (
        db.query(PerformanceRecord)
        .join(Employee, PerformanceRecord.employee_id == Employee.id)
        .filter(Employee.employee_id == "C-9", PerformanceRecord.month == "July", PerformanceRecord.year == 2026)
        .one()
    )
    assert abs(float(stored.score) - float(committed["scored_rows"][0]["score"])) < 0.001
