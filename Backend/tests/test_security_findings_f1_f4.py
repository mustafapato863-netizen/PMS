"""Security findings F1–F4 on feat/general-manager-role (PR #9)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.middleware.auth_middleware import AuthMiddleware
from api.middleware.rbac_middleware import AuthorizationMiddleware, require_permission
from api.routers.bulk_operations import router as bulk_router
from api.routers.users_and_actions import (
    _manager_has_unrestricted_team_access,
    _user_to_public_dict,
    users_router,
)
from config.database import get_db
from models.models import Base, Employee, RefreshSession, RolePermission, Team, User, UserTeamAssignment
from models.schemas import UserUpdateRecord
from services.auth_service import AuthenticationService
from services.permission_seed import PERMISSION_MATRIX, seed_role_permissions


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
def users_client(db_session):
    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.include_router(users_router, prefix="/api/users")

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def bulk_client(db_session):
    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.include_router(bulk_router)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def _admin_headers(db_session, username="admin_sec"):
    AuthenticationService.create_user(
        db_session, username, f"{username}@test.com", "SecurePassword123!", "Admin"
    )
    token = AuthenticationService.authenticate_user(db_session, username, "SecurePassword123!")
    return {"Authorization": f"Bearer {token}"}


def _seed_teams(db_session, names=("Inbound", "Outbound", "Marketing")):
    teams = [
        Team(id=uuid.uuid4(), name=name, db_name=name.lower(), region="EGY", is_active=True)
        for name in names
    ]
    db_session.add_all(teams)
    db_session.commit()
    return teams


class TestF1ManagerUnrestrictedFlag:
    def test_manager_on_one_team_flag_is_false(self, db_session):
        teams = _seed_teams(db_session)
        manager = AuthenticationService.create_user(
            db_session, "one_team_mgr", "otm@test.com", "SecurePassword123!", "Manager"
        )
        db_session.add(
            UserTeamAssignment(
                id=uuid.uuid4(),
                user_id=manager.id,
                team_id=teams[0].id,
                performance_level=None,
                access_level="admin",
                assigned_by="Admin",
            )
        )
        db_session.commit()
        db_session.refresh(manager)

        assert _manager_has_unrestricted_team_access(db_session, manager) is False
        public = _user_to_public_dict(db_session, manager)
        assert public["has_unrestricted_team_access"] is False
        assert public["accessible_teams"] == [teams[0].name]

    def test_manager_all_teams_null_level_flag_is_true(self, db_session):
        teams = _seed_teams(db_session)
        manager = AuthenticationService.create_user(
            db_session, "all_team_mgr", "atm@test.com", "SecurePassword123!", "Manager"
        )
        for team in teams:
            db_session.add(
                UserTeamAssignment(
                    id=uuid.uuid4(),
                    user_id=manager.id,
                    team_id=team.id,
                    performance_level=None,
                    access_level="admin",
                    assigned_by="Admin",
                )
            )
        db_session.commit()
        db_session.refresh(manager)
        assert _manager_has_unrestricted_team_access(db_session, manager) is True
        assert _user_to_public_dict(db_session, manager)["has_unrestricted_team_access"] is True

    def test_user_update_record_flag_defaults_to_none(self):
        record = UserUpdateRecord(
            id=str(uuid.uuid4()),
            name="Mgr",
            username="mgr",
            role="Manager",
            is_active=True,
        )
        assert record.has_unrestricted_team_access is None
        dumped = record.model_dump(exclude_none=True)
        assert "has_unrestricted_team_access" not in dumped

    def test_admin_rename_does_not_assign_all_teams(self, users_client, db_session):
        teams = _seed_teams(db_session)
        manager = AuthenticationService.create_user(
            db_session, "rename_mgr", "rm@test.com", "SecurePassword123!", "Manager"
        )
        db_session.add(
            UserTeamAssignment(
                id=uuid.uuid4(),
                user_id=manager.id,
                team_id=teams[0].id,
                performance_level=None,
                access_level="admin",
                assigned_by="Admin",
            )
        )
        db_session.commit()

        headers = _admin_headers(db_session)
        # Simulate FE reopen: omit flag (None) or send false — must not expand.
        response = users_client.put(
            f"/api/users/{manager.id}",
            headers=headers,
            json={
                "id": str(manager.id),
                "name": "Renamed Manager",
                "username": "rename_mgr",
                "role": "Manager",
                "is_active": True,
                "accessible_teams": [teams[0].name],
                "has_unrestricted_team_access": False,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        assert body["data"]["has_unrestricted_team_access"] is False
        assert body["data"]["accessible_teams"] == [teams[0].name]

        assignments = (
            db_session.query(UserTeamAssignment)
            .filter(UserTeamAssignment.user_id == manager.id)
            .all()
        )
        assert len(assignments) == 1
        assert assignments[0].team_id == teams[0].id

    def test_admin_rename_omitting_flag_does_not_wipe_or_expand(self, users_client, db_session):
        teams = _seed_teams(db_session)
        manager = AuthenticationService.create_user(
            db_session, "omit_mgr", "om@test.com", "SecurePassword123!", "Manager"
        )
        db_session.add(
            UserTeamAssignment(
                id=uuid.uuid4(),
                user_id=manager.id,
                team_id=teams[0].id,
                performance_level=None,
                access_level="admin",
                assigned_by="Admin",
            )
        )
        db_session.commit()
        headers = _admin_headers(db_session, "admin_omit")
        # Omit has_unrestricted_team_access and accessible_teams entirely.
        response = users_client.put(
            f"/api/users/{manager.id}",
            headers=headers,
            json={
                "id": str(manager.id),
                "name": "Still One Team",
                "username": "omit_mgr",
                "role": "Manager",
                "is_active": True,
            },
        )
        assert response.status_code == 200, response.text
        assignments = (
            db_session.query(UserTeamAssignment)
            .filter(UserTeamAssignment.user_id == manager.id)
            .all()
        )
        assert len(assignments) == 1
        assert response.json()["data"]["has_unrestricted_team_access"] is False


class TestF2RedisRoleCache:
    @pytest.mark.asyncio
    async def test_demote_admin_to_gm_manage_users_false_immediately(self, db_session):
        user = AuthenticationService.create_user(
            db_session, "demote_admin", "da@test.com", "SecurePassword123!", "Admin"
        )
        assert await AuthorizationMiddleware.check_permission(
            db_session, str(user.id), "manage_users"
        )

        # Stale Redis session:{user_id} still holds Admin — must be ignored.
        fake_redis = MagicMock()
        fake_redis.get.return_value = "Admin"
        fake_redis.set = MagicMock()

        user.role = "General Manager"
        db_session.commit()

        with patch("api.middleware.rbac_middleware.redis_client", fake_redis):
            assert not await AuthorizationMiddleware.check_permission(
                db_session, str(user.id), "manage_users"
            )
            # Fresh DB role via request.state-style role kwarg also denies.
            assert not await AuthorizationMiddleware.check_permission(
                db_session, str(user.id), "manage_users", role="General Manager"
            )
            # Redis role key must not be written by permission checks.
            for call in fake_redis.set.call_args_list:
                key = call.args[0] if call.args else call.kwargs.get("name")
                assert not str(key).startswith("session:"), call

    @pytest.mark.asyncio
    async def test_require_permission_uses_request_state_role(self, db_session):
        user = AuthenticationService.create_user(
            db_session, "state_role", "sr@test.com", "SecurePassword123!", "General Manager"
        )
        app = FastAPI()
        app.add_middleware(AuthMiddleware)

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        @app.post("/api/users")
        async def manage_users_route(user=Depends(require_permission("manage_users"))):
            return {"success": True}

        client = TestClient(app)
        token = AuthenticationService.authenticate_user(
            db_session, "state_role", "SecurePassword123!"
        )
        assert client.post(
            "/api/users", headers={"Authorization": f"Bearer {token}"}
        ).status_code == 403


class TestF3BulkDeleteAdminOnly:
    def test_gm_denied_bulk_employee_delete(self, bulk_client, db_session):
        AuthenticationService.create_user(
            db_session, "gm_bulk", "gmb@test.com", "SecurePassword123!", "General Manager"
        )
        token = AuthenticationService.authenticate_user(
            db_session, "gm_bulk", "SecurePassword123!"
        )
        team = Team(id=uuid.uuid4(), name="T", db_name="t", region="EGY", is_active=True)
        emp = Employee(id=uuid.uuid4(), employee_id="E1", name="Emp", team_id=team.id, is_active=True)
        db_session.add_all([team, emp])
        db_session.commit()

        response = bulk_client.request(
            "DELETE",
            "/bulk/employees",
            headers={"Authorization": f"Bearer {token}"},
            json={"employee_ids": [str(emp.id)]},
        )
        assert response.status_code == 403
        db_session.refresh(emp)
        assert emp.is_active is True

    def test_admin_ok_bulk_employee_delete(self, bulk_client, db_session):
        from unittest.mock import patch

        headers = _admin_headers(db_session, "admin_bulk")
        team = Team(id=uuid.uuid4(), name="T2", db_name="t2", region="EGY", is_active=True)
        emp = Employee(id=uuid.uuid4(), employee_id="E2", name="Emp2", team_id=team.id, is_active=True)
        db_session.add_all([team, emp])
        db_session.commit()

        with patch("services.audit_service.AuditService.log_operation"):
            response = bulk_client.request(
                "DELETE",
                "/bulk/employees",
                headers=headers,
                json={"employee_ids": [str(emp.id)]},
            )
        assert response.status_code == 200, response.text
        db_session.refresh(emp)
        assert emp.is_active is False


class TestF4StripUploadDeleteFromGM:
    def test_matrix_strips_upload_and_delete_from_gm_only(self):
        gm = set(PERMISSION_MATRIX["General Manager"])
        assert "upload_data" not in gm
        assert "delete_performance" not in gm
        assert "upload_data" in PERMISSION_MATRIX["Admin"]
        assert "delete_performance" in PERMISSION_MATRIX["Admin"]
        assert "upload_data" in PERMISSION_MATRIX["Manager"]

    def test_seed_prunes_obsolete_gm_upload_perms(self, db_session):
        # Pretend old seed left these rows.
        for perm in ("upload_data", "delete_performance"):
            db_session.add(
                RolePermission(id=uuid.uuid4(), role="General Manager", permission=perm)
            )
        db_session.commit()
        seed_role_permissions(db_session)
        remaining = {
            row.permission
            for row in db_session.query(RolePermission)
            .filter(RolePermission.role == "General Manager")
            .all()
        }
        assert "upload_data" not in remaining
        assert "delete_performance" not in remaining
