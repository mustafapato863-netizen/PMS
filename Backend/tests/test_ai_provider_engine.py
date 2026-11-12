"""Tests for Unified PMS AI Provider Engine (Phase 1).

Covers:
- Gemini success as primary provider (OpenAI never called).
- Gemini transient failure retry and eventual success.
- Gemini rate limit (HTTP 429) immediate fallback to OpenAI without retry.
- Gemini timeout fallback to OpenAI.
- Gemini disabled or missing key fallback to OpenAI.
- Both providers failing returning clean provider-neutral unavailable response.
- Both providers disabled or unconfigured.
- Fallback disabled preventing OpenAI calls.
- Strict fallback boundaries:
  * Gemini 400/401/403 Client Errors MUST NOT trigger fallback to OpenAI.
  * Gemini safety refusals (finishReason="SAFETY" or prompt block) MUST NOT trigger fallback.
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
from unittest.mock import MagicMock

import pytest

from services.ai.provider_engine import (
    CloudflareAIProviderAdapter,
    GeminiProviderAdapter,
    OpenAIProviderAdapter,
    ProviderAttempt,
    ProviderClientError,
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
def mock_gemini():
    return MagicMock(spec=GeminiProviderAdapter)


@pytest.fixture
def mock_openai():
    return MagicMock(spec=OpenAIProviderAdapter)


@pytest.fixture
def mock_cloudflare():
    return MagicMock(spec=CloudflareAIProviderAdapter)


@pytest.fixture
def cloudflare_config():
    return UnifiedProviderConfig(
        primary_provider="cloudflare",
        fallback_provider="gemini",
        cloudflare_enabled=True,
        gemini_enabled=True,
        openai_enabled=False,
        fallback_enabled=True,
        cloudflare_account_id="mock-cf-account",
        cloudflare_api_token="mock-cf-token",
        cloudflare_model="@cf/ibm-granite/granite-4.0-h-micro",
        gemini_model="gemini-2.5-flash",
        timeout_seconds=5.0,
        max_retries=1,
        gemini_api_key="mock-gemini-key",
    )


@pytest.fixture
def sample_config():
    return UnifiedProviderConfig(
        gemini_enabled=True,
        openai_enabled=True,
        fallback_enabled=True,
        gemini_model="gemini-2.5-flash",
        openai_model="gpt-4o-mini",
        timeout_seconds=5.0,
        max_retries=1,
        gemini_api_key="mock-gemini-key",
        openai_api_key="mock-openai-key",
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


# ---------------------------------------------------------------------------
# Core Happy Path & Hierarchy Tests
# ---------------------------------------------------------------------------


def test_gemini_primary_success(mock_gemini, mock_openai, sample_config, sample_request):
    """When Gemini succeeds, it returns immediately and OpenAI is never invoked."""
    mock_gemini.execute.return_value = (
        "Action step 1 from Gemini.",
        TokenUsage(prompt_tokens=10, completion_tokens=8, total_tokens=18),
    )

    engine = UnifiedProviderEngine(
        config=sample_config,
        gemini_adapter=mock_gemini,
        openai_adapter=mock_openai,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "gemini"
    assert resp.model == "gemini-2.5-flash"
    assert resp.outcome == "success"
    assert resp.content == "Action step 1 from Gemini."
    assert resp.usage.total_tokens == 18
    assert resp.estimated_cost_usd is not None
    assert resp.estimated_cost_usd > 0
    assert len(resp.attempts) == 1
    assert resp.attempts[0].status == "success"

    # OpenAI must never be called when primary succeeds
    mock_gemini.execute.assert_called_once()
    mock_openai.execute.assert_not_called()


def test_gemini_transient_error_retries_and_succeeds(mock_gemini, mock_openai, sample_config, sample_request):
    """Gemini transient error (e.g. 503) triggers a bounded retry, succeeding on 2nd attempt."""
    mock_gemini.execute.side_effect = [
        ProviderTransientError("Service temporarily unavailable", http_code=503),
        ("Recovered action step from Gemini.", TokenUsage(prompt_tokens=12, completion_tokens=10, total_tokens=22)),
    ]

    engine = UnifiedProviderEngine(
        config=sample_config,
        gemini_adapter=mock_gemini,
        openai_adapter=mock_openai,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "gemini"
    assert resp.outcome == "success"
    assert resp.content == "Recovered action step from Gemini."
    assert len(resp.attempts) == 2
    assert resp.attempts[0].status == "transient_error"
    assert resp.attempts[0].http_code == 503
    assert resp.attempts[1].status == "success"
    assert resp.attempts[1].retry_count == 1

    assert mock_gemini.execute.call_count == 2
    mock_openai.execute.assert_not_called()


def test_gemini_rate_limit_falls_back_to_openai_immediately(mock_gemini, mock_openai, sample_config, sample_request):
    """Gemini HTTP 429 rate limit or quota exhaustion immediately falls back to OpenAI without retrying Gemini."""
    mock_gemini.execute.side_effect = ProviderRateLimitError("Quota exceeded", http_code=429)
    mock_openai.execute.return_value = (
        "Action step from OpenAI fallback.",
        TokenUsage(prompt_tokens=15, completion_tokens=12, total_tokens=27),
    )

    engine = UnifiedProviderEngine(
        config=sample_config,
        gemini_adapter=mock_gemini,
        openai_adapter=mock_openai,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "openai"
    assert resp.model == "gpt-4o-mini"
    assert resp.outcome == "fallback_success"
    assert resp.content == "Action step from OpenAI fallback."
    assert resp.usage.total_tokens == 27
    assert len(resp.attempts) == 2
    assert resp.attempts[0].status == "rate_limited"
    assert resp.attempts[0].provider == "gemini"
    assert resp.attempts[1].status == "success"
    assert resp.attempts[1].provider == "openai"

    # Gemini must only be called once (no pointless retries on 429 quota exhaustion)
    assert mock_gemini.execute.call_count == 1
    mock_openai.execute.assert_called_once()


def test_gemini_timeout_falls_back_to_openai(mock_gemini, mock_openai, sample_config, sample_request):
    """Gemini timeout after max retries falls back cleanly to OpenAI."""
    mock_gemini.execute.side_effect = ProviderTimeoutError("Gemini timed out after 5.0s")
    mock_openai.execute.return_value = (
        "Action step from OpenAI after timeout.",
        TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
    )

    engine = UnifiedProviderEngine(
        config=sample_config,
        gemini_adapter=mock_gemini,
        openai_adapter=mock_openai,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "openai"
    assert resp.outcome == "fallback_success"
    assert resp.content == "Action step from OpenAI after timeout."
    # 1 initial + 1 retry = 2 Gemini attempts, followed by 1 OpenAI attempt
    assert len(resp.attempts) == 3
    assert resp.attempts[0].status == "timeout"
    assert resp.attempts[1].status == "timeout"
    assert resp.attempts[2].status == "success"

    assert mock_gemini.execute.call_count == 2
    mock_openai.execute.assert_called_once()


def test_gemini_disabled_falls_back_to_openai(mock_gemini, mock_openai, sample_request):
    """When Gemini is disabled by config, it falls back to OpenAI without calling Gemini."""
    cfg = UnifiedProviderConfig(
        gemini_enabled=False,
        openai_enabled=True,
        fallback_enabled=True,
        gemini_api_key="mock-key",
        openai_api_key="mock-key",
    )
    mock_openai.execute.return_value = ("OpenAI response", TokenUsage(5, 5, 10))

    engine = UnifiedProviderEngine(config=cfg, gemini_adapter=mock_gemini, openai_adapter=mock_openai)
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "openai"
    assert resp.outcome == "fallback_success"
    assert resp.attempts[0].status == "disabled"
    assert resp.attempts[1].status == "success"

    mock_gemini.execute.assert_not_called()
    mock_openai.execute.assert_called_once()


def test_gemini_missing_key_falls_back_to_openai(mock_gemini, mock_openai, sample_request):
    """When Gemini key is empty, it records missing_key and falls back to OpenAI."""
    cfg = UnifiedProviderConfig(
        gemini_enabled=True,
        openai_enabled=True,
        fallback_enabled=True,
        gemini_api_key="",  # Unset
        openai_api_key="mock-openai-key",
    )
    mock_openai.execute.return_value = ("OpenAI response", TokenUsage(5, 5, 10))

    engine = UnifiedProviderEngine(config=cfg, gemini_adapter=mock_gemini, openai_adapter=mock_openai)
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "openai"
    assert resp.outcome == "fallback_success"
    assert resp.attempts[0].status == "missing_key"
    assert resp.attempts[1].status == "success"

    mock_gemini.execute.assert_not_called()
    mock_openai.execute.assert_called_once()


def test_both_providers_fail_returns_clear_provider_unavailable(mock_gemini, mock_openai, sample_config, sample_request):
    """When both primary and fallback fail, returns a provider-neutral unavailable response."""
    mock_gemini.execute.side_effect = ProviderTransientError("Gemini 500 error", http_code=500)
    mock_openai.execute.side_effect = ProviderRateLimitError("OpenAI 429 quota error", http_code=429)

    engine = UnifiedProviderEngine(config=sample_config, gemini_adapter=mock_gemini, openai_adapter=mock_openai)
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.provider == "none"
    assert resp.model == "none"
    assert resp.content == ""
    assert resp.outcome == "provider_unavailable"
    assert "All AI providers are currently unavailable" in (resp.error_detail or "")
    assert len(resp.attempts) == 3  # 2 Gemini + 1 OpenAI


def test_both_providers_disabled_returns_provider_unavailable(mock_gemini, mock_openai, sample_request):
    """When all providers are disabled, returns clean unavailable response with zero network calls."""
    cfg = UnifiedProviderConfig(
        gemini_enabled=False,
        openai_enabled=False,
        fallback_enabled=True,
    )
    engine = UnifiedProviderEngine(config=cfg, gemini_adapter=mock_gemini, openai_adapter=mock_openai)
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.outcome == "provider_unavailable"
    assert resp.content == ""
    mock_gemini.execute.assert_not_called()
    mock_openai.execute.assert_not_called()


def test_fallback_disabled_does_not_call_openai(mock_gemini, mock_openai, sample_request):
    """When fallback_enabled=False, primary failure stops immediately and never calls OpenAI."""
    cfg = UnifiedProviderConfig(
        gemini_enabled=True,
        openai_enabled=True,
        fallback_enabled=False,  # Fallback disabled
        gemini_api_key="mock-key",
        openai_api_key="mock-key",
        max_retries=0,
    )
    mock_gemini.execute.side_effect = ProviderTransientError("Gemini down")

    engine = UnifiedProviderEngine(config=cfg, gemini_adapter=mock_gemini, openai_adapter=mock_openai)
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.outcome == "provider_unavailable"
    mock_gemini.execute.assert_called_once()
    mock_openai.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Strict Boundary & Fallback Prohibition Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("http_code", [400, 401, 403])
def test_gemini_client_error_does_not_fallback_to_openai(http_code, mock_gemini, mock_openai, sample_config, sample_request):
    """HTTP 400, 401, 403 on Gemini are client errors and MUST NOT trigger fallback to OpenAI."""
    mock_gemini.execute.side_effect = ProviderClientError(f"Client error {http_code}", http_code=http_code)

    engine = UnifiedProviderEngine(config=sample_config, gemini_adapter=mock_gemini, openai_adapter=mock_openai)
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.provider == "none"
    assert resp.outcome in ("invalid_request", "error")
    assert resp.attempts[0].status == "client_error"
    assert resp.attempts[0].http_code == http_code

    # CRITICAL: OpenAI fallback must NOT be called for client errors
    mock_openai.execute.assert_not_called()
    assert len(resp.attempts) == 1


def test_gemini_safety_refusal_does_not_fallback_to_openai(mock_gemini, mock_openai, sample_config, sample_request):
    """Gemini safety refusals MUST NOT trigger fallback to OpenAI to prevent safety filter circumvention."""
    mock_gemini.execute.side_effect = ProviderSafetyRefusalError("Content blocked by Gemini safety policy")

    engine = UnifiedProviderEngine(config=sample_config, gemini_adapter=mock_gemini, openai_adapter=mock_openai)
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.provider == "none"
    assert resp.outcome == "safety_refusal"
    assert "Content blocked" in (resp.error_detail or "")
    assert resp.attempts[0].status == "safety_refusal"

    # CRITICAL: OpenAI fallback must NOT be called for safety blocks
    mock_openai.execute.assert_not_called()
    assert len(resp.attempts) == 1


def test_empty_request_rejected_without_calling_providers(mock_gemini, mock_openai, sample_config):
    """Empty request fails input validation immediately without invoking any model."""
    empty_req = ProviderRequest(messages=[], system_instruction=None)
    engine = UnifiedProviderEngine(config=sample_config, gemini_adapter=mock_gemini, openai_adapter=mock_openai)
    resp = engine.generate(empty_req)

    assert resp.is_success is False
    assert resp.outcome == "invalid_request"
    assert "empty_request" in (resp.error_detail or "")
    mock_gemini.execute.assert_not_called()
    mock_openai.execute.assert_not_called()


def test_excessive_prompt_length_rejected_without_calling_providers(mock_gemini, mock_openai, sample_config):
    """Request exceeding 120,000 characters is rejected without calling any provider."""
    huge_req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="x" * 125_000)],
    )
    engine = UnifiedProviderEngine(config=sample_config, gemini_adapter=mock_gemini, openai_adapter=mock_openai)
    resp = engine.generate(huge_req)

    assert resp.is_success is False
    assert resp.outcome == "invalid_request"
    assert "prompt_exceeds_maximum_length" in (resp.error_detail or "")
    mock_gemini.execute.assert_not_called()
    mock_openai.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Deadline & Timeout Tests
# ---------------------------------------------------------------------------


def test_overall_deadline_exhaustion_prevents_subsequent_attempts(mock_gemini, mock_openai, sample_config):
    """If timeout_seconds is exceeded, engine halts and does not initiate further retries or fallback."""
    # Set a very tight request timeout (0.001 seconds)
    req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="Test")],
        timeout_seconds=0.0001,
    )

    def slow_gemini(*args, **kwargs):
        import time
        time.sleep(0.005)
        raise ProviderTimeoutError("Gemini timed out")

    mock_gemini.execute.side_effect = slow_gemini

    engine = UnifiedProviderEngine(config=sample_config, gemini_adapter=mock_gemini, openai_adapter=mock_openai)
    resp = engine.generate(req)

    assert resp.is_success is False
    assert resp.outcome == "timeout"
    # OpenAI must NOT have been called because overall deadline expired
    mock_openai.execute.assert_not_called()


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


def test_gemini_schema_validation_failure_is_handled(mock_gemini, mock_openai, sample_config):
    """When Gemini returns invalid JSON for a structured request, schema error is terminal and MUST NOT fall back to OpenAI."""
    mock_gemini.execute.side_effect = ProviderSchemaValidationError("Gemini JSON output validation failed: missing key")

    req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="Give JSON")],
        response_format="json",
        json_schema={"type": "object", "required": ["valid"]},
    )

    engine = UnifiedProviderEngine(config=sample_config, gemini_adapter=mock_gemini, openai_adapter=mock_openai)
    resp = engine.generate(req)

    assert resp.is_success is False
    assert resp.outcome == "schema_validation_failed"
    assert "missing key" in resp.error_detail
    mock_openai.execute.assert_not_called()


def test_openai_schema_validation_failure_never_reports_success(mock_gemini, mock_openai, sample_config):
    """When OpenAI fallback also fails schema validation, response is marked unavailable/failed."""
    mock_gemini.execute.side_effect = ProviderRateLimitError("Quota exceeded", http_code=429)
    mock_openai.execute.side_effect = ProviderSchemaValidationError("OpenAI JSON output validation failed: invalid format")

    req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="Give JSON")],
        response_format="json",
        json_schema={"type": "object", "required": ["valid"]},
    )

    engine = UnifiedProviderEngine(config=sample_config, gemini_adapter=mock_gemini, openai_adapter=mock_openai)
    resp = engine.generate(req)

    assert resp.is_success is False
    assert resp.outcome == "provider_unavailable"
    assert resp.content == ""


def test_truncated_response_never_reports_success(mock_gemini, mock_openai, sample_config, sample_request):
    """When response is truncated (max tokens reached), fallback is forbidden and error is reported."""
    mock_gemini.execute.side_effect = ProviderTruncatedError("Gemini candidate truncated due to max output tokens")

    engine = UnifiedProviderEngine(config=sample_config, gemini_adapter=mock_gemini, openai_adapter=mock_openai)
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.outcome == "truncated_response"
    assert resp.content == ""
    mock_openai.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Privacy & Secret Redaction Tests
# ---------------------------------------------------------------------------


def test_secret_redaction_in_logs_and_error_details(mock_gemini, mock_openai, sample_config, sample_request, caplog):
    """API keys in exceptions and error details must be strictly redacted."""
    raw_secret_gemini = "AIzaSyD-mock1234567890abcdef"
    raw_secret_openai = "sk-proj-mock1234567890abcdef"

    mock_gemini.execute.side_effect = ProviderTransientError(f"Failed calling key={raw_secret_gemini} connection refused")
    mock_openai.execute.side_effect = ProviderRateLimitError(f"Key {raw_secret_openai} exhausted quota")

    with caplog.at_level(logging.WARNING):
        engine = UnifiedProviderEngine(config=sample_config, gemini_adapter=mock_gemini, openai_adapter=mock_openai)
        resp = engine.generate(sample_request)

    # Neither raw key must appear anywhere in the response error_detail
    assert raw_secret_gemini not in (resp.error_detail or "")
    assert raw_secret_openai not in (resp.error_detail or "")

    # Neither raw key must appear anywhere in logs
    assert raw_secret_gemini not in caplog.text
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

    classified = _parse_http_error(http_exc, "Gemini")
    assert isinstance(classified, ProviderClientError)
    assert classified.http_code == 400
    # The classified exception message MUST NOT contain sensitive details from the error body
    assert "SSN" not in str(classified)
    assert "123-45-6789" not in str(classified)
    assert "Ahmed" not in str(classified)
    assert "Gemini client error (HTTP 400)" in str(classified)


# ---------------------------------------------------------------------------
# Truthful Observability & Pricing Tests
# ---------------------------------------------------------------------------


def test_cost_estimation_supported_models():
    """Cost estimation correctly applies token pricing for Gemini and OpenAI."""
    gemini_usage = TokenUsage(prompt_tokens=1_000_000, completion_tokens=1_000_000, total_tokens=2_000_000)
    cost_gemini = estimate_cost_usd("gemini", "gemini-2.5-flash", gemini_usage)
    # 0.15 + 0.60 = 0.75 USD
    assert cost_gemini == pytest.approx(0.75, rel=1e-4)

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
    assert estimate_cost_usd("gemini", "unknown-model-xyz", usage) is None
    assert estimate_cost_usd("openai", "custom-fine-tuned", usage) is None

    # Zero tokens returns None
    zero_usage = TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    assert estimate_cost_usd("gemini", "gemini-2.5-flash", zero_usage) is None


# ---------------------------------------------------------------------------
# Adapter Formatting Tests
# ---------------------------------------------------------------------------


def test_gemini_adapter_payload_formatting():
    """Gemini adapter properly formats contents, systemInstruction, and JSON mode."""
    captured_request = {}

    class MockResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps({
                "candidates": [{"content": {"parts": [{"text": "{\"status\": \"ok\"}"}]}}],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 6, "totalTokenCount": 11},
            }).encode("utf-8")

    def mock_urlopen(req, timeout):
        captured_request["url"] = req.full_url
        captured_request["headers"] = dict(req.headers)
        captured_request["body"] = json.loads(req.data.decode("utf-8"))
        captured_request["timeout"] = timeout
        return MockResp()

    adapter = GeminiProviderAdapter(http_client=mock_urlopen)
    cfg = UnifiedProviderConfig(gemini_api_key="test-gemini-key", gemini_model="gemini-2.5-flash")
    req = ProviderRequest(
        messages=[ProviderMessage(role="user", content="Return JSON")],
        system_instruction="Strict system instructions",
        response_format="json",
        json_schema={"type": "object", "properties": {"status": {"type": "string"}}},
        timeout_seconds=4.5,
    )

    text, usage = adapter.execute(req, cfg, timeout=req.timeout_seconds)
    assert text == '{"status": "ok"}'
    assert usage.total_tokens == 11

    headers_lower = {k.lower(): v for k, v in captured_request["headers"].items()}
    assert "x-goog-api-key" in headers_lower
    assert headers_lower["x-goog-api-key"] == "test-gemini-key"
    assert captured_request["body"]["systemInstruction"]["parts"][0]["text"] == "Strict system instructions"
    assert captured_request["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert captured_request["body"]["generationConfig"]["responseSchema"] == req.json_schema
    assert captured_request["timeout"] == 4.5


def test_openai_adapter_payload_formatting():
    """OpenAI adapter properly formats messages, model, and JSON object mode."""
    captured_request = {}

    class MockResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": "{\"result\": \"ok\"}"}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            }).encode("utf-8")

    def mock_urlopen(req, timeout):
        captured_request["url"] = req.full_url
        captured_request["headers"] = dict(req.headers)
        captured_request["body"] = json.loads(req.data.decode("utf-8"))
        captured_request["timeout"] = timeout
        return MockResp()

    adapter = OpenAIProviderAdapter(http_client=mock_urlopen)
    cfg = UnifiedProviderConfig(openai_api_key="test-openai-key", openai_model="gpt-4o-mini")
    req = ProviderRequest(
        messages=[
            ProviderMessage(role="system", content="System text"),
            ProviderMessage(role="user", content="User text"),
        ],
        response_format="json",
        timeout_seconds=6.0,
    )

    text, usage = adapter.execute(req, cfg, timeout=req.timeout_seconds)
    assert text == "{\"result\": \"ok\"}"
    assert usage.total_tokens == 12

    assert "Authorization" in captured_request["headers"]
    assert captured_request["headers"]["Authorization"] == "Bearer test-openai-key"
    assert captured_request["body"]["model"] == "gpt-4o-mini"
    assert captured_request["body"]["response_format"] == {"type": "json_object"}
    assert captured_request["body"]["messages"][0] == {"role": "system", "content": "System text"}
    assert captured_request["body"]["messages"][1] == {"role": "user", "content": "User text"}
    assert captured_request["timeout"] == 6.0


# ---------------------------------------------------------------------------
# Regression Tests: HTTP Error Classification & Schema Validation Rigor
# ---------------------------------------------------------------------------


def test_parse_http_error_does_not_turn_400_with_rate_into_rate_limit(mock_gemini, mock_openai, sample_config):
    """HTTP 400 containing substrings like 'completion_rate' must never be classified as rate limit."""
    import io
    import urllib.error
    from services.ai.provider_engine import ProviderClientError, _parse_http_error

    # Simulate HTTP 400 Bad Request where error message contains the word "rate"
    err_body = b'{"error": "Invalid completion_rate parameter: value out of bounds"}'
    err = urllib.error.HTTPError(
        url="https://generativelanguage.googleapis.com",
        code=400,
        msg="Bad Request",
        hdrs={},
        fp=io.BytesIO(err_body),
    )

    parsed = _parse_http_error(err, "Gemini")
    assert isinstance(parsed, ProviderClientError)
    assert not isinstance(parsed, ProviderRateLimitError)
    assert parsed.http_code == 400

    # In engine: must report invalid_request and strictly forbid fallback
    mock_gemini.execute.side_effect = parsed
    engine = UnifiedProviderEngine(config=sample_config, gemini_adapter=mock_gemini, openai_adapter=mock_openai)
    req = ProviderRequest(messages=[ProviderMessage(role="user", content="Test")])
    resp = engine.generate(req)

    assert resp.is_success is False
    assert resp.outcome == "invalid_request"
    mock_openai.execute.assert_not_called()


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

    # 3. Nullable and union types
    nullable_schema = {
        "type": "object",
        "properties": {
            "note": {"type": ["string", "null"]},
            "comment": {"type": "string", "nullable": True},
        },
    }
    ok, err = validate_structured_output('{"note": null, "comment": null}', nullable_schema)
    assert ok is True
    ok, err = validate_structured_output('{"note": "valid note", "comment": "valid comment"}', nullable_schema)
    assert ok is True

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
    err = _parse_http_error(exc, "Gemini")
    assert isinstance(err, ProviderClientError)
    assert not isinstance(err, ProviderRateLimitError)
    assert err.http_code == 404


def test_safety_refusal_outcome_preserved(mock_gemini, mock_openai, sample_config, sample_request):
    """Safety refusal from provider must be preserved in outcome, never masked as provider_unavailable."""
    mock_gemini.execute.side_effect = ProviderSafetyRefusalError("Content blocked by safety policy")
    engine = UnifiedProviderEngine(
        config=sample_config,
        gemini_adapter=mock_gemini,
        openai_adapter=mock_openai,
    )
    response = engine.generate(sample_request)
    assert response.outcome == "safety_refusal"
    assert response.is_success is False
    # OpenAI must NOT have been called to bypass safety
    mock_openai.execute.assert_not_called()


def test_cost_estimation_incomplete_data_returns_none():
    """estimate_cost_usd returns None for incomplete usage, negative tokens, or unknown models."""
    # Unknown model
    assert estimate_cost_usd("gemini", "gemini-unknown-xyz", TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)) is None
    # None usage
    assert estimate_cost_usd("gemini", "gemini-2.5-flash", None) is None
    # Negative tokens
    assert estimate_cost_usd("gemini", "gemini-2.5-flash", TokenUsage(prompt_tokens=-10, completion_tokens=50, total_tokens=40)) is None
    # Incomplete breakdown (prompt=0, completion=0, but total > 0)
    assert estimate_cost_usd("gemini", "gemini-2.5-flash", TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=100)) is None


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
def test_gemini_terminal_finish_reasons_never_fallback(mock_gemini, mock_openai, sample_config, sample_request, finish_reason):
    """Gemini finish reasons (BLOCKLIST, SPII, etc.) are terminal refusals that never trigger OpenAI fallback."""
    mock_gemini.execute.side_effect = ProviderSafetyRefusalError(f"Gemini candidate blocked by content filter: {finish_reason}")
    engine = UnifiedProviderEngine(
        config=sample_config,
        gemini_adapter=mock_gemini,
        openai_adapter=mock_openai,
    )
    response = engine.generate(sample_request)
    assert response.outcome == "safety_refusal"
    assert response.is_success is False
    assert finish_reason in (response.error_detail or "")
    mock_openai.execute.assert_not_called()


def test_overall_deadline_expiration_after_completion_returns_timeout(mock_gemini, mock_openai, sample_config, sample_request, monkeypatch):
    """If provider completes after overall deadline expired, engine must report timeout, never success."""
    import dataclasses
    import time

    def slow_execute(*args, **kwargs):
        time.sleep(0.05)
        return "Delayed response text", TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20)

    mock_gemini.execute.side_effect = slow_execute
    cfg = dataclasses.replace(sample_config, timeout_seconds=0.01)  # Very short deadline

    engine = UnifiedProviderEngine(
        config=cfg,
        gemini_adapter=mock_gemini,
        openai_adapter=mock_openai,
    )
    response = engine.generate(sample_request)
    assert response.outcome == "timeout"
    assert response.is_success is False
    assert response.content == ""
    # OpenAI fallback must not be called after deadline expired
    mock_openai.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Cloudflare Workers AI Primary Hierarchy Tests
# ---------------------------------------------------------------------------


def test_cloudflare_primary_success(mock_cloudflare, mock_gemini, cloudflare_config, sample_request):
    """When Cloudflare Workers AI succeeds, Gemini fallback is never invoked."""
    mock_cloudflare.execute.return_value = (
        "Action step 1 from Cloudflare.",
        TokenUsage(prompt_tokens=15, completion_tokens=12, total_tokens=27),
    )

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        gemini_adapter=mock_gemini,
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
    mock_gemini.execute.assert_not_called()


def test_cloudflare_transient_error_retries_and_succeeds(mock_cloudflare, mock_gemini, cloudflare_config, sample_request):
    """Cloudflare transient 503 triggers a bounded retry, succeeding on 2nd attempt."""
    mock_cloudflare.execute.side_effect = [
        ProviderTransientError("Cloudflare service temporarily unavailable", http_code=503),
        ("Recovered action step from Cloudflare.", TokenUsage(prompt_tokens=15, completion_tokens=10, total_tokens=25)),
    ]

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        gemini_adapter=mock_gemini,
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
    mock_gemini.execute.assert_not_called()


def test_cloudflare_rate_limit_falls_back_to_gemini_immediately(mock_cloudflare, mock_gemini, cloudflare_config, sample_request):
    """Cloudflare 429 triggers immediate fallback to Gemini without retrying Cloudflare."""
    mock_cloudflare.execute.side_effect = ProviderRateLimitError("Cloudflare rate limited", http_code=429)
    mock_gemini.execute.return_value = (
        "Fallback response from Gemini.",
        TokenUsage(prompt_tokens=20, completion_tokens=15, total_tokens=35),
    )

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        gemini_adapter=mock_gemini,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "gemini"
    assert resp.outcome == "fallback_success"
    assert resp.content == "Fallback response from Gemini."
    assert len(resp.attempts) == 2
    assert resp.attempts[0].status == "rate_limited"
    assert resp.attempts[1].status == "success"

    mock_cloudflare.execute.assert_called_once()
    mock_gemini.execute.assert_called_once()


def test_cloudflare_timeout_falls_back_to_gemini(mock_cloudflare, mock_gemini, cloudflare_config, sample_request):
    """Cloudflare timeout exhausts retries and then successfully falls back to Gemini."""
    mock_cloudflare.execute.side_effect = ProviderTimeoutError("Cloudflare timed out", http_code=408)
    mock_gemini.execute.return_value = (
        "Gemini response after Cloudflare timeout.",
        TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
    )

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        gemini_adapter=mock_gemini,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "gemini"
    assert resp.outcome == "fallback_success"
    assert resp.content == "Gemini response after Cloudflare timeout."
    # 1 initial + 1 retry on Cloudflare, then 1 on Gemini
    assert mock_cloudflare.execute.call_count == 2
    mock_gemini.execute.assert_called_once()


def test_cloudflare_missing_key_falls_back_to_gemini(mock_cloudflare, mock_gemini, sample_request):
    """When Cloudflare credentials are unset, engine skips to Gemini fallback."""
    cfg = UnifiedProviderConfig(
        primary_provider="cloudflare",
        fallback_provider="gemini",
        cloudflare_enabled=True,
        gemini_enabled=True,
        fallback_enabled=True,
        cloudflare_account_id="",  # unset
        cloudflare_api_token="",   # unset
        gemini_api_key="mock-gemini-key",
    )
    mock_gemini.execute.return_value = ("Gemini response", TokenUsage(5, 5, 10))

    engine = UnifiedProviderEngine(
        config=cfg,
        cloudflare_adapter=mock_cloudflare,
        gemini_adapter=mock_gemini,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is True
    assert resp.provider == "gemini"
    assert resp.outcome == "fallback_success"
    assert resp.attempts[0].status == "missing_key"
    mock_cloudflare.execute.assert_not_called()
    mock_gemini.execute.assert_called_once()


def test_cloudflare_client_error_forbids_fallback(mock_cloudflare, mock_gemini, cloudflare_config, sample_request):
    """Cloudflare 400 Bad Request is a client error that strictly forbids fallback to Gemini."""
    mock_cloudflare.execute.side_effect = ProviderClientError("Cloudflare 400 Bad Request", http_code=400)

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        gemini_adapter=mock_gemini,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.outcome == "invalid_request"
    mock_cloudflare.execute.assert_called_once()
    mock_gemini.execute.assert_not_called()


def test_cloudflare_safety_refusal_forbids_fallback(mock_cloudflare, mock_gemini, cloudflare_config, sample_request):
    """Cloudflare safety refusal is terminal and strictly forbids fallback to Gemini."""
    mock_cloudflare.execute.side_effect = ProviderSafetyRefusalError("Cloudflare blocked prompt due to content filter")

    engine = UnifiedProviderEngine(
        config=cloudflare_config,
        cloudflare_adapter=mock_cloudflare,
        gemini_adapter=mock_gemini,
    )
    resp = engine.generate(sample_request)

    assert resp.is_success is False
    assert resp.outcome == "safety_refusal"
    assert "content filter" in (resp.error_detail or "")
    mock_cloudflare.execute.assert_called_once()
    mock_gemini.execute.assert_not_called()


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


