"""Versioned correction of one approved month.

SQLite cannot prove the PostgreSQL team-row lock. A replaced revision must
become superseded before the next active row is inserted. Rollback refuses
an older revision while a newer active revision exists, and a rolled-back
revision stays rolled back.
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
from services.evaluation.access import AccessDenied, EvaluationError
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
    assert revised["source_version_number"] == source.version_number
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
    # This scope has two people, so neither person's score is its aggregate.
    assert reads["periods"][0]["stored_score"] is None
    assert {item["record_id"]: item["score"] for item in reads["periods"][0]["evidence"]} == {
        str(first.id): 70, str(second.id): 72,
    }
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
    assert missing.value.data["missing_evidence"][0]["reason"] == "missing_weighted_actual"
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

    drifted_payload = json.loads(json.dumps(first.record_payload))
    drifted_payload["manager_notes"] = "changed after apply"
    first.record_payload = drifted_payload
    flag_modified(first, "record_payload")
    db.commit()
    with pytest.raises(EvaluationConflict) as changed:
        world.workflow.apply(world.actor, world.scope["id"], 2026, 7)
    assert changed.value.status_code == 409
    assert changed.value.data["code"] == "evidence_changed"
    db.refresh(first)
    db.refresh(revision)
    assert float(first.score) == 100
    assert revision.status == "active"
    assert db.query(EvaluationRevision).count() == 1
    saved_payload = next(item["payload"] for item in revision.applied_snapshot["records"] if item["id"] == str(first.id))
    first.record_payload = json.loads(json.dumps(saved_payload))
    flag_modified(first, "record_payload")
    db.commit()
    restored_retry = world.workflow.apply(world.actor, world.scope["id"], 2026, 7)
    assert restored_retry["idempotent"] is True
    assert restored_retry["revision_id"] == applied["revision_id"]

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
    original_target = kpi_a.target_value
    refuse(lambda: kpi_a.__setattr__("target_value", Decimal("77")), lambda: kpi_a.__setattr__("target_value", original_target))
    full_payload = json.loads(json.dumps(first.record_payload))
    refuse(
        lambda: (
            first.__setattr__("record_payload", {"replaced": True, "evaluation": {"score": 1, "grade": "E"}}),
            flag_modified(first, "record_payload"),
        ),
        lambda: (
            first.__setattr__("record_payload", full_payload),
            flag_modified(first, "record_payload"),
        ),
    )
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
    assert older.status == "superseded"
    assert newer.status == "active"
    assert newer.previous_revision_id == older.id

    with pytest.raises(EvaluationConflict) as too_old:
        world.workflow.rollback(world.actor, first["revision_id"])
    assert too_old.value.status_code == 409
    assert too_old.value.data["code"] == "not_latest"
    db.refresh(record)
    db.refresh(older)
    assert float(record.score) == 75
    assert older.status == "superseded"

    rolled = world.workflow.rollback(world.actor, second["revision_id"])
    db.refresh(record)
    db.refresh(kpi)
    db.refresh(older)
    db.refresh(newer)
    assert rolled["restored_revision_id"] is None
    assert float(record.score) == 100
    assert float(kpi.target_value) == 50
    assert record.record_payload["evaluation_basis"]["version_id"] != revised["id"]
    assert older.status == "superseded"
    assert newer.status == "rolled_back"
    with pytest.raises(EvaluationError) as repeated:
        world.workflow.rollback(world.actor, second["revision_id"])
    assert repeated.value.status_code == 422
    assert repeated.value.data["code"] == "immutable"
    db.refresh(record)
    db.refresh(older)
    db.refresh(newer)
    assert float(record.score) == 100
    assert older.status == "superseded"
    assert newer.status == "rolled_back"
    assert db.query(EvaluationRevision).count() == 2

    third = world.workflow.apply(world.actor, world.scope["id"], 2026, 7)
    db.refresh(older)
    db.refresh(newer)
    chained = db.query(EvaluationRevision).filter(EvaluationRevision.id == uuid.UUID(third["revision_id"])).one()
    assert third["idempotent"] is False
    assert chained.status == "active"
    assert chained.previous_revision_id == newer.id
    assert older.status == "superseded"
    assert newer.status == "rolled_back"
    with pytest.raises(EvaluationConflict) as still_old:
        world.workflow.rollback(world.actor, first["revision_id"])
    assert still_old.value.data["code"] == "not_latest"
    db.refresh(record)
    assert float(record.score) == 75
    assert db.query(EvaluationRevision).count() == 3


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


def _snapshot_obj(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


def _workbook_lines(lines: list[dict]) -> list[dict]:
    edited = []
    for index, line in enumerate(lines):
        edited.append({
            **line,
            "weight": 1 if index == 0 else 0,
            "direction": "higher_better",
            "target_mode": "workbook" if index == 0 else "fixed",
            "target": line.get("target") if index == 0 else 1,
        })
    return edited


def test_successive_corrections_keep_the_original_workbook_target(db):
    world = _World(db)
    draft = _draft_target(world, 7, 65)
    key = draft["lines"][0]["kpi_key"]
    assert key == "QualityErrors"
    record = world.record(world.employee_a, "July", "70.00", "D")
    kpi = world.kpi(record, key, 40, 55)
    db.commit()
    original_payload = json.loads(json.dumps(record.record_payload))

    preview = world.workflow.impact_preview(world.actor, draft["id"])
    db.refresh(kpi)
    assert float(kpi.target_value) == 55
    conflict = preview["conflicts"][0]
    assert conflict["workbook_target"] == 55
    assert conflict["fixed_target"] == 65
    assert conflict["approved_target"] == 65
    assert conflict["difference"] == -10
    compared = preview["comparisons"][0]["kpis"][0]
    assert compared["workbook_target"] == 55
    assert compared["applied_target"] == 65
    assert preview["comparisons"][0]["after_score"] == round((40 / 65) * 100, 2)

    _approve(world.workflow, world.actor, draft["id"])
    applied = world.workflow.apply(world.actor, world.scope["id"], 2026, 7)
    db.refresh(record)
    db.refresh(kpi)
    assert float(kpi.target_value) == 65
    evidence = record.record_payload["source_evidence"]
    assert evidence["origin"] == "sql_before_apply"
    assert evidence["kpis"][key] == {"actual": "40", "target": "55"}
    assert applied["idempotent"] is False

    revised = world.workflow.revise(world.actor, draft["id"])
    again = world.workflow.impact_preview(world.actor, revised["id"])
    db.refresh(kpi)
    assert float(kpi.target_value) == 65
    assert again["conflicts"][0]["workbook_target"] == 55
    assert again["conflicts"][0]["approved_target"] == 65
    assert again["comparisons"][0]["kpis"][0]["workbook_target"] == 55
    assert again["comparisons"][0]["kpis"][0]["applied_target"] == 65

    workbook = world.workflow.edit_draft(world.actor, revised["id"], _workbook_lines(revised["lines"]))
    assert workbook["lines"][0]["target_mode"] == "workbook"
    workbook_preview = world.workflow.impact_preview(world.actor, revised["id"])
    db.refresh(kpi)
    assert float(kpi.target_value) == 65
    assert workbook_preview["comparisons"][0]["kpis"][0]["workbook_target"] == 55
    assert workbook_preview["comparisons"][0]["kpis"][0]["applied_target"] == 55
    assert workbook_preview["comparisons"][0]["after_score"] == round((40 / 55) * 100, 2)
    assert workbook_preview["conflicts"] == []

    rolled = world.workflow.rollback(world.actor, applied["revision_id"])
    db.refresh(record)
    db.refresh(kpi)
    assert rolled["status"] == "rolled_back"
    assert json.loads(json.dumps(record.record_payload, sort_keys=True)) == json.loads(json.dumps(original_payload, sort_keys=True))
    assert "source_evidence" not in record.record_payload
    assert float(kpi.target_value) == 55
    assert float(kpi.actual_value) == 40
    assert float(record.score) == 70


def test_raw_workbook_precision_beats_rounded_sql_and_scored_payload(db):
    world = _World(db)
    draft = _draft_target(world, 7, 70)
    key = draft["lines"][0]["kpi_key"]
    assert key == "QualityErrors"
    record = world.record(world.employee_a, "July", "70.00", "D", payload={
        "manager_notes": "raw july",
        "raw_data": {
            "A.QualityErrorsRate": "60.123456789",
            "T.QualityErrorsRate": "55",
        },
        "kpi_values": {"QualityErrors": {"actual": 1, "target": 99}},
    })
    world.kpi(record, key, Decimal("60.1235"), Decimal("65"))
    db.commit()
    preview = world.workflow.impact_preview(world.actor, draft["id"])
    compared = preview["comparisons"][0]["kpis"][0]
    assert compared["actual"] == float(Decimal("60.123456789"))
    assert compared["workbook_target"] == 55
    assert preview["conflicts"][0]["workbook_target"] == 55
    assert preview["conflicts"][0]["approved_target"] == 70
    _approve(world.workflow, world.actor, draft["id"])
    world.workflow.apply(world.actor, world.scope["id"], 2026, 7)
    db.refresh(record)
    assert record.record_payload["source_evidence"]["origin"] == "workbook_raw"
    assert record.record_payload["source_evidence"]["kpis"][key] == {"actual": "60.123456789", "target": "55"}
    revised = world.workflow.revise(world.actor, draft["id"])
    again = world.workflow.impact_preview(world.actor, revised["id"])
    assert again["comparisons"][0]["kpis"][0]["actual"] == float(Decimal("60.123456789"))
    assert again["comparisons"][0]["kpis"][0]["workbook_target"] == 55


def test_pinned_or_absent_or_duplicate_or_nonfinite_sources_are_refused(db):
    world = _World(db)
    draft = _draft_target(world, 7, 65)
    key = draft["lines"][0]["kpi_key"]
    pinned = world.record(world.employee_a, "July", "70.00", "D", payload={
        "evaluation_basis": {"pinned": True, "version_id": str(uuid.uuid4())},
        "kpi_values": {key: {"actual": 40, "target": 55}},
    })
    world.kpi(pinned, key, 40, 55)
    db.commit()
    with pytest.raises(EvaluationError) as missing_pinned:
        world.workflow.impact_preview(world.actor, draft["id"])
    assert missing_pinned.value.data["code"] == "missing_evidence"
    assert missing_pinned.value.data["missing_evidence"][0]["reason"] == "missing_source"
    db.refresh(pinned)
    assert float(pinned.score) == 70
    stored = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    assert "preview_evidence" not in (stored.config_snapshot or {})

    absent = _draft_target(world, 8, 65)
    absent_record = world.record(world.employee_a, "August", "71.00", "D", payload={
        "raw_data": {"A.QualityErrorsRate": None, "T.QualityErrorsRate": None},
        "kpi_values": {key: {"actual": 40, "target": 55}},
    })
    world.kpi(absent_record, absent["lines"][0]["kpi_key"], 40, 55)
    db.commit()
    with pytest.raises(EvaluationError) as missing_raw:
        world.workflow.impact_preview(world.actor, absent["id"])
    assert missing_raw.value.data["missing_evidence"][0]["reason"] == "missing_source"
    db.refresh(absent_record)
    assert float(absent_record.score) == 71

    nan_draft = _draft_target(world, 9, 65)
    nan_record = world.record(world.employee_a, "September", "72.00", "D", payload={
        "raw_data": {"A.QualityErrorsRate": "NaN", "T.QualityErrorsRate": "55"},
    })
    world.kpi(nan_record, nan_draft["lines"][0]["kpi_key"], 40, 55)
    db.commit()
    with pytest.raises(EvaluationError) as nan_source:
        world.workflow.impact_preview(world.actor, nan_draft["id"])
    assert nan_source.value.data["code"] == "invalid_evidence"
    db.refresh(nan_record)
    assert float(nan_record.score) == 72
    nan_stored = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(nan_draft["id"])).one()
    assert "preview_evidence" not in (nan_stored.config_snapshot or {})

    duplicate_draft = _draft_target(world, 10, 65)
    duplicate_record = world.record(world.employee_a, "October", "73.00", "D")
    duplicate_key = duplicate_draft["lines"][0]["kpi_key"]
    world.kpi(duplicate_record, duplicate_key, 40, 55)
    world.kpi(duplicate_record, duplicate_key, 41, 56)
    db.commit()
    with pytest.raises(EvaluationError) as duplicate:
        world.workflow.impact_preview(world.actor, duplicate_draft["id"])
    assert duplicate.value.data["code"] == "duplicate_kpi"
    db.refresh(duplicate_record)
    assert float(duplicate_record.score) == 73


def test_actor_snapshots_come_from_the_database_user_and_survive_deletion(db):
    world = _World(db)
    spoofed = {**world.actor, "full_name": "Spoofed Name", "username": "spoofed"}
    draft = world.workflow.open_draft(spoofed, world.scope["id"], 2026, 7)
    version = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    created = _snapshot_obj(version.actor_created_snapshot)
    published = _snapshot_obj(version.actor_published_snapshot)
    assert created == {
        "state": "known",
        "user_id": str(world.admin.id),
        "username": world.admin.username,
        "full_name": world.admin.full_name,
        "role": "Admin",
    }
    assert created["full_name"] != "Spoofed Name"
    assert created["username"] != "spoofed"
    assert published == {"state": "unknown"}

    edited = world.workflow.edit_draft(spoofed, draft["id"], _line_edit(draft["lines"], 65))
    record = world.record(world.employee_a, "July", "70.00", "D")
    world.kpi(record, edited["lines"][0]["kpi_key"], 40, 55)
    db.commit()
    _approve(world.workflow, spoofed, draft["id"])
    db.refresh(version)
    assert _snapshot_obj(version.actor_created_snapshot) == created
    assert _snapshot_obj(version.actor_published_snapshot) == created
    applied = world.workflow.apply(spoofed, world.scope["id"], 2026, 7)
    revision = db.query(EvaluationRevision).filter(EvaluationRevision.id == uuid.UUID(applied["revision_id"])).one()
    assert _snapshot_obj(revision.actor_snapshot) == created
    assert revision.created_by_user_id == world.admin.id

    created_bytes = json.dumps(created, sort_keys=True)
    published_bytes = json.dumps(_snapshot_obj(version.actor_published_snapshot), sort_keys=True)
    revision_bytes = json.dumps(_snapshot_obj(revision.actor_snapshot), sort_keys=True)
    db.commit()
    dbapi = db.connection().connection
    previous_isolation = dbapi.isolation_level
    dbapi.isolation_level = None
    cursor = dbapi.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA foreign_keys")
    assert cursor.fetchone()[0] == 1
    cursor.close()
    dbapi.isolation_level = previous_isolation
    db.delete(world.admin)
    db.commit()
    db.refresh(version)
    db.refresh(revision)
    assert version.created_by_user_id is None
    assert version.published_by_user_id is None
    assert revision.created_by_user_id is None
    assert json.dumps(_snapshot_obj(version.actor_created_snapshot), sort_keys=True) == created_bytes
    assert json.dumps(_snapshot_obj(version.actor_published_snapshot), sort_keys=True) == published_bytes
    assert json.dumps(_snapshot_obj(revision.actor_snapshot), sort_keys=True) == revision_bytes

    scope_count = db.query(EvaluationScope).count()
    original_sync = world.workflow.catalog.sync

    def fail_sync(*_args, **_kwargs):
        raise AssertionError("catalog sync")

    world.workflow.catalog.sync = fail_sync
    try:
        for actor in (
            {**world.actor, "user_id": str(uuid.uuid4())},
            {**world.actor, "user_id": str(world.manager.id), "full_name": "Spoofed Name"},
        ):
            with pytest.raises(AccessDenied) as denied:
                world.workflow.revise(actor, draft["id"])
            assert denied.value.status_code == 403
            assert denied.value.message == "Evaluation settings are limited to Admin."
    finally:
        world.workflow.catalog.sync = original_sync
    assert db.query(EvaluationScope).count() == scope_count


def test_copy_previous_leaves_an_existing_draft_unchanged(db):
    world = _World(db)
    draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)
    stored = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    checksum = stored.config_checksum
    notes = stored.notes
    with pytest.raises(EvaluationConflict) as conflict:
        world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7, copy_previous=True)
    assert conflict.value.status_code == 409
    assert conflict.value.data["code"] == "draft_exists"
    db.refresh(stored)
    assert stored.status == "draft"
    assert stored.config_checksum == checksum
    assert stored.notes == notes
    resumed = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)
    assert resumed["id"] == draft["id"]
    assert resumed["checksum"] == checksum


def test_period_revisions_report_rollback_without_mutating_the_catalog(db):
    world = _World(db)
    scope_count = db.query(EvaluationScope).count()
    calls = {"sync": 0}
    original_sync = world.workflow.catalog.sync

    def counting_sync(*args, **kwargs):
        calls["sync"] += 1
        return original_sync(*args, **kwargs)

    world.workflow.catalog.sync = counting_sync
    with pytest.raises(EvaluationError) as missing_scope:
        world.workflow.period(world.actor, str(uuid.uuid4()), 2026, 7)
    assert missing_scope.value.data["code"] == "not_found"
    assert calls["sync"] == 0
    assert db.query(EvaluationScope).count() == scope_count

    draft = _draft_target(world, 7, 65)
    record = world.record(world.employee_a, "July", "70.00", "D")
    world.kpi(record, draft["lines"][0]["kpi_key"], 40, 55)
    db.commit()
    calls["sync"] = 0
    empty = world.workflow.period(world.actor, world.scope["id"], 2026, 7)
    assert empty["revisions"] == []
    assert calls["sync"] == 0
    _approve(world.workflow, world.actor, draft["id"])
    applied = world.workflow.apply(world.actor, world.scope["id"], 2026, 7)
    calls["sync"] = 0
    body = world.workflow.period(world.actor, world.scope["id"], 2026, 7)
    assert calls["sync"] == 0
    assert db.query(EvaluationScope).count() == scope_count
    assert len(body["revisions"]) == 1
    item = body["revisions"][0]
    assert set(item) == {"id", "version_id", "status", "created_at", "affected_count", "can_rollback"}
    assert item["id"] == applied["revision_id"]
    assert item["status"] == "active"
    assert item["affected_count"] == 1
    assert item["can_rollback"] is True
    assert item["created_at"]
    approved = next(row for row in body["versions"] if row["status"] == "approved")
    assert approved["checksum"]
    assert approved["proof"]["source_fingerprint"]
    assert approved["proof"]["affected_count"] == 1
    assert approved["proof"]["rules_checksum"] == approved["checksum"]
    assert "preview_evidence" not in approved

    legacy = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 9)
    legacy_row = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(legacy["id"])).one()
    assert _snapshot_obj(legacy_row.actor_published_snapshot) == {"state": "unknown"}
    calls["sync"] = 0
    world.workflow.period(world.actor, world.scope["id"], 2026, 9)
    db.refresh(legacy_row)
    assert _snapshot_obj(legacy_row.actor_published_snapshot) == {"state": "unknown"}
    assert _snapshot_obj(legacy_row.actor_created_snapshot)["state"] == "known"
    assert calls["sync"] == 0

    db.refresh(record)
    applied_score = record.score
    record.score = Decimal("71.00")
    db.commit()
    stale = world.workflow.period(world.actor, world.scope["id"], 2026, 7)
    assert stale["revisions"][0]["can_rollback"] is False
    assert stale["revisions"][0]["status"] == "active"
    record.score = applied_score
    db.commit()
    restored = world.workflow.period(world.actor, world.scope["id"], 2026, 7)
    assert restored["revisions"][0]["can_rollback"] is True
