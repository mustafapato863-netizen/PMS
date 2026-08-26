import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import Employee, PerformanceRecord, Team
from services.performance_dashboard_read_service import PerformanceDashboardReadService


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db):
    inbound = Team(
        id=uuid.uuid4(),
        name="Inbound",
        db_name="inbound",
        display_name="Inbound",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    outbound = Team(
        id=uuid.uuid4(),
        name="Outbound",
        db_name="outbound",
        display_name="Outbound",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    employees = [
        Employee(id=uuid.uuid4(), employee_id="EMP-A", name="Alice", team_id=inbound.id, region="EGY"),
        Employee(id=uuid.uuid4(), employee_id="EMP-B", name="Bob", team_id=inbound.id, region="EGY"),
        Employee(id=uuid.uuid4(), employee_id="EMP-C", name="Carol", team_id=outbound.id, region="EGY"),
    ]
    db.add_all([inbound, outbound, *employees])
    db.flush()
    rows = [
        PerformanceRecord(
            id=uuid.uuid4(), year=2026, employee_id=employees[0].id, team_id=inbound.id,
            month="June", performance_level="Employee", region="EGY", score=90, grade="A", status="Exceeds",
        ),
        PerformanceRecord(
            id=uuid.uuid4(), year=2026, employee_id=employees[1].id, team_id=inbound.id,
            month="June", performance_level="Employee", region="EGY", score=80, grade="B", status="Meets",
        ),
        PerformanceRecord(
            id=uuid.uuid4(), year=2026, employee_id=employees[0].id, team_id=inbound.id,
            month="May", performance_level="Employee", region="EGY", score=70, grade="C", status="Below",
        ),
        PerformanceRecord(
            id=uuid.uuid4(), year=2026, employee_id=employees[2].id, team_id=outbound.id,
            month="June", performance_level="Employee", region="EGY", score=95, grade="A", status="Exceeds",
        ),
    ]
    db.add_all(rows)
    db.commit()


def _scope():
    return {
        "user_id": str(uuid.uuid4()),
        "role": "Manager",
        "employee_id": None,
        "accessible_teams": ["Inbound"],
        "accessible_team_levels": [("Inbound", "Employee")],
        "is_general_manager": False,
        "is_self_only": False,
        "legacy_unscoped": False,
    }


def test_summary_is_period_bounded_and_sql_scoped():
    db = _session()
    try:
        _seed(db)
        data = PerformanceDashboardReadService(db, _scope()).summary(
            period="2026-06",
            trend_months=2,
        )

        assert data["current"]["total_agents"] == 2
        assert data["current"]["average_score"] == 85.0
        assert data["previous"]["total_agents"] == 1
        assert data["team_breakdown"][0]["teamName"] == "Inbound"
        assert all(item["teamName"] != "Outbound" for item in data["team_breakdown"])
    finally:
        db.close()


def test_records_use_stable_cursor_pages_and_keep_scope_out_of_results():
    db = _session()
    try:
        _seed(db)
        service = PerformanceDashboardReadService(db, _scope())
        first = service.records_page(period="2026-06", page_size=1)
        assert first["has_more"] is True
        assert [item["employee_name"] for item in first["items"]] == ["Alice"]

        second = service.records_page(
            period="2026-06",
            page_size=1,
            cursor=first["next_cursor"],
        )
        assert second["has_more"] is False
        assert [item["employee_name"] for item in second["items"]] == ["Bob"]
        assert all(item["employee_name"] != "Carol" for item in second["items"])

        filtered = service.records_page(
            period="2026-06",
            grade="A",
            status="Exceeds",
        )
        assert filtered["items"][0]["previous_score"] == 70
    finally:
        db.close()


def test_invalid_cursor_and_unbounded_history_are_rejected():
    db = _session()
    try:
        _seed(db)
        service = PerformanceDashboardReadService(db, _scope())
        with pytest.raises(Exception, match="cursor is invalid"):
            service.records_page(period="2026-06", cursor="not-a-cursor")
        with pytest.raises(Exception, match="months must be between"):
            service.employee_history(employee_id="EMP-A", period_end="2026-06", months=25)
        with pytest.raises(Exception, match="sort must be"):
            service.records_page(period="2026-06", sort="unsupported")
        with pytest.raises(Exception, match="location must be"):
            service.records_page(period="2026-06", location="mars")
    finally:
        db.close()
