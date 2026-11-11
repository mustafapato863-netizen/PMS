"""Leftover wording must not be routed as a person name.

Commit b1c4c51 started asking "Which {token}?" for every single token left
after stopword stripping. "Show Marketing's" became the person Show, and
fz-055 (which passed on bd51e73) started clarifying instead of answering
the Marketing corporate scorecard.
"""

from __future__ import annotations

import pytest

from models.ai_schemas import SessionFilterContext
from services.ai.entity_resolver import EmployeeHistoryCandidate
from services.ai.router import HybridQueryRouter, _extract_person_query_from_prompt

# The Phase 0 prompts that were classified as people (frozen_v0 / heldout_v0).
LEFTOVER_PROMPTS = {
    "fz-034": "Can you show Inbound for the month that has not been published?",
    "fz-054": "Show Inbound's managerial score for the latest published month.",
    "fz-055": "Show Marketing's corporate balanced scorecard for the latest published month.",
    "ho-014": "Which Inbound employee was last in August 2026?",
    "ho-057": "Show Pharmacy for the month that has not been published.",
    "ho-072": "Show Pharmacy's managerial score for the latest published month.",
    "ho-074": "What is the published score for the Quality Assurance position in Support for the latest published month?",
    "ho-076": "On this Monthly Review, what is the selected team's score?",
}

POSITIVE_NAMES = {
    "What is Mariam's score?": "Mariam",
    "Was September Adham's best month?": "Adham",
    "Is Mariam a new joiner in Inbound?": "Mariam",
    "mariam is new joiner in inbound team ?": "mariam",
    "When did Nour join Outbound?": "Nour",
    "Show Adham's score for September": "Adham",
    "What is the score of Sara Mahmoud in Inbound?": "Sara Mahmoud",
}


def _router(**kwargs) -> HybridQueryRouter:
    scope = kwargs.pop("scope", {"role": "Admin", "has_unrestricted_team_access": True})
    return HybridQueryRouter(
        scope=scope,
        published_periods=kwargs.pop("published_periods", ["2026-08", "2026-09"]),
        **kwargs,
    )


@pytest.mark.parametrize("case_id,prompt", LEFTOVER_PROMPTS.items())
def test_leftover_words_are_not_person_names(case_id, prompt):
    assert _extract_person_query_from_prompt(prompt) is None, case_id
    result = _router().resolve_and_validate(
        prompt=prompt,
        session_state=SessionFilterContext(function="Call Center"),
        provider_override="deterministic",
    )
    headline = (result.headline or "").casefold()
    assert "would you like to review" not in headline
    assert result.plan.employee_id is None
    assert result.plan.employee_name is None
    assert result.plan.single_person is False


@pytest.mark.parametrize("prompt,expected", POSITIVE_NAMES.items())
def test_real_person_names_are_still_extracted(prompt, expected):
    assert _extract_person_query_from_prompt(prompt) == expected


def test_known_person_still_resolves_and_ambiguous_first_name_still_asks():
    adham = EmployeeHistoryCandidate(
        employee_id="EMP501",
        employee_name="Adham Tarek",
        team="Inbound",
        function="Call Center",
        latest_score=91.0,
    )
    mariam_ali = EmployeeHistoryCandidate(
        employee_id="EMP601",
        employee_name="Mariam Ali",
        team="Inbound",
        function="Call Center",
    )
    mariam_hassan = EmployeeHistoryCandidate(
        employee_id="EMP602",
        employee_name="Mariam Hassan",
        team="Inbound",
        function="Call Center",
    )
    resolved = _router(employee_candidates=[adham]).resolve_and_validate(
        prompt="Was September Adham's best month?",
        session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        provider_override="deterministic",
    )
    assert resolved.outcome != "clarification"
    assert resolved.plan.employee_id == "EMP501"
    assert resolved.plan.employee_name == "Adham Tarek"

    ambiguous = _router(employee_candidates=[mariam_ali, mariam_hassan]).resolve_and_validate(
        prompt="Is Mariam a new joiner in Inbound?",
        session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        provider_override="deterministic",
    )
    assert ambiguous.outcome == "clarification"
    assert ambiguous.clarification is not None
    assert ambiguous.clarification.code == "AMBIGUOUS_PERSON"
    assert "Mariam" in (ambiguous.headline or "")


def test_unknown_single_first_name_still_asks_which_person():
    result = _router().resolve_and_validate(
        prompt="What is Mariam's score?",
        session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        provider_override="deterministic",
    )
    assert result.outcome == "clarification"
    assert "Which Mariam" in (result.headline or "")
