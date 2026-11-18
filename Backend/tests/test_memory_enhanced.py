"""Tests for memory-enhanced model engine helpers."""

import pytest

from services.ai.memory_enhanced import (
    enhance_followups_with_memory,
    get_memory_frequent_kpis,
    get_memory_frequent_teams,
    get_memory_frequent_topics,
    get_memory_preferred_detail_level,
    get_memory_preferred_metrics,
    get_memory_preferred_teams,
    should_use_brief_mode,
)


def test_preferred_detail_level_default():
    assert get_memory_preferred_detail_level(None) == "auto"
    assert get_memory_preferred_detail_level({}) == "auto"


def test_preferred_detail_level_from_memory():
    memory = {"preferences": {"detail_level": "brief"}}
    assert get_memory_preferred_detail_level(memory) == "brief"


def test_preferred_teams():
    assert get_memory_preferred_teams(None) == []
    memory = {"preferences": {"preferred_teams": ["Inbound", "Outbound"]}}
    assert get_memory_preferred_teams(memory) == ["Inbound", "Outbound"]


def test_preferred_metrics():
    assert get_memory_preferred_metrics(None) == []
    memory = {"preferences": {"preferred_metrics": ["Booking Rate"]}}
    assert get_memory_preferred_metrics(memory) == ["Booking Rate"]


def test_frequent_topics():
    assert get_memory_frequent_topics(None) == []
    memory = {"query_patterns": {"frequent_topics": ["score", "trend"]}}
    assert get_memory_frequent_topics(memory) == ["score", "trend"]


def test_frequent_teams_sorted():
    memory = {"query_patterns": {"frequent_teams": {"Outbound": 2, "Inbound": 5}}}
    assert get_memory_frequent_teams(memory) == ["Inbound", "Outbound"]


def test_frequent_kpis_sorted():
    memory = {"query_patterns": {"frequent_kpis": {"Attendance Rate": 3, "Booking Rate": 8}}}
    assert get_memory_frequent_kpis(memory) == ["Booking Rate", "Attendance Rate"]


def test_enhance_followups_no_memory():
    base = ["Show Inbound summary", "Compare teams"]
    assert enhance_followups_with_memory(base, None) == base[:3]


def test_enhance_followups_with_memory():
    memory = {
        "preferences": {"preferred_teams": ["Outbound"]},
        "query_patterns": {"frequent_topics": ["trend"]},
    }
    base = ["Show Inbound summary"]
    result = enhance_followups_with_memory(base, memory)
    assert "Show Outbound performance summary" in result
    assert "Drill into trend details" in result
    assert len(result) <= 3


def test_should_use_brief_mode():
    assert should_use_brief_mode(None) is None
    assert should_use_brief_mode({"preferences": {"detail_level": "brief"}}) is True
    assert should_use_brief_mode({"preferences": {"detail_level": "detailed"}}) is False
    assert should_use_brief_mode({"preferences": {"detail_level": "auto"}}) is None
