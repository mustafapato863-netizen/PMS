import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import AuditLog, PerformancePlan, PlanMilestone, Team, User
from models.planning_schemas import PlanCreate, PlanMilestoneCreate, PlanMilestoneUpdate, PlanUpdate
from services.planning_service import PlanningAccessError, PlanningNotFoundError, PlanningService, PlanningValidationError


class StubRepo:
    def get_all(self): return []


@pytest.fixture()
def workspace():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    team = Team(id=uuid.uuid4(), name="Marketing", db_name="marketing", display_name="Marketing", region="EGY", team_level="employee", is_active=True)
    user = User(id=uuid.uuid4(), username="manager", email="manager@example.com", password_hash="x", role="Manager", is_active=True)
    db.add_all([team, user]); db.commit()
    scope = {"user_id": str(user.id), "role": "Admin", "is_general_manager": True, "legacy_unscoped": False, "accessible_teams": ["Marketing"], "accessible_team_levels": [("Marketing", "Employee")]}
    yield db, user, scope
    db.close()


def _payload(user, **changes):
    start = date.today() - timedelta(days=10)
    values = dict(
        name="Improve Marketing Performance", scope_type="Team", team="Marketing", performance_level="Employee",
        period_start=start, period_end=start + timedelta(days=60), due_date=start + timedelta(days=60), owner_user_id=user.id,
        baseline_value=60, target_value=80, current_value=70, expected_impact=20, no_insight_reason="Operational review requested",
        objectives=[{"name": "Raise team score", "measurement_type": "score", "baseline_value": 60, "target_value": 80, "current_value": 70, "unit": "%", "direction": "higher_better", "due_date": start + timedelta(days=60), "owner_user_id": user.id, "linked_kpi_keys": ["quality"]}],
        kpis=[{"kpi_key": "quality", "kpi_label": "Quality", "unit": "%", "direction": "higher_better", "baseline_value": 60, "target_value": 80, "current_value": 70}],
        actions=[{"title": "Reduce Response Time and review the affected employees with the largest gap", "description": "Run weekly coaching sessions", "owner_user_id": user.id, "due_date": date.today() - timedelta(days=1), "priority": "High", "objective_index": 0, "linked_kpi_key": "quality"}],
        milestones=[{"name": "First review", "due_date": start + timedelta(days=20), "owner_user_id": user.id}], activate=True,
    )
    values.update(changes); return PlanCreate(**values)


def test_create_persists_normalized_plan_and_reuses_action_table(workspace):
    db, user, scope = workspace
    service = PlanningService(StubRepo(), db=db)
    plan = service.create(_payload(user), scope)
    detail = service.get(str(plan.id), scope)

    assert detail["stored_status"] == "In Progress"
    assert detail["progress"]["overall"] == 25.0
    assert detail["counts"] == {"objectives": 1, "actions": 1, "kpis": 1, "milestones": 1, "notes": 0}
    assert detail["actions"][0]["title"] == "Reduce Response Time and review the affected employees with the largest gap"
    assert detail["actions"][0]["action_type"] == "Monitor"
    assert detail["actions"][0]["linked_kpi"] == "quality"
    assert detail["summary"]["current"] == 70.0
    assert detail["objectives"][0]["current"] == 70.0
    assert detail["kpis"][0]["current"] == 70.0
    assert any("overdue" in reason for reason in detail["risk_reasons"])
    assert detail["status"] == "At Risk"


def test_draft_requires_explicit_activation(workspace):
    db, user, scope = workspace
    service = PlanningService(StubRepo(), db=db)
    plan = service.create(_payload(user, activate=False, actions=[], milestones=[]), scope)
    assert service.get(str(plan.id), scope)["status"] == "Draft"


def test_create_uses_baseline_as_first_current_measurement_when_current_is_missing(workspace):
    db, user, scope = workspace
    service = PlanningService(StubRepo(), db=db)
    payload = _payload(user, current_value=None, actions=[], milestones=[])
    payload.objectives[0].current_value = None
    payload.kpis[0].current_value = None

    plan = service.create(payload, scope)
    detail = service.get(str(plan.id), scope)

    assert detail["summary"]["baseline"] == 60.0
    assert detail["summary"]["current"] == 60.0
    assert detail["objectives"][0]["baseline"] == 60.0
    assert detail["objectives"][0]["current"] == 60.0
    assert detail["kpis"][0]["baseline"] == 60.0
    assert detail["kpis"][0]["current"] == 60.0


def test_invalid_objective_kpi_rolls_back_entire_plan(workspace):
    db, user, scope = workspace
    service = PlanningService(StubRepo(), db=db)
    payload = _payload(user, kpis=[])
    with pytest.raises(PlanningValidationError, match="unknown KPI"):
        service.create(payload, scope)
    assert service.plans.list_active() == []


def test_manual_at_risk_and_completion_are_explainable(workspace):
    db, user, scope = workspace
    service = PlanningService(StubRepo(), db=db)
    plan = service.create(_payload(user, activate=False, actions=[], milestones=[]), scope)
    with pytest.raises(PlanningValidationError, match="requires a reason"):
        service.update(str(plan.id), PlanUpdate(status="At Risk"), scope)
    with pytest.raises(PlanningValidationError, match="Completion requires"):
        service.update(str(plan.id), PlanUpdate(status="Completed", completion_note="Done"), scope)


def test_update_validates_owner_and_due_date(workspace):
    db, user, scope = workspace
    service = PlanningService(StubRepo(), db=db)
    plan = service.create(_payload(user, activate=False, actions=[], milestones=[]), scope)
    inactive_owner = User(id=uuid.uuid4(), username="inactive", email="inactive@example.com", password_hash="x", role="Manager", is_active=False)
    db.add(inactive_owner); db.commit()

    with pytest.raises(PlanningValidationError, match="active planning owner"):
        service.update(str(plan.id), PlanUpdate(owner_user_id=inactive_owner.id), scope)
    with pytest.raises(PlanningValidationError, match="before the plan start"):
        service.update(str(plan.id), PlanUpdate(due_date=plan.period_start - timedelta(days=1)), scope)


def test_delete_soft_deletes_plan_and_preserves_audit_history(workspace):
    db, user, scope = workspace
    service = PlanningService(StubRepo(), db=db)
    plan = service.create(_payload(user), scope)

    result = service.delete(str(plan.id), scope)

    assert result == {"id": str(plan.id), "name": plan.name}
    assert db.query(PerformancePlan).filter(PerformancePlan.id == plan.id).one().is_active is False
    assert db.query(AuditLog).filter(AuditLog.record_id == plan.id, AuditLog.operation == "DELETE").count() == 1
    with pytest.raises(PlanningNotFoundError, match="Plan not found"):
        service.get(str(plan.id), scope)


def test_delete_requires_manager_role(workspace):
    _db, user, scope = workspace
    service = PlanningService(StubRepo(), db=_db)
    plan = service.create(_payload(user, activate=False, actions=[], milestones=[]), scope)
    employee_scope = {**scope, "role": "Employee", "employee_id": "unrelated"}

    with pytest.raises(PlanningAccessError):
        service.delete(str(plan.id), employee_scope)
    assert service.get(str(plan.id), scope)["status"] == "Draft"


def test_delete_rolls_back_when_audit_write_fails(workspace, monkeypatch):
    db, user, scope = workspace
    service = PlanningService(StubRepo(), db=db)
    plan = service.create(_payload(user, activate=False, actions=[], milestones=[]), scope)
    monkeypatch.setattr(service, "_audit", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("audit unavailable")))

    with pytest.raises(RuntimeError, match="audit unavailable"):
        service.delete(str(plan.id), scope)

    db.expire_all()
    assert db.query(PerformancePlan).filter(PerformancePlan.id == plan.id).one().is_active is True


def test_milestone_crud_tracks_status_completion_and_progress(workspace):
    db, user, scope = workspace
    service = PlanningService(StubRepo(), db=db)
    plan = service.create(_payload(user, activate=False, actions=[], milestones=[]), scope)

    created = service.add_milestone(
        str(plan.id),
        PlanMilestoneCreate(
            name="Review response-time solution",
            due_date=date.today() + timedelta(days=5),
            owner_user_id=user.id,
            note="Validate the first solution step",
        ),
        scope,
    )
    milestone = created["milestones"][0]
    assert milestone["status"] == "Pending"
    assert milestone["completion_date"] is None
    assert created["counts"]["milestones"] == 1

    completed = service.update_milestone(
        str(plan.id),
        milestone["id"],
        PlanMilestoneUpdate(
            name="Validate response-time solution",
            status="Completed",
            note="Validated with the owner",
        ),
        scope,
    )
    assert completed["milestones"][0]["name"] == "Validate response-time solution"
    assert completed["milestones"][0]["status"] == "Completed"
    assert completed["milestones"][0]["completion_date"] == date.today().isoformat()
    assert completed["progress"]["components"]["milestones"] == 100.0

    reopened = service.update_milestone(
        str(plan.id),
        milestone["id"],
        PlanMilestoneUpdate(status="In Progress"),
        scope,
    )
    assert reopened["milestones"][0]["status"] == "In Progress"
    assert reopened["milestones"][0]["completion_date"] is None

    deleted = service.delete_milestone(str(plan.id), milestone["id"], scope)
    assert deleted["milestones"] == []
    assert deleted["counts"]["milestones"] == 0


def test_milestone_mutations_validate_scope_dates_and_rollback(workspace, monkeypatch):
    db, user, scope = workspace
    service = PlanningService(StubRepo(), db=db)
    plan = service.create(_payload(user, activate=False, actions=[], milestones=[]), scope)
    payload = PlanMilestoneCreate(
        name="Review solution step",
        due_date=date.today() + timedelta(days=5),
        owner_user_id=user.id,
    )

    employee_scope = {**scope, "role": "Employee", "employee_id": "unrelated"}
    with pytest.raises(PlanningAccessError):
        service.add_milestone(str(plan.id), payload, employee_scope)

    invalid_due = payload.model_copy(update={"due_date": plan.due_date + timedelta(days=1)})
    with pytest.raises(PlanningValidationError, match="within the plan"):
        service.add_milestone(str(plan.id), invalid_due, scope)

    monkeypatch.setattr(service, "_audit", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("audit unavailable")))
    with pytest.raises(RuntimeError, match="audit unavailable"):
        service.add_milestone(str(plan.id), payload, scope)

    assert db.query(PlanMilestone).filter(PlanMilestone.plan_id == plan.id).count() == 0
