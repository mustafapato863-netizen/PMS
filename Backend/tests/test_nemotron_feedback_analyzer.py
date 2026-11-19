"""Tests for Direct NVIDIA NIM Feedback Analyzer (Nemotron 3.5 Super VL)."""

from __future__ import annotations

import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import AiInteractionTrace, Employee, Team
from services.ai import nemotron_analyzer
from services.ai.config import redact_secrets
from services.ai.nemotron_analyzer import (
    NemotronFeedbackAnalyzerService,
    get_analyzer_status,
    reset_local_analyzer_budget,
)


def _setup_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _seed_trace(db, *, prompt: str, sanitized_prompt: str, feedback_reason: str = "Wrong intent"):
    trace = AiInteractionTrace(
        id=uuid.uuid4(),
        user_id="admin-1",
        role="Admin",
        prompt=prompt,
        sanitized_prompt=sanitized_prompt,
        session_state={"team": "Inbound", "branch": "dubai"},
        tool_calls=[{"tool_name": "get_team_scorecard"}],
        tool_digest={"plan": {"intent": "current_value", "team": "Inbound"}},
        structured_response={"headline": "Inbound scored 82.0% in September 2026."},
        provider_name="cloudflare",
        model_name="@cf/ibm-granite/granite-4.0-h-micro",
        latency_ms=420,
        non_empty_evidence=True,
        guardrail_triggered=False,
        feedback_rating="down",
        feedback_reason=feedback_reason,
        is_distillation_eligible=False,
        reviewer_verified=False,
    )
    db.add(trace)
    db.commit()
    return trace


def test_redact_secrets_scrubs_nvidia_api_keys():
    raw_bearer = "Authorization: Bearer nvapi-AbCdEf1234567890_secret_token failed"
    cleaned_bearer = redact_secrets(raw_bearer)
    assert "nvapi-" not in cleaned_bearer
    assert "[REDACTED_API_KEY]" in cleaned_bearer

    raw_bare = "key=nvapi-AbCdEf1234567890_secret_token failed"
    cleaned_bare = redact_secrets(raw_bare)
    assert "nvapi-" not in cleaned_bare
    assert "[REDACTED_API_KEY]" in cleaned_bare


def test_nvidia_model_strips_accidental_free_suffix(monkeypatch):
    monkeypatch.setenv("NVIDIA_FEEDBACK_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b:free")
    assert nemotron_analyzer._nvidia_model() == "nvidia/nemotron-3.5-super-vl-120b-a12b"


def test_analyzer_disabled_by_default_and_blocks_non_admin(monkeypatch):
    monkeypatch.delenv("PMS_AI_FEEDBACK_ANALYZER_ENABLED", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    status = get_analyzer_status()
    assert status.enabled is False
    assert status.configured is False

    db = _setup_db()
    trace = _seed_trace(db, prompt="Show Inbound rankings", sanitized_prompt="Show Inbound rankings")
    svc = NemotronFeedbackAnalyzerService(db)

    with pytest.raises(PermissionError):
        svc.analyze_trace(trace_id=str(trace.id), caller_role="Manager")

    res = svc.analyze_trace(trace_id=str(trace.id), caller_role="Admin")
    assert res.outcome == "disabled"


def test_privacy_gate_blocks_residual_pii_without_calling_nvidia(monkeypatch):
    reset_local_analyzer_budget()
    monkeypatch.setenv("PMS_AI_FEEDBACK_ANALYZER_ENABLED", "true")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-TestKey12345678901234567890")

    called = []
    monkeypatch.setattr(nemotron_analyzer, "_post_nvidia_chat_completions", lambda *a, **k: called.append(1))

    db = _setup_db()
    trace = _seed_trace(
        db,
        prompt="Contact maryam@hospital.com for EMP-9921 score",
        sanitized_prompt="Contact maryam@hospital.com for EMP-9921 score",
    )
    # Force assess_pii_quarantine to flag residual PII
    monkeypatch.setattr(
        nemotron_analyzer,
        "assess_pii_quarantine",
        lambda *_a, **_k: (True, ["residual_email_or_id"]),
    )

    res = NemotronFeedbackAnalyzerService(db).analyze_trace(trace_id=str(trace.id), caller_role="Admin")
    assert res.outcome == "blocked_pii_quarantine"
    assert "residual_email_or_id" in res.quarantine_reasons
    assert called == []  # ZERO outbound HTTP calls made


def test_analyze_trace_persists_caches_and_enforces_screenshot_attestation(monkeypatch):
    reset_local_analyzer_budget()
    monkeypatch.setenv("PMS_AI_FEEDBACK_ANALYZER_ENABLED", "true")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-TestKey12345678901234567890")
    monkeypatch.setenv("PMS_AI_FEEDBACK_ANALYZER_DAILY_LIMIT", "2")

    calls: list[dict] = []

    def _fake_nim(messages, **_kwargs):
        calls.append({"messages": messages})
        return {
            "root_cause_category": "intent_misclassification",
            "root_cause_summary": "Query asked for top performer ranking but routed to team scorecard.",
            "why_answer_failed": ["Missing ranking keyword alias for MVP badge"],
            "recommended_system_fix": "Add 'mvp badge' to ranking trigger phrases.",
            "suggested_pattern": {
                "corrected_pattern_prompt": "Who holds the <TEAM> mvp badge in <MONTH> <YEAR>?",
                "intent": "ranking",
                "operation_kind": "ranking_top",
                "metric_hint": "overall_score",
                "persona_tier": "scoped_manager",
            },
            "suggested_dpo_chosen_outline": "State top performer name, score, and period for Inbound.",
            "confidence": 0.91,
        }

    monkeypatch.setattr(nemotron_analyzer, "_post_nvidia_chat_completions", _fake_nim)

    db = _setup_db()
    trace = _seed_trace(
        db,
        prompt="Who holds the Inbound mvp badge in September 2026?",
        sanitized_prompt="Who holds the Inbound mvp badge in September 2026?",
    )
    svc = NemotronFeedbackAnalyzerService(db)

    # Screenshot without attestation rejected with ValueError
    with pytest.raises(ValueError, match="confirmation"):
        svc.analyze_trace(
            trace_id=str(trace.id),
            caller_role="Admin",
            screenshot_data_url="data:image/png;base64,iVBORw0KGgo=",
            screenshot_pii_free_attested=False,
        )

    # First call hits NVIDIA NIM and persists
    res1 = svc.analyze_trace(trace_id=str(trace.id), caller_role="Admin", caller_user_id="admin-1")
    assert res1.outcome == "analyzed"
    assert res1.cached is False
    assert res1.root_cause_category == "intent_misclassification"
    assert res1.suggested_pattern is not None
    assert res1.suggested_pattern.intent == "ranking"
    assert len(calls) == 1

    # Second call returns cached analysis with ZERO new NVIDIA calls
    res2 = svc.analyze_trace(trace_id=str(trace.id), caller_role="Admin")
    assert res2.outcome == "analyzed"
    assert res2.cached is True
    assert len(calls) == 1

    # Force refresh consumes 2nd budget slot
    res3 = svc.analyze_trace(trace_id=str(trace.id), caller_role="Admin", force_refresh=True)
    assert res3.outcome == "analyzed"
    assert res3.cached is False
    assert len(calls) == 2

    # 3rd forced call hits daily limit (2/day)
    res4 = svc.analyze_trace(trace_id=str(trace.id), caller_role="Admin", force_refresh=True)
    assert res4.outcome == "rate_limited"
    assert len(calls) == 2
    reset_local_analyzer_budget()


def test_cluster_batch_analysis_summarizes_redacted_traces(monkeypatch):
    reset_local_analyzer_budget()
    monkeypatch.setenv("PMS_AI_FEEDBACK_ANALYZER_ENABLED", "true")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-TestKey12345678901234567890")

    monkeypatch.setattr(
        nemotron_analyzer,
        "_post_nvidia_chat_completions",
        lambda *_a, **_k: {
            "primary_root_cause": "missing_kpi_alias",
            "executive_summary": "Multiple queries used 'conversion' instead of 'Booking Rate'.",
            "recurring_issues": ["Alias mismatch for conversion rate"],
            "recommended_engineering_fixes": ["Add 'conversion' alias in domain_policies.py"],
            "suggested_pattern": {
                "corrected_pattern_prompt": "Show <TEAM> conversion rate in <MONTH> <YEAR>",
                "intent": "current_value",
                "metric_hint": "booking_rate",
            },
            "confidence": 0.88,
        },
    )

    db = _setup_db()
    _seed_trace(db, prompt="Show Inbound conversion in September 2026", sanitized_prompt="Show Inbound conversion in September 2026")
    _seed_trace(db, prompt="What is Inbound conversion rate in September 2026", sanitized_prompt="What is Inbound conversion rate in September 2026")

    res = NemotronFeedbackAnalyzerService(db).analyze_cluster(
        caller_role="Admin",
        caller_user_id="admin-1",
        scope_team="Inbound",
    )
    assert res.outcome == "analyzed"
    assert res.traces_analyzed == 2
    assert res.primary_root_cause == "missing_kpi_alias"
    assert res.suggested_pattern is not None
    assert res.suggested_pattern.metric_hint == "booking_rate"
    reset_local_analyzer_budget()


def test_export_bundle_enriches_approved_trace_with_redacted_nemotron_analysis():
    from services.ai.feedback_service import FeedbackGovernanceService

    db = _setup_db()
    trace = _seed_trace(
        db,
        prompt="Show Inbound rankings in September 2026",
        sanitized_prompt="Show Inbound rankings in September 2026",
    )
    trace.reviewer_verified = True
    trace.structured_response = {
        "feedback_governance": {
            "surface": "workspace_chat",
            "rating": "down",
            "reason_tag": "misunderstood_question",
            "comment_redacted": "Expected ranking table",
            "review_status": "approved",
            "reviewer_verified": True,
            "scope_team": "Inbound",
            "cohort_size": 12,
            "pii_quarantined": False,
        },
        "nemotron_analysis": {
            "outcome": "analyzed",
            "root_cause_category": "intent_misclassification",
            "suggested_dpo_chosen_outline": "Return the Inbound agent ranking table for September 2026.",
        },
    }
    db.commit()

    bundle = FeedbackGovernanceService(db).build_deidentified_export_bundle(
        caller_role="Admin",
        caller_user_id="admin-1",
    )
    assert bundle.exported_count == 1
    item = bundle.items[0]
    assert item.root_cause_category == "intent_misclassification"
    assert item.suggested_dpo_chosen_outline == "Return the Inbound agent ranking table for September 2026."
