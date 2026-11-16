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
        patch("api.routers.performance._authorized_catalog_teams", return_value=([], [])),
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


def _seed_preapprovals_teams(db, *, include_ip: bool = True, include_offshore_record: bool = False):
    from models.models import Employee, PerformanceRecord, Team
    import uuid

    teams = []
    if include_ip:
        teams.append(
            Team(
                id=uuid.uuid4(),
                name="Pre-Approvals IP",
                db_name="Pre-Approvals IP",
                display_name="Pre-Approvals IP",
                region="EGY",
                team_level="employee",
                is_active=True,
            )
        )
    offshore = Team(
        id=uuid.uuid4(),
        name="Pre-Approvals IP Offshore",
        db_name="Pre-Approvals IP Offshore",
        display_name="Pre-Approvals IP Offshore",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    teams.append(offshore)
    db.add_all(teams)
    db.flush()

    if include_offshore_record:
        emp = Employee(
            id=uuid.uuid4(),
            employee_id="EMP-OFF-1",
            name="Offshore Specialist",
            team_id=offshore.id,
            region="EGY",
            performance_level="Employee",
            position_name="Pre-Authorization Specialist",
        )
        db.add(emp)
        db.flush()
        db.add(
            PerformanceRecord(
                id=uuid.uuid4(),
                employee_id=emp.id,
                team_id=offshore.id,
                month="June",
                year=2026,
                performance_level="Employee",
                position_name="Pre-Approvals IP Specialist",
                region="EGY",
                score=88.5,
                grade="C",
                status="Meets",
            )
        )
    db.commit()
    return offshore


def test_catalog_hides_empty_legacy_preapprovals_ip_offshore_when_preapprovals_ip_is_active():
    from api.routers.performance import _authorized_catalog_teams

    db = _session()
    try:
        _seed_preapprovals_teams(db, include_ip=True, include_offshore_record=False)
        teams, _ = _authorized_catalog_teams(
            db,
            {"role": "Admin", "has_unrestricted_team_access": True},
            [],
        )
        names = [item["team"] for item in teams]
        assert "Pre-Approvals IP" in names
        assert "Pre-Approvals IP Offshore" not in names
    finally:
        db.close()


def test_catalog_keeps_preapprovals_ip_offshore_when_it_has_records_or_canonical_missing():
    from api.routers.performance import _authorized_catalog_teams

    db_with_records = _session()
    try:
        _seed_preapprovals_teams(db_with_records, include_ip=True, include_offshore_record=True)
        teams, _ = _authorized_catalog_teams(
            db_with_records,
            {"role": "Admin", "has_unrestricted_team_access": True},
            [],
        )
        assert "Pre-Approvals IP Offshore" in [item["team"] for item in teams]
    finally:
        db_with_records.close()

    db_without_ip = _session()
    try:
        _seed_preapprovals_teams(db_without_ip, include_ip=False, include_offshore_record=False)
        teams, _ = _authorized_catalog_teams(
            db_without_ip,
            {"role": "Admin", "has_unrestricted_team_access": True},
            [],
        )
        assert [item["team"] for item in teams] == ["Pre-Approvals IP Offshore"]
    finally:
        db_without_ip.close()


def test_migration_deactivates_empty_legacy_preapprovals_ip_offshore_only_when_safe():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from models.models import Team

    mig_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "f4d2e8a9c1b3_deactivate_legacy_preapprovals_ip_offshore.py"
    )
    spec = importlib.util.spec_from_file_location("mig_f4d2e8a9c1b3", mig_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    db_empty = _session()
    try:
        offshore = _seed_preapprovals_teams(db_empty, include_ip=True, include_offshore_record=False)
        conn = db_empty.connection()
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            module.upgrade()
        db_empty.commit()
        refreshed = db_empty.query(Team).filter(Team.id == offshore.id).one()
        assert refreshed.is_active is False
    finally:
        db_empty.close()

    db_with_records = _session()
    try:
        offshore = _seed_preapprovals_teams(db_with_records, include_ip=True, include_offshore_record=True)
        conn = db_with_records.connection()
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            module.upgrade()
        db_with_records.commit()
        refreshed = db_with_records.query(Team).filter(Team.id == offshore.id).one()
        assert refreshed.is_active is True
    finally:
        db_with_records.close()
