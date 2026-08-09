"""
Integration Tests for Phase 5 Stages 4-7
Tests API routers, database repositories, and end-to-end workflows
"""

import pytest
import uuid
from datetime import datetime
from decimal import Decimal

from config.database import SessionLocal
from models.models import Team, TeamKPIConfig, Employee, PerformanceRecord, OnboardingState
from repositories.team_repository import TeamRepository
from repositories.employee_repository import EmployeeRepository
from repositories.performance_repository import PerformanceRepository
from repositories.onboarding_repository import OnboardingRepository


from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def db():
    """Database session using in-memory SQLite for tests"""
    engine = create_engine("sqlite:///:memory:")
    
    from models.models import Base
    Base.metadata.create_all(bind=engine)
    
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestSessionLocal()
    
    yield db
    
    db.close()


@pytest.fixture
def team_data():
    """Sample team data with unique identifiers"""
    unique_id = str(uuid.uuid4())[:8]
    return {
        'name': f'Test Team {unique_id}',
        'db_name': f'test_db_{unique_id}',
        'region': 'UAE',
        'is_active': True
    }


@pytest.fixture
def kpi_data():
    """Sample KPI data"""
    return {
        'kpi_key': 'Attendance',
        'kpi_label': 'Attendance Rate',
        'weight': Decimal('0.70'),
        'direction': 'higher_better',
        'unit': '%',
        'color': '#3B82F6',
        'actual_col': 'A.Attend%',
        'target_col': 'T.Attend%',
        'display_order': 1
    }


@pytest.fixture
def employee_data():
    """Sample employee data with unique identifiers"""
    unique_id = str(uuid.uuid4())[:8]
    return {
        'employee_id': f'EMP{unique_id}',
        'name': f'John Doe {unique_id}',
        'region': 'UAE',
        'is_active': True
    }


class TestTeamRepository:
    """Tests for TeamRepository database operations"""
    
    def test_create_team(self, db, team_data):
        """Test creating a team"""
        repo = TeamRepository(db, Team)
        
        team = repo.create(team_data)
        
        assert team is not None
        assert team.name == team_data['name']
        assert team.db_name == team_data['db_name']
        assert team.region == 'UAE'
        assert team.is_active == True
        assert team.id is not None
    
    def test_get_team_by_id(self, db, team_data):
        """Test retrieving team by ID"""
        repo = TeamRepository(db, Team)
        
        created = repo.create(team_data)
        retrieved = repo.get_by_id(created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == team_data['name']
    
    def test_get_team_by_name(self, db, team_data):
        """Test retrieving team by name"""
        repo = TeamRepository(db, Team)
        
        repo.create(team_data)
        team = repo.get_by_name(team_data['name'])
        
        assert team is not None
        assert team.name == team_data['name']
    
    def test_get_active_teams(self, db):
        """Test getting all active teams"""
        repo = TeamRepository(db, Team)
        
        # Create active team
        repo.create({'name': 'Active 1', 'db_name': 'active1', 'region': 'UAE', 'is_active': True})
        repo.create({'name': 'Active 2', 'db_name': 'active2', 'region': 'UAE', 'is_active': True})
        repo.create({'name': 'Inactive', 'db_name': 'inactive', 'region': 'UAE', 'is_active': False})
        
        active = repo.get_active_teams()
        
        assert len(active) >= 2
        assert all(team.is_active for team in active)
    
    def test_soft_delete_team(self, db, team_data):
        """Test soft deleting a team"""
        repo = TeamRepository(db, Team)
        
        team = repo.create(team_data)
        assert team.is_active == True
        
        repo.soft_delete(team.id)
        
        deleted = repo.get_by_id(team.id, include_deleted=True)
        assert deleted.is_active == False
    
    def test_restore_team(self, db, team_data):
        """Test restoring a soft-deleted team"""
        repo = TeamRepository(db, Team)
        
        team = repo.create(team_data)
        repo.soft_delete(team.id)
        repo.restore(team.id)
        
        restored = repo.get_by_id(team.id)
        assert restored.is_active == True
    
    def test_count_active_teams(self, db):
        """Test counting active teams"""
        repo = TeamRepository(db, Team)
        
        repo.create({'name': 'T1', 'db_name': 'db1', 'region': 'UAE', 'is_active': True})
        repo.create({'name': 'T2', 'db_name': 'db2', 'region': 'UAE', 'is_active': True})
        
        count = repo.count_active()
        assert count >= 2


class TestTeamKPIConfig:
    """Tests for TeamKPIConfig operations"""
    
    def test_create_kpi_config(self, db, team_data, kpi_data):
        """Test creating KPI config for team"""
        repo = TeamRepository(db, Team)
        
        team = repo.create(team_data)
        
        kpi = TeamKPIConfig(
            team_id=team.id,
            **kpi_data
        )
        db.add(kpi)
        db.commit()
        db.refresh(kpi)
        
        assert kpi.id is not None
        assert kpi.team_id == team.id
        assert kpi.kpi_label == 'Attendance Rate'
    
    def test_get_kpis_for_team(self, db, team_data, kpi_data):
        """Test retrieving all KPIs for a team"""
        repo = TeamRepository(db, Team)
        
        team = repo.create(team_data)
        
        # Create multiple KPIs
        for i in range(3):
            kpi = TeamKPIConfig(
                team_id=team.id,
                kpi_key=f'KPI{i}',
                kpi_label=f'KPI Label {i}',
                weight=Decimal('0.33'),
                direction='higher_better',
                unit='%',
                color='#10B981',
                actual_col=f'A.KPI{i}',
                target_col=f'T.KPI{i}',
                display_order=i
            )
            db.add(kpi)
        db.commit()
        
        kpis = db.query(TeamKPIConfig).filter(TeamKPIConfig.team_id == team.id).all()
        assert len(kpis) == 3


class TestEmployeeRepository:
    """Tests for EmployeeRepository operations"""
    
    def test_create_employee(self, db, team_data, employee_data):
        """Test creating employee for team"""
        team_repo = TeamRepository(db, Team)
        emp_repo = EmployeeRepository(db, Employee)
        
        team = team_repo.create(team_data)
        employee_data['team_id'] = team.id
        
        employee = emp_repo.create(employee_data)
        
        assert employee is not None
        assert employee.employee_id == employee_data['employee_id']
        assert employee.name == employee_data['name']
        assert employee.team_id == team.id
    
    def test_get_employee_by_id(self, db, team_data, employee_data):
        """Test retrieving employee by ID"""
        team_repo = TeamRepository(db, Team)
        emp_repo = EmployeeRepository(db, Employee)
        
        team = team_repo.create(team_data)
        employee_data['team_id'] = team.id
        
        created = emp_repo.create(employee_data)
        retrieved = emp_repo.get_by_id(created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id
    
    def test_get_employee_by_employee_id(self, db, team_data, employee_data):
        """Test retrieving employee by external employee ID"""
        team_repo = TeamRepository(db, Team)
        emp_repo = EmployeeRepository(db, Employee)
        
        team = team_repo.create(team_data)
        employee_data['team_id'] = team.id
        
        emp_repo.create(employee_data)
        employee = emp_repo.get_by_employee_id(employee_data['employee_id'])
        
        assert employee is not None
        assert employee.employee_id == employee_data['employee_id']
    
    def test_get_employees_by_team(self, db, team_data, employee_data):
        """Test retrieving all employees in a team"""
        team_repo = TeamRepository(db, Team)
        emp_repo = EmployeeRepository(db, Employee)
        
        team = team_repo.create(team_data)
        
        # Create multiple employees
        for i in range(3):
            emp_data = employee_data.copy()
            emp_data['employee_id'] = f'EMP{i:03d}'
            emp_data['name'] = f'Employee {i}'
            emp_data['team_id'] = team.id
            emp_repo.create(emp_data)
        
        employees = emp_repo.get_by_team(team.id)
        assert len(employees) == 3
    
    def test_get_active_employees_by_team(self, db, team_data, employee_data):
        """Test getting active employees in a team"""
        team_repo = TeamRepository(db, Team)
        emp_repo = EmployeeRepository(db, Employee)
        
        team = team_repo.create(team_data)
        
        # Create active and inactive
        employee_data['team_id'] = team.id
        emp_repo.create(employee_data)
        
        emp_inactive = employee_data.copy()
        emp_inactive['employee_id'] = 'EMPINACTIVE'
        emp_inactive['is_active'] = False
        emp_repo.create(emp_inactive)
        
        active = emp_repo.get_active_by_team(team.id)
        assert len(active) == 1
        assert all(e.is_active for e in active)


class TestPerformanceRepository:
    """Tests for PerformanceRepository operations"""
    
    def test_create_performance_record(self, db, team_data, employee_data):
        """Test creating performance record"""
        team_repo = TeamRepository(db, Team)
        emp_repo = EmployeeRepository(db, Employee)
        perf_repo = PerformanceRepository(db, PerformanceRecord)
        
        team = team_repo.create(team_data)
        employee_data['team_id'] = team.id
        employee = emp_repo.create(employee_data)
        
        record_data = {
            'employee_id': employee.id,
            'team_id': team.id,
            'month': 'January',
            'year': 2024,
            'score': Decimal('85.5'),
            'grade': 'B',
            'status': 'Meets'
        }
        
        record = perf_repo.create(record_data)
        
        assert record is not None
        assert record.score == Decimal('85.5')
        assert record.grade == 'B'
    
    def test_get_by_employee_month(self, db, team_data, employee_data):
        """Test retrieving performance record by employee and month"""
        team_repo = TeamRepository(db, Team)
        emp_repo = EmployeeRepository(db, Employee)
        perf_repo = PerformanceRepository(db, PerformanceRecord)
        
        team = team_repo.create(team_data)
        employee_data['team_id'] = team.id
        employee = emp_repo.create(employee_data)
        
        record_data = {
            'employee_id': employee.id,
            'team_id': team.id,
            'month': 'January',
            'year': 2024,
            'score': Decimal('85.5'),
            'grade': 'B',
            'status': 'Meets'
        }
        
        perf_repo.create(record_data)
        retrieved = perf_repo.get_by_employee_month(employee.id, 'January', 2024)
        
        assert retrieved is not None
        assert retrieved.score == Decimal('85.5')
    
    def test_get_monthly_records(self, db, team_data, employee_data):
        """Test retrieving all records for team in specific month"""
        team_repo = TeamRepository(db, Team)
        emp_repo = EmployeeRepository(db, Employee)
        perf_repo = PerformanceRepository(db, PerformanceRecord)
        
        team = team_repo.create(team_data)
        
        # Create employees and records
        for i in range(3):
            emp_data = employee_data.copy()
            emp_data['employee_id'] = f'EMP{i:03d}'
            emp_data['team_id'] = team.id
            employee = emp_repo.create(emp_data)
            
            record_data = {
                'employee_id': employee.id,
                'team_id': team.id,
                'month': 'January',
                'year': 2024,
                'score': Decimal('85.0'),
                'grade': 'B',
                'status': 'Meets'
            }
            perf_repo.create(record_data)
        
        records = perf_repo.get_monthly_records(team.id, 'January', 2024)
        assert len(records) == 3


class TestOnboardingRepository:
    """Tests for OnboardingRepository operations"""
    
    def test_get_or_create_onboarding_state(self, db, team_data):
        """Test creating onboarding state"""
        team_repo = TeamRepository(db, Team)
        onboarding_repo = OnboardingRepository(db, OnboardingState)
        
        team = team_repo.create(team_data)
        state = onboarding_repo.get_or_create(team.id)
        
        assert state is not None
        assert state.team_id == team.id
        assert state.status == 'pending'
        assert state.current_step == 0
    
    def test_update_step(self, db, team_data):
        """Test updating onboarding step"""
        team_repo = TeamRepository(db, Team)
        onboarding_repo = OnboardingRepository(db, OnboardingState)
        
        team = team_repo.create(team_data)
        state = onboarding_repo.get_or_create(team.id)
        
        onboarding_repo.update_step(team.id, 3, 'in_progress')
        
        updated = onboarding_repo.get_by_team(team.id)
        assert updated.current_step == 3
        assert updated.status == 'in_progress'
    
    def test_mark_completed(self, db, team_data):
        """Test marking onboarding as completed"""
        team_repo = TeamRepository(db, Team)
        onboarding_repo = OnboardingRepository(db, OnboardingState)
        
        team = team_repo.create(team_data)
        onboarding_repo.get_or_create(team.id)
        onboarding_repo.mark_completed(team.id)
        
        state = onboarding_repo.get_by_team(team.id)
        assert state.status == 'completed'
        assert state.completed_at is not None
    
    def test_mark_failed(self, db, team_data):
        """Test marking onboarding as failed"""
        team_repo = TeamRepository(db, Team)
        onboarding_repo = OnboardingRepository(db, OnboardingState)
        
        team = team_repo.create(team_data)
        onboarding_repo.get_or_create(team.id)
        onboarding_repo.mark_failed(team.id, "Test error")
        
        state = onboarding_repo.get_by_team(team.id)
        assert state.status == 'failed'
        assert state.last_error == "Test error"
    
    def test_reset_onboarding(self, db, team_data):
        """Test resetting onboarding state"""
        team_repo = TeamRepository(db, Team)
        onboarding_repo = OnboardingRepository(db, OnboardingState)
        
        team = team_repo.create(team_data)
        state = onboarding_repo.get_or_create(team.id)
        onboarding_repo.mark_completed(team.id)
        
        # Reset
        onboarding_repo.reset(team.id)
        
        reset_state = onboarding_repo.get_by_team(team.id)
        assert reset_state.status == 'pending'
        assert reset_state.current_step == 0
    
    def test_get_pending_teams(self, db):
        """Test getting teams with pending onboarding"""
        team_repo = TeamRepository(db, Team)
        onboarding_repo = OnboardingRepository(db, OnboardingState)
        
        team1 = team_repo.create({'name': 'Team1', 'db_name': 'db1', 'region': 'UAE'})
        team2 = team_repo.create({'name': 'Team2', 'db_name': 'db2', 'region': 'UAE'})
        
        onboarding_repo.get_or_create(team1.id)
        onboarding_repo.get_or_create(team2.id)
        onboarding_repo.mark_completed(team1.id)
        
        pending = onboarding_repo.get_pending_teams()
        assert any(s.team_id == team2.id for s in pending)


class TestEndToEndWorkflow:
    """Tests for complete end-to-end workflows"""
    
    def test_team_creation_workflow(self, db, team_data, kpi_data):
        """Test complete team creation workflow"""
        team_repo = TeamRepository(db, Team)
        
        # Create team
        team = team_repo.create(team_data)
        assert team is not None
        
        # Get team
        retrieved = team_repo.get_by_name(team_data['name'])
        assert retrieved is not None
        
        # Verify team is active
        assert retrieved.is_active == True
    
    def test_employee_management_workflow(self, db, team_data, employee_data):
        """Test complete employee management workflow"""
        team_repo = TeamRepository(db, Team)
        emp_repo = EmployeeRepository(db, Employee)
        
        # Create team
        team = team_repo.create(team_data)
        
        # Create employees
        employee_data['team_id'] = team.id
        emp1 = emp_repo.create(employee_data)
        
        emp2_data = employee_data.copy()
        emp2_data['employee_id'] = 'EMP002'
        emp2 = emp_repo.create(emp2_data)
        
        # Query employees
        team_employees = emp_repo.get_by_team(team.id)
        assert len(team_employees) == 2
        
        # Soft delete one employee
        emp1.is_active = False
        db.commit()
        
        active = emp_repo.get_active_by_team(team.id)
        assert len(active) == 1
    
    def test_performance_tracking_workflow(self, db, team_data, employee_data):
        """Test complete performance tracking workflow"""
        team_repo = TeamRepository(db, Team)
        emp_repo = EmployeeRepository(db, Employee)
        perf_repo = PerformanceRepository(db, PerformanceRecord)
        
        # Create team
        team = team_repo.create(team_data)
        
        # Create employee
        employee_data['team_id'] = team.id
        employee = emp_repo.create(employee_data)
        
        # Record performance for multiple months
        for month_num, month in enumerate(['January', 'February', 'March'], 1):
            record_data = {
                'employee_id': employee.id,
                'team_id': team.id,
                'month': month,
                'year': 2024,
                'score': Decimal(f'{80 + month_num}'),
                'grade': 'B',
                'status': 'Meets'
            }
            perf_repo.create(record_data)
        
        # Query employee history
        history = perf_repo.get_employee_history(employee.id, 2024)
        assert len(history) == 3
        
        # Query specific month
        jan_record = perf_repo.get_by_employee_month(employee.id, 'January', 2024)
        assert jan_record is not None
        assert jan_record.score == Decimal('81')
    
    def test_onboarding_workflow(self, db, team_data):
        """Test complete onboarding workflow"""
        team_repo = TeamRepository(db, Team)
        onboarding_repo = OnboardingRepository(db, OnboardingState)
        
        # Create team
        team = team_repo.create(team_data)
        
        # Start onboarding
        state = onboarding_repo.get_or_create(team.id)
        assert state.status == 'pending'
        
        # Progress through steps
        onboarding_repo.mark_started(team.id)
        state = onboarding_repo.get_by_team(team.id)
        assert state.status == 'in_progress'
        assert state.started_at is not None
        
        # Update steps
        for step in range(1, 7):
            onboarding_repo.update_step(team.id, step)
        
        # Complete onboarding
        onboarding_repo.mark_completed(team.id)
        state = onboarding_repo.get_by_team(team.id)
        assert state.status == 'completed'
        assert state.completed_at is not None
        assert state.current_step == 6


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
