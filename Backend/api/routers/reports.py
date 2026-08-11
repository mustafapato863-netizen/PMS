from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from api.dependencies import require_authenticated_scope
from api.middleware.rbac_middleware import require_permission
from config import settings
from config.database import get_db
from models.report_definitions import (
    DraftPeriodChange,
    NarrativeRegenerateRequest,
    ReportDraftCreate,
    ReportDraftUpdate,
    ReportGenerateRequest,
    ReportTemplateCreate,
    ReportTemplateUpdate,
)
from models.report_schemas import ReportConfiguration, SaveReportTemplateRequest
from models.schemas import StandardResponse
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
from services.processing_job_service import ProcessingJobService, scope_snapshot


router = APIRouter(prefix="/reports", tags=["Reports"])


def _scope(db: Session, request: Request) -> dict:
    return require_authenticated_scope(db, request)


def _raise_report_error(exc: Exception) -> None:
    if isinstance(exc, ReportAccessError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if isinstance(exc, ReportNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, ReportValidationError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    raise exc


def _raise_story_error(exc: Exception) -> None:
    if isinstance(exc, StoryAccessError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if isinstance(exc, StoryNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, StoryConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, StoryValidationError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    raise exc


def _job_key(user_id: str | None, idempotency_key: str | None) -> str | None:
    value = (idempotency_key or "").strip()
    return f"{user_id or 'anonymous'}:{value[:220]}" if value else None


def _queued_response(job, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=StandardResponse(
            success=True,
            message=message,
            data=ProcessingJobService.reference(job),
        ).model_dump(mode="json"),
    )


@router.get("/templates", response_model=StandardResponse)
def list_report_templates(
    _user=Depends(require_permission("view_reports")),
):
    return StandardResponse(success=True, message="Report templates retrieved", data=ReportService.templates())


@router.get("/story/registry", response_model=StandardResponse)
def get_story_registry(
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    return StandardResponse(success=True, message="Report block and layout registries retrieved", data=ReportStoryService.registries(_scope(db, request)))


@router.get("/story/templates", response_model=StandardResponse)
def list_story_templates(
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    return StandardResponse(success=True, message="Story templates retrieved", data=ReportStoryService(db).list_templates(_scope(db, request)))


@router.post("/story/templates", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
def create_story_template(
    payload: ReportTemplateCreate,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        data = ReportStoryService(db).create_template(payload, _scope(db, request))
    except (StoryAccessError, StoryConflictError, StoryNotFoundError, StoryValidationError) as exc:
        _raise_story_error(exc)
    return StandardResponse(success=True, message="Story template saved", data=data)


@router.get("/story/templates/{template_id}", response_model=StandardResponse)
def get_story_template(
    template_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        data = ReportStoryService(db).get_template(template_id, _scope(db, request))
    except (StoryAccessError, StoryNotFoundError, StoryValidationError) as exc:
        _raise_story_error(exc)
    return StandardResponse(success=True, message="Story template retrieved", data=data)


@router.put("/story/templates/{template_id}", response_model=StandardResponse)
def update_story_template(
    template_id: str,
    payload: ReportTemplateUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        data = ReportStoryService(db).update_template(template_id, payload, _scope(db, request))
    except (StoryAccessError, StoryConflictError, StoryNotFoundError, StoryValidationError) as exc:
        _raise_story_error(exc)
    return StandardResponse(success=True, message="New story template version saved", data=data)


@router.delete("/story/templates/{template_id}", response_model=StandardResponse)
def archive_story_template(
    template_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        data = ReportStoryService(db).archive_template(template_id, _scope(db, request))
    except (StoryAccessError, StoryNotFoundError, StoryValidationError) as exc:
        _raise_story_error(exc)
    return StandardResponse(success=True, message="Story template archived", data=data)


@router.get("/story/drafts", response_model=StandardResponse)
def list_story_drafts(
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    return StandardResponse(success=True, message="Report drafts retrieved", data=ReportStoryService(db).list_drafts(_scope(db, request)))


@router.post("/story/drafts", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
def create_story_draft(
    payload: ReportDraftCreate,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        data = ReportStoryService(db).create_draft(payload, _scope(db, request))
    except (StoryAccessError, StoryNotFoundError, StoryValidationError) as exc:
        _raise_story_error(exc)
    return StandardResponse(success=True, message="Report draft created and hydrated", data=data)


@router.get("/story/drafts/{draft_id}", response_model=StandardResponse)
def get_story_draft(
    draft_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        data = ReportStoryService(db).get_draft(draft_id, _scope(db, request))
    except (StoryAccessError, StoryNotFoundError, StoryValidationError) as exc:
        _raise_story_error(exc)
    return StandardResponse(success=True, message="Report draft retrieved", data=data)


@router.put("/story/drafts/{draft_id}", response_model=StandardResponse)
def update_story_draft(
    draft_id: str,
    payload: ReportDraftUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        data = ReportStoryService(db).update_draft(draft_id, payload, _scope(db, request))
    except (StoryAccessError, StoryConflictError, StoryNotFoundError, StoryValidationError) as exc:
        _raise_story_error(exc)
    return StandardResponse(success=True, message="Report draft saved", data=data)


@router.delete("/story/drafts/{draft_id}", response_model=StandardResponse)
def archive_story_draft(
    draft_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        data = ReportStoryService(db).archive_draft(draft_id, _scope(db, request))
    except (StoryAccessError, StoryNotFoundError, StoryValidationError) as exc:
        _raise_story_error(exc)
    return StandardResponse(success=True, message="Report draft archived", data=data)


@router.get("/story/drafts/{draft_id}/pages/{page_id}", response_model=StandardResponse)
def resolve_story_page(
    draft_id: str,
    page_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        data = ReportStoryService(db).resolve_slide(draft_id, page_id, _scope(db, request))
    except (StoryAccessError, StoryNotFoundError, StoryValidationError) as exc:
        _raise_story_error(exc)
    return StandardResponse(success=True, message="Report page data resolved", data=data)


@router.post("/story/drafts/{draft_id}/narratives/regenerate", response_model=StandardResponse)
def regenerate_story_narratives(
    draft_id: str,
    payload: NarrativeRegenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        data = ReportStoryService(db).regenerate_narratives(draft_id, payload, _scope(db, request))
    except (StoryAccessError, StoryConflictError, StoryNotFoundError, StoryValidationError) as exc:
        _raise_story_error(exc)
    return StandardResponse(success=True, message="System analysis regenerated", data=data)


@router.post("/story/drafts/{draft_id}/validate", response_model=StandardResponse)
def validate_story_draft(
    draft_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        data = ReportStoryService(db).validate_draft(draft_id, _scope(db, request)).model_dump(mode="json")
    except (StoryAccessError, StoryNotFoundError, StoryValidationError) as exc:
        _raise_story_error(exc)
    return StandardResponse(success=True, message="Report validation completed", data=data)


@router.post("/story/drafts/{draft_id}/generate", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
def generate_story_report(
    draft_id: str,
    payload: ReportGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _user=Depends(require_permission("export_data")),
):
    try:
        scope = _scope(db, request)
        service = ReportStoryService(db)
        if settings.PMS_ASYNC_JOBS_ENABLED:
            draft = service._get_draft(draft_id, scope)
            if draft.version != payload.expected_version:
                raise StoryConflictError("This draft changed before export. Reload and validate again")
            job = ProcessingJobService.create(
                db,
                kind="story_report_generation",
                request_json={
                    "draft_id": draft_id,
                    "request": payload.model_dump(mode="json"),
                    "scope": scope_snapshot(scope),
                },
                requested_by_user_id=scope.get("user_id"),
                requested_by_name=scope.get("username") or "User",
                idempotency_key=_job_key(scope.get("user_id"), idempotency_key),
            )
            return _queued_response(job, "Presentation PDF queued for background generation")
        data = service.generate(draft_id, payload, scope)
    except (StoryAccessError, StoryConflictError, StoryNotFoundError, StoryValidationError) as exc:
        _raise_story_error(exc)
    return StandardResponse(success=True, message="Presentation PDF generated", data=data)


@router.post("/story/generated/{report_id}/duplicate", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
def duplicate_generated_story(
    report_id: str,
    payload: DraftPeriodChange,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        data = ReportStoryService(db).duplicate_generated(report_id, payload.primary_period, payload.comparison_period, _scope(db, request))
    except (StoryAccessError, StoryNotFoundError, StoryValidationError) as exc:
        _raise_story_error(exc)
    return StandardResponse(success=True, message="Historical report duplicated into a fresh draft", data=data)


@router.delete("/story/generated/{report_id}", response_model=StandardResponse)
def delete_generated_story(
    report_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("export_data")),
):
    try:
        data = ReportStoryService(db).delete_generated(report_id, _scope(db, request))
    except (StoryAccessError, StoryNotFoundError, StoryValidationError) as exc:
        _raise_story_error(exc)
    return StandardResponse(success=True, message="Generated report deleted", data=data)


@router.get("/options", response_model=StandardResponse)
def get_report_options(
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    return StandardResponse(
        success=True,
        message="Authorized report filters retrieved",
        data=ReportService(db).options(_scope(db, request)),
    )


@router.get("", response_model=StandardResponse)
def list_reports(
    request: Request,
    mine: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    data = ReportService(db).list_generated(_scope(db, request), mine=mine, page=page, page_size=page_size)
    return StandardResponse(success=True, message="Generated reports retrieved", data=data)


@router.post("/preview", response_model=StandardResponse)
def preview_report(
    configuration: ReportConfiguration,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        data = ReportService(db).preview(configuration, _scope(db, request))
    except (ReportAccessError, ReportNotFoundError, ReportValidationError) as exc:
        _raise_report_error(exc)
    return StandardResponse(success=True, message="Report preview generated", data=data)


@router.post("/generate", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
def generate_report(
    configuration: ReportConfiguration,
    request: Request,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _user=Depends(require_permission("export_data")),
):
    try:
        scope = _scope(db, request)
        service = ReportService(db)
        if settings.PMS_ASYNC_JOBS_ENABLED:
            service._validate_scope(configuration, scope)
            job = ProcessingJobService.create(
                db,
                kind="report_generation",
                request_json={
                    "configuration": configuration.model_dump(mode="json"),
                    "scope": scope_snapshot(scope),
                },
                requested_by_user_id=scope.get("user_id"),
                requested_by_name=scope.get("username") or "User",
                idempotency_key=_job_key(scope.get("user_id"), idempotency_key),
            )
            return _queued_response(job, "Report queued for background generation")
        report = service.generate(configuration, scope)
    except (ReportAccessError, ReportNotFoundError, ReportValidationError) as exc:
        _raise_report_error(exc)
    return StandardResponse(
        success=True,
        message="Report generated successfully",
        data=service.serialize_generated(report),
    )


@router.get("/saved-templates", response_model=StandardResponse)
def list_saved_report_templates(
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    data = ReportService(db).list_saved_templates(_scope(db, request))
    return StandardResponse(success=True, message="Saved report templates retrieved", data=data)


@router.post("/saved-templates", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
def save_report_template(
    payload: SaveReportTemplateRequest,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        service = ReportService(db)
        template = service.save_template(payload.template_name, payload.configuration, _scope(db, request))
    except (ReportAccessError, ReportNotFoundError, ReportValidationError) as exc:
        _raise_report_error(exc)
    return StandardResponse(
        success=True,
        message="Report template saved",
        data={"id": str(template.id), "name": template.name},
    )


@router.delete("/{report_id}", response_model=StandardResponse)
def delete_report(
    report_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("export_data")),
):
    try:
        data = ReportService(db).delete_generated(report_id, _scope(db, request))
    except (ReportAccessError, ReportNotFoundError, ReportValidationError) as exc:
        _raise_report_error(exc)
    return StandardResponse(success=True, message="Generated report deleted", data=data)


@router.get("/{report_id}/download")
def download_report(
    report_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_reports")),
):
    try:
        report = ReportService(db).get_download(report_id, _scope(db, request))
    except (ReportAccessError, ReportNotFoundError, ReportValidationError) as exc:
        _raise_report_error(exc)
    return StreamingResponse(
        BytesIO(report.file_data),
        media_type=report.content_type,
        headers={"Content-Disposition": f'attachment; filename="{report.file_name}"'},
    )
