"""Tests for Model Enhancement Flywheel helpers."""

import pytest
from datetime import datetime, timezone, timedelta

from services.ai.model_flywheel import (
    build_dpo_structured_response,
    detect_rephrase_signal,
    detect_abandon_signal,
    filter_patterns_by_passport,
    deidentify_export_row,
    safe_evidence_block,
)
from services.ai.identity_service import build_passport, PersonaTier


def test_dpo_structured_response_caps_rejected():
    result = build_dpo_structured_response({"h": "ok"}, {"h": "x" * 2000}, "hallucination")
    assert result["dpo_pair"] is True
    assert len(result["rejected"]) == 1024
    assert result["rejection_reason"] == "hallucination"


def test_detect_rephrase_signal():
    now = datetime.now(timezone.utc)
    prev = {"created_at": now.isoformat()}
    curr = {"created_at": (now + timedelta(seconds=12)).isoformat()}
    result = detect_rephrase_signal(prev, curr)
    assert result is not None
    assert result["friction"] == "rephrase"
    assert result["gap_seconds"] == 12.0


def test_detect_rephrase_signal_outside_window():
    now = datetime.now(timezone.utc)
    prev = {"created_at": now.isoformat()}
    curr = {"created_at": (now + timedelta(seconds=60)).isoformat()}
    assert detect_rephrase_signal(prev, curr) is None


def test_detect_abandon_signal():
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    result = detect_abandon_signal({"created_at": old})
    assert result is not None
    assert result["friction"] == "abandoned"


def test_filter_patterns_by_passport_agent():
    scope = {"role": "Employee", "employee_id": "EMP-1", "accessible_teams": []}
    passport = build_passport(scope)
    assert passport.persona_tier == PersonaTier.SELF_ONLY
    patterns = [
        {"intent": "a", "persona_tier": None},
        {"intent": "b", "persona_tier": "self_only"},
        {"intent": "c", "persona_tier": "global_exec"},
    ]
    result = filter_patterns_by_passport(patterns, passport)
    assert [p["intent"] for p in result] == ["a", "b"]


def test_filter_patterns_no_passport():
    patterns = [{"intent": "a", "persona_tier": None}, {"intent": "b", "persona_tier": "self_only"}]
    assert filter_patterns_by_passport(patterns, None) == [patterns[0]]


def test_deidentify_export_row_small_cohort():
    row = {"cohort_size": 3, "employee_code": "EMP-1", "score": 85.0}
    result = deidentify_export_row(row)
    assert result["cohort_size"] is None
    assert result["cohort_deidentified"] is True
    assert result["employee_code"] == "[REDACTED]"
    assert result["score"] == 85.0


def test_safe_evidence_block_escapes():
    block = safe_evidence_block("<script>alert(1)</script>")
    assert "&lt;script&gt;" in block
    assert "<script>" not in block
