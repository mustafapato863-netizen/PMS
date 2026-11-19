"""Agent 360° profile, authorized directory, and zero-LLM What-If endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.dependencies import require_authenticated_scope
from config.database import get_db, release_read_transaction
from services.ai.agent_360_service import Agent360Service
from services.ai.feature_gate import require_ai_access, require_ai_enabled
from services.ai.identity_service import PersonaTier, build_passport

router = APIRouter(
    prefix="/ai",
    tags=["PMS AI Agent 360"],
    dependencies=[Depends(require_ai_enabled), Depends(require_ai_access)],
)


class WhatIfSimulationRequest(BaseModel):
    kpi_name: str = Field(..., min_length=1, max_length=120)
    improvement_pct: float = Field(..., ge=-100.0, le=100.0)
    employee_code: str | None = Field(default=None, max_length=50)


def _resolve_target_employee_code(
    passport,
    requested_employee_code: str | None,
) -> str:
    if passport.persona_tier == PersonaTier.SELF_ONLY:
        if not passport.employee_code:
            raise HTTPException(
                status_code=400,
                detail="Your account isn't linked to an employee profile yet. Please contact your manager.",
            )
        if requested_employee_code and requested_employee_code.strip() != passport.employee_code:
            raise HTTPException(
                status_code=403,
                detail="You can only view your own 360° profile.",
            )
        return passport.employee_code

    target = (requested_employee_code or "").strip() or passport.employee_code
    if not target:
        raise HTTPException(
            status_code=400,
            detail="Your account isn't linked to an employee profile yet. Specify an employee_code or contact your administrator.",
        )
    return target


@router.get("/agent-360/directory")
def get_agent_360_directory(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List authorized employees for Managers/Admins to inspect 360° scorecards."""
    scope = require_authenticated_scope(db, request)
    svc = Agent360Service(db)
    employees = svc.list_authorized_employees(scope, limit=limit)
    release_read_transaction(db)
    return {"employees": employees}


@router.get("/agent-360")
def get_agent_360(
    request: Request,
    employee_code: str | None = Query(default=None, max_length=50),
    db: Session = Depends(get_db),
):
    """Zero-LLM Agent 360° profile for the authenticated user (or authorized report)."""
    scope = require_authenticated_scope(db, request)
    passport = build_passport(scope, db=db)
    target_code = _resolve_target_employee_code(passport, employee_code)

    svc = Agent360Service(db)
    try:
        profile = svc.get_agent_360(target_code, scope)
    except PermissionError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    release_read_transaction(db)
    if profile is None:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    return profile


@router.post("/agent-360/what-if")
def post_agent_360_what_if(
    body: WhatIfSimulationRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Deterministic zero-LLM What-If simulation against the employee's latest KPIs."""
    scope = require_authenticated_scope(db, request)
    passport = build_passport(scope, db=db)
    target_code = _resolve_target_employee_code(passport, body.employee_code)

    svc = Agent360Service(db)
    try:
        result = svc.simulate_what_if(target_code, body.kpi_name, body.improvement_pct, scope=scope)
    except PermissionError as exc:
        release_read_transaction(db)
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    release_read_transaction(db)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unable to simulate KPI '{body.kpi_name}' for this employee profile.",
        )
    return result
