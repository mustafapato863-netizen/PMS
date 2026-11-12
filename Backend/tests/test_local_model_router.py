from __future__ import annotations

import os

import pytest

from ai_provider_fakes import failed_response, install_scripted_provider

from models.ai_schemas import SessionFilterContext
from services.ai.local_model_router import LocalIntentResult, suggest_intent
from services.ai.router import HybridQueryRouter


def test_disabled_does_not_call_model(monkeypatch):
    monkeypatch.delenv("PMS_AI_LOCAL_ROUTER_ENABLED", raising=False)
    assert suggest_intent("How has booking evolved?").reason == "disabled"


def test_provider_failure_returns_reason_and_never_a_legacy_provider(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "true")
    install_scripted_provider(monkeypatch, failed_response("provider_unavailable"))
    result = suggest_intent("How has booking evolved?")
    assert result.intent is None
    assert result.reason == "provider_unavailable"
    assert result.provider in ("cloudflare", "gemini")


def test_validates_model_response_and_sends_no_pms_data(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "true")
    captured = install_scripted_provider(monkeypatch, '{"intent":"trend"}')
    result = suggest_intent("How has booking evolved?")
    assert result.intent == "trend"
    assert result.provider == "cloudflare"
    assert len(captured[0]["messages"]) == 2
    assert captured[0]["messages"][1]["content"] == "How has booking evolved?"


def test_gemini_fallback_provider_is_reported(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "true")
    install_scripted_provider(monkeypatch, '{"intent":"ranking"}', provider="gemini")
    result = suggest_intent("Who is the best agent?")
    assert (result.intent, result.provider) == ("ranking", "gemini")


def test_rejects_model_generated_extra_fields(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "true")
    install_scripted_provider(monkeypatch, '{"intent":"trend","score":99}')
    assert suggest_intent("How has booking evolved?").reason == "invalid_response"


def test_model_only_refines_resolved_metric_and_cannot_bypass_access(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    calls = []

    def suggest(question):
        calls.append(question)
        return LocalIntentResult("trend", 1.0, "ok")

    monkeypatch.setattr("services.ai.router.suggest_intent", suggest)
    ctx = SessionFilterContext(function="Call Center", month="September", year=2026)
    admin = HybridQueryRouter(scope={"role": "Admin", "has_unrestricted_team_access": True}, published_periods=["2026-08", "2026-09"])
    answer = admin.resolve_and_validate(prompt="How has Inbound booking evolved?", session_state=ctx)
    assert answer.route_used == "local_model_router"
    assert answer.plan.intent == "trend"
    assert answer.plan.metric == "inbound:booking_rate"
    assert calls == ["How has Inbound booking evolved?"]

    restricted = HybridQueryRouter(scope={"role": "Manager", "has_unrestricted_team_access": False, "accessible_teams": ["Outbound"], "accessible_functions": ["Call Center"]}, published_periods=["2026-09"])
    result = restricted.resolve_and_validate(prompt="How has Inbound booking evolved?", session_state=ctx)
    assert result.outcome == "restricted_access"
    assert len(calls) == 1


def test_future_year_is_not_replaced_by_current_session_year(monkeypatch):
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    router = HybridQueryRouter(
        scope={"role": "Admin", "has_unrestricted_team_access": True},
        published_periods=["2026-09"],
    )
    result = router.resolve_and_validate(
        prompt="What was Inbound performance in December 2030?",
        session_state=SessionFilterContext(function="Call Center", month="September", year=2026),
    )
    assert result.outcome == "unavailable_data"
    assert result.plan.periods == ["2030-12"]


def test_followup_keeps_the_employee_returned_by_ranking(monkeypatch):
    from test_ai_workspace import _build_in_memory_db, _make_call_center_record, _patch_records
    from models.ai_schemas import AiChatRequest
    from services.ai.catalog import ai_evidence_cache
    from services.ai.orchestrator import PmsAiOrchestrator

    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    rows = [
        _make_call_center_record("EMP001", "Alice Example", "Inbound", 70, 10, 30, 40, 60, month="August"),
        _make_call_center_record("EMP001", "Alice Example", "Inbound", 80, 10, 30, 40, 60, month="September"),
        _make_call_center_record("EMP002", "Bob Example", "Inbound", 95, 10, 30, 40, 60, month="August"),
        _make_call_center_record("EMP002", "Bob Example", "Inbound", 90, 10, 30, 40, 60, month="September"),
    ]
    _patch_records(monkeypatch, rows)
    ai_evidence_cache.clear()
    with _build_in_memory_db() as db:
        assistant = PmsAiOrchestrator(db, {"role": "Admin", "has_unrestricted_team_access": True})
        state = SessionFilterContext(function="Call Center", month="September", year=2026)
        first = assistant.run_chat_turn(AiChatRequest(prompt="Who is the lowest person in Inbound?", session_state=state))
        assert "Alice" in first.headline
        prior = first.resolved_session_state.last_confirmed_query
        assert prior is not None and prior.last_subject_employee_id == "EMP001"
        followup = assistant.run_chat_turn(AiChatRequest(
            prompt="Was September her best month?",
            session_state=SessionFilterContext(function="Call Center", month="September", year=2026, last_confirmed_query=prior),
        ))
        assert "Alice" in followup.headline
        assert "Bob" not in followup.headline


def test_model_can_resolve_an_overall_score_trend_without_dropping_compound_questions(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    calls = []

    def suggest(question):
        calls.append(question)
        return LocalIntentResult("trend", 1.0, "ok")

    monkeypatch.setattr("services.ai.router.suggest_intent", suggest)
    router = HybridQueryRouter(
        scope={"role": "Admin", "has_unrestricted_team_access": True},
        published_periods=["2026-08", "2026-09"],
    )
    ctx = SessionFilterContext(function="Call Center", month="September", year=2026)
    result = router.resolve_and_validate(prompt="How has Inbound performance evolved?", session_state=ctx)
    assert result.route_used == "local_model_router"
    assert result.plan.intent == "trend"
    assert result.plan.metric is None  # overall score, not a model-invented KPI

    router.resolve_and_validate(prompt="How has Inbound performance evolved and who is the best?", session_state=ctx)
    assert calls == ["How has Inbound performance evolved?"]


@pytest.mark.skipif(os.environ.get("PMS_AI_RUN_LIVE_MODEL_TESTS") != "true", reason="requires local Qwen server")
def test_live_model_routes_score_trend_without_choosing_scope(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    router = HybridQueryRouter(
        scope={"role": "Admin", "has_unrestricted_team_access": True},
        published_periods=["2026-08", "2026-09"],
    )
    result = router.resolve_and_validate(
        prompt="How has Inbound performance evolved?",
        session_state=SessionFilterContext(function="Call Center", month="September", year=2026),
    )
    assert result.outcome == "answer"
    assert result.route_used == "local_model_router"
    assert result.plan.intent == "trend"
    assert result.plan.team == "Inbound"
    assert result.plan.metric is None


@pytest.mark.skipif(os.environ.get("PMS_AI_RUN_LIVE_MODEL_TESTS") != "true", reason="requires local Qwen server")
def test_live_model_score_trend_uses_pms_test_records(monkeypatch):
    from test_ai_workspace import _build_in_memory_db, _make_call_center_record, _patch_records
    from models.ai_schemas import AiChatRequest
    from services.ai.catalog import ai_evidence_cache
    from services.ai.orchestrator import PmsAiOrchestrator

    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    rows = [
        _make_call_center_record("EMP001", "Example Person", "Inbound", 80, 10, 30, 40, 60, month="August"),
        _make_call_center_record("EMP001", "Example Person", "Inbound", 90, 10, 30, 40, 60, month="September"),
    ]
    _patch_records(monkeypatch, rows)
    ai_evidence_cache.clear()
    with _build_in_memory_db() as db:
        result = PmsAiOrchestrator(db, {"role": "Admin", "has_unrestricted_team_access": True}).run_chat_turn(
            AiChatRequest(prompt="How has Inbound performance evolved?", session_state=SessionFilterContext(function="Call Center", month="September", year=2026))
        )
    assert result.outcome == "answer"
    assert result.validated_plan_v2 is not None
    assert result.validated_plan_v2.resolution_source == "local_model_router"
    assert result.tool_calls
    assert result.provider_usage.route_used == "local_model_router"
    assert "90" in (result.headline + " ".join(result.narrative_bullets))


def test_end_to_end_trend_uses_pms_records_not_model_values(monkeypatch):
    from test_ai_workspace import _build_in_memory_db, _make_call_center_record, _patch_records
    from models.ai_schemas import AiChatRequest
    from services.ai.catalog import ai_evidence_cache
    from services.ai.orchestrator import PmsAiOrchestrator

    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    monkeypatch.setattr("services.ai.router.suggest_intent", lambda _: LocalIntentResult("trend", 1.0, "ok"))
    rows = [
        _make_call_center_record("EMP001", "Example Person", "Inbound", 80, 10, 30, 40, 60, month="August"),
        _make_call_center_record("EMP001", "Example Person", "Inbound", 90, 10, 30, 40, 60, month="September"),
    ]
    _patch_records(monkeypatch, rows)
    ai_evidence_cache.clear()
    with _build_in_memory_db() as db:
        result = PmsAiOrchestrator(db, {"role": "Admin", "has_unrestricted_team_access": True}).run_chat_turn(
            AiChatRequest(prompt="How has Inbound booking evolved?", session_state=SessionFilterContext(function="Call Center", month="September", year=2026))
        )
    assert result.outcome == "answer"
    assert result.validated_plan_v2 is not None
    assert result.validated_plan_v2.resolution_source == "local_model_router"
    assert any(call.tool_name for call in result.tool_calls)
    assert "booking" in result.headline.casefold()
