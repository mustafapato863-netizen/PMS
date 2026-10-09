"""Two real persisted Admin identities cannot overwrite a stale draft over HTTP.

The users, team row, and database are synthetic. SQLite is in-memory. The
Coding label is only the catalog key used to open a scope. This file does not
connect to production or change a private workbook.
"""
import copy
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers.evaluation_settings import router
from config.database import Base, get_db
from models.models import Team, TeamConfigurationVersion, User
from services.evaluation.workflow import EvaluationWorkflow


@pytest.fixture
def optimistic_world(monkeypatch):
    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda *_: None)
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()
    users = [User(id=uuid.UUID(f"a1000000-0000-4000-8000-00000000000{i}"), username=f"optimistic-admin-{i}", email=f"optimistic-{i}@example.invalid", role="Admin", password_hash="synthetic") for i in (1, 2)]
    denied = User(id=uuid.UUID("a1000000-0000-4000-8000-000000000003"), username="optimistic-performance", email="optimistic-performance@example.invalid", role="Performance Team", password_hash="synthetic")
    team = Team(id=uuid.UUID("a2000000-0000-4000-8000-000000000001"), name="Coding", db_name="Coding", display_name="Coding", region="UAE", team_level="employee")
    db.add_all([*users, denied, team])
    db.commit()
    actor = {"user_id": str(users[0].id), "role": "Admin", "has_unrestricted_team_access": True, "legacy_unscoped": False}
    workflow = EvaluationWorkflow(db)
    scope = next(item for item in workflow.sync_catalog(actor)["scopes"] if item["display_name"] == "Coding" and item["performance_level"] == "Employee" and item["position_name"] == "")
    draft = workflow.open_draft(actor, scope["id"], 2026, 7)
    holder = {"user": {"user_id": str(users[0].id), "role": "Admin"}}
    app = FastAPI()
    app.include_router(router, prefix="/evaluation")

    @app.middleware("http")
    async def attach_user(request, call_next):
        if holder["user"]:
            request.state.user = holder["user"]
        return await call_next(request)

    def session():
        yield db

    app.dependency_overrides[get_db] = session
    with TestClient(app) as client:
        yield client, db, holder, users, denied, draft
    db.close()
    engine.dispose()


def edited(lines, target):
    return [{**line, "target_mode": "fixed", "target": target} if index == 0 else dict(line) for index, line in enumerate(lines)]


def test_stale_second_admin_does_not_clear_newer_rules_or_preview(optimistic_world):
    client, db, holder, users, _, draft = optimistic_world
    route = f'/evaluation/drafts/{draft["id"]}'
    first = client.patch(route, json={"lines": edited(draft["lines"], .1), "expected_checksum": draft["checksum"]})
    assert first.status_code == 200
    first_data = first.json()["data"]
    assert first_data["checksum"] != draft["checksum"]
    assert client.post(route + "/impact-preview").status_code == 200
    version = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    sealed = copy.deepcopy(version.config_snapshot)
    checksum = version.config_checksum
    holder["user"] = {"user_id": str(users[1].id), "role": "Admin"}
    stale = client.patch(route, json={"lines": edited(draft["lines"], .2), "expected_checksum": draft["checksum"]})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_draft"
    db.refresh(version)
    assert version.config_snapshot == sealed
    assert version.config_checksum == checksum


def test_missing_precondition_is_rejected_after_admin_authorization(optimistic_world):
    client, db, _, _, _, draft = optimistic_world
    result = client.patch(f'/evaluation/drafts/{draft["id"]}', json={"lines": edited(draft["lines"], .1)})
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "draft_precondition_required"
    version = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    assert version.config_checksum == draft["checksum"]


def test_spoofed_admin_is_denied_before_precondition_or_version_lookup(optimistic_world):
    client, _, holder, _, denied, draft = optimistic_world
    holder["user"] = {"user_id": str(denied.id), "role": "Admin"}
    result = client.patch(f"/evaluation/drafts/{uuid.uuid4()}", json={"lines": draft["lines"]})
    assert result.status_code == 403


def _assert_denied_before_version_lookup(result):
    assert result.status_code == 403
    detail = result.json()["detail"]
    if isinstance(detail, dict):
        assert detail.get("code") not in {"not_found", "stale_draft", "draft_precondition_required"}


def test_non_admin_is_denied_before_version_lookup(optimistic_world):
    client, db, holder, _, denied, draft = optimistic_world
    holder["user"] = {"user_id": str(denied.id), "role": "Performance Team"}
    result = client.patch(
        f"/evaluation/drafts/{uuid.uuid4()}",
        json={"lines": draft["lines"], "expected_checksum": draft["checksum"]},
    )
    _assert_denied_before_version_lookup(result)
    version = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    assert version.config_checksum == draft["checksum"]


def test_disabled_admin_is_denied_before_version_lookup(optimistic_world):
    client, db, holder, _, _, draft = optimistic_world
    disabled = User(
        id=uuid.UUID("a1000000-0000-4000-8000-000000000004"),
        username="optimistic-disabled-admin",
        email="optimistic-disabled@example.invalid",
        role="Admin",
        password_hash="synthetic",
        is_active=False,
    )
    db.add(disabled)
    db.commit()
    holder["user"] = {"user_id": str(disabled.id), "role": "Admin"}
    result = client.patch(f"/evaluation/drafts/{uuid.uuid4()}", json={"lines": draft["lines"]})
    _assert_denied_before_version_lookup(result)
    version = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    assert version.config_checksum == draft["checksum"]


def test_same_checksum_keeps_an_unchanged_draft(optimistic_world):
    client, db, _, _, _, draft = optimistic_world
    result = client.patch(
        f'/evaluation/drafts/{draft["id"]}',
        json={"lines": draft["lines"], "expected_checksum": draft["checksum"]},
    )
    assert result.status_code == 200
    version = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    assert version.config_checksum == draft["checksum"]
    assert version.config_snapshot["lines"] == draft["lines"]
