"""Legacy GET /api/performance caches the finished body: same bytes, safe invalidation."""
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
from services.cache_invalidation_service import CacheInvalidationService
from services.cache_service import in_memory_cache


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
    monkeypatch.setattr(performance, "get_current_user_scope", lambda *_a, **_k: scope)
    monkeypatch.setattr(performance, "enforce_user_route_limit", lambda *a, **k: None)
    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.include_router(performance.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    client.db = db
    return client


def test_miss_and_hit_are_identical_and_keep_legacy_headers(client):
    miss = client.get("/api/performance", headers={"Accept-Encoding": "identity"})
    hit = client.get("/api/performance", headers={"Accept-Encoding": "identity"})
    gz_hit = client.get("/api/performance", headers={"Accept-Encoding": "gzip"})
    assert (miss.status_code, hit.status_code, gz_hit.status_code) == (200, 200, 200)
    assert miss.headers["x-cache"] == "MISS" and hit.headers["x-cache"] == "HIT"
    assert miss.content == hit.content == gz_hit.content
    for r in (miss, hit, gz_hit):
        assert r.headers["deprecation"] == "true"
        assert r.headers["x-pms-performance-route"] == "legacy"
        assert "cache-control" not in r.headers
    assert len(miss.json()["data"]) == 3


def test_filters_get_their_own_entries(client):
    all_rows = client.get("/api/performance").json()["data"]
    other = client.get("/api/performance?month=March").json()["data"]
    assert len(all_rows) == 3 and other == []


def test_data_version_bump_invalidates(client):
    first = client.get("/api/performance").json()["data"]
    assert len(first) == 3
    team = client.db.query(Team).first()
    emp = Employee(id=uuid.uuid4(), employee_id="E9", name="New", team_id=team.id, region="EGY")
    client.db.add(emp)
    client.db.flush()
    client.db.add(PerformanceRecord(
        id=uuid.uuid4(), year=2026, employee_id=emp.id, team_id=team.id, month="June",
        performance_level="Employee", region="EGY", score=70, grade="C", status="Meets",
        record_payload={"raw_data": {"x": 1}},
    ))
    client.db.commit()
    CacheInvalidationService.bump_data_version()
    assert len(client.get("/api/performance").json()["data"]) == 4
