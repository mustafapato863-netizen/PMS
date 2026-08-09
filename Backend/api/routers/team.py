from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from api.dependencies import get_current_user_scope
from api.middleware.rbac_middleware import require_permission
from config.database import get_db
from models.schemas import StandardResponse
from services.team_action_service import TeamActionService


router = APIRouter()


@router.get("/", response_model=StandardResponse)
async def get_team_action(
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
async def save_team_action(
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
    except Exception:
        return StandardResponse(success=False, message="Failed to save team action.")
