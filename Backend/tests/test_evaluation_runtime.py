"""SQLite characterization for the opt-in evaluation apply runtime.

The product flag stays false except where a test sets the literal True.
These tests reuse the anonymous bounded-apply fixture, the real bearer
middleware, and the persisted user row. They do not open PostgreSQL, Redis,
Docker, or a private workbook.
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
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

if (
    os.environ.get("APP_ENV") != "test"
    or os.environ.get("DATABASE_URL") != "sqlite:///:memory:"
    or os.environ.get("REDIS_URL", "")
):
    raise RuntimeError("Anonymous environment required before imports")

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.auth_middleware import AuthMiddleware
from api.routers.evaluation_settings import router as evaluation_router
from config import settings
from config.database import get_db
from models.models import (
    AuditLog,
    CacheInvalidationOutbox,
    EvaluationApplyControl,
    EvaluationApplyStageRow,
    EvaluationRevision,
    KPIValue,
    PerformanceRecord,
    ProcessingJob,
    User,
)
from services.auth_service import AuthenticationService
from services.cache_invalidation_service import _fallback_data_version
from services.evaluation.cache_identity import evaluation_cache_identity
from services.evaluation.lease_coordinator import (
    EvaluationLeaseCoordinator,
    LeaseCoordinatorError,
)
from services.evaluation.runtime import EvaluationApplyRuntime, run_enabled_tick
from services.evaluation.workflow import EvaluationWorkflow
from services.processing_job_service import JOB_KINDS, ProcessingJobService


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
PREFIX = "/api/settings/evaluation"
START = datetime(2026, 7, 3, 9, 0, tzinfo=timezone.utc)
AUDIT_KEYS = {
    "action",
    "claim_epoch",
    "control_state",
    "job_status",
    "requested_by_user_id",
}
PEOPLE = ("Ada Sentinel", "Ben Sentinel", "August Sentinel")


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

    def __call__(self):
        return self.moment


class _Client:
    def __init__(self, *, incr_error=None):
        self.calls = []
        self.version = 0
        self.bool_calls = 0
        self.incr_error = incr_error

    def __bool__(self):
        self.bool_calls += 1
        raise AssertionError("client truthiness")

    def incr(self, key):
        self.calls.append(("incr", key))
        if self.incr_error is not None:
            raise self.incr_error
        self.version += 1
        return self.version

    def publish(self, channel, message):
        self.calls.append(("publish", channel, message))
        return 0


class _Log(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class _SessionHandle:
    """Give the worker the real fixture session and ignore its close.

    Membership checks such as ``record in session`` are part of staging.
    A proxy that only forwards ``__getattr__`` is not a session.
    """

    def __init__(self, session):
        self._session = session
        self.calls = 0

        def _keep_open():
            return None

        session.close = _keep_open

    def __call__(self):
        self.calls += 1
        return self._session


@pytest.fixture
def api(db):
    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.include_router(evaluation_router, prefix=PREFIX)

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as client:
        yield client


def _prepared(session, months):
    world = _CHARACTER._World(session)
    prepared = {
        month: _CHARACTER._prepared_ratio(world, "Coding", month, people)
        for month, people in months
    }
    return world, prepared


def _coordinator(session, clock=None):
    return EvaluationLeaseCoordinator(session, clock=clock)


def _runtime(session, clock=None, **kwargs):
    return EvaluationApplyRuntime(
        session,
        "worker-runtime",
        clock=clock,
        lease_seconds=30,
        **kwargs,
    )


def _job(session, job_id):
    return session.query(ProcessingJob).filter(ProcessingJob.id == uuid.UUID(str(job_id))).one()


def _control(session, job_id):
    return session.query(EvaluationApplyControl).filter(EvaluationApplyControl.job_id == uuid.UUID(str(job_id))).one()


def _scores(session):
    return sorted((str(row.score), row.grade, row.status) for row in session.query(PerformanceRecord).all())


def _headers(session, user_id):
    user = session.query(User).filter(User.id == user_id).one()
    token = AuthenticationService._access_token(user, datetime.now(timezone.utc))
    return {"Authorization": f"Bearer {token}"}


def _forged_admin_headers(session, user_id):
    user = session.query(User).filter(User.id == user_id).one()
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": str(user.id),
        "sub": user.username,
        "username": user.username,
        "role": "Admin",
        "type": "access",
        "must_change_password": False,
        "iat": now,
        "exp": now + timedelta(minutes=30),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return {"Authorization": f"Bearer {token}"}


def _code(response) -> str | None:
    detail = response.json().get("detail")
    if isinstance(detail, dict):
        return detail.get("code")
    return None


def _audits(session, job_id=None):
    query = session.query(AuditLog)
    if job_id is not None:
        query = query.filter(AuditLog.record_id == uuid.UUID(str(job_id)))
    return query.order_by(AuditLog.id.asc()).all()


def _values(raw):
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)


def _assert_audit(row, *, action, actor_id, job_id, requester_id):
    assert row.table_name == "evaluation_apply_controls"
    assert row.operation == "UPDATE"
    assert row.record_id == uuid.UUID(str(job_id))
    assert row.performed_by_user_id == actor_id
    assert row.ip_address is None and row.request_id is None
    old = _values(row.old_values)
    new = _values(row.new_values)
    assert set(old) == AUDIT_KEYS
    assert set(new) == AUDIT_KEYS
    assert old["action"] == action and new["action"] == action
    assert old["requested_by_user_id"] == str(requester_id)
    assert new["requested_by_user_id"] == str(requester_id)
    blob = json.dumps({"old": old, "new": new}, sort_keys=True)
    for marker in ("Ada", "Sentinel", "actor_snapshot", "bounded-admin", "SELECT", "Traceback"):
        assert marker not in blob
    return old, new


def _no_people(response):
    for marker in ("Ada Sentinel", "Ben Sentinel", "August Sentinel", "actor_snapshot"):
        assert marker not in response.text


def _user(session, role, name):
    user = _CHARACTER._user(role, name)
    session.add(user)
    session.commit()
    return user


def _block_apply(monkeypatch):
    def _forbidden(*args, **kwargs):
        raise AssertionError("workflow apply")

    monkeypatch.setattr(EvaluationWorkflow, "apply", _forbidden)


def test_flag_defaults_false_and_disabled_calls_do_no_work(monkeypatch):
    assert settings.PMS_EVALUATION_APPLY_JOBS_ENABLED is False
    assert EvaluationLeaseCoordinator(_Boom(), clock=_Boom()).fail_live(
        _Boom(), _Boom(), reason="apply_failed"
    ) == {"enabled": False, "outcome": "disabled"}
    assert EvaluationApplyRuntime(_Boom(), "worker-runtime", clock=_Boom()).run_tick() == {
        "enabled": False,
        "outcome": "disabled",
        "considered": 0,
        "advanced": 0,
        "skipped": 0,
    }
    assert run_enabled_tick(_Boom(), "worker-runtime", client=_Boom(), clock=_Boom())["outcome"] == "disabled"
    monkeypatch.setattr(settings, "PMS_EVALUATION_APPLY_JOBS_ENABLED", "true")
    assert run_enabled_tick(_Boom(), "worker-runtime", client=_Boom(), clock=_Boom())["outcome"] == "disabled"

    source = (BACKEND / "services" / "evaluation" / "runtime.py").read_text(encoding="utf-8")
    assert "with_for_update" not in source
    assert "claim_next" not in source
    assert "process_job_once" not in source
    assert " OFFSET" not in source and ".offset(" not in source
    imported = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.extend(alias.name for alias in node.names)
    assert "EvaluationWorkflow" not in imported
    worker_source = (BACKEND / "worker.py").read_text(encoding="utf-8")
    dispatch = inspect.cleandoc(
        worker_source.split("def process_job_once", 1)[1].split("\n    db = SessionLocal()", 1)[0]
    )
    assert "evaluation_apply" not in dispatch
    assert "outbox_publisher" not in worker_source
    assert "CacheOutboxPublisher" not in worker_source
    assert JOB_KINDS == {"pms_upload", "report_generation", "story_report_generation"}


def test_skipped_candidate_log_has_no_exception_text(db, monkeypatch):
    _block_apply(monkeypatch)
    clock = _Clock(START)
    world, prepared = _prepared(db, ((7, [("C-1", "Ada Sentinel", "60")]),))
    queued = _coordinator(db, clock).enqueue(world.actor, prepared[7]["scope"]["id"], 2026, 7, enabled=True)
    runtime = _runtime(db, clock)
    runtime._candidate_ids = lambda _now: [uuid.uuid4()]

    def _boom(_job_id):
        raise RuntimeError("SECRET-PII Ada Sentinel")

    runtime._advance = _boom
    handler = _Log()
    logger = logging.getLogger("services.evaluation.runtime")
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    try:
        summary = runtime.run_tick(enabled=True)
    finally:
        logger.removeHandler(handler)
    assert summary == {"enabled": True, "outcome": "tick", "considered": 1, "advanced": 0, "skipped": 1}
    assert handler.messages == ["evaluation apply candidate skipped"]
    assert "SECRET-PII" not in " ".join(handler.messages)
    assert _job(db, queued["job_id"]).status == "queued"
    assert int(_job(db, queued["job_id"]).attempt_count or 0) == 0


def test_http_denies_before_the_disabled_runtime_and_keeps_sync_apply(db, api, monkeypatch):
    original_apply = EvaluationWorkflow.apply
    _block_apply(monkeypatch)
    world, prepared = _prepared(db, ((7, [("C-1", "Ada Sentinel", "60"), ("C-2", "Ben Sentinel", "30")]),))
    scope_id = prepared[7]["scope"]["id"]
    admin = _headers(db, world.admin_id)
    manager = _headers(db, world.manager_id)
    performance = _headers(db, _user(db, "Performance Team", "performance-deny").id)
    employee = _headers(db, _user(db, "Employee", "employee-deny").id)
    body = {"scope_id": str(scope_id), "year": 2026, "month": 7}
    random_job = str(uuid.uuid4())

    missing = api.post(f"{PREFIX}/apply-jobs", json=body)
    assert missing.status_code == 401
    assert missing.status_code != 503
    assert "runtime_disabled" not in missing.text

    for headers in (manager, performance, employee):
        denied = api.post(f"{PREFIX}/apply-jobs", headers=headers, json=body)
        assert denied.status_code == 403
        assert _code(denied) == "access_denied"
        capability = api.get(f"{PREFIX}/apply-jobs/capabilities", headers=headers)
        assert capability.status_code == 403
        assert _code(capability) == "access_denied"

    inactive = _user(db, "Admin", "inactive-admin")
    inactive_headers = _headers(db, inactive.id)
    stored = db.query(User).filter(User.id == inactive.id).one()
    stored.is_active = False
    db.commit()
    disabled_user = api.get(f"{PREFIX}/apply-jobs/capabilities", headers=inactive_headers)
    assert disabled_user.status_code == 401
    assert "runtime_disabled" not in disabled_user.text

    forged = api.post(f"{PREFIX}/apply-jobs", headers=_forged_admin_headers(db, world.manager_id), json=body)
    assert forged.status_code == 403
    assert _code(forged) == "access_denied"

    capability = api.get(f"{PREFIX}/apply-jobs/capabilities", headers=admin)
    assert capability.status_code == 200
    assert capability.json()["data"] == {"enabled": False}
    assert type(capability.json()["data"]["enabled"]) is bool

    monkeypatch.setattr(settings, "PMS_EVALUATION_APPLY_JOBS_ENABLED", "true")
    still_off = api.get(f"{PREFIX}/apply-jobs/capabilities", headers=admin)
    assert still_off.status_code == 200
    assert still_off.json()["data"]["enabled"] is False
    monkeypatch.setattr(settings, "PMS_EVALUATION_APPLY_JOBS_ENABLED", False)

    def _forbidden(*args, **kwargs):
        raise AssertionError("coordinator entered")

    for name in ("enqueue", "status", "cancel", "retry", "recover"):
        monkeypatch.setattr(EvaluationLeaseCoordinator, name, _forbidden)
    closed = (
        api.post(f"{PREFIX}/apply-jobs", headers=admin, json=body),
        api.get(f"{PREFIX}/apply-jobs", headers=admin, params={"scope_id": str(scope_id), "year": 2026, "month": 7}),
        api.get(f"{PREFIX}/apply-jobs/{random_job}", headers=admin),
        api.post(f"{PREFIX}/apply-jobs/{random_job}/cancel", headers=admin),
        api.post(f"{PREFIX}/apply-jobs/{random_job}/retry", headers=admin),
        api.post(f"{PREFIX}/apply-jobs/{random_job}/recover", headers=admin, json={"expected_epoch": 0}),
    )
    for response in closed:
        assert response.status_code == 503
        assert response.json()["detail"] == {
            "message": "Evaluation apply jobs are disabled.",
            "code": "runtime_disabled",
        }
    assert db.query(ProcessingJob).count() == 0

    invalid = api.get(f"{PREFIX}/apply-jobs/not-a-uuid", headers=admin)
    assert invalid.status_code == 422
    extra = api.post(f"{PREFIX}/apply-jobs", headers=admin, json={**body, "note": "nope"})
    assert extra.status_code == 422
    assert db.query(ProcessingJob).count() == 0

    monkeypatch.setattr(EvaluationWorkflow, "apply", original_apply)
    monkeypatch.setattr(settings, "PMS_EVALUATION_APPLY_JOBS_ENABLED", False)
    applied = api.post(
        f"{PREFIX}/apply",
        headers=admin,
        json={"scope_id": str(scope_id), "year": 2026, "month": 7},
    )
    assert applied.status_code == 200
    assert applied.json()["success"] is True
    assert db.query(EvaluationRevision).count() == 1
    assert db.query(ProcessingJob).filter(ProcessingJob.kind == "evaluation_apply").count() == 0


def test_http_cross_admin_management_reopen_and_committed_recover(db, api, monkeypatch):
    _block_apply(monkeypatch)
    monkeypatch.setattr(settings, "PMS_EVALUATION_APPLY_JOBS_ENABLED", True)
    world, prepared = _prepared(
        db,
        (
            (7, [("C-1", "Ada Sentinel", "60"), ("C-2", "Ben Sentinel", "30")]),
            (8, [("C-8", "August Sentinel", "60")]),
        ),
    )
    other = _user(db, "Admin", "other-admin")
    other_id = other.id
    admin = _headers(db, world.admin_id)
    other_headers = _headers(db, other_id)
    july = prepared[7]["scope"]["id"]
    august = prepared[8]["scope"]["id"]
    original_scores = _scores(db)
    capability = api.get(f"{PREFIX}/apply-jobs/capabilities", headers=admin)
    assert capability.json()["data"]["enabled"] is True

    created = api.post(f"{PREFIX}/apply-jobs", headers=admin, json={"scope_id": str(july), "year": 2026, "month": 7})
    assert created.status_code == 200, created.text
    queued = created.json()["data"]
    job_id = queued["job_id"]
    assert queued["outcome"] == "queued" and queued["job_status"] == "queued"
    snapshot = dict(_control(db, job_id).actor_snapshot)
    requester = _control(db, job_id).requested_by_user_id
    assert requester == world.admin_id

    owner_status = api.get(f"{PREFIX}/apply-jobs/{job_id}", headers=admin)
    assert owner_status.status_code == 200
    _no_people(owner_status)
    assert owner_status.json()["data"]["job_status"] == "queued"
    assert _audits(db, job_id) == []

    original_commit = db.commit

    def _boom_commit():
        raise RuntimeError("commit failed SECRET-TOKEN")

    db.commit = _boom_commit
    try:
        failed_cancel = api.post(f"{PREFIX}/apply-jobs/{job_id}/cancel", headers=other_headers)
    finally:
        db.commit = original_commit
    assert failed_cancel.status_code == 422
    assert _code(failed_cancel) == "persistence_failed"
    assert "SECRET-TOKEN" not in failed_cancel.text
    assert _job(db, job_id).status == "queued"
    assert _audits(db, job_id) == []

    inspected = api.get(f"{PREFIX}/apply-jobs/{job_id}", headers=other_headers)
    assert inspected.status_code == 200
    assert inspected.json()["data"]["outcome"] == "status"
    _no_people(inspected)
    rows = _audits(db, job_id)
    assert len(rows) == 1
    _assert_audit(rows[0], action="inspect", actor_id=other_id, job_id=job_id, requester_id=requester)
    repeated = api.get(f"{PREFIX}/apply-jobs/{job_id}", headers=other_headers)
    assert repeated.status_code == 200
    assert len(_audits(db, job_id)) == 2
    owner_again = api.get(f"{PREFIX}/apply-jobs/{job_id}", headers=admin)
    assert owner_again.status_code == 200
    assert len(_audits(db, job_id)) == 2
    assert _control(db, job_id).requested_by_user_id == requester
    assert _control(db, job_id).actor_snapshot == snapshot

    denied_retry = api.post(f"{PREFIX}/apply-jobs/{job_id}/retry", headers=other_headers)
    assert denied_retry.status_code == 403
    denied_detail = denied_retry.json()["detail"]
    assert denied_detail["message"] == "Evaluation settings are limited to Admin."
    assert denied_detail.get("code") is None
    assert _job(db, job_id).status == "queued"
    assert int(_job(db, job_id).attempt_count or 0) == 0
    assert len(_audits(db, job_id)) == 2

    duplicate = api.post(
        f"{PREFIX}/apply-jobs",
        headers=other_headers,
        json={"scope_id": str(july), "year": 2026, "month": 7},
    )
    assert duplicate.status_code == 409
    assert _code(duplicate) == "duplicate_binding"
    assert db.query(ProcessingJob).filter(ProcessingJob.kind == "evaluation_apply").count() == 1

    clock = _Clock(datetime.now(timezone.utc))
    token = _coordinator(db, clock).start(world.actor, job_id, "worker-runtime", lease_seconds=30, enabled=True)
    page = _coordinator(db, clock).stage_page(world.actor, token, lease_seconds=30, page_size=100, enabled=True)
    assert page["complete"] is True
    staged = db.query(EvaluationApplyStageRow).filter(EvaluationApplyStageRow.job_id == uuid.UUID(job_id)).count()
    assert staged == 2

    cancelled = api.post(f"{PREFIX}/apply-jobs/{job_id}/cancel", headers=other_headers)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["data"]["state"] == "cancelled"
    assert cancelled.json()["data"]["idempotent"] is False
    cancel_rows = _audits(db, job_id)
    assert len(cancel_rows) == 3
    cancel_audit = [row for row in cancel_rows if _values(row.new_values)["action"] == "cancel"]
    assert len(cancel_audit) == 1
    _old, new = _assert_audit(cancel_audit[0], action="cancel", actor_id=other_id, job_id=job_id, requester_id=requester)
    assert new["job_status"] == "cancelled" and new["control_state"] == "cancelled"
    assert _control(db, job_id).requested_by_user_id == requester
    assert _control(db, job_id).actor_snapshot == snapshot
    assert db.query(EvaluationApplyStageRow).filter(EvaluationApplyStageRow.job_id == uuid.UUID(job_id)).count() == staged
    assert _scores(db) == original_scores

    again = api.post(f"{PREFIX}/apply-jobs/{job_id}/cancel", headers=other_headers)
    assert again.status_code == 200
    assert again.json()["data"]["idempotent"] is True
    repeated_audits = _audits(db, job_id)
    assert len(repeated_audits) == 4
    assert sum(1 for row in repeated_audits if _values(row.new_values)["action"] == "cancel") == 2
    assert db.query(EvaluationApplyStageRow).filter(EvaluationApplyStageRow.job_id == uuid.UUID(job_id)).count() == staged

    replacement = api.post(
        f"{PREFIX}/apply-jobs",
        headers=other_headers,
        json={"scope_id": str(july), "year": 2026, "month": 7},
    )
    assert replacement.status_code == 200, replacement.text
    new_id = replacement.json()["data"]["job_id"]
    assert new_id != job_id
    assert _control(db, new_id).requested_by_user_id == other_id
    assert _job(db, new_id).requested_by_user_id == other_id
    assert _control(db, job_id).actor_snapshot == snapshot
    assert _control(db, job_id).requested_by_user_id == requester
    assert db.query(EvaluationApplyStageRow).filter(EvaluationApplyStageRow.job_id == uuid.UUID(job_id)).count() == staged
    assert db.query(EvaluationApplyStageRow).filter(EvaluationApplyStageRow.job_id == uuid.UUID(new_id)).count() == 0
    old_row = _job(db, job_id)
    new_row = _job(db, new_id)
    old_row.created_at = START
    new_row.created_at = START + timedelta(hours=1)
    db.commit()
    reopened = api.get(
        f"{PREFIX}/apply-jobs",
        headers=other_headers,
        params={"scope_id": str(july), "year": 2026, "month": 7},
    )
    assert reopened.status_code == 200
    _no_people(reopened)
    assert reopened.json()["data"]["job"]["job_id"] == new_id
    assert reopened.json()["data"]["job"]["job_status"] == "queued"
    assert "records" not in reopened.json()["data"]["job"]
    closed = api.post(f"{PREFIX}/apply-jobs/{new_id}/cancel", headers=other_headers)
    assert closed.status_code == 200, closed.text
    assert _job(db, new_id).status == "cancelled"

    august_body = api.post(
        f"{PREFIX}/apply-jobs",
        headers=admin,
        json={"scope_id": str(august), "year": 2026, "month": 8},
    )
    assert august_body.status_code == 200, august_body.text
    august_id = august_body.json()["data"]["job_id"]
    db.info["bounded_apply_fault"] = "before_commit"
    first = _runtime(db).run_tick(enabled=True)
    assert first["advanced"] == 1 and first["skipped"] == 0
    assert _control(db, august_id).state == "promoted"
    assert _job(db, august_id).status == "running"
    assert int(_job(db, august_id).progress or 0) < 100
    assert db.query(EvaluationRevision).count() == 1
    assert db.query(CacheInvalidationOutbox).count() == 1
    assert db.query(CacheInvalidationOutbox).one().published_at is None
    promoted_scores = _scores(db)
    assert promoted_scores != original_scores
    assert _audits(db, august_id) == []

    wrong = api.post(
        f"{PREFIX}/apply-jobs/{august_id}/recover",
        headers=other_headers,
        json={"expected_epoch": 5},
    )
    assert wrong.status_code == 200, wrong.text
    assert wrong.json()["data"]["mutated"] is False
    assert _job(db, august_id).status == "running"
    assert len(_audits(db, august_id)) == 1
    _assert_audit(_audits(db, august_id)[0], action="recover", actor_id=other_id, job_id=august_id, requester_id=world.admin_id)

    faulted = api.post(
        f"{PREFIX}/apply-jobs/{august_id}/recover",
        headers=other_headers,
        json={"expected_epoch": 0},
    )
    assert faulted.status_code == 409
    assert _code(faulted) == "fault_injected"
    assert _job(db, august_id).status == "running"
    assert _control(db, august_id).state == "promoted"
    assert len(_audits(db, august_id)) == 1
    assert db.query(EvaluationRevision).count() == 1
    assert db.query(CacheInvalidationOutbox).count() == 1

    db.info.pop("bounded_apply_fault", None)
    missing_epoch = api.post(f"{PREFIX}/apply-jobs/{august_id}/recover", headers=other_headers, json={})
    assert missing_epoch.status_code == 422
    boolean_epoch = api.post(
        f"{PREFIX}/apply-jobs/{august_id}/recover",
        headers=other_headers,
        json={"expected_epoch": True},
    )
    assert boolean_epoch.status_code == 422
    assert _job(db, august_id).status == "running"

    recovered = api.post(
        f"{PREFIX}/apply-jobs/{august_id}/recover",
        headers=other_headers,
        json={"expected_epoch": 0},
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["data"]["mutated"] is True
    assert recovered.json()["data"]["job_status"] == "succeeded"
    assert int(_job(db, august_id).progress or 0) == 100
    assert db.query(EvaluationRevision).count() == 1
    assert db.query(CacheInvalidationOutbox).count() == 1
    assert _scores(db) == promoted_scores
    assert _control(db, august_id).requested_by_user_id == world.admin_id
    assert len(_audits(db, august_id)) == 2

    repeat = api.post(
        f"{PREFIX}/apply-jobs/{august_id}/recover",
        headers=other_headers,
        json={"expected_epoch": 0},
    )
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["data"]["mutated"] is False
    assert repeat.json()["data"]["idempotent"] is True
    assert db.query(EvaluationRevision).count() == 1
    assert db.query(CacheInvalidationOutbox).count() == 1
    assert len(_audits(db, august_id)) == 3
    august_view = api.get(
        f"{PREFIX}/apply-jobs",
        headers=admin,
        params={"scope_id": str(august), "year": 2026, "month": 8},
    )
    assert august_view.status_code == 200
    _no_people(august_view)
    assert august_view.json()["data"]["job"]["job_id"] == august_id
    assert august_view.json()["data"]["job"]["progress"] == 100


def test_runtime_acks_promoted_work_once_and_keeps_a_live_fence(db, monkeypatch):
    _block_apply(monkeypatch)
    clock = _Clock(START)
    world, prepared = _prepared(
        db,
        (
            (7, [("C-1", "Ada Sentinel", "60"), ("C-2", "Ben Sentinel", "30")]),
            (8, [("C-8", "August Sentinel", "60")]),
        ),
    )
    scope_id = prepared[7]["scope"]["id"]
    august_scope = prepared[8]["scope"]["id"]
    queued = _coordinator(db, clock).enqueue(world.actor, scope_id, 2026, 7, enabled=True)
    job_id = queued["job_id"]
    before = _scores(db)
    db.info["bounded_apply_fault"] = "before_commit"
    first = _runtime(db, clock).run_tick(enabled=True)
    assert first == {"enabled": True, "outcome": "tick", "considered": 1, "advanced": 1, "skipped": 0}
    assert _control(db, job_id).state == "promoted"
    assert _job(db, job_id).status == "running"
    assert int(_job(db, job_id).progress or 0) == 99
    assert _job(db, job_id).error_code is None
    assert db.query(EvaluationRevision).count() == 1
    assert db.query(CacheInvalidationOutbox).count() == 1
    revision_id = db.query(EvaluationRevision).one().id
    outbox_id = db.query(CacheInvalidationOutbox).one().id

    db.info["bounded_apply_fault"] = "before_commit"
    held = _runtime(db, clock).run_tick(enabled=True)
    assert held["considered"] == 1 and held["skipped"] == 1
    assert _job(db, job_id).status == "running"
    assert db.query(EvaluationRevision).one().id == revision_id
    assert db.query(CacheInvalidationOutbox).one().id == outbox_id

    db.info.pop("bounded_apply_fault", None)
    second = _runtime(db, clock).run_tick(enabled=True)
    assert second["advanced"] == 1 and second["skipped"] == 0
    assert _job(db, job_id).status == "succeeded"
    assert int(_job(db, job_id).progress or 0) == 100
    assert _control(db, job_id).state == "promoted"
    assert db.query(EvaluationRevision).one().id == revision_id
    assert db.query(CacheInvalidationOutbox).one().id == outbox_id
    assert _scores(db) != before
    third = _runtime(db, clock).run_tick(enabled=True)
    assert third["considered"] == 0
    assert db.query(EvaluationRevision).count() == 1

    august_job = _coordinator(db, clock).enqueue(world.actor, august_scope, 2026, 8, enabled=True)
    original_stage = EvaluationLeaseCoordinator.stage_page

    def _held(self, actor, token, **kwargs):
        raise LeaseCoordinatorError("lease_held")

    monkeypatch.setattr(EvaluationLeaseCoordinator, "stage_page", _held)
    fenced = _runtime(db, clock).run_tick(enabled=True)
    assert fenced["skipped"] == 1 and fenced["advanced"] == 0
    assert _job(db, august_job["job_id"]).status == "running"
    assert _control(db, august_job["job_id"]).state == "staging"
    assert _job(db, august_job["job_id"]).error_code is None

    def _empty(self, actor, token, **kwargs):
        return {"complete": False, "page_count": 0}

    cancelled = _coordinator(db, clock).cancel(world.actor, august_job["job_id"], enabled=True)
    assert cancelled["state"] == "cancelled"
    monkeypatch.setattr(EvaluationLeaseCoordinator, "stage_page", original_stage)
    retried = _coordinator(db, clock).retry(world.actor, august_job["job_id"], enabled=True)
    assert retried["claim_epoch"] == 1
    monkeypatch.setattr(EvaluationLeaseCoordinator, "stage_page", _empty)
    failed = _runtime(db, clock).run_tick(enabled=True)
    assert failed["advanced"] == 1
    assert _job(db, august_job["job_id"]).status == "failed"
    assert _job(db, august_job["job_id"]).error_code == "incomplete_stage"
    assert _job(db, august_job["job_id"]).safe_error_message == "evaluation apply failed"
    assert _control(db, august_job["job_id"]).state == "failed"
    assert db.query(EvaluationRevision).count() == 1


def test_revoked_requester_does_not_fill_or_stop_the_window(db, monkeypatch):
    _block_apply(monkeypatch)
    clock = _Clock(START)
    world, prepared = _prepared(
        db,
        (
            (7, [("C-1", "Ada Sentinel", "60")]),
            (8, [("C-8", "August Sentinel", "60")]),
        ),
    )
    other = _user(db, "Admin", "later-admin")
    other_actor = _CHARACTER._actor(other)
    coordinator = _coordinator(db, clock)
    july = coordinator.enqueue(world.actor, prepared[7]["scope"]["id"], 2026, 7, enabled=True)
    clock.moment = START + timedelta(seconds=1)
    august = coordinator.enqueue(other_actor, prepared[8]["scope"]["id"], 2026, 8, enabled=True)
    clock.moment = START + timedelta(seconds=1)
    owner = db.query(User).filter(User.id == world.admin_id).one()
    owner.is_active = False
    db.commit()

    window = _runtime(db, clock, candidate_limit=1).run_tick(enabled=True)
    assert window["considered"] == 1 and window["advanced"] == 1
    assert _job(db, july["job_id"]).status == "queued"
    assert int(_job(db, july["job_id"]).attempt_count or 0) == 0
    assert _job(db, august["job_id"]).status == "succeeded"


def test_injected_denial_does_not_stop_the_next_candidate(db, monkeypatch):
    _block_apply(monkeypatch)
    clock = _Clock(START)
    world, prepared = _prepared(
        db,
        (
            (7, [("C-1", "Ada Sentinel", "60")]),
            (8, [("C-8", "August Sentinel", "60")]),
        ),
    )
    other = _user(db, "Admin", "later-admin")
    other_actor = _CHARACTER._actor(other)
    coordinator = _coordinator(db, clock)
    denied = coordinator.enqueue(world.actor, prepared[7]["scope"]["id"], 2026, 7, enabled=True)
    allowed = coordinator.enqueue(other_actor, prepared[8]["scope"]["id"], 2026, 8, enabled=True)
    owner = db.query(User).filter(User.id == world.admin_id).one()
    owner.is_active = False
    db.commit()
    runtime = _runtime(db, clock)

    def _ids(_now):
        runtime._rollback()
        return [uuid.UUID(denied["job_id"]), uuid.UUID(allowed["job_id"])]

    runtime._candidate_ids = _ids
    summary = runtime.run_tick(enabled=True)
    assert summary["considered"] == 2
    assert summary["advanced"] == 1
    assert summary["skipped"] == 1
    assert _job(db, denied["job_id"]).status == "queued"
    assert int(_job(db, denied["job_id"]).attempt_count or 0) == 0
    assert _job(db, allowed["job_id"]).status == "succeeded"
    assert _control(db, denied["job_id"]).requested_by_user_id == world.admin_id


def test_retry_does_not_rescore_changed_evidence_or_pass_the_attempt_cap(db, monkeypatch):
    _block_apply(monkeypatch)
    clock = _Clock(START)
    world, prepared = _prepared(
        db,
        (
            (7, [("C-1", "Ada Sentinel", "60")]),
            (8, [("C-8", "August Sentinel", "60")]),
        ),
    )
    coordinator = _coordinator(db, clock)
    july = coordinator.enqueue(world.actor, prepared[7]["scope"]["id"], 2026, 7, enabled=True)
    august = coordinator.enqueue(world.actor, prepared[8]["scope"]["id"], 2026, 8, enabled=True)
    july_token = coordinator.start(world.actor, july["job_id"], "worker-runtime", lease_seconds=30, enabled=True)
    august_token = coordinator.start(world.actor, august["job_id"], "worker-runtime", lease_seconds=30, enabled=True)
    assert coordinator.stage_page(world.actor, july_token, lease_seconds=30, page_size=100, enabled=True)["complete"] is True
    assert coordinator.stage_page(world.actor, august_token, lease_seconds=30, page_size=100, enabled=True)["complete"] is True
    before = _scores(db)
    july_rows = db.query(EvaluationApplyStageRow).filter(EvaluationApplyStageRow.job_id == uuid.UUID(july["job_id"])).count()
    moving = (
        db.query(KPIValue)
        .join(KPIValue.performance_record)
        .filter(PerformanceRecord.month == "July")
        .one()
    )
    moving.actual_value = Decimal("61")
    august_job = _job(db, august["job_id"])
    august_job.max_attempts = 1
    db.commit()
    clock.moment = START + timedelta(seconds=30)
    summary = _runtime(db, clock).run_tick(enabled=True)
    assert summary["considered"] == 2
    assert summary["advanced"] == 0
    july_failed = _job(db, july["job_id"])
    assert july_failed.status == "failed"
    assert july_failed.error_code == "lease_expired"
    assert _control(db, july["job_id"]).state == "failed"
    assert int(_control(db, july["job_id"]).claim_epoch) == 0
    assert db.query(EvaluationRevision).count() == 0
    assert db.query(CacheInvalidationOutbox).count() == 0
    assert _scores(db) == before
    assert db.query(EvaluationApplyStageRow).filter(EvaluationApplyStageRow.job_id == uuid.UUID(july["job_id"])).count() == july_rows
    august_failed = _job(db, august["job_id"])
    assert august_failed.status == "failed"
    assert august_failed.error_code == "lease_expired"
    assert int(_control(db, august["job_id"]).claim_epoch) == 0
    assert int(august_failed.attempt_count or 0) == 1


def test_fail_live_preserves_a_promotion_and_fails_a_live_token(db, monkeypatch):
    _block_apply(monkeypatch)
    clock = _Clock(START)
    world, prepared = _prepared(
        db,
        (
            (7, [("C-1", "Ada Sentinel", "60")]),
            (8, [("C-8", "August Sentinel", "60")]),
        ),
    )
    coordinator = _coordinator(db, clock)
    july = coordinator.enqueue(world.actor, prepared[7]["scope"]["id"], 2026, 7, enabled=True)
    august = coordinator.enqueue(world.actor, prepared[8]["scope"]["id"], 2026, 8, enabled=True)
    july_token = coordinator.start(world.actor, july["job_id"], "worker-runtime", lease_seconds=30, enabled=True)
    assert coordinator.stage_page(world.actor, july_token, lease_seconds=30, page_size=100, enabled=True)["complete"] is True
    promoted = coordinator.promote(world.actor, july_token, enabled=True)
    assert promoted["acknowledged"] is False
    preserved = coordinator.fail_live(world.actor, july_token, reason="evidence_changed", enabled=True)
    assert preserved["outcome"] == "preserved"
    assert _control(db, july["job_id"]).state == "promoted"
    assert _job(db, july["job_id"]).status == "running"
    assert db.query(EvaluationRevision).count() == 1
    assert _control(db, july["job_id"]).promoted_revision_id is not None

    august_token = coordinator.start(world.actor, august["job_id"], "worker-runtime", lease_seconds=30, enabled=True)
    failed = coordinator.fail_live(world.actor, august_token, reason="evidence_changed", enabled=True)
    assert failed["outcome"] == "failed"
    assert _job(db, august["job_id"]).status == "failed"
    assert _job(db, august["job_id"]).error_code == "evidence_changed"
    assert _job(db, august["job_id"]).safe_error_message == "evaluation apply failed"
    assert _control(db, august["job_id"]).state == "failed"
    opened = coordinator.enqueue(world.actor, prepared[8]["scope"]["id"], 2026, 8, enabled=True)
    assert opened["job_id"] != august["job_id"]
    assert opened["job_status"] == "queued"


def test_execution_actor_is_only_the_persisted_requester_id(db, monkeypatch):
    """The identity trigger rejects a rewritten snapshot, and the tick never reads one."""

    _block_apply(monkeypatch)
    from sqlalchemy.orm.attributes import flag_modified

    clock = _Clock(START)
    world, prepared = _prepared(db, ((7, [("C-1", "Ada Sentinel", "60")]),))
    requester_id = world.admin_id
    queued = _coordinator(db, clock).enqueue(world.actor, prepared[7]["scope"]["id"], 2026, 7, enabled=True)
    control = _control(db, queued["job_id"])
    snapshot = dict(control.actor_snapshot)
    assert snapshot["role"] == "Admin"
    mutated = dict(snapshot)
    mutated["role"] = "Manager"
    control.actor_snapshot = mutated
    flag_modified(control, "actor_snapshot")
    with pytest.raises(Exception) as rejected:
        db.commit()
    assert "immutable" in str(rejected.value).lower()
    db.rollback()
    assert _control(db, queued["job_id"]).actor_snapshot == snapshot

    seen = []

    def _watch(real):
        def _wrapped(self, actor, *args, **kwargs):
            seen.append(dict(actor))
            return real(self, actor, *args, **kwargs)

        return _wrapped

    for name in ("start", "stage_page", "promote", "acknowledge"):
        monkeypatch.setattr(EvaluationLeaseCoordinator, name, _watch(getattr(EvaluationLeaseCoordinator, name)))
    summary = _runtime(db, clock).run_tick(enabled=True)
    assert summary["advanced"] == 1 and summary["skipped"] == 0
    assert [set(actor) for actor in seen] == [{"user_id"}] * len(seen)
    assert {actor["user_id"] for actor in seen} == {str(requester_id)}
    assert _job(db, queued["job_id"]).status == "succeeded"
    assert _control(db, queued["job_id"]).actor_snapshot == snapshot
    assert _control(db, queued["job_id"]).requested_by_user_id == requester_id
    assert db.query(User).filter(User.id == requester_id).one().role == "Admin"


def test_partial_page_keeps_stage_rows_until_a_later_epoch(db, monkeypatch):
    _block_apply(monkeypatch)
    clock = _Clock(START)
    world, prepared = _prepared(db, ((7, [("C-1", "Ada Sentinel", "60"), ("C-2", "Ben Sentinel", "30")]),))
    queued = _coordinator(db, clock).enqueue(world.actor, prepared[7]["scope"]["id"], 2026, 7, enabled=True)
    first = _runtime(db, clock, page_size=1, max_pages=1).run_tick(enabled=True)
    assert first["advanced"] == 1
    assert _job(db, queued["job_id"]).status == "running"
    assert int(_job(db, queued["job_id"]).progress or 0) == 49
    assert _control(db, queued["job_id"]).state == "staging"
    assert db.query(EvaluationApplyStageRow).count() == 1
    assert int(db.query(EvaluationApplyStageRow).one().claim_epoch) == 0
    clock.moment = START + timedelta(seconds=30)
    second = _runtime(db, clock, page_size=1, max_pages=1).run_tick(enabled=True)
    assert second["advanced"] == 1
    assert _job(db, queued["job_id"]).status == "queued"
    assert _control(db, queued["job_id"]).state == "pending"
    assert int(_control(db, queued["job_id"]).claim_epoch) == 1
    assert db.query(EvaluationApplyStageRow).count() == 1
    assert int(db.query(EvaluationApplyStageRow).one().claim_epoch) == 0
    assert db.query(EvaluationRevision).count() == 0


def test_publisher_does_not_use_client_truthiness(db, monkeypatch):
    _block_apply(monkeypatch)
    monkeypatch.setattr(settings, "PMS_EVALUATION_APPLY_JOBS_ENABLED", True)
    clock = _Clock(START)
    world, prepared = _prepared(
        db,
        (
            (7, [("C-1", "Ada Sentinel", "60")]),
            (8, [("C-8", "August Sentinel", "60")]),
        ),
    )
    coordinator = _coordinator(db, clock)
    july = coordinator.enqueue(world.actor, prepared[7]["scope"]["id"], 2026, 7, enabled=True)
    fallback = _fallback_data_version
    failed_client = _Client(incr_error=RuntimeError("redis://secret-token"))
    _runtime(db, clock).run_tick(enabled=True)
    failed = run_enabled_tick(db, "worker-runtime", client=failed_client, clock=clock, lease_seconds=30)
    assert failed["delivery"]["published"] == 0
    assert failed["delivery"]["failed"] == 1
    assert failed_client.bool_calls == 0
    row = db.query(CacheInvalidationOutbox).one()
    assert row.published_at is None
    assert row.last_error == "cache delivery increment failed"
    assert "secret-token" not in (row.last_error or "")
    assert _fallback_data_version == fallback
    identity = evaluation_cache_identity(db)
    assert isinstance(identity, str) and len(identity) == 64
    assert _job(db, july["job_id"]).status == "succeeded"

    clock.moment = START + timedelta(seconds=1)
    august = coordinator.enqueue(world.actor, prepared[8]["scope"]["id"], 2026, 8, enabled=True)
    _runtime(db, clock).run_tick(enabled=True)
    good = _Client()
    published = run_enabled_tick(db, "worker-runtime", client=good, clock=clock, lease_seconds=30)
    assert published["delivery"]["published"] >= 1
    assert good.bool_calls == 0
    august_row = (
        db.query(CacheInvalidationOutbox)
        .join(EvaluationApplyControl, EvaluationApplyControl.promoted_revision_id == CacheInvalidationOutbox.revision_id)
        .filter(EvaluationApplyControl.job_id == uuid.UUID(august["job_id"]))
        .one()
    )
    assert august_row.published_at is not None
    assert _fallback_data_version == fallback
    assert ("incr", "pms:version:data") in good.calls
    assert any(call[0] == "publish" and call[1] == "cache_invalidation" for call in good.calls)


def test_worker_once_stays_finite_and_leaves_legacy_dispatch_unchanged(db, monkeypatch):
    _block_apply(monkeypatch)
    import worker

    clock = _Clock(START)
    world, prepared = _prepared(db, ((7, [("C-1", "Ada Sentinel", "60"), ("C-2", "Ben Sentinel", "30")]),))
    queued = _coordinator(db, clock).enqueue(world.actor, prepared[7]["scope"]["id"], 2026, 7, enabled=True)
    upload = ProcessingJobService.create(
        db,
        kind="pms_upload",
        request_json={"filename": "noop.xlsx"},
        requested_by_user_id=world.admin_id,
        requested_by_name="bounded-admin",
    )
    upload_id = str(upload.id)
    queued_id = queued["job_id"]
    handle = _SessionHandle(db)
    seen = []
    claims = []
    real_claim = ProcessingJobService.claim_next

    def _record(job_id, worker_id):
        seen.append((job_id, worker_id))

    def _claim(session, worker_id):
        found = real_claim(session, worker_id)
        claims.append(found)
        if len(claims) > 3:
            raise AssertionError("worker once did not stop")
        return found

    monkeypatch.setattr(worker, "SessionLocal", handle)
    monkeypatch.setattr(worker, "process_job_once", _record)
    monkeypatch.setattr(ProcessingJobService, "claim_next", _claim)
    assert settings.PMS_EVALUATION_APPLY_JOBS_ENABLED is False

    def _closed_session():
        raise AssertionError("disabled tick opened a session")

    monkeypatch.setattr(worker, "SessionLocal", _closed_session)
    worker._run_optional_evaluation_tick("worker-test")
    monkeypatch.setattr(worker, "SessionLocal", handle)
    worker.run_worker(once=True)
    assert claims == [upload_id, None]
    assert [item[0] for item in seen] == [upload_id]
    assert _job(db, queued_id).status == "queued"
    assert int(_job(db, queued_id).attempt_count or 0) == 0
    assert _job(db, upload_id).status == "running"

    monkeypatch.setattr(settings, "PMS_EVALUATION_APPLY_JOBS_ENABLED", True)
    fallback = _fallback_data_version
    claims.clear()
    worker.run_worker(once=True)
    assert claims == [None]
    assert [item[0] for item in seen] == [upload_id]
    assert _job(db, queued_id).status == "succeeded"
    assert int(_job(db, queued["job_id"]).progress or 0) == 100
    assert db.query(EvaluationRevision).count() == 1
    outbox = db.query(CacheInvalidationOutbox).one()
    assert outbox.published_at is None
    assert outbox.last_error == "cache delivery increment failed"
    assert _fallback_data_version == fallback
    assert isinstance(evaluation_cache_identity(db), str)


def test_page_budget_resumes_live_owned_lease_without_restarting_epoch(db, monkeypatch):
    _block_apply(monkeypatch)
    clock = _Clock(START)
    world, prepared = _prepared(db, ((7, [("C-1", "Ada Sentinel", "60"), ("C-2", "Ben Sentinel", "30")]),))
    queued = _coordinator(db, clock).enqueue(world.actor, prepared[7]["scope"]["id"], 2026, 7, enabled=True)
    first = _runtime(db, clock, page_size=1, max_pages=1).run_tick(enabled=True)
    assert first["advanced"] == 1
    assert _control(db, queued["job_id"]).staged_count == 1
    stranger = EvaluationApplyRuntime(db, "different-worker", clock=clock, lease_seconds=30, page_size=1, max_pages=1)
    assert stranger.run_tick(enabled=True)["considered"] == 0
    assert _control(db, queued["job_id"]).staged_count == 1
    second = _runtime(db, clock, page_size=1, max_pages=1).run_tick(enabled=True)
    assert second["advanced"] == 1
    assert _job(db, queued["job_id"]).status == "succeeded"
    assert _control(db, queued["job_id"]).claim_epoch == 0
    assert _job(db, queued["job_id"]).attempt_count == 1
    assert db.query(EvaluationApplyStageRow).count() == 2
    assert db.query(EvaluationRevision).count() == 1
    assert db.query(CacheInvalidationOutbox).count() == 1


def test_latest_open_binding_beats_cancelled_uuid_when_created_dates_tie(db, api, monkeypatch):
    from sqlalchemy import event
    monkeypatch.setattr(settings, "PMS_EVALUATION_APPLY_JOBS_ENABLED", True)
    clock = _Clock(START)
    world, prepared = _prepared(db, ((7, [("C-1", "Ada Sentinel", "60")]),))
    coordinator = _coordinator(db, clock)
    original_uuid = uuid.uuid4
    def enqueue(chosen):
        first = [True]
        def next_uuid():
            if first[0]:
                first[0] = False
                return uuid.UUID(chosen)
            return original_uuid()
        with monkeypatch.context() as patch:
            patch.setattr(uuid, "uuid4", next_uuid)
            return coordinator.enqueue(world.actor, prepared[7]["scope"]["id"], 2026, 7, enabled=True)
    def same_second(_mapper, _connection, row):
        row.created_at = START
    event.listen(ProcessingJob, "before_insert", same_second)
    event.listen(ProcessingJob, "before_update", same_second)
    try:
        old = enqueue("ffffffff-ffff-4fff-8fff-ffffffffffff")
        coordinator.cancel(world.actor, old["job_id"], enabled=True)
        new = enqueue("00000000-0000-4000-8000-000000000001")
    finally:
        event.remove(ProcessingJob, "before_insert", same_second)
        event.remove(ProcessingJob, "before_update", same_second)
    dates = [row.created_at for row in db.query(ProcessingJob).all()]
    assert len(dates) == 2 and dates[0] == dates[1]
    response = api.get(f"{PREFIX}/apply-jobs", headers=_headers(db, world.admin_id),
                       params={"scope_id": str(prepared[7]["scope"]["id"]), "year": 2026, "month": 7})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["job"]["job_id"] == new["job_id"]
    assert response.json()["data"]["job"]["state"] == "pending"


def test_admission_chronology_and_server_management_hints(db, api, monkeypatch):
    monkeypatch.setattr(settings, "PMS_EVALUATION_APPLY_JOBS_ENABLED", True)
    clock = _Clock(START)
    world, prepared = _prepared(db, ((7, [("C-1", "Ada Sentinel", "60")]),))
    coordinator = _coordinator(db, clock)
    old = coordinator.enqueue(world.actor, prepared[7]["scope"]["id"], 2026, 7, enabled=True)
    coordinator.cancel(world.actor, old["job_id"], enabled=True)
    new = coordinator.enqueue(world.actor, prepared[7]["scope"]["id"], 2026, 7, enabled=True)
    assert _job(db, new["job_id"]).created_at > _job(db, old["job_id"]).created_at
    other = _user(db, "Admin", "management-hint-admin")
    other_id = other.id
    response = api.get(f"{PREFIX}/apply-jobs/{new['job_id']}", headers=_headers(db, other_id))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["can_cancel"] is True and data["can_retry"] is False and data["can_recover"] is False
    token = coordinator.start(world.actor, new["job_id"], "worker-runtime", lease_seconds=30, enabled=True)
    coordinator.fail_live(world.actor, token, reason="evidence_changed", enabled=True)
    owner = api.get(f"{PREFIX}/apply-jobs/{new['job_id']}", headers=_headers(db, world.admin_id)).json()["data"]
    assert owner["safe_reason"] == "evidence_changed" and owner["can_retry"] is True
    denied = api.get(f"{PREFIX}/apply-jobs/{new['job_id']}", headers=_headers(db, other_id)).json()["data"]
    assert denied["can_retry"] is False
