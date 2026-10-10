"""SQLite proof for the evaluation apply foundation.

These tests exercise database constraints with direct SQL. They do not certify
PostgreSQL, and they do not run a worker, route, or scoring apply.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.evaluation_history_schema import missing_history_objects
from models.models import (
    CacheInvalidationOutbox,
    Employee,
    EvaluationApplyControl,
    EvaluationApplyStageRow,
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
    CLAIM_EPOCH_CHECK_SQL,
    CONTROL_CHECKS,
    CURSOR_LIMIT,
    JOB_FOUNDATION_CHECKS,
    KIND_CHECK_SQL,
    OUTBOX_CHECKS,
    OUTBOX_ERROR_LIMIT,
    PRIOR_KIND_CHECK_SQL,
    STAGE_CHECKS,
    STAGE_FOREIGN_KEYS,
    _GUARD_TRIGGER_CONTRACT,
    _INDEX_CONTRACTS,
    _LOCK_ORDER_SQL,
    _canonical_check,
    _decode_trigger_tgtype,
    _foreign_key_actions,
    _foreign_key_identity_problems,
    _postgres_guard_statements,
    _sqlite_guard_statements,
    _sqlite_trigger_targets,
    apply_foundation_downgrade_blockers,
    cache_dedup_key,
    canonical_row_hash,
    check_catalog_problems,
    check_expressions_equivalent,
    downgrade_apply_foundation,
    guard_trigger_problems,
    index_identity_problems,
    known_actor_snapshot,
    missing_apply_foundation_objects,
    processing_job_kind_definition,
    sqlite_prior_processing_job_ddl,
    upgrade_apply_foundation,
)
from services.processing_job_service import JOB_KINDS, ProcessingJobService


RULES = "ab" * 32
PROOF = "cd" * 32
LINEAGE = "ef" * 32
ENGINE = "unset-until-phase7b"
EXCLUDED_TABLES = {
    "processing_jobs",
    "evaluation_apply_controls",
    "evaluation_apply_stage_rows",
    "cache_invalidation_outbox",
}


def _engine():
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

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _bind_uuid(_conn, _cursor, statement, parameters, _context, _executemany):
        # Raw SQL in this file binds uuid.UUID. SQLite stores CHAR(32) hex.
        def _hex(value):
            return value.hex if isinstance(value, uuid.UUID) else value

        if isinstance(parameters, Mapping):
            parameters = {key: _hex(value) for key, value in parameters.items()}
        elif isinstance(parameters, (tuple, list)):
            parameters = type(parameters)(_hex(value) for value in parameters)
        return statement, parameters

    return engine


def _session(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


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
        username="apply-admin",
        email="apply-admin@example.com",
        password_hash="hash",
        role="Admin",
    )
    coding = Team(
        id=uuid.uuid4(),
        name="Coding",
        db_name="Coding",
        display_name="Coding",
        region="UAE",
        team_level="employee",
    )
    other = Team(
        id=uuid.uuid4(),
        name="Submission",
        db_name="Submission",
        display_name="Submission",
        region="UAE",
        team_level="employee",
    )
    session.add_all([admin, coding, other])
    session.flush()
    coding_employee = Employee(
        id=uuid.uuid4(),
        employee_id="C-1",
        name="Ada",
        team_id=coding.id,
        region="UAE",
        performance_level="Employee",
    )
    other_employee = Employee(
        id=uuid.uuid4(),
        employee_id="S-1",
        name="Grace",
        team_id=other.id,
        region="UAE",
        performance_level="Employee",
    )
    scope = EvaluationScope(
        id=uuid.uuid4(),
        team_id=coding.id,
        team_key="coding",
        display_name="Coding",
        performance_level="Employee",
        position_name="",
        readiness="supported",
        history_note="foundation",
        source_kind="workbook",
        ambiguous_kpis=[],
    )
    other_scope = EvaluationScope(
        id=uuid.uuid4(),
        team_id=other.id,
        team_key="submission",
        display_name="Submission",
        performance_level="Employee",
        position_name="",
        readiness="blocked",
        block_reason="unproven",
        history_note="not a grant",
        source_kind="workbook",
        ambiguous_kpis=[],
    )
    version = _version(coding.id, 1, "11" * 32)
    other_version = _version(other.id, 1, "22" * 32)
    july = PerformanceRecord(
        id=uuid.uuid4(),
        year=2026,
        employee_id=coding_employee.id,
        team_id=coding.id,
        month="July",
        performance_level="Employee",
        position_name="",
        score=Decimal("70.00"),
        grade="D",
        status="Below",
        record_payload={"employee": "Ada", "actual": 40},
    )
    august = PerformanceRecord(
        id=uuid.uuid4(),
        year=2026,
        employee_id=coding_employee.id,
        team_id=coding.id,
        month="August",
        performance_level="Employee",
        position_name="",
        score=Decimal("71.00"),
        grade="D",
        status="Below",
        record_payload={"employee": "Ada", "actual": 41},
    )
    other_record = PerformanceRecord(
        id=uuid.uuid4(),
        year=2026,
        employee_id=other_employee.id,
        team_id=other.id,
        month="July",
        performance_level="Employee",
        position_name="",
        score=Decimal("60.00"),
        grade="E",
        status="Below",
        record_payload={"employee": "Grace"},
    )
    job = ProcessingJob(
        id=uuid.uuid4(),
        kind="evaluation_apply",
        status="queued",
        requested_by_user_id=admin.id,
        requested_by_name=admin.username,
        request_json={"scope_id": str(scope.id), "year": 2026, "month": 7},
        claim_epoch=0,
        idempotency_key="coding:2026:7:first",
    )
    session.add_all([
        coding_employee,
        other_employee,
        scope,
        other_scope,
        version,
        other_version,
        july,
        august,
        other_record,
        job,
    ])
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
    return {
        "admin": admin,
        "coding": coding,
        "other": other,
        "scope": scope,
        "other_scope": other_scope,
        "version": version,
        "other_version": other_version,
        "july": july,
        "august": august,
        "other_record": other_record,
        "job": job,
        "control": control,
    }


@pytest.fixture()
def foundation():
    engine = _engine()
    Base.metadata.create_all(engine)
    session = _session(engine)
    try:
        yield session, _seed(session)
    finally:
        session.close()
        engine.dispose()


def test_fresh_schema_matches_the_helper_and_keeps_history_guards(foundation):
    session, _data = foundation
    connection = session.connection()
    assert missing_apply_foundation_objects(connection) == []
    assert missing_history_objects(connection) == []
    definition = processing_job_kind_definition(connection).casefold()
    for kind in ("pms_upload", "report_generation", "story_report_generation", "evaluation_apply"):
        assert f"'{kind}'" in definition
    assert "ck_processing_job_status" in definition
    assert JOB_KINDS == {"pms_upload", "report_generation", "story_report_generation"}
    assert "evaluation_apply" not in JOB_KINDS


def test_check_constraints_reject_bad_identity(foundation):
    session, data = foundation
    job_id = data["job"].id
    year_job = uuid.uuid4()
    month_job = uuid.uuid4()
    session.add_all([
        ProcessingJob(
            id=year_job,
            kind="evaluation_apply",
            status="queued",
            requested_by_user_id=data["admin"].id,
            request_json={"probe": "year"},
            claim_epoch=0,
            idempotency_key="probe-year",
        ),
        ProcessingJob(
            id=month_job,
            kind="evaluation_apply",
            status="queued",
            requested_by_user_id=data["admin"].id,
            request_json={"probe": "month"},
            claim_epoch=0,
            idempotency_key="probe-month",
        ),
    ])
    session.commit()
    _reject(
        session,
        "UPDATE evaluation_apply_controls SET year = 1999 WHERE job_id = :job_id",
        {"job_id": job_id},
        "evaluation apply captured identity is immutable",
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
               1999, month, engine_version, rules_checksum, proof_source_fingerprint,
               lineage_fingerprint, requested_by_user_id, actor_snapshot, state,
               claim_epoch, staged_count, promoted_count
        FROM evaluation_apply_controls WHERE job_id = :job_id
        """,
        {"job_id": job_id, "new_job": year_job},
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
               year, 13, engine_version, rules_checksum, proof_source_fingerprint,
               lineage_fingerprint, requested_by_user_id, actor_snapshot, state,
               claim_epoch, staged_count, promoted_count
        FROM evaluation_apply_controls WHERE job_id = :job_id
        """,
        {"job_id": job_id, "new_job": month_job},
        "ck_evaluation_apply_month",
    )
    _reject(
        session,
        "UPDATE evaluation_apply_controls SET rules_checksum = :checksum WHERE job_id = :job_id",
        {"job_id": job_id, "checksum": "Q" * 64},
        "evaluation apply fingerprints must be lowercase sha256",
    )


def test_direct_insert_rejects_bad_fingerprint_and_cross_scope_team(foundation):
    session, data = foundation
    spare = ProcessingJob(
        id=uuid.uuid4(),
        kind="evaluation_apply",
        status="queued",
        requested_by_user_id=data["admin"].id,
        request_json={"scope_id": str(data["scope"].id)},
        claim_epoch=0,
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
        ) VALUES (
            :job_id, :scope_id, :version_id, :team_id, 'Employee', '',
            2026, 7, :engine, :rules, :proof, :lineage, :user_id, :actor,
            'pending', 0, 0, 0
        )
        """,
        {
            "job_id": spare.id,
            "scope_id": data["other_scope"].id,
            "version_id": data["other_version"].id,
            "team_id": data["coding"].id,
            "engine": ENGINE,
            "rules": RULES,
            "proof": PROOF,
            "lineage": LINEAGE,
            "user_id": data["admin"].id,
            "actor": '{"state":"known","user_id":"%s"}' % data["admin"].id,
        },
        "evaluation apply scope identity does not match the scope row",
    )
    _reject(
        session,
        """
        INSERT INTO evaluation_apply_controls (
            job_id, scope_id, version_id, team_id, performance_level, position_name,
            year, month, engine_version, rules_checksum, proof_source_fingerprint,
            lineage_fingerprint, requested_by_user_id, actor_snapshot, state,
            claim_epoch, staged_count, promoted_count
        ) VALUES (
            :job_id, :scope_id, :version_id, :team_id, 'Employee', '',
            2026, 8, :engine, :rules, :proof, :lineage, :user_id, :actor,
            'pending', 0, 0, 0
        )
        """,
        {
            "job_id": spare.id,
            "scope_id": data["scope"].id,
            "version_id": data["version"].id,
            "team_id": data["coding"].id,
            "engine": ENGINE,
            "rules": "QQ" * 32,
            "proof": PROOF,
            "lineage": LINEAGE,
            "user_id": data["admin"].id,
            "actor": '{"state":"known","user_id":"%s"}' % data["admin"].id,
        },
        "evaluation apply fingerprints must be lowercase sha256",
    )


def test_one_open_job_per_exact_scope_month(foundation):
    session, data = foundation
    second = ProcessingJob(
        id=uuid.uuid4(),
        kind="evaluation_apply",
        status="queued",
        requested_by_user_id=data["admin"].id,
        request_json={"scope_id": str(data["scope"].id)},
        claim_epoch=0,
        idempotency_key="coding:2026:7:second",
    )
    session.add(second)
    session.commit()
    index_sql = session.execute(
        text("SELECT sql FROM sqlite_master WHERE name = 'uq_evaluation_apply_one_open_scope_month'")
    ).scalar()
    assert index_sql
    folded = " ".join(index_sql.split()).casefold()
    assert "unique" in folded
    for state in ("pending", "staging", "promoting"):
        assert state in folded
    _reject(
        session,
        """
        INSERT INTO evaluation_apply_controls (
            job_id, scope_id, version_id, team_id, performance_level, position_name,
            year, month, engine_version, rules_checksum, proof_source_fingerprint,
            lineage_fingerprint, requested_by_user_id, actor_snapshot, state,
            claim_epoch, staged_count, promoted_count
        )
        SELECT :job_id, scope_id, version_id, team_id, performance_level, position_name,
               year, month, engine_version, rules_checksum, proof_source_fingerprint,
               lineage_fingerprint, requested_by_user_id, actor_snapshot, 'pending',
               0, 0, 0
        FROM evaluation_apply_controls WHERE job_id = :existing
        """,
        {"job_id": second.id, "existing": data["job"].id},
        "unique",
    )
    session.execute(
        text("UPDATE evaluation_apply_controls SET state = 'failed' WHERE job_id = :job_id"),
        {"job_id": data["job"].id},
    )
    session.execute(
        text(
            """
            INSERT INTO evaluation_apply_controls (
                job_id, scope_id, version_id, team_id, performance_level, position_name,
                year, month, engine_version, rules_checksum, proof_source_fingerprint,
                lineage_fingerprint, requested_by_user_id, actor_snapshot, state,
                claim_epoch, staged_count, promoted_count
            )
            SELECT :job_id, scope_id, version_id, team_id, performance_level, position_name,
                   year, 8, engine_version, rules_checksum, proof_source_fingerprint,
                   lineage_fingerprint, requested_by_user_id, actor_snapshot, 'pending',
                   0, 0, 0
            FROM evaluation_apply_controls WHERE job_id = :existing
            """
        ),
        {"job_id": second.id, "existing": data["job"].id},
    )
    session.commit()
    assert session.execute(
        text("SELECT COUNT(*) FROM evaluation_apply_controls WHERE scope_id = :scope_id"),
        {"scope_id": data["scope"].id},
    ).scalar() == 2


def test_missing_requester_cannot_remain_open_or_be_replayed(foundation):
    session, data = foundation
    _reject(
        session,
        "UPDATE evaluation_apply_controls SET requested_by_user_id = NULL WHERE job_id = :job_id",
        {"job_id": data["job"].id},
        "open evaluation apply cannot replay a missing requester",
    )
    _reject(
        session,
        "DELETE FROM users WHERE id = :user_id",
        {"user_id": data["admin"].id},
        "open evaluation apply cannot replay a missing requester",
    )
    assert session.get(User, data["admin"].id) is not None
    session.execute(
        text("UPDATE evaluation_apply_controls SET state = 'cancelled' WHERE job_id = :job_id"),
        {"job_id": data["job"].id},
    )
    session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": data["admin"].id})
    session.commit()
    requester = session.execute(
        text("SELECT requested_by_user_id, actor_snapshot FROM evaluation_apply_controls WHERE job_id = :job_id"),
        {"job_id": data["job"].id},
    ).one()
    assert requester[0] is None
    assert "known" in str(requester[1])
    session.execute(
        text("UPDATE processing_jobs SET claim_epoch = 1 WHERE id = :job_id"),
        {"job_id": data["job"].id},
    )
    session.commit()
    _reject(
        session,
        """
        UPDATE evaluation_apply_controls
        SET state = 'pending', claim_epoch = 1, staged_count = 0, stage_cursor = NULL
        WHERE job_id = :job_id
        """,
        {"job_id": data["job"].id},
        "evaluation apply retry must advance the epoch and clear progress",
    )


def test_epoch_fence_idempotent_stage_and_immutable_history(foundation):
    session, data = foundation
    before = {"record_id": str(data["july"].id), "score": "70.00"}
    after = {"record_id": str(data["july"].id), "score": "88.00"}
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
            :job_id, 1, :record_id, 2026, :before_row, :after_row,
            :before_hash, :after_hash, :rules
        )
        """,
        {
            "job_id": data["job"].id,
            "record_id": data["july"].id,
            "before_row": '{"score":"70.00"}',
            "after_row": '{"score":"88.00"}',
            "before_hash": canonical_row_hash(before),
            "after_hash": canonical_row_hash(after),
            "rules": RULES,
        },
        "stale evaluation apply epoch cannot write stage evidence",
    )
    session.add(EvaluationApplyStageRow(
        job_id=data["job"].id,
        claim_epoch=0,
        record_id=data["july"].id,
        record_year=2026,
        before_row=before,
        after_row=after,
        before_hash=canonical_row_hash(before),
        after_hash=canonical_row_hash(after),
        rules_checksum=RULES,
    ))
    session.commit()
    session.execute(
        text(
            """
            UPDATE evaluation_apply_stage_rows
            SET before_hash = before_hash
            WHERE job_id = :job_id AND claim_epoch = 0
            """
        ),
        {"job_id": data["job"].id},
    )
    session.commit()
    _reject(
        session,
        """
        UPDATE evaluation_apply_stage_rows
        SET before_row = :before_row
        WHERE job_id = :job_id AND claim_epoch = 0
        """,
        {"job_id": data["job"].id, "before_row": '{"score":"1.00"}'},
        "evaluation apply stage evidence is immutable",
    )
    _reject(
        session,
        """
        INSERT INTO evaluation_apply_stage_rows (
            job_id, claim_epoch, record_id, record_year, before_row, after_row,
            before_hash, after_hash, rules_checksum
        ) VALUES (
            :job_id, 0, :record_id, 2025, :before_row, :after_row,
            :before_hash, :after_hash, :rules
        )
        """,
        {
            "job_id": data["job"].id,
            "record_id": data["july"].id,
            "before_row": "{}",
            "after_row": "{}",
            "before_hash": "a" * 64,
            "after_hash": "b" * 64,
            "rules": RULES,
        },
        "foreign key",
    )
    _reject(
        session,
        """
        INSERT INTO evaluation_apply_stage_rows (
            job_id, claim_epoch, record_id, record_year, before_row, after_row,
            before_hash, after_hash, rules_checksum
        ) VALUES (
            :job_id, 0, :record_id, 2026, '{}', '{}', :before_hash, :after_hash, :rules
        )
        """,
        {
            "job_id": data["job"].id,
            "record_id": data["august"].id,
            "before_hash": "a" * 64,
            "after_hash": "b" * 64,
            "rules": RULES,
        },
        "evaluation apply stage record is outside the captured scope month",
    )
    _reject(
        session,
        """
        INSERT INTO evaluation_apply_stage_rows (
            job_id, claim_epoch, record_id, record_year, before_row, after_row,
            before_hash, after_hash, rules_checksum
        ) VALUES (
            :job_id, 0, :record_id, 2026, '{}', '{}', :before_hash, :after_hash, :rules
        )
        """,
        {
            "job_id": data["job"].id,
            "record_id": data["other_record"].id,
            "before_hash": "a" * 64,
            "after_hash": "b" * 64,
            "rules": RULES,
        },
        "evaluation apply stage record is outside the captured scope month",
    )
    session.execute(
        text("UPDATE processing_jobs SET claim_epoch = 1 WHERE id = :job_id"),
        {"job_id": data["job"].id},
    )
    session.execute(
        text("UPDATE evaluation_apply_controls SET state = 'failed' WHERE job_id = :job_id"),
        {"job_id": data["job"].id},
    )
    session.execute(
        text(
            """
            UPDATE evaluation_apply_controls
            SET state = 'pending', claim_epoch = 1, staged_count = 0,
                promoted_count = 0, stage_cursor = NULL
            WHERE job_id = :job_id
            """
        ),
        {"job_id": data["job"].id},
    )
    session.commit()
    _reject(
        session,
        """
        UPDATE evaluation_apply_stage_rows
        SET after_hash = after_hash
        WHERE job_id = :job_id AND claim_epoch = 0
        """,
        {"job_id": data["job"].id},
        "stale evaluation apply epoch cannot write stage evidence",
    )
    retained = session.execute(
        text("SELECT COUNT(*) FROM evaluation_apply_stage_rows WHERE claim_epoch = 0")
    ).scalar()
    assert retained == 1
    _reject(
        session,
        "DELETE FROM evaluation_apply_stage_rows WHERE job_id = :job_id",
        {"job_id": data["job"].id},
        "evaluation apply stage evidence cannot be deleted",
    )
    _reject(
        session,
        "DELETE FROM performance_records WHERE id = :record_id AND year = 2026",
        {"record_id": data["july"].id},
        "staged performance evidence cannot be deleted",
    )
    session.execute(
        text("UPDATE performance_records SET score = 91 WHERE id = :record_id AND year = 2026"),
        {"record_id": data["july"].id},
    )
    session.commit()
    _reject(
        session,
        "UPDATE performance_records SET team_id = :team_id WHERE id = :record_id AND year = 2026",
        {"record_id": data["july"].id, "team_id": data["other"].id},
        "staged performance identity cannot change while apply evidence exists",
    )


def test_header_scope_and_revision_deletes_refuse_when_evidence_exists(foundation):
    session, data = foundation
    _reject(
        session,
        "DELETE FROM processing_jobs WHERE id = :job_id",
        {"job_id": data["job"].id},
        "evaluation apply job header cannot be deleted while a control exists",
    )
    _reject(
        session,
        "UPDATE processing_jobs SET kind = 'pms_upload' WHERE id = :job_id",
        {"job_id": data["job"].id},
        "evaluation apply job kind cannot change after control capture",
    )
    _reject(
        session,
        "UPDATE processing_jobs SET request_json = :payload WHERE id = :job_id",
        {"job_id": data["job"].id, "payload": '{"rows":"%s"}' % ("x" * 3000)},
        "evaluation apply job status cannot carry a population payload",
    )
    upload = ProcessingJob(
        id=uuid.uuid4(),
        kind="pms_upload",
        status="queued",
        requested_by_user_id=data["admin"].id,
        request_json={"rows": "x" * 3000},
        claim_epoch=0,
    )
    session.add(upload)
    session.commit()
    _reject(
        session,
        "UPDATE evaluation_scopes SET team_id = :team_id WHERE id = :scope_id",
        {"scope_id": data["scope"].id, "team_id": data["other"].id},
        "captured evaluation scope identity cannot change while apply evidence exists",
    )
    session.execute(
        text("UPDATE evaluation_scopes SET readiness = 'blocked' WHERE id = :scope_id"),
        {"scope_id": data["scope"].id},
    )
    session.commit()
    revision = EvaluationRevision(
        id=uuid.uuid4(),
        team_id=data["coding"].id,
        performance_level="Employee",
        position_name="",
        year=2026,
        month=7,
        version_id=data["version"].id,
        status="active",
        prior_snapshot={"schema": "legacy-full-snapshot", "records": [{"keep": True}]},
        applied_snapshot={"schema": "legacy-full-snapshot", "records": [{"keep": True}]},
        created_by_user_id=data["admin"].id,
        actor_snapshot=known_actor_snapshot(data["admin"].id),
    )
    session.add(revision)
    session.commit()
    _reject(
        session,
        "DELETE FROM evaluation_revisions WHERE id = :revision_id",
        {"revision_id": revision.id},
        "evaluation revision history cannot be deleted",
    )


def test_outbox_is_bounded_and_publish_is_not_reversible(foundation):
    session, data = foundation
    revision = EvaluationRevision(
        id=uuid.uuid4(),
        team_id=data["coding"].id,
        performance_level="Employee",
        position_name="",
        year=2026,
        month=7,
        version_id=data["version"].id,
        status="active",
        prior_snapshot={"schema": "legacy-full-snapshot"},
        applied_snapshot={"schema": "legacy-full-snapshot"},
        created_by_user_id=data["admin"].id,
        actor_snapshot=known_actor_snapshot(data["admin"].id),
    )
    session.add(revision)
    session.commit()
    _reject(
        session,
        """
        INSERT INTO cache_invalidation_outbox (
            id, job_id, revision_id, namespace, dedup_key, delivery_attempts
        ) VALUES (:id, :job_id, :revision_id, 'data', :dedup_key, 0)
        """,
        {
            "id": uuid.uuid4(),
            "job_id": data["job"].id,
            "revision_id": revision.id,
            "dedup_key": cache_dedup_key(data["job"].id, revision.id),
        },
        "cache invalidation outbox requires a promoted revision",
    )
    session.execute(
        text("UPDATE evaluation_apply_controls SET state = 'staging' WHERE job_id = :job_id"),
        {"job_id": data["job"].id},
    )
    session.execute(
        text("UPDATE evaluation_apply_controls SET state = 'promoting' WHERE job_id = :job_id"),
        {"job_id": data["job"].id},
    )
    session.execute(
        text(
            """
            UPDATE evaluation_apply_controls
            SET state = 'promoted', promoted_revision_id = :revision_id, promoted_count = 0
            WHERE job_id = :job_id
            """
        ),
        {"job_id": data["job"].id, "revision_id": revision.id},
    )
    session.commit()
    outbox = CacheInvalidationOutbox(
        id=uuid.uuid4(),
        job_id=data["job"].id,
        revision_id=revision.id,
        namespace="data",
        dedup_key=cache_dedup_key(data["job"].id, revision.id),
        delivery_attempts=0,
    )
    session.add(outbox)
    session.commit()
    _reject(
        session,
        """
        INSERT INTO cache_invalidation_outbox (
            id, job_id, revision_id, namespace, dedup_key, delivery_attempts
        ) VALUES (:id, :job_id, :revision_id, 'data', :dedup_key, 0)
        """,
        {
            "id": uuid.uuid4(),
            "job_id": data["job"].id,
            "revision_id": revision.id,
            "dedup_key": outbox.dedup_key,
        },
        "unique",
    )
    _reject(
        session,
        "UPDATE cache_invalidation_outbox SET last_error = :error WHERE id = :id",
        {"id": outbox.id, "error": "x" * 241},
        "ck_cache_invalidation_error",
    )
    _reject(
        session,
        "UPDATE cache_invalidation_outbox SET published_at = CURRENT_TIMESTAMP WHERE id = :id",
        {"id": outbox.id},
        "ck_cache_invalidation_published_attempt",
    )
    session.execute(
        text(
            """
            UPDATE cache_invalidation_outbox
            SET delivery_attempts = 1, published_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """
        ),
        {"id": outbox.id},
    )
    session.commit()
    _reject(
        session,
        "UPDATE cache_invalidation_outbox SET published_at = NULL WHERE id = :id",
        {"id": outbox.id},
        "published cache invalidation cannot be reversed or rewritten",
    )
    _reject(
        session,
        "DELETE FROM cache_invalidation_outbox WHERE id = :id",
        {"id": outbox.id},
        "cache invalidation outbox evidence cannot be deleted",
    )
    _reject(
        session,
        "DELETE FROM evaluation_apply_controls WHERE job_id = :job_id",
        {"job_id": data["job"].id},
        "evaluation apply evidence cannot be deleted",
    )


def test_canonical_hash_is_order_independent_for_one_row():
    left = canonical_row_hash({"b": 1, "a": {"d": 2, "c": 3}})
    right = canonical_row_hash({"a": {"c": 3, "d": 2}, "b": 1})
    assert left == right
    assert left != canonical_row_hash({"a": {"c": 3, "d": 2}, "b": 2})
    with pytest.raises(TypeError):
        canonical_row_hash([{"employee": "Ada"}])


def test_service_gate_rejects_the_new_kind_before_insert(foundation):
    session, data = foundation
    with pytest.raises(ValueError, match="Unsupported processing job kind"):
        ProcessingJobService.create(
            session,
            kind="evaluation_apply",
            request_json={"scope_id": str(data["scope"].id)},
            requested_by_user_id=data["admin"].id,
            requested_by_name=data["admin"].username,
        )
    created = ProcessingJobService.create(
        session,
        kind="report_generation",
        request_json={"configuration": {"report_name": "Still queued"}},
        requested_by_user_id=data["admin"].id,
        requested_by_name=data["admin"].username,
        idempotency_key="report-still-works",
    )
    assert created.kind == "report_generation"
    assert created.claim_epoch in (0, None)


def test_upgrade_preserves_old_jobs_and_empty_downgrade_restores_checks():
    engine = _engine()
    parents = [table for table in Base.metadata.sorted_tables if table.name not in EXCLUDED_TABLES]
    Base.metadata.create_all(engine, tables=parents)
    with engine.begin() as connection:
        connection.execute(text(sqlite_prior_processing_job_ddl()))
        connection.execute(
            text(
                """
                INSERT INTO processing_jobs (id, kind, request_json, idempotency_key)
                VALUES (:id, 'pms_upload', :payload, 'keep-upload')
                """
            ),
            {"id": "a" * 32, "payload": '{"source":"old-upload"}'},
        )
        upgrade_apply_foundation(connection)
        assert missing_apply_foundation_objects(connection) == []
        connection.execute(
            text(
                """
                INSERT INTO processing_jobs (id, kind, request_json, claim_epoch)
                VALUES (:id, 'evaluation_apply', '{}', 0)
                """
            ),
            {"id": "b" * 32},
        )
    with engine.begin() as connection:
        with pytest.raises(RuntimeError, match="before any schema change"):
            downgrade_apply_foundation(connection)
        assert connection.execute(
            text("SELECT request_json FROM processing_jobs WHERE idempotency_key = 'keep-upload'")
        ).scalar() == '{"source":"old-upload"}'
        assert connection.execute(
            text("SELECT COUNT(*) FROM processing_jobs WHERE kind = 'evaluation_apply'")
        ).scalar() == 1
        assert inspect(connection).has_table("evaluation_apply_controls")
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM processing_jobs WHERE kind = 'evaluation_apply'"))
        assert apply_foundation_downgrade_blockers(connection) == {
            "evaluation_apply_jobs": 0,
            "advanced_claim_epochs": 0,
            "controls": 0,
            "stage_rows": 0,
            "outbox_rows": 0,
        }
        downgrade_apply_foundation(connection)
        definition = processing_job_kind_definition(connection)
        assert "evaluation_apply" not in definition
        for kind in ("pms_upload", "report_generation", "story_report_generation"):
            assert kind in definition
        assert PRIOR_KIND_CHECK_SQL in " ".join(definition.split())
        names = [row[1] for row in connection.execute(text("PRAGMA table_info(processing_jobs)"))]
        assert "claim_epoch" not in names
        assert inspect(connection).has_table("evaluation_apply_controls") is False
        assert connection.execute(
            text("SELECT request_json FROM processing_jobs WHERE idempotency_key = 'keep-upload'")
        ).scalar() == '{"source":"old-upload"}'
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO processing_jobs (id, kind, request_json)
                    VALUES (:id, 'evaluation_apply', '{}')
                    """
                ),
                {"id": "c" * 32},
            )
    engine.dispose()


def test_control_row_blocks_downgrade_before_schema_change(foundation):
    session, data = foundation
    connection = session.connection()
    before = processing_job_kind_definition(connection)
    with pytest.raises(RuntimeError, match="before any schema change"):
        downgrade_apply_foundation(connection)
    session.rollback()
    assert processing_job_kind_definition(session.connection()) == before
    assert session.get(EvaluationApplyControl, data["job"].id) is not None
    assert "evaluation_apply" in KIND_CHECK_SQL


def test_migration_head_is_the_foundation_revision():
    backend = __import__("pathlib").Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == [APPLY_FOUNDATION_REVISION]
    revision = scripts.get_revision(APPLY_FOUNDATION_REVISION)
    assert revision.down_revision == APPLY_FOUNDATION_PREDECESSOR


def test_postgres_check_module_is_outside_normal_collection():
    import importlib.util

    directory = __import__("pathlib").Path(__file__).resolve().parent
    path = directory / "evaluation_apply_foundation_pg_checks.py"
    assert path.is_file()
    assert not list(directory.glob("test_*apply_foundation*pg*"))
    source = path.read_text(encoding="utf-8")
    guard = source.find('os.environ.get("APP_ENV")')
    pytest_import = source.find("\nimport pytest")
    assert 0 < guard < pytest_import
    assert "sqlite:///:memory:" in source
    assert "REDIS_URL" in source
    spec = importlib.util.spec_from_file_location("evaluation_apply_foundation_pg_checks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert [(item["host"], item["port"], item["database"]) for item in module.TARGETS] == [
        ("127.0.0.1", 55432, "pms_eval_review_fix16"),
        ("127.0.0.1", 55433, "pms_eval_review_fix18"),
    ]
    assert module.USER == "pms_eval_test"
    module.refuse_search_path("public")
    module.refuse_search_path("$user, public")
    with pytest.raises(RuntimeError, match="search_path"):
        module.refuse_search_path("public, extensions")
    with pytest.raises(RuntimeError, match="allowlist"):
        module.url_for({"host": "10.0.0.8", "port": 5432, "database": "pms_eval_review_fix16"})


def _deparsed_checks() -> dict[str, str]:
    """Authoritative PostgreSQL deparser shapes, not the authored text."""

    states = "'pending'::text, 'staging'::text, 'promoting'::text, 'promoted'::text, 'failed'::text, 'cancelled'::text"
    levels = "'Employee'::text, 'Managerial'::text, 'Corporate'::text"
    open_states = "'pending'::text, 'staging'::text, 'promoting'::text"
    kinds = (
        "'pms_upload'::character varying, 'report_generation'::character varying, "
        "'story_report_generation'::character varying, 'evaluation_apply'::character varying"
    )
    return {
        "ck_evaluation_apply_state": f"CHECK ((state = ANY (ARRAY[{states}])))",
        "ck_evaluation_apply_month": "CHECK (((month >= 1) AND (month <= 12)))",
        "ck_evaluation_apply_year": "CHECK (((year >= 2000) AND (year <= 2100)))",
        "ck_evaluation_apply_level": f"CHECK ((performance_level = ANY (ARRAY[{levels}])))",
        "ck_evaluation_apply_position": "CHECK ((position_name IS NOT NULL))",
        "ck_evaluation_apply_epoch": "CHECK ((claim_epoch >= 0))",
        "ck_evaluation_apply_staged_count": "CHECK ((staged_count >= 0))",
        "ck_evaluation_apply_promoted_count": "CHECK ((promoted_count >= 0))",
        "ck_evaluation_apply_cursor": (
            "CHECK (((stage_cursor IS NULL) OR ((length((stage_cursor)::text) >= 1) "
            f"AND (length((stage_cursor)::text) <= {CURSOR_LIMIT}))))"
        ),
        "ck_evaluation_apply_engine_version": (
            "CHECK (((length((engine_version)::text) >= 1) AND (length((engine_version)::text) <= 64)))"
        ),
        "ck_evaluation_apply_rules_checksum": "CHECK ((length((rules_checksum)::text) = 64))",
        "ck_evaluation_apply_proof_fingerprint": "CHECK ((length((proof_source_fingerprint)::text) = 64))",
        "ck_evaluation_apply_lineage_fingerprint": "CHECK ((length((lineage_fingerprint)::text) = 64))",
        "ck_evaluation_apply_open_requester": (
            "CHECK (((state <> ALL (ARRAY[" + open_states + "])) OR (requested_by_user_id IS NOT NULL)))"
        ),
        "ck_evaluation_apply_promoted_revision": (
            "CHECK ((((state = 'promoted'::text) AND (promoted_revision_id IS NOT NULL) "
            "AND (promoted_count >= 0)) OR ((state <> 'promoted'::text) "
            "AND (promoted_revision_id IS NULL) AND (promoted_count = 0))))"
        ),
        "ck_evaluation_apply_pending_progress": (
            "CHECK (((state <> 'pending'::text) OR ((staged_count = 0) AND (stage_cursor IS NULL))))"
        ),
        "ck_evaluation_apply_stage_epoch": "CHECK ((claim_epoch >= 0))",
        "ck_evaluation_apply_stage_year": "CHECK (((record_year >= 2000) AND (record_year <= 2100)))",
        "ck_evaluation_apply_stage_before_hash": "CHECK ((length((before_hash)::text) = 64))",
        "ck_evaluation_apply_stage_after_hash": "CHECK ((length((after_hash)::text) = 64))",
        "ck_evaluation_apply_stage_rules_checksum": "CHECK ((length((rules_checksum)::text) = 64))",
        "ck_cache_invalidation_namespace": "CHECK ((namespace = 'data'::text))",
        "ck_cache_invalidation_attempts": "CHECK ((delivery_attempts >= 0))",
        "ck_cache_invalidation_dedup": (
            "CHECK (((length((dedup_key)::text) >= 1) AND (length((dedup_key)::text) <= 200)))"
        ),
        "ck_cache_invalidation_error": (
            "CHECK (((last_error IS NULL) OR (length((last_error)::text) <= "
            f"{OUTBOX_ERROR_LIMIT})))"
        ),
        "ck_cache_invalidation_published_attempt": (
            "CHECK (((published_at IS NULL) OR (delivery_attempts >= 1)))"
        ),
        "ck_processing_job_kind": (
            "CHECK (((kind)::text = ANY ((ARRAY[" + kinds + "])::text[])))"
        ),
        "ck_processing_job_claim_epoch": "CHECK (((claim_epoch IS NULL) OR (claim_epoch >= 0)))",
    }


def test_postgres_check_deparser_matches_and_drift_does_not():
    authored = {**CONTROL_CHECKS, **STAGE_CHECKS, **OUTBOX_CHECKS, **JOB_FOUNDATION_CHECKS}
    deparsed = _deparsed_checks()
    assert set(deparsed) == set(authored)
    validated = {name: True for name in authored}
    found = {name: deparsed[name] for name in authored}
    assert check_catalog_problems("evaluation_apply_controls", found, validated, CONTROL_CHECKS) == []
    assert check_catalog_problems("evaluation_apply_stage_rows", found, validated, STAGE_CHECKS) == []
    assert check_catalog_problems("cache_invalidation_outbox", found, validated, OUTBOX_CHECKS) == []
    assert check_catalog_problems("processing_jobs", found, validated, JOB_FOUNDATION_CHECKS) == []
    for name, expression in authored.items():
        _canonical_check(expression)
        assert check_expressions_equivalent(expression, deparsed[name])
    wide_year = "CHECK (((year >= 2000) AND (year <= 2200)))"
    assert not check_expressions_equivalent(CONTROL_CHECKS["ck_evaluation_apply_year"], wide_year)
    narrow_month = "CHECK (((month >= 0) AND (month <= 12)))"
    assert not check_expressions_equivalent(CONTROL_CHECKS["ck_evaluation_apply_month"], narrow_month)
    missing_state = (
        "CHECK ((state = ANY (ARRAY['pending'::text, 'staging'::text, 'promoted'::text, "
        "'failed'::text, 'cancelled'::text])))"
    )
    assert not check_expressions_equivalent(CONTROL_CHECKS["ck_evaluation_apply_state"], missing_state)
    extra_state = (
        "CHECK ((state = ANY (ARRAY['pending'::text, 'staging'::text, 'promoting'::text, "
        "'promoted'::text, 'failed'::text, 'cancelled'::text, 'archived'::text])))"
    )
    assert not check_expressions_equivalent(CONTROL_CHECKS["ck_evaluation_apply_state"], extra_state)
    negative_epoch = "CHECK ((claim_epoch >= -1))"
    assert not check_expressions_equivalent(CLAIM_EPOCH_CHECK_SQL, negative_epoch)
    assert not check_expressions_equivalent(KIND_CHECK_SQL, "CHECK ((kind = 'evaluation_apply'::text))")
    unvalidated = dict(validated)
    unvalidated["ck_evaluation_apply_year"] = False
    problems = check_catalog_problems(
        "evaluation_apply_controls",
        {"ck_evaluation_apply_year": deparsed["ck_evaluation_apply_year"]},
        unvalidated,
        {"ck_evaluation_apply_year": CONTROL_CHECKS["ck_evaluation_apply_year"]},
    )
    assert problems == ["check evaluation_apply_controls.ck_evaluation_apply_year is not validated"]
    drifted = check_catalog_problems(
        "evaluation_apply_controls",
        {"ck_evaluation_apply_year": wide_year},
        {"ck_evaluation_apply_year": True},
        {"ck_evaluation_apply_year": CONTROL_CHECKS["ck_evaluation_apply_year"]},
    )
    assert drifted == ["check evaluation_apply_controls.ck_evaluation_apply_year expression drifted"]


def _guard_trigger_row(
    table: str,
    function: str,
    enabled: str = "O",
    *,
    schema: str = "public",
    timing: str = "BEFORE",
    granularity: str = "ROW",
    events: frozenset[str] | None = None,
    when_predicate: str | None = None,
) -> tuple:
    return (
        table,
        schema,
        function,
        enabled,
        timing,
        granularity,
        frozenset({"INSERT", "UPDATE", "DELETE"}) if events is None else events,
        when_predicate,
    )


def test_guard_trigger_attachment_rejects_disabled_dropped_and_wrong_target():
    assert _decode_trigger_tgtype(31) == (
        "BEFORE",
        "ROW",
        frozenset({"INSERT", "UPDATE", "DELETE"}),
    )
    assert _decode_trigger_tgtype(29)[0] == "AFTER"
    assert _decode_trigger_tgtype(7)[2] == frozenset({"INSERT"})
    assert _decode_trigger_tgtype(30)[1] == "STATEMENT"
    enabled = {
        name: _guard_trigger_row(table, function)
        for name, table, function in _GUARD_TRIGGER_CONTRACT
    }
    assert guard_trigger_problems(enabled) == []
    assert any("is missing" in item for item in guard_trigger_problems({}))
    stage_name, stage_table, stage_function = _GUARD_TRIGGER_CONTRACT[1]
    wrong_table = dict(enabled)
    wrong_table[stage_name] = _guard_trigger_row("processing_jobs", stage_function)
    assert any(f"is on processing_jobs, expected {stage_table}" in item for item in guard_trigger_problems(wrong_table))
    wrong_function = dict(enabled)
    wrong_function[stage_name] = _guard_trigger_row(stage_table, "reviewer_pause_validated_stage", "A")
    assert any("calls reviewer_pause_validated_stage" in item for item in guard_trigger_problems(wrong_function))
    for flag in ("D", "R"):
        disabled = dict(enabled)
        disabled[stage_name] = _guard_trigger_row(stage_table, stage_function, flag)
        assert any(f"guard trigger {stage_name} is disabled" in item for item in guard_trigger_problems(disabled))
    after = dict(enabled)
    after[stage_name] = _guard_trigger_row(stage_table, stage_function, timing="AFTER")
    assert any("timing is AFTER, expected BEFORE" in item for item in guard_trigger_problems(after))
    insert_only = dict(enabled)
    insert_only[stage_name] = _guard_trigger_row(
        stage_table, stage_function, events=frozenset({"INSERT"})
    )
    assert any("events are ('INSERT',)" in item for item in guard_trigger_problems(insert_only))
    statement_trigger = dict(enabled)
    statement_trigger[stage_name] = _guard_trigger_row(
        stage_table, stage_function, granularity="STATEMENT"
    )
    assert any("granularity is STATEMENT, expected ROW" in item for item in guard_trigger_problems(statement_trigger))
    conditional = dict(enabled)
    conditional[stage_name] = _guard_trigger_row(stage_table, stage_function, when_predicate="false")
    assert any("has a WHEN predicate" in item for item in guard_trigger_problems(conditional))
    other_schema = dict(enabled)
    other_schema[stage_name] = _guard_trigger_row(
        stage_table, stage_function, schema="reviewer_foundation_shadow"
    )
    assert any(
        "function schema is reviewer_foundation_shadow, expected public" in item
        for item in guard_trigger_problems(other_schema)
    )


def test_index_and_foreign_key_identity_reject_name_only_matches():
    by_name = {item[1]: item for item in _INDEX_CONTRACTS}
    _table, name, columns, unique, predicate = by_name["uq_evaluation_apply_one_open_scope_month"]
    open_index = (
        "CREATE UNIQUE INDEX uq_evaluation_apply_one_open_scope_month "
        "ON public.evaluation_apply_controls USING btree (scope_id, year, month) "
        "WHERE ((state)::text = ANY ((ARRAY['pending'::character varying, "
        "'staging'::character varying, 'promoting'::character varying])::text[]))"
    )
    assert index_identity_problems(_table, name, open_index, columns, unique, predicate) == []
    swapped = open_index.replace("(scope_id, year, month)", "(scope_id, month, year)", 1)
    assert any("keys are" in item for item in index_identity_problems(_table, name, swapped, columns, unique, predicate))
    short_predicate = open_index.replace(", 'promoting'::character varying", "", 1)
    assert any("predicate drifted" in item for item in index_identity_problems(_table, name, short_predicate, columns, unique, predicate))
    _table, name, columns, unique, predicate = by_name["idx_evaluation_apply_stage_keyset"]
    keyset = (
        "CREATE INDEX idx_evaluation_apply_stage_keyset ON public.evaluation_apply_stage_rows "
        "USING btree (job_id, claim_epoch, record_year, record_id)"
    )
    assert index_identity_problems(_table, name, keyset, columns, unique, predicate) == []
    reversed_keyset = keyset.replace(
        "(job_id, claim_epoch, record_year, record_id)",
        "(job_id, claim_epoch, record_id, record_year)",
        1,
    )
    assert index_identity_problems(_table, name, reversed_keyset, columns, unique, predicate)
    _table, name, columns, unique, predicate = by_name["idx_cache_invalidation_outbox_unpublished"]
    unpublished = (
        "CREATE INDEX idx_cache_invalidation_outbox_unpublished ON public.cache_invalidation_outbox "
        "USING btree (namespace, next_retry_at) WHERE (published_at IS NULL)"
    )
    assert index_identity_problems(_table, name, unpublished, columns, unique, predicate) == []
    assert index_identity_problems(
        _table, name, unpublished.replace(" WHERE (published_at IS NULL)", ""), columns, unique, predicate
    )
    found = {
        ("record_id", "record_year"): (
            "public",
            "performance_records",
            ("id",),
            "RESTRICT",
            True,
        ),
    }
    problems = _foreign_key_identity_problems(
        "evaluation_apply_stage_rows", found, STAGE_FOREIGN_KEYS
    )
    assert any("performance_records" in item and "('id',)" in item for item in problems)
    shadow = {
        ("requested_by_user_id",): (
            "reviewer_foundation_shadow",
            "users",
            ("id",),
            "SET NULL",
            True,
        ),
    }
    shadow_problems = _foreign_key_identity_problems(
        "evaluation_apply_controls",
        shadow,
        {"requested_by_user_id": ("users", ("id",), "SET NULL")},
    )
    assert any("reviewer_foundation_shadow" in item for item in shadow_problems)
    not_valid = {
        ("requested_by_user_id",): ("public", "users", ("id",), "SET NULL", False),
    }
    invalid_problems = _foreign_key_identity_problems(
        "evaluation_apply_controls",
        not_valid,
        {"requested_by_user_id": ("users", ("id",), "SET NULL")},
    )
    assert any("False" in item for item in invalid_problems)
    assert ("record_id", "record_year") in STAGE_FOREIGN_KEYS
    assert STAGE_FOREIGN_KEYS[("record_id", "record_year")][1] == ("id", "year")


def test_stage_and_reclaim_use_one_lock_order():
    statements = _postgres_guard_statements()
    rendered = "\n".join(statements)
    assert rendered.count(_LOCK_ORDER_SQL) >= 5
    stage = next(item for item in statements if "FUNCTION guard_evaluation_apply_stage_row" in item)
    job_at = stage.index("FROM processing_jobs")
    control_at = stage.index("FROM evaluation_apply_controls")
    record_at = stage.index("FROM performance_records")
    assert job_at < control_at < record_at
    assert stage.count("FOR UPDATE") >= 3
    control = next(item for item in statements if "FUNCTION guard_evaluation_apply_control" in item)
    insert_at = control.index("TG_OP = 'INSERT'")
    job_lock = control.index("FROM processing_jobs", insert_at)
    scope_lock = control.index("FROM evaluation_scopes", insert_at)
    assert job_lock < scope_lock
    assert "FOR UPDATE" in control[job_lock:scope_lock]
    retry_at = control.index("Do not lock processing_jobs here")
    retry_select = control.index("FROM processing_jobs", retry_at)
    assert "FOR UPDATE" not in control[retry_select:retry_select + 160]
    job = next(item for item in statements if "FUNCTION guard_processing_job_apply_foundation" in item)
    assert job.index("FROM evaluation_apply_controls") < job.index("FROM performance_records")
    assert job.index("FROM performance_records") < job.index("INTO live_epoch")
    assert "FOR UPDATE" in job
    record = next(item for item in statements if "FUNCTION guard_performance_record_apply_foundation" in item)
    assert "Do not lock processing_jobs or evaluation_apply_controls" in record
    scope = next(item for item in statements if "FUNCTION guard_evaluation_scope_apply_foundation" in item)
    assert "Do not lock" in scope and "processing_jobs" in scope
    targets = _sqlite_trigger_targets()
    created = [
        statement
        for statement in _sqlite_guard_statements()
        if statement.strip().startswith("CREATE TRIGGER")
    ]
    assert len(targets) == len(created)
    assert targets["trg_performance_record_apply_identity"] == "performance_records"
    assert targets["trg_evaluation_scope_apply_identity"] == "evaluation_scopes"


def test_sqlite_catalog_keeps_composite_foreign_key_and_index_identity(foundation):
    session, _data = foundation
    connection = session.connection()
    assert missing_apply_foundation_objects(connection) == []
    found = _foreign_key_actions(connection, "evaluation_apply_stage_rows")
    assert found[("record_id", "record_year")] == (
        "main",
        "performance_records",
        ("id", "year"),
        "RESTRICT",
        True,
    )
    user_keys = _foreign_key_actions(connection, "evaluation_apply_controls")
    assert user_keys[("requested_by_user_id",)] == ("main", "users", ("id",), "SET NULL", True)


def test_uuid_columns_use_portable_generic_type():
    from sqlalchemy.dialects import sqlite
    from sqlalchemy.dialects.postgresql import UUID as PGUUID
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.sql.sqltypes import Uuid

    assert isinstance(ProcessingJob.id.type, Uuid)
    assert isinstance(EvaluationApplyControl.job_id.type, Uuid)
    assert not isinstance(ProcessingJob.id.type, PGUUID)
    ddl = str(CreateTable(ProcessingJob.__table__).compile(dialect=sqlite.dialect()))
    assert "CHAR(32)" in ddl
    assert "NUMERIC" not in ddl
