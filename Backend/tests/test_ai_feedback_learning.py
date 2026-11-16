"""Batch 3 tests: user feedback tags, clustering, Admin PMS verification gate, and approved pattern learning."""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers import ai_workspace
from config.database import Base, get_db
from models.ai_schemas import AiChatRequest, SessionFilterContext
from models.models import AiApprovedPattern, AiInteractionTrace, AuditLog, Employee, ProductSetting, Team
from services.ai import feature_gate
from services.ai.approved_patterns import ApprovedPatternMatcher, normalize_pattern_prompt
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.router import HybridQueryRouter
from tests.test_ai_booking_comparisons import _make_schema_record


def _make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(ProductSetting(key="ai_enabled", enabled=True))
    db.commit()
    return db


def _build_app(db, *, monkeypatch, ai_enabled: bool = True):
    monkeypatch.setattr(feature_gate, "is_ai_enabled", lambda _db: ai_enabled)

    app = FastAPI()

    @app.middleware("http")
    async def inject_identity(request: Request, call_next):
        role = request.headers.get("x-test-role", "Viewer")
        user_id = request.headers.get("x-test-user-id", "test-user-1")
        request.state.user = {
            "role": role,
            "user_id": user_id,
            "accessible_teams": ["Inbound"],
            "accessible_regions": ["EGY", "UAE"],
            "accessible_branches": ["dubai", "sharjah", "ajman"],
        }
        return await call_next(request)

    monkeypatch.setattr(ai_workspace, "require_authenticated_scope", lambda _db, req: req.state.user)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.include_router(ai_workspace.router, prefix="/api")
    return TestClient(app)


def test_unavailable_and_clarification_turns_emit_valid_trace_ids(monkeypatch):
    db = _make_session()
    rec = _make_schema_record(
        emp_id="E101",
        name="Salma Nabil",
        team="Inbound",
        score=91.4,
        dubai_b=150,
        sharjah_b=90,
        ajman_b=40,
        month="September",
        year=2026,
    )
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_records", lambda _self, **_kw: [rec])
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_analysis_records", lambda _self, **_kw: [rec])

    scope = {
        "role": "Admin",
        "user_id": "admin-trace-check",
        "accessible_teams": ["Inbound", "Outbound", "RCM"],
        "accessible_branches": ["dubai", "sharjah", "ajman"],
    }
    orchestrator = PmsAiOrchestrator(db, scope)

    missing_period = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="What is Inbound score in November 2026?",
            session_state=SessionFilterContext(team="Inbound", month="November", year=2026),
            provider_override="deterministic",
        )
    )
    assert missing_period.outcome == "unavailable_data"
    assert missing_period.trace_id
    assert uuid.UUID(missing_period.trace_id)

    clarification = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="Which branch had more bookings in September 2026: Dubai or Sharjah?",
            session_state=SessionFilterContext(month="September", year=2026),
            provider_override="deterministic",
        )
    )
    assert clarification.outcome == "clarification"
    assert clarification.trace_id
    assert uuid.UUID(clarification.trace_id)


def test_feedback_tags_sync_governance_and_thumbs_up_stays_unverified(monkeypatch):
    db = _make_session()
    rec = _make_schema_record(
        emp_id="E102",
        name="Tariq Mansour",
        team="Inbound",
        score=88.5,
        dubai_b=120,
        sharjah_b=70,
        ajman_b=30,
    )
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_records", lambda _self, **_kw: [rec])
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_analysis_records", lambda _self, **_kw: [rec])

    scope = {
        "role": "Admin",
        "user_id": "test-user-1",
        "accessible_teams": ["Inbound"],
    }
    res = PmsAiOrchestrator(db, scope).run_chat_turn(
        AiChatRequest(
            prompt="What is Inbound score in September 2026?",
            session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
            provider_override="deterministic",
        )
    )
    assert res.trace_id

    client = _build_app(db, monkeypatch=monkeypatch)

    # Thumbs up as regular user (and even Admin without explicit reviewer_verified=True) stays pending/unverified
    up_res = client.post(
        "/api/ai/feedback",
        headers={"x-test-role": "Admin", "x-test-user-id": "test-user-1"},
        json={"trace_id": res.trace_id, "rating": "up"},
    )
    assert up_res.status_code == 200
    assert up_res.json()["reviewer_verified"] is False

    trace_row = db.query(AiInteractionTrace).filter(AiInteractionTrace.id == uuid.UUID(res.trace_id)).first()
    assert trace_row is not None
    assert trace_row.feedback_rating == "up"
    assert trace_row.reviewer_verified is False
    gov_meta = (trace_row.tool_digest or {}).get("feedback_governance", {})
    assert gov_meta.get("review_status") == "pending"
    assert gov_meta.get("reviewer_verified") is False

    # All 4 failure tags are accepted and reflected in clusters
    for tag in ("wrong_data", "misunderstood_question", "lost_context", "too_long"):
        down_res = client.post(
            "/api/ai/feedback",
            headers={"x-test-role": "Admin", "x-test-user-id": "test-user-1"},
            json={
                "trace_id": res.trace_id,
                "rating": "down",
                "category": tag,
                "reason": f"Tag check: {tag}",
            },
        )
        assert down_res.status_code == 200

    clusters_res = client.get("/api/ai/feedback/clusters?rating=down", headers={"x-test-role": "Admin"})
    assert clusters_res.status_code == 200
    clusters_payload = clusters_res.json()
    assert clusters_payload["total_traces"] == 1
    cluster = clusters_payload["clusters"][0]
    assert cluster["failure_category"] == "too_long"
    assert len(cluster["traces"]) == 1
    assert cluster["traces"][0]["trace_id"] == res.trace_id
    assert cluster["traces"][0]["failure_category"] == "too_long"


def test_admin_only_rbac_pms_gate_pii_rejection_and_audit_trail(monkeypatch):
    db = _make_session()
    team = Team(
        id=uuid.uuid4(),
        name="Inbound",
        db_name="inbound",
        display_name="Inbound",
        region="EGY",
    )
    db.add(team)
    db.flush()
    db.add(
        Employee(
            id=uuid.uuid4(),
            employee_id="EMP901",
            name="Nadia Hassan",
            team_id=team.id,
            region="EGY",
            performance_level="Employee",
        )
    )
    db.commit()

    rec = _make_schema_record(
        emp_id="EMP901",
        name="Nadia Hassan",
        team="Inbound",
        score=94.0,
        dubai_b=180,
        sharjah_b=90,
        ajman_b=50,
    )
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_records", lambda _self, **_kw: [rec])
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_analysis_records", lambda _self, **_kw: [rec])

    trace_res = PmsAiOrchestrator(
        db,
        {"role": "Manager", "user_id": "mgr-1", "accessible_teams": ["Inbound"]},
    ).run_chat_turn(
        AiChatRequest(
            prompt="Who holds the Inbound mvp badge in September 2026?",
            session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
            provider_override="deterministic",
        )
    )
    assert trace_res.trace_id

    client = _build_app(db, monkeypatch=monkeypatch)

    # Non-Admin forbidden across all governance & pattern endpoints
    assert client.get("/api/ai/feedback/clusters", headers={"x-test-role": "Manager"}).status_code == 403
    assert client.get("/api/ai/feedback/patterns", headers={"x-test-role": "Manager"}).status_code == 403
    assert (
        client.post(
            f"/api/ai/traces/{trace_res.trace_id}/approve-pattern",
            headers={"x-test-role": "Manager"},
            json={
                "intent": "ranking",
                "verified_against_pms": True,
            },
        ).status_code
        == 403
    )
    assert client.delete("/api/ai/feedback/patterns/pat-1", headers={"x-test-role": "Manager"}).status_code == 403

    # 422 gate when verified_against_pms=False
    unverified = client.post(
        f"/api/ai/traces/{trace_res.trace_id}/approve-pattern",
        headers={"x-test-role": "Admin", "x-test-user-id": "admin-1"},
        json={
            "corrected_pattern_prompt": "Please list the Inbound mvp badge in September 2026",
            "intent": "ranking",
            "verified_against_pms": False,
        },
    )
    assert unverified.status_code == 422

    # 422 rejection when corrected_pattern_prompt contains email/phone PII
    pii_rejected = client.post(
        f"/api/ai/traces/{trace_res.trace_id}/approve-pattern",
        headers={"x-test-role": "Admin", "x-test-user-id": "admin-1"},
        json={
            "corrected_pattern_prompt": "Show Inbound mvp badge for nadia@example.com",
            "intent": "ranking",
            "verified_against_pms": True,
        },
    )
    assert pii_rejected.status_code == 422
    assert "PII" in pii_rejected.json()["detail"] or "email" in pii_rejected.json()["detail"].lower()

    # Valid approval with employee name automatically redacted before persistence
    admin_uuid = str(uuid.uuid4())
    approved = client.post(
        f"/api/ai/traces/{trace_res.trace_id}/approve-pattern",
        headers={"x-test-role": "Admin", "x-test-user-id": admin_uuid},
        json={
            "corrected_pattern_prompt": "Please list the Inbound mvp badge for Nadia Hassan in September 2026",
            "intent": "ranking",
            "operation_kind": "ranking",
            "requested_parts": ["ranking"],
            "tool_choice": "get_team_rankings",
            "failure_category": "misunderstood_question",
            "verified_against_pms": True,
            "review_notes": "Checked rankings against Monthly Presentation.",
        },
    )
    assert approved.status_code == 200
    body = approved.json()
    pat = body["pattern"]
    assert pat["verified_against_pms"] is True
    assert pat["intent"] == "ranking"
    assert "Nadia" not in pat["example_prompt_redacted"]
    assert "Hassan" not in pat["example_prompt_redacted"]
    assert "nadia" not in pat["normalized_pattern"]
    assert body["trace_review"]["reviewer_verified"] is True

    patterns_list = client.get("/api/ai/feedback/patterns", headers={"x-test-role": "Admin"})
    assert patterns_list.status_code == 200
    assert len(patterns_list.json()["patterns"]) == 1

    create_audits = db.query(AuditLog).filter(AuditLog.operation == "AI_APPROVED_PATTERN_CREATE").all()
    assert len(create_audits) == 1
    assert str(create_audits[0].performed_by_user_id) == admin_uuid

    # Delete / deactivate pattern & verify audit trail
    del_res = client.delete(
        f"/api/ai/feedback/patterns/{pat['id']}",
        headers={"x-test-role": "Admin", "x-test-user-id": admin_uuid},
    )
    assert del_res.status_code == 200
    assert client.get("/api/ai/feedback/patterns", headers={"x-test-role": "Admin"}).json()["patterns"] == []
    del_audits = db.query(AuditLog).filter(AuditLog.operation == "AI_APPROVED_PATTERN_DELETE").all()
    assert len(del_audits) == 1


def test_approved_pattern_improves_unseen_paraphrase_while_preserving_rbac(monkeypatch):
    db = _make_session()
    in_rec = _make_schema_record(
        emp_id="EMP11",
        name="Laila Sami",
        team="Inbound",
        score=95.2,
        dubai_b=210,
        sharjah_b=100,
        ajman_b=50,
    )
    in_rec2 = _make_schema_record(
        emp_id="EMP12",
        name="Karim Adel",
        team="Inbound",
        score=82.0,
        dubai_b=130,
        sharjah_b=70,
        ajman_b=30,
    )
    out_rec = _make_schema_record(
        emp_id="EMP21",
        name="Omar Zaki",
        team="Outbound",
        score=93.0,
        dubai_b=180,
        sharjah_b=80,
        ajman_b=40,
    )
    monkeypatch.setattr(
        "services.dashboard_record_service.DashboardRecordService.list_records",
        lambda _self, **_kw: [in_rec, in_rec2, out_rec],
    )
    monkeypatch.setattr(
        "services.dashboard_record_service.DashboardRecordService.list_analysis_records",
        lambda _self, **_kw: [in_rec, in_rec2, out_rec],
    )

    unseen_inbound = "Show me the Inbound mvp badge in September 2026"
    unseen_outbound = "Show me the Outbound mvp badge in September 2026"

    # BEFORE pattern approval: deterministic router falls back to current_value instead of ranking
    router_before = HybridQueryRouter(
        scope={"role": "Manager", "accessible_teams": ["Inbound"], "accessible_branches": ["dubai", "sharjah", "ajman"]},
        db=db,
    )
    before_res = router_before.resolve_and_validate(
        prompt=unseen_inbound,
        session_state=SessionFilterContext(month="September", year=2026),
        provider_override="deterministic",
    )
    assert before_res.plan.intent != "ranking"

    # Admin flags a trace with a different phrasing & approves pattern against live PMS data
    orch_admin = PmsAiOrchestrator(
        db,
        {"role": "Admin", "user_id": "admin-1", "accessible_teams": ["Inbound", "Outbound"]},
    )
    tr = orch_admin.run_chat_turn(
        AiChatRequest(
            prompt="Please list the Inbound mvp badge in September 2026",
            session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
            provider_override="deterministic",
        )
    )
    client = _build_app(db, monkeypatch=monkeypatch)
    approve = client.post(
        f"/api/ai/traces/{tr.trace_id}/approve-pattern",
        headers={"x-test-role": "Admin", "x-test-user-id": "admin-1"},
        json={
            "corrected_pattern_prompt": "Please list the Inbound mvp badge in September 2026",
            "intent": "ranking",
            "operation_kind": "ranking",
            "requested_parts": ["ranking"],
            "tool_choice": "get_team_rankings",
            "failure_category": "misunderstood_question",
            "verified_against_pms": True,
        },
    )
    assert approve.status_code == 200

    # AFTER approval: disjoint unseen paraphrase routes to ranking & executes fresh scoped PMS query
    mgr_scope = {
        "role": "Manager",
        "user_id": "mgr-inbound",
        "accessible_teams": ["Inbound"],
        "accessible_branches": ["dubai", "sharjah", "ajman"],
    }
    after_inbound = PmsAiOrchestrator(db, mgr_scope).run_chat_turn(
        AiChatRequest(
            prompt=unseen_inbound,
            session_state=SessionFilterContext(month="September", year=2026),
            provider_override="deterministic",
        )
    )
    assert after_inbound.outcome == "answer"
    assert after_inbound.structured_query is not None
    assert after_inbound.structured_query.intent == "ranking"
    assert "Laila Sami" in after_inbound.headline or any("Laila Sami" in b for b in after_inbound.narrative_bullets)

    # RBAC MUST still block unauthorized Outbound team even when pattern matches
    after_outbound = PmsAiOrchestrator(db, mgr_scope).run_chat_turn(
        AiChatRequest(
            prompt=unseen_outbound,
            session_state=SessionFilterContext(month="September", year=2026),
            provider_override="deterministic",
        )
    )
    assert after_outbound.outcome == "restricted_access"
    assert "Omar Zaki" not in after_outbound.headline


def test_catalog_chronological_period_sort_and_support_positions_explicit_region_rbac():
    from services.ai.catalog import check_scope_data_availability, user_can_access_team

    sep_rec = _make_schema_record(
        emp_id="E201", name="Rana Ali", team="Inbound", score=89.0, dubai_b=50, sharjah_b=20, ajman_b=10, month="September", year=2026
    )
    oct_rec = _make_schema_record(
        emp_id="E201", name="Rana Ali", team="Inbound", score=91.0, dubai_b=60, sharjah_b=25, ajman_b=12, month="October", year=2026
    )
    dec_rec = _make_schema_record(
        emp_id="E201", name="Rana Ali", team="Inbound", score=92.0, dubai_b=65, sharjah_b=30, ajman_b=15, month="December", year=2026
    )
    avail = check_scope_data_availability([oct_rec, dec_rec, sep_rec], team="Inbound", month="November", year=2026)
    assert avail["has_data"] is False
    assert avail["available_periods"] == ["September 2026", "October 2026", "December 2026"]
    assert avail["available_periods"][-1] == "December 2026"

    uae_rm = {"role": "Regional Manager", "accessible_regions": ["UAE"], "accessible_teams": ["Support Positions", "CSR"]}
    assert user_can_access_team(uae_rm, "Support Positions", region="UAE") is True
    assert user_can_access_team(uae_rm, "Support Positions", region="EGY") is False
    assert user_can_access_team(uae_rm, "Support Positions") is False

    inbound_mgr = {"role": "Manager", "accessible_teams": ["Inbound"]}
    assert user_can_access_team(inbound_mgr, "Support Positions", region="UAE") is False


def test_migration_registers_all_ai_audit_op_enum_labels():
    import importlib.util
    from pathlib import Path
    import re

    mig_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "e2b4c8d9f0a1_add_ai_conversation_persistence_and_patterns.py"
    )
    spec = importlib.util.spec_from_file_location("mig_e2b4c8d9f0a1", mig_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    declared_ai_ops = set(mod.AI_AUDIT_OP_VALUES)
    assert declared_ai_ops == {
        "AI_FEEDBACK_REVIEW",
        "AI_FEEDBACK_PURGE",
        "AI_FEEDBACK_DELETE",
        "AI_FEEDBACK_EXPORT_BUNDLE",
        "AI_APPROVED_PATTERN_CREATE",
        "AI_APPROVED_PATTERN_DELETE",
    }
    valid_audit_op_set = {"INSERT", "UPDATE", "DELETE", "SOFT_DELETE", "EXPORT"} | declared_ai_ops

    services_ai_dir = Path(__file__).resolve().parents[1] / "services" / "ai"
    emitted_ops: set[str] = set()
    for fname in ("feedback_service.py", "approved_patterns.py"):
        src = (services_ai_dir / fname).read_text(encoding="utf-8")
        emitted_ops.update(re.findall(r'operation\s*=\s*["\']([A-Z0-9_]+)["\']', src))

    assert emitted_ops
    assert emitted_ops <= valid_audit_op_set


