"""Corrective-action history from the database: the latest action for an employee-month, the mapping to the legacy
manager_action string, and the recommendation that reads the history. Synthetic data only."""

import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Action, Base, Employee, Team
from services import seeding_service
from services.action_history import DatabaseActionHistory
from services.dashboard_record_service import DashboardRecordService
from services.learning_service import LearningService
from services.seeding_service import DatabaseSeeder
from test_runtime_json_storage import _marketing_workbook


def _engine_after_marketing_upload(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(seeding_service, "SessionLocal", sessionmaker(bind=engine))
    DatabaseSeeder().process_uploaded_file("PMS_Marketing.xlsx", _marketing_workbook())
    return engine


def _add_action(db: Session, *, employee_code, month, year, action_type, action_text, note, created_at, active=True):
    team = db.query(Team).filter(Team.name == "Marketing").one()
    employee = db.query(Employee).filter(Employee.employee_id == employee_code).one()
    db.add(Action(
        employee_id=employee.id, team_id=team.id, month=month, year=year, action_type=action_type,
        action_text=action_text, root_cause_note=note, is_active=active, created_at=created_at,
    ))
    db.commit()


def test_latest_active_action_for_the_month_and_year_is_mapped_to_the_legacy_string(monkeypatch):
    engine = _engine_after_marketing_upload(monkeypatch)
    with Session(bind=engine) as db:
        _add_action(db, employee_code="SGHD90001", month="July", year=2026, action_type="Training",
                    action_text="Old plan", note="old", created_at=dt.datetime(2026, 7, 2, 9, 0, tzinfo=dt.timezone.utc))
        _add_action(db, employee_code="SGHD90001", month="July", year=2026, action_type="PIP",
                    action_text="New plan", note="new", created_at=dt.datetime(2026, 7, 3, 9, 0, tzinfo=dt.timezone.utc))
        _add_action(db, employee_code="SGHD90001", month="July", year=2026, action_type="Warning",
                    action_text="Retired", note="retired", created_at=dt.datetime(2026, 7, 4, 9, 0, tzinfo=dt.timezone.utc),
                    active=False)
        _add_action(db, employee_code="SGHD90001", month="July", year=2025, action_type="Reward",
                    action_text="Last year", note="prior", created_at=dt.datetime(2026, 7, 5, 9, 0, tzinfo=dt.timezone.utc))
        history = DatabaseActionHistory(db)
        latest = history.get_latest_by_employee_and_month("SGHD90001", "July", 2026)
        other_month = history.get_latest_by_employee_and_month("SGHD90001", "June", 2026)
    engine.dispose()

    assert latest.manager_action == "PIP: New plan"
    assert latest.manager_notes == "new"
    assert other_month is None


def test_history_takes_team_score_grade_and_root_cause_from_the_record_and_feeds_the_recommendation(monkeypatch):
    engine = _engine_after_marketing_upload(monkeypatch)
    with Session(bind=engine) as db:
        _add_action(db, employee_code="SGHD90001", month="July", year=2026, action_type="PIP",
                    action_text="New plan", note="new", created_at=dt.datetime(2026, 7, 3, 9, 0, tzinfo=dt.timezone.utc))
        history = DatabaseActionHistory(db).get_history()
        record = next(
            item for item in DashboardRecordService(db).list_records()
            if item.employee_id == "SGHD90001" and item.month == "July"
        )
        recommendation, preferences = LearningService(DatabaseActionHistory(db)).get_historical_recommendations(
            team=record.team,
            score=record.evaluation.score,
            grade=record.evaluation.grade,
            root_cause=record.evaluation.root_cause.kpi if record.evaluation.root_cause else "None",
            default_suggestion="Coaching",
        )
    engine.dispose()

    assert len(history) == 1
    item = history[0]
    assert item.employee_id == "SGHD90001"
    assert item.team == record.team == "Marketing"
    assert item.score == record.evaluation.score
    assert item.grade == record.evaluation.grade
    assert item.root_cause == (record.evaluation.root_cause.kpi if record.evaluation.root_cause else "None")
    assert item.manager_action == "PIP: New plan"
    assert preferences == {"PIP: New plan": 100.0}
    assert recommendation == "PIP: New plan (100.0% historical manager preference)"
