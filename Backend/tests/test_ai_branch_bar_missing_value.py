"""Item 3(d) (PR #84): a missing branch must not carry a numeric bar value.

Background: in a branch comparison, a branch with no recorded count/score
got ``AiBarItem(value=0.0, display_value="Unavailable")`` because the schema
required a float. A consumer reading ``value`` (including the frontend bar
width) therefore saw a small fake value for a branch that has no value at
all. The schema now allows ``value=None`` for unrecorded bars, the
registry emits ``None`` there, and the frontend renders no bar fill for
them. A real recorded zero is unchanged: value 0.0 with display "0 bookings".
"""
from __future__ import annotations

from types import SimpleNamespace

from services.ai.tool_registry import DeterministicToolRegistry

GM_SCOPE = {
    "role": "General Manager",
    "user_id": "00000000-0000-0000-0000-000000000002",
    "has_unrestricted_team_access": True,
}


class _MockInsights:
    def generate_workspace(self, *args, **kwargs):
        # No scores: the branch bars must come from volumes alone, and a
        # branch with no score has capped_s None (not 0.0).
        return SimpleNamespace(
            comparison=SimpleNamespace(
                current=SimpleNamespace(month="September", year=2026)
            ),
            team_summaries=[],
            executive_story=None,
            kpi_diagnosis=[],
        )


class _MockContext:
    def __init__(self, records):
        self._records = records
        self.scope = GM_SCOPE
        self.insights_service = _MockInsights()

    def get_scoped_records(self):
        return self._records

    def resolve_filters(self, **kwargs):
        return {
            "team": kwargs.get("team"),
            "function": kwargs.get("function"),
            "position": kwargs.get("position"),
            "branch": kwargs.get("branch"),
            "performance_level": kwargs.get("performance_level") or "Employee",
            "month": kwargs.get("month") or "September",
            "year": kwargs.get("year") or 2026,
            "region": None,
        }


def _record(bookings: dict, attended: dict):
    # geo containers are plain dicts, as the light-path rows are: a missing
    # key means the branch is unrecorded (never a default 0).
    return SimpleNamespace(
        team="Inbound",
        month="September",
        year=2026,
        calls=None,
        geo=SimpleNamespace(bookings=bookings, attended=attended),
    )


def _bars_by_branch(result):
    cards = [
        c
        for c in (result.visual_cards or [])
        if c.card_type == "horizontal_bar" and "Branch" in (c.title or "")
    ]
    assert cards, "expected a branch comparison bar card"
    return {b.label.split("·")[-1].strip(): b for b in cards[0].bars}


def test_count_bars_missing_branch_has_null_value_not_zero():
    records = [_record({"dubai": 200, "sharjah": 0}, {"dubai": 180, "sharjah": 0})]
    res = DeterministicToolRegistry(_MockContext(records)).execute_kpi_diagnosis_and_trends(
        team="Inbound",
        kpi="inbound:bookings_count",
        month="September",
        year=2026,
        branches=["dubai", "sharjah", "ajman"],
        asks_branch_comparison=True,
    )
    bars = _bars_by_branch(res)
    assert bars["Dubai"].value == 200.0
    assert bars["Dubai"].display_value == "200 bookings"
    # Sharjah recorded an explicit zero: a real zero stays 0.0.
    assert bars["Sharjah"].value == 0.0
    assert bars["Sharjah"].display_value == "0 bookings"
    # Ajman has no booking record at all: no numeric value, never 0.0.
    assert bars["Ajman"].value is None
    assert bars["Ajman"].display_value == "Unavailable"


def test_score_bars_missing_branch_has_null_value_not_zero():
    records = [_record({"dubai": 200, "sharjah": 50}, {"dubai": 180, "sharjah": 40})]
    res = DeterministicToolRegistry(_MockContext(records)).execute_kpi_diagnosis_and_trends(
        team="Inbound",
        month="September",
        year=2026,
        branches=["dubai", "sharjah", "ajman"],
        asks_branch_comparison=True,
    )
    bars = _bars_by_branch(res)
    # No branch has a recorded score in this mock (executive_story is None),
    # so every bar is unrecorded — none may carry the fake 0.0.
    for label, bar in bars.items():
        assert bar.value is None, f"{label} must not carry a numeric value"
        assert bar.display_value == "Unavailable"
