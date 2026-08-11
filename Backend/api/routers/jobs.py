"""Authenticated status endpoint for durable upload/report jobs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.middleware.rbac_middleware import require_permission
from config.database import get_db
from models.schemas import StandardResponse
from services.processing_job_service import ProcessingJobService


router = APIRouter(prefix="/jobs", tags=["Processing Jobs"])


@router.get("/{job_id}", response_model=StandardResponse)
def get_processing_job(
    job_id: str,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    job = ProcessingJobService.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Processing job was not found")
    user_id = _user.get("user_id") if isinstance(_user, dict) else None
    role = _user.get("role") if isinstance(_user, dict) else None
    if not ProcessingJobService.can_view(job, user_id, role):
        raise HTTPException(status_code=403, detail="You cannot view this processing job")
    return StandardResponse(
        success=True,
        message="Processing job status retrieved",
        data=ProcessingJobService.serialize(job),
    )
