from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config import settings
from config.database import Base
from models.models import ProcessingJob, User
from services.job_storage import cleanup_job_files, resolve_input_path, stage_upload
from services.processing_job_service import ProcessingJobService, utcnow


@pytest.fixture()
def job_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__, ProcessingJob.__table__])
    session = sessionmaker(bind=engine)()
    user = User(
        id=uuid.uuid4(),
        username="job-user",
        email="job@example.com",
        password_hash="unused",
        role="Manager",
    )
    session.add(user)
    session.commit()
    yield session, user
    session.close()


def test_job_idempotency_claim_progress_and_completion(job_db):
    db, user = job_db
    first = ProcessingJobService.create(
        db,
        kind="report_generation",
        request_json={"configuration": {"report_name": "Test"}},
        requested_by_user_id=user.id,
        requested_by_name=user.username,
        idempotency_key=f"{user.id}:same-request",
    )
    duplicate = ProcessingJobService.create(
        db,
        kind="report_generation",
        request_json={"configuration": {"report_name": "Different"}},
        requested_by_user_id=user.id,
        requested_by_name=user.username,
        idempotency_key=f"{user.id}:same-request",
    )

    assert duplicate.id == first.id
    assert first.status == "queued"

    claimed_id = ProcessingJobService.claim_next(db, "worker-test")
    assert claimed_id == str(first.id)
    db.refresh(first)
    assert first.status == "running"
    assert first.attempt_count == 1

    assert ProcessingJobService.progress(db, first.id, 42, "worker-test") is True
    assert ProcessingJobService.succeed(
        db,
        first.id,
        result={"id": "stale-worker"},
        worker_id="stale-worker",
    ) is None
    db.refresh(first)
    assert first.status == "running"
    completed = ProcessingJobService.succeed(
        db,
        first.id,
        result={"id": "report-1"},
        result_type="report",
        result_id="report-1",
        worker_id="worker-test",
    )
    assert completed is not None
    assert completed.status == "succeeded"
    assert completed.progress == 100
    assert ProcessingJobService.serialize(completed)["result"] == {"id": "report-1"}


def test_job_retry_becomes_terminal_after_attempt_limit(job_db):
    db, user = job_db
    job = ProcessingJobService.create(
        db,
        kind="pms_upload",
        request_json={"filename": "test.xlsx"},
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


def test_job_file_staging_is_atomic_and_confined(tmp_path):
    previous_data_dir = settings.PMS_DATA_DIR
    previous_job_dir = settings.PMS_JOB_DATA_DIR
    job_id = uuid.uuid4()
    try:
        settings.PMS_DATA_DIR = str(tmp_path)
        settings.PMS_JOB_DATA_DIR = str(tmp_path / "jobs")
        relative = stage_upload(job_id, "edited.xlsx", b"valid-test-bytes")
        resolved = resolve_input_path(relative)
        assert resolved.read_bytes() == b"valid-test-bytes"
        with pytest.raises((ValueError, FileNotFoundError)):
            resolve_input_path("../outside/input.xlsx")
        cleanup_job_files(job_id)
        assert not resolved.exists()
    finally:
        settings.PMS_DATA_DIR = previous_data_dir
        settings.PMS_JOB_DATA_DIR = previous_job_dir
