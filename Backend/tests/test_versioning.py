"""Unit Tests for Versioning Service
"""

import pytest
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Base, Team, Employee, PerformanceRecord, PerformanceRecordVersion, User
from services.versioning_service import VersioningService


@pytest.fixture(scope="function")
def db_session():
    """Create in-memory SQLite database session for testing"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Create tables needed for versioning
    Base.metadata.create_all(bind=engine, tables=[
        User.__table__,
        Team.__table__,
        Employee.__table__,
        PerformanceRecord.__table__,
        PerformanceRecordVersion.__table__
    ])
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_version_increments_sequentially(db_session):
    """Verify version numbers increment sequentially (1, 2, 3...)"""
    # Setup team, employee, and performance record
    team = Team(id=uuid.uuid4(), name="Sales Team", db_name="sales_db", region="UAE")
    db_session.add(team)
    db_session.commit()
    
    employee = Employee(id=uuid.uuid4(), employee_id="EMP555", name="Alex Carter", team_id=team.id)
    db_session.add(employee)
    db_session.commit()
    
    record = PerformanceRecord(
        id=uuid.uuid4(),
        year=2024,
        employee_id=employee.id,
        team_id=team.id,
        month="January",
        score=Decimal("80.00"),
        grade="C",
        status="Meets",
        uploaded_at=datetime.now() - timedelta(hours=3)
    )
    db_session.add(record)
    db_session.commit()
    
    # Create Version 1
    v1 = VersioningService.create_version(db_session, str(record.id), 2024, change_reason="Initial update")
    assert v1.version_number == 1
    assert v1.score == Decimal("80.00")
    
    # Modify record score and create Version 2
    record.score = Decimal("85.50")
    record.grade = "B"
    db_session.commit()
    
    v2 = VersioningService.create_version(db_session, str(record.id), 2024, change_reason="Performance boost")
    assert v2.version_number == 2
    assert v2.score == Decimal("85.50")
    
    # Query history
    history = VersioningService.get_version_history(db_session, str(record.id))
    assert len(history) == 2
    assert history[0].version_number == 2
    assert history[1].version_number == 1


def test_get_record_as_of_date(db_session):
    """Verify get_record_as_of_date returns correct snapshot for a past date"""
    team = Team(id=uuid.uuid4(), name="Tech Team", db_name="tech_db", region="UAE")
    db_session.add(team)
    db_session.commit()
    
    employee = Employee(id=uuid.uuid4(), employee_id="EMP777", name="Dave Miller", team_id=team.id)
    db_session.add(employee)
    db_session.commit()
    
    base_time = datetime.now() - timedelta(hours=10)
    record = PerformanceRecord(
        id=uuid.uuid4(),
        year=2024,
        employee_id=employee.id,
        team_id=team.id,
        month="January",
        score=Decimal("70.00"),
        grade="D",
        status="Below",
        uploaded_at=base_time
    )
    db_session.add(record)
    db_session.commit()
    
    # Create Version 1 (1 hour later)
    v1 = VersioningService.create_version(db_session, str(record.id), 2024)
    v1.changed_at = base_time + timedelta(hours=1)
    
    # Modify record and create Version 2 (2 hours later)
    record.score = Decimal("82.00")
    record.grade = "B"
    record.status = "Meets"
    db_session.commit()
    
    v2 = VersioningService.create_version(db_session, str(record.id), 2024)
    v2.changed_at = base_time + timedelta(hours=2)
    db_session.commit()

    # Query before record was created
    pre_create = VersioningService.get_record_as_of_date(db_session, str(record.id), 2024, base_time - timedelta(minutes=1))
    assert pre_create is None
    
    # Query after creation, before version 1
    at_base = VersioningService.get_record_as_of_date(db_session, str(record.id), 2024, base_time + timedelta(minutes=30))
    assert at_base is not None
    assert at_base["version_number"] == 0
    assert at_base["score"] == Decimal("70.00")
    
    # Query after version 1, before version 2
    at_v1 = VersioningService.get_record_as_of_date(db_session, str(record.id), 2024, base_time + timedelta(hours=1, minutes=30))
    assert at_v1 is not None
    assert at_v1["version_number"] == 1
    assert at_v1["score"] == Decimal("70.00")
    
    # Query after version 2
    at_v2 = VersioningService.get_record_as_of_date(db_session, str(record.id), 2024, base_time + timedelta(hours=3))
    assert at_v2 is not None
    assert at_v2["version_number"] == 2
    assert at_v2["score"] == Decimal("82.00")


def test_diff_versions(db_session):
    """Verify diff_versions accurately calculates differences"""
    v1 = PerformanceRecordVersion(score=Decimal("80.00"), grade="C", status="Meets")
    v2 = PerformanceRecordVersion(score=Decimal("90.00"), grade="A", status="Exceeds")
    
    diff = VersioningService.diff_versions(v1, v2)
    
    assert "score" in diff
    assert diff["score"] == {"old": 80.0, "new": 90.0}
    
    assert "grade" in diff
    assert diff["grade"] == {"old": "C", "new": "A"}
    
    assert "status" in diff
    assert diff["status"] == {"old": "Meets", "new": "Exceeds"}
    
    # Test identical versions
    diff_same = VersioningService.diff_versions(v1, v1)
    assert len(diff_same) == 0
