"""Integration Tests for Bulk Operations API Endpoints
"""

import pytest
import uuid
from decimal import Decimal
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Base, User, RolePermission, Team, Employee, PerformanceRecord, TeamKPIConfig
from services.permission_seed import seed_role_permissions
from services.auth_service import AuthenticationService
from api.middleware.auth_middleware import AuthMiddleware
from api.routers.bulk_operations import router as bulk_router
from config.database import get_db


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
        RolePermission.__table__,
        Team.__table__,
        Employee.__table__,
        PerformanceRecord.__table__,
        TeamKPIConfig.__table__
    ])
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    # Seed role permissions
    seed_role_permissions(session)
    
    yield session
    session.close()


@pytest.fixture(scope="function")
def test_client(db_session):
    """FastAPI TestClient mounted with bulk operations router"""
    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.include_router(bulk_router)
    
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
            
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@patch('services.audit_service.AuditService.log_operation')
def test_bulk_insert_performance_records_endpoint(mock_log, test_client, db_session):
    """Verify POST /bulk/performance/records validates and inserts data"""
    # Create Admin user and authenticate
    admin_user = AuthenticationService.create_user(db_session, "admin_user", "admin@test.com", "SecurePassword123!", "Admin")
    token = AuthenticationService.authenticate_user(db_session, "admin_user", "SecurePassword123!")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create team and employee
    team = Team(id=uuid.uuid4(), name="Support Team", db_name="support_db", region="UAE")
    db_session.add(team)
    db_session.commit()
    
    emp = Employee(id=uuid.uuid4(), employee_id="EMP333", name="Charlie", team_id=team.id)
    db_session.add(emp)
    db_session.commit()
    
    payload = [
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
    
    # Send request
    response = test_client.post("/bulk/performance/records", json=payload, headers=headers)
    assert response.status_code == 201
    
    data = response.json()
    assert data["success"] is True
    assert "Batch insert completed" in data["message"]
    
    # Verify in DB
    records_count = db_session.query(PerformanceRecord).count()
    assert records_count == 2


@patch('services.audit_service.AuditService.log_operation')
def test_bulk_update_kpi_weights_endpoint(mock_log, test_client, db_session):
    """Verify PATCH /bulk/teams/{team_id}/kpi-config updates KPI weights"""
    # Create Admin user and authenticate
    admin_user = AuthenticationService.create_user(db_session, "admin_user", "admin@test.com", "SecurePassword123!", "Admin")
    token = AuthenticationService.authenticate_user(db_session, "admin_user", "SecurePassword123!")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create team and KPI configs
    team = Team(id=uuid.uuid4(), name="Ops Team", db_name="ops_db", region="UAE")
    db_session.add(team)
    db_session.commit()
    
    kpi1 = TeamKPIConfig(team_id=team.id, kpi_key="Speed", kpi_label="Speed", weight=Decimal("0.50"), actual_col="s", target_col="t")
    kpi2 = TeamKPIConfig(team_id=team.id, kpi_key="Quality", kpi_label="Quality", weight=Decimal("0.50"), actual_col="q", target_col="t")
    db_session.add_all([kpi1, kpi2])
    db_session.commit()
    
    payload = [
        {"kpi_key": "Speed", "weight": 0.40},
        {"kpi_key": "Quality", "weight": 0.60}
    ]
    
    # Send request
    response = test_client.patch(f"/bulk/teams/{team.id}/kpi-config", json=payload, headers=headers)
    assert response.status_code == 200
    
    data = response.json()
    assert data["success"] is True
    
    # Verify in DB
    assert float(kpi1.weight) == 0.40
    assert float(kpi2.weight) == 0.60


@patch('services.audit_service.AuditService.log_operation')
def test_bulk_delete_employees_endpoint(mock_log, test_client, db_session):
    """Verify DELETE /bulk/employees soft-deletes a list of employees"""
    # Create Admin user and authenticate
    admin_user = AuthenticationService.create_user(db_session, "admin_user", "admin@test.com", "SecurePassword123!", "Admin")
    token = AuthenticationService.authenticate_user(db_session, "admin_user", "SecurePassword123!")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create team and employees
    team = Team(id=uuid.uuid4(), name="Marketing Team", db_name="marketing_db", region="UAE")
    db_session.add(team)
    db_session.commit()
    
    emp1 = Employee(id=uuid.uuid4(), employee_id="EMP881", name="Ethan", team_id=team.id, is_active=True)
    emp2 = Employee(id=uuid.uuid4(), employee_id="EMP882", name="Emma", team_id=team.id, is_active=True)
    db_session.add_all([emp1, emp2])
    db_session.commit()
    
    payload = {
        "employee_ids": [str(emp1.id), str(emp2.id)]
    }
    
    # Send request
    response = test_client.request("DELETE", "/bulk/employees", json=payload, headers=headers)
    assert response.status_code == 200
    
    data = response.json()
    assert data["success"] is True
    assert "Successfully bulk deleted" in data["message"]
    
    # Verify they are soft-deleted in DB
    assert emp1.is_active is False
    assert emp2.is_active is False
