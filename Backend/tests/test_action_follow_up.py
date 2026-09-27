"""Follow-up tracking for corrective actions and plan-linked actions."""

import datetime as dt
import uuid
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers.users_and_actions import actions_router
from config.database import get_db
from models.models import (
    Action,
    AuditLog,
    Base,
    Employee,
    PerformancePlan,
    PerformanceRecord,
    PlanMilestone,
    Team,
    User,
    UserTeamAssignment,
)
from services.corrective_action_service import (
    CorrectiveActionAccessError,
    CorrectiveActionService,
    CorrectiveActionValidationError,
)

TODAY = dt.date(2026, 9, 27)
LEGACY_ACTION_KEYS = {
    "id",
    "employee_id",
    "employee_name",
    "team",
    "month",
    "year",
    "score",
    "grade",
    "root_cause",
    "suggested_action",
    "manager_action",
    "manager_notes",
    "timestamp",
    "created_by_name",
    "created_by_role",
    "status",
}


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
            PerformanceRecord.__table__,
            PerformancePlan.__table__,
            PlanMilestone.__table__,
            UserTeamAssignment.__table__,
            Action.__table__,
            AuditLog.__table__,
        ],
    )
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield session
    session.close()


def _user(db, username: str, role: str, *, active: bool = True) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name=username.replace("-", " ").title(),
        username=username,
        email=f"{username}@example.com",
        password_hash="not-a-real-hash",
        role=role,
        is_active=active,
    )
    db.add(user)
    db.commit()
    return user


def _team(db, name: str) -> Team:
    team = Team(id=uuid.uuid4(), name=name, db_name=name.casefold(), region="EGY")
    db.add(team)
    db.commit()
    return team


def _employee(db, team: Team, code: str = "SGHD70001") -> Employee:
    employee = Employee(
        id=uuid.uuid4(),
        employee_id=code,
        name="Test Employee",
        team=team,
        region="EGY",
        performance_level="Employee",
    )
    db.add(employee)
    db.commit()
    return employee


def _assign(db, user: User, team: Team) -> None:
    db.add(
        UserTeamAssignment(
            id=uuid.uuid4(),
            user_id=user.id,
            team_id=team.id,
            performance_level="Employee",
            access_level="write",
            assigned_by="test",
        )
    )
    db.commit()


def _plan(db, team: Team, owner: User, *, name: str = "Inbound recovery") -> PerformancePlan:
    plan = PerformancePlan(
        id=uuid.uuid4(),
        name=name,
        scope_type="Team",
        team_id=team.id,
        performance_level="Employee",
        period_start=dt.date(2026, 9, 1),
        period_end=dt.date(2026, 12, 31),
        due_date=dt.date(2026, 12, 31),
        owner_user_id=owner.id,
        baseline_value=10,
        target_value=20,
        outcome_unit="%",
        outcome_direction="higher_better",
        status="In Progress",
        is_active=True,
    )
    db.add(plan)
    db.commit()
    return plan


def _scope(user: User, team_name: str, role: str | None = None) -> dict:
    chosen = role or user.role
    return {
        "role": chosen,
        "user_id": str(user.id),
        "employee_id": "",
        "accessible_teams": [team_name],
        "accessible_team_levels": [(team_name, "Employee")],
        "legacy_unscoped": False,
        "is_general_manager": chosen == "Admin",
    }


def _service(db) -> CorrectiveActionService:
    return CorrectiveActionService(db, today=TODAY)


def _action(db, **kwargs) -> Action:
    values = {
        "id": uuid.uuid4(),
        "month": "September",
        "year": 2026,
        "action_type": "Coaching",
        "action_text": "Follow the checklist",
        "status": "Open",
        "is_active": True,
    }
    values.update(kwargs)
    action = Action(**values)
    db.add(action)
    db.commit()
    return action


def test_save_without_tracking_fields_keeps_the_legacy_contract(db):
    team = _team(db, "Inbound")
    employee = _employee(db, team)
    saved, is_update = _service(db).save(
        employee_identifier=employee.employee_id,
        month="September",
        year=2026,
        manager_action="Coaching: Review the workflow",
        manager_notes="Booking gap",
    )

    assert is_update is False
    assert LEGACY_ACTION_KEYS <= set(saved)
    assert saved["status"] == "Open"
    assert saved["due_date"] is None
    assert saved["owner"] is None
    assert saved["priority"] is None
    assert saved["linked_kpi_key"] is None
    assert saved["plan"] is None
    assert saved["completion_note"] is None
    assert saved["completed_at"] is None
    assert saved["is_overdue"] is False
    assert saved["days_to_due"] is None
    assert saved["follow_up_state"] == "no_due_date"
    assert saved["manager_action"] == "Coaching: Review the workflow"


def test_save_with_tracking_fields_links_owner_plan_and_due_date(db):
    team = _team(db, "Inbound")
    employee = _employee(db, team)
    manager = _user(db, "inbound-manager", "Manager")
    _assign(db, manager, team)
    plan = _plan(db, team, manager)
    scope = _scope(manager, "Inbound")

    saved, _ = _service(db).save(
        employee_identifier=employee.employee_id,
        month="September",
        year=2026,
        manager_action="Training: Rebuild the booking script",
        scope=scope,
        due_date=dt.date(2026, 9, 29),
        owner_user_id=str(manager.id),
        priority="High",
        linked_kpi_key="Booking Rate",
        plan_id=str(plan.id),
        user_id=str(manager.id),
    )

    assert saved["due_date"] == "2026-09-29"
    assert saved["owner"] == {"id": str(manager.id), "name": "Inbound Manager"}
    assert saved["priority"] == "High"
    assert saved["linked_kpi_key"] == "Booking Rate"
    assert saved["plan"] == {"id": str(plan.id), "name": "Inbound recovery"}
    assert saved["follow_up_state"] == "due_soon"
    assert saved["days_to_due"] == 2
    assert saved["is_overdue"] is False


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"owner_user_id": "pending", "priority": "High"}, "due date is required"),
        ({"priority": "Low"}, "due date is required"),
        ({"due_date": dt.date(2026, 9, 26), "priority": "Medium"}, "cannot be earlier"),
        ({"due_date": dt.date(2026, 9, 29), "priority": "Urgent"}, "Priority must be"),
    ],
)
def test_tracking_field_validation(db, kwargs, message):
    team = _team(db, "Inbound")
    employee = _employee(db, team)
    manager = _user(db, "inbound-manager", "Manager")
    scope = _scope(manager, "Inbound")
    if "owner_user_id" in kwargs:
        kwargs = {**kwargs, "owner_user_id": str(manager.id)}

    with pytest.raises(CorrectiveActionValidationError, match=message):
        _service(db).save(
            employee_identifier=employee.employee_id,
            month="September",
            year=2026,
            manager_action="Coaching: Review the workflow",
            scope=scope,
            **kwargs,
        )


def test_owner_must_be_active_and_able_to_access_the_employee_team(db):
    team = _team(db, "Inbound")
    other = _team(db, "Outbound")
    employee = _employee(db, team)
    admin = _user(db, "admin-user", "Admin")
    inactive = _user(db, "inactive-manager", "Manager", active=False)
    outsider = _user(db, "outbound-manager", "Manager")
    _assign(db, outsider, other)
    scope = _scope(admin, "Inbound")
    common = {
        "employee_identifier": employee.employee_id,
        "month": "September",
        "year": 2026,
        "manager_action": "Monitor: Daily check",
        "scope": scope,
        "due_date": TODAY,
    }

    with pytest.raises(CorrectiveActionValidationError, match="active user"):
        _service(db).save(**common, owner_user_id=str(inactive.id))
    with pytest.raises(CorrectiveActionValidationError, match="active user"):
        _service(db).save(**common, owner_user_id=str(outsider.id))


def test_plan_must_be_accessible_and_on_the_employee_team(db):
    inbound = _team(db, "Inbound")
    outbound = _team(db, "Outbound")
    employee = _employee(db, inbound)
    admin = _user(db, "admin-user", "Admin")
    inbound_manager = _user(db, "inbound-manager", "Manager")
    outbound_plan = _plan(db, outbound, admin, name="Outbound plan")
    inbound_plan = _plan(db, inbound, admin, name="Inbound plan")
    common = {
        "employee_identifier": employee.employee_id,
        "month": "September",
        "year": 2026,
        "manager_action": "Coaching: Review the workflow",
        "due_date": TODAY,
    }

    with pytest.raises(CorrectiveActionValidationError, match="employee's team"):
        _service(db).save(**common, scope=_scope(admin, "Inbound"), plan_id=str(outbound_plan.id))
    with pytest.raises(CorrectiveActionAccessError):
        _service(db).save(**common, scope=_scope(inbound_manager, "Outbound"), plan_id=str(inbound_plan.id))


def test_status_transitions_require_notes_and_maintain_completed_at(db):
    team = _team(db, "Inbound")
    employee = _employee(db, team)
    manager = _user(db, "inbound-manager", "Manager")
    scope = _scope(manager, "Inbound")
    saved, _ = _service(db).save(
        employee_identifier=employee.employee_id,
        month="September",
        year=2026,
        manager_action="Coaching: Review the workflow",
        user_id=str(manager.id),
    )
    service = _service(db)

    progressed = service.update_status(saved["id"], status="In Progress", scope=scope, user_id=str(manager.id))
    assert progressed["status"] == "In Progress"
    assert progressed["completed_at"] is None

    with pytest.raises(CorrectiveActionValidationError, match="completion note"):
        service.update_status(saved["id"], status="Completed", scope=scope, completion_note="ok")
    with pytest.raises(CorrectiveActionValidationError, match="cancellation reason"):
        service.update_status(saved["id"], status="Cancelled", scope=scope, completion_note="")

    before = dt.datetime.now(dt.timezone.utc)
    completed = service.update_status(
        saved["id"],
        status="Completed",
        scope=scope,
        completion_note="Script is now in use",
        user_id=str(manager.id),
    )
    after = dt.datetime.now(dt.timezone.utc)
    completed_at = dt.datetime.fromisoformat(completed["completed_at"])
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=dt.timezone.utc)
    assert before <= completed_at <= after
    assert completed["completion_note"] == "Script is now in use"

    audit = db.query(AuditLog).filter(AuditLog.record_id == uuid.UUID(saved["id"])).all()
    assert any(entry.old_values["status"] == "In Progress" and entry.new_values["status"] == "Completed" for entry in audit)

    cancelled = service.update_status(
        saved["id"],
        status="Cancelled",
        scope=scope,
        completion_note="Superseded by a new plan",
        user_id=str(manager.id),
    )
    assert cancelled["status"] == "Cancelled"
    assert cancelled["completed_at"] == completed["completed_at"]

    reopened = service.update_status(saved["id"], status="Open", scope=scope, user_id=str(manager.id))
    assert reopened["status"] == "Open"
    assert reopened["completed_at"] is None
    assert db.query(Action).one().completed_at is None


def test_status_permissions_allow_admin_scoped_manager_and_owner_only(db):
    team = _team(db, "Inbound")
    employee = _employee(db, team)
    admin = _user(db, "admin-user", "Admin")
    manager = _user(db, "inbound-manager", "Manager")
    outsider = _user(db, "outbound-manager", "Manager")
    owner = _user(db, "action-owner", "Manager")
    executive = _user(db, "executive-user", "Executive")
    _assign(db, owner, team)
    _assign(db, executive, team)
    saved, _ = _service(db).save(
        employee_identifier=employee.employee_id,
        month="September",
        year=2026,
        manager_action="Monitor: Daily check",
        scope=_scope(admin, "Inbound"),
        due_date=TODAY,
        owner_user_id=str(owner.id),
        user_id=str(admin.id),
    )
    service = _service(db)

    for blocked in (
        _scope(executive, "Inbound", role="Executive"),
        _scope(outsider, "Inbound", role="Viewer"),
        _scope(outsider, "Outbound"),
    ):
        with pytest.raises(CorrectiveActionAccessError):
            service.update_status(saved["id"], status="In Progress", scope=blocked, user_id=blocked["user_id"])

    assert service.update_status(saved["id"], status="In Progress", scope=_scope(manager, "Inbound"), user_id=str(manager.id))["status"] == "In Progress"
    assert service.update_status(saved["id"], status="Open", scope=_scope(owner, "Outbound"), user_id=str(owner.id))["status"] == "Open"
    owned_by_executive, _ = _service(db).save(
        employee_identifier=employee.employee_id,
        month="October",
        year=2026,
        manager_action="Coaching: Second action",
        scope=_scope(admin, "Inbound"),
        due_date=TODAY,
        owner_user_id=str(executive.id),
        user_id=str(admin.id),
    )
    with pytest.raises(CorrectiveActionAccessError):
        service.update_status(
            owned_by_executive["id"],
            status="In Progress",
            scope=_scope(executive, "Inbound", role="Executive"),
            user_id=str(executive.id),
        )


def test_follow_up_state_uses_the_fixed_today(db):
    team = _team(db, "Inbound")
    employee = _employee(db, team)
    overdue = _action(db, employee_id=employee.id, team_id=team.id, due_date=dt.date(2026, 9, 22), action_text="Overdue item")
    soon = _action(db, employee_id=employee.id, team_id=team.id, due_date=dt.date(2026, 9, 29), action_text="Soon item")
    later = _action(db, employee_id=employee.id, team_id=team.id, due_date=dt.date(2026, 10, 20), action_text="Later item")
    service = _service(db)

    overdue_row = service.serialize(overdue)
    soon_row = service.serialize(soon)
    later_row = service.serialize(later)
    assert (overdue_row["follow_up_state"], overdue_row["days_to_due"], overdue_row["is_overdue"]) == ("overdue", -5, True)
    assert (soon_row["follow_up_state"], soon_row["days_to_due"], soon_row["is_overdue"]) == ("due_soon", 2, False)
    assert (later_row["follow_up_state"], later_row["days_to_due"], later_row["is_overdue"]) == ("upcoming", 23, False)


def test_follow_up_orders_tracked_actions_and_summarizes_before_the_state_filter(db):
    inbound = _team(db, "Inbound")
    outbound = _team(db, "Outbound")
    employee = _employee(db, inbound)
    other_employee = _employee(db, outbound, "SGHD70002")
    manager = _user(db, "inbound-manager", "Manager")
    plan = _plan(db, inbound, manager)
    _action(db, employee_id=employee.id, team_id=inbound.id, due_date=dt.date(2026, 9, 22), action_text="Near overdue")
    _action(db, employee_id=employee.id, team_id=inbound.id, due_date=dt.date(2026, 9, 1), action_text="Far overdue")
    _action(db, employee_id=employee.id, team_id=inbound.id, due_date=dt.date(2026, 9, 29), action_text="Due soon")
    _action(
        db,
        employee_id=employee.id,
        team_id=inbound.id,
        due_date=dt.date(2026, 10, 20),
        status="In Progress",
        action_text="Upcoming",
    )
    _action(db, employee_id=None, team_id=inbound.id, plan_id=plan.id, due_date=None, action_text="Plan only")
    _action(
        db,
        employee_id=employee.id,
        team_id=inbound.id,
        due_date=dt.date(2026, 9, 15),
        status="Completed",
        completed_at=dt.datetime(2026, 9, 10, tzinfo=dt.timezone.utc),
        completion_note="Done",
        action_text="Completed",
    )
    _action(
        db,
        employee_id=employee.id,
        team_id=inbound.id,
        due_date=dt.date(2026, 8, 1),
        status="Cancelled",
        month="August",
        completion_note="Dropped",
        action_text="Cancelled",
    )
    _action(db, employee_id=employee.id, team_id=inbound.id, due_date=None, action_text="Untracked")
    _action(db, employee_id=other_employee.id, team_id=outbound.id, due_date=TODAY, action_text="Other team")

    result = _service(db).list_follow_up(_scope(manager, "Inbound"))
    assert [item["manager_action"].split(": ", 1)[1] for item in result["actions"]] == [
        "Far overdue",
        "Near overdue",
        "Due soon",
        "Upcoming",
        "Plan only",
        "Completed",
        "Cancelled",
    ]
    assert result["summary"] == {
        "overdue": 2,
        "due_soon": 1,
        "open": 4,
        "in_progress": 1,
        "completed_this_month": 1,
        "completion_rate": 16.7,
    }

    overdue_only = _service(db).list_follow_up(_scope(manager, "Inbound"), state="overdue")
    assert [item["manager_action"].split(": ", 1)[1] for item in overdue_only["actions"]] == ["Far overdue", "Near overdue"]
    assert overdue_only["summary"] == result["summary"]
    august = _service(db).list_follow_up(_scope(manager, "Inbound"), month="August")
    assert [item["manager_action"].split(": ", 1)[1] for item in august["actions"]] == ["Cancelled"]
    assert august["summary"]["open"] == 0


def test_legacy_collection_route_keeps_every_previous_key(db):
    team = _team(db, "Inbound")
    employee = _employee(db, team)
    _service(db).save(
        employee_identifier=employee.employee_id,
        month="September",
        year=2026,
        manager_action="Coaching: Review the workflow",
    )
    app = FastAPI()
    app.include_router(actions_router, prefix="/api/corrective-actions")

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    scope = _scope(_user(db, "admin-user", "Admin"), "Inbound")
    with patch("api.routers.users_and_actions.get_current_user_scope", return_value=scope):
        response = client.get("/api/corrective-actions/", headers={"X-User-Role": "Admin"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert LEGACY_ACTION_KEYS <= set(body["data"][0])
    assert body["data"][0]["manager_action"] == "Coaching: Review the workflow"


def test_status_route_rejects_executive_viewers(db):
    team = _team(db, "Inbound")
    employee = _employee(db, team)
    saved, _ = _service(db).save(
        employee_identifier=employee.employee_id,
        month="September",
        year=2026,
        manager_action="Coaching: Review the workflow",
    )
    app = FastAPI()
    app.include_router(actions_router, prefix="/api/corrective-actions")

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    response = client.patch(
        f"/api/corrective-actions/{saved['id']}/status",
        json={"status": "In Progress"},
        headers={"X-User-Role": "Executive"},
    )
    assert response.status_code == 403
