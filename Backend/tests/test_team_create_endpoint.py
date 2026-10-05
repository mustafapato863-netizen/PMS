"""QA GM-09 — POST /team-management/teams through the real router.

Regression: team create returned 400 for Admin and General Manager with
"'TeamCreateRequest' object has no attribute 'db_name'" because
TeamService.create_team read ``request.db_name`` while the request model did
not declare that field. Manager must still receive 403.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import services.team_service as team_service_module
from api.middleware.auth_middleware import AuthMiddleware
from api.routers import team_management
from config.database import get_db
from models.models import Base, RolePermission, Team, TeamKPIConfig, User, UserTeamAssignment
from models.team_models import TeamCreateRequest
from services.auth_service import AuthenticationService
from services.permission_seed import seed_role_permissions

PASSWORD = "SecurePassword123!"


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=eng,
        tables=[
            User.__table__,
            RolePermission.__table__,
            UserTeamAssignment.__table__,
            Team.__table__,
            TeamKPIConfig.__table__,
        ],
    )
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    seed_role_permissions(session)
    yield session
    session.close()


@pytest.fixture()
def client(engine, db_session, monkeypatch):
    # TeamService opens its own session via SessionLocal; point it at the test DB.
    monkeypatch.setattr(
        team_service_module,
        "SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=engine),
    )

    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.include_router(team_management.router, prefix="/api")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _headers(db_session, username: str, role: str) -> dict:
    AuthenticationService.create_user(db_session, username, f"{username}@test.com", PASSWORD, role)
    token = AuthenticationService.authenticate_user(db_session, username, PASSWORD)
    return {"Authorization": f"Bearer {token}"}


def _payload(name: str) -> dict:
    # Mirrors the frontend CreateTeamRequest (no db_name field).
    return {
        "name": name,
        "display_name": f"{name} display",
        "region": "EGY",
        "kpi_keys": [],
        "kpi_weights": {},
    }


def test_create_request_model_exposes_optional_db_name():
    request = TeamCreateRequest(name="QA Team", display_name="QA")
    assert request.db_name is None
    assert TeamCreateRequest(name="qa", display_name="QA", db_name="QA_DB").db_name == "QA_DB"


@pytest.mark.parametrize(
    ("role", "username", "team_name"),
    [
        ("Admin", "admin_creator", "gm09_admin_team"),
        ("General Manager", "gm_creator", "gm09_gm_team"),
    ],
)
def test_admin_and_gm_can_create_team(client, db_session, role, username, team_name):
    headers = _headers(db_session, username, role)

    response = client.post("/api/team-management/teams", json=_payload(team_name), headers=headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == team_name
    assert body["region"] == "EGY"
    assert body["team_level"] == "employee"

    db_session.expire_all()
    team = db_session.query(Team).filter(Team.name == team_name).one()
    assert team.db_name == team_name  # falls back to normalized name when db_name omitted
    assert db_session.query(TeamKPIConfig).filter(TeamKPIConfig.team_id == team.id).count() > 0


def test_create_team_honours_explicit_db_name(client, db_session):
    headers = _headers(db_session, "gm_dbname", "General Manager")
    payload = {**_payload("gm09_explicit"), "db_name": "GM09_Explicit_DB"}

    response = client.post("/api/team-management/teams", json=payload, headers=headers)

    assert response.status_code == 201, response.text
    db_session.expire_all()
    team = db_session.query(Team).filter(Team.name == "gm09_explicit").one()
    assert team.db_name == "GM09_Explicit_DB"


def test_manager_cannot_create_team(client, db_session):
    headers = _headers(db_session, "plain_manager", "Manager")

    response = client.post("/api/team-management/teams", json=_payload("gm09_mgr_team"), headers=headers)

    assert response.status_code == 403, response.text
    assert db_session.query(Team).filter(Team.name == "gm09_mgr_team").count() == 0
