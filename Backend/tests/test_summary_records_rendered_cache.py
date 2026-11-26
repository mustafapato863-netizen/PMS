"""summary-records caches the finished gzip body: same bytes, same headers, one computation per key."""
import gzip
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
from services import response_cache
from services.cache_invalidation_service import CacheInvalidationService
from services.response_cache import (
    encoded_body_response,
    pack_gzip_body,
    single_flight,
    unpack_gzip_body,
)


def test_single_flight_runs_the_work_once_for_concurrent_callers():
    calls = []
    results = []
    cache = {}

    def worker():
        with single_flight("k"):
            if "v" not in cache:
                calls.append(1)
                time.sleep(0.05)
                cache["v"] = 42
            results.append(cache["v"])

    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(calls) == 1
    assert results == [42] * 8
    assert response_cache._flights == {}


def test_single_flight_waiter_does_not_wait_forever():
    release = threading.Event()
    holder_in = threading.Event()

    def holder():
        with single_flight("slow"):
            holder_in.set()
            release.wait(2)

    t = threading.Thread(target=holder)
    t.start()
    holder_in.wait(1)
    with single_flight("slow", wait_seconds=0.05) as held:
        assert held is False
    release.set()
    t.join()
    assert response_cache._flights == {}


def test_packed_body_round_trips_and_serves_both_client_kinds():
    body = b'{"success":true,"data":[1,2,3]}' * 100
    packed = pack_gzip_body(body)
    assert gzip.decompress(unpack_gzip_body(packed)) == body
    gz = encoded_body_response(packed, accept_encoding="gzip, deflate", headers={"X-Total-Count": "3"})
    assert gz.headers["content-encoding"] == "gzip" and gz.headers["x-total-count"] == "3"
    assert gzip.decompress(gz.body) == body
    plain = encoded_body_response(packed, accept_encoding=None)
    assert "content-encoding" not in plain.headers and plain.body == body


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
    CacheInvalidationService.bump_data_version()  # no entry from another test can match this key
    scope = {"role": "Admin", "user_id": "u1", "has_unrestricted_team_access": True, "is_self_only": False,
             "accessible_teams": [], "accessible_team_levels": []}
    monkeypatch.setattr(performance, "require_authenticated_scope", lambda *_a, **_k: scope)
    monkeypatch.setattr(performance, "enforce_user_route_limit", lambda *a, **k: None)
    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.include_router(performance.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_miss_and_hit_return_identical_bodies_and_headers(client):
    url = "/api/performance/summary-records?limit=2"
    miss = client.get(url, headers={"Accept-Encoding": "identity"})
    hit = client.get(url, headers={"Accept-Encoding": "identity"})
    gz_hit = client.get(url, headers={"Accept-Encoding": "gzip"})
    assert (miss.status_code, hit.status_code, gz_hit.status_code) == (200, 200, 200)
    assert miss.headers["x-cache"] == "MISS" and hit.headers["x-cache"] == "HIT"
    assert miss.content == hit.content == gz_hit.content
    for response in (miss, hit, gz_hit):
        assert response.headers["x-total-count"] == "3"
        assert response.headers["x-result-truncated"] == "true"
        assert response.headers["cache-control"] == "private, max-age=60"
    body = miss.json()
    assert body["success"] is True and len(body["data"]) == 2
    assert b"e-0" not in miss.content  # small numbers print as the pydantic writer always did (0.0001, not 1e-04)
