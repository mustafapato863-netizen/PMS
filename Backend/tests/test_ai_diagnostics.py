from __future__ import annotations

import json
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
