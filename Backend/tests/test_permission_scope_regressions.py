"""Isolated audit probes: no network and no production database writes."""
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.middleware.auth_middleware import AuthMiddleware
from api.routers import employee, performance, auth
from api.routers.users_and_actions import users_router
from config.database import get_db
from models.models import (Base, Team, Employee, UserTeamAssignment,
                           UserFunctionAssignment, UserBranchAssignment, UserRegionAssignment)
from models.models import PerformanceRecord as SQLPerformanceRecord
from models.schemas import PerformanceRecord, EvaluationData
from services.auth_service import AuthenticationService
from services.permission_seed import seed_role_permissions

SCOPED_ROLES = ["Employee", "Manager", "Function Director", "Branch Director", "Regional Manager"]
ALL_ROLES = ["Admin", "Performance Team", *SCOPED_ROLES]


@pytest.fixture
def audit_context():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    seed_role_permissions(db)
    coding = Team(id=uuid4(), name="Coding", db_name="coding", region="UAE", team_level="employee")
    marketing = Team(id=uuid4(), name="Marketing", db_name="marketing", region="EGY", team_level="employee")
    db.add_all([coding, marketing])
    db.flush()
    db.add_all([
        Employee(employee_id="AUDIT-SELF", name="Audit Self", team_id=coding.id, region="UAE", performance_level="Employee"),
        Employee(employee_id="AUDIT-OUT", name="Audit Outsider", team_id=marketing.id, region="EGY", performance_level="Employee"),
    ])
    db.commit()
    for identifier, branch in (("AUDIT-SELF", "dubai"), ("AUDIT-OUT", "sharjah")):
        person = db.query(Employee).filter_by(employee_id=identifier).one()
        db.add(SQLPerformanceRecord(id=uuid4(), employee_id=person.id, team_id=person.team_id,
                                   year=2026, month="August", region=person.region, branch_key=branch,
                                   performance_level="Employee", score=85, grade="C", status="Below"))
    db.commit()
    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    app.include_router(employee.router, prefix="/api/employees")
    app.include_router(performance.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    from api.routers import search
    app.include_router(search.router, prefix="/api")
    app.include_router(users_router, prefix="/api/users")
    client = TestClient(app)
    def authorize(role):
        user = AuthenticationService.create_user(db, "audit", "audit@example.invalid", "AuditOnlyPassword123!", role)
        user.employee_id = "AUDIT-SELF"
        if role == "Manager":
            db.add(UserTeamAssignment(user_id=user.id, team_id=coding.id, performance_level="Employee", assigned_by="Audit"))
        elif role == "Function Director":
            db.add(UserFunctionAssignment(user_id=user.id, function_name="RCM", assigned_by="Audit"))
        elif role == "Branch Director":
            db.add(UserBranchAssignment(user_id=user.id, branch_key="dubai", assigned_by="Audit"))
        elif role == "Regional Manager":
            db.add(UserRegionAssignment(user_id=user.id, region_code="UAE", assigned_by="Audit"))
        db.commit()
        token = AuthenticationService.authenticate_user(db, "audit", "AuditOnlyPassword123!")
        return {"Authorization": f"Bearer {token}"}
    yield client, authorize
    client.close()
    db.close()
    engine.dispose()


@pytest.mark.parametrize("role", ALL_ROLES)
def test_current_user_context(audit_context, role):
    client, authorize = audit_context
    response = client.get("/api/auth/me", headers=authorize(role))
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["role"] == role


@pytest.mark.parametrize("role", SCOPED_ROLES)
@pytest.mark.parametrize("path", ["/api/employees", "/api/employees/search?name=Outsider", "/api/employees/team/Marketing", "/api/employees/team/Marketing/active"])
def test_directory_excludes_outside_identity(audit_context, role, path):
    client, authorize = audit_context
    response = client.get(path, headers=authorize(role))
    assert response.status_code in {200, 403}
    if response.status_code == 200:
        assert response.json()["success"] is True
        ids = {row["employee_id"] for row in response.json()["data"]}
        assert "AUDIT-OUT" not in ids, f"{role}: out-of-scope identity returned by {path}"


def test_manager_cannot_create_in_unassigned_team(audit_context):
    client, authorize = audit_context
    response = client.post("/api/employees", headers=authorize("Manager"), params={"employee_id": "AUDIT-NEW", "name": "Audit New", "team": "Marketing", "region": "EGY"})
    assert response.status_code == 403, f"status={response.status_code}, success={response.json().get('success')}"


def test_manager_cannot_move_to_unassigned_team(audit_context):
    client, authorize = audit_context
    response = client.put("/api/employees/AUDIT-SELF", headers=authorize("Manager"), params={"team": "Marketing"})
    assert response.status_code == 403, f"status={response.status_code}, success={response.json().get('success')}"


@pytest.mark.parametrize("level", ["Managerial", "Corporate"])
@pytest.mark.parametrize("path", [
    "/api/performance?team=Coding",
    "/api/performance/records?month=August&team=Coding",
    "/api/performance/team/Coding?month=August",
    "/api/performance/grade/Coding?grade=A&month=August",
    "/api/performance/status/Coding?status=Exceeds&month=August",
    "/api/performance/employee/AUDIT-SELF?month=August",
])
def test_manager_employee_level_cannot_read_corporate(audit_context, monkeypatch, level, path):
    client, authorize = audit_context
    monkeypatch.setattr(performance.settings, "PMS_SCOPED_PERFORMANCE_API_ENABLED", False)
    db = next(client.app.dependency_overrides[get_db]())
    person = db.query(Employee).filter_by(employee_id="AUDIT-SELF").one()
    db.add(SQLPerformanceRecord(id=uuid4(), employee_id=person.id, team_id=person.team_id, year=2026, month="August", region="UAE", performance_level=level, score=97, grade="A", status="Exceeds"))
    db.commit()
    response = client.get(f"{path}&performance_level={level}", headers=authorize("Manager"))
    assert response.status_code in {200, 403}
    if response.status_code == 200:
        assert response.json()["success"] is True
        assert response.json()["data"] == [], "Employee-only Manager received Corporate performance"


@pytest.mark.parametrize("role", ALL_ROLES)
def test_directory_keeps_authorized_identity(audit_context, role):
    client, authorize = audit_context
    response = client.get("/api/employees", headers=authorize(role))
    assert response.status_code == 200 and response.json()["success"] is True
    ids = {row["employee_id"] for row in response.json()["data"]}
    assert "AUDIT-SELF" in ids
    assert ("AUDIT-OUT" in ids) == (role in {"Admin", "Performance Team"})


@pytest.mark.parametrize("role,model", [
    ("Manager", UserTeamAssignment), ("Function Director", UserFunctionAssignment),
    ("Branch Director", UserBranchAssignment), ("Regional Manager", UserRegionAssignment),
])
def test_directory_revocation_applies_to_existing_token(audit_context, role, model):
    client, authorize = audit_context
    headers = authorize(role)
    assert client.get("/api/employees", headers=headers).json()["data"]
    db = next(client.app.dependency_overrides[get_db]())
    db.query(model).delete()
    db.commit()
    assert client.get("/api/employees", headers=headers).json()["data"] == []


def test_branch_directory_projects_own_record_not_latest_other_branch(audit_context):
    client, authorize = audit_context
    headers = authorize("Branch Director")
    db = next(client.app.dependency_overrides[get_db]())
    person = db.query(Employee).filter_by(employee_id="AUDIT-SELF").one()
    outside = db.query(Team).filter_by(name="Marketing").one()
    person.team_id = outside.id
    person.region = "EGY"
    person.position_name = "Other branch position"
    person.performance_level = "Corporate"
    db.add(SQLPerformanceRecord(id=uuid4(), employee_id=person.id, team_id=outside.id, year=2026,
                               month="September", region="EGY", branch_key="sharjah", performance_level="Corporate",
                               position_name="Other branch position", score=97, grade="A", status="Exceeds"))
    db.commit()
    response = client.get("/api/employees", headers=headers)
    assert response.json()["data"] == [{"id": "AUDIT-SELF", "employee_id": "AUDIT-SELF", "name": "Audit Self",
        "team": "Coding", "region": "UAE", "performance_level": "Employee", "position": None, "status": "Active"}]


def test_branch_directory_excludes_unattributed_records(audit_context):
    client, authorize = audit_context
    headers = authorize("Branch Director")
    db = next(client.app.dependency_overrides[get_db]())
    db.query(SQLPerformanceRecord).update({SQLPerformanceRecord.branch_key: None})
    db.commit()
    assert client.get("/api/employees", headers=headers).json()["data"] == []


def test_manager_valid_writes_and_denied_destination_are_atomic(audit_context):
    client, authorize = audit_context
    headers = authorize("Manager")
    created = client.post("/api/employees", headers=headers, params={"employee_id": "AUDIT-NEW", "name": "Allowed New", "team": "Coding"})
    assert created.status_code == 201 and created.json()["success"] is True
    changed = client.put("/api/employees/AUDIT-SELF", headers=headers, params={"name": "Allowed Name"})
    assert changed.status_code == 200 and changed.json()["success"] is True
    denied = client.put("/api/employees/AUDIT-SELF", headers=headers, params={"name": "Denied Name", "team": "Marketing"})
    assert denied.status_code == 403
    db = next(client.app.dependency_overrides[get_db]())
    person = db.query(Employee).filter_by(employee_id="AUDIT-SELF").one()
    assert person.name == "Allowed Name" and person.team.name == "Coding"


def test_manager_level_scope_applies_to_directory_and_mutations(audit_context):
    client, authorize = audit_context
    headers = authorize("Manager")
    db = next(client.app.dependency_overrides[get_db]())
    person = db.query(Employee).filter_by(employee_id="AUDIT-SELF").one()
    person.performance_level = "Corporate"
    db.commit()
    assert client.get("/api/employees", headers=headers).json()["data"] == []
    assert client.put("/api/employees/AUDIT-SELF", headers=headers, params={"name": "Denied Name"}).status_code == 403
    db.refresh(person)
    assert person.name == "Audit Self"


@pytest.mark.parametrize("role", ALL_ROLES)
def test_global_search_uses_same_directory_scope(audit_context, role):
    client, authorize = audit_context
    response = client.get("/api/search/global?q=Audit", headers=authorize(role))
    assert response.status_code == 200 and response.json()["success"] is True
    ids = {row["employee_id"] for row in response.json()["data"]["employees"]}
    assert "AUDIT-SELF" in ids
    assert ("AUDIT-OUT" in ids) == (role in {"Admin", "Performance Team"})


@pytest.mark.parametrize("function", ["Sales", "CSR", "Pharmacy"])
def test_standalone_function_grant_isolated_and_revocable(audit_context, function):
    client, authorize = audit_context
    headers = authorize("Function Director")
    db = next(client.app.dependency_overrides[get_db]())
    grant = db.query(UserFunctionAssignment).one()
    grant.function_name = function
    team = Team(name=function, db_name=function.lower(), region="EGY", team_level="employee")
    db.add(team)
    db.flush()
    db.add(Employee(employee_id="AUDIT-FUNCTION", name="Audit Function", team_id=team.id, region="EGY", performance_level="Employee"))
    db.commit()
    response = client.get("/api/employees", headers=headers)
    assert [row["employee_id"] for row in response.json()["data"]] == ["AUDIT-FUNCTION"]
    me = client.get("/api/auth/me", headers=headers)
    assert me.json()["data"]["accessible_functions"] == [function]
    assert client.get("/api/performance/team/Coding", headers=headers).status_code == 403
    db.delete(grant)
    db.commit()
    assert client.get("/api/employees", headers=headers).json()["data"] == []


@pytest.mark.parametrize("role", ["Performance Team", *SCOPED_ROLES])
def test_non_admin_cannot_list_users(audit_context, role):
    client, authorize = audit_context
    assert client.get("/api/users/", headers=authorize(role)).status_code == 403


@pytest.mark.parametrize("role", SCOPED_ROLES)
def test_legacy_performance_does_not_leak_other_scope(audit_context, monkeypatch, role):
    client, authorize = audit_context
    rows = [
        PerformanceRecord(id="AUDIT-SELF", employee_id="AUDIT-SELF", employee_name="Audit Self", team="Coding", month="August", year=2026, region="UAE", branch_key="dubai", evaluation=EvaluationData(score=85, grade="C")),
        PerformanceRecord(id="AUDIT-OUT", employee_id="AUDIT-OUT", employee_name="Audit Outsider", team="Marketing", month="August", year=2026, region="EGY", branch_key="sharjah", evaluation=EvaluationData(score=95, grade="A")),
    ]
    monkeypatch.setattr(performance, "_get_dashboard_records", lambda *a, **kw: rows)
    response = client.get("/api/performance", headers=authorize(role))
    assert response.status_code == 200 and response.json()["success"] is True
    assert [row["employee_id"] for row in response.json()["data"]] == ["AUDIT-SELF"]
