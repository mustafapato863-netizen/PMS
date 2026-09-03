import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from api.middleware.auth_middleware import AuthMiddleware
from api.routers.users_and_actions import users_router
from config.database import get_db
from models.models import Base, Employee, RefreshSession, RolePermission, Team, User, UserTeamAssignment
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
            "role": "Viewer",
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
