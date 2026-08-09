from types import SimpleNamespace
import uuid
import io

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.dependencies import get_current_user_scope, require_authenticated_scope, user_can_access_team_level
from config.loader import validate_team_config
from models.schemas import EvaluationData, PerformanceRecord
from models.models import Base, Team, User, UserTeamAssignment
from services.balanced_scorecard_service import BalancedScorecardService
from api.routers.performance import get_balanced_scorecard, upload_balanced_scorecard_template
from services.management_bsc_service import ManagementBSCSchemaError


PERSPECTIVES = [
    {"key": "Financial", "label": "Financial", "display_order": 1},
    {"key": "Customer", "label": "Customer", "display_order": 2},
    {"key": "Internal Process", "label": "Internal Process", "display_order": 3},
    {"key": "Learning & Growth", "label": "Learning & Growth", "display_order": 4},
]


def config():
    return {
        "team": "Test Team",
        "db_name": "Test Team",
        "region": "EGY",
        "employee_id_col": "EmployeeID",
        "employee_name_col": "EmployeeName",
        "grade_thresholds": {"A": 90, "B": 80, "C": 70, "D": 60},
        "balanced_scorecard": {
            "enabled": True,
            "perspectives": PERSPECTIVES,
            "strategy_map_links": [{"from": "Learning & Growth", "to": "Internal Process"}],
        },
        "kpis": [
            {"key": "revenue", "label": "Revenue", "perspective": "Financial", "weight": 0.5, "direction": "higher_better", "unit": "%", "color": "#111111", "actual_col": "A.Revenue", "target_col": "T.Revenue", "rollup": "average"},
            {"key": "cycle", "label": "Cycle Time", "perspective": "Internal Process", "weight": 0.3, "direction": "lower_better", "unit": "days", "color": "#222222", "actual_col": "A.Cycle", "target_col": "T.Cycle", "rollup": "average"},
            {"key": "satisfaction", "label": "Satisfaction", "perspective": "Customer", "weight": 0.2, "direction": "higher_better", "unit": "%", "color": "#333333", "actual_col": "A.Satisfaction", "target_col": "T.Satisfaction", "rollup": "average"},
        ],
    }


def record(employee_id, name, date, revenue_contribution, cycle_contribution, month="May"):
    return PerformanceRecord(
        id=f"{employee_id}_{date}",
        employee_id=employee_id,
        employee_name=name,
        team="Test Team",
        month=month,
        performance_level="Managerial",
        raw_data={"Date": f"{date}-05-01T00:00:00", "Position": "Test Manager"},
        evaluation=EvaluationData(score=80, grade="B"),
        kpi_values=[
            {"kpi_key": "revenue", "actual_value": 110, "target_value": 100, "achievement_ratio": 1.1, "weight_applied": 0.5, "contribution": revenue_contribution},
            {"kpi_key": "cycle", "actual_value": 4, "target_value": 5, "achievement_ratio": 1.25, "weight_applied": 0.3, "contribution": cycle_contribution},
        ],
    )


def test_aggregation_uses_contributions_and_preserves_raw_achievement():
    data = BalancedScorecardService.build(
        [record("1", "A", 2025, 0.5, 0.3), record("2", "B", 2025, 0.4, 0.15)],
        config(), "Test Team", "Managerial", "May", 2025,
    )

    assert data["scorecard"]["score"] == pytest.approx(84.375)
    assert data["scorecard"]["coverage"] == pytest.approx(0.8)
    revenue = next(row for row in data["kpi_table"] if row["kpi_key"] == "revenue")
    assert revenue["raw_achievement_ratio"] == pytest.approx(1.1)
    assert revenue["weighted_contribution"] == pytest.approx(0.45)
    assert revenue["score"] == pytest.approx(90)


def test_no_data_is_not_zero_and_employee_filter_is_applied():
    data = BalancedScorecardService.build(
        [record("1", "A", 2025, 0.5, 0.3), record("2", "B", 2025, 0.1, 0.1)],
        config(), "Test Team", "Managerial", "May", 2025, employee_ids=["1"],
    )

    satisfaction = next(row for row in data["kpi_table"] if row["kpi_key"] == "satisfaction")
    customer = next(row for row in data["perspectives"] if row["key"] == "Customer")
    learning = next(row for row in data["perspectives"] if row["key"] == "Learning & Growth")
    assert satisfaction["score"] is None and satisfaction["state"] == "no_data"
    assert customer["score"] is None and customer["state"] == "no_data"
    assert learning["score"] is None and learning["state"] == "not_configured"
    assert data["selection"]["people_count"] == 1
    assert [row["employee_id"] for row in data["contributors"]] == ["1"]


def test_year_is_explicit_and_history_ends_at_selected_period():
    data = BalancedScorecardService.build(
        [record("1", "A", 2025, 0.4, 0.2), record("1", "A", 2026, 0.5, 0.3)],
        config(), "Test Team", "Managerial", "May", 2025,
    )

    assert data["selection"]["year"] == 2025
    assert data["available_periods"] == [{"month": "May", "year": 2025}, {"month": "May", "year": 2026}]
    assert data["history"][-1]["year"] == 2025


def test_selected_kpi_contract_and_trends_use_real_period_records():
    data = BalancedScorecardService.build(
        [
            record("1", "A", 2025, 0.4, 0.2, month="April"),
            record("1", "A", 2025, 0.5, 0.3, month="May"),
        ],
        config(), "Test Team", "Managerial", "May", 2025,
        employee_ids=["1"], selected_kpi="revenue",
    )

    assert data["selected_kpi"]["key"] == "revenue"
    assert data["selected_kpi"]["label"] == "Revenue"
    assert [row["month"] for row in data["selected_kpi"]["history"]] == ["April", "May"]
    assert [row["score"] for row in data["selected_kpi"]["history"]] == [80.0, 100.0]
    assert data["perspectives"][0]["trend_vs_previous"] == pytest.approx(20.0)
    assert data["contributors"][0]["perspectives"]["Financial"]["trend"] == pytest.approx(20.0)
    assert data["contributors"][0]["perspectives"]["Financial"]["measured_weight"] == pytest.approx(0.5)
    assert data["contributors"][0]["perspectives"]["Financial"]["top_kpi_label"] == "Revenue"
    assert data["available_people"][0]["role"] == "Test Manager"


def test_selected_person_history_does_not_invent_other_people_periods():
    data = BalancedScorecardService.build(
        [
            record("2", "B", 2025, 0.4, 0.2, month="April"),
            record("1", "A", 2025, 0.5, 0.3, month="May"),
        ],
        config(), "Test Team", "Managerial", "May", 2025,
        employee_ids=["1"], selected_kpi="revenue",
    )

    assert [row["month"] for row in data["selected_kpi"]["history"]] == ["May"]


def test_available_people_only_contains_people_from_selected_period():
    data = BalancedScorecardService.build(
        [
            record("1", "Historical Manager", 2025, 0.4, 0.2, month="April"),
            record("2", "Current Manager", 2025, 0.5, 0.3, month="May"),
        ],
        config(), "Test Team", "Managerial", "All", 2025,
    )

    assert [row["employee_id"] for row in data["available_people"]] == ["2"]
    assert [row["employee_id"] for row in data["contributors"]] == ["2"]
    assert [row["month"] for row in data["history"]] == ["April", "May"]


def test_all_months_exposes_average_score_for_each_employee():
    data = BalancedScorecardService.build(
        [
            record("1", "A", 2025, 0.4, 0.2, month="April"),
            record("1", "A", 2025, 0.5, 0.3, month="May"),
        ],
        config(), "Test Team", "Managerial", "All", 2025,
    )

    # April is 75% and May is 100%; All Months exposes their measured average.
    assert data["contributors"][0]["overall_score"] == pytest.approx(87.5)
    assert data["scorecard"]["score"] == pytest.approx(87.5)
    assert next(row for row in data["kpi_table"] if row["kpi_key"] == "revenue")["score"] == pytest.approx(90.0)


def test_bsc_config_validation_rejects_unknown_perspective():
    raw = config()
    raw["performance_levels"] = {"Managerial": {"balanced_scorecard": raw.pop("balanced_scorecard"), "kpis": raw.pop("kpis")}}
    raw["kpis"] = [{"key": "legacy", "label": "Legacy", "weight": 1, "direction": "higher_better", "unit": "%", "color": "#000000", "actual_col": "a", "target_col": "t"}]
    raw["performance_levels"]["Managerial"]["kpis"][0]["perspective"] = "Unknown"

    valid, errors = validate_team_config(raw)
    assert valid is False
    assert any("invalid perspective" in error for error in errors)


def test_level_scope_rejects_legacy_and_cross_level_access(monkeypatch):
    assert user_can_access_team_level({"legacy_unscoped": True}, "Finance", "Managerial") is False
    scope = {
        "legacy_unscoped": False,
        "role": "Manager",
        "accessible_teams": ["Finance"],
        "accessible_team_levels": [("Finance", "Managerial")],
    }
    assert user_can_access_team_level(scope, "Finance", "Managerial") is True
    assert user_can_access_team_level(scope, "Finance", "Corporate") is False

    monkeypatch.setattr("api.dependencies.get_current_user_scope", lambda db, request: {"legacy_unscoped": True})
    with pytest.raises(HTTPException) as exc:
        require_authenticated_scope(None, SimpleNamespace())
    assert exc.value.status_code == 401


def test_endpoint_rejects_employee_before_reading_data():
    with pytest.raises(HTTPException) as exc:
        get_balanced_scorecard(
            request=SimpleNamespace(), db=None, team="Test Team", performance_level="Employee",
            month="May", year=2025, branch=None, employee_ids=[], history_months=6, selected_kpi=None,
        )
    assert exc.value.status_code == 422


def test_endpoint_rejects_people_outside_authorized_context(monkeypatch):
    monkeypatch.setattr("api.routers.performance.require_authenticated_scope", lambda db, request: {"legacy_unscoped": False})
    monkeypatch.setattr("api.routers.performance.user_can_access_team_level", lambda scope, team, level: True)
    monkeypatch.setattr("api.routers.performance.load_team_config", lambda team: {"team": team})
    monkeypatch.setattr("api.routers.performance.resolve_team_config", lambda raw, level: config())
    monkeypatch.setattr("api.routers.performance._get_dashboard_records", lambda *args, **kwargs: [record("1", "A", 2025, 0.5, 0.3)])
    monkeypatch.setattr("api.routers.performance.filter_records_by_scope", lambda records, scope: records)
    monkeypatch.setattr(
        "api.routers.performance.ManagementBSCService",
        lambda db: SimpleNamespace(
            build_scorecard_dataset=lambda **kwargs: {
                "available_people": [{"employee_id": "1", "employee_name": "A"}],
                "perspectives": [],
                "kpi_table": [],
                "history": [],
            }
        ),
    )

    with pytest.raises(HTTPException) as exc:
        get_balanced_scorecard(
            request=SimpleNamespace(), db=None, team="Test Team", performance_level="Managerial",
            month="May", year=2025, branch=None, employee_ids=["outside"], history_months=6, selected_kpi=None,
        )
    assert exc.value.status_code == 403


def test_endpoint_rejects_cross_employee_selection_for_self_scoped_user(monkeypatch):
    monkeypatch.setattr(
        "api.routers.performance.require_authenticated_scope",
        lambda db, request: {
            "legacy_unscoped": False,
            "role": "Executive",
            "employee_id": "1",
        },
    )
    monkeypatch.setattr("api.routers.performance.user_can_access_team_level", lambda scope, team, level: True)
    monkeypatch.setattr("api.routers.performance.load_team_config", lambda team: {"team": team})
    monkeypatch.setattr("api.routers.performance.resolve_team_config", lambda raw, level: config())
    monkeypatch.setattr("api.routers.performance._get_dashboard_records", lambda *args, **kwargs: [record("1", "A", 2025, 0.5, 0.3)])
    monkeypatch.setattr("api.routers.performance.filter_records_by_scope", lambda records, scope: records)

    with pytest.raises(HTTPException) as exc:
        get_balanced_scorecard(
            request=SimpleNamespace(), db=None, team="Test Team", performance_level="Corporate",
            month="May", year=2025, branch=None, employee_ids=["2"], history_months=6, selected_kpi=None,
        )

    assert exc.value.status_code == 403


def test_level_specific_access_to_all_teams_does_not_become_general_manager():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user = User(
        id=uuid.uuid4(), username="manager", email="manager@test.local",
        password_hash="x", role="Manager", is_active=True,
    )
    teams = [Team(id=uuid.uuid4(), name=name, db_name=name, region="EGY") for name in ("Finance", "Sales")]
    session.add_all([user, *teams])
    session.flush()
    session.add_all([
        UserTeamAssignment(
            id=uuid.uuid4(), user_id=user.id, team_id=team.id,
            performance_level="Managerial", access_level="read", assigned_by="Admin",
        )
        for team in teams
    ])
    session.commit()

    scope = get_current_user_scope(
        session,
        SimpleNamespace(state=SimpleNamespace(user={"user_id": str(user.id), "role": "Manager"})),
    )
    assert scope["is_general_manager"] is False
    assert user_can_access_team_level(scope, "Finance", "Managerial") is True
    assert user_can_access_team_level(scope, "Finance", "Corporate") is False
    session.close()


def test_endpoint_rejects_invalid_branch_filter(monkeypatch):
    monkeypatch.setattr("api.routers.performance.require_authenticated_scope", lambda db, request: {"legacy_unscoped": False})
    monkeypatch.setattr("api.routers.performance.user_can_access_team_level", lambda scope, team, level: True)
    monkeypatch.setattr("api.routers.performance.load_team_config", lambda team: {"team": team})
    monkeypatch.setattr("api.routers.performance.resolve_team_config", lambda raw, level: config())

    with pytest.raises(HTTPException) as exc:
        get_balanced_scorecard(
            request=SimpleNamespace(), db=None, team="Test Team", performance_level="Managerial",
            month="May", year=2025, branch="Dubai", employee_ids=[], history_months=6, selected_kpi=None,
        )

    assert exc.value.status_code == 422


def test_endpoint_surfaces_schema_mismatch_as_server_error(monkeypatch):
    monkeypatch.setattr("api.routers.performance.require_authenticated_scope", lambda db, request: {"legacy_unscoped": False})
    monkeypatch.setattr("api.routers.performance.user_can_access_team_level", lambda scope, team, level: True)
    monkeypatch.setattr("api.routers.performance.load_team_config", lambda team: {"team": team})
    monkeypatch.setattr("api.routers.performance.resolve_team_config", lambda raw, level: config())
    monkeypatch.setattr("api.routers.performance._get_dashboard_records", lambda *args, **kwargs: [])
    monkeypatch.setattr("api.routers.performance.filter_records_by_scope", lambda records, scope: records)
    monkeypatch.setattr(
        "api.routers.performance.ManagementBSCService",
        lambda db: SimpleNamespace(build_scorecard_dataset=lambda **kwargs: (_ for _ in ()).throw(
            ManagementBSCSchemaError("Management Overview database schema is out of date. Run backend migrations.")
        )),
    )

    with pytest.raises(HTTPException) as exc:
        get_balanced_scorecard(
            request=SimpleNamespace(), db=None, team="Test Team", performance_level="Managerial",
            month="May", year=2025, branch=None, employee_ids=[], history_months=6, selected_kpi=None,
        )

    assert exc.value.status_code == 500


class _RollbackOnlyDB:
    def __init__(self):
        self.rolled_back = False

    def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_upload_endpoint_returns_400_for_invalid_template(monkeypatch):
    db = _RollbackOnlyDB()
    monkeypatch.setattr("api.routers.performance.bsc_template_service.parse_upload", lambda contents: (_ for _ in ()).throw(ValueError("bad row")))

    file = UploadFile(filename="management.xlsx", file=io.BytesIO(b"PK\x03\x04invalid workbook body"))

    with pytest.raises(HTTPException) as exc:
        await upload_balanced_scorecard_template(db=db, file=file, _user={"username": "tester"})

    assert exc.value.status_code == 400
    assert db.rolled_back is True
