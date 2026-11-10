from __future__ import annotations

import pytest
from models.ai_schemas import (
    AiChatRequest,
    ConfirmedQueryContext,
    SessionFilterContext,
)
from services.ai.domain_policies import build_call_center_starter_prompts
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.router import HybridQueryRouter
from tests.test_ai_booking_comparisons import _build_test_db_session


def test_booking_clarification_preserves_original_question():
    router = HybridQueryRouter(scope={"role": "Admin", "accessible_teams": ["Inbound", "Outbound"]})
    prompt = "Which had the fewest bookings, Dubai or Sharjah, in October 2026?"
    result = router.resolve_and_validate(prompt=prompt, session_state=SessionFilterContext(), provider_override="deterministic")
    assert result.clarification is not None
    choice = next(c for c in result.clarification.choices if c.id == "choice-bookings-inbound")
    assert prompt in choice.prompt_to_send
    assert "Inbound" in choice.prompt_to_send


def test_shared_scope_choice_does_not_repeat_clarification():
    router = HybridQueryRouter(scope={"role": "Admin", "accessible_teams": ["RCM"]})
    first = router.resolve_and_validate(prompt="What is the shared RCM score?", session_state=SessionFilterContext(), provider_override="deterministic")
    assert first.clarification is not None
    result = router.resolve_and_validate(
        prompt="What is the shared RCM score?",
        session_state=SessionFilterContext(last_confirmed_query=first.confirmed_context),
        clarification_choice_id="choice-shared-rcm",
        provider_override="deterministic",
    )
    assert result.outcome == "unsupported_request"
    assert "not available" in result.headline


def test_neutral_opening_greeting_and_starter_prompts():
    """A neutral opening must return a concise greeting without unsolicited Call Center analysis."""
    session = _build_test_db_session()
    scope = {"role": "Admin", "accessible_teams": ["Inbound", "Outbound", "Marketing", "Finance"]}
    orchestrator = PmsAiOrchestrator(session, scope)

    # Empty/neutral session state
    res = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="Hi",
            session_state=SessionFilterContext(),
            provider_override="deterministic",
        )
    )
    assert res.outcome == "answer"
    assert "hi!" in res.headline.lower()
    assert "performance" in res.headline.lower()
    # Must NOT run an unsolicited Call Center report
    assert "abandon" not in res.headline.lower()
    assert "call center" not in res.headline.lower()

    # Curated starter prompts for neutral scope should be general ("All authorized departments"), not Call-Center-only
    neutral_prompts = build_call_center_starter_prompts(SessionFilterContext())
    assert len(neutral_prompts) >= 3
    assert any("All authorized departments" in p.prompt for p in neutral_prompts)
    assert not any("Call Center" in p.prompt for p in neutral_prompts)


def test_department_switching_clears_prior_call_center_context():
    """Explicitly switching departments in session state must override prior team and function."""
    router = HybridQueryRouter(scope={"role": "Admin", "accessible_teams": ["Inbound", "Outbound", "Marketing", "Dispatch"]})

    # Turn 1: Call Center / Inbound
    ctx_cc = ConfirmedQueryContext(
        intent="score_drivers",
        function="Call Center",
        team="Inbound",
        periods=["2026-09"],
    )

    # Turn 2: User switches filter to Operations / Dispatch
    switched_state = SessionFilterContext(
        function="Operations",
        team="Dispatch",
        month="September",
        year=2026,
        last_confirmed_query=None,  # Reset on department change
    )

    result = router.resolve_and_validate(
        prompt="How did the team perform in September 2026?",
        session_state=switched_state,
        provider_override="deterministic",
    )
    # Plan must target Operations / Dispatch, NOT Call Center / Inbound
    assert result.plan.function == "Operations"
    assert result.plan.team == "Dispatch"


def test_context_inheritance_and_override():
    """Short follow-ups inherit team context, but naming a new department or country overrides it."""
    router = HybridQueryRouter(scope={"role": "Admin", "accessible_teams": ["Inbound", "Outbound", "Marketing"]})

    # Turn 1 confirmed context
    turn1_ctx = ConfirmedQueryContext(
        intent="ranking",
        function="Call Center",
        team="Inbound",
        periods=["2026-09"],
    )
    session_with_turn1 = SessionFilterContext(
        team="Inbound",
        month="September",
        year=2026,
        last_confirmed_query=turn1_ctx,
    )

    # 1. Follow-up: "What about August?" inherits Inbound and updates period
    res_inherit = router.resolve_and_validate(
        prompt="What about August?",
        session_state=session_with_turn1,
        provider_override="deterministic",
    )
    assert res_inherit.plan.team == "Inbound"
    assert "2026-08" in (res_inherit.plan.periods or [])

    # 2. Override: "How did Marketing perform?" must override Inbound
    res_override = router.resolve_and_validate(
        prompt="How did Marketing perform in September 2026?",
        session_state=session_with_turn1,
        provider_override="deterministic",
    )
    assert res_override.plan.team == "Marketing"
    assert res_override.plan.team != "Inbound"


def test_cross_department_questions_not_redirected_to_call_center():
    """Questions naming another department or cross-department scope must not be forced to Call Center."""
    router = HybridQueryRouter(scope={"role": "Admin", "accessible_teams": ["Inbound", "Marketing", "Finance"]})

    # Neutral session state
    neutral_state = SessionFilterContext(month="September", year=2026)

    # 1. Marketing specific question
    res_mkt = router.resolve_and_validate(
        prompt="What was Marketing score in September 2026?",
        session_state=neutral_state,
        provider_override="deterministic",
    )
    assert res_mkt.plan.team == "Marketing"
    assert (res_mkt.plan.function or "") != "Call Center"

    # 2. Cross-department question
    res_cross = router.resolve_and_validate(
        prompt="Compare Marketing and Inbound in September 2026",
        session_state=neutral_state,
        provider_override="deterministic",
    )
    # Must not silently collapse to Call Center only
    assert res_cross.plan.team in ("Marketing", "Inbound") or res_cross.outcome in ("clarify", "answer", "unsupported_request")
