"""Provider-agnostic AI settings (services.ai.llm_client).

The module no longer contains any transport, self-hosted model, inference slot
or health probe. These tests pin the feature gates, limits and provider
resolution, and prove nothing in it can reach the network or select OpenAI.
"""

from __future__ import annotations

import pytest

from services.ai import llm_client
from services.ai.llm_client import (
    active_provider_name,
    configured_model_name,
    configured_providers,
    context_token_limit,
    estimate_tokens,
    exploration_timeout_seconds,
    get_recent_fallback_reason,
    local_exploration_enabled,
    local_intent_enabled,
    local_synthesis_enabled,
    provider_available,
    provider_status,
    record_fallback_reason,
    routing_timeout_seconds,
    strip_thinking,
    synthesis_timeout_seconds,
)

_ENV = (
    "PMS_AI_PRIMARY_PROVIDER", "PMS_AI_FALLBACK_PROVIDER", "PMS_AI_CLOUDFLARE_ENABLED", "PMS_AI_GEMINI_ENABLED",
    "PMS_AI_FALLBACK_ENABLED", "PMS_AI_OPENAI_ENABLED", "CLOUDFLARE_ACCOUNT_ID", "CF_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN", "CF_API_TOKEN", "CLOUDFLARE_API_KEY", "GEMINI_API_KEY", "Gemini_API_KEY",
    "GOOGLE_API_KEY", "OPENAI_API_KEY", "CLOUDFLARE_AI_MODEL", "CF_AI_MODEL", "PMS_CLOUDFLARE_MODEL",
    "PMS_GEMINI_MODEL", "PMS_AI_GEMINI_MODEL", "GEMINI_MODEL", "PMS_AI_INTENT_ENABLED", "PMS_AI_SYNTHESIS_ENABLED",
    "PMS_AI_EXPLORATION_ENABLED", "PMS_AI_LOCAL_ROUTER_ENABLED", "PMS_AI_LOCAL_SYNTHESIS_ENABLED",
    "PMS_AI_LOCAL_EXPLORATION_ENABLED", "PMS_AI_LOCAL_DATA_EXPLORATION_ENABLED", "APP_ENV",
    "PMS_AI_ROUTER_TIMEOUT_SECONDS", "PMS_AI_SYNTHESIS_TIMEOUT_SECONDS", "PMS_AI_EXPLORATION_TIMEOUT_SECONDS",
    "PMS_AI_PROVIDER_TIMEOUT_SECONDS", "PMS_AI_TIMEOUT_SECONDS", "PMS_AI_CONTEXT_TOKENS",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _cloudflare(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-test")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token-test-not-real")


def _gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key-test-not-real")


# -- decommissioning guarantees ---------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["chat_completion", "check_model_health", "LlmCompletion", "llm_turn", "_SLOT", "_SlotLease",
     "resolve_chat_url", "allowed_hosts", "max_calls_per_turn", "fit_messages", "DEFAULT_CHAT_URL",
     "DEFAULT_ALLOWED_HOSTS", "urllib"],
)
def test_legacy_self_hosted_surface_is_gone(name):
    assert not hasattr(llm_client, name)


def test_module_source_has_no_legacy_or_openai_references():
    source = open(llm_client.__file__, encoding="utf-8").read().casefold()
    for marker in ("qwen", "llama", "pms_ai_llm_", "pms-qwen-pilot", "api.openai.com", "urllib"):
        assert marker not in source


# -- feature gates -------------------------------------------------------------------


def test_everything_is_off_without_credentials():
    assert provider_available() is False
    assert local_intent_enabled() is False
    assert local_synthesis_enabled() is False
    assert local_exploration_enabled() is False
    assert active_provider_name() == "deterministic"


def test_cloudflare_credentials_enable_intent_and_synthesis(clean_env):
    _cloudflare(clean_env)
    assert configured_providers() == ["cloudflare"]
    assert local_intent_enabled() is True
    assert local_synthesis_enabled() is True
    assert local_exploration_enabled() is False  # exploration is always an explicit opt-in


def test_explicit_flags_override_the_credential_default(clean_env):
    _cloudflare(clean_env)
    clean_env.setenv("PMS_AI_INTENT_ENABLED", "false")
    clean_env.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "false")
    assert local_intent_enabled() is False
    assert local_synthesis_enabled() is False


def test_primary_is_cloudflare_and_fallback_is_gemini_in_call_order(clean_env):
    _cloudflare(clean_env)
    _gemini(clean_env)
    assert configured_providers() == ["cloudflare", "gemini"]
    assert active_provider_name() == "cloudflare"


def test_fallback_can_be_disabled(clean_env):
    _cloudflare(clean_env)
    _gemini(clean_env)
    clean_env.setenv("PMS_AI_FALLBACK_ENABLED", "false")
    assert configured_providers() == ["cloudflare"]


def test_gemini_only_when_cloudflare_is_unconfigured(clean_env):
    _gemini(clean_env)
    assert configured_providers() == ["gemini"]
    assert active_provider_name() == "gemini"


def test_openai_is_never_a_usable_provider(clean_env):
    clean_env.setenv("PMS_AI_PRIMARY_PROVIDER", "openai")
    clean_env.setenv("PMS_AI_FALLBACK_PROVIDER", "openai")
    clean_env.setenv("PMS_AI_OPENAI_ENABLED", "true")
    clean_env.setenv("OPENAI_API_KEY", "sk-test-not-real")
    assert configured_providers() == []
    assert provider_available() is False
    assert active_provider_name() == "deterministic"
    assert provider_status()["primary_provider"] == "cloudflare"


def test_exploration_is_opt_in_and_never_in_production(clean_env):
    assert local_exploration_enabled() is False
    clean_env.setenv("PMS_AI_EXPLORATION_ENABLED", "true")
    assert local_exploration_enabled() is True
    clean_env.setenv("PMS_AI_LOCAL_DATA_EXPLORATION_ENABLED", "false")
    assert local_exploration_enabled() is False
    clean_env.setenv("PMS_AI_LOCAL_DATA_EXPLORATION_ENABLED", "true")
    clean_env.setenv("APP_ENV", "production")
    assert local_exploration_enabled() is False


# -- model names and limits -------------------------------------------------------------


def test_configured_model_name_follows_the_primary_provider(clean_env):
    assert configured_model_name() == "@cf/ibm-granite/granite-4.0-h-micro"
    clean_env.setenv("CLOUDFLARE_AI_MODEL", "@cf/zai-org/glm-4.7-flash")
    assert configured_model_name() == "@cf/zai-org/glm-4.7-flash"
    clean_env.setenv("PMS_AI_PRIMARY_PROVIDER", "gemini")
    assert configured_model_name() == "gemini-3.5-flash-lite"


def test_timeouts_are_bounded(clean_env):
    assert routing_timeout_seconds() == 10.0
    assert synthesis_timeout_seconds() == 15.0
    assert exploration_timeout_seconds() == 15.0
    clean_env.setenv("PMS_AI_PROVIDER_TIMEOUT_SECONDS", "500")
    assert routing_timeout_seconds() == 30.0
    assert synthesis_timeout_seconds() == 60.0
    clean_env.setenv("PMS_AI_ROUTER_TIMEOUT_SECONDS", "not-a-number")
    assert routing_timeout_seconds() == 10.0
    clean_env.setenv("PMS_AI_SYNTHESIS_TIMEOUT_SECONDS", "0.01")
    assert synthesis_timeout_seconds() == 0.5


def test_context_limit_and_token_estimate(clean_env):
    assert context_token_limit() == 8192
    clean_env.setenv("PMS_AI_CONTEXT_TOKENS", "1")
    assert context_token_limit() == 512
    clean_env.setenv("PMS_AI_CONTEXT_TOKENS", "999999")
    assert context_token_limit() == 32768
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2


def test_strip_thinking_removes_reasoning_blocks():
    assert strip_thinking('<think>plan</think>{"a":1}') == '{"a":1}'
    assert strip_thinking('{"a":1}<think>unterminated') == '{"a":1}'


def test_fallback_reason_is_recorded_and_bounded():
    record_fallback_reason("provider_unavailable")
    assert get_recent_fallback_reason() == "provider_unavailable"
    record_fallback_reason(None)
    assert get_recent_fallback_reason() == "provider_unavailable"
    record_fallback_reason("x" * 500)
    assert len(get_recent_fallback_reason()) == 80


def test_provider_status_never_contains_secrets(clean_env):
    _cloudflare(clean_env)
    _gemini(clean_env)
    status = str(provider_status()).casefold()
    for secret in ("token-test-not-real", "key-test-not-real", "acct-test"):
        assert secret not in status
