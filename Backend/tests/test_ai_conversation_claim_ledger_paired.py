"""Paired Workstream B (#99) conversation, claim-ledger, and Cloudflare/Gemini integration tests."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from ai_provider_fakes import install_scripted_provider
from models.ai_schemas import AiChatRequest, SessionFilterContext
from services.ai import provider_engine
from services.ai.claim_validator import build_claim_ledger
from services.ai.local_data_explorer import (
    ValidatedExplorationToolCall,
    build_fact_ledger_from_evidence,
    run_bounded_exploration,
    validate_grounded_synthesis,
)
from services.ai.local_evidence_synthesis import (
    synthesize_branch_bookings,
    synthesize_overall_score,
)
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.provider_engine import ProviderAttempt, ProviderRequest, ProviderResponse
from services.ai.tool_registry import ToolExecutionResult
from test_ai_workspace import (
    _build_in_memory_db,
    _make_call_center_record,
    _patch_records,
)

ADMIN_SCOPE = {
    "role": "Admin",
    "has_unrestricted_team_access": True,
    "accessible_teams": ["Inbound", "Outbound", "CSR", "Pharmacy", "Coding"],
    "accessible_functions": ["Call Center", "CSR", "Pharmacy", "RCM"],
}


def _seed_call_center_records(monkeypatch: pytest.MonkeyPatch) -> None:
    records = [
        _make_call_center_record("EMP001", "Alice Synthetic", "Inbound", 88.0, 20, 40, 30, 60, month="August"),
        _make_call_center_record("EMP002", "Bob Synthetic", "Inbound", 74.0, 10, 25, 15, 35, month="August"),
        _make_call_center_record("EMP001", "Alice Synthetic", "Inbound", 92.0, 24, 48, 36, 72, month="September"),
        _make_call_center_record("EMP002", "Bob Synthetic", "Inbound", 79.0, 12, 30, 18, 40, month="September"),
        _make_call_center_record("EMP003", "Clara Synthetic", "Outbound", 85.0, 15, 30, 25, 50, month="September"),
    ]
    _patch_records(monkeypatch, records)


def test_fact_ledger_preserves_none_vs_real_zero_across_tools():
    executed_calls = [
        ValidatedExplorationToolCall(
            tool="compare_branches",
            team="Inbound",
            period="September 2026",
            branches=("dubai", "sharjah", "ajman", "clinics"),
        ),
        ValidatedExplorationToolCall(
            tool="get_trend",
            team="Outbound",
            period="September 2026",
        ),
    ]
    tool_results = [
        ToolExecutionResult(
            tool_name="compare_branches",
            arguments={"team": "Inbound", "period": "September 2026"},
            records_evaluated=4,
            digest={
                "scope": "Inbound",
                "period": "September 2026",
                "branch_comparison": [
                    {"branch": "dubai", "average_score": 30.0, "data_present": True},
                    {"branch": "sharjah", "average_score": 30.0, "data_present": True},
                    {"branch": "ajman", "average_score": None, "data_present": False},
                    {"branch": "clinics", "average_score": 0.0, "data_present": True},
                ],
            },
        ),
        ToolExecutionResult(
            tool_name="get_trend",
            arguments={"team": "Outbound", "period": "September 2026"},
            records_evaluated=2,
            digest={
                "scope": "Outbound",
                "period": "September 2026",
                "team_trend_spotlight": {"team": "Outbound", "score": None},
            },
        ),
    ]
    fact_ledger = build_fact_ledger_from_evidence(
        executed_calls=executed_calls,
        tool_results=tool_results,
        default_headline="Inbound comparison summary",
    )
    by_subj = {f["subject"]: f for f in fact_ledger}
    assert by_subj["ajman"]["value"] is None and by_subj["ajman"]["is_missing"] is True
    assert by_subj["clinics"]["value"] == 0.0 and by_subj["clinics"]["is_missing"] is False
    assert by_subj["Outbound"]["value"] is None and by_subj["Outbound"]["is_missing"] is True

    claim_facts = build_claim_ledger(fact_ledger=fact_ledger)
    ajman_fact = next(f for f in claim_facts if f.subject == "ajman")
    clinics_fact = next(f for f in claim_facts if f.subject == "clinics")
    assert ajman_fact.value is None and ajman_fact.is_missing is True
    assert clinics_fact.value == 0.0 and clinics_fact.is_missing is False


def test_inbound_booking_rate_percent_vs_bookings_count_unit_validation():
    fact_ledger = [
        {
            "fact_id": "F1",
            "part": "rate",
            "subject": "Inbound Booking Rate",
            "team": "Inbound",
            "period": "September 2026",
            "metric_key": "Booking",
            "value": 32.4,
            "unit": "%",
            "direction": "higher_better",
        },
        {
            "fact_id": "F2",
            "part": "count",
            "subject": "Inbound Bookings",
            "team": "Inbound",
            "period": "September 2026",
            "metric_key": "Bookings",
            "value": 180,
            "unit": "count",
            "direction": "higher_better",
        },
    ]
    valid_text, valid_reason = validate_grounded_synthesis(
        draft_payload={
            "headline": "Inbound Booking Rate was 32.4% across 180 Inbound Bookings in September 2026.",
            "fact_ids": ["F1", "F2"],
        },
        fact_ledger=fact_ledger,
    )
    assert valid_text is not None and valid_reason == "ok"

    bad_text, bad_reason = validate_grounded_synthesis(
        draft_payload={
            "headline": "Inbound Booking Rate was 32.4% across 180% Inbound Bookings in September 2026.",
            "fact_ids": ["F1", "F2"],
        },
        fact_ledger=fact_ledger,
    )
    assert bad_text is None and bad_reason == "mismatched_unit"


def test_branch_comparison_ties_and_missing_vs_zero_branches():
    fact_ledger = [
        {
            "fact_id": "B1",
            "part": "branch_0",
            "subject": "Dubai",
            "team": "CSR",
            "branch": "dubai",
            "period": "September 2026",
            "metric_key": "AttendedCR",
            "value": 30.0,
            "unit": "%",
            "direction": "higher_better",
            "ties": ["Dubai", "Sharjah"],
        },
        {
            "fact_id": "B2",
            "part": "branch_1",
            "subject": "Sharjah",
            "team": "CSR",
            "branch": "sharjah",
            "period": "September 2026",
            "metric_key": "AttendedCR",
            "value": 30.0,
            "unit": "%",
            "direction": "higher_better",
            "ties": ["Dubai", "Sharjah"],
        },
        {
            "fact_id": "B3",
            "part": "branch_2",
            "subject": "Ajman",
            "team": "CSR",
            "branch": "ajman",
            "period": "September 2026",
            "metric_key": "AttendedCR",
            "value": None,
            "is_missing": True,
            "unit": "%",
            "direction": "higher_better",
        },
        {
            "fact_id": "B4",
            "part": "branch_3",
            "subject": "Clinics",
            "team": "CSR",
            "branch": "clinics",
            "period": "September 2026",
            "metric_key": "AttendedCR",
            "value": 0.0,
            "is_missing": False,
            "unit": "%",
            "direction": "higher_better",
        },
    ]

    # Undisclosed tie must be rejected
    tie_text, tie_reason = validate_grounded_synthesis(
        draft_payload={
            "headline": "Dubai at 30% led Sharjah at 30% while Clinics recorded 0% and Ajman data was unavailable in September 2026.",
            "fact_ids": ["B1", "B2", "B3", "B4"],
        },
        fact_ledger=fact_ledger,
    )
    assert tie_text is None and tie_reason == "undisclosed_tie"

    # Coercing missing Ajman to 0% must be rejected
    null_text, null_reason = validate_grounded_synthesis(
        draft_payload={
            "headline": "Dubai and Sharjah tied at 30%, Clinics recorded 0%, and Ajman was 0% in September 2026.",
            "fact_ids": ["B1", "B2", "B3", "B4"],
        },
        fact_ledger=fact_ledger,
    )
    assert null_text is None and null_reason == "null_coerced_to_zero"

    # Accurate tie + missing vs real zero wording must pass
    good_text, good_reason = validate_grounded_synthesis(
        draft_payload={
            "headline": "Dubai and Sharjah tied at 30%, Clinics recorded 0%, and Ajman data is unavailable in September 2026.",
            "fact_ids": ["B1", "B2", "B3", "B4"],
        },
        fact_ledger=fact_ledger,
    )
    assert good_text is not None and good_reason == "ok"


def test_lower_better_abandon_rate_synthesis_polarity_check():
    fact_ledger = [
        {
            "fact_id": "A1",
            "part": "agent_0",
            "subject": "Alice",
            "team": "Inbound",
            "period": "September 2026",
            "metric_key": "Other",
            "metric_name": "Abandon Rate",
            "value": 1.2,
            "unit": "%",
            "direction": "lower_better",
        },
        {
            "fact_id": "A2",
            "part": "agent_1",
            "subject": "Bob",
            "team": "Inbound",
            "period": "September 2026",
            "metric_key": "Other",
            "metric_name": "Abandon Rate",
            "value": 4.5,
            "unit": "%",
            "direction": "lower_better",
        },
    ]
    bad_text, bad_reason = validate_grounded_synthesis(
        draft_payload={
            "headline": "Bob at 4.5% outperformed Alice at 1.2% on Abandon Rate in September 2026.",
            "fact_ids": ["A1", "A2"],
        },
        fact_ledger=fact_ledger,
    )
    assert bad_text is None and bad_reason == "inverted_polarity"

    good_text, good_reason = validate_grounded_synthesis(
        draft_payload={
            "headline": "Alice at 1.2% outperformed Bob at 4.5% on Abandon Rate in September 2026.",
            "fact_ids": ["A1", "A2"],
        },
        fact_ledger=fact_ledger,
    )
    assert good_text is not None and good_reason == "ok"


def test_local_evidence_synthesis_overall_score_accepts_verified_and_rejects_hallucination(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "development")
    digests = [
        {
            "period": "September 2026",
            "scope": "Inbound",
            "branch": "All Branches",
            "average_score": 85.5,
            "total_records": 2,
        }
    ]

    install_scripted_provider(
        monkeypatch,
        [{"answer": "Inbound scored 85.5% in September 2026."}],
        provider="cloudflare",
    )
    good = synthesize_overall_score("What is Inbound overall score in September 2026?", digests)
    assert good is not None
    assert good.provider_used == "cloudflare"
    assert good.metrics.fallback_outcome == "none"
    assert "85.5%" in good.headline

    install_scripted_provider(
        monkeypatch,
        [{"answer": "Inbound scored 99.9% in September 2026."}],
        provider="cloudflare",
    )
    bad = synthesize_overall_score("What is Inbound overall score in September 2026?", digests)
    assert bad is not None
    assert bad.provider_used == "deterministic"
    assert bad.metrics.fallback_outcome == "invalid_or_unverified_response"
    assert "85.5%" in bad.headline


def test_local_evidence_synthesis_branch_bookings_rejects_swapped_values_and_falls_back(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "development")
    digests = [
        {
            "period": "September 2026",
            "scope": "Inbound",
            "requested_branches": ["Dubai", "Sharjah"],
            "branch_comparison": [
                {"branch": "Dubai", "bookings": 112},
                {"branch": "Sharjah", "bookings": 70},
            ],
        }
    ]
    install_scripted_provider(
        monkeypatch,
        [{"answer": "Dubai had 70 Inbound bookings in September 2026 and Sharjah had 112."}],
        provider="gemini",
    )
    res = synthesize_branch_bookings("Compare Dubai and Sharjah bookings in September 2026", digests)
    assert res is not None
    assert res.provider_used == "deterministic"
    assert res.metrics.fallback_outcome == "invalid_or_unverified_response"
    assert "Dubai: 112" in res.headline and "Sharjah: 70" in res.headline


def test_explorer_cloudflare_hallucination_falls_back_to_deterministic_synthesis(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "development")
    _seed_call_center_records(monkeypatch)

    def _hallucinating_reply(captured: dict[str, Any]) -> str:
        if captured.get("purpose") == "exploration_synthesis":
            return json.dumps(
                {
                    "headline": "Inbound averaged 99.4% in September 2026.",
                    "fact_ids": ["F1"],
                }
            )
        payload = json.loads(captured["messages"][-1]["content"])
        if not payload.get("collected_evidence"):
            return json.dumps(
                {
                    "action": "call_tools",
                    "unknown_code": "none",
                    "tools": [{"tool": "get_team_score_summary", "team": "Inbound", "period": "2026-09"}],
                }
            )
        return json.dumps({"action": "final_answer", "unknown_code": "none", "tools": []})

    install_scripted_provider(monkeypatch, [_hallucinating_reply], provider="cloudflare")
    with _build_in_memory_db() as db:
        result = run_bounded_exploration(
            db=db,
            scope=ADMIN_SCOPE,
            prompt="What is Inbound average score in September 2026?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            published_periods={"2026-08", "2026-09"},
            employee_candidates=[],
        )
    assert result.handled is True
    assert result.synthesis_validated is False
    assert result.fallback_reason in ("invented_number", "missing_fact_value")
    assert "99.4" not in result.headline


def test_explorer_cloudflare_valid_synthesis_passes_claim_validator(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "development")
    _seed_call_center_records(monkeypatch)

    def _valid_reply(captured: dict[str, Any]) -> str:
        payload = json.loads(captured["messages"][-1]["content"])
        if captured.get("purpose") == "exploration_synthesis":
            ledger = payload["facts"]
            f0 = ledger[0]
            return json.dumps(
                {
                    "headline": f"Inbound average score was {f0['display']} in September 2026.",
                    "fact_ids": [f["fact_id"] for f in ledger],
                }
            )
        if not payload.get("collected_evidence"):
            return json.dumps(
                {
                    "action": "call_tools",
                    "unknown_code": "none",
                    "tools": [{"tool": "get_team_score_summary", "team": "Inbound", "period": "2026-09"}],
                }
            )
        return json.dumps({"action": "final_answer", "unknown_code": "none", "tools": []})

    install_scripted_provider(monkeypatch, [_valid_reply], provider="cloudflare")
    with _build_in_memory_db() as db:
        result = run_bounded_exploration(
            db=db,
            scope=ADMIN_SCOPE,
            prompt="What is Inbound average score in September 2026?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            published_periods={"2026-08", "2026-09"},
            employee_candidates=[],
        )
    assert result.handled is True
    assert result.synthesis_validated is True
    assert result.fallback_reason == "none"
    assert "85.5%" in result.headline


def test_orchestrator_multi_turn_period_and_scope_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "true")
    _seed_call_center_records(monkeypatch)
    install_scripted_provider(monkeypatch, ['{"answer": "Deterministic fallback check"}'], provider="cloudflare")

    with _build_in_memory_db() as db:
        orch = PmsAiOrchestrator(db, ADMIN_SCOPE)
        turn1 = orch.run_chat_turn(
            AiChatRequest(
                prompt="What is Inbound overall score in August 2026?",
                conversation_id="conv-phase4-multi",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", month="August", year=2026),
            )
        )
        assert turn1.outcome == "answer"
        assert "August" in turn1.headline or "81.0%" in turn1.headline

        # Follow-up overrides period to September 2026 while preserving team scope
        turn2 = orch.run_chat_turn(
            AiChatRequest(
                prompt="Now show September 2026",
                conversation_id="conv-phase4-multi",
            )
        )
        assert turn2.outcome == "answer"
        assert "September" in turn2.headline

        # Follow-up overrides team to Outbound while keeping September 2026
        turn3 = orch.run_chat_turn(
            AiChatRequest(
                prompt="Switch to Outbound overall score",
                conversation_id="conv-phase4-multi",
            )
        )
        assert turn3.outcome == "answer"
        assert "Outbound" in turn3.headline


def test_orchestrator_cloudflare_rate_limit_falls_back_to_gemini_and_verifies_claims(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "development")
    _seed_call_center_records(monkeypatch)

    class _FallbackEngine:
        def generate(self, request: ProviderRequest) -> ProviderResponse:
            return ProviderResponse(
                content=json.dumps({"answer": "Inbound scored 85.5% in September 2026."}),
                provider="gemini",
                model="gemini-2.5-flash",
                outcome="success",
                latency_ms=4.0,
                attempts=[
                    ProviderAttempt(provider="cloudflare", model="@cf/ibm-granite/granite-4.0-h-micro", status="rate_limit", latency_ms=2.0),
                    ProviderAttempt(provider="gemini", model="gemini-2.5-flash", status="success", latency_ms=4.0),
                ],
            )

    monkeypatch.setattr(provider_engine, "_default_engine", _FallbackEngine())
    with _build_in_memory_db() as db:
        resp = PmsAiOrchestrator(db, ADMIN_SCOPE).run_chat_turn(
            AiChatRequest(
                prompt="What is Inbound overall score in September 2026?",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            )
        )
    assert resp.outcome == "answer"
    assert resp.provider_used == "gemini"
    assert "85.5%" in resp.headline


def test_orchestrator_defense_in_depth_rejects_hallucinated_gemini_synthesis(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "development")
    _seed_call_center_records(monkeypatch)
    install_scripted_provider(
        monkeypatch,
        [{"answer": "Inbound UAE averaged 99.9% in October 2026 because hiring paused."}],
        provider="gemini",
    )
    with _build_in_memory_db() as db:
        resp = PmsAiOrchestrator(db, ADMIN_SCOPE).run_chat_turn(
            AiChatRequest(
                prompt="What is Inbound overall score in September 2026?",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            )
        )
    assert resp.outcome == "answer"
    assert resp.provider_used == "deterministic"
    assert "99.9" not in resp.headline


def test_explorer_period_mismatch_in_synthesis_triggers_deterministic_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "development")
    _seed_call_center_records(monkeypatch)

    def _mismatched_period_reply(captured: dict[str, Any]) -> str:
        if captured.get("purpose") == "exploration_synthesis":
            return json.dumps(
                {
                    "headline": "Inbound average score was 85.5% in October 2026.",
                    "fact_ids": ["F1"],
                }
            )
        payload = json.loads(captured["messages"][-1]["content"])
        if not payload.get("collected_evidence"):
            return json.dumps(
                {
                    "action": "call_tools",
                    "unknown_code": "none",
                    "tools": [{"tool": "get_team_score_summary", "team": "Inbound", "period": "2026-09"}],
                }
            )
        return json.dumps({"action": "final_answer", "unknown_code": "none", "tools": []})

    install_scripted_provider(monkeypatch, [_mismatched_period_reply], provider="cloudflare")
    with _build_in_memory_db() as db:
        result = run_bounded_exploration(
            db=db,
            scope=ADMIN_SCOPE,
            prompt="What is Inbound average score in September 2026?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            published_periods={"2026-08", "2026-09"},
            employee_candidates=[],
        )
    assert result.handled is True
    assert result.synthesis_validated is False
    assert result.fallback_reason == "mismatched_period"
    assert "October" not in result.headline


@pytest.mark.skipif(
    os.getenv("PMS_AI_RUN_LIVE_MODEL_TESTS") != "true",
    reason="Live model tests require PMS_AI_RUN_LIVE_MODEL_TESTS=true",
)
def test_live_provider_smoke_validation_skipped_by_default():
    engine = provider_engine.get_unified_provider_engine()
    resp = engine.generate(
        ProviderRequest(
            purpose="smoke",
            system_instruction="Respond concisely.",
            messages=[{"role": "user", "content": "Say ok."}],
        )
    )
    assert resp.outcome == "success"
