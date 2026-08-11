"""Database-backed worker for asynchronous uploads and report rendering."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
import threading
import time
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from config import settings
from config.database import SessionLocal
from config.loader import ConfigurationError
from api.dependencies import clear_serialization_cache
from models.models import GeneratedReport
from models.report_definitions import ReportGenerateRequest
from models.report_schemas import ReportConfiguration
from services.cache_invalidation_service import CacheInvalidationService
from services.report_service import (
    ReportAccessError,
    ReportNotFoundError,
    ReportService,
    ReportValidationError,
)
from services.report_story_service import (
    ReportStoryService,
    StoryAccessError,
    StoryConflictError,
    StoryNotFoundError,
    StoryValidationError,
)
from services.seeding_service import DatabaseSeeder, UploadProcessingError
from services.job_storage import cleanup_job_files, resolve_input_path
from services.processing_job_service import ProcessingJobService
from services.socket_service import SocketNotificationService

logger = logging.getLogger(__name__)

NON_RETRYABLE_ERRORS = (
    UploadProcessingError,
    ConfigurationError,
    ValueError,
    ReportAccessError,
    ReportNotFoundError,
    ReportValidationError,
    StoryAccessError,
    StoryConflictError,
    StoryNotFoundError,
    StoryValidationError,
    ValidationError,
)


def _safe_uuid(value: str | UUID | None) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _scope(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("scope")
    return dict(value) if isinstance(value, dict) else {}


def _story_result(report: GeneratedReport) -> dict[str, Any]:
    return {
        "id": str(report.id),
        "name": report.name,
        "status": report.status,
        "format": report.output_format,
        "file_name": report.file_name,
        "integrity_identifier": report.integrity_identifier,
        "download_url": f"/api/reports/{report.id}/download",
    }


def _notify(coro) -> None:
    try:
        asyncio.run(coro)
    except Exception:
        logger.warning("Worker notification delivery failed", exc_info=True)


class JobLeaseHeartbeat:
    def __init__(self, job_id: str, worker_id: str) -> None:
        self.job_id = job_id
        self.worker_id = worker_id
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name=f"job-heartbeat-{job_id[:8]}", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)

    def _run(self) -> None:
        interval = max(5.0, settings.PMS_JOB_LEASE_SECONDS / 3)
        while not self.stop_event.wait(interval):
            db = SessionLocal()
            try:
                if not ProcessingJobService.heartbeat(db, self.job_id, self.worker_id):
                    return
            except Exception:
                logger.warning("Job heartbeat failed", extra={"job_id": self.job_id}, exc_info=True)
            finally:
                db.close()


def _execute_upload(job_id: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str | None, str]:
    input_path = resolve_input_path(str(payload.get("input_path") or ""))
    contents = input_path.read_bytes()
    dry_run = bool(payload.get("dry_run"))
    seeder = DatabaseSeeder()
    result = seeder.process_uploaded_file(
        str(payload.get("filename") or "PMS upload.xlsx"),
        contents,
        dry_run=dry_run,
        uploaded_by_user_id=payload.get("uploaded_by_user_id"),
        uploaded_by_name=payload.get("uploaded_by_name"),
        upload_batch_id=None if dry_run else job_id,
    )
    if not dry_run:
        CacheInvalidationService.bump_data_version()
        clear_serialization_cache()
    return result, result.get("upload_id") if isinstance(result, dict) else None, "upload"


def _existing_report(db, job_id: str, scope: dict[str, Any]) -> GeneratedReport | None:
    owner_id = _safe_uuid(scope.get("user_id"))
    return ReportService(db).reports.get_generated_by_processing_job(job_id, owner_user_id=owner_id)


def _execute_report(job_id: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str | None, str]:
    scope = _scope(payload)
    db = SessionLocal()
    try:
        existing = _existing_report(db, job_id, scope)
        service = ReportService(db)
        if existing:
            return service.serialize_generated(existing), str(existing.id), "report"
        configuration = ReportConfiguration.model_validate(payload.get("configuration") or {})
        report = service.generate(configuration, scope, processing_job_id=job_id)
        return service.serialize_generated(report), str(report.id), "report"
    finally:
        db.close()


def _execute_story_report(job_id: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str | None, str]:
    scope = _scope(payload)
    db = SessionLocal()
    try:
        existing = _existing_report(db, job_id, scope)
        if existing:
            return _story_result(existing), str(existing.id), "story_report"
        request = ReportGenerateRequest.model_validate(payload.get("request") or {})
        service = ReportStoryService(db)
        result = service.generate(
            str(payload.get("draft_id") or ""),
            request,
            scope,
            processing_job_id=job_id,
        )
        return result, str(result.get("id")) if isinstance(result, dict) else None, "story_report"
    finally:
        db.close()


def process_job_once(job_id: str, worker_id: str) -> None:
    claim_db = SessionLocal()
    try:
        job = ProcessingJobService.get(claim_db, job_id)
        if not job or job.status != "running":
            return
        kind = job.kind
        payload = dict(job.request_json or {})
        payload["input_path"] = job.input_path
    finally:
        claim_db.close()

    heartbeat = JobLeaseHeartbeat(job_id, worker_id)
    heartbeat.start()
    try:
        if kind == "pms_upload":
            result, result_id, result_type = _execute_upload(job_id, payload)
        elif kind == "report_generation":
            result, result_id, result_type = _execute_report(job_id, payload)
        elif kind == "story_report_generation":
            result, result_id, result_type = _execute_story_report(job_id, payload)
        else:
            raise ValueError("Unsupported processing job kind")

        db = SessionLocal()
        try:
            completed = ProcessingJobService.succeed(
                db,
                job_id,
                result=result,
                result_type=result_type,
                result_id=result_id,
                worker_id=worker_id,
            )
        finally:
            db.close()
        if completed and kind == "pms_upload" and not bool(payload.get("dry_run")):
            _notify(
                SocketNotificationService.notify_file_upload(
                    filename=str(payload.get("filename") or "PMS upload.xlsx"),
                    team_name="All Teams",
                    teams=[],
                    status="success",
                    details={"job_id": job_id, "status": "succeeded"},
                )
            )
        _notify(SocketNotificationService.notify_job_updated(job_id, kind, "succeeded"))
        if kind == "pms_upload":
            cleanup_job_files(job_id)
    except Exception as exc:
        retryable = not isinstance(exc, NON_RETRYABLE_ERRORS)
        failed = None
        db = SessionLocal()
        try:
            failed = ProcessingJobService.fail(
                db,
                job_id,
                error_code=type(exc).__name__.lower()[:80],
                message=str(exc) if not retryable else "The background operation failed and will be retried.",
                retryable=retryable,
                worker_id=worker_id,
            )
        finally:
            db.close()
        if failed:
            _notify(SocketNotificationService.notify_job_updated(job_id, kind, failed.status))
        logger.exception("Processing job failed", extra={"job_id": job_id, "kind": kind})
    finally:
        heartbeat.stop()


def run_worker(*, once: bool = False) -> None:
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    logger.info("Processing worker started", extra={"worker_id": worker_id})
    while True:
        db = SessionLocal()
        try:
            ProcessingJobService.requeue_expired(db)
            job_id = ProcessingJobService.claim_next(db, worker_id)
        except Exception:
            logger.exception("Unable to claim processing job")
            job_id = None
        finally:
            db.close()

        if job_id:
            process_job_once(job_id, worker_id)
        elif once:
            return
        else:
            time.sleep(settings.PMS_JOB_POLL_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the PMS durable processing worker")
    parser.add_argument("--once", action="store_true", help="claim at most one job and exit")
    args = parser.parse_args()
    run_worker(once=args.once)


if __name__ == "__main__":
    main()
