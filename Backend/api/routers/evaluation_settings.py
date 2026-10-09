"""Monthly evaluation settings API. Approval stays Admin-only."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.dependencies import get_current_user_scope
from config.database import get_db
from models.schemas import StandardResponse
from services.evaluation.access import EvaluationError
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
