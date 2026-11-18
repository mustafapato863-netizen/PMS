"""Agent 360° profile endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.dependencies import get_db, get_current_user_scope
from services.ai.agent_360_service import Agent360Service
from services.ai.identity_service import build_passport

router = APIRouter(prefix="/api/ai", tags=["ai-agent-360"])


@router.get("/agent-360")
def get_agent_360(request, db: Session = Depends(get_db)):
    """Zero-LLM Agent 360° profile for the authenticated user."""
    scope = get_current_user_scope(db, request)
    passport = build_passport(scope)

    if not passport.is_linked_employee:
        raise HTTPException(
            status_code=400,
            detail="Your account isn't linked to an employee profile yet. Please contact your manager.",
        )

    svc = Agent360Service(db)
    profile = svc.get_agent_360(passport.employee_code, scope)
    if profile is None:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    return profile
