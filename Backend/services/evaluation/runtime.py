"""Opt-in worker adapter for evaluation apply jobs.

``run_tick`` returns immediately unless ``enabled is True``. The worker
calls ``run_enabled_tick`` only when ``PMS_EVALUATION_APPLY_JOBS_ENABLED``
is the literal ``True``. Candidate reads are scalar and do not lock
``processing_jobs``. The coordinator takes the team fence before the job,
scope, and control rows.

A tick may start a queued job and page it to acknowledgement, reclaim an
expired staging lease, or acknowledge one promoted job that is still
running. It does not call the generic claim, heartbeat, or requeue helpers,
and it does not call ``EvaluationWorkflow.apply``. The execution actor is
the persisted requester id. The stored actor snapshot is not read.

Rows whose requester is no longer an active Admin are left out of the
candidate window. They stay for an explicit cancel and a new enqueue.
One denied row inside a tick does not stop the later rows.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, or_

from config import settings
from models.models import EvaluationApplyControl, ProcessingJob, User
from services.evaluation.access import EvaluationError
from services.evaluation.apply_job_schema import JOB_KIND_EVALUATION_APPLY
from services.evaluation.bounded_apply import _page_size
from services.evaluation.lease_coordinator import (
    SAFE_FAILURE_REASONS,
    EvaluationLeaseCoordinator,
    LeaseCoordinatorError,
    require_lease_seconds,
    require_worker_id,
)
from services.evaluation.outbox_publisher import CacheOutboxPublisher


logger = logging.getLogger(__name__)

DEFAULT_CANDIDATE_LIMIT = 8
MAX_CANDIDATE_LIMIT = 8
DEFAULT_MAX_PAGES = 25
MAX_PAGES = 25
PRESERVE_CODES = frozenset({
    "fault_injected",
    "lease_expired",
    "lease_held",
    "persistence_failed",
    "stale_epoch",
    "stale_token",
})


def _disabled_tick() -> dict:
    return {"enabled": False, "outcome": "disabled", "considered": 0, "advanced": 0, "skipped": 0}


def _bound(value, upper: int) -> int:
    if type(value) is not int or isinstance(value, bool) or value < 1 or value > upper:
        raise LeaseCoordinatorError("invalid_state")
    return value


def _execution_actor(user_id) -> dict:
    """The persisted requester id only. Role and snapshot are not copied."""

    return {"user_id": str(user_id)}


def _aware(value) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise LeaseCoordinatorError("invalid_clock")
    return value.astimezone(timezone.utc)


class EvaluationApplyRuntime:
    """Bounded selection and coordinator calls for one worker iteration."""

    def __init__(
        self,
        db,
        worker_id,
        *,
        clock=None,
        lease_seconds=None,
        page_size: int = 100,
        max_pages: int = DEFAULT_MAX_PAGES,
        candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    ) -> None:
        self.db = db
        self.worker_id = worker_id
        self.clock = clock
        self.lease_seconds = settings.PMS_JOB_LEASE_SECONDS if lease_seconds is None else lease_seconds
        self.page_size = page_size
        self.max_pages = max_pages
        self.candidate_limit = candidate_limit
        self._coordinator = None

    def run_tick(self, *, enabled: bool = False) -> dict:
        """Advance a bounded set of jobs, then leave the session committed."""

        if enabled is not True:
            return _disabled_tick()
        require_worker_id(self.worker_id)
        require_lease_seconds(self.lease_seconds)
        _page_size(self.page_size)
        _bound(self.max_pages, MAX_PAGES)
        _bound(self.candidate_limit, MAX_CANDIDATE_LIMIT)
        now = self._now()
        considered = 0
        advanced = 0
        skipped = 0
        for job_id in self._candidate_ids(now):
            considered += 1
            try:
                outcome = self._advance(job_id)
            except Exception:
                logger.warning("evaluation apply candidate skipped")
                self._rollback()
                skipped += 1
                continue
            if outcome in {"skipped", "fenced", "unresolved"}:
                skipped += 1
            else:
                advanced += 1
        return {
            "enabled": True,
            "outcome": "tick",
            "considered": considered,
            "advanced": advanced,
            "skipped": skipped,
        }

    def _candidate_ids(self, now: datetime) -> list:
        """Scalar ids only. This statement does not lock the job row."""

        queued = and_(
            ProcessingJob.status == "queued",
            EvaluationApplyControl.state == "pending",
            ProcessingJob.available_at <= now,
            ProcessingJob.attempt_count < ProcessingJob.max_attempts,
        )
        expired = and_(
            ProcessingJob.status == "running",
            EvaluationApplyControl.state == "staging",
            ProcessingJob.lease_expires_at.is_not(None),
            ProcessingJob.lease_expires_at <= now,
        )
        awaiting = and_(
            ProcessingJob.status == "running",
            EvaluationApplyControl.state == "promoted",
        )
        owned_live = and_(
            ProcessingJob.status == "running",
            EvaluationApplyControl.state == "staging",
            ProcessingJob.worker_id == self.worker_id,
            ProcessingJob.lease_expires_at > now,
        )
        rows = (
            self.db.query(ProcessingJob.id)
            .join(EvaluationApplyControl, EvaluationApplyControl.job_id == ProcessingJob.id)
            .join(User, User.id == EvaluationApplyControl.requested_by_user_id)
            .filter(
                ProcessingJob.kind == JOB_KIND_EVALUATION_APPLY,
                User.role == "Admin",
                User.is_active.is_(True),
                or_(queued, expired, awaiting, owned_live),
            )
            .order_by(ProcessingJob.available_at.asc(), ProcessingJob.id.asc())
            .limit(self.candidate_limit)
            .all()
        )
        found = [row[0] for row in rows]
        self._rollback()
        return found

    def _advance(self, job_id) -> str:
        header = self._header(job_id)
        if header is None or header["requested_by_user_id"] is None:
            return "skipped"
        actor = _execution_actor(header["requested_by_user_id"])
        coordinator = self._lease()
        if header["status"] == "queued" and header["state"] == "pending":
            token = coordinator.start(
                actor,
                job_id,
                self.worker_id,
                lease_seconds=self.lease_seconds,
                enabled=True,
            )
            return self._drive(coordinator, actor, token)
        if header["status"] == "running" and header["state"] == "staging":
            if header["worker_id"] == self.worker_id and header["lease_expires_at"] is not None:
                expiry = header["lease_expires_at"]
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                if expiry > self._now():
                    # Coordinator rechecks grants, epoch and lease after fences.
                    return self._drive(coordinator, actor, {
                        "job_id": str(job_id), "worker_id": self.worker_id,
                        "claim_epoch": header["claim_epoch"],
                    })
            coordinator.retry(actor, job_id, enabled=True)
            return "reclaimed"
        if header["status"] == "running" and header["state"] == "promoted":
            coordinator.recover(
                actor,
                job_id,
                expected_epoch=header["claim_epoch"],
                enabled=True,
            )
            return "recovered"
        return "skipped"

    def _drive(self, coordinator, actor, token) -> str:
        try:
            finished = False
            for _page in range(self.max_pages):
                page = coordinator.stage_page(
                    actor,
                    token,
                    lease_seconds=self.lease_seconds,
                    page_size=self.page_size,
                    enabled=True,
                )
                if page["complete"]:
                    finished = True
                    break
                if int(page["page_count"]) == 0:
                    return self._fail(coordinator, actor, token, "incomplete_stage")
            if not finished:
                return "progress"
            coordinator.promote(actor, token, enabled=True)
            coordinator.acknowledge(actor, token, enabled=True)
            return "acknowledged"
        except EvaluationError as exc:
            return self._settle(coordinator, actor, token, exc)

    def _settle(self, coordinator, actor, token, exc: EvaluationError) -> str:
        code = exc.data.get("code") if isinstance(getattr(exc, "data", None), dict) else None
        state = self._state(token.get("job_id"))
        if state == "promoted":
            return "awaiting_ack"
        if code in PRESERVE_CODES:
            return "fenced"
        reason = code if code in SAFE_FAILURE_REASONS else "apply_failed"
        return self._fail(coordinator, actor, token, reason)

    def _fail(self, coordinator, actor, token, reason: str) -> str:
        try:
            result = coordinator.fail_live(actor, token, reason=reason, enabled=True)
        except EvaluationError:
            return "unresolved"
        if result.get("outcome") == "preserved":
            return "awaiting_ack"
        return "failed"

    def _header(self, job_id):
        row = (
            self.db.query(
                EvaluationApplyControl.requested_by_user_id,
                EvaluationApplyControl.state,
                EvaluationApplyControl.claim_epoch,
                ProcessingJob.status,
                ProcessingJob.worker_id,
                ProcessingJob.lease_expires_at,
            )
            .join(ProcessingJob, ProcessingJob.id == EvaluationApplyControl.job_id)
            .filter(
                EvaluationApplyControl.job_id == job_id,
                ProcessingJob.kind == JOB_KIND_EVALUATION_APPLY,
            )
            .one_or_none()
        )
        if row is None:
            self._rollback()
            return None
        header = {
            "requested_by_user_id": row.requested_by_user_id,
            "state": row.state,
            "status": row.status,
            "claim_epoch": int(row.claim_epoch),
            "worker_id": row.worker_id,
            "lease_expires_at": row.lease_expires_at,
        }
        self._rollback()
        return header

    def _state(self, job_id):
        parsed = uuid.UUID(str(job_id))
        state = (
            self.db.query(EvaluationApplyControl.state)
            .filter(EvaluationApplyControl.job_id == parsed)
            .scalar()
        )
        self._rollback()
        return state

    def _lease(self) -> EvaluationLeaseCoordinator:
        if self._coordinator is None:
            self._coordinator = EvaluationLeaseCoordinator(self.db, clock=self.clock)
        return self._coordinator

    def _now(self) -> datetime:
        clock = self.clock
        current = datetime.now(timezone.utc) if clock is None else clock()
        return _aware(current)

    def _rollback(self) -> None:
        try:
            self.db.rollback()
        except Exception:
            return


def run_enabled_tick(
    db,
    worker_id: str,
    *,
    client=None,
    clock=None,
    lease_seconds=None,
    page_size: int = 100,
    max_pages: int = DEFAULT_MAX_PAGES,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict:
    """Run one job tick and one outbox batch when the product flag is on.

    ``client is None`` selects the shared Redis client object. The client is
    not tested with ``bool()``. Delivery stays in the outbox publisher.
    """

    if settings.PMS_EVALUATION_APPLY_JOBS_ENABLED is not True:
        return _disabled_tick()
    summary = EvaluationApplyRuntime(
        db,
        worker_id,
        clock=clock,
        lease_seconds=lease_seconds,
        page_size=page_size,
        max_pages=max_pages,
        candidate_limit=candidate_limit,
    ).run_tick(enabled=True)
    if client is None:
        from services.redis_provider import redis_client

        client = redis_client
    delivery = CacheOutboxPublisher(db, client=client, clock=clock).deliver_due(enabled=True)
    summary["delivery"] = {
        "enabled": delivery["enabled"],
        "considered": delivery["considered"],
        "published": delivery["published"],
        "failed": delivery["failed"],
    }
    return summary
