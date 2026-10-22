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
from services.summary_records_service import (
    LEGACY_PATH_ROLES,
    SummaryFilters,
    apply_limit,
    summary_records_indexed,
)
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
    if scope["role"] in LEGACY_PATH_ROLES:
        assert pushed is None  # kept on the legacy path; the router falls back
        return
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
        legacy = performance._summary_records_legacy(db, _record_service(db), SCOPES["Admin"], SummaryFilters(), None)
        pushed = summary_records_indexed(db, _record_service(db), SCOPES["Admin"], SummaryFilters(), 3)
        default = summary_records_indexed(db, _record_service(db), SCOPES["Admin"], SummaryFilters())
    assert default.data == legacy.data and default.truncated is False and default.total == len(legacy.data)
    assert pushed.data == apply_limit(legacy.data, 3).data
    assert pushed.truncated is True and pushed.total == len(legacy.data)


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


def _region_engine():
    """Synthetic data where Window South rows carry no record/employee region (team SHJ only),
    and one Window North employee (WIN-002) carries an explicit employee region that differs
    from the team's, and one WIN-001 record carries its own record region."""
    from models.models import Employee, PerformanceRecord

    engine = _synthetic_engine()
    with Session(engine) as db:
        south = db.query(Employee).filter(Employee.employee_id.in_(["WIN-004", "WIN-005", "WIN-006"])).all()
        for employee in south:
            employee.region = ""
        db.query(PerformanceRecord).filter(
            PerformanceRecord.employee_id.in_([employee.id for employee in south])
        ).update({PerformanceRecord.region: None}, synchronize_session=False)
        win2 = db.query(Employee).filter(Employee.employee_id == "WIN-002").one()
        win2.region = "AUH"  # employee region wins over the team's DXB
        win1 = db.query(Employee).filter(Employee.employee_id == "WIN-001").one()
        first = db.query(PerformanceRecord).filter(PerformanceRecord.employee_id == win1.id).first()
        first.region = "RAK"  # record region wins over employee and team
        first_id = str(first.id)
        db.commit()
    return engine, first_id


def _rm(region):
    return {**SCOPES["Regional Manager"], "accessible_regions": [region]}


def _visible(engine, scope):
    with Session(engine) as db:
        pushed = summary_records_indexed(db, _record_service(db), scope, SummaryFilters(), 50_000)
        legacy = performance._summary_records_legacy(db, _record_service(db), scope, SummaryFilters(), 50_000)
    assert pushed is not None
    assert pushed.data == legacy.data  # fast path == legacy path, same order
    return pushed.data


def test_team_only_region_is_visible_to_the_matching_regional_manager_only():
    engine, _ = _region_engine()
    try:
        shj = {row["employee_id"] for row in _visible(engine, _rm("SHJ"))}
        dxb = {row["employee_id"] for row in _visible(engine, _rm("DXB"))}
        assert {"WIN-004", "WIN-005", "WIN-006"} <= shj  # team-only region (SHJ)
        assert not {"WIN-004", "WIN-005", "WIN-006"} & dxb
        for row in _visible(engine, _rm("SHJ")):
            if row["employee_id"] in {"WIN-004", "WIN-005", "WIN-006"}:
                assert row["region"] == "SHJ"
    finally:
        engine.dispose()


def test_record_and_employee_regions_win_over_the_team_region():
    engine, rak_record = _region_engine()
    try:
        dxb = _visible(engine, _rm("DXB"))
        auh = _visible(engine, _rm("AUH"))
        rak = _visible(engine, _rm("RAK"))
        assert "WIN-002" not in {row["employee_id"] for row in dxb}  # team DXB, employee AUH
        assert {row["employee_id"] for row in auh} == {"WIN-002"}
        assert [row["id"] for row in rak] == [rak_record]
        assert rak_record not in {row["id"] for row in dxb}
    finally:
        engine.dispose()


def test_index_and_resolved_records_agree_for_regional_managers():
    import uuid as _uuid

    from utils.report_scope import (
        filter_records_by_scope,
        filter_records_by_team_levels,
    )

    engine, _ = _region_engine()
    try:
        with Session(engine) as db:
            service = _record_service(db)
            full, index = service.list_analysis_records(), service.list_record_index()
            assert [row.region for row in index] == [record.region for record in full]
            for region in ("SHJ", "DXB", "AUH", "RAK", "EGY"):
                scope = _rm(region)
                full_ids = [str(r.id) for r in filter_records_by_team_levels(filter_records_by_scope(full, scope), scope)]
                index_ids = [str(_uuid.UUID(hex=r.record_key[0])) for r in filter_records_by_team_levels(
                    filter_records_by_scope(index, scope), scope)]
                assert index_ids == full_ids, region
    finally:
        engine.dispose()


def test_insights_window_matches_full_path_for_team_only_regions():
    from tests.test_insights_period_window import PAGE_SECTIONS, _compare

    engine, _ = _region_engine()
    try:
        cases = [
            (f"RM {region} | {label}", _rm(region), filters, PAGE_SECTIONS)
            for region in ("SHJ", "DXB", "AUH")
            for label, filters in (("latest", {}), ("september", {"year": 2026, "month": "September"}))
        ]
        _compare(engine, cases)
    finally:
        engine.dispose()
