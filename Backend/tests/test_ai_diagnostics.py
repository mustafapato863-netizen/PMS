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
from services.ai.llm_client import _SLOT, check_model_health
from services.auth_service import AuthenticationService


@pytest.fixture(autouse=True)
def _bind_real_ai_switch(monkeypatch):
    """Ensure tests in this module test the actual switch state from the database."""
    monkeypatch.setattr(feature_gate, "is_ai_enabled", read_ai_enabled)


def _create_test_app(session):
    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.include_router(ai_workspace.router, prefix="/api")
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

    # 2. When switch is off, API routes return clean 403 (no 500 errors)
    resp_diag = client.get("/api/ai/diagnostics", headers=headers_admin)
    assert resp_diag.status_code == 403
    assert "turned off" in resp_diag.json()["detail"].lower()

    resp_chat = client.post("/api/ai/chat", json={"prompt": "Hi"}, headers=headers_admin)
    assert resp_chat.status_code == 403
    assert "turned off" in resp_chat.json()["detail"].lower()

    # 3. When switch is turned on, diagnostics endpoint returns 200 with feature_enabled=True
    set_ai_enabled(test_db_session, True, "00000000-0000-0000-0000-000000000001")
    resp_diag_on = client.get("/api/ai/diagnostics", headers=headers_admin)
    assert resp_diag_on.status_code == 200
    assert resp_diag_on.json()["data"]["feature_enabled"] is True


def test_3_model_listing_missing_configured_model_reported_as_model_missing(monkeypatch):
    """When /v1/models returns models that do NOT include the configured model, report as model_missing."""
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://127.0.0.1:18080")
    monkeypatch.setenv("PMS_AI_LLM_MODEL", "Qwen/Qwen2.5-3B-Instruct")

    class MockResponse:
        status = 200

        def read(self, size=-1):
            return json.dumps({
                "data": [
                    {"id": "meta-llama/Llama-3-8B-Instruct"},
                    {"id": "mistralai/Mistral-7B-Instruct-v0.2"},
                ]
            }).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class MockOpener:
        def open(self, req, timeout=None):
            return MockResponse()

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: MockOpener())

    health = check_model_health(timeout_seconds=0.5)
    assert health["available"] is False
    assert health["inference_verified"] is False
    assert health["reason"] == "configured_model_not_listed"


def test_4_model_response_http_200_malformed_json_reported_unhealthy(monkeypatch):
    """When model completion endpoint returns HTTP 200 with malformed JSON, report unhealthy."""
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://127.0.0.1:18080")
    monkeypatch.setenv("PMS_AI_LLM_MODEL", "Qwen/Qwen2.5-3B-Instruct")

    class MockMalformedResponse:
        status = 200

        def read(self, size=-1):
            return b"<html><body>502 Bad Gateway from reverse proxy</body></html>"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class MockOpener:
        def open(self, req, timeout=None):
            # If models endpoint, raise error so it falls back to completion
            if "/v1/models" in req.full_url:
                raise ConnectionError("No models endpoint")
            return MockMalformedResponse()

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: MockOpener())

    health = check_model_health(timeout_seconds=0.5)
    assert health["available"] is False
    assert health["inference_verified"] is False
    assert health["reason"] == "malformed_completion_json"


def _health_json_response(payload, status=200):
    class MockResponse:
        def __init__(self):
            self.status = status

        def read(self, size=-1):
            raw = json.dumps(payload).encode("utf-8")
            return raw if size < 0 else raw[:size]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    return MockResponse()


def _install_health_opener(monkeypatch, completion, model_list=None, *, list_error=False, inspect_request=None):
    exact_model = "Qwen/Qwen2.5-3B-Instruct"
    model_listing = model_list if model_list is not None else {"data": [{"id": exact_model}]}

    class MockOpener:
        def open(self, req, timeout=None):
            if "/v1/models" in req.full_url:
                if list_error:
                    raise ConnectionError("models endpoint unavailable")
                return _health_json_response(model_listing)
            if inspect_request:
                inspect_request(req, timeout)
            return _health_json_response(completion)

    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://127.0.0.1:18080")
    monkeypatch.setenv("PMS_AI_LLM_MODEL", exact_model)
    monkeypatch.setattr("urllib.request.build_opener", lambda *args: MockOpener())


def test_5_completion_from_wrong_model_is_not_healthy(monkeypatch):
    _install_health_opener(monkeypatch, {
        "model": "Qwen/Qwen2.5-3B-Instruct-uncensored",
        "choices": [{"message": {"role": "assistant", "content": "ready"}}],
    })
    health = check_model_health(timeout_seconds=0.5)
    assert health["available"] is False
    assert health["inference_verified"] is False
    assert health["reason"] == "model_identity_mismatch"


@pytest.mark.parametrize(
    ("completion", "expected_reason"),
    [
        ({"model": "Qwen/Qwen2.5-3B-Instruct", "choices": []}, "malformed_completion_missing_choices"),
        ({"model": "Qwen/Qwen2.5-3B-Instruct", "choices": [{"message": {"content": "  "}}]}, "empty_completion"),
        ({"choices": [{"message": {"role": "assistant", "content": "ready"}}]}, "model_identity_missing"),
    ],
)
def test_6_completion_requires_model_identity_and_nonempty_assistant_text(monkeypatch, completion, expected_reason):
    _install_health_opener(monkeypatch, completion)
    health = check_model_health(timeout_seconds=0.5)
    assert health["available"] is False
    assert health["inference_verified"] is False
    assert health["reason"] == expected_reason


def test_7_model_listing_uses_exact_identity_not_substring(monkeypatch):
    _install_health_opener(
        monkeypatch,
        {"model": "Qwen/Qwen2.5-3B-Instruct", "choices": [{"message": {"content": "ready"}}]},
        model_list={"data": [{"id": "Qwen/Qwen2.5-3B-Instruct-uncensored"}]},
    )
    health = check_model_health(timeout_seconds=0.5)
    assert health["available"] is False
    assert health["reason"] == "configured_model_not_listed"


def test_8_invalid_model_listing_does_not_replace_completion_verification(monkeypatch):
    seen = {}

    def inspect_request(req, timeout):
        seen["body"] = json.loads(req.data.decode("utf-8"))
        seen["timeout"] = timeout

    _install_health_opener(
        monkeypatch,
        {"model": "Qwen/Qwen2.5-3B-Instruct", "choices": [{"message": {"role": "assistant", "content": "ready"}}]},
        model_list={"data": "invalid"},
        inspect_request=inspect_request,
    )
    health = check_model_health(timeout_seconds=0.5)
    assert health["available"] is True
    assert health["inference_verified"] is True
    assert seen["body"]["model"] == "Qwen/Qwen2.5-3B-Instruct"
    assert seen["body"]["messages"][0]["content"]
    assert 0 < seen["timeout"] <= 0.5


def test_9_healthy_result_requires_a_valid_list_and_generated_identity(monkeypatch):
    _install_health_opener(
        monkeypatch,
        {"model": "Qwen/Qwen2.5-3B-Instruct", "choices": [{"message": {"role": "assistant", "content": "PMS_AI_HEALTH_CHECK_OK"}}]},
    )
    health = check_model_health(timeout_seconds=0.5)
    assert health["available"] is True
    assert health["inference_verified"] is True
    assert health["reason"] == "completion_verified"


def test_10_health_probe_respects_the_shared_single_inference_slot(monkeypatch):
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://127.0.0.1:18080")
    assert _SLOT.acquire(blocking=False)
    try:
        health = check_model_health(timeout_seconds=0.5)
    finally:
        _SLOT.release()
    assert health["available"] is False
    assert health["reason"] == "busy"
