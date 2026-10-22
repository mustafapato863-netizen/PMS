"""Dashboard fan-out on a tiny pool: no timeout, and the pool is idle afterwards.

Production hung when ~10 parallel ``GET /api/insights/workspace`` calls (one per
team) plus summary-records, follow-up and owners hit a 5-connection pool with
no overflow. This drives the same burst concurrently through the real auth and
error-handling middleware against a file SQLite database with a QueuePool of
3 connections and no overflow, including error paths that go through
ErrorTracker, then asserts every connection was returned and none is left in a
transaction.
"""
from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from config.database import Base, get_db
from models.models import ErrorLog
from tests.test_summary_parity_capture import _seed, _seed_actions

POOL_SIZE = 3
SECTIONS = "kpi_diagnosis,team_summaries"


@pytest.fixture
def fanout(tmp_path, monkeypatch):
    from api.middleware import error_handling_middleware
    from api.middleware.auth_middleware import AuthMiddleware
    from api.middleware.error_handling_middleware import ErrorHandlingMiddleware
    from api.routers.auth import router as auth_router
    from api.routers.insights import router as insights_router
    from api.routers.performance import router as performance_router
    from api.routers.users_and_actions import actions_router
    from config import settings
    from services.auth_service import AuthenticationService
    from services.cache_service import CacheService
    from services.user_presence_service import UserPresenceService

    engine = create_engine(
        f"sqlite:///{tmp_path / 'fanout.db'}",
        poolclass=QueuePool, pool_size=POOL_SIZE, max_overflow=0, pool_timeout=5,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as db:
        teams, employees = _seed(db)
        _seed_actions(db, teams, employees)
        admin = AuthenticationService.create_user(db, "fanout_admin", "fanout@example.test", "SecurePassword123!", "Admin")
        db.commit()
        token = AuthenticationService.authenticate_user(db, admin.username, "SecurePassword123!")
        db.commit()
        team_names = sorted(team.name for team in teams.values())

    monkeypatch.setattr(settings, "PMS_SCOPED_PERFORMANCE_API_ENABLED", True)
    monkeypatch.setattr(settings, "PMS_SCOPED_PERFORMANCE_ALLOWED_ROLES", ("Admin",))
    monkeypatch.setattr("api.middleware.auth_middleware._legacy_access_allowed", lambda: False)
    monkeypatch.setattr(CacheService, "get_json", lambda *_, **__: None)
    monkeypatch.setattr(CacheService, "set_json", lambda *_, **__: None)
    # ErrorTracker writes through its own short session; point it at this pool.
    monkeypatch.setattr(error_handling_middleware, "SessionLocal", factory)
    UserPresenceService.forget()

    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.add_middleware(ErrorHandlingMiddleware)

    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    for router in (auth_router, insights_router, performance_router):
        app.include_router(router, prefix="/api")
    app.include_router(actions_router, prefix="/api/corrective-actions")
    yield app, engine, factory, {"Authorization": f"Bearer {token}"}, team_names
    UserPresenceService.forget()
    engine.dispose()


def _burst(team_names: list[str]) -> list[str]:
    teams = (team_names * 10)[:10]  # ~10 parallel workspace calls, one per team
    urls = [f"/api/insights/workspace?sections={SECTIONS}&team={team}" for team in teams]
    urls += [
        "/api/performance/summary-records",
        "/api/corrective-actions/follow-up",
        "/api/corrective-actions/owners",
    ]
    return urls


async def _fire(app, headers, urls, heartbeats: int = 5):
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as client:
        calls = [client.get(url, headers=headers) for url in urls]
        calls += [client.post("/api/auth/presence/heartbeat", headers=headers) for _ in range(heartbeats)]
        started = time.perf_counter()
        responses = await asyncio.gather(*calls)
        return responses, time.perf_counter() - started


def _assert_pool_idle(engine):
    assert engine.pool.checkedout() == 0
    raw = [engine.raw_connection() for _ in range(POOL_SIZE)]
    try:
        assert not any(conn.driver_connection.in_transaction for conn in raw)
    finally:
        for conn in raw:
            conn.close()
    assert engine.pool.checkedout() == 0


def test_dashboard_fanout_finishes_and_leaves_the_pool_idle(fanout):
    app, engine, _factory, headers, team_names = fanout
    for _round in range(3):
        responses, elapsed = asyncio.run(_fire(app, headers, _burst(team_names)))
        assert [r.status_code for r in responses] == [200] * len(responses), [r.text[:200] for r in responses if r.status_code != 200]
        assert elapsed < 5  # well under pool_timeout: nobody waited for a connection that never came back
        _assert_pool_idle(engine)


def test_fanout_with_errors_through_error_tracker_leaves_the_pool_idle(fanout, monkeypatch):
    from services.error_tracker import ErrorTracker
    from services.insights_service import InsightsService

    app, engine, factory, headers, team_names = fanout
    original = InsightsService.generate_workspace

    def flaky(self, scope, **kwargs):
        if (kwargs.get("team") or "") == team_names[0]:
            raise RuntimeError("synthetic workspace failure")
        return original(self, scope, **kwargs)

    monkeypatch.setattr(InsightsService, "generate_workspace", flaky)
    responses, _ = asyncio.run(_fire(app, headers, _burst(team_names)))
    codes = [r.status_code for r in responses]
    assert 500 in codes and 200 in codes
    _assert_pool_idle(engine)
    with factory() as db:
        assert db.query(ErrorLog).count() == codes.count(500)

    # Error tracker's own failure paths: alert evaluation raising, and the write failing.
    monkeypatch.setattr(ErrorTracker, "evaluate_error_rate", staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("alert down"))))
    responses, _ = asyncio.run(_fire(app, headers, _burst(team_names)))
    assert 500 in [r.status_code for r in responses]
    _assert_pool_idle(engine)

    monkeypatch.setattr(ErrorTracker, "register_error", staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("metrics down"))))
    responses, _ = asyncio.run(_fire(app, headers, _burst(team_names)))
    assert 500 in [r.status_code for r in responses]
    _assert_pool_idle(engine)


def test_error_log_write_ends_its_transaction_before_alerting(fanout, monkeypatch):
    """The Slack alert used to run after refresh() had re-opened a transaction."""
    from starlette.requests import Request

    from services.error_tracker import ErrorTracker

    _app, engine, factory, _headers, _teams = fanout
    seen = []

    def check_alert():
        seen.append(engine.pool.checkedout())

    monkeypatch.setattr(ErrorTracker, "evaluate_error_rate", staticmethod(check_alert))
    request = Request({"type": "http", "method": "GET", "path": "/x", "headers": [], "state": {}})
    with factory() as db:
        logged = ErrorTracker.log_error(db, request, RuntimeError("boom"), "req-1")
        assert logged is not None and logged.id is not None
        assert not db.in_transaction()
    assert seen == [0]
    _assert_pool_idle(engine)
