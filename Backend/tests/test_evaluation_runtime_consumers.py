"""Real JWT/worker propagation using the admitted Outbound source goldens.

Anonymous SQLite only. This is not a new calculation-family admission or a
production performance gate. Live previews are regenerated; saved human
plans and report definitions are deliberately not rewritten by apply.
"""
from __future__ import annotations

from sqlalchemy.orm import sessionmaker
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.middleware.auth_middleware import AuthMiddleware
from api.routers.auth import router as auth_router
from api.routers.employee import router as employee_router
from api.routers.evaluation_settings import router as evaluation_router
from api.routers.insights import router as insights_router
from api.routers.performance import router as performance_router
from api.routers.planning import router as planning_router
from api.routers.reports import router as reports_router
from config import settings
from config.database import get_db
from services.password_service import hash_password
from services.permission_seed import seed_role_permissions
from tests.test_evaluation_bounded_apply import _engine, _live
from tests.test_evaluation_workflow_consumer import (
    AUGUST, JULY, AUGUST_GOLDEN, JULY_GOLDEN, _World, _raw,
)
import worker


def _app(db):
    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    for router in (auth_router, performance_router,
                   insights_router, planning_router, reports_router):
        app.include_router(router, prefix="/api")
    app.include_router(employee_router, prefix="/api/employee")
    app.include_router(evaluation_router, prefix="/api/settings/evaluation")

    def dependency():
        yield db

    app.dependency_overrides[get_db] = dependency
    return app


def _call(client, method, path, body=None):
    response = client.request(method, "/api" + path, json=body)
    assert response.status_code in (200, 201), (path, response.status_code, response.text)
    document = response.json()
    assert document["success"], document
    return document["data"]


def _records(client, month):
    return _call(client, "GET", f"/performance/records?period=2026-{month:02}&detail=full&include_total=true")["items"]


def _consumers(client, employee_id, golden):
    near = lambda value, expected: value == pytest.approx(expected, abs=.005)
    rows = _records(client, 8)
    assert len(rows) == 2
    assert all(near(row["score"], golden) for row in rows)
    summary = _call(client, "GET", "/performance/summary?period=2026-08&team=Outbound&performance_level=Employee")
    assert near(summary["current"]["average_score"], golden)
    assert near(summary["previous"]["average_score"], 82.85)
    for point in summary["trend"]:
        if point["month"] == "August":
            assert near(point["average_score"], golden)
        if point["month"] == "July":
            assert near(point["average_score"], 82.85)
    legacy = _call(client, "GET", "/performance")
    august = [row for row in legacy if row["month"] == "August"]
    assert len(august) == 2
    assert all(near(row["evaluation"]["score"], golden) for row in august)
    employee = _call(client, "GET", "/employee/" + employee_id)
    history = {row["month"]: row for row in employee["performance_history"]}
    assert near(history["August"]["evaluation"]["score"], golden)
    assert near(history["July"]["evaluation"]["score"], 82.85)
    insights = _call(client, "GET", "/insights/workspace?month=August&year=2026&team=Outbound&performance_level=Employee")
    team = next(row for row in insights["team_summaries"] if row["team"] == "Outbound")
    assert team["current_score"] == round(golden, 1)
    assert team["previous_score"] == 82.8
    center = _call(client, "GET", "/reports/center?period=2026-08&comparison_period=2026-07&team=Outbound&performance_level=Employee")
    assert near(center["summary"]["current_score"], golden)
    assert near(center["summary"]["previous_score"], 82.85)
    preview = _call(client, "POST", "/reports/preview", {
        "report_type": "team", "report_name": "Anonymous async consumer QA",
        "start_month": "August", "start_year": 2026,
        "comparison_month": "July", "comparison_year": 2026,
        "team": "Outbound", "performance_level": "Employee", "output_format": "excel",
    })
    assert near(preview["summary"]["average_score"], golden)
    pin = next(k for k in rows[0]["kpi_values"] if k["kpi_key"] == "Attendance")
    for row in preview["table_preview"]:
        assert near(row["Attendance Rate Target"], pin["target_value"])
        assert near(row["Attendance Rate Contribution (%)"], round(pin["contribution"] * 100, 2))
        assert "Productivity Actual" in row
    detail = next(row["detail"] for row in insights["team_analyses"] if row["kpi_key"] == "Attendance")
    health = next(row for row in center["kpi_health"] if row["kpi"] == "Attendance")
    assert detail["target_value"] == health["target"] == pin["target_value"]
    for document in (summary, insights["executive_story"]):
        assert document["basis_context"]["state"] == "changed"
        assert document["basis_context"]["like_for_like"] is False
    july = _call(client, "GET", "/insights/workspace?month=July&year=2026&team=Outbound&performance_level=Employee")
    assert not any(row["kpi_key"] == "Productivity" for row in july["team_analyses"])
    return insights


def test_async_worker_updates_warm_consumers_and_rollback_preserves_human_artifacts(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ALLOW_LEGACY_API_ACCESS", "false")
    for module in ("services.redis_provider", "services.cache_service", "services.cache_invalidation_service"):
        # A direct local pytest invocation must not publish to the user's Redis.
        monkeypatch.setattr(module + ".redis_client", None)
    monkeypatch.setattr(settings, "PMS_EVALUATION_APPLY_JOBS_ENABLED", True)
    monkeypatch.setattr(settings, "PMS_SCOPED_PERFORMANCE_API_ENABLED", True)
    monkeypatch.setattr(settings, "PMS_SCOPED_PERFORMANCE_ALLOWED_ROLES", "")
    engine = _engine()
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = sessions()
    try:
        world = _World(db)
        world.admin.password_hash = hash_password("AnonymousQA!123456")
        world.admin.must_change_password = False
        seed_role_permissions(db)
        db.commit()
        for employee in (world.employee, world.colleague):
            for month, actuals, productivity, score in (
                ("July", JULY, None, JULY_GOLDEN),
                ("August", AUGUST, AUGUST["Productivity"], AUGUST_GOLDEN),
            ):
                record = world.record(employee, month, _raw(actuals, productivity=productivity), score=str(round(score, 2)))
                world.stored_kpis(record, actuals, productivity=productivity)
        monkeypatch.setattr(worker, "SessionLocal", sessions)
        with TestClient(_app(db)) as client:
            assert client.get("/api/performance/catalog").status_code == 401
            login = _call(client, "POST", "/auth/login", {"username": world.admin.username, "password": "AnonymousQA!123456"})
            client.headers["Authorization"] = "Bearer " + login["access_token"]
            versions = {}
            for month in (7, 8):
                payload = {"scope_id": world.scope["id"], "year": 2026, "month": month}
                draft = _call(client, "POST", "/settings/evaluation/drafts", payload)
                _call(client, "POST", f"/settings/evaluation/drafts/{draft['id']}/impact-preview")
                _call(client, "POST", f"/settings/evaluation/drafts/{draft['id']}/approve")
                _call(client, "POST", "/settings/evaluation/apply", payload)
                versions[month] = draft["id"]
            baseline = _live(db)
            july = _records(client, 7)
            august = _records(client, 8)
            insights = _consumers(client, world.employee.employee_id, 79.82)
            linked = next(item for item in insights["priority_insights"] if item["detail"].get("basis_note"))
            plan = _call(client, "POST", "/planning", {
                "name": "Anonymous async QA plan", "scope_type": "Team", "team": "Outbound",
                "performance_level": "Employee", "region": "EGY", "period_start": "2026-08-01",
                "period_end": "2026-12-31", "due_date": "2026-12-31", "owner_user_id": str(world.admin.id),
                "baseline_value": 60, "target_value": 80, "current_value": 70,
                "insight_ids": [linked["id"]], "evidence_month": "August", "evidence_year": 2026, "activate": False,
                "objectives": [{"name": "Anonymous objective", "measurement_type": "KPI",
                    "baseline_value": 60, "target_value": 80, "current_value": 70, "unit": "%",
                    "direction": "higher_better", "due_date": "2026-12-31", "owner_user_id": str(world.admin.id)}],
            })
            template = _call(client, "POST", "/reports/story/templates", {
                "name": "Anonymous async QA template", "template_key": "anonymous_async_qa",
                "report_type": "executive", "visibility": "private", "definition": {"slides": [{
                    "id": "qa-page", "title": "Evaluation comparison", "layout": "full_width", "order": 0,
                    "blocks": [{"id": "qa-block", "type": "overall_score_movement_bridge", "slot": "full"}],
                }]},
            })
            story = _call(client, "POST", "/reports/story/drafts", {
                "name": "Anonymous async QA report", "report_type": "executive", "template_id": template["id"],
                "scope": {"team": "Outbound", "performance_level": "Employee"},
                "primary_period": {"month": "August", "year": 2026}, "comparison_period": {"month": "July", "year": 2026},
            })
            original_plan = _call(client, "GET", f"/planning/{plan['id']}")
            original_definition = _call(client, "GET", f"/reports/story/drafts/{story['id']}")["definition"]
            revised = _call(client, "POST", f"/settings/evaluation/versions/{versions[8]}/revise")
            lines = revised["lines"]
            for line in lines:
                if line["kpi_key"] == "Attendance":
                    line.update(target_mode="fixed", target=.7, weight=.5)
                elif line["kpi_key"] == "Productivity":
                    line["weight"] = .2
            edited = _call(client, "PATCH", f"/settings/evaluation/drafts/{revised['id']}", {"lines": lines, "expected_checksum": revised["checksum"]})
            _call(client, "POST", f"/settings/evaluation/drafts/{edited['id']}/impact-preview")
            _call(client, "POST", f"/settings/evaluation/drafts/{edited['id']}/approve")
            assert _live(db) == baseline, "Approval must not rescore"
            payload = {"scope_id": world.scope["id"], "year": 2026, "month": 8}
            queued = _call(client, "POST", "/settings/evaluation/apply-jobs", payload)
            assert _live(db) == baseline, "Queue acceptance must not rescore"
            _consumers(client, world.employee.employee_id, 79.82)
            db.rollback()
            worker.run_worker(once=True)
            db.expire_all()
            result = _call(client, "GET", f"/settings/evaluation/apply-jobs/{queued['job_id']}")
            assert result["job_status"] == "succeeded" and result["progress"] == 100
            assert result["promoted_count"] == 2
            _consumers(client, world.employee.employee_id, 79.93)
            assert _records(client, 7) == july
            changed = _records(client, 8)
            for row in changed:
                prior = next(item for item in august if item["employee_id"] == row["employee_id"])
                assert row["raw_data"] == prior["raw_data"]
                attendance = next(k for k in row["kpi_values"] if k["kpi_key"] == "Attendance")
                assert attendance["target_value"] == .7 and attendance["weight_applied"] == .5
            page = _call(client, "GET", f"/reports/story/drafts/{story['id']}/pages/qa-page")
            movement = page["blocks"]["qa-block"]["data"]
            assert movement["current_overall_score"] == pytest.approx(79.93, abs=.005)
            assert movement["previous_overall_score"] == pytest.approx(82.85, abs=.005)
            assert movement["basis_context"]["state"] == "changed"
            assert _call(client, "GET", f"/planning/{plan['id']}")["summary"] == original_plan["summary"]
            assert _call(client, "GET", f"/reports/story/drafts/{story['id']}")["definition"] == original_definition
            _call(client, "POST", f"/settings/evaluation/revisions/{result['revision_id']}/rollback")
            assert _live(db) == baseline
            assert _records(client, 7) == july and _records(client, 8) == august
            _consumers(client, world.employee.employee_id, 79.82)
            restored_page = _call(client, "GET", f"/reports/story/drafts/{story['id']}/pages/qa-page")
            restored_movement = restored_page["blocks"]["qa-block"]["data"]
            assert restored_movement["current_overall_score"] == pytest.approx(79.82, abs=.005)
            assert restored_movement["previous_overall_score"] == pytest.approx(82.85, abs=.005)
            assert _call(client, "GET", f"/planning/{plan['id']}")["summary"] == original_plan["summary"]
            assert _call(client, "GET", f"/reports/story/drafts/{story['id']}")["definition"] == original_definition
    finally:
        db.close()
        engine.dispose()
