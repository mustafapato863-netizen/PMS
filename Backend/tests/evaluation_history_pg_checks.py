"""Explicit PostgreSQL checks for monthly evaluation history.

This module is not named test_*.py, so a normal pytest collection does not
run it or drop schemas. Run it by path:

    python -X utf8 -m pytest tests/evaluation_history_pg_checks.py

The runner must already have APP_ENV=test and DATABASE_URL=sqlite:///:memory:.
Owned PostgreSQL URLs are applied only inside allowlisted connections and
restored afterward. This file does not write os.environ at import.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

if os.environ.get("APP_ENV") != "test" or os.environ.get("DATABASE_URL") != "sqlite:///:memory:":
    raise RuntimeError(
        "evaluation_history_pg_checks requires APP_ENV=test and "
        "DATABASE_URL=sqlite:///:memory: from the runner before import. "
        "Owned PostgreSQL URLs are applied only for allowlisted connections."
    )
if os.environ.get("REDIS_URL", "") != "":
    raise RuntimeError("evaluation_history_pg_checks refuses a non-empty REDIS_URL.")

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from models.evaluation_history_schema import (
    PREDECESSOR_REVISION,
    REVISION,
    ROOT_REVISION,
    history_schema_signature,
    missing_history_objects,
)


BACKEND = Path(__file__).resolve().parents[1]
USER = "pms_eval_test"
PASSWORD = "pms-local-disposable-test"
TARGETS = (
    {"name": "pg16", "host": "127.0.0.1", "port": 55432, "database": "pms_eval_review_fix16"},
    {"name": "pg18", "host": "127.0.0.1", "port": 55433, "database": "pms_eval_review_fix18"},
)
ALLOWED_DATABASES = {item["database"] for item in TARGETS}
LEGACY_SNAPSHOT = {"legacy": True, "policy": "keep"}


def url_for(target: dict) -> str:
    if target["host"] != "127.0.0.1" or target["port"] not in {55432, 55433}:
        raise RuntimeError("Refusing a database target outside the disposable allowlist.")
    if target["database"] not in ALLOWED_DATABASES:
        raise RuntimeError("Refusing a database name outside the disposable allowlist.")
    return (
        f"postgresql+psycopg2://{USER}:{PASSWORD}@"
        f"{target['host']}:{target['port']}/{target['database']}"
    )


def assert_safe(connection, target: dict) -> None:
    url_for(target)
    row = connection.execute(
        text(
            """
            SELECT current_database(), current_user, inet_server_port(),
                   (SELECT setting FROM pg_settings WHERE name = 'port')
            """
        )
    ).one()
    database_name, user_name, server_port, configured_port = row
    if database_name != target["database"] or database_name not in ALLOWED_DATABASES:
        raise RuntimeError(f"Refusing statement on database {database_name}.")
    if user_name != USER:
        raise RuntimeError(f"Refusing statement as {user_name}.")
    if int(server_port) != 5432 or int(configured_port) != 5432:
        raise RuntimeError(f"Refusing server port {server_port}/{configured_port}.")


def reset_public(connection, target: dict) -> None:
    assert_safe(connection, target)
    connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
    connection.execute(text("CREATE SCHEMA public"))
    connection.commit()


@contextmanager
def _owned_alembic_env(url: str):
    keys = ("APP_ENV", "DATABASE_URL", "REDIS_URL")
    saved = {key: os.environ.get(key) for key in keys}
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = url
    os.environ["REDIS_URL"] = ""
    try:
        config = Config(str(BACKEND / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND / "migrations"))
        yield config
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def stamp(url: str, revision: str) -> None:
    with _owned_alembic_env(url) as config:
        command.stamp(config, revision)


def upgrade(url: str, revision: str) -> None:
    with _owned_alembic_env(url) as config:
        command.upgrade(config, revision)


def downgrade(url: str, revision: str) -> None:
    with _owned_alembic_env(url) as config:
        command.downgrade(config, revision)


def allowlisted_env(url: str, target: dict) -> dict:
    keys = (
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "PATHEXT",
        "COMSPEC",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "APPDATA",
        "PROGRAMFILES",
        "PROGRAMDATA",
        "PROGRAMW6432",
    )
    env = {key: os.environ[key] for key in keys if key in os.environ}
    env.update(
        {
            "APP_ENV": "test",
            "DATABASE_URL": url,
            "REDIS_URL": "",
            "PYTHONUNBUFFERED": "1",
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PMS_BOOTSTRAP_EXPECT_DATABASE": target["database"],
            "PMS_BOOTSTRAP_EXPECT_USER": USER,
        }
    )
    return env


PREDECESSOR_DDL = """
CREATE TABLE teams (
    id uuid PRIMARY KEY,
    name varchar(100) NOT NULL UNIQUE
);
CREATE TABLE users (
    id uuid PRIMARY KEY,
    username varchar(100) NOT NULL UNIQUE
);
CREATE TABLE team_configuration_versions (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    version_number integer NOT NULL,
    status varchar(20) NOT NULL,
    effective_month varchar(20) NOT NULL,
    effective_year smallint NOT NULL,
    config_snapshot json NOT NULL,
    config_checksum varchar(64) NOT NULL,
    created_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    published_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz DEFAULT now(),
    published_at timestamptz DEFAULT now(),
    superseded_at timestamptz,
    notes text,
    effective_from_month smallint NOT NULL,
    effective_from_year smallint NOT NULL,
    effective_until_month smallint,
    effective_until_year smallint,
    preview_snapshot json,
    total_weight numeric(7, 4),
    overall_score numeric(10, 2),
    is_active boolean NOT NULL DEFAULT true,
    performance_level varchar(20),
    position_name varchar(255),
    CONSTRAINT uq_team_config_version UNIQUE (team_id, version_number),
    CONSTRAINT ck_team_config_effective_from_month CHECK (effective_from_month BETWEEN 1 AND 12),
    CONSTRAINT ck_team_config_effective_until_month CHECK (
        effective_until_month IS NULL OR effective_until_month BETWEEN 1 AND 12
    ),
    CONSTRAINT ck_team_config_effective_range CHECK (
        effective_until_year IS NULL OR
        (effective_until_year * 12 + effective_until_month) >=
        (effective_from_year * 12 + effective_from_month)
    ),
    CONSTRAINT ck_team_config_version_level CHECK (
        performance_level IS NULL OR performance_level IN ('Employee', 'Managerial', 'Corporate')
    )
);
CREATE INDEX idx_team_config_coverage ON team_configuration_versions (
    team_id, status, effective_from_year, effective_from_month,
    effective_until_year, effective_until_month
);
CREATE UNIQUE INDEX uq_team_config_one_approved_month
    ON team_configuration_versions (
        team_id, performance_level, position_name, effective_from_year, effective_from_month
    )
    WHERE status = 'approved' AND performance_level IS NOT NULL;
CREATE UNIQUE INDEX uq_team_config_one_draft_month
    ON team_configuration_versions (
        team_id, performance_level, position_name, effective_from_year, effective_from_month
    )
    WHERE status = 'draft' AND performance_level IS NOT NULL;
CREATE TABLE evaluation_revisions (
    id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    performance_level varchar(20) NOT NULL,
    position_name varchar(255) NOT NULL DEFAULT '',
    year smallint NOT NULL,
    month smallint NOT NULL,
    version_id uuid NOT NULL REFERENCES team_configuration_versions(id) ON DELETE RESTRICT,
    status varchar(20) NOT NULL DEFAULT 'active',
    previous_revision_id uuid REFERENCES evaluation_revisions(id) ON DELETE SET NULL,
    prior_snapshot jsonb NOT NULL,
    applied_snapshot jsonb NOT NULL,
    created_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz DEFAULT now(),
    CONSTRAINT ck_evaluation_revision_status CHECK (status IN ('active', 'rolled_back')),
    CONSTRAINT ck_evaluation_revision_month CHECK (month BETWEEN 1 AND 12)
);
CREATE INDEX idx_evaluation_revision_period ON evaluation_revisions (
    team_id, performance_level, position_name, year, month, status
);
"""


def install_predecessor(connection, target: dict) -> None:
    assert_safe(connection, target)
    for statement in PREDECESSOR_DDL.split(";"):
        if statement.strip():
            connection.execute(text(statement))
    connection.commit()


def seed_base(connection, target: dict) -> dict:
    assert_safe(connection, target)
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()
    connection.execute(
        text("INSERT INTO teams (id, name) VALUES (:id, :name)"),
        {"id": team_id, "name": "History Team"},
    )
    connection.execute(
        text("INSERT INTO users (id, username) VALUES (:id, :username)"),
        {"id": user_id, "username": "history-user"},
    )
    connection.commit()
    return {"team_id": team_id, "user_id": user_id}


def insert_version(connection, **fields) -> uuid.UUID:
    version_id = fields.pop("id", uuid.uuid4())
    payload = {
        "id": version_id,
        "status": "published",
        "effective_month": "July",
        "effective_year": 2026,
        "config_snapshot": json.dumps({"lines": []}),
        "config_checksum": "a" * 64,
        "effective_from_month": 7,
        "effective_from_year": 2026,
        "effective_until_month": None,
        "effective_until_year": None,
        "performance_level": None,
        "position_name": None,
        "published_at": None,
        "created_by_user_id": None,
        "published_by_user_id": None,
        "notes": None,
        "is_active": True,
        "preview_snapshot": None,
        "total_weight": None,
        "overall_score": None,
    }
    payload.update(fields)
    if not isinstance(payload["config_snapshot"], str):
        payload["config_snapshot"] = json.dumps(payload["config_snapshot"])
    if payload.get("preview_snapshot") is not None and not isinstance(payload["preview_snapshot"], str):
        payload["preview_snapshot"] = json.dumps(payload["preview_snapshot"])
    connection.execute(
        text(
            """
            INSERT INTO team_configuration_versions (
                id, team_id, version_number, status, effective_month, effective_year,
                config_snapshot, config_checksum, effective_from_month, effective_from_year,
                effective_until_month, effective_until_year, performance_level, position_name,
                published_at, created_by_user_id, published_by_user_id, notes, is_active,
                preview_snapshot, total_weight, overall_score
            ) VALUES (
                :id, :team_id, :version_number, :status, :effective_month, :effective_year,
                CAST(:config_snapshot AS json), :config_checksum, :effective_from_month, :effective_from_year,
                :effective_until_month, :effective_until_year, :performance_level, :position_name,
                :published_at, :created_by_user_id, :published_by_user_id, :notes, :is_active,
                CAST(:preview_snapshot AS json), :total_weight, :overall_score
            )
            """
        ),
        payload,
    )
    return version_id


def _error_identity(caught: pytest.ExceptionInfo):
    orig = getattr(caught.value, "orig", None) or caught.value
    sqlstate = getattr(orig, "pgcode", None)
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)
    return sqlstate, constraint


def expect_denied(connection, statement: str, params: dict, fragment: str) -> None:
    if connection.in_transaction():
        connection.rollback()
    with pytest.raises(DBAPIError) as caught:
        with connection.begin():
            connection.execute(text(statement), params)
    assert fragment in str(caught.value)


def expect_constraint(
    connection,
    statement: str,
    params: dict,
    sqlstate: str,
    constraint_names: set[str],
    *,
    replica: bool = False,
) -> None:
    if connection.in_transaction():
        connection.rollback()
    with pytest.raises(DBAPIError) as caught:
        with connection.begin():
            if replica:
                connection.execute(text("SET LOCAL session_replication_role = 'replica'"))
            connection.execute(text(statement), params)
    found_state, found_constraint = _error_identity(caught)
    assert found_state == sqlstate, (found_state, found_constraint)
    assert found_constraint in constraint_names, (found_state, found_constraint)


def alembic_version(connection) -> str | None:
    exists = connection.execute(
        text("SELECT to_regclass('public.alembic_version')")
    ).scalar()
    if exists is None:
        return None
    return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()


@pytest.fixture(params=TARGETS, ids=lambda item: item["name"])
def pg(request):
    target = request.param
    engine = create_engine(url_for(target), poolclass=NullPool)
    with engine.connect() as connection:
        reset_public(connection, target)
        install_predecessor(connection, target)
    stamp(url_for(target), PREDECESSOR_REVISION)
    yield engine, target
    engine.dispose()


def test_predecessor_upgrade_preserves_legacy_and_canonicalizes_only_harmless_nulls(pg):
    engine, target = pg
    published_at = datetime(2026, 7, 2, tzinfo=timezone.utc)
    with engine.connect() as connection:
        ids = seed_base(connection, target)
        legacy_id = insert_version(
            connection,
            team_id=ids["team_id"],
            version_number=1,
            status="published",
            config_snapshot=LEGACY_SNAPSHOT,
            config_checksum="b" * 64,
            created_by_user_id=ids["user_id"],
            notes="legacy note",
            effective_month="Jul",
        )
        null_position_id = insert_version(
            connection,
            team_id=ids["team_id"],
            version_number=2,
            status="approved",
            performance_level="Employee",
            position_name=None,
            effective_until_month=7,
            effective_until_year=2026,
            published_at=published_at,
            created_by_user_id=ids["user_id"],
            config_snapshot={"policy": "employee_ratio", "lines": [{"kpi_key": "Quality"}]},
            config_checksum="c" * 64,
            preview_snapshot={"proof": 1},
            total_weight="1.0000",
            overall_score="88.00",
        )
        distinct_id = insert_version(
            connection,
            team_id=ids["team_id"],
            version_number=3,
            status="approved",
            performance_level="Employee",
            position_name="Media Buyer",
            effective_until_month=7,
            effective_until_year=2026,
            published_at=published_at,
            config_snapshot={"policy": "employee_ratio", "position": "Media Buyer"},
            config_checksum="d" * 64,
        )
        connection.commit()
    upgrade(url_for(target), REVISION)

    with engine.connect() as connection:
        assert_safe(connection, target)
        assert alembic_version(connection) == REVISION
        assert missing_history_objects(connection) == []
        legacy = connection.execute(
            text(
                """
                SELECT position_name, notes, config_snapshot::jsonb = CAST(:snapshot AS jsonb),
                       actor_created_snapshot->>'state', actor_created_snapshot::text,
                       created_by_user_id
                FROM team_configuration_versions WHERE id = :id
                """
            ),
            {"id": legacy_id, "snapshot": json.dumps(LEGACY_SNAPSHOT)},
        ).one()
        assert legacy[0] is None
        assert legacy[1] == "legacy note"
        assert legacy[2] is True
        assert legacy[3] == "unknown"
        assert "history-user" not in legacy[4]
        assert legacy[5] == ids["user_id"]
        positions = dict(
            connection.execute(
                text("SELECT id, position_name FROM team_configuration_versions WHERE id IN (:null_id, :distinct_id)"),
                {"null_id": null_position_id, "distinct_id": distinct_id},
            ).all()
        )
        assert positions[null_position_id] == ""
        assert positions[distinct_id] == "Media Buyer"


def test_duplicate_null_positions_refuse_without_deleting_or_choosing(pg):
    engine, target = pg
    published_at = datetime(2026, 7, 2, tzinfo=timezone.utc)
    with engine.connect() as connection:
        ids = seed_base(connection, target)
        install_ready = dict(
            team_id=ids["team_id"],
            status="approved",
            performance_level="Employee",
            position_name=None,
            effective_until_month=7,
            effective_until_year=2026,
            published_at=published_at,
            config_checksum="e" * 64,
        )
        first = insert_version(connection, version_number=1, **install_ready)
        second = insert_version(connection, version_number=2, config_checksum="f" * 64, **{
            key: value for key, value in install_ready.items() if key != "config_checksum"
        })
        connection.commit()
    with pytest.raises(Exception) as caught:
        upgrade(url_for(target), REVISION)
    assert "duplicate_monthly_binding" in str(caught.value)
    assert str(first) in str(caught.value) and str(second) in str(caught.value)
    with engine.connect() as connection:
        assert_safe(connection, target)
        assert alembic_version(connection) == PREDECESSOR_REVISION
        column = connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'team_configuration_versions'
                  AND column_name = 'actor_created_snapshot'
                """
            )
        ).scalar_one()
        assert column == 0
        rows = connection.execute(
            text("SELECT id, position_name FROM team_configuration_versions ORDER BY version_number")
        ).all()
        assert [(row[0], row[1]) for row in rows] == [(first, None), (second, None)]


def test_invalid_monthly_period_refuses_before_rewrite(pg):
    engine, target = pg
    with engine.connect() as connection:
        ids = seed_base(connection, target)
        version_id = insert_version(
            connection,
            team_id=ids["team_id"],
            version_number=1,
            status="approved",
            performance_level="Employee",
            position_name="",
            effective_until_month=None,
            effective_until_year=None,
            published_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )
        connection.commit()
    with pytest.raises(Exception) as caught:
        upgrade(url_for(target), REVISION)
    assert "invalid_monthly_version" in str(caught.value)
    assert str(version_id) in str(caught.value)
    with engine.connect() as connection:
        assert_safe(connection, target)
        assert alembic_version(connection) == PREDECESSOR_REVISION
        until = connection.execute(
            text("SELECT effective_until_month, position_name FROM team_configuration_versions WHERE id = :id"),
            {"id": version_id},
        ).one()
        assert until == (None, "")


def test_guards_reject_mutation_deletion_and_invalid_identity(pg):
    engine, target = pg
    published_at = datetime(2026, 7, 2, tzinfo=timezone.utc)
    with engine.connect() as connection:
        ids = seed_base(connection, target)
        approved_id = insert_version(
            connection,
            team_id=ids["team_id"],
            version_number=1,
            status="approved",
            performance_level="Employee",
            position_name="",
            effective_until_month=7,
            effective_until_year=2026,
            published_at=published_at,
            config_snapshot={"policy": "employee_ratio"},
            config_checksum="a" * 64,
            preview_snapshot={"proof": 1},
            total_weight="1.0000",
            overall_score="70.00",
            notes="approved note",
        )
        draft_id = insert_version(
            connection,
            team_id=ids["team_id"],
            version_number=2,
            status="draft",
            performance_level="Employee",
            position_name="",
            effective_month="August",
            effective_from_month=8,
            effective_until_month=8,
            effective_until_year=2026,
            published_at=None,
            config_checksum="b" * 64,
        )
        legacy_id = insert_version(
            connection,
            team_id=ids["team_id"],
            version_number=3,
            status="draft",
            effective_month="September",
            effective_from_month=9,
            published_at=published_at,
            notes="legacy draft",
            config_checksum="c" * 64,
        )
        connection.commit()
    upgrade(url_for(target), REVISION)

    with engine.connect() as connection:
        assert_safe(connection, target)
        expect_denied(
            connection,
            """
            UPDATE team_configuration_versions
            SET config_snapshot = CAST(:snapshot AS json), config_checksum = :checksum
            WHERE id = :id
            """,
            {"id": approved_id, "snapshot": json.dumps({"policy": "tampered"}), "checksum": "d" * 64},
            "approved monthly evaluation evidence is immutable",
        )
        expect_denied(
            connection,
            "UPDATE team_configuration_versions SET position_name = NULL WHERE id = :id",
            {"id": approved_id},
            "monthly evaluation identity cannot change",
        )
        expect_denied(
            connection,
            "UPDATE team_configuration_versions SET performance_level = NULL WHERE id = :id",
            {"id": approved_id},
            "monthly evaluation identity cannot change",
        )
        expect_denied(
            connection,
            "UPDATE team_configuration_versions SET published_at = NULL WHERE id = :id",
            {"id": approved_id},
            "approved monthly evaluation evidence is immutable",
        )
        expect_denied(
            connection,
            "DELETE FROM team_configuration_versions WHERE id = :id",
            {"id": approved_id},
            "monthly approved evaluation history cannot be deleted",
        )
        with connection.begin():
            connection.execute(
                text(
                    """
                    UPDATE team_configuration_versions
                    SET status = 'approved', published_at = :published_at,
                        config_snapshot = CAST(:snapshot AS json), config_checksum = :checksum,
                        actor_published_snapshot = CAST(:actor AS jsonb)
                    WHERE id = :id
                    """
                ),
                {
                    "id": draft_id,
                    "published_at": published_at,
                    "snapshot": json.dumps({"policy": "employee_ratio", "lines": [1]}),
                    "checksum": "e" * 64,
                    "actor": json.dumps({"state": "known", "user_id": str(ids["user_id"]), "username": "history-user"}),
                },
            )
        expect_denied(
            connection,
            "UPDATE team_configuration_versions SET config_checksum = :checksum WHERE id = :id",
            {"id": draft_id, "checksum": "f" * 64},
            "approved monthly evaluation evidence is immutable",
        )
        with connection.begin():
            connection.execute(
                text(
                    """
                    UPDATE team_configuration_versions
                    SET status = 'superseded', superseded_at = :superseded_at
                    WHERE id = :id
                    """
                ),
                {"id": draft_id, "superseded_at": published_at},
            )
        expect_denied(
            connection,
            "DELETE FROM team_configuration_versions WHERE id = :id",
            {"id": draft_id},
            "monthly approved evaluation history cannot be deleted",
        )
        expect_denied(
            connection,
            "UPDATE team_configuration_versions SET status = 'approved' WHERE id = :id",
            {"id": draft_id},
            "illegal monthly configuration status transition",
        )
        with connection.begin():
            connection.execute(
                text("UPDATE team_configuration_versions SET notes = 'still legacy' WHERE id = :id"),
                {"id": legacy_id},
            )
        expect_denied(
            connection,
            """
            UPDATE team_configuration_versions
            SET performance_level = 'Employee', position_name = ''
            WHERE id = :id
            """,
            {"id": legacy_id},
            "legacy configuration versions cannot become monthly bindings",
        )
        expect_denied(
            connection,
            """
            INSERT INTO team_configuration_versions (
                id, team_id, version_number, status, effective_month, effective_year,
                config_snapshot, config_checksum, effective_from_month, effective_from_year,
                effective_until_month, effective_until_year, performance_level, position_name,
                published_at
            ) VALUES (
                :id, :team_id, 9, 'approved', 'July', 2026, CAST('{"lines":[]}' AS json), :checksum,
                7, 2026, 7, 2026, 'Employee', '', :published_at
            )
            """,
            {
                "id": uuid.uuid4(),
                "team_id": ids["team_id"],
                "checksum": "9" * 64,
                "published_at": published_at,
            },
            "uq_team_config_one_approved_month",
        )
        expect_denied(
            connection,
            """
            INSERT INTO team_configuration_versions (
                id, team_id, version_number, status, effective_month, effective_year,
                config_snapshot, config_checksum, effective_from_month, effective_from_year,
                effective_until_month, effective_until_year, performance_level, position_name,
                published_at
            ) VALUES (
                :id, :team_id, 10, 'approved', 'July', 2026, CAST('{"lines":[]}' AS json), :checksum,
                13, 2026, 13, 2026, 'Employee', '', :published_at
            )
            """,
            {"id": uuid.uuid4(), "team_id": ids["team_id"], "checksum": "8" * 64, "published_at": published_at},
            "ck_team_config",
        )
        expect_denied(
            connection,
            """
            INSERT INTO team_configuration_versions (
                id, team_id, version_number, status, effective_month, effective_year,
                config_snapshot, config_checksum, effective_from_month, effective_from_year,
                effective_until_month, effective_until_year, performance_level, position_name,
                published_at
            ) VALUES (
                :id, :team_id, 11, 'approved', 'July', 2026, CAST('{"lines":[]}' AS json), :checksum,
                7, 2026, 8, 2026, 'Employee', 'Lead', :published_at
            )
            """,
            {"id": uuid.uuid4(), "team_id": ids["team_id"], "checksum": "7" * 64, "published_at": published_at},
            "ck_team_config_monthly_exact_period",
        )


def test_concurrent_approvals_allow_only_one_winner(pg):
    engine, target = pg
    with engine.connect() as connection:
        ids = seed_base(connection, target)
        connection.commit()
    upgrade(url_for(target), REVISION)
    inserted = threading.Event()
    release = threading.Event()
    results: dict[str, str] = {}

    def attempt(name: str, version_number: int, hold: bool) -> None:
        try:
            with engine.connect() as connection:
                assert_safe(connection, target)
                connection.rollback()
                with connection.begin():
                    connection.execute(text("SET LOCAL statement_timeout = '15000'"))
                    insert_version(
                        connection,
                        team_id=ids["team_id"],
                        version_number=version_number,
                        status="approved",
                        performance_level="Employee",
                        position_name="",
                        effective_month="October",
                        effective_from_month=10,
                        effective_until_month=10,
                        effective_until_year=2026,
                        published_at=datetime(2026, 10, 2, tzinfo=timezone.utc),
                        config_checksum=str(version_number) * 32,
                    )
                    if hold:
                        inserted.set()
                        if not release.wait(20):
                            raise TimeoutError("winner was not released")
            results[name] = "committed"
        except Exception as exc:
            results[name] = f"{exc.__class__.__name__}: {exc}"

    winner = threading.Thread(target=attempt, args=("winner", 50, True))
    loser = threading.Thread(target=attempt, args=("loser", 51, False))
    winner.start()
    if not inserted.wait(15):
        release.set()
        winner.join(10)
        raise AssertionError(f"winner did not insert: {results}")
    loser.start()
    threading.Event().wait(0.5)
    release.set()
    winner.join(20)
    loser.join(20)
    assert results.get("winner") == "committed", results
    assert "IntegrityError" in results.get("loser", "") or "UniqueViolation" in results.get("loser", ""), results
    with engine.connect() as connection:
        assert_safe(connection, target)
        count = connection.execute(
            text(
                """
                SELECT count(*) FROM team_configuration_versions
                WHERE performance_level = 'Employee' AND position_name = ''
                  AND effective_from_year = 2026 AND effective_from_month = 10
                  AND status = 'approved'
                """
            )
        ).scalar_one()
        assert count == 1


def test_history_survives_team_restriction_and_user_set_null(pg):
    engine, target = pg
    published_at = datetime(2026, 7, 2, tzinfo=timezone.utc)
    with engine.connect() as connection:
        ids = seed_base(connection, target)
        version_id = insert_version(
            connection,
            team_id=ids["team_id"],
            version_number=1,
            status="approved",
            performance_level="Employee",
            position_name="Lead",
            effective_until_month=7,
            effective_until_year=2026,
            published_at=published_at,
            created_by_user_id=ids["user_id"],
            published_by_user_id=ids["user_id"],
        )
        connection.commit()
    upgrade(url_for(target), REVISION)
    actor = json.dumps({"state": "known", "user_id": str(ids["user_id"]), "username": "history-user", "role": "Admin"})
    revision_id = uuid.uuid4()
    with engine.connect() as connection:
        assert_safe(connection, target)
        expect_denied(
            connection,
            """
            UPDATE team_configuration_versions
            SET actor_created_snapshot = CAST(:actor AS jsonb)
            WHERE id = :id
            """,
            {"id": version_id, "actor": actor},
            "monthly evaluation identity cannot change",
        )
    # The unknown backfill stays. A later approved month can store a known actor at insert.
    with engine.connect() as connection:
        assert_safe(connection, target)
        connection.rollback()
        known_id = uuid.uuid4()
        with connection.begin():
            connection.execute(
                text(
                    """
                    INSERT INTO team_configuration_versions (
                        id, team_id, version_number, status, effective_month, effective_year,
                        config_snapshot, config_checksum, effective_from_month, effective_from_year,
                        effective_until_month, effective_until_year, performance_level, position_name,
                        published_at, created_by_user_id, published_by_user_id,
                        actor_created_snapshot, actor_published_snapshot
                    ) VALUES (
                        :id, :team_id, 4, 'approved', 'November', 2026,
                        CAST('{"policy":"employee_ratio"}' AS json), :checksum, 11, 2026,
                        11, 2026, 'Employee', 'Lead', :published_at, :user_id, :user_id,
                        CAST(:actor AS jsonb), CAST(:actor AS jsonb)
                    )
                    """
                ),
                {
                    "id": known_id,
                    "team_id": ids["team_id"],
                    "checksum": "4" * 64,
                    "published_at": published_at,
                    "user_id": ids["user_id"],
                    "actor": actor,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO evaluation_revisions (
                        id, team_id, performance_level, position_name, year, month, version_id,
                        status, prior_snapshot, applied_snapshot, created_by_user_id, actor_snapshot
                    ) VALUES (
                        :id, :team_id, 'Employee', 'Lead', 2026, 11, :version_id,
                        'active', CAST('{"records":[]}' AS jsonb), CAST('{"records":[1]}' AS jsonb),
                        :user_id, CAST(:actor AS jsonb)
                    )
                    """
                ),
                {"id": revision_id, "team_id": ids["team_id"], "version_id": known_id, "user_id": ids["user_id"], "actor": actor},
            )
        constraints = connection.execute(
            text(
                """
                SELECT con.conname, con.confdeltype
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = con.conkey[1]
                WHERE con.contype = 'f' AND att.attname = 'team_id'
                  AND rel.relname IN ('team_configuration_versions', 'evaluation_revisions')
                """
            )
        ).all()
        assert sorted(row[0] for row in constraints) == [
            "evaluation_revisions_team_id_fkey",
            "team_configuration_versions_team_id_fkey",
        ]
        assert {row[1] for row in constraints} == {"r"}
        # RESTRICT is 23503 on this PG16 and 23001 (restrict_violation) on this PG18.
        restrict_sqlstate = "23001" if target["name"] == "pg18" else "23503"
        expect_constraint(
            connection,
            "DELETE FROM teams WHERE id = :id",
            {"id": ids["team_id"]},
            restrict_sqlstate,
            {row[0] for row in constraints},
        )
        with connection.begin():
            connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": ids["user_id"]})
        version = connection.execute(
            text(
                """
                SELECT created_by_user_id, published_by_user_id, actor_created_snapshot::text
                FROM team_configuration_versions WHERE id = :id
                """
            ),
            {"id": known_id},
        ).one()
        revision = connection.execute(
            text(
                """
                SELECT created_by_user_id, actor_snapshot::text
                FROM evaluation_revisions WHERE id = :id
                """
            ),
            {"id": revision_id},
        ).one()
        assert version[0] is None and version[1] is None
        assert "history-user" in version[2]
        assert revision[0] is None
        assert "history-user" in revision[1]
        expect_denied(
            connection,
            "UPDATE evaluation_revisions SET prior_snapshot = CAST('{\"records\":[9]}' AS jsonb) WHERE id = :id",
            {"id": revision_id},
            "evaluation revision evidence is immutable",
        )
        expect_denied(
            connection,
            "DELETE FROM evaluation_revisions WHERE id = :id",
            {"id": revision_id},
            "evaluation revision history cannot be deleted",
        )
        with connection.begin():
            connection.execute(
                text("UPDATE evaluation_revisions SET status = 'rolled_back' WHERE id = :id"),
                {"id": revision_id},
            )
        expect_denied(
            connection,
            "UPDATE evaluation_revisions SET status = 'active' WHERE id = :id",
            {"id": revision_id},
            "illegal evaluation revision status transition",
        )


def test_populated_downgrade_refuses_and_preserves_guards(pg):
    engine, target = pg
    with engine.connect() as connection:
        ids = seed_base(connection, target)
        version_id = insert_version(
            connection,
            team_id=ids["team_id"],
            version_number=1,
            status="approved",
            performance_level="Employee",
            position_name="",
            effective_until_month=7,
            effective_until_year=2026,
            published_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
            config_checksum="a" * 64,
        )
        connection.commit()
    upgrade(url_for(target), REVISION)
    with pytest.raises(Exception) as caught:
        downgrade(url_for(target), PREDECESSOR_REVISION)
    assert "Refusing to drop monthly evaluation history guards" in str(caught.value)
    with engine.connect() as connection:
        assert_safe(connection, target)
        assert alembic_version(connection) == REVISION
        assert missing_history_objects(connection) == []
        expect_denied(
            connection,
            "UPDATE team_configuration_versions SET config_checksum = :checksum WHERE id = :id",
            {"id": version_id, "checksum": "b" * 64},
            "approved monthly evaluation evidence is immutable",
        )


def test_empty_downgrade_and_reupgrade_preserve_legacy_rows(pg):
    engine, target = pg
    with engine.connect() as connection:
        ids = seed_base(connection, target)
        legacy_id = insert_version(
            connection,
            team_id=ids["team_id"],
            version_number=1,
            config_snapshot=LEGACY_SNAPSHOT,
            config_checksum="c" * 64,
            notes="keep me",
        )
        connection.commit()
    url = url_for(target)
    upgrade(url, REVISION)
    downgrade(url, PREDECESSOR_REVISION)
    with engine.connect() as connection:
        assert_safe(connection, target)
        assert alembic_version(connection) == PREDECESSOR_REVISION
        assert any("actor_created_snapshot" in item for item in missing_history_objects(connection))
        legacy = connection.execute(
            text(
                """
                SELECT notes, position_name, config_snapshot::jsonb = CAST(:snapshot AS jsonb)
                FROM team_configuration_versions WHERE id = :id
                """
            ),
            {"id": legacy_id, "snapshot": json.dumps(LEGACY_SNAPSHOT)},
        ).one()
        assert legacy == ("keep me", None, True)
        ondelete = connection.execute(
            text(
                """
                SELECT con.confdeltype
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = con.conkey[1]
                WHERE rel.relname = 'team_configuration_versions' AND att.attname = 'team_id'
                  AND con.contype = 'f'
                """
            )
        ).scalar_one()
        assert ondelete == "c"
    upgrade(url, REVISION)
    with engine.connect() as connection:
        assert_safe(connection, target)
        assert missing_history_objects(connection) == []
        legacy = connection.execute(
            text(
                """
                SELECT notes, position_name, actor_created_snapshot->>'state',
                       config_snapshot::jsonb = CAST(:snapshot AS jsonb)
                FROM team_configuration_versions WHERE id = :id
                """
            ),
            {"id": legacy_id, "snapshot": json.dumps(LEGACY_SNAPSHOT)},
        ).one()
        assert legacy == ("keep me", None, "unknown", True)


def test_bootstrap_matches_migration_and_reports_root_failure_separately(pg):
    from services.evaluation.apply_job_schema import (
        APPLY_FOUNDATION_REVISION,
        missing_apply_foundation_objects,
    )

    engine, target = pg
    url = url_for(target)
    with engine.connect() as connection:
        ids = seed_base(connection, target)
        insert_version(connection, team_id=ids["team_id"], version_number=1, config_checksum="d" * 64)
        connection.commit()
    upgrade(url, REVISION)
    with engine.connect() as connection:
        migrated = history_schema_signature(connection)

    with engine.connect() as connection:
        reset_public(connection, target)
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "scripts/bootstrap_schema.py"],
        cwd=BACKEND,
        env=allowlisted_env(url, target),
        capture_output=True,
        text=True,
        check=False,
    )
    combined = (completed.stderr + completed.stdout).replace(PASSWORD, "***")
    assert completed.returncode == 0, combined
    assert "HISTORICAL_REPLAY_ROOT_FAILURE" not in combined
    assert "FRESH_SCHEMA_BOOTSTRAP" in completed.stdout
    assert "Not a replay of the historical migration chain." in completed.stdout
    assert f"Root revision {ROOT_REVISION} is not executed" in completed.stdout
    assert f"database={target['database']}" in completed.stdout
    assert "historical migration chain replay succeeded" not in completed.stdout.casefold()
    exact_period = migrated["version_checks"]["ck_team_config_monthly_exact_period"].casefold()
    assert "effective_until_month is not null" in exact_period
    assert "effective_until_year is not null" in exact_period
    version_guard = migrated["guard_functions"]["guard_team_configuration_version"].casefold()
    revision_guard = migrated["guard_functions"]["guard_evaluation_revision"].casefold()
    assert "approved monthly evaluation evidence is immutable" in version_guard
    assert "evaluation revision evidence is immutable" in revision_guard
    with engine.connect() as connection:
        assert_safe(connection, target)
        # Fresh bootstrap stamps the current head, not this historical upgrade's
        # fixed revision. Keep the exact historical signature comparison below
        # and additionally verify every new foundation guard/constraint.
        assert alembic_version(connection) == APPLY_FOUNDATION_REVISION
        assert history_schema_signature(connection) == migrated
        assert missing_apply_foundation_objects(connection) == []

    with engine.connect() as connection:
        reset_public(connection, target)
        assert_safe(connection, target)
        connection.execute(text("CREATE TABLE leftover (id integer)"))
        connection.commit()
    refused = subprocess.run(
        [sys.executable, "-X", "utf8", "scripts/bootstrap_schema.py"],
        cwd=BACKEND,
        env=allowlisted_env(url, target),
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode != 0
    assert "existing tables but no alembic_version" in (refused.stderr + refused.stdout)
    with engine.connect() as connection:
        assert_safe(connection, target)
        assert alembic_version(connection) is None
        assert connection.execute(text("SELECT to_regclass('public.leftover')")).scalar() == "leftover"


def test_monthly_end_nulls_fail_the_check_on_insert_and_update(pg):
    engine, target = pg
    with engine.connect() as connection:
        ids = seed_base(connection, target)
        legacy_id = insert_version(
            connection,
            team_id=ids["team_id"],
            version_number=1,
            status="published",
            effective_month="Jul",
            effective_year=1999,
            effective_from_month=7,
            effective_from_year=1999,
            notes="open legacy",
            config_checksum="b" * 64,
        )
        connection.commit()
    upgrade(url_for(target), REVISION)
    insert_sql = """
        INSERT INTO team_configuration_versions (
            id, team_id, version_number, status, effective_month, effective_year,
            config_snapshot, config_checksum, effective_from_month, effective_from_year,
            effective_until_month, effective_until_year, performance_level, position_name
        ) VALUES (
            :id, :team_id, :version_number, 'draft', 'July', 2026,
            CAST('{"policy":"employee_ratio"}' AS json), :checksum,
            7, 2026, :until_month, :until_year, 'Employee', ''
        )
    """
    shapes = (
        (None, 2026, 20),
        (7, None, 21),
        (None, None, 22),
    )
    with engine.connect() as connection:
        assert_safe(connection, target)
        for until_month, until_year, version_number in shapes:
            expect_constraint(
                connection,
                insert_sql,
                {
                    "id": uuid.uuid4(),
                    "team_id": ids["team_id"],
                    "version_number": version_number,
                    "checksum": "c" * 64,
                    "until_month": until_month,
                    "until_year": until_year,
                },
                "23514",
                {"ck_team_config_monthly_exact_period"},
            )
        draft_id = uuid.uuid4()
        with connection.begin():
            connection.execute(
                text(insert_sql),
                {
                    "id": draft_id,
                    "team_id": ids["team_id"],
                    "version_number": 23,
                    "checksum": "d" * 64,
                    "until_month": 7,
                    "until_year": 2026,
                },
            )
        for assignment in (
            "effective_until_month = NULL",
            "effective_until_year = NULL",
            "effective_until_month = NULL, effective_until_year = NULL",
        ):
            expect_constraint(
                connection,
                f"UPDATE team_configuration_versions SET {assignment} WHERE id = :id",
                {"id": draft_id},
                "23514",
                {"ck_team_config_monthly_exact_period"},
                replica=True,
            )
        draft = connection.execute(
            text(
                """
                SELECT effective_until_month, effective_until_year
                FROM team_configuration_versions WHERE id = :id
                """
            ),
            {"id": draft_id},
        ).one()
        assert draft == (7, 2026)
        connection.rollback()
        with connection.begin():
            connection.execute(
                text("UPDATE team_configuration_versions SET notes = 'still open' WHERE id = :id"),
                {"id": legacy_id},
            )
        legacy = connection.execute(
            text(
                """
                SELECT notes, effective_until_month, effective_until_year, position_name, performance_level
                FROM team_configuration_versions WHERE id = :id
                """
            ),
            {"id": legacy_id},
        ).one()
        assert legacy == ("still open", None, None, None, None)


def test_historical_root_replay_fails_independently_of_fresh_bootstrap(pg):
    engine, target = pg
    url = url_for(target)
    with engine.connect() as connection:
        reset_public(connection, target)
    with pytest.raises(Exception) as caught:
        upgrade(url, ROOT_REVISION)
    detail = str(caught.value).replace(PASSWORD, "***")
    assert PASSWORD not in detail
    folded = detail.casefold()
    assert any(token in folded for token in ("employees", "does not exist", "undefinedtable")), detail
    with engine.connect() as connection:
        assert_safe(connection, target)
        tables = connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        ).scalars().all()
        assert list(tables) == []
        assert alembic_version(connection) is None
