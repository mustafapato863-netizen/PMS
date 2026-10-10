"""Monthly evaluation settings API. Approval stays Admin-only."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case
from sqlalchemy.orm import Session

from api.dependencies import get_current_user_scope
from config import settings
from config.database import get_db
from models.models import EvaluationApplyControl, ProcessingJob
from models.schemas import StandardResponse
from services.evaluation.access import EvaluationError
from services.evaluation.apply_job_schema import JOB_KIND_EVALUATION_APPLY
from services.evaluation.lease_coordinator import EvaluationLeaseCoordinator
from services.evaluation.workflow import EvaluationWorkflow

router = APIRouter()


class DraftRequest(BaseModel):
    scope_id: str
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    copy_previous: bool = False


class EditRequest(BaseModel):
    lines: list[dict]
    weight_only: bool = False
    expected_checksum: str | None = None


class PreviewRequest(BaseModel):
    rows: list[dict] = Field(default_factory=list)


class ApplyRequest(BaseModel):
    scope_id: str
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class ApplyJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_id: uuid.UUID
    year: int = Field(ge=2000, le=2100, strict=True)
    month: int = Field(ge=1, le=12, strict=True)


class RecoverJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_epoch: int = Field(ge=0, strict=True)


def _actor(request: Request, db: Session) -> dict:
    payload = getattr(request.state, "user", None)
    if not isinstance(payload, dict) or not payload.get("user_id"):
        raise HTTPException(status_code=401, detail="Authentication required")
    return get_current_user_scope(db, request)


def _run(action):
    try:
        return action()
    except EvaluationError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"message": exc.message, **exc.data}) from exc


def _admin_actor(request: Request, db: Session) -> dict:
    """Persisted active Admin. The JWT role string is not the grant."""

    actor = _actor(request, db)
    user = actor.get("user")
    if actor.get("legacy_unscoped") or actor.get("role") != "Admin" or user is None or user.is_active is not True:
        raise HTTPException(
            status_code=403,
            detail={"message": "Evaluation settings are limited to Admin.", "code": "access_denied"},
        )
    return actor


def _require_apply_jobs() -> None:
    if settings.PMS_EVALUATION_APPLY_JOBS_ENABLED is not True:
        raise HTTPException(
            status_code=503,
            detail={"message": "Evaluation apply jobs are disabled.", "code": "runtime_disabled"},
        )


def _latest_apply_job_id(db: Session, scope_id: uuid.UUID, year: int, month: int):
    return (
        db.query(ProcessingJob.id)
        .join(EvaluationApplyControl, EvaluationApplyControl.job_id == ProcessingJob.id)
        .filter(
            ProcessingJob.kind == JOB_KIND_EVALUATION_APPLY,
            EvaluationApplyControl.scope_id == scope_id,
            EvaluationApplyControl.year == year,
            EvaluationApplyControl.month == month,
        )
        .order_by(
            case((EvaluationApplyControl.state.in_(("pending", "staging", "promoting")), 0), else_=1),
            ProcessingJob.created_at.desc(), ProcessingJob.id.desc(),
        )
        .limit(1)
        .scalar()
    )


def _management_status(db: Session, actor: dict, job_id: uuid.UUID) -> dict:
    data = EvaluationLeaseCoordinator(db).status(actor, job_id, enabled=True)
    return _with_management_hints(db, actor, job_id, data)


def _with_management_hints(db: Session, actor: dict, job_id: uuid.UUID, data: dict) -> dict:
    # Presentation hints, never grants: commands recheck the persisted Admin.
    current = db.query(
        EvaluationApplyControl.requested_by_user_id,
        EvaluationApplyControl.state,
        ProcessingJob.status,
    ).join(ProcessingJob, ProcessingJob.id == EvaluationApplyControl.job_id).filter(
        EvaluationApplyControl.job_id == job_id,
    ).one_or_none()
    requester, state, status = current if current is not None else (None, None, None)
    data.update({
        "can_cancel": state in {"pending", "staging"},
        "can_retry": state in {"failed", "cancelled"} and str(requester) == str(actor.get("user_id")),
        "can_recover": state == "promoted" and status == "running",
    })
    db.rollback()
    return data


@router.get("/catalog", response_model=StandardResponse)
def evaluation_catalog(request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    return StandardResponse(success=True, message="Evaluation catalog", data=_run(lambda: EvaluationWorkflow(db).sync_catalog(actor)))


@router.post("/drafts", response_model=StandardResponse)
def open_draft(body: DraftRequest, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    data = _run(lambda: EvaluationWorkflow(db).open_draft(actor, body.scope_id, body.year, body.month, copy_previous=body.copy_previous))
    return StandardResponse(success=True, message="Evaluation draft saved", data=data)


@router.patch("/drafts/{version_id}", response_model=StandardResponse)
def edit_draft(version_id: str, body: EditRequest, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    data = _run(lambda: EvaluationWorkflow(db).edit_draft(
        actor, version_id, body.lines, weight_only=body.weight_only,
        expected_checksum=body.expected_checksum, require_precondition=True,
    ))
    return StandardResponse(success=True, message="Evaluation draft updated", data=data)


@router.post("/drafts/{version_id}/preview", response_model=StandardResponse)
def preview_draft(version_id: str, body: PreviewRequest, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    data = _run(lambda: EvaluationWorkflow(db).preview(actor, version_id, body.rows))
    return StandardResponse(success=True, message="Evaluation preview", data=data)


@router.post("/drafts/{version_id}/impact-preview", response_model=StandardResponse)
def impact_preview_draft(version_id: str, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    data = _run(lambda: EvaluationWorkflow(db).impact_preview(actor, version_id))
    return StandardResponse(success=True, message="Evaluation impact preview", data=data)


@router.post("/drafts/{version_id}/approve", response_model=StandardResponse)
def approve_draft(version_id: str, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    data = _run(lambda: EvaluationWorkflow(db).approve(actor, version_id))
    return StandardResponse(success=True, message="Evaluation month approved", data=data)


@router.post("/jobs/{version_id}/preview", response_model=StandardResponse)
def preview_job(version_id: str, body: PreviewRequest, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    data = _run(lambda: EvaluationWorkflow(db).run_preview_job(actor, version_id, body.rows))
    return StandardResponse(success=True, message="Evaluation preview job", data=data)


@router.post("/versions/{version_id}/revise", response_model=StandardResponse)
def revise_version(version_id: str, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    data = _run(lambda: EvaluationWorkflow(db).revise(actor, version_id))
    return StandardResponse(success=True, message="Evaluation revision draft saved", data=data)


@router.get("/versions/{version_id}", response_model=StandardResponse)
def get_version(version_id: str, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    return StandardResponse(success=True, message="Evaluation version", data=_run(lambda: EvaluationWorkflow(db).get_version(actor, version_id)))


@router.get("/versions/{version_id}/export", response_model=StandardResponse)
def export_version(version_id: str, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    return StandardResponse(success=True, message="Evaluation export", data=_run(lambda: EvaluationWorkflow(db).export_version(actor, version_id)))


@router.get("/periods", response_model=StandardResponse)
def evaluation_period(
    request: Request,
    scope_id: str,
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
):
    actor = _actor(request, db)
    return StandardResponse(success=True, message="Evaluation period", data=_run(lambda: EvaluationWorkflow(db).period(actor, scope_id, year, month)))


@router.get("/reads", response_model=StandardResponse)
def evaluation_reads(
    request: Request,
    scope_id: str,
    year: int = Query(ge=2000, le=2100),
    months: str = Query(min_length=1, max_length=64),
    db: Session = Depends(get_db),
):
    actor = _actor(request, db)
    # A bounded, exact calendar list prevents malformed requests from raising
    # uncaught conversion errors or performing repeated evidence reads.
    parts = [part.strip() for part in months.split(",")]
    if len(parts) > 12 or any(not part.isascii() or not part.isdigit() for part in parts):
        raise HTTPException(status_code=422, detail="Provide 1 to 12 distinct calendar months (1-12).")
    parsed = [int(part) for part in parts]
    if any(number < 1 or number > 12 for number in parsed) or len(set(parsed)) != len(parsed):
        raise HTTPException(status_code=422, detail="Provide 1 to 12 distinct calendar months (1-12).")
    return StandardResponse(
        success=True,
        message="Evaluation reads",
        data=_run(lambda: EvaluationWorkflow(db).reads(actor, scope_id, year, parsed)),
    )


@router.post("/apply", response_model=StandardResponse)
def apply_month(body: ApplyRequest, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    return StandardResponse(success=True, message="Evaluation apply completed", data=_run(lambda: EvaluationWorkflow(db).apply(actor, body.scope_id, body.year, body.month)))


@router.post("/revisions/{revision_id}/rollback", response_model=StandardResponse)
def rollback_revision(revision_id: str, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request, db)
    return StandardResponse(success=True, message="Evaluation rollback completed", data=_run(lambda: EvaluationWorkflow(db).rollback(actor, revision_id)))


@router.get("/apply-jobs/capabilities", response_model=StandardResponse)
def apply_job_capabilities(request: Request, db: Session = Depends(get_db)):
    _admin_actor(request, db)
    enabled = settings.PMS_EVALUATION_APPLY_JOBS_ENABLED is True
    return StandardResponse(success=True, message="Evaluation apply job capability", data={"enabled": enabled})


@router.get("/apply-jobs", response_model=StandardResponse)
def latest_apply_job(
    request: Request,
    scope_id: uuid.UUID,
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
):
    actor = _admin_actor(request, db)
    _require_apply_jobs()
    job_id = _latest_apply_job_id(db, scope_id, year, month)
    if job_id is None:
        return StandardResponse(success=True, message="Evaluation apply job", data={"job": None})
    data = _run(lambda: _management_status(db, actor, job_id))
    return StandardResponse(success=True, message="Evaluation apply job", data={"job": data})


@router.post("/apply-jobs", response_model=StandardResponse)
def enqueue_apply_job(body: ApplyJobCreate, request: Request, db: Session = Depends(get_db)):
    actor = _admin_actor(request, db)
    _require_apply_jobs()
    data = _run(lambda: EvaluationLeaseCoordinator(db).enqueue(actor, body.scope_id, body.year, body.month, enabled=True))
    return StandardResponse(success=True, message="Evaluation apply job queued", data=data)


@router.get("/apply-jobs/{job_id}", response_model=StandardResponse)
def apply_job_status(job_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    actor = _admin_actor(request, db)
    _require_apply_jobs()
    data = _run(lambda: _management_status(db, actor, job_id))
    return StandardResponse(success=True, message="Evaluation apply job status", data=data)


@router.post("/apply-jobs/{job_id}/cancel", response_model=StandardResponse)
def cancel_apply_job(job_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    actor = _admin_actor(request, db)
    _require_apply_jobs()
    data = _run(lambda: EvaluationLeaseCoordinator(db).cancel(actor, job_id, enabled=True))
    data = _with_management_hints(db, actor, job_id, data)
    return StandardResponse(success=True, message="Evaluation apply job cancelled", data=data)


@router.post("/apply-jobs/{job_id}/retry", response_model=StandardResponse)
def retry_apply_job(job_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    actor = _admin_actor(request, db)
    _require_apply_jobs()
    data = _run(lambda: EvaluationLeaseCoordinator(db).retry(actor, job_id, enabled=True))
    data = _with_management_hints(db, actor, job_id, data)
    return StandardResponse(success=True, message="Evaluation apply job retry", data=data)


@router.post("/apply-jobs/{job_id}/recover", response_model=StandardResponse)
def recover_apply_job(job_id: uuid.UUID, body: RecoverJobRequest, request: Request, db: Session = Depends(get_db)):
    actor = _admin_actor(request, db)
    _require_apply_jobs()
    data = _run(lambda: EvaluationLeaseCoordinator(db).recover(actor, job_id, expected_epoch=body.expected_epoch, enabled=True))
    data = _with_management_hints(db, actor, job_id, data)
    return StandardResponse(success=True, message="Evaluation apply job recovered", data=data)
