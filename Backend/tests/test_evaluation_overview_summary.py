"""Evaluation overview: counts across every scope, the attention list, and the fixed query count.

Rows are written directly so each state is exact: drafts, approved months with an active revision, with
only rolled-back or superseded revisions on the period, and with no revisions at all, plus superseded rows
and legacy team configuration rows that have no performance level.

Each approved month gets one of three states, the same three-way rule the month view uses in
evaluationWorkflowState.ts (approvedStatus):
- applied: an active revision points at this approved version;
- approved, not applied: no active revision for it, but the period has revisions on record;
- approved, unconfirmed: the period has no revisions on record. The month view says only "Approved".
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers.evaluation_settings import router as evaluation_router
from config.database import get_db
from models.models import (
    Action,
    Base,
    Employee,
    EmployeeUploadBatch,
    EvaluationRevision,
    EvaluationScope,
    GeneratedReport,
    KPIValue,
    ManagementKPIConfig,
    PerformancePlan,
    PerformanceRecord,
    Team,
    TeamConfigurationVersion,
    TeamKPIConfig,
    UploadLog,
    User,
    UserTeamAssignment,
)
from services.evaluation.periods import month_name
from services.evaluation.workflow import OVERVIEW_ATTENTION_LIMIT, EvaluationWorkflow
from utils.team_identity import logical_team_name

# The statements the overview runs with revisions present: the admin user, the table check, one aggregate
# over the versions, the attention page, the teams for that page and the scopes for that page. The number is
# the same at 3 scopes and at 30.
OVERVIEW_QUERY_COUNT = 6

CORE_TABLES = [
    Team.__table__,
    User.__table__,
    Employee.__table__,
    UserTeamAssignment.__table__,
    PerformanceRecord.__table__,
    KPIValue.__table__,
    Action.__table__,
    PerformancePlan.__table__,
    GeneratedReport.__table__,
    TeamConfigurationVersion.__table__,
    EvaluationScope.__table__,
    ManagementKPIConfig.__table__,
    TeamKPIConfig.__table__,
    EmployeeUploadBatch.__table__,
    UploadLog.__table__,
]


def _make_db(*, with_revisions: bool):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    tables = CORE_TABLES + ([EvaluationRevision.__table__] if with_revisions else [])
    Base.metadata.create_all(bind=engine, tables=tables)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    return engine, session


@pytest.fixture
def db():
    _engine, session = _make_db(with_revisions=True)
    yield session
    session.close()


@pytest.fixture
def db_without_revisions():
    _engine, session = _make_db(with_revisions=False)
    yield session
    session.close()


def _user(role: str, name: str) -> User:
    return User(
        id=uuid.uuid4(), full_name=name, username=name, email=f"{name}@example.com",
        password_hash="test-hash", role=role, is_active=True,
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


def _known(user: User) -> dict:
    return {"state": "known", "user_id": str(user.id), "username": user.username, "full_name": user.full_name, "role": user.role}


class _Builder:
    """Adds teams, scopes, versions and revisions. Each scope gets its own team, as the catalog does."""

    def __init__(self, db):
        self.db = db
        self.admin = _user("Admin", "overview-admin")
        db.add(self.admin)
        db.commit()
        self.scopes = []

    def scope(self, label: str, level: str = "Employee", position: str = "") -> tuple[Team, EvaluationScope]:
        team = Team(id=uuid.uuid4(), name=label, db_name=f"db-{label}", display_name=label, region="UAE", team_level="employee")
        scope = EvaluationScope(
            id=uuid.uuid4(), team_id=team.id, team_key=logical_team_name(team).casefold(), display_name=label,
            performance_level=level, position_name=position, readiness="supported", history_note="", source_kind="test",
        )
        self.db.add_all([team, scope])
        self.db.flush()
        self.scopes.append((team, scope))
        return team, scope

    def version(self, team: Team, scope: EvaluationScope, *, year: int, month: int, status: str, number: int = 1,
                revised_by: User | None = None, approved_by: User | None = None) -> TeamConfigurationVersion:
        approved = status == "approved"
        row = TeamConfigurationVersion(
            id=uuid.uuid4(),
            team_id=team.id,
            version_number=number,
            status=status,
            effective_month=month_name(month),
            effective_year=year,
            config_snapshot={"lines": []},
            config_checksum=f"{number:064x}",
            effective_from_month=month,
            effective_from_year=year,
            effective_until_month=month,
            effective_until_year=year,
            performance_level=scope.performance_level,
            position_name=scope.position_name,
            created_by_user_id=revised_by.id if revised_by else self.admin.id,
            published_by_user_id=approved_by.id if approved_by else None,
            published_at=datetime(year, month, 28, 10, 0, tzinfo=timezone.utc) if approved else None,
            actor_created_snapshot=_known(revised_by or self.admin),
            actor_published_snapshot=_known(approved_by) if approved_by else {"state": "unknown"},
        )
        self.db.add(row)
        self.db.flush()
        return row

    def revision(self, scope: EvaluationScope, version: TeamConfigurationVersion, *, status: str) -> EvaluationRevision:
        row = EvaluationRevision(
            id=uuid.uuid4(),
            team_id=scope.team_id,
            performance_level=scope.performance_level,
            position_name=scope.position_name,
            year=version.effective_from_year,
            month=version.effective_from_month,
            version_id=version.id,
            status=status,
            prior_snapshot={},
            applied_snapshot={},
            actor_snapshot={"state": "unknown"},
        )
        self.db.add(row)
        self.db.flush()
        return row

    def legacy_row(self, team: Team, *, number: int) -> None:
        """A team configuration row from before monthly evaluation. It has no performance level."""
        self.db.add(TeamConfigurationVersion(
            id=uuid.uuid4(), team_id=team.id, version_number=number, status="published",
            effective_month="June", effective_year=2026, config_snapshot={"lines": []}, config_checksum=f"{number + 900:064x}",
            effective_from_month=6, effective_from_year=2026, performance_level=None, position_name=None,
            published_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ))
        self.db.flush()


def _overview(db, admin: User) -> dict:
    return EvaluationWorkflow(db).overview(_actor(admin))


def _frontend_status(db, version: TeamConfigurationVersion) -> str:
    """The month view's status for an approved version, transcribed from approvedStatus in evaluationWorkflowState.ts.

    The month view gets `revisions` for the period and returns "applied" when one is active for this version,
    "approved, not applied" when the list is not empty, and "approved" when it is empty.
    """
    revisions = db.query(EvaluationRevision).filter(
        EvaluationRevision.team_id == version.team_id,
        EvaluationRevision.performance_level == version.performance_level,
        EvaluationRevision.position_name == version.position_name,
        EvaluationRevision.year == version.effective_from_year,
        EvaluationRevision.month == version.effective_from_month,
    ).all()
    if any(item.status == "active" and item.version_id == version.id for item in revisions):
        return "applied"
    if revisions:
        return "approved_not_applied"
    return "approved"


def _client(db, holder: dict) -> TestClient:
    app = FastAPI()
    app.include_router(evaluation_router, prefix="/api/settings/evaluation")

    @app.middleware("http")
    async def attach_user(request, call_next):
        if holder["user"]:
            request.state.user = holder["user"]
        return await call_next(request)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def _count_statements(db, action) -> int:
    engine = db.get_bind()
    seen = []

    def count(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        action()
    finally:
        event.remove(engine, "before_cursor_execute", count)
    return len(seen)


def test_counts_drafts_applied_not_applied_and_unconfirmed_across_scopes(db):
    build = _Builder(db)
    coding, coding_scope = build.scope("Coding")
    pharmacy, pharmacy_scope = build.scope("Pharmacy", level="Managerial")
    reviewer = _user("Manager", "overview-reviewer")
    db.add(reviewer)
    db.flush()

    # Coding May: a rolled-back revision is on record for the period, so the approved row is not applied.
    may = build.version(coding, coding_scope, year=2026, month=5, status="approved", number=2, approved_by=build.admin)
    build.revision(coding_scope, may, status="rolled_back")
    # Coding June: an active revision points at the approved row, so it is applied.
    june = build.version(coding, coding_scope, year=2026, month=6, status="approved", number=3, approved_by=build.admin)
    build.revision(coding_scope, june, status="active")
    # Superseded evidence is history, not work to do.
    build.version(coding, coding_scope, year=2026, month=4, status="superseded", number=1, approved_by=build.admin)
    build.version(coding, coding_scope, year=2026, month=7, status="draft", number=4, revised_by=reviewer)
    # Pharmacy June: approved with no revision anywhere on its period. Unconfirmed, not work to do.
    build.version(pharmacy, pharmacy_scope, year=2026, month=6, status="approved", number=1, approved_by=build.admin)
    # Legacy team configuration rows are never monthly work.
    build.legacy_row(coding, number=7)
    db.commit()

    body = _overview(db, build.admin)

    assert body["drafts"] == 1
    assert body["approved_not_applied"] == 1
    assert body["approved_unconfirmed"] == 1
    assert body["applied"] == 1
    assert [item["state"] for item in body["attention"]] == ["draft", "approved_not_applied"]
    assert [(item["year"], item["month"]) for item in body["attention"]] == [(2026, 7), (2026, 5)]
    assert body["attention"][0]["scope_id"] == str(coding_scope.id)
    assert body["attention"][1]["version_id"] == str(may.id)
    assert body["attention"][1]["version_number"] == 2


def test_applied_is_decided_per_version_by_an_active_revision(db):
    build = _Builder(db)
    team, scope = build.scope("Coding")
    approved = [build.version(team, scope, year=2026, month=month, status="approved", number=month, approved_by=build.admin) for month in (1, 2, 3)]
    build.revision(scope, approved[0], status="active")
    build.revision(scope, approved[1], status="rolled_back")
    db.commit()

    body = _overview(db, build.admin)

    assert body["applied"] == 1
    assert body["approved_not_applied"] == 1
    assert body["approved_unconfirmed"] == 1


def test_rolled_back_revision_on_the_period_is_not_applied_and_needs_attention(db):
    build = _Builder(db)
    team, scope = build.scope("Coding")
    approved = build.version(team, scope, year=2026, month=6, status="approved", number=1, approved_by=build.admin)
    build.revision(scope, approved, status="rolled_back")
    db.commit()

    body = _overview(db, build.admin)

    assert body["applied"] == 0
    assert body["approved_not_applied"] == 1
    assert body["approved_unconfirmed"] == 0
    assert [item["state"] for item in body["attention"]] == ["approved_not_applied"]
    assert body["attention"][0]["version_id"] == str(approved.id)


def test_approved_version_with_no_revisions_is_unconfirmed_and_not_attention(db):
    build = _Builder(db)
    team, scope = build.scope("Coding")
    build.version(team, scope, year=2026, month=6, status="approved", number=1, approved_by=build.admin)
    db.commit()

    body = _overview(db, build.admin)

    assert body["approved_unconfirmed"] == 1
    assert body["approved_not_applied"] == 0
    assert body["applied"] == 0
    assert body["attention"] == []


def test_active_revision_on_a_superseded_version_does_not_apply_the_current_approved_one(db):
    build = _Builder(db)
    team, scope = build.scope("Coding")
    older = build.version(team, scope, year=2026, month=6, status="superseded", number=1, approved_by=build.admin)
    build.revision(scope, older, status="active")
    current = build.version(team, scope, year=2026, month=6, status="approved", number=2, approved_by=build.admin)
    db.commit()

    body = _overview(db, build.admin)

    assert body["applied"] == 0
    assert body["approved_not_applied"] == 1
    assert body["approved_unconfirmed"] == 0
    assert [item["version_id"] for item in body["attention"]] == [str(current.id)]
    assert body["attention"][0]["state"] == "approved_not_applied"


def test_each_state_matches_the_month_view_rule_for_its_period(db):
    """The invariant: for every approved monthly version, the overview's state is the status the month view gives it."""
    build = _Builder(db)
    coding_team, coding = build.scope("Coding")
    pharmacy_team, pharmacy = build.scope("Pharmacy", level="Managerial", position="Lead")
    fixtures = []
    # Coding: no revisions (unconfirmed), a superseded active revision on the same period (not applied),
    # an active revision (applied), a rolled-back revision (not applied).
    fixtures.append(build.version(coding_team, coding, year=2026, month=5, status="approved", number=1, approved_by=build.admin))
    superseded_june = build.version(coding_team, coding, year=2026, month=6, status="superseded", number=2, approved_by=build.admin)
    build.revision(coding, superseded_june, status="active")
    fixtures.append(build.version(coding_team, coding, year=2026, month=6, status="approved", number=3, approved_by=build.admin))
    fixtures.append(build.version(coding_team, coding, year=2026, month=7, status="approved", number=4, approved_by=build.admin))
    build.revision(coding, fixtures[-1], status="active")
    fixtures.append(build.version(coding_team, coding, year=2026, month=8, status="approved", number=5, approved_by=build.admin))
    build.revision(coding, fixtures[-1], status="rolled_back")
    # Pharmacy: no revisions (unconfirmed) and an active revision (applied).
    fixtures.append(build.version(pharmacy_team, pharmacy, year=2026, month=6, status="approved", number=1, approved_by=build.admin))
    fixtures.append(build.version(pharmacy_team, pharmacy, year=2026, month=7, status="approved", number=2, approved_by=build.admin))
    build.revision(pharmacy, fixtures[-1], status="active")
    draft = build.version(coding_team, coding, year=2026, month=9, status="draft", number=6)
    build.legacy_row(coding_team, number=9)
    db.commit()

    expected = {"applied": 0, "approved_not_applied": 0, "approved_unconfirmed": 0}
    expected_attention = set()
    for version in fixtures:
        state = _frontend_status(db, version)
        if state == "applied":
            expected["applied"] += 1
        elif state == "approved_not_applied":
            expected["approved_not_applied"] += 1
            expected_attention.add(str(version.id))
        else:
            expected["approved_unconfirmed"] += 1

    body = _overview(db, build.admin)

    assert body["applied"] == expected["applied"] == 2
    assert body["approved_not_applied"] == expected["approved_not_applied"] == 2
    assert body["approved_unconfirmed"] == expected["approved_unconfirmed"] == 2
    assert body["drafts"] == 1
    listed = {item["version_id"]: item["state"] for item in body["attention"]}
    assert set(listed) == expected_attention | {str(draft.id)}
    assert all(state == "approved_not_applied" for version_id, state in listed.items() if version_id in expected_attention)
    assert listed[str(draft.id)] == "draft"


def test_empty_database_reports_zero_and_no_attention(db):
    build = _Builder(db)
    db.commit()
    body = _overview(db, build.admin)
    assert body["drafts"] == 0
    assert body["approved_not_applied"] == 0
    assert body["approved_unconfirmed"] == 0
    assert body["applied"] == 0
    assert body["attention"] == []


def test_attention_is_newest_period_first_and_capped(db):
    build = _Builder(db)
    for index in range(12):
        team, scope = build.scope(f"Team {index:02d}")
        build.version(team, scope, year=2026, month=(index % 12) + 1, status="draft", number=1)
    db.commit()

    body = _overview(db, build.admin)

    assert body["drafts"] == 12
    assert len(body["attention"]) == OVERVIEW_ATTENTION_LIMIT == 10
    periods = [(item["year"], item["month"]) for item in body["attention"]]
    assert periods == sorted(periods, reverse=True)
    assert periods[0] == (2026, 12)


def test_unconfirmed_months_never_reach_attention(db):
    build = _Builder(db)
    team, scope = build.scope("Coding")
    for month in range(1, 13):
        build.version(team, scope, year=2026, month=month, status="approved", number=month, approved_by=build.admin)
    db.commit()

    body = _overview(db, build.admin)

    assert body["approved_unconfirmed"] == 12
    assert body["attention"] == []


def test_attention_item_has_the_full_scope_and_version_identity(db):
    build = _Builder(db)
    team, scope = build.scope("Managed Team", level="Managerial", position="Director")
    draft = build.version(team, scope, year=2026, month=8, status="draft", number=5)
    db.commit()

    (item,) = _overview(db, build.admin)["attention"]

    assert item == {
        "scope_id": str(scope.id),
        "scope_display_name": "Managed Team",
        "performance_level": "Managerial",
        "position_name": "Director",
        "year": 2026,
        "month": 8,
        "month_name": "August",
        "state": "draft",
        "version_id": str(draft.id),
        "version_number": 5,
    }


def test_missing_revision_table_gives_nulls_and_lists_only_drafts(db_without_revisions):
    db = db_without_revisions
    build = _Builder(db)
    team, scope = build.scope("Coding")
    build.version(team, scope, year=2026, month=6, status="approved", number=1, approved_by=build.admin)
    build.version(team, scope, year=2026, month=7, status="draft", number=2)
    db.commit()

    body = _overview(db, build.admin)

    assert body["drafts"] == 1
    assert body["approved_not_applied"] is None
    assert body["approved_unconfirmed"] is None
    assert body["applied"] is None
    assert [item["state"] for item in body["attention"]] == ["draft"]


def test_generated_at_is_utc_iso(db):
    build = _Builder(db)
    db.commit()
    generated = _overview(db, build.admin)["generated_at"]
    parsed = datetime.fromisoformat(generated)
    assert parsed.utcoffset().total_seconds() == 0


def test_overview_route_is_admin_only(db):
    build = _Builder(db)
    manager = _user("Manager", "overview-manager")
    db.add(manager)
    db.commit()
    holder = {"user": None}
    client = _client(db, holder)

    assert client.get("/api/settings/evaluation/overview").status_code == 401

    holder["user"] = {"user_id": str(manager.id), "role": "Admin"}
    refused = client.get("/api/settings/evaluation/overview")
    assert refused.status_code == 403

    holder["user"] = {"user_id": str(build.admin.id), "role": "Manager"}
    allowed = client.get("/api/settings/evaluation/overview")
    assert allowed.status_code == 200
    body = allowed.json()
    assert body["success"] is True
    assert set(body["data"]) == {"drafts", "approved_not_applied", "approved_unconfirmed", "applied", "attention", "generated_at"}


def test_overview_route_is_a_read_for_rate_limiting():
    from services.rate_limit.policy import RouteClass, classify_user_route

    route_class, _label = classify_user_route("GET", "/api/settings/evaluation/overview")
    assert route_class is RouteClass.READ


def test_query_count_does_not_grow_with_scopes(db):
    build = _Builder(db)
    for index in range(3):
        team, scope = build.scope(f"Small {index}")
        build.version(team, scope, year=2026, month=7, status="draft", number=1)
    db.commit()
    workflow = EvaluationWorkflow(db)
    actor = _actor(build.admin)
    few = _count_statements(db, lambda: workflow.overview(actor))

    for index in range(27):
        team, scope = build.scope(f"Large {index}")
        approved = build.version(team, scope, year=2026, month=6, status="approved", number=1, approved_by=build.admin)
        build.revision(scope, approved, status="active")
        build.version(team, scope, year=2026, month=7, status="draft", number=2)
    db.commit()
    many = _count_statements(db, lambda: workflow.overview(actor))

    assert few == many == OVERVIEW_QUERY_COUNT
    body = workflow.overview(actor)
    assert body["drafts"] == 30
    assert body["applied"] == 27
    assert len(body["attention"]) == OVERVIEW_ATTENTION_LIMIT
