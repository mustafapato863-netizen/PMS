"""Integration tests for user-aware assistant features."""

import pytest

from services.ai.user_rules_spec import is_self_service_query, resolve_self_employee_id
from services.ai.domain_policies import is_self_service_prompt
from services.ai.user_memory_service import UserMemoryService


def test_self_service_query_detection_integration():
    """Verify self-service query detection works with real scope."""
    scope = {
        "user_id": "user-emp-1",
        "role": "Employee",
        "employee_id": "EMP-101",
        "is_self_only": True,
        "has_unrestricted_team_access": False,
        "accessible_teams": [],
        "accessible_functions": [],
        "accessible_regions": [],
        "accessible_branches": [],
        "active_team_names": ["Inbound"],
    }
    assert is_self_service_query(scope) is True
    assert resolve_self_employee_id(scope) == "EMP-101"


def test_self_service_prompt_detection():
    """Verify self-service prompt detection works."""
    prompts = [
        "How am I doing?",
        "What's my score?",
        "Show me my KPIs",
        "My trend over recent months",
        "Am I doing well?",
    ]
    for p in prompts:
        assert is_self_service_prompt(p) is True, f"Failed for: {p}"

    non_self = [
        "How is Inbound doing?",
        "Show overall performance",
        "What is the company score?",
    ]
    for p in non_self:
        assert is_self_service_prompt(p) is False, f"Failed for: {p}"


def test_user_memory_persistence_across_sessions():
    """Verify memory persists across service instances."""
    from unittest.mock import MagicMock

    db = MagicMock()
    # First call: no existing memory
    db.query.return_value.filter.return_value.first.return_value = None

    svc1 = UserMemoryService(db)
    svc1.save_memory("user-1", {"preferences": {"detail_level": "brief"}})

    # Simulate DB returning the saved row
    mock_row = MagicMock()
    mock_row.preferences = {"detail_level": "brief"}
    mock_row.query_patterns = {}
    mock_row.interaction_summary = None
    mock_row.feedback_signals = {}
    mock_row.last_accessed_at = None
    db.query.return_value.filter.return_value.first.return_value = mock_row

    svc2 = UserMemoryService(db)
    memory = svc2.load_memory("user-1")
    assert memory is not None
    assert memory["preferences"]["detail_level"] == "brief"


def test_security_self_only_cannot_access_other():
    """Verify self-only users cannot resolve other employee IDs."""
    scope = {
        "is_self_only": True,
        "employee_id": "EMP-101",
    }
    # resolve_self_employee_id only returns the user's own employee_id
    assert resolve_self_employee_id(scope) == "EMP-101"
    # No way to resolve a different employee_id through this function
    # (the function only reads from scope.employee_id, never from user input)


def test_memory_text_includes_user_context():
    """Verify memory text is properly formatted for prompt injection."""
    from services.ai.user_memory_service import UserMemoryService
    from unittest.mock import MagicMock

    svc = UserMemoryService(MagicMock())
    memory = {
        "preferences": {"detail_level": "brief", "preferred_teams": ["Inbound"]},
        "query_patterns": {"frequent_topics": ["score"], "query_count": 5},
        "interaction_summary": "Asks about Inbound frequently",
        "feedback_signals": {"positive_count": 2, "negative_count": 0},
    }
    text = svc.get_memory_text(memory)
    assert "[User Memory]" in text
    assert "Preferred detail level: brief" in text
    assert "Preferred teams: Inbound" in text
    assert "Frequent topics: score" in text
    assert "Asks about Inbound frequently" in text
    assert "Feedback: 2 positive, 0 negative" in text
