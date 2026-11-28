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
