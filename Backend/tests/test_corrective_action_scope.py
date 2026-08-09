from types import SimpleNamespace

import pytest

from services.corrective_action_service import CorrectiveActionService


def employee(team: str):
    return SimpleNamespace(employee_id="A", performance_level="Employee", team=SimpleNamespace(name=team, display_name=team))


def test_authorized_manager_can_write_employee_action_scope(monkeypatch):
    service = CorrectiveActionService(None)
    monkeypatch.setattr(service, "_employee", lambda _identifier: employee("Inbound"))
    scope = {"role": "Manager", "accessible_teams": ["Inbound"], "accessible_team_levels": [("Inbound", "Employee")], "legacy_unscoped": False}
    assert service.ensure_employee_scope("A", scope).employee_id == "A"


def test_unauthorized_manager_action_write_is_rejected(monkeypatch):
    service = CorrectiveActionService(None)
    monkeypatch.setattr(service, "_employee", lambda _identifier: employee("Outbound"))
    scope = {"role": "Manager", "accessible_teams": ["Inbound"], "accessible_team_levels": [("Inbound", "Employee")], "legacy_unscoped": False}
    with pytest.raises(PermissionError):
        service.ensure_employee_scope("A", scope)
