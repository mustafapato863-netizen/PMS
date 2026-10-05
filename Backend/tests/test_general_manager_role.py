"""General Manager role (Option A) — backend contract tests.

Covers:
- Role constant + permission seed
- Product access granted; Settings-admin powers denied
- Team Management permissions granted
- Scope /me field renamed to has_unrestricted_team_access
- No mass migration of Managers
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.dependencies import get_current_user_scope, require_role
from api.middleware.auth_middleware import AuthMiddleware
from api.middleware.rbac_middleware import AuthorizationMiddleware, require_permission
from config import settings
from config.database import get_db
from models.models import Base, RolePermission, Team, User, UserTeamAssignment
from services.auth_service import AuthenticationService
from services.permission_seed import PERMISSION_MATRIX, seed_role_permissions


GM_DENIED = {
    "manage_users",
    "manage_permissions",
    "restore_data",
    "view_system_metrics",
}

GM_TEAM_MGMT = {
    "create_team",
    "edit_team_config",
    "delete_team",
    "configure_kpi",
}

GM_PRODUCT = {
    "edit_performance",
    "view_reports",
    "export_data",
    "manage_team_members",
    "view_actions",
    "create_actions",
    "manage_team_kpi",
    "view_plans",
    "manage_plans",
    "view_aggregated_analytics",
    "view_audit_logs",
    "manage_batch_operations",
    "manage_alerts",
}

# Settings-locked for GM (F4)
GM_SETTINGS_LOCKED = {
    "upload_data",
    "delete_performance",
}


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
            User.__table__,
            RolePermission.__table__,
            UserTeamAssignment.__table__,
            Team.__table__,
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

    @test_app.get("/api/reports")
    async def view_reports_route(user=Depends(require_permission("view_reports"))):
        return {"success": True}

    @test_app.get("/api/plans")
    async def view_plans_route(user=Depends(require_permission("view_plans"))):
        return {"success": True}

    @test_app.post("/api/plans")
    async def manage_plans_route(user=Depends(require_permission("manage_plans"))):
        return {"success": True}

    @test_app.get("/api/actions")
    async def view_actions_route(user=Depends(require_permission("view_actions"))):
        return {"success": True}

    @test_app.post("/api/teams")
    async def create_team_route(user=Depends(require_permission("create_team"))):
        return {"success": True}

    @test_app.put("/api/teams/config")
    async def edit_team_route(user=Depends(require_permission("edit_team_config"))):
        return {"success": True}

    @test_app.delete("/api/teams/config")
    async def delete_team_route(user=Depends(require_permission("delete_team"))):
        return {"success": True}

    @test_app.post("/api/users")
    async def manage_users_route(user=Depends(require_permission("manage_users"))):
        return {"success": True}

    @test_app.post("/api/settings/weights")
    async def manage_permissions_route(user=Depends(require_permission("manage_permissions"))):
        return {"success": True}

    @test_app.post("/api/settings/restore")
    async def restore_data_route(user=Depends(require_permission("restore_data"))):
        return {"success": True}

    @test_app.get("/api/settings/system-errors")
    async def system_errors_route(role: str = Depends(require_role(["Admin"]))):
        return {"success": True, "role": role}

    @test_app.get("/api/insights")
    async def insights_route(role: str = Depends(require_role(["Admin", "General Manager", "Manager", "Executive"]))):
        return {"success": True, "role": role}

    @test_app.get("/api/performance/edit")
    async def performance_edit_route(role: str = Depends(require_role(["Admin", "General Manager", "Manager"]))):
        return {"success": True, "role": role}

    @test_app.post("/api/uploads/pms")
    async def upload_pms_route(user=Depends(require_permission("upload_data"))):
        return {"success": True}

    @test_app.delete("/api/uploads/1")
    async def delete_upload_route(user=Depends(require_permission("delete_performance"))):
        return {"success": True}

    @test_app.post("/api/uploads/batch-delete")
    async def batch_delete_route(user=Depends(require_permission("delete_performance"))):
        return {"success": True}

    client = TestClient(test_app)
    yield client
    test_app.dependency_overrides.clear()


def _login_headers(db_session, username: str, password: str = "SecurePassword123!") -> dict:
    token = AuthenticationService.authenticate_user(db_session, username, password)
    return {"Authorization": f"Bearer {token}"}


def _create_gm(db_session, username: str = "gm_user") -> User:
    return AuthenticationService.create_user(
        db_session, username, f"{username}@test.com", "SecurePassword123!", "General Manager"
    )


def _seed_teams(db_session, names=("Inbound", "Outbound", "Marketing")) -> list[Team]:
    teams = [
        Team(id=uuid.uuid4(), name=name, db_name=name.lower().replace(" ", "_"), region="EGY", is_active=True)
        for name in names
    ]
    db_session.add_all(teams)
    db_session.commit()
    return teams


class TestGeneralManagerConstantsAndSeed:
    def test_role_constant_and_roles_list(self):
        assert settings.ROLE_GENERAL_MANAGER == "General Manager"
        assert "General Manager" in settings.ROLES
        assert settings.ROLE_ADMIN in settings.ROLES

    def test_permission_matrix_excludes_settings_admin_powers(self):
        gm_perms = set(PERMISSION_MATRIX["General Manager"])
        assert GM_DENIED.isdisjoint(gm_perms)
        assert GM_SETTINGS_LOCKED.isdisjoint(gm_perms)
        assert GM_TEAM_MGMT.issubset(gm_perms)
        assert GM_PRODUCT.issubset(gm_perms)
        # Manager retains upload_data; only GM lost Settings-locked perms.
        assert "upload_data" in PERMISSION_MATRIX["Manager"]
        assert "upload_data" in PERMISSION_MATRIX["Admin"]
        assert "delete_performance" in PERMISSION_MATRIX["Admin"]

    def test_seed_persists_gm_permissions(self, db_session):
        rows = {
            row.permission
            for row in db_session.query(RolePermission).filter(RolePermission.role == "General Manager").all()
        }
        assert GM_DENIED.isdisjoint(rows)
        assert "create_team" in rows
        assert "view_reports" in rows
        assert "manage_users" not in rows


class TestGeneralManagerPermissions:
    @pytest.mark.asyncio
    async def test_gm_allowed_product_and_team_mgmt_permissions(self, db_session):
        user = _create_gm(db_session)
        for perm in sorted(GM_PRODUCT | GM_TEAM_MGMT):
            assert await AuthorizationMiddleware.check_permission(db_session, str(user.id), perm), perm

    @pytest.mark.asyncio
    async def test_gm_denied_settings_admin_permissions(self, db_session):
        user = _create_gm(db_session)
        for perm in sorted(GM_DENIED):
            assert not await AuthorizationMiddleware.check_permission(db_session, str(user.id), perm), perm

    @pytest.mark.asyncio
    async def test_gm_denied_upload_and_delete_performance(self, db_session):
        user = _create_gm(db_session)
        for perm in sorted(GM_SETTINGS_LOCKED):
            assert not await AuthorizationMiddleware.check_permission(db_session, str(user.id), perm), perm

    @pytest.mark.asyncio
    async def test_gm_does_not_get_admin_bypass(self, db_session):
        """Unlike Admin, GM must not pass arbitrary unseeded permissions."""
        user = _create_gm(db_session)
        assert not await AuthorizationMiddleware.check_permission(
            db_session, str(user.id), "some_arbitrary_permission"
        )


class TestGeneralManagerHttpAccess:
    def test_gm_can_access_product_permission_routes(self, db_session, test_client):
        _create_gm(db_session)
        headers = _login_headers(db_session, "gm_user")
        for path, method in (
            ("/api/reports", "get"),
            ("/api/plans", "get"),
            ("/api/plans", "post"),
            ("/api/actions", "get"),
            ("/api/teams", "post"),
            ("/api/teams/config", "put"),
            ("/api/teams/config", "delete"),
            ("/api/insights", "get"),
            ("/api/performance/edit", "get"),
        ):
            response = getattr(test_client, method)(path, headers=headers)
            assert response.status_code == 200, (path, method, response.status_code, response.text)

    def test_gm_cannot_manage_users_permissions_restore_or_system_errors(self, db_session, test_client):
        _create_gm(db_session)
        headers = _login_headers(db_session, "gm_user")
        assert test_client.post("/api/users", headers=headers).status_code == 403
        assert test_client.post("/api/settings/weights", headers=headers).status_code == 403
        assert test_client.post("/api/settings/restore", headers=headers).status_code == 403
        assert test_client.get("/api/settings/system-errors", headers=headers).status_code == 403

    def test_gm_denied_upload_and_data_delete_routes(self, db_session, test_client):
        _create_gm(db_session)
        headers = _login_headers(db_session, "gm_user")
        assert test_client.post("/api/uploads/pms", headers=headers).status_code == 403
        assert test_client.delete("/api/uploads/1", headers=headers).status_code == 403
        assert test_client.post("/api/uploads/batch-delete", headers=headers).status_code == 403

    def test_admin_still_passes_settings_admin_endpoints(self, db_session, test_client):
        AuthenticationService.create_user(
            db_session, "admin_user", "admin@test.com", "SecurePassword123!", "Admin"
        )
        headers = _login_headers(db_session, "admin_user")
        assert test_client.post("/api/users", headers=headers).status_code == 200
        assert test_client.post("/api/settings/weights", headers=headers).status_code == 200
        assert test_client.post("/api/settings/restore", headers=headers).status_code == 200
        assert test_client.get("/api/settings/system-errors", headers=headers).status_code == 200


class TestGeneralManagerScopeAndRename:
    def test_gm_scope_has_unrestricted_team_access_and_all_teams(self, db_session):
        user = _create_gm(db_session, "gm_scope")
        teams = _seed_teams(db_session)
        # Even without explicit assignments, role GM grants full scope.
        scope = get_current_user_scope(
            db_session,
            SimpleNamespace(state=SimpleNamespace(user={"user_id": str(user.id), "role": "General Manager"})),
        )
        assert "is_general_manager" not in scope
        assert scope["has_unrestricted_team_access"] is True
        assert set(scope["accessible_teams"]) == {team.name for team in teams}
        assert scope["role"] == "General Manager"

    def test_manager_all_teams_still_sets_renamed_flag_not_role_migration(self, db_session):
        """Do not mass-migrate Managers → General Manager; keep flag semantics."""
        user = AuthenticationService.create_user(
            db_session, "all_teams_mgr", "atm@test.com", "SecurePassword123!", "Manager"
        )
        teams = _seed_teams(db_session)
        for team in teams:
            db_session.add(
                UserTeamAssignment(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    team_id=team.id,
                    performance_level=None,
                    access_level="admin",
                    assigned_by="Admin",
                )
            )
        db_session.commit()

        scope = get_current_user_scope(
            db_session,
            SimpleNamespace(state=SimpleNamespace(user={"user_id": str(user.id), "role": "Manager"})),
        )
        assert scope["role"] == "Manager"
        assert scope["has_unrestricted_team_access"] is True
        assert "is_general_manager" not in scope

    def test_require_role_accepts_general_manager_on_product_gate(self):
        dependency = require_role(["Admin", "General Manager", "Manager"])
        request = SimpleNamespace(state=SimpleNamespace(user={"role": "General Manager"}))
        assert dependency(request=request, x_user_role="Viewer") == "General Manager"

    def test_require_role_rejects_general_manager_on_admin_only_gate(self):
        dependency = require_role(["Admin"])
        request = SimpleNamespace(state=SimpleNamespace(user={"role": "General Manager"}))
        with pytest.raises(HTTPException) as exc:
            dependency(request=request, x_user_role="Viewer")
        assert exc.value.status_code == 403


class TestNoMassMigration:
    def test_existing_managers_remain_managers_in_seed(self, db_session):
        manager = AuthenticationService.create_user(
            db_session, "plain_mgr", "pm@test.com", "SecurePassword123!", "Manager"
        )
        db_session.refresh(manager)
        assert manager.role == "Manager"
        assert db_session.query(User).filter(User.role == "General Manager").count() == 0
