from __future__ import annotations

import json
import os

import pytest

from ai_provider_fakes import install_scripted_provider

from services.ai.local_evidence_synthesis import (
    BranchBookingFacts,
    OverallScoreFacts,
    _validated_answer,
    _validated_score_answer,
    extract_branch_booking_facts,
    extract_overall_score_facts,
    synthesize_branch_bookings,
    synthesize_overall_score,
)


def evidence():
    return [{"period": "September 2026", "scope": "Inbound", "requested_branches": ["Dubai", "Sharjah"], "branch_comparison": [{"branch": "Dubai", "bookings": 180}, {"branch": "Sharjah", "bookings": 70}, {"branch": "Ajman", "bookings": 40}]}]


def test_extracts_only_requested_branch_counts_and_rejects_other_metrics():
    question = "Which branch had more Inbound bookings, Dubai or Sharjah?"
    assert extract_branch_booking_facts(question, evidence()) == BranchBookingFacts("September 2026", "Inbound", (("Dubai", 180), ("Sharjah", 70)))
    assert extract_branch_booking_facts("Compare Dubai and Sharjah booking rate", evidence()) is None
    assert extract_branch_booking_facts("Compare Dubai and Sharjah bookings and attendance", evidence()) is None
    assert extract_branch_booking_facts("Who is responsible for Dubai and Sharjah bookings?", evidence()) is None


def test_generated_answer_is_checked_for_values_scope_and_order():
    facts = BranchBookingFacts("September 2026", "Inbound", (("Dubai", 180), ("Sharjah", 70)))
    assert _validated_answer("Inbound bookings in September 2026: Dubai 180, Sharjah 70.", facts)
    assert not _validated_answer("Inbound bookings in September 2026: Dubai 70, Sharjah 180.", facts)
    assert not _validated_answer("Inbound bookings in September 2026: Sharjah 70, Dubai 180.", facts)
    assert not _validated_answer("Inbound bookings in September 2026: Dubai 180, Sharjah 70, Ajman 40.", facts)
    assert not _validated_answer("Inbound bookings in September 2026: Dubai 180, Sharjah 70. Alice approved it.", facts)
    assert not _validated_answer("Inbound bookings in September 2026: Dubai 180%, Sharjah 70%.", facts)
    assert not _validated_answer("Inbound bookings in September 2026: Dubai 180, Sharjah 70. Dubai had fewer.", facts)
    assert not _validated_answer("Inbound bookings in September 2026: Dubai 180, Sharjah 70 leads.", facts)


def test_model_receives_scoped_facts_and_validated_output_is_used(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    captured = install_scripted_provider(
        monkeypatch, {"answer": "Inbound bookings in September 2026: Dubai 180, Sharjah 70."}
    )
    response = synthesize_branch_bookings("Compare Dubai and Sharjah Inbound bookings", evidence())
    assert response is not None and response.provider_used == "cloudflare"
    assert response.headline == "Inbound bookings in September 2026: Dubai 180, Sharjah 70."
    sent = json.loads(captured[0]["messages"][1]["content"])
    assert sent['bookings'] == {'Dubai': 180, 'Sharjah': 70}
    assert 'Ajman' not in json.dumps(sent)


def test_invalid_model_output_falls_back_to_verified_counts(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    install_scripted_provider(monkeypatch, {"answer": "Inbound bookings in September 2026: Dubai 70, Sharjah 180."})
    response = synthesize_branch_bookings("Compare Dubai and Sharjah Inbound bookings", evidence())
    assert response is not None and response.provider_used == "deterministic"
    assert "Dubai: 180" in response.headline and "Sharjah: 70" in response.headline
    assert response.metrics.fallback_outcome == "invalid_or_unverified_response"


def test_provider_unavailable_falls_back_to_verified_counts(monkeypatch):
    from ai_provider_fakes import failed_response

    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    install_scripted_provider(monkeypatch, failed_response("provider_unavailable"))
    response = synthesize_branch_bookings("Compare Dubai and Sharjah Inbound bookings", evidence())
    assert response is not None and response.provider_used == "deterministic"
    assert response.metrics.fallback_outcome == "provider_unavailable"


def test_zero_or_missing_booking_evidence_does_not_claim_a_measured_zero(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    data = evidence()
    data[0]["branch_comparison"][1]["bookings"] = 0
    install_scripted_provider(monkeypatch, lambda _req: pytest.fail("missing evidence sent to model"))
    response = synthesize_branch_bookings("Compare Dubai and Sharjah Inbound bookings", data)
    assert response is not None and "zero or missing" in response.headline
    assert response.metrics.fallback_outcome == "zero_or_missing_evidence"


def test_score_synthesis_requires_single_valid_scoped_score():
    data = [{"period": "September 2026", "scope": "Inbound", "branch": "All Branches", "average_score": 85.0, "total_records": 2}]
    facts = OverallScoreFacts("September 2026", "Inbound", "All Branches", 85.0)
    assert extract_overall_score_facts("What is Inbound score in September 2026?", data) == facts
    assert extract_overall_score_facts("What is Inbound score and who is the best?", data) is None
    assert extract_overall_score_facts("How has Inbound performance changed?", data) is None
    assert _validated_score_answer("Inbound scored 85.0% in September 2026.", facts)
    assert not _validated_score_answer("Inbound scored 85.0 in September 2026.", facts)
    assert not _validated_score_answer("Inbound scored 90.0% in September 2026.", facts)
    assert not _validated_score_answer("Inbound scored 85.0% in September 2026, above target.", facts)
    assert not _validated_score_answer("Inbound scored 85.0% in September 2026, Alice approved it.", facts)


def test_model_can_compose_a_scoped_score_and_fallback_rejects_added_claims(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    data = [{"period": "September 2026", "scope": "Inbound", "branch": "All Branches", "average_score": 85.0, "total_records": 2}]
    model_answer = ["Inbound scored 85.0% in September 2026."]

    def reply(request):
        sent = json.loads(request["messages"][1]["content"])
        assert sent['overall_score_percent'] == 85.0
        return {'answer': model_answer[0]}

    install_scripted_provider(monkeypatch, reply)
    response = synthesize_overall_score("What is Inbound score?", data)
    assert response is not None and response.provider_used == 'cloudflare'
    assert response.headline == model_answer[0]
    model_answer[0] = "Inbound scored 99.0% in September 2026."
    fallback = synthesize_overall_score("What is Inbound score?", data)
    assert fallback is not None and fallback.provider_used == 'deterministic'
    assert fallback.headline == "Inbound scored 85.0% in September 2026."


def test_denied_scope_never_sends_evidence_to_model(monkeypatch):
    from test_ai_workspace import _build_in_memory_db, _make_call_center_record, _patch_records
    from models.ai_schemas import AiChatRequest, SessionFilterContext
    from services.ai.orchestrator import PmsAiOrchestrator

    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    _patch_records(monkeypatch, [_make_call_center_record("EMP001", "Alice Example", "Inbound", 80, 10, 30, 40, 60)])
    monkeypatch.setattr("services.ai.orchestrator.synthesize_branch_bookings", lambda *args: pytest.fail("restricted evidence reached model"))
    with _build_in_memory_db() as db:
        response = PmsAiOrchestrator(db, {"role": "Manager", "has_unrestricted_team_access": False, "accessible_teams": ["Outbound"], "accessible_functions": ["Call Center"]}).run_chat_turn(
            AiChatRequest(prompt="Compare Dubai and Sharjah Inbound bookings", session_state=SessionFilterContext(function="Call Center", month="September", year=2026))
        )
    assert response.outcome == "restricted_access"


def test_assistant_uses_model_after_fetching_scoped_branch_counts(monkeypatch):
    from test_ai_workspace import _build_in_memory_db, _make_call_center_record, _patch_records
    from models.ai_schemas import AiChatRequest, SessionFilterContext
    from services.ai.catalog import ai_evidence_cache
    from services.ai.orchestrator import PmsAiOrchestrator

    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    records = [
        _make_call_center_record("EMP001", "Alice Example", "Inbound", 80, 10, 30, 40, 120),
        _make_call_center_record("EMP002", "Bob Example", "Inbound", 90, 20, 40, 30, 60),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()

    def reply(request):
        sent = json.loads(request["messages"][1]["content"])
        assert sent['bookings'] == {'Dubai': 180, 'Sharjah': 70}
        return {'answer': 'Inbound bookings in September 2026: Dubai 180, Sharjah 70.'}

    install_scripted_provider(monkeypatch, reply)
    with _build_in_memory_db() as db:
        response = PmsAiOrchestrator(db, {'role': 'Admin', 'has_unrestricted_team_access': True}).run_chat_turn(
            AiChatRequest(prompt='Compare Dubai and Sharjah Inbound bookings in September 2026.', session_state=SessionFilterContext(function='Call Center', month='September', year=2026))
        )
    assert response.outcome == 'answer'
    assert response.provider_used == 'cloudflare'
    assert response.headline == 'Inbound bookings in September 2026: Dubai 180, Sharjah 70.'
    assert response.visual_cards == []
    assert response.scope_banner.startswith('Dubai vs Sharjah')
    assert any(item.label == 'Branches · Dubai, Sharjah' for item in response.citations)
    assert not any('Attended' in item.label for item in response.citations)
    assert response.basis_warning is None


def test_assistant_uses_model_after_fetching_scoped_overall_score(monkeypatch):
    from test_ai_workspace import _build_in_memory_db, _make_call_center_record, _patch_records
    from models.ai_schemas import AiChatRequest, SessionFilterContext
    from services.ai.catalog import ai_evidence_cache
    from services.ai.orchestrator import PmsAiOrchestrator

    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    records = [
        _make_call_center_record("EMP001", "Alice Example", "Inbound", 80, 10, 30, 40, 120),
        _make_call_center_record("EMP002", "Bob Example", "Inbound", 90, 20, 40, 30, 60),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()

    def reply(request):
        sent = json.loads(request["messages"][1]["content"])
        assert sent['overall_score_percent'] == 85.0
        return {'answer': 'Inbound scored 85.0% in September 2026.'}

    install_scripted_provider(monkeypatch, reply)
    with _build_in_memory_db() as db:
        response = PmsAiOrchestrator(db, {'role': 'Admin', 'has_unrestricted_team_access': True}).run_chat_turn(
            AiChatRequest(prompt='What is Inbound score in September 2026?', session_state=SessionFilterContext(function='Call Center', month='September', year=2026))
        )
    assert response.outcome == 'answer'
    assert response.provider_used == 'cloudflare'
    assert response.headline == 'Inbound scored 85.0% in September 2026.'
    assert response.visual_cards == []
    assert response.basis_warning is None


@pytest.mark.skipif(os.environ.get("PMS_AI_RUN_LIVE_MODEL_TESTS") != "true", reason="requires live Cloudflare/Gemini credentials")
def test_live_model_writes_branch_comparison_from_supplied_counts(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    response = synthesize_branch_bookings("Which branch had more Inbound bookings, Dubai or Sharjah?", evidence())
    assert response is not None and response.provider_used in ("cloudflare", "gemini"), response
    assert _validated_answer(response.headline, BranchBookingFacts("September 2026", "Inbound", (("Dubai", 180), ("Sharjah", 70))))


@pytest.mark.skipif(os.environ.get("PMS_AI_RUN_LIVE_MODEL_TESTS") != "true", reason="requires live Cloudflare/Gemini credentials")
def test_live_model_writes_overall_score_from_supplied_facts(monkeypatch):
    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    data = [{"period": "September 2026", "scope": "Inbound", "branch": "All Branches", "average_score": 85.0, "total_records": 2}]
    response = synthesize_overall_score("What is the Inbound score?", data)
    assert response is not None and response.provider_used in ("cloudflare", "gemini"), response
    assert _validated_score_answer(response.headline, OverallScoreFacts("September 2026", "Inbound", "All Branches", 85.0))
