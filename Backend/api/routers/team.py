from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.dependencies import get_current_user_scope
from api.middleware.rbac_middleware import require_permission
from config.database import get_db
from models.schemas import StandardResponse
from services.team_action_service import TeamActionService


router = APIRouter()


class TeamPlanItemSaveRequest(BaseModel):
    card_id: str = Field(..., min_length=1, max_length=200)
    team: str = Field(..., min_length=1, max_length=120)
    region: Optional[str] = Field(default=None, max_length=20)
    month: str = Field(..., min_length=1, max_length=30)
    year: int = Field(..., ge=2000, le=2100)
    title: str = Field(..., min_length=1, max_length=2000)
    target_kpi: str = Field(default="", max_length=500)
    scope_description: str = Field(default="", max_length=1000)
    owner: str = Field(default="", max_length=200)
    status: Literal["Open", "In Progress", "Completed", "Planned"] = "Open"
    due_date: Optional[str] = Field(default=None, max_length=32)
    expected_team_impact: str = Field(default="", max_length=500)


class TeamPlanItemResponse(BaseModel):
    id: str
    card_id: str
    team: str
    region: Optional[str] = None
    month: str
    year: int
    title: str
    target_kpi: str = ""
    scope_description: str = ""
    owner: str = ""
    status: Literal["Open", "In Progress", "Completed", "Planned"] = "Open"
    due_date: Optional[str] = None
    expected_team_impact: str = ""
    updated_at: Optional[str] = None
    is_deleted: bool = False


@router.get("/", response_model=StandardResponse)
def get_team_action(
    request: Request,
    team_id: str = Query(...),
    month: str = Query(...),
    year: int = Query(..., ge=2000, le=2100),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_actions")),
):
    try:
        action = TeamActionService(db).get(
            team_reference=team_id,
            month=month,
            year=year,
            scope=get_current_user_scope(db, request),
        )
        return StandardResponse(
            success=True,
            message="Team action retrieved successfully",
            data=action,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        return StandardResponse(success=False, message="Failed to load team action.")


@router.post("/", response_model=StandardResponse)
def save_team_action(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("create_actions")),
):
    team_id = str(payload.get("team_id") or "").strip()
    month = str(payload.get("month") or "").strip()
    overall_action = str(payload.get("overall_action") or "").strip()
    if not team_id or not month or payload.get("year") is None:
        raise HTTPException(status_code=400, detail="team_id, month and year are required")
    try:
        year = int(payload["year"])
        if year < 2000 or year > 2100:
            raise ValueError("Invalid year")
        action = TeamActionService(db).save(
            team_reference=team_id,
            month=month,
            year=year,
            overall_action=overall_action,
            scope=get_current_user_scope(db, request),
            user_id=(getattr(request.state, "user", None) or {}).get("user_id"),
        )
        return StandardResponse(
            success=True,
            message="Team action saved successfully",
            data=action,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "Team not found" else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HTTPException:
        raise


@router.get("/plan-items", response_model=StandardResponse)
def list_team_plan_items(
    request: Request,
    team: str = Query(..., min_length=1),
    month: str = Query(..., min_length=1),
    year: int = Query(..., ge=2000, le=2100),
    region: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("view_actions")),
):
    try:
        scope = get_current_user_scope(db, request)
        items = TeamActionService(db).list_plan_items(
            team_name=team,
            month=month,
            year=year,
            current_user=scope,
            region=region,
        )
        validated = [TeamPlanItemResponse(**item).model_dump() for item in items]
        return StandardResponse(
            success=True,
            message="Team plan items retrieved successfully",
            data=validated,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "Team not found" else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        return StandardResponse(success=False, message="Failed to load team plan items.")


@router.post("/plan-items", response_model=StandardResponse)
def save_team_plan_item(
    payload: TeamPlanItemSaveRequest,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("create_actions")),
):
    try:
        scope = get_current_user_scope(db, request)
        saved = TeamActionService(db).save_plan_item(
            payload.model_dump(),
            current_user=scope,
        )
        validated = TeamPlanItemResponse(**saved).model_dump()
        return StandardResponse(
            success=True,
            message="Team plan item saved successfully",
            data=validated,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "Team not found" else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        return StandardResponse(success=False, message="Failed to save team plan item.")


@router.delete("/plan-items/{card_id}", response_model=StandardResponse)
def delete_team_plan_item(
    card_id: str,
    request: Request,
    team: str = Query(..., min_length=1),
    month: str = Query(..., min_length=1),
    year: int = Query(..., ge=2000, le=2100),
    region: Optional[str] = Query(default=None),
    purge_tombstone: bool = Query(default=False),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("create_actions")),
):
    try:
        scope = get_current_user_scope(db, request)
        deleted = TeamActionService(db).delete_plan_item(
            card_id=card_id,
            team_name=team,
            month=month,
            year=year,
            current_user=scope,
            region=region,
            purge_tombstone=purge_tombstone,
        )
        validated = TeamPlanItemResponse(**deleted).model_dump()
        return StandardResponse(
            success=True,
            message="Team plan item deleted successfully",
            data=validated,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "Team not found" else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        return StandardResponse(success=False, message="Failed to delete team plan item.")
