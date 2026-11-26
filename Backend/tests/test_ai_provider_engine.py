"""Tests for Unified PMS AI Provider Engine (Phase 1).

Covers:
- Primary provider success (fallback never called).
- Nvidia transient failure retry and eventual success.
- Nvidia rate limit (HTTP 429) immediate fallback to OpenAI without retry.
- Nvidia timeout fallback to OpenAI.
- Nvidia disabled or missing key fallback to OpenAI.
- Both providers failing returning clean provider-neutral unavailable response.
- Both providers disabled or unconfigured.
- Fallback disabled preventing OpenAI calls.
- Strict fallback boundaries:
  * Nvidia 400/401/403 Client Errors MUST NOT trigger fallback to OpenAI.
  * Nvidia safety refusals (finishReason="SAFETY" or prompt block) MUST NOT trigger fallback.
- Overall request deadline enforcement cutting off retries/fallback.
- Strict response & schema validation for BOTH providers (empty, truncated, schema mismatch).
- Strict secret & private data protection:
  * API keys redacted from logs and error details.
  * Raw HTTP error bodies (which might contain sensitive data or prompt echo) never exposed.
- Truthful observability: exact token counts and cost estimation for supported models,
  and None (unknown) for unrecognized models.
"""

from __future__ import annotations

import io
import json
import logging
import urllib.error
from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from services.ai.provider_engine import (
    CloudflareAIProviderAdapter,
    NvidiaProviderAdapter,
    ModelPricing,
    OpenAIProviderAdapter,
    ProviderAttempt,
    ProviderClientError,
    ProviderEmptyResponseError,
    ProviderError,
    ProviderMessage,
    ProviderRateLimitError,
    ProviderRequest,
    ProviderResponse,
    ProviderSafetyRefusalError,
    ProviderSchemaValidationError,
    ProviderTimeoutError,
    ProviderTransientError,
    ProviderTruncatedError,
    TokenUsage,
    UnifiedProviderConfig,
    UnifiedProviderEngine,
    _parse_http_error,
    estimate_cost_usd,
    validate_structured_output,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_nvidia():
    return MagicMock(spec=NvidiaProviderAdapter)


@pytest.fixture
def mock_cloudflare():
    return MagicMock(spec=CloudflareAIProviderAdapter)


@pytest.fixture
def cloudflare_config():
    return UnifiedProviderConfig(
        primary_provider="cloudflare",
        fallback_provider="nvidia",
        cloudflare_enabled=True,
        nvidia_enabled=True,
        fallback_enabled=True,
        cloudflare_account_id="mock-cf-account",
        cloudflare_api_token="mock-cf-token",
        cloudflare_model="@cf/ibm-granite/granite-4.0-h-micro",
        nvidia_model="nvidia/nemotron-3.5-super-vl-120b-a12b",
        timeout_seconds=5.0,
        max_retries=1,
        nvidia_api_key="mock-nvidia-key",
    )


@pytest.fixture
def sample_config():
    return UnifiedProviderConfig(
        primary_provider="cloudflare",
        fallback_provider="nvidia",
        cloudflare_enabled=True,
        nvidia_enabled=True,
        fallback_enabled=True,
        cloudflare_account_id="mock-cf-account",
        cloudflare_api_token="mock-cf-token",
        cloudflare_model="@cf/ibm-granite/granite-4.0-h-micro",
        nvidia_model="nvidia/nemotron-3.5-super-vl-120b-a12b",
        timeout_seconds=5.0,
        max_retries=1,
        nvidia_api_key="mock-nvidia-key",
    )


@pytest.fixture
def sample_request():
    return ProviderRequest(
        messages=[ProviderMessage(role="user", content="Hello, suggest action steps.")],
        system_instruction="You are a helpful assistant.",
        temperature=0.0,
        max_tokens=256,
        purpose="test_purpose",
    )


@pytest.mark.parametrize("purpose", ["model_led_router", "model_led_synthesis", "general"])
@pytest.mark.parametrize(
    ("provider", "model", "reasoning"),
    [
        ("cloudflare", "@cf/zai-org/glm-4.7-flash", {"enable_thinking": True}),
        ("cloudflare", "@cf/ibm-granite/granite-4.0-h-micro", None),
        ("nvidia", "nvidia/nemotron-3.5-super-vl-120b-a12b", "none"),
    ],
)
def test_model_led_output_limit_and_reasoning_wire_settings(
    sample_config, purpose, provider, model, reasoning, monkeypatch,
):
    monkeypatch.delenv("PMS_AI_NVIDIA_REASONING_EFFORT", raising=False)
    model_led = purpose != "general"
    request = ProviderRequest(
        messages=[ProviderMessage(role="user", content="Return a JSON result.")],
        purpose=purpose,
        response_format="json",
        max_tokens=None if model_led else 300,
    )
    bodies = []
    if provider == "cloudflare":
        adapter_class = CloudflareAIProviderAdapter
        response = {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
    else:
        adapter_class = NvidiaProviderAdapter
        response = {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}

    def transport(http_request, *, timeout):
        bodies.append(json.loads(http_request.data))
        return io.BytesIO(json.dumps(response).encode())

    adapter_class(transport).execute(request, sample_config, timeout=5, model=model)
    assert len(bodies) == 1
    body = bodies[0]
    if provider == "cloudflare":
        assert body["response_format"] == {"type": "json_object"}
        assert "max_completion_tokens" not in body
        if model_led:
            assert "max_tokens" not in body
        else:
            assert body["max_tokens"] == 300
        expected = reasoning
        if reasoning == {"enable_thinking": True} and purpose == "model_led_synthesis":
            # Synthesis only rewords verified facts, so it skips the slow reasoning tokens by default.
            expected = {"enable_thinking": False}
        assert body.get("chat_template_kwargs") == (expected if model_led else None)
    else:
        assert body["response_format"] == {"type": "json_object"}
        assert body["stream"] is False
        assert body.get("max_tokens") == (None if model_led else 300)
        assert body["reasoning_effort"] == (reasoning if model_led else "none")


# ---------------------------------------------------------------------------
# Core Happy Path & Hierarchy Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("role", "expected"), [
    ("routine", "cloudflare"), ("investigation", "nvidia"), ("repair", "nvidia"),
])
def test_task_routing_uses_selected_adapter(role, expected, mock_cloudflare, mock_nvidia, sample_config, sample_request):
    sample_config = replace(sample_config, task_routing_enabled=True)
    sample_request.task_role = role
    for adapter in (mock_cloudflare, mock_nvidia):
        adapter.execute.return_value = ("Verified", TokenUsage())
    engine = UnifiedProviderEngine(config=sample_config, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
    response = engine.generate(sample_request)
    assert response.provider == expected
    assert [attempt.provider for attempt in response.attempts] == [expected]


def test_retired_cloudflare_model_uses_alternative_once(mock_cloudflare, mock_nvidia, sample_config, sample_request):
    sample_config = replace(sample_config, cloudflare_alter_model="replacement")
    mock_cloudflare.execute.side_effect = [
        ProviderClientError("retired", http_code=410), ProviderClientError("also retired", http_code=410),
    ]
    engine = UnifiedProviderEngine(config=sample_config, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
    resp = engine.generate(sample_request)
    assert not resp.is_success
    assert [a.model for a in resp.attempts] == [sample_config.cloudflare_model, "replacement"]
    mock_nvidia.execute.assert_not_called()


def test_primary_primary_success(mock_cloudflare, mock_nvidia, sample_config, sample_request):
    """When Nvidia succeeds, it returns immediately and OpenAI is never invoked."""
    mock_cloudflare.execute.return_value = (
        "Action step 1 from Nvidia.",
        TokenUsage(prompt_tokens=10, completion_tokens=8, total_tokens=18, neurons=1.0),
    )

    engine = UnifiedProviderEngine(
        config=sample_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "cloudflare"
    assert resp.model == "@cf/ibm-granite/granite-4.0-h-micro"
    assert resp.outcome == "success"
    assert resp.content == "Action step 1 from Nvidia."
    assert resp.usage.total_tokens == 18
    assert resp.estimated_cost_usd is not None
    assert resp.estimated_cost_usd > 0
    assert len(resp.attempts) == 1
    assert resp.attempts[0].status == "success"

    # OpenAI must never be called when primary succeeds
    mock_cloudflare.execute.assert_called_once()
    mock_nvidia.execute.assert_not_called()


def test_primary_transient_error_retries_and_succeeds(mock_cloudflare, mock_nvidia, sample_config, sample_request):
    """Nvidia transient error (e.g. 503) triggers a bounded retry, succeeding on 2nd attempt."""
    mock_cloudflare.execute.side_effect = [
        ProviderTransientError("Service temporarily unavailable", http_code=503),
        ("Recovered action step from Nvidia.", TokenUsage(prompt_tokens=12, completion_tokens=10, total_tokens=22)),
    ]

    engine = UnifiedProviderEngine(
        config=sample_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "cloudflare"
    assert resp.outcome == "success"
    assert resp.content == "Recovered action step from Nvidia."
    assert len(resp.attempts) == 2
    assert resp.attempts[0].status == "transient_error"
    assert resp.attempts[0].http_code == 503
    assert resp.attempts[1].status == "success"
    assert resp.attempts[1].retry_count == 1

    assert mock_cloudflare.execute.call_count == 2
    mock_nvidia.execute.assert_not_called()


def test_primary_rate_limit_falls_back_to_nvidia_immediately(mock_cloudflare, mock_nvidia, sample_config, sample_request):
    """Nvidia HTTP 429 rate limit or quota exhaustion immediately falls back to OpenAI without retrying Nvidia."""
    mock_cloudflare.execute.side_effect = ProviderRateLimitError("Quota exceeded", http_code=429)
    mock_nvidia.execute.return_value = (
        "Action step from OpenAI fallback.",
        TokenUsage(prompt_tokens=15, completion_tokens=12, total_tokens=27),
    )

    engine = UnifiedProviderEngine(
        config=sample_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "nvidia"
    assert resp.model == "nvidia/nemotron-3.5-super-vl-120b-a12b"
    assert resp.outcome == "fallback_success"
    assert resp.content == "Action step from OpenAI fallback."
    assert resp.usage.total_tokens == 27
    assert len(resp.attempts) == 2
    assert resp.attempts[0].status == "rate_limited"
    assert resp.attempts[0].provider == "cloudflare"
    assert resp.attempts[1].status == "success"
    assert resp.attempts[1].provider == "nvidia"

    # Nvidia must only be called once (no pointless retries on 429 quota exhaustion)
    assert mock_cloudflare.execute.call_count == 1
    mock_nvidia.execute.assert_called_once()


def test_primary_timeout_falls_back_to_nvidia(mock_cloudflare, mock_nvidia, sample_config, sample_request):
    """Nvidia timeout after max retries falls back cleanly to OpenAI."""
    mock_cloudflare.execute.side_effect = ProviderTimeoutError("Nvidia timed out after 5.0s")
    mock_nvidia.execute.return_value = (
        "Action step from OpenAI after timeout.",
        TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
    )

    engine = UnifiedProviderEngine(
        config=sample_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "nvidia"
    assert resp.outcome == "fallback_success"
    assert resp.content == "Action step from OpenAI after timeout."
    # 1 initial + 1 retry = 2 Nvidia attempts, followed by 1 OpenAI attempt
    assert len(resp.attempts) == 3
    assert resp.attempts[0].status == "timeout"
    assert resp.attempts[1].status == "timeout"
    assert resp.attempts[2].status == "success"

    assert mock_cloudflare.execute.call_count == 2
    mock_nvidia.execute.assert_called_once()


def test_primary_disabled_falls_back_to_nvidia(mock_cloudflare, mock_nvidia, sample_request):
    """When Nvidia is disabled by config, it falls back to OpenAI without calling Nvidia."""
    cfg = UnifiedProviderConfig(
        primary_provider="cloudflare",
        fallback_provider="nvidia",
        cloudflare_enabled=False,
        nvidia_enabled=True,
        fallback_enabled=True,
        cloudflare_account_id="acct", cloudflare_api_token="mock-key",
        nvidia_api_key="mock-key",
    )
    mock_nvidia.execute.return_value = ("OpenAI response", TokenUsage(5, 5, 10))

    engine = UnifiedProviderEngine(config=cfg, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "nvidia"
    assert resp.outcome == "fallback_success"
    assert resp.attempts[0].status == "disabled"
    assert resp.attempts[1].status == "success"

    mock_cloudflare.execute.assert_not_called()
    mock_nvidia.execute.assert_called_once()


def test_primary_missing_key_falls_back_to_nvidia(mock_cloudflare, mock_nvidia, sample_request):
    """When Nvidia key is empty, it records missing_key and falls back to OpenAI."""
    cfg = UnifiedProviderConfig(
        primary_provider="cloudflare",
        fallback_provider="nvidia",
        cloudflare_enabled=True,
        nvidia_enabled=True,
        fallback_enabled=True,
        cloudflare_account_id="", cloudflare_api_token="",  # Unset
        nvidia_api_key="mock-openai-key",
    )
    mock_nvidia.execute.return_value = ("OpenAI response", TokenUsage(5, 5, 10))

    engine = UnifiedProviderEngine(config=cfg, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "nvidia"
    assert resp.outcome == "fallback_success"
    assert resp.attempts[0].status == "missing_key"
    assert resp.attempts[1].status == "success"

    mock_cloudflare.execute.assert_not_called()
    mock_nvidia.execute.assert_called_once()


def test_both_providers_fail_returns_clear_provider_unavailable(mock_cloudflare, mock_nvidia, sample_config, sample_request):
    """When both primary and fallback fail, returns a provider-neutral unavailable response."""
    mock_cloudflare.execute.side_effect = ProviderTransientError("Nvidia 500 error", http_code=500)
    mock_nvidia.execute.side_effect = ProviderRateLimitError("OpenAI 429 quota error", http_code=429)

    engine = UnifiedProviderEngine(config=sample_config, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.provider == "none"
    assert resp.model == "none"
    assert resp.content == ""
    assert resp.outcome == "provider_unavailable"
    assert "All AI providers are currently unavailable" in (resp.error_detail or "")
    assert len(resp.attempts) == 3  # 2 Nvidia + 1 OpenAI


def test_both_providers_disabled_returns_provider_unavailable(mock_cloudflare, mock_nvidia, sample_request):
    """When all providers are disabled, returns clean unavailable response with zero network calls."""
    cfg = UnifiedProviderConfig(
        primary_provider="cloudflare",
        fallback_provider="nvidia",
        cloudflare_enabled=False,
        nvidia_enabled=False,
        fallback_enabled=True,
    )
    engine = UnifiedProviderEngine(config=cfg, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.outcome == "provider_unavailable"
    assert resp.content == ""
    mock_cloudflare.execute.assert_not_called()
    mock_nvidia.execute.assert_not_called()


def test_fallback_disabled_does_not_call_fallback(mock_cloudflare, mock_nvidia, sample_request):
    """When fallback_enabled=False, primary failure stops immediately and never calls OpenAI."""
    cfg = UnifiedProviderConfig(
        primary_provider="cloudflare",
        fallback_provider="nvidia",
        cloudflare_enabled=True,
        nvidia_enabled=True,
        fallback_enabled=False,  # Fallback disabled
        cloudflare_account_id="acct", cloudflare_api_token="mock-key",
        nvidia_api_key="mock-key",
        max_retries=0,
    )
    mock_cloudflare.execute.side_effect = ProviderTransientError("Nvidia down")

    engine = UnifiedProviderEngine(config=cfg, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.outcome == "provider_unavailable"
    mock_cloudflare.execute.assert_called_once()
    mock_nvidia.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Strict Boundary & Fallback Prohibition Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("http_code", [400, 401, 403])
def test_primary_client_error_does_not_fallback(http_code, mock_cloudflare, mock_nvidia, sample_config, sample_request):
    """HTTP 400, 401, 403 on Nvidia are client errors and MUST NOT trigger fallback to OpenAI."""
    mock_cloudflare.execute.side_effect = ProviderClientError(f"Client error {http_code}", http_code=http_code)

    engine = UnifiedProviderEngine(config=sample_config, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.provider == "none"
    assert resp.outcome in ("invalid_request", "error")
    assert resp.attempts[0].status == "client_error"
    assert resp.attempts[0].http_code == http_code

    # CRITICAL: OpenAI fallback must NOT be called for client errors
    mock_nvidia.execute.assert_not_called()
    assert len(resp.attempts) == 1


def test_primary_safety_refusal_does_not_fallback(mock_cloudflare, mock_nvidia, sample_config, sample_request):
    """Nvidia safety refusals MUST NOT trigger fallback to OpenAI to prevent safety filter circumvention."""
    mock_cloudflare.execute.side_effect = ProviderSafetyRefusalError("Content blocked by Nvidia safety policy")

    engine = UnifiedProviderEngine(config=sample_config, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.provider == "none"
    assert resp.outcome == "safety_refusal"
    assert "Content blocked" in (resp.error_detail or "")
    assert resp.attempts[0].status == "safety_refusal"

    # CRITICAL: OpenAI fallback must NOT be called for safety blocks
    mock_nvidia.execute.assert_not_called()
    assert len(resp.attempts) == 1


def test_empty_request_rejected_without_calling_providers(mock_cloudflare, mock_nvidia, sample_config):
    """Empty request fails input validation immediately without invoking any model."""
    empty_req = ProviderRequest(messages=[], system_instruction=None)
    engine = UnifiedProviderEngine(config=sample_config, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
    resp = engine.generate(empty_req)

    assert resp.is_success is False
    assert resp.outcome == "invalid_request"
    assert "empty_request" in (resp.error_detail or "")
    mock_cloudflare.execute.assert_not_called()
    mock_nvidia.execute.assert_not_called()


def test_excessive_prompt_length_rejected_without_calling_providers(mock_cloudflare, mock_nvidia, sample_config):
    """Request exceeding 120,000 characters is rejected without calling any provider."""
    huge_req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="x" * 125_000)],
    )
    engine = UnifiedProviderEngine(config=sample_config, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
    resp = engine.generate(huge_req)

    assert resp.is_success is False
    assert resp.outcome == "invalid_request"
    assert "prompt_exceeds_maximum_length" in (resp.error_detail or "")
    mock_cloudflare.execute.assert_not_called()
    mock_nvidia.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Deadline & Timeout Tests
# ---------------------------------------------------------------------------


def test_overall_deadline_exhaustion_prevents_subsequent_attempts(mock_cloudflare, mock_nvidia, sample_config):
    """If timeout_seconds is exceeded, engine halts and does not initiate further retries or fallback."""
    # Set a very tight request timeout (0.001 seconds)
    req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="Test")],
        timeout_seconds=0.0001,
    )

    def slow_nvidia(*args, **kwargs):
        import time
        time.sleep(0.005)
        raise ProviderTimeoutError("Nvidia timed out")

    mock_cloudflare.execute.side_effect = slow_nvidia

    engine = UnifiedProviderEngine(config=sample_config, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
    resp = engine.generate(req)

    assert resp.is_success is False
    assert resp.outcome == "timeout"
    # OpenAI must NOT have been called because overall deadline expired
    mock_nvidia.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Schema & Output Validation Tests
# ---------------------------------------------------------------------------


def test_schema_validation_helper():
    """validate_structured_output validates valid JSON, object types, and required fields."""
    schema = {
        "type": "object",
        "required": ["step", "owner"],
        "properties": {"step": {"type": "string"}, "owner": {"type": "string"}},
    }

    # Valid
    ok, err = validate_structured_output('{"step": "Plan", "owner": "Alice"}', schema)
    assert ok is True
    assert err is None

    # Invalid JSON syntax
    ok, err = validate_structured_output("not valid json", schema)
    assert ok is False
    assert "not valid JSON" in err

    # Wrong type (expected object, got list)
    ok, err = validate_structured_output('[{"step": "Plan"}]', schema)
    assert ok is False
    assert "Expected JSON object" in err

    # Missing required field
    ok, err = validate_structured_output('{"step": "Plan"}', schema)
    assert ok is False
    assert "missing required fields" in err


def test_primary_schema_validation_failure_is_handled(mock_cloudflare, mock_nvidia, sample_config):
    """When Nvidia returns invalid JSON for a structured request, schema error is terminal and MUST NOT fall back to OpenAI."""
    mock_cloudflare.execute.side_effect = ProviderSchemaValidationError("Nvidia JSON output validation failed: missing key")

    req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="Give JSON")],
        response_format="json",
        json_schema={"type": "object", "required": ["valid"]},
    )

    engine = UnifiedProviderEngine(config=sample_config, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
    resp = engine.generate(req)

    assert resp.is_success is False
    assert resp.outcome == "schema_validation_failed"
    assert "missing key" in resp.error_detail
    mock_nvidia.execute.assert_not_called()


def test_fallback_schema_validation_failure_never_reports_success(mock_cloudflare, mock_nvidia, sample_config):
    """When OpenAI fallback also fails schema validation, response is marked unavailable/failed."""
    mock_cloudflare.execute.side_effect = ProviderRateLimitError("Quota exceeded", http_code=429)
    mock_nvidia.execute.side_effect = ProviderSchemaValidationError("OpenAI JSON output validation failed: invalid format")

    req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="Give JSON")],
        response_format="json",
        json_schema={"type": "object", "required": ["valid"]},
    )

    engine = UnifiedProviderEngine(config=sample_config, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
    resp = engine.generate(req)

    assert resp.is_success is False
    assert resp.outcome == "provider_unavailable"
    assert resp.content == ""


def test_truncated_response_never_reports_success(mock_cloudflare, mock_nvidia, sample_config, sample_request):
    """When response is truncated (max tokens reached), fallback is forbidden and error is reported."""
    mock_cloudflare.execute.side_effect = ProviderTruncatedError("Nvidia candidate truncated due to max output tokens")

    engine = UnifiedProviderEngine(config=sample_config, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.outcome == "truncated_response"
    assert resp.content == ""
    mock_nvidia.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Privacy & Secret Redaction Tests
# ---------------------------------------------------------------------------


def test_secret_redaction_in_logs_and_error_details(mock_cloudflare, mock_nvidia, sample_config, sample_request, caplog):
    """API keys in exceptions and error details must be strictly redacted."""
    raw_secret_nvidia = "AIzaSyD-mock1234567890abcdef"
    raw_secret_openai = "sk-proj-mock1234567890abcdef"

    mock_cloudflare.execute.side_effect = ProviderTransientError(f"Failed calling key={raw_secret_nvidia} connection refused")
    mock_nvidia.execute.side_effect = ProviderRateLimitError(f"Key {raw_secret_openai} exhausted quota")

    with caplog.at_level(logging.WARNING):
        engine = UnifiedProviderEngine(config=sample_config, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
        resp = engine.generate(sample_request)

    # Neither raw key must appear anywhere in the response error_detail
    assert raw_secret_nvidia not in (resp.error_detail or "")
    assert raw_secret_openai not in (resp.error_detail or "")

    # Neither raw key must appear anywhere in logs
    assert raw_secret_nvidia not in caplog.text
    assert raw_secret_openai not in caplog.text


def test_parse_http_error_does_not_leak_response_body():
    """_parse_http_error classifies errors without returning raw sensitive upstream error bodies."""
    sensitive_body = '{"error": {"message": "Invalid prompt containing SSN 123-45-6789 and employee Ahmed"}}'.encode("utf-8")
    fp = io.BytesIO(sensitive_body)
    http_exc = urllib.error.HTTPError(
        url="https://api.example.com",
        code=400,
        msg="Bad Request",
        hdrs={},  # type: ignore[arg-type]
        fp=fp,
    )

    classified = _parse_http_error(http_exc, "Nvidia")
    assert isinstance(classified, ProviderClientError)
    assert classified.http_code == 400
    # The classified exception message MUST NOT contain sensitive details from the error body
    assert "SSN" not in str(classified)
    assert "123-45-6789" not in str(classified)
    assert "Ahmed" not in str(classified)
    assert "Nvidia client error (HTTP 400)" in str(classified)


# ---------------------------------------------------------------------------
# Truthful Observability & Pricing Tests
# ---------------------------------------------------------------------------


def test_cost_estimation_supported_models():
    """Cost estimation correctly applies token pricing for Gemini and OpenAI."""
    gemini_usage = TokenUsage(prompt_tokens=1_000_000, completion_tokens=1_000_000, total_tokens=2_000_000)
    cost_gemini = estimate_cost_usd("gemini", "gemini-2.5-flash", gemini_usage)
    # Verified pricing: 0.30 in + 2.50 out = 2.80 USD
    assert cost_gemini == pytest.approx(2.80, rel=1e-4)

    openai_mini_usage = TokenUsage(prompt_tokens=1_000_000, completion_tokens=1_000_000, total_tokens=2_000_000)
    cost_mini = estimate_cost_usd("openai", "gpt-4o-mini", openai_mini_usage)
    assert cost_mini == pytest.approx(0.75, rel=1e-4)

    openai_4o_usage = TokenUsage(prompt_tokens=1_000_000, completion_tokens=1_000_000, total_tokens=2_000_000)
    cost_4o = estimate_cost_usd("openai", "gpt-4o", openai_4o_usage)
    # 2.50 + 10.00 = 12.50 USD
    assert cost_4o == pytest.approx(12.50, rel=1e-4)


def test_cost_estimation_unknown_model_returns_none():
    """Truthful reporting: Cost estimation returns None for unrecognized models or zero tokens."""
    usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    assert estimate_cost_usd("nvidia", "unknown-model-xyz", usage) is None
    assert estimate_cost_usd("openai", "custom-fine-tuned", usage) is None

    # Zero tokens returns None
    zero_usage = TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    assert estimate_cost_usd("gemini", "gemini-2.5-flash", zero_usage) is None


# ---------------------------------------------------------------------------
# Adapter Formatting Tests
# ---------------------------------------------------------------------------


def test_nvidia_adapter_payload_formatting(sample_config):
    def transport(request, *, timeout):
        assert request.full_url == "https://integrate.api.nvidia.com/v1/chat/completions"
        assert request.get_header("Authorization") == f"Bearer {sample_config.nvidia_api_key}"
        assert timeout == 4.5
        assert json.loads(request.data)["messages"] == [
            {"role": "system", "content": "Return structured output"},
            {"role": "user", "content": "Return JSON"},
        ]
        return io.BytesIO(json.dumps({
            "choices": [{"finish_reason": "stop", "message": {"content": '{"status": "ok"}'}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
        }).encode())

    text, usage = NvidiaProviderAdapter(transport).execute(
        ProviderRequest(
            messages=[ProviderMessage(role="user", content="Return JSON")],
            system_instruction="Return structured output",
            response_format="json",
        ),
        sample_config,
        timeout=4.5,
    )
    assert json.loads(text) == {"status": "ok"}
    assert usage.total_tokens == 11


def test_openai_adapter_is_inert_and_makes_no_outbound_request():
    """OpenAIProviderAdapter is deprecated: it never performs I/O, whatever client or config is supplied."""
    calls = []

    def must_not_be_called(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("outbound request attempted")

    adapter = OpenAIProviderAdapter(http_client=must_not_be_called)
    req = ProviderRequest(messages=[ProviderMessage(role="user", content="hello")], response_format="json")
    with pytest.raises(ProviderClientError) as excinfo:
        adapter.execute(req, UnifiedProviderConfig(), timeout=1.0)
    assert "decommissioned" in str(excinfo.value)
    assert calls == []


def test_openai_adapter_source_has_no_endpoint_or_credentials():
    import inspect

    source = inspect.getsource(OpenAIProviderAdapter)
    assert "api.openai.com" not in source
    assert "Authorization" not in source
    assert "urllib" not in source


def test_openai_config_surface_is_removed():
    cfg = UnifiedProviderConfig()
    for attr in ("openai_enabled", "openai_model", "openai_api_key"):
        assert not hasattr(cfg, attr)


def test_openai_can_never_be_selected_as_a_provider(monkeypatch, sample_request):
    """Even if configuration names openai (provider, flag, key), the engine never routes to it."""
    from services.ai.provider_engine import load_unified_provider_config

    monkeypatch.setenv("PMS_AI_PRIMARY_PROVIDER", "openai")
    monkeypatch.setenv("PMS_AI_FALLBACK_PROVIDER", "openai")
    monkeypatch.setenv("PMS_AI_OPENAI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY_ALTER", raising=False)
    cfg = load_unified_provider_config()
    assert cfg.effective_primary_provider == "nvidia"
    assert cfg.effective_fallback_provider == "cloudflare"

    cloudflare = MagicMock(spec=CloudflareAIProviderAdapter)
    nvidia = MagicMock(spec=NvidiaProviderAdapter)
    opener = MagicMock()
    engine = UnifiedProviderEngine(
        config=cfg,
        cloudflare_adapter=cloudflare,
        nvidia_adapter=nvidia,
    )
    monkeypatch.setattr("urllib.request.urlopen", opener)
    resp = engine.generate(sample_request)
    assert resp.is_success is False
    assert resp.provider == "none"
    assert all(a.provider in ("cloudflare", "nvidia") for a in resp.attempts)
    cloudflare.execute.assert_not_called()
    nvidia.execute.assert_not_called()
    opener.assert_not_called()


# ---------------------------------------------------------------------------
# Regression Tests: HTTP Error Classification & Schema Validation Rigor
# ---------------------------------------------------------------------------


def test_parse_http_error_does_not_turn_400_with_rate_into_rate_limit(mock_cloudflare, mock_nvidia, sample_config):
    """HTTP 400 containing substrings like 'completion_rate' must never be classified as rate limit."""
    import io
    import urllib.error
    from services.ai.provider_engine import ProviderClientError, _parse_http_error

    # Simulate HTTP 400 Bad Request where error message contains the word "rate"
    err_body = b'{"error": "Invalid completion_rate parameter: value out of bounds"}'
    err = urllib.error.HTTPError(
        url="https://integrate.api.nvidia.com",
        code=400,
        msg="Bad Request",
        hdrs={},
        fp=io.BytesIO(err_body),
    )

    parsed = _parse_http_error(err, "Nvidia")
    assert isinstance(parsed, ProviderClientError)
    assert not isinstance(parsed, ProviderRateLimitError)
    assert parsed.http_code == 400

    # In engine: must report invalid_request and strictly forbid fallback
    mock_cloudflare.execute.side_effect = parsed
    engine = UnifiedProviderEngine(config=sample_config, cloudflare_adapter=mock_cloudflare, nvidia_adapter=mock_nvidia)
    req = ProviderRequest(messages=[ProviderMessage(role="user", content="Test")])
    resp = engine.generate(req)

    assert resp.is_success is False
    assert resp.outcome == "invalid_request"
    mock_nvidia.execute.assert_not_called()


def test_complete_json_schema_validation_features():
    """Verify recursive type checking, nested required fields, enums, additionalProperties, and unsupported keywords."""
    # 1. Unsupported features must be cleanly rejected
    schema_ref = {
        "type": "object",
        "properties": {"item": {"$ref": "#/definitions/Item"}},
    }
    ok, err = validate_structured_output('{"item": "val"}', schema_ref)
    assert ok is False
    assert "Unsupported JSON schema feature: '$ref'" in err

    schema_oneof = {
        "type": "object",
        "oneOf": [{"properties": {"a": {"type": "string"}}}],
    }
    ok, err = validate_structured_output('{"a": "val"}', schema_oneof)
    assert ok is False
    assert "Unsupported JSON schema feature: 'oneOf'" in err

    # 2. Nested schema validation with additionalProperties: False
    strict_schema = {
        "type": "object",
        "required": ["step", "details"],
        "additionalProperties": False,
        "properties": {
            "step": {"type": "string"},
            "details": {
                "type": "object",
                "required": ["priority", "days"],
                "properties": {
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                    "days": {"type": "integer"},
                },
            },
        },
    }

    # Valid instance
    valid_json = '{"step": "Review", "details": {"priority": "high", "days": 5}}'
    ok, err = validate_structured_output(valid_json, strict_schema)
    assert ok is True
    assert err is None

    # Invalid: extra property when additionalProperties is False
    extra_prop_json = '{"step": "Review", "extra_key": 123, "details": {"priority": "high", "days": 5}}'
    ok, err = validate_structured_output(extra_prop_json, strict_schema)
    assert ok is False
    assert "additionalProperties is False" in err

    # Invalid: nested missing required field
    missing_nested = '{"step": "Review", "details": {"priority": "high"}}'
    ok, err = validate_structured_output(missing_nested, strict_schema)
    assert ok is False
    assert "missing required fields" in err

    # Invalid: enum mismatch
    invalid_enum = '{"step": "Review", "details": {"priority": "critical", "days": 5}}'
    ok, err = validate_structured_output(invalid_enum, strict_schema)
    assert ok is False
    assert "not in enum" in err

    # Invalid: type mismatch (string instead of integer)
    invalid_type = '{"step": "Review", "details": {"priority": "high", "days": "five"}}'
    ok, err = validate_structured_output(invalid_type, strict_schema)
    assert ok is False
    assert "Expected integer" in err


def test_read_with_deadline_timeout_enforcement():
    """Slow response reads must abort at the specified timeout."""
    import time
    from services.ai.provider_engine import _read_with_deadline

    class SlowSocketMock:
        def read(self, *args):
            time.sleep(0.05)
            return b"data"

    mock_resp = SlowSocketMock()
    with pytest.raises(TimeoutError) as exc_info:
        _read_with_deadline(mock_resp, timeout=0.02)
    assert "exceeded timeout limit" in str(exc_info.value)


def test_schema_validation_advanced_constraints():
    """Verify minItems, maxItems, uniqueItems, numeric bounds, nullable types, and error sanitization."""
    # 1. Array minItems / maxItems / uniqueItems
    array_schema = {
        "type": "object",
        "required": ["actions"],
        "properties": {
            "actions": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "uniqueItems": True,
                "items": {"type": "string"},
            }
        },
    }
    # Empty array violates minItems: 1
    ok, err = validate_structured_output('{"actions": []}', array_schema)
    assert ok is False
    assert "fewer items than minItems" in err

    # Valid array
    ok, err = validate_structured_output('{"actions": ["Coaching"]}', array_schema)
    assert ok is True
    assert err is None

    # Array exceeds maxItems: 3
    ok, err = validate_structured_output('{"actions": ["a", "b", "c", "d"]}', array_schema)
    assert ok is False
    assert "more items than maxItems" in err

    # Array contains duplicate items
    ok, err = validate_structured_output('{"actions": ["a", "a"]}', array_schema)
    assert ok is False
    assert "contains duplicate items" in err

    # 2. Numeric bounds
    num_schema = {
        "type": "object",
        "properties": {
            "score": {"type": "number", "minimum": 0.0, "maximum": 100.0},
            "ratio": {"type": "number", "exclusiveMinimum": 0.0, "exclusiveMaximum": 1.0},
        },
    }
    # Below minimum
    ok, err = validate_structured_output('{"score": -5.0}', num_schema)
    assert ok is False
    assert "less than minimum" in err

    # Above maximum
    ok, err = validate_structured_output('{"score": 150.0}', num_schema)
    assert ok is False
    assert "greater than maximum" in err

    # Equal to exclusiveMinimum
    ok, err = validate_structured_output('{"ratio": 0.0}', num_schema)
    assert ok is False
    assert "less than or equal to exclusiveMinimum" in err

    # Equal to exclusiveMaximum
    ok, err = validate_structured_output('{"ratio": 1.0}', num_schema)
    assert ok is False
    assert "greater than or equal to exclusiveMaximum" in err

    # Valid numbers
    ok, err = validate_structured_output('{"score": 85.5, "ratio": 0.75}', num_schema)
    assert ok is True

    # 3. Nullable and union types (including nullable enums from Nvidia structured tool schemas)
    nullable_schema = {
        "type": "object",
        "properties": {
            "note": {"type": ["string", "null"]},
            "comment": {"type": "string", "nullable": True},
            "threshold_operator": {"type": ["string", "null"], "enum": ["gt", "gte", "lt", "lte"]},
        },
    }
    ok, err = validate_structured_output('{"note": null, "comment": null, "threshold_operator": null}', nullable_schema)
    assert ok is True
    ok, err = validate_structured_output('{"note": "valid note", "comment": "valid comment", "threshold_operator": "lt"}', nullable_schema)
    assert ok is True
    ok, err = validate_structured_output('{"note": null, "comment": null, "threshold_operator": "invalid"}', nullable_schema)
    assert ok is False
    assert "not in enum" in err

    # 4. Error message NEVER leaks model private/synthetic values
    private_val = "CONFIDENTIAL_SYNTHETIC_MODEL_DATA_xyz987"
    enum_schema = {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["APPROVE", "REJECT"]}
        },
    }
    ok, err = validate_structured_output(f'{{"decision": "{private_val}"}}', enum_schema)
    assert ok is False
    assert private_val not in err
    assert "not in enum" in err


def test_unsupported_schema_keywords_rejected_before_provider_call():
    """Unsupported schema keywords must be caught in validate_input before any provider call."""
    req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="Test")],
        response_format="json",
        json_schema={
            "type": "object",
            "properties": {"data": {"$schema": "http://json-schema.org/draft-07/schema#"}},
        },
    )
    issue = req.validate_input()
    assert issue is not None
    assert "unsupported_schema_keyword:$schema" in issue


def test_http_404_classified_as_client_error_not_rate_limit():
    """HTTP 404 with 'rate_limit' text in body must be classified as client error, never rate limit."""
    body = b'<html><body>Not Found: rate_limit exceeded on path /v1/models</body></html>'
    exc = urllib.error.HTTPError(
        url="https://api.example.com",
        code=404,
        msg="Not Found",
        hdrs=MagicMock(),
        fp=io.BytesIO(body),
    )
    err = _parse_http_error(exc, "Nvidia")
    assert isinstance(err, ProviderClientError)
    assert not isinstance(err, ProviderRateLimitError)
    assert err.http_code == 404


def test_safety_refusal_outcome_preserved(mock_cloudflare, mock_nvidia, sample_config, sample_request):
    """Safety refusal from provider must be preserved in outcome, never masked as provider_unavailable."""
    mock_cloudflare.execute.side_effect = ProviderSafetyRefusalError("Content blocked by safety policy")
    engine = UnifiedProviderEngine(
        config=sample_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    response = engine.generate(sample_request)
    assert response.outcome == "safety_refusal"
    assert response.is_success is False
    # OpenAI must NOT have been called to bypass safety
    mock_nvidia.execute.assert_not_called()


def test_cost_estimation_incomplete_data_returns_none():
    """estimate_cost_usd returns None for incomplete usage, negative tokens, or unknown models."""
    # Unknown model
    assert estimate_cost_usd("nvidia", "nvidia-unknown-xyz", TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)) is None
    # None usage
    assert estimate_cost_usd("nvidia", "nvidia/nemotron-3.5-super-vl-120b-a12b", None) is None
    # Negative tokens
    assert estimate_cost_usd("nvidia", "nvidia/nemotron-3.5-super-vl-120b-a12b", TokenUsage(prompt_tokens=-10, completion_tokens=50, total_tokens=40)) is None
    # Incomplete breakdown (prompt=0, completion=0, but total > 0)
    assert estimate_cost_usd("nvidia", "nvidia/nemotron-3.5-super-vl-120b-a12b", TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=100)) is None


def test_schema_properties_named_like_keywords():
    """Properties named like schema keywords (e.g. 'oneOf', 'type', 'minimum') must be allowed as property names."""
    schema = {
        "type": "object",
        "required": ["oneOf", "type", "minimum"],
        "properties": {
            "oneOf": {"type": "string"},
            "type": {"type": "integer"},
            "minimum": {"type": "number"},
        },
    }
    # 1. validate_input on ProviderRequest must not reject it
    req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="Test")],
        response_format="json",
        json_schema=schema,
    )
    assert req.validate_input() is None

    # 2. validate_structured_output validates it successfully
    ok, err = validate_structured_output('{"oneOf": "choice_a", "type": 1, "minimum": 0.5}', schema)
    assert ok is True
    assert err is None

    # 3. Type mismatch does not leak model values
    private_val = "SECRET_VALUE_999"
    ok, err = validate_structured_output(f'{{"oneOf": 12345, "type": "{private_val}", "minimum": 0.5}}', schema)
    assert ok is False
    assert private_val not in err
    assert "Expected" in err


def test_unsupported_schema_keywords_rejection_extended():
    """Unsupported keywords such as 'contains', 'not', 'patternProperties' must be rejected in validate_input."""
    unsupported = ["contains", "not", "patternProperties", "dependencies", "$id", "if", "then", "else"]
    for kw in unsupported:
        req = ProviderRequest(
            messages=[ProviderMessage(role="user", content="Test")],
            response_format="json",
            json_schema={"type": "object", kw: {}},
        )
        issue = req.validate_input()
        assert issue is not None, f"Expected keyword '{kw}' to be rejected"
        assert f"unsupported_schema_keyword:{kw}" in issue


def test_string_numeric_and_object_constraints():
    """Verify minLength, maxLength, pattern, multipleOf, minProperties, maxProperties, and error sanitization."""
    schema = {
        "type": "object",
        "minProperties": 1,
        "maxProperties": 3,
        "properties": {
            "code": {"type": "string", "minLength": 3, "maxLength": 5, "pattern": r"^[A-Z]+$"},
            "step_count": {"type": "integer", "multipleOf": 5},
        },
    }

    # Valid
    ok, err = validate_structured_output('{"code": "ABC", "step_count": 15}', schema)
    assert ok is True

    # minLength violation (does not leak private string)
    private_str = "ab"
    ok, err = validate_structured_output(f'{{"code": "{private_str}"}}', schema)
    assert ok is False
    assert "less than minLength" in err
    assert private_str not in err

    # maxLength violation
    ok, err = validate_structured_output('{"code": "TOOLONGSTRING"}', schema)
    assert ok is False
    assert "greater than maxLength" in err
    assert "TOOLONGSTRING" not in err

    # pattern violation
    ok, err = validate_structured_output('{"code": "abc"}', schema)
    assert ok is False
    assert "does not match required pattern" in err
    assert "abc" not in err

    # multipleOf violation
    ok, err = validate_structured_output('{"code": "ABC", "step_count": 12}', schema)
    assert ok is False
    assert "not a multiple of 5" in err
    assert "12" not in err

    # maxProperties violation (does not leak property names)
    extra_obj = '{"code": "ABC", "step_count": 10, "extra1": 1, "extra2": 2}'
    ok, err = validate_structured_output(extra_obj, schema)
    assert ok is False
    assert "more properties than maxProperties" in err
    assert "extra1" not in err
    assert "extra2" not in err


@pytest.mark.parametrize("finish_reason", [
    "BLOCKLIST",
    "SPII",
    "RECITATION",
    "PROHIBITED_CONTENT",
    "MALICIOUS",
])
def test_primary_terminal_finish_reasons_never_fallback(mock_cloudflare, mock_nvidia, sample_config, sample_request, finish_reason):
    """Nvidia finish reasons (BLOCKLIST, SPII, etc.) are terminal refusals that never trigger OpenAI fallback."""
    mock_cloudflare.execute.side_effect = ProviderSafetyRefusalError(f"Nvidia candidate blocked by content filter: {finish_reason}")
    engine = UnifiedProviderEngine(
        config=sample_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    response = engine.generate(sample_request)
    assert response.outcome == "safety_refusal"
    assert response.is_success is False
    assert finish_reason in (response.error_detail or "")
    mock_nvidia.execute.assert_not_called()


def test_overall_deadline_expiration_after_completion_returns_timeout(mock_cloudflare, mock_nvidia, sample_config, sample_request, monkeypatch):
    """If provider completes after overall deadline expired, engine must report timeout, never success."""
    import dataclasses
    import time

    def slow_execute(*args, **kwargs):
        time.sleep(0.05)
        return "Delayed response text", TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20)

    mock_cloudflare.execute.side_effect = slow_execute
    cfg = dataclasses.replace(sample_config, timeout_seconds=0.01)  # Very short deadline

    engine = UnifiedProviderEngine(
        config=cfg,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    response = engine.generate(sample_request)
    assert response.outcome == "timeout"
    assert response.is_success is False
    assert response.content == ""
    # OpenAI fallback must not be called after deadline expired
    mock_nvidia.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Cloudflare Workers AI Primary Hierarchy Tests
# ---------------------------------------------------------------------------


def test_cloudflare_primary_success(mock_cloudflare, mock_nvidia, cloudflare_config, sample_request):
    """When Cloudflare Workers AI succeeds, Nvidia fallback is never invoked."""
    mock_cloudflare.execute.return_value = (
        "Action step 1 from Cloudflare.",
        TokenUsage(prompt_tokens=15, completion_tokens=12, total_tokens=27, neurons=1.5),
    )

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "cloudflare"
    assert resp.model == "@cf/ibm-granite/granite-4.0-h-micro"
    assert resp.outcome == "success"
    assert resp.content == "Action step 1 from Cloudflare."
    assert resp.usage.total_tokens == 27
    assert resp.estimated_cost_usd is not None
    assert resp.estimated_cost_usd > 0
    assert len(resp.attempts) == 1
    assert resp.attempts[0].status == "success"

    mock_cloudflare.execute.assert_called_once()
    mock_nvidia.execute.assert_not_called()


def test_cloudflare_transient_error_retries_and_succeeds(mock_cloudflare, mock_nvidia, cloudflare_config, sample_request):
    """Cloudflare transient 503 triggers a bounded retry, succeeding on 2nd attempt."""
    mock_cloudflare.execute.side_effect = [
        ProviderTransientError("Cloudflare service temporarily unavailable", http_code=503),
        ("Recovered action step from Cloudflare.", TokenUsage(prompt_tokens=15, completion_tokens=10, total_tokens=25)),
    ]

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "cloudflare"
    assert resp.outcome == "success"
    assert resp.content == "Recovered action step from Cloudflare."
    assert len(resp.attempts) == 2
    assert resp.attempts[0].status == "transient_error"
    assert resp.attempts[1].status == "success"
    assert mock_cloudflare.execute.call_count == 2
    mock_nvidia.execute.assert_not_called()


def test_cloudflare_rate_limit_falls_back_to_nvidia_immediately(mock_cloudflare, mock_nvidia, cloudflare_config, sample_request):
    """Cloudflare 429 triggers immediate fallback to Nvidia without retrying Cloudflare."""
    mock_cloudflare.execute.side_effect = ProviderRateLimitError("Cloudflare rate limited", http_code=429)
    mock_nvidia.execute.return_value = (
        "Fallback response from Nvidia.",
        TokenUsage(prompt_tokens=20, completion_tokens=15, total_tokens=35),
    )

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "nvidia"
    assert resp.outcome == "fallback_success"
    assert resp.content == "Fallback response from Nvidia."
    assert len(resp.attempts) == 2
    assert resp.attempts[0].status == "rate_limited"
    assert resp.attempts[1].status == "success"

    mock_cloudflare.execute.assert_called_once()
    mock_nvidia.execute.assert_called_once()


def test_cloudflare_timeout_falls_back_to_nvidia(mock_cloudflare, mock_nvidia, cloudflare_config, sample_request):
    """Cloudflare timeout exhausts retries and then successfully falls back to Nvidia."""
    mock_cloudflare.execute.side_effect = ProviderTimeoutError("Cloudflare timed out", http_code=408)
    mock_nvidia.execute.return_value = (
        "Nvidia response after Cloudflare timeout.",
        TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
    )

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "nvidia"
    assert resp.outcome == "fallback_success"
    assert resp.content == "Nvidia response after Cloudflare timeout."
    # 1 initial + 1 retry on Cloudflare, then 1 on Nvidia
    assert mock_cloudflare.execute.call_count == 2
    mock_nvidia.execute.assert_called_once()


def test_cloudflare_missing_key_falls_back_to_nvidia(mock_cloudflare, mock_nvidia, sample_request):
    """When Cloudflare credentials are unset, engine skips to Nvidia fallback."""
    cfg = UnifiedProviderConfig(
        primary_provider="cloudflare",
        fallback_provider="nvidia",
        cloudflare_enabled=True,
        nvidia_enabled=True,
        fallback_enabled=True,
        cloudflare_account_id="",  # unset
        cloudflare_api_token="",   # unset
        nvidia_api_key="mock-nvidia-key",
    )
    mock_nvidia.execute.return_value = ("Nvidia response", TokenUsage(5, 5, 10))

    engine = UnifiedProviderEngine(
        config=cfg,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "nvidia"
    assert resp.outcome == "fallback_success"
    assert resp.attempts[0].status == "missing_key"
    mock_cloudflare.execute.assert_not_called()
    mock_nvidia.execute.assert_called_once()


def test_cloudflare_client_error_forbids_fallback(mock_cloudflare, mock_nvidia, cloudflare_config, sample_request):
    """Cloudflare 400 Bad Request is a client error that strictly forbids fallback to Nvidia."""
    mock_cloudflare.execute.side_effect = ProviderClientError("Cloudflare 400 Bad Request", http_code=400)

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.outcome == "invalid_request"
    mock_cloudflare.execute.assert_called_once()
    mock_nvidia.execute.assert_not_called()


def test_cloudflare_safety_refusal_forbids_fallback(mock_cloudflare, mock_nvidia, cloudflare_config, sample_request):
    """Cloudflare safety refusal is terminal and strictly forbids fallback to Nvidia."""
    mock_cloudflare.execute.side_effect = ProviderSafetyRefusalError("Cloudflare blocked prompt due to content filter")

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.outcome == "safety_refusal"
    assert "content filter" in (resp.error_detail or "")
    mock_cloudflare.execute.assert_called_once()
    mock_nvidia.execute.assert_not_called()


def test_cloudflare_adapter_execute_direct():
    """Unit test CloudflareAIProviderAdapter.execute with mock HTTP response."""
    adapter = CloudflareAIProviderAdapter()

    fake_resp_body = json.dumps({
        "choices": [
            {
                "message": {"role": "assistant", "content": "Direct Cloudflare output"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        "success": True,
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.side_effect = [fake_resp_body, b""]
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    mock_client = MagicMock(return_value=mock_resp)
    adapter._http_client = mock_client

    cfg = UnifiedProviderConfig(
        cloudflare_account_id="test-account-123",
        cloudflare_api_token="test-token-456",
        cloudflare_model="@cf/ibm-granite/granite-4.0-h-micro",
    )
    req = ProviderRequest(messages=[ProviderMessage(role="user", content="Hello")])

    text, usage = adapter.execute(req, cfg, timeout=5.0)

    assert text == "Direct Cloudflare output"
    assert usage.total_tokens == 20
    assert usage.prompt_tokens == 12
    assert usage.completion_tokens == 8

    # Verify HTTP request details
    call_args = mock_client.call_args
    req_sent = call_args[0][0]
    assert "https://api.cloudflare.com/client/v4/accounts/test-account-123/ai/v1/chat/completions" in req_sent.full_url
    assert req_sent.get_header("Authorization") == "Bearer test-token-456"


# ---------------------------------------------------------------------------
# Phase 1 & 2 Failure Handling, Model Optimization & Diagnostics Tests
# ---------------------------------------------------------------------------


def test_cloudflare_http_401_invalid_token_forbids_fallback(mock_cloudflare, mock_nvidia, cloudflare_config, sample_request):
    """Cloudflare 401 Unauthorized (e.g. invalid API token) is a client error and must strictly forbid fallback to Nvidia."""
    mock_cloudflare.execute.side_effect = ProviderClientError("Cloudflare authentication failed: Invalid token", http_code=401)

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.outcome == "error"
    assert resp.attempts[0].status == "client_error"
    assert resp.attempts[0].http_code == 401
    mock_cloudflare.execute.assert_called_once()
    mock_nvidia.execute.assert_not_called()


def test_cloudflare_http_403_forbidden_forbids_fallback(mock_cloudflare, mock_nvidia, cloudflare_config, sample_request):
    """Cloudflare 403 Forbidden is a client error that strictly forbids fallback to Nvidia."""
    mock_cloudflare.execute.side_effect = ProviderClientError("Cloudflare forbidden (HTTP 403)", http_code=403)

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.outcome == "error"
    assert resp.attempts[0].status == "client_error"
    assert resp.attempts[0].http_code == 403
    mock_cloudflare.execute.assert_called_once()
    mock_nvidia.execute.assert_not_called()


@pytest.mark.parametrize("status_code", [500, 502, 503, 504])
def test_cloudflare_server_errors_retry_then_fallback_to_nvidia(mock_cloudflare, mock_nvidia, cloudflare_config, sample_request, status_code):
    """Cloudflare 5xx server errors retry boundedly and then fallback to Nvidia."""
    mock_cloudflare.execute.side_effect = ProviderTransientError(f"Cloudflare server error (HTTP {status_code})", http_code=status_code)
    mock_nvidia.execute.return_value = ("Nvidia recovered response", TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20))

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.outcome == "fallback_success"
    assert resp.provider == "nvidia"
    assert resp.content == "Nvidia recovered response"
    # Initial + 1 retry on Cloudflare = 2 calls
    assert mock_cloudflare.execute.call_count == 2
    mock_nvidia.execute.assert_called_once()


def test_cloudflare_network_connection_failure_retries_then_fallback(mock_cloudflare, mock_nvidia, cloudflare_config, sample_request):
    """Network connection reset / unreachable error retries boundedly on Cloudflare, then falls back to Nvidia."""
    mock_cloudflare.execute.side_effect = ProviderTransientError("Cloudflare connection reset or unreachable: ConnectionResetError")
    mock_nvidia.execute.return_value = ("Nvidia response after network drop", TokenUsage(5, 5, 10))

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.outcome == "fallback_success"
    assert resp.provider == "nvidia"
    assert mock_cloudflare.execute.call_count == 2
    mock_nvidia.execute.assert_called_once()


def test_cloudflare_empty_response_retries_then_falls_back(mock_cloudflare, mock_nvidia, cloudflare_config, sample_request):
    """Cloudflare empty response is a transient error that retries then falls back."""
    mock_cloudflare.execute.side_effect = ProviderEmptyResponseError("Cloudflare returned empty text response")
    mock_nvidia.execute.return_value = ("Nvidia valid response", TokenUsage(8, 8, 16))

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.outcome == "fallback_success"
    assert resp.provider == "nvidia"
    assert mock_cloudflare.execute.call_count == 2
    mock_nvidia.execute.assert_called_once()


def test_cloudflare_malformed_json_retries_then_falls_back(mock_cloudflare, mock_nvidia, cloudflare_config, sample_request):
    """Cloudflare invalid non-JSON body is a transient error that retries then falls back."""
    mock_cloudflare.execute.side_effect = ProviderTransientError("Cloudflare returned invalid non-JSON HTTP response body")
    mock_nvidia.execute.return_value = ("Nvidia valid response", TokenUsage(8, 8, 16))

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.outcome == "fallback_success"
    assert resp.provider == "nvidia"
    assert mock_cloudflare.execute.call_count == 2
    mock_nvidia.execute.assert_called_once()


def test_cloudflare_schema_validation_failure_forbids_fallback(mock_cloudflare, mock_nvidia, cloudflare_config):
    """Structured output failing schema validation must strictly forbid fallback."""
    mock_cloudflare.execute.side_effect = ProviderSchemaValidationError("Cloudflare structured output failed schema validation")

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="Return JSON")],
        response_format="json",
        json_schema={"type": "object", "properties": {"k": {"type": "string"}}, "required": ["k"]},
    )
    resp = engine.generate(req)

    assert resp.is_success is False
    assert resp.outcome == "schema_validation_failed"
    mock_cloudflare.execute.assert_called_once()
    mock_nvidia.execute.assert_not_called()


def test_cloudflare_truncated_response_forbids_fallback(mock_cloudflare, mock_nvidia, cloudflare_config, sample_request):
    """Truncated response (e.g. maxOutputTokens reached) must strictly forbid fallback."""
    mock_cloudflare.execute.side_effect = ProviderTruncatedError("Cloudflare output truncated: model reached maxOutputTokens limit")

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.outcome == "truncated_response"
    mock_cloudflare.execute.assert_called_once()
    mock_nvidia.execute.assert_not_called()


def test_all_providers_unavailable_when_both_fail_transient(mock_cloudflare, mock_nvidia, cloudflare_config, sample_request):
    """When both Cloudflare and Nvidia fail with transient errors, engine truthfully reports provider_unavailable."""
    mock_cloudflare.execute.side_effect = ProviderTransientError("Cloudflare 503", http_code=503)
    mock_nvidia.execute.side_effect = ProviderTransientError("Nvidia 503", http_code=503)

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.outcome == "provider_unavailable"
    assert "unavailable" in resp.error_detail
    assert len(resp.attempts) >= 3


def test_cloudflare_explicit_alter_model_selection():
    """Setting use_alter_model=True on ProviderRequest uses CLOUDFLARE_AI_MODEL_ALTER."""
    adapter = CloudflareAIProviderAdapter()
    captured_payload = {}

    def fake_client(req, timeout=None):
        nonlocal captured_payload
        captured_payload = json.loads(req.data.decode("utf-8"))
        body = json.dumps({
            "choices": [{"message": {"role": "assistant", "content": "GLM answer"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30, "neurons": 0.5},
            "success": True,
        }).encode("utf-8")
        resp = MagicMock()
        resp.read.side_effect = [body, b""]
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    adapter._http_client = fake_client
    cfg = UnifiedProviderConfig(
        cloudflare_account_id="acc-123",
        cloudflare_api_token="tok-456",
        cloudflare_model="@cf/ibm-granite/granite-4.0-h-micro",
        cloudflare_alter_model="@cf/zai-org/glm-4.7-flash",
    )
    req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="test alter model")],
        use_alter_model=True,
    )
    text, usage = adapter.execute(req, cfg, timeout=5.0)
    assert text == "GLM answer"
    assert captured_payload.get("model") == "@cf/zai-org/glm-4.7-flash"
    assert usage.neurons == 0.5


def test_cloudflare_explicit_specific_model_selection():
    """Setting approved alter model on ProviderRequest uses the alter model; arbitrary unapproved models are rejected."""
    adapter = CloudflareAIProviderAdapter()
    captured_payload = {}

    def fake_client(req, timeout=None):
        nonlocal captured_payload
        captured_payload = json.loads(req.data.decode("utf-8"))
        body = json.dumps({
            "choices": [{"message": {"role": "assistant", "content": "Specific model answer"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 15, "completion_tokens": 25, "total_tokens": 40, "neurons": 1.2},
            "success": True,
        }).encode("utf-8")
        resp = MagicMock()
        resp.read.side_effect = [body, b""]
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    adapter._http_client = fake_client
    cfg = UnifiedProviderConfig(
        cloudflare_account_id="acc-123",
        cloudflare_api_token="tok-456",
        cloudflare_model="@cf/ibm-granite/granite-4.0-h-micro",
        cloudflare_alter_model="@cf/zai-org/glm-4.7-flash",
    )
    # Server-approved alter model selection
    req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="test specific model")],
        model="@cf/zai-org/glm-4.7-flash",
    )
    text, usage = adapter.execute(req, cfg, timeout=5.0)
    assert text == "Specific model answer"
    assert captured_payload.get("model") == "@cf/zai-org/glm-4.7-flash"
    assert usage.neurons == 1.2

    # Unauthorized arbitrary model override is safely rejected and falls back to server default
    req_unauth = ProviderRequest(
        messages=[ProviderMessage(role="user", content="test unauth model")],
        model="@cf/meta/llama-3.3-70b-instruct",
    )
    text2, _ = adapter.execute(req_unauth, cfg, timeout=5.0)
    assert text2 == "Specific model answer"
    assert captured_payload.get("model") == "@cf/ibm-granite/granite-4.0-h-micro"


def test_model_pricing_dataclass_and_cost_estimation_verified():
    """Verify ModelPricing indexing compatibility, neurons, and rate calculations."""
    pricing = ModelPricing(input_per_million=0.05, output_per_million=0.15, source="Cloudflare")
    # Verify tuple-like indexing compatibility
    assert pricing[0] == 0.05
    assert pricing[1] == 0.15
    with pytest.raises(IndexError):
        _ = pricing[2]

    # Verify estimate_cost_usd calculation for granite-4.0-h-micro via Neurons
    usage = TokenUsage(prompt_tokens=100_000, completion_tokens=100_000, total_tokens=200_000, neurons=1.5)
    cost = estimate_cost_usd("cloudflare", "@cf/ibm-granite/granite-4.0-h-micro", usage)
    # 1.5 neurons * $0.000011/neuron = 0.0000165 USD
    assert cost == pytest.approx(1.65e-5, rel=1e-4)

    # Cloudflare without neurons returns None (unverified flat token pricing)
    usage_no_neurons = TokenUsage(prompt_tokens=100_000, completion_tokens=100_000, total_tokens=200_000, neurons=None)
    assert estimate_cost_usd("cloudflare", "@cf/ibm-granite/granite-4.0-h-micro", usage_no_neurons) is None

    # Verify historical Gemini pricing
    cost_lite = estimate_cost_usd("gemini", "gemini-3.5-flash-lite", usage)
    # 0.1 * 0.30 + 0.1 * 2.50 = 0.03 + 0.25 = 0.28 USD
    assert cost_lite == pytest.approx(0.28, rel=1e-4)


def test_attempt_captures_token_usage_and_neurons(mock_cloudflare, mock_nvidia, cloudflare_config, sample_request):
    """Successful ProviderAttempt captures input_tokens, output_tokens, and neurons."""
    mock_cloudflare.execute.return_value = (
        "Output with neurons",
        TokenUsage(prompt_tokens=45, completion_tokens=55, total_tokens=100, neurons=0.85),
    )
    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert len(resp.attempts) == 1
    attempt = resp.attempts[0]
    assert attempt.input_tokens == 45
    assert attempt.output_tokens == 55
    assert attempt.neurons == 0.85
    assert resp.usage.neurons == 0.85
    att_dict = attempt.to_dict()
    assert att_dict["input_tokens"] == 45
    assert att_dict["output_tokens"] == 55
    assert att_dict["neurons"] == 0.85


def test_glm_selection_recorded_everywhere_consistently(mock_cloudflare, mock_nvidia, cloudflare_config):
    """FIX 2: Selecting the alter model records it consistently in request, attempt, and response."""
    mock_cloudflare.execute.return_value = (
        "Alter model generated analysis",
        TokenUsage(prompt_tokens=50, completion_tokens=30, total_tokens=80, neurons=1.4),
    )
    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="Analyze with alter model")],
        use_alter_model=True,
    )
    resp = engine.generate(req)

    assert resp.is_success is True
    assert resp.provider == "cloudflare"
    assert resp.model == cloudflare_config.cloudflare_alter_model
    assert len(resp.attempts) == 1
    attempt = resp.attempts[0]
    assert attempt.model == cloudflare_config.cloudflare_alter_model
    assert attempt.status == "success"
    assert attempt.neurons == 1.4
    assert resp.usage.neurons == 1.4
    # Estimated cost: 1.4 neurons * 0.000011 USD/neuron
    assert resp.estimated_cost_usd == pytest.approx(1.4 * 0.000011, rel=1e-4)


def test_nvidia_does_not_return_reasoning_as_a_final_answer(sample_config, sample_request):
    def transport(_request, *, timeout):
        return io.BytesIO(json.dumps({
            "choices": [{"finish_reason": "stop", "message": {"content": None, "reasoning_content": "internal"}}],
        }).encode())

    with pytest.raises(ProviderEmptyResponseError):
        NvidiaProviderAdapter(transport).execute(sample_request, sample_config, timeout=5)


def test_cloudflare_dict_message_content_and_string_errors():
    """Cloudflare adapter serializes dict content as JSON and formats plain-string errors."""
    adapter = CloudflareAIProviderAdapter()
    cfg = UnifiedProviderConfig(
        cloudflare_account_id="acc-123",
        cloudflare_api_token="tok-456",
        cloudflare_model="@cf/ibm-granite/granite-4.0-h-micro",
    )
    req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="Return JSON")],
        response_format="json",
        json_schema={"type": "object", "required": ["focus_kpi_key"], "properties": {"focus_kpi_key": {"type": "string"}}},
    )

    def _make_resp(payload_dict):
        body = json.dumps(payload_dict).encode("utf-8")
        resp = MagicMock()
        resp.read.side_effect = [body, b""]
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    # 1. message.content as dict -> json.dumps passes schema validation
    adapter._http_client = lambda _req, timeout=None: _make_resp({
        "choices": [{"message": {"role": "assistant", "content": {"focus_kpi_key": "Attendance"}}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20, "neurons": 0.4},
        "success": True,
    })
    text, usage = adapter.execute(req, cfg, timeout=5.0)
    assert json.loads(text) == {"focus_kpi_key": "Attendance"}
    assert usage.neurons == 0.4

    # 2. errors containing plain strings -> ProviderTransientError without AttributeError
    adapter._http_client = lambda _req, timeout=None: _make_resp({
        "success": False,
        "errors": ["Upstream worker overloaded", {"message": "Retry later"}],
    })
    with pytest.raises(ProviderTransientError, match="Upstream worker overloaded; Retry later"):
        adapter.execute(req, cfg, timeout=5.0)


def test_engine_catches_unexpected_adapter_exception_without_500(mock_cloudflare, mock_nvidia, cloudflare_config, sample_request):
    """Unexpected non-ProviderError exceptions from adapters degrade cleanly without raising."""
    mock_cloudflare.execute.side_effect = RuntimeError("unexpected JSON shape")
    mock_nvidia.execute.side_effect = KeyError("missing_field")

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        nvidia_adapter=mock_nvidia,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.outcome == "provider_unavailable"
    assert resp.provider == "none"
    assert len(resp.attempts) == 3  # primary initial + 1 retry + fallback
    assert any("Unexpected adapter error: RuntimeError" in (a.error_detail or "") for a in resp.attempts)
    assert any("Unexpected adapter error: KeyError" in (a.error_detail or "") for a in resp.attempts)


def test_nvidia_validates_nullable_structured_output_locally(sample_config):
    request = ProviderRequest(
        messages=[ProviderMessage(role="user", content="Return JSON")],
        response_format="json",
        json_schema={
            "type": "object",
            "properties": {"tool_name": {"type": ["string", "null"]}},
            "required": ["tool_name"],
            "additionalProperties": False,
        },
    )

    def adapter(content):
        body = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": content}}]}).encode()
        return NvidiaProviderAdapter(lambda _request, **_: io.BytesIO(body))

    text, _ = adapter('{"tool_name": null}').execute(request, sample_config, timeout=5)
    assert json.loads(text) == {"tool_name": None}
    with pytest.raises(ProviderSchemaValidationError):
        adapter('{"tool_name": 123}').execute(request, sample_config, timeout=5)


def test_retired_provider_settings_cannot_enable_gemini(monkeypatch):
    from services.ai import provider_config_store
    from services.ai.provider_engine import load_unified_provider_config

    monkeypatch.setenv("PMS_AI_PRIMARY_PROVIDER", "gemini")
    monkeypatch.setenv("PMS_AI_FALLBACK_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "retired-key")
    monkeypatch.setenv("NVIDIA_API_KEY", "primary-feedback-key")
    monkeypatch.setenv("NVIDIA_API_KEY_ALTER", "alternate-chat-key")
    provider_config_store.invalidate_provider_config()
    config = load_unified_provider_config()

    assert config.effective_primary_provider == "nvidia"
    assert config.effective_fallback_provider == "cloudflare"
    assert config.nvidia_api_key == "alternate-chat-key"
    assert UnifiedProviderEngine(config)._get_adapter("gemini") is None
    provider_config_store.invalidate_provider_config()


def test_nvidia_primary_failure_modes_and_fallback_attribution():
    """Phase 1 failure matrix: 401/malformed never fall back; 429/timeout/empty fall back truthfully."""
    import urllib.error

    cfg = UnifiedProviderConfig(
        primary_provider="nvidia",
        fallback_provider="cloudflare",
        nvidia_enabled=True,
        cloudflare_enabled=True,
        fallback_enabled=True,
        nvidia_api_key="AIzaFakeKey12345678901234567890",
        cloudflare_account_id="0" * 32,
        cloudflare_api_token="cfut_FakeToken12345678901234567890",
        nvidia_model="nvidia/test-alternate-model",
        cloudflare_model="@cf/ibm-granite/granite-4.0-h-micro",
        timeout_seconds=5.0,
        max_retries=0,
    )
    req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="Return JSON")],
        response_format="json",
        json_schema={"type": "object", "properties": {"response_type": {"type": "string"}}, "required": ["response_type"]},
        purpose="model_led_router",
    )
    cf_body = json.dumps(
        {
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"response_type": "tool_call"})}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "neurons": 0.1},
        }
    ).encode()
    cf_ok = lambda _req, timeout=5.0: io.BytesIO(cf_body)

    def http_err(code: int):
        def _fn(r, timeout=5.0):
            raise urllib.error.HTTPError(r.full_url, code, f"HTTP {code}", {}, io.BytesIO(b"{}"))
        return _fn

    # 1. Auth 401 -> no fallback
    eng_401 = UnifiedProviderEngine(config=cfg, nvidia_adapter=NvidiaProviderAdapter(http_err(401)), cloudflare_adapter=CloudflareAIProviderAdapter(cf_ok))
    r_401 = eng_401.generate(req)
    assert r_401.is_success is False
    assert r_401.provider == "none"
    assert [(a.provider, a.status, a.http_code) for a in r_401.attempts] == [("nvidia", "client_error", 401)]

    # 2. Rate limit 429 -> immediate fallback to cloudflare
    eng_429 = UnifiedProviderEngine(config=cfg, nvidia_adapter=NvidiaProviderAdapter(http_err(429)), cloudflare_adapter=CloudflareAIProviderAdapter(cf_ok))
    r_429 = eng_429.generate(req)
    assert r_429.is_success is True
    assert r_429.outcome == "fallback_success"
    assert r_429.provider == "cloudflare"
    assert [a.status for a in r_429.attempts] == ["rate_limited", "success"]

    # 3. Timeout -> fallback to cloudflare
    def raise_timeout(_r, timeout=5.0):
        raise TimeoutError("timed out")
    eng_to = UnifiedProviderEngine(config=cfg, nvidia_adapter=NvidiaProviderAdapter(raise_timeout), cloudflare_adapter=CloudflareAIProviderAdapter(cf_ok))
    r_to = eng_to.generate(req)
    assert r_to.is_success is True
    assert r_to.outcome == "fallback_success"
    assert [a.status for a in r_to.attempts] == ["timeout", "success"]

    # 4. Malformed JSON -> schema_validation_failed, no fallback
    bad_json = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": "NOT JSON"}}]}).encode()
    eng_bad = UnifiedProviderEngine(config=cfg, nvidia_adapter=NvidiaProviderAdapter(lambda _r, timeout=5.0: io.BytesIO(bad_json)), cloudflare_adapter=CloudflareAIProviderAdapter(cf_ok))
    r_bad = eng_bad.generate(req)
    assert r_bad.is_success is False
    assert r_bad.outcome == "schema_validation_failed"
    assert len(r_bad.attempts) == 1

    # 5. Empty response -> transient error -> fallback to cloudflare
    empty_resp = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": "   "}}]}).encode()
    eng_empty = UnifiedProviderEngine(config=cfg, nvidia_adapter=NvidiaProviderAdapter(lambda _r, timeout=5.0: io.BytesIO(empty_resp)), cloudflare_adapter=CloudflareAIProviderAdapter(cf_ok))
    r_empty = eng_empty.generate(req)
    assert r_empty.is_success is True
    assert r_empty.outcome == "fallback_success"
    assert [a.status for a in r_empty.attempts] == ["empty_response", "success"]


def test_cloudflare_thinking_env_override(sample_config, monkeypatch):
    request = ProviderRequest(
        messages=[ProviderMessage(role="user", content="x")], purpose="model_led_synthesis", response_format="json",
        max_tokens=None,
    )
    for mode, purpose, want in (("on", "model_led_synthesis", True), ("off", "model_led_router", False), ("auto", "model_led_router", True)):
        monkeypatch.setenv("PMS_AI_CF_THINKING", mode)
        request.purpose = purpose
        bodies = []

        def transport(http_request, *, timeout):
            bodies.append(json.loads(http_request.data))
            return io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}).encode())

        CloudflareAIProviderAdapter(transport).execute(request, sample_config, timeout=5, model="@cf/zai-org/glm-4.7-flash")
        assert bodies[0]["chat_template_kwargs"] == {"enable_thinking": want}
