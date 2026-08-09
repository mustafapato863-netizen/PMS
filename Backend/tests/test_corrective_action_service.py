import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Action, Base, Employee, PerformanceRecord, Team, User
from services.corrective_action_service import CorrectiveActionService


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[Team.__table__, Employee.__table__, User.__table__, PerformanceRecord.__table__, Action.__table__],
    )
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield session
    session.close()


@pytest.fixture
def employee(db):
    team = Team(id=uuid.uuid4(), name="Test Team", db_name="test_team", region="EGY")
    employee = Employee(
        id=uuid.uuid4(),
        employee_id="SGHD70001",
        name="Test Employee",
        team=team,
        region="EGY",
    )
    db.add_all([team, employee])
    db.commit()
    return employee


def test_action_persists_without_performance_record(db, employee):
    service = CorrectiveActionService(db)

    saved, is_update = service.save(
        employee_identifier=employee.employee_id,
        month="May",
        year=2026,
        manager_action="Training: Review the workflow",
        manager_notes="Booking Rate",
    )

    assert is_update is False
    assert saved["employee_id"] == "SGHD70001"
    assert saved["manager_action"] == "Training: Review the workflow"
    assert db.query(Action).count() == 1

    history = service.get_history(employee.employee_id)
    assert [item["id"] for item in history] == [saved["id"]]


def test_update_and_delete_keep_single_historical_row(db, employee):
    service = CorrectiveActionService(db)
    saved, _ = service.save(
        employee_identifier=employee.employee_id,
        month="May",
        year=2026,
        manager_action="Coaching: Initial follow-up",
    )

    updated, is_update = service.save(
        employee_identifier=employee.employee_id,
        month="May",
        year=2026,
        action_id=saved["id"],
        manager_action="Monitor: Weekly follow-up",
    )
    assert is_update is True
    assert updated["manager_action"] == "Monitor: Weekly follow-up"
    assert db.query(Action).count() == 1

    service.deactivate(employee_identifier=employee.employee_id, action_id=saved["id"])
    assert service.get_history(employee.employee_id) == []
    assert db.query(Action).count() == 1
    assert db.query(Action).one().is_active is False


def test_retry_with_same_client_id_is_idempotent(db, employee):
    service = CorrectiveActionService(db)
    payload = {
        "employee_identifier": employee.employee_id,
        "month": "May",
        "year": 2026,
        "action_id": "SGHD70001_May_123456",
        "manager_action": "Coaching: Daily follow-up",
    }

    first, first_is_update = service.save(**payload)
    second, second_is_update = service.save(**payload)

    assert first_is_update is False
    assert second_is_update is True
    assert second["id"] == first["id"]
    assert db.query(Action).count() == 1


def test_save_rolls_back_when_commit_fails(db, employee, monkeypatch):
    service = CorrectiveActionService(db)
    original_commit = db.commit

    def fail_commit():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="database unavailable"):
        service.save(
            employee_identifier=employee.employee_id,
            month="May",
            year=2026,
            manager_action="Coaching: Should roll back",
        )

    monkeypatch.setattr(db, "commit", original_commit)
    assert db.query(Action).count() == 0
