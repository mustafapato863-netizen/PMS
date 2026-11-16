from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ai_provider_fakes import failed_response, install_scripted_provider
from api.middleware.auth_middleware import AuthMiddleware
from api.routers.ai_workspace import router as ai_router
from config.database import Base, get_db
from models.ai_schemas import AiChatRequest, PageContextV1, SessionFilterContext
from models.models import AiConversation, ProductSetting
from services.ai.catalog import ai_evidence_cache
from services.ai.local_model_router import ALLOWED_INTENTS, build_intent_json_schema
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.router import HybridQueryRouter
from services.auth_service import AuthenticationService
from services.dashboard_record_service import DashboardRecordService
from services.database_record_source import DatabaseRecordSource
from test_ai_workspace import _build_in_memory_db, _make_call_center_record, _patch_records


def _make_record(
    *,
    emp_id: str,
    name: str,
    team: str,
    score: float,
    month: str = "September",
    year: int = 2026,
    region: str = "EGY",
) -> SimpleNamespace:
    rec = _make_call_center_record(emp_id, name, "Inbound", score, 40, 60, 50, 80, month=month)
    rec.year = year
    rec.team = team
    rec.region = region
    return rec


def _install_db_record_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def spy_get_all(self, *args, **kwargs):
        calls.append("DatabaseRecordSource.get_all")
        return []

    def spy_list_records(self, *args, **kwargs):
        calls.append("DashboardRecordService.list_analysis_records")
        return []

    monkeypatch.setattr(DatabaseRecordSource, "get_all", spy_get_all)
    monkeypatch.setattr(DashboardRecordService, "list_analysis_records", spy_list_records)
    return calls


@pytest.mark.parametrize(
    "prompt",
    [
        "How can u help me?",
        "How can you help me?",
        "How can u help?",
        "What can I ask?",
        "What can you do?",
        "What can this assistant do?",
        "What can you help with?",
        "Help",
    ],
)
def test_capabilities_help_variants_zero_db_reads_and_role_aware(monkeypatch: pytest.MonkeyPatch, prompt: str) -> None:
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    spy_calls = _install_db_record_spy(monkeypatch)
    db = _build_in_memory_db()
    try:
        admin_res = PmsAiOrchestrator(
            db,
            {"role": "Admin", "user_id": "u-admin", "has_unrestricted_team_access": True},
        ).run_chat_turn(AiChatRequest(prompt=prompt, session_state=SessionFilterContext()))
        assert admin_res.outcome == "answer"
        assert admin_res.capability_mode == "capabilities_help"
        assert admin_res.tool_calls == []
        assert 1 <= len(admin_res.suggested_followups) <= 3
        assert "88." not in admin_res.headline and "92." not in admin_res.headline
        assert "Call Center" not in (admin_res.scope_banner or "")

        emp_res = PmsAiOrchestrator(
            db,
            {
                "role": "Employee",
                "user_id": "u-emp",
                "employee_id": "EMP101",
                "is_self_only": True,
                "accessible_teams": ["Inbound"],
            },
        ).run_chat_turn(AiChatRequest(prompt=prompt, session_state=SessionFilterContext()))
        assert emp_res.outcome == "answer"
        assert emp_res.capability_mode == "capabilities_help"
        assert emp_res.tool_calls == []
        assert "My Scope" in (emp_res.scope_banner or "")
        assert "own" in emp_res.headline.casefold() or "scorecard" in emp_res.headline.casefold()
        assert spy_calls == []
    finally:
        db.close()


def test_analytical_questions_containing_help_route_to_performance_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "false")
    _patch_records(
        monkeypatch,
        [
            _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 78.0, 25, 60, 40, 80, month="August"),
            _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 72.0, 20, 60, 35, 80, month="September"),
        ],
    )
    ai_evidence_cache.clear()
    db = _build_in_memory_db()
    try:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "has_unrestricted_team_access": True})
        r1 = orch.run_chat_turn(
            AiChatRequest(
                prompt="Help me understand why Inbound score dropped",
                session_state=SessionFilterContext(month="September", year=2026),
            )
        )
        assert r1.capability_mode == "performance_query"
        assert r1.outcome == "answer"
        assert len(r1.tool_calls) >= 1

        r2 = orch.run_chat_turn(
            AiChatRequest(
                prompt="What helped Booking Rate improve?",
                session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
            )
        )
        assert r2.capability_mode == "performance_query"
        assert r2.outcome == "answer"
        assert len(r2.tool_calls) >= 1
    finally:
        db.close()


@pytest.mark.parametrize(
    "prompt",
    [
        "What's the weather in Dubai today?",
        "Tell me a joke",
        "Give me a pasta recipe",
        "Recommend a good movie",
        "Random chatter about purple elephants",
    ],
)
def test_off_topic_prompts_cause_zero_db_queries(monkeypatch: pytest.MonkeyPatch, prompt: str) -> None:
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "false")
    spy_calls = _install_db_record_spy(monkeypatch)
    db = _build_in_memory_db()
    try:
        res = PmsAiOrchestrator(
            db, {"role": "Admin", "has_unrestricted_team_access": True}
        ).run_chat_turn(AiChatRequest(prompt=prompt, session_state=SessionFilterContext()))
        assert res.outcome == "unsupported_request"
        assert res.capability_mode == "off_topic"
        assert res.tool_calls == []
        assert 2 <= len(res.suggested_followups) <= 3
        assert spy_calls == []
    finally:
        db.close()


@pytest.mark.parametrize(
    "prompt",
    [
        "Check the numbers",
        "Look at the data",
        "Show me",
        "Anything?",
        "Analyze this",
    ],
)
def test_vague_dataless_requests_return_clarification_with_zero_db_queries(
    monkeypatch: pytest.MonkeyPatch, prompt: str
) -> None:
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "false")
    spy_calls = _install_db_record_spy(monkeypatch)
    db = _build_in_memory_db()
    try:
        res = PmsAiOrchestrator(
            db, {"role": "Admin", "has_unrestricted_team_access": True}
        ).run_chat_turn(AiChatRequest(prompt=prompt, session_state=SessionFilterContext()))
        assert res.outcome == "clarification"
        assert res.capability_mode == "clarification"
        assert res.clarification is not None
        assert res.tool_calls == []
        assert spy_calls == []
    finally:
        db.close()


def test_router_never_defaults_unrecognized_or_vague_prompt_to_current_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "false")
    router = HybridQueryRouter(scope={"role": "Admin", "has_unrestricted_team_access": True})

    vague = router.resolve_and_validate(prompt="Check the numbers", session_state=SessionFilterContext())
    assert vague.outcome == "clarification"
    assert vague.plan.intent == "clarify"

    unrelated = router.resolve_and_validate(prompt="Purple elephants dancing", session_state=SessionFilterContext())
    assert unrelated.outcome == "unsupported_request"
    assert unrelated.plan.intent == "unsupported"


def test_local_model_intent_gate_failure_falls_back_safely_never_current_value(monkeypatch: pytest.MonkeyPatch) -> None:
    assert {"greeting", "capabilities_help", "off_topic", "clarification", "performance_query"}.issubset(ALLOWED_INTENTS)
    schema = build_intent_json_schema()
    assert set(schema["schema"]["properties"]["intent"]["enum"]) == ALLOWED_INTENTS

    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    spy_calls = _install_db_record_spy(monkeypatch)
    db = _build_in_memory_db()
    try:
        # Provider fails -> must fall back to clarification or off_topic, NEVER current_value
        install_scripted_provider(monkeypatch, failed_response("provider_unavailable"))
        res_fail = PmsAiOrchestrator(
            db, {"role": "Admin", "has_unrestricted_team_access": True}
        ).run_chat_turn(AiChatRequest(prompt="Could you look into things?", session_state=SessionFilterContext()))
        assert res_fail.capability_mode in ("clarification", "off_topic")
        assert res_fail.outcome in ("clarification", "unsupported_request")
        assert res_fail.tool_calls == []

        # Provider returns invalid JSON -> must fall back safely, NEVER current_value
        install_scripted_provider(monkeypatch, '{"intent":"current_value","team":"Inbound"}')
        res_bad = PmsAiOrchestrator(
            db, {"role": "Admin", "has_unrestricted_team_access": True}
        ).run_chat_turn(AiChatRequest(prompt="Tell me something interesting", session_state=SessionFilterContext()))
        assert res_bad.capability_mode in ("clarification", "off_topic")
        assert res_bad.tool_calls == []
        assert spy_calls == []
    finally:
        db.close()


def test_broad_overview_uses_authorized_scope_and_accurate_scope_banner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "false")

    records = [
        _make_record(emp_id="EMP301", name="Nadia Adel", team="Resubmission", score=86.5),
        _make_record(emp_id="EMP302", name="Tarek Hassan", team="Marketing", score=91.0),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    db = _build_in_memory_db()
    try:
        # 1. Multi-department Admin asking "How are we doing?" -> All Authorized Departments, function is None, never Call Center
        admin_res = PmsAiOrchestrator(
            db, {"role": "Admin", "user_id": "adm-1", "has_unrestricted_team_access": True}
        ).run_chat_turn(
            AiChatRequest(
                prompt="How are we doing?",
                session_state=SessionFilterContext(month="September", year=2026),
            )
        )
        assert admin_res.outcome == "answer"
        assert admin_res.capability_mode == "performance_query"
        assert admin_res.resolved_session_state.function is None
        assert "All Authorized Departments" in (admin_res.scope_banner or "")
        assert "Call Center" not in (admin_res.scope_banner or "")

        # 2. Resubmission-only Manager asking "How are we doing?" -> scope_banner reflects Resubmission/RCM, never Call Center
        resub_res = PmsAiOrchestrator(
            db,
            {
                "role": "Manager",
                "user_id": "mgr-resub",
                "has_unrestricted_team_access": False,
                "accessible_teams": ["Resubmission"],
                "accessible_functions": ["RCM"],
            },
        ).run_chat_turn(
            AiChatRequest(
                prompt="How are we doing?",
                session_state=SessionFilterContext(month="September", year=2026),
            )
        )
        assert resub_res.outcome == "answer"
        assert resub_res.capability_mode == "performance_query"
        assert "Resubmission" in (resub_res.scope_banner or "")
        assert "Call Center" not in (resub_res.scope_banner or "")

        # 3. Greeting has capability_mode="greeting", 0 tools, no Call Center badge
        greet_res = PmsAiOrchestrator(
            db, {"role": "Admin", "user_id": "adm-1", "has_unrestricted_team_access": True}
        ).run_chat_turn(AiChatRequest(prompt="Hi", session_state=SessionFilterContext()))
        assert greet_res.outcome == "answer"
        assert greet_res.capability_mode == "greeting"
        assert greet_res.tool_calls == []
        assert "Call Center" not in (greet_res.scope_banner or "")
    finally:
        db.close()


def test_migration_a8c3e1f4d9b2_upgrade_and_downgrade() -> None:
    mig_dir = Path(__file__).resolve().parent.parent / "migrations" / "versions"
    mig_file = next(mig_dir.glob("*a8c3e1f4d9b2*.py"))
    spec = importlib.util.spec_from_file_location("mig_a8c3e1f4d9b2", mig_file)
    assert spec is not None and spec.loader is not None
    mig_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig_mod)
    assert mig_mod.revision == "a8c3e1f4d9b2"
    assert mig_mod.down_revision == "f4d2e8a9c1b3"

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE ai_conversations (
                    id VARCHAR(64) PRIMARY KEY NOT NULL,
                    owner_user_id VARCHAR(100) NOT NULL,
                    status VARCHAR(24) NOT NULL,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO ai_conversations (id, owner_user_id, status) "
                "VALUES ('legacy-1', 'user-1', 'active')"
            )
        )

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        orig_op = mig_mod.op
        mig_mod.op = Operations(ctx)
        try:
            mig_mod.upgrade()
        finally:
            mig_mod.op = orig_op

    legacy_mig_file = next(mig_dir.glob("*b3f7d2a9c6e1*.py"))
    legacy_spec = importlib.util.spec_from_file_location("mig_b3f7d2a9c6e1", legacy_mig_file)
    assert legacy_spec is not None and legacy_spec.loader is not None
    legacy_mig_mod = importlib.util.module_from_spec(legacy_spec)
    legacy_spec.loader.exec_module(legacy_mig_mod)
    assert legacy_mig_mod.revision == "b3f7d2a9c6e1"
    assert legacy_mig_mod.down_revision == "a8c3e1f4d9b2"

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        orig_op = legacy_mig_mod.op
        legacy_mig_mod.op = Operations(ctx)
        try:
            legacy_mig_mod.upgrade()
        finally:
            legacy_mig_mod.op = orig_op

    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("ai_conversations")}
    assert "origin" in cols
    idx_names = {idx["name"] for idx in insp.get_indexes("ai_conversations")}
    assert "idx_ai_conversations_owner_origin_updated" in idx_names

    with engine.begin() as conn:
        row_origin = conn.execute(text("SELECT origin FROM ai_conversations WHERE id = 'legacy-1'")).scalar()
        assert row_origin == "legacy"

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        orig_op = legacy_mig_mod.op
        legacy_mig_mod.op = Operations(ctx)
        try:
            legacy_mig_mod.downgrade()
        finally:
            legacy_mig_mod.op = orig_op

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        orig_op = mig_mod.op
        mig_mod.op = Operations(ctx)
        try:
            mig_mod.downgrade()
        finally:
            mig_mod.op = orig_op

    insp_after = inspect(engine)
    assert "origin" not in {c["name"] for c in insp_after.get_columns("ai_conversations")}


def test_conversation_origin_separation_promote_and_context_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "false")

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        AuthenticationService.create_user(db, "orig_admin", "orig@example.invalid", "AdminSecret123!", "Admin")
        db.add(ProductSetting(key="ai_enabled", enabled=True))
        db.commit()
        tok = AuthenticationService.authenticate_user(db, "orig_admin", "AdminSecret123!")

    _patch_records(
        monkeypatch,
        [
            _make_call_center_record("EMP401", "Mariam Adel", "Inbound", 91.0, 40, 70, 50, 80, month="September"),
            _make_record(emp_id="EMP402", name="Karim Nour", team="Marketing", score=88.0, month="September"),
        ],
    )
    ai_evidence_cache.clear()

    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.include_router(ai_router, prefix="/api")

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {tok}"}

    # 1. Create a workspace conversation and a page_assistant conversation
    r_ws = client.post(
        "/api/ai/chat",
        headers=headers,
        json={
            "prompt": "What is Inbound score in September 2026?",
            "origin": "workspace",
            "session_state": {"month": "September", "year": 2026},
        },
    )
    assert r_ws.status_code == 200
    ws_id = r_ws.json()["data"]["conversation_id"]

    r_pa = client.post(
        "/api/ai/chat",
        headers=headers,
        json={
            "prompt": "Explain this page",
            "origin": "page_assistant",
            "page_context": {"page_id": "monthly_presentation", "team_id": "Marketing", "period": "2026-09"},
        },
    )
    assert r_pa.status_code == 200
    pa_data = r_pa.json()["data"]
    pa_id = pa_data["conversation_id"]
    pa_ver = pa_data["context_version"]

    # 2. A workspace request cannot continue a page_assistant thread without explicit promotion.
    r_cross_surface = client.post(
        "/api/ai/chat",
        headers=headers,
        json={
            "prompt": "What is Marketing score in September 2026?",
            "conversation_id": pa_id,
            "context_version": pa_ver,
            "origin": "workspace",
        },
    )
    assert r_cross_surface.status_code == 409

    r_pa_followup = client.post(
        "/api/ai/chat",
        headers=headers,
        json={
            "prompt": "What is Marketing score in September 2026?",
            "conversation_id": pa_id,
            "context_version": pa_ver,
            "origin": "page_assistant",
        },
    )
    assert r_pa_followup.status_code == 200

    # 3. Default GET /api/ai/conversations returns only workspace; origin=page_assistant returns page_assistant; origin=all returns both
    ws_list = client.get("/api/ai/conversations", headers=headers).json()["conversations"]
    assert [c["conversation_id"] for c in ws_list] == [ws_id]
    assert ws_list[0]["origin"] == "workspace"

    pa_list = client.get("/api/ai/conversations?origin=page_assistant", headers=headers).json()["conversations"]
    assert [c["conversation_id"] for c in pa_list] == [pa_id]
    assert pa_list[0]["origin"] == "page_assistant"

    all_list = client.get("/api/ai/conversations?origin=all", headers=headers).json()["conversations"]
    assert {c["conversation_id"] for c in all_list} == {ws_id, pa_id}

    # 4. Detail and context routes enforce the requested origin.
    assert client.get(f"/api/ai/conversations/{pa_id}", headers=headers).status_code == 404
    pa_detail = client.get(f"/api/ai/conversations/{pa_id}?origin=page_assistant", headers=headers)
    assert pa_detail.status_code == 200
    assert pa_detail.json()["data"]["origin"] == "page_assistant"
    assert len(pa_detail.json()["data"]["turns"]) == 2

    # 5. Promote page_assistant -> workspace preserves all history
    r_promote = client.post(f"/api/ai/conversations/{pa_id}/promote", headers=headers)
    assert r_promote.status_code == 200
    assert r_promote.json()["data"]["origin"] == "workspace"

    ws_list_after = client.get("/api/ai/conversations", headers=headers).json()["conversations"]
    assert {c["conversation_id"] for c in ws_list_after} == {ws_id, pa_id}
    assert client.get("/api/ai/conversations?origin=page_assistant", headers=headers).json()["conversations"] == []

    pa_detail_after = client.get(
        f"/api/ai/conversations/{pa_id}?origin=workspace", headers=headers
    ).json()["data"]
    assert pa_detail_after["origin"] == "workspace"
    assert len(pa_detail_after["turns"]) == 2

    # 6. Starting a new conversation never inherits confirmed query context from previous conversation
    r_new_conv = client.post("/api/ai/conversations", headers=headers, json={"origin": "workspace"})
    assert r_new_conv.status_code == 200
    new_conv_id = r_new_conv.json()["data"]["conversation_id"]
    assert r_new_conv.json()["data"]["confirmed_context"]["team"] is None

    r_new_vague = client.post(
        "/api/ai/chat",
        headers=headers,
        json={"prompt": "Analyze this", "conversation_id": new_conv_id},
    )
    assert r_new_vague.status_code == 200
    assert r_new_vague.json()["data"]["outcome"] == "clarification"
    assert r_new_vague.json()["data"]["capability_mode"] == "clarification"
    assert r_new_vague.json()["data"]["tool_calls"] == []

    # 7. Delete works regardless of origin
    pa_delete_target = client.post(
        "/api/ai/conversations", headers=headers, json={"origin": "page_assistant"}
    ).json()["data"]["conversation_id"]
    assert client.delete(f"/api/ai/conversations/{pa_delete_target}", headers=headers).status_code == 200
    assert client.get(f"/api/ai/conversations/{pa_delete_target}", headers=headers).status_code == 404

    # 8. Pre-migration unstamped rows default to 'legacy', are blocked from workspace chat until promoted, and promote cleanly
    with Session() as db:
        ws_owner_id = (
            db.query(AiConversation)
            .filter(AiConversation.id == ws_id)
            .one()
            .owner_user_id
        )
        legacy_row = AiConversation(
            id="conv-legacy-db",
            owner_user_id=ws_owner_id,
            owner_role="Admin",
            title="Older unclassified chat",
        )
        db.add(legacy_row)
        db.commit()
        assert legacy_row.origin == "legacy"

    assert all(
        c["conversation_id"] != "conv-legacy-db"
        for c in client.get("/api/ai/conversations", headers=headers).json()["conversations"]
    )
    legacy_list = client.get("/api/ai/conversations?origin=legacy", headers=headers).json()["conversations"]
    assert [c["conversation_id"] for c in legacy_list] == ["conv-legacy-db"]
    assert client.get("/api/ai/conversations/conv-legacy-db", headers=headers).status_code == 404
    assert client.get("/api/ai/conversations/conv-legacy-db?origin=legacy", headers=headers).status_code == 200
    assert (
        client.post(
            "/api/ai/chat",
            headers=headers,
            json={"prompt": "What is Inbound score in September 2026?", "conversation_id": "conv-legacy-db"},
        ).status_code
        == 409
    )

    r_promote_legacy = client.post("/api/ai/conversations/conv-legacy-db/promote", headers=headers)
    assert r_promote_legacy.status_code == 200
    assert r_promote_legacy.json()["data"]["origin"] == "workspace"
    assert (
        client.post(
            "/api/ai/chat",
            headers=headers,
            json={"prompt": "What is Inbound score in September 2026?", "conversation_id": "conv-legacy-db"},
        ).status_code
        == 200
    )
