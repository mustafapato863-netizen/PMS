"""Safe staging and cleanup for files associated with processing jobs."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import UUID

from config import settings


def _job_uuid(job_id: str | UUID) -> UUID:
    return job_id if isinstance(job_id, UUID) else UUID(str(job_id))


def _data_root() -> Path:
    return Path(settings.PMS_DATA_DIR).resolve()


def _job_root(job_id: str | UUID) -> Path:
    root = Path(settings.PMS_JOB_DATA_DIR).resolve()
    path = root / str(_job_uuid(job_id))
    path.relative_to(root)
    return path


def stage_upload(job_id: str | UUID, filename: str, contents: bytes) -> str:
    """Atomically write an already-validated workbook to the shared data volume."""

    if not contents:
        raise ValueError("The staged upload is empty")
    directory = _job_root(job_id)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "input.xlsx"
    partial = directory / "input.part"
    with partial.open("wb") as handle:
        handle.write(contents)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(partial, target)
    return target.relative_to(_data_root()).as_posix()


def resolve_input_path(relative_path: str) -> Path:
    """Resolve only paths below the configured data directory."""

    root = _data_root()
    path = (root / relative_path).resolve()
    path.relative_to(root)
    if path.name != "input.xlsx" or not path.is_file():
        raise FileNotFoundError("The staged job input is unavailable")
    return path


def cleanup_job_files(job_id: str | UUID) -> None:
    """Remove only the validated temporary directory for one completed job."""

    root = Path(settings.PMS_JOB_DATA_DIR).resolve()
    directory = _job_root(job_id)
    directory.relative_to(root)
    if directory.exists():
        shutil.rmtree(directory)
