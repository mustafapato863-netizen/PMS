import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from api.middleware.rbac_middleware import require_permission
from config.database import get_db
from config import settings
from models.schemas import StandardResponse, KPIWeight, Target
from services.cache_invalidation_service import CacheInvalidationService
from api.dependencies import clear_serialization_cache
from services.corrective_action_service import CorrectiveActionService, CorrectiveActionValidationError
from services.kpi_configuration_service import KPIConfigurationService
from sqlalchemy.orm import Session

router = APIRouter()

@router.get("/weights", response_model=StandardResponse)
async def get_weights(db: Session = Depends(get_db)):
    try:
        return StandardResponse(
            success=True,
            message="KPI Weights retrieved",
            data=KPIConfigurationService(db).list_weights(),
        )
    except Exception:
        return StandardResponse(success=False, message="Failed to load KPI weights.")

@router.post("/weights", response_model=StandardResponse, deprecated=True)
async def update_weights(
    _payload: KPIWeight,
    _user=Depends(require_permission("manage_permissions"))
):
    raise HTTPException(
        status_code=409,
        detail="KPI weights are read-only here; update the tracked team configuration and re-upload the workbook.",
    )

@router.get("/targets", response_model=StandardResponse)
async def get_targets(db: Session = Depends(get_db)):
    try:
        return StandardResponse(
            success=True,
            message="KPI Targets retrieved",
            data=KPIConfigurationService(db).list_targets(),
        )
    except Exception:
        return StandardResponse(success=False, message="Failed to load targets.")


@router.get("/corrective-actions/export")
async def export_corrective_actions(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("export_data")),
):
    """Download a versioned JSON snapshot that can be moved to another PMS database."""
    payload = CorrectiveActionService(db).export_transfer_payload()
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"pms-corrective-actions-{datetime.now(timezone.utc):%Y%m%d}.json"
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/corrective-actions/import", response_model=StandardResponse)
async def import_corrective_actions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("restore_data")),
):
    """Atomically restore corrective actions from a JSON export."""
    filename = (file.filename or "").strip()
    if filename and not filename.lower().endswith(".json"):
        raise HTTPException(status_code=422, detail="Only corrective action JSON files are supported")
    contents = await file.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(contents) > settings.MAX_UPLOAD_BYTES:
        limit_mb = settings.MAX_UPLOAD_BYTES / (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"Corrective action file exceeds the {limit_mb:.0f} MB upload limit")
    try:
        payload = json.loads(contents.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="The uploaded file is not valid UTF-8 JSON") from exc

    try:
        result = CorrectiveActionService(db).import_transfer_payload(payload)
        CacheInvalidationService.flush_all()
        clear_serialization_cache()
        return StandardResponse(
            success=True,
            message="Corrective actions imported successfully",
            data=result,
        )
    except CorrectiveActionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Corrective action import failed. No changes were saved.") from exc

@router.post("/targets", response_model=StandardResponse, deprecated=True)
async def update_targets(
    _payload: Target,
    _user=Depends(require_permission("manage_permissions"))
):
    raise HTTPException(
        status_code=409,
        detail="KPI targets are sourced from persisted workbook evidence; upload a corrected workbook instead.",
    )
