"""Identical concurrent cold /records requests compute (and store) once."""
import threading
import time
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.gzip import GZipMiddleware

from api.routers import performance
from config.database import Base, get_db
from models.models import Employee, PerformanceRecord, Team
from services import performance_dashboard_read_service as svc
from services.cache_invalidation_service import CacheInvalidationService
from services.cache_service import CacheService, in_memory_cache


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    team = Team(id=uuid.uuid4(), name="Inbound", db_name="inbound", display_name="Inbound", region="EGY", team_level="employee", is_active=True)
    db.add(team)
    db.flush()
    for i in range(3):
        emp = Employee(id=uuid.uuid4(), employee_id=f"E{i}", name=f"Emp {i}", team_id=team.id, region="EGY")
        db.add(emp)
        db.flush()
        db.add(PerformanceRecord(
            id=uuid.uuid4(), year=2026, employee_id=emp.id, team_id=team.id, month="June",
            performance_level="Employee", region="EGY", score=80 + i, grade="B", status="Meets",
            record_payload={"raw_data": {"x": 0.00009 * (i + 1)}},
        ))
    db.commit()
    CacheInvalidationService.bump_data_version()
    in_memory_cache.cache.clear()  # no entry from another test can match this key
    in_memory_cache.current_bytes = 0
    scope = {"role": "Admin", "user_id": "u1", "has_unrestricted_team_access": True, "is_self_only": False,
             "accessible_teams": [], "accessible_team_levels": []}
    monkeypatch.setattr(performance, "require_authenticated_scope", lambda *_a, **_k: scope)
    monkeypatch.setattr(performance, "enforce_user_route_limit", lambda *a, **k: None)
    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.include_router(performance.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_concurrent_identical_cold_requests_compute_once(client, monkeypatch):
    writes = []
    real_set = CacheService.set_json
    real_uncached = svc.PerformanceDashboardReadService._records_page_uncached

    def slow_uncached(self, **kw):
        time.sleep(0.05)
        return real_uncached(self, **kw)

    def counting_set(key, value, *a, **k):
        if k.get("cache_type") == "performance_records":
            writes.append(key)
        return real_set(key, value, *a, **k)

    monkeypatch.setattr(svc.PerformanceDashboardReadService, "_records_page_uncached", slow_uncached)
    monkeypatch.setattr(CacheService, "set_json", staticmethod(counting_set))
    bodies = []

    def call():
        r = client.get("/api/performance/records?period=2026-06&detail=full&page_size=100")
        bodies.append((r.status_code, r.json()["data"]["items"]))

    threads = [threading.Thread(target=call) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(bodies) == 6 and all(b[0] == 200 and len(b[1]) == 3 for b in bodies)
    assert len(writes) == 1
