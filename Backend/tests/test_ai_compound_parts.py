"""Focused PR 2 regression tests: compound multi-part planning, bilingual normalization, and reversible toggle."""

from __future__ import annotations

from models.ai_schemas import AiChatRequest, SessionFilterContext
from scripts.run_unseen_eval import _build_eval_records
from services.ai.catalog import ai_evidence_cache
from services.ai.compound_parts_planner import (
    compound_parts_enabled,
    compute_target_gap_fact,
    plan_compound_parts,
    render_compound_parts_answer,
    verify_compound_answer_completeness,
)
from services.ai.orchestrator import PmsAiOrchestrator
from test_ai_workspace import _build_in_memory_db, _patch_records


def _admin_scope() -> dict:
    return {"user_id": "u-test-admin", "role": "Admin", "permissions": ["*"], "has_unrestricted_team_access": True}


def test_compound_plan_and_target_gap_unit_direction():
    plan = plan_compound_parts(
        "September, Nadia Fadel. Waiting Time and overall PMS please. How far off target?",
        team="Pharmacy",
    )
    assert plan.is_compound is True
    assert plan.asks_overall_score is True
    assert plan.asks_target_gap is True
    assert "overall_score" in plan.requested_metrics

    gap = compute_target_gap_fact(
        actual=6.2,
        target=5.0,
        unit="min",
        direction="lower_better",
        metric_label="Waiting Time",
    )
    assert gap["met_target"] is False
    assert gap["gap_value"] == 1.2
    assert "min" in gap["summary"]


def test_nadia_fadel_compound_answers_all_parts_despite_passive_call_center_session(monkeypatch):
    db = _build_in_memory_db()
    try:
        _patch_records(monkeypatch, _build_eval_records())
        ai_evidence_cache.clear()
        orch = PmsAiOrchestrator(db, _admin_scope())
        resp = orch.run_chat_turn(
            AiChatRequest(
                prompt="September, Nadia Fadel. Waiting Time and overall PMS please. How far off target?",
                session_state=SessionFilterContext(function="Call Center", month="September", year=2026),
                provider_override="deterministic",
            )
        )
        assert resp.outcome == "answer", resp.headline
        text = " ".join([resp.headline, *resp.narrative_bullets]).casefold()
        assert "nadia fadel" in text
        assert "6.2" in text
        assert "87.5" in text
        assert "5" in text
        assert "1.2" in text
    finally:
        ai_evidence_cache.clear()
        db.close()


def test_arabic_person_and_mixed_followup_target_gap(monkeypatch):
    db = _build_in_memory_db()
    try:
        _patch_records(monkeypatch, _build_eval_records())
        ai_evidence_cache.clear()
        orch = PmsAiOrchestrator(db, _admin_scope())
        turn1 = orch.run_chat_turn(
            AiChatRequest(
                prompt="نادية فاضل في سبتمبر وقت الانتظار كام؟",
                session_state=SessionFilterContext(function="Call Center", month="September", year=2026),
                provider_override="deterministic",
            )
        )
        assert turn1.outcome == "answer", turn1.headline
        assert "6.2" in turn1.headline
        assert "nadia fadel" in turn1.headline.casefold()

        turn2 = orch.run_chat_turn(
            AiChatRequest(
                prompt="طيب كانت أعلى من التارجت بكام؟",
                conversation_id=turn1.conversation_id,
                context_version=turn1.context_version,
                session_state=turn1.resolved_session_state or SessionFilterContext(),
                history=[
                    {"role": "user", "content": "نادية فاضل في سبتمبر وقت الانتظار كام؟"},
                    {"role": "assistant", "content": turn1.headline},
                ],
                provider_override="deterministic",
            )
        )
        assert turn2.outcome == "answer", turn2.headline
        t2_text = " ".join([turn2.headline, *turn2.narrative_bullets]).casefold()
        assert "1.2" in t2_text
        assert "5" in t2_text
    finally:
        ai_evidence_cache.clear()
        db.close()


def test_multi_kpi_target_gap_clarification_before_single_kpi_resolved(monkeypatch):
    db = _build_in_memory_db()
    try:
        _patch_records(monkeypatch, _build_eval_records())
        ai_evidence_cache.clear()
        orch = PmsAiOrchestrator(db, _admin_scope())
        turn1 = orch.run_chat_turn(
            AiChatRequest(
                prompt="Show Sara Mahmoud's Booking Rate and Attendance Rate in September 2026.",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
                provider_override="deterministic",
            )
        )
        assert turn1.outcome == "answer"
        turn2 = orch.run_chat_turn(
            AiChatRequest(
                prompt="How far from target was she?",
                conversation_id=turn1.conversation_id,
                context_version=turn1.context_version,
                session_state=turn1.resolved_session_state or SessionFilterContext(),
                history=[
                    {"role": "user", "content": "Show Sara Mahmoud's Booking Rate and Attendance Rate in September 2026."},
                    {"role": "assistant", "content": turn1.headline},
                ],
                provider_override="deterministic",
            )
        )
        assert turn2.outcome == "clarification", turn2.headline
        assert turn2.clarification is not None
        assert turn2.clarification.code == "AMBIGUOUS_KPI_SCOPE"
    finally:
        ai_evidence_cache.clear()
        db.close()


def test_partial_period_comparison_and_unsupported_email_notice(monkeypatch):
    db = _build_in_memory_db()
    try:
        _patch_records(monkeypatch, _build_eval_records())
        ai_evidence_cache.clear()
        orch = PmsAiOrchestrator(db, _admin_scope())
        resp = orch.run_chat_turn(
            AiChatRequest(
                prompt="Compare Coding EGY overall score in October 2026 vs September 2026, and email the summary to the manager.",
                session_state=SessionFilterContext(function="RCM", team="Coding EGY"),
                provider_override="deterministic",
            )
        )
        combined = " ".join([resp.headline, *resp.narrative_bullets]).casefold()
        assert "october 2026" in combined
        assert "89.0%" in combined
        assert "cannot" in combined or "not sent" in combined
    finally:
        ai_evidence_cache.clear()
        db.close()


def test_compound_parts_flag_reversible_and_completeness_check(monkeypatch):
    assert compound_parts_enabled() is True
    plan = plan_compound_parts(
        "Show Nadia Fadel Waiting Time and overall PMS, then send an email.",
        team="Pharmacy",
    )
    headline, bullets, contract = render_compound_parts_answer(
        plan=plan,
        subject_name="Nadia Fadel",
        team_name="Pharmacy",
        period_label="September 2026",
        kpi_evidence={"display_name": "Waiting Time", "actual": 6.2, "target": 5.0, "unit": "min", "direction": "lower_better"},
        overall_score_val=87.5,
    )
    ok, missing = verify_compound_answer_completeness(
        plan,
        headline + " " + " ".join(bullets),
        required_groups=contract["required_groups"],
    )
    assert ok is True, missing

    monkeypatch.setenv("PMS_AI_COMPOUND_PARTS_ENABLED", "false")
    assert compound_parts_enabled() is False
