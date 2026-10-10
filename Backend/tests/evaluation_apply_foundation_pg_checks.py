"""Opt-in PostgreSQL 16/18 checks for the evaluation apply foundation.

This module is not named test_*.py, so a normal pytest collection does not
run it or drop schemas. A reviewer runs it by path, one process at a time,
against the disposable databases already allowlisted by
evaluation_history_pg_checks.py:

    python -X utf8 -m pytest -q -p no:cacheprovider tests/evaluation_apply_foundation_pg_checks.py

The runner must already have APP_ENV=test, DATABASE_URL=sqlite:///:memory:,
and an empty REDIS_URL. This file does not open a database at import and
does not create containers or roles.
"""

from __future__ import annotations

import importlib.util
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

if os.environ.get("APP_ENV") != "test" or os.environ.get("DATABASE_URL") != "sqlite:///:memory:":
    raise RuntimeError(
        "evaluation_apply_foundation_pg_checks requires APP_ENV=test and "
        "DATABASE_URL=sqlite:///:memory: from the runner before import. "
        "Owned PostgreSQL URLs are applied only for allowlisted connections."
    )
if os.environ.get("REDIS_URL", "") != "":
    raise RuntimeError("evaluation_apply_foundation_pg_checks refuses a non-empty REDIS_URL.")

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from config.database import Base
from models.evaluation_history_schema import missing_history_objects
from models.models import (
    Employee,
    EvaluationApplyControl,
    EvaluationRevision,
    EvaluationScope,
    PerformanceRecord,
    ProcessingJob,
    Team,
    TeamConfigurationVersion,
    User,
)
from services.evaluation.apply_job_schema import (
    APPLY_FOUNDATION_PREDECESSOR,
    APPLY_FOUNDATION_REVISION,
    KIND_CHECK_SQL,
    PRIOR_KIND_CHECK_SQL,
    apply_foundation_downgrade_blockers,
    cache_dedup_key,
    known_actor_snapshot,
    missing_apply_foundation_objects,
    processing_job_kind_definition,
)
from services.processing_job_service import JOB_KINDS


def _load_history_helpers():
    path = Path(__file__).with_name("evaluation_history_pg_checks.py")
    spec = importlib.util.spec_from_file_location("evaluation_history_pg_checks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_HISTORY = _load_history_helpers()
TARGETS = _HISTORY.TARGETS
USER = _HISTORY.USER
assert_safe = _HISTORY.assert_safe
reset_public = _HISTORY.reset_public
url_for = _HISTORY.url_for
upgrade = _HISTORY.upgrade
downgrade = _HISTORY.downgrade
alembic_version = _HISTORY.alembic_version

RULES = "ab" * 32
PROOF = "cd" * 32
LINEAGE = "ef" * 32
ENGINE = "unset-until-phase7b"


def refuse_search_path(raw: str) -> None:
    """Allow only the public schema. Do not fall back to another schema."""

    parts = [part.strip().strip('"') for part in (raw or "").split(",") if part.strip()]
    allowed = {"public", "$user"}
    if not parts or "public" not in parts or any(part not in allowed for part in parts):
        raise RuntimeError(f"Refusing search_path {raw!r}.")


def assert_public_search_path(connection, target: dict) -> None:
    assert_safe(connection, target)
    schema = connection.execute(text("SELECT current_schema()")).scalar_one()
    if schema != "public":
        raise RuntimeError(f"Refusing current_schema {schema}.")
    refuse_search_path(connection.execute(text("SHOW search_path")).scalar_one())


def _exception_text(exc: BaseException) -> str:
    parts = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(str(current))
        current = current.__cause__ or current.__context__
    return "\n".join(parts)


def _reject(session, sql: str, params: dict, needle: str) -> None:
    with pytest.raises(Exception) as caught:
        session.execute(text(sql), params)
        session.commit()
    session.rollback()
    assert needle.casefold() in str(caught.value).casefold()


def _version(team_id, number: int, checksum: str) -> TeamConfigurationVersion:
    return TeamConfigurationVersion(
        id=uuid.uuid4(),
        team_id=team_id,
        version_number=number,
        status="approved",
        effective_month="July",
        effective_year=2026,
        config_snapshot={"policy": "employee_ratio"},
        config_checksum=checksum,
        effective_from_month=7,
        effective_from_year=2026,
        effective_until_month=7,
        effective_until_year=2026,
        performance_level="Employee",
        position_name="",
        published_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        actor_created_snapshot={"state": "unknown"},
        actor_published_snapshot={"state": "unknown"},
    )


def _seed(session):
    admin = User(
        id=uuid.uuid4(),
        full_name="Apply Admin",
        username=f"apply-admin-{uuid.uuid4().hex[:8]}",
        email=f"apply-admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hash",
        role="Admin",
    )
    coding = Team(
        id=uuid.uuid4(),
        name=f"Coding-{uuid.uuid4().hex[:6]}",
        db_name=f"Coding-{uuid.uuid4().hex[:6]}",
        display_name="Coding",
        region="UAE",
        team_level="employee",
    )
    session.add_all([admin, coding])
    session.flush()
    employee = Employee(
        id=uuid.uuid4(),
        employee_id=f"C-{uuid.uuid4().hex[:8]}",
        name="Ada",
        team_id=coding.id,
        region="UAE",
        performance_level="Employee",
    )
    scope = EvaluationScope(
        id=uuid.uuid4(),
        team_id=coding.id,
        team_key=f"coding-{uuid.uuid4().hex[:8]}",
        display_name="Coding",
        performance_level="Employee",
        position_name="",
        readiness="supported",
        history_note="foundation",
        source_kind="workbook",
        ambiguous_kpis=[],
    )
    version = _version(coding.id, 1, "11" * 32)
    record = PerformanceRecord(
        id=uuid.uuid4(),
        year=2026,
        employee_id=employee.id,
        team_id=coding.id,
        month="July",
        performance_level="Employee",
        position_name="",
        score=Decimal("70.00"),
        grade="D",
        status="Below",
        record_payload={"employee": "Ada", "actual": 40},
    )
    job = ProcessingJob(
        id=uuid.uuid4(),
        kind="evaluation_apply",
        status="queued",
        requested_by_user_id=admin.id,
        requested_by_name=admin.username,
        request_json={"scope_id": str(scope.id), "year": 2026, "month": 7},
        claim_epoch=0,
        idempotency_key=f"coding:2026:7:{uuid.uuid4().hex[:8]}",
    )
    session.add_all([employee, scope, version, record, job])
    session.flush()
    control = EvaluationApplyControl(
        job_id=job.id,
        scope_id=scope.id,
        version_id=version.id,
        team_id=coding.id,
        performance_level="Employee",
        position_name="",
        year=2026,
        month=7,
        engine_version=ENGINE,
        rules_checksum=RULES,
        proof_source_fingerprint=PROOF,
        lineage_fingerprint=LINEAGE,
        requested_by_user_id=admin.id,
        actor_snapshot=known_actor_snapshot(admin.id),
        state="pending",
        claim_epoch=0,
        staged_count=0,
        promoted_count=0,
    )
    session.add(control)
    session.commit()
    return {"admin": admin, "coding": coding, "scope": scope, "version": version, "record": record, "job": job}


@pytest.fixture(params=list(TARGETS), ids=lambda item: item["name"])
def pg(request):
    target = request.param
    engine = create_engine(url_for(target), poolclass=NullPool)
    with engine.connect() as connection:
        reset_public(connection, target)
        assert_public_search_path(connection, target)
    # The historical root migration alters an already-present schema; it is
    # not a bootstrap migration. Exercise this new migration from its actual
    # predecessor, not an imaginary empty-database upgrade chain.
    parents = [table for table in Base.metadata.sorted_tables if table.name not in {
        "processing_jobs", "evaluation_apply_controls", "evaluation_apply_stage_rows", "cache_invalidation_outbox",
    }]
    Base.metadata.create_all(engine, tables=parents)
    with engine.begin() as connection:
        assert_public_search_path(connection, target)
        path = Path(__file__).resolve().parents[1] / "migrations/versions/f5c2d7e8a901_add_processing_jobs.py"
        spec = importlib.util.spec_from_file_location("prior_processing_job_migration", path)
        prior_jobs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prior_jobs)
        with Operations.context(MigrationContext.configure(connection)):
            prior_jobs.upgrade()
    _HISTORY.stamp(url_for(target), APPLY_FOUNDATION_PREDECESSOR)
    upgrade(url_for(target), "head")
    with engine.connect() as connection:
        assert_public_search_path(connection, target)
        assert alembic_version(connection) == APPLY_FOUNDATION_REVISION
    yield engine, target
    engine.dispose()


def _session(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def test_upgraded_schema_matches_the_helper(pg):
    engine, target = pg
    with engine.connect() as connection:
        assert_public_search_path(connection, target)
        assert missing_apply_foundation_objects(connection) == []
        assert missing_history_objects(connection) == []
        definition = processing_job_kind_definition(connection).casefold()
    for kind in ("pms_upload", "report_generation", "story_report_generation", "evaluation_apply"):
        assert f"'{kind}'" in definition
    assert JOB_KINDS == {"pms_upload", "report_generation", "story_report_generation"}
    assert "evaluation_apply" not in JOB_KINDS
    assert "evaluation_apply" in KIND_CHECK_SQL


def test_direct_sql_constraints_fence_evidence(pg):
    engine, target = pg
    session = _session(engine)
    try:
        with engine.connect() as connection:
            assert_public_search_path(connection, target)
        data = _seed(session)
        spare = ProcessingJob(
            id=uuid.uuid4(),
            kind="evaluation_apply",
            status="queued",
            requested_by_user_id=data["admin"].id,
            request_json={"probe": "year"},
            claim_epoch=0,
            idempotency_key=f"probe-{uuid.uuid4().hex[:8]}",
        )
        session.add(spare)
        session.commit()
        _reject(
            session,
            """
            INSERT INTO evaluation_apply_controls (
                job_id, scope_id, version_id, team_id, performance_level, position_name,
                year, month, engine_version, rules_checksum, proof_source_fingerprint,
                lineage_fingerprint, requested_by_user_id, actor_snapshot, state,
                claim_epoch, staged_count, promoted_count
            )
            SELECT :new_job, scope_id, version_id, team_id, performance_level, position_name,
                   1999, month, engine_version, rules_checksum, proof_source_fingerprint,
                   lineage_fingerprint, requested_by_user_id, actor_snapshot, state,
                   claim_epoch, staged_count, promoted_count
            FROM evaluation_apply_controls WHERE job_id = :job_id
            """,
            {"job_id": data["job"].id, "new_job": spare.id},
            "ck_evaluation_apply_year",
        )
        _reject(
            session,
            """
            INSERT INTO evaluation_apply_controls (
                job_id, scope_id, version_id, team_id, performance_level, position_name,
                year, month, engine_version, rules_checksum, proof_source_fingerprint,
                lineage_fingerprint, requested_by_user_id, actor_snapshot, state,
                claim_epoch, staged_count, promoted_count
            )
            SELECT :new_job, scope_id, version_id, team_id, performance_level, position_name,
                   year, month, engine_version, rules_checksum, proof_source_fingerprint,
                   lineage_fingerprint, requested_by_user_id, actor_snapshot, 'pending',
                   0, 0, 0
            FROM evaluation_apply_controls WHERE job_id = :job_id
            """,
            {"job_id": data["job"].id, "new_job": spare.id},
            "uq_evaluation_apply_one_open_scope_month",
        )
        session.execute(
            text("UPDATE evaluation_apply_controls SET state = 'staging' WHERE job_id = :job_id"),
            {"job_id": data["job"].id},
        )
        session.commit()
        _reject(
            session,
            """
            INSERT INTO evaluation_apply_stage_rows (
                job_id, claim_epoch, record_id, record_year, before_row, after_row,
                before_hash, after_hash, rules_checksum
            ) VALUES (
                :job_id, 1, :record_id, 2026, CAST('{"score":"70"}' AS jsonb),
                CAST('{"score":"88"}' AS jsonb), :before_hash, :after_hash, :rules
            )
            """,
            {
                "job_id": data["job"].id,
                "record_id": data["record"].id,
                "before_hash": "a" * 64,
                "after_hash": "b" * 64,
                "rules": RULES,
            },
            "stale evaluation apply epoch cannot write stage evidence",
        )
        _reject(
            session,
            """
            INSERT INTO evaluation_apply_stage_rows (
                job_id, claim_epoch, record_id, record_year, before_row, after_row,
                before_hash, after_hash, rules_checksum
            ) VALUES (
                :job_id, 0, :record_id, 2025, CAST('{}' AS jsonb), CAST('{}' AS jsonb),
                :before_hash, :after_hash, :rules
            )
            """,
            {
                "job_id": data["job"].id,
                "record_id": data["record"].id,
                "before_hash": "a" * 64,
                "after_hash": "b" * 64,
                "rules": RULES,
            },
            "foreign key",
        )
        _reject(
            session,
            "UPDATE processing_jobs SET claim_epoch = -1 WHERE id = :job_id",
            {"job_id": data["job"].id},
            "ck_processing_job_claim_epoch",
        )
    finally:
        session.close()


def test_empty_downgrade_restores_prior_kind_check(pg):
    engine, target = pg
    upload_id = uuid.uuid4()
    with engine.begin() as connection:
        assert_public_search_path(connection, target)
        assert apply_foundation_downgrade_blockers(connection) == {
            "evaluation_apply_jobs": 0,
            "advanced_claim_epochs": 0,
            "controls": 0,
            "stage_rows": 0,
            "outbox_rows": 0,
        }
        connection.execute(
            text(
                """
                INSERT INTO processing_jobs (id, kind, request_json, idempotency_key)
                VALUES (:id, 'pms_upload', CAST(:payload AS jsonb), 'keep-upload')
                """
            ),
            {"id": upload_id, "payload": '{"source":"old-upload"}'},
        )
    downgrade(url_for(target), APPLY_FOUNDATION_PREDECESSOR)
    with engine.connect() as connection:
        assert_public_search_path(connection, target)
        assert alembic_version(connection) == APPLY_FOUNDATION_PREDECESSOR
        assert missing_history_objects(connection) == []
        definition = " ".join(processing_job_kind_definition(connection).split()).casefold()
        assert "evaluation_apply" not in definition
        for kind in ("pms_upload", "report_generation", "story_report_generation"):
            assert kind in definition
        assert "in (" in definition or "any" in definition
        columns = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'processing_jobs'
                    """
                )
            )
        }
        assert "claim_epoch" not in columns
        assert connection.execute(text("SELECT to_regclass('public.evaluation_apply_controls')")).scalar() is None
        assert connection.execute(text("SELECT to_regclass('public.evaluation_revisions')")).scalar() is not None
        payload = connection.execute(
            text("SELECT request_json->>'source' FROM processing_jobs WHERE id = :id"),
            {"id": upload_id},
        ).scalar_one()
        assert payload == "old-upload"
        with pytest.raises(Exception, match="ck_processing_job_kind"):
            connection.execute(
                text(
                    """
                    INSERT INTO processing_jobs (id, kind, request_json)
                    VALUES (:id, 'evaluation_apply', CAST('{}' AS jsonb))
                    """
                ),
                {"id": uuid.uuid4()},
            )


def test_populated_downgrade_refuses_before_schema_change(pg):
    engine, target = pg
    job_id = uuid.uuid4()
    with engine.begin() as connection:
        assert_public_search_path(connection, target)
        connection.execute(
            text(
                """
                INSERT INTO processing_jobs (id, kind, request_json, claim_epoch)
                VALUES (:id, 'evaluation_apply', CAST('{}' AS jsonb), 1)
                """
            ),
            {"id": job_id},
        )
    with pytest.raises(Exception) as caught:
        downgrade(url_for(target), APPLY_FOUNDATION_PREDECESSOR)
    assert "before any schema change" in _exception_text(caught.value).casefold()
    with engine.connect() as connection:
        assert_public_search_path(connection, target)
        assert alembic_version(connection) == APPLY_FOUNDATION_REVISION
        assert missing_apply_foundation_objects(connection) == []
        assert connection.execute(
            text("SELECT claim_epoch FROM processing_jobs WHERE id = :id"),
            {"id": job_id},
        ).scalar_one() == 1
        revision = EvaluationRevision.__table__.name
        assert connection.execute(text(f"SELECT to_regclass('public.{revision}')")).scalar() is not None


@pytest.mark.parametrize("mutation", ["epoch", "record_month"])
def test_validated_stage_write_serializes_with_epoch_and_record_changes(pg, mutation):
    """Pause AFTER validation, then prove no conflicting commit can overtake it."""
    engine, target = pg
    session = _session(engine)
    try:
        data = _seed(session)
        job_id, record_id = data["job"].id, data["record"].id
        session.execute(text("UPDATE evaluation_apply_controls SET state='staging' WHERE job_id=:id"), {"id": job_id})
        session.commit()
    finally:
        session.close()

    # Only the strict pg fixture's disposable public schema is altered. Trigger
    # names order alphabetically; zz executes after the actual BEFORE guard.
    lock_key = 780710
    with engine.begin() as connection:
        assert_public_search_path(connection, target)
        connection.execute(text("""
            CREATE FUNCTION reviewer_pause_validated_stage() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
              PERFORM pg_advisory_xact_lock(780710);
              RETURN NEW;
            END $$
        """))
        connection.execute(text("""
            CREATE TRIGGER zz_reviewer_pause_validated_stage
            BEFORE INSERT ON evaluation_apply_stage_rows
            FOR EACH ROW EXECUTE FUNCTION reviewer_pause_validated_stage()
        """))

    blocker = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    blocker.execute(text("SELECT pg_advisory_lock(:key)"), {"key": lock_key})
    worker_started = threading.Event()
    worker_errors = []
    worker_pid = []

    def insert_stage():
        try:
            with engine.begin() as connection:
                assert_public_search_path(connection, target)
                connection.execute(text("SET LOCAL statement_timeout='8000ms'"))
                worker_pid.append(connection.execute(text("SELECT pg_backend_pid()")).scalar_one())
                worker_started.set()
                connection.execute(text("""
                    INSERT INTO evaluation_apply_stage_rows (
                      job_id, claim_epoch, record_id, record_year, before_row, after_row,
                      before_hash, after_hash, rules_checksum
                    ) VALUES (:job,0,:record,2026,'{}'::jsonb,'{}'::jsonb,:before,:after,:rules)
                """), {"job": job_id, "record": record_id, "before": "a"*64, "after": "b"*64, "rules": RULES})
        except Exception as error:
            worker_errors.append(error)
            worker_started.set()

    worker = threading.Thread(target=insert_stage, daemon=True)
    worker.start()
    try:
        assert worker_started.wait(3), "Stage writer never started"
        assert worker_pid and not worker_errors
        deadline = time.monotonic() + 4
        paused = False
        while time.monotonic() < deadline:
            with engine.connect() as observer:
                paused = observer.execute(text("""
                    SELECT wait_event='advisory' FROM pg_stat_activity WHERE pid=:pid
                """), {"pid": worker_pid[0]}).scalar() is True
            if paused:
                break
            time.sleep(0.02)
        assert paused, "Writer was not paused after foundation validation"
        overtook = False
        with engine.connect() as connection:
            assert_public_search_path(connection, target)
            connection.execute(text("SET LOCAL lock_timeout='500ms'"))
            try:
                if mutation == "epoch":
                    connection.execute(text("UPDATE processing_jobs SET claim_epoch=1 WHERE id=:id"), {"id": job_id})
                else:
                    connection.execute(text("UPDATE performance_records SET month='August' WHERE id=:id AND year=2026"), {"id": record_id})
                connection.commit()
                overtook = True
            except Exception as error:
                connection.rollback()
                assert "lock timeout" in str(error).casefold(), str(error)
        assert not overtook, f"{mutation} committed after validation but before the old stage write"
    finally:
        blocker.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
        blocker.close()
        worker.join(10)
    assert not worker.is_alive()
    assert not worker_errors, [str(error) for error in worker_errors]
