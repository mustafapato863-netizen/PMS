"""Phase 1A baseline: ORM mapping and PostgreSQL version-groundwork reconciliation.

PostgreSQL cases write only to an explicit disposable URL. They refuse every
other target, including a DATABASE_URL inherited from the environment.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.pool import NullPool

from models.models import (
    Base,
    Employee,
    PerformanceRecord,
    Team,
    TeamConfigurationVersion,
    User,
)


BACKEND = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    BACKEND / "migrations" / "versions" / "f1a9c3e7d842_reconcile_team_configuration_version_groundwork.py"
)
REVISION = "f1a9c3e7d842"
PRIOR_REVISION = "d9e4b7a2c106"
PG18_URL = "postgresql://pms_eval_test:pms-local-disposable-test@127.0.0.1:55433/pms_eval_foundation18"
PG16_URL = "postgresql://pms_eval_test:pms-local-disposable-test@127.0.0.1:55432/pms_eval_foundation16"
ALLOWED_URLS = {PG18_URL, PG16_URL}
ALLOWED_PAIRS = {55433: "pms_eval_foundation18", 55432: "pms_eval_foundation16"}

TEAM_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
USER_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
VERSION_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
OTHER_VERSION_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
ORPHAN_VERSION_ID = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
CROSS_YEAR_VERSION_ID = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
LEGACY_RECORD_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
LINKED_RECORD_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")
KPI_ID = uuid.UUID("66666666-6666-4666-8666-666666666666")
CONFIG_ID = uuid.UUID("77777777-7777-4777-8777-777777777777")
HISTORY_ID = uuid.UUID("88888888-8888-4888-8888-888888888888")
SNAPSHOT_ID = uuid.UUID("99999999-9999-4999-8999-999999999999")
CHECKSUM = "ab" * 32
SNAPSHOT = {
    "grade_thresholds": {"A": 90},
    "kpis": [{"key": "synthetic_kpi", "weight": 1}],
    "schema_version": 1,
    "team": "Synthetic",
    "workbook_mapping": {"sheet": "Synthetic"},
}
PREVIEW = {"sentinel": "preview"}
RAW_PAYLOAD = {"calls": 4, "raw": "sentinel"}

requires_disposable_pg = pytest.mark.skipif(
    not os.environ.get("PMS_EVAL_SCHEMA_TEST_URL"),
    reason="Set PMS_EVAL_SCHEMA_TEST_URL to an allowlisted disposable database.",
)


def assert_allowlisted(url: str) -> None:
    if os.environ.get("APP_ENV", "").strip().lower() != "test":
        raise RuntimeError("APP_ENV=test is required before touching a schema test database.")
    parsed = urlparse(url)
    database = parsed.path.lstrip("/")
    if (
        url not in ALLOWED_URLS
        or parsed.scheme != "postgresql"
        or parsed.hostname != "127.0.0.1"
        or parsed.username != "pms_eval_test"
        or parsed.port not in ALLOWED_PAIRS
        or ALLOWED_PAIRS[parsed.port] != database
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            f"Refusing schema test target host={parsed.hostname!r} port={parsed.port!r} database={database!r}."
        )


def _load_migration():
    spec = importlib.util.spec_from_file_location("reconcile_team_configuration_versions", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    return ScriptDirectory.from_config(config)


def test_reconciliation_revision_stays_in_the_single_head_ancestry():
    scripts = _script_directory()
    heads = scripts.get_heads()
    assert len(heads) == 1
    revision = scripts.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PRIOR_REVISION
    ancestors = _ancestors(scripts, heads[0])
    assert REVISION in ancestors
    assert PRIOR_REVISION in ancestors


def _ancestors(scripts: ScriptDirectory, revision: str) -> set[str]:
    found: set[str] = set()
    stack = [revision]
    while stack:
        current = stack.pop()
        if current in found:
            continue
        found.add(current)
        script = scripts.get_revision(current)
        if script is None or script.down_revision is None:
            continue
        down = script.down_revision
        if isinstance(down, tuple):
            stack.extend(str(item) for item in down)
        else:
            stack.append(str(down))
    return found


def _current_head() -> str:
    heads = _script_directory().get_heads()
    assert len(heads) == 1
    return heads[0]


def test_schema_target_guard_rejects_other_databases(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    assert_allowlisted(PG18_URL)
    assert_allowlisted(PG16_URL)
    with pytest.raises(RuntimeError):
        assert_allowlisted("postgresql://pms_eval_test:pms-local-disposable-test@localhost:55433/pms_eval_foundation18")
    with pytest.raises(RuntimeError):
        assert_allowlisted("postgresql://pms_eval_test:pms-local-disposable-test@127.0.0.1:5432/pms_eval_foundation18")
    with pytest.raises(RuntimeError):
        assert_allowlisted("postgresql://pms_eval_test:pms-local-disposable-test@127.0.0.1:55433/postgres")
    with pytest.raises(RuntimeError):
        assert_allowlisted(PG18_URL + "?sslmode=disable")
    monkeypatch.setenv("APP_ENV", "development")
    with pytest.raises(RuntimeError):
        assert_allowlisted(PG18_URL)


def test_downgrade_sql_retains_version_evidence_and_offline_upgrade_is_refused():
    migration = _load_migration()
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    with Operations.context(context):
        with pytest.raises(RuntimeError, match="cannot emit offline SQL"):
            migration.upgrade()
    with Operations.context(context):
        migration.downgrade()
    sql = output.getvalue().upper()
    assert "DROP TABLE" not in sql
    assert "DROP COLUMN" not in sql
    assert "DELETE FROM" not in sql
    assert "UPDATE " not in sql


def test_upgrade_refuses_non_postgresql_without_touching_schema():
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match="PostgreSQL"):
                migration.upgrade()
    engine.dispose()


def test_orm_metadata_matches_audited_version_contract():
    table = TeamConfigurationVersion.__table__
    assert [column.name for column in table.primary_key.columns] == ["id"]
    nullable = {column.name: column.nullable for column in table.columns}
    assert nullable["effective_from_month"] is False
    assert nullable["effective_from_year"] is False
    assert nullable["effective_until_month"] is True
    assert nullable["effective_until_year"] is True
    assert nullable["preview_snapshot"] is True
    assert nullable["total_weight"] is True
    assert nullable["overall_score"] is True
    assert nullable["is_active"] is False
    assert nullable["config_snapshot"] is False
    assert nullable["created_by_user_id"] is True
    constraint_names = {constraint.name for constraint in table.constraints}
    assert {
        "uq_team_config_version",
        "ck_team_config_effective_from_month",
        "ck_team_config_effective_until_month",
        "ck_team_config_effective_range",
    } <= constraint_names
    coverage = next(index for index in table.indexes if index.name == "idx_team_config_coverage")
    assert [column.name for column in coverage.columns] == [
        "team_id",
        "status",
        "effective_from_year",
        "effective_from_month",
        "effective_until_year",
        "effective_until_month",
    ]
    assert coverage.unique is False
    team_fk = next(fk for fk in table.c.team_id.foreign_keys)
    actor_fk = next(fk for fk in table.c.created_by_user_id.foreign_keys)
    assert team_fk.ondelete == "CASCADE"
    assert actor_fk.ondelete == "SET NULL"
    record = PerformanceRecord.__table__.c.configuration_version_id
    assert record.nullable is True
    record_fk = next(iter(record.foreign_keys))
    assert record_fk.ondelete == "SET NULL"
    assert record_fk.constraint.name == "fk_performance_records_configuration_version"
    assert [column.name for column in PerformanceRecord.__table__.primary_key.columns] == ["id", "year"]


def test_sqlite_orm_roundtrip_preserves_version_row_and_legacy_null_link():
    engine = sa.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            Team.__table__,
            Employee.__table__,
            TeamConfigurationVersion.__table__,
            PerformanceRecord.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    team = Team(name="Synthetic Team", db_name="synthetic_team", region="UAE", team_level="employee")
    user = User(
        username="synth-admin",
        email="synth-admin@example.com",
        password_hash="synthetic-hash",
        full_name="Synthetic Admin",
    )
    session.add_all([team, user])
    session.flush()
    employee = Employee(employee_id="SYNTH-1", name="Synthetic Employee", team_id=team.id, region="UAE")
    session.add(employee)
    session.flush()
    version = TeamConfigurationVersion(
        team_id=team.id,
        version_number=1,
        status="published",
        effective_month="July",
        effective_year=2026,
        config_snapshot=SNAPSHOT,
        config_checksum=CHECKSUM,
        created_by_user_id=user.id,
        effective_from_month=8,
        effective_from_year=2025,
        preview_snapshot=PREVIEW,
        total_weight=Decimal("1.2500"),
        overall_score=Decimal("88.50"),
        is_active=True,
        notes="synthetic-version",
    )
    session.add(version)
    session.flush()
    legacy = PerformanceRecord(
        employee_id=employee.id,
        team_id=team.id,
        month="July",
        year=2026,
        score=Decimal("80.00"),
        grade="B",
        status="Meets",
        record_payload=RAW_PAYLOAD,
    )
    linked = PerformanceRecord(
        employee_id=employee.id,
        team_id=team.id,
        month="August",
        year=2026,
        score=Decimal("91.00"),
        grade="A",
        status="Exceeds",
        record_payload={"raw": "linked"},
        configuration_version_id=version.id,
    )
    session.add_all([legacy, linked])
    session.commit()
    version_id = version.id
    legacy_id = legacy.id
    linked_id = linked.id
    session.expire_all()

    stored = session.get(TeamConfigurationVersion, version_id)
    assert stored.config_snapshot == SNAPSHOT
    assert stored.preview_snapshot == PREVIEW
    assert stored.config_checksum == CHECKSUM
    assert stored.effective_month == "July"
    assert stored.effective_from_month == 8
    assert stored.effective_from_year == 2025
    assert stored.effective_until_month is None
    assert Decimal(stored.total_weight) == Decimal("1.2500")
    assert Decimal(stored.overall_score) == Decimal("88.50")
    assert stored.is_active is True
    assert stored.team.db_name == "synthetic_team"
    assert stored.created_by_user.username == "synth-admin"
    legacy_row = session.query(PerformanceRecord).filter_by(id=legacy_id, year=2026).one()
    linked_row = session.query(PerformanceRecord).filter_by(id=linked_id, year=2026).one()
    assert legacy_row.configuration_version_id is None
    assert legacy_row.configuration_version is None
    assert legacy_row.record_payload == RAW_PAYLOAD
    assert linked_row.configuration_version_id == version_id
    assert linked_row.configuration_version.config_checksum == CHECKSUM
    assert {row.id for row in stored.performance_records} == {linked_id}

    session.add(
        TeamConfigurationVersion(
            team_id=team.id,
            version_number=1,
            status="draft",
            effective_month="August",
            effective_year=2026,
            config_snapshot={"schema_version": 2},
            config_checksum=CHECKSUM,
            effective_from_month=8,
            effective_from_year=2026,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.add(
        TeamConfigurationVersion(
            team_id=team.id,
            version_number=2,
            status="draft",
            effective_month="August",
            effective_year=2026,
            config_snapshot={"schema_version": 2},
            config_checksum=CHECKSUM,
            effective_from_month=13,
            effective_from_year=2026,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.close()
    engine.dispose()


@requires_disposable_pg
def test_old_head_bootstrap_shape_reconciles_without_inventing_history(pg_engine):
    engine, url = pg_engine
    with engine.begin() as conn:
        _install_support(conn)
        _install_performance(conn, partitioned=False, with_version_column=False)
        _install_sentinels(conn, linked=False)
        _stamp(conn, PRIOR_REVISION)
        before = _preserved_rows(conn)
    _alembic(url, "upgrade", "head")
    with engine.begin() as conn:
        assert _version_count(conn) == 0
        assert _legacy_link(conn) is None
        assert _preserved_rows(conn) == before
        assert _relkind(conn, "performance_records") == "r"
        assert _child_partitions(conn) == []
        _assert_single_groundwork(conn)
        after_upgrade = _groundwork_fingerprint(conn)
    _run_upgrade_again(url)
    with engine.begin() as conn:
        assert _groundwork_fingerprint(conn) == after_upgrade
        assert _preserved_rows(conn) == before
        _insert_version_evidence(conn)
        evidence = _version_rows(conn)
        linked = _linked_row(conn)
        with_evidence = _preserved_rows(conn)
    _alembic(url, "downgrade", PRIOR_REVISION)
    with engine.begin() as conn:
        assert _alembic_version(conn) == PRIOR_REVISION
        assert _version_rows(conn) == evidence
        assert _linked_row(conn) == linked
        assert _legacy_link(conn) is None
        assert _preserved_rows(conn) == with_evidence
        _assert_single_groundwork(conn)
    _alembic(url, "upgrade", "head")
    with engine.begin() as conn:
        assert _alembic_version(conn) == _current_head()
        assert _version_rows(conn) == evidence
        assert _linked_row(conn) == linked
        assert _preserved_rows(conn) == with_evidence
        _assert_single_groundwork(conn)


@requires_disposable_pg
def test_migrated_partitioned_shape_preserves_rows_and_does_not_duplicate_keys(pg_engine):
    engine, url = pg_engine
    with engine.begin() as conn:
        _install_support(conn)
        _install_version_table(conn)
        _insert_existing_version(conn)
        _install_performance(conn, partitioned=True, with_version_column=True)
        _install_record_fk(conn)
        _install_sentinels(conn, linked=True)
        _stamp(conn, PRIOR_REVISION)
        before_rows = _preserved_rows(conn)
        before_versions = _version_rows(conn)
        before_links = _record_links(conn)
        before_fingerprint = _groundwork_fingerprint(conn)
    _alembic(url, "upgrade", "head")
    _run_upgrade_again(url)
    with engine.begin() as conn:
        assert _preserved_rows(conn) == before_rows
        assert _version_rows(conn) == before_versions
        assert _record_links(conn) == before_links
        assert _version_rows(conn)[0]["effective_month"] == "July"
        assert _version_rows(conn)[0]["effective_from_month"] == 8
        assert _groundwork_fingerprint(conn) == before_fingerprint
        _assert_single_groundwork(conn)
        _assert_partition_fk_parent(conn)
        assert _child_partitions(conn) == ["performance_records_2026", "performance_records_default"]
    _alembic(url, "downgrade", PRIOR_REVISION)
    _alembic(url, "upgrade", "head")
    with engine.begin() as conn:
        assert _alembic_version(conn) == _current_head()
        assert _preserved_rows(conn) == before_rows
        assert _version_rows(conn) == before_versions
        assert _record_links(conn) == before_links
        assert _groundwork_fingerprint(conn) == before_fingerprint
        _assert_partition_fk_parent(conn)


@requires_disposable_pg
def test_missing_nullable_preview_is_added_without_rewriting_rows(pg_engine):
    engine, url = pg_engine
    with engine.begin() as conn:
        _install_support(conn)
        _install_version_table(conn, include_preview=False)
        _install_performance(conn, partitioned=False, with_version_column=True)
        _install_record_fk(conn)
        _insert_existing_version(conn)
        _stamp(conn, PRIOR_REVISION)
        before = _version_rows(conn)
        assert "preview_snapshot" not in before[0]
    _alembic(url, "upgrade", "head")
    _run_upgrade_again(url)
    with engine.begin() as conn:
        stored = _version_rows(conn)[0]
        assert stored["preview_snapshot"] is None
        without_preview = {key: value for key, value in stored.items() if key != "preview_snapshot"}
        assert without_preview == before[0]
        assert _column_count(conn, "team_configuration_versions", "preview_snapshot") == 1


@requires_disposable_pg
def test_incompatible_snapshot_type_fails_without_rewriting_rows(pg_engine):
    engine, url = pg_engine
    with engine.begin() as conn:
        _install_support(conn)
        _install_version_table(conn, snapshot_type="jsonb")
        _install_performance(conn, partitioned=True, with_version_column=True)
        _install_record_fk(conn)
        _insert_existing_version(conn)
        _stamp(conn, PRIOR_REVISION)
        before = _version_rows(conn)
        fingerprint = _groundwork_fingerprint(conn)
    result = _alembic(url, "upgrade", "head", check=False)
    assert result.returncode != 0
    assert "config_snapshot" in f"{result.stdout}\n{result.stderr}"
    with engine.begin() as conn:
        assert _alembic_version(conn) == PRIOR_REVISION
        assert _version_rows(conn) == before
        assert _groundwork_fingerprint(conn) == fingerprint
        assert _column_udt(conn, "team_configuration_versions", "config_snapshot") == "jsonb"


@requires_disposable_pg
def test_incompatible_record_fk_action_is_not_replaced(pg_engine):
    engine, url = pg_engine
    with engine.begin() as conn:
        _install_support(conn)
        _install_version_table(conn)
        _install_performance(conn, partitioned=True, with_version_column=True)
        _install_record_fk(conn, on_delete="CASCADE")
        _insert_existing_version(conn)
        _stamp(conn, PRIOR_REVISION)
        before = _version_rows(conn)
    result = _alembic(url, "upgrade", "head", check=False)
    assert result.returncode != 0
    assert "configuration_version_id" in f"{result.stdout}\n{result.stderr}"
    with engine.begin() as conn:
        assert _alembic_version(conn) == PRIOR_REVISION
        assert _version_rows(conn) == before
        assert _record_fk_delete_action(conn) == "c"
        assert _parent_record_fk_count(conn) == 1


@requires_disposable_pg
def test_named_unique_on_other_columns_is_rejected_without_mutation(pg_engine):
    engine, url = pg_engine
    with engine.begin() as conn:
        _install_support(conn)
        _install_version_table(conn)
        _install_performance(conn, partitioned=False, with_version_column=False)
        _replace_unique_with_extra_column(conn)
        _insert_existing_version(conn)
        _stamp(conn, PRIOR_REVISION)
        before_rows = _version_rows(conn)
        before_fingerprint = _groundwork_fingerprint(conn)
    _assert_upgrade_rejected(engine, url, before_fingerprint, "uq_team_config_version", "team_id_extra")
    with engine.begin() as conn:
        assert _version_rows(conn) == before_rows
        assert _column_count(conn, "performance_records", "configuration_version_id") == 0
        assert _unique_key_columns(conn, "uq_team_config_version") == ("team_id_extra", "version_number")
        _insert_existing_version(conn, OTHER_VERSION_ID)
        stored = _fetch(
            conn,
            """
            SELECT team_id::text, version_number
            FROM public.team_configuration_versions
            ORDER BY id::text
            """,
        )
    assert stored == [(str(TEAM_ID), 1), (str(TEAM_ID), 1)]


@requires_disposable_pg
def test_exact_team_version_unique_rejects_duplicate_rows(pg_engine):
    engine, url = pg_engine
    with engine.begin() as conn:
        _install_support(conn)
        _install_performance(conn, partitioned=False, with_version_column=False)
        _stamp(conn, PRIOR_REVISION)
    _alembic(url, "upgrade", "head")
    with engine.begin() as conn:
        _insert_existing_version(conn)
        assert _unique_key_columns(conn, "uq_team_config_version") == ("team_id", "version_number")
    with pytest.raises(IntegrityError, match="uq_team_config_version"):
        with engine.begin() as conn:
            _insert_existing_version(conn, OTHER_VERSION_ID)
    with engine.begin() as conn:
        assert _version_count(conn) == 1
        assert _version_rows(conn)[0]["id"] == str(VERSION_ID)


@requires_disposable_pg
def test_public_schema_is_repaired_when_search_path_prefers_shadow(pg_engine):
    engine, url = pg_engine
    search_path = "shadow_review,public"
    with engine.begin() as conn:
        _install_support(conn)
        _install_performance(conn, partitioned=False, with_version_column=False)
        _install_sentinels(conn, linked=False)
        _install_shadow_support(conn)
        _stamp(conn, PRIOR_REVISION)
        before_rows = _preserved_rows(conn)
        before_shadow = _relations(conn, "shadow_review")
    probe = _run_python_text(url, "import sqlalchemy as sa; print(sa.create_engine(__import__('os').environ['DATABASE_URL']).connect().execute(sa.text('SHOW search_path')).scalar_one())", search_path)
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip().startswith("shadow_review")
    assert "public" in probe.stdout
    _alembic(url, "upgrade", "head", search_path=search_path)
    with engine.begin() as conn:
        assert _alembic_version(conn) == _current_head()
        assert _version_table_schemas(conn) == ["public"]
        assert _relkind(conn, "team_configuration_versions") == "r"
        assert _column_udt(conn, "performance_records", "configuration_version_id") == "uuid"
        assert _preserved_rows(conn) == before_rows
        assert _legacy_link(conn) is None
        assert _relations(conn, "shadow_review") == before_shadow
        assert _column_count_in_schema(conn, "shadow_review", "performance_records", "configuration_version_id") == 0
        _assert_single_groundwork(conn)


@requires_disposable_pg
def test_foreign_key_to_non_public_table_is_rejected_without_mutation(pg_engine):
    engine, url = pg_engine
    with engine.begin() as conn:
        _install_support(conn)
        _install_version_table(conn)
        _install_performance(conn, partitioned=False, with_version_column=False)
        _retarget_team_fk_to_shadow(conn)
        _insert_existing_version(conn)
        _stamp(conn, PRIOR_REVISION)
        before_rows = _version_rows(conn)
        before_fingerprint = _groundwork_fingerprint(conn)
    _assert_upgrade_rejected(engine, url, before_fingerprint, "team_id")
    with engine.begin() as conn:
        assert _version_rows(conn) == before_rows
        assert _column_count(conn, "performance_records", "configuration_version_id") == 0
        assert _fk_referred_schema(conn, "team_configuration_versions", "team_id") == "shadow_review"


@requires_disposable_pg
@pytest.mark.parametrize("index_sql", ["partial", "expression"])
def test_incompatible_named_coverage_index_is_rejected_without_mutation(pg_engine, index_sql):
    engine, url = pg_engine
    with engine.begin() as conn:
        _install_support(conn)
        _install_version_table(conn)
        _install_performance(conn, partitioned=False, with_version_column=False)
        _replace_coverage_index(conn, index_sql)
        _insert_existing_version(conn)
        _stamp(conn, PRIOR_REVISION)
        before_rows = _version_rows(conn)
        before_fingerprint = _groundwork_fingerprint(conn)
    _assert_upgrade_rejected(engine, url, before_fingerprint, "idx_team_config_coverage")
    with engine.begin() as conn:
        assert _version_rows(conn) == before_rows
        assert _column_count(conn, "performance_records", "configuration_version_id") == 0
        assert _coverage_index_flags(conn) == _expected_drift_flags(index_sql)


@requires_disposable_pg
def test_regrouped_range_check_is_rejected_without_mutation(pg_engine):
    engine, url = pg_engine
    with engine.begin() as conn:
        _install_support(conn)
        _install_version_table(conn)
        _install_performance(conn, partitioned=False, with_version_column=False)
        _replace_range_check(conn)
        _insert_range_version(
            conn,
            VERSION_ID,
            1,
            from_month=1,
            from_year=2026,
            until_month=12,
            until_year=2025,
        )
        _stamp(conn, PRIOR_REVISION)
        before_rows = _version_rows(conn)
        before_fingerprint = _groundwork_fingerprint(conn)
        before_definition = _check_definition(conn, "ck_team_config_effective_range")
    assert "(12 + effective_until_month)" in before_definition
    _assert_upgrade_rejected(engine, url, before_fingerprint, "ck_team_config_effective_range")
    with engine.begin() as conn:
        assert _version_rows(conn) == before_rows
        assert _check_definition(conn, "ck_team_config_effective_range") == before_definition
        assert _column_count(conn, "performance_records", "configuration_version_id") == 0
        assert _version_rows(conn)[0]["effective_from_year"] == 2026
        assert _version_rows(conn)[0]["effective_until_year"] == 2025


@requires_disposable_pg
def test_correct_range_check_rejects_end_before_start(pg_engine):
    engine, url = pg_engine
    with engine.begin() as conn:
        _install_support(conn)
        _install_performance(conn, partitioned=False, with_version_column=False)
        _stamp(conn, PRIOR_REVISION)
    _alembic(url, "upgrade", "head")
    with engine.begin() as conn:
        definition = _check_definition(conn, "ck_team_config_effective_range")
        assert "((effective_until_year * 12) + effective_until_month)" in definition
        assert "(12 + effective_until_month)" not in definition
        _insert_range_version(
            conn,
            VERSION_ID,
            1,
            from_month=1,
            from_year=2026,
            until_month=1,
            until_year=2026,
        )
        _insert_range_version(
            conn,
            CROSS_YEAR_VERSION_ID,
            2,
            from_month=12,
            from_year=2025,
            until_month=1,
            until_year=2026,
        )
    with pytest.raises(IntegrityError, match="ck_team_config_effective_range"):
        with engine.begin() as conn:
            _insert_range_version(
                conn,
                ORPHAN_VERSION_ID,
                3,
                from_month=1,
                from_year=2026,
                until_month=12,
                until_year=2025,
            )
    with engine.begin() as conn:
        stored = _fetch(
            conn,
            """
            SELECT version_number, effective_from_year, effective_from_month,
                   effective_until_year, effective_until_month
            FROM public.team_configuration_versions
            ORDER BY version_number
            """,
        )
    assert stored == [(1, 2026, 1, 2026, 1), (2, 2025, 12, 2026, 1)]


@requires_disposable_pg
def test_not_valid_record_fk_is_rejected_without_mutation(pg_engine):
    engine, url = pg_engine
    with engine.begin() as conn:
        _install_support(conn)
        _install_version_table(conn)
        _install_performance(conn, partitioned=False, with_version_column=True)
        _insert_orphan_record(conn)
        _install_record_fk(conn, on_delete="SET NULL", not_valid=True)
        _stamp(conn, PRIOR_REVISION)
        before_links = _record_links(conn)
        before_fingerprint = _groundwork_fingerprint(conn)
        assert _record_fk_validated(conn) is False
    _assert_upgrade_rejected(engine, url, before_fingerprint, "configuration_version_id", "validat")
    with engine.begin() as conn:
        assert _record_links(conn) == before_links
        assert _record_links(conn) == [(str(LEGACY_RECORD_ID), "July", str(ORPHAN_VERSION_ID))]
        assert _record_fk_validated(conn) is False
        assert _parent_record_fk_count(conn) == 1
        assert _version_count(conn) == 0


@requires_disposable_pg
def test_empty_version_table_missing_required_columns_is_not_repaired(pg_engine):
    engine, url = pg_engine
    with engine.begin() as conn:
        _install_support(conn)
        _install_performance(conn, partitioned=False, with_version_column=False)
        conn.execute(
            sa.text(
                """
                CREATE TABLE public.team_configuration_versions (
                    id uuid PRIMARY KEY,
                    notes text
                )
                """
            )
        )
        _stamp(conn, PRIOR_REVISION)
        before_fingerprint = _groundwork_fingerprint(conn)
    result = _assert_upgrade_rejected(
        engine,
        url,
        before_fingerprint,
        "team_id",
        "version_number",
        "Refusing to repair",
    )
    output = f"{result.stdout}\n{result.stderr}"
    assert "UndefinedColumn" not in output
    assert "does not exist" not in output
    with engine.begin() as conn:
        assert _column_count(conn, "team_configuration_versions", "team_id") == 0
        assert _column_count(conn, "team_configuration_versions", "version_number") == 0
        assert _column_count(conn, "team_configuration_versions", "preview_snapshot") == 0
        assert _column_count(conn, "performance_records", "configuration_version_id") == 0


@requires_disposable_pg
def test_supported_bootstrap_stamps_head_and_roundtrips_through_orm(pg_engine):
    _engine, url = pg_engine
    bootstrap = _run_python(url, "scripts/bootstrap_schema.py")
    assert bootstrap.returncode == 0, f"{bootstrap.stdout}\n{bootstrap.stderr}"
    assert "stamped head" in bootstrap.stdout
    upgrade = _alembic(url, "upgrade", "head", check=False)
    assert upgrade.returncode == 0, f"{upgrade.stdout}\n{upgrade.stderr}"
    engine = sa.create_engine(url, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            assert _alembic_version(conn) == _current_head()
            assert _relkind(conn, "team_configuration_versions") == "r"
            assert _relkind(conn, "performance_records") == "r"
            assert _column_udt(conn, "team_configuration_versions", "config_snapshot") == "json"
            assert _column_udt(conn, "performance_records", "configuration_version_id") == "uuid"
            _assert_single_groundwork(conn)
            fingerprint = _groundwork_fingerprint(conn)
        _orm_roundtrip(engine)
        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE alembic_version SET version_num = :revision"), {"revision": PRIOR_REVISION})
            evidence = _version_rows(conn)
        _alembic(url, "upgrade", "head")
        _alembic(url, "downgrade", PRIOR_REVISION)
        _alembic(url, "upgrade", "head")
        with engine.begin() as conn:
            assert _alembic_version(conn) == _current_head()
            assert _version_rows(conn) == evidence
            assert _groundwork_fingerprint(conn) == fingerprint
            _assert_single_groundwork(conn)
            assert _legacy_link_for_month(conn, "July") is None
    finally:
        engine.dispose()


@pytest.fixture
def pg_engine():
    url = os.environ.get("PMS_EVAL_SCHEMA_TEST_URL", "").strip()
    if not url:
        pytest.skip("PMS_EVAL_SCHEMA_TEST_URL is not set.")
    assert_allowlisted(url)
    engine = sa.create_engine(url, poolclass=NullPool)
    try:
        _reset(engine, url)
        yield engine, url
    finally:
        engine.dispose()


def _reset(engine, url: str) -> None:
    assert_allowlisted(url)
    expected = urlparse(url).path.lstrip("/")
    with engine.begin() as conn:
        current = conn.execute(sa.text("SELECT current_database()")).scalar_one()
        port = conn.execute(sa.text("SHOW port")).scalar_one()
        if current != expected:
            raise RuntimeError(f"Connected database {current!r} does not match the allowlisted name.")
        if str(port).strip() != "5432":
            raise RuntimeError(f"Unexpected in-container PostgreSQL port {port!r}; refusing to reset.")
        conn.execute(sa.text("DROP SCHEMA IF EXISTS shadow_review CASCADE"))
        conn.execute(sa.text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(sa.text("CREATE SCHEMA public"))


def _child_env(url: str) -> dict[str, str]:
    assert_allowlisted(url)
    env = os.environ.copy()
    env["APP_ENV"] = "test"
    env["DATABASE_URL"] = url
    env["PMS_EVAL_SCHEMA_TEST_URL"] = url
    return env


def _alembic(
    url: str,
    *args: str,
    check: bool = True,
    search_path: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = _child_env(url)
    if search_path is not None:
        env["PGOPTIONS"] = f"-c search_path={search_path}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"alembic {' '.join(args)} exited {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def _run_python(url: str, script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, script],
        cwd=BACKEND,
        env=_child_env(url),
        text=True,
        capture_output=True,
        check=False,
    )


def _run_upgrade_again(url: str) -> None:
    migration = _load_migration()
    engine = sa.create_engine(url, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
    finally:
        engine.dispose()


def _install_support(conn) -> None:
    conn.execute(
        sa.text(
            """
            CREATE TABLE teams (
                id uuid PRIMARY KEY,
                name varchar(100) NOT NULL UNIQUE,
                db_name varchar(100) NOT NULL UNIQUE
            );
            CREATE TABLE users (
                id uuid PRIMARY KEY,
                username varchar(100) NOT NULL UNIQUE
            );
            CREATE TABLE management_kpi_config (
                id uuid PRIMARY KEY,
                team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                employee_identifier varchar(50),
                position_name varchar(255),
                kpi_key varchar(100) NOT NULL,
                effective_month varchar(20) NOT NULL,
                effective_year smallint NOT NULL,
                target_value numeric(18,4),
                weight numeric(7,4) NOT NULL
            );
            CREATE TABLE management_kpi_config_history (
                id uuid PRIMARY KEY,
                team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                action varchar(20) NOT NULL,
                old_values json,
                new_values json,
                changed_by varchar(100)
            );
            CREATE TABLE management_kpi_snapshots (
                id uuid PRIMARY KEY,
                team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                employee_identifier varchar(50) NOT NULL,
                employee_name varchar(255) NOT NULL,
                position_name varchar(255) NOT NULL,
                month varchar(20) NOT NULL,
                year smallint NOT NULL,
                kpi_key varchar(100) NOT NULL,
                actual_value numeric(18,4)
            );
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO teams (id, name, db_name) VALUES (:team_id, 'Synthetic Team', 'synthetic_team');
            INSERT INTO users (id, username) VALUES (:user_id, 'synth-admin');
            """
        ),
        {"team_id": TEAM_ID, "user_id": USER_ID},
    )


def _install_version_table(conn, *, include_preview: bool = True, snapshot_type: str = "json") -> None:
    if snapshot_type not in {"json", "jsonb"}:
        raise RuntimeError(f"Unsupported fixture snapshot type {snapshot_type}.")
    preview_sql = ", preview_snapshot json" if include_preview else ""
    conn.execute(
        sa.text(
            f"""
            CREATE TABLE team_configuration_versions (
                id uuid PRIMARY KEY,
                team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                version_number integer NOT NULL,
                status varchar(20) NOT NULL,
                effective_month varchar(20) NOT NULL,
                effective_year smallint NOT NULL,
                config_snapshot {snapshot_type} NOT NULL,
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
                total_weight numeric(7,4),
                overall_score numeric(10,2),
                is_active boolean NOT NULL DEFAULT true
                {preview_sql},
                CONSTRAINT uq_team_config_version UNIQUE (team_id, version_number),
                CONSTRAINT ck_team_config_effective_from_month CHECK (effective_from_month BETWEEN 1 AND 12),
                CONSTRAINT ck_team_config_effective_until_month CHECK (
                    effective_until_month IS NULL OR effective_until_month BETWEEN 1 AND 12
                ),
                CONSTRAINT ck_team_config_effective_range CHECK (
                    effective_until_year IS NULL OR
                    (effective_until_year * 12 + effective_until_month) >=
                    (effective_from_year * 12 + effective_from_month)
                )
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX idx_team_config_coverage
            ON team_configuration_versions (
                team_id, status, effective_from_year, effective_from_month,
                effective_until_year, effective_until_month
            )
            """
        )
    )


def _install_performance(conn, *, partitioned: bool, with_version_column: bool) -> None:
    version_column = ", configuration_version_id uuid" if with_version_column else ""
    partition = " PARTITION BY RANGE (year)" if partitioned else ""
    conn.execute(
        sa.text(
            f"""
            CREATE TABLE performance_records (
                id uuid NOT NULL,
                year smallint NOT NULL,
                team_id uuid,
                month varchar(20),
                score numeric(6,2),
                record_payload json
                {version_column},
                PRIMARY KEY (id, year)
            ){partition}
            """
        )
    )
    if partitioned:
        conn.execute(
            sa.text(
                """
                CREATE TABLE performance_records_2026
                    PARTITION OF performance_records FOR VALUES FROM (2026) TO (2027);
                CREATE TABLE performance_records_default
                    PARTITION OF performance_records DEFAULT;
                """
            )
        )
    conn.execute(
        sa.text(
            """
            CREATE TABLE kpi_values (
                id uuid PRIMARY KEY,
                record_id uuid NOT NULL,
                record_year smallint NOT NULL,
                kpi_key varchar(50) NOT NULL,
                actual_value numeric(18,4) NOT NULL,
                target_value numeric(18,4) NOT NULL,
                achievement_ratio numeric(10,4) NOT NULL,
                weight_applied numeric(5,4) NOT NULL,
                contribution numeric(7,4) NOT NULL,
                CONSTRAINT uq_kpi_value_record_key UNIQUE (record_id, kpi_key),
                CONSTRAINT fk_kpi_values_performance_records
                    FOREIGN KEY (record_id, record_year)
                    REFERENCES performance_records (id, year) ON DELETE CASCADE
            )
            """
        )
    )


def _install_record_fk(conn, *, on_delete: str = "SET NULL", not_valid: bool = False) -> None:
    if on_delete not in {"SET NULL", "CASCADE"}:
        raise RuntimeError(f"Unsupported fixture delete action {on_delete}.")
    validity = " NOT VALID" if not_valid else ""
    conn.execute(
        sa.text(
            f"""
            ALTER TABLE public.performance_records
            ADD CONSTRAINT fk_performance_records_configuration_version
            FOREIGN KEY (configuration_version_id)
            REFERENCES public.team_configuration_versions (id)
            ON DELETE {on_delete}{validity}
            """
        )
    )


def _replace_range_check(conn) -> None:
    conn.execute(
        sa.text(
            """
            ALTER TABLE public.team_configuration_versions
                DROP CONSTRAINT ck_team_config_effective_range;
            ALTER TABLE public.team_configuration_versions
                ADD CONSTRAINT ck_team_config_effective_range CHECK (
                    effective_until_year IS NULL OR
                    effective_until_year * (12 + effective_until_month) >=
                    effective_from_year * (12 + effective_from_month)
                );
            """
        )
    )


def _insert_range_version(
    conn,
    version_id,
    version_number: int,
    *,
    from_month: int,
    from_year: int,
    until_month: int,
    until_year: int,
) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO public.team_configuration_versions (
                id, team_id, version_number, status, effective_month, effective_year,
                config_snapshot, config_checksum, created_by_user_id, notes,
                effective_from_month, effective_from_year,
                effective_until_month, effective_until_year, is_active
            ) VALUES (
                :version_id, :team_id, :version_number, 'published', 'January', :from_year,
                CAST(:snapshot AS json), :checksum, :user_id, 'range-sentinel',
                :from_month, :from_year, :until_month, :until_year, true
            )
            """
        ),
        {
            "version_id": version_id,
            "team_id": TEAM_ID,
            "version_number": version_number,
            "from_year": from_year,
            "from_month": from_month,
            "until_month": until_month,
            "until_year": until_year,
            "user_id": USER_ID,
            "snapshot": json.dumps(SNAPSHOT, sort_keys=True),
            "checksum": CHECKSUM,
        },
    )


def _insert_orphan_record(conn) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO public.performance_records (
                id, year, team_id, month, score, record_payload, configuration_version_id
            ) VALUES (
                :record_id, 2026, :team_id, 'July', 80.00, CAST(:payload AS json), :version_id
            )
            """
        ),
        {
            "record_id": LEGACY_RECORD_ID,
            "team_id": TEAM_ID,
            "payload": json.dumps(RAW_PAYLOAD, sort_keys=True),
            "version_id": ORPHAN_VERSION_ID,
        },
    )


def _check_definition(conn, name: str) -> str:
    return str(
        conn.execute(
            sa.text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = :name
                  AND conrelid = 'public.team_configuration_versions'::regclass
                """
            ),
            {"name": name},
        ).scalar_one()
    )


def _record_fk_validated(conn) -> bool:
    return bool(
        conn.execute(
            sa.text(
                """
                SELECT con.convalidated
                FROM pg_constraint AS con
                JOIN pg_class AS rel ON rel.oid = con.conrelid
                JOIN pg_namespace AS nsp ON nsp.oid = rel.relnamespace
                WHERE nsp.nspname = 'public'
                  AND rel.relname = 'performance_records'
                  AND con.conname = 'fk_performance_records_configuration_version'
                  AND con.contype = 'f'
                  AND con.conparentid = 0
                """
            )
        ).scalar_one()
    )


def _replace_unique_with_extra_column(conn) -> None:
    conn.execute(
        sa.text(
            """
            ALTER TABLE public.team_configuration_versions
                ADD COLUMN team_id_extra uuid;
            ALTER TABLE public.team_configuration_versions
                DROP CONSTRAINT uq_team_config_version;
            ALTER TABLE public.team_configuration_versions
                ADD CONSTRAINT uq_team_config_version UNIQUE (team_id_extra, version_number);
            """
        )
    )


def _install_shadow_support(conn) -> None:
    conn.execute(
        sa.text(
            """
            CREATE SCHEMA shadow_review;
            CREATE TABLE shadow_review.teams (
                id uuid PRIMARY KEY,
                name varchar(100) NOT NULL,
                db_name varchar(100) NOT NULL
            );
            CREATE TABLE shadow_review.users (
                id uuid PRIMARY KEY,
                username varchar(100) NOT NULL
            );
            CREATE TABLE shadow_review.performance_records (
                id uuid NOT NULL,
                year smallint NOT NULL,
                team_id uuid,
                month varchar(20),
                score numeric(6,2),
                record_payload json,
                PRIMARY KEY (id, year)
            );
            INSERT INTO shadow_review.teams (id, name, db_name)
            VALUES (:team_id, 'Shadow Team', 'shadow_team');
            INSERT INTO shadow_review.users (id, username)
            VALUES (:user_id, 'shadow-admin');
            """
        ),
        {"team_id": TEAM_ID, "user_id": USER_ID},
    )


def _retarget_team_fk_to_shadow(conn) -> None:
    _install_shadow_support(conn)
    conn.execute(
        sa.text(
            """
            ALTER TABLE public.team_configuration_versions
                DROP CONSTRAINT team_configuration_versions_team_id_fkey;
            ALTER TABLE public.team_configuration_versions
                ADD CONSTRAINT team_configuration_versions_team_id_fkey
                FOREIGN KEY (team_id)
                REFERENCES shadow_review.teams (id)
                ON DELETE CASCADE;
            """
        )
    )


def _replace_coverage_index(conn, kind: str) -> None:
    if kind == "partial":
        definition = """
            CREATE INDEX idx_team_config_coverage
            ON public.team_configuration_versions (
                team_id, status, effective_from_year, effective_from_month,
                effective_until_year, effective_until_month
            )
            WHERE status = 'published'
        """
    elif kind == "expression":
        definition = """
            CREATE INDEX idx_team_config_coverage
            ON public.team_configuration_versions (
                team_id, status, effective_from_year, effective_from_month,
                effective_until_year, (effective_until_month + 0)
            )
        """
    else:
        raise RuntimeError(f"Unsupported coverage index drift {kind}.")
    conn.execute(sa.text("DROP INDEX public.idx_team_config_coverage"))
    conn.execute(sa.text(definition))


def _assert_upgrade_rejected(engine, url: str, before_fingerprint, *needles: str):
    result = _alembic(url, "upgrade", "head", check=False)
    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0, output
    for needle in needles:
        assert needle in output, output
    with engine.begin() as conn:
        assert _alembic_version(conn) == PRIOR_REVISION
        assert _groundwork_fingerprint(conn) == before_fingerprint
    return result


def _run_python_text(url: str, script: str, search_path: str | None = None) -> subprocess.CompletedProcess[str]:
    env = _child_env(url)
    if search_path is not None:
        env["PGOPTIONS"] = f"-c search_path={search_path}"
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _install_sentinels(conn, *, linked: bool) -> None:
    has_link = _column_count(conn, "performance_records", "configuration_version_id") == 1
    if linked and not has_link:
        raise RuntimeError("Linked sentinel requires configuration_version_id.")
    if has_link:
        conn.execute(
            sa.text(
                """
                INSERT INTO performance_records (
                    id, year, team_id, month, score, record_payload, configuration_version_id
                ) VALUES (
                    :record_id, 2026, :team_id, 'July', 80.00, CAST(:payload AS json), :version_id
                )
                """
            ),
            {
                "record_id": LINKED_RECORD_ID if linked else LEGACY_RECORD_ID,
                "team_id": TEAM_ID,
                "payload": json.dumps(RAW_PAYLOAD, sort_keys=True),
                "version_id": VERSION_ID if linked else None,
            },
        )
    else:
        conn.execute(
            sa.text(
                """
                INSERT INTO performance_records (id, year, team_id, month, score, record_payload)
                VALUES (:record_id, 2026, :team_id, 'July', 80.00, CAST(:payload AS json))
                """
            ),
            {
                "record_id": LEGACY_RECORD_ID,
                "team_id": TEAM_ID,
                "payload": json.dumps(RAW_PAYLOAD, sort_keys=True),
            },
        )
    if linked:
        conn.execute(
            sa.text(
                """
                INSERT INTO performance_records (
                    id, year, team_id, month, score, record_payload, configuration_version_id
                ) VALUES (:record_id, 2026, :team_id, 'June', 70.00, CAST(:payload AS json), NULL)
                """
            ),
            {
                "record_id": LEGACY_RECORD_ID,
                "team_id": TEAM_ID,
                "payload": json.dumps({"raw": "legacy-null"}, sort_keys=True),
            },
        )
    record_id = LINKED_RECORD_ID if linked else LEGACY_RECORD_ID
    conn.execute(
        sa.text(
            """
            INSERT INTO kpi_values (
                id, record_id, record_year, kpi_key, actual_value, target_value,
                achievement_ratio, weight_applied, contribution
            ) VALUES (
                :kpi_id, :record_id, 2026, 'synthetic_kpi', 4.0000, 5.0000, 0.8000, 0.2500, 0.2000
            )
            """
        ),
        {"kpi_id": KPI_ID, "record_id": record_id},
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO management_kpi_config (
                id, team_id, employee_identifier, position_name, kpi_key,
                effective_month, effective_year, target_value, weight
            ) VALUES (
                :config_id, :team_id, 'SYNTH-PERSON', 'Synthetic Role', 'synthetic_kpi',
                'July', 2026, 3.5000, 0.2500
            );
            INSERT INTO management_kpi_config_history (
                id, team_id, action, old_values, new_values, changed_by
            ) VALUES (
                :history_id, :team_id, 'replace',
                CAST(:old_values AS json), CAST(:new_values AS json), 'synthetic-admin'
            );
            INSERT INTO management_kpi_snapshots (
                id, team_id, employee_identifier, employee_name, position_name,
                month, year, kpi_key, actual_value
            ) VALUES (
                :snapshot_id, :team_id, 'SYNTH-PERSON', 'Synthetic Person', 'Synthetic Role',
                'July', 2026, 'synthetic_kpi', 3.2500
            );
            """
        ),
        {
            "config_id": CONFIG_ID,
            "history_id": HISTORY_ID,
            "snapshot_id": SNAPSHOT_ID,
            "team_id": TEAM_ID,
            "old_values": json.dumps({"weight": "0.2000"}, sort_keys=True),
            "new_values": json.dumps({"employee_identifier": "SYNTH-PERSON", "weight": "0.2500"}, sort_keys=True),
        },
    )


def _insert_existing_version(conn, version_id=VERSION_ID) -> None:
    has_preview = _column_count(conn, "team_configuration_versions", "preview_snapshot") == 1
    preview_column = ", preview_snapshot" if has_preview else ""
    preview_value = ", CAST(:preview AS json)" if has_preview else ""
    conn.execute(
        sa.text(
            f"""
            INSERT INTO team_configuration_versions (
                id, team_id, version_number, status, effective_month, effective_year,
                config_snapshot, config_checksum, created_by_user_id, notes,
                effective_from_month, effective_from_year, total_weight, overall_score, is_active
                {preview_column}
            ) VALUES (
                :version_id, :team_id, 1, 'published', 'July', 2026,
                CAST(:snapshot AS json), :checksum, :user_id, 'do-not-rewrite',
                8, 2025, 1.2500, 88.50, true
                {preview_value}
            )
            """
        ),
        {
            "version_id": version_id,
            "team_id": TEAM_ID,
            "user_id": USER_ID,
            "snapshot": json.dumps(SNAPSHOT, sort_keys=True),
            "preview": json.dumps(PREVIEW, sort_keys=True),
            "checksum": CHECKSUM,
        },
    )


def _insert_version_evidence(conn) -> None:
    _insert_existing_version(conn)
    conn.execute(
        sa.text(
            """
            INSERT INTO performance_records (
                id, year, team_id, month, score, record_payload, configuration_version_id
            ) VALUES (
                :record_id, 2026, :team_id, 'August', 91.00, CAST(:payload AS json), :version_id
            )
            """
        ),
        {
            "record_id": LINKED_RECORD_ID,
            "team_id": TEAM_ID,
            "version_id": VERSION_ID,
            "payload": json.dumps({"raw": "linked"}, sort_keys=True),
        },
    )


def _stamp(conn, revision: str) -> None:
    conn.execute(
        sa.text(
            """
            CREATE TABLE alembic_version (version_num varchar(32) NOT NULL);
            INSERT INTO alembic_version (version_num) VALUES (:revision);
            """
        ),
        {"revision": revision},
    )


def _preserved_rows(conn) -> dict[str, list[tuple]]:
    return {
        "performance": _fetch(
            conn,
            """
            SELECT id::text, year, month, score, record_payload::text
            FROM performance_records
            ORDER BY month, id::text
            """,
        ),
        "kpi": _fetch(
            conn,
            """
            SELECT id::text, record_id::text, record_year, kpi_key, actual_value, target_value,
                   achievement_ratio, weight_applied, contribution
            FROM kpi_values ORDER BY id::text
            """,
        ),
        "management_config": _fetch(
            conn,
            """
            SELECT id::text, employee_identifier, position_name, kpi_key, effective_month,
                   effective_year, target_value, weight
            FROM management_kpi_config ORDER BY id::text
            """,
        ),
        "management_history": _fetch(
            conn,
            """
            SELECT id::text, action, old_values::text, new_values::text, changed_by
            FROM management_kpi_config_history ORDER BY id::text
            """,
        ),
        "management_snapshot": _fetch(
            conn,
            """
            SELECT id::text, employee_identifier, employee_name, position_name, month, year,
                   kpi_key, actual_value
            FROM management_kpi_snapshots ORDER BY id::text
            """,
        ),
    }


def _version_rows(conn) -> list[dict[str, object]]:
    preview = ", preview_snapshot::text AS preview_snapshot" if _column_count(conn, "team_configuration_versions", "preview_snapshot") else ""
    rows = conn.execute(
        sa.text(
            f"""
            SELECT id::text AS id, version_number, status, effective_month, effective_year,
                   config_snapshot::text AS config_snapshot, config_checksum,
                   effective_from_month, effective_from_year, effective_until_month, effective_until_year,
                   total_weight, overall_score, is_active, notes
                   {preview}
            FROM team_configuration_versions
            ORDER BY version_number
            """
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def _fetch(conn, sql: str) -> list[tuple]:
    return [tuple(row) for row in conn.execute(sa.text(sql)).all()]


def _version_count(conn) -> int:
    return int(conn.execute(sa.text("SELECT count(*) FROM team_configuration_versions")).scalar_one())


def _record_links(conn) -> list[tuple]:
    return _fetch(
        conn,
        """
        SELECT id::text, month, configuration_version_id::text
        FROM performance_records
        ORDER BY month, id::text
        """,
    )


def _legacy_link(conn):
    return conn.execute(
        sa.text("SELECT configuration_version_id::text FROM performance_records WHERE id = :record_id"),
        {"record_id": LEGACY_RECORD_ID},
    ).scalar_one()


def _legacy_link_for_month(conn, month: str):
    return conn.execute(
        sa.text(
            """
            SELECT configuration_version_id::text
            FROM performance_records
            WHERE month = :month
            """
        ),
        {"month": month},
    ).scalar_one()


def _linked_row(conn) -> tuple:
    return conn.execute(
        sa.text(
            """
            SELECT id::text, month, record_payload::text, configuration_version_id::text
            FROM performance_records
            WHERE id = :record_id
            """
        ),
        {"record_id": LINKED_RECORD_ID},
    ).one()


def _alembic_version(conn) -> str:
    return str(conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one())


def _relkind(conn, table: str) -> str:
    return str(
        conn.execute(
            sa.text(
                """
                SELECT c.relkind
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname = :table
                """
            ),
            {"table": table},
        ).scalar_one()
    )


def _child_partitions(conn) -> list[str]:
    rows = conn.execute(
        sa.text(
            """
            SELECT child.relname
            FROM pg_inherits AS inheritance
            JOIN pg_class AS parent ON parent.oid = inheritance.inhparent
            JOIN pg_class AS child ON child.oid = inheritance.inhrelid
            WHERE parent.relname = 'performance_records'
            ORDER BY child.relname
            """
        )
    ).scalars().all()
    return [str(row) for row in rows]


def _column_count(conn, table: str, column: str) -> int:
    return int(
        conn.execute(
            sa.text(
                """
                SELECT count(*)
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :table AND column_name = :column
                """
            ),
            {"table": table, "column": column},
        ).scalar_one()
    )


def _column_udt(conn, table: str, column: str) -> str:
    return str(
        conn.execute(
            sa.text(
                """
                SELECT udt_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :table AND column_name = :column
                """
            ),
            {"table": table, "column": column},
        ).scalar_one()
    )


def _parent_record_fk_count(conn) -> int:
    return int(
        conn.execute(
            sa.text(
                """
                SELECT count(*)
                FROM pg_constraint AS con
                JOIN pg_class AS rel ON rel.oid = con.conrelid
                JOIN pg_namespace AS nsp ON nsp.oid = rel.relnamespace
                WHERE nsp.nspname = 'public'
                  AND rel.relname = 'performance_records'
                  AND con.contype = 'f'
                  AND con.conparentid = 0
                  AND pg_get_constraintdef(con.oid) ILIKE '%configuration_version_id%'
                """
            )
        ).scalar_one()
    )


def _record_fk_delete_action(conn) -> str:
    return str(
        conn.execute(
            sa.text(
                """
                SELECT con.confdeltype
                FROM pg_constraint AS con
                JOIN pg_class AS rel ON rel.oid = con.conrelid
                WHERE rel.relname = 'performance_records'
                  AND con.contype = 'f'
                  AND con.conparentid = 0
                  AND pg_get_constraintdef(con.oid) ILIKE '%configuration_version_id%'
                """
            )
        ).scalar_one()
    )


def _relations(conn, schema: str) -> list[tuple]:
    if schema not in {"public", "shadow_review"}:
        raise RuntimeError(f"Refusing to list unexpected schema {schema}.")
    return _fetch(
        conn,
        f"""
        SELECT c.relname, c.relkind
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = '{schema}'
          AND c.relkind IN ('r', 'p', 'i')
        ORDER BY c.relname
        """,
    )


def _version_table_schemas(conn) -> list[str]:
    rows = conn.execute(
        sa.text(
            """
            SELECT n.nspname
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE c.relname = 'team_configuration_versions'
              AND c.relkind = 'r'
            ORDER BY n.nspname
            """
        )
    ).scalars().all()
    return [str(row) for row in rows]


def _column_count_in_schema(conn, schema: str, table: str, column: str) -> int:
    if schema not in {"public", "shadow_review"}:
        raise RuntimeError(f"Refusing to inspect unexpected schema {schema}.")
    return int(
        conn.execute(
            sa.text(
                """
                SELECT count(*)
                FROM information_schema.columns
                WHERE table_schema = :schema AND table_name = :table AND column_name = :column
                """
            ),
            {"schema": schema, "table": table, "column": column},
        ).scalar_one()
    )


def _unique_key_columns(conn, name: str) -> tuple:
    columns = conn.execute(
        sa.text(
            """
            SELECT array_agg(att.attname::text ORDER BY key.ord) AS columns
            FROM pg_constraint AS con
            JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS key(attnum, ord) ON true
            JOIN pg_attribute AS att
              ON att.attrelid = con.conrelid
             AND att.attnum = key.attnum
            WHERE con.contype = 'u'
              AND con.conname = :name
              AND con.conrelid = 'public.team_configuration_versions'::regclass
            GROUP BY con.oid
            """
        ),
        {"name": name},
    ).scalar_one()
    return tuple(columns)


def _fk_referred_schema(conn, table: str, column: str) -> str:
    return str(
        conn.execute(
            sa.text(
                """
                SELECT ref_nsp.nspname
                FROM pg_constraint AS con
                JOIN pg_class AS rel ON rel.oid = con.conrelid
                JOIN pg_namespace AS nsp ON nsp.oid = rel.relnamespace
                JOIN LATERAL unnest(con.conkey) AS src(attnum) ON true
                JOIN pg_attribute AS att
                  ON att.attrelid = rel.oid
                 AND att.attnum = src.attnum
                JOIN pg_class AS ref_cls ON ref_cls.oid = con.confrelid
                JOIN pg_namespace AS ref_nsp ON ref_nsp.oid = ref_cls.relnamespace
                WHERE nsp.nspname = 'public'
                  AND rel.relname = :table
                  AND att.attname = :column
                  AND con.contype = 'f'
                  AND con.conparentid = 0
                """
            ),
            {"table": table, "column": column},
        ).scalar_one()
    )


def _coverage_index_flags(conn) -> dict[str, bool]:
    row = conn.execute(
        sa.text(
            """
            SELECT (ix.indpred IS NOT NULL) AS is_partial,
                   (ix.indexprs IS NOT NULL) AS has_expressions,
                   ix.indisvalid AS is_valid,
                   ix.indisready AS is_ready,
                   (ix.indnatts > ix.indnkeyatts) AS has_included
            FROM pg_index AS ix
            JOIN pg_class AS i ON i.oid = ix.indexrelid
            JOIN pg_class AS t ON t.oid = ix.indrelid
            JOIN pg_namespace AS n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public'
              AND t.relname = 'team_configuration_versions'
              AND i.relname = 'idx_team_config_coverage'
            """
        )
    ).mappings().one()
    return {key: bool(row[key]) for key in ("is_partial", "has_expressions", "is_valid", "is_ready", "has_included")}


def _expected_drift_flags(kind: str) -> dict[str, bool]:
    if kind not in {"partial", "expression"}:
        raise RuntimeError(f"Unsupported coverage index drift {kind}.")
    return {
        "is_partial": kind == "partial",
        "has_expressions": kind == "expression",
        "is_valid": True,
        "is_ready": True,
        "has_included": False,
    }


def _assert_single_groundwork(conn) -> None:
    assert _parent_record_fk_count(conn) == 1
    assert _record_fk_delete_action(conn) == "n"
    assert _column_count(conn, "performance_records", "configuration_version_id") == 1
    assert _coverage_index_flags(conn) == {
        "is_partial": False,
        "has_expressions": False,
        "is_valid": True,
        "is_ready": True,
        "has_included": False,
    }
    assert _unique_key_columns(conn, "uq_team_config_version") == ("team_id", "version_number")


def _assert_partition_fk_parent(conn) -> None:
    parent_oid = conn.execute(
        sa.text(
            """
            SELECT con.oid::text
            FROM pg_constraint AS con
            JOIN pg_class AS rel ON rel.oid = con.conrelid
            WHERE rel.relname = 'performance_records'
              AND con.contype = 'f'
              AND con.conparentid = 0
              AND con.conname = 'fk_performance_records_configuration_version'
            """
        )
    ).scalar_one()
    children = conn.execute(
        sa.text(
            """
            SELECT child.relname, child_con.conparentid::text
            FROM pg_inherits AS inheritance
            JOIN pg_class AS parent ON parent.oid = inheritance.inhparent
            JOIN pg_class AS child ON child.oid = inheritance.inhrelid
            JOIN pg_constraint AS child_con ON child_con.conrelid = child.oid
            WHERE parent.relname = 'performance_records'
              AND child_con.contype = 'f'
              AND pg_get_constraintdef(child_con.oid) ILIKE '%configuration_version_id%'
            ORDER BY child.relname
            """
        )
    ).all()
    assert [tuple(row) for row in children] == [
        ("performance_records_2026", parent_oid),
        ("performance_records_default", parent_oid),
    ]


def _groundwork_fingerprint(conn) -> list[tuple]:
    return _fetch(
        conn,
        """
        SELECT 'column' AS kind, table_name::text, column_name::text, udt_name::text, is_nullable::text
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND (
              table_name = 'team_configuration_versions'
              OR (table_name = 'performance_records' AND column_name = 'configuration_version_id')
          )
        UNION ALL
        SELECT 'constraint', rel.relname::text, con.conname::text, con.contype::text, pg_get_constraintdef(con.oid)
        FROM pg_constraint AS con
        JOIN pg_class AS rel ON rel.oid = con.conrelid
        JOIN pg_namespace AS nsp ON nsp.oid = rel.relnamespace
        WHERE nsp.nspname = 'public'
          AND rel.relname IN ('team_configuration_versions', 'performance_records')
          AND con.conparentid = 0
        UNION ALL
        SELECT 'index', tablename::text, indexname::text, indexdef, ''
        FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = 'team_configuration_versions'
        ORDER BY 1, 2, 3
        """
    )


def _orm_roundtrip(engine) -> None:
    Session = sessionmaker(bind=engine)
    session = Session()
    team = Team(name="Bootstrap Synthetic", db_name="bootstrap_synthetic", region="UAE", team_level="employee")
    user = User(
        username="bootstrap-admin",
        email="bootstrap-admin@example.com",
        password_hash="synthetic-hash",
        full_name="Bootstrap Admin",
    )
    session.add_all([team, user])
    session.flush()
    employee = Employee(employee_id="BOOT-1", name="Bootstrap Employee", team_id=team.id, region="UAE")
    session.add(employee)
    session.flush()
    version = TeamConfigurationVersion(
        team_id=team.id,
        version_number=1,
        status="published",
        effective_month="July",
        effective_year=2026,
        config_snapshot=SNAPSHOT,
        config_checksum=CHECKSUM,
        created_by_user_id=user.id,
        effective_from_month=8,
        effective_from_year=2025,
        preview_snapshot=PREVIEW,
        total_weight=Decimal("1.2500"),
        overall_score=Decimal("88.50"),
        is_active=True,
        notes="bootstrap-roundtrip",
    )
    session.add(version)
    session.flush()
    session.add_all(
        [
            PerformanceRecord(
                employee_id=employee.id,
                team_id=team.id,
                month="July",
                year=2026,
                score=Decimal("80.00"),
                grade="B",
                status="Meets",
                record_payload=RAW_PAYLOAD,
            ),
            PerformanceRecord(
                employee_id=employee.id,
                team_id=team.id,
                month="August",
                year=2026,
                score=Decimal("91.00"),
                grade="A",
                status="Exceeds",
                record_payload={"raw": "linked"},
                configuration_version_id=version.id,
            ),
        ]
    )
    session.commit()
    session.expire_all()
    stored = session.query(TeamConfigurationVersion).filter_by(notes="bootstrap-roundtrip").one()
    assert stored.config_snapshot == SNAPSHOT
    assert stored.effective_from_month == 8
    july = session.query(PerformanceRecord).filter_by(month="July").one()
    august = session.query(PerformanceRecord).filter_by(month="August").one()
    assert july.configuration_version_id is None
    assert august.configuration_version_id == stored.id
    session.close()
