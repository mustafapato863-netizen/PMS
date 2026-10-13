"""Catalog periods come from the option rows the catalog already loads (synthetic data only)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import router as api_router
from api.routers.performance import _catalog_row_counted
from services.dashboard_record_service import DashboardRecordService
from tests.test_option_projections import _seed_option_data, _session

app = FastAPI()
app.include_router(api_router, prefix="/api")
client = TestClient(app)


@pytest.mark.parametrize(
    ("row", "counted"),
    [
        ({"year": 2026, "month": "June"}, True),  # no score information: fail open
        ({"score": None}, True),
        ({"score": "not a number"}, True),
        ({"score": 0}, False),
        ({"score": 0.0}, False),
        ({"score": 0.5}, True),
        ({"score": 82.85}, True),
    ],
)
def test_a_row_counts_for_the_catalog_when_its_score_is_above_zero_or_unknown(row, counted):
    assert _catalog_row_counted(row) is counted


def test_the_default_option_projection_does_not_carry_a_score():
    db = _session()
    try:
        _seed_option_data(db)
        assert "score" not in DashboardRecordService(db).list_option_rows()[0]
    finally:
        db.close()


def test_the_catalog_option_projection_carries_the_score_in_the_same_query():
    db = _session()
    try:
        _seed_option_data(db)
        rows = DashboardRecordService(db).list_option_rows(include_scores=True)
        assert len(rows) == 1
        assert rows[0]["score"] is not None
        assert float(rows[0]["score"]) >= 0
    finally:
        db.close()


def _rows(*items):
    return [
        {
            "employee_id": f"E{index}",
            "employee_name": f"Person {index}",
            "team": "Sales",
            "month": month,
            "year": 2026,
            "region": "UAE",
            "performance_level": "Employee",
            "position": "Agent",
            **({"score": score} if score is not None else {}),
        }
        for index, (month, score) in enumerate(items)
    ]


def _catalog_months(rows):
    with (
        patch("api.routers.performance.DashboardRecordService") as mock_service,
        patch("api.routers.performance.get_current_user_scope") as mock_scope,
    ):
        mock_service.return_value.list_option_rows.return_value = rows
        mock_scope.return_value = {
            "role": "Manager",
            "accessible_teams": ["Sales"],
            "accessible_team_levels": [("Sales", "Employee")],
            "has_unrestricted_team_access": False,
            "legacy_unscoped": False,
        }
        response = client.get("/api/performance/catalog")
        assert response.status_code == 200
        assert mock_service.return_value.list_option_rows.call_args.kwargs == {"include_scores": True}
        return [period["month"] for period in response.json()["data"]["periods"]]


def test_a_zero_score_only_period_is_not_listed_and_a_scored_period_is_listed():
    months = _catalog_months(_rows(("June", 82.85), ("September", 0), ("September", 0)))
    assert months == ["June"]


def test_a_period_with_a_positive_row_is_listed_even_beside_zero_rows():
    months = _catalog_months(_rows(("July", 0), ("July", 79.8), ("August", 0)))
    assert months == ["July"]


def test_rows_without_score_information_are_listed_fail_open():
    months = _catalog_months(_rows(("June", None), ("July", None)))
    assert months == ["July", "June"]
