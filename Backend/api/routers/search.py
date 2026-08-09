from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from api.dependencies import get_current_user_scope, require_authenticated_scope
from config.database import get_db
from models.schemas import StandardResponse
from services.employee_directory_service import EmployeeDirectoryService


router = APIRouter(prefix="/search", tags=["Search"])


def _matches(value: str | None, query: str) -> bool:
    return query in str(value or "").strip().lower()


@router.get("/global", response_model=StandardResponse)
def global_search(
    request: Request,
    db: Session = Depends(get_db),
    q: str = Query("", max_length=100),
    limit: int = Query(6, ge=1, le=20),
):
    scope = require_authenticated_scope(db, request)
    query = q.strip().lower()
    role = scope.get("role")

    if role in {"Admin", "Executive"} or scope.get("is_general_manager"):
        allowed_teams = list(dict.fromkeys(scope.get("active_team_names", [])))
    elif role == "Manager":
        allowed_teams = list(dict.fromkeys(scope.get("accessible_teams", [])))
    else:
        allowed_teams = []

    teams = [
        {
            "name": team_name,
            "subtitle": "Team dashboard",
        }
        for team_name in sorted(allowed_teams)
        if not query or _matches(team_name, query)
    ][:limit]

    employees = []
    if query:
        all_employees = EmployeeDirectoryService(db).list(name=query)
        if role in {"Admin", "Manager", "Executive"}:
            visible = [
                employee for employee in all_employees
                if employee["status"] == "Active" and employee["team"] in allowed_teams
            ]
        elif role == "Agent":
            self_id = str(scope.get("employee_id") or scope.get("user_id") or "")
            visible = [
                employee for employee in all_employees
                if employee["status"] == "Active" and str(employee["id"]) == self_id
            ]
        else:
            visible = []

        employees = [
            {
                "id": str(employee["id"]),
                "name": employee["name"],
                "employee_id": str(employee["employee_id"]),
                "team": employee["team"],
                "performance_level": employee["performance_level"],
            }
            for employee in visible
            if _matches(employee["name"], query) or _matches(employee["id"], query)
        ][:limit]

    return StandardResponse(
        success=True,
        message="Global search results retrieved successfully",
        data={
            "query": q,
            "teams": teams,
            "employees": employees,
        },
    )
