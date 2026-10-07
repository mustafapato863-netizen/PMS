from fastapi import HTTPException
import pytest

from api.routers import performance
from models.schemas import PerformanceRecord
from services.dashboard_record_service import DashboardRecordService
from services.management_bsc_service import ManagementBSCService


def _sources(monkeypatch):
    employee = PerformanceRecord(id="employee-row", employee_id="e1", employee_name="Employee", team="Coding", month="August", year=2026, performance_level="Employee", evaluation={"score": 88, "grade": "C"})
    management = [
        {"employee_id": "m1", "employee_name": "Manager", "team": "Coding", "month": "August", "year": 2026, "performance_level": "Managerial", "evaluation": {"score": 84}},
        {"employee_id": "c1", "employee_name": "Director", "team": "Coding", "month": "August", "year": 2026, "performance_level": "Corporate", "evaluation": {"score": 95}},
        {"employee_id": "other", "team": "Marketing", "performance_level": "Managerial", "evaluation": {"score": 60}},
        {"employee_id": "missing", "team": "Coding", "performance_level": "Corporate", "evaluation": {"score": None}},
    ]
    monkeypatch.setattr(DashboardRecordService, "list_analysis_records", lambda _self: [employee])
    monkeypatch.setattr(ManagementBSCService, "list_analysis_records", lambda _self: management)


def test_summary_source_combines_canonical_levels_and_filters_profile(monkeypatch):
    _sources(monkeypatch)
    monkeypatch.setattr(performance, "require_authenticated_scope", lambda *_args: {"role": "Admin", "has_unrestricted_team_access": True})
    data = performance.get_summary_records(None, object(), employee_id=None).data
    assert {row["performance_level"] for row in data} == {"Employee", "Managerial", "Corporate"}
    assert not any(row["employee_id"] == "missing" for row in data)
    profile = performance.get_summary_records(None, object(), employee_id="m1").data
    assert [row["employee_id"] for row in profile] == ["m1"]


def test_summary_source_enforces_team_and_level_assignments(monkeypatch):
    _sources(monkeypatch)
    scope = {"role": "Manager", "accessible_teams": ["Coding"], "accessible_team_levels": [("Coding", "Employee")], "has_unrestricted_team_access": False, "is_self_only": False}
    monkeypatch.setattr(performance, "require_authenticated_scope", lambda *_args: scope)
    data = performance.get_summary_records(None, object(), employee_id=None).data
    assert [row["employee_id"] for row in data] == ["e1"]
    assert performance.get_summary_records(None, object(), employee_id="m1").data == []


def test_summary_source_requires_authentication(monkeypatch):
    def unauthenticated(*_args):
        raise HTTPException(status_code=401, detail="Authenticated session required")
    monkeypatch.setattr(performance, "require_authenticated_scope", unauthenticated)
    with pytest.raises(HTTPException) as error:
        performance.get_summary_records(None, object(), employee_id=None)
    assert error.value.status_code == 401
