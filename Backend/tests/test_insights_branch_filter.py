from __future__ import annotations

import pytest
from models.schemas import CallsData, EvaluationData, GeoBreakdown, GeoData, PerformanceRecord
from services.insights_service import InsightsService
from services.planning_service import PlanningService
from utils.branch_scope import project_record_for_branch


class StubRepository:
    def __init__(self, records):
        self.records = records

    def get_all(self):
        return self.records


def _make_outbound_record(
    emp_id: str,
    name: str,
    sharjah_attended: int,
    sharjah_bookings: int,
    dubai_attended: int,
    dubai_bookings: int,
) -> PerformanceRecord:
    total_attended = sharjah_attended + dubai_attended
    total_bookings = sharjah_bookings + dubai_bookings
    unpartitioned_attend_rate = (total_attended / total_bookings) if total_bookings > 0 else 0.0
    return PerformanceRecord(
        id=f"OB_{emp_id}",
        employee_id=emp_id,
        employee_name=name,
        team="Outbound",
        month="September",
        year=2026,
        region="EGY",
        position="Call Center Agent",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=88.4, grade="B"),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=dubai_bookings, sharjah=sharjah_bookings, ajman=100, clinics=20),
            attended=GeoBreakdown(dubai=dubai_attended, sharjah=sharjah_attended, ajman=50, clinics=10),
        ),
        kpi_values=[
            {
                "kpi_key": "Attendance",
                "label": "Attendance Rate",
                "actual_value": unpartitioned_attend_rate,
                "target_value": 0.65,
                "weight_applied": 0.7,
                "contribution": (unpartitioned_attend_rate / 0.65) * 0.7,
            },
            {
                "kpi_key": "Booking",
                "label": "Booking Rate",
                "actual_value": 0.3,
                "target_value": 0.3,
                "weight_applied": 0.3,
                "contribution": 0.3,
            },
        ],
    )


def test_project_record_for_branch_with_geo_data():
    record = _make_outbound_record(
        emp_id="EMP1",
        name="Abdelrahman",
        sharjah_attended=19,
        sharjah_bookings=25,
        dubai_attended=259,
        dubai_bookings=528,
    )

    # Sharjah projection: 19 / 25 = 0.76 (target 0.65 -> above target)
    proj_shj = project_record_for_branch(record, "sharjah")
    attend_shj = next(k for k in proj_shj.kpi_values if k.get("kpi_key") == "Attendance")
    assert round(attend_shj["actual_value"], 2) == 0.76
    assert attend_shj["achievement_ratio"] > 1.0
    assert proj_shj.evaluation.score > record.evaluation.score
    assert proj_shj.branch_key == "sharjah"

    # Dubai projection: 259 / 528 = 0.49 (target 0.65 -> below target)
    proj_dxb = project_record_for_branch(record, "dubai")
    attend_dxb = next(k for k in proj_dxb.kpi_values if k.get("kpi_key") == "Attendance")
    assert round(attend_dxb["actual_value"], 2) == 0.49
    assert attend_dxb["achievement_ratio"] < 1.0
    assert proj_dxb.branch_key == "dubai"


def test_workspace_call_center_branch_partitioning():
    # Agent 1: Sharjah 19/25 = 76% (above target 65%), Dubai 259/528 = 49% (below)
    r1 = _make_outbound_record("EMP1", "Agent 1", 19, 25, 259, 528)
    # Agent 2: Sharjah 10/20 = 50% (below target 65%), Dubai 200/250 = 80% (above)
    r2 = _make_outbound_record("EMP2", "Agent 2", 10, 20, 200, 250)

    records = [r1, r2]
    repo = StubRepository(records)
    service = InsightsService(repo, PlanningService(repo))
    service._authorized_records = lambda _scope: (records, 0)
    scope = {"role": "Admin"}

    # 1. Unpartitioned
    ws_all = service.generate_workspace(scope, year=2026, month="September", team="Outbound")
    attend_all = next(k for k in ws_all.kpi_diagnosis if k.key == "Attendance")
    assert attend_all is not None

    # 2. Sharjah: Agent 1 is above (76%), Agent 2 is below (50%) -> 1 below target
    ws_shj = service.generate_workspace(scope, year=2026, month="September", team="Outbound", branch="sharjah")
    attend_shj = next(k for k in ws_shj.kpi_diagnosis if k.key == "Attendance")
    assert round(attend_shj.actual, 2) == round((0.76 + 0.50) / 2, 2)
    assert attend_shj.people_below_target == 1

    # 3. Dubai: Agent 1 is below (49%), Agent 2 is above (80%) -> 1 below target
    ws_dxb = service.generate_workspace(scope, year=2026, month="September", team="Outbound", branch="dubai")
    attend_dxb = next(k for k in ws_dxb.kpi_diagnosis if k.key == "Attendance")
    assert round(attend_dxb.actual, 2) == round((259 / 528 + 0.8) / 2, 2)
    assert attend_dxb.people_below_target == 1


def test_workspace_region_and_branch_coexistence():
    r1 = _make_outbound_record("EMP1", "Agent 1", 19, 25, 259, 528)
    records = [r1]
    repo = StubRepository(records)
    service = InsightsService(repo, PlanningService(repo))
    service._authorized_records = lambda _scope: (records, 0)
    scope = {"role": "Admin"}

    # When Region=UAE and Branch=sharjah, Outbound records (region="EGY") must not be discarded
    ws = service.generate_workspace(scope, year=2026, month="September", region="UAE", team="Outbound", branch="sharjah")
    assert "Outbound" in ws.options.teams
    attend = next((k for k in ws.kpi_diagnosis if k.key == "Attendance"), None)
    assert attend is not None
    assert attend.people_below_target == 0  # 76% is above target
