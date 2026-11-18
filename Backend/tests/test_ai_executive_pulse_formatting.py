from __future__ import annotations

from models.ai_schemas import (
    AiChatResponsePayload,
    AiSpotlightMetadata,
    SessionFilterContext,
    StructuredVisualCard,
)
from services.ai.domain_policies import extract_prompt_signals
from services.ai.orchestrator import build_response_summary_tiles
from services.ai.providers import DeterministicLocalProviderAdapter


def test_multi_team_overall_question_leads_with_overall_score_and_avoids_zero_below_target_paradox():
    provider = DeterministicLocalProviderAdapter()
    merged = {
        "period": "October 2026",
        "scope": "All Authorized Departments",
        "branch": "All Branches",
        "average_score": 86.4,
        "score_change": 1.8,
        "total_records": 71,
        "employees_below_target": 4,
        "total_teams": 8,
        "teams_on_track": 7,
        "best_team": {
            "team": "Coding",
            "current_score": 94.2,
            "total_employees": 12,
        },
        "worst_team": {
            "team": "Resubmission",
            "current_score": 75.1,
            "score_change": -2.6,
            "gap_points": 24.9,
            "impacted_employees": 0,
            "total_employees": 1,
            "main_cause": "Rejection Rate After Re-Submission contributed to the performance gap",
        },
        "teams": [
            {"team": "Resubmission", "score": 75.1, "change": -2.6, "impacted": 0, "total": 1},
            {"team": "Inbound", "score": 88.0, "change": 2.1, "impacted": 2, "total": 25},
            {"team": "Coding", "score": 94.2, "change": 1.4, "impacted": 0, "total": 12},
        ],
    }

    prompt = "How are we doing overall?"
    state = SessionFilterContext()
    syn = provider.synthesize(
        prompt=prompt,
        signals=extract_prompt_signals(prompt, state),
        tool_digests=[merged],
        guardrail_notes=[],
        session_state=state,
        variation_seed=0,
    )

    assert "86.4%" in syn.headline
    assert "71" in syn.headline
    assert "Resubmission has the lowest score at 75.1%" in syn.headline
    assert "0 of 1 agents below target" not in syn.headline


def test_single_team_score_parity_kept_without_zero_below_target_noise():
    provider = DeterministicLocalProviderAdapter()
    merged = {
        "period": "September 2026",
        "scope": "Inbound",
        "branch": "All Branches",
        "average_score": 88.0,
        "score_change": None,
        "total_records": 4,
        "employees_below_target": 0,
        "worst_team": {
            "team": "Inbound",
            "current_score": 88.0,
            "score_change": None,
            "gap_points": 12.0,
            "impacted_employees": 0,
            "total_employees": 4,
            "main_cause": None,
        },
        "teams": [
            {"team": "Inbound", "score": 88.0, "change": None, "impacted": 0, "total": 4},
        ],
    }

    prompt = "What is the Inbound score in September 2026?"
    state = SessionFilterContext(team="Inbound")
    syn = provider.synthesize(
        prompt=prompt,
        signals=extract_prompt_signals(prompt, state),
        tool_digests=[merged],
        guardrail_notes=[],
        session_state=state,
        variation_seed=0,
    )

    assert "Inbound has the lowest score at 88.0%" in syn.headline
    assert "0 of 4 agents below target" not in syn.headline


def test_build_response_summary_tiles_creates_four_executive_tiles_for_multi_team_digest():
    merged = {
        "period": "October 2026",
        "scope": "All Authorized Departments",
        "average_score": 86.4,
        "score_change": 1.8,
        "total_records": 71,
        "employees_below_target": 4,
        "total_teams": 8,
        "teams_on_track": 7,
        "best_team": {"team": "Coding", "current_score": 94.2, "total_employees": 12},
        "worst_team": {
            "team": "Resubmission",
            "current_score": 75.1,
            "score_change": -2.6,
            "impacted_employees": 0,
            "total_employees": 1,
        },
        "teams": [
            {"team": "Resubmission", "score": 75.1, "change": -2.6, "impacted": 0, "total": 1},
            {"team": "Coding", "score": 94.2, "change": 1.4, "impacted": 0, "total": 12},
        ],
    }

    tiles = build_response_summary_tiles(merged=merged, visual_cards=[], typed_evidence=[])
    assert len(tiles) == 4
    labels = [t.label for t in tiles]
    assert labels[0] == "Overall Score"
    assert tiles[0].value == "86.4%"
    assert "Teams On Track" in labels
    assert any("Resubmission" in (t.value + " " + (t.sublabel or "")) for t in tiles)
    assert any("Coding" in (t.value + " " + (t.sublabel or "")) for t in tiles)

    payload = AiChatResponsePayload(
        trace_id="t-1",
        headline="Test",
        summary_tiles=tiles,
        resolved_session_state=SessionFilterContext(),
    )
    assert len(payload.summary_tiles) == 4


def test_build_response_summary_tiles_skips_when_trend_spotlight_already_present():
    spotlight_card = StructuredVisualCard(
        card_type="trend_spotlight",
        title="Agent Spotlight",
        spotlight=AiSpotlightMetadata(
            kicker="Agent Spotlight",
            entity_name="Sara Mahmoud",
            team="Inbound",
            score=95.4,
            grade="A",
            previous_month_label="August",
            target=100.0,
        ),
    )
    tiles = build_response_summary_tiles(
        merged={"average_score": 95.4, "total_records": 1},
        visual_cards=[spotlight_card],
        typed_evidence=[],
    )
    assert tiles == []
