"""SQLite characterization for the dormant evaluation lease coordinator.

The coordinator is not registered with a worker, a setting, or a route.
These tests reuse the anonymous bounded-apply fixture. They do not open
PostgreSQL, Redis, or a private workbook, and they do not change the known
Marketing 131-versus-68 expectation.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import logging
import os
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

if (
    os.environ.get("APP_ENV") != "test"
    or os.environ.get("DATABASE_URL") != "sqlite:///:memory:"
    or os.environ.get("REDIS_URL", "")
):
    raise RuntimeError("Anonymous environment required before imports")

import pytest
from sqlalchemy import event

from models.models import (
    CacheInvalidationOutbox,
    EvaluationApplyControl,
    EvaluationApplyStageRow,
    EvaluationRevision,
    KPIValue,
    PerformanceRecord,
    ProcessingJob,
    Team,
    TeamConfigurationVersion,
    User,
)
from services.evaluation.access import TargetConflict
from services.evaluation.apply_job_schema import STATUS_PAYLOAD_LIMIT
import services.evaluation.bounded_apply as bounded_apply_module
from services.evaluation.lease_coordinator import (
    EvaluationLeaseCoordinator,
    LeaseCoordinatorError,
)
from services.evaluation.resolver import score_basis
from services.evaluation.workflow import EvaluationConflict, EvaluationError, EvaluationWorkflow
from services.processing_job_service import JOB_KINDS, ProcessingJobService, _legacy_kind_clause


def _load_characterization():
    path = Path(__file__).with_name("test_evaluation_bounded_apply.py")
    name = "bounded_apply_sqlite_characterization"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_CHARACTER = _load_characterization()
db = _CHARACTER.db

BACKEND = Path(__file__).resolve().parents[1]
START = datetime(2026, 7, 3, 9, 0, tzinfo=timezone.utc)
CLOSED_NAMES = {
    "Marketing",
    "Pharmacy",
    "CSR",
    "Pre-Approvals IP Final Dubai",
    "Pre-Approvals IP Final SHJAJM",
}
STATUS_KEYS = {
    "enabled",
    "outcome",
    "job_id",
    "state",
    "job_status",
    "claim_epoch",
    "staged_count",
    "promoted_count",
    "stage_cursor",
    "revision_id",
    "progress",
    "attempt_count",
    "safe_reason",
}
HEADER_MARKERS = ("Ada Sentinel", "Ben Sentinel", "August Sentinel", "actor_snapshot", "kpi_key")


class _Boom:
    """Any use, including bool(), is a test failure."""

    def __call__(self, *args, **kwargs):
        raise AssertionError("call")

    def __getattr__(self, name):
        raise AssertionError(name)

    def __bool__(self):
        raise AssertionError("bool")


class _Clock:
    def __init__(self, moment):
        self.moment = moment
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.moment


def _code(caught) -> str:
    data = getattr(caught.value, "data", {}) or {}
    return data.get("code") or getattr(caught.value, "code", None)


@contextmanager
def _sql(session):
    statements = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    bind = session.get_bind()
    event.listen(bind, "before_cursor_execute", capture)
    try:
        yield statements
    finally:
        event.remove(bind, "before_cursor_execute", capture)


def _coordinator(session, clock):
    return EvaluationLeaseCoordinator(session, clock=clock)


def _job(session, job_id):
    return session.query(ProcessingJob).filter(ProcessingJob.id == uuid.UUID(str(job_id))).one()


def _control(session, job_id):
    return session.query(EvaluationApplyControl).filter(EvaluationApplyControl.job_id == uuid.UUID(str(job_id))).one()


def _aware(value):
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _scores(session):
    return sorted((str(row.score), row.grade, row.status) for row in session.query(PerformanceRecord).all())


def _token(job_id, worker="worker-a", epoch=0, **extra):
    body = {"job_id": str(job_id), "worker_id": worker, "claim_epoch": epoch}
    body.update(extra)
    return body


def _quiet(session, job_id):
    job = _job(session, job_id)
    control = _control(session, job_id)
    return {
        "status": job.status,
        "state": control.state,
        "epoch": int(control.claim_epoch),
        "attempt": int(job.attempt_count or 0),
        "worker": job.worker_id,
        "lease": None if job.lease_expires_at is None else _aware(job.lease_expires_at),
        "progress": int(job.progress or 0),
        "rows": session.query(EvaluationApplyStageRow).count(),
        "revisions": session.query(EvaluationRevision).count(),
        "outbox": session.query(CacheInvalidationOutbox).count(),
        "scores": _scores(session),
    }


def _assert_status_document(document):
    assert set(document) == STATUS_KEYS
    encoded = json.dumps(document, sort_keys=True)
    assert len(encoded) <= STATUS_PAYLOAD_LIMIT
    for marker in HEADER_MARKERS:
        assert marker not in encoded
    assert document["enabled"] is True
    assert document["outcome"] == "status"


def _prepared(session, month, people):
    world = _CHARACTER._World(session)
    prepared = _CHARACTER._prepared_ratio(world, "Coding", month, people)
    return world, prepared


def _reload(world):
    """Coordinator commits expunge every object the world still holds."""

    world.teams = {
        name: world.db.query(Team).filter(Team.id == team_id).one()
        for name, team_id in world.team_ids.items()
    }
    world.admin = world.db.query(User).filter(User.id == world.admin_id).one()


def test_disabled_operations_do_not_touch_a_session_or_clock():
    coordinator = EvaluationLeaseCoordinator(_Boom(), clock=_Boom())
    disabled = {"enabled": False, "outcome": "disabled"}
    assert coordinator.enqueue(_Boom(), _Boom(), True, 1.5) == disabled
    assert coordinator.start(_Boom(), _Boom(), True, lease_seconds=True) == disabled
    assert coordinator.heartbeat(_Boom(), _Boom(), lease_seconds=1.5) == disabled
    assert coordinator.stage_page(_Boom(), _Boom(), lease_seconds=True, page_size=True) == disabled
    assert coordinator.promote(_Boom(), _Boom()) == disabled
    assert coordinator.acknowledge(_Boom(), _Boom()) == disabled
    assert coordinator.recover(_Boom(), _Boom(), expected_epoch=True) == disabled
    assert coordinator.status(_Boom(), _Boom()) == disabled
    assert coordinator.cancel(_Boom(), _Boom()) == disabled
    assert coordinator.retry(_Boom(), _Boom()) == disabled
    for flag in (False, 0, 1, "true", _Boom()):
        assert coordinator.enqueue(_Boom(), _Boom(), 2026, 7, enabled=flag) == disabled


def test_invalid_arguments_raise_before_sql_or_the_clock(db):
    clock = _Clock(datetime(2026, 7, 3, 9, 0))
    coordinator = _coordinator(db, clock)
    job_id = uuid.uuid4()
    token = _token(job_id)
    with _sql(db) as statements:
        with pytest.raises(LeaseCoordinatorError) as lease:
            coordinator.start({"user_id": str(uuid.uuid4())}, job_id, "worker-a", lease_seconds=True, enabled=True)
        assert _code(lease) == "invalid_lease_seconds"
        with pytest.raises(LeaseCoordinatorError) as floated:
            coordinator.start({"user_id": str(uuid.uuid4())}, job_id, "worker-a", lease_seconds=30.0, enabled=True)
        assert _code(floated) == "invalid_lease_seconds"
        with pytest.raises(LeaseCoordinatorError) as worker:
            coordinator.start({"user_id": str(uuid.uuid4())}, job_id, "worker a", lease_seconds=30, enabled=True)
        assert _code(worker) == "invalid_worker_id"
        with pytest.raises(LeaseCoordinatorError) as epoch:
            coordinator.heartbeat({"user_id": str(uuid.uuid4())}, _token(job_id, epoch=True), lease_seconds=30, enabled=True)
        assert _code(epoch) == "invalid_epoch"
        with pytest.raises(LeaseCoordinatorError) as period:
            coordinator.enqueue({"user_id": str(uuid.uuid4())}, uuid.uuid4(), True, 7, enabled=True)
        assert _code(period) == "invalid_period"
        with pytest.raises(EvaluationError) as page:
            coordinator.stage_page({"user_id": str(uuid.uuid4())}, token, lease_seconds=30, page_size=True, enabled=True)
        assert _code(page) == "invalid_page"
        with pytest.raises(LeaseCoordinatorError) as naive:
            coordinator.start({"user_id": str(uuid.uuid4())}, job_id, "worker-a", lease_seconds=30, enabled=True)
        assert _code(naive) == "invalid_clock"
    assert statements == []
    assert clock.calls == 1

    source = (BACKEND / "services" / "evaluation" / "lease_coordinator.py").read_text(encoding="utf-8")
    modules = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    imported = " ".join(modules)
    assert "redis" not in imported and "fastapi" not in imported
    assert "settings" not in imported and "worker" not in imported
    assert " OFFSET" not in source and ".offset(" not in source
    assert "PMS_JOB_LEASE_SECONDS" not in source
    assert "lease_coordinator" not in (BACKEND / "services" / "evaluation" / "__init__.py").read_text(encoding="utf-8")
    worker_source = (BACKEND / "worker.py").read_text(encoding="utf-8")
    dispatch = inspect.cleandoc(worker_source.split("def process_job_once", 1)[1].split("\n    db = SessionLocal()", 1)[0])
    assert "evaluation_apply" not in dispatch
    assert JOB_KINDS == {"pms_upload", "report_generation", "story_report_generation"}


def test_enqueue_is_pending_identity_and_does_not_score(db):
    clock = _Clock(START)
    world, prepared = _prepared(db, 7, [("C-1", "Ada Sentinel", "60"), ("C-2", "Ben Sentinel", "30")])
    coordinator = _coordinator(db, clock)
    scope_id = prepared["scope"]["id"]
    before = _scores(db)
    queued = coordinator.enqueue(world.actor, scope_id, 2026, 7, enabled=True)
    assert queued["outcome"] == "queued"
    assert queued["resumed"] is False
    assert queued["state"] == "pending"
    assert queued["job_status"] == "queued"
    assert queued["claim_epoch"] == 0
    assert queued["expected_count"] == 2
    job = _job(db, queued["job_id"])
    control = _control(db, queued["job_id"])
    assert job.kind == "evaluation_apply"
    assert job.worker_id is None and job.lease_expires_at is None and job.heartbeat_at is None
    assert job.progress == 0 and job.attempt_count == 0 and job.result_json is None
    assert _aware(job.available_at) == START
    assert control.state == "pending" and control.claim_epoch == 0
    assert control.staged_count == 0 and control.promoted_count == 0
    assert control.stage_cursor is None and control.promoted_revision_id is None
    assert control.requested_by_user_id == world.admin_id
    assert db.query(EvaluationApplyStageRow).count() == 0
    assert db.query(EvaluationRevision).count() == 0
    assert db.query(CacheInvalidationOutbox).count() == 0
    assert _scores(db) == before
    request_text = json.dumps(job.request_json, sort_keys=True)
    assert len(request_text) <= STATUS_PAYLOAD_LIMIT
    assert "Ada Sentinel" not in request_text
    snapshot = dict(control.actor_snapshot)
    requester = control.requested_by_user_id

    clock.moment = START + timedelta(hours=1)
    resumed = coordinator.enqueue(world.actor, scope_id, 2026, 7, enabled=True)
    assert resumed["resumed"] is True and resumed["job_id"] == queued["job_id"]
    job = _job(db, queued["job_id"])
    control = _control(db, queued["job_id"])
    assert _aware(job.available_at) == START
    assert control.requested_by_user_id == requester
    assert control.actor_snapshot == snapshot

    forged = dict(world.actor)
    forged["role"] = "Manager"
    assert coordinator.status(forged, queued["job_id"], enabled=True)["job_status"] == "queued"
    other = _CHARACTER._user("Admin", "other-admin")
    db.add(other)
    db.commit()
    other_actor = _CHARACTER._actor(other)
    with pytest.raises(EvaluationConflict) as duplicate:
        coordinator.enqueue(other_actor, scope_id, 2026, 7, enabled=True)
    assert _code(duplicate) == "duplicate_binding"
    assert _control(db, queued["job_id"]).requested_by_user_id == requester
    with pytest.raises(Exception) as denied:
        coordinator.status(other_actor, queued["job_id"], enabled=True)
    assert denied.value.status_code == 403
    assert _job(db, queued["job_id"]).status == "queued"
    visible = db.query(ProcessingJob).filter(_legacy_kind_clause(), ProcessingJob.status == "queued").all()
    assert visible == []
    with pytest.raises(ValueError, match="Unsupported processing job kind"):
        ProcessingJobService.create(
            db,
            kind="evaluation_apply",
            request_json={"scope_id": scope_id},
            requested_by_user_id=None,
            requested_by_name="Admin",
        )
    db.rollback()
    assert db.query(ProcessingJob).count() == 1

    captured = world.service.capture(world.actor, scope_id, 2026, 7)
    assert captured["job_id"] == queued["job_id"] and captured["resumed"] is True
    assert _job(db, queued["job_id"]).status == "queued"
    assert _control(db, queued["job_id"]).state == "pending"


def test_claim_cancel_and_retry_keep_one_epoch_boundary(db):
    clock = _Clock(START)
    world, prepared = _prepared(db, 7, [("C-1", "Ada Sentinel", "60"), ("C-2", "Ben Sentinel", "30")])
    august = _CHARACTER._prepared_ratio(world, "Coding", 8, [("C-8", "August Sentinel", "60")])
    coordinator = _coordinator(db, clock)
    scope_id = prepared["scope"]["id"]
    original_scores = _scores(db)
    queued = coordinator.enqueue(world.actor, scope_id, 2026, 7, enabled=True)
    job_id = queued["job_id"]
    cancelled = coordinator.cancel(world.actor, job_id, enabled=True)
    assert cancelled["state"] == "cancelled" and cancelled["idempotent"] is False
    assert db.query(EvaluationApplyStageRow).count() == 0
    assert _scores(db) == original_scores
    again = coordinator.cancel(world.actor, job_id, enabled=True)
    assert again["idempotent"] is True
    retried = coordinator.retry(world.actor, job_id, enabled=True)
    assert retried["claim_epoch"] == 1 and retried["job_status"] == "queued"
    assert retried["attempt_count"] == 0

    job = _job(db, job_id)
    job.available_at = START + timedelta(days=1)
    db.commit()
    with pytest.raises(LeaseCoordinatorError) as early:
        coordinator.start(world.actor, job_id, "worker-a", lease_seconds=30, enabled=True)
    assert _code(early) == "invalid_state"
    assert _job(db, job_id).status == "queued" and _job(db, job_id).attempt_count == 0
    job = _job(db, job_id)
    job.available_at = START
    job.attempt_count = 3
    db.commit()
    with pytest.raises(LeaseCoordinatorError) as exhausted:
        coordinator.start(world.actor, job_id, "worker-a", lease_seconds=30, enabled=True)
    assert _code(exhausted) == "attempts_exhausted"
    job = _job(db, job_id)
    job.attempt_count = 0
    db.commit()

    token = coordinator.start(world.actor, job_id, "worker-a", lease_seconds=30, enabled=True)
    assert token["outcome"] == "running"
    assert token["worker_id"] == "worker-a" and token["claim_epoch"] == 1
    assert _aware(datetime.fromisoformat(token["lease_expires_at"])) == START + timedelta(seconds=30)
    assert _job(db, job_id).attempt_count == 1
    assert _control(db, job_id).state == "staging"
    with pytest.raises(LeaseCoordinatorError) as held:
        coordinator.start(world.actor, job_id, "worker-b", lease_seconds=30, enabled=True)
    assert _code(held) == "lease_held"
    assert _job(db, job_id).worker_id == "worker-a" and _job(db, job_id).attempt_count == 1

    loaded = _job(db, job_id)
    loaded.worker_id = "forged-in-map"
    clock.moment = START + timedelta(seconds=5)
    beat = coordinator.heartbeat(world.actor, token, lease_seconds=30, enabled=True)
    assert beat["outcome"] == "heartbeat"
    assert _job(db, job_id).worker_id == "worker-a"
    assert _aware(_job(db, job_id).lease_expires_at) == clock.moment + timedelta(seconds=30)
    lease_at = _aware(_job(db, job_id).lease_expires_at)
    updated = db.query(ProcessingJob).filter(ProcessingJob.id == uuid.UUID(str(job_id))).update(
        {ProcessingJob.worker_id: "intruder"},
        synchronize_session=False,
    )
    assert updated == 1
    with pytest.raises(LeaseCoordinatorError) as stale_map:
        coordinator.heartbeat(world.actor, token, lease_seconds=30, enabled=True)
    assert _code(stale_map) == "stale_token"
    assert _job(db, job_id).worker_id == "worker-a"
    assert _aware(_job(db, job_id).lease_expires_at) == lease_at

    with pytest.raises(LeaseCoordinatorError) as wrong_worker:
        coordinator.heartbeat(world.actor, _token(job_id, "worker-b", 1), lease_seconds=30, enabled=True)
    assert _code(wrong_worker) == "stale_token"
    with pytest.raises(LeaseCoordinatorError) as wrong_epoch:
        coordinator.stage_page(world.actor, _token(job_id, "worker-a", 0), lease_seconds=30, page_size=1, enabled=True)
    assert _code(wrong_epoch) == "stale_epoch"
    assert db.query(EvaluationApplyStageRow).count() == 0

    clock.moment = START + timedelta(seconds=5) + timedelta(seconds=30)
    with pytest.raises(LeaseCoordinatorError) as expired_page:
        coordinator.stage_page(world.actor, token, lease_seconds=30, page_size=1, enabled=True)
    assert _code(expired_page) == "lease_expired"
    with pytest.raises(LeaseCoordinatorError) as expired_promote:
        coordinator.promote(world.actor, token, enabled=True)
    assert _code(expired_promote) == "lease_expired"
    assert db.query(EvaluationRevision).count() == 0
    assert _scores(db) == original_scores
    opened = coordinator.retry(world.actor, job_id, enabled=True)
    assert opened["claim_epoch"] == 2 and opened["attempt_count"] == 1
    assert _job(db, job_id).status == "queued" and _job(db, job_id).worker_id is None
    assert _control(db, job_id).state == "pending" and _control(db, job_id).staged_count == 0
    with pytest.raises(LeaseCoordinatorError):
        coordinator.heartbeat(world.actor, token, lease_seconds=30, enabled=True)
    assert _quiet(db, job_id)["rows"] == 0

    clock.moment = START + timedelta(hours=2)
    token = coordinator.start(world.actor, job_id, "worker-a", lease_seconds=30, enabled=True)
    assert token["claim_epoch"] == 2 and _job(db, job_id).attempt_count == 2
    first = coordinator.stage_page(world.actor, token, lease_seconds=30, page_size=1, enabled=True)
    assert first["inserted_count"] == 1 and first["staged_count"] == 1 and first["complete"] is False
    assert first["progress"] == 49 and first["progress"] < 100
    second = coordinator.stage_page(world.actor, token, lease_seconds=30, page_size=1, enabled=True)
    assert second["staged_count"] == 2 and second["complete"] is True and second["progress"] == 99
    assert _job(db, job_id).progress == 99
    stopped = coordinator.cancel(world.actor, job_id, enabled=True)
    assert stopped["state"] == "cancelled"
    assert db.query(EvaluationApplyStageRow).filter(EvaluationApplyStageRow.claim_epoch == 2).count() == 2
    assert _scores(db) == original_scores
    assert _job(db, job_id).worker_id is None and _job(db, job_id).progress == 99
    document = coordinator.status(world.actor, job_id, enabled=True)
    _assert_status_document(document)
    assert document["safe_reason"] == "cancelled"
    assert document["staged_count"] == 2 and document["revision_id"] is None
    with pytest.raises(LeaseCoordinatorError) as dead:
        coordinator.stage_page(world.actor, token, lease_seconds=30, page_size=1, enabled=True)
    assert _code(dead) in {"stale_token", "invalid_state", "lease_expired", "stale_epoch"}
    assert db.query(EvaluationApplyStageRow).count() == 2

    clock.moment = START + timedelta(hours=3)
    retried = coordinator.retry(world.actor, job_id, enabled=True)
    assert retried["claim_epoch"] == 3 and retried["attempt_count"] == 2
    assert _control(db, job_id).stage_cursor is None and _control(db, job_id).staged_count == 0
    assert db.query(EvaluationApplyStageRow).filter(EvaluationApplyStageRow.claim_epoch == 2).count() == 2
    assert _job(db, job_id).progress == 0 and _job(db, job_id).worker_id is None
    with pytest.raises(LeaseCoordinatorError) as old_promote:
        coordinator.promote(world.actor, token, enabled=True)
    assert _code(old_promote) == "stale_epoch"
    assert db.query(EvaluationRevision).count() == 0

    token = coordinator.start(world.actor, job_id, "worker-a", lease_seconds=30, enabled=True)
    assert _job(db, job_id).attempt_count == 3
    control = _control(db, job_id)
    control.state = "promoting"
    db.commit()
    with pytest.raises(LeaseCoordinatorError) as promoting:
        coordinator.cancel(world.actor, job_id, enabled=True)
    assert _code(promoting) == "invalid_state"
    assert _control(db, job_id).state == "promoting"
    assert _scores(db) == original_scores
    control = _control(db, job_id)
    control.state = "failed"
    job = _job(db, job_id)
    job.status = "failed"
    db.commit()
    with pytest.raises(LeaseCoordinatorError) as exhausted_retry:
        coordinator.retry(world.actor, job_id, enabled=True)
    assert _code(exhausted_retry) == "attempts_exhausted"
    assert _control(db, job_id).claim_epoch == 3
    assert db.query(EvaluationApplyStageRow).count() == 2

    public = world.service.capture(world.actor, august["scope"]["id"], 2026, 8)
    public_id = public["job_id"]
    assert _job(db, public_id).status == "running" and _job(db, public_id).worker_id is None
    assert _control(db, public_id).state == "staging" and _job(db, public_id).lease_expires_at is None
    before_public = _quiet(db, public_id)
    with pytest.raises(LeaseCoordinatorError) as adopted:
        coordinator.start(world.actor, public_id, "worker-a", lease_seconds=30, enabled=True)
    assert _code(adopted) == "invalid_state"
    with pytest.raises(LeaseCoordinatorError) as adopted_retry:
        coordinator.retry(world.actor, public_id, enabled=True)
    assert _code(adopted_retry) == "invalid_state"
    with pytest.raises(EvaluationConflict) as wrapped:
        coordinator.enqueue(world.actor, august["scope"]["id"], 2026, 8, enabled=True)
    assert _code(wrapped) == "duplicate_binding"
    assert _quiet(db, public_id) == before_public


def test_drift_role_and_closed_scopes_fail_closed(db):
    clock = _Clock(START)
    world = _CHARACTER._World(db, (
        "Coding",
        "Marketing",
        "Pharmacy",
        "CSR",
        "Pre-Approvals IP Final Dubai",
        "Pre-Approvals IP Final SHJAJM",
        "Outbound",
    ))
    names = {item["display_name"] for item in world.catalog["scopes"]}
    assert CLOSED_NAMES <= names
    levels = {item["performance_level"] for item in world.catalog["scopes"]}
    assert {"Managerial", "Corporate"} <= levels
    coordinator = _coordinator(db, clock)
    for item in world.catalog["scopes"]:
        name = item["display_name"]
        position = item["position_name"] or ""
        closed = (
            item["performance_level"] in {"Managerial", "Corporate"}
            or name in CLOSED_NAMES
            or (name == "Coding" and position not in {"", None})
        )
        if not closed:
            continue
        with pytest.raises(EvaluationError) as blocked:
            coordinator.enqueue(world.actor, item["id"], 2026, 7, enabled=True)
        assert _code(blocked) in {"unsupported_calculation", "not_found", "scope_blocked"}
    outbound = world.scope("Outbound")
    for month in (6, 9):
        with pytest.raises(EvaluationError) as refused:
            coordinator.enqueue(world.actor, outbound["id"], 2026, month, enabled=True)
        assert _code(refused) == "unsupported_calculation"
    assert db.query(ProcessingJob).count() == 0

    _reload(world)
    prepared = _CHARACTER._prepared_ratio(world, "Coding", 7, [("C-1", "Ada Sentinel", "60")])
    august = _CHARACTER._prepared_ratio(world, "Coding", 8, [("C-8", "August Sentinel", "60")])
    scope_id = prepared["scope"]["id"]
    queued = coordinator.enqueue(world.actor, scope_id, 2026, 7, enabled=True)
    job_id = queued["job_id"]
    admin = db.query(User).filter(User.id == world.admin_id).one()
    admin.role = "Manager"
    db.commit()
    snapshot = _control(db, job_id).actor_snapshot
    assert snapshot["role"] == "Admin"
    with pytest.raises(Exception) as revoked:
        coordinator.start(world.actor, job_id, "worker-a", lease_seconds=30, enabled=True)
    assert revoked.value.status_code == 403
    assert _job(db, job_id).status == "queued" and _job(db, job_id).attempt_count == 0
    admin = db.query(User).filter(User.id == world.admin_id).one()
    admin.role = "Admin"
    admin.is_active = False
    db.commit()
    with pytest.raises(Exception) as inactive:
        coordinator.status(world.actor, job_id, enabled=True)
    assert inactive.value.status_code == 403
    admin = db.query(User).filter(User.id == world.admin_id).one()
    admin.is_active = True
    db.commit()

    token = coordinator.start(world.actor, job_id, "worker-a", lease_seconds=30, enabled=True)
    moving = (
        db.query(KPIValue)
        .join(KPIValue.performance_record)
        .filter(PerformanceRecord.month == "July")
        .one()
    )
    moving_id = moving.id
    original_actual = moving.actual_value
    moving.actual_value = Decimal("61")
    db.commit()
    with pytest.raises(EvaluationConflict) as changed:
        coordinator.stage_page(world.actor, token, lease_seconds=30, page_size=1, enabled=True)
    assert _code(changed) == "evidence_changed"
    assert db.query(EvaluationApplyStageRow).count() == 0
    moving = db.query(KPIValue).filter(KPIValue.id == moving_id).one()
    moving.actual_value = original_actual
    db.commit()
    page = coordinator.stage_page(world.actor, token, lease_seconds=30, page_size=1, enabled=True)
    assert page["complete"] is True and page["progress"] == 99
    clock.moment = START + timedelta(seconds=30)
    moving = db.query(KPIValue).filter(KPIValue.id == moving_id).one()
    moving.actual_value = Decimal("61")
    db.commit()
    with pytest.raises(EvaluationConflict) as expired_drift:
        coordinator.retry(world.actor, job_id, enabled=True)
    assert _code(expired_drift) == "evidence_changed"
    failed = _job(db, job_id)
    assert failed.status == "failed" and failed.error_code == "lease_expired"
    assert _control(db, job_id).state == "failed" and _control(db, job_id).claim_epoch == 0
    document = coordinator.status(world.actor, job_id, enabled=True)
    _assert_status_document(document)
    assert document["safe_reason"] == "lease_expired"
    moving = db.query(KPIValue).filter(KPIValue.id == moving_id).one()
    moving.actual_value = original_actual
    db.commit()

    original_engine = bounded_apply_module.ENGINE_VERSION
    bounded_apply_module.ENGINE_VERSION = "employee-ratio-cap-v2"
    try:
        with pytest.raises(EvaluationConflict) as engine:
            coordinator.retry(world.actor, job_id, enabled=True)
        assert _code(engine) == "stale_preview"
    finally:
        bounded_apply_module.ENGINE_VERSION = original_engine
    assert _control(db, job_id).claim_epoch == 0 and _control(db, job_id).engine_version == original_engine

    original_rules = bounded_apply_module._rules_checksum
    bounded_apply_module._rules_checksum = lambda _snapshot: "ab" * 32
    try:
        with pytest.raises(EvaluationConflict) as rules:
            coordinator.retry(world.actor, job_id, enabled=True)
        assert _code(rules) == "stale_preview"
    finally:
        bounded_apply_module._rules_checksum = original_rules
    assert _control(db, job_id).state == "failed"

    version = db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.status == "approved", TeamConfigurationVersion.effective_from_month == 7).one()
    scope_row_id = version.id
    extra = EvaluationRevision(
        team_id=version.team_id,
        performance_level="Employee",
        position_name="",
        year=2026,
        month=7,
        version_id=scope_row_id,
        status="active",
        prior_snapshot={"records": [], "hash": "ab" * 32},
        applied_snapshot={"records": [], "hash": "ab" * 32},
        created_by_user_id=world.admin_id,
        actor_snapshot={"state": "known", "user_id": str(world.admin_id)},
    )
    db.add(extra)
    lineage_error = None
    try:
        db.flush()
        db.commit()
        inserted = True
    except Exception as exc:
        db.rollback()
        inserted = False
        lineage_error = exc
    assert inserted, lineage_error
    with pytest.raises(EvaluationConflict) as lineage:
        coordinator.retry(world.actor, job_id, enabled=True)
    assert _code(lineage) == "lineage_changed"
    assert _control(db, job_id).claim_epoch == 0
    assert db.query(EvaluationRevision).count() == 1
    assert db.query(CacheInvalidationOutbox).count() == 0

    _reload(world)
    august_job = coordinator.enqueue(world.actor, august["scope"]["id"], 2026, 8, enabled=True)
    coordinator.cancel(world.actor, august_job["job_id"], enabled=True)
    approved = db.query(TeamConfigurationVersion).filter(
        TeamConfigurationVersion.status == "approved",
        TeamConfigurationVersion.effective_from_month == 8,
    ).one()
    captured_version = _control(db, august_job["job_id"]).version_id
    revised = world.workflow.revise(world.actor, str(approved.id))
    _CHARACTER._approve(world.workflow, world.actor, revised["id"])
    with pytest.raises(EvaluationConflict) as approval:
        coordinator.retry(world.actor, august_job["job_id"], enabled=True)
    assert _code(approval) == "stale_preview"
    assert _control(db, august_job["job_id"]).version_id == captured_version
    assert _control(db, august_job["job_id"]).state == "cancelled"
    assert db.query(EvaluationApplyControl).filter(EvaluationApplyControl.job_id == uuid.UUID(august_job["job_id"])).count() == 1

    admin = db.query(User).filter(User.id == world.admin_id).one()
    removed = False
    try:
        db.delete(admin)
        db.commit()
        removed = True
    except Exception:
        db.rollback()
    if removed:
        with pytest.raises(Exception) as deleted:
            coordinator.status(world.actor, job_id, enabled=True)
        assert deleted.value.status_code == 403
    else:
        assert db.query(User).filter(User.id == world.admin_id).count() == 1
    assert _scores(db) == [("70.00", "D", "Below"), ("70.00", "D", "Below")]


def test_promoted_recovery_acks_without_a_second_revision(db, caplog):
    clock = _Clock(START)
    world, prepared = _prepared(db, 7, [("C-1", "Ada Sentinel", "60")])
    coordinator = _coordinator(db, clock)
    queued = coordinator.enqueue(world.actor, prepared["scope"]["id"], 2026, 7, enabled=True)
    job_id = queued["job_id"]
    token = coordinator.start(world.actor, job_id, "worker-a", lease_seconds=30, enabled=True)
    page = coordinator.stage_page(world.actor, token, lease_seconds=30, page_size=100, enabled=True)
    assert page["complete"] is True and page["progress"] == 99
    caplog.set_level(logging.WARNING)
    original_commit = db.commit

    def _fail_commit():
        raise RuntimeError("UPDATE secret syntax near Ada Sentinel")

    db.commit = _fail_commit
    try:
        with pytest.raises(LeaseCoordinatorError) as persisted:
            coordinator.heartbeat(world.actor, token, lease_seconds=30, enabled=True)
        assert _code(persisted) == "persistence_failed"
        assert persisted.value.__cause__ is None
    finally:
        db.commit = original_commit
    assert _job(db, job_id).status == "running"
    assert "Ada Sentinel" not in " ".join(record.getMessage() for record in caplog.records)
    assert "syntax" not in " ".join(record.getMessage() for record in caplog.records)
    promoted = coordinator.promote(world.actor, token, enabled=True)
    assert promoted["acknowledged"] is False and promoted["idempotent"] is False
    assert promoted["state"] == "promoted"
    job = _job(db, job_id)
    assert job.status == "running" and job.progress == 99 and job.worker_id == "worker-a"
    record = db.query(PerformanceRecord).one()
    assert record.score == Decimal("100.00") and record.grade == "A" and record.status == "Exceeds"
    assert db.query(EvaluationRevision).count() == 1
    assert db.query(CacheInvalidationOutbox).count() == 1
    repeated = coordinator.promote(world.actor, token, enabled=True)
    assert repeated["idempotent"] is True and repeated["revision_id"] == promoted["revision_id"]
    assert db.query(EvaluationRevision).count() == 1
    assert _job(db, job_id).status == "running"

    db.info["bounded_apply_fault"] = "before_commit"
    with pytest.raises(EvaluationConflict) as fault:
        coordinator.acknowledge(world.actor, token, enabled=True)
    assert _code(fault) == "fault_injected"
    assert _job(db, job_id).status == "running" and _job(db, job_id).progress == 99
    assert db.query(EvaluationRevision).count() == 1
    assert db.query(CacheInvalidationOutbox).one().published_at is None
    db.info.pop("bounded_apply_fault", None)

    clock.moment = START + timedelta(seconds=30)
    stale = coordinator.recover(world.actor, job_id, expected_epoch=4, enabled=True)
    assert stale["mutated"] is False and stale["revision_id"] == promoted["revision_id"]
    assert _job(db, job_id).status == "running"
    with pytest.raises(LeaseCoordinatorError) as expired_ack:
        coordinator.acknowledge(world.actor, token, enabled=True)
    assert _code(expired_ack) == "lease_expired"
    assert _job(db, job_id).status == "running" and _job(db, job_id).progress == 99

    db.info["bounded_apply_fault"] = "before_commit"
    with pytest.raises(EvaluationConflict):
        coordinator.recover(world.actor, job_id, expected_epoch=0, enabled=True)
    assert _job(db, job_id).status == "running"
    db.info.pop("bounded_apply_fault", None)
    recovered = coordinator.recover(world.actor, job_id, expected_epoch=0, enabled=True)
    assert recovered["outcome"] == "recovered" and recovered["mutated"] is True
    assert _job(db, job_id).status == "succeeded" and _job(db, job_id).progress == 100
    assert _job(db, job_id).worker_id is None and _job(db, job_id).lease_expires_at is None
    result = _job(db, job_id).result_json
    assert result["outcome"] == "promoted" and result["revision_id"] == promoted["revision_id"]
    assert len(json.dumps(result, sort_keys=True)) <= STATUS_PAYLOAD_LIMIT
    assert "Ada Sentinel" not in json.dumps(result)
    acked = coordinator.acknowledge(world.actor, token, enabled=True)
    assert acked["idempotent"] is True and acked["progress"] == 100
    observed = coordinator.recover(world.actor, job_id, expected_epoch=0, enabled=True)
    assert observed["mutated"] is False and observed["idempotent"] is True
    assert db.query(EvaluationRevision).count() == 1
    assert db.query(CacheInvalidationOutbox).count() == 1
    with pytest.raises(LeaseCoordinatorError) as terminal:
        coordinator.cancel(world.actor, job_id, enabled=True)
    assert _code(terminal) == "invalid_state"
    with pytest.raises(LeaseCoordinatorError):
        coordinator.heartbeat(world.actor, _token(job_id, "worker-b", 0), lease_seconds=30, enabled=True)
    assert _job(db, job_id).status == "succeeded" and _job(db, job_id).progress == 100


def test_outbound_coding_and_submission_keep_the_canonical_ratios(db, monkeypatch):
    def _refuse_apply(self, *args, **kwargs):
        raise AssertionError("coordinator reused public synchronous apply")

    monkeypatch.setattr(EvaluationWorkflow, "apply", _refuse_apply)
    clock = _Clock(START)
    world = _CHARACTER._World(db, ("Coding", "Submission", "Outbound"))
    protected = world.protect(world.teams["Coding"])
    coordinator = _coordinator(db, clock)

    coding = _CHARACTER._prepared_ratio(world, "Coding", 7, [("C-1", "Ada Sentinel", "60")])
    version = db.query(TeamConfigurationVersion).filter(
        TeamConfigurationVersion.status == "approved",
        TeamConfigurationVersion.effective_from_month == 7,
        TeamConfigurationVersion.team_id == world.team_ids["Coding"],
    ).one()
    with pytest.raises(TargetConflict) as conflict:
        score_basis(version, [{"kpi_key": coding["key"], "actual": 60, "workbook_target": 40}])
    assert conflict.value.data["code"] == "target_conflict"
    _finish(coordinator, world, coding["scope"]["id"], 7)
    coding_row = db.query(PerformanceRecord).filter(PerformanceRecord.team_id == world.team_ids["Coding"]).one()
    assert coding_row.score == Decimal("100.00")
    assert coding_row.grade == "A" and coding_row.status == "Exceeds"
    _reload(world)
    assert world.workflow.protected_texts() == protected

    submission = _CHARACTER._prepared_ratio(world, "Submission", 7, [("S-1", "Sam Sentinel", "60")])
    _finish(coordinator, world, submission["scope"]["id"], 7)
    submission_row = db.query(PerformanceRecord).filter(PerformanceRecord.team_id == world.team_ids["Submission"]).one()
    assert submission_row.score == Decimal("100.00")
    assert submission_row.grade == "A" and submission_row.status == "Exceeds"

    _reload(world)
    outbound = world.scope("Outbound")
    july = world.workflow.open_draft(world.actor, outbound["id"], 2026, 7)
    july_weights = {line["kpi_key"]: line["weight"] for line in july["lines"] if float(line["weight"]) > 0}
    assert july_weights == {
        "Attendance": pytest.approx(0.70),
        "Booking": pytest.approx(0.10),
        "Quality": pytest.approx(0.10),
        "Other": pytest.approx(0.10),
    }
    assert "Productivity" not in july_weights
    july_record = _CHARACTER._outbound_record(world, july, "July", {
        "Attendance": "0.325",
        "Booking": "0.3",
        "Quality": "0.95",
        "Other": "0.75",
    })
    july_id = (july_record.id, july_record.year)
    _CHARACTER._approve(world.workflow, world.actor, july["id"])
    _finish(coordinator, world, outbound["id"], 7)
    july_record = _CHARACTER._performance(db, july_id[0], july_id[1])
    attendance = next(value for value in july_record.kpi_values if value.kpi_key == "Attendance")
    assert july_record.score == Decimal("65.00")
    assert july_record.grade == "D" and july_record.status == "Below"
    assert attendance.actual_value == Decimal("0.3250")
    assert attendance.target_value == Decimal("0.6500")
    assert attendance.achievement_ratio == Decimal("0.5000")
    assert attendance.weight_applied == Decimal("0.7000")
    assert attendance.contribution == Decimal("0.3500")

    _reload(world)
    august = world.workflow.open_draft(world.actor, outbound["id"], 2026, 8)
    august_weights = {line["kpi_key"]: line["weight"] for line in august["lines"] if float(line["weight"]) > 0}
    assert august_weights["Attendance"] == pytest.approx(0.60)
    assert august_weights["Productivity"] == pytest.approx(0.10)
    august_record = _CHARACTER._outbound_record(world, august, "August", {
        "Attendance": "0.65",
        "Booking": "0.3",
        "Quality": "0.95",
        "Other": "0.75",
        "Productivity": "0.8",
    })
    august_id = (august_record.id, august_record.year)
    _CHARACTER._approve(world.workflow, world.actor, august["id"])
    _finish(coordinator, world, outbound["id"], 8)
    august_record = _CHARACTER._performance(db, august_id[0], august_id[1])
    productivity = next(value for value in august_record.kpi_values if value.kpi_key == "Productivity")
    august_attendance = next(value for value in august_record.kpi_values if value.kpi_key == "Attendance")
    assert august_record.score == Decimal("100.00")
    assert august_record.grade == "A" and august_record.status == "Exceeds"
    assert august_attendance.weight_applied == Decimal("0.6000")
    assert august_attendance.target_value == Decimal("0.6500")
    assert productivity.weight_applied == Decimal("0.1000")
    assert productivity.target_value == Decimal("0.8000")
    assert productivity.actual_value == Decimal("0.8000")
    july_record = _CHARACTER._performance(db, july_id[0], july_id[1])
    assert july_record.score == Decimal("65.00")
    assert db.query(CacheInvalidationOutbox).filter(CacheInvalidationOutbox.published_at.isnot(None)).count() == 0
    assert world.workflow.protected_texts() == protected


def _shift_after_lock(coordinator, clock, moment):
    original = coordinator._locked

    def delayed(*args, **kwargs):
        result = original(*args, **kwargs)
        clock.moment = moment
        return result

    coordinator._locked = delayed


@pytest.mark.parametrize("operation", ["heartbeat", "stage_page", "promote", "acknowledge"])
def test_lease_expired_while_waiting_for_headers(db, operation):
    clock = _Clock(START)
    world, prepared = _prepared(db, 7, [("C-1", "Anonymous", "60")])
    coordinator = _coordinator(db, clock)
    queued = coordinator.enqueue(world.actor, prepared["scope"]["id"], 2026, 7, enabled=True)
    token = coordinator.start(world.actor, queued["job_id"], "reviewer", lease_seconds=30, enabled=True)
    if operation in {"promote", "acknowledge"}:
        coordinator.stage_page(world.actor, token, page_size=100, lease_seconds=30, enabled=True)
    if operation == "acknowledge":
        coordinator.promote(world.actor, token, enabled=True)
    before = _quiet(db, queued["job_id"])
    _shift_after_lock(coordinator, clock, START + timedelta(seconds=31))
    kwargs = {"enabled": True}
    if operation in {"heartbeat", "stage_page"}:
        kwargs["lease_seconds"] = 30
    with pytest.raises(LeaseCoordinatorError) as expired:
        getattr(coordinator, operation)(world.actor, token, **kwargs)
    assert _code(expired) == "lease_expired"
    assert _quiet(db, queued["job_id"]) == before


def test_start_and_retry_read_the_clock_after_each_fence(db):
    clock = _Clock(START)
    world, prepared = _prepared(db, 7, [("C-1", "Anonymous", "60")])
    coordinator = _coordinator(db, clock)
    real_locked = coordinator._locked
    queued = coordinator.enqueue(world.actor, prepared["scope"]["id"], 2026, 7, enabled=True)
    job_id = queued["job_id"]
    due = START + timedelta(seconds=10)
    job = _job(db, job_id)
    job.available_at = due
    db.commit()

    clock.moment = START
    _shift_after_lock(coordinator, clock, due)
    token = coordinator.start(world.actor, job_id, "worker-a", lease_seconds=30, enabled=True)
    started = _job(db, job_id)
    assert _aware(started.started_at) == due
    assert _aware(started.heartbeat_at) == due
    assert _aware(datetime.fromisoformat(token["lease_expires_at"])) == due + timedelta(seconds=30)
    assert started.attempt_count == 1

    coordinator._locked = real_locked
    clock.moment = due
    later = START + timedelta(seconds=15)
    _shift_after_lock(coordinator, clock, later)
    coordinator.heartbeat(world.actor, token, lease_seconds=30, enabled=True)
    assert _aware(_job(db, job_id).lease_expires_at) == later + timedelta(seconds=30)
    assert _aware(_job(db, job_id).heartbeat_at) == later

    coordinator._locked = real_locked
    clock.moment = later
    expired_at = later + timedelta(seconds=31)
    _shift_after_lock(coordinator, clock, expired_at)
    held = _quiet(db, job_id)
    with pytest.raises(LeaseCoordinatorError) as blocked:
        coordinator.start(world.actor, job_id, "worker-b", lease_seconds=30, enabled=True)
    assert _code(blocked) == "invalid_state"
    assert _quiet(db, job_id) == held

    coordinator._locked = real_locked
    clock.moment = later
    seen = {"calls": 0}

    def two_fences(*args, **kwargs):
        result = real_locked(*args, **kwargs)
        seen["calls"] += 1
        if seen["calls"] == 1:
            clock.moment = expired_at
            return result
        failed = _job(db, job_id)
        seen["error"] = failed.error_code
        seen["finished"] = _aware(failed.finished_at)
        clock.moment = START + timedelta(seconds=80)
        return result

    coordinator._locked = two_fences
    retried = coordinator.retry(world.actor, job_id, enabled=True)
    reopened = _job(db, job_id)
    assert seen["calls"] == 2
    assert seen["error"] == "lease_expired"
    assert seen["finished"] == expired_at
    assert retried["claim_epoch"] == 1 and retried["job_status"] == "queued"
    assert retried["attempt_count"] == 1
    assert _aware(reopened.available_at) == START + timedelta(seconds=80)
    assert reopened.worker_id is None and reopened.lease_expires_at is None
    assert reopened.finished_at is None and reopened.error_code is None
    assert _control(db, job_id).claim_epoch == 1


def test_enqueue_and_cancel_timestamps_follow_the_post_fence_clock(db):
    clock = _Clock(START)
    world, prepared = _prepared(db, 7, [("C-1", "Anonymous", "60")])
    coordinator = _coordinator(db, clock)
    scope_id = prepared["scope"]["id"]
    service = bounded_apply_module.BoundedApplyService
    original_capture = service.capture_queued

    def delayed_capture(self, *args, **kwargs):
        body = original_capture(self, *args, **kwargs)
        clock.moment = START + timedelta(seconds=11)
        return body

    service.capture_queued = delayed_capture
    try:
        queued = coordinator.enqueue(world.actor, scope_id, 2026, 7, enabled=True)
    finally:
        service.capture_queued = original_capture
    job_id = queued["job_id"]
    assert _aware(_job(db, job_id).available_at) == START + timedelta(seconds=11)

    clock.moment = START
    _shift_after_lock(coordinator, clock, START + timedelta(seconds=8))
    coordinator.cancel(world.actor, job_id, enabled=True)
    assert _aware(_job(db, job_id).finished_at) == START + timedelta(seconds=8)
    assert _job(db, job_id).error_code == "cancelled"


def test_recover_timestamp_follows_the_post_fence_clock(db):
    clock = _Clock(START)
    world, prepared = _prepared(db, 7, [("C-1", "Anonymous", "60")])
    coordinator = _coordinator(db, clock)
    queued = coordinator.enqueue(world.actor, prepared["scope"]["id"], 2026, 7, enabled=True)
    token = coordinator.start(world.actor, queued["job_id"], "worker-a", lease_seconds=30, enabled=True)
    coordinator.stage_page(world.actor, token, lease_seconds=30, page_size=100, enabled=True)
    revisions = db.query(EvaluationRevision).count()
    outbox = db.query(CacheInvalidationOutbox).count()
    promoted = coordinator.promote(world.actor, token, enabled=True)
    assert promoted["acknowledged"] is False
    assert db.query(EvaluationRevision).count() == revisions + 1
    assert db.query(CacheInvalidationOutbox).count() == outbox + 1
    _shift_after_lock(coordinator, clock, START + timedelta(seconds=90))
    recovered = coordinator.recover(world.actor, queued["job_id"], expected_epoch=0, enabled=True)
    acked = _job(db, queued["job_id"])
    assert recovered["mutated"] is True and recovered["outcome"] == "recovered"
    assert acked.status == "succeeded" and acked.progress == 100
    assert _aware(acked.finished_at) == START + timedelta(seconds=90)
    assert db.query(EvaluationRevision).count() == revisions + 1
    assert db.query(CacheInvalidationOutbox).count() == outbox + 1


def _finish(coordinator, world, scope_id, month):
    queued = coordinator.enqueue(world.actor, scope_id, 2026, month, enabled=True)
    token = coordinator.start(world.actor, queued["job_id"], "worker-a", lease_seconds=30, enabled=True)
    page = coordinator.stage_page(world.actor, token, lease_seconds=30, page_size=100, enabled=True)
    assert page["complete"] is True and page["progress"] < 100
    promoted = coordinator.promote(world.actor, token, enabled=True)
    assert promoted["acknowledged"] is False
    running = world.db.query(ProcessingJob).filter(ProcessingJob.id == uuid.UUID(queued["job_id"])).one()
    assert running.status == "running" and running.progress < 100
    acked = coordinator.acknowledge(world.actor, token, enabled=True)
    assert acked["progress"] == 100 and acked["idempotent"] is False
    return queued["job_id"]
