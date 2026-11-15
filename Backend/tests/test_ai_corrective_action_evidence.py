"""Corrective-action pilot switch and authorized read evidence service (#95).

Rules-only / mocked: no model is started and no production data is touched.
Fixtures are isolated in-memory SQLite rows. The evidence bundle must never
invent a cause, owner, due date, or numerical uplift, must never coerce a
missing value to 0, and must never write to the database.
"""

from __future__ import annotations

import datetime as dt
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
    MONTH_MAP,
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
            created_at=dt.datetime(year, MONTH_MAP.get(str(month).strip().casefold(), 1), 1, 0, 0, tzinfo=dt.timezone.utc),
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


def _add_month_record(
    db,
    *,
    employee: Employee,
    team: Team,
    month: str,
    year: int,
    score: float,
    kpis: list[tuple[str, float | None, float | None, float | None]],
    region: str = "EGY",
):
    rec = PerformanceRecord(
        id=uuid.uuid4(),
        employee_id=employee.id,
        team_id=team.id,
        month=month,
        year=year,
        performance_level="Employee",
        position_name="Agent",
        region=region,
        score=score,
        grade="C" if score < 85 else "B",
        status="Below" if score < 85 else "Meets",
    )
    db.add(rec)
    db.flush()
    w = 1.0 / max(1, len(kpis))
    for key, actual, target, ratio in kpis:
        db.add(
            KPIValue(
                record_id=rec.id,
                record_year=year,
                kpi_key=key,
                actual_value=actual,
                target_value=target,
                achievement_ratio=ratio,
                weight_applied=w,
                contribution=(ratio * w) if ratio is not None else None,
            )
        )
    db.flush()
    return rec


def test_employee_multimonth_trend_summary_directions_and_weak_kpis_ranking():
    db = _make_db()
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
    emp_dec = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-DEC",
        name="Declining Agent",
        team_id=team.id,
        region="EGY",
        performance_level="Employee",
        position_name="Agent",
        is_active=True,
    )
    emp_imp = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-IMP",
        name="Improving Agent",
        team_id=team.id,
        region="EGY",
        performance_level="Employee",
        position_name="Agent",
        is_active=True,
    )
    emp_stb = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-STB",
        name="Stable Agent",
        team_id=team.id,
        region="EGY",
        performance_level="Employee",
        position_name="Agent",
        is_active=True,
    )
    db.add_all([emp_dec, emp_imp, emp_stb])
    db.flush()

    # Declining: July 86.0% -> Aug 79.0% -> Sep 62.5%; two weak KPIs (upsell 50% ach worse than bookings 75% ach)
    for m, bk, up in [
        ("July", 38.0, 7.7),
        ("August", 34.0, 7.3),
        ("September", 30.0, 5.0),
    ]:
        sc = round(((bk / 40.0) * 0.5 + (up / 10.0) * 0.5) * 100.0, 2)
        _add_month_record(
            db,
            employee=emp_dec,
            team=team,
            month=m,
            year=2026,
            score=sc,
            kpis=[
                ("bookings_count", bk, 40.0, bk / 40.0),
                ("upsell", up, 10.0, up / 10.0),
            ],
        )

    # Improving: Aug 70.0% -> Sep 85.0%
    for m, bk in [("August", 28.0), ("September", 34.0)]:
        _add_month_record(
            db,
            employee=emp_imp,
            team=team,
            month=m,
            year=2026,
            score=round((bk / 40.0) * 100.0, 2),
            kpis=[("bookings_count", bk, 40.0, bk / 40.0)],
        )

    # Stable: Aug 80.0% -> Sep 80.2%
    for m, bk in [("August", 32.0), ("September", 32.08)]:
        _add_month_record(
            db,
            employee=emp_stb,
            team=team,
            month=m,
            year=2026,
            score=round((bk / 40.0) * 100.0, 2),
            kpis=[("bookings_count", bk, 40.0, bk / 40.0)],
        )
    db.commit()

    dec_bundle = build_corrective_action_evidence(
        db, user_scope=ADMIN_SCOPE, employee_id="EMP-DEC", team="Inbound", month="September", year=2026
    )
    dec_trend = dec_bundle["trend_summary"]
    assert dec_trend["measured_periods"] == 3
    assert dec_trend["current_score"] == 62.5
    assert dec_trend["previous_score"] == 79.0
    assert dec_trend["score_delta"] == pytest.approx(-16.5)
    assert dec_trend["score_direction"] == "declining"
    assert [k["kpi_key"] for k in dec_trend["weak_kpis"]] == ["upsell", "bookings_count"]
    assert dec_trend["weak_kpis"][0]["months_below_target"] == 3

    imp_bundle = build_corrective_action_evidence(
        db, user_scope=ADMIN_SCOPE, employee_id="EMP-IMP", team="Inbound", month="September", year=2026
    )
    assert imp_bundle["trend_summary"]["score_direction"] == "improving"

    stb_bundle = build_corrective_action_evidence(
        db, user_scope=ADMIN_SCOPE, employee_id="EMP-STB", team="Inbound", month="September", year=2026
    )
    assert stb_bundle["trend_summary"]["score_direction"] == "stable"

    single_bundle = build_corrective_action_evidence(
        db, user_scope=ADMIN_SCOPE, employee_id="EMP-DEC", team="Inbound", month="July", year=2026
    )
    assert single_bundle["trend_summary"]["measured_periods"] == 1
    assert single_bundle["trend_summary"]["score_direction"] == "single_period"


def test_trend_summary_preserves_none_vs_zero_and_blocks_future_leakage():
    db = _make_db()
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
    emp = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-GAP",
        name="Gap Agent",
        team_id=team.id,
        region="EGY",
        performance_level="Employee",
        position_name="Agent",
        is_active=True,
    )
    emp_noprev = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-NOPREV",
        name="NoPrev Agent",
        team_id=team.id,
        region="EGY",
        performance_level="Employee",
        position_name="Agent",
        is_active=True,
    )
    db.add_all([emp, emp_noprev])
    db.flush()

    # August has genuine 0.0 upsell (and no bookings_count); September has bookings_count=0.0; October is future
    _add_month_record(
        db,
        employee=emp,
        team=team,
        month="August",
        year=2026,
        score=0.0,
        kpis=[("upsell", 0.0, 10.0, 0.0)],
    )
    _add_month_record(
        db,
        employee=emp,
        team=team,
        month="September",
        year=2026,
        score=10.0,
        kpis=[("upsell", 2.0, 10.0, 0.2), ("bookings_count", 0.0, 40.0, 0.0)],
    )
    _add_month_record(
        db,
        employee=emp,
        team=team,
        month="October",
        year=2026,
        score=99.0,
        kpis=[("upsell", 15.0, 10.0, 1.0)],
    )
    # EMP-NOPREV: only September (no prior month record) -> previous_score MUST be None, never 0
    _add_month_record(
        db,
        employee=emp_noprev,
        team=team,
        month="September",
        year=2026,
        score=70.0,
        kpis=[("bookings_count", 28.0, 40.0, 0.7)],
    )
    db.commit()

    bundle = build_corrective_action_evidence(
        db, user_scope=ADMIN_SCOPE, employee_id="EMP-GAP", team="Inbound", month="September", year=2026
    )
    trend = bundle["trend_summary"]
    assert trend["current_score"] == 10.0
    assert trend["previous_score"] == 0.0
    assert trend["measured_periods"] == 2  # October 99.0 must NOT leak into September
    assert trend["kpi_trends"]["upsell"]["previous_actual"] == 0.0  # genuine 0.0 preserved
    assert trend["kpi_trends"]["bookings_count"]["previous_actual"] is None
    assert any(k["kpi_key"] == "bookings_count" and k["actual"] == 0.0 for k in trend["weak_kpis"])

    noprev_bundle = build_corrective_action_evidence(
        db, user_scope=ADMIN_SCOPE, employee_id="EMP-NOPREV", team="Inbound", month="September", year=2026
    )
    assert noprev_bundle["trend_summary"]["current_score"] == 70.0
    assert noprev_bundle["trend_summary"]["previous_score"] is None
    assert noprev_bundle["trend_summary"]["score_delta"] is None


def test_trend_summary_respects_region_isolation_for_shared_team_name():
    db = _make_db()
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
    db.add_all([egy_team, uae_team])
    db.flush()
    egy_emp = Employee(
        id=uuid.uuid4(),
        employee_id="EGY-1",
        name="Egypt Agent",
        team_id=egy_team.id,
        region="EGY",
        performance_level="Employee",
        position_name="Agent",
        is_active=True,
    )
    uae_emp = Employee(
        id=uuid.uuid4(),
        employee_id="UAE-1",
        name="UAE Agent",
        team_id=uae_team.id,
        region="UAE",
        performance_level="Employee",
        position_name="Agent",
        is_active=True,
    )
    db.add_all([egy_emp, uae_emp])
    db.flush()

    _add_month_record(
        db,
        employee=egy_emp,
        team=egy_team,
        month="August",
        year=2026,
        score=50.0,
        kpis=[("bookings_count", 20.0, 40.0, 0.5)],
        region="EGY",
    )
    _add_month_record(
        db,
        employee=egy_emp,
        team=egy_team,
        month="September",
        year=2026,
        score=55.0,
        kpis=[("bookings_count", 22.0, 40.0, 0.55)],
        region="EGY",
    )
    _add_month_record(
        db,
        employee=uae_emp,
        team=uae_team,
        month="September",
        year=2026,
        score=87.5,
        kpis=[("bookings_count", 35.0, 40.0, 0.875)],
        region="UAE",
    )
    db.commit()

    uae_scope = {"role": "Regional Manager", "accessible_regions": ["UAE"], "accessible_teams": ["Re-Submission"]}
    uae_bundle = build_corrective_action_evidence(
        db, user_scope=uae_scope, team="Re-Submission", month="September", year=2026
    )
    assert uae_bundle["country"] == "UAE"
    assert {item["employee_id"] for item in uae_bundle["kpi_items"]} == {"UAE-1"}
    assert uae_bundle["trend_summary"]["measured_periods"] == 1
    assert uae_bundle["trend_summary"]["current_score"] == 87.5


def test_team_prior_actions_handle_duplicate_team_display_names_and_cohort_plan_rows():
    """Shared Team display_name (employee + management) and cohort-plan rows never raise MultipleResultsFound."""
    db = _make_db()
    emp_team = Team(
        id=uuid.uuid4(),
        name="inbound",
        db_name="Inbound",
        display_name="Inbound",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    mgmt_team = Team(
        id=uuid.uuid4(),
        name="inbound management",
        db_name="Inbound Management",
        display_name="Inbound",
        region="EGY",
        team_level="management",
        is_active=True,
    )
    db.add_all([emp_team, mgmt_team])
    db.flush()

    emp = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-DUP-1",
        name="Agent One",
        team_id=emp_team.id,
        region="EGY",
        performance_level="Employee",
        position_name="Agent",
        is_active=True,
    )
    db.add(emp)
    db.flush()

    record = PerformanceRecord(
        id=uuid.uuid4(),
        employee_id=emp.id,
        team_id=emp_team.id,
        month="September",
        year=2026,
        performance_level="Employee",
        position_name="Agent",
        region="EGY",
        branch_key=None,
        score=76.0,
        grade="C",
        status="Below",
        record_payload={"evaluation_basis": {"pinned": True, "version_number": 4, "policy": "employee_ratio"}},
    )
    db.add(record)
    db.flush()
    db.add(
        KPIValue(
            record_id=record.id,
            record_year=2026,
            kpi_key="Attendance",
            actual_value=68.2,
            target_value=75.0,
            achievement_ratio=0.909,
            weight_applied=0.3,
            contribution=0.2727,
        )
    )
    db.add_all(
        [
            # Pre-existing team action with employee_id=None and real linked_kpi_key
            Action(
                id=uuid.uuid4(),
                employee_id=None,
                team_id=emp_team.id,
                month="August",
                year=2026,
                created_at=dt.datetime(2026, 8, 5, tzinfo=dt.timezone.utc),
                action_type="Team Action",
                action_text="Shift overlap coaching",
                status="Open",
                linked_kpi_key="Attendance",
                evidence_reference="cohort-plan:team-act-inb-3",
                is_active=True,
            ),
            # Presentation-only cohort-plan row WITHOUT linked_kpi_key -> skipped
            Action(
                id=uuid.uuid4(),
                employee_id=None,
                team_id=emp_team.id,
                month="August",
                year=2026,
                created_at=dt.datetime(2026, 8, 6, tzinfo=dt.timezone.utc),
                action_type="Team Action",
                action_text="Placeholder cohort card",
                status="Open",
                linked_kpi_key=None,
                evidence_reference="cohort-plan:team-act-inb-0",
                is_active=True,
            ),
            # Inactive action -> skipped
            Action(
                id=uuid.uuid4(),
                employee_id=None,
                team_id=emp_team.id,
                month="August",
                year=2026,
                created_at=dt.datetime(2026, 8, 7, tzinfo=dt.timezone.utc),
                action_type="Coaching",
                action_text="Deactivated action",
                status="Cancelled",
                linked_kpi_key="AHT",
                is_active=False,
            ),
        ]
    )
    db.commit()

    bundle = build_corrective_action_evidence(
        db, user_scope=ADMIN_SCOPE, employee_id=None, team="Inbound", month="September", year=2026
    )
    assert bundle["subject"] == "team"
    assert bundle["scoring_basis"] == "pinned team-configuration version 4 (employee_ratio)"
    assert len(bundle["prior_corrective_actions"]) == 1
    assert bundle["prior_corrective_actions"][0]["linked_kpi_key"] == "Attendance"
    assert bundle["prior_corrective_actions"][0]["action_type"] == "Team Action"


def test_duplicate_employee_codes_prefer_active_row_without_multiple_results_found():
    """Duplicate Employee.employee_id rows resolve deterministically without raising MultipleResultsFound."""
    from sqlalchemy import text as sa_text

    db = _make_db()
    # Simulate legacy production schema where employee_id lacked a unique index
    db.execute(sa_text("DROP TABLE employees"))
    db.execute(
        sa_text(
            """
            CREATE TABLE employees (
                id VARCHAR(32) PRIMARY KEY,
                employee_id VARCHAR(50) NOT NULL,
                name VARCHAR(255) NOT NULL,
                team_id VARCHAR(32) NOT NULL,
                region VARCHAR(10) NOT NULL,
                performance_level VARCHAR(20) NOT NULL,
                position_name VARCHAR(255),
                is_active BOOLEAN NOT NULL,
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        )
    )
    db.commit()

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

    inactive_emp = Employee(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        employee_id="EMP-DUP",
        name="Legacy Inactive",
        team_id=team.id,
        region="EGY",
        performance_level="Employee",
        position_name="Agent",
        is_active=False,
    )
    active_emp = Employee(
        id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        employee_id="EMP-DUP",
        name="Active Duplicate",
        team_id=team.id,
        region="EGY",
        performance_level="Employee",
        position_name="Agent",
        is_active=True,
    )
    db.add_all([inactive_emp, active_emp])
    db.flush()

    rec = PerformanceRecord(
        id=uuid.uuid4(),
        employee_id=active_emp.id,
        team_id=team.id,
        month="September",
        year=2026,
        performance_level="Employee",
        position_name="Agent",
        region="EGY",
        score=70.0,
        grade="C",
        status="Below",
    )
    db.add(rec)
    db.flush()
    db.add(
        KPIValue(
            record_id=rec.id,
            record_year=2026,
            kpi_key="AHT",
            actual_value=3.1,
            target_value=2.6,
            achievement_ratio=0.838,
            weight_applied=0.3,
            contribution=0.251,
        )
    )
    db.commit()

    bundle = build_corrective_action_evidence(
        db, user_scope=ADMIN_SCOPE, employee_id="EMP-DUP", team="Inbound", month="September", year=2026
    )
    assert bundle["subject"] == "employee"
    assert bundle["employee_name"] == "Active Duplicate"
    assert len(bundle["kpi_items"]) == 1


def test_normalize_kpi_values_for_unit_scales_percent_ratios_and_leaves_non_percent_untouched():
    from services.ai.corrective_action_evidence import normalize_kpi_values_for_unit

    items = [
        {"kpi_key": "Quality", "display_name": "Quality Score", "actual": 0.92, "target": 0.95, "unit": "%"},
        {"kpi_key": "CSAT", "display_name": "CSAT", "actual": 0.96, "target": 0.98, "unit": "percent"},
        {"kpi_key": "AbandonRate", "display_name": "Abandon Rate", "actual": 0.0098, "target": 0.01, "unit": "%"},
        {"kpi_key": "NoTargetPct", "display_name": "No Target Pct", "actual": 0.88, "target": None, "unit": "percentage"},
        {"kpi_key": "Bookings", "display_name": "Bookings", "actual": 1.0, "target": 1.0, "unit": "count"},
        {"kpi_key": "Spend", "display_name": "Spend", "actual": 0.85, "target": 1.0, "unit": "AED"},
        {"kpi_key": "AHT", "display_name": "AHT", "actual": 0.95, "target": 1.0, "unit": "min"},
        {"kpi_key": "Assessment", "display_name": "Assessment", "actual": 0.8, "target": 1.0, "unit": "score"},
    ]
    normalized = normalize_kpi_values_for_unit(
        items,
        historical_targets={"NoTargetPct": [0.95]},
    )
    by_key = {row["kpi_key"]: row for row in normalized}
    assert (by_key["Quality"]["actual"], by_key["Quality"]["target"]) == (92.0, 95.0)
    assert (by_key["CSAT"]["actual"], by_key["CSAT"]["target"]) == (96.0, 98.0)
    assert (by_key["AbandonRate"]["actual"], by_key["AbandonRate"]["target"]) == (0.98, 1.0)
    assert by_key["NoTargetPct"]["actual"] == 88.0
    # Non-percentage units are never scaled by magnitude
    assert (by_key["Bookings"]["actual"], by_key["Bookings"]["target"]) == (1.0, 1.0)
    assert (by_key["Spend"]["actual"], by_key["Spend"]["target"]) == (0.85, 1.0)
    assert (by_key["AHT"]["actual"], by_key["AHT"]["target"]) == (0.95, 1.0)
    assert (by_key["Assessment"]["actual"], by_key["Assessment"]["target"]) == (0.8, 1.0)


def test_observation_status_classifies_missing_unverified_zero_and_recorded_zero(db=None):
    from services.ai.corrective_action_evidence import classify_kpi_observation

    # 1. Missing when raw_data has A.QualityScore=None even if legacy coerced actual=0.0
    status, actual, reason, note = classify_kpi_observation(
        kpi_key="Quality",
        display_name="Quality Score",
        actual=0.0,
        direction="higher_better",
        weight=0.3,
        contributes_to_score=True,
        raw_data={"A.QualityScore": None, "A.Attend%": 0.95},
    )
    assert status == "missing"
    assert actual is None
    assert reason == "missing_source_value_for_kpi:Quality"
    assert note and "source record" in note.lower()

    # 2. Unverified zero: audit/survey KPI with 0 and no positive sample/audit denominator
    status2, actual2, reason2, note2 = classify_kpi_observation(
        kpi_key="Quality",
        display_name="Quality Score",
        actual=0.0,
        direction="higher_better",
        weight=0.3,
        contributes_to_score=True,
        raw_data={"A.QualityScore": 0},
    )
    assert status2 == "unverified_zero"
    assert actual2 == 0.0
    assert reason2 == "unverified_zero_for_kpi:Quality"
    assert note2 and "verify" in note2.lower()

    # 3. Recorded zero: audit KPI backed by positive sample/audit denominator
    status3, actual3, reason3, _ = classify_kpi_observation(
        kpi_key="Quality",
        display_name="Quality Score",
        actual=0.0,
        direction="higher_better",
        weight=0.3,
        contributes_to_score=True,
        raw_data={"A.QualityScore": 0, "AuditCount": 5},
    )
    assert status3 == "recorded_zero"
    assert actual3 == 0.0
    assert reason3 is None

    # 4. Recorded zero: Phase 4 CA-03 operational Attendance 0% with weight > 0 and no missing marker
    status4, actual4, reason4, _ = classify_kpi_observation(
        kpi_key="Attendance",
        display_name="Attendance Rate",
        actual=0.0,
        direction="higher_better",
        weight=0.7,
        contributes_to_score=True,
        raw_data={},
    )
    assert status4 == "recorded_zero"
    assert actual4 == 0.0
    assert reason4 is None

    # 5. Unverified zero: higher_better with weight == 0
    status5, actual5, reason5, _ = classify_kpi_observation(
        kpi_key="Booking",
        display_name="Booking Rate",
        actual=0.0,
        direction="higher_better",
        weight=0.0,
        contributes_to_score=False,
        raw_data={},
    )
    assert status5 == "unverified_zero"
    assert actual5 == 0.0
    assert reason5 == "unverified_zero_for_kpi:Booking"


def test_non_adjacent_trend_metadata_historical_scaling_and_projected_lift():
    db = _make_db()
    team = Team(
        id=uuid.uuid4(),
        name="inbound",
        db_name="Inbound",
        display_name="Inbound",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    emp = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-TREND-GAP",
        name="Trend Gap Agent",
        team_id=team.id,
        region="EGY",
        performance_level="Employee",
        position_name="Agent",
        is_active=True,
    )
    db.add_all([team, emp])
    db.flush()

    # May 2026 (0.92/0.95 ratio scale -> 89.8), Aug 2026 (88/95 -> 89.6), Sep 2026 MISSING, Oct 2026 (70/95 -> 76.7)
    periods_data = [
        ("May", 2026, 89.8, 0.92, 0.95, 0.968, 86.8, 0.868),
        ("August", 2026, 89.6, 88.0, 95.0, 0.926, 88.314, 0.88314),
        ("October", 2026, 76.7, 70.0, 95.0, 0.737, 77.986, 0.77986),
    ]
    for m, y, score, qual_actual, qual_target, qual_ratio, att_actual, att_ratio in periods_data:
        rec = PerformanceRecord(
            id=uuid.uuid4(),
            employee_id=emp.id,
            team_id=team.id,
            month=m,
            year=y,
            performance_level="Employee",
            position_name="Agent",
            region="EGY",
            score=score,
            grade="B" if score >= 80 else "C",
            status="Meets" if score >= 80 else "Below",
            record_payload={"raw_data": {"AuditCount": 10}},
        )
        db.add(rec)
        db.flush()
        db.add_all(
            [
                KPIValue(
                    record_id=rec.id,
                    record_year=y,
                    kpi_key="Quality",
                    actual_value=qual_actual,
                    target_value=qual_target,
                    achievement_ratio=qual_ratio,
                    weight_applied=0.30,
                    contribution=qual_ratio * 0.30,
                ),
                KPIValue(
                    record_id=rec.id,
                    record_year=y,
                    kpi_key="Attendance",
                    actual_value=att_actual,
                    target_value=100.0,
                    achievement_ratio=att_ratio,
                    weight_applied=0.70,
                    contribution=att_ratio * 0.70,
                ),
                KPIValue(
                    record_id=rec.id,
                    record_year=y,
                    kpi_key="DiagnosticNote",
                    actual_value=1.0,
                    target_value=4.0,
                    achievement_ratio=0.25,
                    weight_applied=0.0,
                    contribution=0.0,
                ),
            ]
        )
    db.commit()

    bundle = build_corrective_action_evidence(
        db, user_scope=ADMIN_SCOPE, employee_id="EMP-TREND-GAP", team="Inbound", month="October", year=2026
    )
    trend = bundle["trend_summary"]
    assert trend["previous_period"] == "August 2026"
    assert trend["previous_is_adjacent"] is False
    assert trend["missing_intermediate_periods"] == ["September 2026"]
    assert trend["window_start_period"] == "May 2026"
    assert trend["window_start_score"] == 89.8
    assert trend["score_delta"] == -12.9
    assert trend["window_delta"] == -13.1

    by_key = {item["kpi_key"]: item for item in bundle["kpi_items"]}
    qual = by_key["Quality"]
    assert qual["actual"] == 70.0
    assert qual["target"] == 95.0
    assert qual["previous_actual"] == 88.0
    assert qual["previous_period"] == "August 2026"
    assert qual["contributes_to_score"] is True
    assert qual["projected_agent_score_lift"] == round((1.0 - 0.737) * 30.0, 2)

    diag = by_key["DiagnosticNote"]
    assert diag["contributes_to_score"] is False
    assert diag["projected_agent_score_lift"] is None
    assert bundle["team_headcount"] == 1

