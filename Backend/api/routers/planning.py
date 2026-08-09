from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from api.dependencies import performance_repo, require_authenticated_scope
from api.middleware.rbac_middleware import require_permission
from config.database import get_db
from models.planning_schemas import (
    PlanCreate,
    PlanItemUpdate,
    PlanMilestoneCreate,
    PlanMilestoneUpdate,
    PlanNoteCreate,
    PlanUpdate,
)
from models.schemas import StandardResponse
from services.planning_service import PlanningAccessError, PlanningNotFoundError, PlanningService, PlanningValidationError


router = APIRouter(prefix="/planning", tags=["Planning"])


def _service(db: Session) -> PlanningService:
    return PlanningService(performance_repo, db=db)


def _scope(db: Session, request: Request) -> dict:
    return require_authenticated_scope(db, request)


def _raise(exc: Exception):
    if isinstance(exc, PlanningAccessError): raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, PlanningNotFoundError): raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, PlanningValidationError): raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.get("/options", response_model=StandardResponse)
def options(request: Request, db: Session = Depends(get_db), _user=Depends(require_permission("view_plans"))):
    return StandardResponse(success=True, message="Authorized planning options retrieved", data=_service(db).options(_scope(db, request)))


@router.get("", response_model=StandardResponse)
def list_plans(request: Request, team: str | None = None, owner_id: str | None = None, plan_status: str | None = Query(None, alias="status"), search: str | None = None, db: Session = Depends(get_db), _user=Depends(require_permission("view_plans"))):
    return StandardResponse(success=True, message="Authorized plans retrieved", data=_service(db).list(_scope(db, request), team, owner_id, plan_status, search))


@router.post("", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
def create_plan(payload: PlanCreate, request: Request, db: Session = Depends(get_db), _user=Depends(require_permission("manage_plans"))):
    try:
        service = _service(db); plan = service.create(payload, _scope(db, request))
        return StandardResponse(success=True, message="Plan activated" if payload.activate else "Plan saved as draft", data=service.get(str(plan.id), _scope(db, request)))
    except (PlanningAccessError, PlanningNotFoundError, PlanningValidationError) as exc: _raise(exc)


@router.get("/{plan_id}", response_model=StandardResponse)
def get_plan(plan_id: str, request: Request, db: Session = Depends(get_db), _user=Depends(require_permission("view_plans"))):
    try: return StandardResponse(success=True, message="Plan retrieved", data=_service(db).get(plan_id, _scope(db, request)))
    except (PlanningAccessError, PlanningNotFoundError, PlanningValidationError) as exc: _raise(exc)


@router.put("/{plan_id}", response_model=StandardResponse)
def update_plan(plan_id: str, payload: PlanUpdate, request: Request, db: Session = Depends(get_db), _user=Depends(require_permission("manage_plans"))):
    try: return StandardResponse(success=True, message="Plan updated", data=_service(db).update(plan_id, payload, _scope(db, request)))
    except (PlanningAccessError, PlanningNotFoundError, PlanningValidationError) as exc: _raise(exc)


@router.delete("/{plan_id}", response_model=StandardResponse)
def delete_plan(plan_id: str, request: Request, db: Session = Depends(get_db), _user=Depends(require_permission("manage_plans"))):
    try:
        return StandardResponse(success=True, message="Plan deleted", data=_service(db).delete(plan_id, _scope(db, request)))
    except (PlanningAccessError, PlanningNotFoundError, PlanningValidationError) as exc:
        _raise(exc)


@router.patch("/{plan_id}/{kind}/{item_id}", response_model=StandardResponse)
def update_plan_item(plan_id: str, kind: str, item_id: str, payload: PlanItemUpdate, request: Request, db: Session = Depends(get_db), _user=Depends(require_permission("manage_plans"))):
    if kind not in {"objective", "kpi", "action", "milestone"}: raise HTTPException(status_code=404, detail="Plan item not found")
    try: return StandardResponse(success=True, message="Plan item updated", data=_service(db).update_item(plan_id, kind, item_id, payload, _scope(db, request)))
    except (PlanningAccessError, PlanningNotFoundError, PlanningValidationError) as exc: _raise(exc)


@router.post("/{plan_id}/milestones", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
def add_milestone(plan_id: str, payload: PlanMilestoneCreate, request: Request, db: Session = Depends(get_db), _user=Depends(require_permission("manage_plans"))):
    try: return StandardResponse(success=True, message="Milestone added", data=_service(db).add_milestone(plan_id, payload, _scope(db, request)))
    except (PlanningAccessError, PlanningNotFoundError, PlanningValidationError) as exc: _raise(exc)


@router.put("/{plan_id}/milestones/{milestone_id}", response_model=StandardResponse)
def update_milestone(plan_id: str, milestone_id: str, payload: PlanMilestoneUpdate, request: Request, db: Session = Depends(get_db), _user=Depends(require_permission("manage_plans"))):
    try: return StandardResponse(success=True, message="Milestone updated", data=_service(db).update_milestone(plan_id, milestone_id, payload, _scope(db, request)))
    except (PlanningAccessError, PlanningNotFoundError, PlanningValidationError) as exc: _raise(exc)


@router.delete("/{plan_id}/milestones/{milestone_id}", response_model=StandardResponse)
def delete_milestone(plan_id: str, milestone_id: str, request: Request, db: Session = Depends(get_db), _user=Depends(require_permission("manage_plans"))):
    try: return StandardResponse(success=True, message="Milestone deleted", data=_service(db).delete_milestone(plan_id, milestone_id, _scope(db, request)))
    except (PlanningAccessError, PlanningNotFoundError, PlanningValidationError) as exc: _raise(exc)


@router.post("/{plan_id}/notes", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
def add_plan_note(plan_id: str, payload: PlanNoteCreate, request: Request, db: Session = Depends(get_db), _user=Depends(require_permission("manage_plans"))):
    try: return StandardResponse(success=True, message="Review note added", data=_service(db).add_note(plan_id, payload, _scope(db, request)))
    except (PlanningAccessError, PlanningNotFoundError, PlanningValidationError) as exc: _raise(exc)
