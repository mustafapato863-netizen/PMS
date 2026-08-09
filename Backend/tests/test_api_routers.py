"""
Integration tests for the current API router contracts.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import router as api_router
from models.schemas import Employee as EmployeeSchema


app = FastAPI()
app.include_router(api_router, prefix="/api")
client = TestClient(app)


def _performance_record(employee_id: str = "EMP001", team: str = "Sales", month: str = "January", score: float = 85.5):
    root_cause = MagicMock()
    root_cause.kpi = "booking"
    root_cause.model_dump.return_value = {
        "kpi": "booking",
        "impact_pct": 12.0,
        "actual": 80.0,
        "target": 100.0,
    }
    record = MagicMock()
    record.id = str(uuid4())
    record.employee_id = employee_id
    record.employee_name = "John Doe"
    record.team = team
    record.month = month
    record.year = 2026
    record.region = "UAE"
    record.performance_level = "Employee"
    record.position = None
    record.status = "Meets"
    record.calls = MagicMock(inbound=10, outbound=0, total_handled=10, abandoned=1, aht_raw="00:05:00")
    record.geo = MagicMock(
        bookings=MagicMock(dubai=1, sharjah=2, ajman=3, clinics=4),
        attended=MagicMock(dubai=1, sharjah=1, ajman=1, clinics=1),
    )
    record.actual = MagicMock(
        booking_rate=0.8,
        attend_rate=0.9,
        abandon_rate=0.1,
        reachability_rate=0.0,
        rejection_rate=0.0,
        initial_error_rate=0.0,
        submission_rate=0.0,
        quality_rate=0.95,
        utz_rate=0.0,
    )
    record.achievement = MagicMock(
        booking_ach=80.0,
        attend_ach=90.0,
        quality_ach=95.0,
        aht_ach=88.0,
        reachability_ach=0.0,
        abandon_ach=90.0,
        rejection_ach=0.0,
        initial_error_ach=0.0,
        submission_ach=0.0,
        op_census_ach=0.0,
        op_revenue_ach=0.0,
        ip_census_ach=0.0,
        ip_revenue_ach=0.0,
        activity_ach=0.0,
    )
    record.evaluation = MagicMock()
    record.evaluation.score = score
    record.evaluation.grade = "B"
    record.evaluation.root_cause = root_cause
    record.evaluation.suggested_action = "Coach"
    record.evaluation.corrective_action = None
    record.evaluation.manager_notes = None
    record.evaluation.planning_category = []
    record.evaluation.trend_status = "Stable"
    record.raw_data = {}
    record.kpi_values = []
    return record


class TestTeamManagementRouter:
    def test_list_teams_success(self):
        with patch("api.routers.team_management.TeamService.get_all_teams") as mock_get:
            mock_get.return_value = [
                {
                    "id": str(uuid4()),
                    "name": "inbound",
                    "display_name": "Inbound Team",
                    "db_name": "inbound_db",
                    "region": "UAE",
                    "team_level": "employee",
                    "description": "Inbound team",
                    "kpi_keys": ["attendance", "quality"],
                    "kpi_weights": {"attendance": 0.5, "quality": 0.5},
                    "data_source": "Excel",
                    "team_lead": "Ahmed",
                    "team_lead_email": "ahmed@test.com",
                    "is_active": True,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
            ]

            response = client.get("/api/team-management/teams")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert data["active_count"] == 1
            assert data["teams"][0]["team_level"] == "employee"


class TestEmployeeRouter:
    def test_get_all_employees(self):
        with patch("api.routers.employee.EmployeeDirectoryService") as mock_service:
            mock_service.return_value.list.return_value = [
                {"id": "EMP001", "employee_id": "EMP001", "name": "John Doe", "team": "Sales", "region": "UAE", "performance_level": "Employee", "position": None, "status": "Active"}
            ]

            response = client.get("/api/employee")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"][0]["id"] == "EMP001"
            assert data["data"][0]["team"] == "Sales"

    def test_search_employees(self):
        with patch("api.routers.employee.EmployeeDirectoryService") as mock_service:
            mock_service.return_value.list.return_value = [
                {"id": "EMP001", "employee_id": "EMP001", "name": "John Doe", "team": "Sales", "region": "UAE", "performance_level": "Employee", "position": None, "status": "Active"}
            ]

            response = client.get("/api/employee/search", params={"name": "john"})
            assert response.status_code == 200
            assert response.json()["data"][0]["name"] == "John Doe"

    def test_get_employee_profile(self):
        january = _performance_record(month="January", score=85.5)
        june = _performance_record(month="June", score=92.2)
        with (
            patch("api.routers.employee.DashboardRecordService") as mock_dashboard_service,
            patch("api.routers.employee.CorrectiveActionService") as mock_action_service,
        ):
            mock_dashboard_service.return_value.list_records.return_value = [june, january]
            mock_action_service.return_value.get_history.return_value = []

            response = client.get("/api/employee/EMP001")
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["employee"]["id"] == "EMP001"
            assert [row["month"] for row in data["performance_history"]] == ["January", "June"]
            mock_dashboard_service.return_value.list_records.assert_called_once_with(employee_id="EMP001")
            mock_action_service.return_value.get_history.assert_called_once_with("EMP001")

    def test_create_employee(self):
        with patch("api.routers.employee.EmployeeDirectoryService") as mock_service:
            mock_service.return_value.create.return_value = {
                "id": "EMP001", "employee_id": "EMP001", "name": "John Doe", "team": "Sales",
                "region": "UAE", "performance_level": "Employee", "position": None, "status": "Active",
            }
            response = client.post(
                "/api/employee",
                params={
                    "employee_id": "EMP001",
                    "name": "John Doe",
                    "team": "Sales",
                    "region": "UAE",
                },
                headers={"X-User-Role": "Admin"},
            )

            assert response.status_code == 201
            data = response.json()
            assert data["success"] is True
            assert data["data"]["id"] == "EMP001"
            assert data["data"]["team"] == "Sales"
            mock_service.return_value.create.assert_called_once()

    def test_update_employee(self):
        with patch("api.routers.employee.EmployeeDirectoryService") as mock_service:
            employee = MagicMock()
            employee.employee_id = "EMP001"
            employee.team.display_name = "Sales"
            employee.team.name = "Sales"
            mock_service.return_value.get_model.return_value = employee
            mock_service.return_value.update.return_value = {
                "id": "EMP001", "employee_id": "EMP001", "name": "Jane Doe", "team": "Sales",
                "region": "UAE", "performance_level": "Employee", "position": None, "status": "Active",
            }

            response = client.put(
                "/api/employee/EMP001",
                params={"name": "Jane Doe"},
                headers={"X-User-Role": "Admin"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"]["name"] == "Jane Doe"
            mock_service.return_value.update.assert_called_once_with(
                "EMP001", name="Jane Doe", team=None, region=None,
            )

    def test_delete_employee(self):
        with patch("api.routers.employee.EmployeeService.delete_employee") as mock_delete:
            mock_delete.return_value = (True, [])

            response = client.delete("/api/employee/EMP001", headers={"X-User-Role": "Admin"})
            assert response.status_code == 200
            assert response.json()["success"] is True

    def test_update_employee_assignment(self):
        with patch("api.routers.employee.EmployeeService.update_employee_assignment") as mock_update:
            mock_update.return_value = (
                True,
                {"employee_id": "EMP001", "team": "Outbound", "performance_level": "Managerial"},
                [],
            )

            response = client.put(
                "/api/employee/EMP001/assignment",
                params={"team": "Outbound", "performance_level": "Managerial"},
                headers={"X-User-Role": "Admin"},
            )

            assert response.status_code == 200
            assert response.json()["data"]["performance_level"] == "Managerial"
            mock_update.assert_called_once_with(
                employee_identifier="EMP001",
                team_name="Outbound",
                performance_level="Managerial",
            )

    def test_update_employee_assignment_rejects_manager(self):
        response = client.put(
            "/api/employee/EMP001/assignment",
            params={"team": "Outbound", "performance_level": "Managerial"},
            headers={"X-User-Role": "Manager"},
        )

        assert response.status_code == 403


class TestPerformanceRouter:
    def test_catalog_uses_lightweight_rows_and_team_level_scope(self):
        with (
            patch("api.routers.performance.DashboardRecordService") as mock_service,
            patch("api.routers.performance.get_current_user_scope") as mock_scope,
        ):
            mock_service.return_value.list_option_rows.return_value = [
                {
                    "employee_id": "EMP001",
                    "employee_name": "John Doe",
                    "team": "Sales",
                    "month": "June",
                    "year": 2026,
                    "region": "UAE",
                    "performance_level": "Employee",
                    "position": "Agent",
                },
                {
                    "employee_id": "EMP002",
                    "employee_name": "Jane Doe",
                    "team": "Sales",
                    "month": "June",
                    "year": 2026,
                    "region": "UAE",
                    "performance_level": "Managerial",
                    "position": "Manager",
                },
            ]
            mock_scope.return_value = {
                "role": "Manager",
                "accessible_teams": ["Sales"],
                "accessible_team_levels": [("Sales", "Employee")],
                "is_general_manager": False,
                "legacy_unscoped": False,
            }

            response = client.get("/api/performance/catalog")

            assert response.status_code == 200
            data = response.json()["data"]
            assert data["months"] == ["June"]
            assert data["periods"] == [{"year": 2026, "month": "June", "key": "2026-06"}]
            assert data["scopes"] == [{
                "team": "Sales",
                "region": "UAE",
                "performance_level": "Employee",
                "position": "Agent",
            }]
            mock_service.return_value.list_records.assert_not_called()

    def test_get_monthly_records(self):
        with patch("api.routers.performance.DashboardRecordService") as mock_service:
            mock_service.return_value.list_records.return_value = [_performance_record(team="Sales", month="January")]

            response = client.get("/api/performance/records", params={"team": "Sales", "month": "January"})
            assert response.status_code == 200
            data = response.json()["data"]
            assert len(data) == 1
            assert data[0]["team"] == "Sales"
            assert data[0]["month"] == "January"

    def test_get_employee_history(self):
        with patch("api.routers.performance.DashboardRecordService") as mock_service:
            mock_service.return_value.list_records.return_value = [_performance_record(employee_id="EMP001")]

            response = client.get("/api/performance/employee/EMP001")
            assert response.status_code == 200
            assert response.json()["data"][0]["employee_id"] == "EMP001"

    def test_get_team_yearly_records(self):
        with patch("api.routers.performance.DashboardRecordService") as mock_service:
            mock_service.return_value.list_records.return_value = [_performance_record(team="Sales")]

            response = client.get("/api/performance/team/Sales")
            assert response.status_code == 200
            assert response.json()["data"][0]["team"] == "Sales"

    def test_get_by_grade(self):
        with patch("api.routers.performance.DashboardRecordService") as mock_service:
            record = _performance_record(team="Sales", month="January", score=95.0)
            record.evaluation.grade = "A"
            mock_service.return_value.list_records.return_value = [record]

            response = client.get("/api/performance/grade/Sales", params={"grade": "A", "month": "January"})
            assert response.status_code == 200
            assert response.json()["data"][0]["evaluation"]["grade"] == "A"

    def test_get_by_status(self):
        with patch("api.routers.performance.DashboardRecordService") as mock_service:
            mock_service.return_value.list_records.return_value = [_performance_record(team="Sales", month="January", score=85.5)]

            response = client.get("/api/performance/status/Sales", params={"status": "Meets", "month": "January"})
            assert response.status_code == 200
            assert response.json()["data"][0]["evaluation"]["score"] == 85.5


class TestSearchRouter:
    def test_global_search_returns_scoped_teams_and_employee_matches(self):
        employees = [
            {"id": "EMP001", "employee_id": "EMP001", "name": "John Doe", "team": "Sales", "status": "Active", "performance_level": "Employee"},
            {"id": "EMP002", "employee_id": "EMP002", "name": "Jane Roe", "team": "Inbound", "status": "Active", "performance_level": "Employee"},
        ]
        with (
            patch("api.routers.search.require_authenticated_scope") as mock_scope,
            patch("api.routers.search.EmployeeDirectoryService") as mock_service,
        ):
            mock_scope.return_value = {
                "role": "Manager",
                "accessible_teams": ["Sales"],
                "active_team_names": ["Sales", "Inbound"],
                "is_general_manager": False,
                "employee_id": None,
                "user_id": "manager-1",
            }
            mock_service.return_value.list.return_value = employees

            response = client.get("/api/search/global", params={"q": "jo"})

            assert response.status_code == 200
            data = response.json()["data"]
            assert data["teams"] == []
            assert data["employees"] == [
                {
                    "id": "EMP001",
                    "name": "John Doe",
                    "employee_id": "EMP001",
                    "team": "Sales",
                    "performance_level": "Employee",
                }
            ]

    def test_global_search_empty_query_returns_accessible_teams_only(self):
        with patch("api.routers.search.require_authenticated_scope") as mock_scope:
            mock_scope.return_value = {
                "role": "Admin",
                "accessible_teams": [],
                "active_team_names": ["Sales", "Inbound"],
                "is_general_manager": True,
                "employee_id": None,
                "user_id": "admin-1",
            }

            response = client.get("/api/search/global")

            assert response.status_code == 200
            data = response.json()["data"]
            assert [team["name"] for team in data["teams"]] == ["Inbound", "Sales"]
            assert data["employees"] == []


class TestErrorHandling:
    def test_404_error_handling(self):
        with patch("api.routers.employee.DashboardRecordService") as mock_service:
            mock_service.return_value.list_records.return_value = []
            response = client.get("/api/employee/nonexistent")
            assert response.status_code == 404

    def test_validation_error_for_missing_query_param(self):
        response = client.get("/api/employee/search")
        assert response.status_code == 422

    def test_500_style_error_returns_standard_response(self):
        with patch("api.routers.employee.EmployeeDirectoryService") as mock_service:
            mock_service.return_value.list.side_effect = Exception("Database connection error")
            response = client.get("/api/employee")
            assert response.status_code == 200
            assert response.json()["success"] is False


class TestResponseSchemas:
    def test_employee_response_schema(self):
        with patch("api.routers.employee.EmployeeDirectoryService") as mock_service:
            mock_service.return_value.list.return_value = [
                {"id": "EMP001", "employee_id": "EMP001", "name": "John Doe", "team": "Sales", "region": "UAE", "performance_level": "Employee", "position": None, "status": "Active"}
            ]

            response = client.get("/api/employee")
            data = response.json()
            assert "success" in data
            assert "message" in data
            assert isinstance(data["data"], list)
            emp = data["data"][0]
            assert "id" in emp
            assert "name" in emp
            assert "team" in emp

    def test_performance_response_schema(self):
        with patch("api.routers.performance.DashboardRecordService") as mock_service:
            mock_service.return_value.list_records.return_value = [_performance_record()]

            response = client.get("/api/performance/records", params={"month": "January"})
            data = response.json()
            assert "success" in data
            assert "message" in data
            assert isinstance(data["data"], list)
            record = data["data"][0]
            assert "employee_id" in record
            assert "team" in record
            assert "evaluation" in record


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
