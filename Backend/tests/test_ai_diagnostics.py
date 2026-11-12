from __future__ import annotations

import json
import time
from unittest.mock import MagicMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.middleware.auth_middleware import AuthMiddleware
from api.routers import ai_workspace
from config.database import Base, get_db
from models.models import ProductSetting, User
from services.ai import feature_gate
from services.ai.feature_gate import read_ai_enabled, set_ai_enabled
from services.ai.llm_client import provider_status
from services.auth_service import AuthenticationService


@pytest.fixture(autouse=True)
def _bind_real_ai_switch(monkeypatch):
    """Ensure tests in this module test the actual switch state from the database."""
    monkeypatch.setattr(feature_gate, "is_ai_enabled", read_ai_enabled)


def _create_test_app(session):
    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.include_router(ai_workspace.router, prefix="/api")
    app.include_router(ai_workspace.diagnostics_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: session
    return app


@pytest.fixture
def test_db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _get_user_token(db, username: str, role: str) -> str:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        AuthenticationService.create_user(db, username, f"{username}@test.invalid", "TestSecret123!", role)
    return AuthenticationService.authenticate_user(db, username, "TestSecret123!")


def test_1_non_admin_receives_403_on_diagnostics_and_workspace(test_db_session):
    """Non-admin roles must receive HTTP 403 on diagnostics and workspace endpoints."""
    # Enable AI so we specifically test the Admin-only pilot role boundary
    test_db_session.add(ProductSetting(key="ai_enabled", enabled=True))
    test_db_session.commit()

    try:
        app = _create_test_app(test_db_session)
        client = TestClient(app, raise_server_exceptions=False)

        for non_admin_role in ("Manager", "Employee", "Viewer"):
            username = f"user_{non_admin_role.lower()}"
            tok = _get_user_token(test_db_session, username, non_admin_role)
            headers = {"Authorization": f"Bearer {tok}"}

            # Diagnostics endpoint: 403 Forbidden
            resp_diag = client.get("/api/ai/diagnostics", headers=headers)
            assert resp_diag.status_code == 403, f"Expected 403 for {non_admin_role} on diagnostics, got {resp_diag.status_code}"

            # Workspace chat endpoint: 403 Forbidden
            resp_chat = client.post("/api/ai/chat", json={"prompt": "Hi"}, headers=headers)
            assert resp_chat.status_code == 403, f"Expected 403 for {non_admin_role} on chat, got {resp_chat.status_code}"
    finally:
        test_db_session.query(ProductSetting).delete()
        test_db_session.commit()


def test_2_feature_switch_off_returns_disabled_status_cleanly(test_db_session):
    """When the feature switch is off, diagnostics report disabled cleanly and routes reject with 403 without 500."""
    test_db_session.query(ProductSetting).delete()
    test_db_session.commit()

    app = _create_test_app(test_db_session)
    client = TestClient(app, raise_server_exceptions=False)

    # 1. Direct diagnostic builder cleanly reports feature_enabled=False
    assert read_ai_enabled(test_db_session) is False
    from api.routers.ai_workspace import build_ai_diagnostics_payload
    payload = build_ai_diagnostics_payload(test_db_session)
    assert payload.feature_enabled is False

    tok = _get_user_token(test_db_session, "admin_user", "Admin")
    headers_admin = {"Authorization": f"Bearer {tok}"}

    # 2. When the switch is off, diagnostics still load for an Admin and chat stays closed.
    resp_diag = client.get("/api/ai/diagnostics", headers=headers_admin)
    assert resp_diag.status_code == 200
    assert resp_diag.json()["data"]["feature_enabled"] is False

    resp_chat = client.post("/api/ai/chat", json={"prompt": "Hi"}, headers=headers_admin)
    assert resp_chat.status_code == 403
    assert "turned off" in resp_chat.json()["detail"].lower()

    # 3. When switch is turned on, diagnostics endpoint returns 200 with feature_enabled=True
    set_ai_enabled(test_db_session, True, "00000000-0000-0000-0000-000000000001")
    resp_diag_on = client.get("/api/ai/diagnostics", headers=headers_admin)
    assert resp_diag_on.status_code == 200
    assert resp_diag_on.json()["data"]["feature_enabled"] is True


def test_anonymous_caller_is_rejected_on_diagnostics_before_any_role_check(test_db_session):
    """No token and no legacy header: the diagnostics route answers 401, not 403."""
    test_db_session.query(ProductSetting).delete()
    test_db_session.commit()

    app = _create_test_app(test_db_session)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/ai/diagnostics")
    assert resp.status_code == 401
    assert "authorization" in resp.json()["detail"].lower()


_PROVIDER_ENV = (
    "PMS_AI_PRIMARY_PROVIDER", "PMS_AI_FALLBACK_PROVIDER", "PMS_AI_CLOUDFLARE_ENABLED", "PMS_AI_GEMINI_ENABLED",
    "PMS_AI_FALLBACK_ENABLED", "CLOUDFLARE_ACCOUNT_ID", "CF_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "CF_API_TOKEN",
    "CLOUDFLARE_API_KEY", "GEMINI_API_KEY", "Gemini_API_KEY", "GOOGLE_API_KEY", "CLOUDFLARE_AI_MODEL", "CF_AI_MODEL",
    "PMS_CLOUDFLARE_MODEL", "PMS_GEMINI_MODEL", "PMS_AI_GEMINI_MODEL", "GEMINI_MODEL",
)


@pytest.fixture
def clean_provider_env(monkeypatch):
    from services.ai.llm_client import clear_fallback_reason, clear_live_verification
    clear_fallback_reason()
    clear_live_verification()
    for name in _PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: pytest.fail("diagnostics must not make a network call"))
    monkeypatch.setattr("urllib.request.build_opener", lambda *a, **k: pytest.fail("diagnostics must not make a network call"))
    return monkeypatch


def test_3_no_credentials_reports_unavailable_without_a_network_probe(clean_provider_env):
    health = provider_status()
    assert health["available"] is False
    assert health["endpoint_configured"] is False
    assert health["active_provider"] == "deterministic"
    assert health["reason"] == "no_credentials_configured"
    assert health["primary_provider"] == "cloudflare"
    assert health["fallback_provider"] == "gemini"


def test_4_cloudflare_credentials_make_cloudflare_the_active_provider(clean_provider_env):
    clean_provider_env.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-test")
    clean_provider_env.setenv("CLOUDFLARE_API_TOKEN", "token-test-not-real")
    health = provider_status()
    assert health["available"] is True
    assert health["active_provider"] == "cloudflare"
    assert health["configured_model"] == "@cf/ibm-granite/granite-4.0-h-micro"
    assert health["endpoint_host"] == "api.cloudflare.com"
    assert health["reason"] == "configured"
    assert "token-test-not-real" not in json.dumps(health)


def test_5_gemini_only_credentials_fall_back_to_gemini(clean_provider_env):
    clean_provider_env.setenv("GEMINI_API_KEY", "key-test-not-real")
    health = provider_status()
    assert health["available"] is True
    assert health["active_provider"] == "gemini"
    assert health["configured_model"] == "gemini-2.5-flash"
    assert health["reason"] == "primary_unconfigured_fallback_only"
    assert "key-test-not-real" not in json.dumps(health)

    # Candidate model is configurable via PMS_GEMINI_MODEL
    clean_provider_env.setenv("PMS_GEMINI_MODEL", "gemini-3.5-flash-lite")
    health_candidate = provider_status()
    assert health_candidate["configured_model"] == "gemini-3.5-flash-lite"


def test_6_disabled_providers_are_never_active(clean_provider_env):
    clean_provider_env.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-test")
    clean_provider_env.setenv("CLOUDFLARE_API_TOKEN", "token-test-not-real")
    clean_provider_env.setenv("GEMINI_API_KEY", "key-test-not-real")
    clean_provider_env.setenv("PMS_AI_CLOUDFLARE_ENABLED", "false")
    clean_provider_env.setenv("PMS_AI_GEMINI_ENABLED", "false")
    health = provider_status()
    assert health["available"] is False
    assert health["active_provider"] == "deterministic"


def test_7_openai_can_never_be_selected_even_when_configured(clean_provider_env):
    clean_provider_env.setenv("PMS_AI_PRIMARY_PROVIDER", "openai")
    clean_provider_env.setenv("PMS_AI_FALLBACK_PROVIDER", "openai")
    clean_provider_env.setenv("PMS_AI_OPENAI_ENABLED", "true")
    clean_provider_env.setenv("OPENAI_API_KEY", "sk-test-not-real")
    health = provider_status()
    assert health["primary_provider"] == "cloudflare"
    assert health["fallback_provider"] == "gemini"
    assert health["active_provider"] == "deterministic"


def test_8_diagnostics_payload_providers_are_cloudflare_gemini_or_deterministic(clean_provider_env, test_db_session):
    from api.routers.ai_workspace import build_ai_diagnostics_payload

    clean_provider_env.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-test")
    clean_provider_env.setenv("CLOUDFLARE_API_TOKEN", "token-test-not-real")
    clean_provider_env.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "true")
    clean_provider_env.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    payload = build_ai_diagnostics_payload(test_db_session)
    assert payload.routing_provider == "cloudflare"
    assert payload.synthesis_provider == "cloudflare"
    assert payload.model_endpoint_host == "api.cloudflare.com"
    assert payload.inference_verified is False
    assert "token-test-not-real" not in payload.model_dump_json()


# ---------------------------------------------------------------------------
# Phase 1 & 2 Live Verification and 6-State Diagnostics Tests
# ---------------------------------------------------------------------------


def test_9_diagnostics_six_states_distinction(clean_provider_env):
    """Verify clean transitions across the 6 diagnostic states without network calls."""
    from services.ai.llm_client import (
        STATUS_CONFIGURED,
        STATUS_UNAVAILABLE,
        STATUS_CREDENTIALS_PRESENT,
        STATUS_LIVE_VERIFIED,
        STATUS_LIVE_FAILED,
        STATUS_FALLBACK_ACTIVE,
        clear_live_verification,
        record_live_verification,
    )

    clear_live_verification()

    # 1. STATUS_CONFIGURED: Provider enabled in config, but credentials not yet configured
    st1 = provider_status()
    assert st1["status_code"] == STATUS_CONFIGURED
    assert st1["live_verified"] is False
    assert st1["reason"] == "no_credentials_configured"

    # 2. STATUS_UNAVAILABLE: Providers explicitly disabled in config
    clean_provider_env.setenv("PMS_AI_CLOUDFLARE_ENABLED", "false")
    clean_provider_env.setenv("PMS_AI_GEMINI_ENABLED", "false")
    st_unavail = provider_status()
    assert st_unavail["status_code"] == STATUS_UNAVAILABLE
    assert st_unavail["available"] is False
    clean_provider_env.delenv("PMS_AI_CLOUDFLARE_ENABLED", raising=False)
    clean_provider_env.delenv("PMS_AI_GEMINI_ENABLED", raising=False)

    # 3. STATUS_CREDENTIALS_PRESENT: Credentials configured, but live verification not yet executed
    clean_provider_env.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-test")
    clean_provider_env.setenv("CLOUDFLARE_API_TOKEN", "token-test")
    st2 = provider_status()
    assert st2["status_code"] == STATUS_CREDENTIALS_PRESENT
    assert st2["live_verified"] is False

    # 4. STATUS_LIVE_VERIFIED: Explicit successful live verification recorded
    record_live_verification({
        "verified": True,
        "provider": "cloudflare",
        "model": "@cf/ibm-granite/granite-4.0-h-micro",
        "total_latency_ms": 125.0,
    })
    st3 = provider_status()
    assert st3["status_code"] == STATUS_LIVE_VERIFIED
    assert st3["live_verified"] is True
    assert st3["live_verification"]["latency_ms"] == 125.0

    # 5. STATUS_LIVE_FAILED: Explicit failed live verification recorded
    record_live_verification({
        "verified": False,
        "provider": "cloudflare",
        "model": "@cf/ibm-granite/granite-4.0-h-micro",
        "total_latency_ms": 450.0,
        "error": "Cloudflare 401 Unauthorized",
    })
    st4 = provider_status()
    assert st4["status_code"] == STATUS_LIVE_FAILED
    assert st4["live_verified"] is False
    assert "401" in st4["live_verification"]["error"]

    # 6. STATUS_FALLBACK_ACTIVE: Primary unconfigured, fallback configured
    clear_live_verification()
    clean_provider_env.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    clean_provider_env.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    clean_provider_env.setenv("GEMINI_API_KEY", "gemini-key-test")
    st5 = provider_status()
    assert st5["status_code"] == STATUS_FALLBACK_ACTIVE
    assert st5["active_provider"] == "gemini"


def test_10_verify_live_endpoint_admin_success(test_db_session, monkeypatch):
    """POST /api/ai/diagnostics/verify-live succeeds for Admin and records live verified state."""
    from scripts import verify_cloudflare_ai
    from services.ai.llm_client import clear_live_verification, get_live_verification

    clear_live_verification()
    ai_workspace._daily_verify_counts.clear()
    ai_workspace._live_verify_in_flight = False
    monkeypatch.setenv("PMS_AI_LIVE_VERIFY_ENDPOINT_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-acct-123456789012345678901234")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cfut_testtoken12345678901234567890")

    app = _create_test_app(test_db_session)
    client = TestClient(app, raise_server_exceptions=False)

    fake_result = {
        "verified": True,
        "provider": "cloudflare",
        "model": "@cf/ibm-granite/granite-4.0-h-micro",
        "account_id_configured": True,
        "api_token_configured": True,
        "test_a_completion": {"status": "passed", "latency_ms": 110.0},
        "test_b_structured": {"status": "passed", "latency_ms": 220.0},
        "total_latency_ms": 330.0,
        "error": None,
    }
    monkeypatch.setattr(verify_cloudflare_ai, "run_live_verification", lambda **kwargs: fake_result)

    tok = _get_user_token(test_db_session, "admin_user_verify", "Admin")
    headers = {"Authorization": f"Bearer {tok}"}

    resp = client.post("/api/ai/diagnostics/verify-live", headers=headers)
    assert resp.status_code == 200
    res_body = resp.json()
    assert res_body["success"] is True
    data = res_body["data"]
    assert data["inference_verified"] is True
    assert data["provider_status_code"] == "live_verified"
    assert data["live_verification_latency_ms"] == 330.0

    live_state = get_live_verification()
    assert live_state["verified"] is True
    assert live_state["provider"] == "cloudflare"


def test_11_verify_live_endpoint_non_admin_forbidden(test_db_session, monkeypatch):
    """POST /api/ai/diagnostics/verify-live is forbidden for non-Admin callers."""
    monkeypatch.setenv("PMS_AI_LIVE_VERIFY_ENDPOINT_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "development")
    app = _create_test_app(test_db_session)
    client = TestClient(app, raise_server_exceptions=False)

    for role in ("Manager", "Employee", "Viewer"):
        username = f"user_block_{role.lower()}"
        tok = _get_user_token(test_db_session, username, role)
        headers = {"Authorization": f"Bearer {tok}"}
        resp = client.post("/api/ai/diagnostics/verify-live", headers=headers)
        assert resp.status_code == 403, f"Expected 403 for role {role}, got {resp.status_code}"


def test_12_verify_cloudflare_ai_script_mocked(monkeypatch):
    """Unit test verify_cloudflare_ai.run_live_verification with mocked urllib calls."""
    from scripts.verify_cloudflare_ai import run_live_verification

    call_count = 0

    def fake_urlopen(req, timeout=None):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        if call_count == 1:
            body = json.dumps({
                "choices": [{"message": {"role": "assistant", "content": "PMS AI connection successful."}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                "success": True,
            }).encode("utf-8")
        else:
            body = json.dumps({
                "choices": [{"message": {"role": "assistant", "content": '{"intent": "performance_lookup", "requires_data": true}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 15, "completion_tokens": 8, "total_tokens": 23},
                "success": True,
            }).encode("utf-8")
        resp.read.side_effect = [body, b""]
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    res = run_live_verification(
        account_id="fake-acct-123",
        api_token="mock-cf-token-12345",
        model="@cf/ibm-granite/granite-4.0-h-micro",
        timeout=5.0,
    )
    assert res["verified"] is True
    assert res["test_a_completion"]["status"] == "passed"
    assert res["test_b_structured"]["status"] == "passed"
    assert res["error"] is None


def test_13_live_endpoint_disabled_by_default(test_db_session, monkeypatch):
    """POST /api/ai/diagnostics/verify-live returns 403 when the enablement flag is false."""
    monkeypatch.delenv("PMS_AI_LIVE_VERIFY_ENDPOINT_ENABLED", raising=False)
    app = _create_test_app(test_db_session)
    client = TestClient(app, raise_server_exceptions=False)
    tok = _get_user_token(test_db_session, "admin_user_flag", "Admin")
    headers = {"Authorization": f"Bearer {tok}"}

    resp = client.post("/api/ai/diagnostics/verify-live", headers=headers)
    assert resp.status_code == 403
    assert "disabled by configuration" in resp.json()["detail"]


def test_14_live_endpoint_blocked_in_production(test_db_session, monkeypatch):
    """POST /api/ai/diagnostics/verify-live returns 403 in production environment."""
    monkeypatch.setenv("PMS_AI_LIVE_VERIFY_ENDPOINT_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("PMS_AI_ALLOW_PRODUCTION_LIVE_VERIFY", raising=False)
    app = _create_test_app(test_db_session)
    client = TestClient(app, raise_server_exceptions=False)
    tok = _get_user_token(test_db_session, "admin_user_prod", "Admin")
    headers = {"Authorization": f"Bearer {tok}"}

    resp = client.post("/api/ai/diagnostics/verify-live", headers=headers)
    assert resp.status_code == 403
    assert "disabled in production" in resp.json()["detail"]


def test_15_live_endpoint_daily_budget_exceeded(test_db_session, monkeypatch):
    """POST /api/ai/diagnostics/verify-live returns 429 when daily budget is exhausted."""
    monkeypatch.setenv("PMS_AI_LIVE_VERIFY_ENDPOINT_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("PMS_AI_LIVE_VERIFY_DAILY_BUDGET", "2")
    ai_workspace._daily_verify_counts.clear()
    ai_workspace._live_verify_in_flight = False

    app = _create_test_app(test_db_session)
    client = TestClient(app, raise_server_exceptions=False)
    tok = _get_user_token(test_db_session, "admin_user_budget", "Admin")
    headers = {"Authorization": f"Bearer {tok}"}

    from scripts import verify_cloudflare_ai
    fake_result = {"verified": True, "provider": "cloudflare", "model": "test", "total_latency_ms": 50.0}
    monkeypatch.setattr(verify_cloudflare_ai, "run_live_verification", lambda **kwargs: fake_result)

    # First 2 calls pass
    r1 = client.post("/api/ai/diagnostics/verify-live", headers=headers)
    assert r1.status_code == 200
    r2 = client.post("/api/ai/diagnostics/verify-live", headers=headers)
    assert r2.status_code == 200

    # 3rd call exceeds budget
    r3 = client.post("/api/ai/diagnostics/verify-live", headers=headers)
    assert r3.status_code == 429
    assert "daily budget exceeded" in r3.json()["detail"]


def test_16_live_endpoint_rejects_concurrent_execution(test_db_session, monkeypatch):
    """POST /api/ai/diagnostics/verify-live returns 429 if another check is already in-flight."""
    monkeypatch.setenv("PMS_AI_LIVE_VERIFY_ENDPOINT_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "development")
    ai_workspace._live_verify_in_flight = True  # Simulate active execution

    app = _create_test_app(test_db_session)
    client = TestClient(app, raise_server_exceptions=False)
    tok = _get_user_token(test_db_session, "admin_user_concurrent", "Admin")
    headers = {"Authorization": f"Bearer {tok}"}

    resp = client.post("/api/ai/diagnostics/verify-live", headers=headers)
    assert resp.status_code == 429
    assert "already in progress" in resp.json()["detail"]
    ai_workspace._live_verify_in_flight = False


def test_17_live_verification_ttl_expiration(monkeypatch):
    """get_live_verification marks expired results as not verified after TTL."""
    from services.ai.llm_client import (
        clear_live_verification,
        get_live_verification,
        provider_status,
        record_live_verification,
    )
    from services.ai.provider_engine import UnifiedProviderConfig

    clear_live_verification()
    cfg = UnifiedProviderConfig(
        cloudflare_account_id="test-acct",
        cloudflare_api_token="test-token",
        cloudflare_model="@cf/ibm-granite/granite-4.0-h-micro",
    )
    record_live_verification({"verified": True, "provider": "cloudflare", "model": cfg.cloudflare_model}, config=cfg)

    # Fresh state
    fresh = get_live_verification(cfg)
    assert fresh is not None
    assert fresh["verified"] is True

    # Simulate TTL expiration (16 minutes later with 15 min TTL)
    from services.ai import llm_client
    with llm_client._live_verification_lock:
        llm_client._last_live_verification["monotonic_ts"] = time.monotonic() - 1000.0

    expired = get_live_verification(cfg)
    assert expired is not None
    assert expired["verified"] is False
    assert expired["status"] == "verification_expired"

    # provider_status reflects expired state
    st = provider_status(cfg)
    assert st["live_verified"] is False
    assert st["reason"] == "verification_expired"


def test_18_live_verification_invalidated_on_config_or_credential_change():
    """Live verification is invalidated immediately when credentials or model change."""
    from services.ai.llm_client import (
        clear_live_verification,
        get_live_verification,
        provider_status,
        record_live_verification,
    )
    from services.ai.provider_engine import UnifiedProviderConfig

    clear_live_verification()
    cfg1 = UnifiedProviderConfig(
        cloudflare_account_id="acct-initial",
        cloudflare_api_token="token-initial",
        cloudflare_model="@cf/ibm-granite/granite-4.0-h-micro",
    )
    record_live_verification({"verified": True, "provider": "cloudflare", "model": cfg1.cloudflare_model}, config=cfg1)

    # Verified under cfg1
    assert get_live_verification(cfg1)["verified"] is True

    # Token changed in cfg2 -> prior verification invalidated
    cfg2 = UnifiedProviderConfig(
        cloudflare_account_id="acct-initial",
        cloudflare_api_token="token-NEW",
        cloudflare_model="@cf/ibm-granite/granite-4.0-h-micro",
    )
    assert get_live_verification(cfg2) is None
    st2 = provider_status(cfg2)
    assert st2["live_verified"] is False
    assert st2["status_code"] == "credentials_present"

    # Model changed in cfg3 -> prior verification invalidated
    record_live_verification({"verified": True, "provider": "cloudflare", "model": cfg2.cloudflare_model}, config=cfg2)
    assert get_live_verification(cfg2)["verified"] is True
    cfg3 = UnifiedProviderConfig(
        cloudflare_account_id="acct-initial",
        cloudflare_api_token="token-NEW",
        cloudflare_model="@cf/zai-org/glm-4.7-flash",
    )
    assert get_live_verification(cfg3) is None
    st3 = provider_status(cfg3)
    assert st3["live_verified"] is False

