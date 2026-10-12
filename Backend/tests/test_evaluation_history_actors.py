"""Evaluation history: who created and approved each version, and when.

The new fields are additive. They carry display names only, never an email or a user id. A name that
cannot be resolved is null, and a draft has no approval.
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
from services.evaluation.workflow import EvaluationWorkflow
from utils.team_identity import logical_team_name


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(
        bind=engine,
        tables=[
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
            EvaluationRevision.__table__,
            ManagementKPIConfig.__table__,
            TeamKPIConfig.__table__,
            EmployeeUploadBatch.__table__,
            UploadLog.__table__,
        ],
    )
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield session
    session.close()


def _user(name: str, full_name: str | None = None) -> User:
    return User(
        id=uuid.uuid4(),
        full_name=full_name if full_name is not None else name,
        username=name,
        email=f"{name}@private.example",
        password_hash="test-hash",
        role="Admin",
        is_active=True,
    )


def _known(user: User) -> dict:
    return {
        "state": "known",
        "user_id": str(user.id),
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
    }


@pytest.fixture
def world(db):
    creator = _user("history-creator", "Ruth Creator")
    approver = _user("history-approver", "Amir Approver")
    db.add_all([creator, approver])
    team = Team(id=uuid.uuid4(), name="Coding", db_name="Coding", display_name="Coding", region="UAE", team_level="employee")
    scope = EvaluationScope(
        id=uuid.uuid4(), team_id=team.id, team_key=logical_team_name(team).casefold(), display_name="Coding",
        performance_level="Employee", position_name="", readiness="supported", history_note="", source_kind="test",
    )
    db.add_all([team, scope])
    db.commit()
    return {"creator": creator, "approver": approver, "team": team, "scope": scope, "db": db}


def _version(world, *, status: str, number: int, month: int = 6, creator_known: bool = True, approved_by=None,
             published_at=None, actor_published=None) -> TeamConfigurationVersion:
    db = world["db"]
    created_by = world["creator"] if creator_known else None
    approved = status == "approved"
    row = TeamConfigurationVersion(
        id=uuid.uuid4(),
        team_id=world["team"].id,
        version_number=number,
        status=status,
        effective_month=month_name(month),
        effective_year=2026,
        config_snapshot={"lines": []},
        config_checksum=f"{number:064x}",
        effective_from_month=month,
        effective_from_year=2026,
        effective_until_month=month,
        effective_until_year=2026,
        performance_level="Employee",
        position_name="",
        created_by_user_id=created_by.id if created_by is not None else None,
        published_by_user_id=approved_by.id if approved_by is not None else None,
        published_at=published_at or (datetime(2026, 6, 28, 9, 30, tzinfo=timezone.utc) if approved else None),
        actor_created_snapshot=_known(created_by) if created_by is not None else {"state": "unknown"},
        actor_published_snapshot=(
            actor_published if actor_published is not None
            else (_known(approved_by) if approved_by is not None else {"state": "unknown"})
        ),
    )
    db.add(row)
    db.commit()
    return row


def _serialize(world, row) -> dict:
    return EvaluationWorkflow(world["db"])._serialize_version(row, world["scope"])


def test_approved_version_names_its_creator_and_approver_with_when(world):
    row = _version(world, status="approved", number=1, approved_by=world["approver"])

    body = _serialize(world, row)

    assert body["created_by"] == "Ruth Creator"
    assert body["approved_by"] == "Amir Approver"
    assert body["created_at"] is not None
    assert body["approved_at"] == "2026-06-28T09:30:00+00:00"


def test_draft_has_a_creator_and_no_approval(world):
    row = _version(world, status="draft", number=2, month=7)

    body = _serialize(world, row)

    assert body["created_by"] == "Ruth Creator"
    assert body["created_at"] is not None
    assert body["approved_by"] is None
    assert body["approved_at"] is None


def test_no_email_or_user_id_appears_in_the_payload(world):
    row = _version(world, status="approved", number=1, approved_by=world["approver"])

    text = json.dumps(_serialize(world, row))

    assert "@private.example" not in text
    assert str(world["creator"].id) not in text
    assert str(world["approver"].id) not in text
    assert "history-creator" not in text
    for key in ("created_by_user_id", "published_by_user_id", "user_id", "email"):
        assert key not in json.loads(text)


def test_unresolvable_creator_is_null(world):
    row = _version(world, status="draft", number=3, month=7, creator_known=False)

    body = _serialize(world, row)

    assert body["created_by"] is None
    assert body["created_at"] is not None


def test_approver_name_falls_back_to_the_humanized_username(world):
    nameless = _user("history-nameless", full_name="")
    world["db"].add(nameless)
    world["db"].commit()
    row = _version(
        world, status="approved", number=4, approved_by=nameless,
        actor_published={"state": "known", "user_id": str(nameless.id), "username": "history.nameless", "full_name": "", "role": "Admin"},
    )

    body = _serialize(world, row)

    assert body["approved_by"] == "History Nameless"


def test_unknown_approver_snapshot_is_null_even_with_a_timestamp(world):
    row = _version(world, status="approved", number=5, actor_published={"state": "unknown"})

    body = _serialize(world, row)

    assert body["approved_by"] is None
    assert body["approved_at"] is not None


def test_existing_fields_keep_their_names_and_values(world):
    row = _version(world, status="approved", number=1, approved_by=world["approver"])

    body = _serialize(world, row)

    assert body["id"] == str(row.id)
    assert body["scope_id"] == str(world["scope"].id)
    assert body["status"] == "approved"
    assert body["version_number"] == 1
    assert body["year"] == 2026
    assert body["month"] == 6
    assert body["month_name"] == "June"
    assert body["checksum"] == f"{1:064x}"
    for key in ("contract", "revision_choice", "lines", "grade_thresholds", "notes", "source_version_id", "source_version_number", "source_checksum", "proof"):
        assert key in body
