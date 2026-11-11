"""Corrective-action pilot switch and authorized read evidence service (#95).

Rules-only / mocked: no model is started and no production data is touched.
Fixtures are isolated in-memory SQLite rows. The evidence bundle must never
invent a cause, owner, due date, or numerical uplift, must never coerce a
missing value to 0, and must never write to the database.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers.settings import router as settings_router
from config.database import Base, get_db
from models.models import Action, Employee, KPIValue, PerformanceRecord, ProductSetting, Team
from services.ai import feature_gate
from services.ai.corrective_action_evidence import (
    CorrectiveActionEvidenceService,
    build_corrective_action_evidence,
)
from services.ai.feature_gate import (
    AI_CORRECTIVE_ACTION_PILOT_KEY,
    read_ai_corrective_action_pilot_enabled,
    require_ai_corrective_action_pilot_enabled,
)

ADMIN_SCOPE = {"role": "Admin"}
OUT_OF_SCOPE_MANAGER = {"role": "Manager", "accessible_teams": ["Outbound"]}


def _make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _seed_period(db, *, month="September", year=2026):
    """One Inbound employee with two stored KPI rows and one prior action."""
    team = Team(
        id=uuid.uuid4(),
        name="inbound",
        db_name="Inbound",
        display_name="Inbound",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    db.add(team)
    db.flush()
    employee = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-1",
        name="Sara Inbound",
        team_id=team.id,
        region="EGY",
        performance_level="Employee",
        position_name="Agent",
        is_active=True,
    )
    db.add(employee)
    db.flush()
    record = PerformanceRecord(
        id=uuid.uuid4(),
        employee_id=employee.id,
        team_id=team.id,
        month=month,
        year=year,
        performance_level="Employee",
        position_name="Agent",
        region="EGY",
        branch_key=None,
        score=82.0,
        grade="B",
        status="Meets",
    )
    db.add(record)
    db.flush()
    db.add_all(
        [
            KPIValue(
                record_id=record.id,
                record_year=year,
                kpi_key="bookings_count",
                actual_value=30,
                target_value=40,
                achievement_ratio=0.75,
                weight_applied=0.5,
                contribution=0.375,
            ),
            KPIValue(
                record_id=record.id,
                record_year=year,
                kpi_key="upsell",
                actual_value=0,
                target_value=10,
                achievement_ratio=0,
                weight_applied=0.2,
                contribution=0,
            ),
        ]
    )
    db.add(
        Action(
            id=uuid.uuid4(),
            employee_id=employee.id,
            team_id=team.id,
            branch_key=None,
            month=month,
            year=year,
            action_type="Coaching",
            action_text="Coach on closing technique",
            root_cause_note="Secret cause that must not leak",
            status="Open",
            linked_kpi_key="bookings_count",
        )
    )
    db.commit()
    return team, employee, record


def _settings_client(db):
    app = FastAPI()
    app.include_router(settings_router, prefix="/api/settings")

    @app.get("/api/ai/pilot-ping")
    def ping(_gate=Depends(require_ai_corrective_action_pilot_enabled)):
        return {"ok": True}

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Pilot switch
# ---------------------------------------------------------------------------


def test_pilot_is_off_by_default_and_independent_of_ai_chat():
    db = _make_db()
    assert read_ai_corrective_action_pilot_enabled(db) is False
    feature_gate.set_ai_enabled(db, True, None)
    assert read_ai_corrective_action_pilot_enabled(db) is False
    feature_gate.set_ai_corrective_action_pilot_enabled(db, True, None)
    assert read_ai_corrective_action_pilot_enabled(db) is True
    assert feature_gate.read_ai_enabled(db) is True
    feature_gate.set_ai_corrective_action_pilot_enabled(db, False, None)
    assert read_ai_corrective_action_pilot_enabled(db) is False
    assert feature_gate.read_ai_enabled(db) is True
    row = db.query(ProductSetting).filter(ProductSetting.key == AI_CORRECTIVE_ACTION_PILOT_KEY).one()
    assert row.enabled is False


def test_pilot_endpoints_are_admin_only_and_do_not_touch_chat_switch():
    db = _make_db()
    client = _settings_client(db)

    assert client.get("/api/ai/pilot-ping", headers={"X-User-Role": "Admin"}).status_code == 403
    hidden = client.get("/api/settings/ai-corrective-action-pilot", headers={"X-User-Role": "Admin"})
    assert hidden.status_code == 200
    assert hidden.json()["data"]["corrective_action_pilot_enabled"] is False

    denied = client.put(
        "/api/settings/ai-corrective-action-pilot",
        json={"enabled": True},
        headers={"X-User-Role": "Manager"},
    )
    assert denied.status_code == 403

    enabled = client.put(
        "/api/settings/ai-corrective-action-pilot",
        json={"enabled": True},
        headers={"X-User-Role": "Admin", "X-User-Id": "legacy"},
    )
    assert enabled.status_code == 200
    assert enabled.json()["data"]["corrective_action_pilot_enabled"] is True
    assert client.get("/api/ai/pilot-ping", headers={"X-User-Role": "Admin"}).status_code == 200

    assistant = client.get("/api/settings/ai-assistant", headers={"X-User-Role": "Admin"})
    assert assistant.status_code == 200
    assert assistant.json()["data"]["enabled"] is False
    assert assistant.json()["data"]["corrective_action_pilot_enabled"] is True

    # Turning standalone chat on leaves the pilot flag exactly as it was.
    client.put("/api/settings/ai-assistant", json={"enabled": True}, headers={"X-User-Role": "Admin"})
    assert client.get("/api/settings/ai-assistant", headers={"X-User-Role": "Admin"}).json()["data"][
        "corrective_action_pilot_enabled"
    ] is True

    client.put("/api/settings/ai-corrective-action-pilot", json={"enabled": False}, headers={"X-User-Role": "Admin"})
    assert client.get("/api/ai/pilot-ping", headers={"X-User-Role": "Admin"}).status_code == 403


# ---------------------------------------------------------------------------
# Evidence service: employee subject
# ---------------------------------------------------------------------------


def test_employee_evidence_binds_real_kpis_and_preserves_zero():
    db = _make_db()
    _seed_period(db)
    bundle = build_corrective_action_evidence(
        db,
        user_scope=ADMIN_SCOPE,
        employee_id="EMP-1",
        team="Inbound",
        month="September",
        year=2026,
        performance_level="Employee",
    )
    assert bundle["subject"] == "employee"
    assert bundle["employee_id"] == "EMP-1"
    assert bundle["employee_name"] == "Sara Inbound"
    assert bundle["country"] == "EGY"
    assert bundle["function"] == "Call Center"
    assert bundle["team"] == "Inbound"
    assert bundle["position"] == "Agent"
    assert bundle["period"] == {"month": "September", "year": 2026}
    assert bundle["performance_level"] == "Employee"
    assert bundle["read_only"] is True
    assert bundle["insufficient_evidence_reasons"] == []

    by_key = {item["kpi_key"]: item for item in bundle["kpi_items"]}
    bookings = by_key["bookings_count"]
    assert bookings["actual"] == 30.0
    assert bookings["target"] == 40.0
    assert bookings["achievement_percent"] == 75.0
    assert bookings["weight"] == 0.5
    assert bookings["contributes_to_score"] is True
    assert bookings["direction"] is not None
    # A real measured 0.0 is preserved as 0.0, never turned into None.
    upsell = by_key["upsell"]
    assert upsell["actual"] == 0.0
    assert upsell["target"] == 10.0
    assert upsell["achievement_percent"] == 0.0


def test_prior_actions_are_sanitized_and_nothing_is_invented():
    db = _make_db()
    _seed_period(db)
    bundle = build_corrective_action_evidence(
        db,
        user_scope=ADMIN_SCOPE,
        employee_id="EMP-1",
        team="Inbound",
        month="September",
        year=2026,
    )
    assert len(bundle["prior_corrective_actions"]) == 1
    prior = bundle["prior_corrective_actions"][0]
    assert prior["status"] == "Open"
    assert prior["linked_kpi_key"] == "bookings_count"
    assert prior["period"] == {"month": "September", "year": 2026}
    assert prior["action_type"] == "Coaching"
    assert prior["summary"] == "Coaching (Open)"

    dumped = json.dumps(bundle)
    assert "Secret cause that must not leak" not in dumped
    assert "Coach on closing technique" not in dumped
    for forbidden in ("due_date", "owner", "cause", "uplift"):
        assert forbidden not in dumped


def test_evidence_build_writes_nothing():
    db = _make_db()
    _seed_period(db)
    before = (
        db.query(PerformanceRecord).count(),
        db.query(KPIValue).count(),
        db.query(Action).count(),
    )
    build_corrective_action_evidence(
        db,
        user_scope=ADMIN_SCOPE,
        employee_id="EMP-1",
        team="Inbound",
        month="September",
        year=2026,
    )
    build_corrective_action_evidence(
        db,
        user_scope=ADMIN_SCOPE,
        team="Inbound",
        month="September",
        year=2026,
    )
    after = (
        db.query(PerformanceRecord).count(),
        db.query(KPIValue).count(),
        db.query(Action).count(),
    )
    assert before == after == (1, 2, 1)


def test_missing_period_is_reported_not_zeroed():
    db = _make_db()
    _seed_period(db)
    bundle = build_corrective_action_evidence(
        db,
        user_scope=ADMIN_SCOPE,
        employee_id="EMP-1",
        team="Inbound",
        month="October",
        year=2026,
    )
    assert bundle["kpi_items"] == []
    assert "no_performance_record_for_period" in bundle["insufficient_evidence_reasons"]


def test_missing_linked_kpi_is_flagged():
    db = _make_db()
    _seed_period(db)
    bundle = build_corrective_action_evidence(
        db,
        user_scope=ADMIN_SCOPE,
        employee_id="EMP-1",
        team="Inbound",
        month="September",
        year=2026,
        linked_kpi_key="does_not_exist",
    )
    assert bundle["linked_kpi_key"] == "does_not_exist"
    assert "linked_kpi_not_found:does_not_exist" in bundle["insufficient_evidence_reasons"]
    # The other KPIs are still reported; the missing link is not fabricated.
    assert {item["kpi_key"] for item in bundle["kpi_items"]} == {"bookings_count", "upsell"}


def test_out_of_scope_employee_and_team_are_refused():
    db = _make_db()
    _seed_period(db)
    with pytest.raises(PermissionError):
        build_corrective_action_evidence(
            db,
            user_scope=OUT_OF_SCOPE_MANAGER,
            employee_id="EMP-1",
            team="Inbound",
            month="September",
            year=2026,
        )
    with pytest.raises(PermissionError):
        build_corrective_action_evidence(
            db,
            user_scope=OUT_OF_SCOPE_MANAGER,
            team="Inbound",
            month="September",
            year=2026,
        )


def test_invalid_inputs_raise_value_error():
    db = _make_db()
    _seed_period(db)
    with pytest.raises(ValueError):
        build_corrective_action_evidence(
            db, user_scope=ADMIN_SCOPE, employee_id="NOPE", team="Inbound", month="September", year=2026
        )
    with pytest.raises(ValueError):
        build_corrective_action_evidence(
            db, user_scope=ADMIN_SCOPE, team="Inbound", month="September", year=2026, performance_level="Bogus"
        )
    with pytest.raises(ValueError):
        build_corrective_action_evidence(
            db, user_scope=ADMIN_SCOPE, team="Inbound", month="September", year=1999
        )
    with pytest.raises(ValueError):
        build_corrective_action_evidence(db, user_scope=ADMIN_SCOPE, team="", month="September", year=2026)


def test_scoring_basis_comes_only_from_the_periods_own_records():
    db = _make_db()
    _seed_period(db)
    team = db.query(Team).filter(Team.display_name == "Inbound").one()
    employee = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-9",
        name="Nadia Inbound",
        team_id=team.id,
        region="EGY",
        performance_level="Employee",
        position_name="Agent",
        is_active=True,
    )
    db.add(employee)
    db.flush()
    record = PerformanceRecord(
        id=uuid.uuid4(),
        employee_id=employee.id,
        team_id=team.id,
        month="October",
        year=2026,
        performance_level="Employee",
        position_name="Agent",
        region="EGY",
        score=80.0,
        grade="B",
        status="Meets",
        record_payload={"evaluation_basis": {"pinned": True, "version_number": 3, "policy": "employee_ratio"}},
    )
    db.add(record)
    db.flush()
    db.add(
        KPIValue(
            record_id=record.id,
            record_year=2026,
            kpi_key="bookings_count",
            actual_value=28,
            target_value=40,
            achievement_ratio=0.7,
            weight_applied=0.5,
            contribution=0.35,
        )
    )
    db.commit()

    pinned = build_corrective_action_evidence(
        db,
        user_scope=ADMIN_SCOPE,
        employee_id="EMP-9",
        team="Inbound",
        month="October",
        year=2026,
    )
    assert pinned["scoring_basis"] == "pinned team-configuration version 3 (employee_ratio)"
    assert pinned["kpi_items"][0]["actual"] == 28.0

    # No records at all in November, although October's record carries a
    # pinned basis: the basis must not leak across periods.
    empty = build_corrective_action_evidence(
        db,
        user_scope=ADMIN_SCOPE,
        team="Inbound",
        month="November",
        year=2026,
    )
    assert empty["scoring_basis"] is None
    assert "no_performance_record_for_period" in empty["insufficient_evidence_reasons"]


def test_team_subject_reports_every_member_without_picking_a_winner():
    db = _make_db()
    _seed_period(db)
    # A second member with the exact same stored score: a tie is not a winner.
    team = db.query(Team).filter(Team.display_name == "Inbound").one()
    employee2 = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-2",
        name="Omar Inbound",
        team_id=team.id,
        region="EGY",
        performance_level="Employee",
        position_name="Agent",
        is_active=True,
    )
    db.add(employee2)
    db.flush()
    record2 = PerformanceRecord(
        id=uuid.uuid4(),
        employee_id=employee2.id,
        team_id=team.id,
        month="September",
        year=2026,
        performance_level="Employee",
        position_name="Agent",
        region="EGY",
        score=82.0,
        grade="B",
        status="Meets",
    )
    db.add(record2)
    db.flush()
    db.add(
        KPIValue(
            record_id=record2.id,
            record_year=2026,
            kpi_key="bookings_count",
            actual_value=30,
            target_value=40,
            achievement_ratio=0.75,
            weight_applied=0.5,
            contribution=0.375,
        )
    )
    db.commit()

    bundle = CorrectiveActionEvidenceService(db).build(
        user_scope=ADMIN_SCOPE,
        team="Inbound",
        month="September",
        year=2026,
    )
    assert bundle["subject"] == "team"
    assert bundle["employee_id"] is None
    assert bundle["country"] == "EGY"
    assert {item["employee_id"] for item in bundle["kpi_items"]} == {"EMP-1", "EMP-2"}
    assert "winner" not in json.dumps(bundle)
