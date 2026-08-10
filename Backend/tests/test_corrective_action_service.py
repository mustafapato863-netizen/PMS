import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Action, Base, Employee, PerformanceRecord, Team, User
from services.corrective_action_service import CorrectiveActionService, CorrectiveActionValidationError


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


def test_transfer_export_and_import_preserve_action_history(db, employee):
    service = CorrectiveActionService(db)
    saved, _ = service.save(
        employee_identifier=employee.employee_id,
        month="July",
        year=2026,
        manager_action="Training: Review the workflow",
        manager_notes="Initial root cause",
    )
    service.deactivate(employee_identifier=employee.employee_id, action_id=saved["id"])

    payload = service.export_transfer_payload()
    assert payload["format"] == "pms.corrective-actions"
    assert payload["version"] == 1
    assert payload["record_count"] == 1
    assert payload["records"][0]["is_active"] is False
    # Archived legacy rows may have an empty action body. The downloaded
    # backup must still be importable without inventing a replacement text.
    payload["records"][0]["action_text"] = ""
    db.query(Action).delete()
    db.commit()

    result = service.import_transfer_payload(payload)
    assert result == {"created": 1, "updated": 0, "total": 1}
    restored = db.query(Action).one()
    assert restored.employee_id == employee.id
    assert restored.team_id == employee.team_id
    assert restored.is_active is False
    assert restored.action_text == ""
    assert restored.root_cause_note == "Initial root cause"

    payload["records"][0]["action_text"] = "Updated after transfer"
    result = service.import_transfer_payload(payload)
    assert result == {"created": 0, "updated": 1, "total": 1}
    assert db.query(Action).one().action_text == "Updated after transfer"


def test_transfer_import_keeps_existing_required_fields_when_backup_row_is_blank(db, employee):
    service = CorrectiveActionService(db)
    saved, _ = service.save(
        employee_identifier=employee.employee_id,
        month="August",
        year=2026,
        manager_action="Coaching: Review the workflow",
    )

    payload = service.export_transfer_payload()
    payload["records"][0]["month"] = ""
    payload["records"][0]["action_text"] = ""
    payload["records"][0]["status"] = "Completed"

    result = service.import_transfer_payload(payload)

    assert result == {"created": 0, "updated": 1, "total": 1}
    restored = db.query(Action).one()
    assert restored.month == "August"
    assert restored.action_text == "Review the workflow"
    assert restored.status == "Completed"


def test_transfer_import_still_rejects_missing_required_fields_for_new_rows(db, employee):
    service = CorrectiveActionService(db)
    payload = {
        "format": "pms.corrective-actions",
        "version": 1,
        "records": [
            {
                "employee": {"employee_id": employee.employee_id},
                "month": "",
                "year": 2026,
                "action_type": "Coaching",
                "action_text": "",
            }
        ],
    }

    with pytest.raises(CorrectiveActionValidationError, match="Row 1: month and action_text are required"):
        service.import_transfer_payload(payload)


def test_transfer_import_accepts_legacy_manager_action_rows(db, employee):
    service = CorrectiveActionService(db)
    payload = {
        "format": "pms.corrective-actions",
        "version": 1,
        "records": [
            {
                "id": str(uuid.uuid4()),
                "employee_id": employee.employee_id,
                "team": "Test Team",
                "month": "",
                "year": "",
                "manager_action": "Training: Review the legacy workflow",
                "manager_notes": "Legacy root cause",
                "timestamp": "2026-09-05T10:00:00+00:00",
            }
        ],
    }

    result = service.import_transfer_payload(payload)

    assert result == {"created": 1, "updated": 0, "total": 1}
    restored = db.query(Action).one()
    assert restored.month == "September"
    assert restored.year == 2026
    assert restored.action_type == "Training"
    assert restored.action_text == "Review the legacy workflow"
    assert restored.root_cause_note == "Legacy root cause"
