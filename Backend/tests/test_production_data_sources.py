import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Action, Base, Employee, KPIValue, PerformanceRecord, Team, User
from models.schemas import KPIWeight, Target
from api.routers.settings import update_targets, update_weights
from services.employee_directory_service import EmployeeDirectoryService
from services.kpi_configuration_service import KPIConfigurationService
from services.team_action_service import TeamActionService


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Team.__table__,
            Employee.__table__,
            User.__table__,
            PerformanceRecord.__table__,
            KPIValue.__table__,
            Action.__table__,
        ],
    )
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield session
    session.close()


@pytest.fixture
def employee(db):
    team = Team(
        id=uuid.uuid4(),
        name="inbound_storage",
        db_name="Inbound",
        display_name="Inbound",
        region="EGY",
        team_level="employee",
    )
    employee = Employee(
        id=uuid.uuid4(),
        employee_id="SGHD70001",
        name="Test Employee",
        team=team,
        region="EGY",
        performance_level="Employee",
    )
    db.add_all([team, employee])
    db.commit()
    return employee


def test_employee_directory_reads_relational_employee_identity(db, employee):
    rows = EmployeeDirectoryService(db).list(name="70001", team="Inbound")

    assert rows == [{
        "id": "SGHD70001",
        "employee_id": "SGHD70001",
        "name": "Test Employee",
        "team": "Inbound",
        "region": "EGY",
        "performance_level": "Employee",
        "position": None,
        "status": "Active",
    }]


def test_kpi_configuration_exposes_tracked_weights_and_latest_persisted_target(db, employee):
    record = PerformanceRecord(
        id=uuid.uuid4(),
        year=2026,
        employee_id=employee.id,
        team_id=employee.team_id,
        month="June",
        performance_level="Employee",
        region="EGY",
        score=91.1,
        grade="B",
        status="Meets",
    )
    db.add(record)
    db.flush()
    db.add(KPIValue(
        record_id=record.id,
        record_year=record.year,
        kpi_key="Attendance",
        actual_value=.678,
        target_value=.75,
        achievement_ratio=.904,
        weight_applied=.70,
        contribution=.6328,
    ))
    db.commit()

    service = KPIConfigurationService(db)
    inbound_weights = next(item for item in service.list_weights() if item["team"] == "Inbound")
    inbound_targets = next(item for item in service.list_targets() if item["team"] == "Inbound")

    assert inbound_weights["weights"]["Attendance"] == pytest.approx(.70)
    assert inbound_targets["targets"]["Attendance"] == pytest.approx(.75)


def test_team_action_is_persisted_once_per_team_period(db, employee):
    service = TeamActionService(db)
    scope = {"role": "Admin", "legacy_unscoped": False}

    first = service.save(
        team_reference="Inbound",
        month="June",
        year=2026,
        overall_action="Review attendance gaps",
        scope=scope,
        user_id=None,
    )
    second = service.save(
        team_reference="Inbound",
        month="June",
        year=2026,
        overall_action="Run weekly attendance review",
        scope=scope,
        user_id=None,
    )

    assert first["year"] == 2026
    assert second["overall_action"] == "Run weekly attendance review"
    assert service.get(team_reference="Inbound", month="June", year=2026, scope=scope) == second
    assert db.query(Action).filter(Action.action_type == "Team Action").count() == 1


@pytest.mark.asyncio
async def test_legacy_settings_mutations_cannot_create_a_second_scoring_source():
    with pytest.raises(HTTPException) as weights_error:
        await update_weights(KPIWeight(team="Inbound", weights={"Attendance": 0.7}), _user={})
    with pytest.raises(HTTPException) as targets_error:
        await update_targets(Target(team="Inbound", targets={"Attendance": 0.75}), _user={})

    assert weights_error.value.status_code == 409
    assert targets_error.value.status_code == 409
