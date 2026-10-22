"""HTTP shape regression for summary-records, follow-up and owners.

Uses the synthetic dataset from ``test_summary_parity_capture`` through the real
AuthMiddleware (which now does its DB lookup in the threadpool) and checks the
new optional summary-records parameters keep the default response unchanged.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.test_summary_parity_capture import (
    _auth_app,
    _data,
    _seed,
    _seed_actions,
    _session,
)


@pytest.fixture
def client_and_headers(monkeypatch):
    db = _session()
    teams, employees = _seed(db)
    _seed_actions(db, teams, employees)
    app, headers = _auth_app(db, monkeypatch)
    with TestClient(app) as client:
        yield client, headers
    db.close()


def test_summary_records_default_shape_is_unchanged(client_and_headers):
    client, headers = client_and_headers
    response = client.get("/api/performance/summary-records", headers=headers)
    body = response.json()
    assert set(body) >= {"success", "message", "data"}
    rows = body["data"]
    assert isinstance(rows, list) and rows
    assert response.headers["X-Total-Count"] == str(len(rows))
    assert response.headers["X-Result-Truncated"] == "false"
    for row in rows:
        assert {"employee_id", "month", "year", "evaluation"} <= set(row)
        assert row["evaluation"]["score"] is not None


def _ids(rows):
    return sorted(str(row["id"]) for row in rows)


def test_summary_records_filters_and_limit(client_and_headers):
    client, headers = client_and_headers
    every = _data(client.get("/api/performance/summary-records", headers=headers))
    sample = every[0]

    by_month = _data(client.get("/api/performance/summary-records", params={"month": str(sample["month"]).upper()}, headers=headers))
    assert _ids(by_month) == _ids(row for row in every if str(row["month"]).casefold() == str(sample["month"]).casefold())

    by_year = _data(client.get("/api/performance/summary-records", params={"year": sample["year"]}, headers=headers))
    assert _ids(by_year) == _ids(row for row in every if str(row["year"]) == str(sample["year"]))

    by_employee = _data(client.get("/api/performance/summary-records", params={"employee_id": sample["employee_id"]}, headers=headers))
    assert by_employee == [row for row in every if str(row["employee_id"]) == sample["employee_id"]]

    limited = client.get("/api/performance/summary-records", params={"limit": 1}, headers=headers)
    assert _data(limited) == every[:1]
    if len(every) > 1:
        # Truncated: the query-level path stops resolving, so no exact total.
        assert limited.headers["X-Result-Truncated"] == "true"
        assert "X-Total-Count" not in limited.headers
    else:
        assert limited.headers["X-Result-Truncated"] == "false"


@pytest.mark.parametrize("limit", [0, 50_001])
def test_summary_records_limit_is_bounded(client_and_headers, limit):
    client, headers = client_and_headers
    assert client.get("/api/performance/summary-records", params={"limit": limit}, headers=headers).status_code == 422


def test_follow_up_and_owners_shapes(client_and_headers):
    client, headers = client_and_headers
    follow_up = _data(client.get("/api/corrective-actions/follow-up", headers=headers))
    assert set(follow_up) == {"summary", "actions"}
    assert set(follow_up["summary"]) == {"overdue", "due_soon", "open", "in_progress", "completed_this_month", "completion_rate"}
    owners = _data(client.get("/api/corrective-actions/owners", headers=headers))
    assert isinstance(owners, list)
    for owner in owners:
        assert set(owner) == {"id", "name", "role"}
