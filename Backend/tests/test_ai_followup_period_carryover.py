"""Follow-up turns keep the team and the period of the previous turn.

Shapes come from multi-turn probes of the live Ask AI: "and last month?", "the month
before", "how about <team> in the same month?", and a bare "and <month>?".
"""
from __future__ import annotations

import pytest

from models.ai_schemas import AiChatRequest, SessionFilterContext
from services.ai.catalog import ai_evidence_cache
from services.ai.orchestrator import PmsAiOrchestrator
from tests.test_ai_flexible_scenarios import _in_memory_db, _multi_department_records, _patch_records


def _two_turns(monkeypatch, first: str, second: str):
    _patch_records(monkeypatch, _multi_department_records())
    ai_evidence_cache.clear()
    db = _in_memory_db()
    try:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "followup-1", "has_unrestricted_team_access": True})
        r1 = orch.run_chat_turn(AiChatRequest(prompt=first, session_state=SessionFilterContext(), provider_override="deterministic"))
        r2 = orch.run_chat_turn(
            AiChatRequest(
                prompt=second,
                conversation_id=r1.conversation_id,
                context_version=r1.context_version,
                session_state=r1.resolved_session_state,
                history=[{"role": "user", "content": first}, {"role": "assistant", "content": r1.headline}],
                provider_override="deterministic",
            )
        )
        return r1, r2
    finally:
        db.close()


def _text(resp) -> str:
    return (resp.headline + " " + " ".join(resp.narrative_bullets or [])).casefold()


@pytest.mark.parametrize("follow_up", ["and last month?", "what about the month before?", "and the previous month?"])
def test_relative_month_follow_up_steps_back_from_the_previous_turn(monkeypatch, follow_up):
    r1, r2 = _two_turns(monkeypatch, "how did Marketing do in October 2026", follow_up)
    text = _text(r2)
    assert "marketing" in text, r2.headline
    assert "september" in text, r2.headline


@pytest.mark.parametrize("follow_up", ["how about Finance in the same month?", "and for Finance?", "same question for Finance"])
def test_new_team_follow_up_keeps_the_previous_month(monkeypatch, follow_up):
    r1, r2 = _two_turns(monkeypatch, "how did Marketing do in September 2026", follow_up)
    text = _text(r2)
    assert "finance" in text, r2.headline
    assert "september" in text and "october" not in text, r2.headline


@pytest.mark.parametrize("follow_up", ["and August?", "what about August?"])
def test_bare_month_follow_up_keeps_the_previous_team(monkeypatch, follow_up):
    r1, r2 = _two_turns(monkeypatch, "how did Marketing do in September 2026", follow_up)
    text = _text(r2)
    assert "marketing" in text, r2.headline
    assert "august" in text, r2.headline


def test_clarification_wording_drops_the_follow_up_lead_in():
    from services.ai.router import _strip_followup_lead_in

    assert _strip_followup_lead_in("and January?") == "January"
    assert _strip_followup_lead_in("What about March 2026?") == "March 2026"
    assert _strip_followup_lead_in("show me March") == "show me March"


def test_step_back_uses_the_latest_period_when_the_previous_turn_covered_two():
    from services.ai.router import _step_back_periods

    assert _step_back_periods("what about the month before?", ["2026-07", "2026-08"]) == ["2026-07"]
    assert _step_back_periods("and last month?", ["2026-01"]) == ["2025-12"]
    assert _step_back_periods("and for finance?", ["2026-03"]) == []


def test_unsupported_tool_copy_never_shows_internal_tool_names():
    from services.ai.orchestrator import _unsupported_tool_bullets, _unsupported_tool_headline

    for name in ("", "get_kpi_diagnosis_v9"):
        text = _unsupported_tool_headline(name) + " " + " ".join(_unsupported_tool_bullets(name))
        assert "tool" not in text.casefold().replace("lookup", "")
        assert name not in text or name == ""
        assert "authorized" not in text.casefold()


def test_country_clarification_keeps_the_month_the_user_asked_for():
    from tests.test_ai_phase2_reconciliation import _route

    dated = _route("What is the Coding score in March 2026?")
    assert dated.outcome == "clarification"
    assert dated.confirmed_context.periods == ["2026-03"]

    undated = _route("What is the Coding score?")
    assert undated.outcome == "clarification"
    assert undated.confirmed_context.periods == []


def test_model_planner_cannot_move_a_relative_month_follow_up(monkeypatch):
    """Live probe: the planner turned 'the month before' after August into June. The router decides the month."""
    import json

    from services.ai.provider_engine import ProviderResponse

    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")

    class WrongMonthPlanner:
        def generate(self, req):
            return ProviderResponse(
                content=json.dumps({
                    "response_type": "tool_call",
                    "tool_name": "get_kpi_diagnosis",
                    "tool_arguments": {"team": "Marketing", "metric_id": "overall_score", "period": "2026-06"},
                }),
                provider="mock", model="mock-v1", latency_ms=1.0, outcome="success",
            )

    monkeypatch.setattr("services.ai.provider_engine.get_unified_provider_engine", lambda: WrongMonthPlanner())
    _patch_records(monkeypatch, _multi_department_records())
    ai_evidence_cache.clear()
    db = _in_memory_db()
    try:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "planner-1", "has_unrestricted_team_access": True})
        r1 = orch.run_chat_turn(AiChatRequest(prompt="how did Marketing do in October 2026", session_state=SessionFilterContext(), provider_override="deterministic"))
        r2 = orch.run_chat_turn(
            AiChatRequest(prompt="what about the month before?", session_state=r1.resolved_session_state, history=[])
        )
        calls = [c for c in (r2.tool_calls or [])]
        periods = [str((getattr(c, "arguments", None) or getattr(c, "tool_arguments", None) or {}).get("period")) for c in calls]
        assert periods and all(p == "2026-09" for p in periods), (periods, r2.headline)
    finally:
        db.close()


def test_team_follow_up_without_a_metric_does_not_ask_for_a_metric(monkeypatch):
    """Live probe: 'last month' after a team score turn got 'missing required metric argument'."""
    import json

    from services.ai.provider_engine import ProviderResponse

    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")

    class NoMetricPlanner:
        def generate(self, req):
            return ProviderResponse(
                content=json.dumps({
                    "response_type": "tool_call",
                    "tool_name": "read_employee_metric",
                    "tool_arguments": {"team": "Marketing", "period": "2026-09"},
                }),
                provider="mock", model="mock-v1", latency_ms=1.0, outcome="success",
            )

    monkeypatch.setattr("services.ai.provider_engine.get_unified_provider_engine", lambda: NoMetricPlanner())
    _patch_records(monkeypatch, _multi_department_records())
    ai_evidence_cache.clear()
    db = _in_memory_db()
    try:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "planner-2", "has_unrestricted_team_access": True})
        r1 = orch.run_chat_turn(AiChatRequest(prompt="what is the overall score for Marketing in October 2026", session_state=SessionFilterContext(), provider_override="deterministic"))
        r2 = orch.run_chat_turn(AiChatRequest(prompt="and last month?", session_state=r1.resolved_session_state, history=[]))
        assert "missing required metric" not in _text(r2), r2.headline
    finally:
        db.close()
