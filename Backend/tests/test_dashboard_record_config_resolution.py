from types import SimpleNamespace

from services import dashboard_record_service as module


def test_dashboard_records_resolve_each_config_scope_once(monkeypatch):
    calls = []
    team = SimpleNamespace(display_name="Coding", name="Coding", db_name="Coding")
    employee = SimpleNamespace(
        employee_id="E-1",
        name="Employee",
        team=team,
        position_name="Coder",
        region="EGY",
    )
    records = [
        SimpleNamespace(
            id=f"record-{index}",
            employee=employee,
            team=team,
            performance_level="Employee",
            position_name="Coder",
            kpi_values=[],
            record_payload=None,
            month="June",
            year=2026,
            region="EGY",
            status="Active",
            upload_id=None,
            score=90,
            grade="B",
        )
        for index in range(3)
    ]

    class Repository:
        def __init__(self, db, model):
            pass

        def get_dashboard_records(self, **filters):
            return records

    monkeypatch.setattr(
        module,
        "load_team_config",
        lambda team_name: calls.append(team_name) or {"team": team_name},
    )
    monkeypatch.setattr(
        module,
        "resolve_team_config",
        lambda config, level, position: {"kpis": []},
    )
    monkeypatch.setattr(
        module,
        "SchemaPerformanceRecord",
        lambda **values: values,
    )

    result = module.DashboardRecordService(object(), sql_repository_cls=Repository).list_records()

    assert len(result) == 3
    assert calls == ["Coding"]
