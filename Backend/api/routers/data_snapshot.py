"""Data snapshot routes. Admin only: export the business data as a streamed JSON file, and import one.

The export streams to the browser and is never stored on the server. The import reads the upload into memory,
checks it with a dry run first, and commits in one transaction.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from api.middleware.rbac_middleware import require_permission
from config import settings
from config.database import get_db
from models.schemas import StandardResponse
from services.data_snapshot_service import (
    SnapshotError,
    import_snapshot,
    parse_snapshot,
    plan_export,
    record_export,
    stream_export,
)

router = APIRouter(prefix="/settings/data-snapshot", tags=["Data Snapshot"])

# restore_data is granted to Admin only in services/permission_seed.py; every route below requires it.
ADMIN_PERMISSION = "restore_data"


async def _read_upload(file: UploadFile) -> bytes:
    limit = settings.DATA_SNAPSHOT_MAX_BYTES
    contents = await file.read(limit + 1)
    if len(contents) > limit:
        limit_mb = limit / (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"The snapshot exceeds the {limit_mb:.0f} MB limit")
    return contents


def _run_import(db: Session, contents: bytes, policy: str, dry_run: bool, actor_user_id: str | None) -> StandardResponse:
    try:
        document = parse_snapshot(contents)
        report = import_snapshot(db, document, policy=policy, dry_run=dry_run, actor_user_id=actor_user_id)
    except SnapshotError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    message = "Snapshot checked; nothing was saved" if dry_run else "Snapshot imported"
    return StandardResponse(success=True, message=message, data=report)


@router.get("/export")
def export_data_snapshot(
    db: Session = Depends(get_db),
    user=Depends(require_permission(ADMIN_PERMISSION)),
):
    """Download a versioned JSON snapshot of the business tables. Credentials are never included."""
    engine = db.get_bind()
    plan = plan_export(engine)
    record_export(db, plan, user.get("user_id"))
    filename = f"pms-data-snapshot-{plan.exported_at:%Y%m%d-%H%M%S}.json"
    return StreamingResponse(
        stream_export(engine, plan),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/import/dry-run", response_model=StandardResponse)
async def dry_run_data_snapshot(
    file: UploadFile = File(...),
    policy: str = Query(..., description="skip or replace: applied to every existing id in the snapshot"),
    db: Session = Depends(get_db),
    user=Depends(require_permission(ADMIN_PERMISSION)),
):
    """Check a snapshot without saving anything: counts, conflicts, the schema and revision checks."""
    contents = await _read_upload(file)
    return await run_in_threadpool(_run_import, db, contents, policy, dry_run=True, actor_user_id=user.get("user_id"))


@router.post("/import", response_model=StandardResponse)
async def import_data_snapshot(
    file: UploadFile = File(...),
    policy: str = Query(..., description="skip or replace: applied to every existing id in the snapshot"),
    db: Session = Depends(get_db),
    user=Depends(require_permission(ADMIN_PERMISSION)),
):
    """Import a snapshot in one transaction. Any error rolls back everything."""
    contents = await _read_upload(file)
    return await run_in_threadpool(_run_import, db, contents, policy, dry_run=False, actor_user_id=user.get("user_id"))
