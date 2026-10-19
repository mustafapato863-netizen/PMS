"""Ordinary Inbound and Outbound scoring follows the operational upload contract.

Expected scores in this module are the weighted row ratios, with the final total
capped at 100. They are not taken from the reference-workbook helper. Rows are
synthetic and anonymous.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import selectinload, sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import (
    Base,
    Employee,
    KPIValue,
    PerformanceRecord,
    Team,
    TeamConfigurationVersion,
    User,
)
from services.cache_service import in_memory_cache, redis_client
from services.evaluation.access import AccessDenied, EvaluationError, TargetConflict
from services.evaluation.resolver import require_approved_capability
from services.evaluation.workflow import EvaluationConflict, EvaluationWorkflow
from services.kpi_service import KPIService
from services.performance_dashboard_read_service import PerformanceDashboardReadService


def _total(parts: list[float]) -> float:
    raw = 0.0
    for part in parts:
        raw += part
    return float(round(min(max(raw, 0.0), 1.0) * 100.0, 2))


def _grade(score: float, thresholds: dict) -> str:
    for band in ("A", "B", "C", "D"):
        if score >= float(thresholds[band]):
            return band
    return "E"


OUTBOUND_WEIGHTS = {"Attend": 0.70, "Booking": 0.10, "Quality": 0.10, "Other": 0.10}
JUNE_OUTBOUND_WEIGHTS = {"Attend": 0.70, "Booking": 0.10, "Quality": 0.0, "Other": 0.20}
INBOUND_WEIGHTS = {"Attend": 0.70, "Booking": 0.10, "Quality": 0.05, "AHT": 0.05, "Other": 0.10}
JUNE_INBOUND_WEIGHTS = {"Attend": 0.70, "Booking": 0.10, "Quality": 0.0, "AHT": 0.05, "Other": 0.15}

# Sheet ratios used by every ordinary Outbound month. Booking is twice its target.
_ATTEND_ACTUAL, _ATTEND_TARGET = 0.40, 0.80
_BOOKING_ACTUAL, _BOOKING_TARGET = 0.60, 0.30
_QUALITY_ACTUAL, _QUALITY_TARGET = 0.40, 0.80
_OTHER_ACTUAL, _OTHER_TARGET = 0.25, 0.50
_ATTEND_ACH = _ATTEND_ACTUAL / _ATTEND_TARGET
_BOOKING_ACH = _BOOKING_ACTUAL / _BOOKING_TARGET
_QUALITY_ACH = _QUALITY_ACTUAL / _QUALITY_TARGET
_OTHER_ACH = _OTHER_ACTUAL / _OTHER_TARGET

# Inbound volume defaults: attendance 0.75, booking 0.45, quality 0.95,
# AHT 150 seconds, utilization 0.85, abandon 0.01.
_HANDLED = 100.0
_BOOKINGS = 45.0
_ATTENDS = 16.875
_IN_ATTEND_ACH = (_ATTENDS / _BOOKINGS) / 0.75
_IN_BOOKING_ACH = (_BOOKINGS / _HANDLED) / 0.45
_IN_QUALITY_ACH = 0.95 / 0.95
_IN_AHT_ACH = 150.0 / (2.0 * 60.0)
_IN_UTZ_ACH = 0.85 / 0.85
_IN_ABANDON_ACH = 0.01 / (2.0 / 100.0)


def _outbound_parts(weights: dict[str, float]) -> list[float]:
    return [
        min(_ATTEND_ACH, 1.0) * weights["Attend"],
        min(_BOOKING_ACH, 1.0) * weights["Booking"],
        min(_QUALITY_ACH, 1.0) * weights["Quality"],
        min(_OTHER_ACH, 1.0) * weights["Other"],
    ]


def _inbound_parts(weights: dict[str, float], other_achievement: float, aht_achievement: float) -> list[float]:
    return [
        min(_IN_ATTEND_ACH, 1.0) * weights["Attend"],
        min(_IN_BOOKING_ACH, 1.0) * weights["Booking"],
        min(_IN_QUALITY_ACH, 1.0) * weights["Quality"],
        min(aht_achievement, 1.0) * weights["AHT"],
        min(other_achievement, 1.0) * weights["Other"],
    ]


class _EmptyConfigRepository:
    def get_by_team(self, _team):
        return None


def _kpi_service() -> KPIService:
    empty = _EmptyConfigRepository()
    return KPIService(empty, empty)


def _outbound_sheet(when: date, *, productivity: float | None = None, quality: float | None = _QUALITY_ACTUAL) -> dict:
    row = {
        "Date": when,
        "A.Attend%": _ATTEND_ACTUAL,
        "T.Attend%": _ATTEND_TARGET,
        "A.Booking%": _BOOKING_ACTUAL,
        "T.Booking%": _BOOKING_TARGET,
        "A.Reachability%": _OTHER_ACTUAL,
        "T.Reachability%": _OTHER_TARGET,
    }
    if quality is not None:
        row["A.QualityScore"] = quality
        row["T.Quality%"] = _QUALITY_TARGET
    if productivity is not None:
        row["A.Productivity%"] = productivity
        row["T.Productivity%"] = 0.80
    return row


def _inbound_sheet(when: date, *, utz, aht_minutes: float = 2.0, abandoned: float = 0.0) -> dict:
    row = {
        "Date": when,
        "TotalHandledCalls": _HANDLED,
        "Dubai_Booking": _BOOKINGS,
        "Dubai_Attend": _ATTENDS,
        "InboundCalls": _HANDLED,
        "AbandonedCalls": abandoned,
        "A.QualityScore": 0.95,
        "AHT_Minutes": aht_minutes,
    }
    if utz is not None:
        row["A.UTZ%"] = utz
    return row


def _user(role: str, name: str) -> User:
    suffix = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        full_name=name,
        username=f"{name}-{suffix}",
        email=f"{name}-{suffix}@example.com",
        password_hash="test-hash",
        role=role,
        is_active=True,
    )


def _actor(user: User) -> dict:
    return {
        "user_id": str(user.id),
        "role": user.role,
        "employee_id": "",
        "accessible_teams": [],
        "accessible_functions": [],
        "accessible_regions": [],
        "accessible_branches": [],
        "has_unrestricted_team_access": user.role == "Admin",
        "legacy_unscoped": False,
    }


@pytest.fixture
def db():
    assert not redis_client
    import services.cache_invalidation_service as versions

    data_version = versions._fallback_data_version
    config_version = versions._fallback_config_version
    in_memory_cache.invalidate_by_prefix("pms:")
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        versions._fallback_data_version = data_version
        versions._fallback_config_version = config_version
        in_memory_cache.invalidate_by_prefix("pms:")


class _World:
    def __init__(self, session):
        self.db = session
        self.admin = _user("Admin", "synthetic-admin")
        self.manager = _user("Manager", "synthetic-manager")
        self.teams = {}
        for name in ("Outbound", "Inbound", "Coding"):
            self.teams[name] = Team(
                id=uuid.uuid4(),
                name=name,
                db_name=name,
                display_name=name,
                region="UAE",
                team_level="employee",
                is_active=True,
            )
        session.add_all([self.admin, self.manager, *self.teams.values()])
        session.commit()
        self.actor = _actor(self.admin)
        self.manager_actor = _actor(self.manager)
        self.workflow = EvaluationWorkflow(session)
        self.catalog = self.workflow.sync_catalog(self.actor)
        self.uploaded_at = datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc)

    def scope(self, name: str, level: str = "Employee", position: str = "") -> dict:
        return next(
            item for item in self.catalog["scopes"]
            if item["display_name"].casefold() == name.casefold()
            and item["performance_level"] == level
            and item["position_name"] == position
        )

    def employee(self, team: Team, code: str) -> Employee:
        row = Employee(
            id=uuid.uuid4(),
            employee_id=code,
            name="Synthetic",
            team_id=team.id,
            region="UAE",
            performance_level="Employee",
            position_name="",
        )
        self.db.add(row)
        self.db.flush()
        return row

    def record(self, team: Team, employee: Employee, month: str, score: str, grade: str, raw: dict | None = None) -> PerformanceRecord:
        payload = {"evaluation": {"score": float(score), "grade": grade}}
        if raw is not None:
            payload["raw_data"] = raw
        row = PerformanceRecord(
            id=uuid.uuid4(),
            year=2026,
            employee_id=employee.id,
            team_id=team.id,
            month=month,
            performance_level="Employee",
            position_name="",
            region="UAE",
            branch_key="dubai",
            score=Decimal(score),
            grade=grade,
            status="Below",
            uploaded_at=self.uploaded_at,
            record_payload=payload,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def kpi(self, record: PerformanceRecord, key: str, actual, target, achievement, weight, contribution) -> None:
        self.db.add(KPIValue(
            id=uuid.uuid4(),
            record_id=record.id,
            record_year=record.year,
            kpi_key=key,
            actual_value=Decimal(str(actual)),
            target_value=Decimal(str(target)),
            achievement_ratio=Decimal(str(achievement)),
            weight_applied=Decimal(str(weight)),
            contribution=Decimal(str(contribution)),
        ))
        self.db.flush()


def _weights_of(lines: list[dict]) -> dict[str, float]:
    return {line["kpi_key"]: float(line["weight"]) for line in lines}


def _edit_target(lines: list[dict], key: str, target: float) -> list[dict]:
    edited = []
    for line in lines:
        item = {
            "kpi_key": line["kpi_key"],
            "weight": line["weight"],
            "direction": line["direction"],
            "target_mode": line.get("target_mode") or "workbook",
            "target": line.get("target"),
        }
        if line["kpi_key"] == key:
            item["target_mode"] = "fixed"
            item["target"] = target
        edited.append(item)
    return edited


def _edit_weights(lines: list[dict], weights: dict[str, float]) -> list[dict]:
    return [
        {
            "kpi_key": line["kpi_key"],
            "weight": weights[line["kpi_key"]],
            "direction": line["direction"],
            "target_mode": "workbook",
            "target": None,
        }
        for line in lines
    ]


def _reload(db, record_id, year: int) -> PerformanceRecord:
    row = (
        db.query(PerformanceRecord)
        .options(selectinload(PerformanceRecord.kpi_values), selectinload(PerformanceRecord.employee))
        .filter(PerformanceRecord.id == record_id, PerformanceRecord.year == year)
        .one()
    )
    db.refresh(row)
    return row


def _kpi_map(record: PerformanceRecord) -> dict[str, KPIValue]:
    return {value.kpi_key: value for value in record.kpi_values}


def test_outbound_upload_keeps_one_contract_across_months(monkeypatch):
    def _reference_selected(*_args, **_kwargs):
        raise AssertionError("a row date selected the reference workbook")

    monkeypatch.setattr("services.outbound_period_basis.canonical_outbound_basis", _reference_selected)
    service = _kpi_service()
    ordinary = _total(_outbound_parts(OUTBOUND_WEIGHTS))
    assert ordinary == pytest.approx(55.0, abs=0.001)

    scores = {}
    for month in (3, 5, 7, 8, 9):
        score, _grade_name, achievements, weights = service.calculate_performance(
            "Outbound", _outbound_sheet(date(2026, month, 1)),
        )
        scores[month] = score
        assert score == pytest.approx(ordinary, abs=0.001)
        assert weights["Attend"] == pytest.approx(0.70)
        assert weights["Booking"] == pytest.approx(0.10)
        assert weights["Quality"] == pytest.approx(0.10)
        assert weights["Other"] == pytest.approx(0.10)
        assert "Productivity" not in weights
        assert achievements["Booking"] == pytest.approx(_BOOKING_ACH)
        assert achievements["Booking"] > 1

    assert len(set(scores.values())) == 1

    june_score, _june_grade, june_achievements, june_weights = service.calculate_performance(
        "Outbound", _outbound_sheet(date(2026, 6, 1)),
    )
    june_expected = _total(_outbound_parts(JUNE_OUTBOUND_WEIGHTS))
    assert june_weights["Quality"] == pytest.approx(0.0)
    assert june_weights["Other"] == pytest.approx(0.20)
    assert june_weights["Attend"] == pytest.approx(0.70)
    assert "Productivity" not in june_weights
    assert june_score == pytest.approx(june_expected, abs=0.001)
    assert june_achievements["Quality"] == pytest.approx(_QUALITY_ACH)
    assert june_achievements["Booking"] == pytest.approx(_BOOKING_ACH)

    zero_score, _zero_grade, zero_achievements, zero_weights = service.calculate_performance(
        "Outbound", _outbound_sheet(date(2026, 8, 1), quality=0),
    )
    assert zero_achievements["Quality"] == pytest.approx(0.0)
    assert zero_weights["Quality"] == pytest.approx(0.10)
    assert zero_score != june_score

    missing_score, _missing_grade, missing_achievements, missing_weights = service.calculate_performance(
        "Outbound", _outbound_sheet(date(2026, 8, 1), quality=None),
    )
    assert missing_achievements["Quality"] == pytest.approx(0.0)
    assert missing_weights == zero_weights
    assert missing_score == pytest.approx(zero_score, abs=0.001)


def test_outbound_upload_keeps_productivity_at_zero_weight():
    service = _kpi_service()
    score, _grade_name, achievements, weights = service.calculate_performance(
        "Outbound", _outbound_sheet(date(2026, 8, 1), productivity=0.50),
    )
    expected = _total(_outbound_parts(OUTBOUND_WEIGHTS))
    assert "Productivity" in weights
    assert weights["Productivity"] == pytest.approx(0.0)
    assert achievements["Productivity"] == pytest.approx(0.50 / 0.80)
    assert weights["Attend"] == pytest.approx(0.70)
    assert weights["Booking"] == pytest.approx(0.10)
    assert weights["Quality"] == pytest.approx(0.10)
    assert weights["Other"] == pytest.approx(0.10)
    assert score == pytest.approx(expected, abs=0.001)
    assert abs(sum(weights.values()) - 1.0) < 0.0001


def test_operational_pin_keeps_a_present_productivity_actual_at_zero_weight():
    """An approved operational pin must not reject a Productivity actual."""
    from services.operational_upload_contract import operational_lines
    from services.seeding_service import pin_upload_score

    lines = operational_lines("Outbound", 2026, 8)
    assert [line["kpi_key"] for line in lines] == ["Attendance", "Booking", "Quality", "Other"]
    version = SimpleNamespace(
        id="operational-pin",
        version_number=1,
        performance_level="Employee",
        position_name="",
        effective_from_year=2026,
        effective_from_month=8,
        config_snapshot={
            "contract": "operational_upload",
            "policy": "operational_upload",
            "lines": lines,
            "grade_thresholds": {"A": 95, "B": 85, "C": 75, "D": 65},
        },
    )
    evidence = [
        {"kpi_key": "Attendance", "actual": _ATTEND_ACTUAL, "workbook_target": _ATTEND_TARGET},
        {"kpi_key": "Booking", "actual": _BOOKING_ACTUAL, "workbook_target": _BOOKING_TARGET},
        {"kpi_key": "Quality", "actual": _QUALITY_ACTUAL, "workbook_target": _QUALITY_TARGET},
        {"kpi_key": "Other", "actual": _OTHER_ACTUAL, "workbook_target": _OTHER_TARGET},
        {"kpi_key": "Productivity", "actual": 0.50, "workbook_target": 0.80},
    ]
    scored = pin_upload_score(version, evidence)
    by_key = {item["kpi_key"]: item for item in scored["rows"]}
    expected = _total(_outbound_parts(OUTBOUND_WEIGHTS))
    assert set(by_key) == {"Attendance", "Booking", "Quality", "Other", "Productivity"}
    assert by_key["Productivity"]["weight"] == 0
    assert by_key["Productivity"]["contribution"] == 0
    assert by_key["Productivity"]["actual"] == pytest.approx(0.50)
    assert by_key["Productivity"]["achievement"] == pytest.approx(0.50 / 0.80)
    assert by_key["Attendance"]["weight"] == pytest.approx(0.70)
    assert by_key["Booking"]["weight"] == pytest.approx(0.10)
    assert by_key["Quality"]["weight"] == pytest.approx(0.10)
    assert by_key["Other"]["weight"] == pytest.approx(0.10)
    assert scored["score"] == pytest.approx(expected, abs=0.001)
    with pytest.raises(EvaluationError) as unknown:
        pin_upload_score(version, [*evidence, {"kpi_key": "Mystery", "actual": 1, "workbook_target": 1}])
    assert unknown.value.data["code"] == "unknown_kpi"
    assert unknown.value.data["kpi_key"] == "Mystery"


def test_operational_commit_caps_over_target_booking_at_its_weight():
    from services.dashboard_record_service import _normalise_kpi_values
    from services.legacy_kpi_evidence import build_legacy_employee_kpi_values
    from services.operational_upload_contract import operational_lines
    from services.seeding_service import DatabaseSeeder, pin_upload_score

    service = _kpi_service()
    row = _outbound_sheet(date(2026, 8, 1))
    score, _grade_name, achievements, weights = service.calculate_performance("Outbound", row)
    expected = _total(_outbound_parts(OUTBOUND_WEIGHTS))
    assert score == pytest.approx(expected, abs=0.001)
    assert expected == pytest.approx(55.0, abs=0.001)

    evidence = build_legacy_employee_kpi_values(
        "Outbound",
        row,
        achievements=achievements,
        weights=weights,
        config={"kpis": []},
    )
    by_key = {item["kpi_key"]: item for item in evidence}
    booking_contribution = min(_BOOKING_ACH, 1.0) * OUTBOUND_WEIGHTS["Booking"]
    assert by_key["Booking"]["achievement_ratio"] == pytest.approx(_BOOKING_ACH)
    assert by_key["Booking"]["achievement_ratio"] > 1
    assert by_key["Booking"]["contribution"] == pytest.approx(booking_contribution)
    assert by_key["Booking"]["weight_applied"] == pytest.approx(0.10)
    assert by_key["Attendance"]["weight_applied"] == pytest.approx(0.70)

    def _stored(items: list[dict]):
        return [
            SimpleNamespace(
                kpi_key=item["kpi_key"],
                contribution=item["contribution"],
                weight_applied=item["weight_applied"],
                achievement_ratio=item["achievement_ratio"],
            )
            for item in items
        ]

    assert DatabaseSeeder._score_from_kpi_rows(_stored(evidence)) == pytest.approx(expected, abs=0.001)
    bare = [
        SimpleNamespace(contribution=item["contribution"], weight_applied=item["weight_applied"])
        for item in evidence
    ]
    assert DatabaseSeeder._score_from_kpi_rows(bare) == pytest.approx(expected, abs=0.001)

    lines = operational_lines("Outbound", 2026, 8)
    version = SimpleNamespace(
        id="operational-commit",
        version_number=1,
        performance_level="Employee",
        position_name="",
        effective_from_year=2026,
        effective_from_month=8,
        config_snapshot={
            "contract": "operational_upload",
            "policy": "operational_upload",
            "lines": lines,
            "grade_thresholds": {"A": 95, "B": 85, "C": 75, "D": 65},
        },
    )
    pinned = pin_upload_score(
        version,
        [
            {
                "kpi_key": item["kpi_key"],
                "actual": item["actual_value"],
                "workbook_target": item["target_value"],
            }
            for item in evidence
        ],
    )
    pin_by_key = {item["kpi_key"]: item for item in pinned["rows"]}
    assert pin_by_key["Booking"]["contribution"] == pytest.approx(booking_contribution)
    assert pin_by_key["Booking"]["contribution"] == pytest.approx(pin_by_key["Booking"]["weight"])
    assert pinned["score"] == pytest.approx(expected, abs=0.001)
    pinned_rows = [
        SimpleNamespace(
            kpi_key=item["kpi_key"],
            contribution=item["contribution"],
            weight_applied=item["weight"],
            achievement_ratio=item["achievement"],
        )
        for item in pinned["rows"]
    ]
    assert DatabaseSeeder._score_from_kpi_rows(pinned_rows) == pytest.approx(expected, abs=0.001)
    assert DatabaseSeeder._score_from_kpi_rows(
        pinned_rows,
        final_total_cap=True,
    ) == pytest.approx(expected, abs=0.001)

    visible = _normalise_kpi_values(evidence, None, {}, "Outbound")
    visible_booking = next(item for item in visible if item["kpi_key"] == "Booking")
    assert visible_booking["achievement_ratio"] == pytest.approx(_BOOKING_ACH)
    assert visible_booking["contribution"] == pytest.approx(booking_contribution)


def test_inbound_upload_selects_utilization_abandon_and_aht_minutes():
    service = _kpi_service()
    supplied = _total(_inbound_parts(INBOUND_WEIGHTS, _IN_UTZ_ACH, _IN_AHT_ACH))
    zero_utz = _total(_inbound_parts(INBOUND_WEIGHTS, 0.0, _IN_AHT_ACH))
    missing_utz = _total(_inbound_parts(INBOUND_WEIGHTS, _IN_ABANDON_ACH, _IN_AHT_ACH))
    zero_aht = _total(_inbound_parts(INBOUND_WEIGHTS, _IN_UTZ_ACH, 0.0))
    june = _total(_inbound_parts(JUNE_INBOUND_WEIGHTS, _IN_UTZ_ACH, _IN_AHT_ACH))
    capped_aht = _total(_inbound_parts(INBOUND_WEIGHTS, _IN_UTZ_ACH, min(_IN_AHT_ACH, 1.0)))
    assert _IN_AHT_ACH == pytest.approx(1.25)
    assert supplied == pytest.approx(65.0, abs=0.001)
    assert zero_utz == pytest.approx(55.0, abs=0.001)
    assert missing_utz == pytest.approx(60.0, abs=0.001)
    assert zero_aht == pytest.approx(60.0, abs=0.001)
    assert supplied == capped_aht

    score, _grade_name, achievements, weights = service.calculate_performance(
        "Inbound", _inbound_sheet(date(2026, 8, 1), utz=0.85),
    )
    assert score == pytest.approx(supplied, abs=0.001)
    assert achievements["AHT"] == pytest.approx(_IN_AHT_ACH)
    assert achievements["AHT"] > 1
    assert achievements["Other"] == pytest.approx(_IN_UTZ_ACH)
    assert weights == pytest.approx(INBOUND_WEIGHTS)

    zero_score, _zero_grade, zero_achievements, zero_weights = service.calculate_performance(
        "Inbound", _inbound_sheet(date(2026, 7, 1), utz=0),
    )
    assert zero_score == pytest.approx(zero_utz, abs=0.001)
    assert zero_achievements["Other"] == pytest.approx(0.0)
    assert zero_weights["Other"] == pytest.approx(0.10)

    abandon_score, _abandon_grade, abandon_achievements, _abandon_weights = service.calculate_performance(
        "Inbound", _inbound_sheet(date(2026, 5, 1), utz=None, abandoned=2),
    )
    assert abandon_score == pytest.approx(missing_utz, abs=0.001)
    assert abandon_achievements["Other"] == pytest.approx(_IN_ABANDON_ACH)

    aht_score, _aht_grade, aht_achievements, _aht_weights = service.calculate_performance(
        "Inbound", _inbound_sheet(date(2026, 3, 1), utz=0.85, aht_minutes=0),
    )
    assert aht_score == pytest.approx(zero_aht, abs=0.001)
    assert aht_achievements["AHT"] == pytest.approx(0.0)

    june_score, _june_grade, _june_achievements, june_weights = service.calculate_performance(
        "Inbound", _inbound_sheet(date(2026, 6, 1), utz=0.85),
    )
    assert june_weights["Quality"] == pytest.approx(0.0)
    assert june_weights["Other"] == pytest.approx(0.15)
    assert june_weights["AHT"] == pytest.approx(0.05)
    assert june_score == pytest.approx(june, abs=0.001)


def test_new_drafts_follow_the_operational_contract_and_leave_coding_alone(db):
    world = _World(db)
    outbound = world.scope("Outbound")
    inbound = world.scope("Inbound")
    coding = world.scope("Coding")

    for month, quality, other in ((5, 0.10, 0.10), (7, 0.10, 0.10), (8, 0.10, 0.10), (9, 0.10, 0.10)):
        draft = world.workflow.open_draft(world.actor, outbound["id"], 2026, month)
        weights = _weights_of(draft["lines"])
        assert draft["contract"] == "operational_upload"
        assert draft["revision_choice"]["available"] is False
        assert set(weights) == {"Attendance", "Booking", "Quality", "Other"}
        assert weights["Attendance"] == pytest.approx(0.70)
        assert weights["Quality"] == pytest.approx(quality)
        assert weights["Other"] == pytest.approx(other)
        assert all(line.get("cap_each") is True for line in draft["lines"])
        assert "Productivity" not in weights

    june = world.workflow.open_draft(world.actor, outbound["id"], 2026, 6)
    june_weights = _weights_of(june["lines"])
    assert june["contract"] == "operational_upload"
    assert june_weights["Quality"] == pytest.approx(0.0)
    assert june_weights["Other"] == pytest.approx(0.20)
    assert june_weights["Attendance"] == pytest.approx(0.70)
    monitored = world.workflow.preview(world.actor, june["id"], [
        {"kpi_key": "Attendance", "actual": _ATTEND_ACTUAL, "workbook_target": _ATTEND_TARGET},
        {"kpi_key": "Booking", "actual": _BOOKING_ACTUAL, "workbook_target": _BOOKING_TARGET},
        {"kpi_key": "Quality", "actual": None, "workbook_target": _QUALITY_TARGET},
        {"kpi_key": "Other", "actual": _OTHER_ACTUAL, "workbook_target": _OTHER_TARGET},
    ])
    by_key = {row["kpi_key"]: row for row in monitored["rows"]}
    assert by_key["Quality"]["weight"] == pytest.approx(0.0)
    assert by_key["Quality"]["achievement"] is None
    assert by_key["Quality"]["contribution"] is None
    assert by_key["Quality"]["achievement_state"] == "missing_actual"
    assert by_key["Other"]["weight"] == pytest.approx(0.20)
    assert monitored["score"] == pytest.approx(_total(_outbound_parts(JUNE_OUTBOUND_WEIGHTS)), abs=0.001)

    visible = world.workflow.preview(world.actor, june["id"], [
        {"kpi_key": "Attendance", "actual": _ATTEND_ACTUAL, "workbook_target": _ATTEND_TARGET},
        {"kpi_key": "Booking", "actual": _BOOKING_ACTUAL, "workbook_target": _BOOKING_TARGET},
        {"kpi_key": "Quality", "actual": _QUALITY_ACTUAL, "workbook_target": _QUALITY_TARGET},
        {"kpi_key": "Other", "actual": _OTHER_ACTUAL, "workbook_target": _OTHER_TARGET},
    ])
    visible_quality = next(row for row in visible["rows"] if row["kpi_key"] == "Quality")
    assert visible_quality["achievement"] == pytest.approx(_QUALITY_ACH)
    assert visible_quality["contribution"] == pytest.approx(0.0)
    assert visible["score"] == pytest.approx(monitored["score"], abs=0.001)

    inbound_draft = world.workflow.open_draft(world.actor, inbound["id"], 2026, 8)
    inbound_weights = _weights_of(inbound_draft["lines"])
    labels = {line["kpi_key"]: line["label"] for line in inbound_draft["lines"]}
    assert inbound_draft["contract"] == "operational_upload"
    assert set(inbound_weights) == {"Attendance", "Booking", "Quality", "AHT", "Other"}
    assert labels["Other"] == "Abandon Rate"
    assert labels["AHT"] == "AHT (Handle Time)"
    other_line = next(line for line in inbound_draft["lines"] if line["kpi_key"] == "Other")
    aht_line = next(line for line in inbound_draft["lines"] if line["kpi_key"] == "AHT")
    assert other_line["row_selection"] == "utz_or_abandon"
    assert other_line["direction"] == "lower_better"
    assert aht_line["direction"] == "lower_better"
    assert aht_line["unit"] == "min"
    assert inbound_weights["AHT"] == pytest.approx(0.05)
    assert inbound_weights["Other"] == pytest.approx(0.10)

    coding_draft = world.workflow.open_draft(world.actor, coding["id"], 2026, 8)
    assert coding_draft["contract"] is None
    assert coding_draft["revision_choice"] is None


def test_reference_snapshots_stay_immutable_until_admin_adopts(db):
    world = _World(db)
    outbound = world.scope("Outbound")
    draft = world.workflow.open_reference_draft(world.actor, outbound["id"], 2026, 8)
    weights = _weights_of(draft["lines"])
    checksum = draft["checksum"]
    assert draft["contract"] == "reference_workbook"
    assert draft["revision_choice"]["available"] is True
    assert draft["revision_choice"]["code"] == "adopt_operational_upload"
    assert weights["Attendance"] == pytest.approx(0.60)
    assert weights["Productivity"] == pytest.approx(0.10)
    assert "Productivity" in weights

    again = world.workflow.get_version(world.actor, draft["id"])
    world.workflow.period(world.actor, outbound["id"], 2026, 8)
    stored = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    assert again["checksum"] == checksum
    assert stored.config_checksum == checksum
    assert stored.status == "draft"
    assert _weights_of(again["lines"])["Productivity"] == pytest.approx(0.10)

    world.workflow.impact_preview(world.actor, draft["id"])
    approved = world.workflow.approve(world.actor, draft["id"])
    approved_checksum = approved["checksum"]
    db.refresh(stored)
    assert stored.status == "approved"
    assert stored.config_snapshot["contract"] == "reference_workbook"
    reread = world.workflow.get_version(world.actor, approved["id"])
    assert reread["checksum"] == approved_checksum
    assert reread["contract"] == "reference_workbook"
    assert _weights_of(reread["lines"])["Attendance"] == pytest.approx(0.60)

    with pytest.raises(EvaluationConflict) as blocked:
        world.workflow.open_draft(world.actor, outbound["id"], 2026, 8)
    assert blocked.value.data["code"] == "already_approved"
    db.refresh(stored)
    assert stored.status == "approved"
    assert stored.config_checksum == approved_checksum

    with pytest.raises(EvaluationError) as unconfirmed:
        world.workflow.adopt_operational_contract(world.actor, approved["id"], confirm=False)
    assert unconfirmed.value.data["code"] == "confirmation_required"
    db.refresh(stored)
    assert stored.config_checksum == approved_checksum
    assert stored.config_snapshot["contract"] == "reference_workbook"

    adopted = world.workflow.adopt_operational_contract(world.actor, approved["id"], confirm=True)
    db.refresh(stored)
    assert adopted["id"] != approved["id"]
    assert adopted["status"] == "draft"
    assert adopted["contract"] == "operational_upload"
    assert "Productivity" not in _weights_of(adopted["lines"])
    assert stored.status == "approved"
    assert stored.config_checksum == approved_checksum
    assert stored.config_snapshot["contract"] == "reference_workbook"
    assert _weights_of(stored.config_snapshot["lines"])["Productivity"] == pytest.approx(0.10)


def _seed_outbound(world: _World, month: str, code: str) -> PerformanceRecord:
    team = world.teams["Outbound"]
    employee = world.employee(team, code)
    record = world.record(team, employee, month, "65.00", "D")
    rows = (
        ("Attendance", _ATTEND_ACTUAL, _ATTEND_TARGET, _ATTEND_ACH, 0.70, _ATTEND_ACH * 0.70),
        ("Booking", _BOOKING_ACTUAL, _BOOKING_TARGET, _BOOKING_ACH, 0.10, _BOOKING_ACH * 0.10),
        ("Quality", _QUALITY_ACTUAL, _QUALITY_TARGET, _QUALITY_ACH, 0.10, _QUALITY_ACH * 0.10),
        ("Other", _OTHER_ACTUAL, _OTHER_TARGET, _OTHER_ACH, 0.10, _OTHER_ACH * 0.10),
    )
    for key, actual, target, achievement, weight, contribution in rows:
        world.kpi(record, key, actual, target, achievement, weight, contribution)
    world.db.commit()
    return record


def _summary_score(db, actor: dict, period: str) -> tuple[float, int]:
    scope = {
        "role": "Admin",
        "user_id": actor["user_id"],
        "has_unrestricted_team_access": True,
        "legacy_unscoped": False,
        "accessible_teams": [],
        "accessible_team_levels": [],
    }
    body = PerformanceDashboardReadService(db, scope).summary(period=period, team="Outbound", trend_months=2)
    return float(body["current"]["average_score"]), int(body["data_version"])


def test_admin_target_and_weight_edits_match_from_preview_through_rollback(db):
    world = _World(db)
    outbound = world.scope("Outbound")
    may = _seed_outbound(world, "May", "SYN-MAY")
    september = _seed_outbound(world, "September", "SYN-SEP")
    may_draft = world.workflow.open_draft(world.actor, outbound["id"], 2026, 5)
    september_draft = world.workflow.open_draft(world.actor, outbound["id"], 2026, 9)
    thresholds = may_draft["grade_thresholds"]

    fixed_attendance = 0.40
    target_score = _total([
        (_ATTEND_ACTUAL / fixed_attendance) * 0.70,
        min(_BOOKING_ACH, 1.0) * 0.10,
        _QUALITY_ACH * 0.10,
        _OTHER_ACH * 0.10,
    ])
    weight_score = _total([
        min(_ATTEND_ACH, 1.0) * 0.40,
        min(_BOOKING_ACH, 1.0) * 0.20,
        min(_QUALITY_ACH, 1.0) * 0.20,
        min(_OTHER_ACH, 1.0) * 0.20,
    ])
    assert target_score == pytest.approx(90.0, abs=0.001)
    assert weight_score == pytest.approx(60.0, abs=0.001)

    may_edited = world.workflow.edit_draft(
        world.actor, may_draft["id"], _edit_target(may_draft["lines"], "Attendance", fixed_attendance),
    )
    september_edited = world.workflow.edit_draft(
        world.actor,
        september_draft["id"],
        _edit_weights(september_draft["lines"], {
            "Attendance": 0.40,
            "Booking": 0.20,
            "Quality": 0.20,
            "Other": 0.20,
        }),
    )
    assert _weights_of(may_edited["lines"])["Attendance"] == pytest.approx(0.70)
    assert next(line for line in may_edited["lines"] if line["kpi_key"] == "Attendance")["target"] == fixed_attendance
    assert _weights_of(september_edited["lines"]) == pytest.approx({
        "Attendance": 0.40, "Booking": 0.20, "Quality": 0.20, "Other": 0.20,
    })

    cached_score, cached_version = _summary_score(db, world.actor, "2026-05")
    assert cached_score == pytest.approx(65.0, abs=0.001)

    may_preview = world.workflow.impact_preview(world.actor, may_edited["id"])
    september_preview = world.workflow.impact_preview(world.actor, september_edited["id"])
    assert may_preview["comparisons"][0]["after_score"] == pytest.approx(target_score, abs=0.001)
    assert may_preview["comparisons"][0]["after_grade"] == _grade(target_score, thresholds)
    assert may_preview["writes"] == 0
    assert september_preview["comparisons"][0]["after_score"] == pytest.approx(weight_score, abs=0.001)
    booking = next(item for item in may_preview["comparisons"][0]["kpis"] if item["kpi_key"] == "Booking")
    assert booking["after_achievement"] == pytest.approx(_BOOKING_ACH)
    assert booking["after_achievement"] > 1

    may_approved = world.workflow.approve(world.actor, may_edited["id"])
    may_applied = world.workflow.apply(world.actor, outbound["id"], 2026, 5)
    assert may_applied["records"][0]["score"] == pytest.approx(may_preview["comparisons"][0]["after_score"], abs=0.001)
    may_row = _reload(db, may.id, 2026)
    september_row = _reload(db, september.id, 2026)
    assert float(may_row.score) == pytest.approx(target_score, abs=0.001)
    assert may_row.grade == _grade(target_score, thresholds)
    evidence = may_row.record_payload["source_evidence"]["kpis"]
    assert evidence["Attendance"]["actual"] == "0.4"
    assert evidence["Attendance"]["target"] == "0.8"
    assert evidence["Booking"]["actual"] == "0.6"
    assert float(_kpi_map(may_row)["Attendance"].target_value) == pytest.approx(fixed_attendance)
    assert float(_kpi_map(may_row)["Attendance"].actual_value) == pytest.approx(_ATTEND_ACTUAL)
    assert float(september_row.score) == pytest.approx(65.0, abs=0.001)
    assert september_row.record_payload.get("source_evidence") is None
    assert float(_kpi_map(september_row)["Attendance"].target_value) == pytest.approx(_ATTEND_TARGET)
    assert float(_kpi_map(september_row)["Booking"].actual_value) == pytest.approx(_BOOKING_ACTUAL)

    applied_score, applied_version = _summary_score(db, world.actor, "2026-05")
    assert applied_score == pytest.approx(target_score, abs=0.001)
    assert applied_version > cached_version
    may_read = world.workflow.reads(world.actor, outbound["id"], 2026, [5])["periods"][0]
    assert may_read["pinned"] is True
    assert may_read["basis_state"] == "pinned"
    assert may_read["stored_score"] == pytest.approx(target_score, abs=0.001)
    trend = PerformanceDashboardReadService(db, {
        "role": "Admin",
        "user_id": world.actor["user_id"],
        "has_unrestricted_team_access": True,
        "legacy_unscoped": False,
        "accessible_teams": [],
    }).summary(period="2026-05", team="Outbound", trend_months=2)
    may_trend = next(item for item in trend["trend"] if item["month"] == "May")
    assert may_trend["average_score"] == pytest.approx(target_score, abs=0.001)

    world.workflow.approve(world.actor, september_edited["id"])
    september_applied = world.workflow.apply(world.actor, outbound["id"], 2026, 9)
    assert september_applied["records"][0]["score"] == pytest.approx(weight_score, abs=0.001)
    may_row = _reload(db, may.id, 2026)
    september_row = _reload(db, september.id, 2026)
    assert float(september_row.score) == pytest.approx(weight_score, abs=0.001)
    assert september_row.record_payload["source_evidence"]["kpis"]["Attendance"]["target"] == "0.8"
    assert float(_kpi_map(september_row)["Attendance"].actual_value) == pytest.approx(_ATTEND_ACTUAL)
    assert float(may_row.score) == pytest.approx(target_score, abs=0.001)
    assert may_row.record_payload["source_evidence"]["kpis"]["Attendance"]["target"] == "0.8"

    september_read = world.workflow.reads(world.actor, outbound["id"], 2026, [9])["periods"][0]
    assert september_read["stored_score"] == pytest.approx(weight_score, abs=0.001)
    september_revision = september_applied["revision_id"]
    rolled_september = world.workflow.rollback(world.actor, september_revision)
    assert rolled_september["status"] == "rolled_back"
    september_row = _reload(db, september.id, 2026)
    may_row = _reload(db, may.id, 2026)
    assert float(september_row.score) == pytest.approx(65.0, abs=0.001)
    assert float(_kpi_map(september_row)["Attendance"].target_value) == pytest.approx(_ATTEND_TARGET)
    assert float(_kpi_map(september_row)["Attendance"].weight_applied) == pytest.approx(0.70)
    assert float(may_row.score) == pytest.approx(target_score, abs=0.001)

    may_revision = may_applied["revision_id"]
    rolled_may = world.workflow.rollback(world.actor, may_revision)
    assert rolled_may["status"] == "rolled_back"
    restored_score, restored_version = _summary_score(db, world.actor, "2026-05")
    assert restored_score == pytest.approx(65.0, abs=0.001)
    assert restored_version > applied_version
    may_row = _reload(db, may.id, 2026)
    assert float(may_row.score) == pytest.approx(65.0, abs=0.001)
    assert float(_kpi_map(may_row)["Attendance"].target_value) == pytest.approx(_ATTEND_TARGET)
    restored_read = world.workflow.reads(world.actor, outbound["id"], 2026, [5])["periods"][0]
    assert restored_read["stored_score"] == pytest.approx(65.0, abs=0.001)
    assert restored_read["basis_state"] == "legacy"
    history = world.workflow.period(world.actor, outbound["id"], 2026, 5)
    assert {item["status"] for item in history["revisions"]} == {"rolled_back"}


def test_guards_reject_bad_weights_checksums_scope_conflicts_and_missing_actuals(db):
    world = _World(db)
    outbound = world.scope("Outbound")
    draft = world.workflow.open_draft(world.actor, outbound["id"], 2026, 10)
    checksum = draft["checksum"]

    with pytest.raises(EvaluationError) as bad_total:
        world.workflow.edit_draft(
            world.actor,
            draft["id"],
            _edit_weights(draft["lines"], {key: 0.10 for key in ("Attendance", "Booking", "Quality", "Other")}),
        )
    assert bad_total.value.data["code"] == "invalid_weight_total"
    stored = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    assert stored.config_checksum == checksum
    assert _weights_of(stored.config_snapshot["lines"])["Attendance"] == pytest.approx(0.70)

    with pytest.raises(EvaluationConflict) as stale:
        world.workflow.edit_draft(
            world.actor,
            draft["id"],
            _edit_target(draft["lines"], "Attendance", 0.50),
            expected_checksum="f" * 64,
        )
    assert stale.value.data["code"] == "stale_draft"
    db.refresh(stored)
    assert stored.config_checksum == checksum

    edited = world.workflow.edit_draft(
        world.actor, draft["id"], _edit_target(draft["lines"], "Attendance", 0.50),
    )
    with pytest.raises(TargetConflict) as conflict:
        world.workflow.preview(world.actor, edited["id"], [
            {"kpi_key": "Attendance", "actual": _ATTEND_ACTUAL, "workbook_target": _ATTEND_TARGET},
            {"kpi_key": "Booking", "actual": _BOOKING_ACTUAL, "workbook_target": _BOOKING_TARGET},
            {"kpi_key": "Quality", "actual": _QUALITY_ACTUAL, "workbook_target": _QUALITY_TARGET},
            {"kpi_key": "Other", "actual": _OTHER_ACTUAL, "workbook_target": _OTHER_TARGET},
        ])
    assert conflict.value.data["code"] == "target_conflict"
    assert conflict.value.data["conflicts"][0]["kpi_key"] == "Attendance"

    with pytest.raises(EvaluationError) as missing:
        world.workflow.preview(world.actor, edited["id"], [
            {"kpi_key": "Attendance", "actual": None, "workbook_target": 0.50},
            {"kpi_key": "Booking", "actual": _BOOKING_ACTUAL, "workbook_target": _BOOKING_TARGET},
            {"kpi_key": "Quality", "actual": _QUALITY_ACTUAL, "workbook_target": _QUALITY_TARGET},
            {"kpi_key": "Other", "actual": _OTHER_ACTUAL, "workbook_target": _OTHER_TARGET},
        ])
    assert missing.value.data["code"] == "missing_actual"
    assert missing.value.data["kpi_key"] == "Attendance"

    zero = world.workflow.preview(world.actor, edited["id"], [
        {"kpi_key": "Attendance", "actual": 0, "workbook_target": 0.50},
        {"kpi_key": "Booking", "actual": _BOOKING_ACTUAL, "workbook_target": _BOOKING_TARGET},
        {"kpi_key": "Quality", "actual": _QUALITY_ACTUAL, "workbook_target": _QUALITY_TARGET},
        {"kpi_key": "Other", "actual": _OTHER_ACTUAL, "workbook_target": _OTHER_TARGET},
    ])
    attendance = next(row for row in zero["rows"] if row["kpi_key"] == "Attendance")
    assert attendance["achievement"] == pytest.approx(0.0)
    assert attendance["contribution"] == pytest.approx(0.0)

    bare = world.workflow.open_draft(world.actor, outbound["id"], 2026, 11)
    with pytest.raises(EvaluationConflict) as no_preview:
        world.workflow.approve(world.actor, bare["id"])
    assert no_preview.value.data["code"] == "preview_required"

    record = _seed_outbound(world, "November", "SYN-NOV")
    quality = next(value for value in record.kpi_values if value.kpi_key == "Quality")
    world.db.delete(quality)
    world.db.commit()
    with pytest.raises(EvaluationError) as stored_missing:
        world.workflow.impact_preview(world.actor, bare["id"])
    assert stored_missing.value.data["code"] == "missing_evidence"
    named = stored_missing.value.data["missing_evidence"]
    assert named[0]["kpi_key"] == "Quality"
    assert named[0]["record_id"] == str(record.id)

    world.workflow.impact_preview(world.actor, edited["id"])
    approved = world.workflow.approve(world.actor, edited["id"])
    version = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(approved["id"])).one()
    with pytest.raises(EvaluationError) as wrong_month:
        require_approved_capability(version, team_name="Outbound", config=None, year=2026, month=9)
    assert wrong_month.value.data["code"] == "unsupported_calculation"
    assert wrong_month.value.data["capability_reason"] == "period"


def test_inbound_draft_scores_stored_actuals_and_names_a_missing_aht(db):
    world = _World(db)
    inbound = world.scope("Inbound")
    team = world.teams["Inbound"]
    employee = world.employee(team, "SYN-IN")
    record = world.record(team, employee, "April", "1.00", "E", raw={"A.UTZ%": 0.85})
    expected = _total(_inbound_parts(INBOUND_WEIGHTS, _IN_UTZ_ACH, _IN_AHT_ACH))
    stored = (
        ("Attendance", _ATTENDS / _BOOKINGS, 0.75, _IN_ATTEND_ACH, 0.70, _IN_ATTEND_ACH * 0.70),
        ("Booking", _BOOKINGS / _HANDLED, 0.45, _IN_BOOKING_ACH, 0.10, _IN_BOOKING_ACH * 0.10),
        ("Quality", 0.95, 0.95, 1.0, 0.05, 0.05),
        ("AHT", 2.0, 2.5, _IN_AHT_ACH, 0.05, _IN_AHT_ACH * 0.05),
        ("Other", 0.85, 0.85, 1.0, 0.10, 0.10),
    )
    for key, actual, target, achievement, weight, contribution in stored:
        world.kpi(record, key, actual, target, achievement, weight, contribution)
    world.db.commit()
    draft = world.workflow.open_draft(world.actor, inbound["id"], 2026, 4)
    preview = world.workflow.impact_preview(world.actor, draft["id"])
    assert preview["comparisons"][0]["after_score"] == pytest.approx(expected, abs=0.001)
    other = next(item for item in preview["comparisons"][0]["kpis"] if item["kpi_key"] == "Other")
    aht = next(item for item in preview["comparisons"][0]["kpis"] if item["kpi_key"] == "AHT")
    assert other["after_achievement"] == pytest.approx(1.0)
    assert aht["after_achievement"] == pytest.approx(_IN_AHT_ACH)
    assert aht["after_achievement"] > 1

    zero_utz = world.workflow.preview(world.actor, draft["id"], [
        {"kpi_key": "Attendance", "actual": _ATTENDS / _BOOKINGS, "workbook_target": 0.75},
        {"kpi_key": "Booking", "actual": _BOOKINGS / _HANDLED, "workbook_target": 0.45},
        {"kpi_key": "Quality", "actual": 0.95, "workbook_target": 0.95},
        {"kpi_key": "AHT", "actual": 2.0, "workbook_target": 2.5},
        {"kpi_key": "Other", "actual": 0, "workbook_target": 0.85, "direction": "higher_better"},
    ])
    assert zero_utz["score"] == pytest.approx(_total(_inbound_parts(INBOUND_WEIGHTS, 0.0, _IN_AHT_ACH)), abs=0.001)

    abandon = world.workflow.preview(world.actor, draft["id"], [
        {"kpi_key": "Attendance", "actual": _ATTENDS / _BOOKINGS, "workbook_target": 0.75},
        {"kpi_key": "Booking", "actual": _BOOKINGS / _HANDLED, "workbook_target": 0.45},
        {"kpi_key": "Quality", "actual": 0.95, "workbook_target": 0.95},
        {"kpi_key": "AHT", "actual": 2.0, "workbook_target": 2.5},
        {"kpi_key": "Other", "actual": 0.02, "workbook_target": 0.01, "direction": "lower_better"},
    ])
    assert abandon["score"] == pytest.approx(_total(_inbound_parts(INBOUND_WEIGHTS, _IN_ABANDON_ACH, _IN_AHT_ACH)), abs=0.001)

    with pytest.raises(EvaluationError) as missing:
        world.workflow.preview(world.actor, draft["id"], [
            {"kpi_key": "Attendance", "actual": _ATTENDS / _BOOKINGS, "workbook_target": 0.75},
            {"kpi_key": "Booking", "actual": _BOOKINGS / _HANDLED, "workbook_target": 0.45},
            {"kpi_key": "Quality", "actual": 0.95, "workbook_target": 0.95},
            {"kpi_key": "AHT", "actual": None, "workbook_target": 2.5},
            {"kpi_key": "Other", "actual": 0.85, "workbook_target": 0.85, "direction": "higher_better"},
        ])
    assert missing.value.data["code"] == "missing_actual"
    assert missing.value.data["kpi_key"] == "AHT"


def test_non_admin_cannot_open_or_apply_and_admin_can(db):
    world = _World(db)
    outbound = world.scope("Outbound")
    with pytest.raises(AccessDenied):
        world.workflow.open_draft(world.manager_actor, outbound["id"], 2026, 5)
    draft = world.workflow.open_draft(world.actor, outbound["id"], 2026, 5)
    assert draft["contract"] == "operational_upload"
    with pytest.raises(AccessDenied):
        world.workflow.impact_preview(world.manager_actor, draft["id"])
    with pytest.raises(AccessDenied):
        world.workflow.apply(world.manager_actor, outbound["id"], 2026, 5)


_TRACKING_WEIGHTS = {"Attendance": 0.8, "Booking": 0.0, "Quality": 0.1, "Other": 0.1}


def _cloned(lines: list[dict]) -> list[dict]:
    return [dict(line) for line in lines]


def _gate_version(month: int, lines: list[dict], *, cap: str = "final_total"):
    return SimpleNamespace(
        id="operational-gate",
        version_number=1,
        performance_level="Employee",
        position_name="",
        effective_from_year=2026,
        effective_from_month=month,
        config_snapshot={
            "contract": "operational_upload",
            "policy": "operational_upload",
            "cap": cap,
            "lines": lines,
            "grade_thresholds": {"A": 95, "B": 85, "C": 75, "D": 65},
        },
    )


def _reason(caught) -> str:
    return caught.value.data["capability_reason"]


def test_tracking_only_weight_saves_previews_applies_and_rolls_back_one_month(db):
    world = _World(db)
    outbound = world.scope("Outbound")
    may = _seed_outbound(world, "May", "SYN-TRACK")
    september = _seed_outbound(world, "September", "SYN-OTHER")
    draft = world.workflow.open_draft(world.actor, outbound["id"], 2026, 5)
    edited = world.workflow.edit_draft(
        world.actor, draft["id"], _edit_weights(draft["lines"], _TRACKING_WEIGHTS),
    )
    assert _weights_of(edited["lines"])["Booking"] == pytest.approx(0.0)
    assert edited["lines"][0]["direction"] == draft["lines"][0]["direction"]
    preview = world.workflow.impact_preview(world.actor, edited["id"])
    booking = next(item for item in preview["comparisons"][0]["kpis"] if item["kpi_key"] == "Booking")
    assert preview["comparisons"][0]["after_score"] == 50.0
    assert booking["after_achievement"] == pytest.approx(_BOOKING_ACH)
    assert booking["after_contribution"] == pytest.approx(0.0)
    assert preview["writes"] == 0
    world.workflow.approve(world.actor, edited["id"])
    applied = world.workflow.apply(world.actor, outbound["id"], 2026, 5)
    assert applied["records"][0]["score"] == 50.0
    may_row = _reload(db, may.id, 2026)
    september_row = _reload(db, september.id, 2026)
    assert float(may_row.score) == pytest.approx(50.0)
    assert float(_kpi_map(may_row)["Booking"].actual_value) == pytest.approx(_BOOKING_ACTUAL)
    assert float(_kpi_map(may_row)["Booking"].weight_applied) == pytest.approx(0.0)
    assert float(_kpi_map(may_row)["Booking"].contribution) == pytest.approx(0.0)
    assert float(september_row.score) == pytest.approx(65.0)
    assert float(_kpi_map(september_row)["Booking"].weight_applied) == pytest.approx(0.10)
    rolled = world.workflow.rollback(world.actor, applied["revision_id"])
    assert rolled["status"] == "rolled_back"
    may_row = _reload(db, may.id, 2026)
    september_row = _reload(db, september.id, 2026)
    assert float(may_row.score) == pytest.approx(65.0)
    assert float(_kpi_map(may_row)["Booking"].weight_applied) == pytest.approx(0.10)
    assert float(september_row.score) == pytest.approx(65.0)


def test_missing_tracking_evidence_is_not_scored_as_zero(db):
    world = _World(db)
    outbound = world.scope("Outbound")
    record = _seed_outbound(world, "May", "SYN-MISS")
    booking = next(value for value in record.kpi_values if value.kpi_key == "Booking")
    world.db.delete(booking)
    world.db.commit()
    draft = world.workflow.open_draft(world.actor, outbound["id"], 2026, 5)
    edited = world.workflow.edit_draft(
        world.actor, draft["id"], _edit_weights(draft["lines"], _TRACKING_WEIGHTS),
    )
    preview = world.workflow.impact_preview(world.actor, edited["id"])
    assert preview["comparisons"][0]["after_score"] == 50.0
    assert preview["writes"] == 0
    assert "Booking" not in {item["kpi_key"] for item in preview["comparisons"][0]["kpis"]}
    reloaded = _reload(db, record.id, 2026)
    assert "Booking" not in _kpi_map(reloaded)
    assert float(reloaded.score) == pytest.approx(65.0)
    sample = world.workflow.preview(world.actor, edited["id"], [
        {"kpi_key": "Attendance", "actual": _ATTEND_ACTUAL, "workbook_target": _ATTEND_TARGET},
        {"kpi_key": "Booking", "actual": None, "workbook_target": _BOOKING_TARGET},
        {"kpi_key": "Quality", "actual": _QUALITY_ACTUAL, "workbook_target": _QUALITY_TARGET},
        {"kpi_key": "Other", "actual": _OTHER_ACTUAL, "workbook_target": _OTHER_TARGET},
    ])
    absent = next(row for row in sample["rows"] if row["kpi_key"] == "Booking")
    assert absent["actual"] is None
    assert absent["achievement"] is None
    assert absent["contribution"] is None
    assert sample["score"] == 50.0


def test_june_quality_redistribution_uses_source_formula_and_evidence(db):
    from config.loader import load_team_config
    from services.seeding_service import DatabaseSeeder, pin_upload_score

    world = _World(db)
    outbound = world.scope("Outbound")
    record = _seed_outbound(world, "June", "SYN-JUNE")
    draft = world.workflow.open_draft(world.actor, outbound["id"], 2026, 6)
    assert _weights_of(draft["lines"])["Quality"] == pytest.approx(0.0)
    edited = world.workflow.edit_draft(
        world.actor,
        draft["id"],
        _edit_weights(draft["lines"], {
            "Attendance": 0.70, "Booking": 0.10, "Quality": 0.20, "Other": 0.0,
        }),
    )
    stored = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(edited["id"])).one()
    require_approved_capability(
        stored, team_name="Outbound", config=load_team_config("Outbound"), year=2026, month=6,
    )
    DatabaseSeeder._refuse_unsupported_outbound_binding(SimpleNamespace(team="Outbound", month="June"), stored, 2026)
    preview = world.workflow.impact_preview(world.actor, edited["id"])
    quality = next(item for item in preview["comparisons"][0]["kpis"] if item["kpi_key"] == "Quality")
    other = next(item for item in preview["comparisons"][0]["kpis"] if item["kpi_key"] == "Other")
    assert quality["after_achievement"] == pytest.approx(_QUALITY_ACH)
    assert quality["after_contribution"] == pytest.approx(_QUALITY_ACH * 0.20)
    assert other["weight"] == pytest.approx(0.0)
    assert other["after_contribution"] == pytest.approx(0.0)
    evidence = [
        {"kpi_key": "Attendance", "actual": _ATTEND_ACTUAL, "workbook_target": _ATTEND_TARGET},
        {"kpi_key": "Booking", "actual": _BOOKING_ACTUAL, "workbook_target": _BOOKING_TARGET},
        {"kpi_key": "Quality", "actual": _QUALITY_ACTUAL, "workbook_target": _QUALITY_TARGET},
        {"kpi_key": "Other", "actual": _OTHER_ACTUAL, "workbook_target": _OTHER_TARGET},
    ]
    pinned = pin_upload_score(stored, evidence)
    pinned_quality = next(item for item in pinned["rows"] if item["kpi_key"] == "Quality")
    assert pinned_quality["achievement"] == pytest.approx(_QUALITY_ACH)
    assert pinned_quality["contribution"] == pytest.approx(_QUALITY_ACH * 0.20)
    with pytest.raises(EvaluationError) as omitted:
        pin_upload_score(stored, [row for row in evidence if row["kpi_key"] != "Quality"])
    assert omitted.value.data["code"] == "incomplete_evidence"
    assert "Quality" in omitted.value.data["missing"]
    quality_row = next(value for value in record.kpi_values if value.kpi_key == "Quality")
    world.db.delete(quality_row)
    world.db.commit()
    with pytest.raises(EvaluationError) as missing:
        world.workflow.impact_preview(world.actor, edited["id"])
    assert missing.value.data["code"] == "missing_evidence"
    assert missing.value.data["missing_evidence"][0]["kpi_key"] == "Quality"


def test_operational_gate_rejects_identity_direction_cap_and_nonfinite_weights():
    from config.loader import load_team_config
    from services.operational_upload_contract import operational_lines
    from services.outbound_period_basis import period_capability

    config = load_team_config("Outbound")
    base = _cloned(operational_lines("Outbound", 2026, 5))
    tracking = _cloned(base)
    for line in tracking:
        line["weight"] = _TRACKING_WEIGHTS[line["kpi_key"]]
    allowed = require_approved_capability(
        _gate_version(5, tracking), team_name="Outbound", config=config, year=2026, month=5,
    )
    assert allowed.allows_ratio_edit is True

    unknown = _cloned(base) + [{
        "kpi_key": "Productivity", "weight": 0.0, "direction": "higher_better", "cap_each": False,
    }]
    with pytest.raises(EvaluationError) as unknown_key:
        require_approved_capability(_gate_version(5, unknown), team_name="Outbound", config=config, year=2026, month=5)
    assert _reason(unknown_key) == "kpi_key"

    duplicate = _cloned(base)
    duplicate.append(dict(duplicate[1]))
    with pytest.raises(EvaluationError) as repeated:
        require_approved_capability(_gate_version(5, duplicate), team_name="Outbound", config=config, year=2026, month=5)
    assert _reason(repeated) == "duplicate_kpi"

    missing = [line for line in _cloned(base) if line["kpi_key"] != "Booking"]
    for line in missing:
        if line["kpi_key"] == "Attendance":
            line["weight"] = 0.80
    with pytest.raises(EvaluationError) as scored_missing:
        require_approved_capability(_gate_version(5, missing), team_name="Outbound", config=config, year=2026, month=5)
    assert _reason(scored_missing) == "scored_keys"

    lowered = _cloned(base)
    lowered[0]["direction"] = "lower_better"
    with pytest.raises(EvaluationError) as direction:
        require_approved_capability(_gate_version(5, lowered), team_name="Outbound", config=config, year=2026, month=5)
    assert _reason(direction) == "direction"

    legacy_cap_flag = _cloned(base)
    legacy_cap_flag[0]["cap_each"] = False
    require_approved_capability(
        _gate_version(5, legacy_cap_flag), team_name="Outbound", config=config, year=2026, month=5,
    )
    with pytest.raises(EvaluationError) as snapshot_cap:
        require_approved_capability(
            _gate_version(5, _cloned(base), cap="per_kpi"), team_name="Outbound", config=config, year=2026, month=5,
        )
    assert _reason(snapshot_cap) == "cap"

    nonfinite = _cloned(base)
    nonfinite[0]["weight"] = float("nan")
    with pytest.raises(EvaluationError) as weight:
        require_approved_capability(_gate_version(5, nonfinite), team_name="Outbound", config=config, year=2026, month=5)
    assert _reason(weight) == "weight"

    inbound = _cloned(operational_lines("Inbound", 2026, 4))
    for line in inbound:
        if line["kpi_key"] == "Other":
            line["row_selection"] = "fixed_other"
    with pytest.raises(EvaluationError) as selection:
        require_approved_capability(
            _gate_version(4, inbound), team_name="Inbound", config=load_team_config("Inbound"), year=2026, month=4,
        )
    assert _reason(selection) == "row_selection"

    reference = _cloned(period_capability(2026, 8)["lines"])
    for line in reference:
        if line["kpi_key"] == "Booking":
            line["weight"] = 0.0
    reference_version = SimpleNamespace(
        performance_level="Employee",
        position_name="",
        effective_from_year=2026,
        effective_from_month=8,
        config_snapshot={"policy": "employee_ratio", "lines": reference},
    )
    with pytest.raises(EvaluationError) as canonical:
        require_approved_capability(reference_version, team_name="Outbound", config=config, year=2026, month=8)
    assert _reason(canonical) == "scored_keys"


def test_operational_binding_uses_mapped_keys_not_baseline_positive_weights():
    from services.operational_upload_contract import operational_lines
    from services.outbound_period_basis import OutboundUnsupportedApprovedBinding
    from services.seeding_service import DatabaseSeeder

    lines = _cloned(operational_lines("Outbound", 2026, 5))
    for line in lines:
        line["weight"] = _TRACKING_WEIGHTS[line["kpi_key"]]
    version = _gate_version(5, lines)
    DatabaseSeeder._refuse_unsupported_outbound_binding(SimpleNamespace(team="Outbound", month="May"), version, 2026)
    dropped = [line for line in lines if line["kpi_key"] != "Booking"]
    with pytest.raises(OutboundUnsupportedApprovedBinding):
        DatabaseSeeder._refuse_unsupported_outbound_binding(
            SimpleNamespace(team="Outbound", month="May"), _gate_version(5, dropped), 2026,
        )


def _adopt_app(world: _World):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routers.evaluation_settings import router
    from config.database import get_db

    app = FastAPI()
    app.include_router(router, prefix="/evaluation")
    holder = {"user": dict(world.actor)}

    @app.middleware("http")
    async def actor(request, call_next):
        if holder["user"]:
            request.state.user = holder["user"]
        return await call_next(request)

    def session():
        yield world.db

    app.dependency_overrides[get_db] = session
    return app, holder, TestClient


def test_stale_adoption_keeps_the_newer_edit_and_requires_a_checksum(db):
    world = _World(db)
    outbound = world.scope("Outbound")
    draft = world.workflow.open_reference_draft(world.actor, outbound["id"], 2026, 8)
    edited = world.workflow.edit_draft(world.actor, draft["id"], _edit_target(draft["lines"], "Booking", 0.4))
    app, holder, client_type = _adopt_app(world)
    route = f'/evaluation/versions/{draft["id"]}/adopt-operational'
    with client_type(app) as client:
        stale = client.post(route, json={"confirm": True, "expected_checksum": draft["checksum"]})
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "stale_draft"
        missing = client.post(route, json={"confirm": True})
        assert missing.status_code == 409
        assert missing.json()["detail"]["code"] == "draft_precondition_required"
        holder["user"] = dict(world.manager_actor)
        denied = client.post(f"/evaluation/versions/{uuid.uuid4()}/adopt-operational", json={"confirm": True})
        assert denied.status_code == 403
        detail = denied.json()["detail"]
        if isinstance(detail, dict):
            assert detail.get("code") not in {"not_found", "stale_draft", "draft_precondition_required"}
        holder["user"] = {"user_id": world.manager_actor["user_id"], "role": "Admin"}
        spoofed = client.post(f"/evaluation/versions/{uuid.uuid4()}/adopt-operational", json={"confirm": True})
        assert spoofed.status_code == 403
        disabled = _user("Admin", "disabled-admin")
        disabled.is_active = False
        db.add(disabled)
        db.commit()
        holder["user"] = {"user_id": str(disabled.id), "role": "Admin"}
        inactive = client.post(f"/evaluation/versions/{uuid.uuid4()}/adopt-operational", json={"confirm": True})
        assert inactive.status_code == 403
    stored = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    assert stored.config_checksum == edited["checksum"]
    assert stored.config_snapshot["contract"] == "reference_workbook"
    booking = next(line for line in stored.config_snapshot["lines"] if line["kpi_key"] == "Booking")
    assert booking["target"] == pytest.approx(0.4)
    adopted = world.workflow.adopt_operational_contract(
        world.actor, draft["id"], confirm=True, expected_checksum=edited["checksum"], require_precondition=True,
    )
    db.refresh(stored)
    assert adopted["id"] == draft["id"]
    assert adopted["contract"] == "operational_upload"
    assert adopted["checksum"] != edited["checksum"]
    assert "Adopted the operational upload contract." in (adopted["notes"] or "")
    assert "Productivity" not in _weights_of(adopted["lines"])
    assert stored.config_snapshot["contract"] == "operational_upload"


def test_already_operational_adoption_does_not_reset_edits(db):
    world = _World(db)
    outbound = world.scope("Outbound")
    may = _seed_outbound(world, "May", "SYN-IDEM")
    draft = world.workflow.open_draft(world.actor, outbound["id"], 2026, 5)
    edited = world.workflow.edit_draft(
        world.actor, draft["id"], _edit_weights(draft["lines"], _TRACKING_WEIGHTS),
    )
    before = db.query(TeamConfigurationVersion).count()
    note = edited["notes"]
    with pytest.raises(EvaluationConflict) as stale:
        world.workflow.adopt_operational_contract(
            world.actor, edited["id"], confirm=True, expected_checksum="a" * 64,
        )
    assert stale.value.data["code"] == "stale_draft"
    again = world.workflow.adopt_operational_contract(
        world.actor, edited["id"], confirm=True, expected_checksum=edited["checksum"],
    )
    trusted = world.workflow.adopt_operational_contract(world.actor, edited["id"], confirm=True)
    assert again["id"] == edited["id"]
    assert again["checksum"] == edited["checksum"]
    assert again["notes"] == note
    assert trusted["checksum"] == edited["checksum"]
    assert trusted["notes"] == note
    assert _weights_of(again["lines"])["Booking"] == pytest.approx(0.0)
    assert db.query(TeamConfigurationVersion).count() == before
    world.workflow.impact_preview(world.actor, edited["id"])
    approved = world.workflow.approve(world.actor, edited["id"])
    approved_count = db.query(TeamConfigurationVersion).count()
    repeated = world.workflow.adopt_operational_contract(
        world.actor, approved["id"], confirm=True, expected_checksum=approved["checksum"],
    )
    assert repeated["id"] == approved["id"]
    assert repeated["status"] == "approved"
    assert repeated["checksum"] == approved["checksum"]
    assert db.query(TeamConfigurationVersion).count() == approved_count
    drafts = db.query(TeamConfigurationVersion).filter(
        TeamConfigurationVersion.status == "draft",
        TeamConfigurationVersion.effective_from_month == 5,
    ).count()
    assert drafts == 0
    assert float(_reload(db, may.id, 2026).score) == pytest.approx(65.0)


def test_open_apply_and_existing_draft_block_contract_adoption(db):
    import copy

    from models.models import EvaluationApplyControl, ProcessingJob
    from services.evaluation.apply_job_schema import known_actor_snapshot
    from services.evaluation.scoring import ENGINE_VERSION

    world = _World(db)
    outbound = world.scope("Outbound")
    draft = world.workflow.open_reference_draft(world.actor, outbound["id"], 2026, 8)
    edited = world.workflow.edit_draft(world.actor, draft["id"], _edit_target(draft["lines"], "Booking", 0.4))
    stored = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
    sealed = copy.deepcopy(stored.config_snapshot)
    job = ProcessingJob(
        id=uuid.uuid4(),
        kind="evaluation_apply",
        status="queued",
        requested_by_user_id=world.admin.id,
        requested_by_name=world.admin.username,
        request_json={"scope_id": outbound["id"], "year": 2026, "month": 8},
        claim_epoch=0,
        idempotency_key=f"synthetic-adopt-{uuid.uuid4().hex}",
    )
    db.add(job)
    db.flush()
    control = EvaluationApplyControl(
        job_id=job.id,
        scope_id=uuid.UUID(outbound["id"]),
        version_id=stored.id,
        team_id=world.teams["Outbound"].id,
        performance_level="Employee",
        position_name="",
        year=2026,
        month=8,
        engine_version=ENGINE_VERSION,
        rules_checksum="b" * 64,
        proof_source_fingerprint="c" * 64,
        lineage_fingerprint="d" * 64,
        requested_by_user_id=world.admin.id,
        actor_snapshot=known_actor_snapshot(world.admin.id),
        state="pending",
        claim_epoch=0,
        staged_count=0,
        promoted_count=0,
    )
    db.add(control)
    db.commit()
    with pytest.raises(EvaluationConflict) as blocked:
        world.workflow.adopt_operational_contract(
            world.actor, draft["id"], confirm=True, expected_checksum=edited["checksum"], require_precondition=True,
        )
    assert blocked.value.data["code"] == "apply_open"
    db.refresh(stored)
    assert stored.config_snapshot == sealed
    assert stored.config_checksum == edited["checksum"]
    control.state = "cancelled"
    db.commit()
    world.workflow.impact_preview(world.actor, draft["id"])
    approved = world.workflow.approve(world.actor, draft["id"])
    db.refresh(stored)
    approved_snapshot = copy.deepcopy(stored.config_snapshot)
    approved_checksum = stored.config_checksum
    approved_notes = stored.notes
    approved_number = stored.version_number
    revised = world.workflow.revise(world.actor, approved["id"])
    with pytest.raises(EvaluationConflict) as conflict:
        world.workflow.adopt_operational_contract(world.actor, stored.id, confirm=True)
    assert conflict.value.data["code"] == "draft_exists"
    assert conflict.value.data["draft_id"] == revised["id"]
    db.refresh(stored)
    assert stored.status == "approved"
    assert stored.version_number == approved_number
    assert stored.config_checksum == approved_checksum
    assert stored.config_snapshot == approved_snapshot
    assert stored.notes == approved_notes
    assert revised["source_version_id"] == approved["id"]
    converted = world.workflow.adopt_operational_contract(
        world.actor, revised["id"], confirm=True, expected_checksum=revised["checksum"],
    )
    assert converted["id"] == revised["id"]
    assert converted["contract"] == "operational_upload"
    assert converted["source_version_id"] == approved["id"]
    assert converted["source_checksum"] == approved_checksum
    db.refresh(stored)
    assert stored.status == "approved"
    assert stored.config_checksum == approved_checksum
    assert stored.config_snapshot == approved_snapshot
    assert stored.notes == approved_notes
