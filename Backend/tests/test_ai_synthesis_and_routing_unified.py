"""Tests verifying synthesis and routing integration with UnifiedProviderEngine.

Verifies:
1. synthesize_branch_bookings uses Gemini when available and formats verified counts.
2. synthesize_overall_score falls back to OpenAI when Gemini fails (quota/timeout).
3. Rejection of ungrounded or hallucinated answers, falling back to deterministic text.
4. suggest_intent with UnifiedProviderEngine for allowed intents.
5. Graceful fallback to deterministic outcomes when no model is configured.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from services.ai.local_evidence_synthesis import (
    synthesize_branch_bookings,
    synthesize_overall_score,
)
from services.ai.local_model_router import suggest_intent
from services.ai.provider_engine import (
    ProviderAttempt,
    ProviderRequest,
    ProviderResponse,
    TokenUsage,
    UnifiedProviderEngine,
    reset_unified_provider_engine,
)


def _branch_evidence():
    return [
        {
            "period": "September 2026",
            "scope": "Inbound",
            "requested_branches": ["Dubai", "Sharjah"],
            "branch_comparison": [
                {"branch": "Dubai", "bookings": 180},
                {"branch": "Sharjah", "bookings": 70},
                {"branch": "Ajman", "bookings": 40},
            ],
        }
    ]


def _score_evidence():
    return [
        {
            "period": "September 2026",
            "scope": "Inbound",
            "branch": "All Branches",
            "average_score": 85.0,
            "total_records": 10,
        }
    ]


def test_unified_synthesis_branch_bookings_gemini_success(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_UNIFIED_SYNTHESIS", "true")
    reset_unified_provider_engine()

    mock_engine = MagicMock(spec=UnifiedProviderEngine)
    mock_engine.generate.return_value = ProviderResponse(
        content=json.dumps({"answer": "Inbound bookings in September 2026: Dubai 180, Sharjah 70."}),
        provider="gemini",
        model="gemini-2.5-flash",
        latency_ms=120.0,
        usage=TokenUsage(prompt_tokens=40, completion_tokens=15, total_tokens=55),
        attempts=[ProviderAttempt(provider="gemini", model="gemini-2.5-flash", status="success", latency_ms=120.0)],
        outcome="success",
    )

    monkeypatch.setattr(
        "services.ai.local_evidence_synthesis.get_unified_provider_engine",
        lambda: mock_engine,
    )

    res = synthesize_branch_bookings("Compare Dubai and Sharjah Inbound bookings", _branch_evidence())
    assert res is not None
    assert res.provider_used == "gemini"
    assert res.model_used == "gemini-2.5-flash"
    assert res.headline == "Inbound bookings in September 2026: Dubai 180, Sharjah 70."
    assert res.metrics.fallback_outcome == "none"
    assert res.metrics.provider_calls == 1


def test_unified_synthesis_overall_score_openai_fallback_success(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_UNIFIED_SYNTHESIS", "true")
    reset_unified_provider_engine()

    mock_engine = MagicMock(spec=UnifiedProviderEngine)
    mock_engine.generate.return_value = ProviderResponse(
        content=json.dumps({"answer": "Inbound scored 85.0% in September 2026."}),
        provider="openai",
        model="gpt-4o-mini",
        latency_ms=180.0,
        usage=TokenUsage(prompt_tokens=35, completion_tokens=12, total_tokens=47),
        attempts=[
            ProviderAttempt(provider="gemini", model="gemini-2.5-flash", status="rate_limit", latency_ms=80.0),
            ProviderAttempt(provider="openai", model="gpt-4o-mini", status="success", latency_ms=100.0),
        ],
        outcome="success",
    )

    monkeypatch.setattr(
        "services.ai.local_evidence_synthesis.get_unified_provider_engine",
        lambda: mock_engine,
    )

    res = synthesize_overall_score("What is Inbound score in September 2026?", _score_evidence())
    assert res is not None
    assert res.provider_used == "openai"
    assert res.model_used == "gpt-4o-mini"
    assert res.headline == "Inbound scored 85.0% in September 2026."
    assert res.metrics.fallback_outcome == "none"
    assert res.metrics.provider_calls == 1


def test_unified_synthesis_rejects_hallucinated_facts_and_falls_back(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_UNIFIED_SYNTHESIS", "true")
    reset_unified_provider_engine()

    # Model fabricates numbers and Ajman branch
    mock_engine = MagicMock(spec=UnifiedProviderEngine)
    mock_engine.generate.return_value = ProviderResponse(
        content=json.dumps({"answer": "Inbound bookings in September 2026: Dubai 999, Ajman 500."}),
        provider="gemini",
        model="gemini-2.5-flash",
        latency_ms=110.0,
        outcome="success",
    )

    monkeypatch.setattr(
        "services.ai.local_evidence_synthesis.get_unified_provider_engine",
        lambda: mock_engine,
    )

    res = synthesize_branch_bookings("Compare Dubai and Sharjah Inbound bookings", _branch_evidence())
    assert res is not None
    assert res.provider_used == "deterministic"
    assert "Dubai: 180" in res.headline and "Sharjah: 70" in res.headline
    assert res.metrics.fallback_outcome == "invalid_or_unverified_response"


def test_unified_synthesis_no_model_configured_falls_back_cleanly(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_UNIFIED_SYNTHESIS", "true")
    reset_unified_provider_engine()

    mock_engine = MagicMock(spec=UnifiedProviderEngine)
    mock_engine.generate.return_value = ProviderResponse(
        content="",
        provider="none",
        model="none",
        latency_ms=5.0,
        attempts=[
            ProviderAttempt(provider="gemini", model="gemini-2.5-flash", status="missing_key"),
            ProviderAttempt(provider="openai", model="gpt-4o-mini", status="missing_key"),
        ],
        outcome="no_model_configured",
    )

    monkeypatch.setattr(
        "services.ai.local_evidence_synthesis.get_unified_provider_engine",
        lambda: mock_engine,
    )

    res = synthesize_overall_score("What is Inbound score in September 2026?", _score_evidence())
    assert res is not None
    assert res.provider_used == "deterministic"
    assert "85.0%" in res.headline
    assert res.metrics.fallback_outcome == "no_model_configured"


def test_unified_suggest_intent_gemini_success(monkeypatch):
    monkeypatch.setenv("PMS_AI_LLM_INTENT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_UNIFIED_ROUTER", "true")
    reset_unified_provider_engine()

    mock_engine = MagicMock(spec=UnifiedProviderEngine)
    mock_engine.generate.return_value = ProviderResponse(
        content=json.dumps({"intent": "trend"}),
        provider="gemini",
        model="gemini-2.5-flash",
        latency_ms=85.0,
        outcome="success",
    )

    monkeypatch.setattr(
        "services.ai.local_model_router.get_unified_provider_engine",
        lambda: mock_engine,
    )

    res = suggest_intent("How has Inbound performance changed over the last 3 months?")
    assert res.intent == "trend"
    assert res.reason == "ok"
    assert res.model == "gemini-2.5-flash"


def test_unified_suggest_intent_rejects_invalid_intent_value(monkeypatch):
    monkeypatch.setenv("PMS_AI_LLM_INTENT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_UNIFIED_ROUTER", "true")
    reset_unified_provider_engine()

    mock_engine = MagicMock(spec=UnifiedProviderEngine)
    mock_engine.generate.return_value = ProviderResponse(
        content=json.dumps({"intent": "execute_unauthorized_sql"}),
        provider="gemini",
        model="gemini-2.5-flash",
        latency_ms=75.0,
        outcome="success",
    )

    monkeypatch.setattr(
        "services.ai.local_model_router.get_unified_provider_engine",
        lambda: mock_engine,
    )

    res = suggest_intent("Show me something")
    assert res.intent is None
    assert res.reason == "invalid_intent"
