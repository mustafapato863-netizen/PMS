"""Phase 6 TDD tests for centralized prompt versions and model-led pilot guards."""

from __future__ import annotations

import json

import pytest

from ai_provider_fakes import failed_response, install_scripted_provider
from models.ai_schemas import SessionFilterContext
from services.ai import (
    contextual_assistant,
    local_evidence_synthesis,
    local_model_router,
    orchestrator,
    router,
)
from services.ai.entity_resolver import EmployeeHistoryCandidate
from services.ai.local_evidence_synthesis import OverallScoreFacts, extract_overall_score_facts
from services.ai.router import HybridQueryRouter


def test_active_prompt_versions_registry_and_module_exports():
    from services.ai.prompt_versions import (
        ACTIVE_PROMPT_VERSIONS,
        EXECUTIVE_VARIATION_PROMPT_VERSION,
        EXPLAIN_PREVIOUS_PROMPT_VERSION,
        INTENT_CLASSIFIER_PROMPT_VERSION,
        MODEL_LED_PLANNER_PROMPT_VERSION,
        MODEL_LED_SYNTHESIS_PROMPT_VERSION,
        NARROW_EVIDENCE_SYNTHESIS_PROMPT_VERSION,
    )

    expected = {
        "model_led_planner": MODEL_LED_PLANNER_PROMPT_VERSION,
        "model_led_synthesis": MODEL_LED_SYNTHESIS_PROMPT_VERSION,
        "intent_classifier": INTENT_CLASSIFIER_PROMPT_VERSION,
        "narrow_evidence_synthesis": NARROW_EVIDENCE_SYNTHESIS_PROMPT_VERSION,
        "executive_variation": EXECUTIVE_VARIATION_PROMPT_VERSION,
        "explain_previous": EXPLAIN_PREVIOUS_PROMPT_VERSION,
    }
    assert ACTIVE_PROMPT_VERSIONS == expected
    assert all(isinstance(v, str) and v.strip() for v in expected.values())

    assert orchestrator.MODEL_LED_SYNTHESIS_PROMPT_VERSION == MODEL_LED_SYNTHESIS_PROMPT_VERSION
    assert router.MODEL_LED_PLANNER_PROMPT_VERSION == MODEL_LED_PLANNER_PROMPT_VERSION
    assert local_model_router.INTENT_CLASSIFIER_PROMPT_VERSION == INTENT_CLASSIFIER_PROMPT_VERSION
    assert (
        local_evidence_synthesis.NARROW_EVIDENCE_SYNTHESIS_PROMPT_VERSION
        == NARROW_EVIDENCE_SYNTHESIS_PROMPT_VERSION
    )
    assert local_evidence_synthesis.EXECUTIVE_VARIATION_PROMPT_VERSION == EXECUTIVE_VARIATION_PROMPT_VERSION
    assert contextual_assistant.EXPLAIN_PREVIOUS_PROMPT_VERSION == EXPLAIN_PREVIOUS_PROMPT_VERSION


def test_extract_overall_score_facts_disabled_when_model_led_pilot_enabled(
    monkeypatch: pytest.MonkeyPatch,
):
    digests = [
        {
            "period": "September 2026",
            "scope": "Inbound",
            "branch": "All Branches",
            "average_score": 88.5,
            "total_records": 4,
        }
    ]
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "false")
    facts = extract_overall_score_facts("What is Inbound overall score in September 2026?", digests)
    assert facts == OverallScoreFacts("September 2026", "Inbound", "All Branches", 88.5)

    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    assert extract_overall_score_facts("What is Inbound overall score in September 2026?", digests) is None


def test_admin_model_led_fallback_skips_redundant_suggest_intent(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_INTENT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "true")
    install_scripted_provider(monkeypatch, failed_response("provider_unavailable"), provider="cloudflare")

    suggest_calls: list[str] = []

    def _unexpected_suggest_intent(question: str, context=None):
        suggest_calls.append(question)
        raise AssertionError("suggest_intent must not be called on Admin model-led fallback")

    monkeypatch.setattr(router, "suggest_intent", _unexpected_suggest_intent)

    res = HybridQueryRouter(
        scope={"role": "Admin", "has_unrestricted_team_access": True},
        published_periods={"2026-09"},
    ).resolve_and_validate(
        prompt="What is Inbound overall performance?",
        session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        provider_override="auto",
    )
    assert suggest_calls == []
    assert res.outcome == "answer"
    assert res.route_used != "local_model_router"


def test_admin_model_led_conversational_guard_uses_dynamic_year_and_plan_period(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(
        monkeypatch,
        [json.dumps({"response_type": "conversational", "direct_response": "Sure, happy to help."})],
        provider="cloudflare",
    )
    candidates = [
        EmployeeHistoryCandidate(
            employee_id="EMP101",
            employee_name="Sara Mahmoud",
            team="Inbound",
            function="Call Center",
            position="Call Center Agent",
        )
    ]
    res = HybridQueryRouter(
        scope={"role": "Admin", "has_unrestricted_team_access": True},
        published_periods={"2025-08", "2025-09"},
        employee_candidates=candidates,
    ).resolve_and_validate(
        prompt="What was Sara Mahmoud's score in August?",
        session_state=SessionFilterContext(function="Call Center", team="Inbound", year=2025),
        provider_override="auto",
    )
    assert res.route_used == "model_led_pilot"
    assert res.plan.model_led_tool_call is not None
    assert res.plan.model_led_tool_call["tool_name"] == "read_employee_metric"
    assert res.plan.model_led_tool_call["tool_arguments"]["period"] == "2025-08"
