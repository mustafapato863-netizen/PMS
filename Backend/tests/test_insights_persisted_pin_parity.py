"""Insights must keep a server-pinned KPI that the static file does not define.

Outbound's technical file has Attendance at weight 0.70 and no Productivity.
August's trusted monthly pin adds Productivity at weight 0.10 and keeps
Attendance at weight 0.60, both with the workbook attendance target 0.65.
A pin counts only when ``evaluation_pinned`` is exactly ``True``.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import (
    Employee,
    EmployeeUploadBatch,
    EvaluationRevision,
    EvaluationScope,
    KPIValue,
    ManagementKPIConfig,
    ManagementKPISnapshot,
    PerformanceRecord,
    Team,
    TeamConfigurationVersion,
    TeamKPIConfig,
    UploadLog,
    User,
)
from models.schemas import EvaluationData
from models.schemas import PerformanceRecord as SchemaRecord
from services.dashboard_record_service import DashboardRecordService
from services.evaluation.access import EvaluationError
from services.evaluation.workflow import EvaluationWorkflow
from services.insights_service import InsightsService, _configured_kpi_values
from services.planning_service import PlanningService
from tests.test_evaluation_workflow_consumer import (
    _World,
    _approve,
    _raw,
)
from tests.test_outbound_productivity_ingestion import AUGUST, JULY


ATTENDANCE_FILE_AGGREGATION = {
    "method": "ratio",
    "numerator_col": "$geo.attended",
    "denominator_col": "$geo.bookings",
}
PRODUCTIVITY_ACTUAL = AUGUST["Productivity"]
PRODUCTIVITY_CONTRIBUTION = (PRODUCTIVITY_ACTUAL / 0.8) * 0.1


def _admin_scope() -> dict:
    return {
        "role": "Admin",
        "has_unrestricted_team_access": True,
        "legacy_unscoped": False,
        "accessible_teams": [],
        "accessible_team_levels": [],
        "accessible_functions": [],
        "accessible_regions": [],
        "accessible_branches": [],
        "employee_id": "",
    }


def _manager_scope(team: str) -> dict:
    return {
        "role": "Manager",
        "has_unrestricted_team_access": False,
        "legacy_unscoped": False,
        "accessible_teams": [team],
        "accessible_team_levels": [],
        "accessible_functions": [],
        "accessible_regions": [],
        "accessible_branches": [],
        "employee_id": "",
    }


def _employee_scope(employee_id: str) -> dict:
    return {
        "role": "Employee",
        "has_unrestricted_team_access": False,
        "legacy_unscoped": False,
        "accessible_teams": [],
        "accessible_team_levels": [],
        "accessible_functions": [],
        "accessible_regions": [],
        "accessible_branches": [],
        "employee_id": employee_id,
    }


class _Repo:
    def get_all(self):
        return []


def _service(records):
    repository = _Repo()
    service = InsightsService(repository, PlanningService(repository))
    service._authorized_records = lambda _scope: (records, 0)
    return service


def _db_service(db):
    repository = _Repo()
    return InsightsService(
        repository,
        PlanningService(repository),
        db=db,
        record_service=DashboardRecordService(db),
    )


def _option_keys(workspace) -> set[str]:
    return {item["key"] for item in workspace.options.kpis}


def _analyses(workspace, key: str) -> list:
    return [item for item in workspace.team_analyses if item.kpi_key == key]


def _weight_text(item) -> str:
    return next(evidence.value for evidence in item.detail.evidence if evidence.label == "Applied KPI weight")


def _record(month: str, kpis: list, *, employee_id: str = "E1", score: float = 80.0) -> SchemaRecord:
    return SchemaRecord(
        id=f"{employee_id}_Outbound_2026_{month}",
        employee_id=employee_id,
        employee_name=employee_id,
        team="Outbound",
        month=month,
        year=2026,
        region="EGY",
        position="Agent",
        performance_level="Employee",
        status="Meets",
        evaluation=EvaluationData(score=score, grade="C"),
        kpi_values=kpis,
    )


def _attendance(actual: float, target: float, weight: float, direction: str, **extra) -> dict:
    row = {
        "kpi_key": "Attendance",
        "label": "Attendance Rate",
        "unit": "%",
        "direction": direction,
        "actual_value": actual,
        "target_value": target,
        "weight_applied": weight,
        "achievement_ratio": 1.2,
        "contribution": 0.72,
    }
    row.update(extra)
    return row


def _productivity(**extra) -> dict:
    row = {
        "kpi_key": "Productivity",
        "label": "Productivity",
        "unit": "%",
        "direction": "higher_better",
        "actual_value": PRODUCTIVITY_ACTUAL,
        "target_value": 0.8,
        "weight_applied": 0.1,
        "achievement_ratio": PRODUCTIVITY_ACTUAL / 0.8,
        "contribution": PRODUCTIVITY_CONTRIBUTION,
    }
    row.update(extra)
    return row


def test_exact_true_pin_keeps_unknown_productivity_and_edited_attendance_values():
    record = _record("August", [
        _attendance(0.46, 0.70, 0.50, "lower_better", evaluation_pinned=True),
        _productivity(evaluation_pinned=True),
    ])

    values = {item["kpi_key"]: item for item in _configured_kpi_values(record)}

    productivity = values["Productivity"]
    assert productivity["actual_value"] == PRODUCTIVITY_ACTUAL
    assert productivity["target_value"] == 0.8
    assert productivity["weight_applied"] == 0.1
    assert productivity["direction"] == "higher_better"
    assert productivity["unit"] == "%"
    assert productivity["achievement_ratio"] == PRODUCTIVITY_ACTUAL / 0.8
    assert productivity["contribution"] == PRODUCTIVITY_CONTRIBUTION
    assert productivity.get("aggregation") != ATTENDANCE_FILE_AGGREGATION

    attendance = values["Attendance"]
    assert attendance["target_value"] == 0.70
    assert attendance["weight_applied"] == 0.50
    assert attendance["direction"] == "lower_better"
    assert attendance["achievement_ratio"] == 1.2
    assert attendance["contribution"] == 0.72
    assert attendance.get("aggregation") != ATTENDANCE_FILE_AGGREGATION


@pytest.mark.parametrize("flag", ["true", "True", 1, {"pinned": True}, object()])
def test_malformed_pin_does_not_keep_an_unknown_kpi_or_override_a_known_one(flag):
    record = _record("August", [
        _attendance(0.46, 0.70, 0.50, "lower_better", evaluation_pinned=flag),
        _productivity(evaluation_pinned=flag),
    ])

    values = {item["kpi_key"]: item for item in _configured_kpi_values(record)}

    assert "Productivity" not in values
    attendance = values["Attendance"]
    assert attendance["direction"] == "higher_better"
    assert attendance["contribution"] == pytest.approx(0.50)
    assert attendance["weight_applied"] == pytest.approx(0.50)


def test_unpinned_unknown_kpi_stays_excluded_and_file_aggregation_stays_on_legacy_rows():
    record = _record("August", [
        _attendance(0.40, 0.50, 0.60, "higher_better"),
        _productivity(),
    ], employee_id="E1")
    other = _record("August", [
        _attendance(0.80, 1.50, 0.60, "higher_better"),
    ], employee_id="E2")

    assert "Productivity" not in {item["kpi_key"] for item in _configured_kpi_values(record)}
    workspace = _service([record, other]).generate_workspace(_admin_scope(), month="August", year=2026, kpi="Attendance")
    attendance = _analyses(workspace, "Attendance")
    assert len(attendance) == 1
    assert attendance[0].detail.current_value == pytest.approx(0.60)


def test_object_shaped_pin_matches_dict_pin_and_raw_rows_do_not_inherit_a_parent_claim():
    pinned = SimpleNamespace(
        kpi_key="Productivity",
        label="Productivity",
        unit="%",
        direction="higher_better",
        actual_value=PRODUCTIVITY_ACTUAL,
        target_value=0.8,
        weight_applied=0.1,
        achievement_ratio=PRODUCTIVITY_ACTUAL / 0.8,
        contribution=PRODUCTIVITY_CONTRIBUTION,
        evaluation_pinned=True,
    )
    attendance = SimpleNamespace(
        kpi_key="Attendance",
        label="Attendance Rate",
        unit="%",
        direction="lower_better",
        actual_value=0.46,
        target_value=0.70,
        weight_applied=0.50,
        achievement_ratio=1.2,
        contribution=0.72,
        evaluation_pinned=True,
    )

    def row(kpi_values):
        return SimpleNamespace(
            team="Outbound",
            month="August",
            year=2026,
            performance_level="Employee",
            position="Agent",
            employee_id="E1",
            employee_name="E1",
            region="EGY",
            status="Meets",
            evaluation=SimpleNamespace(score=79.82, grade="C"),
            raw_data={},
            kpi_values=kpi_values,
        )

    object_workspace = _service([row([pinned, attendance])]).generate_workspace(
        _admin_scope(), month="August", year=2026, kpi="Attendance",
    )
    dict_workspace = _service([
        _record("August", [
            _attendance(0.46, 0.70, 0.50, "lower_better", evaluation_pinned=True),
            _productivity(evaluation_pinned=True),
        ]),
    ]).generate_workspace(_admin_scope(), month="August", year=2026, kpi="Attendance")

    assert "Productivity" in _option_keys(object_workspace)
    assert "Productivity" in _option_keys(dict_workspace)
    object_attendance = _analyses(object_workspace, "Attendance")[0]
    dict_attendance = _analyses(dict_workspace, "Attendance")[0]
    assert object_attendance.detail.direction == "lower_better"
    assert dict_attendance.detail.direction == "lower_better"
    assert object_attendance.detail.target_value == pytest.approx(0.70)
    assert dict_attendance.detail.target_value == pytest.approx(0.70)
    assert _weight_text(object_attendance) == "50.0%"
    assert _weight_text(dict_attendance) == "50.0%"

    raw_parent_claim = row([
        SimpleNamespace(
            kpi_key="Productivity",
            label="Productivity",
            unit="%",
            direction="higher_better",
            actual_value=PRODUCTIVITY_ACTUAL,
            target_value=0.8,
            weight_applied=0.1,
            achievement_ratio=PRODUCTIVITY_ACTUAL / 0.8,
            contribution=PRODUCTIVITY_CONTRIBUTION,
        ),
    ])
    raw_parent_claim.evaluation_basis = {"pinned": True}
    raw_workspace = _service([raw_parent_claim]).generate_workspace(
        _admin_scope(), month="August", year=2026,
    )
    assert "Productivity" not in _option_keys(raw_workspace)


def test_pinned_cohort_keeps_its_own_direction_unit_and_does_not_use_the_file_ratio_rollup():
    pinned_low = _record("August", [
        _attendance(0.40, 0.50, 0.60, "higher_better", evaluation_pinned=True, contribution=0.40),
    ], employee_id="E1")
    pinned_high = _record("August", [
        _attendance(0.80, 1.50, 0.60, "higher_better", evaluation_pinned=True, contribution=0.32),
    ], employee_id="E2")
    workspace = _service([pinned_low, pinned_high]).generate_workspace(
        _admin_scope(), month="August", year=2026, kpi="Attendance",
    )
    attendance = _analyses(workspace, "Attendance")
    assert len(attendance) == 1
    assert attendance[0].detail.current_value == pytest.approx(0.70)

    higher = _record("August", [
        _attendance(0.40, 0.80, 0.60, "higher_better", evaluation_pinned=True, contribution=0.30),
    ], employee_id="E1")
    lower = _record("August", [
        _attendance(0.20, 0.80, 0.60, "lower_better", evaluation_pinned=True, unit="count", contribution=0.60),
    ], employee_id="E2")
    mixed = _service([higher, lower]).generate_workspace(
        _admin_scope(), month="August", year=2026, kpi="Attendance",
    )
    mixed_rows = _analyses(mixed, "Attendance")
    assert sorted(item.detail.direction for item in mixed_rows) == ["higher_better", "lower_better"]
    assert sorted(item.detail.current_value for item in mixed_rows) == pytest.approx([0.20, 0.40])
    assert mixed.kpi_overview.total_kpis == 2
    assert mixed.kpi_trend is not None
    assert mixed.kpi_trend.points[-1].actual_value is None


def test_direction_change_across_months_is_not_scored_as_one_cohort():
    july = _record("July", [
        _attendance(0.40, 0.80, 0.70, "higher_better", evaluation_pinned=True, contribution=0.35),
    ])
    august = _record("August", [
        _attendance(0.20, 0.80, 0.60, "lower_better", evaluation_pinned=True, contribution=0.60),
    ])
    workspace = _service([july, august]).generate_workspace(
        _admin_scope(), month="August", year=2026, kpi="Attendance",
    )

    august_row = _analyses(workspace, "Attendance")[0]
    assert august_row.detail.direction == "lower_better"
    assert august_row.detail.current_value == pytest.approx(0.20)
    assert august_row.detail.previous_value is None
    assert august_row.detail.achievement_percent == 100.0

    july_point = next(point for point in workspace.kpi_trend.points if point.period.month == "July")
    august_point = next(point for point in workspace.kpi_trend.points if point.period.month == "August")
    assert july_point.achievement_percent == 50.0
    assert august_point.achievement_percent == 100.0
    assert july_point.actual_value == pytest.approx(0.40)
    assert july_point.target_value == pytest.approx(0.80)
    assert august_point.actual_value == pytest.approx(0.20)
    assert august_point.change_value is None


def test_same_direction_and_unit_still_compare_across_months():
    july = _record("July", [
        _attendance(0.40, 0.80, 0.70, "higher_better", contribution=0.35),
    ])
    august = _record("August", [
        _attendance(0.50, 0.80, 0.60, "higher_better", contribution=0.375),
    ])
    workspace = _service([july, august]).generate_workspace(
        _admin_scope(), month="August", year=2026, kpi="Attendance",
    )
    row = _analyses(workspace, "Attendance")[0]
    assert row.detail.direction == "higher_better"
    assert row.detail.current_value == pytest.approx(0.50)
    assert row.detail.previous_value == pytest.approx(0.40)


def test_reviewer_unit_change_does_not_plot_percent_history_as_counts_or_calculate_movement():
    july = _record("July", [_attendance(0.40, 0.80, 0.60, "higher_better", evaluation_pinned=True)])
    august = _record("August", [_attendance(20, 40, 0.60, "higher_better", unit="count", evaluation_pinned=True)])
    workspace = _service([july, august]).generate_workspace(_admin_scope(), month="August", year=2026, kpi="Attendance")
    trend = workspace.kpi_trend
    assert trend.unit == "count"
    july_point = next(p for p in trend.points if p.period.month == "July")
    august_point = next(p for p in trend.points if p.period.month == "August")
    # The current response has ONE unit for the entire actual/target chart.
    # An incompatible old point must be a gap, not 0.4 count or a fabricated delta.
    assert july_point.actual_value is None
    assert july_point.target_value is None
    assert august_point.actual_value == 20
    assert august_point.change_value is None


def test_reviewer_distinct_mixed_cohorts_are_not_deduplicated_by_identical_narrative_ids():
    percent = _record("August", [_attendance(0.40, 0.80, 0.60, "higher_better", evaluation_pinned=True)], employee_id="E1")
    count = _record("August", [_attendance(0.50, 0.80, 0.60, "higher_better", unit="count", evaluation_pinned=True)], employee_id="E2")
    workspace = _service([percent, count]).generate_workspace(_admin_scope(), month="August", year=2026, kpi="Attendance")
    rows = _analyses(workspace, "Attendance")
    assert len(rows) == 2
    assert len({row.id for row in rows}) == 2
    assert {row.detail.unit for row in rows} == {"%", "count"}


def test_reviewer_mixed_current_unit_leaves_older_raw_points_off_the_unlabeled_chart():
    july = _record("July", [_attendance(0.40, 0.80, 0.60, "higher_better", evaluation_pinned=True)])
    august_percent = _record(
        "August",
        [_attendance(0.40, 0.80, 0.60, "higher_better", evaluation_pinned=True)],
        employee_id="E1",
    )
    august_count = _record(
        "August",
        [_attendance(20, 40, 0.60, "higher_better", unit="count", evaluation_pinned=True)],
        employee_id="E2",
    )
    workspace = _service([july, august_percent, august_count]).generate_workspace(
        _admin_scope(), month="August", year=2026, kpi="Attendance",
    )
    trend = workspace.kpi_trend
    assert trend is not None
    assert trend.unit is None
    july_point = next(point for point in trend.points if point.period.month == "July")
    august_point = next(point for point in trend.points if point.period.month == "August")
    assert july_point.actual_value is None
    assert july_point.target_value is None
    assert july_point.status is None
    assert july_point.change_value is None
    assert july_point.achievement_percent == 50.0
    assert august_point.actual_value is None
    assert august_point.target_value is None
    assert august_point.status is None


def test_reviewer_same_title_cohorts_keep_distinct_ids_and_driver_links():
    higher_percent = _record(
        "August",
        [_attendance(0.40, 0.80, 0.60, "higher_better", evaluation_pinned=True)],
        employee_id="E1",
    )
    higher_count = _record(
        "August",
        [_attendance(0.50, 0.80, 0.60, "higher_better", unit="count", evaluation_pinned=True)],
        employee_id="E2",
    )
    lower_percent = _record(
        "August",
        [_attendance(0.90, 0.80, 0.60, "lower_better", evaluation_pinned=True)],
        employee_id="E3",
    )
    workspace = _service([higher_percent, higher_count, lower_percent]).generate_workspace(
        _admin_scope(), month="August", year=2026, kpi="Attendance",
    )
    rows = _analyses(workspace, "Attendance")
    assert len(rows) == 3
    assert len({row.title for row in rows}) == 1
    assert len({row.id for row in rows}) == 3
    assert len({row.planning_context["source_insight_id"] for row in rows}) == 3
    drivers = [driver for driver in workspace.performance_drivers if driver.driver == "Attendance Rate"]
    assert len(drivers) == 3
    assert {driver.insight_id for driver in drivers} == {row.id for row in rows}
    assert len({driver.id for driver in drivers}) == 3
    assert {driver.insight_id for driver in drivers} <= {item.id for item in workspace.priority_insights}


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda self, kind: None)
    monkeypatch.setattr("services.cache_service.redis_client", None, raising=False)
    monkeypatch.setattr("services.cache_invalidation_service.redis_client", None, raising=False)
    monkeypatch.setattr(
        "services.cache_invalidation_service.CacheInvalidationService.bump_data_version",
        staticmethod(lambda: 0),
    )
    monkeypatch.setattr(
        "services.cache_invalidation_service.CacheInvalidationService.bump_config_version",
        staticmethod(lambda: 0),
    )
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from config.database import Base

    Base.metadata.create_all(
        bind=engine,
        tables=[
            Team.__table__,
            User.__table__,
            Employee.__table__,
            PerformanceRecord.__table__,
            KPIValue.__table__,
            TeamKPIConfig.__table__,
            TeamConfigurationVersion.__table__,
            EvaluationScope.__table__,
            EvaluationRevision.__table__,
            EmployeeUploadBatch.__table__,
            UploadLog.__table__,
            ManagementKPIConfig.__table__,
            ManagementKPISnapshot.__table__,
        ],
    )
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _edit_attendance(lines: list[dict], *, direction: str | None = None) -> list[dict]:
    edited = []
    for line in lines:
        item = dict(line)
        if item["kpi_key"] == "Attendance":
            item["weight"] = 0.50
            item["target_mode"] = "fixed"
            item["target"] = 0.70
            if direction is not None:
                item["direction"] = direction
        elif item["kpi_key"] == "Booking":
            item["weight"] = 0.20
        edited.append(item)
    return edited


def test_apply_and_rollback_round_trip_the_pinned_basis_through_insights(db):
    world = _World(db)
    july_record = world.record(world.employee, "July", _raw(JULY, productivity=None))
    august_raw = _raw(AUGUST, productivity=PRODUCTIVITY_ACTUAL)
    august_record = world.record(world.employee, "August", august_raw)
    world.stored_kpis(july_record, JULY, productivity=None)
    world.stored_kpis(august_record, AUGUST, productivity=PRODUCTIVITY_ACTUAL)
    db.refresh(august_record)
    raw_before = copy.deepcopy(august_record.record_payload["raw_data"])
    score_before = float(august_record.score)
    service = _db_service(db)

    before = service.generate_workspace(_admin_scope(), month="August", year=2026)
    assert "Productivity" not in _option_keys(before)

    draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 8)
    _approve(world, draft["id"])
    world.workflow.apply(world.actor, world.scope["id"], 2026, 8)
    db.refresh(august_record)
    db.refresh(july_record)
    applied_score = float(august_record.score)
    assert applied_score == pytest.approx(79.82)
    assert applied_score != score_before
    assert august_record.record_payload["raw_data"] == raw_before
    assert float(july_record.score) == score_before

    applied = service.generate_workspace(_admin_scope(), month="August", year=2026, team="Outbound")
    july_view = service.generate_workspace(_admin_scope(), month="July", year=2026, team="Outbound")
    assert "Productivity" in _option_keys(applied)
    assert "Productivity" not in _option_keys(july_view)
    august_point = next(point for point in applied.kpi_overview.points if point.period.month == "August")
    july_point = next(point for point in applied.kpi_overview.points if point.period.month == "July")
    assert august_point.total_kpis == 5
    assert july_point.total_kpis == 4
    productivity_view = service.generate_workspace(
        _admin_scope(), month="August", year=2026, team="Outbound", kpi="Productivity",
    )
    assert productivity_view.kpi_trend is not None
    assert productivity_view.kpi_trend.kpi_key == "Productivity"
    august_trend = next(point for point in productivity_view.kpi_trend.points if point.period.month == "August")
    july_trend = next(point for point in productivity_view.kpi_trend.points if point.period.month == "July")
    assert august_trend.actual_value == pytest.approx(round(PRODUCTIVITY_ACTUAL, 4))
    assert august_trend.measured_records == 1
    assert july_trend.measured_records == 0
    productivity = _analyses(applied, "Productivity")[0]
    stored_actual = float(next(row.actual_value for row in august_record.kpi_values if row.kpi_key == "Productivity"))
    assert stored_actual == pytest.approx(round(PRODUCTIVITY_ACTUAL, 4))
    assert productivity.detail.current_value == pytest.approx(stored_actual)
    assert august_record.record_payload["raw_data"]["Productivity"] == pytest.approx(PRODUCTIVITY_ACTUAL)
    assert productivity.detail.target_value == pytest.approx(0.8)
    assert productivity.detail.direction == "higher_better"
    assert _weight_text(productivity) == "10.0%"
    assert applied.team_summaries[0].current_score == pytest.approx(79.8)

    own_manager = service.generate_workspace(_manager_scope("Outbound"), month="August", year=2026)
    assert "Productivity" in _option_keys(own_manager)
    other_manager = service.generate_workspace(_manager_scope("Sales"), month="August", year=2026)
    assert "Productivity" not in _option_keys(other_manager)
    assert other_manager.team_summaries == []
    with pytest.raises(Exception):
        service.generate_workspace(_manager_scope("Sales"), month="August", year=2026, team="Outbound")
    own_employee = service.generate_workspace(_employee_scope("ANON-1"), month="August", year=2026)
    assert "Productivity" in _option_keys(own_employee)
    other_employee = service.generate_workspace(_employee_scope("ANON-2"), month="August", year=2026)
    assert "Productivity" not in _option_keys(other_employee)

    revised = world.workflow.revise(world.actor, draft["id"])
    with pytest.raises(EvaluationError) as refused:
        world.workflow.edit_draft(
            world.actor,
            revised["id"],
            _edit_attendance(revised["lines"], direction="lower_better"),
        )
    assert "higher-is-better" in str(refused.value)
    world.workflow.edit_draft(world.actor, revised["id"], _edit_attendance(revised["lines"]))
    world.workflow.impact_preview(world.actor, revised["id"])
    world.workflow.approve(world.actor, revised["id"])
    world.workflow.apply(world.actor, world.scope["id"], 2026, 8)
    db.refresh(august_record)
    edited_score = float(august_record.score)
    assert edited_score != applied_score
    assert august_record.record_payload["raw_data"] == raw_before
    assert august_record.record_payload["source_evidence"]["kpis"]["Attendance"]["target"] == "0.65"
    edited = service.generate_workspace(
        _admin_scope(), month="August", year=2026, team="Outbound", kpi="Attendance",
    )
    attendance = _analyses(edited, "Attendance")[0]
    assert attendance.detail.direction == "higher_better"
    assert attendance.detail.target_value == pytest.approx(0.70)
    assert _weight_text(attendance) == "50.0%"
    assert "Productivity" in _option_keys(edited)
    assert edited.team_summaries[0].current_score == pytest.approx(round(edited_score, 1))

    active = db.query(EvaluationRevision).filter(EvaluationRevision.status == "active").one()
    world.workflow.rollback(world.actor, active.id)
    db.refresh(august_record)
    db.refresh(july_record)
    assert float(august_record.score) == pytest.approx(applied_score)
    assert float(july_record.score) == score_before
    assert august_record.record_payload["raw_data"] == raw_before
    restored = service.generate_workspace(
        _admin_scope(), month="August", year=2026, team="Outbound", kpi="Attendance",
    )
    restored_attendance = _analyses(restored, "Attendance")[0]
    assert restored_attendance.detail.direction == "higher_better"
    assert restored_attendance.detail.target_value == pytest.approx(0.65)
    assert _weight_text(restored_attendance) == "60.0%"
    assert "Productivity" in _option_keys(restored)
    assert restored.team_summaries[0].current_score == pytest.approx(79.8)
    july_after = service.generate_workspace(_admin_scope(), month="July", year=2026, team="Outbound")
    assert "Productivity" not in _option_keys(july_after)
