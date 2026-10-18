from __future__ import annotations

import pytest
from config.database import get_db
from services.insights_service import InsightsService
from services.planning_service import PlanningService
from services.dashboard_record_service import DashboardRecordService
from utils.branch_scope import project_record_for_branch


def test_project_record_for_branch_with_geo_data():
    db = next(get_db())
    repo = DashboardRecordService(db)
    records = repo.list_records(year=2026, month="September", team="Outbound")
    assert len(records) == 7

    # Find Abdelrahman
    abdelrahman = next(r for r in records if "Abdelrahman" in r.employee_name)
    # Sharjah: 19 attended / 25 bookings = 0.76 (target 0.65 -> above target)
    proj_shj = project_record_for_branch(abdelrahman, "sharjah")
    attend_kpi = next(k for k in proj_shj.kpi_values if k.get("kpi_key") == "Attendance")
    assert round(attend_kpi["actual_value"], 2) == 0.76
    assert attend_kpi["achievement_ratio"] > 1.0
    assert proj_shj.evaluation.score > abdelrahman.evaluation.score

    # Dubai: 259 attended / 528 bookings = 0.49 (target 0.65 -> below target)
    proj_dxb = project_record_for_branch(abdelrahman, "dubai")
    attend_kpi_dxb = next(k for k in proj_dxb.kpi_values if k.get("kpi_key") == "Attendance")
    assert round(attend_kpi_dxb["actual_value"], 2) == 0.49
    assert attend_kpi_dxb["achievement_ratio"] < 1.0


def test_workspace_call_center_branch_partitioning():
    db = next(get_db())
    repo = DashboardRecordService(db)
    service = InsightsService(repo, PlanningService(repo, db=db), db=db)
    scope = {"role": "Admin"}

    # 1. Unpartitioned Outbound
    ws_all = service.generate_workspace(scope, year=2026, month="September", team="Outbound")
    attend_all = next(k for k in ws_all.kpi_diagnosis if k.key == "Attendance")
    assert round(attend_all.actual, 3) == 0.566
    assert attend_all.people_below_target == 6

    # 2. Sharjah Outbound
    ws_shj = service.generate_workspace(scope, year=2026, month="September", team="Outbound", branch="sharjah")
    attend_shj = next(k for k in ws_shj.kpi_diagnosis if k.key == "Attendance")
    # In Sharjah, actual attendance is ~73.3%, and only 2 people are below target
    assert attend_shj.actual > 0.70
    assert attend_shj.people_below_target == 2

    # 3. Dubai Outbound
    ws_dxb = service.generate_workspace(scope, year=2026, month="September", team="Outbound", branch="dubai")
    attend_dxb = next(k for k in ws_dxb.kpi_diagnosis if k.key == "Attendance")
    assert round(attend_dxb.actual, 2) == 0.57
    assert attend_dxb.people_below_target == 6

    # 4. Ajman Outbound
    ws_ajm = service.generate_workspace(scope, year=2026, month="September", team="Outbound", branch="ajman")
    attend_ajm = next(k for k in ws_ajm.kpi_diagnosis if k.key == "Attendance")
    assert round(attend_ajm.actual, 2) == 0.54
    assert attend_ajm.people_below_target == 7


def test_workspace_region_and_branch_coexistence():
    db = next(get_db())
    repo = DashboardRecordService(db)
    service = InsightsService(repo, PlanningService(repo, db=db), db=db)
    scope = {"role": "Admin"}

    # When Region=UAE and Branch=sharjah, Outbound call center records must not be discarded
    ws = service.generate_workspace(scope, year=2026, month="September", region="UAE", team="Outbound", branch="sharjah")
    assert "Outbound" in ws.options.teams
    attend = next((k for k in ws.kpi_diagnosis if k.key == "Attendance"), None)
    assert attend is not None
    assert attend.people_below_target == 2
