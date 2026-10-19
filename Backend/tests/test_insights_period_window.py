"""The Insights workspace with sections resolves only the months they read, and answers exactly as with every record.

``InsightsService(period_window=False)`` resolves every record, as before the window. Each case below builds the
workspace both ways on the same database and compares the JSON byte for byte. The synthetic data has months with
gaps, a month with no records, duplicate records, and employees whose planning history lies years before the window
(the classification reads the two records before the current month, wherever they fall).

The same comparison runs on a real workbook, as uploaded and with every record copied into the two years before,
when PMS_INSIGHTS_WINDOW_WORKBOOK names the workbook. Without it that test is skipped.
"""

import copy
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Base, Employee, KPIValue, PerformanceRecord, Team
from services.database_record_source import DatabaseRecordSource
from services.insights_service import PERIOD_WINDOW_SECTIONS, InsightsService
from services.planning_service import PlanningService

PAGE_SECTIONS = (
    "summary", "options", "comparison", "executive_story", "priority_insights", "people_contribution_analysis",
    "kpi_trend", "kpi_diagnosis", "tracking_indicators",
)
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
TEAMS = {"Window North": "DXB", "Window South": "SHJ"}


def _scope(role: str, **extra) -> dict:
    scope = {
        "role": role, "user_id": "", "employee_id": "", "accessible_teams": [], "accessible_functions": [],
        "accessible_regions": [], "accessible_branches": [], "accessible_team_levels": [],
        "has_unrestricted_team_access": False, "is_self_only": False, "active_team_names": list(TEAMS),
        "legacy_unscoped": False,
    }
    scope.update(extra)
    return scope


SCOPES = {
    "Admin": _scope("Admin", has_unrestricted_team_access=True, accessible_teams=list(TEAMS)),
    "Manager": _scope("Manager", accessible_teams=["Window North"],
                      accessible_team_levels=[("Window North", "Employee")]),
    "Regional Manager": _scope("Regional Manager", accessible_regions=["SHJ"]),
    "Function Director": _scope("Function Director", accessible_functions=["Window South"]),
    "Executive": _scope("Executive", employee_id="WIN-003"),
}

# Each employee's (year, month number, score, position) records. Scores below 70 in two adjacent months make
# employee risks, which carry the planning classification; WIN-001's falling scores reach back to 2025, so its
# attrition risk in September 2026 is decided by a record far before the window. WIN-004 holds two records for
# August 2026 and WIN-007 two for June 2024 (duplicates). No record exists for May 2026. WIN-006's records carry an empty region and WIN-007's no
# position, so both fall back to the employee's.
HISTORY = {
    "WIN-001": ("Window North", "Agent", [(2025, 1, 68), (2026, 8, 60), (2026, 9, 55)]),
    "WIN-002": ("Window North", "Agent", [(2025, 2, 95), (2025, 3, 94), (2026, 4, 92), (2026, 9, 66), (2026, 8, 64)]),
    "WIN-003": ("Window North", "Senior Agent", [(2025, 12, 40), (2026, 3, 75), (2026, 6, 58), (2026, 7, 52),
                                                 (2026, 8, 61), (2026, 9, 49), (2026, 10, 47)]),
    "WIN-004": ("Window South", "Agent", [(2025, 6, 85), (2026, 7, 88), (2026, 8, 69), (2026, 8, 67), (2026, 9, 62)]),
    "WIN-005": ("Window South", "Coordinator", [(2024, 11, 91), (2025, 1, 93), (2026, 9, 96), (2026, 10, 97)]),
    "WIN-006": ("Window South", "Agent", [(2026, 1, 72), (2026, 2, 66), (2026, 3, 64), (2026, 4, 63), (2026, 6, 57),
                                          (2026, 7, 59)]),
    "WIN-007": ("Window North", "Coordinator", [(2024, 6, 50), (2024, 6, 52)]),
}


def _kpis(score: float) -> list[tuple[str, float, float, float]]:
    """(key, actual, target, weight) whose contributions add up to the score."""
    quality = min(score + 7, 100.0)
    attendance = max((score - quality * 0.6) / 0.4, 0.0)
    return [("quality_score", quality, 100.0, 0.6), ("attendance_rate", attendance, 100.0, 0.4)]


def _seed(db: Session) -> None:
    teams = {}
    for name, region in TEAMS.items():
        team = Team(id=uuid.uuid4(), name=name, db_name=name, region=region, team_level="employee", is_active=True)
        db.add(team)
        teams[name] = team
    for code, (team_name, position, records) in HISTORY.items():
        employee = Employee(id=uuid.uuid4(), employee_id=code, name=f"Window {code}", team_id=teams[team_name].id,
                            region=TEAMS[team_name], position_name=position)
        db.add(employee)
        for year, month, score in records:
            record_id = uuid.uuid4()
            db.add(PerformanceRecord(
                id=record_id, year=year, employee_id=employee.id, team_id=teams[team_name].id, month=MONTHS[month - 1],
                performance_level="Employee", position_name=None if code == "WIN-007" else position, score=score,
                # An empty record region falls back to the employee's, as in the resolver.
                region="" if code == "WIN-006" else None,
                grade="A" if score >= 95 else "B" if score >= 85 else "C" if score >= 75 else "D" if score >= 65 else "E",
                status="Meets" if score >= 70 else "Below",
            ))
            for key, actual, target, weight in _kpis(score):
                db.add(KPIValue(id=uuid.uuid4(), record_id=record_id, record_year=year, kpi_key=key, actual_value=actual,
                                target_value=target, achievement_ratio=min(actual / target, 1.0),
                                weight_applied=weight, contribution=min(actual / target, 1.0) * weight))
    db.commit()


def _synthetic_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        _seed(db)
    return engine


def _build(db: Session, scope: dict, filters: dict, sections, *, window: bool) -> tuple[str, bool]:
    source = DatabaseRecordSource(db)
    service = InsightsService(source, PlanningService(source, db=db), db=db, period_window=window)
    used = []
    windowed_records = service._windowed_records

    def recording(*args, **kwargs):
        result = windowed_records(*args, **kwargs)
        used.append(result is not None)
        return result

    service._windowed_records = recording
    try:
        text = service.generate_workspace(scope, sections=sections, **filters).model_dump_json()
    except Exception as exc:  # both paths must fail the same way
        text = f"{type(exc).__name__}: {exc}"
    return text, any(used)


def _compare(engine, cases) -> int:
    windowed_cases = 0
    with Session(engine) as db:
        for label, scope, filters, sections in cases:
            full, full_used = _build(db, scope, filters, sections, window=False)
            windowed, window_used = _build(db, scope, filters, sections, window=True)
            assert not full_used, label
            assert windowed == full, label
            windowed_cases += window_used
    return windowed_cases


def _synthetic_cases():
    months = [("latest completed", {})] + [
        (f"{MONTHS[month - 1]} {year}", {"year": year, "month": MONTHS[month - 1]})
        for year, month in ((2026, 10), (2026, 9), (2026, 8), (2026, 6), (2026, 5), (2026, 1), (2025, 1), (2024, 6))
    ]
    filters = [
        ("no filter", {}), ("team", {"team": "Window North"}), ("function", {"function": "Window South"}),
        ("region", {"region": "SHJ"}), ("level", {"performance_level": "Employee"}), ("position", {"position": "Agent"}),
        ("employee", {"employee_id": "WIN-001"}), ("kpi", {"kpi": "quality_score"}), ("severity", {"severity": "critical"}),
        ("type", {"insight_type": "employee_risk"}), ("insight status", {"insight_status": "new"}),
    ]
    cases = []
    for month_label, month_filters in months:
        for scope_name, scope in SCOPES.items():
            cases.append((f"{scope_name} | {month_label}", scope, month_filters, PAGE_SECTIONS))
        for filter_label, extra in filters:
            cases.append((f"Admin | {month_label} | {filter_label}", SCOPES["Admin"], {**month_filters, **extra},
                          PAGE_SECTIONS))
        cases.append((f"Admin | {month_label} | every window section", SCOPES["Admin"], month_filters,
                      sorted(PERIOD_WINDOW_SECTIONS)))
    return cases


def test_the_windowed_workspace_answers_exactly_as_with_every_record():
    engine = _synthetic_engine()
    try:
        cases = _synthetic_cases()
        windowed = _compare(engine, cases)
    finally:
        engine.dispose()
    assert windowed == len(cases)


def test_the_window_resolves_only_its_months_and_the_planning_history():
    engine = _synthetic_engine()
    try:
        with Session(engine) as db:
            source = DatabaseRecordSource(db)
            service = InsightsService(source, PlanningService(source, db=db), db=db)
            windowed = service._windowed_records(SCOPES["Admin"], {"year": 2026, "month": "September"},
                                                 frozenset(PAGE_SECTIONS))
            periods = sorted({(record.year, MONTHS.index(record.month) + 1) for record in windowed.records})
            # April to September 2026, and the planning history before the window: WIN-001 January 2025, WIN-005
            # November 2024 and January 2025.
            assert periods == [(2024, 11), (2025, 1), (2026, 4), (2026, 6), (2026, 7), (2026, 8), (2026, 9)]
            assert windowed.current_period == (2026, 9)
            assert len(windowed.duplicate_source) == sum(len(records) for _, _, records in HISTORY.values())
    finally:
        engine.dispose()


def test_other_requests_resolve_every_record():
    engine = _synthetic_engine()
    try:
        with Session(engine) as db:
            source = DatabaseRecordSource(db)
            service = InsightsService(source, PlanningService(source, db=db), db=db)
            september = {"year": 2026, "month": "September"}
            assert service._windowed_records(SCOPES["Admin"], september, None) is None
            assert service._windowed_records(SCOPES["Admin"], september, frozenset({"overall_trend"})) is None
            assert service._windowed_records(SCOPES["Admin"], september, frozenset({"kpi_overview", "options"})) is None
            assert service._windowed_records(SCOPES["Admin"], {**september, "status": "Below"}, frozenset(PAGE_SECTIONS)) is None
            branch = _scope("Branch Director", accessible_branches=["DXB"])
            assert service._windowed_records(branch, september, frozenset(PAGE_SECTIONS)) is None
            assert InsightsService(source, PlanningService(source, db=db), db=db, period_window=False)._windowed_records(
                SCOPES["Admin"], september, frozenset(PAGE_SECTIONS)
            ) is None
    finally:
        engine.dispose()


def _workbook_engine(workbook: Path, copies: int):
    import services.seeding_service as seeding_service
    from services.seeding_service import DatabaseSeeder

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    previous = seeding_service.SessionLocal
    seeding_service.SessionLocal = sessionmaker(bind=engine)
    try:
        DatabaseSeeder().process_uploaded_file("PMS_Trend_All.xlsx", workbook.read_bytes())
    finally:
        seeding_service.SessionLocal = previous
    with Session(engine) as db:
        originals = db.query(PerformanceRecord).all()
        record_columns = [column.key for column in PerformanceRecord.__table__.columns]
        value_columns = [column.key for column in KPIValue.__table__.columns]
        for offset in range(1, copies):
            for record in originals:
                data = {key: getattr(record, key) for key in record_columns}
                data["id"] = uuid.uuid4()
                data["year"] = record.year - offset
                payload = copy.deepcopy(record.record_payload)
                if isinstance(payload, dict) and "year" in payload:
                    payload["year"] = data["year"]
                data["record_payload"] = payload
                db.add(PerformanceRecord(**data))
                for value in record.kpi_values:
                    value_data = {key: getattr(value, key) for key in value_columns}
                    value_data.update(id=uuid.uuid4(), record_id=data["id"], record_year=data["year"])
                    db.add(KPIValue(**value_data))
        db.commit()
    return engine


@pytest.mark.parametrize("copies", [1, 3])
def test_the_windowed_workspace_matches_on_a_real_workbook(copies):
    workbook = os.environ.get("PMS_INSIGHTS_WINDOW_WORKBOOK")
    if not workbook:
        pytest.skip("PMS_INSIGHTS_WINDOW_WORKBOOK is not set")
    engine = _workbook_engine(Path(workbook), copies)
    try:
        with Session(engine) as db:
            rows = db.query(Team.name, Employee.employee_id, PerformanceRecord.region, PerformanceRecord.position_name,
                            PerformanceRecord.year, PerformanceRecord.month).join(
                Team, PerformanceRecord.team_id == Team.id).join(Employee, PerformanceRecord.employee_id == Employee.id).all()
        teams = sorted({row[0] for row in rows})
        regions = sorted({row[2] for row in rows if row[2]})
        positions = sorted({row[3] for row in rows if row[3]})
        periods = sorted({(row[4], MONTHS.index(row[5]) + 1) for row in rows})
        months = [("latest completed", {})] + [
            (f"{MONTHS[month - 1]} {year}", {"year": year, "month": MONTHS[month - 1]})
            for year, month in sorted({periods[0], periods[len(periods) // 2], periods[-2], periods[-1]})
        ]
        filters = [
            ("no filter", {}), ("team", {"team": teams[0]}), ("function", {"function": "RCM"}), ("region", {"region": regions[0]}),
            ("level", {"performance_level": "Employee"}), ("position", {"position": positions[0]}),
            ("employee", {"employee_id": rows[0][1]}), ("kpi", {"kpi": "attendance"}), ("severity", {"severity": "critical"}),
        ]
        scopes = {
            "Admin": SCOPES["Admin"],
            "Manager": _scope("Manager", accessible_teams=teams[:2],
                              accessible_team_levels=[(team, "Employee") for team in teams[:2]]),
            "Regional Manager": _scope("Regional Manager", accessible_regions=regions[:1]),
            "Function Director": _scope("Function Director", accessible_functions=["Call Center"]),
        }
        cases = []
        for month_label, month_filters in months:
            for scope_name, scope in scopes.items():
                cases.append((f"{scope_name} | {month_label}", scope, month_filters, PAGE_SECTIONS))
            for filter_label, extra in filters[1:]:
                cases.append((f"Admin | {month_label} | {filter_label}", SCOPES["Admin"], {**month_filters, **extra},
                              PAGE_SECTIONS))
        windowed = _compare(engine, cases)
    finally:
        engine.dispose()
    assert windowed == len(cases)
