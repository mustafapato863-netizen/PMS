"""Tests for Admin AI provider configuration, encrypted keys, and key failover."""

from __future__ import annotations

import io
import json
import urllib.error
import uuid
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers import ai_provider_config
from config.database import Base, get_db
from models.models import AiProviderConfig, AuditLog
from services.ai import nemotron_analyzer, provider_config_store, provider_engine
from services.ai.provider_probe import probe_provider
from services.ai.secret_crypto import decrypt_secret, encrypt_secret, mask_secret

TEST_KEY_MATERIAL = "unit-test-provider-secret-material"


@pytest.fixture(autouse=True)
def _stable_encryption_key(monkeypatch):
    monkeypatch.setenv("PMS_SECRETS_ENCRYPTION_KEY", TEST_KEY_MATERIAL)
    provider_config_store.invalidate_provider_config()
    yield
    provider_config_store.invalidate_provider_config()


def _make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _build_app(db, monkeypatch):
    app = FastAPI()

    @app.middleware("http")
    async def inject_identity(request: Request, call_next):
        role = request.headers.get("x-test-role")
        user_id = request.headers.get("x-test-user-id", "")
        if role:
            request.state.user = {"role": role, "user_id": user_id}
        return await call_next(request)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.include_router(ai_provider_config.router, prefix="/api")
    return TestClient(app)


ADMIN_ID = str(uuid.uuid4())


class _FakeHttpResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200):
        self._body = json.dumps(payload).encode("utf-8")
        self._position = 0
        self.status = status_code

    def read(self, size: int = -1) -> bytes:
        if self._position >= len(self._body):
            return b""
        if size is None or size < 0:
            chunk = self._body[self._position :]
        else:
            chunk = self._body[self._position : self._position + size]
        self._position += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _RetryOnceHttpClient:
    """Fails the first request with a rejected-key status, then succeeds."""

    def __init__(self, payload: dict[str, Any], status_code: int = 429):
        self.payload = payload
        self.status_code = status_code
        self.calls: list[dict[str, str]] = []

    def __call__(self, request, timeout=None):
        self.calls.append({key.lower(): value for key, value in request.header_items()})
        if len(self.calls) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                self.status_code,
                "key rejected",
                None,
                io.BytesIO(b'{"error":"key rejected"}'),
            )
        return _FakeHttpResponse(self.payload)


def _cloudflare_payload() -> dict[str, Any]:
    return {
        "success": True,
        "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


# ---------------------------------------------------------------------------
# Encryption & masking
# ---------------------------------------------------------------------------


def test_fernet_roundtrip_and_masking_never_returns_plaintext():
    encrypted = encrypt_secret("nvapi-super-secret-value-7a2f")
    assert encrypted
    assert "super-secret" not in encrypted
    assert decrypt_secret(encrypted) == "nvapi-super-secret-value-7a2f"

    assert mask_secret("nvapi-super-secret-value-7a2f") == "nvapi-••••7a2f"
    assert mask_secret("AIzaABCDEFGHIJKLMNOP9x1q") == "AIza••••9x1q"
    assert mask_secret("short") == "••••"
    assert mask_secret(None) == ""
    assert encrypt_secret("   ") is None


def test_mask_does_not_leak_normal_keys():
    secret = "abcdefghijklmnopqrstuvwxyz"
    masked = mask_secret(secret)
    assert secret not in masked
    assert masked.startswith("abcd")
    assert masked.endswith("wxyz")


# ---------------------------------------------------------------------------
# Store precedence and slot resolution
# ---------------------------------------------------------------------------


def test_store_falls_back_to_environment(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "env-primary-token")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN_ALTER", "env-standby-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "env-account")
    monkeypatch.setenv("CLOUDFLARE_AI_MODEL", "env-model")

    config = provider_config_store.resolve_provider_config("cloudflare", use_cache=False)
    assert config.active_key_slot == "primary"
    assert config.active_api_key == "env-primary-token"
    assert config.standby_api_key == "env-standby-token"
    assert config.account_id == "env-account"
    assert config.primary_model == "env-model"
    assert config.primary_key_source == "env"


def test_store_database_overrides_environment(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "env-primary-token")
    monkeypatch.setenv("CLOUDFLARE_AI_MODEL", "env-model")

    db = _make_session()
    db.add(
        AiProviderConfig(
            provider="cloudflare",
            primary_model="db-model",
            primary_api_key_encrypted=encrypt_secret("db-primary-token"),
            alternate_api_key_encrypted=encrypt_secret("db-standby-token"),
            account_id_encrypted=encrypt_secret("db-account"),
            active_key_slot="alternate",
            auto_failover_key=True,
        )
    )
    db.commit()

    config = provider_config_store.resolve_provider_config("cloudflare", db=db, use_cache=False)
    assert config.primary_model == "db-model"
    assert config.primary_model_source == "db"
    assert config.active_key_slot == "alternate"
    assert config.active_api_key == "db-standby-token"
    assert config.standby_api_key == "db-primary-token"
    assert config.active_account_id == "db-account"


def test_store_ignores_unreadable_ciphertext_and_uses_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-gemini-key")
    db = _make_session()
    db.add(AiProviderConfig(provider="gemini", primary_api_key_encrypted="not-a-token"))
    db.commit()

    config = provider_config_store.resolve_provider_config("gemini", db=db, use_cache=False)
    assert config.primary_api_key == "env-gemini-key"
    assert config.primary_key_source == "env"


# ---------------------------------------------------------------------------
# Auto-failover
# ---------------------------------------------------------------------------


def test_key_switching_error_classification():
    assert provider_engine._is_key_switching_error(
        provider_engine.ProviderClientError("auth", http_code=401)
    )
    assert provider_engine._is_key_switching_error(
        provider_engine.ProviderClientError("forbidden", http_code=403)
    )
    assert provider_engine._is_key_switching_error(
        provider_engine.ProviderRateLimitError("quota", http_code=429)
    )
    assert not provider_engine._is_key_switching_error(
        provider_engine.ProviderClientError("bad request", http_code=400)
    )
    assert not provider_engine._is_key_switching_error(
        provider_engine.ProviderTransientError("down", http_code=503)
    )


@pytest.mark.parametrize("status_code", [401, 403, 429])
def test_cloudflare_retries_once_with_standby_key(status_code: int):
    client = _RetryOnceHttpClient(_cloudflare_payload(), status_code=status_code)
    config = provider_engine.UnifiedProviderConfig(
        cloudflare_account_id="account-1",
        cloudflare_api_token="primary-key",
        cloudflare_standby_api_token="standby-key",
        cloudflare_auto_failover_key=True,
        cloudflare_model="model-1",
    )
    request = provider_engine.ProviderRequest(
        messages=[provider_engine.ProviderMessage(role="user", content="hello")],
        max_tokens=8,
    )

    text, usage = provider_engine.CloudflareAIProviderAdapter(http_client=client).execute(
        request, config, timeout=5.0
    )

    assert text == "OK"
    assert usage.total_tokens == 2
    assert len(client.calls) == 2
    assert client.calls[0]["authorization"] == "Bearer primary-key"
    assert client.calls[1]["authorization"] == "Bearer standby-key"


def test_cloudflare_does_not_retry_when_auto_failover_is_off():
    client = _RetryOnceHttpClient(_cloudflare_payload())
    config = provider_engine.UnifiedProviderConfig(
        cloudflare_account_id="account-1",
        cloudflare_api_token="primary-key",
        cloudflare_standby_api_token="standby-key",
        cloudflare_auto_failover_key=False,
        cloudflare_model="model-1",
    )
    request = provider_engine.ProviderRequest(
        messages=[provider_engine.ProviderMessage(role="user", content="hello")],
        max_tokens=8,
    )

    with pytest.raises(provider_engine.ProviderRateLimitError):
        provider_engine.CloudflareAIProviderAdapter(http_client=client).execute(
            request, config, timeout=5.0
        )
    assert len(client.calls) == 1


def test_gemini_retries_once_with_standby_key():
    client = _RetryOnceHttpClient(
        {
            "candidates": [
                {"content": {"parts": [{"text": "OK"}]}, "finishReason": "STOP"}
            ],
            "usageMetadata": {
                "promptTokenCount": 1,
                "candidatesTokenCount": 1,
                "totalTokenCount": 2,
            },
        }
    )
    config = provider_engine.UnifiedProviderConfig(
        gemini_api_key="primary-key",
        gemini_standby_api_key="standby-key",
        gemini_auto_failover_key=True,
    )
    request = provider_engine.ProviderRequest(
        messages=[provider_engine.ProviderMessage(role="user", content="hello")],
        max_tokens=8,
    )

    text, usage = provider_engine.GeminiProviderAdapter(http_client=client).execute(
        request, config, timeout=5.0
    )

    assert text == "OK"
    assert usage.total_tokens == 2
    assert len(client.calls) == 2
    assert client.calls[0]["x-goog-api-key"] == "primary-key"
    assert client.calls[1]["x-goog-api-key"] == "standby-key"


def test_nvidia_analyzer_retries_once_with_standby_key(monkeypatch):
    monkeypatch.setattr(nemotron_analyzer, "_nvidia_runtime_config", lambda: None)
    monkeypatch.setenv("NVIDIA_API_KEY", "primary-key")
    monkeypatch.setenv("NVIDIA_API_KEY_ALTER", "standby-key")
    monkeypatch.delenv("PMS_AI_AUTO_FAILOVER_KEY", raising=False)

    authorizations: list[str] = []

    def fake_urlopen(request, timeout=None):
        authorizations.append(dict(request.header_items())["Authorization"])
        if len(authorizations) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "unauthorized",
                None,
                io.BytesIO(b'{"error":"invalid key"}'),
            )
        return _FakeHttpResponse(
            {"choices": [{"message": {"content": '{"summary": "ok"}'}}]}
        )

    monkeypatch.setattr(nemotron_analyzer.urllib.request, "urlopen", fake_urlopen)

    assert nemotron_analyzer._post_nvidia_chat_completions([{"role": "user", "content": "hi"}], max_tokens=10) == {
        "summary": "ok"
    }
    assert authorizations == ["Bearer primary-key", "Bearer standby-key"]


def test_nvidia_analyzer_does_not_retry_when_auto_failover_is_off(monkeypatch):
    monkeypatch.setattr(nemotron_analyzer, "_nvidia_runtime_config", lambda: None)
    monkeypatch.setenv("NVIDIA_API_KEY", "primary-key")
    monkeypatch.setenv("NVIDIA_API_KEY_ALTER", "standby-key")
    monkeypatch.setenv("PMS_AI_AUTO_FAILOVER_KEY", "false")

    calls: list[int] = []

    def fake_urlopen(request, timeout=None):
        calls.append(1)
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "forbidden",
            None,
            io.BytesIO(b'{"error":"invalid key"}'),
        )

    monkeypatch.setattr(nemotron_analyzer.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="HTTP 403"):
        nemotron_analyzer._post_nvidia_chat_completions([{"role": "user", "content": "hi"}], max_tokens=10)
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------


def test_admin_endpoints_reject_non_admin(monkeypatch):
    db = _make_session()
    client = _build_app(db, monkeypatch)

    assert client.get("/api/ai/admin/providers", headers={"x-test-role": "Manager"}).status_code == 403
    assert (
        client.put(
            "/api/ai/admin/providers/cloudflare",
            headers={"x-test-role": "Manager"},
            json={"primary_model": "x"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/ai/admin/providers/cloudflare/switch-key",
            headers={"x-test-role": "Manager"},
            json={"slot": "alternate"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/ai/admin/providers/cloudflare/test",
            headers={"x-test-role": "Manager"},
            json={"slot": "primary"},
        ).status_code
        == 403
    )


def test_admin_can_list_masked_provider_config(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "env-cloudflare-token-value")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "env-account-id")
    db = _make_session()
    client = _build_app(db, monkeypatch)

    response = client.get(
        "/api/ai/admin/providers",
        headers={"x-test-role": "Admin", "x-test-user-id": ADMIN_ID},
    )
    assert response.status_code == 200
    payload = response.json()
    providers = {item["provider"]: item for item in payload["providers"]}
    assert set(providers) == {"cloudflare", "gemini", "nvidia"}
    assert providers["cloudflare"]["primary_key"]["configured"] is True
    assert providers["cloudflare"]["primary_key"]["source"] == "env"
    assert "env-cloudflare-token-value" not in response.text
    assert "env-account-id" not in response.text


def test_admin_update_encrypts_key_and_audits_without_secret(monkeypatch):
    db = _make_session()
    client = _build_app(db, monkeypatch)

    response = client.put(
        "/api/ai/admin/providers/cloudflare",
        headers={"x-test-role": "Admin", "x-test-user-id": ADMIN_ID},
        json={
            "primary_model": "custom-model",
            "primary_api_key": "super-secret-key-value",
            "account_id": "account-xyz",
            "auto_failover_key": False,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["provider"]["primary_model"] == "custom-model"
    assert payload["provider"]["primary_key"]["configured"] is True
    assert payload["provider"]["primary_key"]["source"] == "db"
    assert payload["provider"]["auto_failover_key"] is False
    assert "super-secret-key-value" not in response.text

    row = db.query(AiProviderConfig).filter(AiProviderConfig.provider == "cloudflare").one()
    assert row.primary_api_key_encrypted
    assert "super-secret-key-value" not in row.primary_api_key_encrypted
    assert decrypt_secret(row.primary_api_key_encrypted) == "super-secret-key-value"

    audit = db.query(AuditLog).filter(AuditLog.operation == "AI_PROVIDER_CONFIG_UPDATED").one()
    assert audit.new_values["provider"] == "cloudflare"
    assert "super-secret-key-value" not in json.dumps(audit.new_values)


def test_admin_switch_key_requires_target_credentials(monkeypatch):
    db = _make_session()
    client = _build_app(db, monkeypatch)

    response = client.post(
        "/api/ai/admin/providers/gemini/switch-key",
        headers={"x-test-role": "Admin", "x-test-user-id": ADMIN_ID},
        json={"slot": "alternate"},
    )
    assert response.status_code == 400

    db.add(
        AiProviderConfig(
            provider="gemini",
            primary_api_key_encrypted=encrypt_secret("primary-key"),
            alternate_api_key_encrypted=encrypt_secret("alternate-key"),
        )
    )
    db.commit()
    provider_config_store.invalidate_provider_config("gemini")

    response = client.post(
        "/api/ai/admin/providers/gemini/switch-key",
        headers={"x-test-role": "Admin", "x-test-user-id": ADMIN_ID},
        json={"slot": "alternate"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["provider"]["active_key_slot"] == "alternate"

    audit = (
        db.query(AuditLog)
        .filter(AuditLog.operation == "AI_PROVIDER_KEY_SWITCHED")
        .one()
    )
    assert audit.new_values["slot"] == "alternate"


def test_admin_test_endpoint_uses_resolved_slot(monkeypatch):
    db = _make_session()
    db.add(
        AiProviderConfig(
            provider="nvidia",
            primary_model="nvidia-model",
            primary_api_key_encrypted=encrypt_secret("primary-key"),
            alternate_api_key_encrypted=encrypt_secret("alternate-key"),
            active_key_slot="alternate",
        )
    )
    db.commit()
    provider_config_store.invalidate_provider_config("nvidia")
    client = _build_app(db, monkeypatch)

    captured: dict[str, Any] = {}

    def fake_probe(provider, *, api_key, model, account_id="", timeout=12.0):
        captured.update(
            {"provider": provider, "api_key": api_key, "model": model, "account_id": account_id}
        )
        return {
            "ok": True,
            "latency_ms": 12.5,
            "status_code": 200,
            "message": "verified",
            "tested_model": model,
        }

    monkeypatch.setattr(ai_provider_config, "probe_provider", fake_probe)

    response = client.post(
        "/api/ai/admin/providers/nvidia/test",
        headers={"x-test-role": "Admin", "x-test-user-id": ADMIN_ID},
        json={"slot": "alternate"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["ok"] is True
    assert data["tested_slot"] == "alternate"
    assert data["latency_ms"] == 12.5
    assert captured["api_key"] == "alternate-key"
    assert captured["model"] == "nvidia-model"


def test_admin_clear_key_falls_back_to_environment(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "env-fallback-token")
    db = _make_session()
    db.add(
        AiProviderConfig(
            provider="cloudflare",
            primary_api_key_encrypted=encrypt_secret("db-token"),
        )
    )
    db.commit()
    provider_config_store.invalidate_provider_config("cloudflare")
    client = _build_app(db, monkeypatch)

    response = client.put(
        "/api/ai/admin/providers/cloudflare",
        headers={"x-test-role": "Admin", "x-test-user-id": ADMIN_ID},
        json={"clear_primary_api_key": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["provider"]["primary_key"]["source"] == "env"
    assert response.json()["provider"]["primary_key"]["masked_preview"] == "env-••••oken"


def test_probe_provider_rejects_unknown_provider():
    with pytest.raises(ValueError):
        probe_provider("unknown", api_key="x", model="m")
