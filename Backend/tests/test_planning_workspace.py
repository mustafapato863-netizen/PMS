import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import AuditLog, Employee, KPIValue, PerformancePlan, PerformanceRecord, PlanInsightLink, PlanMilestone, Team, User
from models.planning_schemas import PlanCreate, PlanMilestoneCreate, PlanMilestoneUpdate, PlanUpdate
from services.planning_service import PlanningAccessError, PlanningNotFoundError, PlanningService, PlanningValidationError


class StubRepo:
    def get_all(self): return []


def test_risk_reasons_accept_datetime_due_dates_and_skip_blank_ones():
    plan = SimpleNamespace(
        due_date=datetime(2026, 9, 20, tzinfo=timezone.utc),
        status="In Progress",
        actions=[SimpleNamespace(due_date=None, status="Open")],
        milestones=[
            SimpleNamespace(due_date=None, status="Pending"),
            SimpleNamespace(due_date=datetime(2026, 9, 1), status="Pending"),
        ],
        current_value=1,
        baseline_value=2,
        target_value=3,
        outcome_direction="higher_better",
    )

    reasons = PlanningService.risk_reasons(plan, 10, today=date(2026, 9, 27))

    assert "1 milestone(s) overdue" in reasons


def test_regional_manager_plan_listing_uses_explicit_region_attribution():
    service = PlanningService(StubRepo(), db=None)
    team = SimpleNamespace(name="Inbound", display_name="Inbound")
    scope = {
        "role": "Regional Manager",
        "accessible_regions": ["UAE"],
        "accessible_teams": ["Inbound"],
        "legacy_unscoped": False,
    }

    assert service._can_access(SimpleNamespace(region="UAE", team=team), scope)
    assert not service._can_access(SimpleNamespace(region="EGY", team=team), scope)


@pytest.fixture()
def workspace():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    team = Team(id=uuid.uuid4(), name="Marketing", db_name="marketing", display_name="Marketing", region="EGY", team_level="employee", is_active=True)
    user = User(id=uuid.uuid4(), username="manager", email="manager@example.com", password_hash="x", role="Manager", is_active=True)
    db.add_all([team, user]); db.commit()
    scope = {"user_id": str(user.id), "role": "Admin", "has_unrestricted_team_access": True, "legacy_unscoped": False, "accessible_teams": ["Marketing"], "accessible_team_levels": [("Marketing", "Employee")]}
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


def _stored_outcome(plan):
    return (plan.baseline_value, plan.target_value, plan.current_value, plan.status)


def _pin(db, team, employee, month, score, target):
    record = PerformanceRecord(
        id=uuid.uuid4(), year=2026, employee_id=employee.id, team_id=team.id, month=month,
        performance_level="Employee", position_name="Agent", region="EGY", score=score, grade="C", status="Below",
        record_payload={"evaluation_basis": {"pinned": True, "lines": [{"kpi_key": "Attendance", "label": "Attendance", "direction": "higher_better", "unit": "%"}]}},
    )
    db.add(record)
    db.flush()
    db.add(KPIValue(record_id=record.id, record_year=2026, kpi_key="Attendance", actual_value=0.60, target_value=target, achievement_ratio=0.9, weight_applied=0.70, contribution=0.20))
    return record


def _linked_plan(db, user, scope, targets):
    from services.insights_service import InsightsService

    team = db.query(Team).filter(Team.name == "Marketing").one()
    employee = Employee(id=uuid.uuid4(), employee_id=f"MKT-{uuid.uuid4().hex[:8]}", name="Anonymous", team_id=team.id, region="EGY", performance_level="Employee", position_name="Agent")
    db.add(employee)
    db.flush()
    for month, score, target in targets:
        _pin(db, team, employee, month, score, target)
    db.commit()
    service = PlanningService(StubRepo(), db=db)
    workspace = InsightsService(StubRepo(), service, db=db).generate_workspace(scope, month="August", year=2026, team="Marketing", performance_level="Employee")
    noted = next(item for item in workspace.priority_insights if item.detail.basis_note)
    plan = service.create(_payload(user, insight_ids=[noted.id], evidence_month="August", evidence_year=2026, no_insight_reason=None), scope)
    return service, plan, noted


def test_saved_plan_get_keeps_human_values_and_shows_the_linked_basis_note(workspace):
    db, user, scope = workspace
    service, plan, noted = _linked_plan(db, user, scope, [("July", 80, 0.55), ("August", 70, 0.65)])
    stored = db.query(PerformancePlan).filter(PerformancePlan.id == plan.id).one()
    before = _stored_outcome(stored)

    detail = service.get(str(plan.id), scope)
    db.refresh(stored)
    linked = next(item for item in detail["linked_insights"] if item["id"] == noted.id)

    assert _stored_outcome(stored) == before
    assert detail["summary"]["baseline"] == 60.0
    assert detail["summary"]["target"] == 80.0
    assert detail["summary"]["current"] == 70.0
    assert detail["stored_status"] == "In Progress"
    assert linked["resolved"] is True
    assert linked["basis_note"]
    assert "Scores can be affected by evaluation settings." in linked["basis_note"]

    db.add(PlanInsightLink(plan_id=plan.id, insight_id="missing-evidence", evidence_month="August", evidence_year=2026))
    db.commit()
    reread = service.get(str(plan.id), scope)
    missing = next(item for item in reread["linked_insights"] if item["id"] == "missing-evidence")
    db.refresh(stored)

    assert missing == {"id": "missing-evidence", "resolved": False}
    assert reread["summary"]["baseline"] == 60.0
    assert reread["summary"]["target"] == 80.0
    assert reread["summary"]["current"] == 70.0
    assert _stored_outcome(stored) == before


def test_saved_plan_get_stays_readable_when_linked_evidence_is_mixed(workspace):
    db, user, scope = workspace
    team = db.query(Team).filter(Team.name == "Marketing").one()
    other = Employee(id=uuid.uuid4(), employee_id=f"MKT-{uuid.uuid4().hex[:8]}", name="Anonymous two", team_id=team.id, region="EGY", performance_level="Employee", position_name="Agent")
    db.add(other)
    db.flush()
    service, plan, noted = _linked_plan(db, user, scope, [("July", 80, 0.55), ("August", 70, 0.65)])
    _pin(db, team, other, "July", 80, 0.55)
    _pin(db, team, other, "August", 70, 0.90)
    db.commit()
    stored = db.query(PerformancePlan).filter(PerformancePlan.id == plan.id).one()
    before = _stored_outcome(stored)

    detail = service.get(str(plan.id), scope)
    db.refresh(stored)
    linked = next(item for item in detail["linked_insights"] if item["id"] == noted.id)

    assert _stored_outcome(stored) == before
    assert detail["summary"]["current"] == 70.0
    assert linked["resolved"] is True
    assert linked["basis_note"]
    assert "mixed" in linked["basis_note"].casefold()
