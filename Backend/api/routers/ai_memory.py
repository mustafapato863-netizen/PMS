"""Admin endpoints for user memory management (privacy/GDPR)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.dependencies import get_db, get_current_user_scope
from models.models import AiUserMemory, User
from services.ai.user_memory_service import UserMemoryService
from services.ai.identity_service import build_passport

router = APIRouter(prefix="/api/ai/memory", tags=["ai-memory"])


@router.get("/me")
def get_my_memory(request, db: Session = Depends(get_db)):
    """View the current user's own memory (self-service)."""
    scope = get_current_user_scope(db, request)
    user_id = str(scope.get("user_id") or "")
    svc = UserMemoryService(db)
    memory = svc.load_memory(user_id)
    return {"memory": memory}


@router.delete("/me")
def clear_my_memory(request, db: Session = Depends(get_db)):
    """Clear the current user's own memory (self-service, GDPR)."""
    scope = get_current_user_scope(db, request)
    user_id = str(scope.get("user_id") or "")
    try:
        row = db.query(AiUserMemory).filter(AiUserMemory.user_id == user_id).first()
        if row is None:
            return {"cleared": False}
        db.delete(row)
        db.commit()
        return {"cleared": True}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{user_id}")
def get_user_memory(user_id: str, db: Session = Depends(get_db)):
    """View a user's stored memory (admin only)."""
    svc = UserMemoryService(db)
    memory = svc.load_memory(user_id)
    if memory is None:
        return {"user_id": user_id, "memory": None, "message": "No memory found"}
    return {"user_id": user_id, "memory": memory}


@router.delete("/{user_id}")
def clear_user_memory(user_id: str, db: Session = Depends(get_db)):
    """Clear a user's stored memory (admin only, GDPR compliance)."""
    try:
        row = db.query(AiUserMemory).filter(AiUserMemory.user_id == user_id).first()
        if row is None:
            return {"user_id": user_id, "cleared": False, "message": "No memory found"}
        db.delete(row)
        db.commit()
        return {"user_id": user_id, "cleared": True, "message": "Memory cleared"}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/")
def list_user_memory_stats(db: Session = Depends(get_db)):
    """Get aggregate memory stats (admin only)."""
    total = db.query(AiUserMemory).count()
    return {"total_users_with_memory": total}
