import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import (
    Employee,
    ManagementKPIConfig,
    ManagementKPISnapshot,
    PerformanceRecord,
    Team,
)
from repositories.performance_repository import PerformanceRepository
from services.dashboard_record_service import DashboardRecordService
from services.management_bsc_service import ManagementBSCService
from services.planning_service import PlanningService
from services.report_service import ReportService


class _UnusedPerformanceRepo:
    def get_all(self):
        raise AssertionError("Planning options must not load full performance records")


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_option_data(db):
    employee_team = Team(
        id=uuid.uuid4(),
        name="Marketing",
        db_name="marketing",
        display_name="Marketing",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    management_team = Team(
        id=uuid.uuid4(),
        name="Marketing__management",
        db_name="marketing__management",
        display_name="Marketing",
        region="EGY",
        team_level="management",
        is_active=True,
    )
    employee = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-1",
        name="Employee One",
        team_id=employee_team.id,
        region="EGY",
        performance_level="Employee",
        position_name="Designer",
    )
    record = PerformanceRecord(
        id=uuid.uuid4(),
        year=2026,
        employee_id=employee.id,
        team_id=employee_team.id,
        month="June",
        performance_level="Employee",
        position_name="Designer",
        region="EGY",
        score=91.5,
        grade="B",
        status="Meets",
    )
    config = ManagementKPIConfig(
        id=uuid.uuid4(),
        team_id=management_team.id,
        performance_level="Managerial",
        position_name="Marketing Manager",
        employee_identifier=None,
        perspective_key="financial",
        kpi_key="revenue",
        kpi_label="Revenue",
        direction="higher_better",
        weight=1,
        target_value=100,
        target_unit="%",
        display_order=0,
        effective_month="June",
        effective_year=2026,
        is_active=True,
    )
    snapshot = ManagementKPISnapshot(
        id=uuid.uuid4(),
        team_id=management_team.id,
        employee_identifier="MGR-1",
        employee_name="Manager One",
        position_name="Marketing Manager",
        performance_level="Managerial",
        month="June",
        year=2026,
        perspective_key="financial",
        kpi_key="revenue",
        kpi_label="Revenue",
        actual_value=90,
    )
    db.add_all([employee_team, management_team, employee, record, config, snapshot])
    db.commit()


def test_sql_option_rows_preserve_employee_and_management_dimensions():
    db = _session()
    try:
        _seed_option_data(db)

        employee_rows = DashboardRecordService(db).list_option_rows()
        management_rows = ManagementBSCService(db).list_option_rows()

        assert employee_rows == [{
            "employee_id": "EMP-1",
            "employee_name": "Employee One",
            "team": "Marketing",
            "month": "June",
            "year": 2026,
            "region": "EGY",
            "performance_level": "Employee",
            "position": "Designer",
            "grade": "B",
            "status": "Meets",
        }]
        assert management_rows == [{
            "employee_id": "MGR-1",
            "employee_name": "Manager One",
            "team": "Marketing",
            "month": "June",
            "year": 2026,
            "region": "EGY",
            "performance_level": "Managerial",
            "position": "Marketing Manager",
            "grade": None,
            "status": None,
        }]
    finally:
        db.close()


def test_planning_projection_reuses_team_and_level_scope():
    db = _session()
    try:
        _seed_option_data(db)
        service = PlanningService(_UnusedPerformanceRepo(), db=db)
        scope = {
            "role": "Manager",
            "user_id": str(uuid.uuid4()),
            "accessible_teams": ["Marketing"],
            "accessible_team_levels": [("Marketing", "Employee")],
            "is_general_manager": False,
            "legacy_unscoped": False,
        }

        options = service.options(scope)

        assert options["teams"] == ["Marketing"]
        assert options["performance_levels"] == ["Employee"]
        assert [employee["id"] for employee in options["employees"]] == ["EMP-1"]
    finally:
        db.close()


def test_report_options_use_projection_without_loading_full_records(monkeypatch):
    db = _session()
    try:
        _seed_option_data(db)
        monkeypatch.setattr(
            PerformanceRepository,
            "get_dashboard_records",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("Report options must not load full dashboard records")
            ),
        )
        scope = {
            "role": "Admin",
            "accessible_teams": [],
            "accessible_team_levels": [],
            "is_general_manager": True,
            "legacy_unscoped": False,
        }

        options = ReportService(db).options(scope)

        assert options["periods"] == [{"year": 2026, "month": "June", "key": "2026-06"}]
        assert options["teams"] == ["Marketing"]
        assert options["grades"] == ["B"]
        assert options["statuses"] == ["Meets"]
        assert [employee["id"] for employee in options["employees"]] == ["EMP-1"]
    finally:
        db.close()
