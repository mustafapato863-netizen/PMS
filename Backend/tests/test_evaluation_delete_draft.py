"""Delete draft discards only a DRAFT row and keeps approved history intact.

Users, teams, and the database are synthetic. SQLite is in-memory. Nothing here
connects to PostgreSQL or reads an environment file.
"""

import copy
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers.evaluation_settings import router
from config.database import Base, get_db
from models.models import Team, TeamConfigurationVersion, User
from services.evaluation.access import EvaluationError
from services.evaluation.workflow import EvaluationWorkflow


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda *_: None)
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()
    admin = User(
        id=uuid.UUID("b1000000-0000-4000-8000-000000000001"),
        username="delete-draft-admin",
        email="delete-draft-admin@example.invalid",
        role="Admin",
        password_hash="synthetic",
    )
    denied = User(
        id=uuid.UUID("b1000000-0000-4000-8000-000000000003"),
        username="delete-draft-performance",
        email="delete-draft-performance@example.invalid",
        role="Performance Team",
        password_hash="synthetic",
    )
    team = Team(
        id=uuid.UUID("b2000000-0000-4000-8000-000000000001"),
        name="Coding",
        db_name="Coding",
        display_name="Coding",
        region="UAE",
        team_level="employee",
    )
    db.add_all([admin, denied, team])
    db.commit()
    actor = {"user_id": str(admin.id), "role": "Admin", "has_unrestricted_team_access": True, "legacy_unscoped": False}
    workflow = EvaluationWorkflow(db)
    scope = next(
        item for item in workflow.sync_catalog(actor)["scopes"]
        if item["display_name"] == "Coding" and item["performance_level"] == "Employee" and item["position_name"] == ""
    )
    holder = {"user": {"user_id": str(admin.id), "role": "Admin"}}
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
        yield SimpleNamespace(
            client=client, db=db, holder=holder, actor=actor, workflow=workflow,
            scope=scope, admin=admin, denied=denied,
        )
    db.close()
    engine.dispose()


def _row(db, version_id) -> TeamConfigurationVersion:
    return db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(str(version_id))).one()


def _exists(db, version_id) -> bool:
    return db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(str(version_id))).one_or_none() is not None


def _edited(lines, target):
    return [{**line, "target_mode": "fixed", "target": target} if index == 0 else dict(line) for index, line in enumerate(lines)]


def _approve(world, draft, target=0.1):
    edited_draft = world.workflow.edit_draft(world.actor, draft["id"], _edited(draft["lines"], target))
    world.workflow.impact_preview(world.actor, edited_draft["id"])
    return world.workflow.approve(world.actor, edited_draft["id"])


def _delete_url(version_id):
    return f"/evaluation/drafts/{version_id}"


def test_delete_baseline_draft_then_open_creates_a_fresh_draft(world):
    draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)
    result = world.workflow.delete_draft(world.actor, draft["id"], expected_checksum=draft["checksum"])
    assert result == {
        "deleted_version_id": draft["id"],
        "scope_id": world.scope["id"],
        "year": 2026,
        "month": 7,
    }
    assert not _exists(world.db, draft["id"])
    fresh = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)
    assert fresh["id"] != draft["id"]
    assert fresh["status"] == "draft"


def test_delete_revision_draft_keeps_the_approved_source_as_current(world):
    baseline = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)
    approved = _approve(world, baseline)
    approved_before = _row(world.db, approved["id"])
    snapshot_before = copy.deepcopy(approved_before.config_snapshot)
    checksum_before = approved_before.config_checksum

    revision = world.workflow.revise(world.actor, approved["id"])
    assert revision["status"] == "draft"
    assert revision["source_version_id"] == approved["id"]

    world.workflow.delete_draft(world.actor, revision["id"], expected_checksum=revision["checksum"])
    assert not _exists(world.db, revision["id"])

    source = _row(world.db, approved["id"])
    assert source.status == "approved"
    assert source.config_snapshot == snapshot_before
    assert source.config_checksum == checksum_before
    period = world.workflow.period(world.actor, world.scope["id"], 2026, 7)
    current = [item for item in period["versions"] if item["status"] in {"draft", "approved"}]
    assert [(item["id"], item["status"]) for item in current] == [(approved["id"], "approved")]


def test_approved_and_superseded_versions_are_refused_and_kept(world):
    baseline = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)
    first = _approve(world, baseline)
    revision = world.workflow.revise(world.actor, first["id"])
    second = _approve(world, revision, target=0.2)
    assert _row(world.db, first["id"]).status == "superseded"

    for version in (first, second):
        with pytest.raises(EvaluationError) as refused:
            world.workflow.delete_draft(world.actor, version["id"], expected_checksum=version["checksum"])
        assert refused.value.data.get("code") == "not_draft"
        assert refused.value.status_code == 409
        assert _exists(world.db, version["id"])
        assert _row(world.db, version["id"]).status in {"approved", "superseded"}


def test_stale_and_missing_checksum_are_refused_and_the_draft_stays(world):
    draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)

    with pytest.raises(EvaluationError) as stale:
        world.workflow.delete_draft(world.actor, draft["id"], expected_checksum="0" * 64)
    assert stale.value.data.get("code") == "stale_draft"
    assert stale.value.status_code == 409

    with pytest.raises(EvaluationError) as missing:
        world.workflow.delete_draft(world.actor, draft["id"], expected_checksum=None)
    assert missing.value.data.get("code") == "draft_precondition_required"
    assert missing.value.status_code == 409

    assert _exists(world.db, draft["id"])
    assert _row(world.db, draft["id"]).config_checksum == draft["checksum"]


def test_unknown_version_id_is_not_found(world):
    with pytest.raises(EvaluationError) as missing:
        world.workflow.delete_draft(world.actor, uuid.uuid4(), expected_checksum="0" * 64)
    assert missing.value.data.get("code") == "not_found"


def test_draft_in_another_month_is_not_affected(world):
    july = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)
    august = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 8)
    world.workflow.delete_draft(world.actor, july["id"], expected_checksum=july["checksum"])
    assert _exists(world.db, august["id"])
    assert _row(world.db, august["id"]).config_checksum == august["checksum"]


def test_http_delete_removes_draft_with_checksum_query(world):
    draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)
    result = world.client.delete(_delete_url(draft["id"]), params={"expected_checksum": draft["checksum"]})
    assert result.status_code == 200
    body = result.json()
    assert body["success"] is True
    assert body["data"]["deleted_version_id"] == draft["id"]
    assert not _exists(world.db, draft["id"])


def test_http_stale_checksum_returns_409_and_keeps_draft(world):
    draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)
    result = world.client.delete(_delete_url(draft["id"]), params={"expected_checksum": "0" * 64})
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "stale_draft"
    assert _exists(world.db, draft["id"])


def test_http_missing_checksum_returns_409_and_keeps_draft(world):
    draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)
    result = world.client.delete(_delete_url(draft["id"]))
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "draft_precondition_required"
    assert _exists(world.db, draft["id"])


def test_http_approved_version_returns_409_and_is_kept(world):
    baseline = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)
    approved = _approve(world, baseline)
    result = world.client.delete(_delete_url(approved["id"]), params={"expected_checksum": approved["checksum"]})
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "not_draft"
    assert _row(world.db, approved["id"]).status == "approved"


def test_http_unknown_version_id_is_refused(world):
    result = world.client.delete(_delete_url(uuid.uuid4()), params={"expected_checksum": "0" * 64})
    assert result.status_code == 422
    assert result.json()["detail"]["code"] == "not_found"


def test_http_non_admin_is_denied_before_version_lookup(world):
    draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)
    world.holder["user"] = {"user_id": str(world.denied.id), "role": "Performance Team"}
    result = world.client.delete(_delete_url(draft["id"]), params={"expected_checksum": draft["checksum"]})
    assert result.status_code == 403
    assert _exists(world.db, draft["id"])


def test_http_anonymous_is_unauthorized(world):
    draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)
    world.holder["user"] = None
    result = world.client.delete(_delete_url(draft["id"]), params={"expected_checksum": draft["checksum"]})
    assert result.status_code == 401
    assert _exists(world.db, draft["id"])
