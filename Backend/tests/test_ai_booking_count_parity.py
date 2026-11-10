"""Task 2 (PR #84): paired model-on vs rules-only source parity for booking
counts, and honest handling of unsupported branch percentages.

Background (Qwen smoke testing): a Clinics booking request was answered with
the unrelated Booking Rate KPI, an Inbound booking-count question was answered
with a rate percentage, and a branch booking count was answered as performance
percentages. The fixes under test live in the tool/resolver layer only:

- services/ai/catalog.py: bare "bookings" is a count alias (not a rate alias);
  find_metric_definition picks the best alias match, preferring a count
  metric when the question carries a count cue.
- services/ai/router.py: _detect_metric_id sends bare/count booking
  phrasing to bookings_count and only explicit rate phrasing to booking_rate.
- services/ai/domain_policies.py: extract_prompt_signals agrees.
- services/ai/local_data_explorer.py: a bookings question without rate
  language forces the booking counter even when Qwen labelled it a rate,
  for every tool (not just compare_branches).
- services/ai/tool_registry.py: branch-comparison bars show booking counts
  (not performance-score percentages) when the comparison is about counts,
  and an unrecorded count is labelled Unavailable, never 0%.

All model behaviour here uses deterministic / mocked responses. No live
Qwen endpoint is contacted and no live-model accuracy is claimed.
"""
from __future__ import annotations

import io
import json
from typing import Any

import pytest

from models.ai_schemas import AiChatRequest, SessionFilterContext
from services.ai.catalog import ai_evidence_cache, get_ai_catalog
from services.ai.domain_policies import ParsedPromptSignals, extract_prompt_signals
from services.ai.local_data_explorer import _validate_and_normalize_tool_call
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.providers import DeterministicLocalProviderAdapter
from services.ai.router import _detect_metric_id
from test_ai_workspace import (
    _build_in_memory_db,
    _make_call_center_record,
    _patch_records,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    ai_evidence_cache.clear()
    yield
    ai_evidence_cache.clear()


# ---------------------------------------------------------------------------
# Fixture data (same shape as test_ai_workspace.py):
# Inbound EMP101: Dubai 200, Sharjah 50, Ajman 20, Clinics 10 bookings
# Inbound EMP102: Dubai 150, Sharjah 40, Ajman 20, Clinics 10 bookings
# Outbound EMP201: Dubai 160, Sharjah 60, Ajman 20, Clinics 10 bookings
# => Inbound total 500; Clinics function-wide total 30; Dubai Inbound 350,
#    Sharjah Inbound 90, Ajman Inbound 40, Clinics Inbound 20.
# ---------------------------------------------------------------------------
GM_SCOPE = {
    "role": "General Manager",
    "user_id": "00000000-0000-0000-0000-000000000002",
    "has_unrestricted_team_access": True,
}


def _records():
    return [
        _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 91.0, 45, 50, 90, 200, month="September"),
        _make_call_center_record("EMP102", "Omar Ali", "Inbound", 85.0, 30, 40, 70, 150, month="September"),
        _make_call_center_record("EMP201", "Mona Hassan", "Outbound", 72.0, 34, 60, 72, 160, month="September"),
    ]


def _ask(monkeypatch, prompt, **env):
    _patch_records(monkeypatch, _records())
    with _build_in_memory_db() as db:
        return PmsAiOrchestrator(db, GM_SCOPE).run_chat_turn(
            AiChatRequest(
                prompt=prompt,
                session_state=SessionFilterContext(function="Call Center"),
            )
        )


def _mock_llama_steps(monkeypatch: pytest.MonkeyPatch, step_payloads: list[dict[str, Any] | str]):
    """Script Qwen step responses (copied pattern from
    test_local_assistant_exploration.py); the model is never contacted.
    Returns the list of captured request bodies, proving the model path ran."""

    captured_requests: list[dict[str, Any]] = []
    counter = [0]

    class _MockOpener:
        def open(self, request: Any, timeout: float = 8.0) -> io.BytesIO:
            captured_requests.append(json.loads(request.data.decode("utf-8")))
            idx = min(counter[0], len(step_payloads) - 1)
            counter[0] += 1
            payload_item = step_payloads[idx]
            content_str = payload_item if isinstance(payload_item, str) else json.dumps(payload_item)
            envelope = {"choices": [{"message": {"content": content_str}}]}
            return io.BytesIO(json.dumps(envelope).encode("utf-8"))

    monkeypatch.setattr("services.ai.llm_client.urllib.request.build_opener", lambda *_: _MockOpener())
    return captured_requests


def _enable_exploration(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")


# ---------------------------------------------------------------------------
# 1. Catalog: count phrasing resolves to the counter, rate phrasing to the rate
# ---------------------------------------------------------------------------
COUNT_PHRASES = [
    "bookings",
    "Clinics bookings",
    "How many Clinics bookings in September?",
    "What is the Inbound booking count?",
    "How many Inbound bookings in September 2026?",
    "What are Inbound bookings in Dubai and Sharjah in September 2026?",
    "Inbound bookings: did Dubai, Ajman, or Sharjah have the highest count?",
    "Rank Dubai and Sharjah by Inbound booking count in September 2026.",
    "total bookings",
    "number of bookings",
    "booking volume",
    "most bookings",
    "more bookings",
]

RATE_PHRASES = [
    "What is the Inbound Booking Rate in September 2026?",
    "What is the Inbound Booking Conversion Rate in September 2026?",
    "booking rate",
    "booking conversion",
]


@pytest.mark.parametrize("team", ["Inbound", "Outbound"])
@pytest.mark.parametrize("phrase", COUNT_PHRASES)
def test_catalog_booking_count_phrasing_resolves_to_counter(team, phrase):
    found = get_ai_catalog().find_metric_definition(team=team, kpi_key_or_label=phrase)
    assert found is not None, phrase
    assert found.metric_id == f"{team.casefold()}:bookings_count", phrase
    assert found.value_kind == "count"
    assert found.unit == "count"


@pytest.mark.parametrize("team", ["Inbound", "Outbound"])
@pytest.mark.parametrize("phrase", RATE_PHRASES)
def test_catalog_booking_rate_phrasing_still_resolves_to_rate(team, phrase):
    found = get_ai_catalog().find_metric_definition(team=team, kpi_key_or_label=phrase)
    assert found is not None, phrase
    assert found.metric_id == f"{team.casefold()}:booking_rate", phrase
    assert found.value_kind == "rate"


def test_catalog_count_cue_prefers_attended_counter_over_attendance_rate():
    found = get_ai_catalog().find_metric_definition(
        team="Inbound", kpi_key_or_label="How many attended bookings in September?"
    )
    assert found is not None
    assert found.metric_id == "inbound:attended_count"


def test_catalog_rate_cue_keeps_attendance_rate():
    found = get_ai_catalog().find_metric_definition(
        team="Inbound", kpi_key_or_label="What is the Inbound Attendance Rate in September 2026?"
    )
    assert found is not None
    assert found.metric_id == "inbound:attendance_rate"


# ---------------------------------------------------------------------------
# 2. Router: same phrasings, same verdicts
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("phrase", COUNT_PHRASES)
def test_router_booking_count_phrasing_resolves_to_counter(phrase):
    assert _detect_metric_id(phrase.casefold(), team="Inbound", position=None, performance_level="Employee") == "inbound:bookings_count"


@pytest.mark.parametrize("phrase", RATE_PHRASES)
def test_router_booking_rate_phrasing_still_resolves_to_rate(phrase):
    assert _detect_metric_id(phrase.casefold(), team="Inbound", position=None, performance_level="Employee") == "inbound:booking_rate"


def test_router_outbound_count_phrasing_uses_outbound_counter():
    assert (
        _detect_metric_id("how many outbound bookings in september?", team="Outbound", position=None, performance_level="Employee")
        == "outbound:bookings_count"
    )


# ---------------------------------------------------------------------------
# 3. Signals agree the question is a count question
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "phrase",
    [
        "How many Clinics bookings in September 2026?",
        "What is the Inbound booking count?",
        "How many Inbound bookings in September 2026?",
    ],
)
def test_signals_flag_booking_count_questions(phrase):
    sig = extract_prompt_signals(phrase, SessionFilterContext(function="Call Center"))
    assert sig.asks_booking_count is True


# ---------------------------------------------------------------------------
# 4. Rules-only end to end: the authorised counter, not the rate
# ---------------------------------------------------------------------------
def test_rules_only_clinics_bookings_returns_count_not_rate(monkeypatch):
    res = _ask(monkeypatch, "How many Clinics bookings in September 2026?")
    assert res.outcome == "answer"
    assert res.structured_query is not None
    assert res.structured_query.metric == "inbound:bookings_count"
    assert res.structured_query.branches == ["clinics"]
    assert "Bookings (Count) reached 30" in res.headline
    assert "Booking Rate is at" not in res.headline


def test_rules_only_inbound_bookings_returns_total_count(monkeypatch):
    res = _ask(monkeypatch, "How many Inbound bookings in September 2026?")
    assert res.outcome == "answer"
    assert res.structured_query is not None
    assert res.structured_query.team == "Inbound"
    assert res.structured_query.metric == "inbound:bookings_count"
    assert "Bookings (Count) reached 500" in res.headline
    assert "Booking Rate is at" not in res.headline


def test_rules_only_explicit_rate_question_still_returns_rate(monkeypatch):
    res = _ask(monkeypatch, "What is the Inbound Booking Rate in September 2026?")
    assert res.outcome == "answer"
    assert res.structured_query is not None
    assert res.structured_query.metric == "inbound:booking_rate"
    assert "Booking Rate is at 28.0%" in res.headline


def test_rules_only_branch_booking_comparison_bars_show_counts(monkeypatch):
    res = _ask(
        monkeypatch,
        "Which branch had the most Inbound bookings in September 2026: Dubai, Sharjah, or Ajman?",
    )
    assert res.outcome == "answer"
    assert res.structured_query is not None
    assert res.structured_query.metric == "inbound:bookings_count"
    assert "Dubai led September 2026 Inbound bookings with 350" in res.headline
    bar_cards = [c for c in (res.visual_cards or []) if c.card_type == "horizontal_bar" and "Booking" in (c.title or "")]
    assert bar_cards, "expected a branch booking-count bar card"
    bars = {b.label: b for b in bar_cards[0].bars}
    assert "Booking Counts" in bar_cards[0].title
    assert bars["Inbound · Dubai"].display_value == "350 bookings"
    assert bars["Inbound · Sharjah"].display_value == "90 bookings"
    assert bars["Inbound · Ajman"].display_value == "40 bookings"
    assert bars["Inbound · Clinics"].display_value == "20 bookings"
    assert all("%" not in b.display_value for b in bar_cards[0].bars), "count bars must not show percentages"


# ---------------------------------------------------------------------------
# 5. Explorer validation: Qwen's labels are corrected, not trusted blindly
# ---------------------------------------------------------------------------
def _validate(raw_tool, prompt, team=None):
    return _validate_and_normalize_tool_call(
        raw_tool=raw_tool,
        prompt=prompt,
        scope=GM_SCOPE,
        session_state=SessionFilterContext(function="Call Center", team=team, month="September", year=2026),
        published_periods={"2026-09"},
        latest_published_period="2026-09",
        employee_candidates=[],
    )


def test_explorer_validation_overrides_qwen_rate_label_for_clinics_count():
    call, early, status = _validate(
        {"tool": "get_kpi_diagnosis", "team": "Call Center", "metric": "Booking Rate", "branch": "clinics", "period": "2026-09"},
        "How many Clinics bookings in September 2026?",
    )
    assert early is None, status
    assert call is not None
    assert call.metric_id == "inbound:bookings_count"
    assert call.kpi_key == "TotalBookings"
    assert call.branch == "clinics"


def test_explorer_validation_does_not_infer_team_from_shared_metric_label():
    # "Booking Rate" is tracked by both Inbound and Outbound. Qwen's label
    # must not silently narrow a function-wide Clinics question to the
    # Inbound-only count (20) instead of the function-wide count (30).
    call, early, status = _validate(
        {"tool": "get_kpi_diagnosis", "team": "Call Center", "metric": "Booking Rate", "branch": "clinics", "period": "2026-09"},
        "How many Clinics bookings in September 2026?",
    )
    assert early is None, status
    assert call is not None
    assert call.team is None
    assert call.metric_id == "inbound:bookings_count"
    assert call.kpi_key == "TotalBookings"


def test_explorer_validation_infers_team_from_team_unique_metric_label():
    # "CPL" belongs to Marketing only, so the team can be inferred. (Labels
    # like "Abandon Rate" look unique but are shared with Call Center
    # position-level metrics, so they must not infer a team.)
    call, early, status = _validate(
        {"tool": "get_kpi_diagnosis", "metric": "CPL", "period": "2026-09"},
        "What is the CPL in September 2026?",
    )
    assert early is None, status
    assert call is not None
    assert call.team == "Marketing"
    assert call.metric_id == "marketing:media_buyer:cpl"


def test_explorer_validation_binds_explicit_inbound_team_over_qwen_call_center():
    call, early, status = _validate(
        {"tool": "get_team_score_summary", "team": "Call Center", "period": "2026-09"},
        "What is the Inbound score in September 2026?",
    )
    assert early is None, status
    assert call is not None
    assert call.team == "Inbound"


def test_explorer_validation_binds_explicit_inbound_team_over_qwen_wrong_team():
    call, early, status = _validate(
        {"tool": "get_team_score_summary", "team": "Outbound", "period": "2026-09"},
        "What is the Inbound score in September 2026?",
    )
    assert early is None, status
    assert call is not None
    assert call.team == "Inbound"


def test_explorer_validation_keeps_explicit_rate_label_for_rate_question():
    call, early, status = _validate(
        {"tool": "get_kpi_diagnosis", "team": "Inbound", "metric": "Booking Rate", "period": "2026-09"},
        "What is the Inbound Booking Rate in September 2026?",
    )
    assert early is None, status
    assert call is not None
    assert call.metric_id == "inbound:booking_rate"


def test_explorer_validation_forces_counter_for_branch_comparison_despite_rate_label():
    call, early, status = _validate(
        {"tool": "compare_branches", "team": "Call Center", "metric": "Booking Rate", "period": "2026-09"},
        "Which branch had the most Inbound bookings in September 2026: Dubai, Sharjah, or Ajman?",
    )
    assert early is None, status
    assert call is not None
    assert call.tool == "compare_branches"
    assert call.team == "Inbound"
    assert call.metric_id == "inbound:bookings_count"
    assert call.kpi_key == "TotalBookings"


# ---------------------------------------------------------------------------
# 6. Paired parity: same prompt, mocked Qwen tool choice vs rules-only —
#    same authorised metric and same count
# ---------------------------------------------------------------------------
def test_paired_parity_clinics_bookings_model_on_vs_rules_only(monkeypatch):
    prompt = "How many Clinics bookings in September 2026?"
    rules_only = _ask(monkeypatch, prompt)

    _enable_exploration(monkeypatch)
    captured = _mock_llama_steps(
        monkeypatch,
        [
            {
                "action": "call_tools",
                "unknown_code": "none",
                "tools": [{"tool": "get_kpi_diagnosis", "team": "Call Center", "metric": "Booking Rate", "branch": "clinics", "period": "2026-09"}],
            }
        ],
    )
    model_on = _ask(monkeypatch, prompt)

    assert captured, "mocked Qwen was never called — the model-on path did not run"
    assert rules_only.structured_query.metric == "inbound:bookings_count"
    assert model_on.structured_query.metric == "inbound:bookings_count"
    assert model_on.headline == rules_only.headline
    assert "Bookings (Count) reached 30" in model_on.headline
    assert "Booking Rate is at" not in model_on.headline


def test_paired_parity_branch_booking_comparison_model_on_vs_rules_only(monkeypatch):
    prompt = "Which branch had the most Inbound bookings in September 2026: Dubai, Sharjah, or Ajman?"
    rules_only = _ask(monkeypatch, prompt)

    _enable_exploration(monkeypatch)
    captured = _mock_llama_steps(
        monkeypatch,
        [
            {
                "action": "call_tools",
                "unknown_code": "none",
                "tools": [{"tool": "compare_branches", "team": "Call Center", "metric": "Booking Rate", "period": "2026-09"}],
            }
        ],
    )
    model_on = _ask(monkeypatch, prompt)

    assert captured, "mocked Qwen was never called — the model-on path did not run"
    assert rules_only.structured_query.metric == "inbound:bookings_count"
    assert model_on.structured_query.metric == "inbound:bookings_count"
    assert model_on.headline == rules_only.headline
    assert "Dubai led September 2026 Inbound bookings with 350" in model_on.headline


def test_paired_parity_inbound_score_model_on_vs_rules_only(monkeypatch):
    prompt = "What is the Inbound score in September 2026?"
    rules_only = _ask(monkeypatch, prompt)

    _enable_exploration(monkeypatch)
    captured = _mock_llama_steps(
        monkeypatch,
        [
            {
                "action": "call_tools",
                "unknown_code": "none",
                "tools": [{"tool": "get_team_score_summary", "team": "Call Center", "period": "2026-09"}],
            }
        ],
    )
    model_on = _ask(monkeypatch, prompt)

    assert captured, "mocked Qwen was never called — the model-on path did not run"
    assert model_on.outcome == "answer"
    assert model_on.headline == rules_only.headline
    assert "Inbound has the lowest score at 88.0%" in model_on.headline
    assert "Call Center has the lowest score" not in model_on.headline


# ---------------------------------------------------------------------------
# 7. Unsupported branch data is reported honestly, never as a percentage
# ---------------------------------------------------------------------------
def _booking_digest_with_missing_branch():
    return {
        "period": "September 2026",
        "scope": "Inbound",
        "requested_branches": ["Dubai", "Sharjah", "Ajman"],
        "branch_comparison": [
            {"branch": "Dubai", "bookings": 150, "attended": 140, "attendance_rate_pct": 93.3, "data_present": True},
            {"branch": "Sharjah", "bookings": 80, "attended": 70, "attendance_rate_pct": 87.5, "data_present": True},
            {"branch": "Ajman", "bookings": None, "attended": None, "attendance_rate_pct": None, "data_present": False},
        ],
    }


def test_missing_branch_is_not_ranked_or_given_a_percentage():
    sig = ParsedPromptSignals()
    sig.asks_booking_count = True
    sig.asks_branch_comparison = True
    res = DeterministicLocalProviderAdapter().synthesize(
        prompt="Which branch had the most Inbound bookings in September 2026: Dubai, Sharjah, or Ajman?",
        signals=sig,
        tool_digests=[_booking_digest_with_missing_branch()],
        guardrail_notes=[],
    )
    assert "partially available" in res.headline
    assert "Ajman" in res.headline and "missing or unpublished" in res.headline
    assert "Dubai recorded 150 bookings" in res.headline
    assert "led" not in res.headline
    assert "Ajman: data missing or unpublished" in res.narrative_bullets[1]
    # Ajman must not be ranked as zero: no fabricated zero count or percentage.
    assert "Ajman recorded 0" not in res.headline
    assert "tied with 0" not in res.headline
    assert "0%" not in res.headline


def test_all_branches_missing_reports_unavailable_not_zero():
    sig = ParsedPromptSignals()
    sig.asks_booking_count = True
    sig.asks_branch_comparison = True
    digest = _booking_digest_with_missing_branch()
    digest["branch_comparison"] = [
        {**b, "bookings": None, "attended": None, "attendance_rate_pct": None, "data_present": False}
        for b in digest["branch_comparison"]
    ]
    res = DeterministicLocalProviderAdapter().synthesize(
        prompt="Which branch had the most Inbound bookings in September 2026: Dubai, Sharjah, or Ajman?",
        signals=sig,
        tool_digests=[digest],
        guardrail_notes=[],
    )
    assert "Booking data is missing or unpublished" in res.headline
    assert "0 bookings" not in res.headline


def test_attendance_unrecorded_is_not_fabricated_as_zero_percent():
    sig = ParsedPromptSignals()
    sig.asks_booking_count = True
    sig.asks_branch_comparison = True
    digest = {
        "period": "September 2026",
        "scope": "Inbound",
        "requested_branches": ["Dubai", "Sharjah"],
        "branch_comparison": [
            {"branch": "Dubai", "bookings": 100, "attended": 90, "attendance_rate_pct": 90.0, "data_present": True},
            {"branch": "Sharjah", "bookings": 80, "attended": None, "attendance_rate_pct": None, "data_present": True},
        ],
    }
    res = DeterministicLocalProviderAdapter().synthesize(
        prompt="Which branch had the most Inbound bookings in September 2026: Dubai or Sharjah?",
        signals=sig,
        tool_digests=[digest],
        guardrail_notes=[],
    )
    assert "Dubai led September 2026 Inbound bookings with 100" in res.headline
    # Sharjah's attendance is unrecorded: stated as such, never as 0%.
    # (Dubai's 90.0% is a real recorded attendance rate, not a fabrication.)
    assert res.narrative_bullets[0] == (
        "Branch booking breakdown: Dubai: 100 bookings (90 attended, 90.0%) · "
        "Sharjah: 80 bookings (attendance unrecorded)."
    )
    assert "Sharjah: 80 bookings (0" not in res.narrative_bullets[0]
