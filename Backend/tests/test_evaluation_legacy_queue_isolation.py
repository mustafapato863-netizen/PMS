"""Fail-closed legacy queue isolation. Anonymous SQLite only.

This file proves the legacy worker cannot claim, mutate, or disclose an
unsupported job, including when the identity map still holds an older kind
or status. It does not start an evaluation runtime. The import guard requires
APP_ENV=test, DATABASE_URL=sqlite:///:memory:, and an empty REDIS_URL.
"""
from __future__ import annotations

import copy
import os
import uuid
from contextlib import contextmanager
from datetime import timedelta

if (
    os.environ.get("APP_ENV") != "test"
    or os.environ.get("DATABASE_URL") != "sqlite:///:memory:"
    or os.environ.get("REDIS_URL", "")
):
    raise RuntimeError("Anonymous environment required before imports")

import pytest
from sqlalchemy import event, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Query, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

import worker as worker_module
from models.models import Base, ProcessingJob, User
from services.processing_job_service import JOB_KINDS, ProcessingJobService, utcnow

LEGACY_KINDS = ("pms_upload", "report_generation", "story_report_generation")
LOW_ID = uuid.UUID("00000000-0000-4000-8000-000000000010")
HIGH_ID = uuid.UUID("00000000-0000-4000-8000-000000000020")
_DML = {"insert", "update", "delete"}


@pytest.fixture()
def world():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__, ProcessingJob.__table__])
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    user = User(
        id=uuid.uuid4(),
        username="queue-owner",
        email="queue-owner@example.test",
        password_hash="unused",
        full_name="Queue Owner",
        role="Manager",
        is_active=True,
    )
    db.add(user)
    db.commit()
    try:
        yield engine, db, user
    finally:
        db.close()
        engine.dispose()


def add_job(db, user, **overrides) -> ProcessingJob:
    now = overrides.pop("now", utcnow())
    job_id = overrides.get("id", uuid.uuid4())
    payload = {
        "id": job_id,
        "kind": "pms_upload",
        "status": "queued",
        "requested_by_user_id": user.id,
        "requested_by_name": user.username,
        "request_json": {"marker": "legacy"},
        "input_path": None,
        "progress": 0,
        "attempt_count": 0,
        "max_attempts": 3,
        "claim_epoch": 0,
        "available_at": now - timedelta(minutes=5),
        "worker_id": None,
        "lease_expires_at": None,
        "heartbeat_at": None,
        "started_at": None,
        "finished_at": None,
        "result_type": None,
        "result_id": None,
        "result_json": None,
        "error_code": None,
        "safe_error_message": None,
        "idempotency_key": f"job-{job_id}",
        "created_at": now - timedelta(minutes=5),
        "updated_at": now - timedelta(minutes=5),
    }
    payload.update(overrides)
    job = ProcessingJob(**payload)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def snapshot(db, job) -> dict:
    db.refresh(job)
    return {
        column.name: copy.deepcopy(getattr(job, column.name))
        for column in ProcessingJob.__table__.columns
    }


def flatten(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from flatten(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from flatten(item)
    else:
        yield value


def sql_verb(statement: str) -> str:
    return statement.lstrip().split(None, 1)[0].lower()


def bound_kinds(parameters) -> set[str]:
    return {
        value
        for value in flatten(parameters)
        if isinstance(value, str) and (value in JOB_KINDS or value == "evaluation_apply")
    }


@contextmanager
def capture_sql(engine):
    captured = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        captured.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield captured
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


@contextmanager
def spy_row_locks():
    seen = []
    original = Query.with_for_update

    def wrapped(self, *args, **kwargs):
        locked = original(self, *args, **kwargs)
        seen.append((locked, kwargs))
        return locked

    Query.with_for_update = wrapped
    try:
        yield seen
    finally:
        Query.with_for_update = original


def assert_executed_kind_filter(captured, marker: str) -> None:
    selects = []
    for statement, parameters in captured:
        normalized = " ".join(statement.lower().split())
        if normalized.startswith("select") and marker in normalized:
            selects.append((normalized, parameters))
    assert len(selects) == 1
    normalized, parameters = selects[0]
    where = normalized.split(" where ", 1)[-1]
    assert "kind" in where
    assert bound_kinds(parameters) == JOB_KINDS
    assert not any(sql_verb(statement) in _DML for statement, _parameters in captured)


def assert_kind_locked_query(query: Query, kwargs: dict) -> None:
    """Compile the locked ORM statement as PostgreSQL text without connecting."""

    assert kwargs.get("skip_locked") is True
    compiled = query.statement.compile(dialect=postgresql.dialect())
    sql = " ".join(str(compiled).upper().split())
    where = sql.split(" WHERE ", 1)[-1]
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "KIND" in where
    assert bound_kinds(compiled.params) == JOB_KINDS
    assert "EVALUATION_APPLY" not in sql


def assert_admission_lock(query: Query, kwargs: dict) -> None:
    """Point-update admission locks one legacy job row and does not skip it."""

    assert kwargs.get("skip_locked") is False
    assert kwargs.get("of") is None
    compiled = query.statement.compile(dialect=postgresql.dialect())
    sql = " ".join(str(compiled).upper().split())
    where = sql.split(" WHERE ", 1)[-1]
    assert "FOR UPDATE" in sql
    assert "SKIP LOCKED" not in sql
    assert " JOIN " not in sql
    assert "KIND" in where
    assert "STATUS" in where
    assert bound_kinds(compiled.params) == JOB_KINDS
    assert "EVALUATION_APPLY" not in sql


def stored_row(db, job_id) -> dict:
    return dict(
        db.execute(
            select(ProcessingJob.__table__).where(ProcessingJob.id == job_id)
        ).mappings().one()
    )


def diverge_persisted(db, job, values: dict) -> None:
    """Commit column changes without updating the loaded identity-map row."""

    db.query(ProcessingJob).filter(ProcessingJob.id == job.id).update(
        values,
        synchronize_session=False,
    )
    db.commit()


def _invoke_mutator(db, job, operation: str, worker_id):
    if operation == "heartbeat":
        return ProcessingJobService.heartbeat(db, job.id, worker_id)
    if operation == "progress":
        return ProcessingJobService.progress(db, job.id, 50, worker_id)
    if operation == "succeed":
        return ProcessingJobService.succeed(
            db,
            job.id,
            result={"published": True},
            result_type="report",
            result_id="row-1",
            worker_id=worker_id,
        )
    if operation == "fail":
        return ProcessingJobService.fail(
            db,
            job.id,
            error_code="legacy",
            message="unsupported",
            retryable=False,
            worker_id=worker_id,
        )
    raise AssertionError(operation)


_MUTATOR_CASES = (
    ("heartbeat", "legacy-worker"),
    ("progress", "legacy-worker"),
    ("progress", None),
    ("succeed", "legacy-worker"),
    ("succeed", None),
    ("fail", "legacy-worker"),
    ("fail", None),
)


def assert_only_queue_tables(engine) -> None:
    assert set(inspect(engine).get_table_names()) == {"users", "processing_jobs"}


class _InjectedSession:
    def __init__(self, session) -> None:
        self._session = session

    def close(self) -> None:
        return None

    def __getattr__(self, name):
        return getattr(self._session, name)


class _SessionFactory:
    def __init__(self, session) -> None:
        self._session = _InjectedSession(session)
        self.opens = 0

    def __call__(self):
        self.opens += 1
        return self._session


def _running_evaluation(db, user) -> ProcessingJob:
    now = utcnow()
    return add_job(
        db,
        user,
        kind="evaluation_apply",
        status="running",
        request_json={"marker": "do-not-touch"},
        input_path="jobs/evaluation.xlsx",
        progress=12,
        attempt_count=1,
        max_attempts=3,
        claim_epoch=9,
        worker_id="legacy-worker",
        lease_expires_at=now - timedelta(minutes=5),
        heartbeat_at=now - timedelta(minutes=6),
        started_at=now - timedelta(minutes=7),
        result_json={"kept": True},
        result_type="evaluation",
        result_id="kept-row",
        error_code="prior",
        safe_error_message="prior message",
        idempotency_key="evaluation-running",
    )


def test_public_create_rejects_evaluation_apply_without_writing(world):
    engine, db, user = world
    assert JOB_KINDS == {"pms_upload", "report_generation", "story_report_generation"}
    assert set(LEGACY_KINDS) == JOB_KINDS
    assert "evaluation_apply" not in JOB_KINDS

    with capture_sql(engine) as captured:
        with pytest.raises(ValueError, match=r"Unsupported processing job kind: evaluation_apply"):
            ProcessingJobService.create(
                db,
                kind="evaluation_apply",
                request_json={"scope_id": "not-a-runtime"},
                requested_by_user_id=user.id,
                requested_by_name=user.username,
            )
    assert not any(sql_verb(statement) in _DML for statement, _parameters in captured)
    assert db.query(ProcessingJob).count() == 0

    created = ProcessingJobService.create(
        db,
        kind="pms_upload",
        request_json={"filename": "still-legacy.xlsx"},
        requested_by_user_id=user.id,
        requested_by_name=user.username,
    )
    assert created.kind == "pms_upload"
    assert created.status == "queued"
    assert created.claim_epoch in (0, None)
    assert db.query(ProcessingJob).count() == 1


def test_mixed_queue_claims_legacy_jobs_in_order_and_leaves_unsupported(world):
    _engine, db, user = world
    base = utcnow() - timedelta(hours=2)
    tie = base + timedelta(minutes=10)
    future = add_job(
        db,
        user,
        kind="pms_upload",
        created_at=base,
        updated_at=base,
        available_at=utcnow() + timedelta(days=1),
        idempotency_key="future-upload",
    )
    evaluation = add_job(
        db,
        user,
        kind="evaluation_apply",
        created_at=base + timedelta(seconds=1),
        updated_at=base + timedelta(seconds=1),
        available_at=base,
        claim_epoch=11,
        request_json={"marker": "evaluation"},
        progress=3,
        idempotency_key="queued-evaluation",
    )
    low = add_job(
        db,
        user,
        id=LOW_ID,
        kind="pms_upload",
        created_at=tie,
        updated_at=tie,
        available_at=base,
        idempotency_key="low-upload",
    )
    high = add_job(
        db,
        user,
        id=HIGH_ID,
        kind="pms_upload",
        created_at=tie,
        updated_at=tie,
        available_at=base,
        idempotency_key="high-upload",
    )
    report = add_job(
        db,
        user,
        kind="report_generation",
        created_at=tie + timedelta(seconds=1),
        updated_at=tie + timedelta(seconds=1),
        available_at=base,
        idempotency_key="queued-report",
    )
    story = add_job(
        db,
        user,
        kind="story_report_generation",
        created_at=tie + timedelta(seconds=2),
        updated_at=tie + timedelta(seconds=2),
        available_at=base,
        idempotency_key="queued-story",
    )
    before_evaluation = snapshot(db, evaluation)
    before_future = snapshot(db, future)

    assert ProcessingJobService.claim_next(db, "legacy-worker") == str(low.id)
    assert ProcessingJobService.claim_next(db, "legacy-worker") == str(high.id)
    assert ProcessingJobService.claim_next(db, "legacy-worker") == str(report.id)
    assert ProcessingJobService.claim_next(db, "legacy-worker") == str(story.id)
    assert ProcessingJobService.claim_next(db, "legacy-worker") is None
    assert snapshot(db, evaluation) == before_evaluation
    assert snapshot(db, future) == before_future

    future.available_at = utcnow()
    db.commit()
    assert ProcessingJobService.claim_next(db, "legacy-worker") == str(future.id)
    assert snapshot(db, evaluation) == before_evaluation
    db.refresh(low)
    assert low.status == "running"
    assert low.attempt_count == 1
    assert low.kind == "pms_upload"


def test_claim_and_requeue_sql_filters_kinds_before_lock(world):
    engine, db, user = world
    queued = add_job(
        db,
        user,
        kind="evaluation_apply",
        status="queued",
        claim_epoch=4,
        request_json={"marker": "queued-evaluation"},
        idempotency_key="sql-queued-evaluation",
    )
    running = _running_evaluation(db, user)
    before_queued = snapshot(db, queued)
    before_running = snapshot(db, running)

    with spy_row_locks() as claim_locks, capture_sql(engine) as claim_sql:
        claimed = ProcessingJobService.claim_next(db, "legacy-worker")
    assert len(claim_locks) == 1
    assert_kind_locked_query(claim_locks[0][0], claim_locks[0][1])
    assert_executed_kind_filter(claim_sql, "available_at")
    assert claimed is None
    assert snapshot(db, queued) == before_queued
    assert snapshot(db, running) == before_running

    with spy_row_locks() as requeue_locks, capture_sql(engine) as requeue_sql:
        changed = ProcessingJobService.requeue_expired(db)
    assert len(requeue_locks) == 1
    assert_kind_locked_query(requeue_locks[0][0], requeue_locks[0][1])
    assert_executed_kind_filter(requeue_sql, "lease_expires_at")
    assert changed == 0
    assert snapshot(db, queued) == before_queued
    assert snapshot(db, running) == before_running
    assert_only_queue_tables(engine)


@pytest.mark.parametrize(
    ("operation", "worker_id"),
    [
        ("heartbeat", "legacy-worker"),
        ("progress", "legacy-worker"),
        ("progress", None),
        ("succeed", "legacy-worker"),
        ("succeed", None),
        ("fail", "legacy-worker"),
        ("fail", None),
        ("requeue_expired", None),
    ],
)
def test_legacy_mutators_do_not_write_unsupported_jobs(world, operation, worker_id):
    engine, db, user = world
    job = _running_evaluation(db, user)
    before = snapshot(db, job)

    with capture_sql(engine) as captured:
        if operation == "heartbeat":
            assert ProcessingJobService.heartbeat(db, job.id, worker_id) is False
        elif operation == "progress":
            assert ProcessingJobService.progress(db, job.id, 77, worker_id) is False
        elif operation == "succeed":
            assert ProcessingJobService.succeed(
                db,
                job.id,
                result={"published": True},
                result_type="evaluation",
                result_id="should-not-write",
                worker_id=worker_id,
            ) is None
        elif operation == "fail":
            assert ProcessingJobService.fail(
                db,
                job.id,
                error_code="legacy",
                message="No handler",
                retryable=True,
                worker_id=worker_id,
            ) is None
        else:
            assert ProcessingJobService.requeue_expired(db) == 0

    assert not any(sql_verb(statement) in _DML for statement, _parameters in captured)
    assert snapshot(db, job) == before
    assert_only_queue_tables(engine)


@pytest.mark.parametrize(
    ("kind", "role", "requester"),
    [
        ("evaluation_apply", "Admin", True),
        ("evaluation_apply", "Manager", True),
        ("evaluation_apply", "Performance Team", True),
        ("evaluation_apply", "Admin", False),
        ("evaluation_apply", None, True),
        ("unknown_job", "Admin", True),
        ("unknown_job", "Performance Team", False),
    ],
)
def test_generic_can_view_rejects_unsupported_kinds(world, kind, role, requester):
    _engine, db, user = world
    other_id = uuid.uuid4()
    user_id = str(user.id) if requester else str(other_id)
    if kind == "evaluation_apply":
        job = add_job(
            db,
            user,
            kind="evaluation_apply",
            request_json={"marker": "hidden"},
            idempotency_key="hidden-evaluation",
        )
        before = snapshot(db, job)
        assert ProcessingJobService.can_view(job, user_id, role) is False
        assert snapshot(db, job) == before
    else:
        job = type("Job", (), {"kind": kind, "requested_by_user_id": user.id})()
        assert ProcessingJobService.can_view(job, user_id, role) is False


def test_generic_can_view_keeps_legacy_owner_and_admin_rules(world):
    _engine, db, user = world
    other_id = str(uuid.uuid4())
    for kind in LEGACY_KINDS:
        job = add_job(db, user, kind=kind, idempotency_key=f"visible-{kind}")
        assert ProcessingJobService.can_view(job, str(user.id), "Manager") is True
        assert ProcessingJobService.can_view(job, other_id, "Admin") is True
        assert ProcessingJobService.can_view(job, other_id, "Manager") is False
        assert ProcessingJobService.can_view(job, None, None) is False


def test_get_and_serialize_remain_pure_reads(world):
    _engine, db, user = world
    job = add_job(
        db,
        user,
        kind="evaluation_apply",
        status="queued",
        progress=4,
        claim_epoch=2,
        request_json={"marker": "readable"},
        idempotency_key="readable-evaluation",
    )
    before = snapshot(db, job)
    loaded = ProcessingJobService.get(db, job.id)
    payload = ProcessingJobService.serialize(loaded)
    assert loaded.id == job.id
    assert payload["kind"] == "evaluation_apply"
    assert payload["status"] == "queued"
    assert payload["progress"] == 4
    assert payload["status_url"] == f"/api/jobs/{job.id}"
    assert snapshot(db, job) == before
    assert ProcessingJobService.can_view(loaded, str(user.id), "Admin") is False


@pytest.mark.parametrize("kind", LEGACY_KINDS)
def test_legacy_kind_claim_heartbeat_progress_and_success(world, kind):
    _engine, db, user = world
    job = ProcessingJobService.create(
        db,
        kind=kind,
        request_json={"filename": f"{kind}.xlsx"},
        requested_by_user_id=user.id,
        requested_by_name=user.username,
        max_attempts=3,
    )
    assert ProcessingJobService.claim_next(db, "worker-test") == str(job.id)
    db.refresh(job)
    assert job.status == "running"
    assert job.attempt_count == 1
    assert job.worker_id == "worker-test"
    lease_after_claim = job.lease_expires_at
    assert lease_after_claim is not None

    assert ProcessingJobService.heartbeat(db, job.id, "worker-test") is True
    assert ProcessingJobService.heartbeat(db, job.id, "other-worker") is False
    db.refresh(job)
    assert job.status == "running"
    assert job.worker_id == "worker-test"
    assert job.lease_expires_at >= lease_after_claim

    assert ProcessingJobService.progress(db, job.id, 42, "worker-test") is True
    assert ProcessingJobService.succeed(
        db,
        job.id,
        result={"id": "report-1"},
        result_type=kind,
        result_id="report-1",
        worker_id="stale-worker",
    ) is None
    db.refresh(job)
    assert job.status == "running"
    assert job.progress == 42
    completed = ProcessingJobService.succeed(
        db,
        job.id,
        result={"id": "report-1"},
        result_type=kind,
        result_id="report-1",
        worker_id="worker-test",
    )
    assert completed is not None
    assert completed.status == "succeeded"
    assert completed.progress == 100
    assert completed.claim_epoch in (0, None)
    assert ProcessingJobService.serialize(completed)["result"] == {"id": "report-1"}


def test_legacy_omitted_worker_id_can_progress_and_succeed(world):
    _engine, db, user = world
    job = ProcessingJobService.create(
        db,
        kind="report_generation",
        request_json={"configuration": {"report_name": "Omitted worker"}},
        requested_by_user_id=user.id,
        requested_by_name=user.username,
    )
    assert ProcessingJobService.claim_next(db, "worker-test") == str(job.id)
    assert ProcessingJobService.progress(db, job.id, 15) is True
    completed = ProcessingJobService.succeed(db, job.id, result={"id": "ok"}, result_type="report", result_id="ok")
    assert completed is not None
    assert completed.status == "succeeded"
    assert completed.progress == 100
    assert completed.result_json == {"id": "ok"}


@pytest.mark.parametrize("kind", LEGACY_KINDS)
def test_legacy_kind_retry_becomes_terminal_at_attempt_limit(world, kind):
    _engine, db, user = world
    job = ProcessingJobService.create(
        db,
        kind=kind,
        request_json={"filename": f"{kind}.xlsx"},
        requested_by_user_id=user.id,
        requested_by_name=user.username,
        max_attempts=2,
    )
    assert ProcessingJobService.claim_next(db, "worker-test") == str(job.id)
    first_failure = ProcessingJobService.fail(
        db,
        job.id,
        error_code="temporary",
        message="temporary failure",
        retryable=True,
    )
    assert first_failure is not None
    assert first_failure.status == "queued"
    assert first_failure.error_code == "temporary"
    assert first_failure.attempt_count == 1
    assert first_failure.worker_id is None
    assert first_failure.lease_expires_at is None

    first_failure.available_at = utcnow()
    db.commit()
    assert ProcessingJobService.claim_next(db, "worker-test") == str(job.id)
    terminal = ProcessingJobService.fail(
        db,
        job.id,
        error_code="permanent",
        message="permanent failure",
        retryable=True,
    )
    assert terminal is not None
    assert terminal.status == "failed"
    assert terminal.error_code == "permanent"
    assert terminal.attempt_count == 2


def test_requeue_expired_keeps_legacy_attempt_rules_and_skips_unsupported(world):
    _engine, db, user = world
    now = utcnow()
    evaluation = _running_evaluation(db, user)
    retryable = add_job(
        db,
        user,
        kind="pms_upload",
        status="running",
        attempt_count=1,
        max_attempts=3,
        claim_epoch=2,
        progress=8,
        worker_id="legacy-worker",
        lease_expires_at=now - timedelta(minutes=5),
        started_at=now - timedelta(minutes=6),
        idempotency_key="expired-upload",
    )
    exhausted = add_job(
        db,
        user,
        kind="report_generation",
        status="running",
        attempt_count=3,
        max_attempts=3,
        claim_epoch=2,
        progress=9,
        worker_id="legacy-worker",
        lease_expires_at=now - timedelta(minutes=5),
        started_at=now - timedelta(minutes=6),
        idempotency_key="expired-report",
    )
    fresh = add_job(
        db,
        user,
        kind="story_report_generation",
        status="running",
        attempt_count=1,
        max_attempts=3,
        worker_id="legacy-worker",
        lease_expires_at=now + timedelta(hours=2),
        idempotency_key="fresh-story",
    )
    waiting = add_job(
        db,
        user,
        kind="pms_upload",
        status="queued",
        idempotency_key="still-queued-upload",
    )
    before_evaluation = snapshot(db, evaluation)
    before_fresh = snapshot(db, fresh)
    before_waiting = snapshot(db, waiting)

    changed = ProcessingJobService.requeue_expired(db)

    assert snapshot(db, evaluation) == before_evaluation
    assert snapshot(db, fresh) == before_fresh
    assert snapshot(db, waiting) == before_waiting
    assert changed == 2
    db.refresh(retryable)
    db.refresh(exhausted)
    assert retryable.status == "queued"
    assert retryable.attempt_count == 1
    assert retryable.claim_epoch == 2
    assert retryable.progress == 8
    assert retryable.error_code == "worker_lease_expired"
    assert retryable.safe_error_message == "The worker lease expired; the job was re-queued."
    assert retryable.worker_id is None
    assert retryable.lease_expires_at is None
    assert retryable.finished_at is None
    assert exhausted.status == "failed"
    assert exhausted.attempt_count == 3
    assert exhausted.claim_epoch == 2
    assert exhausted.progress == 9
    assert exhausted.error_code == "worker_lease_expired"
    assert exhausted.safe_error_message == "The worker stopped responding before the job completed."
    assert exhausted.worker_id is None
    assert exhausted.lease_expires_at is None
    assert exhausted.finished_at is not None


def test_process_job_once_unsupported_kind_is_a_noop(world, monkeypatch):
    engine, db, user = world
    job = _running_evaluation(db, user)
    before = snapshot(db, job)
    factory = _SessionFactory(db)
    calls = []
    constructed = []

    class _RecordingThread:
        def __init__(self, *args, **kwargs) -> None:
            constructed.append(kwargs.get("name"))

        def start(self) -> None:
            calls.append("thread-start")

        def join(self, timeout=None) -> None:
            return None

    def record(name):
        def _recorded(*_args, **_kwargs):
            calls.append(name)
            raise AssertionError(name)

        return _recorded

    original_fail = ProcessingJobService.__dict__["fail"].__func__
    original_succeed = ProcessingJobService.__dict__["succeed"].__func__

    def record_fail(*args, **kwargs):
        calls.append("fail")
        return original_fail(*args, **kwargs)

    def record_succeed(*args, **kwargs):
        calls.append("succeed")
        return original_succeed(*args, **kwargs)

    def record_notify(coro) -> None:
        calls.append(getattr(getattr(coro, "cr_code", None), "co_name", "notify"))
        coro.close()

    monkeypatch.setattr(worker_module, "SessionLocal", factory)
    monkeypatch.setattr(worker_module.threading, "Thread", _RecordingThread)
    monkeypatch.setattr(worker_module, "_execute_upload", record("upload"))
    monkeypatch.setattr(worker_module, "_execute_report", record("report"))
    monkeypatch.setattr(worker_module, "_execute_story_report", record("story"))
    monkeypatch.setattr(worker_module, "_notify", record_notify)
    monkeypatch.setattr(worker_module, "cleanup_job_files", record("cleanup"))
    monkeypatch.setattr(worker_module.ProcessingJobService, "fail", record_fail)
    monkeypatch.setattr(worker_module.ProcessingJobService, "succeed", record_succeed)

    before_threads = {thread.ident for thread in __import__("threading").enumerate()}
    assert worker_module.process_job_once(str(job.id), "legacy-worker") is None
    after_threads = {thread.ident for thread in __import__("threading").enumerate()}

    assert snapshot(db, job) == before
    assert constructed == []
    assert calls == []
    assert factory.opens == 1
    assert after_threads == before_threads
    assert_only_queue_tables(engine)


@pytest.mark.parametrize(
    ("kind", "executor_name", "result_type"),
    [
        ("pms_upload", "_execute_upload", "upload"),
        ("report_generation", "_execute_report", "report"),
        ("story_report_generation", "_execute_story_report", "story_report"),
    ],
)
def test_process_job_once_legacy_happy_path_uses_existing_handlers(world, monkeypatch, kind, executor_name, result_type):
    _engine, db, user = world
    job = add_job(
        db,
        user,
        kind=kind,
        status="running",
        attempt_count=1,
        worker_id="worker-test",
        request_json={"filename": f"{kind}.xlsx", "marker": kind},
        input_path=f"jobs/{kind}.xlsx",
        idempotency_key=f"happy-{kind}",
    )
    factory = _SessionFactory(db)
    sequence = []

    class _Heartbeat:
        def __init__(self, job_id, worker_id) -> None:
            self.job_id = job_id
            self.worker_id = worker_id

        def start(self) -> None:
            sequence.append(("heartbeat", self.job_id))

        def stop(self) -> None:
            sequence.append(("heartbeat-stop", self.job_id))

    def execute(job_id, payload):
        sequence.append(("execute", kind))
        assert job_id == str(job.id)
        assert payload["filename"] == f"{kind}.xlsx"
        assert payload["input_path"] == f"jobs/{kind}.xlsx"
        return {"id": "report-1"}, "report-1", result_type

    def notify(coro) -> None:
        sequence.append(("notify", coro.cr_code.co_name))
        coro.close()

    def cleanup(job_id) -> None:
        sequence.append(("cleanup", job_id))

    monkeypatch.setattr(worker_module, "SessionLocal", factory)
    monkeypatch.setattr(worker_module, "JobLeaseHeartbeat", _Heartbeat)
    monkeypatch.setattr(worker_module, executor_name, execute)
    monkeypatch.setattr(worker_module, "_notify", notify)
    monkeypatch.setattr(worker_module, "cleanup_job_files", cleanup)

    worker_module.process_job_once(str(job.id), "worker-test")
    db.refresh(job)
    assert job.status == "succeeded"
    assert job.progress == 100
    assert job.result_json == {"id": "report-1"}
    assert job.result_type == result_type
    assert job.result_id == "report-1"
    assert job.worker_id is None
    assert job.lease_expires_at is None
    assert job.claim_epoch in (0, None)
    expected = [
        ("heartbeat", str(job.id)),
        ("execute", kind),
    ]
    if kind == "pms_upload":
        expected.append(("notify", "notify_file_upload"))
    expected.append(("notify", "notify_job_updated"))
    if kind == "pms_upload":
        expected.append(("cleanup", str(job.id)))
    expected.append(("heartbeat-stop", str(job.id)))
    assert sequence == expected
    assert factory.opens == 2


@pytest.mark.parametrize("kind", LEGACY_KINDS)
def test_process_job_once_legacy_retryable_error_requeues(world, monkeypatch, kind):
    _engine, db, user = world
    job = add_job(
        db,
        user,
        kind=kind,
        status="running",
        attempt_count=1,
        max_attempts=3,
        worker_id="worker-test",
        request_json={"filename": f"{kind}.xlsx"},
        idempotency_key=f"retry-{kind}",
    )
    factory = _SessionFactory(db)
    sequence = []

    class _Heartbeat:
        def __init__(self, job_id, _worker_id) -> None:
            self.job_id = job_id

        def start(self) -> None:
            sequence.append("start")

        def stop(self) -> None:
            sequence.append("stop")

    def explode(_job_id, _payload):
        sequence.append("execute")
        raise RuntimeError("storage offline")

    def notify(coro) -> None:
        sequence.append(("notify", coro.cr_code.co_name))
        coro.close()

    def cleanup(_job_id) -> None:
        sequence.append("cleanup")

    monkeypatch.setattr(worker_module, "SessionLocal", factory)
    monkeypatch.setattr(worker_module, "JobLeaseHeartbeat", _Heartbeat)
    monkeypatch.setattr(worker_module, "_notify", notify)
    monkeypatch.setattr(worker_module, "cleanup_job_files", cleanup)
    for executor_name in ("_execute_upload", "_execute_report", "_execute_story_report"):
        monkeypatch.setattr(worker_module, executor_name, explode)

    worker_module.process_job_once(str(job.id), "worker-test")
    db.refresh(job)
    assert job.status == "queued"
    assert job.attempt_count == 1
    assert job.error_code == "runtimeerror"
    assert job.safe_error_message == f"Background processing failed. Check the worker logs for job {job.id}."
    assert job.worker_id is None
    assert job.lease_expires_at is None
    assert job.finished_at is None
    assert sequence == ["start", "execute", ("notify", "notify_job_updated"), "stop"]
    assert factory.opens == 2


@pytest.mark.parametrize("kind", LEGACY_KINDS)
def test_process_job_once_legacy_nonretryable_error_fails_without_cleanup(world, monkeypatch, kind):
    _engine, db, user = world
    job = add_job(
        db,
        user,
        kind=kind,
        status="running",
        attempt_count=1,
        max_attempts=3,
        progress=0,
        worker_id="worker-test",
        request_json={"filename": f"{kind}.xlsx"},
        idempotency_key=f"terminal-{kind}",
    )
    factory = _SessionFactory(db)

    class _Heartbeat:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

    def explode(_job_id, _payload):
        raise ValueError("bad workbook")

    def notify(coro) -> None:
        coro.close()

    cleaned = []
    monkeypatch.setattr(worker_module, "SessionLocal", factory)
    monkeypatch.setattr(worker_module, "JobLeaseHeartbeat", _Heartbeat)
    monkeypatch.setattr(worker_module, "_notify", notify)
    monkeypatch.setattr(worker_module, "cleanup_job_files", lambda job_id: cleaned.append(job_id))
    for executor_name in ("_execute_upload", "_execute_report", "_execute_story_report"):
        monkeypatch.setattr(worker_module, executor_name, explode)

    worker_module.process_job_once(str(job.id), "worker-test")
    db.refresh(job)
    assert job.status == "failed"
    assert job.attempt_count == 1
    assert job.error_code == "valueerror"
    assert job.safe_error_message == "bad workbook"
    assert job.worker_id is None
    assert job.lease_expires_at is None
    assert job.finished_at is not None
    assert cleaned == []


def _running_report(db, user) -> ProcessingJob:
    return add_job(
        db,
        user,
        kind="report_generation",
        status="running",
        worker_id="legacy-worker",
        attempt_count=1,
        progress=12,
        claim_epoch=4,
        request_json={"marker": "stale-header"},
        idempotency_key=f"stale-{uuid.uuid4()}",
    )


@pytest.mark.parametrize(("operation", "worker_id"), _MUTATOR_CASES)
def test_mutators_follow_persisted_kind_not_stale_identity(world, operation, worker_id):
    engine, db, user = world
    job = _running_report(db, user)
    diverge_persisted(db, job, {ProcessingJob.kind: "evaluation_apply"})
    assert job.kind == "report_generation"
    before = stored_row(db, job.id)
    assert before["kind"] == "evaluation_apply"
    assert before["status"] == "running"
    assert before["claim_epoch"] == 4

    with spy_row_locks() as locks, capture_sql(engine) as captured:
        result = _invoke_mutator(db, job, operation, worker_id)

    if operation in {"heartbeat", "progress"}:
        assert result is False
    else:
        assert result is None
    assert len(locks) == 1
    assert_admission_lock(locks[0][0], locks[0][1])
    assert_executed_kind_filter(captured, "kind")
    assert job.kind == "report_generation"
    assert stored_row(db, job.id) == before
    assert_only_queue_tables(engine)


@pytest.mark.parametrize(("operation", "worker_id"), _MUTATOR_CASES)
def test_mutators_admit_persisted_legacy_kind_over_stale_identity(world, operation, worker_id):
    _engine, db, user = world
    job = add_job(
        db,
        user,
        kind="evaluation_apply",
        status="running",
        worker_id="legacy-worker",
        attempt_count=1,
        max_attempts=3,
        progress=3,
        claim_epoch=6,
        idempotency_key=f"reverse-{operation}-{worker_id}",
    )
    diverge_persisted(db, job, {ProcessingJob.kind: "report_generation"})
    assert job.kind == "evaluation_apply"
    before = stored_row(db, job.id)
    assert before["kind"] == "report_generation"

    result = _invoke_mutator(db, job, operation, worker_id)
    after = stored_row(db, job.id)
    assert after["kind"] == "report_generation"
    assert after["claim_epoch"] == before["claim_epoch"]
    assert after["attempt_count"] == 1
    if operation == "heartbeat":
        assert result is True
        assert after["status"] == "running"
        assert after["worker_id"] == "legacy-worker"
        assert after["heartbeat_at"] != before["heartbeat_at"]
        assert after["lease_expires_at"] != before["lease_expires_at"]
    elif operation == "progress":
        assert result is True
        assert after["status"] == "running"
        assert after["progress"] == 50
    elif operation == "succeed":
        assert result is not None
        assert result.kind == "report_generation"
        assert after["status"] == "succeeded"
        assert after["progress"] == 100
        assert after["worker_id"] is None
        assert after["lease_expires_at"] is None
    else:
        assert result is not None
        assert result.kind == "report_generation"
        assert after["status"] == "failed"
        assert after["error_code"] == "legacy"
        assert after["safe_error_message"] == "unsupported"
        assert after["worker_id"] is None
        assert after["lease_expires_at"] is None
        assert after["finished_at"] is not None


def test_get_and_status_projection_follow_persisted_kind(world):
    engine, db, user = world
    job = _running_report(db, user)
    diverge_persisted(db, job, {ProcessingJob.kind: "evaluation_apply"})
    assert job.kind == "report_generation"
    assert job.status == "running"
    before = stored_row(db, job.id)

    with spy_row_locks() as locks, capture_sql(engine) as captured:
        loaded = ProcessingJobService.get(db, job.id)
        payload = ProcessingJobService.serialize(loaded)

    assert locks == []
    assert not any(sql_verb(statement) in _DML for statement, _parameters in captured)
    selects = [
        (statement, parameters)
        for statement, parameters in captured
        if sql_verb(statement) == "select"
    ]
    assert len(selects) == 1
    normalized = " ".join(selects[0][0].lower().split())
    where = normalized.split(" where ", 1)[-1]
    assert "kind" not in where
    assert bound_kinds(selects[0][1]) == set()
    assert loaded is job
    assert loaded.kind == "evaluation_apply"
    assert loaded.status == "running"
    assert payload["kind"] == "evaluation_apply"
    assert payload["status"] == "running"
    assert payload["progress"] == 12
    assert ProcessingJobService.can_view(loaded, str(user.id), "Admin") is False
    assert stored_row(db, job.id) == before
    assert_only_queue_tables(engine)


def test_get_and_mutators_follow_persisted_status(world):
    engine, db, user = world
    job = _running_report(db, user)
    diverge_persisted(db, job, {ProcessingJob.status: "queued"})
    assert job.status == "running"
    assert job.kind == "report_generation"
    before = stored_row(db, job.id)
    assert before["status"] == "queued"
    assert before["kind"] == "report_generation"

    loaded = ProcessingJobService.get(db, job.id)
    assert loaded is job
    assert loaded.status == "queued"
    assert loaded.kind == "report_generation"
    assert ProcessingJobService.can_view(loaded, str(user.id), "Admin") is True
    assert ProcessingJobService.serialize(loaded)["status"] == "queued"
    assert ProcessingJobService.heartbeat(db, job.id, "legacy-worker") is False
    assert ProcessingJobService.progress(db, job.id, 50) is False
    assert ProcessingJobService.succeed(db, job.id, result={"published": True}) is None
    assert ProcessingJobService.fail(
        db,
        job.id,
        error_code="legacy",
        message="unsupported",
        retryable=True,
    ) is None
    assert stored_row(db, job.id) == before
    assert_only_queue_tables(engine)


def test_missing_and_malformed_ids_do_not_mutate(world):
    engine, db, user = world
    job = _running_report(db, user)
    before = stored_row(db, job.id)
    missing = uuid.uuid4()

    with capture_sql(engine) as captured:
        assert ProcessingJobService.get(db, "") is None
        assert ProcessingJobService.get(db, "not-a-uuid") is None
        assert ProcessingJobService.get(db, None) is None
        assert ProcessingJobService.heartbeat(db, "not-a-uuid", "legacy-worker") is False
        assert ProcessingJobService.progress(db, "", 10) is False
        assert ProcessingJobService.succeed(db, "not-a-uuid", result={}) is None
        assert ProcessingJobService.fail(
            db,
            "",
            error_code="legacy",
            message="unsupported",
            retryable=False,
        ) is None

    assert not any(sql_verb(statement) in _DML | {"select"} for statement, _parameters in captured)
    assert stored_row(db, job.id) == before

    with capture_sql(engine) as missing_sql:
        assert ProcessingJobService.get(db, missing) is None
        assert ProcessingJobService.heartbeat(db, missing, "legacy-worker") is False
    assert any(sql_verb(statement) == "select" for statement, _parameters in missing_sql)
    assert not any(sql_verb(statement) in _DML for statement, _parameters in missing_sql)
    assert stored_row(db, job.id) == before
    assert_only_queue_tables(engine)


def test_claim_and_requeue_follow_persisted_kind_not_stale_identity(world):
    engine, db, user = world
    queued = add_job(
        db,
        user,
        kind="report_generation",
        status="queued",
        claim_epoch=3,
        idempotency_key="stale-claim",
    )
    running = _running_report(db, user)
    running.lease_expires_at = utcnow() - timedelta(minutes=5)
    db.commit()
    diverge_persisted(db, queued, {ProcessingJob.kind: "evaluation_apply"})
    diverge_persisted(db, running, {ProcessingJob.kind: "evaluation_apply"})
    assert queued.kind == "report_generation"
    assert running.kind == "report_generation"
    before_queued = stored_row(db, queued.id)
    before_running = stored_row(db, running.id)
    assert before_queued["kind"] == "evaluation_apply"
    assert before_running["kind"] == "evaluation_apply"
    assert before_running["status"] == "running"

    with spy_row_locks() as locks:
        assert ProcessingJobService.claim_next(db, "legacy-worker") is None
        assert ProcessingJobService.requeue_expired(db) == 0

    assert len(locks) == 2
    for query, kwargs in locks:
        assert_kind_locked_query(query, kwargs)
    assert stored_row(db, queued.id) == before_queued
    assert stored_row(db, running.id) == before_running
    assert_only_queue_tables(engine)


def _record_worker_side_effects(monkeypatch, db, *, calls):
    factory = _SessionFactory(db)
    constructed = []

    class _RecordingThread:
        def __init__(self, *args, **kwargs) -> None:
            constructed.append(kwargs.get("name"))

        def start(self) -> None:
            calls.append("thread-start")

        def join(self, timeout=None) -> None:
            return None

    class _Heartbeat:
        def __init__(self, job_id, worker_id) -> None:
            calls.append(("heartbeat-init", job_id, worker_id))

        def start(self) -> None:
            calls.append("heartbeat-start")

        def stop(self) -> None:
            calls.append("heartbeat-stop")

    def record(name):
        def _recorded(*_args, **_kwargs):
            calls.append(name)
            raise AssertionError(name)

        return _recorded

    def notify(coro) -> None:
        calls.append(getattr(getattr(coro, "cr_code", None), "co_name", "notify"))
        coro.close()

    monkeypatch.setattr(worker_module, "SessionLocal", factory)
    monkeypatch.setattr(worker_module.threading, "Thread", _RecordingThread)
    monkeypatch.setattr(worker_module, "JobLeaseHeartbeat", _Heartbeat)
    monkeypatch.setattr(worker_module, "_execute_upload", record("upload"))
    monkeypatch.setattr(worker_module, "_execute_report", record("report"))
    monkeypatch.setattr(worker_module, "_execute_story_report", record("story"))
    monkeypatch.setattr(worker_module, "_notify", notify)
    monkeypatch.setattr(worker_module, "cleanup_job_files", record("cleanup"))
    return factory, constructed


@pytest.mark.parametrize(
    ("column", "value"),
    [
        (ProcessingJob.kind, "evaluation_apply"),
        (ProcessingJob.status, "queued"),
    ],
)
def test_process_job_once_sees_persisted_kind_and_status(world, monkeypatch, column, value):
    engine, db, user = world
    job = _running_report(db, user)
    diverge_persisted(db, job, {column: value})
    assert job.kind == "report_generation"
    assert job.status == "running"
    before = stored_row(db, job.id)
    calls = []
    factory, constructed = _record_worker_side_effects(monkeypatch, db, calls=calls)

    assert worker_module.process_job_once(str(job.id), "legacy-worker") is None

    assert stored_row(db, job.id) == before
    assert calls == []
    assert constructed == []
    assert factory.opens == 1
    assert_only_queue_tables(engine)


def test_process_job_once_dispatches_persisted_legacy_kind(world, monkeypatch):
    _engine, db, user = world
    job = add_job(
        db,
        user,
        kind="evaluation_apply",
        status="running",
        worker_id="worker-test",
        attempt_count=1,
        claim_epoch=0,
        request_json={"filename": "report.xlsx", "marker": "reverse-worker"},
        input_path="jobs/report.xlsx",
        idempotency_key="reverse-worker",
    )
    diverge_persisted(db, job, {ProcessingJob.kind: "report_generation"})
    assert job.kind == "evaluation_apply"
    assert stored_row(db, job.id)["kind"] == "report_generation"
    calls = []
    factory = _SessionFactory(db)

    class _Heartbeat:
        def __init__(self, job_id, worker_id) -> None:
            self.job_id = job_id
            self.worker_id = worker_id

        def start(self) -> None:
            calls.append(("heartbeat", self.job_id))

        def stop(self) -> None:
            calls.append(("heartbeat-stop", self.job_id))

    def execute(job_id, payload):
        calls.append("report")
        assert job_id == str(job.id)
        assert payload["filename"] == "report.xlsx"
        assert payload["input_path"] == "jobs/report.xlsx"
        return {"id": "report-1"}, "report-1", "report"

    def notify(coro) -> None:
        calls.append(coro.cr_code.co_name)
        coro.close()

    def rejected(name):
        def _rejected(*_args, **_kwargs):
            calls.append(name)
            raise AssertionError(name)

        return _rejected

    monkeypatch.setattr(worker_module, "SessionLocal", factory)
    monkeypatch.setattr(worker_module, "JobLeaseHeartbeat", _Heartbeat)
    monkeypatch.setattr(worker_module, "_execute_upload", rejected("upload"))
    monkeypatch.setattr(worker_module, "_execute_report", execute)
    monkeypatch.setattr(worker_module, "_execute_story_report", rejected("story"))
    monkeypatch.setattr(worker_module, "_notify", notify)
    monkeypatch.setattr(worker_module, "cleanup_job_files", rejected("cleanup"))

    worker_module.process_job_once(str(job.id), "worker-test")
    after = stored_row(db, job.id)
    assert after["kind"] == "report_generation"
    assert after["status"] == "succeeded"
    assert after["progress"] == 100
    assert after["result_type"] == "report"
    assert after["result_id"] == "report-1"
    assert after["claim_epoch"] == 0
    assert after["worker_id"] is None
    assert calls == [
        ("heartbeat", str(job.id)),
        "report",
        "notify_job_updated",
        ("heartbeat-stop", str(job.id)),
    ]
    assert factory.opens == 2
    assert_only_queue_tables(_engine)
