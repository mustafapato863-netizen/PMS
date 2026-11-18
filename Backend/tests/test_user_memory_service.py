"""Tests for User Memory Service."""

import pytest
from unittest.mock import MagicMock, patch

from services.ai.user_memory_service import UserMemoryService


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


def test_user_memory_and_conversations_use_separate_orm_tables():
    """Adding user memory must not replace the existing AI conversations mapping."""
    from config.database import Base
    from models.models import AiConversation, AiUserMemory

    assert AiUserMemory.__tablename__ == "ai_user_memory"
    assert AiConversation.__tablename__ == "ai_conversations"
    assert Base.metadata.tables["ai_user_memory"] is AiUserMemory.__table__
    assert Base.metadata.tables["ai_conversations"] is AiConversation.__table__
    assert "user_id" in AiUserMemory.__table__.c
    assert "owner_user_id" in AiConversation.__table__.c


def test_load_memory_returns_none_when_empty(mock_db):
    svc = UserMemoryService(mock_db)
    result = svc.load_memory("user-1")
    assert result is None


def test_save_memory_creates_new_row(mock_db):
    svc = UserMemoryService(mock_db)
    svc.save_memory("user-1", {"preferences": {"detail_level": "brief"}})
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


def test_get_memory_text_empty():
    svc = UserMemoryService(MagicMock())
    assert svc.get_memory_text(None) == ""
    assert svc.get_memory_text({}) == ""


def test_get_memory_text_with_data():
    svc = UserMemoryService(MagicMock())
    memory = {
        "preferences": {"detail_level": "brief", "preferred_metrics": ["Booking Rate"]},
        "query_patterns": {"frequent_topics": ["score"], "frequent_teams": {"Inbound": 5}},
        "interaction_summary": "User asks about Inbound frequently",
        "feedback_signals": {"positive_count": 3, "negative_count": 1},
    }
    text = svc.get_memory_text(memory)
    assert "Preferred detail level: brief" in text
    assert "Preferred metrics: Booking Rate" in text
    assert "Frequent topics: score" in text
    assert "Frequently asked teams: Inbound" in text
    assert "Recent interaction summary: User asks about Inbound frequently" in text
    assert "Feedback: 3 positive, 1 negative" in text


def test_record_query():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    svc = UserMemoryService(mock_db)
    # Should not raise even if load returns None
    svc.record_query("user-1", topic="score", team="Inbound", kpi="Booking Rate")
    mock_db.add.assert_called()


def test_record_feedback():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    svc = UserMemoryService(mock_db)
    svc.record_feedback("user-1", positive=True, correction="Use Booking Rate not booking")
    mock_db.add.assert_called()


def test_decay_memory_no_row():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    svc = UserMemoryService(mock_db)
    # Should not raise
    svc.decay_memory("user-1")
