"""Workflow consumer for an exact Outbound month.

Synthetic workbooks and sqlite memory only. July and August Employee with an
empty position are the admitted periods. Other months, levels, and positions
stay blocked.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

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
    PerformanceRecord,
    Team,
    TeamConfigurationVersion,
    TeamKPIConfig,
    UploadLog,
    User,
)
from services.dashboard_record_service import DashboardRecordService
from services.evaluation.access import AccessDenied, EvaluationError
from services.evaluation.workflow import EvaluationConflict, EvaluationWorkflow
from tests.test_outbound_productivity_ingestion import (
    AUGUST,
    AUGUST_RATIO,
    JULY,
    JULY_RATIO,
    TARGETS,
    _august_bytes,
    _bind,
    _seeder,
    _workbook,
)


JULY_GOLDEN = 82.85143792679492
AUGUST_GOLDEN = 79.82419863297692


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
        ],
    )
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _user(role: str, name: str) -> User:
    return User(
        id=uuid.uuid4(),
        full_name=name,
        username=name,
        email=f"{name}@example.com",
        password_hash="test-hash",
        role=role,
        is_active=True,
    )


def _actor(user: User) -> dict:
    return {
        "user_id": str(user.id),
        "role": "Admin",
        "employee_id": "",
        "accessible_teams": [],
        "accessible_team_levels": [],
        "accessible_functions": [],
        "accessible_regions": [],
        "accessible_branches": [],
        "has_unrestricted_team_access": True,
        "legacy_unscoped": False,
    }


def _raw(actuals: dict, *, productivity: float | None) -> dict:
    raw = {
        "A.Booking%": actuals["Booking"],
        "T.Booking%": TARGETS["Booking"],
        "A.Attend%": actuals["Attendance"],
        "T.Attend%": TARGETS["Attendance"],
        "A.Reachability%": actuals["Other"],
        "T.Reachability%": TARGETS["Other"],
        "A.QualityScore": actuals["Quality"],
        "T.Quality%": TARGETS["Quality"],
        "Available Time": 0.25,
        "AHT": "00:02:30",
    }
    if productivity is not None:
        raw["Productivity"] = productivity
        raw["T.Productivity%"] = TARGETS["Productivity"]
    return raw


def _reweight(lines: list[dict], weights: dict, fixed: dict | None = None) -> list[dict]:
    fixed = fixed or {}
    edited = []
    for line in lines:
        item = dict(line)
        key = item["kpi_key"]
        if key in weights:
            item["weight"] = weights[key]
        if key in fixed:
            item["target_mode"] = "fixed"
            item["target"] = fixed[key]
        edited.append(item)
    return edited


def _line(lines: list[dict], key: str) -> dict:
    return next(item for item in lines if item["kpi_key"] == key)


class _World:
    def __init__(self, db):
        self.db = db
        self.admin = _user("Admin", "consumer-admin")
        self.performance = _user("Performance Team", "consumer-performance")
        self.team = Team(
            id=uuid.uuid4(),
            name="Outbound",
            db_name="Outbound",
            display_name="Outbound",
            region="EGY",
            team_level="employee",
            is_active=True,
        )
        self.employee = Employee(
            id=uuid.uuid4(),
            employee_id="ANON-1",
            name="Anonymous Agent",
            team=self.team,
            region="EGY",
            performance_level="Employee",
        )
        self.colleague = Employee(
            id=uuid.uuid4(),
            employee_id="ANON-2",
            name="Second Agent",
            team=self.team,
            region="EGY",
            performance_level="Employee",
        )
        db.add_all([self.admin, self.performance, self.team, self.employee, self.colleague])
        db.commit()
        self.actor = _actor(self.admin)
        self.workflow = EvaluationWorkflow(db)
        catalog = self.workflow.sync_catalog(self.actor)
        self.scopes = catalog["scopes"]
        self.scope = self._scope("Employee", "")
        self.managerial = self._scope("Managerial", "")

    def _scope(self, level: str, position: str) -> dict:
        return next(
            item for item in self.scopes
            if item["display_name"] == "Outbound"
            and item["performance_level"] == level
            and item["position_name"] == position
        )

    def record(self, employee: Employee, month: str, raw: dict, *, score: str = "70.00") -> PerformanceRecord:
        row = PerformanceRecord(
            id=uuid.uuid4(),
            year=2026,
            employee_id=employee.id,
            team_id=self.team.id,
            month=month,
            performance_level="Employee",
            position_name="",
            region="EGY",
            score=Decimal(score),
            grade="D",
            status="Below",
            record_payload={
                "manager_notes": f"keep {month}",
                "evaluation": {"score": float(score), "grade": "D"},
                "raw_data": raw,
            },
        )
        self.db.add(row)
        self.db.flush()
        return row

    def kpi(self, record: PerformanceRecord, key: str, actual, target) -> KPIValue:
        row = KPIValue(
            id=uuid.uuid4(),
            record_id=record.id,
            record_year=record.year,
            kpi_key=key,
            actual_value=Decimal(str(actual)).quantize(Decimal("0.0001")),
            target_value=Decimal(str(target)).quantize(Decimal("0.0001")),
            achievement_ratio=Decimal("1.0000"),
            weight_applied=Decimal("0.1000"),
            contribution=Decimal("0.1000"),
        )
        self.db.add(row)
        return row

    def stored_kpis(self, record: PerformanceRecord, actuals: dict, *, productivity: float | None, sql_target: str = "0.1100") -> None:
        keys = ["Attendance", "Booking", "Quality", "Other"]
        if productivity is not None:
            keys.append("Productivity")
        for key in keys:
            actual = productivity if key == "Productivity" else actuals[key]
            # Available Time is the decoy for Productivity. Other targets are not the workbook targets.
            target = "0.2500" if key == "Productivity" else sql_target
            self.kpi(record, key, actual, target)
        self.db.commit()


def _approve(world: _World, version_id: str) -> dict:
    world.workflow.impact_preview(world.actor, version_id)
    return world.workflow.approve(world.actor, version_id)


def test_exact_month_catalog_admits_july_and_august_only(db):
    world = _World(db)
    assert world.scope["readiness"] == "blocked"
    assert world.scope["supported"] is False
    july = world.workflow.period(world.actor, world.scope["id"], 2026, 7)
    august = world.workflow.period(world.actor, world.scope["id"], 2026, 8)
    september = world.workflow.period(world.actor, world.scope["id"], 2026, 9)
    assert july["scope"]["readiness"] == "supported"
    assert july["scope"]["global_readiness"] == "blocked"
    assert july["scope"]["global_supported"] is False
    assert august["scope"]["readiness"] == "supported"
    assert august["scope"]["period_supported"] is True
    assert "Productivity" in {line["kpi_key"] for line in august["scope"]["lines"]}
    assert september["scope"]["readiness"] == "blocked"
    assert september["scope"]["global_readiness"] == "blocked"
    assert db.query(Team).filter(Team.id == world.team.id).one().is_active is True


def test_unsupported_period_level_position_and_inactive_team_stay_blocked(db):
    world = _World(db)
    for year, month in ((2026, 9), (2027, 8), (2026, 6)):
        with pytest.raises(EvaluationError) as blocked:
            world.workflow.open_draft(world.actor, world.scope["id"], year, month)
        assert blocked.value.data["code"] == "unsupported_calculation"
        assert blocked.value.data["edit_mode"] == "blocked"
        assert blocked.value.data["weight_only_allowed"] is False
    with pytest.raises(EvaluationError) as managerial:
        world.workflow.open_draft(world.actor, world.managerial["id"], 2026, 8)
    assert managerial.value.data["code"] == "unsupported_calculation"

    positioned = EvaluationScope(
        id=uuid.uuid4(),
        team_id=world.team.id,
        team_key="outbound",
        display_name="Outbound",
        performance_level="Employee",
        position_name="Agent",
        readiness="supported",
        block_reason=None,
        history_note="Stored readiness must not grant this position.",
        ambiguous_kpis=[],
        policy_family="employee_ratio",
        source_kind="database",
    )
    db.add(positioned)
    db.commit()
    with pytest.raises(EvaluationError) as position:
        world.workflow.open_draft(world.actor, positioned.id, 2026, 8)
    assert position.value.data["code"] == "unsupported_calculation"
    assert db.query(TeamConfigurationVersion).count() == 0

    world.team.is_active = False
    db.commit()
    with pytest.raises(EvaluationError) as inactive:
        world.workflow.open_draft(world.actor, world.scope["id"], 2026, 8)
    assert inactive.value.data["code"] == "scope_blocked"


def test_july_to_august_copy_adds_productivity_and_same_month_keeps_custom_weights(db):
    world = _World(db)
    july_raw = _raw(JULY, productivity=None)
    august_raw = _raw(AUGUST, productivity=AUGUST["Productivity"])
    july_record = world.record(world.employee, "July", july_raw)
    august_record = world.record(world.employee, "August", august_raw)
    world.stored_kpis(july_record, JULY, productivity=None)
    world.stored_kpis(august_record, AUGUST, productivity=AUGUST["Productivity"])

    july_draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 7)
    assert "Productivity" not in {line["kpi_key"] for line in july_draft["lines"] if float(line["weight"]) > 0}
    july_lines = _reweight(july_draft["lines"], {"Attendance": 0.40, "Booking": 0.20, "Quality": 0.20, "Other": 0.20})
    world.workflow.edit_draft(world.actor, july_draft["id"], july_lines)
    approved_july = _approve(world, july_draft["id"])
    db.refresh(july_record)
    assert approved_july["applied"] is False
    assert float(july_record.score) == 70.0
    assert "evaluation_basis" not in (july_record.record_payload or {})

    august_draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 8, copy_previous=True)
    assert august_draft["source_version_id"] is None
    assert _line(august_draft["lines"], "Attendance")["weight"] == pytest.approx(0.60)
    productivity = _line(august_draft["lines"], "Productivity")
    assert productivity["weight"] == pytest.approx(0.10)
    assert productivity["target"] == pytest.approx(0.8)
    assert "Productivity" in (august_draft["notes"] or "")
    stored_draft = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(august_draft["id"])).one()
    assert stored_draft.config_snapshot["template_changed"] is True
    assert stored_draft.config_snapshot["preserved_values"] is False
    assert any("Productivity" in item for item in stored_draft.config_snapshot["copy_diagnostics"])

    custom = _reweight(
        august_draft["lines"],
        {"Attendance": 0.50, "Booking": 0.10, "Quality": 0.10, "Other": 0.10, "Productivity": 0.20, "AHT": 0},
        {"Attendance": 0.50},
    )
    world.workflow.edit_draft(world.actor, august_draft["id"], custom)
    preview = world.workflow.impact_preview(world.actor, august_draft["id"])
    assert preview["writes"] == 0
    assert preview["conflicts"]
    assert preview["conflicts"][0]["workbook_target"] == pytest.approx(0.65)
    assert preview["conflicts"][0]["workbook_target"] != pytest.approx(0.11)
    db.refresh(stored_draft)
    proof = stored_draft.config_snapshot["preview_evidence"]
    assert proof["comparisons"]
    assert proof["conflicts"]
    approved = world.workflow.approve(world.actor, august_draft["id"])
    assert "preview_evidence" not in approved
    db.refresh(august_record)
    assert float(august_record.score) == 70.0
    assert "evaluation_basis" not in (august_record.record_payload or {})

    applied = world.workflow.apply(world.actor, world.scope["id"], 2026, 8)
    db.refresh(august_record)
    db.refresh(july_record)
    assert float(july_record.score) == 70.0
    assert "evaluation_basis" not in (july_record.record_payload or {})
    assert august_record.record_payload["evaluation_basis"]["pinned"] is True
    assert august_record.record_payload["evaluation_basis"]["version_id"] == approved["id"]
    assert august_record.record_payload["manager_notes"] == "keep August"
    assert august_record.record_payload["raw_data"]["T.Attend%"] == pytest.approx(0.65)
    assert august_record.record_payload["raw_data"]["Productivity"] == pytest.approx(AUGUST["Productivity"])
    assert august_record.record_payload["raw_data"]["Productivity"] != pytest.approx(0.25)
    source = august_record.record_payload["source_evidence"]["kpis"]
    assert source["Attendance"]["target"] == "0.65"
    assert source["Productivity"]["target"] == "0.8"
    assert Decimal(source["Productivity"]["actual"]) == pytest.approx(Decimal(str(AUGUST["Productivity"])))
    assert source["Productivity"]["actual"] != "0.25"
    attendance = next(row for row in august_record.kpi_values if row.kpi_key == "Attendance")
    assert float(attendance.target_value) == pytest.approx(0.50)
    assert float(august_record.score) != 70.0
    assert applied["idempotent"] is False

    revised = world.workflow.revise(world.actor, approved["id"])
    assert _line(revised["lines"], "Attendance")["weight"] == pytest.approx(0.50)
    assert _line(revised["lines"], "Productivity")["weight"] == pytest.approx(0.20)
    assert _line(revised["lines"], "Attendance")["target"] == pytest.approx(0.50)
    assert revised["source_version_id"] == approved["id"]
    second_lines = _reweight(revised["lines"], {}, {"Attendance": 0.40})
    world.workflow.edit_draft(world.actor, revised["id"], second_lines)
    world.workflow.impact_preview(world.actor, revised["id"])
    world.workflow.approve(world.actor, revised["id"])
    world.workflow.apply(world.actor, world.scope["id"], 2026, 8)
    db.refresh(august_record)
    assert august_record.record_payload["source_evidence"]["kpis"]["Attendance"]["target"] == "0.65"
    assert august_record.record_payload["source_evidence"]["kpis"]["Productivity"]["actual"] == source["Productivity"]["actual"]
    assert august_record.record_payload["raw_data"]["T.Attend%"] == pytest.approx(0.65)
    attendance = next(row for row in august_record.kpi_values if row.kpi_key == "Attendance")
    assert float(attendance.target_value) == pytest.approx(0.40)

    active = db.query(EvaluationRevision).filter(EvaluationRevision.status == "active").one()
    world.workflow.rollback(world.actor, active.id)
    db.refresh(august_record)
    attendance = next(row for row in august_record.kpi_values if row.kpi_key == "Attendance")
    assert float(attendance.target_value) == pytest.approx(0.50)
    assert august_record.record_payload["source_evidence"]["kpis"]["Attendance"]["target"] == "0.65"
    assert august_record.record_payload["manager_notes"] == "keep August"
    db.refresh(july_record)
    assert float(july_record.score) == 70.0


def test_missing_productivity_and_invalid_edits_are_refused(db):
    world = _World(db)
    draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 8)
    raw = _raw(AUGUST, productivity=None)
    record = world.record(world.employee, "August", raw)
    world.stored_kpis(record, AUGUST, productivity=AUGUST["Productivity"])
    with pytest.raises(EvaluationError) as missing:
        world.workflow.impact_preview(world.actor, draft["id"])
    assert missing.value.data["code"] == "missing_evidence"
    assert missing.value.data["missing_evidence"][0]["kpi_key"] == "Productivity"
    assert missing.value.data["missing_evidence"][0]["reason"] == "missing_source"
    db.refresh(record)
    assert float(record.score) == 70.0
    assert "evaluation_basis" not in (record.record_payload or {})

    activated = _reweight(draft["lines"], {"AHT": 0.05, "Attendance": 0.55})
    with pytest.raises(EvaluationError) as aht:
        world.workflow.edit_draft(world.actor, draft["id"], activated)
    assert aht.value.data["code"] == "unsupported_calculation"
    lowered = [dict(line) for line in draft["lines"]]
    lowered[0]["direction"] = "lower_better"
    with pytest.raises(EvaluationError) as direction:
        world.workflow.edit_draft(world.actor, draft["id"], lowered)
    assert direction.value.data["code"] in {"unsupported_calculation", "unsupported_direction"}
    added = [dict(line) for line in draft["lines"]]
    added.append({**added[0], "kpi_key": "Mystery", "weight": 0})
    with pytest.raises(EvaluationError) as extra:
        world.workflow.edit_draft(world.actor, draft["id"], added)
    assert extra.value.data["code"] == "unsupported_edit"
    removed = [dict(line) for line in draft["lines"] if line["kpi_key"] != "Productivity"]
    with pytest.raises(EvaluationError) as dropped:
        world.workflow.edit_draft(world.actor, draft["id"], removed)
    assert dropped.value.data["code"] == "unsupported_edit"
    shifted = _reweight(draft["lines"], {"Productivity": 0, "Attendance": 0.70})
    with pytest.raises(EvaluationError) as keys:
        world.workflow.edit_draft(world.actor, draft["id"], shifted)
    assert keys.value.data["code"] == "unsupported_calculation"
    db.refresh(record)
    assert float(record.score) == 70.0


def test_stale_evidence_and_mixed_reads_stay_truthful(db):
    world = _World(db)
    raw = _raw(AUGUST, productivity=AUGUST["Productivity"])
    record = world.record(world.employee, "August", raw)
    world.stored_kpis(record, AUGUST, productivity=AUGUST["Productivity"])
    draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 8)
    world.workflow.impact_preview(world.actor, draft["id"])
    record.record_payload = {
        **record.record_payload,
        "raw_data": {**raw, "A.Attend%": 0.2},
    }
    db.commit()
    with pytest.raises(EvaluationConflict) as stale:
        world.workflow.approve(world.actor, draft["id"])
    assert stale.value.data["code"] == "stale_preview"
    db.refresh(record)
    assert float(record.score) == 70.0
    assert "evaluation_basis" not in (record.record_payload or {})

    record.record_payload = {
        "manager_notes": "keep August",
        "evaluation": {"score": 70, "grade": "D"},
        "raw_data": raw,
        "evaluation_basis": {
            "pinned": True,
            "version_id": "saved-pin",
            "lines": [{"kpi_key": "Attendance", "label": "SAVED-PIN", "target": 0.65, "weight": 0.60}],
        },
    }
    legacy = world.record(world.colleague, "August", raw, score="88.00")
    legacy.record_payload = {"manager_notes": "legacy-row", "evaluation": {"score": 88, "grade": "B"}}
    hidden_team = Team(
        id=uuid.uuid4(), name="Pharmacy", db_name="Pharmacy", display_name="Pharmacy",
        region="EGY", team_level="employee", is_active=True,
    )
    hidden_employee = Employee(
        id=uuid.uuid4(), employee_id="SECRET-1", name="Hidden", team=hidden_team,
        region="EGY", performance_level="Employee",
    )
    db.add_all([hidden_team, hidden_employee])
    db.flush()
    hidden = world.record(hidden_employee, "August", raw, score="91.00")
    hidden.team_id = hidden_team.id
    hidden.record_payload = {"evaluation_basis": {"pinned": True, "version_id": "hidden", "lines": [{"label": "COLLEAGUE-SECRET"}]}}
    db.commit()
    reads = world.workflow.reads(world.actor, world.scope["id"], 2026, [8])
    body = reads["periods"][0]
    assert body["basis_state"] == "mixed"
    assert body["pinned"] is False
    assert body["version_id"] is None
    assert body["lines"] == []
    assert body["stored_score"] is None
    assert {item["record_id"] for item in body["evidence"]} == {str(record.id), str(legacy.id)}
    assert {item["version_id"] for item in body["evidence"]} == {"saved-pin", None}
    again = world.workflow.reads(world.actor, world.scope["id"], 2026, [8])
    assert again == reads
    rendered = str(reads)
    assert "COLLEAGUE-SECRET" not in rendered
    assert "91.0" not in rendered


def test_only_a_persisted_admin_can_manage(db):
    world = _World(db)
    draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, 8)
    _approve(world, draft["id"])
    performance_actor = _actor(world.performance)
    performance_actor["role"] = "Performance Team"
    with pytest.raises(AccessDenied):
        world.workflow.revise(performance_actor, draft["id"])
    disguised = _actor(world.performance)
    with pytest.raises(AccessDenied):
        world.workflow.revise(disguised, draft["id"])
    with pytest.raises(AccessDenied):
        world.workflow.open_draft(
            {"user_id": str(uuid.uuid4()), "role": "Admin", "legacy_unscoped": False},
            world.scope["id"],
            2026,
            8,
        )
    assert db.query(EvaluationRevision).count() == 0


def test_approved_upload_preview_commit_and_resolved_read_match_period_goldens(db, monkeypatch):
    world = _World(db)
    for month in (7, 8):
        draft = world.workflow.open_draft(world.actor, world.scope["id"], 2026, month)
        approved = _approve(world, draft["id"])
        assert approved["applied"] is False
    _bind(db, monkeypatch)
    seeder = _seeder()
    august_blob = _august_bytes()
    august_preview = seeder.process_uploaded_file("august.xlsx", august_blob, dry_run=True, db_session=db)
    august_committed = seeder.process_uploaded_file("august.xlsx", august_blob, dry_run=False, db_session=db)
    assert august_preview["scored_rows"] == august_committed["scored_rows"]
    july_blob = _workbook(
        datetime(2026, 7, 15), JULY, productivity=None, role="Emp", sheet="Outbound Offshore Call Center",
    )
    july_preview = seeder.process_uploaded_file("july.xlsx", july_blob, dry_run=True, db_session=db)
    july_committed = seeder.process_uploaded_file("july.xlsx", july_blob, dry_run=False, db_session=db)
    assert july_preview["scored_rows"] == july_committed["scored_rows"]

    stored = db.query(PerformanceRecord).filter(PerformanceRecord.month == "August").one()
    july = db.query(PerformanceRecord).filter(PerformanceRecord.month == "July").one()
    august_ratio = sum(float(item["contribution"]) for item in stored.record_payload["kpi_values"])
    july_ratio = sum(float(item["contribution"]) for item in july.record_payload["kpi_values"])
    assert august_ratio * 100 == pytest.approx(AUGUST_GOLDEN, abs=1e-8, rel=0)
    assert august_ratio == pytest.approx(AUGUST_RATIO, abs=1e-8, rel=0)
    assert july_ratio * 100 == pytest.approx(JULY_GOLDEN, abs=1e-8, rel=0)
    assert july_ratio == pytest.approx(JULY_RATIO, abs=1e-8, rel=0)
    assert float(stored.score) == pytest.approx(round(AUGUST_RATIO * 100, 2), abs=0.001)
    assert float(july.score) == pytest.approx(round(JULY_RATIO * 100, 2), abs=0.001)
    assert stored.record_payload["raw_data"]["Productivity"] == pytest.approx(AUGUST["Productivity"])
    available = stored.record_payload["raw_data"].get("Available Time", stored.record_payload["raw_data"].get("AvailableTime"))
    assert available == pytest.approx(0.25)
    assert stored.record_payload["raw_data"]["Productivity"] != pytest.approx(available)
    assert stored.record_payload["source_evidence"]["kpis"]["Productivity"]["target"] == "0.8"
    assert stored.record_payload["evaluation_basis"]["pinned"] is True
    assert "calls" in stored.record_payload
    assert stored.record_payload["actual"]["productivity_rate"] == pytest.approx(AUGUST["Productivity"])
    [resolved] = DashboardRecordService(db).resolve_records([stored])
    assert resolved.actual.productivity_rate == pytest.approx(AUGUST["Productivity"])
    assert float(resolved.evaluation.score) == pytest.approx(round(AUGUST_RATIO * 100, 2), abs=0.001)
    productivity = next(item for item in resolved.kpi_values if item["kpi_key"] == "Productivity")
    assert productivity["actual_value"] == pytest.approx(AUGUST["Productivity"], abs=5e-5)
