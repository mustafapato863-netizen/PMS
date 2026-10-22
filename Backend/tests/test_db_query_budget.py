"""Query-count and response-shape regression tests for the pool-exhaustion fixes.

The follow-up view used to issue several queries per action (period record,
employee team, plan team/employee) and /owners one query per candidate user.
These tests seed a small dataset, count SQL statements with a SQLAlchemy
``before_cursor_execute`` listener and compare the batched responses with the
legacy per-row code path, which is still reachable inside the service.
"""

import datetime as dt
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
    CorrectiveActionService,
    month_match_values,
)

TODAY = dt.date(2026, 9, 27)
TEAMS = ("Inbound", "Outbound", "Retention")
MONTHS = ("July", "August", "September")


@pytest.fixture
def engine():
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
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield session
    session.close()


@contextmanager
def count_queries(engine):
    statements: list[str] = []

    def _listener(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _listener)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _listener)


def seed(db, *, employees_per_team: int = 8, prefix: str = "") -> dict:
    teams = {}
    for name in TEAMS:
        team = Team(id=uuid.uuid4(), name=prefix + name, db_name=(prefix + name).casefold(), region="EGY")
        db.add(team)
        teams[name] = team
    users = []
    for index in range(12):
        role = ("Manager", "Performance Team", "General Manager", "Admin")[index % 4]
        user = User(
            id=uuid.uuid4(),
            full_name=f"{prefix}Owner {index:02d}",
            username=f"{prefix}owner-{index:02d}",
            email=f"{prefix}owner-{index:02d}@example.com",
            password_hash="x",
            role=role,
            is_active=True,
        )
        db.add(user)
        users.append(user)
    db.flush()
    for index, user in enumerate(users):
        db.add(UserTeamAssignment(
            id=uuid.uuid4(), user_id=user.id, team_id=teams[TEAMS[index % 3]].id,
            performance_level="Employee", access_level="write", assigned_by="test",
        ))
    plans = []
    for name, team in teams.items():
        plan = PerformancePlan(
            id=uuid.uuid4(), name=f"{name} plan", scope_type="Team", team_id=team.id,
            performance_level="Employee", period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 12, 31),
            due_date=dt.date(2026, 12, 31), owner_user_id=users[0].id, baseline_value=1, target_value=2,
            outcome_unit="%", outcome_direction="higher_better", status="In Progress", is_active=True,
        )
        db.add(plan)
        plans.append(plan)
    db.flush()
    statuses = ("Open", "In Progress", "Completed", "Cancelled")
    counter = 0
    for team in teams.values():
        for number in range(employees_per_team):
            counter += 1
            employee = Employee(
                id=uuid.uuid4(), employee_id=f"{prefix}SGHD{70000 + counter}", name=f"Employee {counter:03d}",
                team=team, region="EGY", performance_level="Employee",
            )
            db.add(employee)
            db.flush()
            for month_index, month in enumerate(MONTHS):
                # Two uploads for one month: the latest must win.
                for upload in range(2 if month == "September" else 1):
                    db.add(PerformanceRecord(
                        id=uuid.uuid4(), year=2026, employee_id=employee.id, team_id=team.id, month=month,
                        performance_level="Employee", region="EGY", score=60 + month_index * 10 + upload,
                        grade="C" if upload == 0 else "B", status="Meets",
                        uploaded_at=dt.datetime(2026, 7 + month_index, 5 + upload, tzinfo=dt.UTC),
                    ))
                db.add(Action(
                    id=uuid.uuid4(), employee_id=employee.id, team_id=team.id, month=month, year=2026,
                    action_type="Coaching", action_text=f"Action {counter}-{month}",
                    status=statuses[(counter + month_index) % 4], is_active=True,
                    due_date=TODAY + dt.timedelta(days=(counter % 20) - 10),
                    owner_user_id=users[counter % len(users)].id, priority="High",
                    created_by_user_id=users[(counter + 1) % len(users)].id,
                    completed_at=dt.datetime(2026, 9, 2, tzinfo=dt.UTC) if (counter + month_index) % 4 == 2 else None,
                ))
    for plan in plans:
        db.add(Action(
            id=uuid.uuid4(), plan_id=plan.id, team_id=plan.team_id, month="September", year=2026,
            action_type="Training", action_text="Plan action", status="Open", is_active=True,
            due_date=TODAY + dt.timedelta(days=3), owner_user_id=users[1].id,
        ))
    db.commit()
    return {"teams": teams, "users": users}


def _manager_scope(user: User, team_name: str) -> dict:
    return {
        "role": "Manager",
        "user_id": str(user.id),
        "employee_id": "",
        "accessible_teams": [team_name],
        "accessible_team_levels": [(team_name, "Employee")],
        "legacy_unscoped": False,
        "has_unrestricted_team_access": False,
    }


def _admin_scope(user: User) -> dict:
    return {"role": "Admin", "user_id": str(user.id), "has_unrestricted_team_access": True, "legacy_unscoped": False}


def _legacy_follow_up(db, scope: dict, **filters) -> dict:
    """The pre-fix algorithm: plain list_active() and one record lookup per action."""
    service = CorrectiveActionService(db, today=TODAY)
    service._record_cache = None
    return service._list_follow_up_from(service.actions.list_active(), scope, [], set(), **{
        "state": None, "team": None, "owner": None, "month": None, **filters,
    })


def _legacy_owners(db, scope: dict) -> list[dict]:
    service = CorrectiveActionService(db, today=TODAY)
    if scope.get("role") in {"Regional Manager", "Branch Director", "Function Director", "Function Viewer", "Employee"}:
        return []
    users = (
        db.query(User)
        .filter(User.is_active.is_(True), User.role.in_(["Admin", "General Manager", "Manager", "Performance Team"]))
        .order_by(User.full_name.asc(), User.username.asc())
        .all()
    )
    return [
        {"id": str(user.id), "name": service._person_name(user), "role": user.role}
        for user in users
        if service._caller_may_assign(user, scope)
    ]


@pytest.mark.parametrize("filters", [{}, {"month": "September"}, {"month": "september"}, {"state": "overdue"}, {"team": "inbound"}])
@pytest.mark.parametrize("scope_kind", ["admin", "manager"])
def test_follow_up_response_matches_legacy_path(db, filters, scope_kind):
    seeded = seed(db)
    manager = seeded["users"][0]
    scope = _admin_scope(seeded["users"][3]) if scope_kind == "admin" else _manager_scope(manager, "Inbound")

    expected = _legacy_follow_up(db, scope, **filters)
    db.expire_all()
    actual = CorrectiveActionService(db, today=TODAY).list_follow_up(scope, **filters)

    assert actual == expected
    assert actual["actions"], "seed should produce visible follow-up actions"
    assert set(actual) == {"summary", "actions"}


def test_follow_up_query_count_is_constant(engine, db):
    seeded = seed(db, employees_per_team=4)
    scope = _admin_scope(seeded["users"][3])
    db.expire_all()
    with count_queries(engine) as legacy:
        _legacy_follow_up(db, scope)
    db.expire_all()
    with count_queries(engine) as small:
        small_result = CorrectiveActionService(db, today=TODAY).list_follow_up(scope)

    # Grow the dataset; the batched path must not issue more statements.
    seed(db, employees_per_team=12, prefix="X")
    db.expire_all()
    with count_queries(engine) as large:
        large_result = CorrectiveActionService(db, today=TODAY).list_follow_up(scope)

    assert len(large_result["actions"]) > len(small_result["actions"])
    assert len(small) <= 5, small
    assert len(large) == len(small)
    employee_actions = sum(1 for item in small_result["actions"] if item["employee_id"])
    assert len(legacy) > employee_actions  # the per-action lookups it replaces


def test_follow_up_month_filter_does_not_wrap_the_column(engine, db):
    seeded = seed(db, employees_per_team=2)
    scope = _admin_scope(seeded["users"][3])
    db.expire_all()
    with count_queries(engine) as statements:
        result = CorrectiveActionService(db, today=TODAY).list_follow_up(scope, month="SEPTEMBER")
    assert result["actions"] and all(item["month"] == "September" for item in result["actions"])
    joined = "\n".join(statements).lower()
    assert "lower(actions.month)" not in joined
    assert "lower(performance_records.month)" not in joined
    assert "actions.month in" in joined


def test_period_record_lookup_is_sargable(engine, db):
    seed(db, employees_per_team=1)
    action = db.query(Action).filter(Action.employee_id.isnot(None)).first()
    with count_queries(engine) as statements:
        record = CorrectiveActionService(db, today=TODAY)._performance_record_for_action(action)
    assert record is not None
    assert "lower(performance_records.month)" not in "\n".join(statements).lower()


def test_latest_upload_wins_in_batched_lookup(db):
    seeded = seed(db, employees_per_team=1)
    scope = _admin_scope(seeded["users"][3])
    result = CorrectiveActionService(db, today=TODAY).list_follow_up(scope, month="September")
    employee_items = [item for item in result["actions"] if item["employee_id"]]
    assert employee_items and all(item["grade"] == "B" for item in employee_items)


def test_month_match_values_are_precomputed_spellings():
    assert {"September", "september", "SEPTEMBER"} <= set(month_match_values(" sePTember "))


@pytest.mark.parametrize("scope_kind", ["admin", "manager"])
def test_owners_match_legacy_and_use_one_assignment_query(engine, db, scope_kind):
    seeded = seed(db, employees_per_team=1)
    scope = _admin_scope(seeded["users"][3]) if scope_kind == "admin" else _manager_scope(seeded["users"][0], "Inbound")
    expected = _legacy_owners(db, scope)
    db.expire_all()
    with count_queries(engine) as statements:
        actual = CorrectiveActionService(db, today=TODAY).list_owners(scope)
    assert actual == expected
    assert len(statements) <= 2, statements
