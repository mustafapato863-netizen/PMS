import uuid

import pytest
from sqlalchemy.exc import ProgrammingError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.models import Base, Team
from services.management_bsc_service import ManagementBSCService, ManagementBSCSchemaError, _highest_position


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _base_config():
    return {
        "grade_thresholds": {"A": 90, "B": 80, "C": 70, "D": 60},
        "balanced_scorecard": {
            "enabled": True,
            "perspectives": [
                {"key": "Financial", "label": "Financial", "display_order": 1},
                {"key": "Customer", "label": "Customer", "display_order": 2},
                {"key": "Internal Process", "label": "Internal Process", "display_order": 3},
                {"key": "Learning & Growth", "label": "Learning & Growth", "display_order": 4},
            ],
            "strategy_map_links": [],
        },
    }


def _seed_team(session, name="Sales"):
    team = Team(id=uuid.uuid4(), name=name, db_name=name, region="EGY")
    session.add(team)
    session.commit()
    return team


def test_highest_position_uses_org_seniority():
    assert _highest_position({"Account Manager", "Finance Manager", "Sales Director"}) == "Sales Director"


def test_employee_override_beats_position_config():
    session = _db()
    _seed_team(session, "Sales")
    service = ManagementBSCService(session)
    rows = [
        {
            "employee_id": "EMP-1",
            "team": "Sales",
            "employee_name": "One",
            "position": "Sales Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Financial",
            "kpi_label": "Revenue Achievement",
            "direction": "higher_better",
            "weight": 0.5,
            "target_value": 100.0,
            "target_unit": "%",
            "actual_value": 100.0,
        },
        {
            "employee_id": "EMP-2",
            "team": "Sales",
            "employee_name": "Two",
            "position": "Sales Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Financial",
            "kpi_label": "Revenue Achievement",
            "direction": "higher_better",
            "weight": 0.5,
            "target_value": 100.0,
            "target_unit": "%",
            "actual_value": 100.0,
        },
        {
            "employee_id": "EMP-3",
            "team": "Sales",
            "employee_name": "Three",
            "position": "Sales Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Financial",
            "kpi_label": "Revenue Achievement",
            "direction": "higher_better",
            "weight": 0.5,
            "target_value": 50.0,
            "target_unit": "%",
            "actual_value": 100.0,
        },
    ]

    result = service.import_template_rows(rows=rows, updated_by="tester")
    data = service.build_scorecard_dataset(
        team_name="Sales",
        performance_level="Managerial",
        month="May",
        year=2025,
        employee_ids=["EMP-3"],
        history_months=6,
        selected_kpi="revenue_achievement",
        base_config=_base_config(),
    )

    revenue = next(row for row in data["kpi_table"] if row["kpi_key"] == "revenue_achievement")
    assert result["config_rows"] == 2
    assert revenue["score"] == 200.0
    assert data["team"]["top_position"] == "Sales Manager"
    assert data["selection"]["config_scope_summary"]["employee_overrides"] == 1
    session.close()


def test_partial_employee_override_keeps_other_position_kpis():
    session = _db()
    _seed_team(session, "Sales")
    service = ManagementBSCService(session)
    rows = []
    for employee_id in ("EMP-1", "EMP-2", "EMP-3"):
        for perspective, label, weight, target, actual in (
            ("Financial", "Revenue Achievement", 0.6, 100.0, 100.0),
            ("Learning & Growth", "Coaching Completion", 0.4, 100.0, 90.0),
        ):
            rows.append({
                "employee_id": employee_id,
                "team": "Sales",
                "employee_name": employee_id,
                "position": "Sales Manager",
                "performance_level": "Managerial",
                "month": "May",
                "year": 2025,
                "perspective": perspective,
                "kpi_label": label,
                "direction": "higher_better",
                "weight": weight,
                "target_value": 50.0 if employee_id == "EMP-3" and label == "Revenue Achievement" else target,
                "target_unit": "%",
                "actual_value": actual,
            })

    result = service.import_template_rows(rows=rows, updated_by="tester")
    data = service.build_scorecard_dataset(
        team_name="Sales",
        performance_level="Managerial",
        month="May",
        year=2025,
        employee_ids=["EMP-3"],
        history_months=6,
        selected_kpi="revenue_achievement",
        base_config=_base_config(),
    )

    kpis = {row["kpi_key"]: row for row in data["kpi_table"]}
    assert result["config_rows"] == 3
    assert set(kpis) == {"revenue_achievement", "coaching_completion"}
    assert kpis["revenue_achievement"]["score"] == 200.0
    assert kpis["coaching_completion"]["score"] == 90.0
    assert data["scorecard"]["coverage"] == 1.0
    session.close()


def test_historical_month_uses_exact_period_config():
    session = _db()
    _seed_team(session, "Sales")
    service = ManagementBSCService(session)
    rows = [
        {
            "employee_id": "EMP-1",
            "team": "Sales",
            "employee_name": "One",
            "position": "Sales Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Financial",
            "kpi_label": "Revenue Achievement",
            "direction": "higher_better",
            "weight": 0.5,
            "target_value": 100.0,
            "target_unit": "%",
            "actual_value": 100.0,
        },
        {
            "employee_id": "EMP-1",
            "team": "Sales",
            "employee_name": "One",
            "position": "Sales Manager",
            "performance_level": "Managerial",
            "month": "June",
            "year": 2025,
            "perspective": "Financial",
            "kpi_label": "Revenue Achievement",
            "direction": "higher_better",
            "weight": 0.5,
            "target_value": 50.0,
            "target_unit": "%",
            "actual_value": 100.0,
        },
    ]

    service.import_template_rows(rows=rows, updated_by="tester")

    may_data = service.build_scorecard_dataset(
        team_name="Sales",
        performance_level="Managerial",
        month="May",
        year=2025,
        employee_ids=["EMP-1"],
        history_months=6,
        selected_kpi="revenue_achievement",
        base_config=_base_config(),
    )
    june_data = service.build_scorecard_dataset(
        team_name="Sales",
        performance_level="Managerial",
        month="June",
        year=2025,
        employee_ids=["EMP-1"],
        history_months=6,
        selected_kpi="revenue_achievement",
        base_config=_base_config(),
    )

    may_score = next(row for row in may_data["kpi_table"] if row["kpi_key"] == "revenue_achievement")["score"]
    june_score = next(row for row in june_data["kpi_table"] if row["kpi_key"] == "revenue_achievement")["score"]
    assert may_score == 100.0
    assert june_score == 200.0
    assert may_data["selection"]["effective_month"] == "May"
    assert june_data["selection"]["effective_month"] == "June"
    session.close()


def test_all_months_honors_explicit_year():
    session = _db()
    _seed_team(session, "Sales")
    service = ManagementBSCService(session)
    rows = [
        {
            "employee_id": "EMP-1",
            "team": "Sales",
            "employee_name": "One",
            "position": "Sales Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": year,
            "perspective": "Financial",
            "kpi_label": "Revenue Achievement",
            "direction": "higher_better",
            "weight": 1.0,
            "target_value": 100.0,
            "target_unit": "%",
            "actual_value": actual,
        }
        for year, actual in ((2025, 90.0), (2026, 110.0))
    ]
    service.import_template_rows(rows=rows, updated_by="tester")

    data = service.build_scorecard_dataset(
        team_name="Sales",
        performance_level="Managerial",
        month="All",
        year=2025,
        employee_ids=["EMP-1"],
        history_months=6,
        selected_kpi="revenue_achievement",
        base_config=_base_config(),
    )

    assert data["selection"]["year"] == 2025
    assert data["scorecard"]["score"] == 90.0
    assert data["available_periods"] == [
        {"month": "May", "year": 2025},
        {"month": "May", "year": 2026},
    ]
    session.close()


def test_each_period_uses_its_own_kpi_configuration():
    session = _db()
    _seed_team(session, "Sales")
    service = ManagementBSCService(session)
    rows = [
        {
            "employee_id": "EMP-1",
            "team": "Sales",
            "employee_name": "One",
            "position": "Sales Manager",
            "performance_level": "Managerial",
            "month": month,
            "year": 2025,
            "perspective": perspective,
            "kpi_label": label,
            "direction": "higher_better",
            "weight": 1.0,
            "target_value": 100.0,
            "target_unit": "%",
            "actual_value": actual,
        }
        for month, perspective, label, actual in (
            ("April", "Financial", "Revenue Achievement", 100.0),
            ("May", "Learning & Growth", "Coaching Completion", 90.0),
        )
    ]
    service.import_template_rows(rows=rows, updated_by="tester")

    data = service.build_scorecard_dataset(
        team_name="Sales",
        performance_level="Managerial",
        month="All",
        year=2025,
        employee_ids=["EMP-1"],
        history_months=6,
        selected_kpi="coaching_completion",
        base_config=_base_config(),
    )

    assert [row["kpi_key"] for row in data["kpi_table"]] == ["coaching_completion"]
    assert [(row["month"], row["score"]) for row in data["history"]] == [
        ("April", 100.0),
        ("May", 90.0),
    ]
    assert [row["month"] for row in data["selected_kpi"]["history"]] == ["May"]
    session.close()


def test_missing_management_config_returns_real_empty_response():
    session = _db()
    _seed_team(session, "Sales")
    data = ManagementBSCService(session).build_scorecard_dataset(
        team_name="Sales",
        performance_level="Managerial",
        month="May",
        year=2025,
        employee_ids=[],
        history_months=6,
        selected_kpi=None,
        base_config=_base_config(),
    )

    assert data["kpi_table"] == []
    assert data["perspectives"] == []
    assert data["selection"]["data_source"] == "database_config"
    session.close()


def test_import_template_rows_groups_by_team_column():
    session = _db()
    _seed_team(session, "Sales")
    _seed_team(session, "CSR")
    service = ManagementBSCService(session)
    rows = [
        {
            "employee_id": "EMP-1",
            "team": "Sales",
            "employee_name": "One",
            "position": "Sales Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Financial",
            "kpi_label": "Revenue Achievement",
            "direction": "higher_better",
            "weight": 0.5,
            "target_value": 100.0,
            "target_unit": "%",
            "actual_value": 100.0,
        },
        {
            "employee_id": "EMP-2",
            "team": "CSR",
            "employee_name": "Two",
            "position": "CSR Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Customer",
            "kpi_label": "CSAT",
            "direction": "higher_better",
            "weight": 0.5,
            "target_value": 90.0,
            "target_unit": "%",
            "actual_value": 91.0,
        },
    ]

    result = service.import_template_rows(rows=rows, updated_by="tester")

    assert result["teams"] == ["CSR", "Sales"]
    sales_data = service.build_scorecard_dataset(
        team_name="Sales",
        performance_level="Managerial",
        month="May",
        year=2025,
        employee_ids=["EMP-1"],
        history_months=6,
        selected_kpi="revenue_achievement",
        base_config=_base_config(),
    )
    csr_data = service.build_scorecard_dataset(
        team_name="CSR",
        performance_level="Managerial",
        month="May",
        year=2025,
        employee_ids=["EMP-2"],
        history_months=6,
        selected_kpi="csat",
        base_config=_base_config(),
    )

    assert sales_data["kpi_table"][0]["kpi_key"] == "revenue_achievement"
    assert csr_data["kpi_table"][0]["kpi_key"] == "csat"
    session.close()


def test_import_template_rows_creates_missing_team_from_template():
    session = _db()
    service = ManagementBSCService(session)
    rows = [
        {
            "employee_id": "EMP-1",
            "team": "Call Center",
            "employee_name": "One",
            "position": "Call Center Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Customer",
            "kpi_label": "CSAT",
            "direction": "higher_better",
            "weight": 1.0,
            "target_value": 90.0,
            "target_unit": "%",
            "actual_value": 91.0,
        },
    ]

    result = service.import_template_rows(rows=rows, updated_by="tester")

    assert result["teams"] == ["Call Center"]
    team = (
        session.query(Team)
        .filter(
            Team.display_name == "Call Center",
            Team.team_level == "management",
        )
        .one()
    )
    assert team.name == "call_center_management"
    assert team.db_name == "call_center_management"
    session.close()


def test_analysis_records_reuse_management_snapshot_configuration():
    session = _db()
    _seed_team(session, "Sales")
    service = ManagementBSCService(session)
    service.import_template_rows(rows=[{
        "employee_id": "MGR-1",
        "team": "Sales",
        "employee_name": "Manager One",
        "position": "Sales Manager",
        "performance_level": "Managerial",
        "month": "June",
        "year": 2026,
        "perspective": "Financial",
        "kpi_label": "Revenue Achievement",
        "direction": "higher_better",
        "weight": 1.0,
        "target_value": 100.0,
        "target_unit": "%",
        "actual_value": 90.0,
    }], updated_by="tester")

    records = service.list_analysis_records()

    record = next(item for item in records if item["employee_id"] == "MGR-1")
    assert record["team"] == "Sales"
    assert record["performance_level"] == "Managerial"
    assert record["evaluation"]["score"] == 90.0
    assert record["kpi_values"][0] | {
        "label": "Revenue Achievement",
        "direction": "higher_better",
        "unit": "%",
    } == record["kpi_values"][0]
    session.close()


def test_management_import_creates_distinct_identity_for_existing_employee_team():
    session = _db()
    employee_team = _seed_team(session, "Marketing")
    service = ManagementBSCService(session)
    rows = [
        {
            "employee_id": "EMP-1",
            "team": "Marketing",
            "employee_name": "One",
            "position": "Marketing Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Customer",
            "kpi_label": "Campaign Quality",
            "direction": "higher_better",
            "weight": 1.0,
            "target_value": 90.0,
            "target_unit": "%",
            "actual_value": 91.0,
        },
    ]

    service.import_template_rows(rows=rows, updated_by="tester")

    management_team = (
        session.query(Team)
        .filter(
            Team.display_name == "Marketing",
            Team.team_level == "management",
        )
        .one()
    )
    assert management_team.id != employee_team.id
    assert management_team.name == "marketing_management"
    assert management_team.db_name == "marketing_management"
    assert management_team.display_name == employee_team.name

    data = service.build_scorecard_dataset(
        team_name="Marketing",
        performance_level="Managerial",
        month="May",
        year=2025,
        employee_ids=["EMP-1"],
        history_months=6,
        selected_kpi=None,
        base_config=_base_config(),
    )
    assert data["team"]["id"] == str(management_team.id)
    assert data["team"]["team_level"] == "management"
    session.close()


def test_management_import_rolls_back_new_scoped_identity_on_failure(monkeypatch):
    session = _db()
    service = ManagementBSCService(session)

    def fail_payload(_rows):
        raise ValueError("invalid management payload")

    monkeypatch.setattr(service, "_build_database_payload", fail_payload)

    with pytest.raises(ValueError, match="invalid management payload"):
        service.import_template_rows(
            rows=[{"team": "New Management Team"}],
            updated_by="tester",
        )

    assert (
        session.query(Team)
        .filter(
            Team.display_name == "New Management Team",
            Team.team_level == "management",
        )
        .count()
        == 0
    )
    session.close()


def test_delete_upload_batch_removes_management_rows():
    session = _db()
    service = ManagementBSCService(session)
    rows = [
        {
            "employee_id": "EMP-1",
            "team": "Call Center",
            "employee_name": "One",
            "position": "Call Center Manager",
            "performance_level": "Managerial",
            "month": "May",
            "year": 2025,
            "perspective": "Customer",
            "kpi_label": "CSAT",
            "direction": "higher_better",
            "weight": 1.0,
            "target_value": 90.0,
            "target_unit": "%",
            "actual_value": 91.0,
        },
    ]

    result = service.import_template_rows(rows=rows, updated_by="tester", source_filename="dummy.xlsx")
    deleted = service.delete_upload_batch(result["upload_batch_id"])

    assert deleted["config_rows_deleted"] > 0
    assert deleted["snapshot_rows_deleted"] > 0
    assert service.list_upload_batches() == []
    session.close()


def test_list_upload_batches_and_history_return_empty_when_no_rows_exist():
    session = _db()
    _seed_team(session, "Sales")
    service = ManagementBSCService(session)

    assert service.list_upload_batches() == []
    assert service.list_history(team_name="Sales") == []
    session.close()


def test_schema_mismatch_raises_explicit_management_bsc_error(monkeypatch):
    session = _db()
    service = ManagementBSCService(session)

    def _broken_query(*args, **kwargs):
        raise ProgrammingError("SELECT 1", {}, Exception("UndefinedTable: management_kpi_snapshots does not exist"))

    monkeypatch.setattr(session, "query", _broken_query)

    with pytest.raises(ManagementBSCSchemaError) as exc:
        service.list_upload_batches()

    assert "schema is out of date" in str(exc.value)
    session.close()
