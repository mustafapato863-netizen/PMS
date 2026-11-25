"""End-to-end wiring tests for User-Aware 360° Agent Coach (P0/P1 verification)."""

from __future__ import annotations

import uuid
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers import router as api_router
from config.database import Base, get_db
from models.ai_schemas import SessionFilterContext
from models.models import Employee, KPIValue, PerformanceRecord, ProductSetting, Team, User
from services.ai import feature_gate
from services.ai.identity_service import PersonaTier, build_passport
from services.ai.tool_registry import DeterministicToolRegistry, ToolExecutionContext
from services.ai.usage_budget import AiBudgetExceededError, check_user_daily_budget
from services.ai.user_memory_service import UserMemoryService


def _setup_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    return db


def _seed_agent_and_data(db):
    team = Team(id=uuid.uuid4(), name="Inbound", db_name="Inbound", display_name="Inbound", is_active=True)
    db.add(team)
    db.flush()

    emp = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-360",
        name="Sara Coach",
        team_id=team.id,
        region="UAE",
        position_name="Agent",
        is_active=True,
    )
    db.add(emp)
    db.flush()

    user = User(
        id=uuid.uuid4(),
        username="sara_agent",
        email="sara@example.com",
        password_hash="x",
        role="Agent",
        employee_id="EMP-360",
        is_active=True,
    )
    db.add(user)

    # Seed 5 peers in same position + branch for privacy-safe cohort benchmark
    for idx in range(5):
        peer_emp = Employee(
            id=uuid.uuid4(),
            employee_id=f"EMP-P{idx}",
            name=f"Peer {idx}",
            team_id=team.id,
            region="UAE",
            position_name="Agent",
            is_active=True,
        )
        db.add(peer_emp)
        db.flush()
        db.add(
            PerformanceRecord(
                id=uuid.uuid4(),
                year=2026,
                month="October",
                employee_id=peer_emp.id,
                team_id=team.id,
                position_name="Agent",
                region="UAE",
                branch_key="dubai",
                score=75.0 + idx * 3.0,
                grade="C",
                status="Meets",
            )
        )

    rec = PerformanceRecord(
        id=uuid.uuid4(),
        year=2026,
        month="October",
        employee_id=emp.id,
        team_id=team.id,
        position_name="Agent",
        region="UAE",
        branch_key="dubai",
        score=82.5,
        grade="C",
        status="Meets",
    )
    db.add(rec)
    db.flush()

    db.add(
        KPIValue(
            id=uuid.uuid4(),
            record_id=rec.id,
            record_year=2026,
            kpi_key="booking_rate",
            actual_value=24.0,
            target_value=30.0,
            achievement_ratio=0.80,
            weight_applied=0.60,
            contribution=48.0,
        )
    )
    db.add(
        KPIValue(
            id=uuid.uuid4(),
            record_id=rec.id,
            record_year=2026,
            kpi_key="rejection_rate",
            actual_value=12.0,
            target_value=10.0,
            achievement_ratio=0.8333,
            weight_applied=0.40,
            contribution=33.33,
        )
    )
    db.add(ProductSetting(key="ai_enabled", enabled=True))
    db.add(ProductSetting(key="ai_access_tier", enabled=True, value_str="all_authenticated_users"))
    db.commit()
    return user, emp


def _build_client(db, monkeypatch, *, scope_override: dict):
    from api.routers import agent_360, ai_memory

    monkeypatch.setattr(agent_360, "require_authenticated_scope", lambda _db, _req: scope_override)
    monkeypatch.setattr(ai_memory, "require_authenticated_scope", lambda _db, _req: scope_override)

    app = FastAPI()
    app.include_router(api_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_passport_resolves_employee_pk_and_executive_tier():
    db = _setup_db()
    user, emp = _seed_agent_and_data(db)

    passport = build_passport({"user_id": str(user.id), "role": "Agent", "employee_id": "EMP-360"}, db=db)
    assert passport.persona_tier == PersonaTier.SELF_ONLY
    assert passport.employee_code == "EMP-360"
    assert passport.employee_pk == str(emp.id)
    assert passport.is_linked_employee is True

    exec_passport = build_passport({"user_id": "exec-1", "role": "Executive"}, db=db)
    assert exec_passport.persona_tier == PersonaTier.GLOBAL_EXEC


def test_agent_360_and_what_if_endpoints_live_and_scoped(monkeypatch):
    db = _setup_db()
    user, _emp = _seed_agent_and_data(db)
    agent_scope = {"user_id": str(user.id), "role": "Agent", "employee_id": "EMP-360", "is_self_only": True}
    client = _build_client(db, monkeypatch, scope_override=agent_scope)

    # Anonymous rejected with 401 even under all_authenticated_users
    anon = client.get("/api/ai/agent-360")
    assert anon.status_code == 401

    # Self-scoped Agent gets real per-KPI breakdown + privacy-safe cohort
    resp = client.get("/api/ai/agent-360", headers={"X-User-Role": "Agent"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["employee_code"] == "EMP-360"
    assert len(data["kpi_scores"]) == 2
    assert data["cohort"] is not None
    assert data["cohort"]["cohort_size"] >= 5
    assert "min" not in data["cohort"] and "max" not in data["cohort"]

    # Self-only cannot peek at another employee
    denied = client.get("/api/ai/agent-360?employee_code=EMP-P0", headers={"X-User-Role": "Agent"})
    assert denied.status_code == 403

    # Deterministic What-If simulation works via POST /api/ai/agent-360/what-if
    sim = client.post(
        "/api/ai/agent-360/what-if",
        headers={"X-User-Role": "Agent"},
        json={"kpi_name": "Booking Rate", "improvement_pct": 6.0},
    )
    assert sim.status_code == 200, sim.text
    sim_data = sim.json()
    assert sim_data["projected_score"] > sim_data["current_score"]
    assert sim_data["capped"] is True  # 24 + 6 = 30 -> 100% cap


def test_memory_endpoints_self_service_and_admin_guard(monkeypatch):
    db = _setup_db()
    user, _emp = _seed_agent_and_data(db)
    agent_scope = {"user_id": str(user.id), "role": "Agent", "employee_id": "EMP-360", "is_self_only": True}
    client = _build_client(db, monkeypatch, scope_override=agent_scope)

    # Self-service PUT / GET / DELETE /api/ai/memory/me
    put_res = client.put(
        "/api/ai/memory/me",
        headers={"X-User-Role": "Agent"},
        json={"preferences": {"detail_level": "brief", "communication_style": "formal"}},
    )
    assert put_res.status_code == 200, put_res.text
    assert put_res.json()["memory"]["preferences"]["detail_level"] == "brief"

    get_res = client.get("/api/ai/memory/me", headers={"X-User-Role": "Agent"})
    assert get_res.status_code == 200
    assert get_res.json()["memory"]["preferences"]["communication_style"] == "formal"

    # Non-Admin MUST be forbidden from admin memory endpoints even when tier == all_authenticated_users
    admin_peek = client.get(f"/api/ai/memory/{user.id}", headers={"X-User-Role": "Agent"})
    assert admin_peek.status_code == 403
    admin_stats = client.get("/api/ai/memory/", headers={"X-User-Role": "Agent"})
    assert admin_stats.status_code == 403

    del_res = client.delete("/api/ai/memory/me", headers={"X-User-Role": "Agent"})
    assert del_res.status_code == 200
    assert del_res.json()["cleared"] is True


def test_tool_registry_wires_scoring_rules_and_what_if_for_self_only():
    db = _setup_db()
    user, _emp = _seed_agent_and_data(db)
    scope = {"user_id": str(user.id), "role": "Agent", "employee_id": "EMP-360", "is_self_only": True}
    registry = DeterministicToolRegistry(ToolExecutionContext(db=db, scope=scope, session_state=SessionFilterContext()))

    rules_res = registry.execute_model_led_tool("explain_scoring_rules_and_targets", {})
    assert rules_res.tool_name == "explain_scoring_rules_and_targets"
    assert rules_res.digest["achievement_cap"] == 1.0
    assert "A" in rules_res.digest["grade_thresholds"]

    sim_res = registry.execute_model_led_tool(
        "simulate_kpi_improvement",
        {"kpi_name": "Booking Rate", "improvement_pct": 3.0},
    )
    assert sim_res.tool_name == "simulate_kpi_improvement"
    assert sim_res.digest["score_delta"] > 0


def test_memory_extraction_persists_and_escapes_xml():
    db = _setup_db()
    user, _emp = _seed_agent_and_data(db)
    svc = UserMemoryService(db)

    assert not svc.extract_and_persist_turn_signals(str(user.id), "Please keep it brief", team="Inbound")
    assert not svc.extract_and_persist_turn_signals(str(user.id), "Remember that I don't like brief replies")
    assert svc.load_personalization(str(user.id)) is None
    ok = svc.extract_and_persist_turn_signals(
        str(user.id),
        "Remember that I prefer brief replies.",
        topic="score",
        team="Inbound",
        kpi="Booking Rate",
    )
    assert ok is True
    loaded = svc.load_memory(str(user.id))
    assert loaded is not None
    assert loaded["preferences"]["detail_level"] == "brief"
    assert not loaded["query_patterns"]
    assert svc.load_personalization(str(user.id)) == {"preferences": {"detail_level": "brief"}}

    xml_text = svc.get_memory_text(loaded)
    assert "<VERIFIED_USER_MEMORY>" in xml_text
    assert "<script>" not in xml_text
    assert "Inbound" not in xml_text


def test_tiered_usage_budget_enforces_self_only_cap(monkeypatch):
    monkeypatch.delenv("PMS_AI_DAILY_USER_REQUEST_LIMIT", raising=False)
    monkeypatch.delenv("PMS_AI_DAILY_USER_TOKEN_LIMIT", raising=False)
    monkeypatch.setenv("PMS_AI_ENFORCE_TIER_BUDGETS", "true")
    uid = f"agent-budget-{uuid.uuid4()}"

    # When tier budgets are explicitly enabled, Agent gets 20 turns/day cap
    for _ in range(20):
        check_user_daily_budget(uid, "Agent", increment_request=True, access_tier="all_authenticated_users")

    try:
        check_user_daily_budget(uid, "Agent", increment_request=True, access_tier="all_authenticated_users")
        assert False, "Expected AiBudgetExceededError on 21st turn"
    except AiBudgetExceededError as exc:
        assert exc.reason == "daily_request_limit"


def test_usage_budget_is_unlimited_by_default(monkeypatch):
    monkeypatch.delenv("PMS_AI_DAILY_USER_REQUEST_LIMIT", raising=False)
    monkeypatch.delenv("PMS_AI_DAILY_USER_TOKEN_LIMIT", raising=False)
    monkeypatch.delenv("PMS_AI_ENFORCE_TIER_BUDGETS", raising=False)
    uid = f"unlimited-user-{uuid.uuid4()}"

    for _ in range(250):
        check_user_daily_budget(uid, "Admin", increment_request=True, access_tier="all_authenticated_users")
        check_user_daily_budget(uid, "Agent", increment_request=True, access_tier="all_authenticated_users")


def test_pass1_identity_context_injects_passport_and_memory_within_cap():
    from services.ai.router import build_pass1_identity_context

    scope = {
        "user_id": "u-1",
        "role": "Agent",
        "employee_id": "EMP-360",
        "accessible_teams": ["Inbound"],
        "user_memory_text": "<VERIFIED_USER_MEMORY>\n[User Memory]\nPreferred detail level: brief\n</VERIFIED_USER_MEMORY>",
    }
    ctx = build_pass1_identity_context(scope)
    assert "<CALLER_PASSPORT" in ctx
    assert 'employee_code="EMP-360"' in ctx
    assert "<VERIFIED_USER_MEMORY>" in ctx
    assert len(ctx) <= 8000

    # Oversized memory is bounded by the 256k-era 8000-char identity block.
    huge_scope = {**scope, "user_memory_text": "X" * 12000}
    capped = build_pass1_identity_context(huge_scope)
    assert len(capped) <= 8000


def test_manager_360_directory_and_team_scope_isolation(monkeypatch):
    db = _setup_db()
    _user, _emp = _seed_agent_and_data(db)

    # Create a second team and an employee outside the manager's team
    other_team = Team(id=uuid.uuid4(), name="Outbound", db_name="Outbound", display_name="Outbound", is_active=True)
    db.add(other_team)
    db.flush()
    other_emp = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-OUT-1",
        name="Other Team Agent",
        team_id=other_team.id,
        region="UAE",
        position_name="Agent",
        is_active=True,
    )
    db.add(other_emp)
    db.commit()

    manager_scope = {
        "user_id": str(uuid.uuid4()),
        "role": "Manager",
        "employee_id": None,
        "is_self_only": False,
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Inbound"],
    }
    client = _build_client(db, monkeypatch, scope_override=manager_scope)

    # Directory returns only Inbound employees, not Outbound
    dir_resp = client.get("/api/ai/agent-360/directory", headers={"X-User-Role": "Manager"})
    assert dir_resp.status_code == 200, dir_resp.text
    codes = {row["employee_code"] for row in dir_resp.json()["employees"]}
    assert "EMP-360" in codes
    assert "EMP-OUT-1" not in codes

    # Manager can inspect direct report in Inbound
    ok_resp = client.get("/api/ai/agent-360?employee_code=EMP-360", headers={"X-User-Role": "Manager"})
    assert ok_resp.status_code == 200

    # Manager is forbidden from inspecting employee in Outbound
    forbidden_resp = client.get("/api/ai/agent-360?employee_code=EMP-OUT-1", headers={"X-User-Role": "Manager"})
    assert forbidden_resp.status_code == 403
