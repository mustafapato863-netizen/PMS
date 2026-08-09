import io

import pandas as pd
from starlette.requests import Request

from api.routers import performance as performance_router
from exports.report_exporter import ReportExporter
from models.schemas import EvaluationData, PerformanceRecord


def _marketing_record() -> PerformanceRecord:
    return PerformanceRecord(
        id="SGHD70001_2026_June",
        employee_id="SGHD70001",
        employee_name="Marketing Employee",
        team="Marketing",
        position="Media Buyer",
        region="EGY",
        performance_level="Employee",
        year=2026,
        month="June",
        status="Meets",
        evaluation=EvaluationData(score=93.5, grade="B"),
        kpi_values=[
            {
                "kpi_key": "mb_cpl",
                "label": "CPL",
                "actual_value": 80,
                "target_value": 100,
                "achievement_ratio": 1.25,
                "contribution": 0.1,
            }
        ],
    )


def test_marketing_excel_export_contains_dimensions_and_kpi_values():
    payload = ReportExporter.export_to_excel([_marketing_record()])
    frame = pd.read_excel(io.BytesIO(payload), sheet_name="Performance Summary")

    assert frame.loc[0, "Position"] == "Media Buyer"
    assert frame.loc[0, "Region"] == "EGY"
    assert frame.loc[0, "Year"] == 2026
    assert frame.loc[0, "Status"] == "Meets"
    assert frame.loc[0, "CPL Achievement (%)"] == 100
    assert frame.loc[0, "CPL Contribution (%)"] == 10


def test_export_route_passes_marketing_filters_and_builds_stable_filename(monkeypatch):
    captured = {}
    record = _marketing_record()

    def fake_get_records(_db, **filters):
        captured.update(filters)
        return [record]

    monkeypatch.setattr(performance_router, "_get_dashboard_records", fake_get_records)
    monkeypatch.setattr(performance_router, "get_current_user_scope", lambda _db, _request: {"role": "Admin"})
    monkeypatch.setattr(performance_router, "filter_records_by_scope", lambda records, _scope: records)
    monkeypatch.setattr(performance_router, "user_can_access_team", lambda _scope, _team: True)

    request = Request({"type": "http", "headers": []})
    response = performance_router.export_report(
        request=request,
        db=object(),
        month="June",
        team="Marketing",
        format="excel",
        performance_level="Employee",
        year=2026,
        position="Media Buyer",
        region="EGY",
        role="Admin",
    )

    assert captured == {
        "team": "Marketing",
        "month": "June",
        "performance_level": "Employee",
        "year": 2026,
        "position": "Media Buyer",
        "region": "EGY",
    }
    assert response.headers["content-disposition"] == (
        "attachment; filename=Marketing_Media_Buyer_2026_June.xlsx"
    )


def test_export_route_preserves_legacy_filename_for_other_teams(monkeypatch):
    monkeypatch.setattr(performance_router, "_get_dashboard_records", lambda _db, **_filters: [])
    monkeypatch.setattr(performance_router, "get_current_user_scope", lambda _db, _request: {"role": "Admin"})
    monkeypatch.setattr(performance_router, "filter_records_by_scope", lambda records, _scope: records)
    monkeypatch.setattr(performance_router, "user_can_access_team", lambda _scope, _team: True)

    response = performance_router.export_report(
        request=Request({"type": "http", "headers": []}),
        db=object(),
        month="June",
        team="Inbound",
        format="excel",
        performance_level="Employee",
        year=None,
        position=None,
        region=None,
        role="Admin",
    )

    assert response.headers["content-disposition"] == (
        "attachment; filename=PMS_Report_June_Inbound.xlsx"
    )
