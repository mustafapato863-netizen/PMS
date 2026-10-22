"""QA PMS #79 (ad08cf2) regressions.

1. DB unavailability during auth is 503 + Retry-After, never 401.
2. summary-records never truncates by default; an explicit limit keeps the
   newest periods; the count headers are exposed through CORS.
3. Whitespace-only regions are "missing" on every path (follow-up's record
   scope, the summary-records fast/legacy paths and the SQL scope).
"""
from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import Session
from starlette.requests import Request

from api.dependencies import get_current_user_scope
from api.middleware.error_handling_middleware import ErrorHandlingMiddleware
from api.routers import performance
from services.summary_records_service import (
    SUMMARY_RECORDS_CAP,
    SummaryFilters,
    apply_limit,
    order_key,
    period_key,
    summary_records_indexed,
)
from tests.test_insights_period_window import SCOPES
from tests.test_summary_parity_capture import (
    _auth_app,
    _data,
    _seed,
    _seed_actions,
    _session,
)
from utils.db_errors import RETRY_AFTER_SECONDS, is_db_unavailable

POOL_TIMEOUT = sa_exc.TimeoutError("QueuePool limit of size 5 overflow 0 reached, connection timed out, timeout 10.00")


@pytest.fixture
def auth_client(monkeypatch):
    db = _session()
    teams, employees = _seed(db)
    _seed_actions(db, teams, employees)
    app, headers = _auth_app(db, monkeypatch)
    with TestClient(app) as client:
        yield client, headers
    db.close()


# --- 1. 503 vs 401 -----------------------------------------------------------

@pytest.fixture(scope="module")
def window_engine_qa():
    from tests.test_insights_period_window import _synthetic_engine

    engine = _synthetic_engine()
    yield engine
    engine.dispose()


def _record_service(db):
    from repositories.performance_repository import PerformanceRepository
    from services.dashboard_record_service import DashboardRecordService

    return DashboardRecordService(db, sql_repository_cls=PerformanceRepository)


@pytest.mark.parametrize("error", [
    POOL_TIMEOUT,
    sa_exc.OperationalError("SELECT 1", {}, Exception("server closed the connection unexpectedly")),
    ConnectionError("connection refused"),
])
def test_db_failure_during_auth_is_503_with_retry_after(auth_client, monkeypatch, error):
    client, headers = auth_client

    def unavailable(*_args, **_kwargs):
        raise error

    monkeypatch.setattr("api.middleware.auth_middleware._load_authenticated_user", unavailable)
    for path in ("/api/performance/summary-records", "/api/corrective-actions/follow-up"):
        response = client.get(path, headers=headers)
        assert response.status_code == 503, path
        assert response.headers["Retry-After"] == str(RETRY_AFTER_SECONDS)
        assert response.json()["code"] == "SERVICE_UNAVAILABLE"


@pytest.mark.parametrize("error", [RuntimeError("bug"), KeyError("x"), sa_exc.IntegrityError("SELECT", {}, Exception("x"))])
def test_unexpected_auth_failure_is_500_not_401_or_503(auth_client, monkeypatch, error):
    client, headers = auth_client

    def broken(*_args, **_kwargs):
        raise error

    monkeypatch.setattr("api.middleware.auth_middleware._load_authenticated_user", broken)
    response = client.get("/api/performance/summary-records", headers=headers)
    assert response.status_code == 500
    assert "Retry-After" not in response.headers


@pytest.mark.parametrize("token", ["not-a-jwt", "a.b.c", ""])
def test_invalid_token_is_still_401(auth_client, token):
    client, _ = auth_client
    response = client.get("/api/performance/summary-records", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "Retry-After" not in response.headers


def test_expired_token_is_still_401(auth_client, monkeypatch):
    client, headers = auth_client

    def expired(_token):
        raise ValueError("Token has expired.")

    monkeypatch.setattr("services.auth_service.AuthenticationService.validate_token", staticmethod(expired))
    assert client.get("/api/performance/summary-records", headers=headers).status_code == 401


def test_disabled_user_is_still_401(auth_client, monkeypatch):
    client, headers = auth_client

    def disabled(*_args, **_kwargs):
        raise ValueError("User account is disabled")

    monkeypatch.setattr("api.middleware.auth_middleware._load_authenticated_user", disabled)
    assert client.get("/api/performance/summary-records", headers=headers).status_code == 401


def test_valid_token_still_200(auth_client):
    client, headers = auth_client
    assert client.get("/api/performance/summary-records", headers=headers).status_code == 200


class _TimeoutDB:
    def query(self, *_args, **_kwargs):
        raise POOL_TIMEOUT


def _request_with_user(user_id="00000000-0000-0000-0000-000000000001"):
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    request.state.user = {"user_id": user_id, "role": "Admin"}
    return request


def test_current_user_scope_maps_pool_timeout_to_503():
    with pytest.raises(HTTPException) as caught:
        get_current_user_scope(_TimeoutDB(), _request_with_user())
    assert caught.value.status_code == 503
    assert caught.value.headers["Retry-After"] == str(RETRY_AFTER_SECONDS)


def test_scope_dependency_db_failure_reaches_client_as_503(auth_client, monkeypatch):
    """Past the middleware, a pool timeout in the scope lookup must not become
    success:false (follow-up) or a 401."""
    client, headers = auth_client
    import api.dependencies as deps

    def timeout(*_args, **_kwargs):
        raise POOL_TIMEOUT

    monkeypatch.setattr(deps, "_get_current_user_scope", timeout)
    for path in ("/api/performance/summary-records", "/api/corrective-actions/follow-up",
                 "/api/corrective-actions/owners"):
        response = client.get(path, headers=headers)
        assert response.status_code == 503, path
        assert response.headers["Retry-After"] == str(RETRY_AFTER_SECONDS)


def test_error_middleware_maps_unhandled_pool_timeout_to_503(monkeypatch):
    monkeypatch.setattr("api.middleware.error_handling_middleware._log_error_blocking", lambda *a, **k: None)
    app = FastAPI()
    app.add_middleware(ErrorHandlingMiddleware)

    @app.get("/boom")
    def boom():
        raise POOL_TIMEOUT

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == str(RETRY_AFTER_SECONDS)


def test_classifier_only_matches_availability_errors():
    assert is_db_unavailable(POOL_TIMEOUT)
    wrapped = RuntimeError("wrapper")
    wrapped.__cause__ = POOL_TIMEOUT
    assert is_db_unavailable(wrapped)
    assert not is_db_unavailable(sa_exc.IntegrityError("INSERT", {}, Exception("dup")))
    assert not is_db_unavailable(ValueError("Invalid token."))


# --- 2. summary-records truncation + CORS -------------------------------------

_MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August",
                "September", "October", "November", "December"]


def _row(year, month, rid):
    return {"id": rid, "year": year, "month": month}


def test_default_cap_is_50k_with_truncated_header(caplog):
    assert SUMMARY_RECORDS_CAP == 50_000
    rows = [_row(2000 + i // 12 % 30, _MONTH_NAMES[i % 12], f"{i:06d}") for i in range(50_001)]
    with caplog.at_level(logging.WARNING, logger="services.summary_records_service"):
        result = apply_limit(rows, None)
    assert len(result.data) == 50_000 and result.truncated is True and result.total == 50_001
    assert min(order_key(row) for row in rows) not in {order_key(row) for row in result.data}
    assert any("summary-records truncated" in record.message for record in caplog.records)
    assert apply_limit(rows[:10], None).truncated is False


def test_explicit_limit_keeps_newest_periods_oldest_first():
    rows = [
        _row(2026, "September", "a"), _row(2025, "December", "b"), _row(2026, "October", "c"),
        _row(2026, "January", "d"), _row("2026", "oct", "e"), _row(2024, "May", "f"),
    ]
    result = apply_limit(rows, 3)
    assert [row["id"] for row in result.data] == ["a", "c", "e"]  # Sep, Oct, Oct (id tiebreak)
    assert result.truncated is True and result.total == 6


def test_period_key_orders_months_numerically():
    assert period_key(_row(2026, "February", "x")) > period_key(_row(2026, "January", "x"))
    assert period_key(_row(2026, "12", "x")) > period_key(_row(2026, "Nov", "x"))
    assert period_key(_row(None, "bogus", "x")) == (0, 0)


def test_sql_month_case_matches_python_ordering(window_engine_qa):
    from sqlalchemy import select

    from models.models import PerformanceRecord
    from repositories.performance_repository import month_number_sql
    from utils.months import month_number

    with Session(window_engine_qa) as db:
        rows = db.execute(select(PerformanceRecord.month, month_number_sql())).all()
    assert rows and all(number == month_number(month) and number > 0 for month, number in rows)


def test_index_order_by_and_limit_are_in_the_emitted_sql(window_engine_qa):
    statements = []
    listener = lambda *a, **k: statements.append(a[2])
    event.listen(window_engine_qa, "before_cursor_execute", listener)
    try:
        with Session(window_engine_qa) as db:
            result = summary_records_indexed(db, _record_service(db), SCOPES["Admin"], SummaryFilters(), 3)
    finally:
        event.remove(window_engine_qa, "before_cursor_execute", listener)
    index_sql = [sql.lower() for sql in statements if "order by performance_records.year desc" in sql.lower()]
    assert index_sql, "index query must ORDER BY year DESC in SQL"
    sql = index_sql[0]
    assert "case lower(trim(performance_records.month" in sql and "desc, performance_records.id desc" in sql
    assert " limit " in sql and " offset " in sql
    assert result.truncated is True and len(result.data) == 3


def test_fast_path_keeps_newest_and_matches_legacy(window_engine_qa):
    with Session(window_engine_qa) as db:
        legacy_all = performance._summary_records_legacy(db, _record_service(db), SCOPES["Admin"], SummaryFilters(), None)
        pushed = summary_records_indexed(db, _record_service(db), SCOPES["Admin"], SummaryFilters(), 4)
        legacy = performance._summary_records_legacy(db, _record_service(db), SCOPES["Admin"], SummaryFilters(), 4)
    newest = sorted(legacy_all.data, key=order_key)[-4:]
    assert pushed.data == legacy.data == newest  # oldest first, newest 4 kept
    assert pushed.total == legacy.total == len(legacy_all.data)


def test_default_cap_through_the_endpoint(auth_client, monkeypatch):
    import services.summary_records_service as svc

    client, headers = auth_client
    every = _data(client.get("/api/performance/summary-records", headers=headers))
    monkeypatch.setattr(svc, "SUMMARY_RECORDS_CAP", 2)
    response = client.get("/api/performance/summary-records", headers=headers)
    assert response.headers["X-Result-Truncated"] == "true"
    assert response.headers["X-Total-Count"] == str(len(every))
    assert _data(response) == sorted(every, key=order_key)[-2:]


def test_endpoint_without_limit_is_complete(auth_client):
    client, headers = auth_client
    response = client.get("/api/performance/summary-records", headers=headers)
    rows = _data(response)
    assert response.headers["X-Result-Truncated"] == "false"
    assert response.headers["X-Total-Count"] == str(len(rows))


def test_summary_records_rate_limit_returns_429(auth_client, monkeypatch):
    import time

    from api.routers import performance as perf
    from services.rate_limit import policy
    from services.rate_limit.limiter import InProcessCounterStore, RateLimiter, RateRule

    client, headers = auth_client
    runtime = policy.RateLimitRuntime(
        mode="enforce",
        limiter=RateLimiter(primary=None, fallback=InProcessCounterStore(max_keys=100), clock=time.time,
                            cool_down_seconds=1),
        rules=policy.RuleSet.from_limits(policy.RateLimits(*(10_000,) * 7)),
        trusted_networks=(),
    )
    previous = policy.set_runtime(runtime)
    monkeypatch.setattr(perf, "SUMMARY_RECORDS_RULE", RateRule("summary_records_user", 2, 60))
    try:
        codes = [client.get("/api/performance/summary-records", headers=headers).status_code for _ in range(3)]
        blocked = client.get("/api/performance/summary-records", headers=headers)
    finally:
        policy.set_runtime(previous)
    assert codes == [200, 200, 429]
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) >= 1
    assert blocked.json()["code"] == "rate_limited"


def test_cors_exposes_count_headers():
    from app import app
    from config import settings

    origin = next((o for o in settings.CORS_ORIGINS if o != "*"), "http://localhost:5173")
    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": origin})
    exposed = {h.strip().lower() for h in response.headers.get("access-control-expose-headers", "").split(",")}
    assert {"x-total-count", "x-result-truncated", "retry-after"} <= exposed


# --- 3. whitespace-only regions / blank grants ------------------------------------

@pytest.mark.parametrize("grants", [[""], [" "], ["\t", "  "]])
def test_blank_region_grants_are_dropped(grants):
    from types import SimpleNamespace

    from utils.report_scope import filter_records_by_scope, user_can_access_team

    blank = SimpleNamespace(region="", employee=SimpleNamespace(region=" "), team=SimpleNamespace(region=None))
    shj = SimpleNamespace(region="SHJ", employee=None, team=None)
    scope = {"role": "Regional Manager", "accessible_regions": grants}
    assert filter_records_by_scope([blank, shj], scope) == []
    assert user_can_access_team(scope, "Any Team") is False
    mixed = {"role": "Regional Manager", "accessible_regions": [*grants, "shj "]}
    assert filter_records_by_scope([blank, shj], mixed) == [shj]


# --- 3b. whitespace-only regions --------------------------------------------------

def test_whitespace_regions_agree_on_follow_up_and_summary_paths():
    """QA L5: record '', employee ' ', team region SHJ."""
    from api.routers import performance
    from models.models import Employee, PerformanceRecord
    from repositories.performance_repository import PerformanceRepository
    from services.dashboard_record_service import DashboardRecordService
    from tests.test_insights_period_window import _synthetic_engine
    from tests.test_presence_pool_and_summary_pushdown import _record_service, _rm
    from utils.report_scope import filter_records_by_scope

    engine = _synthetic_engine()
    try:
        with Session(engine) as db:
            south = db.query(Employee).filter(Employee.employee_id.in_(["WIN-004", "WIN-005", "WIN-006"])).all()
            ids = [e.id for e in south]
            for employee, value in zip(south, [" ", "\t", "  "]):
                employee.region = value
            db.query(PerformanceRecord).filter(PerformanceRecord.employee_id.in_(ids)).update(
                {PerformanceRecord.region: ""}, synchronize_session=False)
            records = db.query(PerformanceRecord).filter(PerformanceRecord.employee_id.in_(ids)).all()
            db.commit()
            from tests.test_insights_period_window import SCOPES
            admin_repo = PerformanceRepository(db, PerformanceRecord)
            expected_sql = {str(r.id) for r in admin_repo._dashboard_query(kpi_values=False)
                            .filter(PerformanceRecord.employee_id.in_(ids)).all()}
            expected = {str(r.id) for r in records}
            expected_summary = {row["id"] for row in summary_records_indexed(
                db, _record_service(db), SCOPES["Admin"], SummaryFilters()).data} & expected
            assert expected_summary and expected_sql
            for region, visible in (("SHJ", True), ("DXB", False)):
                scope = _rm(region)
                # follow-up / corrective-action scope check (ORM record)
                follow_up = {str(r.id) for r in records if filter_records_by_scope([r], scope)}
                # SQL scope
                repo = PerformanceRepository(db, PerformanceRecord)
                sql_ids = {str(r.id) for r in repo._apply_scope(repo._dashboard_query(kpi_values=False), scope)
                           .filter(PerformanceRecord.employee_id.in_(ids)).all()}
                pushed = summary_records_indexed(db, _record_service(db), scope, SummaryFilters())
                legacy = performance._summary_records_legacy(db, _record_service(db), scope, SummaryFilters(), None)
                assert pushed.data == legacy.data
                summary = {row["id"] for row in pushed.data} & expected
                assert follow_up == (expected if visible else set()), region
                assert sql_ids == (expected_sql if visible else set()), region
                assert summary == (expected_summary if visible else set()), region
                if visible:
                    assert {row["region"] for row in pushed.data if row["id"] in expected} == {"SHJ"}
            index = {str(r.record_key[0]): r.region for r in DashboardRecordService(db).list_record_index()}
            assert {index[r.id.hex] for r in records} == {"SHJ"}
    finally:
        engine.dispose()
