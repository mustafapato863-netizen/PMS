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
from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import Session
from starlette.requests import Request

from api.dependencies import get_current_user_scope
from api.middleware.error_handling_middleware import ErrorHandlingMiddleware
from services.summary_records_service import (
    SummaryFilters,
    apply_limit,
    period_key,
    summary_records_indexed,
)
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

def _row(year, month, rid):
    return {"id": rid, "year": year, "month": month}


def test_no_default_truncation():
    rows = [_row(2020 + i % 7, "January", str(i)) for i in range(25_000)]
    result = apply_limit(rows, None)
    assert result.data == rows and result.truncated is False and result.total == 25_000


def test_explicit_limit_keeps_newest_periods_in_original_order(caplog):
    rows = [
        _row(2026, "September", "a"), _row(2025, "December", "b"), _row(2026, "October", "c"),
        _row(2026, "January", "d"), _row("2026", "oct", "e"), _row(2024, "May", "f"),
    ]
    with caplog.at_level(logging.WARNING, logger="services.summary_records_service"):
        result = apply_limit(rows, 3)
    assert [row["id"] for row in result.data] == ["a", "c", "e"]  # Oct, Oct, Sep, response order
    assert result.truncated is True and result.total == 6
    assert any("summary-records truncated" in record.message for record in caplog.records)


def test_period_key_orders_months_numerically():
    assert period_key(_row(2026, "February", "x")) > period_key(_row(2026, "January", "x"))
    assert period_key(_row(2026, "12", "x")) > period_key(_row(2026, "Nov", "x"))
    assert period_key(_row(None, "bogus", "x")) == (0, 0)


def test_endpoint_without_limit_is_complete(auth_client):
    client, headers = auth_client
    response = client.get("/api/performance/summary-records", headers=headers)
    rows = _data(response)
    assert response.headers["X-Result-Truncated"] == "false"
    assert response.headers["X-Total-Count"] == str(len(rows))
    limited = client.get("/api/performance/summary-records", params={"limit": 2}, headers=headers)
    newest = sorted((period_key(row) for row in rows), reverse=True)[:2]
    assert sorted((period_key(row) for row in _data(limited)), reverse=True) == newest


def test_cors_exposes_count_headers():
    from app import app
    from config import settings

    origin = next((o for o in settings.CORS_ORIGINS if o != "*"), "http://localhost:5173")
    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": origin})
    exposed = {h.strip().lower() for h in response.headers.get("access-control-expose-headers", "").split(",")}
    assert {"x-total-count", "x-result-truncated", "retry-after"} <= exposed


# --- 3. whitespace-only regions --------------------------------------------------

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
