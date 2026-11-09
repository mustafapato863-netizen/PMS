import logging
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.database import Base
from models.models import Employee, PerformanceRecord, Team, UploadLog
from repositories.performance_repository import PerformanceRepository


@pytest.fixture
def records():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    first = Team(id=uuid.uuid4(), name="Resubmission", db_name="resubmission", display_name="Resubmission", region="EGY", team_level="employee")
    second = Team(id=uuid.uuid4(), name="Re-Submission EGY", db_name="resubmission_egy", display_name="Re-Submission EGY", region="EGY", team_level="employee")
    uae = Team(id=uuid.uuid4(), name="Re-Submission", db_name="re_submission", display_name="Re-Submission", region="UAE", team_level="employee")
    employee = Employee(id=uuid.uuid4(), employee_id="EMP1", name="Test", team_id=first.id, region="EGY")
    db.add_all([first, second, uae, employee])
    db.flush()
    now = datetime(2026, 9, 5)
    older = UploadLog(id=uuid.uuid4(), team_id=first.id, month="September", year=2026, status="success", uploaded_at=now)
    newer = UploadLog(id=uuid.uuid4(), team_id=second.id, month="September", year=2026, status="success", uploaded_at=now + timedelta(days=1))
    failed = UploadLog(id=uuid.uuid4(), team_id=first.id, month="September", year=2026, status="failed", uploaded_at=now + timedelta(days=2))
    db.add_all([older, newer, failed])
    db.flush()
    def row(team, upload, score, region="EGY"):
        return PerformanceRecord(id=uuid.uuid4(), year=2026, employee_id=employee.id, team_id=team.id, month="September", performance_level="Employee", region=region, score=score, grade="A" if score >= 90 else "D", status="Meets", upload_id=upload.id if upload else None)
    old_record, winner, failed_record, uae_record = row(first, older, 70), row(second, newer, 95), row(first, failed, 50), row(uae, None, 88, "UAE")
    db.add_all([old_record, winner, failed_record, uae_record])
    db.commit()
    yield db, old_record, winner, failed_record, uae_record, older, newer
    db.close()
    engine.dispose()


def test_latest_successful_upload_is_selected_before_filters_and_paging(records, caplog):
    db, old, winner, failed, uae, _, _ = records
    repository = PerformanceRepository(db, PerformanceRecord)
    with caplog.at_level(logging.INFO):
        rows = repository.get_dashboard_summary_rows(periods=[(2026, "September")])
    assert {row["record_id"] for row in rows} == {winner.id, uae.id}
    assert str(winner.id) in caplog.text and str(winner.upload_id) in caplog.text
    assert repository.get_dashboard_summary_rows(periods=[(2026, "September")], max_score=80) == []
    page, total = repository.get_dashboard_record_page(year=2026, month="September", page_size=1, include_total=True)
    assert total == 2 and {row.id for row in page} == {winner.id, uae.id}
    index = repository.get_dashboard_record_index(year=2026)
    assert len(index) == 2


@pytest.mark.parametrize("reason", ["missing", "tie"])
def test_ambiguous_uploads_fail_closed(records, reason):
    db, old, winner, failed, uae, older, newer = records
    if reason == "missing":
        older.status = newer.status = "failed"
    else:
        newer.uploaded_at = older.uploaded_at
    db.commit()
    with pytest.raises(HTTPException) as error:
        PerformanceRepository(db, PerformanceRecord).get_dashboard_summary_rows(periods=[(2026, "September")])
    assert error.value.status_code == 409
