"""Tests for Agent 360° service."""

import pytest
from unittest.mock import MagicMock, patch

from services.ai.agent_360_service import Agent360Service


@pytest.fixture
def mock_db():
    return MagicMock()


def test_get_agent_360_no_employee(mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = None
    svc = Agent360Service(mock_db)
    scope = {"user_id": "u-1", "role": "Employee", "employee_id": "EMP-999"}
    result = svc.get_agent_360("EMP-999", scope)
    assert result is None


def test_get_agent_360_no_records(mock_db):
    emp = MagicMock()
    emp.id = "emp-1"
    emp.name = "Test Agent"
    mock_db.query.return_value.filter.return_value.first.return_value = emp
    # No performance records
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    svc = Agent360Service(mock_db)
    scope = {"user_id": "u-1", "role": "Employee", "employee_id": "EMP-101"}
    result = svc.get_agent_360("EMP-101", scope)
    assert result is not None
    assert result["employee_code"] == "EMP-101"
    assert result["employee_name"] == "Test Agent"
    assert result["overall_score"] is None
    assert result["performance_classification"] == "New"
    assert result["cohort"] is None


def test_get_agent_360_with_records(mock_db):
    emp = MagicMock()
    emp.id = "emp-1"
    emp.name = "Test Agent"
    emp.position = "Agent"
    emp.region = "EGY"

    rec1 = MagicMock()
    rec1.month = "August"
    rec1.year = 2026
    rec1.score = 85.0
    rec1.grade = "B"
    rec1.status = "Good"

    rec2 = MagicMock()
    rec2.month = "September"
    rec2.year = 2026
    rec2.score = 90.0
    rec2.grade = "A"
    rec2.status = "Excellent"
    rec2.employee_id = "emp-1"

    # First query: employee lookup
    mock_db.query.return_value.filter.return_value.first.side_effect = [emp, None]
    # Second query: performance records
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [rec1, rec2]

    svc = Agent360Service(mock_db)
    scope = {"user_id": "u-1", "role": "Employee", "employee_id": "EMP-101"}
    result = svc.get_agent_360("EMP-101", scope)
    assert result is not None
    assert result["employee_code"] == "EMP-101"
    assert result["overall_score"] == 90.0
    assert result["overall_grade"] == "A"
    assert result["performance_classification"] == "Improving"
    assert len(result["score_trend"]) == 2
    assert result["current_period"] == "September 2026"
