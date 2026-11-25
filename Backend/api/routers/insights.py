from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from api.dependencies import require_authenticated_scope, require_role
from config.database import get_db, release_read_transaction
from models.insight_schemas import InsightFilterOptions, InsightKpiOverview, InsightsWorkspace, InsightsWorkspaceResponse
from services.database_record_source import DatabaseRecordSource
from services.insights_service import InsightAccessError, InsightValidationError, InsightsService, normalize_workspace_sections
from services.planning_service import PlanningService
from services.response_cache import (
    apply_private_cache_headers,
    build_scoped_response_cache_key,
    read_cached_response,
    write_cached_response,
)


router = APIRouter(prefix="/insights", tags=["Insights"])


def _priority_workspace(workspace: InsightsWorkspace, *, limit: int = 10) -> InsightsWorkspace:
    """Compact response for consumers that only render decision priorities."""
    return workspace.model_copy(update={
        "priority_insights": workspace.priority_insights[:limit],
        "team_analyses": [],
        "performance_drivers": [],
        "risks": [],
        "opportunities": [],
        "data_issues": [],
        "team_summaries": [],
        "people_contribution_analysis": None,
        "kpi_trend": None,
        "role_summaries": [],
        "kpi_overview": InsightKpiOverview(),
        "options": InsightFilterOptions(),
    })


@router.get("/workspace", response_model=InsightsWorkspaceResponse)
def get_insights_workspace(
    request: Request,
    db: Session = Depends(get_db),
    month: str | None = Query(default=None),
    year: int | None = Query(default=None, ge=2000, le=2100),
    region: str | None = Query(default=None),
    team: str | None = Query(default=None),
    function: str | None = Query(
        default=None,
        description=(
            "Parent function (Call Center, RCM, Pre-Approvals, or a standalone team). "
            "Expands to the function's source teams intersected with the caller's authorized scope."
        ),
    ),
    performance_level: str | None = Query(default=None),
    position: str | None = Query(default=None),
    employee_id: str | None = Query(default=None),
    kpi: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    insight_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    branch: str | None = Query(default=None, description="Branch key (dubai, sharjah, ajman, clinics). Narrows records to the selected branch."),
    view: Literal["full", "priority"] = Query(default="full"),
    # Comma-separated InsightsWorkspace fields to compute, for example `options,comparison,kpi_trend`. Absent
    # means every field, as before; unrequested fields are not computed and come back empty.
    sections: str | None = None,
    response: Response = None,
    _role: str = Depends(require_role([
        "Admin", "General Manager", "Manager", "Executive", "Performance Team",
        "Regional Manager", "Branch Director", "Function Director",
    ])),
):
    if bool(month) != bool(year):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Month and year must be selected together",
        )
    scope = require_authenticated_scope(db, request)
    normalized_branch = branch if isinstance(branch, str) else None
    cache_key: str | None = None
    try:
        normalized_sections = normalize_workspace_sections(sections)
    except InsightValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if isinstance(db, Session):
        cache_key = build_scoped_response_cache_key(
            db,
            namespace="insights-workspace",
            scope=scope,
            params={
                "today": date.today().isoformat(),
                "view": view,
                "sections": sorted(normalized_sections) if normalized_sections is not None else None,
                "month": month.strip().casefold() if isinstance(month, str) and month.strip() else None,
                "year": year,
                "region": region.strip().casefold() if isinstance(region, str) and region.strip() else None,
                "team": team.strip().casefold() if isinstance(team, str) and team.strip() else None,
                "function": function.strip().casefold() if isinstance(function, str) and function.strip() else None,
                "performance_level": performance_level.strip().casefold() if isinstance(performance_level, str) and performance_level.strip() else None,
                "position": position.strip().casefold() if isinstance(position, str) and position.strip() else None,
                "employee_id": employee_id,
                "kpi": kpi.strip().casefold() if isinstance(kpi, str) and kpi.strip() else None,
                "severity": severity.strip().casefold() if isinstance(severity, str) and severity.strip() else None,
                "insight_type": insight_type.strip().casefold() if isinstance(insight_type, str) and insight_type.strip() else None,
                "status": status_filter.strip().casefold() if isinstance(status_filter, str) and status_filter.strip() else None,
                "branch": normalized_branch.strip().casefold() if normalized_branch and normalized_branch.strip() else None,
            },
        )
        cached = read_cached_response(cache_key, cache_type="insights_workspace")
        if isinstance(cached, dict):
            release_read_transaction(db)
            apply_private_cache_headers(response, hit=True)
            return InsightsWorkspaceResponse(
                success=True,
                message="Authorized insights generated",
                data=InsightsWorkspace.model_validate(cached),
            )
    try:
        source = DatabaseRecordSource(db)
        workspace = InsightsService(
            source,
            PlanningService(source, db=db),
            db=db,
        ).generate_workspace(
            scope,
            priority_only=view == "priority",
            sections=sections,
            month=month,
            year=year,
            region=region,
            team=team,
            function=function,
            performance_level=performance_level,
            position=position,
            employee_id=employee_id,
            kpi=kpi,
            severity=severity,
            insight_type=insight_type,
            insight_status=status_filter,
            branch=normalized_branch,
        )
    except InsightAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except InsightValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if view == "priority":
        workspace = _priority_workspace(workspace)
    if cache_key is not None:
        write_cached_response(
            cache_key,
            workspace.model_dump(mode="json"),
            cache_type="insights_workspace",
        )
    release_read_transaction(db)
    apply_private_cache_headers(response, hit=False)
    return InsightsWorkspaceResponse(success=True, message="Authorized insights generated", data=workspace)
