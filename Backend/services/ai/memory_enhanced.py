"""Memory-enhanced model engine helpers.

Uses stored user memory to personalize intent classification, response
formatting, evidence selection, and follow-up suggestions.
"""

from __future__ import annotations

from typing import Any


def get_memory_preferred_detail_level(memory: dict[str, Any] | None) -> str:
    """Return the user's preferred detail level from memory."""
    if not memory:
        return "auto"
    prefs = memory.get("preferences", {})
    return str(prefs.get("detail_level") or "auto")


def get_memory_preferred_teams(memory: dict[str, Any] | None) -> list[str]:
    """Return the user's preferred teams from memory."""
    if not memory:
        return []
    prefs = memory.get("preferences", {})
    return list(prefs.get("preferred_teams") or [])


def get_memory_preferred_metrics(memory: dict[str, Any] | None) -> list[str]:
    """Return the user's preferred metrics from memory."""
    if not memory:
        return []
    prefs = memory.get("preferences", {})
    return list(prefs.get("preferred_metrics") or [])


def get_memory_frequent_topics(memory: dict[str, Any] | None) -> list[str]:
    """Return the user's frequently asked topics from memory."""
    if not memory:
        return []
    patterns = memory.get("query_patterns", {})
    return list(patterns.get("frequent_topics") or [])


def get_memory_frequent_teams(memory: dict[str, Any] | None) -> list[str]:
    """Return the user's frequently asked teams (sorted by frequency)."""
    if not memory:
        return []
    patterns = memory.get("query_patterns", {})
    freq = patterns.get("frequent_teams", {})
    if not isinstance(freq, dict):
        return []
    return [t for t, _ in sorted(freq.items(), key=lambda x: -x[1])]


def get_memory_frequent_kpis(memory: dict[str, Any] | None) -> list[str]:
    """Return the user's frequently asked KPIs (sorted by frequency)."""
    if not memory:
        return []
    patterns = memory.get("query_patterns", {})
    freq = patterns.get("frequent_kpis", {})
    if not isinstance(freq, dict):
        return []
    return [k for k, _ in sorted(freq.items(), key=lambda x: -x[1])]


def enhance_followups_with_memory(
    base_followups: list[str],
    memory: dict[str, Any] | None,
    max_followups: int = 3,
) -> list[str]:
    """Enhance follow-up suggestions using user memory.

    Prepends memory-based follow-ups (preferred teams, frequent topics)
    to the base list, deduplicating and capping at max_followups.
    """
    if not memory:
        return base_followups[:max_followups]

    enhanced = list(base_followups)
    prefs = memory.get("preferences", {})
    patterns = memory.get("query_patterns", {})

    # Add preferred team follow-ups
    for team in (prefs.get("preferred_teams") or [])[:2]:
        followup = f"Show {team} performance summary"
        if followup not in enhanced:
            enhanced.insert(0, followup)

    # Add frequent topic follow-ups
    for topic in (patterns.get("frequent_topics") or [])[:1]:
        if topic and topic not in " ".join(enhanced).lower():
            followup = f"Drill into {topic} details"
            if followup not in enhanced:
                enhanced.insert(0, followup)

    # Deduplicate preserving order
    seen = set()
    result = []
    for f in enhanced:
        if f not in seen:
            seen.add(f)
            result.append(f)
    return result[:max_followups]


def should_use_brief_mode(memory: dict[str, Any] | None) -> bool | None:
    """Return True if user prefers brief mode, False if detailed, None if auto."""
    level = get_memory_preferred_detail_level(memory)
    if level == "brief":
        return True
    if level == "detailed":
        return False
    return None
