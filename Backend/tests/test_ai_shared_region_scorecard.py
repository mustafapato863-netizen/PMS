"""Shared All-region (region='All') scorecard for Finance and RCM (PR #84).

End-to-end coverage through PmsAiOrchestrator with provider_override="deterministic":
no model is started and no production data is touched. Fixtures mirror the
Phase 6 holdout shared records (region='All' Finance/RCM rows) plus
country-scoped RCM sub-team rows that must NEVER leak into the shared average.

Score rule: simple mean of the stored overall evaluation scores of the team's
own region='All' Employee records for the period — the same single averaging
rule as ``executive_story.current_score``. Shared rows are never folded into
an Egypt-only or UAE-only total (no attribution rule exists for that).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.ai_schemas import AiChatRequest, SessionFilterContext
from models.models import Employee, PerformanceRecord, ProductSetting, Team
from services.ai.catalog import ai_evidence_cache
from services.ai.orchestrator import PmsAiOrchestrator


@pytest.fixture(autouse=True)
def _clear_cache():
    ai_evidence_cache.clear()
    yield
    ai_evidence_cache.clear()


def _make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(ProductSetting(key="ai_enabled", enabled=True))
    session.commit()
    return session


def _seed_shared_records(db):
    """Shared Finance/RCM rows (region 'All') plus country RCM sub-team rows."""
    teams = {}
    for name, db_name, region in (
        ("Finance", "Finance", "All"),
        ("RCM", "RCM", "All"),
        ("Coding EGY", "Coding EGY", "EGY"),
        ("Coding", "Coding", "UAE"),
    ):
        team = Team(
            id=uuid.uuid4(),
            name=name.casefold().replace(" ", "_"),
            db_name=db_name,
            display_name=db_name,
            region=region,
            team_level="employee",
            is_active=True,
        )
        db.add(team)
        teams[db_name] = team
    db.flush()

    employees: dict[str, Employee] = {}

    def add_record(emp_code, emp_name, team_name, score, month, year=2026, region="All"):
        team = teams[team_name]
        emp = employees.get(emp_code)
        if emp is None:
            emp = Employee(
                id=uuid.uuid4(),
                employee_id=emp_code,
                name=emp_name,
                team_id=team.id,
                region=region,
                performance_level="Employee",
                is_active=True,
            )
            db.add(emp)
            db.flush()
            employees[emp_code] = emp
        db.add(
            PerformanceRecord(
                id=uuid.uuid4(),
                employee_id=emp.id,
                team_id=team.id,
                month=month,
                year=year,
                performance_level="Employee",
                region=region,
                branch_key=None,
                score=score,
                grade="B",
                status="Good",
            )
        )

    # Shared Finance, September 2026: (86 + 90) / 2 = 88.0
    add_record("EMP_ALL_FIN_1", "Karim Finance", "Finance", 86.0, "September")
    add_record("EMP_ALL_FIN_2", "Layla Finance", "Finance", 90.0, "September")
    # Shared Finance, May 2026 (earlier period, proves month filtering)
    add_record("EMP_ALL_FIN_1", "Karim Finance", "Finance", 80.0, "May")
    # Shared RCM, September 2026: (90 + 84) / 2 = 87.0
    add_record("EMP_ALL_RCM_1", "Tariq RCM", "RCM", 90.0, "September")
    add_record("EMP_ALL_RCM_2", "Mona RCM", "RCM", 84.0, "September")
    # Shared RCM, June 2026 (latest period with RCM rows if September is not asked)
    add_record("EMP_ALL_RCM_1", "Tariq RCM", "RCM", 70.0, "June")
    # Country RCM sub-team rows: must NEVER enter the shared average.
    # If they leaked in, the September RCM mean would be (90+84+95+60)/4 = 82.25, not 87.0.
    add_record("EMP_EGY_COD_1", "Cairo Coder", "Coding EGY", 95.0, "September", region="EGY")
    add_record("EMP_UAE_COD_1", "Dubai Coder", "Coding", 60.0, "September", region="UAE")
    # An August country row makes August a published period with no shared rows.
    add_record("EMP_EGY_COD_1", "Cairo Coder", "Coding EGY", 92.0, "August", region="EGY")
    db.commit()


def _run_choice_flow(db, scope, first_prompt, choice_prompt, choice_id, session_state=None):
    """Two-turn clarification flow: first turn asks, second picks `choice_id`."""
    orch = PmsAiOrchestrator(db, scope)
    state = session_state or SessionFilterContext()
    first = orch.run_chat_turn(
        AiChatRequest(
            prompt=first_prompt,
            session_state=state,
            provider_override="deterministic",
        )
    )
    assert first.clarification is not None, f"expected clarification, got outcome={first.outcome}"
    assert first.outcome == "clarification"
    confirmed = first.resolved_session_state.last_confirmed_query
    assert confirmed is not None
    return orch.run_chat_turn(
        AiChatRequest(
            prompt=choice_prompt,
            session_state=SessionFilterContext(
                region=state.region,
                month=state.month,
                year=state.year,
                last_confirmed_query=confirmed,
            ),
            clarification_choice_id=choice_id,
            provider_override="deterministic",
        )
    )


def _choose_shared(db, scope, team_label, choice_id, session_state=None):
    """First turn asks (clarification), second turn picks the shared choice."""
    return _run_choice_flow(
        db,
        scope,
        f"What is the shared {team_label} score?",
        f"What is the shared {team_label} score?",
        choice_id,
        session_state,
    )


ADMIN_SCOPE = {"role": "Admin", "accessible_teams": ["RCM", "Finance"]}


def test_admin_shared_finance_scorecard():
    db = _make_db()
    try:
        _seed_shared_records(db)
        res = _choose_shared(db, ADMIN_SCOPE, "Finance", "choice-shared-finance")
        assert res.outcome == "answer"
        assert "Shared All-region Finance" in res.headline
        assert "88.0%" in res.headline
        assert "2 evaluated records" in res.headline
        assert "September 2026" in res.headline
    finally:
        db.close()


def test_admin_shared_rcm_scorecard_excludes_country_subteams():
    db = _make_db()
    try:
        _seed_shared_records(db)
        res = _choose_shared(db, ADMIN_SCOPE, "RCM", "choice-shared-rcm")
        assert res.outcome == "answer"
        assert "Shared All-region RCM" in res.headline
        # (90 + 84) / 2 = 87.0 over the two shared rows only. The EGY Coding
        # row (95.0) and UAE Coding row (60.0) must not be averaged in.
        assert "87.0%" in res.headline
        assert "82.2%" not in res.headline
        assert "2 evaluated records" in res.headline
        assert "September 2026" in res.headline
    finally:
        db.close()


def test_admin_shared_rcm_in_explicit_month():
    """An explicitly requested month with shared rows uses that month's rows."""
    db = _make_db()
    try:
        _seed_shared_records(db)
        res = _choose_shared(
            db,
            ADMIN_SCOPE,
            "RCM",
            "choice-shared-rcm",
            session_state=SessionFilterContext(month="June", year=2026),
        )
        assert res.outcome == "answer"
        assert "Shared All-region RCM" in res.headline
        assert "70.0%" in res.headline
        assert "June 2026" in res.headline
        assert "1 evaluated records" in res.headline
    finally:
        db.close()


def test_admin_shared_rcm_month_without_shared_records_is_honest():
    """August is published (country rows exist) but has no shared RCM rows:
    the answer must say no records matched, never substitute another month."""
    db = _make_db()
    try:
        _seed_shared_records(db)
        res = _choose_shared(
            db,
            ADMIN_SCOPE,
            "RCM",
            "choice-shared-rcm",
            session_state=SessionFilterContext(month="August", year=2026),
        )
        assert res.outcome == "answer"
        assert "No performance records matched" in res.headline
        assert "Shared All-region RCM" in res.headline
        assert "August 2026" in res.headline
        assert "September" not in res.headline
    finally:
        db.close()


def test_regional_manager_egy_only_gets_scoped_denial():
    """Single-region Regional Managers never see region='All' rows (record
    filter), so the shared choice is a scoped denial, not an empty answer."""
    db = _make_db()
    try:
        _seed_shared_records(db)
        scope = {"role": "Regional Manager", "accessible_regions": ["EGY"], "accessible_teams": ["RCM"]}
        res = _choose_shared(db, scope, "RCM", "choice-shared-rcm")
        assert res.outcome == "restricted_access"
        assert "Access restricted" in res.headline
    finally:
        db.close()


def test_manager_without_rcm_grant_gets_scoped_denial():
    db = _make_db()
    try:
        _seed_shared_records(db)
        scope = {"role": "Manager", "accessible_teams": ["Inbound"]}
        res = _choose_shared(db, scope, "Finance", "choice-shared-finance")
        assert res.outcome == "restricted_access"
        assert "Access restricted" in res.headline
    finally:
        db.close()


def test_manager_with_explicit_rcm_grant_sees_shared_rcm():
    db = _make_db()
    try:
        _seed_shared_records(db)
        scope = {"role": "Manager", "accessible_teams": ["RCM"]}
        res = _choose_shared(db, scope, "RCM", "choice-shared-rcm")
        assert res.outcome == "answer"
        assert "Shared All-region RCM" in res.headline
        assert "87.0%" in res.headline
    finally:
        db.close()


def test_shared_and_egypt_rcm_do_not_share_cache_or_totals():
    """Aggregation boundary, end to end: the Egypt-only RCM total must NOT
    include the shared region='All' rows, and the shared scorecard and the
    Egypt total must not share a cache entry (same team, different numbers).

    Seeded September rows: shared RCM 90.0 + 84.0, EGY Coding 95.0, UAE
    Coding 60.0. Shared-only mean is 87.0%; Egypt-only mean is 95.0%.
    """
    db = _make_db()
    try:
        _seed_shared_records(db)
        shared = _choose_shared(db, ADMIN_SCOPE, "RCM", "choice-shared-rcm")
        assert shared.outcome == "answer"
        assert "87.0%" in shared.headline

        egypt = _run_choice_flow(
            db,
            ADMIN_SCOPE,
            "What is the RCM score in September 2026?",
            "What is the Egypt RCM performance?",
            "choice-rcm-egy",
            session_state=SessionFilterContext(region="EGY"),
        )
        assert egypt.outcome == "answer"
        # Only the EGY Coding row (95.0) belongs in the Egypt total. If the
        # shared rows leaked in, the mean would be (95+90+84)/3 = 89.7%.
        assert "95.0%" in egypt.headline
        assert "87.0%" not in egypt.headline
        assert "89.7%" not in egypt.headline
    finally:
        db.close()
