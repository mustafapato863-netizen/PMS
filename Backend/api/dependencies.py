import time
from uuid import UUID
import pandas as pd
from fastapi import Header, HTTPException, Request
from typing import List, Dict, Any

from repositories.json_repos import (
    JSONPerformanceRepository, JSONEmployeeRepository,
    JSONKPIWeightsRepository, JSONTargetsRepository, JSONUploadsRepository,
    JSONManagerNotesRepository, JSONCorrectiveActionsRepository,
    JSONUserRepository
)
from processors.excel_processor import ExcelProcessor
from services.kpi_service import KPIService
from services.analysis_service import AnalysisService
from services.learning_service import LearningService
from services.planning_service import PlanningService
from services.trend_service import TrendService
from services.insights_service import InsightsService
from models.models import User, Team, UserTeamAssignment
from utils.performance_levels import PERFORMANCE_LEVELS
from utils.team_identity import logical_team_name
from utils.report_scope import (
    filter_records_by_scope as filter_records_for_scope,
    user_can_access_team as scope_can_access_team,
    user_can_access_team_level as scope_can_access_team_level,
)

# ── cache for serialized performance records ──
_serialize_cache: dict[str, tuple[dict, float]] = {}
_SERIALIZE_CACHE_TTL = 300


def clear_serialization_cache() -> None:
    _serialize_cache.clear()

# Instantiate JSON-based repositories (single source of truth)
performance_repo = JSONPerformanceRepository()
employee_repo = JSONEmployeeRepository()
weights_repo = JSONKPIWeightsRepository()
targets_repo = JSONTargetsRepository()
uploads_repo = JSONUploadsRepository()
notes_repo = JSONManagerNotesRepository()
actions_repo = JSONCorrectiveActionsRepository()
user_repo = JSONUserRepository()

# Instantiate services
kpi_service = KPIService(weights_repo, targets_repo)
analysis_service = AnalysisService(targets_repo)
learning_service = LearningService(actions_repo)
planning_service = PlanningService(performance_repo)
trend_service = TrendService()
insights_service = InsightsService(performance_repo, planning_service)
excel_processor = ExcelProcessor()

def safe_float(val) -> float:
    if pd.isna(val):
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def get_overall_trend_label(trend_status) -> str:
    if isinstance(trend_status, dict):
        return trend_status.get("score", {}).get("mom", "Stable")
    return trend_status or "Stable"

def serialize_performance_record(r) -> Dict[str, Any]:
    now = time.time()
    cache_key = f"ser:{r.id}"
    entry = _serialize_cache.get(cache_key)
    if entry is not None and now < entry[1]:
        return entry[0]

    # Reconstruct GeoBreakdown totals
    geo_bookings = {
        "dubai": r.geo.bookings.dubai,
        "sharjah": r.geo.bookings.sharjah,
        "ajman": r.geo.bookings.ajman,
        "clinics": r.geo.bookings.clinics
    }
    geo_attended = {
        "dubai": r.geo.attended.dubai,
        "sharjah": r.geo.attended.sharjah,
        "ajman": r.geo.attended.ajman,
        "clinics": r.geo.attended.clinics
    }
    
    # Resolve actual values with fallback to raw_data if database field is missing/zero
    actual_booking = r.actual.booking_rate or safe_float(r.raw_data.get("A.Booking%", 0.0))
    actual_attend = r.actual.attend_rate or safe_float(r.raw_data.get("A.Attend%", 0.0))
    actual_abandon = r.actual.abandon_rate or safe_float(r.raw_data.get("A.AbandonRate%", 0.0))
    actual_reachability = r.actual.reachability_rate or safe_float(r.raw_data.get("A.Reachability%", 0.0))
    actual_rejection = r.actual.rejection_rate or safe_float(
        r.raw_data.get("IPInitialRejection%")
        or r.raw_data.get("A.RejectionRateAfterRe-Submission")
        or r.raw_data.get("A.RejectionRateAfterResubmission")
        or 0.0
    )
    actual_error = r.actual.initial_error_rate or safe_float(r.raw_data.get("Error%", 0.0))
    actual_submission = r.actual.submission_rate or safe_float(r.raw_data.get("NumberApprovalwithin48hrs", 0.0))
    actual_quality = getattr(r.actual, "quality_rate", 0.0) or safe_float(r.raw_data.get("A.QualityScore", 0.0))
    actual_utz = getattr(r.actual, "utz_rate", 0.0) or safe_float(r.raw_data.get("A.UTZ%", 0.0))

    aht_raw = r.calls.aht_raw
    if aht_raw == "00:00:00" or not aht_raw:
        aht_mins = r.raw_data.get("AHT_Minutes") or safe_float(r.raw_data.get("A.AHT", 0.0)) or safe_float(r.raw_data.get("AHT", 0.0))
        if aht_mins > 0:
            if aht_mins < 1.0 and not r.raw_data.get("AHT_Minutes"):
                aht_mins = aht_mins * 24.0 * 60.0
            from utils.helpers import format_minutes_to_hhmmss
            aht_raw = format_minutes_to_hhmmss(aht_mins)

    record_year = getattr(r, "year", None)
    if not isinstance(record_year, int):
        record_year = None
    record_position = getattr(r, "position", None)
    if not isinstance(record_position, str):
        record_position = None
    record_status = getattr(r, "status", None)
    if not isinstance(record_status, str):
        record_status = None

    result = {
        "id": r.id,
        "employee_id": r.employee_id,
        "employee_name": r.employee_name,
        "team": r.team,
        "month": r.month,
        "year": record_year,
        "region": getattr(r, "region", "EGY") or "EGY",
        "performance_level": getattr(r, "performance_level", "Employee") or "Employee",
        "position": record_position,
        "status": record_status,
        "identity": {
            "name": r.employee_name,
            "month": r.month,
            "team": r.team,
            "employee_id": r.employee_id,
            "position": record_position,
            "region": getattr(r, "region", "EGY") or "EGY",
        },
        "calls": {
            "inbound": r.calls.inbound,
            "outbound": r.calls.outbound,
            "total_handled": r.calls.total_handled,
            "abandoned": r.calls.abandoned,
            "aht_raw": aht_raw
        },
        "geo": {
            "bookings": geo_bookings,
            "attended": geo_attended
        },
        "actual": {
            "booking_rate": actual_booking,
            "attend_rate": actual_attend,
            "abandon_rate": actual_abandon,
            "reachability_rate": actual_reachability,
            "rejection_rate": actual_rejection,
            "initial_error_rate": actual_error,
            "submission_rate": actual_submission,
            "quality_rate": actual_quality,
            "utz_rate": actual_utz
        },
        "achievement": {
            "booking_ach": r.achievement.booking_ach,
            "attend_ach": r.achievement.attend_ach,
            "quality_ach": r.achievement.quality_ach,
            "aht_ach": r.achievement.aht_ach,
            "reachability_ach": r.achievement.reachability_ach,
            "abandon_ach": r.achievement.abandon_ach,
            "rejection_ach": r.achievement.rejection_ach,
            "initial_error_ach": r.achievement.initial_error_ach,
            "submission_ach": r.achievement.submission_ach,
            "op_census_ach": getattr(r.achievement, "op_census_ach", 0.0),
            "op_revenue_ach": getattr(r.achievement, "op_revenue_ach", 0.0),
            "ip_census_ach": getattr(r.achievement, "ip_census_ach", 0.0),
            "ip_revenue_ach": getattr(r.achievement, "ip_revenue_ach", 0.0),
            "activity_ach": getattr(r.achievement, "activity_ach", 0.0)
        },
        "evaluation": {
            "score": r.evaluation.score,
            "grade": r.evaluation.grade,
            "root_cause": r.evaluation.root_cause.model_dump() if r.evaluation.root_cause else None,
            "suggested_action": r.evaluation.suggested_action,
            "corrective_action": r.evaluation.corrective_action,
            "manager_notes": r.evaluation.manager_notes,
            "planning_category": r.evaluation.planning_category,
            "trend_status": get_overall_trend_label(r.evaluation.trend_status)
        },
        "raw_data": r.raw_data,
        "kpi_values": getattr(r, "kpi_values", []) or [],
    }

    _serialize_cache[cache_key] = (result, now + _SERIALIZE_CACHE_TTL)
    return result

def require_role(allowed_roles: List[str]):
    def dependency(
        request: Request,
        x_user_role: str = Header(default="Viewer", alias="X-User-Role")
    ):
        # Check if JWT session is attached to request state
        role = x_user_role
        if hasattr(request.state, "user") and request.state.user:
            role = request.state.user.get("role", x_user_role)

        if role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied for role '{role}'. Required: {allowed_roles}"
            )
        return role
    return dependency


def get_current_user_payload(request: Request) -> dict:
    payload = getattr(request.state, "user", None)
    if not isinstance(payload, dict):
        return {
            "role": request.headers.get("x-user-role", "Viewer"),
            "user_id": request.headers.get("x-user-id", ""),
            "employee_id": request.headers.get("x-user-employee-id", ""),
            "legacy_unscoped": True,
        }
    return payload


def get_current_user_scope(db, request: Request) -> dict:
    payload = get_current_user_payload(request)
    user_id = payload.get("user_id")
    if not user_id:
        if payload.get("legacy_unscoped"):
            return {
                "user_id": "",
                "role": payload.get("role", "Admin"),
                "employee_id": payload.get("employee_id") or "",
                "accessible_teams": [],
                "is_general_manager": True,
                "is_self_only": False,
                "active_team_names": [],
                "legacy_unscoped": True,
            }
        raise HTTPException(status_code=401, detail="Authentication required")

    user = db.query(User).filter(User.id == UUID(str(user_id))).first()
    if not user:
        return {
            "user_id": str(user_id),
            "role": payload.get("role", "Viewer"),
            "employee_id": payload.get("employee_id") or "",
            "accessible_teams": [],
            "is_general_manager": False,
            "is_self_only": payload.get("role") == "Agent",
            "active_team_names": [],
            "legacy_unscoped": True,
        }

    active_teams = db.query(Team).filter(Team.is_active.is_(True)).all()
    active_team_names = list(dict.fromkeys(logical_team_name(team) for team in active_teams))
    assignments = (
        db.query(UserTeamAssignment, Team)
        .join(Team, Team.id == UserTeamAssignment.team_id)
        .filter(UserTeamAssignment.user_id == user.id, Team.is_active.is_(True))
        .all()
    )
    assigned_teams = list(dict.fromkeys(logical_team_name(team) for _, team in assignments))
    accessible_team_levels = list(dict.fromkeys(
        (logical_team_name(team), level)
        for assignment, team in assignments
        for level in ([assignment.performance_level] if assignment.performance_level else PERFORMANCE_LEVELS)
    ))
    unrestricted_teams = {
        logical_team_name(team)
        for assignment, team in assignments
        if assignment.performance_level is None
    }
    is_general_manager = user.role == "Admin" or (
        user.role == "Manager" and bool(active_team_names) and unrestricted_teams >= set(active_team_names)
    )

    if user.role == "Admin" or is_general_manager:
        accessible_teams = active_team_names
    elif user.role == "Manager":
        accessible_teams = assigned_teams
    else:
        accessible_teams = []

    return {
        "user": user,
        "user_id": str(user.id),
        "role": user.role,
        "employee_id": user.employee_id,
        "accessible_teams": accessible_teams,
        "accessible_team_levels": accessible_team_levels,
        "is_general_manager": is_general_manager,
        "is_self_only": user.role == "Agent",
        "active_team_names": active_team_names,
        "legacy_unscoped": False,
    }


def user_can_access_team(scope: dict, team_name: str) -> bool:
    return scope_can_access_team(scope, team_name)


def user_can_access_team_level(scope: dict, team_name: str, performance_level: str) -> bool:
    """Level-specific assignments restrict BSC access; legacy NULL assignments retain all-level access."""
    return scope_can_access_team_level(scope, team_name, performance_level)


def require_authenticated_scope(db, request: Request) -> dict:
    scope = get_current_user_scope(db, request)
    if scope.get("legacy_unscoped"):
        raise HTTPException(status_code=401, detail="Authenticated session required")
    return scope


def filter_records_by_scope(records, scope: dict):
    return filter_records_for_scope(records, scope)
