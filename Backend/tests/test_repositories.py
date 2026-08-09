"""
Comprehensive test suite for all repositories
Tests CRUD operations, custom queries, error handling, and transactions
"""

import pytest
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from models.models import (
    Base, Team, Employee, PerformanceRecord, User, Action, 
    AuditLog, OnboardingState, TeamKPIConfig, KPIValue
)
from repositories.base_repository import BaseRepository
from repositories.team_repository import TeamRepository
from repositories.employee_repository import EmployeeRepository
from repositories.performance_repository import PerformanceRepository
from repositories.user_repository import UserRepository
from repositories.action_repository import ActionRepository
from repositories.audit_log_repository import AuditLogRepository
from repositories.onboarding_repository import OnboardingRepository


# ============================================================
# FIXTURES - Database Setup
# ============================================================

@pytest.fixture(scope="function")
def db():
    """Create in-memory SQLite database for testing"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Create only the necessary tables manually
    # Exclude models that use JSONB/INET which SQLite doesn't support
    from sqlalchemy import Table, MetaData
    
    metadata = MetaData()
    
    # Create only the core tables we need
    Base.metadata.create_all(bind=engine, tables=[
        Team.__table__,
        Employee.__table__,
        PerformanceRecord.__table__,
        KPIValue.__table__,
        User.__table__,
        Action.__table__,
        OnboardingState.__table__,
        TeamKPIConfig.__table__,
    ])
    
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def sample_team(db: Session):
    """Create a sample team for testing"""
    team = Team(
        id=uuid.uuid4(),
        name="Inbound",
        db_name="inbound_db",
        region="UAE",
        is_active=True
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


@pytest.fixture
def sample_employee(db: Session, sample_team):
    """Create a sample employee for testing"""
    employee = Employee(
        id=uuid.uuid4(),
        employee_id="EMP001",
        name="John Doe",
        team_id=sample_team.id,
        region="UAE",
        is_active=True
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


@pytest.fixture
def sample_user(db: Session):
    """Create a sample user for testing"""
    user = User(
        id=uuid.uuid4(),
        username="admin",
        email="admin@test.com",
        password_hash="hashed_password",
        role="Admin",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ============================================================
# BASE REPOSITORY TESTS
# ============================================================

class TestBaseRepository:
    """Test BaseRepository CRUD operations"""
    
    def test_create(self, db: Session, sample_team):
        """Test create operation"""
        repo = BaseRepository(db, Team)
        
        new_team = repo.create({
            'name': 'Outbound',
            'db_name': 'outbound_db',
            'region': 'UAE',
            'is_active': True
        })
        
        assert new_team is not None
        assert new_team.name == 'Outbound'
        assert new_team.is_active is True
    
    def test_get_by_id(self, db: Session, sample_team):
        """Test get by ID"""
        repo = BaseRepository(db, Team)
        
        team = repo.get_by_id(sample_team.id)
        
        assert team is not None
        assert team.name == "Inbound"
        assert team.id == sample_team.id
    
    def test_get_by_id_not_found(self, db: Session):
        """Test get by ID when not found"""
        repo = BaseRepository(db, Team)
        
        team = repo.get_by_id(uuid.uuid4())
        
        assert team is None
    
    def test_get_all(self, db: Session, sample_team):
        """Test get all with pagination"""
        repo = BaseRepository(db, Team)
        
        # Add another team
        repo.create({
            'name': 'Outbound',
            'db_name': 'outbound_db',
            'region': 'UAE',
            'is_active': True
        })
        
        teams = repo.get_all(skip=0, limit=10)
        
        assert len(teams) == 2
    
    def test_get_all_with_skip(self, db: Session):
        """Test get all with skip"""
        repo = BaseRepository(db, Team)
        
        # Create 3 teams
        for i in range(3):
            repo.create({
                'name': f'Team{i}',
                'db_name': f'team_db_{i}',
                'region': 'UAE',
                'is_active': True
            })
        
        teams = repo.get_all(skip=1, limit=10)
        
        assert len(teams) == 2
    
    def test_update(self, db: Session, sample_team):
        """Test update operation"""
        repo = BaseRepository(db, Team)
        
        updated_team = repo.update(sample_team.id, {'region': 'US'})
        
        assert updated_team is not None
        assert updated_team.region == 'US'
    
    def test_update_not_found(self, db: Session):
        """Test update when record not found"""
        repo = BaseRepository(db, Team)
        
        result = repo.update(uuid.uuid4(), {'region': 'US'})
        
        assert result is None
    
    def test_delete(self, db: Session, sample_team):
        """Test delete operation"""
        repo = BaseRepository(db, Team)
        
        result = repo.delete(sample_team.id)
        
        assert result is True
        assert repo.get_by_id(sample_team.id) is None
    
    def test_delete_not_found(self, db: Session):
        """Test delete when record not found"""
        repo = BaseRepository(db, Team)
        
        result = repo.delete(uuid.uuid4())
        
        assert result is False
    
    def test_count(self, db: Session):
        """Test count operation"""
        repo = BaseRepository(db, Team)
        
        repo.create({
            'name': 'Team1',
            'db_name': 'team_db_1',
            'region': 'UAE',
            'is_active': True
        })
        repo.create({
            'name': 'Team2',
            'db_name': 'team_db_2',
            'region': 'UAE',
            'is_active': True
        })
        
        count = repo.count()
        
        assert count == 2


# ============================================================
# TEAM REPOSITORY TESTS
# ============================================================

class TestTeamRepository:
    """Test TeamRepository custom queries"""
    
    def test_get_by_name(self, db: Session, sample_team):
        """Test get team by name"""
        repo = TeamRepository(db, Team)
        
        team = repo.get_by_name("Inbound")
        
        assert team is not None
        assert team.id == sample_team.id
    
    def test_get_by_db_name(self, db: Session, sample_team):
        """Test get team by database name"""
        repo = TeamRepository(db, Team)
        
        team = repo.get_by_db_name("inbound_db")
        
        assert team is not None
        assert team.name == "Inbound"
    
    def test_get_active_teams(self, db: Session):
        """Test get active teams"""
        repo = TeamRepository(db, Team)
        
        # Create active team
        repo.create({
            'name': 'Active',
            'db_name': 'active_db',
            'region': 'UAE',
            'is_active': True
        })
        
        # Create inactive team
        repo.create({
            'name': 'Inactive',
            'db_name': 'inactive_db',
            'region': 'UAE',
            'is_active': False
        })
        
        active_teams = repo.get_active_teams()
        
        assert len(active_teams) == 1
        assert active_teams[0].name == 'Active'
    
    def test_get_by_region(self, db: Session):
        """Test get teams by region"""
        repo = TeamRepository(db, Team)
        
        repo.create({
            'name': 'UAETeam1',
            'db_name': 'uae_db_1',
            'region': 'UAE',
            'is_active': True
        })
        repo.create({
            'name': 'USTeam',
            'db_name': 'us_db',
            'region': 'US',
            'is_active': True
        })
        
        uae_teams = repo.get_by_region("UAE")
        
        assert len(uae_teams) == 1
        assert uae_teams[0].region == "UAE"
    
    def test_count_active(self, db: Session):
        """Test count active teams"""
        repo = TeamRepository(db, Team)
        
        repo.create({
            'name': 'Team1',
            'db_name': 'team_db_1',
            'region': 'UAE',
            'is_active': True
        })
        repo.create({
            'name': 'Team2',
            'db_name': 'team_db_2',
            'region': 'UAE',
            'is_active': False
        })
        
        count = repo.count_active()
        
        assert count == 1
    
    def test_soft_delete(self, db: Session, sample_team):
        """Test soft delete"""
        repo = TeamRepository(db, Team)
        
        result = repo.soft_delete(sample_team.id)
        
        assert result is True
        team = repo.get_by_id(sample_team.id, include_deleted=True)
        assert team.is_active is False
    
    def test_restore(self, db: Session, sample_team):
        """Test restore soft-deleted team"""
        repo = TeamRepository(db, Team)
        
        repo.soft_delete(sample_team.id)
        result = repo.restore(sample_team.id)
        
        assert result is True
        team = repo.get_by_id(sample_team.id)
        assert team.is_active is True


# ============================================================
# EMPLOYEE REPOSITORY TESTS
# ============================================================

class TestEmployeeRepository:
    """Test EmployeeRepository custom queries"""
    
    def test_get_by_employee_id(self, db: Session, sample_employee):
        """Test get employee by external ID"""
        repo = EmployeeRepository(db, Employee)
        
        emp = repo.get_by_employee_id("EMP001")
        
        assert emp is not None
        assert emp.name == "John Doe"
    
    def test_get_by_team(self, db: Session, sample_team):
        """Test get employees by team"""
        repo = EmployeeRepository(db, Employee)
        
        # Create multiple employees
        repo.create({
            'employee_id': 'EMP001',
            'name': 'John',
            'team_id': sample_team.id,
            'region': 'UAE',
            'is_active': True
        })
        repo.create({
            'employee_id': 'EMP002',
            'name': 'Jane',
            'team_id': sample_team.id,
            'region': 'UAE',
            'is_active': True
        })
        
        employees = repo.get_by_team(sample_team.id)
        
        assert len(employees) == 2
    
    def test_get_active_by_team(self, db: Session, sample_team):
        """Test get active employees by team"""
        repo = EmployeeRepository(db, Employee)
        
        repo.create({
            'employee_id': 'EMP001',
            'name': 'John',
            'team_id': sample_team.id,
            'region': 'UAE',
            'is_active': True
        })
        repo.create({
            'employee_id': 'EMP002',
            'name': 'Jane',
            'team_id': sample_team.id,
            'region': 'UAE',
            'is_active': False
        })
        
        active_emps = repo.get_active_by_team(sample_team.id)
        
        assert len(active_emps) == 1
        assert active_emps[0].name == 'John'
    
    def test_count_by_team(self, db: Session, sample_team):
        """Test count employees by team"""
        repo = EmployeeRepository(db, Employee)
        
        repo.create({
            'employee_id': 'EMP002',
            'name': 'Jane',
            'team_id': sample_team.id,
            'region': 'UAE',
            'is_active': True
        })
        
        count = repo.count_by_team(sample_team.id)
        
        assert count == 1
    
    def test_search_by_name(self, db: Session, sample_team):
        """Test search employees by name"""
        repo = EmployeeRepository(db, Employee)
        
        repo.create({
            'employee_id': 'EMP002',
            'name': 'Jane Smith',
            'team_id': sample_team.id,
            'region': 'UAE',
            'is_active': True
        })
        
        results = repo.search_by_name("jane")
        
        assert len(results) == 1
        assert "jane" in results[0].name.lower()


# ============================================================
# PERFORMANCE REPOSITORY TESTS
# ============================================================

class TestPerformanceRepository:
    """Test PerformanceRepository custom queries"""

    def test_dashboard_keys_use_logical_team_name(self, db: Session):
        """Storage slugs must not hide records from the config-facing dashboard identity."""
        team = Team(
            id=uuid.uuid4(),
            name="pre_approvals_op_dubai",
            db_name="Pre-Approvals OP Dubai",
            display_name="Pre-Approvals OP Dubai",
            region="UAE",
            is_active=True,
        )
        employee = Employee(
            id=uuid.uuid4(),
            employee_id="EMP-DXB-1",
            name="Dubai Agent",
            team=team,
            region="UAE",
            is_active=True,
        )
        record = PerformanceRecord(
            id=uuid.uuid4(),
            employee=employee,
            team_id=team.id,
            month="May",
            year=2026,
            score=90,
            grade="A",
            status="Exceeds",
        )
        db.add_all([team, employee, record])
        db.commit()

        repo = PerformanceRepository(db, PerformanceRecord)

        assert repo.get_dashboard_record_keys() == [
            ("EMP-DXB-1", "Pre-Approvals OP Dubai", "May", 2026)
        ]
        assert repo.get_dashboard_record_keys(team="Pre-Approvals OP Dubai") == [
            ("EMP-DXB-1", "Pre-Approvals OP Dubai", "May", 2026)
        ]
        assert repo.get_dashboard_record_keys(team="pre_approvals_op_dubai") == [
            ("EMP-DXB-1", "Pre-Approvals OP Dubai", "May", 2026)
        ]
    
    def test_get_by_employee_month(self, db: Session, sample_employee):
        """Test get performance record by employee and month"""
        repo = PerformanceRepository(db, PerformanceRecord)
        
        # Create performance record
        record = repo.create({
            'id': uuid.uuid4(),
            'employee_id': sample_employee.id,
            'team_id': sample_employee.team_id,
            'month': 'January',
            'year': 2024,
            'score': 85.5,
            'grade': 'B',
            'status': 'Meets'
        })
        
        retrieved = repo.get_by_employee_month(
            sample_employee.id, 'January', 2024
        )
        
        assert retrieved is not None
        assert retrieved.score == 85.5
    
    def test_get_monthly_records(self, db: Session, sample_employee):
        """Test get all records for team in specific month"""
        repo = PerformanceRepository(db, PerformanceRecord)
        
        # Create multiple records
        repo.create({
            'id': uuid.uuid4(),
            'employee_id': sample_employee.id,
            'team_id': sample_employee.team_id,
            'month': 'January',
            'year': 2024,
            'score': 85.5,
            'grade': 'B',
            'status': 'Meets'
        })
        repo.create({
            'id': uuid.uuid4(),
            'employee_id': sample_employee.id,
            'team_id': sample_employee.team_id,
            'month': 'January',
            'year': 2024,
            'score': 90.0,
            'grade': 'A',
            'status': 'Exceeds'
        })
        
        records = repo.get_monthly_records(
            sample_employee.team_id, 'January', 2024
        )
        
        assert len(records) == 2
    
    def test_get_employee_history(self, db: Session, sample_employee):
        """Test get performance history for employee"""
        repo = PerformanceRepository(db, PerformanceRecord)
        
        # Create records for different months
        for month_idx, month in enumerate(['January', 'February', 'March'], 1):
            repo.create({
                'id': uuid.uuid4(),
                'employee_id': sample_employee.id,
                'team_id': sample_employee.team_id,
                'month': month,
                'year': 2024,
                'score': 80.0 + month_idx,
                'grade': 'B',
                'status': 'Meets'
            })
        
        history = repo.get_employee_history(sample_employee.id, 2024)
        
        assert len(history) == 3


# ============================================================
# USER REPOSITORY TESTS
# ============================================================

class TestUserRepository:
    """Test UserRepository custom queries"""
    
    def test_get_by_username(self, db: Session, sample_user):
        """Test get user by username"""
        repo = UserRepository(db, User)
        
        user = repo.get_by_username("admin")
        
        assert user is not None
        assert user.email == "admin@test.com"
    
    def test_get_by_email(self, db: Session, sample_user):
        """Test get user by email"""
        repo = UserRepository(db, User)
        
        user = repo.get_by_email("admin@test.com")
        
        assert user is not None
        assert user.username == "admin"
    
    def test_get_by_role(self, db: Session):
        """Test get users by role"""
        repo = UserRepository(db, User)
        
        repo.create({
            'username': 'admin1',
            'email': 'admin1@test.com',
            'password_hash': 'hash',
            'role': 'Admin',
            'is_active': True
        })
        repo.create({
            'username': 'viewer1',
            'email': 'viewer1@test.com',
            'password_hash': 'hash',
            'role': 'Viewer',
            'is_active': True
        })
        
        admins = repo.get_by_role("Admin")
        
        assert len(admins) == 1
        assert admins[0].role == "Admin"
    
    def test_get_active_users(self, db: Session):
        """Test get active users"""
        repo = UserRepository(db, User)
        
        repo.create({
            'username': 'user1',
            'email': 'user1@test.com',
            'password_hash': 'hash',
            'role': 'Viewer',
            'is_active': True
        })
        repo.create({
            'username': 'user2',
            'email': 'user2@test.com',
            'password_hash': 'hash',
            'role': 'Viewer',
            'is_active': False
        })
        
        active = repo.get_active_users()
        
        assert len(active) == 1
    
    def test_disable_user(self, db: Session, sample_user):
        """Test disable user"""
        repo = UserRepository(db, User)
        
        result = repo.disable_user(sample_user.id)
        
        assert result is True
        user = repo.get_by_id(sample_user.id, include_deleted=True)
        assert user.is_active is False
    
    def test_enable_user(self, db: Session, sample_user):
        """Test enable user"""
        repo = UserRepository(db, User)
        
        repo.disable_user(sample_user.id)
        result = repo.enable_user(sample_user.id)
        
        assert result is True
        user = repo.get_by_id(sample_user.id)
        assert user.is_active is True


# ============================================================
# ACTION REPOSITORY TESTS
# ============================================================

class TestActionRepository:
    """Test ActionRepository custom queries"""
    
    def test_get_by_employee(self, db: Session, sample_employee, sample_user):
        """Test get actions by employee"""
        repo = ActionRepository(db, Action)
        
        repo.create({
            'employee_id': sample_employee.id,
            'team_id': sample_employee.team_id,
            'month': 'January',
            'year': 2024,
            'action_type': 'Training',
            'action_text': 'Needs training',
            'status': 'Open',
            'created_by_user_id': sample_user.id
        })
        
        actions = repo.get_by_employee(sample_employee.id)
        
        assert len(actions) == 1
        assert actions[0].action_type == 'Training'
    
    def test_get_by_status(self, db: Session, sample_employee, sample_user):
        """Test get actions by status"""
        repo = ActionRepository(db, Action)
        
        repo.create({
            'employee_id': sample_employee.id,
            'team_id': sample_employee.team_id,
            'month': 'January',
            'year': 2024,
            'action_type': 'Training',
            'action_text': 'Training needed',
            'status': 'Open',
            'created_by_user_id': sample_user.id
        })
        repo.create({
            'employee_id': sample_employee.id,
            'team_id': sample_employee.team_id,
            'month': 'January',
            'year': 2024,
            'action_type': 'Reward',
            'action_text': 'Recognition',
            'status': 'Completed',
            'created_by_user_id': sample_user.id
        })
        
        open_actions = repo.get_by_status('Open')
        
        assert len(open_actions) == 1


# ============================================================
# ONBOARDING REPOSITORY TESTS
# ============================================================

class TestOnboardingRepository:
    """Test OnboardingRepository persistence"""
    
    def test_get_or_create(self, db: Session, sample_team):
        """Test get or create onboarding state"""
        repo = OnboardingRepository(db, OnboardingState)
        
        state = repo.get_or_create(sample_team.id)
        
        assert state is not None
        assert state.team_id == sample_team.id
        assert state.status == "pending"
        assert state.current_step == 0
    
    def test_update_step(self, db: Session, sample_team):
        """Test update onboarding step"""
        repo = OnboardingRepository(db, OnboardingState)
        
        repo.get_or_create(sample_team.id)
        state = repo.update_step(sample_team.id, 2, "in_progress")
        
        assert state.current_step == 2
        assert state.status == "in_progress"
    
    def test_mark_completed(self, db: Session, sample_team):
        """Test mark onboarding as completed"""
        repo = OnboardingRepository(db, OnboardingState)
        
        repo.get_or_create(sample_team.id)
        state = repo.mark_completed(sample_team.id)
        
        assert state.status == "completed"
        assert state.completed_at is not None
    
    def test_mark_failed(self, db: Session, sample_team):
        """Test mark onboarding as failed"""
        repo = OnboardingRepository(db, OnboardingState)
        
        repo.get_or_create(sample_team.id)
        state = repo.mark_failed(sample_team.id, "Database connection failed")
        
        assert state.status == "failed"
        assert state.last_error == "Database connection failed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
