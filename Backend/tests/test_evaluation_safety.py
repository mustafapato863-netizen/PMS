"""Permission and evidence gates for monthly evaluation settings.

Ordinary applied reads stay on the canonical team, level, and row scope.
Settings writes are Admin-only. Unsupported formulas stay blocked.
"""

import json
import math
import uuid
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from types import SimpleNamespace

from api.routers.evaluation_settings import router as evaluation_router
from config.database import get_db
from models.models import (
    Employee,
    EvaluationScope,
    KPIValue,
    PerformanceRecord,
    Team,
    TeamConfigurationVersion,
    User,
    UserBranchAssignment,
    UserFunctionAssignment,
    UserRegionAssignment,
    UserTeamAssignment,
)
from services.evaluation.access import AccessDenied, EvaluationError, TargetConflict
from services.evaluation.capabilities import weight_only_allowed
from services.evaluation.scoring import overall_score, score_rows
from services.evaluation.resolver import require_approved_capability, score_basis
from services.evaluation.workflow import EvaluationWorkflow


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda self, kind: None)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        Team.__table__,
        User.__table__,
        Employee.__table__,
        UserTeamAssignment.__table__,
        UserFunctionAssignment.__table__,
        UserRegionAssignment.__table__,
        UserBranchAssignment.__table__,
        PerformanceRecord.__table__,
        KPIValue.__table__,
        TeamConfigurationVersion.__table__,
        EvaluationScope.__table__,
    ]
    from models.models import Base

    Base.metadata.create_all(bind=engine, tables=tables)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield session
    session.close()


def _user(role: str, name: str, employee_id: str | None = None) -> User:
    return User(
        id=uuid.uuid4(),
        full_name=name,
        username=name,
        email=f"{name}@example.com",
        password_hash="test-hash",
        role=role,
        employee_id=employee_id,
    )


def _team(name: str, region: str = "UAE") -> Team:
    return Team(
        id=uuid.uuid4(),
        name=name,
        db_name=name,
        display_name=name,
        region=region,
        team_level="employee",
        is_active=True,
    )


def _record(employee: Employee, team: Team, level: str, score: str, *, branch: str | None = None, region: str | None = None) -> PerformanceRecord:
    return PerformanceRecord(
        id=uuid.uuid4(),
        year=2026,
        employee_id=employee.id,
        team_id=team.id,
        month="July",
        performance_level=level,
        position_name="",
        region=region,
        branch_key=branch,
        score=Decimal(score),
        grade="B",
        status="Meets",
        record_payload={"evaluation": {"score": float(score), "grade": "B"}},
    )


def _lines() -> list[dict]:
    return [
        {"kpi_key": "Attendance", "label": "Attendance", "weight": 0.70, "direction": "higher_better", "target_mode": "fixed", "target": 90},
        {"kpi_key": "Booking", "label": "Booking", "weight": 0.10, "direction": "higher_better", "target_mode": "fixed", "target": 80},
        {"kpi_key": "Quality", "label": "Quality", "weight": 0.10, "direction": "higher_better", "target_mode": "fixed", "target": 90},
        {"kpi_key": "Other", "label": "Reachability", "weight": 0.10, "direction": "higher_better", "target_mode": "fixed", "target": 70},
    ]


def _complete_rows() -> list[dict]:
    return [
        {"kpi_key": "Attendance", "actual": 90, "workbook_target": 90},
        {"kpi_key": "Booking", "actual": 80, "workbook_target": 80},
        {"kpi_key": "Quality", "actual": 90, "workbook_target": 90},
        {"kpi_key": "Other", "actual": 70, "workbook_target": 70},
    ]


def _basis(lines: list[dict], level: str = "Employee"):
    return SimpleNamespace(
        performance_level=level,
        config_snapshot={"lines": lines, "grade_thresholds": {"A": 95, "B": 85, "C": 75, "D": 65}, "policy": "employee_ratio"},
    )


def test_weight_only_stays_server_owned():
    assert weight_only_allowed([{"score_formula": "baseline_80", "achievement_col": "AcceptanceRateAchievement"}]) is False


def test_complete_ratio_evidence_scores_and_partial_booking_does_not():
    """Outbound's four weighted KPIs are the fixture. This does not enable Outbound settings."""
    scored = score_rows("Employee", _lines(), _complete_rows())
    assert [row["kpi_key"] for row in scored] == ["Attendance", "Booking", "Quality", "Other"]
    assert overall_score(scored) == 100.0

    with pytest.raises(EvaluationError) as partial:
        score_rows("Employee", _lines(), [{"kpi_key": "Booking", "actual": 80, "workbook_target": 80}])
    assert partial.value.data["code"] == "incomplete_evidence"
    assert set(partial.value.data["missing"]) == {"Attendance", "Quality", "Other"}


def test_numeric_zero_is_kept_and_missing_lower_better_actual_is_not_success():
    lines = [
        {"kpi_key": "QualityErrors", "label": "Quality", "weight": 1, "direction": "lower_better", "target_mode": "fixed", "target": 10},
        {"kpi_key": "Note", "label": "Note", "weight": 0, "direction": "lower_better", "target_mode": "fixed", "target": 10},
    ]
    scored = score_rows(
        "Employee",
        lines,
        [
            {"kpi_key": "QualityErrors", "actual": 0, "workbook_target": 10},
            {"kpi_key": "Note", "actual": None, "workbook_target": 10},
        ],
    )
    quality = next(row for row in scored if row["kpi_key"] == "QualityErrors")
    note = next(row for row in scored if row["kpi_key"] == "Note")
    assert quality["actual"] == 0.0
    assert quality["achievement"] == 1.0
    assert note["achievement"] is None
    assert note["achievement_state"] == "missing_actual"
    assert note["contribution"] is None
    assert overall_score(scored) == 100.0

    with pytest.raises(EvaluationError) as missing:
        score_rows(
            "Employee",
            lines,
            [
                {"kpi_key": "QualityErrors", "actual": None, "workbook_target": 10},
                {"kpi_key": "Note", "actual": 0, "workbook_target": 10},
            ],
        )
    assert missing.value.data["code"] == "missing_actual"


def test_duplicate_unknown_and_nonfinite_evidence_is_rejected():
    with pytest.raises(EvaluationError) as duplicate:
        score_rows("Employee", _lines(), _complete_rows() + [{"kpi_key": "Booking", "actual": 80, "workbook_target": 80}])
    assert duplicate.value.data["code"] == "duplicate_kpi"

    with pytest.raises(EvaluationError) as unknown:
        score_rows("Employee", _lines(), _complete_rows() + [{"kpi_key": "Productivity", "actual": 1, "workbook_target": 1}])
    assert unknown.value.data["code"] == "unknown_kpi"

    poisoned = _complete_rows()
    poisoned[0]["actual"] = float("nan")
    with pytest.raises(EvaluationError) as nonfinite:
        score_rows("Employee", _lines(), poisoned)
    assert nonfinite.value.data["code"] == "nonfinite_evidence"

    broken = _lines()
    broken[1]["weight"] = float("inf")
    with pytest.raises(EvaluationError) as bad_weight:
        score_rows("Employee", broken, _complete_rows())
    assert bad_weight.value.data["code"] == "nonfinite_evidence"


def test_huge_and_overflow_values_cannot_become_a_score():
    huge = Decimal("1e999")
    lines = [{"kpi_key": "Booking", "label": "Booking", "weight": 1, "direction": "higher_better", "target_mode": "fixed", "target": 80}]
    row = {"kpi_key": "Booking", "actual": 80, "workbook_target": 80}
    for poisoned in (
        {**row, "actual": huge},
        {**row, "actual": Decimal("1e-400")},
        {**row, "workbook_target": huge},
        {**row, "actual": Decimal("-1e999")},
    ):
        with pytest.raises(EvaluationError) as rejected:
            score_rows("Employee", lines, [poisoned])
        assert rejected.value.data["code"] == "nonfinite_evidence"

    heavy = [{**lines[0], "weight": huge}]
    with pytest.raises(EvaluationError) as bad_weight:
        score_rows("Employee", heavy, [row])
    assert bad_weight.value.data["code"] == "nonfinite_evidence"

    with pytest.raises(EvaluationError) as bad_threshold:
        score_basis(
            SimpleNamespace(
                performance_level="Employee",
                config_snapshot={"lines": lines, "grade_thresholds": {"A": huge, "B": 85, "C": 75, "D": 65}},
            ),
            [row],
        )
    assert bad_threshold.value.data["code"] == "nonfinite_evidence"

    overflow_lines = [{**lines[0], "target": Decimal("1e-300"), "target_mode": "fixed"}]
    with pytest.raises(EvaluationError) as overflow:
        score_rows("Managerial", overflow_lines, [{"kpi_key": "Booking", "actual": Decimal("1e308"), "workbook_target": Decimal("1e-300")}])
    assert overflow.value.data["code"] == "nonfinite_evidence"
    with pytest.raises(EvaluationError) as capped_overflow:
        score_rows("Employee", overflow_lines, [{"kpi_key": "Booking", "actual": Decimal("1e308"), "workbook_target": Decimal("1e-300")}])
    assert capped_overflow.value.data["code"] == "nonfinite_evidence"

    zero_lines = [{"kpi_key": "QualityErrors", "label": "Quality", "weight": 1, "direction": "lower_better", "target_mode": "fixed", "target": 10}]
    zero_scored = score_rows("Employee", zero_lines, [{"kpi_key": "QualityErrors", "actual": 0, "workbook_target": 10}])
    assert zero_scored[0]["actual"] == 0.0
    assert zero_scored[0]["achievement"] == 1.0
    json.dumps({"rows": zero_scored, "score": overall_score(zero_scored)}, allow_nan=False)

    ratio_lines = [{"kpi_key": "Booking", "label": "Booking", "weight": 1, "direction": "higher_better", "target_mode": "fixed", "target": 100}]
    ratio = score_rows("Corporate", ratio_lines, [{"kpi_key": "Booking", "actual": 250, "workbook_target": 100}])
    assert ratio[0]["achievement"] == 2.5
    assert math.isfinite(overall_score(ratio))
    json.dumps(ratio, allow_nan=False)


def test_target_conflict_still_blocks_direct_scoring_when_other_rows_are_missing():
    lines = _lines()
    conflict_only = [{"kpi_key": "Booking", "actual": 80, "workbook_target": 10, "precomputed_achievement": 1}]
    with pytest.raises(TargetConflict) as conflict:
        score_basis(_basis(lines), conflict_only)
    assert conflict.value.data["conflicts"][0]["kpi_key"] == "Booking"
    assert conflict.value.data["conflicts"][0]["approved_target"] == 80
    assert conflict.value.data["conflicts"][0]["workbook_target"] == 10


def test_catalog_enables_only_audited_ratio_scopes_and_blocks_ip_final(db):
    admin = _user("Admin", "safety-admin")
    teams = [
        _team("Coding"),
        _team("Submission"),
        _team("CSR"),
        _team("Outbound", "EGY"),
        _team("Pre-Approvals IP Final Dubai"),
        _team("Pre-Approvals IP Final SHJAJM"),
    ]
    db.add_all([admin, *teams])
    db.commit()
    workflow = EvaluationWorkflow(db)
    catalog = workflow.sync_catalog({"user_id": str(admin.id), "role": "Admin", "legacy_unscoped": False})
    scopes = catalog["scopes"]

    supported = [item for item in scopes if item["readiness"] == "supported"]
    assert {(item["display_name"], item["performance_level"], item["position_name"]) for item in supported} == {
        ("Coding", "Employee", ""),
        ("Submission", "Employee", ""),
    }
    assert all(item["edit_mode"] == "full" and item["weight_only_allowed"] is False for item in supported)
    assert "calculate_achievement" in supported[0]["capability_reason"]

    ip_scopes = [item for item in scopes if "IP Final" in item["display_name"] and item["performance_level"] == "Employee" and item["position_name"]]
    assert ip_scopes
    assert all(item["readiness"] == "blocked" and item["supported"] is False and item["weight_only_allowed"] is False for item in ip_scopes)
    assert all("baseline_80" in item["block_reason"] for item in ip_scopes)

    csr = next(item for item in scopes if item["display_name"] == "CSR" and item["performance_level"] == "Employee" and item["position_name"] == "")
    assert csr["readiness"] == "blocked"
    assert "not proof of the ratio formula" in csr["capability_reason"]
    outbound = next(item for item in scopes if item["display_name"] == "Outbound" and item["performance_level"] == "Employee" and item["position_name"] == "")
    assert outbound["readiness"] == "blocked"
    assert outbound["edit_mode"] == "blocked"

    ip = next(item for item in ip_scopes if item["display_name"] == "Pre-Approvals IP Final Dubai")
    before_versions = db.query(TeamConfigurationVersion).count()
    with pytest.raises(EvaluationError) as blocked:
        workflow.open_draft({"user_id": str(admin.id), "role": "Admin", "legacy_unscoped": False}, ip["id"], 2026, 7)
    assert blocked.value.data["weight_only_allowed"] is False
    assert "baseline_80" in blocked.value.message
    assert db.query(TeamConfigurationVersion).count() == before_versions

    stored = db.query(EvaluationScope).filter(EvaluationScope.id == uuid.UUID(ip["id"])).one()
    stored.readiness = "supported"
    stored.block_reason = None
    stored.policy_family = "employee_ratio"
    stored.importer_name = "preapprovals_ip_final_dubai"
    version = TeamConfigurationVersion(
        id=uuid.uuid4(),
        team_id=stored.team_id,
        version_number=1,
        status="draft",
        effective_month="July",
        effective_year=2026,
        config_snapshot={
            "lines": [{
                "kpi_key": "combined_acceptance_rate",
                "label": "Acceptance",
                "weight": 1,
                "direction": "higher_better",
                "target": 90,
                "target_mode": "workbook",
                "unit": "%",
            }],
            "grade_thresholds": {"A": 95, "B": 85, "C": 75, "D": 65},
            "policy": "employee_ratio",
        },
        config_checksum="d" * 64,
        effective_from_month=7,
        effective_from_year=2026,
        effective_until_month=7,
        effective_until_year=2026,
        performance_level=stored.performance_level,
        position_name=stored.position_name,
    )
    db.add(version)
    db.commit()
    crafted = [{
        "kpi_key": "combined_acceptance_rate",
        "weight": 1,
        "direction": "lower_better",
        "target_mode": "fixed",
        "target": 10,
        "weight_only": True,
        "score_formula": "target_ratio",
        "provenance": "stored",
        "edit_mode": "full",
    }]
    actor = {"user_id": str(admin.id), "role": "Admin", "legacy_unscoped": False}
    with pytest.raises(EvaluationError) as edited:
        workflow.edit_draft(actor, str(version.id), crafted, weight_only=True)
    assert edited.value.data["code"] == "unsupported_calculation"
    assert edited.value.data["weight_only_allowed"] is False
    with pytest.raises(EvaluationError):
        workflow.approve(actor, str(version.id))
    db.refresh(version)
    assert version.status == "draft"
    assert version.config_snapshot["lines"][0]["target"] == 90
    assert version.config_snapshot["lines"][0]["direction"] == "higher_better"


def test_authenticated_reads_use_team_level_and_row_scope(db):
    coding = _team("Coding")
    admin = _user("Admin", "read-admin")
    manager = _user("Manager", "read-manager")
    broad_manager = _user("Manager", "read-broad-manager")
    employee_user = _user("Employee", "read-employee", "C-SELF")
    performance = _user("Performance Team", "read-performance")
    general = _user("General Manager", "read-gm")
    rcm = _user("Function Director", "read-rcm")
    calls = _user("Function Director", "read-calls")
    regional = _user("Regional Manager", "read-regional")
    director = _user("Branch Director", "read-branch")
    self_employee = Employee(id=uuid.uuid4(), employee_id="C-SELF", name="Self", team=coding, region="UAE", performance_level="Employee")
    colleague = Employee(id=uuid.uuid4(), employee_id="C-OTHER", name="Other", team=coding, region="UAE", performance_level="Employee")
    dubai_employee = Employee(id=uuid.uuid4(), employee_id="C-DXB", name="Dubai", team=coding, region="UAE", performance_level="Employee")
    sharjah_employee = Employee(id=uuid.uuid4(), employee_id="C-SHJ", name="Sharjah", team=coding, region="UAE", performance_level="Employee")
    egypt_employee = Employee(id=uuid.uuid4(), employee_id="C-EGY", name="Egypt", team=coding, region="EGY", performance_level="Employee")
    corporate_employee = Employee(id=uuid.uuid4(), employee_id="C-CORP", name="Corporate", team=coding, region="UAE", performance_level="Corporate")
    records = [
        _record(self_employee, coding, "Employee", "70.00", region="UAE"),
        _record(colleague, coding, "Employee", "88.00", region="UAE"),
        _record(dubai_employee, coding, "Employee", "61.00", branch="dubai", region="UAE"),
        _record(sharjah_employee, coding, "Employee", "88.00", branch="sharjah", region="UAE"),
        _record(egypt_employee, coding, "Employee", "91.00", region="EGY"),
        _record(corporate_employee, coding, "Corporate", "88.00", region="UAE"),
    ]
    db.add_all([
        coding, admin, manager, broad_manager, employee_user, performance, general, rcm, calls, regional, director,
        self_employee, colleague, dubai_employee, sharjah_employee, egypt_employee, corporate_employee, *records,
    ])
    db.flush()
    db.add_all([
        UserTeamAssignment(id=uuid.uuid4(), user_id=manager.id, team_id=coding.id, performance_level="Employee", access_level="read", assigned_by="Admin"),
        UserTeamAssignment(id=uuid.uuid4(), user_id=broad_manager.id, team_id=coding.id, performance_level=None, access_level="read", assigned_by="Admin"),
        UserFunctionAssignment(id=uuid.uuid4(), user_id=rcm.id, function_name="RCM", assigned_by="Admin"),
        UserFunctionAssignment(id=uuid.uuid4(), user_id=calls.id, function_name="Call Center", assigned_by="Admin"),
        UserRegionAssignment(id=uuid.uuid4(), user_id=regional.id, region_code="UAE", assigned_by="Admin"),
        UserBranchAssignment(id=uuid.uuid4(), user_id=director.id, branch_key="dubai", assigned_by="Admin"),
    ])
    db.commit()

    app = FastAPI()
    app.include_router(evaluation_router, prefix="/api/settings/evaluation")
    holder = {"user": {"user_id": str(admin.id), "role": "Admin"}}

    @app.middleware("http")
    async def attach_user(request, call_next):
        if holder["user"]:
            request.state.user = holder["user"]
        return await call_next(request)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    before = db.query(EvaluationScope).count()
    for user in (performance, general, manager):
        holder["user"] = {"user_id": str(user.id), "role": "Admin"}
        denied = client.get("/api/settings/evaluation/catalog")
        assert denied.status_code == 403
        assert denied.json()["detail"]["message"] == "Evaluation settings are limited to Admin."
    assert db.query(EvaluationScope).count() == before

    holder["user"] = {"user_id": str(admin.id), "role": "Manager"}
    synced = client.get("/api/settings/evaluation/catalog")
    assert synced.status_code == 200
    scopes = synced.json()["data"]["scopes"]
    employee_scope = next(item for item in scopes if item["display_name"] == "Coding" and item["performance_level"] == "Employee" and item["position_name"] == "")
    corporate_scope = next(item for item in scopes if item["display_name"] == "Coding" and item["performance_level"] == "Corporate" and item["position_name"] == "")
    after_sync = db.query(EvaluationScope).count()
    readiness = [(row.team_key, row.performance_level, row.position_name, row.readiness) for row in db.query(EvaluationScope).all()]

    def management_denied(user_id: str) -> None:
        holder["user"] = {"user_id": user_id, "role": "Admin"}
        fake = str(uuid.uuid4())
        calls_made = [
            client.get("/api/settings/evaluation/catalog"),
            client.post("/api/settings/evaluation/drafts", json={"scope_id": employee_scope["id"], "year": 2026, "month": 7}),
            client.patch(f"/api/settings/evaluation/drafts/{fake}", json={"lines": [], "weight_only": True}),
            client.post(f"/api/settings/evaluation/drafts/{fake}/preview", json={"rows": []}),
            client.post(f"/api/settings/evaluation/jobs/{fake}/preview", json={"rows": []}),
            client.get(f"/api/settings/evaluation/versions/{fake}"),
            client.get(f"/api/settings/evaluation/versions/{fake}/export"),
            client.get("/api/settings/evaluation/periods", params={"scope_id": corporate_scope["id"], "year": 2026, "month": 7}),
            client.post("/api/settings/evaluation/apply", json={"scope_id": employee_scope["id"], "year": 2026, "month": 7}),
            client.post(f"/api/settings/evaluation/revisions/{fake}/rollback"),
        ]
        assert [item.status_code for item in calls_made] == [403] * len(calls_made)

    management_denied(str(performance.id))
    management_denied(str(general.id))
    assert db.query(EvaluationScope).count() == after_sync
    assert [(row.team_key, row.performance_level, row.position_name, row.readiness) for row in db.query(EvaluationScope).all()] == readiness

    def reads(user_id: str, scope_id: str):
        holder["user"] = {"user_id": user_id, "role": "Employee"}
        return client.get("/api/settings/evaluation/reads", params={"scope_id": scope_id, "year": 2026, "months": "7"})

    manager_employee = reads(str(manager.id), employee_scope["id"])
    assert manager_employee.status_code == 200
    manager_corporate = reads(str(manager.id), corporate_scope["id"])
    assert manager_corporate.status_code == 403
    assert "88" not in manager_corporate.text

    broad = reads(str(broad_manager.id), corporate_scope["id"])
    assert broad.status_code == 200
    assert broad.json()["data"]["periods"][0]["stored_score"] == 88.0

    own = reads(str(employee_user.id), employee_scope["id"])
    assert own.status_code == 200
    assert own.json()["data"]["periods"][0]["stored_score"] == 70.0
    assert "88.0" not in own.text
    corporate_for_employee = reads(str(employee_user.id), corporate_scope["id"])
    assert corporate_for_employee.status_code == 200
    assert corporate_for_employee.json()["data"]["periods"][0]["stored_score"] is None

    assert reads(str(calls.id), employee_scope["id"]).status_code == 403
    rcm_corporate = reads(str(rcm.id), corporate_scope["id"])
    assert rcm_corporate.status_code == 200
    assert rcm_corporate.json()["data"]["periods"][0]["stored_score"] == 88.0

    branch = reads(str(director.id), employee_scope["id"])
    assert branch.status_code == 200
    assert branch.json()["data"]["periods"][0]["stored_score"] == 61.0

    region = reads(str(regional.id), employee_scope["id"])
    assert region.status_code == 200
    assert region.json()["data"]["periods"][0]["stored_score"] != 91.0

    workflow = EvaluationWorkflow(db)
    from api.dependencies import get_current_user_scope

    class _Request:
        state = SimpleNamespace(user={"user_id": str(regional.id)})

    regional_scope = get_current_user_scope(db, _Request())
    visible_regions = {row.region for row in workflow._records(
        db.query(EvaluationScope).filter(EvaluationScope.id == uuid.UUID(employee_scope["id"])).one(),
        2026,
        7,
        regional_scope,
    )}
    assert visible_regions == {"UAE"}

    tampered = reads(str(manager.id), str(uuid.uuid4()))
    assert tampered.status_code == 422
    assert db.query(EvaluationScope).count() == after_sync

    grant = db.query(UserTeamAssignment).filter(UserTeamAssignment.user_id == manager.id).one()
    db.delete(grant)
    db.commit()
    revoked = reads(str(manager.id), employee_scope["id"])
    assert revoked.status_code == 403
    with pytest.raises(AccessDenied):
        workflow.reads(
            {"user_id": str(manager.id), "role": "Manager", "accessible_teams": [], "accessible_team_levels": [], "legacy_unscoped": False},
            employee_scope["id"],
            2026,
            [7],
        )


def test_ip_final_upload_pin_does_not_invent_a_ratio_score(db):
    admin = _user("Admin", "pin-admin")
    team = _team("Pre-Approvals IP Final SHJAJM")
    employee = Employee(id=uuid.uuid4(), employee_id="IP-1", name="Final", team=team, region="UAE", performance_level="Employee")
    record = _record(employee, team, "Employee", "77.00", region="UAE")
    record.position_name = "IP Final"
    db.add_all([admin, team, employee, record])
    db.commit()
    workflow = EvaluationWorkflow(db)
    catalog = workflow.sync_catalog({"user_id": str(admin.id), "role": "Admin", "legacy_unscoped": False})
    scope = next(item for item in catalog["scopes"] if item["display_name"] == team.display_name and item["position_name"] == "IP Final")
    version = TeamConfigurationVersion(
        id=uuid.uuid4(),
        team_id=team.id,
        version_number=1,
        status="approved",
        effective_month="July",
        effective_year=2026,
        config_snapshot={"lines": [{"kpi_key": "ip_final_acceptance_rate", "weight": 1, "direction": "higher_better", "target": 10, "target_mode": "fixed"}], "policy": "employee_ratio"},
        config_checksum="e" * 64,
        effective_from_month=7,
        effective_from_year=2026,
        effective_until_month=7,
        effective_until_year=2026,
        performance_level="Employee",
        position_name="IP Final",
        published_at=None,
    )
    value = KPIValue(
        id=uuid.uuid4(),
        record_id=record.id,
        record_year=2026,
        kpi_key="ip_final_acceptance_rate",
        actual_value=Decimal("50"),
        target_value=Decimal("90"),
        achievement_ratio=Decimal("0.4200"),
        weight_applied=Decimal("0.4000"),
        contribution=Decimal("0.1680"),
    )
    db.add_all([version, value])
    db.commit()
    before_payload = dict(record.record_payload)
    before_score = record.score
    with pytest.raises(EvaluationError) as refused:
        require_approved_capability(
            version,
            team_name=team.display_name,
            config=workflow.catalog._config_for(team.display_name),
        )
    assert refused.value.data["code"] == "unsupported_calculation"
    assert refused.value.data["edit_mode"] == "blocked"
    assert refused.value.data["weight_only_allowed"] is False
    with pytest.raises(EvaluationError) as pinned:
        workflow.rescore_uploaded(record, team, [value], 0)
    assert pinned.value.data["code"] == "unsupported_calculation"
    db.refresh(value)
    db.refresh(record)
    assert float(value.achievement_ratio) == 0.42
    assert float(value.target_value) == 90
    assert float(value.weight_applied) == 0.4
    assert float(value.contribution) == 0.168
    assert record.score == before_score
    assert record.record_payload == before_payload
    assert "evaluation_basis" not in record.record_payload
    assert scope["readiness"] == "blocked"


def _approved_version(team: Team, label: str) -> TeamConfigurationVersion:
    return TeamConfigurationVersion(
        id=uuid.uuid4(),
        team_id=team.id,
        version_number=1,
        status="approved",
        effective_month="July",
        effective_year=2026,
        config_snapshot={
            "lines": [{
                "kpi_key": "QualityErrors",
                "label": label,
                "weight": 1,
                "direction": "lower_better",
                "target": 55,
                "target_mode": "fixed",
            }],
            "policy": "employee_ratio",
        },
        config_checksum="f" * 64,
        effective_from_month=7,
        effective_from_year=2026,
        effective_until_month=7,
        effective_until_year=2026,
        performance_level="Employee",
        position_name="",
    )


def test_applied_reads_hide_unapplied_and_unauthorized_configuration(db):
    coding = _team("Coding")
    other = _team("Future Desk")
    admin = _user("Admin", "basis-admin")
    employee_user = _user("Employee", "basis-employee", "C-SELF")
    regional = _user("Regional Manager", "basis-regional")
    director = _user("Branch Director", "basis-branch")
    self_employee = Employee(id=uuid.uuid4(), employee_id="C-SELF", name="Self", team=coding, region="UAE", performance_level="Employee")
    colleague = Employee(id=uuid.uuid4(), employee_id="C-OTHER", name="Other", team=coding, region="UAE", performance_level="Employee")
    dubai_employee = Employee(id=uuid.uuid4(), employee_id="C-DXB", name="Dubai", team=coding, region="UAE", performance_level="Employee")
    other_employee = Employee(id=uuid.uuid4(), employee_id="F-1", name="Foreign", team=other, region="UAE", performance_level="Employee")
    own = _record(self_employee, coding, "Employee", "70.00", region="UAE")
    colleague_row = _record(colleague, coding, "Employee", "88.00", region="UAE")
    colleague_row.record_payload = {"evaluation_basis": {"pinned": True, "version_id": "colleague-basis", "lines": [{"label": "COLLEAGUE-SECRET", "target": 88}]}}
    dubai = _record(dubai_employee, coding, "Employee", "61.00", branch="dubai", region="UAE")
    foreign = _record(other_employee, other, "Employee", "99.00", region="UAE")
    foreign.record_payload = {"evaluation_basis": {"pinned": True, "version_id": "foreign-basis", "lines": [{"label": "OTHER-TEAM-SECRET", "target": 99}]}}
    db.add_all([
        coding, other, admin, employee_user, regional, director,
        self_employee, colleague, dubai_employee, other_employee, own, colleague_row, dubai, foreign,
        UserRegionAssignment(id=uuid.uuid4(), user_id=regional.id, region_code="EGY", assigned_by="Admin"),
        UserBranchAssignment(id=uuid.uuid4(), user_id=director.id, branch_key="ajman", assigned_by="Admin"),
    ])
    db.commit()

    app = FastAPI()
    app.include_router(evaluation_router, prefix="/api/settings/evaluation")
    holder = {"user": {"user_id": str(admin.id), "role": "Employee"}}

    @app.middleware("http")
    async def attach_user(request, call_next):
        request.state.user = holder["user"]
        return await call_next(request)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    synced = client.get("/api/settings/evaluation/catalog")
    assert synced.status_code == 200
    scopes = synced.json()["data"]["scopes"]
    coding_scope = next(item for item in scopes if item["display_name"] == "Coding" and item["performance_level"] == "Employee" and item["position_name"] == "")
    other_scope = next(item for item in scopes if item["display_name"] == "Future Desk" and item["performance_level"] == "Employee" and item["position_name"] == "")
    coding_version = _approved_version(coding, "UNAPPLIED-SECRET")
    other_version = _approved_version(other, "OTHER-TEAM-SECRET")
    db.add_all([coding_version, other_version])
    db.commit()

    def reads(user_id: str, scope_id: str):
        holder["user"] = {"user_id": user_id, "role": "Employee"}
        return client.get("/api/settings/evaluation/reads", params={"scope_id": scope_id, "year": 2026, "months": "7"})

    legacy = reads(str(employee_user.id), coding_scope["id"])
    assert legacy.status_code == 200
    legacy_body = legacy.json()["data"]["periods"][0]
    assert legacy_body["stored_score"] == 70.0
    assert legacy_body["pinned"] is False
    assert legacy_body["lines"] == []
    assert legacy_body["version_id"] is None
    assert "UNAPPLIED-SECRET" not in legacy.text
    assert "COLLEAGUE-SECRET" not in legacy.text
    assert str(coding_version.id) not in legacy.text

    other_read = reads(str(employee_user.id), other_scope["id"])
    assert other_read.status_code == 200
    other_body = other_read.json()["data"]["periods"][0]
    assert other_body["stored_score"] is None
    assert other_body["lines"] == []
    assert other_body["version_id"] is None
    assert other_body["pinned"] is False
    assert "OTHER-TEAM-SECRET" not in other_read.text
    assert "99.0" not in other_read.text
    assert str(other_version.id) not in other_read.text

    branch = reads(str(director.id), coding_scope["id"])
    assert branch.status_code == 200
    assert branch.json()["data"]["periods"][0]["stored_score"] is None
    assert branch.json()["data"]["periods"][0]["lines"] == []
    assert "UNAPPLIED-SECRET" not in branch.text
    assert "61.0" not in branch.text

    region = reads(str(regional.id), coding_scope["id"])
    assert region.status_code == 200
    assert region.json()["data"]["periods"][0]["stored_score"] is None
    assert region.json()["data"]["periods"][0]["lines"] == []
    assert "UNAPPLIED-SECRET" not in region.text
    assert str(coding_version.id) not in region.text

    own.record_payload = {
        "evaluation": {"score": 70, "grade": "B"},
        "evaluation_basis": {
            "pinned": True,
            "version_id": "applied-own-basis",
            "lines": [{"kpi_key": "QualityErrors", "label": "OWN-BASIS", "target": 40, "weight": 1}],
        },
    }
    db.commit()
    applied = reads(str(employee_user.id), coding_scope["id"])
    assert applied.status_code == 200
    applied_body = applied.json()["data"]["periods"][0]
    assert applied_body["stored_score"] == 70.0
    assert applied_body["pinned"] is True
    assert applied_body["version_id"] == "applied-own-basis"
    assert applied_body["lines"][0]["label"] == "OWN-BASIS"
    assert "UNAPPLIED-SECRET" not in applied.text
    assert "COLLEAGUE-SECRET" not in applied.text
    assert str(coding_version.id) not in applied.text

    holder["user"] = {"user_id": str(admin.id), "role": "Employee"}
    period = client.get("/api/settings/evaluation/periods", params={"scope_id": coding_scope["id"], "year": 2026, "month": 7})
    assert period.status_code == 200
    assert "UNAPPLIED-SECRET" in period.text
