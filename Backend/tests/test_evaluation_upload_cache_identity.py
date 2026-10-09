"""Committed workbook replacements invalidate cached summaries without Redis."""
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Base, Employee, EmployeeUploadBatch, PerformanceRecord, Team, UploadLog
from services.cache_service import CacheService
from services.cache_invalidation_service import CacheInvalidationService
from services.performance_dashboard_read_service import PerformanceDashboardReadService


def test_reused_upload_log_with_new_batch_refreshes_cached_summary(monkeypatch):
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    cache = {}
    monkeypatch.setattr(CacheService, "get_json", lambda key, **_: cache.get(key))
    monkeypatch.setattr(CacheService, "set_json", lambda key, value, **_: cache.setdefault(key, value))
    monkeypatch.setattr(CacheInvalidationService, "get_data_version", lambda: 0)
    monkeypatch.setattr(CacheInvalidationService, "get_config_version", lambda: 0)
    try:
        team = Team(id=uuid.uuid4(), name="Coding", db_name="Coding", region="UAE", team_level="employee")
        employee = Employee(id=uuid.uuid4(), employee_id="UPLOAD-CACHE-SYNTHETIC", name="Synthetic", team=team, region="UAE", performance_level="Employee")
        first = EmployeeUploadBatch(id=uuid.uuid4(), filename="first-synthetic.xlsx", status="completed")
        second = EmployeeUploadBatch(id=uuid.uuid4(), filename="second-synthetic.xlsx", status="completed")
        log = UploadLog(id=uuid.uuid4(), batch_id=first.id, team=team, year=2026, month="August", status="success", record_count=1)
        record = PerformanceRecord(id=uuid.uuid4(), year=2026, employee=employee, team=team, month="August", performance_level="Employee", score=70, grade="D", status="Below", upload_id=log.id)
        db.add_all([team, employee, first, second, log, record])
        db.commit()
        service = PerformanceDashboardReadService(db, {"role": "Admin", "has_unrestricted_team_access": True, "legacy_unscoped": False})
        assert service.summary(period="2026-08")["current"]["average_score"] == 70
        count = len(cache)
        assert service.summary(period="2026-08")["current"]["average_score"] == 70
        assert len(cache) == count
        # The real uploader reuses a per-team/month log and replaces batch_id;
        # neither log count nor its original uploaded_at necessarily changes.
        log.batch_id = second.id
        record.score = 80
        record.grade = "C"
        db.commit()
        assert service.summary(period="2026-08")["current"]["average_score"] == 80
    finally:
        db.close()
        engine.dispose()
