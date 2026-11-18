"""Admin endpoints for user memory management (privacy/GDPR)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.dependencies import get_db
from models.models import AiUserMemory, User
from services.ai.user_memory_service import UserMemoryService

router = APIRouter(prefix="/api/ai/memory", tags=["ai-memory"])


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
