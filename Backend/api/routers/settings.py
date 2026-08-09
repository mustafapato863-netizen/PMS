from fastapi import APIRouter, Depends, HTTPException

from api.middleware.rbac_middleware import require_permission
from config.database import get_db
from models.schemas import StandardResponse, KPIWeight, Target
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

@router.post("/targets", response_model=StandardResponse, deprecated=True)
async def update_targets(
    _payload: Target,
    _user=Depends(require_permission("manage_permissions"))
):
    raise HTTPException(
        status_code=409,
        detail="KPI targets are sourced from persisted workbook evidence; upload a corrected workbook instead.",
    )
