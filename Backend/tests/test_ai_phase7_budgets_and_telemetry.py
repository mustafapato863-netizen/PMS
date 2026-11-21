"""Phase 7 Ticket 01 & 02 Tests: Telemetry, Traceability, Honest Fallback & Server Budgets."""
from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.routers.ai_workspace as ai_workspace
import services.ai.feature_gate as feature_gate
from config.database import Base, get_db
from models.models import AiInteractionTrace
from models.schemas import (
    CallsData,
    EvaluationData,
    GeoBreakdown,
    GeoData,
    PerformanceRecord,
)
from services.ai.catalog import ai_evidence_cache
from services.ai.provider_engine import (
    ProviderAttempt,
    ProviderMessage,
    ProviderRequest,
    ProviderResponse,
    TokenUsage,
    UnifiedProviderConfig,
    resolve_provider_model,
)
from services.dashboard_record_service import DashboardRecordService
from services.database_record_source import DatabaseRecordSource
from tests.ai_provider_fakes import failed_response, install_scripted_provider, tool_response


@pytest.fixture(autouse=True)
def _setup_env(monkeypatch):
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_PROVIDER_TIMEOUT_SECONDS", "20.0")
    install_scripted_provider(monkeypatch, failed_response())
    ai_evidence_cache.clear()
    yield
    ai_evidence_cache.clear()


@pytest.fixture
def memory_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture
def sample_records() -> list[PerformanceRecord]:
    return [
        PerformanceRecord(
            id="Inbound_EMP501_2026_Sep",
            employee_id="EMP501",
            employee_name="Nadia Fadel",
            team="Inbound",
            month="September",
            year=2026,
            region="EGY",
            branch="dubai",
            raw_data={"Branch": "Dubai"},
            position="Senior Call Center Agent",
            performance_level="Employee",
            status="On Track",
            evaluation=EvaluationData(score=91.0, grade="A"),
            calls=CallsData(inbound=480, total_handled=550, abandoned=0),
            geo=GeoData(
                bookings=GeoBreakdown(dubai=130, sharjah=45, ajman=25, clinics=10),
                attended=GeoBreakdown(dubai=115, sharjah=40, ajman=22, clinics=9),
            ),
            kpi_values=[
                {
                    "kpi_key": "waitingtime",
                    "label": "Waiting Time",
                    "actual_value": 6.2,
                    "target_value": 5.0,
                    "unit": "min",
                    "direction": "lower_better",
                },
                {
                    "kpi_key": "overall_score",
                    "label": "Overall Score",
                    "actual_value": 91.0,
                    "target_value": 85.0,
                    "unit": "%",
                    "direction": "higher_better",
                },
            ],
        )
    ]


def _make_client(memory_db, sample_records, monkeypatch, *, scope_factory=None) -> TestClient:
    monkeypatch.setattr(DatabaseRecordSource, "get_all", lambda *a, **k: sample_records)
    monkeypatch.setattr(DashboardRecordService, "list_analysis_records", lambda *a, **k: sample_records)
    monkeypatch.setattr(DashboardRecordService, "list_record_index", lambda *a, **k: None)
    monkeypatch.setattr(feature_gate, "is_ai_enabled", lambda db: True)
    monkeypatch.setattr(feature_gate, "_legacy_role_header_allowed", lambda: True)

    def default_scope(db, request):
        role = request.headers.get("X-User-Role", "Admin")
        user_id = request.headers.get("X-User-Id", "admin-phase7-1")
        return {
            "role": role,
            "user_id": user_id,
            "has_unrestricted_team_access": role == "Admin",
            "is_admin": role == "Admin",
        }

    monkeypatch.setattr(ai_workspace, "require_authenticated_scope", scope_factory or default_scope)
    monkeypatch.setattr(ai_workspace, "release_read_transaction", lambda db: None)

    app = FastAPI()
    app.include_router(ai_workspace.router, prefix="/api")
    app.include_router(ai_workspace.diagnostics_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: memory_db
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Ticket 01: Telemetry, Traceability, Mid-Turn RBAC & Truthful Fallback
# ---------------------------------------------------------------------------


def test_model_led_turn_populates_trace_id_tokens_neurons_and_cost_status(memory_db, sample_records, monkeypatch):
    captured_requests: list[ProviderRequest] = []

    class TelemetryFakeEngine:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, request: ProviderRequest) -> ProviderResponse:
            captured_requests.append(request)
            self.calls += 1
            if self.calls == 1:
                return ProviderResponse(
                    content=json.dumps(
                        tool_response(
                            "read_employee_metric",
                            employee_name="Nadia Fadel",
                            metric_id="waitingtime",
                            period="2026-09",
                        )
                    ),
                    provider="cloudflare",
                    model="@cf/ibm-granite/granite-4.0-h-micro",
                    outcome="success",
                    latency_ms=12.0,
                    usage=TokenUsage(prompt_tokens=110, completion_tokens=25, total_tokens=135, neurons=180.0),
                    neurons=180.0,
                    estimated_cost_usd=0.00198,
                    attempts=[ProviderAttempt(provider="cloudflare", model="@cf/ibm-granite/granite-4.0-h-micro", status="success")],
                )
            return ProviderResponse(
                content=json.dumps(
                    {
                        "headline": "Nadia Fadel's Waiting Time was 6.2 min in September 2026, exceeding the target limit of 5.0 min by 1.2 min.",
                        "narrative_bullets": ["Target: 5.0 min"],
                    }
                ),
                provider="cloudflare",
                model="@cf/ibm-granite/granite-4.0-h-micro",
                outcome="success",
                latency_ms=18.0,
                usage=TokenUsage(prompt_tokens=210, completion_tokens=45, total_tokens=255, neurons=320.0),
                neurons=320.0,
                estimated_cost_usd=0.00352,
                attempts=[ProviderAttempt(provider="cloudflare", model="@cf/ibm-granite/granite-4.0-h-micro", status="success")],
            )

    from services.ai import provider_engine

    monkeypatch.setattr(provider_engine, "_default_engine", TelemetryFakeEngine())
    client = _make_client(memory_db, sample_records, monkeypatch)

    resp = client.post(
        "/api/ai/chat",
        headers={"X-User-Role": "Admin", "X-User-Id": "admin-trace-check"},
        json={
            "prompt": "What was Nadia Fadel's Waiting Time in September 2026?",
            "session_state": {"team": "Inbound", "month": "September", "year": 2026},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["message"] == "AI analytical response generated"
    data = body["data"]
    assert data["trace_id"], "Expected persisted trace_id on authorized model-led turn"
    assert data["answer_source"] == "model_synthesis"
    assert data["provider_used"] == "cloudflare"

    usage = data["provider_usage"]
    assert usage["input_tokens"] == 320
    assert usage["output_tokens"] == 70
    assert usage["neurons"] == 500
    assert isinstance(usage["estimated_cost_usd"], float)
    assert usage["estimated_cost_usd"] == pytest.approx(0.0055, rel=1e-4)
    assert usage["cost_status"] == "measured_neurons"

    assert len(captured_requests) == 2
    assert all(req.user_id == "admin-trace-check" for req in captured_requests)
    assert all(req.user_role == "Admin" for req in captured_requests)

    trace_row = memory_db.query(AiInteractionTrace).first()
    assert trace_row is not None
    assert str(trace_row.id) == data["trace_id"]


def test_cloudflare_without_neurons_coerces_none_cost_and_reports_unknown(memory_db, sample_records, monkeypatch):
    class NoNeuronsEngine:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, request: ProviderRequest) -> ProviderResponse:
            self.calls += 1
            if self.calls == 1:
                return ProviderResponse(
                    content=json.dumps(
                        tool_response(
                            "read_employee_metric",
                            employee_name="Nadia Fadel",
                            metric_id="waitingtime",
                            period="2026-09",
                        )
                    ),
                    provider="cloudflare",
                    model="@cf/ibm-granite/granite-4.0-h-micro",
                    outcome="success",
                    latency_ms=10.0,
                    usage=TokenUsage(prompt_tokens=90, completion_tokens=20, total_tokens=110, neurons=None),
                    neurons=None,
                    estimated_cost_usd=None,
                    attempts=[ProviderAttempt(provider="cloudflare", model="@cf/ibm-granite/granite-4.0-h-micro", status="success")],
                )
            return ProviderResponse(
                content=json.dumps(
                    {
                        "headline": "Nadia Fadel's Waiting Time was 6.2 min in September 2026, exceeding the target limit of 5.0 min by 1.2 min.",
                        "narrative_bullets": [],
                    }
                ),
                provider="cloudflare",
                model="@cf/ibm-granite/granite-4.0-h-micro",
                outcome="success",
                latency_ms=15.0,
                usage=TokenUsage(prompt_tokens=140, completion_tokens=30, total_tokens=170, neurons=None),
                neurons=None,
                estimated_cost_usd=None,
                attempts=[ProviderAttempt(provider="cloudflare", model="@cf/ibm-granite/granite-4.0-h-micro", status="success")],
            )

    from services.ai import provider_engine

    monkeypatch.setattr(provider_engine, "_default_engine", NoNeuronsEngine())
    client = _make_client(memory_db, sample_records, monkeypatch)

    resp = client.post(
        "/api/ai/chat",
        headers={"X-User-Role": "Admin"},
        json={
            "prompt": "What was Nadia Fadel's Waiting Time in September 2026?",
            "session_state": {"team": "Inbound", "month": "September", "year": 2026},
        },
    )
    assert resp.status_code == 200, resp.text
    usage = resp.json()["data"]["provider_usage"]
    assert usage["input_tokens"] == 230
    assert usage["output_tokens"] == 50
    assert usage["neurons"] == 0
    assert usage["estimated_cost_usd"] == 0.0
    assert usage["cost_status"] == "unknown"


def test_model_led_turn_mid_turn_permission_revocation_blocks_evidence_and_trace(memory_db, sample_records, monkeypatch):
    from services.ai import provider_engine
    from services.ai.conversation_service import AiConversationService

    # Allow initial auth + tool check, then narrow scope mid-turn during Pass 2 synthesis
    state = {"narrowed": False}
    orig_validate = AiConversationService.validate_live_account_and_scope

    def narrowing_validate(self, scope=None):
        base = orig_validate(self, scope)
        if state["narrowed"]:
            return {
                **base,
                "role": "Manager",
                "has_unrestricted_team_access": False,
                "is_admin": False,
                "accessible_teams": ["Coding"],
            }
        return base

    monkeypatch.setattr(AiConversationService, "validate_live_account_and_scope", narrowing_validate)

    class TwoPassEngine:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, request: ProviderRequest) -> ProviderResponse:
            self.calls += 1
            if self.calls == 1:
                return ProviderResponse(
                    content=json.dumps(
                        tool_response(
                            "read_employee_metric",
                            employee_name="Nadia Fadel",
                            metric_id="waitingtime",
                            period="2026-09",
                        )
                    ),
                    provider="cloudflare",
                    model="@cf/ibm-granite/granite-4.0-h-micro",
                    outcome="success",
                    latency_ms=10.0,
                    usage=TokenUsage(prompt_tokens=80, completion_tokens=20, total_tokens=100),
                )
            # Simulate admin narrowing the caller's role/teams while Pass 2 synthesis runs
            state["narrowed"] = True
            return ProviderResponse(
                content=json.dumps(
                    {
                        "headline": "Nadia Fadel's Waiting Time was 6.2 min in September 2026.",
                        "narrative_bullets": [],
                    }
                ),
                provider="cloudflare",
                model="@cf/ibm-granite/granite-4.0-h-micro",
                outcome="success",
                latency_ms=10.0,
                usage=TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
            )

    monkeypatch.setattr(provider_engine, "_default_engine", TwoPassEngine())
    client = _make_client(memory_db, sample_records, monkeypatch)

    resp = client.post(
        "/api/ai/chat",
        headers={"X-User-Role": "Admin"},
        json={
            "prompt": "What was Nadia Fadel's Waiting Time in September 2026?",
            "session_state": {"team": "Inbound", "month": "September", "year": 2026},
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["outcome"] == "restricted_access"
    assert data["trace_id"] == ""
    assert data["typed_evidence"] == []
    assert data["visual_cards"] == []
    assert "6.2" not in data["headline"]
    assert memory_db.query(func.count(AiInteractionTrace.id)).scalar() == 0


def test_model_led_fallback_reports_deterministic_provider_and_truthful_message(memory_db, sample_records, monkeypatch):
    install_scripted_provider(
        monkeypatch,
        [
            tool_response("read_employee_metric", employee_name="Nadia Fadel", metric_id="waitingtime", period="2026-09"),
            failed_response("timeout"),
        ],
    )
    client = _make_client(memory_db, sample_records, monkeypatch)

    resp = client.post(
        "/api/ai/chat",
        headers={"X-User-Role": "Admin"},
        json={
            "prompt": "What was Nadia Fadel's Waiting Time in September 2026?",
            "session_state": {"team": "Inbound", "month": "September", "year": 2026},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["message"] == "Deterministic fallback response generated"
    data = body["data"]
    assert data["provider_used"] == "deterministic"
    assert data["answer_source"] == "fallback"
    assert data["trace_id"]


def test_resolve_provider_model_rejects_unapproved_nvidia_model(caplog):
    cfg = UnifiedProviderConfig(nvidia_model="nvidia/nemotron-3.5-super-vl-120b-a12b")
    req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="hi")],
        model="nvidia-3.5-flash",
    )
    with caplog.at_level(logging.WARNING):
        resolved = resolve_provider_model("nvidia", cfg, req)
    assert resolved == cfg.nvidia_model
    assert "Rejected unapproved Nvidia model override" not in caplog.text


# ---------------------------------------------------------------------------
# Ticket 02: Concurrency Budgets, Configurable Per-User Caps & Diagnostics
# ---------------------------------------------------------------------------


def test_concurrency_budget_returns_429_with_retry_after_and_increments_rejected(memory_db, sample_records, monkeypatch):
    import threading
    from services.ai import provider_engine
    from services.ai.usage_budget import reset_usage_budget_state_for_tests

    reset_usage_budget_state_for_tests()
    monkeypatch.setenv("PMS_AI_MAX_CONCURRENT_CHAT_REQUESTS", "1")
    monkeypatch.setenv("PMS_AI_DAILY_USER_REQUEST_LIMIT", "0")
    monkeypatch.setenv("PMS_AI_DAILY_USER_TOKEN_LIMIT", "0")

    entered = threading.Event()
    release = threading.Event()

    class BlockingEngine:
        def generate(self, request: ProviderRequest) -> ProviderResponse:
            entered.set()
            release.wait(timeout=5.0)
            return failed_response("timeout")

    monkeypatch.setattr(provider_engine, "_default_engine", BlockingEngine())
    client = _make_client(memory_db, sample_records, monkeypatch)

    first_result: dict[str, int] = {}

    def run_first():
        r = client.post(
            "/api/ai/chat",
            headers={"X-User-Role": "Admin", "X-User-Id": "admin-conc-1"},
            json={
                "prompt": "What was Nadia Fadel's Waiting Time in September 2026?",
                "session_state": {"team": "Inbound", "month": "September", "year": 2026},
            },
        )
        first_result["status"] = r.status_code

    t = threading.Thread(target=run_first, daemon=True)
    t.start()
    try:
        assert entered.wait(timeout=3.0), "First request did not enter provider engine"
        second_resp = client.post(
            "/api/ai/chat",
            headers={"X-User-Role": "Admin", "X-User-Id": "admin-conc-2"},
            json={
                "prompt": "What was Nadia Fadel's Waiting Time in September 2026?",
                "session_state": {"team": "Inbound", "month": "September", "year": 2026},
            },
        )
        assert second_resp.status_code == 429
        assert "Retry-After" in second_resp.headers
    finally:
        release.set()
        t.join(timeout=5.0)

    assert first_result.get("status") == 200
    diag = client.get("/api/ai/diagnostics", headers={"X-User-Role": "Admin"})
    assert diag.status_code == 200
    assert diag.json()["data"]["rejected_budget_requests"] >= 1
    reset_usage_budget_state_for_tests()


def test_default_unconfigured_daily_caps_are_zero_and_allow_requests(memory_db, sample_records, monkeypatch):
    from services.ai.usage_budget import reset_usage_budget_state_for_tests

    reset_usage_budget_state_for_tests()
    monkeypatch.delenv("PMS_AI_DAILY_USER_REQUEST_LIMIT", raising=False)
    monkeypatch.delenv("PMS_AI_DAILY_USER_TOKEN_LIMIT", raising=False)

    client = _make_client(memory_db, sample_records, monkeypatch)
    diag = client.get("/api/ai/diagnostics", headers={"X-User-Role": "Admin"})
    assert diag.status_code == 200, diag.text
    diag_data = diag.json()["data"]
    assert diag_data["daily_user_request_limit"] == 0
    assert diag_data["daily_user_token_limit"] == 0

    for idx in range(3):
        resp = client.post(
            "/api/ai/chat",
            headers={"X-User-Role": "Admin", "X-User-Id": "admin-unlimited"},
            json={
                "prompt": "Hello",
                "session_state": {"team": "Inbound", "month": "September", "year": 2026},
            },
        )
        assert resp.status_code == 200, f"Turn {idx} failed: {resp.text}"
    reset_usage_budget_state_for_tests()


def test_configured_daily_user_request_limit_rejects_third_but_allows_idempotent_replay(memory_db, sample_records, monkeypatch):
    from services.ai.usage_budget import reset_usage_budget_state_for_tests

    reset_usage_budget_state_for_tests()
    monkeypatch.setenv("PMS_AI_DAILY_USER_REQUEST_LIMIT", "2")
    monkeypatch.setenv("PMS_AI_DAILY_USER_TOKEN_LIMIT", "0")

    client = _make_client(memory_db, sample_records, monkeypatch)
    conv_resp = client.post(
        "/api/ai/conversations",
        headers={"X-User-Role": "Admin", "X-User-Id": "admin-cap-user"},
        json={"origin": "workspace"},
    )
    assert conv_resp.status_code == 200, conv_resp.text
    conv_id = conv_resp.json()["data"]["conversation_id"]

    r1 = client.post(
        "/api/ai/chat",
        headers={"X-User-Role": "Admin", "X-User-Id": "admin-cap-user"},
        json={
            "prompt": "What was Nadia Fadel's Waiting Time in September 2026?",
            "conversation_id": conv_id,
            "client_request_id": "req-1",
            "session_state": {"team": "Inbound", "month": "September", "year": 2026},
        },
    )
    assert r1.status_code == 200, r1.text

    r2 = client.post(
        "/api/ai/chat",
        headers={"X-User-Role": "Admin", "X-User-Id": "admin-cap-user"},
        json={
            "prompt": "What was Nadia Fadel's Overall Score in September 2026?",
            "conversation_id": conv_id,
            "client_request_id": "req-2",
            "context_version": r1.json()["data"]["context_version"],
            "session_state": {"team": "Inbound", "month": "September", "year": 2026},
        },
    )
    assert r2.status_code == 200, r2.text

    # Replaying req-2 with same client_request_id must succeed without burning Turn 3 quota
    replay = client.post(
        "/api/ai/chat",
        headers={"X-User-Role": "Admin", "X-User-Id": "admin-cap-user"},
        json={
            "prompt": "What was Nadia Fadel's Overall Score in September 2026?",
            "conversation_id": conv_id,
            "client_request_id": "req-2",
            "context_version": r1.json()["data"]["context_version"],
            "session_state": {"team": "Inbound", "month": "September", "year": 2026},
        },
    )
    assert replay.status_code == 200, replay.text

    # New turn 3 exceeds the daily request limit of 2
    r3 = client.post(
        "/api/ai/chat",
        headers={"X-User-Role": "Admin", "X-User-Id": "admin-cap-user"},
        json={
            "prompt": "Show Inbound team summary",
            "conversation_id": conv_id,
            "client_request_id": "req-3",
            "context_version": r2.json()["data"]["context_version"],
            "session_state": {"team": "Inbound", "month": "September", "year": 2026},
        },
    )
    assert r3.status_code == 429
    assert "Retry-After" in r3.headers
    reset_usage_budget_state_for_tests()


def test_configured_daily_token_limit_blocks_chat_and_provider_engine(memory_db, sample_records, monkeypatch):
    from services.ai import provider_engine
    from services.ai.provider_engine import UnifiedProviderEngine
    from services.ai.usage_budget import reset_usage_budget_state_for_tests

    reset_usage_budget_state_for_tests()
    monkeypatch.setenv("PMS_AI_DAILY_USER_REQUEST_LIMIT", "0")
    monkeypatch.setenv("PMS_AI_DAILY_USER_TOKEN_LIMIT", "250")

    class TokenSpendingEngine:
        def generate(self, request: ProviderRequest) -> ProviderResponse:
            return ProviderResponse(
                content=json.dumps(
                    tool_response(
                        "read_employee_metric",
                        employee_name="Nadia Fadel",
                        metric_id="waitingtime",
                        period="2026-09",
                    )
                ),
                provider="cloudflare",
                model="@cf/ibm-granite/granite-4.0-h-micro",
                outcome="success",
                latency_ms=10.0,
                usage=TokenUsage(prompt_tokens=120, completion_tokens=30, total_tokens=150),
            )

    monkeypatch.setattr(provider_engine, "_default_engine", TokenSpendingEngine())
    client = _make_client(memory_db, sample_records, monkeypatch)

    r1 = client.post(
        "/api/ai/chat",
        headers={"X-User-Role": "Admin", "X-User-Id": "admin-tok-user"},
        json={
            "prompt": "What was Nadia Fadel's Waiting Time in September 2026?",
            "session_state": {"team": "Inbound", "month": "September", "year": 2026},
        },
    )
    assert r1.status_code == 200, r1.text
    # Two calls (router + synth) consumed 300 tokens > 250 daily token cap
    r2 = client.post(
        "/api/ai/chat",
        headers={"X-User-Role": "Admin", "X-User-Id": "admin-tok-user"},
        json={
            "prompt": "What was Nadia Fadel's Waiting Time in September 2026?",
            "session_state": {"team": "Inbound", "month": "September", "year": 2026},
        },
    )
    assert r2.status_code == 429
    assert "Retry-After" in r2.headers

    # UnifiedProviderEngine.generate must also enforce _check_user_limits
    real_engine = UnifiedProviderEngine(config=UnifiedProviderConfig())
    eng_resp = real_engine.generate(
        ProviderRequest(
            messages=[ProviderMessage(role="user", content="hello")],
            user_id="admin-tok-user",
            user_role="Admin",
        )
    )
    assert eng_resp.is_success is False
    assert eng_resp.outcome == "rate_limited"
    reset_usage_budget_state_for_tests()


def test_request_input_token_ceiling_defaults_to_256k(monkeypatch):
    from services.ai.usage_budget import max_request_input_tokens

    monkeypatch.delenv("PMS_AI_MAX_REQUEST_INPUT_TOKENS", raising=False)
    monkeypatch.delenv("PMS_AI_CONTEXT_TOKENS", raising=False)
    assert max_request_input_tokens() == 262144

    # A single 256k context setting now raises the hard per-request ceiling too.
    monkeypatch.setenv("PMS_AI_CONTEXT_TOKENS", "262144")
    assert max_request_input_tokens() == 262144

    # Even an absurd override cannot exceed the hard cap.
    monkeypatch.setenv("PMS_AI_MAX_REQUEST_INPUT_TOKENS", "999999")
    assert max_request_input_tokens() == 262144


def test_request_input_token_ceiling_blocks_oversized_prompt_before_http(memory_db, sample_records, monkeypatch):
    from unittest.mock import MagicMock
    from services.ai.provider_engine import UnifiedProviderEngine
    from services.ai.usage_budget import reset_usage_budget_state_for_tests

    reset_usage_budget_state_for_tests()
    monkeypatch.setenv("PMS_AI_MAX_REQUEST_INPUT_TOKENS", "50")

    mock_cf = MagicMock()
    mock_gem = MagicMock()
    engine = UnifiedProviderEngine(
        config=UnifiedProviderConfig(
            cloudflare_enabled=True,
            cloudflare_account_id="acct",
            cloudflare_api_token="tok",
        ),
        cloudflare_adapter=mock_cf,
        nvidia_adapter=mock_gem,
    )
    resp = engine.generate(
        ProviderRequest(
            messages=[ProviderMessage(role="user", content="word " * 200)],
        )
    )
    assert resp.is_success is False
    assert resp.outcome == "context_overflow"
    mock_cf.execute.assert_not_called()
    mock_gem.execute.assert_not_called()

    client = _make_client(memory_db, sample_records, monkeypatch)
    http_resp = client.post(
        "/api/ai/chat",
        headers={"X-User-Role": "Admin", "X-User-Id": "admin-oversized"},
        json={"prompt": "word " * 200},
    )
    assert http_resp.status_code == 429
    reset_usage_budget_state_for_tests()


def test_diagnostics_reports_budget_timeout_and_pilot_fields_without_secrets(memory_db, sample_records, monkeypatch):
    from services.ai.usage_budget import reset_usage_budget_state_for_tests

    reset_usage_budget_state_for_tests()
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_MAX_CONCURRENT_CHAT_REQUESTS", "8")
    monkeypatch.setenv("PMS_AI_DAILY_USER_REQUEST_LIMIT", "0")
    monkeypatch.setenv("PMS_AI_DAILY_USER_TOKEN_LIMIT", "0")
    monkeypatch.setenv("PMS_AI_MAX_REQUEST_INPUT_TOKENS", "8192")
    monkeypatch.setenv("PMS_AI_ROUTER_TIMEOUT_SECONDS", "12.0")
    monkeypatch.setenv("PMS_AI_SYNTHESIS_TIMEOUT_SECONDS", "18.0")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "super-secret-cf-token-value")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "super-secret-account-id-123456")
    monkeypatch.setenv("NVIDIA_API_KEY_ALTER", "AIzaSySuperSecretNvidiaKeyValue12345")

    client = _make_client(memory_db, sample_records, monkeypatch)
    resp = client.get("/api/ai/diagnostics", headers={"X-User-Role": "Admin"})
    assert resp.status_code == 200, resp.text
    raw_text = resp.text
    assert "super-secret-cf-token-value" not in raw_text
    assert "super-secret-account-id-123456" not in raw_text
    assert "AIzaSySuperSecretNvidiaKeyValue12345" not in raw_text

    data = resp.json()["data"]
    assert data["model_led_pilot_enabled"] is True
    assert data["max_concurrent_requests"] == 8
    assert data["active_concurrent_requests"] == 0
    assert data["daily_user_request_limit"] == 0
    assert data["daily_user_token_limit"] == 0
    assert data["max_request_input_tokens"] == 8192
    assert data["router_timeout_seconds"] == 12.0
    assert data["synthesis_timeout_seconds"] == 18.0
    assert data["rejected_budget_requests"] == 0
    reset_usage_budget_state_for_tests()
