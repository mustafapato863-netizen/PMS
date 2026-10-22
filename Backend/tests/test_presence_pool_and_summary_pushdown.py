"""Connection hygiene for the presence heartbeat, and query-level summary-records.

* Heartbeats must never leave a pooled connection checked out or a transaction
  open, on the success, throttled, inactive-user and error paths.
* summary-records' query-level path must return exactly what the legacy
  "resolve everything, then filter" path returns, for every scope.
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from api.routers import performance
from config.database import Base, get_db
from models.models import User
from repositories.performance_repository import PerformanceRepository
from services.dashboard_record_service import DashboardRecordService
from services.summary_records_service import SummaryFilters, summary_records_indexed
from services.user_presence_service import UserPresenceService
from tests.test_insights_period_window import SCOPES, _synthetic_engine

# --------------------------------------------------------------------------- presence

@pytest.fixture
def pooled(tmp_path):
    # A real QueuePool (file SQLite) so checkedout() is meaningful.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'presence.db'}",
        poolclass=QueuePool, pool_size=2, max_overflow=0, pool_timeout=2,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    UserPresenceService.forget()
    yield engine, factory
    UserPresenceService.forget()
    engine.dispose()


def _make_user(factory, *, active=True) -> uuid.UUID:
    user_id = uuid.uuid4()
    with factory() as db:
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@t.test",
                    full_name="Presence", password_hash="x", role="Viewer", is_active=active))
        db.commit()
    return user_id


def _app(factory, monkeypatch):
    from api.middleware.auth_middleware import AuthMiddleware
    from api.routers.auth import router as auth_router
    from services.auth_service import AuthenticationService

    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    app.include_router(auth_router, prefix="/api")
    monkeypatch.setattr("api.middleware.auth_middleware._legacy_access_allowed", lambda: False)
    with factory() as db:
        user = AuthenticationService.create_user(db, f"hb{uuid.uuid4().hex[:6]}", f"{uuid.uuid4().hex[:6]}@t.test",
                                                 "SecurePassword123!", "Viewer")
        db.commit()
        token = AuthenticationService.authenticate_user(db, user.username, "SecurePassword123!")
        db.commit()
    return app, {"Authorization": f"Bearer {token}"}


def test_heartbeat_service_never_holds_a_connection(pooled):
    engine, factory = pooled
    user_id = _make_user(factory)
    start = dt.datetime(2026, 10, 22, 7, 0, tzinfo=dt.UTC)
    db = factory()  # one long-lived session, like a request that outlives the call
    try:
        for tick in range(120):  # one hour of 30s heartbeats
            UserPresenceService.forget()  # bypass the memo so every tick reaches the DB
            UserPresenceService.record_heartbeat(db, str(user_id), start + dt.timedelta(seconds=30 * tick))
            assert not db.in_transaction(), tick
            assert engine.pool.checkedout() == 0, tick
    finally:
        db.close()
    with factory() as check:
        seen = check.get(User, user_id).last_seen_at.replace(tzinfo=dt.UTC)
    assert seen == start + dt.timedelta(seconds=30 * 118)  # writes at most once per 60s


def test_throttled_heartbeats_issue_no_queries(pooled):
    engine, factory = pooled
    user_id = _make_user(factory)
    statements = []
    event.listen(engine, "before_cursor_execute", lambda *a, **k: statements.append(a[2]))
    now = dt.datetime.now(dt.UTC)
    with factory() as db:
        UserPresenceService.record_heartbeat(db, str(user_id), now)
        first = len(statements)
        for second in range(1, 59):
            UserPresenceService.record_heartbeat(db, str(user_id), now + dt.timedelta(seconds=second))
    assert first == 2  # one light SELECT + one UPDATE
    assert len(statements) == first


@pytest.mark.parametrize("active", [True, False])
def test_heartbeat_inactive_and_unknown_users_release_the_connection(pooled, active):
    engine, factory = pooled
    user_id = _make_user(factory, active=active)
    with factory() as db:
        result = UserPresenceService.record_heartbeat(db, str(user_id))
        assert (result is not None) is active
        assert UserPresenceService.record_heartbeat(db, str(uuid.uuid4())) is None
        assert UserPresenceService.record_heartbeat(db, "not-a-uuid") is None
        assert engine.pool.checkedout() == 0


def test_heartbeat_error_path_rolls_back_and_releases(pooled, monkeypatch):
    engine, factory = pooled
    user_id = _make_user(factory)
    with factory() as db:
        original = db.commit

        def boom():
            raise RuntimeError("db down")

        monkeypatch.setattr(db, "commit", boom)
        with pytest.raises(RuntimeError):
            UserPresenceService.record_heartbeat(db, str(user_id))
        monkeypatch.setattr(db, "commit", original)
        assert not db.in_transaction()
        assert engine.pool.checkedout() == 0


def test_no_leaked_connections_after_many_http_heartbeats(pooled, monkeypatch):
    engine, factory = pooled
    app, headers = _app(factory, monkeypatch)
    with TestClient(app) as client:
        for _ in range(60):  # pool_size=2, overflow=0: any leak would time out
            response = client.post("/api/auth/presence/heartbeat", headers=headers)
            assert response.status_code == 200, response.text
        assert engine.pool.checkedout() == 0
        # Error path: the presence write fails -> 503, still nothing checked out.
        UserPresenceService.forget()

        def failing(*_args, **_kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(UserPresenceService, "record_heartbeat", failing)
        for _ in range(10):
            assert client.post("/api/auth/presence/heartbeat", headers=headers).status_code == 503
        assert engine.pool.checkedout() == 0
        # Unauthenticated path.
        assert client.post("/api/auth/presence/heartbeat").status_code == 401
        assert engine.pool.checkedout() == 0


# --------------------------------------------------------------------------- summary-records

FILTER_CASES = [
    SummaryFilters(),
    SummaryFilters(year=2026),
    SummaryFilters(month="september"),
    SummaryFilters(year=2026, month="August"),
    SummaryFilters(team="window north"),
    SummaryFilters(team="Window South", year=2025),
    SummaryFilters(employee_id="WIN-001"),
    SummaryFilters(employee_id="WIN-003", month="SEPTEMBER"),
    SummaryFilters(team="No Such Team"),
]


@pytest.fixture(scope="module")
def window_engine():
    engine = _synthetic_engine()
    yield engine
    engine.dispose()


def _record_service(db):
    return DashboardRecordService(db, sql_repository_cls=PerformanceRepository)


@pytest.mark.parametrize("scope_name", sorted(SCOPES))
@pytest.mark.parametrize("filters", FILTER_CASES, ids=repr)
def test_query_level_summary_matches_legacy(window_engine, scope_name, filters):
    scope = SCOPES[scope_name]
    with Session(window_engine) as db:
        legacy = performance._summary_records_legacy(db, _record_service(db), scope, filters, 50_000)
        pushed = summary_records_indexed(db, _record_service(db), scope, filters, 50_000)
    assert pushed is not None
    key = lambda row: str(row["id"])
    if filters.year is None and filters.month is None and filters.team is None:
        assert pushed.data == legacy.data  # default and employee_id: identical, same order
    else:
        assert sorted(pushed.data, key=key) == sorted(legacy.data, key=key)
    assert pushed.total == legacy.total
    assert pushed.truncated is False


def test_query_level_limit_and_truncation(window_engine):
    with Session(window_engine) as db:
        legacy = performance._summary_records_legacy(db, _record_service(db), SCOPES["Admin"], SummaryFilters(), 50_000)
        pushed = summary_records_indexed(db, _record_service(db), SCOPES["Admin"], SummaryFilters(), 3)
    assert pushed.data == legacy.data[:3]
    assert pushed.truncated is True and pushed.total is None


def test_filters_reach_sql_and_only_matching_records_are_resolved(window_engine, monkeypatch):
    statements = []
    resolved_keys = []
    original = DashboardRecordService.list_records_by_keys

    def spy(self, keys):
        resolved_keys.extend(keys)
        return original(self, keys)

    monkeypatch.setattr(DashboardRecordService, "list_records_by_keys", spy)
    listener = lambda *a, **k: statements.append(a[2])
    event.listen(window_engine, "before_cursor_execute", listener)
    try:
        with Session(window_engine) as db:
            result = summary_records_indexed(db, _record_service(db), SCOPES["Admin"],
                                             SummaryFilters(year=2026, month="September"), 50_000)
            total_records = db.execute(text("select count(*) from performance_records")).scalar()
    finally:
        event.remove(window_engine, "before_cursor_execute", listener)
    sql = "\n".join(statements).lower()
    assert "performance_records.year =" in sql
    assert "performance_records.month in" in sql
    assert len(resolved_keys) == len([row for row in result.data if row["performance_level"] == "Employee"])
    assert len(resolved_keys) < total_records


def test_branch_director_keeps_the_legacy_path(window_engine):
    from tests.test_insights_period_window import _scope

    with Session(window_engine) as db:
        assert summary_records_indexed(db, _record_service(db), _scope("Branch Director", accessible_branches=["DXB"]),
                                       SummaryFilters(), 10) is None
