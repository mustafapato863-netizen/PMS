"""Tests for User Rules Spec builder."""

import pytest

from services.ai.domain_policies import is_self_service_prompt
from services.ai.user_rules_spec import (
    build_user_rules_spec,
    get_user_rules_spec_text,
    is_self_service_query,
    resolve_self_employee_id,
)


def test_build_user_rules_spec_admin():
    scope = {
        "user_id": "user-1",
        "role": "Admin",
        "employee_id": None,
        "has_unrestricted_team_access": True,
        "is_self_only": False,
        "accessible_teams": ["Inbound", "Outbound", "Support"],
        "accessible_functions": [],
        "accessible_regions": [],
        "accessible_branches": [],
        "active_team_names": ["Inbound", "Outbound", "Support"],
    }
    spec = build_user_rules_spec(scope)
    assert spec["identity"]["role"] == "Admin"
    assert spec["identity"]["is_self_only"] is False
    assert spec["permissions"]["has_unrestricted_team_access"] is True
    assert spec["restrictions"]["restricted_teams"] == []
    assert "ALL teams (unrestricted)" in spec["summary_text"]


def test_build_user_rules_spec_employee():
    scope = {
        "user_id": "user-2",
        "role": "Employee",
        "employee_id": "EMP-101",
        "has_unrestricted_team_access": False,
        "is_self_only": True,
        "accessible_teams": [],
        "accessible_functions": [],
        "accessible_regions": [],
        "accessible_branches": [],
        "active_team_names": ["Inbound", "Outbound"],
    }
    spec = build_user_rules_spec(scope)
    assert spec["identity"]["role"] == "Employee"
    assert spec["identity"]["employee_id"] == "EMP-101"
    assert spec["identity"]["is_self_only"] is True
    assert spec["restrictions"]["cannot_access_other_employees"] is True
    assert "self-only" in spec["summary_text"]
    assert "EMP-101" in spec["summary_text"]


def test_build_user_rules_spec_manager():
    scope = {
        "user_id": "user-3",
        "role": "Manager",
        "employee_id": None,
        "has_unrestricted_team_access": False,
        "is_self_only": False,
        "accessible_teams": ["Inbound"],
        "accessible_functions": ["Call Center"],
        "accessible_regions": [],
        "accessible_branches": [],
        "active_team_names": ["Inbound", "Outbound", "Support"],
    }
    spec = build_user_rules_spec(scope)
    assert spec["identity"]["role"] == "Manager"
    assert spec["permissions"]["accessible_teams"] == ["Inbound"]
    assert spec["permissions"]["accessible_functions"] == ["Call Center"]
    assert "Inbound" in spec["permissions"]["accessible_teams"]
    assert "Outbound" in spec["restrictions"]["restricted_teams"]
    assert "Support" in spec["restrictions"]["restricted_teams"]


def test_get_user_rules_spec_text():
    scope = {
        "user_id": "user-1",
        "role": "Admin",
        "employee_id": None,
        "has_unrestricted_team_access": True,
        "is_self_only": False,
        "accessible_teams": [],
        "accessible_functions": [],
        "accessible_regions": [],
        "accessible_branches": [],
        "active_team_names": [],
    }
    text = get_user_rules_spec_text(scope)
    assert "role=Admin" in text
    assert "ALL teams (unrestricted)" in text


def test_is_self_service_prompt():
    assert is_self_service_prompt("How am I doing?") is True
    assert is_self_service_prompt("What's my score?") is True
    assert is_self_service_prompt("Show me my KPIs") is True
    assert is_self_service_prompt("My trend over recent months") is True
    assert is_self_service_prompt("Am I doing well?") is True
    assert is_self_service_prompt("Show overall performance") is False
    assert is_self_service_prompt("How is Inbound doing?") is False
    assert is_self_service_prompt("") is False


def test_resolve_self_employee_id():
    scope = {"is_self_only": True, "employee_id": "EMP-101"}
    assert resolve_self_employee_id(scope) == "EMP-101"

    scope_no_emp = {"is_self_only": True, "employee_id": None}
    assert resolve_self_employee_id(scope_no_emp) is None

    scope_admin = {"is_self_only": False, "employee_id": "EMP-101"}
    assert resolve_self_employee_id(scope_admin) is None
