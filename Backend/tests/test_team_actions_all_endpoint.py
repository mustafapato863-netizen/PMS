"""Tests for GET /api/team-actions/all, PATCH /api/team-actions/{id}/status, and DELETE /api/team-actions/{id}."""

import uuid

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers import team as team_router_module
from config.database import get_db
from models.models import Action, Base, Employee, Team
from services.team_action_service import TeamActionService


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _seed_teams_and_actions(db):
    coding = Team(
        id=uuid.uuid4(),
        name="coding",
        db_name="Coding",
        display_name="Coding",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    inbound = Team(
        id=uuid.uuid4(),
        name="inbound",
        db_name="Inbound",
        display_name="Inbound",
        region="UAE",
        team_level="employee",
        is_active=True,
    )
    db.add_all([coding, inbound])
    db.flush()

    emp = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-100",
        name="Individual Agent",
        team_id=inbound.id,
        region="UAE",
        is_active=True,
    )
    db.add(emp)
    db.flush()

    # Individual employee corrective action (must NOT appear in whole-team actions)
    indv_action = Action(
        id=uuid.uuid4(),
        team_id=inbound.id,
        employee_id=emp.id,
        month="October",
        year=2026,
        action_type="Coaching",
        action_text="Individual coaching for AHT",
        status="Open",
        is_active=True,
    )
    db.add(indv_action)
    db.commit()

    admin_scope = {
        "user_id": str(uuid.uuid4()),
        "role": "Admin",
        "accessible_teams": [],
        "accessible_regions": [],
        "accessible_functions": [],
        "has_unrestricted_team_access": True,
    }
    svc = TeamActionService(db)
    cohort_item = svc.save_plan_item(
        {
            "card_id": "team-act-custom-1",
            "team": "Coding",
            "region": "EGY",
            "month": "October",
            "year": 2026,
            "title": "Institute mandatory 100% pre-bill peer audit on OP Coding batches",
            "target_kpi": "Coding EGY Quality Errors Rate (11.3% -> <= 5.0%)",
            "owner": "Coding & Audit QA Lead",
            "status": "Open",
            "expected_team_impact": "Bring quality error rate below 5%",
        },
        current_user=admin_scope,
    )
    overall_item = svc.save(
        team_reference="inbound",
        month="October",
        year=2026,
        overall_action="Run daily queue rebalance huddle across peak inbound hours",
        scope=admin_scope,
        user_id=admin_scope["user_id"],
    )
    # Create and delete a built-in tombstone to verify tombstones are excluded
    svc.delete_plan_item(
        card_id="coding-builtin-1",
        team_name="Coding",
        month="October",
        year=2026,
        current_user=admin_scope,
        region="EGY",
    )
    db.commit()
    return {"coding": coding, "inbound": inbound, "cohort": cohort_item, "overall": overall_item}


def _make_client(db, monkeypatch, active_user_box):
    monkeypatch.setattr(team_router_module, "get_current_user_scope", lambda _db, _req: active_user_box["user"])
    app = FastAPI()

    @app.middleware("http")
    async def inject_user(request: Request, call_next):
        request.state.user = active_user_box["user"]
        return await call_next(request)

    app.include_router(team_router_module.router, prefix="/api/team-actions")

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_list_all_team_actions_returns_only_whole_team_actions_and_respects_scope(db_session, monkeypatch):
    seeded = _seed_teams_and_actions(db_session)
    active_user = {
        "user": {
            "user_id": str(uuid.uuid4()),
            "role": "Admin",
            "accessible_teams": [],
            "accessible_regions": [],
            "accessible_functions": [],
            "has_unrestricted_team_access": True,
        }
    }
    client = _make_client(db_session, monkeypatch, active_user)

    res = client.get("/api/team-actions/all")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    items = body["data"]
    assert len(items) == 2

    kinds = {item["kind"] for item in items}
    assert kinds == {"cohort_plan", "overall_action"}
    titles = {item["title"] for item in items}
    assert "Individual coaching for AHT" not in titles
    assert "[Deleted team action]" not in titles
    assert "Institute mandatory 100% pre-bill peer audit on OP Coding batches" in titles
    assert "Run daily queue rebalance huddle across peak inbound hours" in titles

    # Manager scoped only to Inbound sees only Inbound's whole-team action
    active_user["user"] = {
        "user_id": str(uuid.uuid4()),
        "role": "Manager",
        "accessible_teams": ["Inbound"],
        "accessible_regions": [],
        "accessible_functions": [],
        "has_unrestricted_team_access": False,
    }
    res_mgr = client.get("/api/team-actions/all")
    assert res_mgr.status_code == 200
    mgr_items = res_mgr.json()["data"]
    assert len(mgr_items) == 1
    assert mgr_items[0]["team"] == "Inbound"

    # Branch Director receives empty list (never 403 crash on page load)
    active_user["user"] = {
        "user_id": str(uuid.uuid4()),
        "role": "Branch Director",
        "accessible_teams": ["Inbound"],
        "accessible_regions": [],
        "accessible_functions": [],
        "has_unrestricted_team_access": False,
    }
    res_bd = client.get("/api/team-actions/all")
    assert res_bd.status_code == 200
    assert res_bd.json()["data"] == []

    # Admin can update status and delete a whole-team action by id
    active_user["user"] = {
        "user_id": str(uuid.uuid4()),
        "role": "Admin",
        "accessible_teams": [],
        "accessible_regions": [],
        "accessible_functions": [],
        "has_unrestricted_team_access": True,
    }
    cohort_id = seeded["cohort"]["id"]
    res_patch = client.patch(f"/api/team-actions/{cohort_id}/status", json={"status": "Completed"})
    assert res_patch.status_code == 200
    assert res_patch.json()["data"]["status"] == "Completed"

    res_del = client.delete(f"/api/team-actions/{cohort_id}")
    assert res_del.status_code == 200
    assert res_del.json()["data"]["deleted"] is True

    res_after = client.get("/api/team-actions/all")
    assert res_after.status_code == 200
    assert len(res_after.json()["data"]) == 1
