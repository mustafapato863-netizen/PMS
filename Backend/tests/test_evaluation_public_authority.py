"""Persisted Admin is read again after the public workflow's team fence.

The fence hook is a deterministic sequencing probe. It does not certify a
native PostgreSQL race. SQLite does not take the team row lock.
"""

import os

if (
    os.environ.get("APP_ENV") != "test"
    or os.environ.get("DATABASE_URL") != "sqlite:///:memory:"
    or os.environ.get("REDIS_URL", "")
):
    raise RuntimeError("Anonymous test environment is required before import")

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
from services.cache_invalidation_service import CacheInvalidationService
from services.evaluation.access import AccessDenied, EvaluationError
from services.evaluation.workflow import EvaluationWorkflow, _freeze, _full_snapshot
from test_evaluation_month_revision import (
    _actor,
    _approve,
    _client,
    _draft_target,
    _line_edit,
    _World,
)

OPERATIONS = (
    "apply",
    "rollback",
    "idempotent_apply",
    "open_draft",
    "open_draft_copy",
    "edit_draft",
    "approve",
    "revise",
    "impact_preview",
    "preview",
    "run_preview_job",
)


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
            UploadLog.__table__,
        ],
    )
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield session
    session.close()


def _protect(world: _World) -> None:
    plan = PerformancePlan(
        id=uuid.uuid4(), name="July coaching plan", scope_type="Team", team_id=world.coding.id,
        performance_level="Employee", period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
        due_date=date(2026, 7, 31), owner_user_id=world.admin.id, baseline_value=1, target_value=10,
        outcome_unit="%", outcome_direction="higher_better", status="Draft",
    )
    action = Action(
        id=uuid.uuid4(), team_id=world.coding.id, month="July", year=2026, action_type="Coaching",
        action_text="Coach the queue", status="Open",
    )
    report = GeneratedReport(
        id=uuid.uuid4(), name="July pack", report_type="team", scope_summary="Coding", period_label="July 2026",
        created_by_name="revision-admin", output_format="pdf", status="ready", file_name="july.pdf",
        content_type="application/pdf", file_data=b"saved-report", configuration={}, scope_json={},
        final_definition_json={}, narrative_snapshot_json={"text": "original narrative"},
        data_snapshot_json={"score": 70}, validation_json={},
    )
    world.db.add_all([plan, action, report])
    world.db.commit()


def _inventory(world: _World) -> dict:
    records = world.db.query(PerformanceRecord).all()
    versions = world.db.query(TeamConfigurationVersion).order_by(TeamConfigurationVersion.id).all()
    revisions = world.db.query(EvaluationRevision).order_by(EvaluationRevision.id).all()
    return {
        "records": _freeze(_full_snapshot(records)),
        "versions": [
            (
                str(row.id),
                row.status,
                row.version_number,
                row.config_checksum,
                _freeze(row.config_snapshot),
                _freeze(row.actor_created_snapshot),
                _freeze(row.actor_published_snapshot),
            )
            for row in versions
        ],
        "revisions": [
            (
                str(row.id),
                row.status,
                str(row.version_id),
                None if row.previous_revision_id is None else str(row.previous_revision_id),
                _freeze(row.prior_snapshot),
                _freeze(row.applied_snapshot),
                _freeze(row.actor_snapshot),
            )
            for row in revisions
        ],
        "protected": world.workflow.protected_texts(),
        "cache": (
            CacheInvalidationService.get_data_version(),
            CacheInvalidationService.get_config_version(),
        ),
    }


def _mutation(world: _World, operation: str, actor: dict):
    """Build one public call. Setup itself always uses the real persisted Admin."""
    record = world.record(world.employee_a, "July", "70.00", "D")
    world.record(world.employee_a, "August", "71.00", "D")
    draft = _draft_target(world, 7, 50)
    key = draft["lines"][0]["kpi_key"]
    world.kpi(record, key, 40, 50)
    _protect(world)
    workflow = world.workflow
    scope_id = world.scope["id"]

    def approve_current():
        return _approve(workflow, world.actor, draft["id"])

    if operation == "open_draft":
        return lambda: workflow.open_draft(actor, scope_id, 2026, 8)
    if operation == "open_draft_copy":
        approve_current()
        return lambda: workflow.open_draft(actor, scope_id, 2026, 8, copy_previous=True)
    if operation == "edit_draft":
        lines = _line_edit(draft["lines"], 48)
        return lambda: workflow.edit_draft(actor, draft["id"], lines)
    if operation == "impact_preview":
        return lambda: workflow.impact_preview(actor, draft["id"])
    if operation == "preview":
        rows = [{"kpi_key": key, "actual": 40, "workbook_target": 50}]
        return lambda: workflow.preview(actor, draft["id"], rows)
    if operation == "run_preview_job":
        rows = [{"kpi_key": key, "actual": 40, "workbook_target": 50}]
        return lambda: workflow.run_preview_job(actor, draft["id"], rows)
    if operation == "approve":
        workflow.impact_preview(world.actor, draft["id"])
        return lambda: workflow.approve(actor, draft["id"])
    if operation == "revise":
        approved = approve_current()
        return lambda: workflow.revise(actor, approved["id"])
    if operation == "apply":
        approve_current()
        return lambda: workflow.apply(actor, scope_id, 2026, 7)
    if operation == "idempotent_apply":
        approve_current()
        workflow.apply(world.actor, scope_id, 2026, 7)
        return lambda: workflow.apply(actor, scope_id, 2026, 7)
    if operation == "rollback":
        approve_current()
        applied = workflow.apply(world.actor, scope_id, 2026, 7)
        return lambda: workflow.rollback(actor, applied["revision_id"])
    raise AssertionError(operation)


def _hook_fence(monkeypatch, world: _World, preloaded: User, revocation: str | None) -> list:
    """Revoke inside the first team fence, after the real lock request returns."""
    original = world.workflow._lock_team
    seen = []
    admin_id = preloaded.id

    def hooked(team_id):
        original(team_id)
        seen.append(team_id)
        if revocation is None or len(seen) != 1:
            return
        column = User.role if revocation == "role" else User.is_active
        value = "Performance Team" if revocation == "role" else False
        updated = world.db.query(User).filter(User.id == admin_id).update(
            {column: value},
            synchronize_session=False,
        )
        assert updated == 1
        world.db.flush()
        assert preloaded.role == "Admin"
        assert preloaded.is_active is True

    monkeypatch.setattr(world.workflow, "_lock_team", hooked)
    return seen


def _lock_count(world: _World) -> int:
    return len(world.db.info.get("evaluation_team_lock_order") or [])


@pytest.mark.parametrize("revocation", ["role", "deactivate"])
@pytest.mark.parametrize("operation", OPERATIONS)
def test_persisted_revocation_during_team_fence_is_denied(db, monkeypatch, operation, revocation):
    world = _World(db)
    db.expire_on_commit = False
    call = _mutation(world, operation, world.actor)
    preloaded = db.query(User).filter(User.id == world.admin.id).one()
    assert preloaded.role == "Admin"
    assert preloaded.is_active is True
    seen = _hook_fence(monkeypatch, world, preloaded, revocation)
    before_locks = _lock_count(world)
    before = _inventory(world)

    with pytest.raises(AccessDenied) as denied:
        call()

    assert denied.value.status_code == 403
    assert seen == [world.coding.id]
    assert _lock_count(world) == before_locks + 1
    assert world.db.info["evaluation_team_lock_order"][-1] == [world.coding.id]
    assert world.actor["role"] == "Admin"
    if revocation == "role":
        assert preloaded.role == "Performance Team"
        assert preloaded.is_active is True
    else:
        assert preloaded.role == "Admin"
        assert preloaded.is_active is False
    reloaded = db.query(User).populate_existing().filter(User.id == preloaded.id).one()
    assert reloaded is preloaded
    assert _inventory(world) == before


@pytest.mark.parametrize("operation", OPERATIONS)
def test_spoofed_admin_is_denied_before_the_team_fence(db, monkeypatch, operation):
    world = _World(db)
    call = _mutation(world, operation, {
        **_actor(world.performance),
        "role": "Admin",
        "has_unrestricted_team_access": True,
    })
    preloaded = db.query(User).filter(User.id == world.performance.id).one()
    seen = _hook_fence(monkeypatch, world, preloaded, None)
    before_locks = _lock_count(world)
    before = _inventory(world)

    with pytest.raises(AccessDenied) as denied:
        call()

    assert denied.value.status_code == 403
    assert seen == []
    assert _lock_count(world) == before_locks
    assert preloaded.role == "Performance Team"
    assert _inventory(world) == before


def test_direct_stale_actor_role_is_denied_before_the_fence(db, monkeypatch):
    world = _World(db)
    stale = {**world.actor, "role": "Manager"}
    call = _mutation(world, "apply", stale)
    preloaded = db.query(User).filter(User.id == world.admin.id).one()
    seen = _hook_fence(monkeypatch, world, preloaded, None)
    before = _inventory(world)

    with pytest.raises(AccessDenied) as denied:
        call()

    assert denied.value.status_code == 403
    assert seen == []
    assert preloaded.role == "Admin"
    assert preloaded.is_active is True
    assert stale["role"] == "Manager"
    assert _inventory(world) == before


def test_idle_fence_still_admits_persisted_admin(db, monkeypatch):
    world = _World(db)
    db.expire_on_commit = False
    call = _mutation(world, "apply", world.actor)
    preloaded = db.query(User).filter(User.id == world.admin.id).one()
    seen = _hook_fence(monkeypatch, world, preloaded, None)
    before = _inventory(world)

    applied = call()

    assert seen == [world.coding.id]
    assert applied["idempotent"] is False
    assert preloaded.role == "Admin"
    assert preloaded.is_active is True
    after = _inventory(world)
    assert after["records"] != before["records"]
    assert after["cache"][0] == before["cache"][0] + 1
    assert after["cache"][1] == before["cache"][1]
    assert [row[1] for row in after["revisions"]] == ["active"]


def test_admin_apply_is_idempotent_and_rollback_does_not_reactivate_approval(db):
    world = _World(db)
    record = world.record(world.employee_a, "July", "70.00", "D")
    world.record(world.employee_a, "August", "71.00", "D")
    draft = _draft_target(world, 7, 50)
    world.kpi(record, draft["lines"][0]["kpi_key"], 40, 50)
    _protect(world)
    protected = world.workflow.protected_texts()
    initial_records = _inventory(world)["records"]

    first = _approve(world.workflow, world.actor, draft["id"])
    revised = world.workflow.revise(world.actor, first["id"])
    edited = world.workflow.edit_draft(world.actor, revised["id"], _line_edit(revised["lines"], 40))
    second = _approve(world.workflow, world.actor, edited["id"])
    stored_first = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(first["id"])).one()
    stored_second = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(second["id"])).one()
    assert stored_first.status == "superseded"
    assert stored_second.status == "approved"
    assert _inventory(world)["records"] == initial_records

    data_before = CacheInvalidationService.get_data_version()
    config_before = CacheInvalidationService.get_config_version()
    applied = world.workflow.apply(world.actor, world.scope["id"], 2026, 7)
    assert applied["idempotent"] is False
    assert CacheInvalidationService.get_data_version() == data_before + 1
    assert CacheInvalidationService.get_config_version() == config_before
    changed = _inventory(world)
    assert changed["records"] != initial_records
    assert [row[1] for row in changed["revisions"]] == ["active"]

    retry = world.workflow.apply(world.actor, world.scope["id"], 2026, 7)
    assert retry["idempotent"] is True
    assert retry["revision_id"] == applied["revision_id"]
    assert CacheInvalidationService.get_data_version() == data_before + 1
    assert _inventory(world)["records"] == changed["records"]
    assert db.query(EvaluationRevision).count() == 1

    rolled = world.workflow.rollback(world.actor, applied["revision_id"])
    assert rolled["status"] == "rolled_back"
    assert rolled["restored_revision_id"] is None
    assert CacheInvalidationService.get_data_version() == data_before + 2
    restored = _inventory(world)
    assert restored["records"] == initial_records
    db.refresh(stored_first)
    db.refresh(stored_second)
    revision = db.query(EvaluationRevision).one()
    assert revision.status == "rolled_back"
    assert stored_first.status == "superseded"
    assert stored_second.status == "approved"
    with pytest.raises(EvaluationError) as again:
        world.workflow.rollback(world.actor, applied["revision_id"])
    assert again.value.data["code"] == "immutable"
    db.refresh(revision)
    db.refresh(stored_first)
    db.refresh(stored_second)
    assert revision.status == "rolled_back"
    assert stored_first.status == "superseded"
    assert stored_second.status == "approved"
    assert world.workflow.protected_texts() == protected
    assert _inventory(world)["records"] == initial_records


def test_stale_non_admin_request_role_keeps_persisted_admin_contract(db):
    world = _World(db)
    record = world.record(world.employee_a, "July", "70.00", "D")
    draft = _draft_target(world, 7, 50)
    world.kpi(record, draft["lines"][0]["kpi_key"], 40, 50)
    _protect(world)
    _approve(world.workflow, world.actor, draft["id"])
    before = _inventory(world)
    client, holder = _client(db)
    holder["user"] = {"user_id": str(world.admin.id), "role": "Manager"}

    applied = client.post(
        "/api/settings/evaluation/apply",
        json={"scope_id": world.scope["id"], "year": 2026, "month": 7},
    )
    assert applied.status_code == 200
    body = applied.json()["data"]
    assert body["idempotent"] is False
    assert _inventory(world)["records"] != before["records"]
    db.refresh(record)
    assert float(record.score) != 70

    holder["user"] = {"user_id": str(world.performance.id), "role": "Admin"}
    spoofed = client.post(
        "/api/settings/evaluation/revisions/{revision}/rollback".format(revision=body["revision_id"]),
    )
    assert spoofed.status_code == 403
    assert db.query(EvaluationRevision).one().status == "active"

    holder["user"] = {"user_id": str(world.admin.id), "role": "Employee"}
    rolled = client.post(
        "/api/settings/evaluation/revisions/{revision}/rollback".format(revision=body["revision_id"]),
    )
    assert rolled.status_code == 200
    assert rolled.json()["data"]["status"] == "rolled_back"
    assert rolled.json()["data"]["restored_revision_id"] is None
    db.refresh(record)
    assert float(record.score) == 70
    version = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    assert version.status == "approved"
    repeat = client.post(
        "/api/settings/evaluation/revisions/{revision}/rollback".format(revision=body["revision_id"]),
    )
    assert repeat.status_code == 422
    assert repeat.json()["detail"]["code"] == "immutable"
    assert db.query(EvaluationRevision).one().status == "rolled_back"
    assert version.status == "approved"
