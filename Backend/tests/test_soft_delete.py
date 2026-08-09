"""Soft Delete and Restore Tests
"""

import pytest
import uuid
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Base, Team, Employee, User, Action, TeamKPIConfig
from repositories.team_repository import TeamRepository
from repositories.employee_repository import EmployeeRepository
from services.employee_service import EmployeeService
from services.soft_delete_service import SoftDeleteService
from services.audit_service import AuditService
from config.database import get_db

@pytest.fixture(scope="function")
def db_session():
    """Create in-memory SQLite database session for testing"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Create tables (excluding AuditLog because SQLite does not compile JSONB)
    Base.metadata.create_all(bind=engine, tables=[
        User.__table__,
        Team.__table__,
        Employee.__table__,
        Action.__table__,
        TeamKPIConfig.__table__
    ])
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_team_soft_delete_and_restore_repository(db_session):
    """Verify TeamRepository soft_delete and restore works"""
    repo = TeamRepository(db_session, Team)
    
    team = repo.create({
        "name": "Soft Deleted Team",
        "db_name": "soft_deleted_db",
        "region": "UAE",
        "is_active": True
    })
    assert team.is_active is True
    
    # Soft delete
    result = repo.soft_delete(team.id)
    assert result is True
    
    # Should not be fetched by default
    fetched = repo.get_by_id(team.id)
    assert fetched is None
    
    # Can be fetched with include_deleted=True
    fetched_deleted = repo.get_by_id(team.id, include_deleted=True)
    assert fetched_deleted is not None
    assert fetched_deleted.is_active is False
    
    # Restore
    restore_result = repo.restore(team.id)
    assert restore_result is True
    
    fetched_restored = repo.get_by_id(team.id)
    assert fetched_restored is not None
    assert fetched_restored.is_active is True


@patch('services.audit_service.AuditService.log_operation')
def test_employee_soft_delete_and_restore_service(mock_log, db_session):
    """Verify SoftDeleteService soft delete and restore for employees"""
    team_repo = TeamRepository(db_session, Team)
    emp_repo = EmployeeRepository(db_session, Employee)
    
    team = team_repo.create({
        "name": "Team A",
        "db_name": "team_a_db",
        "region": "UAE",
        "is_active": True
    })
    
    emp = emp_repo.create({
        "employee_id": "EMP999",
        "name": "Jane Smith",
        "team_id": team.id,
        "region": "UAE",
        "is_active": True
    })
    
    user_id = str(uuid.uuid4())
    
    # Soft delete via service
    success = SoftDeleteService.soft_delete_employee(db_session, str(emp.id), performed_by_user_id=user_id)
    assert success is True
    
    # Verify employee state
    assert emp.is_active is False
    
    # Verify AuditService was called
    mock_log.assert_called_once_with(
        db=db_session,
        table_name="employees",
        operation="SOFT_DELETE",
        record_id=str(emp.id),
        old_values={"is_active": True},
        new_values={"is_active": False},
        performed_by_user_id=user_id
    )
    
    mock_log.reset_mock()
    
    # Restore via service
    success_restore = SoftDeleteService.restore_employee(db_session, str(emp.id), performed_by_user_id=user_id)
    assert success_restore is True
    
    # Verify state restored
    assert emp.is_active is True
    mock_log.assert_called_once_with(
        db=db_session,
        table_name="employees",
        operation="RESTORE",
        record_id=str(emp.id),
        old_values={"is_active": False},
        new_values={"is_active": True},
        performed_by_user_id=user_id
    )


def test_employee_getters_exclude_inactive(db_session):
    """Verify getters automatically filter by is_active == True unless include_deleted=True"""
    team_repo = TeamRepository(db_session, Team)
    emp_repo = EmployeeRepository(db_session, Employee)
    
    team = team_repo.create({
        "name": "Team A",
        "db_name": "team_a_db",
        "region": "UAE",
        "is_active": True
    })
    
    emp_active = emp_repo.create({
        "employee_id": "EMP111",
        "name": "Active Employee",
        "team_id": team.id,
        "region": "UAE",
        "is_active": True
    })
    
    emp_inactive = emp_repo.create({
        "employee_id": "EMP222",
        "name": "Inactive Employee",
        "team_id": team.id,
        "region": "UAE",
        "is_active": False
    })
    
    # Mocking SessionLocal to return our in-memory db_session
    with patch('services.employee_service.SessionLocal', return_value=db_session):
        # get_all_employees
        all_active = EmployeeService.get_all_employees()
        assert len(all_active) == 1
        assert all_active[0]['employee_id'] == "EMP111"
        
        all_with_deleted = EmployeeService.get_all_employees(include_deleted=True)
        assert len(all_with_deleted) == 2
        
        # get_employee
        assert EmployeeService.get_employee(str(emp_inactive.id)) is None
        assert EmployeeService.get_employee(str(emp_inactive.id), include_deleted=True) is not None
        
        # get_employees_by_team
        team_active = EmployeeService.get_employees_by_team(team.id)
        assert len(team_active) == 1
        
        team_all = EmployeeService.get_employees_by_team(team.id, include_deleted=True)
        assert len(team_all) == 2
