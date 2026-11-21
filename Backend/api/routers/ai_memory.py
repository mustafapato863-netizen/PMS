"""Self-service and admin endpoints for governed user memory (privacy/GDPR)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.dependencies import require_authenticated_scope
from config.database import get_db, release_read_transaction
from models.models import AiUserMemory
from services.ai.feature_gate import require_ai_access, require_ai_admin, require_ai_enabled
from services.ai.user_memory_service import UserMemoryService

router = APIRouter(
    prefix="/ai/memory",
    tags=["PMS AI Memory"],
    dependencies=[Depends(require_ai_enabled), Depends(require_ai_access)],
)

admin_router = APIRouter(
    prefix="/ai/memory",
    tags=["PMS AI Memory Admin"],
    dependencies=[Depends(require_ai_enabled), Depends(require_ai_admin)],
)


class UserMemoryPreferencesUpdate(BaseModel):
    detail_level: Literal["brief", "detailed", "auto"] | None = None
    communication_style: Literal["formal", "casual", "auto"] | None = None
    preferred_metrics: list[str] | None = Field(default=None, max_length=10)
    preferred_teams: list[str] | None = Field(default=None, max_length=10)


class UserMemorySelfUpdateRequest(BaseModel):
    preferences: UserMemoryPreferencesUpdate | None = None


def _coerce_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value).strip())
    except (ValueError, TypeError, AttributeError):
        return None


@router.get("/me")
def get_my_memory(request: Request, db: Session = Depends(get_db)):
    """View the current user's own stored AI memory (strictly self-scoped)."""
    scope = require_authenticated_scope(db, request)
    user_id = str(scope.get("user_id") or "")
    svc = UserMemoryService(db)
    memory = svc.load_personalization(user_id, include_empty=True)
    release_read_transaction(db)
    return {"memory": memory}


@router.put("/me")
def update_my_memory(
    body: UserMemorySelfUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Update the current user's validated preferences (governed schema)."""
    scope = require_authenticated_scope(db, request)
    user_id = str(scope.get("user_id") or "")
    if not user_id:
        raise HTTPException(status_code=400, detail="Authenticated user id is required")
    updates: dict = {}
    if body.preferences is not None:
        prefs = {
            k: v
            for k, v in body.preferences.model_dump(exclude_none=True).items()
        }
        if "preferred_metrics" in prefs:
            prefs["preferred_metrics"] = [str(m).strip()[:60] for m in prefs["preferred_metrics"] if str(m).strip()][:10]
        if "preferred_teams" in prefs:
            prefs["preferred_teams"] = [str(t).strip()[:60] for t in prefs["preferred_teams"] if str(t).strip()][:10]
        if prefs:
            updates["preferences"] = prefs
    svc = UserMemoryService(db)
    if updates and not svc.save_memory(user_id, updates):
        raise HTTPException(status_code=503, detail="Your preferences could not be saved. Please try again.")
    memory = svc.load_personalization(user_id)
    return {"memory": memory}


@router.delete("/me")
def clear_my_memory(request: Request, db: Session = Depends(get_db)):
    """Clear the current user's own memory (self-service, GDPR)."""
    scope = require_authenticated_scope(db, request)
    user_id = str(scope.get("user_id") or "")
    uid = _coerce_uuid(user_id)
    if uid is None:
        return {"cleared": False}
    try:
        row = db.query(AiUserMemory).filter(AiUserMemory.user_id == uid).first()
        if row is None:
            return {"cleared": False}
        db.delete(row)
        db.commit()
        return {"cleared": True}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@admin_router.get("/")
def list_user_memory_stats(request: Request, db: Session = Depends(get_db)):
    """Get aggregate memory stats (Admin only)."""
    require_authenticated_scope(db, request)
    total = db.query(AiUserMemory).count()
    release_read_transaction(db)
    return {"total_users_with_memory": total}


@admin_router.get("/{user_id}")
def get_user_memory(user_id: str, request: Request, db: Session = Depends(get_db)):
    """View a user's stored memory (Admin only)."""
    require_authenticated_scope(db, request)
    svc = UserMemoryService(db)
    memory = svc.load_personalization(user_id)
    release_read_transaction(db)
    if memory is None:
        return {"user_id": user_id, "memory": None, "message": "No memory found"}
    return {"user_id": user_id, "memory": memory}


@admin_router.delete("/{user_id}")
def clear_user_memory(user_id: str, request: Request, db: Session = Depends(get_db)):
    """Clear a user's stored memory (Admin only, GDPR compliance)."""
    require_authenticated_scope(db, request)
    uid = _coerce_uuid(user_id)
    if uid is None:
        return {"user_id": user_id, "cleared": False, "message": "Invalid user_id"}
    try:
        row = db.query(AiUserMemory).filter(AiUserMemory.user_id == uid).first()
        if row is None:
            return {"user_id": user_id, "cleared": False, "message": "No memory found"}
        db.delete(row)
        db.commit()
        return {"user_id": user_id, "cleared": True, "message": "Memory cleared"}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
