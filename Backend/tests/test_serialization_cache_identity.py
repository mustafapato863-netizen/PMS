"""Legacy serialization stays with the row that was just loaded.

The process cache used to keep ``ser:{id}`` for five minutes. Apply and
rollback rewrite that same id, including a different year of the composite
key, and a Redis version bump does not clear this cache.
"""
import time
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.dependencies import (
    _serialize_cache,
    clear_serialization_cache,
    serialization_cache_key,
    serialize_performance_record,
)
from api.routers.performance import router as performance_router
from config.database import get_db
from models.models import Base, Employee, KPIValue, PerformanceRecord, Team, User
from models.schemas import EvaluationData, PerformanceRecord as SchemaRecord
from services.cache_service import CacheService
from services.evaluation.workflow import EvaluationWorkflow


def _schema_record(*, year: int, score: float, target: float, weight: float) -> SchemaRecord:
    return SchemaRecord(
        id="same-record",
        employee_id="CACHE-SYNTHETIC",
        employee_name="Cache test",
        team="Outbound",
        month="August",
        year=year,
        status="Meets",
        evaluation=EvaluationData(score=score, grade="C", manager_notes="keep the human note"),
        raw_data={"T.Attend%": 0.65, "source_marker": "workbook-raw"},
        kpi_values=[{
            "kpi_key": "Attendance",
            "label": "Attendance",
            "direction": "lower_better",
            "evaluation_pinned": True,
            "actual_value": 0.46,
            "target_value": target,
            "weight_applied": weight,
            "contribution": 0.32857142857142857,
            "unit": "%",
        }],
    )


def test_warmed_serialization_follows_basis_revision_and_year():
    clear_serialization_cache()
    current = _schema_record(year=2026, score=79.82, target=0.65, weight=0.6)
    _serialize_cache[f"ser:{current.id}"] = (
        {"evaluation": {"score": 1, "manager_notes": "stale"}, "raw_data": {}, "kpi_values": []},
        time.time() + 300,
    )
    try:
        first = serialize_performance_record(current)
        assert first["evaluation"]["score"] == pytest.approx(79.82)
        assert first["evaluation"]["manager_notes"] == "keep the human note"
        assert first["raw_data"]["T.Attend%"] == pytest.approx(0.65)
        assert first["raw_data"]["source_marker"] == "workbook-raw"
        assert first["kpi_values"][0]["target_value"] == pytest.approx(0.65)
        assert first["kpi_values"][0]["weight_applied"] == pytest.approx(0.6)
        assert serialize_performance_record(current) is first

        revised = current.model_copy(update={
            "evaluation": current.evaluation.model_copy(update={"score": 79.93}),
            "kpi_values": [{
                **current.kpi_values[0],
                "target_value": 0.7,
                "weight_applied": 0.5,
                "direction": "higher_better",
            }],
        })
        second = serialize_performance_record(revised)
        assert second is not first
        assert second["evaluation"]["score"] == pytest.approx(79.93)
        assert second["evaluation"]["manager_notes"] == "keep the human note"
        assert second["raw_data"]["T.Attend%"] == pytest.approx(0.65)
        assert second["kpi_values"][0]["target_value"] == pytest.approx(0.7)
        assert second["kpi_values"][0]["weight_applied"] == pytest.approx(0.5)
        assert second["kpi_values"][0]["direction"] == "higher_better"
        assert serialize_performance_record(current)["evaluation"]["score"] == pytest.approx(79.82)

        other_year = _schema_record(year=2025, score=11, target=0.65, weight=0.6)
        assert serialize_performance_record(other_year)["evaluation"]["score"] == pytest.approx(11)
        assert serialize_performance_record(other_year)["year"] == 2025
        assert serialize_performance_record(revised)["evaluation"]["score"] == pytest.approx(79.93)
        assert f"ser:{current.id}" in _serialize_cache
    finally:
        clear_serialization_cache()


def test_warmed_serialization_follows_identity_metadata_and_kpi_passthrough():
    clear_serialization_cache()
    current = _schema_record(year=2026, score=79.82, target=0.65, weight=0.6)
    try:
        first = serialize_performance_record(current)
        revisions = (
            ("employee_name", "Anonymous renamed"),
            ("employee_id", "ANONYMOUS-2"),
            ("region", "UAE"),
            ("branch_key", "dubai"),
            ("performance_level", "Corporate"),
            ("position", "Anonymous revised position"),
            ("upload_id", "anonymous-upload"),
            ("meta", {"anonymous_basis": "current"}),
        )
        for field, changed in revisions:
            revised = current.model_copy(update={field: changed})
            after = serialize_performance_record(revised)
            assert after is not first
            assert after.get(field) == changed
            assert serialization_cache_key(revised) != serialization_cache_key(current)
            assert "anonymous" not in serialization_cache_key(revised).split(":")[-1]

        noted = current.model_copy(update={
            "kpi_values": [{**current.kpi_values[0], "source_note": "current basis"}],
        })
        with_note = serialize_performance_record(noted)
        assert with_note is not first
        assert with_note["kpi_values"][0]["source_note"] == "current basis"
        assert with_note["evaluation"]["manager_notes"] == "keep the human note"
        assert with_note["raw_data"]["T.Attend%"] == pytest.approx(0.65)

        ordered = current.model_copy(update={"meta": {"b": 2, "a": 1}})
        reordered = current.model_copy(update={"meta": {"a": 1, "b": 2}})
        left = serialize_performance_record(ordered)
        assert serialize_performance_record(reordered) is left
        assert left["meta"] == {"b": 2, "a": 1}
    finally:
        clear_serialization_cache()


def _row(payload, predicate):
    return next(item for item in payload if predicate(item))


def test_legacy_and_bounded_reads_refresh_after_apply_and_rollback_without_redis(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    response_cache = {}

    def set_json(key, value, **_):
        response_cache.setdefault(key, value)
        return True

    monkeypatch.setattr(CacheService, "get_json", lambda key, **_: response_cache.get(key))
    monkeypatch.setattr(CacheService, "set_json", set_json)
    monkeypatch.setattr("services.cache_invalidation_service.redis_client", None, raising=False)
    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda *_args, **_kwargs: None)
    clear_serialization_cache()
    try:
        admin = User(id=uuid.uuid4(), username="cache-ser-admin", email="cache-ser@example.invalid", role="Admin", password_hash="synthetic")
        team = Team(id=uuid.uuid4(), name="Coding", db_name="Coding", display_name="Coding", region="UAE", team_level="employee")
        august_employee = Employee(id=uuid.uuid4(), employee_id="CACHE-SYNTHETIC", name="Cache test", team=team, region="UAE", performance_level="Employee")
        july_employee = Employee(id=uuid.uuid4(), employee_id="CACHE-JULY", name="July untouched", team=team, region="UAE", performance_level="Employee")
        august = PerformanceRecord(
            id=uuid.uuid4(), year=2026, employee=august_employee, team=team, month="August",
            performance_level="Employee", score=70, grade="D", status="Below",
            record_payload={
                "id": "placeholder",
                "employee_id": "CACHE-SYNTHETIC",
                "employee_name": "Cache test",
                "team": "Coding",
                "month": "August",
                "year": 2026,
                "evaluation": {"score": 70, "grade": "D", "manager_notes": "keep the human note"},
                "raw_data": {"T.Attend%": 0.65, "source_marker": "workbook-raw"},
            },
        )
        july = PerformanceRecord(
            id=uuid.uuid4(), year=2026, employee=july_employee, team=team, month="July",
            performance_level="Employee", score=82.85, grade="C", status="Meets",
        )
        db.add_all([admin, team, august_employee, july_employee, august, july])
        db.commit()
        # Injected fixture identity so the isolated client can call the read
        # routes. This is not a real JWT session and does not change product auth.
        actor = {"user_id": str(admin.id), "role": "Admin", "has_unrestricted_team_access": True, "legacy_unscoped": False}
        workflow = EvaluationWorkflow(db)
        scope = next(
            row for row in workflow.sync_catalog(actor)["scopes"]
            if row["display_name"] == "Coding" and row["performance_level"] == "Employee" and row["position_name"] == ""
        )
        draft = workflow.open_draft(actor, scope["id"], 2026, 8)
        lines = [{**line, "weight": 1 if index == 0 else 0, "direction": "higher_better", "target_mode": "fixed", "target": 10} for index, line in enumerate(draft["lines"])]
        workflow.edit_draft(actor, draft["id"], lines)
        db.add(KPIValue(
            record_id=august.id, record_year=2026, kpi_key=lines[0]["kpi_key"],
            actual_value=8, target_value=10, achievement_ratio=0.7, weight_applied=1, contribution=0.7,
        ))
        db.commit()
        workflow.impact_preview(actor, draft["id"])
        workflow.approve(actor, draft["id"])

        app = FastAPI()
        app.include_router(performance_router, prefix="/api")

        @app.middleware("http")
        async def attach_user(request, call_next):
            request.state.user = actor
            return await call_next(request)

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db
        client = TestClient(app)
        _serialize_cache[f"ser:{august.id}"] = (
            {"id": str(august.id), "evaluation": {"score": 1, "manager_notes": "stale"}, "raw_data": {}, "kpi_values": []},
            time.time() + 300,
        )

        def legacy():
            response = client.get("/api/performance")
            assert response.status_code == 200
            body = response.json()
            assert body["success"] is True
            return body["data"]

        def bounded():
            response = client.get("/api/performance/records", params={"period": "2026-08", "detail": "full", "page_size": 50})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["success"] is True
            return body["data"]["items"]

        before = legacy()
        august_before = _row(before, lambda item: item["employee_id"] == "CACHE-SYNTHETIC")
        july_before = _row(before, lambda item: item["employee_id"] == "CACHE-JULY")
        assert august_before["evaluation"]["score"] != 1
        assert august_before["evaluation"]["manager_notes"] == "keep the human note"
        assert august_before["raw_data"]["T.Attend%"] == pytest.approx(0.65)
        assert august_before["raw_data"]["source_marker"] == "workbook-raw"
        assert july_before["evaluation"]["score"] == pytest.approx(82.85)
        warmed_bounded = bounded()
        assert _row(warmed_bounded, lambda item: item["employee_id"] == "CACHE-SYNTHETIC")["evaluation"]["score"] == pytest.approx(august_before["evaluation"]["score"])
        cache_size = len(response_cache)
        assert bounded()[0]["evaluation"]["score"] == pytest.approx(august_before["evaluation"]["score"])
        assert len(response_cache) == cache_size

        applied = workflow.apply(actor, scope["id"], 2026, 8)
        after = legacy()
        august_after = _row(after, lambda item: item["employee_id"] == "CACHE-SYNTHETIC")
        july_after = _row(after, lambda item: item["employee_id"] == "CACHE-JULY")
        assert august_after["evaluation"]["score"] != pytest.approx(august_before["evaluation"]["score"])
        assert august_after["evaluation"]["manager_notes"] == "keep the human note"
        assert august_after["raw_data"]["T.Attend%"] == pytest.approx(0.65)
        assert august_after["raw_data"]["source_marker"] == "workbook-raw"
        assert july_after["evaluation"]["score"] == pytest.approx(82.85)
        bounded_after = _row(bounded(), lambda item: item["employee_id"] == "CACHE-SYNTHETIC")
        assert bounded_after["evaluation"]["score"] == pytest.approx(august_after["evaluation"]["score"])
        assert bounded_after["evaluation"]["manager_notes"] == "keep the human note"
        assert bounded_after["raw_data"]["T.Attend%"] == pytest.approx(0.65)

        workflow.rollback(actor, applied["revision_id"])
        restored = _row(legacy(), lambda item: item["employee_id"] == "CACHE-SYNTHETIC")
        assert restored["evaluation"]["score"] == pytest.approx(august_before["evaluation"]["score"])
        assert restored["evaluation"]["manager_notes"] == "keep the human note"
        assert restored["raw_data"]["T.Attend%"] == pytest.approx(0.65)
        restored_bounded = _row(bounded(), lambda item: item["employee_id"] == "CACHE-SYNTHETIC")
        assert restored_bounded["evaluation"]["score"] == pytest.approx(august_before["evaluation"]["score"])
        assert restored_bounded["raw_data"]["source_marker"] == "workbook-raw"
    finally:
        clear_serialization_cache()
        db.close()
        engine.dispose()
