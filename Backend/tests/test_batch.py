"""Unit Tests for Batch Processor Service
"""

import pytest
import uuid
from decimal import Decimal
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Base, Team, Employee, PerformanceRecord, TeamKPIConfig, User
from services.batch_processor import BatchProcessor


@pytest.fixture(scope="function")
def db_session():
    """Create in-memory SQLite database session for testing"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Create tables
    Base.metadata.create_all(bind=engine, tables=[
        User.__table__,
        Team.__table__,
        Employee.__table__,
        PerformanceRecord.__table__,
        TeamKPIConfig.__table__
    ])
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@patch('services.audit_service.AuditService.log_operation')
def test_batch_insert_performance_records_success(mock_log, db_session):
    """Verify batch insert succeeds with valid records"""
    team = Team(id=uuid.uuid4(), name="Tech Team", db_name="tech_db", region="UAE")
    db_session.add(team)
    db_session.commit()
    
    emp = Employee(id=uuid.uuid4(), employee_id="EMP111", name="Alice", team_id=team.id)
    db_session.add(emp)
    db_session.commit()
    
    records = [
        {
            "employee_id": str(emp.id),
            "team_id": str(team.id),
            "month": "January",
            "year": 2024,
            "score": 85.0,
            "grade": "B",
            "status": "Meets"
        },
        {
            "employee_id": str(emp.id),
            "team_id": str(team.id),
            "month": "February",
            "year": 2024,
            "score": 92.5,
            "grade": "A",
            "status": "Exceeds"
        }
    ]
    
    result = BatchProcessor.batch_insert_performance_records(db_session, records)
    
    assert result["success_count"] == 2
    assert result["failed_count"] == 0
    assert len(result["failed_records"]) == 0
    assert mock_log.call_count == 2
    
    # Verify records are in database
    db_records = db_session.query(PerformanceRecord).all()
    assert len(db_records) == 2


@patch('services.audit_service.AuditService.log_operation')
def test_batch_insert_performance_records_atomicity_failure(mock_log, db_session):
    """Verify that if one record fails validation up-front, NO records are inserted (atomicity)"""
    team = Team(id=uuid.uuid4(), name="Tech Team", db_name="tech_db", region="UAE")
    db_session.add(team)
    db_session.commit()
    
    emp = Employee(id=uuid.uuid4(), employee_id="EMP111", name="Alice", team_id=team.id)
    db_session.add(emp)
    db_session.commit()
    
    records = [
        {
            "employee_id": str(emp.id),
            "team_id": str(team.id),
            "month": "January",
            "year": 2024,
            "score": 85.0,
            "grade": "B",
            "status": "Meets"
        },
        {
            # Missing team_id (validation failure)
            "employee_id": str(emp.id),
            "month": "February",
            "year": 2024,
            "score": 105.0, # out of bounds score (validation failure)
            "grade": "X", # invalid grade (validation failure)
            "status": "Meets"
        }
    ]
    
    result = BatchProcessor.batch_insert_performance_records(db_session, records)
    
    assert result["success_count"] == 0
    assert result["failed_count"] > 0
    assert mock_log.call_count == 0
    
    # Verify no records were inserted
    db_records = db_session.query(PerformanceRecord).all()
    assert len(db_records) == 0


@patch('services.audit_service.AuditService.log_operation')
def test_batch_insert_performance_records_database_error_isolation(mock_log, db_session):
    """Verify that if a database integrity error occurs on one record, the remaining records still succeed"""
    team = Team(id=uuid.uuid4(), name="Tech Team", db_name="tech_db", region="UAE")
    db_session.add(team)
    db_session.commit()
    
    emp = Employee(id=uuid.uuid4(), employee_id="EMP111", name="Alice", team_id=team.id)
    db_session.add(emp)
    db_session.commit()
    
    records = [
        {
            "employee_id": str(emp.id),
            "team_id": str(team.id),
            "month": "January",
            "year": 2024,
            "score": 85.0,
            "grade": "B",
            "status": "Meets"
        },
        {
            # Month is None -> violates NOT NULL constraint in database
            "employee_id": str(emp.id),
            "team_id": str(team.id),
            "month": None, 
            "year": 2024,
            "score": 90.0,
            "grade": "A",
            "status": "Exceeds"
        },
        {
            "employee_id": str(emp.id),
            "team_id": str(team.id),
            "month": "March",
            "year": 2024,
            "score": 95.0,
            "grade": "A",
            "status": "Exceeds"
        }
    ]
    
    result = BatchProcessor.batch_insert_performance_records(db_session, records)
    
    assert result["success_count"] == 2
    assert result["failed_count"] == 1
    assert len(result["failed_records"]) == 1
    assert mock_log.call_count == 2
    
    # Verify that the successful records are committed to DB
    db_records = db_session.query(PerformanceRecord).all()
    assert len(db_records) == 2
    assert db_records[0].month == "January"
    assert db_records[1].month == "March"


@patch('services.audit_service.AuditService.log_operation')
def test_batch_update_kpi_weights_success(mock_log, db_session):
    """Verify batch weight updates succeed when sum is 1.0"""
    team = Team(id=uuid.uuid4(), name="Design Team", db_name="design_db", region="UAE")
    db_session.add(team)
    db_session.commit()
    
    kpi1 = TeamKPIConfig(team_id=team.id, kpi_key="Attendance", kpi_label="Attend", weight=Decimal("0.40"), actual_col="a", target_col="t")
    kpi2 = TeamKPIConfig(team_id=team.id, kpi_key="Quality", kpi_label="Quality", weight=Decimal("0.60"), actual_col="q", target_col="t")
    db_session.add_all([kpi1, kpi2])
    db_session.commit()
    
    updates = [
        {"kpi_key": "Attendance", "weight": 0.30},
        {"kpi_key": "Quality", "weight": 0.70}
    ]
    
    result = BatchProcessor.batch_update_kpi_weights(db_session, str(team.id), updates)
    assert result["success"] is True
    assert len(result["errors"]) == 0
    assert mock_log.call_count == 2
    
    # Verify new weights are stored
    assert float(kpi1.weight) == 0.30
    assert float(kpi2.weight) == 0.70


@patch('services.audit_service.AuditService.log_operation')
def test_batch_update_kpi_weights_sum_error(mock_log, db_session):
    """Verify batch weight updates fail if weights do not sum to 1.0"""
    team = Team(id=uuid.uuid4(), name="Design Team", db_name="design_db", region="UAE")
    db_session.add(team)
    db_session.commit()
    
    kpi1 = TeamKPIConfig(team_id=team.id, kpi_key="Attendance", kpi_label="Attend", weight=Decimal("0.40"), actual_col="a", target_col="t")
    kpi2 = TeamKPIConfig(team_id=team.id, kpi_key="Quality", kpi_label="Quality", weight=Decimal("0.60"), actual_col="q", target_col="t")
    db_session.add_all([kpi1, kpi2])
    db_session.commit()
    
    updates = [
        {"kpi_key": "Attendance", "weight": 0.50},
        {"kpi_key": "Quality", "weight": 0.80} # 0.50 + 0.80 = 1.30 -> error
    ]
    
    result = BatchProcessor.batch_update_kpi_weights(db_session, str(team.id), updates)
    assert result["success"] is False
    assert len(result["errors"]) > 0
    assert "weights exceed 1.0" in result["errors"][0]
    assert mock_log.call_count == 0
    
    # Verify old weights remain unchanged
    assert float(kpi1.weight) == 0.40
    assert float(kpi2.weight) == 0.60
