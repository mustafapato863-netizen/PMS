"""Staging, cleanup and the startup sweep for files that belong to processing jobs.

The backend stages an upload on the job volume and the worker reads it from the same volume, so PMS_JOB_DATA_DIR must be
shared by both services. Directories are owner-only where the platform supports it. A job's directory is removed when
the job succeeds or fails for good (see worker.py). Leftovers, such as a worker that died with the job, are removed by
sweep_stale_job_files once they are older than PMS_JOB_FAILED_FILE_RETENTION_SECONDS.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from uuid import UUID

from config import settings

INPUT_NAME = "input.xlsx"
_PARTIAL_NAME = "input.part"
_DIRECTORY_MODE = 0o700
_FILE_MODE = 0o600


def _job_uuid(job_id: str | UUID) -> UUID:
    return job_id if isinstance(job_id, UUID) else UUID(str(job_id))


def _root() -> Path:
    return Path(settings.PMS_JOB_DATA_DIR).resolve()


def _job_root(job_id: str | UUID) -> Path:
    root = _root()
    path = root / str(_job_uuid(job_id))
    path.relative_to(root)
    return path


def stage_upload(job_id: str | UUID, filename: str, contents: bytes) -> str:
    """Atomically write an already-validated workbook to the shared job volume and return its relative path."""

    if not contents:
        raise ValueError("The staged upload is empty")
    directory = _job_root(job_id)
    os.makedirs(directory, mode=_DIRECTORY_MODE, exist_ok=True)
    target = directory / INPUT_NAME
    partial = directory / _PARTIAL_NAME
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(contents)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(partial, target)
    return target.relative_to(_root()).as_posix()


def resolve_input_path(relative_path: str) -> Path:
    """Resolve only the staged input of a job, and only below the job root."""

    root = _root()
    path = (root / relative_path).resolve()
    path.relative_to(root)
    if path.name != INPUT_NAME or not path.is_file():
        raise FileNotFoundError("The staged job input is unavailable")
    return path


def cleanup_job_files(job_id: str | UUID) -> None:
    """Remove only the directory of one job."""

    directory = _job_root(job_id)
    if directory.exists():
        shutil.rmtree(directory)


def sweep_stale_job_files(*, now: float | None = None) -> list[str]:
    """Remove job directories older than the retention window and return their names.

    Only directories named by a job UUID are candidates, so nothing else on the volume is touched.
    """

    root = _root()
    if not root.is_dir():
        return []
    cutoff = (time.time() if now is None else now) - settings.PMS_JOB_FAILED_FILE_RETENTION_SECONDS
    removed: list[str] = []
    for entry in os.scandir(root):
        if not entry.is_dir(follow_symlinks=False):
            continue
        try:
            UUID(entry.name)
        except ValueError:
            continue
        if entry.stat(follow_symlinks=False).st_mtime < cutoff:
            shutil.rmtree(entry.path)
            removed.append(entry.name)
    return removed
