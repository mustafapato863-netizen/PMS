"""Dashboard cache observes committed evaluation changes without Redis bumps."""
import logging
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Base, Employee, KPIValue, PerformanceRecord, Team, User
from services.cache_service import CacheService
from services.cache_invalidation_service import CacheInvalidationService
from services.evaluation.workflow import EvaluationWorkflow
from services.performance_dashboard_read_service import PerformanceDashboardReadService


def test_scoped_summary_refreshes_after_apply_and_rollback_without_shared_version(monkeypatch):
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    cache = {}
    monkeypatch.setattr(CacheService, "get_json", lambda key, **_: cache.get(key))
    monkeypatch.setattr(CacheService, "set_json", lambda key, value, **_: cache.setdefault(key, value))
    monkeypatch.setattr(CacheInvalidationService, "get_data_version", lambda: 0)
    monkeypatch.setattr(CacheInvalidationService, "get_config_version", lambda: 0)
    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda *_: None)
    try:
        admin = User(id=uuid.uuid4(), username="cache-review-admin", email="cache-review@example.invalid", role="Admin", password_hash="synthetic")
        team = Team(id=uuid.uuid4(), name="Coding", db_name="Coding", display_name="Coding", region="UAE", team_level="employee")
        employee = Employee(id=uuid.uuid4(), employee_id="CACHE-SYNTHETIC", name="Cache test", team=team, region="UAE", performance_level="Employee")
        record = PerformanceRecord(id=uuid.uuid4(), year=2026, employee=employee, team=team, month="August", performance_level="Employee", score=70, grade="D", status="Below")
        db.add_all([admin, team, employee, record])
        db.commit()
        actor = {"user_id": str(admin.id), "role": "Admin", "has_unrestricted_team_access": True, "legacy_unscoped": False}
        workflow = EvaluationWorkflow(db)
        scope = next(row for row in workflow.sync_catalog(actor)["scopes"] if row["display_name"] == "Coding" and row["performance_level"] == "Employee" and row["position_name"] == "")
        draft = workflow.open_draft(actor, scope["id"], 2026, 8)
        lines = [{**line, "weight": 1 if index == 0 else 0, "direction": "higher_better", "target_mode": "fixed", "target": 10} for index, line in enumerate(draft["lines"])]
        workflow.edit_draft(actor, draft["id"], lines)
        db.add(KPIValue(record_id=record.id, record_year=2026, kpi_key=lines[0]["kpi_key"], actual_value=8, target_value=10, achievement_ratio=.7, weight_applied=1, contribution=.7))
        db.commit()
        workflow.impact_preview(actor, draft["id"])
        workflow.approve(actor, draft["id"])
        service = PerformanceDashboardReadService(db, actor)
        assert service.summary(period="2026-08")["current"]["average_score"] == 70
        # The same request is genuinely cached before a lifecycle mutation.
        count = len(cache)
        assert service.summary(period="2026-08")["current"]["average_score"] == 70
        assert len(cache) == count
        applied = workflow.apply(actor, scope["id"], 2026, 8)
        assert service.summary(period="2026-08")["current"]["average_score"] == 80
        # Persisted pin enrichment must not replace the scope/version cache key
        # with a record/year pair. Prove a warm request does not query the roster.
        assert all(isinstance(key, str) and key.startswith("pms:v1:performance:summary:") for key in cache)
        with monkeypatch.context() as warm:
            def reject_projection(**kwargs):
                raise AssertionError("Pinned summary repeat missed its response cache")
            warm.setattr(service.repository, "get_dashboard_summary_rows", reject_projection)
            assert service.summary(period="2026-08")["current"]["average_score"] == 80
        workflow.rollback(actor, applied["revision_id"])
        assert service.summary(period="2026-08")["current"]["average_score"] == 70
    finally:
        db.close()
        engine.dispose()


def test_bump_failure_logs_kind_without_credentials(monkeypatch, caplog):
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        workflow = EvaluationWorkflow(db)

        def explode():
            raise RuntimeError("redis://secret-user:secret-pass@internal")

        monkeypatch.setattr(CacheInvalidationService, "bump_data_version", explode)
        with caplog.at_level(logging.WARNING, logger="services.evaluation.workflow"):
            workflow._bump("data")
        assert "kind=data" in caplog.text
        assert "secret-pass" not in caplog.text
        assert "redis://" not in caplog.text
    finally:
        db.close()
        engine.dispose()
