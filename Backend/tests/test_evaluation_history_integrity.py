"""SQLite equivalents of the monthly evaluation history guards.

PostgreSQL checks live in evaluation_history_pg_checks.py and are not part of
the default collection. This module does not read or set DATABASE_URL.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.evaluation_history_schema import missing_history_objects
from models.models import Base, Employee, EvaluationRevision, Team, TeamConfigurationVersion, User


LEGACY_SNAPSHOT = {"legacy": True, "policy": "keep"}
EXACT_CHECK = "ck_team_config_monthly_exact_period"


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(
        bind=engine,
        tables=[
            Team.__table__,
            User.__table__,
            Employee.__table__,
            TeamConfigurationVersion.__table__,
            EvaluationRevision.__table__,
        ],
    )
    return engine


def _session():
    engine = _engine()
    with engine.connect() as connection:
        assert missing_history_objects(connection) == []
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def _team_and_user(session):
    user = User(
        id=uuid.uuid4(),
        full_name="SQLite Actor",
        username="sqlite-actor",
        email="sqlite-actor@example.com",
        password_hash="hash",
        role="Admin",
    )
    team = Team(
        id=uuid.uuid4(),
        name="SQLite Team",
        db_name="SQLite Team",
        display_name="SQLite Team",
        region="UAE",
        team_level="employee",
    )
    session.add_all([user, team])
    session.commit()
    return team, user


def _version(team_id, version_number, **overrides):
    values = dict(
        id=uuid.uuid4(),
        team_id=team_id,
        version_number=version_number,
        status="draft",
        effective_month="July",
        effective_year=2026,
        config_snapshot={"policy": "employee_ratio"},
        config_checksum=f"{version_number:064d}"[-64:],
        effective_from_month=7,
        effective_from_year=2026,
        effective_until_month=7,
        effective_until_year=2026,
        performance_level="Employee",
        position_name="",
    )
    values.update(overrides)
    return TeamConfigurationVersion(**values)


def _reject_flush(session, match: str) -> None:
    with pytest.raises(IntegrityError, match=match):
        session.flush()
    session.rollback()


def test_sqlite_orm_guards_match_the_monthly_rules():
    session = _session()
    team, _user = _team_and_user(session)
    legacy = _version(
        team.id,
        1,
        status="published",
        effective_month="Jul",
        effective_year=1999,
        config_snapshot=LEGACY_SNAPSHOT,
        config_checksum="a" * 64,
        effective_from_month=7,
        effective_from_year=1999,
        effective_until_month=None,
        effective_until_year=None,
        performance_level=None,
        position_name=None,
        notes="legacy",
    )
    approved = _version(
        team.id,
        2,
        status="approved",
        config_checksum="b" * 64,
        published_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        preview_snapshot={"proof": 1},
        total_weight="1.0000",
        overall_score="70.00",
    )
    session.add_all([legacy, approved])
    session.commit()
    legacy.notes = "still legacy"
    session.commit()
    approved.config_checksum = "c" * 64
    with pytest.raises(IntegrityError, match="approved monthly evaluation evidence is immutable"):
        session.commit()
    session.rollback()
    approved = session.get(TeamConfigurationVersion, approved.id)
    approved.status = "superseded"
    approved.superseded_at = datetime(2026, 7, 3, tzinfo=timezone.utc)
    session.commit()
    session.delete(approved)
    with pytest.raises(IntegrityError, match="monthly approved evaluation history cannot be deleted"):
        session.commit()
    session.rollback()
    session.delete(session.get(Team, team.id))
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        session.commit()
    session.rollback()
    stored = session.get(TeamConfigurationVersion, legacy.id)
    assert stored.config_snapshot["policy"] == "keep"
    assert stored.effective_until_month is None
    assert stored.position_name is None
    session.close()


def test_sqlite_monthly_end_nulls_fail_the_check_and_legacy_stays_open():
    session = _session()
    team, _user = _team_and_user(session)
    legacy = _version(
        team.id,
        1,
        status="published",
        effective_month="Jul",
        effective_year=1999,
        config_snapshot=LEGACY_SNAPSHOT,
        effective_from_year=1999,
        effective_until_month=None,
        effective_until_year=None,
        performance_level=None,
        position_name=None,
        notes="open legacy",
    )
    session.add(legacy)
    session.commit()
    legacy_id = legacy.id
    team_id = team.id

    for version_number, until_month, until_year in (
        (2, None, 2026),
        (3, 7, None),
        (4, None, None),
    ):
        session.add(_version(
            team_id,
            version_number,
            effective_until_month=until_month,
            effective_until_year=until_year,
        ))
        _reject_flush(session, EXACT_CHECK)

    draft = _version(team_id, 5, status="draft")
    session.add(draft)
    session.commit()
    draft_id = draft.id
    for until_month, until_year in ((None, 2026), (7, None), (None, None)):
        row = session.get(TeamConfigurationVersion, draft_id)
        session.connection().execute(text("DROP TRIGGER IF EXISTS trg_team_config_version_identity"))
        row.effective_until_month = until_month
        row.effective_until_year = until_year
        _reject_flush(session, EXACT_CHECK)
        stored = session.get(TeamConfigurationVersion, draft_id)
        assert (stored.effective_until_month, stored.effective_until_year) == (7, 2026)

    legacy = session.get(TeamConfigurationVersion, legacy_id)
    legacy.notes = "still open"
    session.commit()
    legacy = session.get(TeamConfigurationVersion, legacy_id)
    assert legacy.notes == "still open"
    assert legacy.effective_until_month is None
    assert legacy.effective_until_year is None
    assert legacy.performance_level is None
    assert legacy.position_name is None
    session.close()
