import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from api.middleware.auth_middleware import AuthMiddleware
from api.dependencies import get_current_user_scope
from api.routers.users_and_actions import users_router
from config.database import get_db
from models.models import (
    Base,
    Employee,
    RefreshSession,
    RolePermission,
    Team,
    User,
    UserBranchAssignment,
    UserFunctionAssignment,
    UserRegionAssignment,
    UserTeamAssignment,
)
from services.auth_service import AuthenticationService
from services.permission_seed import seed_role_permissions
from services.password_service import verify_password


@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Team.__table__,
            Employee.__table__,
            User.__table__,
            UserTeamAssignment.__table__,
            UserFunctionAssignment.__table__,
            UserRegionAssignment.__table__,
            UserBranchAssignment.__table__,
            RolePermission.__table__,
            RefreshSession.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    seed_role_permissions(session)
    yield session
    session.close()


@pytest.fixture(scope="function")
def test_client(db_session):
    test_app = FastAPI()
    test_app.add_middleware(AuthMiddleware)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.include_router(users_router, prefix="/api/users")
    return TestClient(test_app)


def _auth_headers(db_session, username: str, password: str):
    AuthenticationService.create_user(db_session, username, f"{username}@test.com", password, "Admin")
    token = AuthenticationService.authenticate_user(db_session, username, password)
    return {"Authorization": f"Bearer {token}"}


def test_viewer_cannot_manage_users(test_client, db_session):
    AuthenticationService.create_user(db_session, "viewer_user", "viewer@test.com", "SecurePassword123!", "Viewer")
    token = AuthenticationService.authenticate_user(db_session, "viewer_user", "SecurePassword123!")

    response = test_client.post(
        "/api/users/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "id": str(uuid.uuid4()),
            "name": "New User",
            "username": "newuser",
            "password": "SecurePassword123!",
            "role": "Viewer",
            "is_active": True,
        },
    )

    assert response.status_code == 403
    assert "manage_users" in response.json()["detail"]


def test_admin_create_user_persists_to_db(test_client, db_session):
    headers = _auth_headers(db_session, "admin_user", "SecurePassword123!")

    response = test_client.post(
        "/api/users/",
        headers=headers,
        json={
            "id": "ignored-by-db",
            "name": "New User",
            "username": "newuser",
            "password": "SecurePassword123!",
            "role": "Performance Team",
            "is_active": True,
        },
    )

    assert response.status_code == 200
    created = db_session.query(User).filter(User.username == "newuser").first()
    assert created is not None
    assert created.email == "newuser@pms.local"
    assert created.full_name == "New User"
    assert created.employee_id is None
    assert response.json()["data"]["name"] == "New User"
    assert response.json()["data"]["is_online"] is False
    assert response.json()["data"]["last_seen_at"] is None


def test_user_list_reports_online_offline_and_never_seen_from_activity_timestamp(test_client, db_session):
    headers = _auth_headers(db_session, "presence_admin", "SecurePassword123!")
    now = datetime.now(timezone.utc)
    recently_active = AuthenticationService.create_user(
        db_session, "recent_user", "recent@test.com", "SecurePassword123!", "Viewer"
    )
    stale_user = AuthenticationService.create_user(
        db_session, "stale_user", "stale@test.com", "SecurePassword123!", "Viewer"
    )
    never_seen = AuthenticationService.create_user(
        db_session, "never_user", "never@test.com", "SecurePassword123!", "Viewer"
    )
    recently_active.last_seen_at = now - timedelta(seconds=90)
    stale_user.last_seen_at = now - timedelta(days=22)
    db_session.commit()

    response = test_client.get("/api/users/", headers=headers)

    assert response.status_code == 200
    users = {entry["username"]: entry for entry in response.json()["data"]}
    assert users["recent_user"]["is_online"] is True
    assert users["stale_user"]["is_online"] is False
    assert users["stale_user"]["last_seen_at"] is not None
    assert users["never_user"]["is_online"] is False
    assert users["never_user"]["last_seen_at"] is None


def test_admin_can_update_full_name_without_changing_username(test_client, db_session):
    headers = _auth_headers(db_session, "admin_editor", "SecurePassword123!")
    user = AuthenticationService.create_user(
        db_session,
        "dr_ahmed_essa",
        "dr_ahmed_essa@test.com",
        "SecurePassword123!",
        "Manager",
    )

    response = test_client.put(
        f"/api/users/{user.id}",
        headers=headers,
        json={
            "id": str(user.id),
            "name": "Dr. Ahmed Mohamed Essa",
            "username": "dr_ahmed_essa",
            "role": "Manager",
            "is_active": True,
        },
    )

    assert response.status_code == 200
    db_session.refresh(user)
    assert user.full_name == "Dr. Ahmed Mohamed Essa"
    assert user.username == "dr_ahmed_essa"
    assert response.json()["data"]["name"] == "Dr. Ahmed Mohamed Essa"


def test_admin_password_update_replaces_old_password_and_allows_new_login(test_client, db_session):
    headers = _auth_headers(db_session, "admin_password_editor", "SecurePassword123!")
    user = AuthenticationService.create_user(
        db_session,
        "password_target",
        "password_target@test.com",
        "OldPassword123!",
        "Viewer",
    )

    response = test_client.put(
        f"/api/users/{user.id}",
        headers=headers,
        json={
            "id": str(user.id),
            "name": "Password Target",
            "username": "password_target",
            "role": "Viewer",
            "is_active": True,
            "new_password": "NewPassword456!",
        },
    )

    assert response.status_code == 200
    db_session.refresh(user)
    assert verify_password("OldPassword123!", user.password_hash) is False
    assert verify_password("NewPassword456!", user.password_hash) is True
    assert AuthenticationService.authenticate_user(
        db_session,
        "password_target",
        "NewPassword456!",
    )
    with pytest.raises(ValueError, match="Invalid username or password"):
        AuthenticationService.authenticate_user(
            db_session,
            "password_target",
            "OldPassword123!",
        )


def test_admin_password_update_clears_existing_lockout(test_client, db_session):
    headers = _auth_headers(db_session, "admin_lockout_editor", "SecurePassword123!")
    user = AuthenticationService.create_user(
        db_session,
        "locked_password_target",
        "locked_password_target@test.com",
        "OldPassword123!",
        "Viewer",
    )
    user.failed_login_attempts = 5
    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
    db_session.commit()

    response = test_client.put(
        f"/api/users/{user.id}",
        headers=headers,
        json={
            "id": str(user.id),
            "name": "Locked Password Target",
            "username": "locked_password_target",
            "role": "Viewer",
            "is_active": True,
            "new_password": "NewPassword456!",
        },
    )

    assert response.status_code == 200
    db_session.refresh(user)
    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    assert AuthenticationService.authenticate_user(
        db_session,
        "locked_password_target",
        "NewPassword456!",
    )


def test_admin_can_delete_user_and_revoke_related_sessions(test_client, db_session):
    headers = _auth_headers(db_session, "admin_delete_editor", "SecurePassword123!")
    user = AuthenticationService.create_user(
        db_session,
        "delete_target",
        "delete_target@test.com",
        "SecurePassword123!",
        "Viewer",
    )
    AuthenticationService.authenticate_user_with_session(
        db_session,
        "delete_target",
        "SecurePassword123!",
    )
    assert db_session.query(RefreshSession).filter(RefreshSession.user_id == user.id).count() == 1

    response = test_client.delete(f"/api/users/{user.id}", headers=headers)

    assert response.status_code == 200
    assert db_session.query(User).filter(User.id == user.id).first() is None
    sessions = db_session.query(RefreshSession).filter(RefreshSession.user_id == user.id).all()
    assert len(sessions) == 1
    assert sessions[0].revoked_at is not None
    assert sessions[0].revocation_reason == "user_deleted"


def test_delete_user_rejects_invalid_id_without_corrupting_session(test_client, db_session):
    headers = _auth_headers(db_session, "admin_invalid_delete", "SecurePassword123!")

    response = test_client.delete("/api/users/not-a-uuid", headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid user ID"
    assert db_session.query(User).filter(User.username == "admin_invalid_delete").one()


def test_admin_cannot_delete_self(test_client, db_session):
    headers = _auth_headers(db_session, "admin_user", "SecurePassword123!")
    admin = db_session.query(User).filter(User.username == "admin_user").first()

    response = test_client.delete(f"/api/users/{admin.id}", headers=headers)
    print("DEBUG DELETE SELF RESPONSE:", response.json())
    assert response.status_code == 400
    assert "own account" in response.json()["detail"]


def test_admin_cannot_deactivate_self(test_client, db_session):
    headers = _auth_headers(db_session, "admin_two", "SecurePassword123!")
    admin = db_session.query(User).filter(User.username == "admin_two").first()

    response = test_client.post(
        f"/api/users/{admin.id}/toggle-active",
        params={"is_active": False},
        headers=headers,
    )
    print("DEBUG DEACTIVATE SELF RESPONSE:", response.json())
    assert response.status_code == 400
    assert "own account" in response.json()["detail"]


def test_admin_create_function_director_with_selected_functions(test_client, db_session):
    headers = _auth_headers(db_session, "function_admin", "SecurePassword123!")

    response = test_client.post(
        "/api/users/",
        headers=headers,
        json={
            "id": "function-viewer",
            "name": "Function Director",
            "username": "function_director",
            "password": "SecurePassword123!",
            "role": "Function Director",
            "accessible_functions": [" rcm ", "Marketing", "RCM"],
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["accessible_functions"] == ["RCM", "Marketing"]
    created = db_session.query(User).filter(User.username == "function_director").first()
    assert created is not None
    assert {
        assignment.function_name for assignment in created.function_assignments
    } == {"RCM", "Marketing"}


@pytest.mark.parametrize(
    ("role", "assignment_field", "assignment_values", "response_field", "model"),
    [
        ("Regional Manager", "accessible_regions", ["uae", "EGY"], "accessible_regions", UserRegionAssignment),
        ("Branch Director", "accessible_branches", ["Dubai", "Sharjah"], "accessible_branches", UserBranchAssignment),
    ],
)
def test_admin_create_scoped_director_persists_explicit_assignments(
    test_client, db_session, role, assignment_field, assignment_values, response_field, model,
):
    headers = _auth_headers(db_session, f"{role.lower().replace(' ', '_')}_admin", "SecurePassword123!")
    response = test_client.post(
        "/api/users/",
        headers=headers,
        json={
            "id": "scoped-director",
            "name": "Scoped Director",
            "username": "scoped_director",
            "password": "SecurePassword123!",
            "role": role,
            assignment_field: assignment_values,
        },
    )

    assert response.status_code == 200
    assignments = response.json()["data"][response_field]
    expected = ["UAE", "EGY"] if role == "Regional Manager" else ["dubai", "sharjah"]
    assert set(assignments) == set(expected)
    created = db_session.query(User).filter(User.username == "scoped_director").one()
    persisted = db_session.query(model).filter(model.user_id == created.id).all()
    persisted_values = [row.region_code if role == "Regional Manager" else row.branch_key for row in persisted]
    assert set(persisted_values) == set(expected)


@pytest.mark.parametrize(
    ("role", "assignment_field"),
    [("Regional Manager", "accessible_regions"), ("Branch Director", "accessible_branches")],
)
def test_admin_cannot_create_scoped_director_without_assignment(test_client, db_session, role, assignment_field):
    headers = _auth_headers(db_session, f"missing_{role.lower().replace(' ', '_')}", "SecurePassword123!")
    response = test_client.post(
        "/api/users/",
        headers=headers,
        json={
            "id": "missing-scope",
            "name": "Missing Scope",
            "username": "missing_scope",
            "password": "SecurePassword123!",
            "role": role,
            assignment_field: [],
        },
    )

    assert response.status_code == 422
    assert db_session.query(User).filter(User.username == "missing_scope").count() == 0


def test_admin_function_permissions_are_replaced_and_cleared_on_role_change(test_client, db_session):
    headers = _auth_headers(db_session, "function_editor", "SecurePassword123!")
    user = AuthenticationService.create_user(
        db_session,
        "function_target",
        "function_target@test.com",
        "SecurePassword123!",
        "Function Viewer",
    )
    db_session.add(UserFunctionAssignment(user_id=user.id, function_name="RCM", assigned_by="Admin"))
    db_session.commit()

    updated = test_client.put(
        f"/api/users/{user.id}",
        headers=headers,
        json={
            "id": str(user.id),
            "name": "Function Target",
            "username": "function_target",
            "role": "Function Director",
            "is_active": True,
            "accessible_functions": ["Pre-Approvals"],
        },
    )

    assert updated.status_code == 200
    assert updated.json()["data"]["accessible_functions"] == ["Pre-Approvals"]

    demoted = test_client.put(
        f"/api/users/{user.id}",
        headers=headers,
        json={
            "id": str(user.id),
            "name": "Function Target",
            "username": "function_target",
            "role": "Manager",
            "is_active": True,
            "accessible_teams": [],
        },
    )

    assert demoted.status_code == 200
    assert demoted.json()["data"]["accessible_functions"] == []
    assert db_session.query(UserFunctionAssignment).filter(
        UserFunctionAssignment.user_id == user.id
    ).count() == 0


def test_admin_cannot_create_legacy_function_viewer_or_assign_unknown_function(test_client, db_session):
    headers = _auth_headers(db_session, "invalid_function_admin", "SecurePassword123!")

    response = test_client.post(
        "/api/users/",
        headers=headers,
        json={
            "id": "bad-function",
            "name": "Bad Function",
            "username": "bad_function",
            "password": "SecurePassword123!",
            "role": "Function Viewer",
            "accessible_functions": ["Finance"],
        },
    )

    assert response.status_code == 422
    assert db_session.query(User).filter(User.username == "bad_function").first() is None

    current_role_response = test_client.post(
        "/api/users/",
        headers=headers,
        json={
            "id": "bad-function-grant",
            "name": "Bad Function Grant",
            "username": "bad_function_grant",
            "password": "SecurePassword123!",
            "role": "Function Director",
            "accessible_functions": ["Finance"],
        },
    )
    assert current_role_response.status_code == 422
    assert db_session.query(User).filter(User.username == "bad_function_grant").first() is None


def test_function_assignments_load_into_authoritative_request_scope(db_session):
    user = AuthenticationService.create_user(
        db_session,
        "scoped_function_user",
        "scoped_function_user@test.com",
        "SecurePassword123!",
        "Function Viewer",
    )
    db_session.add(UserFunctionAssignment(
        user_id=user.id,
        function_name="Call Center",
        assigned_by="admin_user",
    ))
    db_session.commit()

    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/performance/records",
        "headers": [],
        "query_string": b"",
    })
    request.state.user = {
        "user_id": str(user.id),
        "role": "Function Viewer",
        "employee_id": user.employee_id,
    }

    scope = get_current_user_scope(db_session, request)

    assert scope["accessible_functions"] == ["Call Center"]


@pytest.mark.parametrize("role", ["Function Viewer", "Manager", "General Manager"])
def test_non_admin_cannot_change_permissions_even_with_forged_role_header(test_client, db_session, role):
    user = AuthenticationService.create_user(
        db_session, "permission_attacker", "attacker@test.com", "SecurePassword123!", role,
    )
    token = AuthenticationService.authenticate_user(db_session, user.username, "SecurePassword123!")
    headers = {"Authorization": f"Bearer {token}", "X-User-Role": "Admin"}
    payload = {
        "id": str(user.id), "name": "Attacker", "username": user.username,
        "password": "SecurePassword123!", "role": "Admin",
        "accessible_functions": ["RCM", "Marketing"], "has_unrestricted_team_access": True,
    }
    assert test_client.get("/api/users/", headers=headers).status_code == 403
    assert test_client.post("/api/users/", headers=headers, json=payload).status_code == 403
    assert test_client.put(f"/api/users/{user.id}", headers=headers, json=payload).status_code == 403
    assert test_client.delete(f"/api/users/{user.id}", headers=headers).status_code == 403
    db_session.refresh(user)
    assert user.role == role
    assert db_session.query(UserFunctionAssignment).filter_by(user_id=user.id).count() == 0


def test_role_changes_do_not_restore_historical_branch_permissions(test_client, db_session):
    headers = _auth_headers(db_session, "branch_security_admin", "SecurePassword123!")
    team = Team(name="Coding", db_name="coding", display_name="Coding", region="EGY", is_active=True)
    user = AuthenticationService.create_user(
        db_session, "former_manager", "former@test.com", "SecurePassword123!", "Manager",
    )
    db_session.add(team)
    db_session.flush()
    db_session.add(UserTeamAssignment(user_id=user.id, team_id=team.id, assigned_by="Admin"))
    db_session.commit()
    payload = {"id": str(user.id), "name": "Former Manager", "username": user.username}
    demoted = test_client.put(
        f"/api/users/{user.id}", headers=headers,
        json={**payload, "role": "Function Director", "accessible_functions": ["Marketing"]},
    )
    assert demoted.status_code == 200
    assert db_session.query(UserTeamAssignment).filter_by(user_id=user.id).count() == 0
    # Also handle historical rows left behind before role changes cleared grants.
    db_session.add(UserTeamAssignment(user_id=user.id, team_id=team.id, assigned_by="Admin"))
    db_session.commit()
    promoted = test_client.put(
        f"/api/users/{user.id}", headers=headers, json={**payload, "role": "Manager"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["data"]["accessible_teams"] == []
    assert promoted.json()["data"]["has_unrestricted_team_access"] is False
