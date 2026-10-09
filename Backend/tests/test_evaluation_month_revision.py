"""Versioned correction of one approved month.

SQLite cannot prove the PostgreSQL team-row lock, and the current revision
check constraint has no superseded status. A replaced revision stays active
and is not marked rolled back. Rollback still refuses that older revision
while a newer one points at it.
"""

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.pool import StaticPool

from api.routers.evaluation_settings import router as evaluation_router
from config.database import get_db
from models.models import (
    Action,
    Base,
    Employee,
    EvaluationRevision,
    EvaluationScope,
    GeneratedReport,
    KPIValue,
    PerformancePlan,
    PerformanceRecord,
    Team,
    TeamConfigurationVersion,
    UploadLog,
    User,
    UserTeamAssignment,
)
from services.evaluation.access import AccessDenied
from services.evaluation.workflow import EvaluationConflict, EvaluationWorkflow


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda self, kind: None)
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


def _actor(user: User) -> dict:
    return {
        "user_id": str(user.id),
        "role": user.role,
        "employee_id": user.employee_id or "",
        "accessible_teams": [],
        "accessible_functions": [],
        "accessible_regions": [],
        "accessible_branches": [],
        "has_unrestricted_team_access": user.role == "Admin",
        "legacy_unscoped": False,
    }


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


def _coding_scope(workflow: EvaluationWorkflow, actor: dict) -> dict:
    catalog = workflow.sync_catalog(actor)
    return next(
        item for item in catalog["scopes"]
        if item["display_name"].casefold() == "coding"
        and item["performance_level"] == "Employee"
        and item["position_name"] == ""
    )


def _freeze(value):
    return json.dumps(value, sort_keys=True, default=str)


def _approve(workflow: EvaluationWorkflow, actor: dict, version_id: str) -> dict:
    workflow.impact_preview(actor, version_id)
    return workflow.approve(actor, version_id)


class _World:
    def __init__(self, db):
        self.db = db
        self.admin = _user("Admin", "revision-admin")
        self.manager = _user("Manager", "revision-manager")
        self.performance = _user("Performance Team", "revision-performance")
        self.coding = Team(id=uuid.uuid4(), name="Coding", db_name="Coding", display_name="Coding", region="UAE", team_level="employee")
        self.other = Team(id=uuid.uuid4(), name="Pharmacy", db_name="Pharmacy", display_name="Pharmacy", region="UAE", team_level="employee")
        self.employee_a = Employee(id=uuid.uuid4(), employee_id="C-1", name="Ada", team=self.coding, region="UAE", performance_level="Employee")
        self.employee_b = Employee(id=uuid.uuid4(), employee_id="C-2", name="Ben", team=self.coding, region="UAE", performance_level="Employee")
        self.uploaded_at = datetime(2026, 7, 2, 9, 0, tzinfo=timezone.utc)
        self.upload = UploadLog(
            id=uuid.uuid4(), team_id=self.coding.id, month="July", year=2026,
            record_count=2, status="completed", uploaded_at=self.uploaded_at,
        )
        db.add_all([
            self.admin, self.manager, self.performance, self.coding, self.other,
            self.employee_a, self.employee_b, self.upload,
        ])
        db.commit()
        self.actor = _actor(self.admin)
        self.workflow = EvaluationWorkflow(db)
        self.scope = _coding_scope(self.workflow, self.actor)

    def record(self, employee, month, score, grade, team=None, level="Employee", payload=None, upload=True):
        team = team or self.coding
        row = PerformanceRecord(
            id=uuid.uuid4(),
            year=2026,
            employee_id=employee.id,
            team_id=team.id,
            month=month,
            performance_level=level,
            position_name="",
            region="UAE",
            branch_key="dubai",
            score=Decimal(score),
            grade=grade,
            status="Below",
            upload_id=self.upload.id if upload else None,
            uploaded_at=self.uploaded_at,
            record_payload=payload or {
                "manager_notes": f"keep {month}",
                "evaluation": {"score": float(score), "grade": grade},
            },
        )
        self.db.add(row)
        self.db.flush()
        return row

    def kpi(self, record, key, actual, target):
        row = KPIValue(
            id=uuid.uuid4(),
            record_id=record.id,
            record_year=record.year,
            kpi_key=key,
            actual_value=Decimal(str(actual)),
            target_value=Decimal(str(target)),
            achievement_ratio=Decimal("1"),
            weight_applied=Decimal("1"),
            contribution=Decimal("1"),
        )
        self.db.add(row)
        self.db.flush()
        return row


def _draft_target(world: _World, month: int, target: float) -> dict:
    draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, month)
    return world.workflow.edit_draft(world.actor, draft["id"], _line_edit(draft["lines"], target))


def _client(db):
    app = FastAPI()
    app.include_router(evaluation_router, prefix="/api/settings/evaluation")
    holder = {"user": None}

    @app.middleware("http")
    async def attach_user(request, call_next):
        if holder["user"]:
            request.state.user = holder["user"]
        return await call_next(request)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), holder


def test_revise_copies_selected_month_and_leaves_original_checksum(db):
    world = _World(db)
    draft = _draft_target(world, 7, 55)
    version = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    snapshot = dict(version.config_snapshot)
    snapshot["grade_thresholds"] = {"A": 91, "B": 81, "C": 71, "D": 61}
    version.config_snapshot = snapshot
    flag_modified(version, "config_snapshot")
    db.commit()
    approved = _approve(world.workflow, world.actor, draft["id"])
    source = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(approved["id"])).one()
    before_checksum = source.config_checksum
    before_snapshot = _freeze(source.config_snapshot)
    before_published_by = source.published_by_user_id

    with pytest.raises(EvaluationConflict) as blocked:
        world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)
    assert blocked.value.status_code == 409
    assert blocked.value.data["code"] == "already_approved"

    revised = world.workflow.revise(world.actor, approved["id"])
    db.refresh(source)
    assert revised["resumed"] is False
    assert revised["status"] == "draft"
    assert revised["month"] == 7
    assert revised["source_version_id"] == approved["id"]
    assert revised["source_checksum"] == before_checksum
    assert revised["lines"][0]["target"] == 55
    assert revised["lines"][0]["direction"] == "higher_better"
    assert revised["lines"][0]["weight"] == 1
    assert revised["grade_thresholds"]["A"] == 91
    assert source.status == "approved"
    assert source.config_checksum == before_checksum
    assert source.published_by_user_id == before_published_by
    assert _freeze(source.config_snapshot) == before_snapshot

    again = world.workflow.revise(world.actor, approved["id"])
    assert again["id"] == revised["id"]
    assert again["resumed"] is True
    assert db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.status == "draft").count() == 1

    world.workflow.edit_draft(world.actor, revised["id"], _line_edit(revised["lines"], 48))
    db.refresh(source)
    assert source.config_checksum == before_checksum
    assert _freeze(source.config_snapshot) == before_snapshot
    _approve(world.workflow, world.actor, revised["id"])
    db.refresh(source)
    assert source.status == "superseded"
    assert source.config_checksum == before_checksum
    assert _freeze(source.config_snapshot) == before_snapshot


def test_existing_draft_is_not_overwritten_and_file_entry_stays_separate(db):
    world = _World(db)
    approved = _approve(world.workflow, world.actor, _draft_target(world, 7, 55)["id"])
    stray = TeamConfigurationVersion(
        id=uuid.uuid4(), team_id=world.coding.id, version_number=50, status="draft",
        effective_month="July", effective_year=2026,
        config_snapshot={"lines": [{
            "kpi_key": "QualityErrors", "label": "Quality Errors", "weight": 1,
            "direction": "higher_better", "target": 1, "target_mode": "fixed", "unit": "%",
        }]},
        config_checksum="d" * 64,
        effective_from_month=7, effective_from_year=2026, effective_until_month=7, effective_until_year=2026,
        performance_level="Employee", position_name="", notes="keep me",
    )
    db.add(stray)
    db.commit()
    with pytest.raises(EvaluationConflict) as conflict:
        world.workflow.revise(world.actor, approved["id"])
    assert conflict.value.status_code == 409
    assert conflict.value.data["code"] == "draft_exists"
    db.refresh(stray)
    assert stray.notes == "keep me"
    assert stray.config_checksum == "d" * 64

    db.delete(stray)
    db.commit()
    revised = world.workflow.revise(world.actor, approved["id"])
    world.workflow.edit_draft(world.actor, revised["id"], _line_edit(revised["lines"], 44))
    resumed = world.workflow.revise(world.actor, approved["id"])
    assert resumed["id"] == revised["id"]
    assert resumed["lines"][0]["target"] == 44

    august = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 8, copy_previous=True)
    assert august["id"] != revised["id"]
    assert august["month"] == 8
    assert august["source_version_id"] is None
    assert august["lines"][0]["target"] == 55
    with pytest.raises(EvaluationConflict) as mixed:
        world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)
    assert mixed.value.data["code"] == "draft_exists"


def test_permissions_reject_spoofed_admin_before_revision(db):
    world = _World(db)
    approved = _approve(world.workflow, world.actor, _draft_target(world, 7, 55)["id"])
    for user in (world.manager, world.performance):
        actor = _actor(user)
        calls = (
            lambda: world.workflow.revise(actor, approved["id"]),
            lambda: world.workflow.impact_preview(actor, approved["id"]),
            lambda: world.workflow.approve(actor, approved["id"]),
            lambda: world.workflow.apply(actor, world.scope["id"], 2026, 7),
            lambda: world.workflow.rollback(actor, str(uuid.uuid4())),
        )
        for call in calls:
            with pytest.raises(AccessDenied) as denied:
                call()
            assert denied.value.status_code == 403

    client, holder = _client(db)
    holder["user"] = {"user_id": str(world.manager.id), "role": "Admin"}
    spoofed = client.post(f"/api/settings/evaluation/versions/{approved['id']}/revise")
    assert spoofed.status_code == 403
    assert client.post(f"/api/settings/evaluation/drafts/{approved['id']}/impact-preview").status_code == 403
    holder["user"] = None
    assert client.post(f"/api/settings/evaluation/versions/{approved['id']}/revise").status_code == 401

    holder["user"] = {"user_id": str(world.admin.id), "role": "Manager"}
    allowed = client.post(f"/api/settings/evaluation/versions/{approved['id']}/revise")
    assert allowed.status_code == 200
    body = allowed.json()["data"]
    assert body["source_version_id"] == approved["id"]
    assert body["source_checksum"]
    resume = client.post(f"/api/settings/evaluation/versions/{approved['id']}/revise")
    assert resume.status_code == 200
    assert resume.json()["data"]["id"] == body["id"]
    assert resume.json()["data"]["resumed"] is True


def test_impact_preview_uses_every_stored_record_and_keeps_source_targets(db):
    world = _World(db)
    draft = _draft_target(world, 7, 50)
    key = draft["lines"][0]["kpi_key"]
    first = world.record(world.employee_a, "July", "70.00", "D")
    second = world.record(world.employee_b, "July", "72.00", "D")
    august = world.record(world.employee_a, "August", "71.00", "D")
    managerial = world.record(world.employee_a, "July", "80.00", "C", level="Managerial")
    other = world.record(world.employee_a, "July", "88.00", "B", team=world.other)
    world.kpi(first, key, 60, 40)
    world.kpi(second, key, 30, 40)
    world.kpi(august, key, 60, 40)
    world.kpi(managerial, key, 60, 40)
    world.kpi(other, key, 60, 40)
    plan = PerformancePlan(
        id=uuid.uuid4(), name="July coaching plan", scope_type="Team", team_id=world.coding.id,
        performance_level="Employee", period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
        due_date=date(2026, 7, 31), owner_user_id=world.admin.id, baseline_value=1, target_value=10,
        outcome_unit="%", outcome_direction="higher_better", status="Draft",
    )
    action = Action(id=uuid.uuid4(), team_id=world.coding.id, month="July", year=2026, action_type="Coaching", action_text="Coach the queue", status="Open")
    report = GeneratedReport(
        id=uuid.uuid4(), name="July pack", report_type="team", scope_summary="Coding", period_label="July 2026",
        created_by_name="revision-admin", output_format="pdf", status="ready", file_name="july.pdf",
        content_type="application/pdf", file_data=b"saved-report", configuration={}, scope_json={},
        final_definition_json={}, narrative_snapshot_json={"text": "original narrative"},
        data_snapshot_json={"score": 70}, validation_json={},
    )
    db.add_all([plan, action, report])
    db.commit()
    protected = world.workflow.protected_texts()

    sample = world.workflow.preview(world.actor, draft["id"], [{
        "kpi_key": key, "actual": 1, "workbook_target": 50,
    }])
    assert sample["satisfies_approval_gate"] is False
    with pytest.raises(EvaluationConflict) as gate:
        world.workflow.approve(world.actor, draft["id"])
    assert gate.value.status_code == 409
    assert gate.value.data["code"] == "preview_required"

    preview = world.workflow.impact_preview(world.actor, draft["id"])
    db.refresh(first)
    db.refresh(second)
    assert preview["writes"] == 0
    assert preview["affected_count"] == 2
    assert preview["scored_employees"] == 2
    assert preview["zero_affected"] is False
    assert preview["changed_count"] == 2
    assert {item["employee_code"] for item in preview["comparisons"]} == {"C-1", "C-2"}
    by_code = {item["employee_code"]: item for item in preview["comparisons"]}
    assert by_code["C-1"]["before_score"] == 70
    assert by_code["C-1"]["after_score"] == 100
    assert by_code["C-1"]["kpis"][0]["workbook_target"] == 40
    assert by_code["C-1"]["kpis"][0]["applied_target"] == 50
    assert by_code["C-2"]["after_score"] == 60
    assert len(preview["conflicts"]) == 2
    assert {item["workbook_target"] for item in preview["conflicts"]} == {40}
    assert {item["fixed_target"] for item in preview["conflicts"]} == {50}
    assert float(first.score) == 70
    assert float(first.kpi_values[0].target_value) == 40
    assert float(august.score) == 71
    assert float(managerial.score) == 80
    assert float(other.score) == 88
    assert world.workflow.protected_texts() == protected
    stored = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    assert stored.config_snapshot["preview_evidence"]["source_fingerprint"] == preview["source_fingerprint"]
    assert stored.config_checksum == stored.config_snapshot["preview_evidence"]["rules_checksum"]

    reads = world.workflow.reads(world.actor, world.scope["id"], 2026, [7])
    assert reads["periods"][0]["pinned"] is False
    assert reads["periods"][0]["stored_score"] == 70
    assert "evaluation_basis" not in (first.record_payload or {})


def test_missing_actual_and_empty_month_do_not_pretend_to_score(db):
    world = _World(db)
    empty = _draft_target(world, 8, 55)
    preview = world.workflow.impact_preview(world.actor, empty["id"])
    assert preview["affected_count"] == 0
    assert preview["scored_employees"] == 0
    assert preview["zero_affected"] is True
    assert preview["config_validated"] is True
    assert preview["comparisons"] == []
    assert preview["conflicts"] == []
    approved = world.workflow.approve(world.actor, empty["id"])
    assert approved["applied"] is False
    assert db.query(PerformanceRecord).count() == 0
    assert db.query(EvaluationRevision).count() == 0

    draft = _draft_target(world, 7, 55)
    key = draft["lines"][0]["kpi_key"]
    record = world.record(world.employee_a, "July", "70.00", "D")
    world.kpi(record, "NotTheWeightedKpi", 60, 40)
    db.commit()
    with pytest.raises(Exception) as missing:
        world.workflow.impact_preview(world.actor, draft["id"])
    assert missing.value.status_code == 422
    assert missing.value.data["code"] == "missing_evidence"
    assert missing.value.data["missing_evidence"][0]["kpi_key"] == key
    db.refresh(record)
    assert float(record.score) == 70
    stored = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    assert "preview_evidence" not in (stored.config_snapshot or {})


def test_stale_rules_or_uploads_block_approval_and_apply(db):
    world = _World(db)
    draft = _draft_target(world, 7, 55)
    key = draft["lines"][0]["kpi_key"]
    record = world.record(world.employee_a, "July", "70.00", "D")
    kpi = world.kpi(record, key, 60, 40)
    db.commit()
    world.workflow.impact_preview(world.actor, draft["id"])
    stored = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    original_snapshot = json.loads(json.dumps(stored.config_snapshot))
    mutated = json.loads(json.dumps(stored.config_snapshot))
    mutated["lines"][0]["target"] = 58
    stored.config_snapshot = mutated
    flag_modified(stored, "config_snapshot")
    db.commit()
    with pytest.raises(EvaluationConflict) as stale_rules:
        world.workflow.approve(world.actor, draft["id"])
    assert stale_rules.value.status_code == 409
    assert stale_rules.value.data["code"] == "stale_preview"
    db.refresh(record)
    assert float(record.score) == 70
    stored.config_snapshot = original_snapshot
    flag_modified(stored, "config_snapshot")
    db.commit()

    world.workflow.edit_draft(world.actor, draft["id"], _line_edit(draft["lines"], 57))
    with pytest.raises(EvaluationConflict) as cleared_proof:
        world.workflow.approve(world.actor, draft["id"])
    assert cleared_proof.value.status_code == 409
    assert cleared_proof.value.data["code"] == "preview_required"
    db.refresh(record)
    assert float(record.score) == 70

    world.workflow.impact_preview(world.actor, draft["id"])
    kpi.actual_value = Decimal("61")
    db.commit()
    with pytest.raises(EvaluationConflict) as stale_upload:
        world.workflow.approve(world.actor, draft["id"])
    assert stale_upload.value.data["code"] == "stale_preview"
    kpi.actual_value = Decimal("60")
    db.commit()
    approved = world.workflow.approve(world.actor, draft["id"])
    assert approved["applied"] is False
    assert db.query(EvaluationRevision).count() == 0
    db.refresh(record)
    assert float(record.score) == 70
    assert record.record_payload["manager_notes"] == "keep July"

    record.uploaded_at = datetime(2026, 7, 18, tzinfo=timezone.utc)
    db.commit()
    with pytest.raises(EvaluationConflict) as stale_apply:
        world.workflow.apply(world.actor, world.scope["id"], 2026, 7)
    assert stale_apply.value.data["code"] == "stale_preview"
    db.refresh(record)
    assert float(record.score) == 70
    record.uploaded_at = world.uploaded_at
    db.commit()


def test_apply_is_idempotent_and_rollback_refuses_drift(db):
    world = _World(db)
    draft = _draft_target(world, 7, 50)
    key = draft["lines"][0]["kpi_key"]
    first = world.record(world.employee_a, "July", "70.00", "D")
    second = world.record(world.employee_b, "July", "72.00", "D")
    august = world.record(world.employee_a, "August", "71.00", "D")
    other = world.record(world.employee_a, "July", "88.00", "B", team=world.other)
    managerial = world.record(world.employee_a, "July", "80.00", "C", level="Managerial")
    kpi_a = world.kpi(first, key, 60, 40)
    kpi_b = world.kpi(second, key, 30, 40)
    world.kpi(august, key, 60, 40)
    world.kpi(other, key, 60, 40)
    world.kpi(managerial, key, 60, 40)
    plan = PerformancePlan(
        id=uuid.uuid4(), name="July coaching plan", scope_type="Team", team_id=world.coding.id,
        performance_level="Employee", period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
        due_date=date(2026, 7, 31), owner_user_id=world.admin.id, baseline_value=1, target_value=10,
        outcome_unit="%", outcome_direction="higher_better", status="Draft",
    )
    action = Action(id=uuid.uuid4(), team_id=world.coding.id, month="July", year=2026, action_type="Coaching", action_text="Coach the queue", status="Open")
    report = GeneratedReport(
        id=uuid.uuid4(), name="July pack", report_type="team", scope_summary="Coding", period_label="July 2026",
        created_by_name="revision-admin", output_format="pdf", status="ready", file_name="july.pdf",
        content_type="application/pdf", file_data=b"saved-report", configuration={}, scope_json={},
        final_definition_json={}, narrative_snapshot_json={"text": "original narrative"},
        data_snapshot_json={"score": 70}, validation_json={},
    )
    db.add_all([plan, action, report])
    db.commit()
    protected = world.workflow.protected_texts()
    approved = _approve(world.workflow, world.actor, draft["id"])
    db.refresh(first)
    assert float(first.score) == 70

    applied = world.workflow.apply(world.actor, world.scope["id"], 2026, 7)
    assert applied["idempotent"] is False
    db.refresh(first)
    db.refresh(second)
    db.refresh(august)
    db.refresh(other)
    db.refresh(managerial)
    assert float(first.score) == 100
    assert first.grade == "A"
    assert first.record_payload["evaluation_basis"]["version_id"] == approved["id"]
    assert first.record_payload["evaluation_basis"]["lines"][0]["target"] == 50
    assert first.record_payload["manager_notes"] == "keep July"
    assert float(second.score) == 60
    assert float(august.score) == 71
    assert float(other.score) == 88
    assert float(managerial.score) == 80
    assert world.workflow.protected_texts() == protected
    revision = db.query(EvaluationRevision).one()
    assert revision.status == "active"
    assert revision.previous_revision_id is None
    for snapshot in (revision.prior_snapshot, revision.applied_snapshot):
        assert snapshot["hash"]
        assert len(snapshot["records"]) == 2
        item = snapshot["records"][0]
        assert {"id", "year", "month", "team_id", "performance_level", "position_name", "employee_id", "branch_key", "region", "upload_id", "uploaded_at", "payload", "kpis"} <= set(item)
        kpi = item["kpis"][0]
        assert {"id", "kpi_key", "actual", "target", "achievement", "weight", "contribution"} <= set(kpi)
    assert revision.prior_snapshot["hash"] != revision.applied_snapshot["hash"]

    scores = (float(first.score), float(second.score))
    retry = world.workflow.apply(world.actor, world.scope["id"], 2026, 7)
    db.refresh(first)
    db.refresh(second)
    assert retry["idempotent"] is True
    assert retry["revision_id"] == applied["revision_id"]
    assert db.query(EvaluationRevision).count() == 1
    assert (float(first.score), float(second.score)) == scores

    def refuse(mutate, repair):
        mutate()
        db.commit()
        with pytest.raises(EvaluationConflict) as refused:
            world.workflow.rollback(world.actor, applied["revision_id"])
        assert refused.value.status_code == 409
        assert refused.value.data["code"] == "evidence_changed"
        db.refresh(first)
        db.refresh(revision)
        assert float(first.score) == 100
        assert revision.status == "active"
        repair()
        db.commit()

    original_payload = json.loads(json.dumps(first.record_payload))
    refuse(
        lambda: first.__setattr__("record_payload", {**first.record_payload, "manager_notes": "edited"}),
        lambda: first.__setattr__("record_payload", original_payload),
    )
    original_actual = kpi_a.actual_value
    refuse(lambda: kpi_a.__setattr__("actual_value", Decimal("12")), lambda: kpi_a.__setattr__("actual_value", original_actual))
    later = datetime(2026, 7, 20, tzinfo=timezone.utc)
    newer = UploadLog(id=uuid.uuid4(), team_id=world.coding.id, month="July", year=2026, record_count=2, status="completed", uploaded_at=later)
    db.add(newer)
    db.commit()
    refuse(
        lambda: (first.__setattr__("upload_id", newer.id), first.__setattr__("uploaded_at", later)),
        lambda: (first.__setattr__("upload_id", world.upload.id), first.__setattr__("uploaded_at", world.uploaded_at)),
    )
    extra_kpi = None

    def add_kpi():
        nonlocal extra_kpi
        extra_kpi = world.kpi(first, "ExtraKpi", 1, 1)

    def drop_kpi():
        db.delete(extra_kpi)

    refuse(add_kpi, drop_kpi)
    extra_record = None

    def add_record():
        nonlocal extra_record
        extra_record = world.record(world.employee_b, "July", "61.00", "E", upload=False)
        world.kpi(extra_record, key, 10, 40)

    def drop_record():
        for value in list(extra_record.kpi_values):
            db.delete(value)
        db.delete(extra_record)

    refuse(add_record, drop_record)
    removed = {
        "id": kpi_b.id,
        "actual": kpi_b.actual_value,
        "target": kpi_b.target_value,
        "achievement": kpi_b.achievement_ratio,
        "weight": kpi_b.weight_applied,
        "contribution": kpi_b.contribution,
        "key": kpi_b.kpi_key,
        "record_id": kpi_b.record_id,
        "year": kpi_b.record_year,
    }
    db.delete(kpi_b)
    db.commit()
    with pytest.raises(EvaluationConflict) as deleted_kpi:
        world.workflow.rollback(world.actor, applied["revision_id"])
    assert deleted_kpi.value.data["code"] == "evidence_changed"
    db.refresh(first)
    assert float(first.score) == 100
    db.add(KPIValue(
        id=removed["id"], record_id=removed["record_id"], record_year=removed["year"], kpi_key=removed["key"],
        actual_value=removed["actual"], target_value=removed["target"], achievement_ratio=removed["achievement"],
        weight_applied=removed["weight"], contribution=removed["contribution"],
    ))
    db.commit()

    removed_record_id = second.id
    removed_score = second.score
    removed_grade = second.grade
    removed_status = second.status
    removed_payload = json.loads(json.dumps(second.record_payload))
    kept_kpis = [
        {
            "id": value.id,
            "kpi_key": value.kpi_key,
            "actual": value.actual_value,
            "target": value.target_value,
            "achievement": value.achievement_ratio,
            "weight": value.weight_applied,
            "contribution": value.contribution,
        }
        for value in list(second.kpi_values)
    ]
    for value in list(second.kpi_values):
        db.delete(value)
    db.delete(second)
    db.commit()
    with pytest.raises(EvaluationConflict) as deleted_record:
        world.workflow.rollback(world.actor, applied["revision_id"])
    assert deleted_record.value.data["code"] == "evidence_changed"
    restored_record = PerformanceRecord(
        id=removed_record_id, year=2026, employee_id=world.employee_b.id, team_id=world.coding.id,
        month="July", performance_level="Employee", position_name="", region="UAE", branch_key="dubai",
        score=removed_score, grade=removed_grade, status=removed_status,
        upload_id=world.upload.id, uploaded_at=world.uploaded_at, record_payload=removed_payload,
    )
    db.add(restored_record)
    db.flush()
    for value in kept_kpis:
        db.add(KPIValue(
            id=value["id"], record_id=removed_record_id, record_year=2026, kpi_key=value["kpi_key"],
            actual_value=value["actual"], target_value=value["target"],
            achievement_ratio=value["achievement"], weight_applied=value["weight"],
            contribution=value["contribution"],
        ))
    db.commit()

    rolled = world.workflow.rollback(world.actor, applied["revision_id"])
    db.refresh(first)
    db.refresh(kpi_a)
    db.refresh(revision)
    assert rolled["status"] == "rolled_back"
    assert rolled["restored_revision_id"] is None
    assert rolled["restored_basis"]
    assert all(item["evaluation_basis"] is None for item in rolled["restored_basis"])
    assert float(first.score) == 70
    assert first.grade == "D"
    assert first.record_payload["manager_notes"] == "keep July"
    assert "evaluation_basis" not in first.record_payload
    assert float(kpi_a.target_value) == 40
    assert float(kpi_a.actual_value) == 60
    assert revision.status == "rolled_back"
    assert float(august.score) == 71
    assert float(other.score) == 88
    assert float(managerial.score) == 80
    assert world.workflow.protected_texts() == protected
    with pytest.raises(Exception) as repeated:
        world.workflow.rollback(world.actor, applied["revision_id"])
    assert repeated.value.status_code == 422
    db.refresh(first)
    assert float(first.score) == 70


def test_older_revision_is_not_marked_rolled_back_and_cannot_undo_a_newer_one(db):
    world = _World(db)
    draft = _draft_target(world, 7, 50)
    key = draft["lines"][0]["kpi_key"]
    record = world.record(world.employee_a, "July", "70.00", "D")
    kpi = world.kpi(record, key, 60, 40)
    db.commit()
    _approve(world.workflow, world.actor, draft["id"])
    first = world.workflow.apply(world.actor, world.scope["id"], 2026, 7)
    db.refresh(record)
    assert float(record.score) == 100

    revised = world.workflow.revise(world.actor, db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.status == "approved").one().id)
    world.workflow.edit_draft(world.actor, revised["id"], _line_edit(revised["lines"], 80))
    _approve(world.workflow, world.actor, revised["id"])
    second = world.workflow.apply(world.actor, world.scope["id"], 2026, 7)
    db.refresh(record)
    db.refresh(kpi)
    assert second["revision_id"] != first["revision_id"]
    assert float(record.score) == 75
    assert float(kpi.target_value) == 80
    older = db.query(EvaluationRevision).filter(EvaluationRevision.id == uuid.UUID(first["revision_id"])).one()
    newer = db.query(EvaluationRevision).filter(EvaluationRevision.id == uuid.UUID(second["revision_id"])).one()
    assert older.status != "rolled_back"
    assert newer.status == "active"
    assert newer.previous_revision_id == older.id
    older_status = older.status

    with pytest.raises(EvaluationConflict) as too_old:
        world.workflow.rollback(world.actor, first["revision_id"])
    assert too_old.value.status_code == 409
    assert too_old.value.data["code"] == "not_latest"
    db.refresh(record)
    db.refresh(older)
    assert float(record.score) == 75
    assert older.status == older_status

    rolled = world.workflow.rollback(world.actor, second["revision_id"])
    db.refresh(record)
    db.refresh(kpi)
    db.refresh(older)
    db.refresh(newer)
    assert rolled["restored_revision_id"] is None
    assert float(record.score) == 100
    assert float(kpi.target_value) == 50
    assert record.record_payload["evaluation_basis"]["version_id"] != revised["id"]
    assert older.status == older_status
    assert newer.status == "rolled_back"
    with pytest.raises(Exception):
        world.workflow.rollback(world.actor, second["revision_id"])
    db.refresh(record)
    assert float(record.score) == 100
    assert db.query(EvaluationRevision).count() == 2


def test_pharmacy_records_stay_outside_the_audited_correction_rollout(db):
    world = _World(db)
    pharmacy = next(
        item for item in world.workflow.sync_catalog(world.actor)["scopes"]
        if item["display_name"] == "Pharmacy" and item["performance_level"] == "Employee" and item["position_name"] == ""
    )
    record = world.record(world.employee_a, "July", "70.00", "D", team=world.other)
    world.kpi(record, "WaitingTime", 60, 40)
    db.commit()
    if pharmacy["readiness"] != "supported":
        with pytest.raises(Exception) as blocked:
            world.workflow.open_draft(world.actor, pharmacy["id"], 2026, 7)
        assert blocked.value.status_code in {422, 409}
        db.refresh(record)
        assert float(record.score) == 70
        return
    draft = world.workflow.open_draft(world.actor, pharmacy["id"], 2026, 7)
    with pytest.raises(Exception) as blocked:
        world.workflow.impact_preview(world.actor, draft["id"])
    assert blocked.value.data["code"] == "scope_blocked"
    db.refresh(record)
    assert float(record.score) == 70
    stored = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    assert "preview_evidence" not in (stored.config_snapshot or {})
