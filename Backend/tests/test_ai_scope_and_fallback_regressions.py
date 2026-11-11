"""Call Center scope leaks and the chat fallback reason for an unreachable model."""

from __future__ import annotations

import io
import json
import urllib.error
from types import SimpleNamespace

import pytest

from models.ai_schemas import AiChatRequest, SessionFilterContext
from services.ai.catalog import ai_evidence_cache
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.router import HybridQueryRouter
from test_ai_workspace import _build_in_memory_db, _make_call_center_record, _patch_records

EGYPT_SUPPORT = (
    "Who is the lowest person in Egypt support for the latest published month, "
    "and what is their position?"
)


def test_egypt_support_ranks_support_positions_not_the_call_center_function():
    router = HybridQueryRouter(
        scope={"role": "Admin", "has_unrestricted_team_access": True},
        published_periods=["2026-09"],
    )
    result = router.resolve_and_validate(
        prompt=EGYPT_SUPPORT,
        session_state=SessionFilterContext(function="Call Center"),
        provider_override="deterministic",
    )
    assert result.plan.team == "Support Positions"
    assert result.plan.function == "Call Center"
    assert result.plan.intent == "ranking"
    assert result.plan.operation_kind_v2 == "ranking"
    assert result.plan.single_person is True
    assert result.outcome != "clarification"


def test_watching_alert_badge_uses_the_active_scope(monkeypatch):
    def fake_workspace(self, scope, **kwargs):
        return SimpleNamespace(
            comparison=SimpleNamespace(current=SimpleNamespace(month="September", year=2026)),
            team_summaries=[],
            priority_insights=[
                SimpleNamespace(
                    id="drop",
                    severity="warning",
                    title="Score dropped",
                    explanation="The gap widened.",
                    team=None,
                    detail=None,
                )
            ],
            risks=[SimpleNamespace(key="sip", count=2, label="SIP", explanation="Two people are flagged.")],
            executive_story=None,
        )

    monkeypatch.setattr("services.insights_service.InsightsService.generate_workspace", fake_workspace)
    db = _build_in_memory_db()
    orchestrator = PmsAiOrchestrator(db, {"role": "Admin", "has_unrestricted_team_access": True})

    pharmacy = orchestrator.build_watching_workspace(SessionFilterContext(function="Pharmacy"))
    pharmacy_text = " ".join(
        f"{alert.badge_text} {alert.prompt_to_ask}" for alert in pharmacy.alerts
    )
    assert "Pharmacy" in pharmacy_text
    assert "Call Center" not in pharmacy_text

    neutral = orchestrator.build_watching_workspace(SessionFilterContext())
    neutral_text = " ".join(
        f"{alert.badge_text} {alert.prompt_to_ask}" for alert in neutral.alerts
    )
    assert "this scope" in neutral_text
    assert "Call Center" not in neutral_text

    call_center = orchestrator.build_watching_workspace(SessionFilterContext(function="Call Center"))
    assert any(alert.badge_text == "Call Center" for alert in call_center.alerts)


def _admin_chat(monkeypatch, opener):
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://127.0.0.1:8080/v1")
    records = [_make_call_center_record("EMP001", "Alice Example", "Inbound", 85.0, 15, 30, 40, 80)]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    monkeypatch.setattr("services.ai.llm_client.urllib.request.build_opener", lambda *_: opener)
    with _build_in_memory_db() as db:
        return PmsAiOrchestrator(db, {"role": "Admin", "has_unrestricted_team_access": True}).run_chat_turn(
            AiChatRequest(
                prompt="What is the Inbound score in September 2026?",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            )
        )


def test_chat_reports_connection_refused_when_the_model_is_unreachable(monkeypatch):
    class Opener:
        def open(self, request, timeout):
            raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))

    response = _admin_chat(monkeypatch, Opener())
    assert response.provider_usage.fallback_outcome == "connection_refused"
    assert response.provider_usage.fallback_outcome not in {"none", "unavailable_or_invalid", "not_called"}
    assert response.outcome == "answer"


def test_chat_reports_timeout_when_model_synthesis_cannot_be_reached(monkeypatch):
    class Opener:
        def __init__(self):
            self.calls = 0

        def open(self, request, timeout):
            self.calls += 1
            if self.calls == 1:
                content = json.dumps(
                    {
                        "action": "call_tools",
                        "unknown_code": "none",
                        "tools": [{"tool": "get_team_score_summary", "team": "Inbound", "period": "2026-09"}],
                    }
                )
                return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())
            raise TimeoutError("model timed out")

    response = _admin_chat(monkeypatch, Opener())
    assert response.provider_usage.fallback_outcome == "timeout"
    assert response.outcome == "answer"


def test_chat_reports_invalid_response_when_model_synthesis_is_unusable(monkeypatch):
    """A synthesis draft the validator cannot use is a fallback, not success.

    The fallback whitelist used to propagate only transport reasons, so an
    unparsable synthesis draft still reported fallback_outcome "none" while
    the turn silently fell back to the rules headline.
    """

    class Opener:
        def __init__(self):
            self.calls = 0

        def open(self, request, timeout):
            self.calls += 1
            if self.calls == 1:
                content = json.dumps(
                    {
                        "action": "call_tools",
                        "unknown_code": "none",
                        "tools": [{"tool": "get_team_score_summary", "team": "Inbound", "period": "2026-09"}],
                    }
                )
            else:
                content = "this is not a grounded synthesis payload"
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())

    response = _admin_chat(monkeypatch, Opener())
    assert response.provider_usage.fallback_outcome == "invalid_response"
    assert response.provider_usage.fallback_outcome != "none"
    assert response.outcome == "answer"
