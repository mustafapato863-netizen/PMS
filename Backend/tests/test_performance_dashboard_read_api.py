import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import Employee, PerformanceRecord, Team
from services.performance_dashboard_read_service import PerformanceDashboardReadService


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db):
    inbound = Team(
        id=uuid.uuid4(),
        name="Inbound",
        db_name="inbound",
        display_name="Inbound",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    outbound = Team(
        id=uuid.uuid4(),
        name="Outbound",
        db_name="outbound",
        display_name="Outbound",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    employees = [
        Employee(id=uuid.uuid4(), employee_id="EMP-A", name="Alice", team_id=inbound.id, region="EGY"),
        Employee(id=uuid.uuid4(), employee_id="EMP-B", name="Bob", team_id=inbound.id, region="EGY"),
        Employee(id=uuid.uuid4(), employee_id="EMP-C", name="Carol", team_id=outbound.id, region="EGY"),
    ]
    db.add_all([inbound, outbound, *employees])
    db.flush()
    rows = [
        PerformanceRecord(
            id=uuid.uuid4(), year=2026, employee_id=employees[0].id, team_id=inbound.id,
            month="June", performance_level="Employee", region="EGY", branch_key="dubai", score=90, grade="A", status="Exceeds",
        ),
        PerformanceRecord(
            id=uuid.uuid4(), year=2026, employee_id=employees[1].id, team_id=inbound.id,
            month="June", performance_level="Employee", region="EGY", branch_key="dubai", score=80, grade="B", status="Meets",
        ),
        PerformanceRecord(
            id=uuid.uuid4(), year=2026, employee_id=employees[0].id, team_id=inbound.id,
            month="May", performance_level="Employee", region="EGY", score=70, grade="C", status="Below",
        ),
        PerformanceRecord(
            id=uuid.uuid4(), year=2026, employee_id=employees[2].id, team_id=outbound.id,
            month="June", performance_level="Employee", region="EGY", score=95, grade="A", status="Exceeds",
        ),
    ]
    db.add_all(rows)
    db.commit()


def _scope():
    return {
        "user_id": str(uuid.uuid4()),
        "role": "Manager",
        "employee_id": None,
        "accessible_teams": ["Inbound"],
        "accessible_team_levels": [("Inbound", "Employee")],
        "has_unrestricted_team_access": False,
        "is_self_only": False,
        "legacy_unscoped": False,
    }


def test_summary_is_period_bounded_and_sql_scoped():
    db = _session()
    try:
        _seed(db)
        data = PerformanceDashboardReadService(db, _scope()).summary(
            period="2026-06",
            trend_months=2,
        )

        assert data["current"]["total_agents"] == 2
        assert data["current"]["average_score"] == 85.0
        assert data["previous"]["total_agents"] == 1
        assert data["team_breakdown"][0]["teamName"] == "Inbound"
        assert all(item["teamName"] != "Outbound" for item in data["team_breakdown"])
    finally:
        db.close()


def test_function_viewer_http_scope_tampering_and_revocation(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.middleware.auth_middleware import AuthMiddleware
    from api.routers.performance import router
    from api.routers.users_and_actions import users_router
    from config import settings
    from config.database import get_db
    from models.models import UserFunctionAssignment
    from services.auth_service import AuthenticationService
    from services.cache_service import CacheService

    db = _session()
    try:
        _seed(db)
        marketing = Team(id=uuid.uuid4(), name="Marketing", db_name="marketing", region="EGY", is_active=True)
        employee = Employee(id=uuid.uuid4(), employee_id="EMP-M", name="Hidden", team_id=marketing.id, region="EGY")
        db.add_all([marketing, employee])
        db.flush()
        db.add(PerformanceRecord(
            id=uuid.uuid4(), year=2026, month="June", employee_id=employee.id, team_id=marketing.id,
            performance_level="Employee", region="EGY", score=99, grade="A", status="Exceeds",
        ))
        admin = AuthenticationService.create_user(db, "scope_admin", "scope-admin@test.com", "SecurePassword123!", "Admin")
        viewer = AuthenticationService.create_user(db, "scope_viewer", "scope-viewer@test.com", "SecurePassword123!", "Function Viewer")
        db.add(UserFunctionAssignment(user_id=viewer.id, function_name="Call Center", assigned_by=admin.username))
        db.commit()
        viewer_headers = {"Authorization": f"Bearer {AuthenticationService.authenticate_user(db, viewer.username, 'SecurePassword123!')}", "X-User-Role": "Admin"}
        admin_headers = {"Authorization": f"Bearer {AuthenticationService.authenticate_user(db, admin.username, 'SecurePassword123!')}"}
        monkeypatch.setattr(settings, "PMS_SCOPED_PERFORMANCE_API_ENABLED", True)
        monkeypatch.setattr(settings, "PMS_SCOPED_PERFORMANCE_ALLOWED_ROLES", ("Admin",))
        monkeypatch.setattr("api.middleware.auth_middleware._legacy_access_allowed", lambda: False)
        cache = {}
        monkeypatch.setattr(CacheService, "get_json", lambda key, **kwargs: cache.get(key))
        monkeypatch.setattr(CacheService, "set_json", lambda key, value, **kwargs: cache.setdefault(key, value))
        app = FastAPI()
        app.add_middleware(AuthMiddleware)

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db
        app.include_router(router, prefix="/api")
        app.include_router(users_router, prefix="/api/users")
        with TestClient(app) as client:
            assert client.get("/api/performance/records?period=2026-06", headers={"X-User-Role": "Admin"}).status_code == 401
            page = client.get("/api/performance/records?period=2026-06", headers=viewer_headers)
            assert page.status_code == 200
            assert {item["team"] for item in page.json()["data"]["items"]} == {"Inbound", "Outbound"}
            assert client.get("/api/performance/records?period=2026-06&team=Marketing", headers=viewer_headers).json()["data"]["items"] == []
            assert client.get("/api/performance/employee/EMP-M?period_end=2026-06", headers=viewer_headers).json()["data"] == []
            assert client.get("/api/performance/team/Marketing", headers=viewer_headers).status_code == 403
            catalog = client.get("/api/performance/catalog", headers=viewer_headers).json()["data"]
            assert {item["team"] for item in catalog["scopes"]} == {"Inbound", "Outbound"}
            summary_url = "/api/performance/summary?period=2026-06"
            assert client.get(summary_url, headers=viewer_headers).json()["data"]["current"]["total_agents"] == 3
            assert cache
            revoked = client.put(f"/api/users/{viewer.id}", headers=admin_headers, json={
                "id": str(viewer.id), "name": "Scope Viewer", "username": viewer.username,
                "role": "Function Viewer", "accessible_functions": [],
            })
            assert revoked.status_code == 200
            assert revoked.json()["data"]["accessible_functions"] == []
            assert client.get(summary_url, headers=viewer_headers).json()["data"]["current"]["total_agents"] == 0
            assert client.get("/api/performance/records?period=2026-06", headers=viewer_headers).json()["data"]["items"] == []
            assert client.get("/api/performance/catalog", headers=viewer_headers).json()["data"]["scopes"] == []
    finally:
        db.close()


def test_records_use_stable_cursor_pages_and_keep_scope_out_of_results():
    db = _session()
    try:
        _seed(db)
        service = PerformanceDashboardReadService(db, _scope())
        first = service.records_page(period="2026-06", page_size=1)
        assert first["has_more"] is True
        assert [item["employee_name"] for item in first["items"]] == ["Alice"]

        second = service.records_page(
            period="2026-06",
            page_size=1,
            cursor=first["next_cursor"],
        )
        assert second["has_more"] is False
        assert [item["employee_name"] for item in second["items"]] == ["Bob"]
        assert all(item["employee_name"] != "Carol" for item in second["items"])

        filtered = service.records_page(
            period="2026-06",
            grade="A",
            status="Exceeds",
        )
        assert filtered["items"][0]["previous_score"] == 70
    finally:
        db.close()


def test_records_page_filters_below_score_and_branch_with_stable_filtered_total():
    db = _session()
    try:
        _seed(db)
        service = PerformanceDashboardReadService(db, _scope())

        first = service.records_page(
            period="2026-06",
            branch="Dubai",
            score_lt=100,
            sort="score_asc",
            page_size=1,
            include_total=True,
        )
        assert first["total"] == 2
        assert first["has_more"] is True
        assert [(item["employee_name"], item["score"]) for item in first["items"]] == [("Bob", 80.0)]

        second = service.records_page(
            period="2026-06",
            branch="dubai",
            score_lt=100,
            sort="score_asc",
            cursor=first["next_cursor"],
            page_size=1,
            include_total=True,
        )
        assert second["total"] == 2
        assert second["has_more"] is False
        assert [(item["employee_name"], item["score"]) for item in second["items"]] == [("Alice", 90.0)]

        below_90 = service.records_page(
            period="2026-06",
            branch="dubai",
            score_lt=90,
            include_total=True,
        )
        assert below_90["total"] == 1
        assert [(item["employee_name"], item["score"]) for item in below_90["items"]] == [("Bob", 80.0)]
    finally:
        db.close()


def test_invalid_cursor_and_unbounded_history_are_rejected():
    db = _session()
    try:
        _seed(db)
        service = PerformanceDashboardReadService(db, _scope())
        with pytest.raises(Exception, match="cursor is invalid"):
            service.records_page(period="2026-06", cursor="not-a-cursor")
        with pytest.raises(Exception, match="months must be between"):
            service.employee_history(employee_id="EMP-A", period_end="2026-06", months=25)
        with pytest.raises(Exception, match="sort must be"):
            service.records_page(period="2026-06", sort="unsupported")
        with pytest.raises(Exception, match="location must be"):
            service.records_page(period="2026-06", location="mars")
    finally:
        db.close()
