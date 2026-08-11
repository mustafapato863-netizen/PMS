"""Durable database-backed job queue primitives."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import settings
from models.models import ProcessingJob

logger = logging.getLogger(__name__)

JOB_KINDS = {"pms_upload", "report_generation", "story_report_generation"}
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_uuid(value: str | UUID | None) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def scope_snapshot(scope: dict[str, Any]) -> dict[str, Any]:
    """Keep only the authorization facts needed when the worker re-checks work."""

    allowed = (
        "user_id",
        "username",
        "role",
        "employee_id",
        "accessible_teams",
        "accessible_team_levels",
        "is_general_manager",
        "is_self_only",
        "active_team_names",
        "legacy_unscoped",
    )
    snapshot = {key: scope.get(key) for key in allowed if key in scope}
    user = scope.get("user")
    if "username" not in snapshot and user is not None:
        snapshot["username"] = getattr(user, "username", None)
    return jsonable_encoder(snapshot)


class ProcessingJobService:
    @staticmethod
    def find_by_idempotency(
        db: Session,
        kind: str,
        idempotency_key: str | None,
    ) -> ProcessingJob | None:
        normalized_key = (idempotency_key or "").strip()[:255] or None
        if not normalized_key:
            return None
        return (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.kind == kind,
                ProcessingJob.idempotency_key == normalized_key,
            )
            .first()
        )

    @staticmethod
    def create(
        db: Session,
        *,
        kind: str,
        request_json: dict[str, Any],
        requested_by_user_id: str | UUID | None,
        requested_by_name: str | None,
        input_path: str | None = None,
        idempotency_key: str | None = None,
        job_id: UUID | None = None,
        max_attempts: int | None = None,
    ) -> ProcessingJob:
        if kind not in JOB_KINDS:
            raise ValueError(f"Unsupported processing job kind: {kind}")
        normalized_key = (idempotency_key or "").strip()[:255] or None
        if normalized_key:
            existing = ProcessingJobService.find_by_idempotency(db, kind, normalized_key)
            if existing:
                return existing

        job = ProcessingJob(
            id=job_id or uuid4(),
            kind=kind,
            status="queued",
            requested_by_user_id=_as_uuid(requested_by_user_id),
            requested_by_name=(requested_by_name or "User")[:255],
            request_json=jsonable_encoder(request_json),
            input_path=input_path,
            progress=0,
            attempt_count=0,
            max_attempts=max_attempts or settings.PMS_JOB_MAX_ATTEMPTS,
            available_at=utcnow(),
            idempotency_key=normalized_key,
        )
        db.add(job)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if normalized_key:
                existing = (
                    db.query(ProcessingJob)
                    .filter(
                        ProcessingJob.kind == kind,
                        ProcessingJob.idempotency_key == normalized_key,
                    )
                    .first()
                )
                if existing:
                    return existing
            raise
        db.refresh(job)
        return job

    @staticmethod
    def get(db: Session, job_id: str | UUID) -> ProcessingJob | None:
        parsed = _as_uuid(job_id)
        return db.query(ProcessingJob).filter(ProcessingJob.id == parsed).first() if parsed else None

    @staticmethod
    def serialize(job: ProcessingJob) -> dict[str, Any]:
        error = None
        if job.error_code or job.safe_error_message:
            error = {
                "code": job.error_code or "processing_failed",
                "message": job.safe_error_message or "Processing failed.",
            }
        return {
            "job_id": str(job.id),
            "id": str(job.id),
            "kind": job.kind,
            "status": job.status,
            "progress": int(job.progress or 0),
            "attempt": int(job.attempt_count or 0),
            "max_attempts": int(job.max_attempts or 1),
            "result": job.result_json,
            "result_type": job.result_type,
            "result_id": job.result_id,
            "error": error,
            "created_at": _iso(job.created_at),
            "started_at": _iso(job.started_at),
            "finished_at": _iso(job.finished_at),
            "status_url": f"/api/jobs/{job.id}",
        }

    @staticmethod
    def reference(job: ProcessingJob) -> dict[str, Any]:
        return {
            "job_id": str(job.id),
            "kind": job.kind,
            "status": job.status,
            "progress": int(job.progress or 0),
            "status_url": f"/api/jobs/{job.id}",
        }

    @staticmethod
    def can_view(job: ProcessingJob, user_id: str | None, role: str | None) -> bool:
        return role == "Admin" or (
            bool(user_id)
            and job.requested_by_user_id is not None
            and str(job.requested_by_user_id) == str(user_id)
        )

    @staticmethod
    def claim_next(db: Session, worker_id: str) -> str | None:
        now = utcnow()
        job = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.status == "queued",
                ProcessingJob.available_at <= now,
            )
            .order_by(ProcessingJob.created_at.asc(), ProcessingJob.id.asc())
            .with_for_update(skip_locked=True)
            .first()
        )
        if job is None:
            db.rollback()
            return None
        job.status = "running"
        job.attempt_count = int(job.attempt_count or 0) + 1
        job.worker_id = worker_id[:150]
        job.started_at = job.started_at or now
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=settings.PMS_JOB_LEASE_SECONDS)
        db.commit()
        return str(job.id)

    @staticmethod
    def heartbeat(db: Session, job_id: str | UUID, worker_id: str) -> bool:
        job = ProcessingJobService.get(db, job_id)
        if not job or job.status != "running" or job.worker_id != worker_id:
            return False
        now = utcnow()
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=settings.PMS_JOB_LEASE_SECONDS)
        db.commit()
        return True

    @staticmethod
    def progress(db: Session, job_id: str | UUID, value: int, worker_id: str | None = None) -> bool:
        job = ProcessingJobService.get(db, job_id)
        if not job or job.status != "running" or (worker_id and job.worker_id != worker_id):
            return False
        job.progress = max(0, min(99, int(value)))
        now = utcnow()
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=settings.PMS_JOB_LEASE_SECONDS)
        db.commit()
        return True

    @staticmethod
    def succeed(
        db: Session,
        job_id: str | UUID,
        *,
        result: dict[str, Any] | None = None,
        result_type: str | None = None,
        result_id: str | None = None,
        worker_id: str | None = None,
    ) -> ProcessingJob | None:
        job = ProcessingJobService.get(db, job_id)
        if (
            not job
            or job.status != "running"
            or (worker_id and job.worker_id != worker_id)
        ):
            return None
        job.status = "succeeded"
        job.progress = 100
        job.result_json = jsonable_encoder(result or {})
        job.result_type = result_type
        job.result_id = result_id
        job.error_code = None
        job.safe_error_message = None
        job.finished_at = utcnow()
        job.worker_id = None
        job.lease_expires_at = None
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def fail(
        db: Session,
        job_id: str | UUID,
        *,
        error_code: str,
        message: str,
        retryable: bool,
        worker_id: str | None = None,
    ) -> ProcessingJob | None:
        job = ProcessingJobService.get(db, job_id)
        if (
            not job
            or job.status != "running"
            or (worker_id and job.worker_id != worker_id)
        ):
            return None
        safe_message = (message or "Processing failed.").replace("\x00", " ").strip()[:500]
        if retryable and int(job.attempt_count or 0) < int(job.max_attempts or 1):
            job.status = "queued"
            job.available_at = utcnow() + timedelta(seconds=min(60, 2 ** int(job.attempt_count or 1)))
            job.error_code = error_code[:80]
            job.safe_error_message = safe_message
            job.worker_id = None
            job.lease_expires_at = None
        else:
            job.status = "failed"
            job.progress = max(0, min(99, int(job.progress or 0)))
            job.error_code = error_code[:80]
            job.safe_error_message = safe_message
            job.finished_at = utcnow()
            job.worker_id = None
            job.lease_expires_at = None
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def requeue_expired(db: Session) -> int:
        now = utcnow()
        jobs = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.status == "running",
                ProcessingJob.lease_expires_at.is_not(None),
                ProcessingJob.lease_expires_at < now,
            )
            .with_for_update(skip_locked=True)
            .all()
        )
        changed = 0
        for job in jobs:
            changed += 1
            if int(job.attempt_count or 0) < int(job.max_attempts or 1):
                job.status = "queued"
                job.available_at = now
                job.error_code = "worker_lease_expired"
                job.safe_error_message = "The worker lease expired; the job was re-queued."
            else:
                job.status = "failed"
                job.error_code = "worker_lease_expired"
                job.safe_error_message = "The worker stopped responding before the job completed."
                job.finished_at = now
            job.worker_id = None
            job.lease_expires_at = None
        if changed:
            db.commit()
        else:
            db.rollback()
        return changed
