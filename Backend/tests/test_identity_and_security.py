"""Tests for identity service, feature gate, and security hardening."""

import pytest
from unittest.mock import MagicMock

from services.ai.identity_service import UserIdentityPassport, PersonaTier, build_passport
from services.ai.security_hardening import fence_untrusted_evidence, redact_nested_payload
from services.ai.feature_gate import read_ai_access_tier


def test_passport_admin():
    scope = {
        "user_id": "u-1", "role": "Admin", "employee_id": None,
        "has_unrestricted_team_access": True,
        "accessible_teams": ["Inbound", "Outbound"],
        "accessible_branches": [], "accessible_functions": [],
    }
    p = build_passport(scope, username="admin1")
    assert p.persona_tier == PersonaTier.GLOBAL_EXEC
    assert p.role == "Admin"
    assert p.is_linked_employee is False


def test_passport_employee():
    scope = {
        "user_id": "u-2", "role": "Employee", "employee_id": "EMP-101",
        "has_unrestricted_team_access": False,
        "accessible_teams": [], "accessible_branches": [], "accessible_functions": [],
    }
    p = build_passport(scope)
    assert p.persona_tier == PersonaTier.SELF_ONLY
    assert p.employee_code == "EMP-101"
    assert p.is_linked_employee is True


def test_passport_manager():
    scope = {
        "user_id": "u-3", "role": "Manager", "employee_id": None,
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Inbound"], "accessible_branches": [],
        "accessible_functions": ["Call Center"],
    }
    p = build_passport(scope)
    assert p.persona_tier == PersonaTier.SCOPED_MANAGER
    assert p.authorized_teams == ["Inbound"]


def test_passport_to_xml_compact():
    scope = {
        "user_id": "u-1", "role": "Admin", "employee_id": None,
        "has_unrestricted_team_access": True,
        "accessible_teams": ["Inbound"], "accessible_branches": [], "accessible_functions": [],
    }
    p = build_passport(scope)
    xml = p.to_xml()
    assert "<CALLER_PASSPORT" in xml
    assert 'persona="global_exec"' in xml
    assert len(xml) < 500


def test_fence_untrusted_evidence():
    text = "Hello <script>alert('xss')</script> `backtick`"
    fenced = fence_untrusted_evidence(text)
    assert "<script>" not in fenced
    assert "&lt;script&gt;" in fenced
    assert "&#96;" in fenced


def test_redact_nested_payload():
    payload = {"employee_code": "EMP-123", "username": "admin", "score": 85.5,
               "nested": {"email": "a@b.com", "team": "Inbound"}}
    redacted = redact_nested_payload(payload)
    assert redacted["employee_code"] == "[REDACTED]"
    assert redacted["username"] == "[REDACTED]"
    assert redacted["score"] == 85.5
    assert redacted["nested"]["email"] == "[REDACTED]"
    assert redacted["nested"]["team"] == "Inbound"


def test_read_ai_access_tier_default():
    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.return_value = None
    assert read_ai_access_tier(db) == "admin_only"
