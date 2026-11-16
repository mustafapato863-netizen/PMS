"""Team references for team-level actions resolve to exactly one team.

The frontend sends the canonical route id of the team page (types.ts teamPath). Each
route id must reach the team row that stores its notes, and no reference may land on
Marketing (or any other row) by accident.
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Action, AuditLog, Base, Team
from services.team_action_service import TeamActionService

# (name, db_name, display_name) for the team rows the dashboards read. Display names are the
# logical team names; the unique index on them mirrors the production table.
TEAM_ROWS = [
    ("inbound", "Inbound", "Inbound"),
    ("outbound", "Outbound", "Outbound"),
    ("pre_approvals_offshore", "Pre-Approvals IP Offshore", "Pre-Approvals IP Offshore"),
    ("coding", "Coding", "Coding"),
    ("csr", "CSR", "CSR"),
    ("sales", "Sales", "Sales"),
    ("pharmacy", "Pharmacy", "Pharmacy"),
    ("submission", "Submission", "Submission"),
    ("re_submission", "Re-Submission", "Re-Submission"),
    ("pre_approvals_op_dubai", "Pre-Approvals OP Dubai", "Pre-Approvals OP Dubai"),
    ("pre_approvals_op_final_shj_ajm", "Pre-Approvals OP Final SHJAJM", "Pre-Approvals OP Final SHJAJM"),
    ("pre_approvals_ip_final_dubai", "Pre-Approvals IP Final Dubai", "Pre-Approvals IP Final Dubai"),
    ("pre_approvals_ip_final_shj_ajm", "Pre-Approvals IP Final SHJAJM", "Pre-Approvals IP Final SHJAJM"),
    ("pre_approvals_ip_elective_dubai", "Pre-Approvals IP Elective Dubai", "Pre-Approvals IP Elective Dubai"),
    ("marketing", "Marketing", "Marketing"),
    ("rcm", "RCM", "RCM"),
    ("call_center", "Call Center", "Call Center"),
    ("pre_approvals_uae", "Pre-Approvals", "Pre-Approvals"),
]

# Every canonical route id teamPath can produce (types.ts TEAM_ID_MAP values), with the
# team row that stores its notes. Merged and parent views keep the stored-row
# behaviour described in TeamActionService._SLUG_ALIASES.
CANONICAL_ROUTE_IDS = {
    "rcm": "RCM",
    "call-center": "Call Center",
    "inbound": "Inbound",
    "outbound": "Outbound",
    "pre-approvals": "Pre-Approvals IP Offshore",
    "sales": "Sales",
    "coding": "Coding",
    "csr": "CSR",
    "pharmacy": "Pharmacy",
    "submission": "Submission",
    "re-submission": "Re-Submission",
    "pre-approvals-op-final": "Pre-Approvals OP Dubai",
    "pre-approvals-ip-final": "Pre-Approvals IP Final Dubai",
    "pre-approvals-uae": "Pre-Approvals",
    "pre-approvals-op-dubai": "Pre-Approvals OP Dubai",
    "pre-approvals-ip-final-dubai": "Pre-Approvals IP Final Dubai",
    "pre-approvals-ip-elective-dubai": "Pre-Approvals IP Elective Dubai",
    "pre-approvals-op-final-shj-ajm": "Pre-Approvals OP Dubai",
    "pre-approvals-ip-final-shj-ajm": "Pre-Approvals IP Final Dubai",
    "marketing": "Marketing",
}


def add_team(db, name: str, db_name: str, display: str, *, active: bool = True) -> None:
    db.add(Team(id=uuid.uuid4(), name=name, db_name=db_name, display_name=display, region="UAE", team_level="employee", is_active=active))


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine, tables=[Team.__table__])
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    for name, db_name, display in TEAM_ROWS:
        add_team(session, name, db_name, display)
    session.commit()
    yield session
    session.close()


def resolved_display(db, reference: str) -> str:
    team = TeamActionService(db)._team(reference)
    return team.display_name


@pytest.mark.parametrize(("route_id", "expected"), sorted(CANONICAL_ROUTE_IDS.items()))
def test_every_canonical_route_id_resolves_to_its_team(db, route_id, expected):
    assert resolved_display(db, route_id) == expected


def test_no_canonical_route_id_lands_on_marketing_except_marketing(db):
    landed = {route_id: resolved_display(db, route_id) for route_id in CANONICAL_ROUTE_IDS}
    assert [route_id for route_id, team in landed.items() if team == "Marketing"] == ["marketing"]


def test_legacy_display_and_db_names_resolve_to_their_team(db):
    assert resolved_display(db, "Inbound") == "Inbound"
    assert resolved_display(db, "Pre-Approvals IP Offshore") == "Pre-Approvals IP Offshore"
    assert resolved_display(db, "pre-approvals-ip-offshore") == "Pre-Approvals IP Offshore"
    assert resolved_display(db, "Pre-Approvals IP Elective") == "Pre-Approvals IP Elective Dubai"


@pytest.mark.parametrize("reference", ["pre-approvals-ip-offshor", "not-a-team", "randd-team", ""])
def test_an_unknown_reference_raises_team_not_found(db, reference):
    with pytest.raises(ValueError, match="Team not found"):
        TeamActionService(db)._team(reference)


def test_an_alias_never_falls_back_to_another_team(db):
    # Elective is an alias to a row that is missing here; the lookup must not pick any other team.
    db.query(Team).filter(Team.display_name == "Pre-Approvals IP Elective Dubai").delete()
    db.commit()
    with pytest.raises(ValueError, match="Team not found"):
        TeamActionService(db)._team("pre-approvals-ip-elective-dubai")


def test_an_inactive_parent_still_resolves_and_source_teams_do_not(db):
    db.query(Team).filter(Team.display_name == "Call Center").update({"is_active": False})
    db.query(Team).filter(Team.display_name == "Inbound").update({"is_active": False})
    db.commit()
    assert resolved_display(db, "call-center") == "Call Center"
    with pytest.raises(ValueError, match="Team not found"):
        TeamActionService(db)._team("inbound")


def test_a_reference_matching_two_teams_raises_instead_of_picking_one(db):
    # Two rows carry the name "foo" (case-insensitively), so the reference is not unique.
    add_team(db, "foo", "Bar Team", "Bar Team Logical")
    add_team(db, "Foo", "Baz Team", "Baz Team Logical")
    db.commit()
    with pytest.raises(ValueError, match="more than one team"):
        TeamActionService(db)._team("Foo")


@pytest.fixture()
def full_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _make_user(
    *,
    role: str = "Admin",
    accessible_teams: list[str] | None = None,
    accessible_regions: list[str] | None = None,
    has_unrestricted: bool = False,
):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        accessible_teams=accessible_teams or [],
        accessible_regions=accessible_regions or [],
        accessible_functions=[],
        has_unrestricted_team_access=has_unrestricted,
        is_general_manager=False,
    )


def test_cohort_plan_item_save_list_upsert_and_planned_enum_mapping(full_db):
    import json
    from models.models import Action

    egy_team = Team(
        id=uuid.uuid4(),
        name="Re-Submission EGY",
        db_name="Re-Submission EGY",
        display_name="Re-Submission EGY",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    uae_team = Team(
        id=uuid.uuid4(),
        name="Re-Submission",
        db_name="Re-Submission",
        display_name="Re-Submission",
        region="UAE",
        team_level="employee",
        is_active=True,
    )
    full_db.add_all([egy_team, uae_team])
    full_db.commit()

    admin = _make_user(role="Admin")
    svc = TeamActionService(full_db)

    # Save with UI status 'Planned' -> DB status MUST be valid ENUM 'Open' + ui_status='Planned' in JSON
    saved = svc.save_plan_item(
        {
            "card_id": "team-act-resub-1",
            "team": "Re-Submission",
            "region": "EGY",
            "month": "September",
            "year": 2026,
            "title": "Run live coaching huddles on quality",
            "target_kpi": "Quality · 92% -> 95%",
            "scope_description": "All Resubmission Agents",
            "owner": "Resubmission Team Leader",
            "status": "Planned",
            "due_date": "2026-10-05",
            "expected_team_impact": "+1.2% team score lift",
        },
        current_user=admin,
    )
    assert saved["card_id"] == "team-act-resub-1"
    assert saved["status"] == "Planned"
    assert saved["region"] == "EGY"
    assert saved["due_date"] == "2026-10-05"

    row = (
        full_db.query(Action)
        .filter(Action.evidence_reference == "cohort-plan:team-act-resub-1")
        .one()
    )
    assert row.action_type == "Team Action"
    assert row.employee_id is None
    assert row.status == "Open"  # PostgreSQL ENUM safe
    meta = json.loads(row.root_cause_note)
    assert meta["ui_status"] == "Planned"

    # Upsert same card_id -> updates existing active row cleanly without duplicating
    updated = svc.save_plan_item(
        {
            "card_id": "team-act-resub-1",
            "team": "Re-Submission",
            "region": "EGY",
            "month": "September",
            "year": 2026,
            "title": "Updated coaching cadence",
            "target_kpi": "Quality · 92% -> 96%",
            "scope_description": "All Resubmission Agents",
            "owner": "QA Lead",
            "status": "In Progress",
            "due_date": None,
            "expected_team_impact": "+1.5% team score lift",
        },
        current_user=admin,
    )
    assert updated["id"] == saved["id"]
    assert updated["status"] == "In Progress"
    assert updated["owner"] == "QA Lead"

    items_egy = svc.list_plan_items("Re-Submission", "September", 2026, current_user=admin, region="EGY")
    assert len(items_egy) == 1
    assert items_egy[0]["title"] == "Updated coaching cadence"
    assert svc.list_plan_items("Re-Submission", "September", 2026, current_user=admin, region="UAE") == []


def test_cohort_plan_items_never_collide_with_team_dashboard_summary(full_db):
    egy_team = Team(
        id=uuid.uuid4(),
        name="Inbound",
        db_name="Inbound",
        display_name="Inbound",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    full_db.add(egy_team)
    full_db.commit()

    admin = _make_user(role="Admin")
    admin_scope = {
        "role": "Admin",
        "accessible_teams": [],
        "accessible_regions": [],
        "accessible_functions": [],
        "has_unrestricted_team_access": True,
    }
    svc = TeamActionService(full_db)

    svc.save_plan_item(
        {
            "card_id": "team-act-cohort-9",
            "team": "Inbound",
            "region": "EGY",
            "month": "September",
            "year": 2026,
            "title": "Cohort Plan Card",
            "target_kpi": "Booking Rate",
            "scope_description": "All Inbound",
            "owner": "Lead",
            "status": "Planned",
            "due_date": None,
            "expected_team_impact": "+1.0%",
        },
        current_user=admin,
    )
    # Team summary has evidence_reference IS NULL, so get() sees empty summary and saving summary does not touch cohort card
    assert svc.get(team_reference="Inbound", month="September", year=2026, scope=admin_scope) is None

    svc.save(
        team_reference="Inbound",
        month="September",
        year=2026,
        overall_action="Overall team summary",
        scope=admin_scope,
        user_id=str(admin.id),
    )
    summary = svc.get(team_reference="Inbound", month="September", year=2026, scope=admin_scope)
    assert summary["overall_action"] == "Overall team summary"
    cohort_items = svc.list_plan_items("Inbound", "September", 2026, current_user=admin, region="EGY")
    assert len(cohort_items) == 1
    assert cohort_items[0]["title"] == "Cohort Plan Card"


def test_cohort_plan_items_router_enforces_team_and_region_scope(full_db, monkeypatch):
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    from api.routers import team as team_router_module
    from config.database import get_db

    inbound = Team(
        id=uuid.uuid4(),
        name="Inbound",
        db_name="Inbound",
        display_name="Inbound",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    outbound = Team(
        id=uuid.uuid4(),
        name="Outbound",
        db_name="Outbound",
        display_name="Outbound",
        region="UAE",
        team_level="employee",
        is_active=True,
    )
    full_db.add_all([inbound, outbound])
    full_db.commit()

    active_user = {
        "user": {
            "user_id": str(uuid.uuid4()),
            "role": "Manager",
            "accessible_teams": ["Inbound"],
            "accessible_regions": [],
            "accessible_functions": [],
            "has_unrestricted_team_access": False,
        }
    }

    monkeypatch.setattr(team_router_module, "get_current_user_scope", lambda _db, _req: active_user["user"])

    app = FastAPI()

    @app.middleware("http")
    async def inject_user(request: Request, call_next):
        request.state.user = active_user["user"]
        return await call_next(request)

    app.include_router(team_router_module.router, prefix="/api/team-actions")

    def override_db():
        yield full_db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    # In-scope team succeeds
    res_ok = client.post(
        "/api/team-actions/plan-items",
        json={
            "card_id": "card-1",
            "team": "Inbound",
            "region": "EGY",
            "month": "September",
            "year": 2026,
            "title": "Inbound plan",
            "status": "Planned",
        },
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["data"]["status"] == "Planned"

    # Out-of-scope team returns 403
    res_team_403 = client.post(
        "/api/team-actions/plan-items",
        json={
            "card_id": "card-2",
            "team": "Outbound",
            "region": "UAE",
            "month": "September",
            "year": 2026,
            "title": "Outbound plan",
            "status": "Open",
        },
    )
    assert res_team_403.status_code == 403

    # Cross-region Regional Manager returns 403
    active_user["user"] = {
        "user_id": str(uuid.uuid4()),
        "role": "Regional Manager",
        "accessible_teams": ["Inbound", "Outbound"],
        "accessible_regions": ["UAE"],
        "accessible_functions": [],
        "has_unrestricted_team_access": False,
    }
    res_region_403 = client.get(
        "/api/team-actions/plan-items",
        params={"team": "Inbound", "month": "September", "year": 2026, "region": "EGY"},
    )
    assert res_region_403.status_code == 403


def test_delete_plan_item_custom_and_builtin_tombstone_and_restore(full_db):
    inbound = Team(
        id=uuid.uuid4(),
        name="Inbound",
        db_name="Inbound",
        display_name="Inbound",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    full_db.add(inbound)
    full_db.commit()

    user = _make_user(role="Manager", accessible_teams=["Inbound"], has_unrestricted=False)
    service = TeamActionService(full_db)

    # 1. Custom card save -> delete deactivates & logs AuditLog(operation="DELETE")
    custom_saved = service.save_plan_item(
        {
            "card_id": "team-act-custom-123",
            "team": "Inbound",
            "region": "EGY",
            "month": "September",
            "year": 2026,
            "title": "Custom coaching drill",
        },
        current_user=user,
    )
    deleted_custom = service.delete_plan_item(
        card_id="team-act-custom-123",
        team_name="Inbound",
        region="EGY",
        month="September",
        year=2026,
        current_user=user,
    )
    assert deleted_custom["is_deleted"] is True
    custom_row = full_db.query(Action).filter(Action.id == uuid.UUID(custom_saved["id"])).one()
    assert custom_row.is_active is False
    assert custom_row.status == "Cancelled"
    assert service.list_plan_items("Inbound", "September", 2026, current_user=user, region="EGY") == []
    custom_audit = (
        full_db.query(AuditLog)
        .filter(AuditLog.table_name == "actions", AuditLog.record_id == uuid.UUID(custom_saved["id"]), AuditLog.operation == "DELETE")
        .one()
    )
    assert custom_audit.new_values["is_active"] is False

    # 2. Built-in card delete creates persistent tombstone (is_deleted=True) & logs DELETE audit
    tombstone = service.delete_plan_item(
        card_id="inbound-team-1",
        team_name="Inbound",
        region="EGY",
        month="September",
        year=2026,
        current_user=user,
    )
    assert tombstone["card_id"] == "inbound-team-1"
    assert tombstone["is_deleted"] is True
    listed = service.list_plan_items("Inbound", "September", 2026, current_user=user, region="EGY")
    assert len(listed) == 1
    assert listed[0]["card_id"] == "inbound-team-1"
    assert listed[0]["is_deleted"] is True

    # 3. Re-saving clears is_deleted
    resaved = service.save_plan_item(
        {
            "card_id": "inbound-team-1",
            "team": "Inbound",
            "region": "EGY",
            "month": "September",
            "year": 2026,
            "title": "Restored & updated team plan",
            "status": "Open",
        },
        current_user=user,
    )
    assert resaved["is_deleted"] is False

    # 4. Tombstone + purge_tombstone=True removes tombstone completely
    service.delete_plan_item(
        card_id="inbound-team-1",
        team_name="Inbound",
        region="EGY",
        month="September",
        year=2026,
        current_user=user,
    )
    purged = service.delete_plan_item(
        card_id="inbound-team-1",
        team_name="Inbound",
        region="EGY",
        month="September",
        year=2026,
        current_user=user,
        purge_tombstone=True,
    )
    assert purged["is_deleted"] is False
    assert service.list_plan_items("Inbound", "September", 2026, current_user=user, region="EGY") == []


def test_delete_plan_items_router_enforces_rbac_and_scope(full_db, monkeypatch):
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    from api.routers import team as team_router_module
    from config.database import get_db

    inbound = Team(
        id=uuid.uuid4(),
        name="Inbound",
        db_name="Inbound",
        display_name="Inbound",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    outbound = Team(
        id=uuid.uuid4(),
        name="Outbound",
        db_name="Outbound",
        display_name="Outbound",
        region="UAE",
        team_level="employee",
        is_active=True,
    )
    full_db.add_all([inbound, outbound])
    full_db.commit()

    active_user = {
        "user": {
            "user_id": str(uuid.uuid4()),
            "role": "Viewer",
            "accessible_teams": ["Inbound"],
            "accessible_regions": [],
            "accessible_functions": [],
            "has_unrestricted_team_access": False,
        }
    }
    monkeypatch.setattr(team_router_module, "get_current_user_scope", lambda _db, _req: active_user["user"])

    app = FastAPI()

    @app.middleware("http")
    async def inject_user(request: Request, call_next):
        request.state.user = active_user["user"]
        return await call_next(request)

    app.include_router(team_router_module.router, prefix="/api/team-actions")

    def override_db():
        yield full_db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    # Viewer lacks create_actions permission -> 403
    res_403 = client.delete(
        "/api/team-actions/plan-items/inbound-team-1",
        params={"team": "Inbound", "month": "September", "year": 2026, "region": "EGY"},
    )
    assert res_403.status_code == 403

    # Manager for Outbound fails scope check for Inbound -> 403
    active_user["user"] = {
        "user_id": str(uuid.uuid4()),
        "role": "Manager",
        "accessible_teams": ["Outbound"],
        "accessible_regions": [],
        "accessible_functions": [],
        "has_unrestricted_team_access": False,
    }
    res_scope_403 = client.delete(
        "/api/team-actions/plan-items/inbound-team-1",
        params={"team": "Inbound", "month": "September", "year": 2026, "region": "EGY"},
    )
    assert res_scope_403.status_code == 403

    # Manager for Inbound succeeds + purge_tombstone clears it
    active_user["user"]["accessible_teams"] = ["Inbound"]
    res_del = client.delete(
        "/api/team-actions/plan-items/inbound-team-1",
        params={"team": "Inbound", "month": "September", "year": 2026, "region": "EGY"},
    )
    assert res_del.status_code == 200
    assert res_del.json()["data"]["is_deleted"] is True

    res_purge = client.delete(
        "/api/team-actions/plan-items/inbound-team-1",
        params={
            "team": "Inbound",
            "month": "September",
            "year": 2026,
            "region": "EGY",
            "purge_tombstone": "true",
        },
    )
    assert res_purge.status_code == 200
    assert res_purge.json()["data"]["is_deleted"] is False
