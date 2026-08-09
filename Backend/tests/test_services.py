"""
Comprehensive Service Tests
Testing service implementations with mocking.
"""

import pytest
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

import pandas as pd

from services.team_service import TeamService
from services.employee_service import EmployeeService
from services.performance_service import PerformanceService
from services.seeding_service import DatabaseSeeder


# ============================================================
# TEAM SERVICE TESTS
# ============================================================

class TestTeamService:
    """Test suite for TeamService."""

    @patch('services.team_service.TeamRepository')
    @patch('services.team_service.SessionLocal')
    def test_get_all_teams(self, mock_session_local, mock_team_repo):
        """Test getting all teams."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_team_repo.return_value = mock_repo_instance
        
        mock_team = MagicMock()
        mock_team.id = uuid.uuid4()
        mock_team.name = 'test_team'
        mock_team.db_name = 'test_team_db'
        mock_team.team_level = 'employee'
        mock_team.region = 'UAE'
        mock_team.is_active = True
        mock_team.created_at = datetime.now()
        mock_team.updated_at = datetime.now()
        
        mock_repo_instance.get_active_teams.return_value = [mock_team]
        mock_session.query.return_value.filter.return_value.all.return_value = []
        
        # Execute
        teams = TeamService.get_all_teams()
        
        # Verify
        assert len(teams) > 0
        assert teams[0]['name'] == 'test_team'
        mock_session.close.assert_called_once()

    @patch('services.team_service.find_team_config_by_db_name')
    @patch('services.team_service.load_team_config')
    @patch('services.team_service.TeamRepository')
    @patch('services.team_service.SessionLocal')
    def test_get_all_teams_uses_team_config_when_available(
        self,
        mock_session_local,
        mock_team_repo,
        mock_load_team_config,
        mock_find_config,
    ):
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session

        mock_repo_instance = MagicMock()
        mock_team_repo.return_value = mock_repo_instance

        mock_team = MagicMock()
        mock_team.id = uuid.uuid4()
        mock_team.name = 'new_team'
        mock_team.db_name = 'new_team_db'
        mock_team.team_level = 'employee'
        mock_team.region = 'UAE'
        mock_team.is_active = True
        mock_team.created_at = datetime.now()
        mock_team.updated_at = datetime.now()

        mock_repo_instance.get_active_teams.return_value = [mock_team]
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_load_team_config.return_value = {
            'team': 'New Team',
            'db_name': 'New Team DB',
            'region': 'EGY',
            'kpis': [
                {'key': 'A', 'label': 'Alpha', 'weight': 0.6},
                {'key': 'B', 'label': 'Beta', 'weight': 0.4},
            ],
        }
        mock_find_config.return_value = None

        teams = TeamService.get_all_teams()

        assert teams[0]['display_name'] == 'New Team'
        assert teams[0]['db_name'] == 'new_team_db'
        assert teams[0]['kpi_keys'] == ['A', 'B']
        assert teams[0]['kpi_weights'] == {'A': 0.6, 'B': 0.4}
        assert teams[0]['data_source'] == 'Excel'
        mock_session.close.assert_called_once()

    @patch('services.team_service.TeamRepository')
    @patch('services.team_service.SessionLocal')
    def test_get_team(self, mock_session_local, mock_team_repo):
        """Test getting a single team."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_team_repo.return_value = mock_repo_instance
        
        mock_team = MagicMock()
        mock_team.id = uuid.uuid4()
        mock_team.name = 'test_team'
        mock_team.db_name = 'test_team_db'
        mock_team.region = 'UAE'
        mock_team.is_active = True
        mock_team.created_at = datetime.now()
        mock_team.updated_at = datetime.now()
        
        mock_repo_instance.get_by_name.return_value = mock_team
        mock_session.query.return_value.filter.return_value.all.return_value = []
        
        # Execute
        team = TeamService.get_team('test_team')
        
        # Verify
        assert team is not None
        assert team['name'] == 'test_team'
        mock_session.close.assert_called_once()

    @patch('services.team_service.TeamRepository')
    @patch('services.team_service.SessionLocal')
    def test_get_team_not_found(self, mock_session_local, mock_team_repo):
        """Test getting non-existent team."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_team_repo.return_value = mock_repo_instance
        mock_repo_instance.get_by_name.return_value = None
        
        # Execute
        team = TeamService.get_team('nonexistent')
        
        # Verify
        assert team is None
        mock_session.close.assert_called_once()

    @patch('services.team_service.TeamRepository')
    @patch('services.team_service.SessionLocal')
    def test_team_statistics(self, mock_session_local, mock_team_repo):
        """Test getting team statistics."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_team_repo.return_value = mock_repo_instance
        
        mock_team = MagicMock()
        mock_team.region = 'UAE'
        
        mock_repo_instance.get_all.return_value = [mock_team]
        mock_repo_instance.get_active_teams.return_value = [mock_team]
        mock_session.query.return_value.all.return_value = []
        
        # Execute
        stats = TeamService.get_team_statistics()
        
        # Verify
        assert 'total_teams' in stats
        assert 'active_teams' in stats


# ============================================================
# EMPLOYEE SERVICE TESTS
# ============================================================

class TestEmployeeService:
    """Test suite for EmployeeService."""

    @patch('services.employee_service.EmployeeRepository')
    @patch('services.employee_service.SessionLocal')
    def test_get_all_employees(self, mock_session_local, mock_emp_repo):
        """Test getting all employees."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_emp_repo.return_value = mock_repo_instance
        
        mock_emp = MagicMock()
        mock_emp.id = uuid.uuid4()
        mock_emp.employee_id = 'EMP001'
        mock_emp.name = 'John Doe'
        mock_emp.team_id = uuid.uuid4()
        mock_emp.region = 'UAE'
        mock_emp.is_active = True
        mock_emp.created_at = datetime.now()
        mock_emp.updated_at = datetime.now()
        mock_emp.team = None
        
        mock_repo_instance.get_all.return_value = [mock_emp]
        
        # Execute
        employees = EmployeeService.get_all_employees()
        
        # Verify
        assert len(employees) > 0
        assert employees[0]['employee_id'] == 'EMP001'
        mock_session.close.assert_called_once()

    @patch('services.employee_service.EmployeeRepository')
    @patch('services.employee_service.SessionLocal')
    def test_get_employee_by_uuid(self, mock_session_local, mock_emp_repo):
        """Test getting employee by UUID."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_emp_repo.return_value = mock_repo_instance
        
        test_id = uuid.uuid4()
        mock_emp = MagicMock()
        mock_emp.id = test_id
        mock_emp.employee_id = 'EMP001'
        mock_emp.name = 'John Doe'
        mock_emp.team_id = uuid.uuid4()
        mock_emp.region = 'UAE'
        mock_emp.is_active = True
        mock_emp.created_at = datetime.now()
        mock_emp.updated_at = datetime.now()
        mock_emp.team = None
        
        mock_repo_instance.get_by_id.return_value = mock_emp
        
        # Execute
        emp = EmployeeService.get_employee(str(test_id))
        
        # Verify
        assert emp is not None
        assert emp['employee_id'] == 'EMP001'
        mock_session.close.assert_called_once()

    @patch('services.employee_service.EmployeeRepository')
    @patch('services.employee_service.SessionLocal')
    def test_create_employee(self, mock_session_local, mock_emp_repo):
        """Test creating a new employee."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_emp_repo_instance = MagicMock()
        mock_emp_repo.return_value = mock_emp_repo_instance
        
        from services.employee_service import TeamRepository
        with patch('services.employee_service.TeamRepository') as mock_team_repo:
            mock_team_repo_instance = MagicMock()
            mock_team_repo.return_value = mock_team_repo_instance
            
            mock_team = MagicMock()
            mock_team.id = uuid.uuid4()
            mock_team.name = 'test_team'
            
            mock_team_repo_instance.get_by_id.return_value = mock_team
            mock_emp_repo_instance.get_by_employee_id.return_value = None
            
            mock_new_emp = MagicMock()
            mock_new_emp.id = uuid.uuid4()
            mock_new_emp.employee_id = 'EMP002'
            mock_new_emp.name = 'Jane Doe'
            mock_new_emp.team_id = mock_team.id
            mock_new_emp.region = 'UAE'
            mock_new_emp.is_active = True
            
            mock_emp_repo_instance.create.return_value = mock_new_emp
            
            # Execute
            success, emp_dict, errors = EmployeeService.create_employee(
                employee_id='EMP002',
                name='Jane Doe',
                team_id=mock_team.id,
                region='UAE'
            )
            
            # Verify
            assert success is True
            assert len(errors) == 0
            assert emp_dict['employee_id'] == 'EMP002'

    @patch('services.employee_service.TeamRepository')
    @patch('services.employee_service.EmployeeRepository')
    @patch('services.employee_service.SessionLocal')
    def test_update_employee_assignment_by_external_id(self, mock_session_local, mock_emp_repo, mock_team_repo):
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        employee = MagicMock()
        employee.employee_id = 'EMP001'
        employee.performance_level = 'Employee'
        team = MagicMock()
        team.id = uuid.uuid4()
        team.name = 'Outbound'
        mock_emp_repo.return_value.get_by_employee_id.return_value = employee
        mock_team_repo.return_value.get_by_name.return_value = team

        success, data, errors = EmployeeService.update_employee_assignment('EMP001', 'Outbound', 'Managerial')

        assert success is True
        assert errors == []
        assert data == {
            'employee_id': 'EMP001',
            'team': 'Outbound',
            'performance_level': 'Managerial',
        }
        assert employee.team_id == team.id
        assert employee.performance_level == 'Managerial'
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @patch('services.employee_service.TeamRepository')
    @patch('services.employee_service.EmployeeRepository')
    @patch('services.employee_service.SessionLocal')
    def test_update_employee_assignment_rolls_back_on_commit_failure(self, mock_session_local, mock_emp_repo, mock_team_repo):
        mock_session = MagicMock()
        mock_session.commit.side_effect = RuntimeError('commit failed')
        mock_session_local.return_value = mock_session
        employee = MagicMock()
        employee.employee_id = 'EMP001'
        team = MagicMock()
        team.id = uuid.uuid4()
        team.name = 'Outbound'
        mock_emp_repo.return_value.get_by_employee_id.return_value = employee
        mock_team_repo.return_value.get_by_name.return_value = team

        success, data, errors = EmployeeService.update_employee_assignment('EMP001', 'Outbound', 'Managerial')

        assert success is False
        assert data == {}
        assert errors == ['Failed to update employee assignment: commit failed']
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()

    @patch('services.soft_delete_service.SoftDeleteService.soft_delete_employee')
    @patch('services.employee_service.EmployeeRepository')
    @patch('services.employee_service.SessionLocal')
    def test_delete_employee_resolves_external_id(self, mock_session_local, mock_emp_repo, mock_soft_delete):
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        employee = MagicMock(id=uuid.uuid4())
        mock_emp_repo.return_value.get_by_employee_id.return_value = employee
        mock_soft_delete.return_value = True

        success, errors = EmployeeService.delete_employee('EMP001', 'admin-id')

        assert success is True
        assert errors == []
        mock_soft_delete.assert_called_once_with(mock_session, employee.id, 'admin-id')
        mock_session.close.assert_called_once()


# ============================================================
# PERFORMANCE SERVICE TESTS
# ============================================================

class TestPerformanceService:
    """Test suite for PerformanceService."""

    @patch('services.performance_service.PerformanceRepository')
    @patch('services.performance_service.SessionLocal')
    def test_get_monthly_records(self, mock_session_local, mock_perf_repo):
        """Test getting monthly performance records."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_perf_repo.return_value = mock_repo_instance
        
        mock_record = MagicMock()
        mock_record.id = uuid.uuid4()
        mock_record.employee_id = uuid.uuid4()
        mock_record.team_id = uuid.uuid4()
        mock_record.month = 'January'
        mock_record.year = 2024
        mock_record.score = 85.5
        mock_record.grade = 'B'
        mock_record.status = 'Meets'
        mock_record.uploaded_at = datetime.now()
        
        mock_repo_instance.get_monthly_records.return_value = [mock_record]
        mock_session.query.return_value.filter.return_value.all.return_value = []
        
        # Execute
        records = PerformanceService.get_monthly_records(
            mock_record.team_id,
            'January',
            2024
        )
        
        # Verify
        assert len(records) > 0
        assert records[0]['month'] == 'January'
        mock_session.close.assert_called_once()

    @patch('services.performance_service.PerformanceRepository')
    @patch('services.performance_service.SessionLocal')
    def test_get_employee_history(self, mock_session_local, mock_perf_repo):
        """Test getting employee performance history."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_perf_repo.return_value = mock_repo_instance
        
        mock_record = MagicMock()
        mock_record.id = uuid.uuid4()
        mock_record.employee_id = uuid.uuid4()
        mock_record.team_id = uuid.uuid4()
        mock_record.month = 'January'
        mock_record.year = 2024
        mock_record.score = 85.5
        mock_record.grade = 'B'
        mock_record.status = 'Meets'
        mock_record.uploaded_at = datetime.now()
        
        mock_repo_instance.get_employee_history.return_value = [mock_record]
        mock_session.query.return_value.filter.return_value.all.return_value = []
        
        # Execute
        records = PerformanceService.get_employee_history(
            mock_record.employee_id,
            2024
        )
        
        # Verify
        assert len(records) > 0
        mock_session.close.assert_called_once()


def test_seeding_service_excludes_raw_performance_grade_values():
    assert DatabaseSeeder._should_exclude_raw_row(pd.Series({"Performance Grade": "-"}))
    assert DatabaseSeeder._should_exclude_raw_row(pd.Series({"Performance Grade": "New Staff"}))
    assert DatabaseSeeder._should_exclude_raw_row(pd.Series({"PerformanceGrade": "Leave"}))
    assert not DatabaseSeeder._should_exclude_raw_row(pd.Series({"Performance Grade": "A"}))


# ============================================================
# ERROR HANDLING TESTS
# ============================================================

class TestErrorHandling:
    """Test error handling across services."""

    @patch('services.team_service.TeamRepository')
    @patch('services.team_service.SessionLocal')
    def test_team_service_handles_missing_team(self, mock_session_local, mock_team_repo):
        """Test that TeamService handles missing team gracefully."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_team_repo.return_value = mock_repo_instance
        mock_repo_instance.get_by_name.return_value = None
        
        # Execute
        team = TeamService.get_team('nonexistent_team')
        
        # Verify
        assert team is None

    @patch('services.performance_service.PerformanceRepository')
    @patch('services.performance_service.SessionLocal')
    def test_performance_service_handles_missing_record(self, mock_session_local, mock_perf_repo):
        """Test that PerformanceService handles missing record gracefully."""
        # Setup mocks
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        mock_repo_instance = MagicMock()
        mock_perf_repo.return_value = mock_repo_instance
        mock_repo_instance.get_by_id.return_value = None
        
        # Execute
        success, errors = PerformanceService.delete_performance_record(
            uuid.uuid4(),
            2024
        )
        
        # Verify
        assert success is False
        assert len(errors) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

