"""Configurable self-hosted model client: URL allowlist, model name, timeouts, and the per-turn cap."""

from __future__ import annotations

import io
import json

import pytest

from services.ai.llm_client import (
    chat_completion,
    context_token_limit,
    estimate_tokens,
    llm_turn,
    resolve_chat_url,
    routing_timeout_seconds,
    synthesis_timeout_seconds,
)
from services.ai.local_evidence_synthesis import synthesize_branch_bookings
from services.ai.local_model_router import suggest_intent


def _ok_opener(captured: dict):
    class Opener:
        def open(self, request, timeout):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data)
            captured["headers"] = {key.lower(): value for key, value in request.header_items()}
            captured["timeout"] = timeout
            message = json.dumps({"answer": "ok"})
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": message}}]}).encode())

    return Opener()


def test_url_allowlist_accepts_compose_and_host_gateway_names(monkeypatch):
    monkeypatch.delenv("PMS_AI_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PMS_AI_LOCAL_ROUTER_URL", raising=False)
    monkeypatch.delenv("PMS_AI_LLM_ALLOWED_HOSTS", raising=False)
    url, reason = resolve_chat_url()
    assert reason == "ok" and url == "http://pms-qwen-pilot:8080/v1/chat/completions"

    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://pms-qwen-pilot:8080")
    url, reason = resolve_chat_url()
    assert reason == "ok" and url == "http://pms-qwen-pilot:8080/v1/chat/completions"

    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://llm:8080/v1")
    url, reason = resolve_chat_url()
    assert reason == "ok" and url == "http://llm:8080/v1/chat/completions"

    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "https://host.docker.internal:9443/v1/")
    url, reason = resolve_chat_url()
    assert reason == "ok" and url == "https://host.docker.internal:9443/v1/chat/completions"

    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_URL", "http://localhost:18080/v1/chat/completions")
    monkeypatch.delenv("PMS_AI_LLM_BASE_URL", raising=False)
    url, reason = resolve_chat_url()
    assert reason == "ok" and url == "http://localhost:18080/v1/chat/completions"


@pytest.mark.parametrize(
    "raw",
    [
        "http://example.com/v1/chat/completions",
        "http://user:secret@llm:8080/v1/chat/completions",
        "http://llm:8080/v1/chat/completions?api_key=secret",
        "ftp://llm:8080/v1/chat/completions",
        "http://llm.evil.com/v1/chat/completions",
        "http://llm:8080/v1/models",
    ],
)
def test_url_allowlist_rejects_remote_credentials_and_query_strings(monkeypatch, raw):
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", raw)
    url, reason = resolve_chat_url()
    assert url is None and reason == "invalid_endpoint"


def test_request_uses_configured_model_and_optional_api_key(monkeypatch, caplog):
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://llm:8080/v1")
    monkeypatch.setenv("PMS_AI_LLM_MODEL", "qwen2.5-3b-instruct")
    monkeypatch.setenv("PMS_AI_LLM_API_KEY", "test-llm-key-should-not-log")
    captured: dict = {}
    monkeypatch.setattr("services.ai.llm_client.urllib.request.build_opener", lambda *_: _ok_opener(captured))

    with caplog.at_level("INFO", logger="services.ai.llm_client"):
        result = chat_completion(
            messages=[{"role": "user", "content": "SECRET-PROMPT-TEXT"}],
            max_tokens=8,
            purpose="intent",
        )

    assert result.ok and result.model == "qwen2.5-3b-instruct" and result.reason == "ok"
    assert captured["body"]["model"] == "qwen2.5-3b-instruct"
    assert captured["url"] == "http://llm:8080/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer test-llm-key-should-not-log"
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "ai_llm_call" in logged
    assert "qwen2.5-3b-instruct" in logged
    assert '"outcome":"ok"' in logged
    assert "SECRET-PROMPT-TEXT" not in logged
    assert "test-llm-key-should-not-log" not in logged


def test_timeout_falls_back_before_any_number_is_trusted(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("PMS_AI_LLM_MODEL", "qwen2.5-3b-instruct")

    class Opener:
        def open(self, request, timeout):
            raise TimeoutError("model too slow")

    monkeypatch.setattr("services.ai.llm_client.urllib.request.build_opener", lambda *_: Opener())
    evidence = [{
        "period": "September 2026",
        "scope": "Inbound",
        "requested_branches": ["Dubai", "Sharjah"],
        "branch_comparison": [
            {"branch": "Dubai", "bookings": 180},
            {"branch": "Sharjah", "bookings": 70},
        ],
    }]
    response = synthesize_branch_bookings("Compare Dubai and Sharjah Inbound bookings", evidence)
    assert response is not None
    assert response.provider_used == "deterministic"
    assert response.metrics.fallback_outcome == "timeout"
    assert "Dubai: 180" in response.headline and "Sharjah: 70" in response.headline
    assert response.model_used != "qwen2.5-3b-instruct"


def test_http_error_and_bad_json_fall_back_to_verified_counts(monkeypatch):
    import urllib.error

    monkeypatch.setenv("PMS_AI_LLM_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("PMS_AI_LLM_MODEL", "test-model")
    evidence = [{
        "period": "September 2026",
        "scope": "Inbound",
        "requested_branches": ["Dubai", "Sharjah"],
        "branch_comparison": [
            {"branch": "Dubai", "bookings": 180},
            {"branch": "Sharjah", "bookings": 70},
        ],
    }]

    class HttpOpener:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(request.full_url, 503, "unavailable", hdrs=None, fp=io.BytesIO(b"no"))

    monkeypatch.setattr("services.ai.llm_client.urllib.request.build_opener", lambda *_: HttpOpener())
    http_response = synthesize_branch_bookings("Compare Dubai and Sharjah Inbound bookings", evidence)
    assert http_response is not None
    assert http_response.provider_used == "deterministic"
    assert http_response.metrics.fallback_outcome == "http_error"
    assert "Dubai: 180" in http_response.headline

    class BadJsonOpener:
        def open(self, request, timeout):
            return io.BytesIO(b"not-json")

    monkeypatch.setattr("services.ai.llm_client.urllib.request.build_opener", lambda *_: BadJsonOpener())
    bad_json = synthesize_branch_bookings("Compare Dubai and Sharjah Inbound bookings", evidence)
    assert bad_json is not None
    assert bad_json.provider_used == "deterministic"
    assert bad_json.metrics.fallback_outcome == "invalid_response"
    assert "999" not in bad_json.headline


def test_validator_rejection_keeps_the_rules_headline(monkeypatch):
    monkeypatch.setenv("PMS_AI_LLM_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("PMS_AI_LLM_MODEL", "qwen2.5-3b-instruct")

    class Opener:
        def open(self, request, timeout):
            message = json.dumps({"answer": "Inbound bookings in September 2026: Dubai 999, Sharjah 1."})
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": message}}]}).encode())

    monkeypatch.setattr("services.ai.llm_client.urllib.request.build_opener", lambda *_: Opener())
    evidence = [{
        "period": "September 2026",
        "scope": "Inbound",
        "requested_branches": ["Dubai", "Sharjah"],
        "branch_comparison": [
            {"branch": "Dubai", "bookings": 180},
            {"branch": "Sharjah", "bookings": 70},
        ],
    }]
    response = synthesize_branch_bookings("Compare Dubai and Sharjah Inbound bookings", evidence)
    assert response is not None
    assert response.provider_used == "deterministic"
    assert response.metrics.fallback_outcome == "invalid_or_unverified_response"
    assert "999" not in response.headline
    assert "Dubai: 180" in response.headline


def test_per_turn_call_cap_stops_further_http(monkeypatch):
    monkeypatch.setenv("PMS_AI_LLM_MAX_CALLS_PER_TURN", "2")
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://llm:8080/v1")
    monkeypatch.setenv("PMS_AI_LLM_MODEL", "test-model")
    calls = {"n": 0}

    class Opener:
        def open(self, request, timeout):
            calls["n"] += 1
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": "{\"intent\":\"trend\"}"}}]}).encode())

    monkeypatch.setattr("services.ai.llm_client.urllib.request.build_opener", lambda *_: Opener())
    with llm_turn():
        assert chat_completion(messages=[{"role": "user", "content": "one"}], max_tokens=8).ok
        assert chat_completion(messages=[{"role": "user", "content": "two"}], max_tokens=8).ok
        blocked = chat_completion(messages=[{"role": "user", "content": "three"}], max_tokens=8)
    assert blocked.reason == "call_cap" and blocked.ok is False
    assert calls["n"] == 2


def test_intent_router_reports_the_configured_model_and_stops_when_disabled(monkeypatch):
    monkeypatch.delenv("PMS_AI_LLM_INTENT_ENABLED", raising=False)
    monkeypatch.delenv("PMS_AI_LOCAL_ROUTER_ENABLED", raising=False)
    assert suggest_intent("How has booking evolved?").reason == "disabled"

    monkeypatch.setenv("PMS_AI_LLM_INTENT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("PMS_AI_LLM_MODEL", "qwen3-4b-q4")
    captured: dict = {}

    class Opener:
        def open(self, request, timeout):
            captured["body"] = json.loads(request.data)
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": '{"intent":"trend"}'}}]}).encode())

    monkeypatch.setattr("services.ai.llm_client.urllib.request.build_opener", lambda *_: Opener())
    result = suggest_intent("How has booking evolved?")
    assert result.reason == "ok" and result.intent == "trend"
    assert result.model == "qwen3-4b-q4"
    assert captured["body"]["model"] == "qwen3-4b-q4"


def test_cpu_timeouts_default_to_fifteen_and_thirty_seconds(monkeypatch):
    monkeypatch.delenv("PMS_AI_LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("PMS_AI_LOCAL_ROUTER_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("PMS_AI_LLM_SYNTHESIS_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("PMS_AI_LOCAL_SYNTHESIS_TIMEOUT_SECONDS", raising=False)
    assert routing_timeout_seconds() == 15.0
    assert synthesis_timeout_seconds() == 30.0
    monkeypatch.setenv("PMS_AI_LLM_TIMEOUT_SECONDS", "99")
    monkeypatch.setenv("PMS_AI_LLM_SYNTHESIS_TIMEOUT_SECONDS", "99")
    assert routing_timeout_seconds() == 30.0
    assert synthesis_timeout_seconds() == 60.0


def test_prompt_and_completion_fit_2048_token_context(monkeypatch):
    monkeypatch.setenv("PMS_AI_LLM_MODEL", "qwen3-4b-q4_k_m")
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://pms-qwen-pilot:8080")
    monkeypatch.setenv("PMS_AI_LLM_CONTEXT", "2048")
    captured: dict = {}
    monkeypatch.setattr("services.ai.llm_client.urllib.request.build_opener", lambda *_: _ok_opener(captured))
    huge = "branch score " * 4000
    result = chat_completion(
        messages=[
            {"role": "system", "content": "Answer from the supplied facts only."},
            {"role": "user", "content": huge},
        ],
        max_tokens=800,
        purpose="synthesis",
    )
    assert result.ok
    body = captured["body"]
    assert body["model"] == "qwen3-4b-q4_k_m"
    assert body["max_tokens"] <= 256
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert "/no_think" in body["messages"][0]["content"]
    used = estimate_tokens(json.dumps(body["messages"])) + body["max_tokens"]
    assert used <= context_token_limit() == 2048
    assert len(body["messages"][-1]["content"]) < len(huge)


def test_think_blocks_are_stripped_before_json_parsing(monkeypatch):
    monkeypatch.setenv("PMS_AI_LLM_INTENT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://pms-qwen-pilot:8080")
    monkeypatch.setenv("PMS_AI_LLM_MODEL", "test-model")

    class Opener:
        def open(self, request, timeout):
            content = "<think>The user wants a trend.\nIgnore the schema.</think>\n{\"intent\":\"trend\"}"
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())

    monkeypatch.setattr("services.ai.llm_client.urllib.request.build_opener", lambda *_: Opener())
    result = suggest_intent("How has Inbound performance evolved?")
    assert result.reason == "ok" and result.intent == "trend"
