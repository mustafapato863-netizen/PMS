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


@pytest.mark.parametrize(("region", "expected_count"), [("UAE", 1), ("EGY", 0)])
def test_regional_manager_corrective_actions_use_the_period_region(monkeypatch, region, expected_count):
    service = CorrectiveActionService(None)
    action = SimpleNamespace(id="action-1", employee_id="employee-db-id", employee=employee("Inbound"), branch_key=None)
    record = SimpleNamespace(region=region, team=SimpleNamespace(name="Inbound", display_name="Inbound"))
    service.actions.list_active = lambda: [action]
    monkeypatch.setattr(service, "_performance_record_for_action", lambda _action: record)
    monkeypatch.setattr(service, "serialize", lambda _action, **_kwargs: {"id": "action-1"})
    scope = {
        "role": "Regional Manager",
        "accessible_regions": ["UAE"],
        "accessible_teams": ["Inbound"],
        "accessible_team_levels": [("Inbound", "Employee")],
        "legacy_unscoped": False,
    }

    assert len(service.list_scoped(scope)) == expected_count


def test_regional_manager_plan_access_uses_explicit_plan_region():
    service = CorrectiveActionService(None)
    team = SimpleNamespace(name="Inbound", display_name="Inbound")
    scope = {
        "role": "Regional Manager",
        "accessible_regions": ["UAE"],
        "accessible_teams": ["Inbound"],
        "legacy_unscoped": False,
    }

    assert service._can_access_plan(SimpleNamespace(region="UAE", team=team), scope)
    assert not service._can_access_plan(SimpleNamespace(region="EGY", team=team), scope)
