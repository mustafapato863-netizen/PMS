"""Lease coordinator for one persisted evaluation apply.

The evaluation runtime and settings routes call this module only when
``PMS_EVALUATION_APPLY_JOBS_ENABLED is True``. Every operation still returns
immediately unless ``enabled is True``. A truthy value is not enough.
Disabled calls do not touch the session, the clock, or a client.

Any persisted active Admin may inspect a job, cancel it, or acknowledge an
already committed promotion. Those calls keep ``requested_by_user_id`` and
``actor_snapshot`` unchanged. When the caller is not the captured requester,
the same transaction writes one ``audit_log`` row: old and new job and
control state, the claim epoch, and the original requester id. It does not
store the snapshot, a source array, a name, or an error string.
``performed_by`` is the Admin who made the call.

Start, heartbeat, stage, promote, acknowledge, live failure, and retry of
the same job stay with the captured requester. The actor snapshot is not a
role grant and is never used to impersonate a revoked or deleted requester.
Another Admin who wants a new attempt cancels the unpromoted job and
enqueues a new job. Historical stage rows stay on the old job and epoch.

The grant is a non-locking user read after the team, job, scope, and control
fences. The shared team fence also reads the user before those header locks.
That earlier row is not the grant. A role change committed after the later
read is not held off for the rest of the transaction.

Lock order stays team, processing job, evaluation scope, apply control, then
the records taken by the existing stage and promote code. Claim epoch changes
on the job first, then the control. This module does not lock the user and
does not lock the control before the job.

``promote`` commits the accepted score, revision, and outbox write while the
job stays ``running`` and progress stays below 100. ``acknowledge`` is a later
transaction for the same worker, epoch, and unexpired lease. ``recover`` is
the management path for the crash between those commits: a matching epoch
acknowledges a still-running promoted job even after the lease has expired; a
stale epoch returns the committed revision and writes nothing. Neither path
inserts a second revision or outbox row. ``fail_live`` fails one live staging
token. A promoted control is left in place.

A running staging row with no lease is the public capture, not an expired
worker job. Retry does not adopt it. An expired worker lease is failed in its
own commit before the next epoch opens.

Enabled calls that use time read the clock once before SQL and discard that
reading when it is aware. A naive clock still raises ``invalid_clock`` with
no SQL. The admission instant is a later reading, taken after that call's
team, job, scope, and control fences are held. Live-lease checks and the
timestamps written in the transaction use that instant. Retry reads again
after each of its two fences. The instant is not read again at commit: a
page or promotion that continues after admission can still commit if the
clock moves during that later work.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm.attributes import flag_modified

import services.evaluation.bounded_apply as bounded_apply_module
from models.models import AuditLog, EvaluationApplyControl, ProcessingJob
from services.evaluation.access import EvaluationError
from services.evaluation.apply_job_schema import JOB_KIND_EVALUATION_APPLY, STATUS_PAYLOAD_LIMIT
from services.evaluation.bounded_apply import BoundedApplyService, _page_size
from services.evaluation.workflow import EvaluationConflict


logger = logging.getLogger(__name__)

MIN_LEASE_SECONDS = 1
MAX_LEASE_SECONDS = 3600
MAX_WORKER_ID = 150
SAFE_REASONS = {
    "cancelled": "cancelled",
    "lease_expired": "lease_expired",
}
SAFE_FAILURE_REASONS = frozenset({
    "access_denied",
    "apply_failed",
    "evidence_changed",
    "incomplete_stage",
    "invalid_state",
    "lineage_changed",
    "scope_blocked",
    "stale_preview",
    "target_conflict",
})
AUDIT_TABLE = "evaluation_apply_controls"
AUDIT_OPERATION = "UPDATE"


class LeaseCoordinatorError(EvaluationError):
    """Bounded coordinator failure. The message is a stable code, not row data."""

    def __init__(self, code: str) -> None:
        super().__init__(code, code=code)
        self.code = code


def _disabled() -> dict:
    return {"enabled": False, "outcome": "disabled"}


def require_lease_seconds(value) -> int:
    """Accept only a real integer from 1 through 3600. Booleans are rejected."""

    if type(value) is not int or value < MIN_LEASE_SECONDS or value > MAX_LEASE_SECONDS:
        raise LeaseCoordinatorError("invalid_lease_seconds")
    return value


def require_worker_id(value) -> str:
    """Accept one short visible token. Do not trim or truncate it."""

    if type(value) is not str or not value or len(value) > MAX_WORKER_ID:
        raise LeaseCoordinatorError("invalid_worker_id")
    if any(ord(char) < 33 or ord(char) == 127 for char in value):
        raise LeaseCoordinatorError("invalid_worker_id")
    return value


def require_epoch(value) -> int:
    """Accept only a non-negative integer. ``True`` is not epoch 1."""

    if type(value) is not int or value < 0:
        raise LeaseCoordinatorError("invalid_epoch")
    return value


def _safe_failure_reason(value) -> str:
    """Accept one stable code. Exception text is not a reason."""

    if type(value) is not str or value not in SAFE_FAILURE_REASONS:
        raise LeaseCoordinatorError("invalid_state")
    return value


def _stored_epoch(value) -> int:
    """Read a persisted epoch. Zero stays zero; booleans are not integers here."""

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LeaseCoordinatorError("stale_epoch")
    return value


def _same_epoch(job, control) -> int:
    job_epoch = _stored_epoch(job.claim_epoch)
    control_epoch = _stored_epoch(control.claim_epoch)
    if job_epoch != control_epoch:
        raise LeaseCoordinatorError("stale_epoch")
    return job_epoch


def require_period(year, month) -> tuple[int, int]:
    """Accept an exact calendar year and month. Floats and booleans are rejected."""

    if type(year) is not int or year < 2000 or year > 2100:
        raise LeaseCoordinatorError("invalid_period")
    if type(month) is not int or month < 1 or month > 12:
        raise LeaseCoordinatorError("invalid_period")
    return year, month


def _parse_job(value) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise EvaluationError("Evaluation apply was not found.", code="not_found") from exc


def _parse_token(token) -> tuple[uuid.UUID, str, int]:
    if not isinstance(token, dict):
        raise LeaseCoordinatorError("stale_token")
    return _parse_job(token.get("job_id")), require_worker_id(token.get("worker_id")), require_epoch(token.get("claim_epoch"))


def _as_utc(value) -> datetime:
    if not isinstance(value, datetime):
        raise LeaseCoordinatorError("invalid_state")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat()


def _stage_progress(staged: int, expected: int) -> int:
    """Map a committed page count to progress and keep 100 for acknowledgement."""

    if type(staged) is not int or type(expected) is not int or expected < 1 or staged < 0:
        raise LeaseCoordinatorError("invalid_state")
    if staged <= 0:
        return 0
    if staged >= expected:
        return 99
    return min(99, (staged * 99) // expected)


def _ack_body(control) -> dict:
    body = {
        "outcome": "promoted",
        "revision_id": str(control.promoted_revision_id),
        "count": int(control.promoted_count or 0),
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    if len(encoded) > STATUS_PAYLOAD_LIMIT:
        raise LeaseCoordinatorError("persistence_failed")
    return body


def _acked(job, control) -> bool:
    result = job.result_json if isinstance(job.result_json, dict) else {}
    return result.get("outcome") == "promoted" and result.get("revision_id") == str(control.promoted_revision_id)


class EvaluationLeaseCoordinator:
    """Explicit enqueue, claim, page, promote, and recovery for one job id."""

    def __init__(self, db, clock=None) -> None:
        self.db = db
        self.clock = clock
        self._service = None

    def enqueue(self, actor, scope_id, year, month, *, enabled: bool = False) -> dict:
        """Persist one queued pending binding, or repeat that same binding."""

        if enabled is not True:
            return _disabled()
        checked_year, checked_month = require_period(year, month)
        self._require_clock()
        return self._guard(lambda: self._enqueue(actor, scope_id, checked_year, checked_month))

    def start(self, actor, job_id, worker_id, *, lease_seconds=None, enabled: bool = False) -> dict:
        """Claim one specified queued job. This is not a polling loop."""

        if enabled is not True:
            return _disabled()
        worker = require_worker_id(worker_id)
        lease = require_lease_seconds(lease_seconds)
        parsed = _parse_job(job_id)
        self._require_clock()
        return self._guard(lambda: self._start(actor, parsed, worker, lease))

    def heartbeat(self, actor, token, *, lease_seconds=None, enabled: bool = False) -> dict:
        """Extend one live lease. Progress and epoch stay unchanged."""

        if enabled is not True:
            return _disabled()
        parsed, worker, epoch = _parse_token(token)
        lease = require_lease_seconds(lease_seconds)
        self._require_clock()
        return self._guard(lambda: self._heartbeat(actor, parsed, worker, epoch, lease))

    def stage_page(self, actor, token, *, lease_seconds=None, page_size: int = 100, enabled: bool = False) -> dict:
        """Stage one keyset page under the lease already held by this call."""

        if enabled is not True:
            return _disabled()
        parsed, worker, epoch = _parse_token(token)
        lease = require_lease_seconds(lease_seconds)
        size = _page_size(page_size)
        self._require_clock()
        return self._guard(lambda: self._stage(actor, parsed, worker, epoch, lease, size))

    def promote(self, actor, token, *, enabled: bool = False) -> dict:
        """Commit promotion and leave job acknowledgement to a later call."""

        if enabled is not True:
            return _disabled()
        parsed, worker, epoch = _parse_token(token)
        self._require_clock()
        return self._guard(lambda: self._promote(actor, parsed, worker, epoch))

    def acknowledge(self, actor, token, *, enabled: bool = False) -> dict:
        """Mark one promoted running job succeeded for its current lease."""

        if enabled is not True:
            return _disabled()
        parsed, worker, epoch = _parse_token(token)
        self._require_clock()
        return self._guard(lambda: self._acknowledge(actor, parsed, worker, epoch))

    def recover(self, actor, job_id, *, expected_epoch=None, enabled: bool = False) -> dict:
        """Report a committed promotion. A matching epoch can acknowledge it."""

        if enabled is not True:
            return _disabled()
        epoch = require_epoch(expected_epoch)
        parsed = _parse_job(job_id)
        self._require_clock()
        return self._guard(lambda: self._recover(actor, parsed, epoch))

    def status(self, actor, job_id, *, enabled: bool = False) -> dict:
        """Return counts, cursor, state, epoch, revision, and a safe reason."""

        if enabled is not True:
            return _disabled()
        parsed = _parse_job(job_id)
        return self._guard(lambda: self._status(actor, parsed))

    def cancel(self, actor, job_id, *, enabled: bool = False) -> dict:
        """Cancel pending or staging work and drop the current token."""

        if enabled is not True:
            return _disabled()
        parsed = _parse_job(job_id)
        self._require_clock()
        return self._guard(lambda: self._cancel(actor, parsed))

    def retry(self, actor, job_id, *, enabled: bool = False) -> dict:
        """Move failed, cancelled, or expired work to a new pending epoch."""

        if enabled is not True:
            return _disabled()
        parsed = _parse_job(job_id)
        self._require_clock()
        return self._guard(lambda: self._retry(actor, parsed))

    def fail_live(self, actor, token, *, reason=None, enabled: bool = False) -> dict:
        """Fail one live staging token without rewriting a promoted commit."""

        if enabled is not True:
            return _disabled()
        parsed, worker, epoch = _parse_token(token)
        safe = _safe_failure_reason(reason)
        self._require_clock()
        return self._guard(lambda: self._fail_live(actor, parsed, worker, epoch, safe))

    def _enqueue(self, actor, scope_id, year: int, month: int) -> dict:
        body = self._apply().capture_queued(actor, scope_id, year, month)
        job_id = uuid.UUID(str(body["job_id"]))
        job = self.db.query(ProcessingJob).populate_existing().filter(ProcessingJob.id == job_id).one()
        control = (
            self.db.query(EvaluationApplyControl)
            .populate_existing()
            .filter(EvaluationApplyControl.job_id == job_id)
            .one()
        )
        actor_id = uuid.UUID(str((actor or {}).get("user_id")))
        if control.requested_by_user_id != actor_id or job.status != "queued" or control.state != "pending":
            raise EvaluationConflict(
                "An evaluation apply is already open for this month.",
                code="duplicate_binding",
            )
        if not body["resumed"]:
            now = self._admit()
            job.available_at = now
            # Admission is serialized by the Team fence. UUIDs are not clocks.
            previous = (
                self.db.query(ProcessingJob.created_at)
                .join(EvaluationApplyControl, EvaluationApplyControl.job_id == ProcessingJob.id)
                .filter(EvaluationApplyControl.scope_id == control.scope_id,
                        EvaluationApplyControl.year == year, EvaluationApplyControl.month == month,
                        ProcessingJob.id != job.id)
                .order_by(ProcessingJob.created_at.desc()).limit(1).scalar()
            )
            job.created_at = max(now, _as_utc(previous) + timedelta(microseconds=1)) if previous else now
            job.worker_id = None
            job.lease_expires_at = None
            job.heartbeat_at = None
            job.progress = 0
            job.attempt_count = int(job.attempt_count or 0)
        if job.worker_id is not None or job.lease_expires_at is not None or int(job.progress or 0) != 0:
            raise LeaseCoordinatorError("invalid_state")
        payload = {
            "enabled": True,
            "outcome": "queued",
            "job_id": str(job.id),
            "state": control.state,
            "job_status": job.status,
            "claim_epoch": _same_epoch(job, control),
            "expected_count": int(body["expected_count"]),
            "resumed": bool(body["resumed"]),
        }
        self._commit()
        return payload

    def _start(self, actor, job_id, worker: str, lease: int) -> dict:
        _user, job, control, _scope = self._locked(actor, job_id)
        now = self._admit()
        if job.status == "running" and control.state == "staging" and self._lease_active(job, now):
            raise LeaseCoordinatorError("lease_held")
        if job.status != "queued" or control.state != "pending":
            raise LeaseCoordinatorError("invalid_state")
        if job.worker_id is not None or job.lease_expires_at is not None:
            raise LeaseCoordinatorError("lease_held")
        _same_epoch(job, control)
        if _as_utc(job.available_at) > now:
            raise LeaseCoordinatorError("invalid_state")
        if int(job.attempt_count or 0) >= int(job.max_attempts or 1):
            raise LeaseCoordinatorError("attempts_exhausted")
        job.status = "running"
        job.attempt_count = int(job.attempt_count or 0) + 1
        job.worker_id = worker
        job.started_at = now
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=lease)
        control.state = "staging"
        self.db.flush()
        payload = self._token(job, control, "running")
        payload["attempt_count"] = int(job.attempt_count)
        self._commit()
        return payload

    def _heartbeat(self, actor, job_id, worker: str, epoch: int, lease: int) -> dict:
        _user, job, control, _scope = self._locked(actor, job_id)
        now = self._admit()
        self._require_live(job, control, worker, epoch, now)
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=lease)
        self.db.flush()
        payload = self._token(job, control, "heartbeat")
        self._commit()
        return payload

    def _stage(self, actor, job_id, worker: str, epoch: int, lease: int, page_size: int) -> dict:
        _user, job, control, _scope = self._locked(actor, job_id)
        now = self._admit()
        self._require_live(job, control, worker, epoch, now)
        page = self._apply()._stage_page(
            actor,
            job.id,
            page_size=page_size,
            cursor=None,
            replay=False,
            expected_epoch=epoch,
        )
        progress = _stage_progress(int(page["staged_count"]), self._apply()._expected_count(job))
        job.progress = progress
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=lease)
        self.db.flush()
        payload = {
            "enabled": True,
            "outcome": "staged",
            "progress": progress,
            "job_id": page["job_id"],
            "claim_epoch": page["claim_epoch"],
            "page_count": page["page_count"],
            "inserted_count": page["inserted_count"],
            "staged_count": page["staged_count"],
            "complete": page["complete"],
            "idempotent": page["idempotent"],
            "lease_expires_at": _iso(job.lease_expires_at),
        }
        self._commit()
        return payload

    def _promote(self, actor, job_id, worker: str, epoch: int) -> dict:
        _user, job, control, _scope = self._locked(actor, job_id)
        now = self._admit()
        self._require_epoch(job, control, epoch)
        if control.state == "promoted" and control.promoted_revision_id is not None:
            if job.worker_id not in {None, worker}:
                raise LeaseCoordinatorError("stale_token")
            return self._release(self._promoted_body(job, control, acknowledged=False, idempotent=True))
        self._require_worker(job, worker)
        self._require_running(job, control, now)
        body = self._apply()._promote(actor, job.id, expected_epoch=epoch, acknowledge_job=False)
        payload = {
            "enabled": True,
            "outcome": "promoted",
            "acknowledged": False,
            "idempotent": bool(body["idempotent"]),
            "job_id": body["job_id"],
            "revision_id": body["revision_id"],
            "applied_count": body["applied_count"],
            "state": body["state"],
            "claim_epoch": epoch,
        }
        self._commit()
        return payload

    def _acknowledge(self, actor, job_id, worker: str, epoch: int) -> dict:
        _user, job, control, _scope = self._locked(actor, job_id)
        now = self._admit()
        self._require_epoch(job, control, epoch)
        if control.state != "promoted" or control.promoted_revision_id is None:
            raise LeaseCoordinatorError("invalid_state")
        if job.status == "succeeded" and job.worker_id in {None, worker} and _acked(job, control):
            return self._release(self._ack_payload(job, control, idempotent=True))
        self._require_worker(job, worker)
        if job.status != "running" or not self._lease_active(job, now):
            raise LeaseCoordinatorError("lease_expired" if job.status == "running" else "invalid_state")
        self._write_ack(job, control, now)
        self._apply()._fault("before_commit")
        payload = self._ack_payload(job, control, idempotent=False)
        self._commit()
        return payload

    def _recover(self, actor, job_id, epoch: int) -> dict:
        user, job, control, _scope = self._locked(actor, job_id, owner_required=False)
        now = self._admit()
        identity = self._identity(job, control)
        remembered = self._remembered(job, control)
        current = _same_epoch(job, control)
        promoted = control.state == "promoted" and control.promoted_revision_id is not None
        if not promoted or job.status != "running" or current != epoch:
            outcome = "promoted" if promoted else "observed"
            idempotent = bool(promoted and job.status == "succeeded" and _acked(job, control))
            payload = self._recovery_body(job, control, outcome=outcome, mutated=False, idempotent=idempotent)
            return self._finish_read(user, job, control, identity, remembered, "recover", payload)
        self._write_ack(job, control, now)
        self._require_same_identity(identity, job, control)
        self._audit_cross_admin(user, job, control, remembered, "recover")
        self._apply()._fault("before_commit")
        payload = self._recovery_body(job, control, outcome="recovered", mutated=True, idempotent=False)
        self._commit()
        return payload

    def _status(self, actor, job_id) -> dict:
        user, job, control, _scope = self._locked(actor, job_id, owner_required=False)
        identity = self._identity(job, control)
        remembered = self._remembered(job, control)
        epoch = _same_epoch(job, control)
        payload = {
            "enabled": True,
            "outcome": "status",
            "job_id": str(job.id),
            "state": control.state,
            "job_status": job.status,
            "claim_epoch": epoch,
            "staged_count": int(control.staged_count or 0),
            "promoted_count": int(control.promoted_count or 0),
            "stage_cursor": control.stage_cursor or "",
            "revision_id": None if control.promoted_revision_id is None else str(control.promoted_revision_id),
            "progress": int(job.progress or 0),
            "attempt_count": int(job.attempt_count or 0),
            "safe_reason": job.error_code if job.error_code in SAFE_FAILURE_REASONS else SAFE_REASONS.get(job.error_code),
        }
        return self._finish_read(user, job, control, identity, remembered, "inspect", payload)

    def _cancel(self, actor, job_id) -> dict:
        user, job, control, _scope = self._locked(actor, job_id, owner_required=False)
        now = self._admit()
        identity = self._identity(job, control)
        remembered = self._remembered(job, control)
        if control.state in {"promoted", "promoting"} or job.status == "succeeded":
            raise LeaseCoordinatorError("invalid_state")
        if control.state == "cancelled" and job.status == "cancelled":
            payload = self._terminal(job, control, "cancelled", idempotent=True)
            return self._finish_read(user, job, control, identity, remembered, "cancel", payload)
        if control.state not in {"pending", "staging"} or job.status not in {"queued", "running"}:
            raise LeaseCoordinatorError("invalid_state")
        control.state = "cancelled"
        job.status = "cancelled"
        job.worker_id = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        job.finished_at = now
        job.error_code = "cancelled"
        job.safe_error_message = "cancelled"
        if int(job.progress or 0) > 99:
            job.progress = 99
        self.db.flush()
        self._require_same_identity(identity, job, control)
        self._audit_cross_admin(user, job, control, remembered, "cancel")
        payload = self._terminal(job, control, "cancelled", idempotent=False)
        self._commit()
        return payload

    def _fail_live(self, actor, job_id, worker: str, epoch: int, reason: str) -> dict:
        _user, job, control, _scope = self._locked(actor, job_id)
        now = self._admit()
        identity = self._identity(job, control)
        self._require_epoch(job, control, epoch)
        if control.state == "promoted" or job.status == "succeeded" or control.promoted_revision_id is not None:
            if control.promoted_revision_id is None:
                raise LeaseCoordinatorError("invalid_state")
            body = self._promoted_body(
                job,
                control,
                acknowledged=job.status == "succeeded",
                idempotent=True,
            )
            body["outcome"] = "preserved"
            return self._release(body)
        self._require_worker(job, worker)
        if job.status != "running" or control.state != "staging":
            raise LeaseCoordinatorError("invalid_state")
        if not self._lease_active(job, now):
            raise LeaseCoordinatorError("lease_expired")
        control.state = "failed"
        job.status = "failed"
        job.worker_id = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        job.finished_at = now
        job.error_code = reason
        job.safe_error_message = "evaluation apply failed"
        if int(job.progress or 0) > 99:
            job.progress = 99
        self.db.flush()
        self._require_same_identity(identity, job, control)
        payload = self._terminal(job, control, "failed", idempotent=False)
        self._commit()
        return payload

    def _retry(self, actor, job_id) -> dict:
        self._close_expired(actor, job_id)
        return self._open_retry(actor, job_id)

    def _close_expired(self, actor, job_id) -> None:
        """Persist staging to failed before a retry may open the next epoch."""

        _user, job, control, _scope = self._locked(actor, job_id)
        now = self._admit()
        if job.status != "running" or control.state != "staging":
            self._rollback()
            return
        if job.lease_expires_at is None or self._lease_active(job, now):
            raise LeaseCoordinatorError("invalid_state")
        control.state = "failed"
        job.status = "failed"
        job.worker_id = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        job.finished_at = now
        job.error_code = "lease_expired"
        job.safe_error_message = "The worker lease expired."
        if int(job.progress or 0) > 99:
            job.progress = 99
        self.db.flush()
        self._commit()

    def _open_retry(self, actor, job_id) -> dict:
        _user, job, control, scope = self._locked(actor, job_id)
        now = self._admit()
        if control.state not in {"failed", "cancelled"} or job.status not in {"failed", "cancelled"}:
            raise LeaseCoordinatorError("invalid_state")
        if control.requested_by_user_id is None:
            raise EvaluationError("Evaluation settings are limited to Admin.", code="access_denied")
        if int(job.attempt_count or 0) >= int(job.max_attempts or 1):
            raise LeaseCoordinatorError("attempts_exhausted")
        current = _same_epoch(job, control)
        self._matches_captured(scope, control, job)
        new_epoch = current + 1
        # The job epoch is flushed before the control leaves failed or cancelled.
        job.claim_epoch = new_epoch
        self.db.flush()
        control.state = "pending"
        control.claim_epoch = new_epoch
        control.staged_count = 0
        control.promoted_count = 0
        control.promoted_revision_id = None
        control.stage_cursor = None
        self.db.flush()
        job.status = "queued"
        job.progress = 0
        job.worker_id = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        job.started_at = None
        job.finished_at = None
        job.error_code = None
        job.safe_error_message = None
        job.result_json = None
        job.available_at = now
        flag_modified(job, "result_json")
        self.db.flush()
        payload = {
            "enabled": True,
            "outcome": "retry",
            "job_id": str(job.id),
            "state": "pending",
            "job_status": "queued",
            "claim_epoch": new_epoch,
            "attempt_count": int(job.attempt_count or 0),
        }
        self._commit()
        return payload

    def _matches_captured(self, scope, control, job) -> None:
        """Reuse the promotion fences. Do not write a replacement control."""

        apply = self._apply()
        version, _resolved, rules = apply._approved_version(scope, control.year, control.month, lock=True)
        apply._require_captured_version(control, version, rules)
        if control.engine_version != bounded_apply_module.ENGINE_VERSION:
            raise EvaluationConflict("The scoring engine changed before this apply could finish.", code="stale_preview")
        proof = apply._proof_header(version, scope, rules)
        if rules != control.rules_checksum or proof.get("source_fingerprint") != control.proof_source_fingerprint:
            raise EvaluationConflict("Approved rules or proof changed before this apply could finish.", code="stale_preview")
        lineage = apply._lineage_fingerprint(scope, control.year, control.month)
        if lineage != control.lineage_fingerprint:
            raise EvaluationConflict("Revision lineage changed before promotion.", code="lineage_changed")
        fingerprint, live_count = apply._stream_source(scope, control.year, control.month, lock=True)
        expected = apply._expected_count(job)
        if fingerprint != control.proof_source_fingerprint or live_count != expected:
            raise EvaluationConflict(
                "Stored evidence changed before promotion. Nothing was promoted.",
                code="evidence_changed",
            )

    def _write_ack(self, job, control, now: datetime) -> None:
        job.status = "succeeded"
        job.progress = 100
        job.result_json = _ack_body(control)
        flag_modified(job, "result_json")
        job.error_code = None
        job.safe_error_message = None
        job.finished_at = now
        job.worker_id = None
        job.lease_expires_at = None
        self.db.flush()

    def _require_live(self, job, control, worker: str, epoch: int, now: datetime) -> None:
        self._require_epoch(job, control, epoch)
        self._require_worker(job, worker)
        self._require_running(job, control, now)

    def _require_epoch(self, job, control, epoch: int) -> None:
        if _same_epoch(job, control) != epoch:
            raise LeaseCoordinatorError("stale_epoch")

    def _require_worker(self, job, worker: str) -> None:
        if job.worker_id != worker:
            raise LeaseCoordinatorError("stale_token")

    def _require_running(self, job, control, now: datetime) -> None:
        if job.status != "running" or control.state != "staging":
            raise LeaseCoordinatorError("invalid_state")
        if not self._lease_active(job, now):
            raise LeaseCoordinatorError("lease_expired")

    def _lease_active(self, job, now: datetime) -> bool:
        if job.lease_expires_at is None:
            return False
        return _as_utc(job.lease_expires_at) > now

    def _locked(self, actor, job_id, *, owner_required: bool = True):
        """Lock team, job, scope, and control, then reread the caller.

        The user row returned by the team fence is stale for authorization.
        ``_admin`` after the header locks is the grant. A revocation that
        commits after that second read is outside this transaction.
        """

        apply = self._apply()
        kind = self.db.query(ProcessingJob.kind).filter(ProcessingJob.id == job_id).scalar()
        peeked = apply._peek_control(job_id)
        if kind != JOB_KIND_EVALUATION_APPLY or peeked is None or peeked.team_id is None:
            raise EvaluationError("Evaluation apply was not found.", code="not_found")
        team, _earlier_user = apply._team_fence(peeked.team_id, actor)
        job, control, scope = apply._lock_existing_header(peeked, team)
        user = apply._admin(actor)
        if owner_required:
            apply._require_open_actor(control, user)
        return user, job, control, scope

    def _identity(self, job, control):
        snapshot = control.actor_snapshot
        if isinstance(snapshot, dict):
            snapshot = json.dumps(snapshot, sort_keys=True, default=str)
        return (job.requested_by_user_id, job.requested_by_name, control.requested_by_user_id, snapshot)

    def _require_same_identity(self, identity, job, control) -> None:
        if self._identity(job, control) != identity:
            raise LeaseCoordinatorError("invalid_state")

    def _remembered(self, job, control) -> tuple[str, str, int]:
        return job.status, control.state, int(control.claim_epoch)

    def _cross_admin(self, user, control) -> bool:
        return control.requested_by_user_id != user.id

    def _audit_cross_admin(self, user, job, control, remembered, action: str) -> None:
        """One safe audit row. Names, snapshots, and errors stay out of it."""

        if not self._cross_admin(user, control):
            return
        old_status, old_state, old_epoch = remembered
        requester = None if control.requested_by_user_id is None else str(control.requested_by_user_id)
        old_values = {
            "action": action,
            "claim_epoch": old_epoch,
            "control_state": old_state,
            "job_status": old_status,
            "requested_by_user_id": requester,
        }
        new_values = {
            "action": action,
            "claim_epoch": int(control.claim_epoch),
            "control_state": control.state,
            "job_status": job.status,
            "requested_by_user_id": requester,
        }
        self.db.add(AuditLog(
            id=uuid.uuid4(),
            table_name=AUDIT_TABLE,
            operation=AUDIT_OPERATION,
            record_id=job.id,
            old_values=old_values,
            new_values=new_values,
            performed_by_user_id=user.id,
        ))
        self.db.flush()

    def _finish_read(self, user, job, control, identity, remembered, action: str, payload: dict) -> dict:
        self._require_same_identity(identity, job, control)
        if not self._cross_admin(user, control):
            return self._release(payload)
        self._audit_cross_admin(user, job, control, remembered, action)
        self._commit()
        return payload

    def _apply(self) -> BoundedApplyService:
        if self._service is None:
            self._service = BoundedApplyService(self.db)
        return self._service

    def _require_clock(self) -> None:
        """Reject a naive clock before SQL. This reading is not admission time."""

        self._now()

    def _admit(self) -> datetime:
        """Read the clock after this transaction's fences are already held."""

        return self._now()

    def _now(self) -> datetime:
        clock = self.clock
        current = datetime.now(timezone.utc) if clock is None else clock()
        if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
            raise LeaseCoordinatorError("invalid_clock")
        return current

    def _token(self, job, control, outcome: str) -> dict:
        return {
            "enabled": True,
            "outcome": outcome,
            "job_id": str(job.id),
            "worker_id": job.worker_id,
            "claim_epoch": _stored_epoch(control.claim_epoch),
            "lease_expires_at": _iso(job.lease_expires_at),
        }

    def _promoted_body(self, job, control, *, acknowledged: bool, idempotent: bool) -> dict:
        return {
            "enabled": True,
            "outcome": "promoted",
            "acknowledged": acknowledged,
            "idempotent": idempotent,
            "job_id": str(job.id),
            "revision_id": str(control.promoted_revision_id),
            "applied_count": int(control.promoted_count or 0),
            "state": control.state,
            "claim_epoch": int(control.claim_epoch),
            "job_status": job.status,
        }

    def _ack_payload(self, job, control, *, idempotent: bool) -> dict:
        return {
            "enabled": True,
            "outcome": "acknowledged",
            "idempotent": idempotent,
            "job_id": str(job.id),
            "revision_id": str(control.promoted_revision_id),
            "claim_epoch": int(control.claim_epoch),
            "progress": int(job.progress or 0),
        }

    def _recovery_body(self, job, control, *, outcome: str, mutated: bool, idempotent: bool) -> dict:
        return {
            "enabled": True,
            "outcome": outcome,
            "mutated": mutated,
            "idempotent": idempotent,
            "job_id": str(job.id),
            "state": control.state,
            "job_status": job.status,
            "claim_epoch": int(control.claim_epoch),
            "revision_id": None if control.promoted_revision_id is None else str(control.promoted_revision_id),
        }

    def _terminal(self, job, control, outcome: str, *, idempotent: bool) -> dict:
        return {
            "enabled": True,
            "outcome": outcome,
            "idempotent": idempotent,
            "job_id": str(job.id),
            "state": control.state,
            "job_status": job.status,
            "claim_epoch": int(control.claim_epoch),
        }

    def _release(self, payload: dict) -> dict:
        self._rollback()
        return payload

    def _commit(self) -> None:
        self.db.commit()
        self.db.expunge_all()

    def _rollback(self) -> None:
        try:
            self.db.rollback()
        except Exception:
            return
        try:
            self.db.expunge_all()
        except Exception:
            return

    def _guard(self, fn):
        try:
            return fn()
        except EvaluationError:
            self._rollback()
            raise
        except Exception:
            self._rollback()
            logger.warning("evaluation lease coordinator persistence failed")
            raise LeaseCoordinatorError("persistence_failed") from None
