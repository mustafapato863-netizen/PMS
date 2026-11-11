"""Phase 3 (issue #96): source-to-response parity & RBAC matrix, plus the
read-only DB transaction guard.

Every test here compares a ``DeterministicToolRegistry`` output directly
against the canonical PMS service that owns the same data on the same
in-memory SQLite database — ``DashboardRecordService`` for records and
stored KPI rows, ``KPIService`` for KPI arithmetic and grades, and
``ManagementBSCService`` for Corporate balanced scorecards. Expected
values are recomputed from those canonical outputs inside the test, never
copied from the registry and never invented: a seeded stored score is not
the expectation, because ``DashboardRecordService`` recomputes a record's
score from its stored KPI rows when they exist (e.g. a stored 90.0 with
KPI contributions totalling 87.66 resolves to 87.66).

Coverage required by the issue:
- EGY / UAE / Shared (``Finance``, ``RCM``) / Corporate BSC scopes.
- True ``0`` vs missing (a real 0.0 score counts in averages; a period
  with no rows is an honest empty result, never another month's data).
- Exact score ties (never a single winner), duplicate first names across
  teams/countries, unpublished periods, tracking-only vs scored KPIs, and
  cross-team / cross-country / non-Admin RBAC rejection.
- The read-only guard: ``flush()`` / staged writes raise
  ``RuntimeError("AI read tools cannot write to the database")``; empty
  flushes stay no-ops so SQLAlchemy autoflush does not break reads.

No model is started and no production data is touched; all behaviour is
rules-only / mocked at the data layer. Labels in the test names below
that mention a catalog display string (e.g. "Booking Rate") are the
#94-sensitive surface: #94 rewrites catalog vocabulary and router
aliases, so a #94 vocabulary change may change those expected labels
(and ``metric_id`` values); the numeric parity assertions do not depend
on them.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.ai_schemas import SessionFilterContext
from models.models import (
    Employee,
    KPIValue,
    ManagementKPIConfig,
    ManagementKPISnapshot,
    PerformanceRecord,
    ProductSetting,
    Team,
)
from services.ai.catalog import ai_evidence_cache, user_can_access_branch, user_can_access_team
from services.ai.read_only_guard import (
    AI_READ_ONLY_WRITE_ERROR,
    ReadOnlySessionGuard,
    is_read_only_guarded,
    read_only_session,
)
from services.ai.tool_registry import DeterministicToolRegistry, ToolExecutionContext
from services.dashboard_record_service import DashboardRecordService
from services.insights_service import _target_achievement
from services.kpi_service import KPIService
from services.management_bsc_service import ManagementBSCService


@pytest.fixture(autouse=True)
def _clear_cache():
    ai_evidence_cache.clear()
    yield
    ai_evidence_cache.clear()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ADMIN_SCOPE = {"role": "Admin"}
SEP = ("September", 2026)
AUG = ("August", 2026)

# Inbound KPI rows shared by the tied pair (Layla / Omar) and by Ahmed's
# September row in a different mix. Contributions sum to the resolved
# score: 0.70 + 0.0933 + 0.0833 = 0.8766 -> 87.66.
_TIE_KPIS = [
    ("Attendance", 0.90, 0.65, 1.0, 0.70, 0.70),
    ("Booking", 0.28, 0.30, 0.9333, 0.10, 0.0933),
    ("Other", 0.06, 0.05, 0.8333, 0.10, 0.0833),
]
_AHMED_SEP_KPIS = [
    ("Attendance", 0.85, 0.65, 1.0, 0.70, 0.70),
    ("Booking", 0.25, 0.30, 0.8333, 0.10, 0.0833),
    ("Other", 0.04, 0.05, 1.0, 0.10, 0.10),
]
_ZERO_KPIS = [
    ("Attendance", 0.0, 0.65, 0.0, 0.70, 0.0),
    ("Booking", 0.0, 0.30, 0.0, 0.10, 0.0),
    ("Other", 0.0, 0.05, 0.0, 0.10, 0.0),
]
_AUG_KPIS = [("Attendance", 0.80, 0.65, 1.0, 0.70, 0.70)]

# Raw upload row for the Coding employee; KPIService computes the stored
# KPI rows from it, exactly as the upload pipeline would persist them.
CODING_RAW_ROW = {
    "A.QualityErrorsRate": 0.02,
    "T.QualityErrorsRate": 0.05,
    "A.RejectionRate": 0.10,
    "T.RejectionRate": 0.08,
    "A.TAT": 20,
    "T.TAT": 24,
}


def _make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add(ProductSetting(key="ai_enabled", enabled=True))
    session.commit()
    return session


def _seed_base(db):
    """Common fixture: EGY/UAE/shared rows, a tie pair, a true zero, and
    a duplicate full name across teams and countries.

    Regions follow the catalog, not the seed author's guess: Inbound and
    Outbound are Egypt-based Call Center teams (``canonical_team_region``
    is EGY for both), Coding is UAE, and "Coding EGY" is its Egypt
    counterpart. Seeding Outbound rows as UAE would make the row-region
    record filter and the catalog-region access helper disagree.
    """
    teams = {}
    for name, db_name, region, level in (
        ("Inbound", "Inbound", "EGY", "employee"),
        ("Outbound", "Outbound", "EGY", "employee"),
        ("Coding", "Coding", "UAE", "employee"),
        ("Coding EGY", "Coding EGY", "EGY", "employee"),
        ("Finance", "Finance", "All", "employee"),
        ("RCM", "RCM", "All", "employee"),
    ):
        team = Team(
            id=uuid.uuid4(),
            name=name.casefold().replace(" ", "_"),
            db_name=db_name,
            display_name=db_name,
            region=region,
            team_level=level,
            is_active=True,
        )
        db.add(team)
        teams[db_name] = team
    db.flush()

    def add(emp_code, emp_name, team_name, score, month, year=2026, region=None, kpis=None):
        team = teams[team_name]
        emp = db.query(Employee).filter_by(employee_id=emp_code).first()
        if emp is None:
            emp = Employee(
                id=uuid.uuid4(),
                employee_id=emp_code,
                name=emp_name,
                team_id=team.id,
                region=region or team.region,
                performance_level="Employee",
                is_active=True,
            )
            db.add(emp)
            db.flush()
        rec = PerformanceRecord(
            id=uuid.uuid4(),
            employee_id=emp.id,
            team_id=team.id,
            month=month,
            year=year,
            performance_level="Employee",
            region=region or team.region,
            branch_key=None,
            score=score,
            grade="B",
            status="Good",
        )
        db.add(rec)
        db.flush()
        for kpi_key, actual, target, achievement, weight, contribution in (kpis or []):
            db.add(
                KPIValue(
                    id=uuid.uuid4(),
                    record_id=rec.id,
                    record_year=year,
                    kpi_key=kpi_key,
                    actual_value=actual,
                    target_value=target,
                    achievement_ratio=achievement,
                    weight_applied=weight,
                    contribution=contribution,
                )
            )
        return rec

    # Inbound, September 2026: Ahmed is the outright best; Layla and Omar
    # tie exactly; Mona is a real measured zero.
    add("E-IN-1", "Ahmed Hassan", "Inbound", 90.0, "September", kpis=_AHMED_SEP_KPIS)
    add("E-IN-2", "Layla Nour", "Inbound", 90.0, "September", kpis=_TIE_KPIS)
    add("E-IN-3", "Omar Nour", "Inbound", 90.0, "September", kpis=_TIE_KPIS)
    add("E-IN-4", "Mona Ali", "Inbound", 0.0, "September", kpis=_ZERO_KPIS)
    # Inbound, August 2026: the trend's previous period.
    add("E-IN-1", "Ahmed Hassan", "Inbound", 80.0, "August", kpis=_AUG_KPIS)
    add("E-IN-2", "Layla Nour", "Inbound", 80.0, "August", kpis=_AUG_KPIS)
    add("E-IN-3", "Omar Nour", "Inbound", 80.0, "August", kpis=_AUG_KPIS)
    add("E-IN-4", "Mona Ali", "Inbound", 70.0, "August")
    add("E-OUT-1", "Huda Saleh", "Outbound", 90.0, "September", region="EGY",
        kpis=[("Attendance", 0.85, 0.65, 1.0, 0.70, 0.70)])
    # Coding (UAE) KPI rows are the KPIService computation on the raw row.
    coding_score, coding_grade, coding_kpis = KPIService().calculate_performance_multi_team(
        "Coding", dict(CODING_RAW_ROW)
    )
    coding_rec = add("E-COD-1", "Sara Coder", "Coding", coding_score, "September")
    for kv in coding_kpis:
        db.add(
            KPIValue(
                id=uuid.uuid4(),
                record_id=coding_rec.id,
                record_year=2026,
                kpi_key=kv["kpi_key"],
                actual_value=kv["actual_value"],
                target_value=kv["target_value"],
                achievement_ratio=kv["achievement_ratio"],
                weight_applied=kv["weight_applied"],
                contribution=kv["contribution"],
            )
        )
    # Same full name, different person / team / country: Ahmed Hassan
    # also works in Coding (UAE) and in Coding EGY (EGY). The Coding
    # namesake carries the identical KPIService-computed KPI rows as Sara
    # Coder, so Coding's KPI means are unchanged.
    coding_rec2 = add("E-COD-2", "Ahmed Hassan", "Coding", coding_score, "September")
    for kv in coding_kpis:
        db.add(
            KPIValue(
                id=uuid.uuid4(),
                record_id=coding_rec2.id,
                record_year=2026,
                kpi_key=kv["kpi_key"],
                actual_value=kv["actual_value"],
                target_value=kv["target_value"],
                achievement_ratio=kv["achievement_ratio"],
                weight_applied=kv["weight_applied"],
                contribution=kv["contribution"],
            )
        )
    add("E-CEG-2", "Ahmed Hassan", "Coding EGY", 88.0, "September", region="EGY")
    # Country RCM sub-team rows: must never enter a shared average.
    add("E-CEG-1", "Cairo Coder", "Coding EGY", 95.0, "September", region="EGY")
    # Shared All-region rows.
    add("F-1", "Karim Finance", "Finance", 86.0, "September")
    add("F-2", "Layla Finance", "Finance", 0.0, "September")
    add("R-1", "Tariq RCM", "RCM", 90.0, "September")
    add("R-2", "Mona RCM", "RCM", 84.0, "September")
    db.commit()
    return teams


def _seed_crm_bsc(db):
    """Corporate BSC dataset (CRM), seeded only for the BSC tests.

    It lives apart from the base fixture: the executive workspace counts
    management-snapshot people as a team summary, so seeding it in the
    base fixture would make executive totals exceed the canonical
    PerformanceRecord count (a pre-existing workspace behaviour, not a
    registry parity failure — see the report).
    """
    crm = Team(
        id=uuid.uuid4(),
        name="crm_management",
        db_name="crm_management",
        display_name="CRM",
        region="UAE",
        team_level="management",
        is_active=True,
    )
    db.add(crm)
    db.flush()
    # Two scored KPIs and one tracking-only KPI
    # (weight 0.0001, the catalog's tracking sentinel; a literal 0.0 weight
    # is rejected by the management_kpi_config check constraint).
    for key, label, persp, weight, target, direction, actual in (
        ("patient_satisfaction_score", "Patient Satisfaction Score", "Customer",
         0.10, 0.90, "higher_better", 0.85),
        ("initial_rejection_rate", "Initial Rejection Rate", "Internal Process",
         0.20, 0.05, "lower_better", 0.04),
        ("360_survey", "360 Survey", "Learning & Growth",
         0.0001, 0.80, "higher_better", 0.75),
    ):
        db.add(
            ManagementKPIConfig(
                id=uuid.uuid4(),
                team_id=crm.id,
                performance_level="Corporate",
                position_name="Group CRM Director",
                perspective_key=persp,
                kpi_key=key,
                kpi_label=label,
                direction=direction,
                weight=weight,
                target_value=target,
                target_unit="%",
                display_order=0,
                effective_month="September",
                effective_year=2026,
                is_active=True,
            )
        )
        db.add(
            ManagementKPISnapshot(
                id=uuid.uuid4(),
                team_id=crm.id,
                employee_identifier="CRM-DIR-1",
                employee_name="Rania Director",
                position_name="Group CRM Director",
                performance_level="Corporate",
                month="September",
                year=2026,
                perspective_key=persp,
                kpi_key=key,
                kpi_label=label,
                actual_value=actual,
            )
        )
    db.commit()


def _registry(db, scope):
    return DeterministicToolRegistry(
        ToolExecutionContext(db=db, scope=scope, session_state=SessionFilterContext())
    )


def _canonical(db, scope, **filters):
    """The canonical resolved records for a scope/filters."""
    return DashboardRecordService(db).list_records(scope=scope, **filters)


def _resolved_score(record):
    """A resolved record's stored overall score (None when missing)."""
    evaluation = getattr(record, "evaluation", None)
    raw = getattr(evaluation, "score", None) if evaluation is not None else None
    if raw is None:
        raw = getattr(record, "score", None)
    return float(raw) if raw is not None else None


def _mean_1dp(scores):
    scored = [s for s in scores if s is not None]
    assert scored, "expected at least one scored record"
    return min(100.0, round(sum(scored) / len(scored), 1))


def _kpi_map(record):
    return {str(kv.get("kpi_key")): kv for kv in (getattr(record, "kpi_values", None) or [])}


def _pct_display(value):
    return f"{float(value) * 100:.1f}%"


def _count_rows(db, model):
    return db.query(model).count()


# ---------------------------------------------------------------------------
# Read-only guard
# ---------------------------------------------------------------------------


def test_guard_blocks_flush_with_pending_writes():
    db = _make_db()
    try:
        # The inner flush raises, and the guard raises again at exit
        # because the staged write is still pending there.
        with pytest.raises(RuntimeError, match="AI read tools cannot write to the database"):
            with ReadOnlySessionGuard(db):
                db.add(
                    Team(
                        id=uuid.uuid4(),
                        name="tmp_team",
                        db_name="tmp_team",
                        display_name="tmp_team",
                        region="UAE",
                        team_level="employee",
                        is_active=True,
                    )
                )
                with pytest.raises(RuntimeError, match="AI read tools cannot write to the database"):
                    db.flush()
        db.rollback()
        assert _count_rows(db, Team) == 0
    finally:
        db.close()


def test_guard_allows_empty_flush_and_reads():
    """Autoflush runs before every query even when nothing is pending, so
    an empty flush inside the guard must stay a no-op (and reads work)."""
    db = _make_db()
    try:
        _seed_base(db)
        with read_only_session(db):
            assert is_read_only_guarded(db) is True
            db.flush()  # nothing pending: no error
            records = DashboardRecordService(db).list_records(scope=ADMIN_SCOPE)
            assert len(records) == 17
            db.flush()
        assert is_read_only_guarded(db) is False
        db.flush()  # guard restored the original flush
    finally:
        db.close()


def test_guard_blocks_commit_of_staged_write():
    db = _make_db()
    try:
        _seed_base(db)
        before = _count_rows(db, Team)
        with pytest.raises(RuntimeError, match="AI read tools cannot write to the database"):
            with ReadOnlySessionGuard(db):
                db.add(
                    Team(
                        id=uuid.uuid4(),
                        name="tmp_team",
                        db_name="tmp_team",
                        display_name="tmp_team",
                        region="UAE",
                        team_level="employee",
                        is_active=True,
                    )
                )
                db.commit()  # commit flushes first: blocked
        db.rollback()
        assert _count_rows(db, Team) == before
    finally:
        db.close()


def test_guard_rejects_dirty_session_at_entry():
    db = _make_db()
    try:
        _seed_base(db)
        db.add(
            Team(
                id=uuid.uuid4(),
                name="tmp_team",
                db_name="tmp_team",
                display_name="tmp_team",
                region="UAE",
                team_level="employee",
                is_active=True,
            )
        )
        with pytest.raises(RuntimeError, match="AI read tools cannot write to the database"):
            with ReadOnlySessionGuard(db):
                pass
        db.rollback()
        assert _count_rows(db, Team) == 6
    finally:
        db.close()


def test_guard_blocks_staged_write_by_exit():
    """A write staged inside the guard without an explicit flush is still
    caught at exit and rolled back."""
    db = _make_db()
    try:
        _seed_base(db)
        with pytest.raises(RuntimeError, match="AI read tools cannot write to the database"):
            with ReadOnlySessionGuard(db):
                db.add(
                    Team(
                        id=uuid.uuid4(),
                        name="tmp_team",
                        db_name="tmp_team",
                        display_name="tmp_team",
                        region="UAE",
                        team_level="employee",
                        is_active=True,
                    )
                )
        assert _count_rows(db, Team) == 6
        db.flush()  # original flush restored after the failed guard
    finally:
        db.close()


def test_guard_nested_collapses_to_outermost():
    db = _make_db()
    try:
        _seed_base(db)
        with ReadOnlySessionGuard(db):
            with ReadOnlySessionGuard(db):
                db.add(
                    Team(
                        id=uuid.uuid4(),
                        name="tmp_team",
                        db_name="tmp_team",
                        display_name="tmp_team",
                        region="UAE",
                        team_level="employee",
                        is_active=True,
                    )
                )
                with pytest.raises(RuntimeError, match="AI read tools cannot write to the database"):
                    db.flush()
                db.rollback()
            # Inner exit must not restore flush while the outer guard runs.
            assert is_read_only_guarded(db) is True
            db.add(
                Team(
                    id=uuid.uuid4(),
                    name="tmp_team2",
                    db_name="tmp_team2",
                    display_name="tmp_team2",
                    region="UAE",
                    team_level="employee",
                    is_active=True,
                )
            )
            with pytest.raises(RuntimeError, match="AI read tools cannot write to the database"):
                db.flush()
            db.rollback()
        assert is_read_only_guarded(db) is False
        db.flush()
    finally:
        db.close()


def test_guard_is_inactive_without_a_real_session():
    # Registry unit tests run on mock contexts with no session; the guard
    # must stay inert instead of raising, and SQLite has no read-only
    # transaction statement to apply.
    with ReadOnlySessionGuard(None):
        pass
    with ReadOnlySessionGuard(object()):
        pass
    db = _make_db()
    try:
        guard = ReadOnlySessionGuard(db)
        with guard:
            assert guard.read_only_transaction_applied is False
    finally:
        db.close()


def test_guard_wires_into_registry_entrypoints():
    """A tool call on a session carrying a staged write fails; the same
    call succeeds once the staged write is rolled back."""
    db = _make_db()
    try:
        _seed_base(db)
        reg = _registry(db, ADMIN_SCOPE)
        db.add(
            Team(
                id=uuid.uuid4(),
                name="tmp_team",
                db_name="tmp_team",
                display_name="tmp_team",
                region="UAE",
                team_level="employee",
                is_active=True,
            )
        )
        with pytest.raises(RuntimeError, match="AI read tools cannot write to the database"):
            reg.execute_shared_region_scorecard(team="Finance", month="September", year=2026)
        db.rollback()
        result = reg.execute_shared_region_scorecard(team="Finance", month="September", year=2026)
        assert result.digest["average_score"] == 43.0
        assert result.digest["total_records"] == 2
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Source-to-response parity: executive / shared scorecards
# ---------------------------------------------------------------------------


def test_executive_scores_match_canonical_records():
    db = _make_db()
    try:
        _seed_base(db)
        reg = _registry(db, ADMIN_SCOPE)
        result = reg.execute_executive_and_priority_insights(team="Inbound", month="September", year=2026)
        canonical = [
            r for r in _canonical(db, ADMIN_SCOPE, team="Inbound", month="September", year=2026)
        ]
        assert len(canonical) == 4
        assert result.digest["total_records"] == len(canonical)
        assert result.digest["average_score"] == _mean_1dp([_resolved_score(r) for r in canonical])
        assert result.digest["period"] == "September 2026"
        by_team = {t["team"].casefold(): t["score"] for t in result.digest["teams"]}
        assert by_team["inbound"] == _mean_1dp([_resolved_score(r) for r in canonical])
    finally:
        db.close()


def test_executive_all_teams_match_canonical_grouping():
    db = _make_db()
    try:
        _seed_base(db)
        reg = _registry(db, ADMIN_SCOPE)
        result = reg.execute_executive_and_priority_insights(month="September", year=2026)
        canonical = _canonical(db, ADMIN_SCOPE, month="September", year=2026)
        assert result.digest["total_records"] == len(canonical)
        assert result.digest["average_score"] == _mean_1dp([_resolved_score(r) for r in canonical])
        grouped: dict[str, list[float]] = {}
        for record in canonical:
            grouped.setdefault(str(getattr(record, "team", "")).casefold(), []).append(
                _resolved_score(record)
            )
        by_team = {t["team"].casefold(): t["score"] for t in result.digest["teams"]}
        assert set(by_team) <= set(grouped)
        assert {"inbound", "outbound", "finance", "rcm", "coding"} <= set(by_team)
        for team_key, score in by_team.items():
            assert score == _mean_1dp(grouped[team_key]), team_key
    finally:
        db.close()


def test_true_zero_counts_and_unpublished_period_is_empty():
    db = _make_db()
    try:
        _seed_base(db)
        reg = _registry(db, ADMIN_SCOPE)
        # Mona Ali's real 0.0 is one of the four Inbound September scores:
        # dropping it would change the mean, so the mean proves it counted.
        canonical = _canonical(db, ADMIN_SCOPE, team="Inbound", month="September", year=2026)
        scores = [_resolved_score(r) for r in canonical]
        assert 0.0 in scores
        assert _mean_1dp(scores) != _mean_1dp([s for s in scores if s != 0.0])
        result = reg.execute_executive_and_priority_insights(team="Inbound", month="September", year=2026)
        assert result.digest["average_score"] == _mean_1dp(scores)
        # October 2026 has no rows anywhere: honest empty, no substitution.
        empty = reg.execute_executive_and_priority_insights(team="Inbound", month="October", year=2026)
        assert empty.digest["average_score"] is None
        assert empty.digest["total_records"] == 0
        assert empty.digest["teams"] == []
        assert empty.resolved_month == "October"
        assert empty.resolved_year == 2026
    finally:
        db.close()


def test_shared_scorecards_match_canonical_and_exclude_country_rows():
    db = _make_db()
    try:
        _seed_base(db)
        reg = _registry(db, ADMIN_SCOPE)
        for team_name, expected_count in (("Finance", 2), ("RCM", 2)):
            canonical = [
                r
                for r in _canonical(db, ADMIN_SCOPE, team=team_name, month="September", year=2026)
                if str(getattr(r, "region", "") or "").strip().casefold() == "all"
            ]
            assert len(canonical) == expected_count
            result = reg.execute_shared_region_scorecard(team=team_name, month="September", year=2026)
            assert result.digest["total_records"] == expected_count
            assert result.digest["average_score"] == _mean_1dp([_resolved_score(r) for r in canonical])
            assert result.digest["period"] == "September 2026"
        # The country Coding rows (95.0 EGY, 60.0 UAE) must not leak in:
        # the RCM mean is (90 + 84) / 2 = 87.0, never (90 + 84 + 95 + 60) / 4.
        rcm = reg.execute_shared_region_scorecard(team="RCM", month="September", year=2026)
        assert rcm.digest["average_score"] == 87.0
        assert rcm.digest["average_score"] != 82.2
        finance = reg.execute_shared_region_scorecard(team="Finance", month="September", year=2026)
        # Karim 86.0 plus Layla's real 0.0: the zero counts.
        assert finance.digest["average_score"] == 43.0
    finally:
        db.close()


def test_shared_scorecard_unpublished_period_is_empty():
    db = _make_db()
    try:
        _seed_base(db)
        reg = _registry(db, ADMIN_SCOPE)
        # August is published for Inbound but has no shared Finance rows.
        for month in ("August", "October"):
            result = reg.execute_shared_region_scorecard(team="Finance", month=month, year=2026)
            assert result.digest["average_score"] is None
            assert result.digest["total_records"] == 0
            assert result.visual_cards == []
            assert result.digest["period"] == f"{month} 2026"
            assert "September" not in result.digest["period"]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Source-to-response parity: KPI diagnosis and KPIService
# ---------------------------------------------------------------------------


def test_kpi_diagnosis_matches_canonical_kpi_values():
    db = _make_db()
    try:
        _seed_base(db)
        reg = _registry(db, ADMIN_SCOPE)
        result = reg.execute_kpi_diagnosis_and_trends(team="Inbound", month="September", year=2026)
        canonical = _canonical(db, ADMIN_SCOPE, team="Inbound", month="September", year=2026)
        assert result.digest["total_records"] == len(canonical)
        assert result.digest["average_score"] == _mean_1dp([_resolved_score(r) for r in canonical])
        # Recompute each KPI's team aggregate from the canonical stored rows.
        by_key: dict[str, list[dict]] = {}
        for record in canonical:
            for key, kv in _kpi_map(record).items():
                by_key.setdefault(key, []).append(kv)
        rows = {row["kpi_key"]: row for row in result.digest["kpis"]}
        assert set(rows) == set(by_key)
        kpi_service = KPIService()
        for key, values in by_key.items():
            row = rows[key]
            actuals = [float(v["actual_value"]) for v in values]
            targets = [float(v["target_value"]) for v in values]
            mean_actual = sum(actuals) / len(actuals)
            mean_target = sum(targets) / len(targets)
            # Displays are rounded to one decimal; the means themselves are
            # exact to float noise, so compare within half a display step.
            assert abs(float(row["actual_display"].rstrip("%")) - mean_actual * 100) <= 0.06, key
            assert abs(float(row["target_display"].rstrip("%")) - mean_target * 100) <= 0.06, key
            direction = str(values[0].get("direction") or "higher_better")
            assert row["direction"] == direction, key
            expected_achievement = kpi_service._calculate_achievement(
                mean_actual, mean_target, is_inverse=(direction == "lower_better")
            )
            assert row["achievement_percent"] == pytest.approx(expected_achievement, abs=0.15), key
            weights = {round(float(v["weight_applied"]) * 100, 1) for v in values}
            assert row["weight_percent"] in weights, key
            assert row["contributes_to_score"] is True, key
            assert row["tracking_only_badge"] is None, key
            # Same rule as InsightsService._people_impacts: a person is
            # below target when the direction-aware achievement exists and
            # the weighted impact (contribution - weight, shared across the
            # people measured for this KPI) is below -0.005. A stored
            # achievement ratio alone is the wrong oracle: a 0.0 actual on
            # a lower-is-better KPI achieves 100%, and the contribution is
            # what is weighted, not the ratio.
            n_measured = len(values)
            below = 0
            for v in values:
                actual = float(v["actual_value"])
                target = float(v["target_value"])
                direction_v = str(v.get("direction") or "higher_better")
                contribution = float(v["contribution"])
                weight = float(v["weight_applied"])
                impact = (contribution * 100 - weight * 100) / n_measured
                if (
                    _target_achievement(actual, target, direction_v) is not None
                    and impact < -0.005
                ):
                    below += 1
            assert row["people_below_target"] == below, key
    finally:
        db.close()


def test_kpi_service_achievements_match_registry():
    db = _make_db()
    try:
        _seed_base(db)
        # KPIService on the raw upload row is the oracle for this employee.
        score, grade, kpi_values = KPIService().calculate_performance_multi_team(
            "Coding", dict(CODING_RAW_ROW)
        )
        assert grade == "B"
        assert round(score, 1) == 90.0
        by_key = {kv["kpi_key"]: kv for kv in kpi_values}
        assert by_key["Rejection"]["achievement_ratio"] == pytest.approx(0.8)
        reg = _registry(db, ADMIN_SCOPE)
        diagnosis = reg.execute_kpi_diagnosis_and_trends(team="Coding", month="September", year=2026)
        assert diagnosis.digest["average_score"] == round(score, 1)
        rows = {row["kpi_key"]: row for row in diagnosis.digest["kpis"]}
        assert rows["Rejection"]["actual_display"] == "10.0%"
        assert rows["Rejection"]["target_display"] == "8.0%"
        assert rows["Rejection"]["achievement_percent"] == 80.0
        assert rows["Rejection"]["weight_percent"] == 50.0
        assert rows["Rejection"]["contributes_to_score"] is True
        # The trend snapshot for the same KPI reads the same stored rows.
        trend = reg.execute_team_trend_spotlight(team="Coding", kpi="Rejection", month="September", year=2026)
        spotlight = trend.digest["team_trend_spotlight"]
        assert spotlight["score"] == 10.0
        assert spotlight["target"] == 8.0
        assert spotlight["latest_month_label"] == "September 2026"
        # Grade parity between the canonical calculator and the registry.
        assert KPIService.assign_grade(95.0) == DeterministicToolRegistry._grade_for_score(95.0) == "A"
        assert KPIService.assign_grade(90.0) == DeterministicToolRegistry._grade_for_score(90.0) == "B"
        assert KPIService.assign_grade(80.0) == DeterministicToolRegistry._grade_for_score(80.0) == "C"
        assert KPIService.assign_grade(70.0) == DeterministicToolRegistry._grade_for_score(70.0) == "D"
        assert KPIService.assign_grade(69.9) == DeterministicToolRegistry._grade_for_score(69.9) == "E"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Source-to-response parity: Corporate BSC and tracking-only KPIs
# ---------------------------------------------------------------------------


def test_management_bsc_matches_direct_service():
    db = _make_db()
    try:
        _seed_base(db)
        _seed_crm_bsc(db)
        direct = ManagementBSCService(db).build_scorecard_dataset(
            team_name="CRM",
            performance_level="Corporate",
            month="September",
            year=2026,
            employee_ids=None,
            history_months=6,
            selected_kpi=None,
            base_config={},
        )
        assert direct["scorecard"]["score"] is not None
        reg = _registry(db, ADMIN_SCOPE)
        result = reg.execute_management_balanced_scorecard(
            team="CRM", performance_level="Corporate", month="September", year=2026
        )
        assert result.digest["level"] == "Corporate"
        assert result.digest["period"] == "September 2026"
        assert result.digest["average_score"] == round(float(direct["scorecard"]["score"]), 1)
        direct_rows = {row["kpi_key"]: row for row in direct["kpi_table"]}
        digest_rows = {row["key"]: row for row in result.digest["bsc_kpis"]}
        assert set(digest_rows) == set(direct_rows)
        for key, direct_row in direct_rows.items():
            digest_row = digest_rows[key]
            assert digest_row["weight_percent"] == round(float(direct_row["weight"]) * 100, 1), key
            assert digest_row["actual_display"] == _pct_display(direct_row["actual_value"]), key
            assert digest_row["target_display"] == _pct_display(direct_row["target_value"]), key
    finally:
        db.close()


def test_tracking_only_bsc_kpi_never_contributes():
    db = _make_db()
    try:
        _seed_base(db)
        _seed_crm_bsc(db)
        reg = _registry(db, ADMIN_SCOPE)
        result = reg.execute_management_balanced_scorecard(
            team="CRM", performance_level="Corporate", month="September", year=2026
        )
        by_key = {row["key"]: row for row in result.digest["bsc_kpis"]}
        tracking = by_key["360_survey"]
        assert tracking["weight_percent"] == 0.0
        assert tracking["achievement_percent"] is None
        typed = {item.kpi_key: item for item in result.typed_evidence}
        assert typed["360_survey"].contributes_to_score is False
        assert typed["360_survey"].achievement_percent is None
        assert typed["360_survey"].actual == pytest.approx(0.75)
        assert typed["360_survey"].target == pytest.approx(0.80)
        # The scored KPIs still contribute with the direct service's scores.
        assert typed["initial_rejection_rate"].contributes_to_score is True
        assert typed["initial_rejection_rate"].achievement_percent == 100.0
        assert typed["patient_satisfaction_score"].contributes_to_score is True
        assert typed["patient_satisfaction_score"].achievement_percent == 94.4
        assert by_key["initial_rejection_rate"]["achievement_percent"] == 100.0
        assert by_key["patient_satisfaction_score"]["achievement_percent"] == 94.4
    finally:
        db.close()


def test_managerial_bsc_matches_canonical_managerial_records():
    db = _make_db()
    try:
        teams = _seed_base(db)
        inbound = teams["Inbound"]
        emp = db.query(Employee).filter_by(employee_id="E-IN-1").first()
        db.add(
            PerformanceRecord(
                id=uuid.uuid4(),
                employee_id=emp.id,
                team_id=inbound.id,
                month="September",
                year=2026,
                performance_level="Managerial",
                region="EGY",
                branch_key=None,
                score=80.0,
                grade="C",
                status="Good",
            )
        )
        db.commit()
        canonical = _canonical(
            db, ADMIN_SCOPE, team="Inbound", month="September", year=2026, performance_level="Managerial"
        )
        assert len(canonical) == 1
        reg = _registry(db, ADMIN_SCOPE)
        result = reg.execute_management_balanced_scorecard(
            team="Inbound", performance_level="Managerial", month="September", year=2026
        )
        assert result.digest["level"] == "Managerial"
        assert result.digest["average_score"] == _mean_1dp([_resolved_score(r) for r in canonical])
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Source-to-response parity: rankings, ties, duplicates, history
# ---------------------------------------------------------------------------


def test_agent_spotlight_tie_reports_both_names():
    db = _make_db()
    try:
        _seed_base(db)
        reg = _registry(db, ADMIN_SCOPE)
        result = reg.execute_agent_spotlight_and_trend(
            team="Inbound", month="September", year=2026, ranking_direction="best"
        )
        spotlight = result.digest["agent_spotlight"]
        # Ahmed (88.33) is first; Layla and Omar tie at 87.66. Whoever the
        # spotlight names, the tie must name the other one, never a single
        # winner.
        assert spotlight["entity_name"] == "Ahmed Hassan"
        assert spotlight["rank"] == 1
        assert spotlight["total_in_team"] == 4
        assert spotlight["score"] == pytest.approx(88.33, abs=0.05)
        # Rank the tied pair directly: the spotlight for the tied score
        # must list its tie partner.
        tied = reg.execute_agent_spotlight_and_trend(
            team="Inbound", month="September", year=2026, ranking_direction="best",
            employee_query="Layla Nour",
        )
        tied_spotlight = tied.digest["agent_spotlight"]
        assert tied_spotlight["entity_name"] == "Layla Nour"
        assert tied_spotlight["score"] == pytest.approx(87.66, abs=0.05)
        assert any("Omar Nour" in entry for entry in tied_spotlight["ties"])
        assert tied_spotlight["rank_label"].startswith("Rank #")
    finally:
        db.close()


def test_agent_spotlight_worst_direction_reports_tied_last_place():
    db = _make_db()
    try:
        _seed_base(db)
        reg = _registry(db, ADMIN_SCOPE)
        result = reg.execute_agent_spotlight_and_trend(
            team="Inbound", month="September", year=2026, ranking_direction="worst"
        )
        spotlight = result.digest["agent_spotlight"]
        assert spotlight["entity_name"] == "Mona Ali"
        assert spotlight["score"] == 0.0
        assert spotlight["score"] is not None  # a real zero, not a missing value
    finally:
        db.close()


def test_duplicate_first_names_are_disambiguated():
    db = _make_db()
    try:
        _seed_base(db)
        reg = _registry(db, ADMIN_SCOPE)
        inbound = reg.execute_agent_spotlight_and_trend(
            team="Inbound", month="September", year=2026, employee_query="Ahmed Hassan"
        )
        assert inbound.digest["employee_id"] == "E-IN-1"
        assert inbound.digest["team"] == "Inbound"
        coding = reg.execute_agent_spotlight_and_trend(
            team="Coding", month="September", year=2026, employee_query="Ahmed Hassan"
        )
        assert coding.digest["employee_id"] == "E-COD-2"
        assert coding.digest["team"] == "Coding"
        coding_egy = reg.execute_agent_spotlight_and_trend(
            team="Coding EGY", month="September", year=2026, employee_query="Ahmed Hassan"
        )
        assert coding_egy.digest["employee_id"] == "E-CEG-2"
        assert coding_egy.digest["team"] == "Coding EGY"
        # A Coding employee id asked for inside Coding EGY is not found:
        # no cross-team leak, and no cross-period substitution either.
        missing = reg.execute_agent_spotlight_and_trend(
            team="Coding EGY", month="September", year=2026, employee_query="E-COD-2"
        )
        assert missing.digest["spotlight"] is None
        assert missing.digest["agent_spotlight"] is None
        assert missing.records_evaluated == 0
        # Multi-month history follows the employee id, not the shared name.
        history = reg.execute_employee_multi_month_history(employee_query="E-IN-1")
        months = {
            (point["month"], point["year"]) for point in history.digest["agent_spotlight"]["all_history"]
        }
        assert months == {("August", 2026), ("September", 2026)}
        assert history.digest["agent_spotlight"]["entity_name"] == "Ahmed Hassan"
        assert history.digest["agent_spotlight"]["team"] == "Inbound"
    finally:
        db.close()


def test_spotlight_unpublished_period_is_empty():
    db = _make_db()
    try:
        _seed_base(db)
        reg = _registry(db, ADMIN_SCOPE)
        result = reg.execute_agent_spotlight_and_trend(team="Inbound", month="October", year=2026)
        assert result.digest["spotlight"] is None
        assert result.digest["agent_spotlight"] is None
        assert result.records_evaluated == 0
        assert result.visual_cards == []
        assert result.digest["period"] == "October 2026"
        assert result.resolved_month == "October"
        assert result.resolved_year == 2026
        # A named person in an unpublished period is empty too.
        named = reg.execute_agent_spotlight_and_trend(
            team="Inbound", month="October", year=2026, employee_query="Ahmed Hassan"
        )
        assert named.digest["spotlight"] is None
        assert named.records_evaluated == 0
    finally:
        db.close()


def test_employee_history_best_month_matches_canonical():
    db = _make_db()
    try:
        _seed_base(db)
        reg = _registry(db, ADMIN_SCOPE)
        result = reg.execute_employee_multi_month_history(employee_query="E-IN-2")
        spotlight = result.digest["agent_spotlight"]
        assert spotlight["entity_name"] == "Layla Nour"
        by_period = {}
        for record in _canonical(db, ADMIN_SCOPE):
            if str(getattr(record, "employee_id", "")) == "E-IN-2":
                by_period[(str(getattr(record, "month", "")), int(getattr(record, "year", 0)))] = (
                    _resolved_score(record)
                )
        assert by_period == {("August", 2026): 70.0, ("September", 2026): pytest.approx(87.66, abs=0.05)}
        assert spotlight["best_months"] == ["September 2026"]
        assert spotlight["worst_months"] == ["August 2026"]
        history = {(p["month"], p["year"]): p["score"] for p in spotlight["all_history"]}
        assert history[("September", 2026)] == pytest.approx(87.66, abs=0.05)
        assert history[("August", 2026)] == 70.0
    finally:
        db.close()


def test_team_trend_points_match_canonical_monthly_means():
    db = _make_db()
    try:
        _seed_base(db)
        reg = _registry(db, ADMIN_SCOPE)
        result = reg.execute_team_trend_spotlight(team="Inbound", month="September", year=2026)
        spotlight = result.digest["team_trend_spotlight"]
        canonical = _canonical(db, ADMIN_SCOPE, team="Inbound")
        by_period: dict[tuple[str, int], list[float]] = {}
        for record in canonical:
            by_period.setdefault(
                (str(getattr(record, "month", "")), int(getattr(record, "year", 0))), []
            ).append(_resolved_score(record))
        assert spotlight["months_tracked"] == len(by_period)
        assert spotlight["latest_month_label"] == "September 2026"
        assert spotlight["score"] == _mean_1dp(by_period[("September", 2026)])
        assert spotlight["first_score"] == _mean_1dp(by_period[("August", 2026)])
        assert spotlight["change_vs_prev"] == pytest.approx(
            _mean_1dp(by_period[("September", 2026)]) - _mean_1dp(by_period[("August", 2026)]),
            abs=0.05,
        )
        card = result.visual_cards[0]
        points = {(p.month, p.year): p.score for p in card.spotlight.trend_points}
        assert points[("September", 2026)] == _mean_1dp(by_period[("September", 2026)])
        assert points[("August", 2026)] == _mean_1dp(by_period[("August", 2026)])
    finally:
        db.close()


def test_people_rankings_match_canonical_records():
    db = _make_db()
    try:
        _seed_base(db)
        reg = _registry(db, ADMIN_SCOPE)
        # Pin Booking: without a kpi the workspace analyses the largest
        # |impact| driver, which is also Booking here, but pinning makes
        # the test independent of that selection rule.
        result = reg.execute_people_contribution_and_rankings(
            team="Inbound", month="September", year=2026, kpi="Booking"
        )
        canonical = _canonical(db, ADMIN_SCOPE, team="Inbound", month="September", year=2026)
        assert result.digest["total_employees"] == len(canonical)
        assert "Booking" in result.digest["kpi_analyzed"]
        expected_scores = {
            str(getattr(r, "employee_id", "")): _resolved_score(r) for r in canonical
        }
        # Booking weighted impacts: Mona -2.5, Ahmed -0.42, Layla/Omar
        # -0.17 each — all four are negative contributors.
        assert result.digest["negative_contributors"] == 4
        top = result.digest["top_contributors"]
        assert top[0]["employee_name"] == "Mona Ali"
        assert top[0]["performance_score"] == 0.0
        assert top[0]["weighted_impact"] == pytest.approx(-2.5, abs=0.05)
        assert top[0]["achievement_percent"] == 0.0
        for entry in top:
            assert entry["employee_id"] in expected_scores
            assert entry["performance_score"] == pytest.approx(
                expected_scores[entry["employee_id"]], abs=0.05
            )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# RBAC matrix
# ---------------------------------------------------------------------------

RBAC_SCOPES = [
    ("admin", ADMIN_SCOPE),
    ("manager_inbound_only", {"role": "Manager", "accessible_teams": ["Inbound"]}),
    ("manager_outbound_only", {"role": "Manager", "accessible_teams": ["Outbound"]}),
    (
        "regional_manager_egy",
        {"role": "Regional Manager", "accessible_regions": ["EGY"],
         "accessible_teams": ["Inbound", "Outbound", "Coding EGY"]},
    ),
    (
        "regional_manager_uae",
        {"role": "Regional Manager", "accessible_regions": ["UAE"],
         "accessible_teams": ["Coding"]},
    ),
    (
        "branch_director_dubai",
        {"role": "Branch Director", "accessible_branches": ["dubai"]},
    ),
]


@pytest.mark.parametrize("scope_name,scope", RBAC_SCOPES)
def test_rbac_matrix_registry_matches_canonical_scope(scope_name, scope):
    """For every role, the registry's teams and totals equal exactly what
    the canonical service returns for the same scope — no cross-team,
    cross-country, or shared-region leak."""
    db = _make_db()
    try:
        _seed_base(db)
        reg = _registry(db, scope)
        result = reg.execute_executive_and_priority_insights(month="September", year=2026)
        canonical = _canonical(db, scope, month="September", year=2026)
        assert result.digest["total_records"] == len(canonical), scope_name
        grouped: dict[str, list[float]] = {}
        for record in canonical:
            grouped.setdefault(str(getattr(record, "team", "")).casefold(), []).append(
                _resolved_score(record)
            )
        by_team = {t["team"].casefold(): t["score"] for t in result.digest["teams"]}
        assert set(by_team) <= set(grouped), scope_name
        for team_key, score in by_team.items():
            assert score == _mean_1dp(grouped[team_key]), (scope_name, team_key)
        if canonical:
            assert result.digest["average_score"] == _mean_1dp([_resolved_score(r) for r in canonical])
        else:
            assert result.digest["average_score"] is None, scope_name
        # Shared scorecards obey the same scope: only Admin sees them here.
        shared = reg.execute_shared_region_scorecard(team="Finance", month="September", year=2026)
        shared_canonical = [
            r
            for r in _canonical(db, scope, team="Finance", month="September", year=2026)
            if str(getattr(r, "region", "") or "").strip().casefold() == "all"
        ]
        assert shared.digest["total_records"] == len(shared_canonical), scope_name
        if shared_canonical:
            assert shared.digest["average_score"] == _mean_1dp(
                [_resolved_score(r) for r in shared_canonical]
            )
        else:
            assert shared.digest["average_score"] is None, scope_name
    finally:
        db.close()


@pytest.mark.parametrize(
    "scope,team,expected",
    [
        (ADMIN_SCOPE, "Finance", True),
        (ADMIN_SCOPE, "Outbound", True),
        ({"role": "Manager", "accessible_teams": ["Inbound"]}, "Inbound", True),
        ({"role": "Manager", "accessible_teams": ["Inbound"]}, "Outbound", False),
        ({"role": "Manager", "accessible_teams": ["Inbound"]}, "Finance", False),
        (
            {"role": "Regional Manager", "accessible_regions": ["EGY"],
             "accessible_teams": ["Inbound"]},
            "Inbound",
            True,
        ),
        (
            {"role": "Regional Manager", "accessible_regions": ["EGY"],
             "accessible_teams": ["Inbound"]},
            "Outbound",
            True,
        ),
        (
            {"role": "Regional Manager", "accessible_regions": ["EGY"],
             "accessible_teams": ["Inbound"]},
            "RCM",
            False,
        ),
        (
            {"role": "Regional Manager", "accessible_regions": ["UAE"],
             "accessible_teams": ["Outbound"]},
            "Outbound",
            False,
        ),
        (
            {"role": "Regional Manager", "accessible_regions": ["UAE"],
             "accessible_teams": ["Outbound"]},
            "Inbound",
            False,
        ),
        # Shared teams fall back to their corporate region at the helper
        # level (Finance/RCM are UAE-corporate), so a UAE Regional
        # Manager passes this check — but the record filter still keeps
        # region='All' rows out of a single-region scope, which the
        # registry-level RBAC test above verifies.
        (
            {"role": "Regional Manager", "accessible_regions": ["UAE"],
             "accessible_teams": ["Outbound"]},
            "Finance",
            True,
        ),
        (
            {"role": "Regional Manager", "accessible_regions": ["UAE"],
             "accessible_teams": ["Outbound"]},
            "RCM",
            True,
        ),
        (
            {"role": "Regional Manager", "accessible_regions": ["EGY"],
             "accessible_teams": ["Inbound"]},
            "Finance",
            False,
        ),
    ],
)
def test_rbac_team_access_matrix(scope, team, expected):
    assert user_can_access_team(scope, team) is expected


@pytest.mark.parametrize(
    "scope,branch,expected",
    [
        (ADMIN_SCOPE, "dubai", True),
        (ADMIN_SCOPE, "sharjah", True),
        ({"role": "Branch Director", "accessible_branches": ["dubai"]}, "dubai", True),
        ({"role": "Branch Director", "accessible_branches": ["dubai"]}, "sharjah", False),
        ({"role": "Branch Director", "accessible_branches": ["dubai"]}, "all", True),
        ({"role": "Manager", "accessible_teams": ["Inbound"]}, "dubai", True),
    ],
)
def test_rbac_branch_access_matrix(scope, branch, expected):
    assert user_can_access_branch(scope, branch) is expected


# ---------------------------------------------------------------------------
# Governance / corrective reads and whole-registry read-only sweep
# ---------------------------------------------------------------------------


def test_governance_and_corrective_status_are_scoped_reads():
    db = _make_db()
    try:
        _seed_base(db)
        reg = _registry(db, ADMIN_SCOPE)
        governance = reg.execute_governance_candidates_and_plans(
            team="Inbound", month="September", year=2026
        )
        canonical = _canonical(db, ADMIN_SCOPE, team="Inbound", month="September", year=2026)
        assert governance.records_evaluated == len(canonical)
        assert governance.digest["period"] == "September 2026"
        actions = reg.execute_corrective_actions_status(team="Inbound", month="September", year=2026)
        assert actions.digest["total_actions"] == 0
        assert actions.digest["actions"] == []
        assert actions.visual_cards[0].card_type == "guardrail_notice"
    finally:
        db.close()


def test_all_registry_entrypoints_are_read_only():
    """Run every public tool entrypoint; no table gains or loses a row and
    the session carries no pending writes afterwards."""
    db = _make_db()
    try:
        _seed_base(db)
        models = (Team, Employee, PerformanceRecord, KPIValue, ManagementKPIConfig, ManagementKPISnapshot)
        before = {model: _count_rows(db, model) for model in models}
        reg = _registry(db, ADMIN_SCOPE)
        reg.execute_executive_and_priority_insights(team="Inbound", month="September", year=2026)
        reg.execute_shared_region_scorecard(team="RCM", month="September", year=2026)
        reg.execute_kpi_diagnosis_and_trends(team="Inbound", month="September", year=2026)
        reg.execute_people_contribution_and_rankings(team="Inbound", month="September", year=2026)
        reg.execute_agent_spotlight_and_trend(team="Inbound", month="September", year=2026)
        reg.execute_team_trend_spotlight(team="Inbound", month="September", year=2026)
        reg.execute_employee_multi_month_history(employee_query="E-IN-1")
        reg.execute_governance_candidates_and_plans(team="Inbound", month="September", year=2026)
        reg.execute_corrective_actions_status(team="Inbound", month="September", year=2026)
        reg.execute_management_balanced_scorecard(
            team="CRM", performance_level="Corporate", month="September", year=2026
        )
        for model in models:
            assert _count_rows(db, model) == before[model], model.__name__
        assert not db.new and not db.dirty and not db.deleted
    finally:
        db.close()
