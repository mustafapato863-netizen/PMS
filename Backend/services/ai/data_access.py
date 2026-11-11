"""Authorized read-only PMS data access layer for the unified AI engine (Phase 2).

Security and Architectural Invariants:
1. Gated by default to the Admin-only AI pilot policy (enforce_pilot=True).
   Non-admin callers are strictly rejected with PermissionError.
2. Server-side identity & scope resolution: user_scope is verified from the
   authenticated session, never client-supplied overrides.
3. Read-only session guarantee: Every database interaction is executed within
   `ReadOnlySessionGuard`. Any attempt to stage ORM writes or flush raises
   `RuntimeError("AI read tools cannot write to the database")`.
4. Zero arbitrary SQL: No dynamic queries, raw SQL strings, or arbitrary shell commands.
   All reads use authoritative services (DashboardRecordService,
   CorrectiveActionEvidenceService, config.loader).
5. Cross-scope isolation:
   - Regional isolation (Egypt vs UAE): users cannot read records outside their assigned regions.
   - Branch isolation (Dubai vs Sharjah vs Abu Dhabi): restricted branch roles cannot cross boundaries.
   - Team & employee isolation: users cannot access teams or employees outside their scope.
6. Numerical & Historical Integrity:
   - Missing data stays None, never coerced to 0.0.
   - Real measured 0.0 is preserved as 0.0.
   - Direction (higher_is_better, lower_is_better), units, weights, and scoring bases are preserved.
   - Never invents missing data, demo data, or artificial rankings.
7. Data Minimization & Sanitization:
   - Credentials, passwords, tokens, full database dumps, upload blobs, and sensitive contact PII
     are excluded.
   - All input parameters are sanitized against SQL injection and script injection patterns.
   - Returns structured evidence with explicit source and scope metadata.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

from sqlalchemy.orm import Session

from config.loader import get_team_names, load_team_config
from models.models import Employee, PerformanceRecord, Team
from services.ai.corrective_action_evidence import CorrectiveActionEvidenceService
from services.ai.feature_gate import AI_PILOT_ROLE
from services.ai.read_only_guard import ReadOnlySessionGuard
from services.corrective_action_service import CorrectiveActionService
from services.dashboard_record_service import DashboardRecordService
from utils.kpi_direction import resolve_kpi_direction
from utils.performance_levels import normalize_performance_level
from utils.report_scope import (
    filter_records_by_scope,
    functions_for_team,
    user_can_access_region,
    user_can_access_team,
    user_can_access_team_level,
)

logger = logging.getLogger(__name__)

# Disallow any parameter values containing SQL control characters or keywords
_UNSAFE_PARAM_RE = re.compile(
    r"(?:[\x00-\x08\x0b\x0c\x0e-\x1f]|[;<>`'\"]|--|/\*|\*/|\.\./|\.\.\\|"
    r"\b(?:select|union|insert|update|delete|drop|alter|create|truncate|exec|execute|pragma|xp_|sp_|sleep|benchmark)\b|"
    r"\bor\s+['\"]?\w+['\"]?\s*=\s*['\"]?\w+)",
    re.IGNORECASE,
)

# Supported tool operations
SUPPORTED_OPERATIONS: frozenset[str] = frozenset({
    "list_authorized_scopes",
    "get_performance_summary",
    "get_kpi_details",
    "get_corrective_action_context",
})

# Pilot teams with tested and verified calculation parity across test suites
TESTED_PILOT_TEAMS: frozenset[str] = frozenset({
    "Inbound",
    "Pre-Approvals OP Dubai",
    "Outbound",
    "Coding",
    "Submission",
})

# Backward compatibility alias
VERIFIED_TEAMS: frozenset[str] = TESTED_PILOT_TEAMS


def _validate_param_safety(key: str, value: Any) -> None:
    """Reject parameters that resemble SQL injection, script tags, or control characters."""
    if isinstance(value, str):
        if _UNSAFE_PARAM_RE.search(value):
            logger.warning("Rejected unsafe parameter '%s' with pattern match", key)
            raise ValueError(f"Unsafe parameter value detected for '{key}'")
    elif isinstance(value, dict):
        for sub_k, sub_v in value.items():
            _validate_param_safety(f"{key}.{sub_k}", sub_v)
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _validate_param_safety(f"{key}[{idx}]", item)


def _float_or_none(value: Any) -> float | None:
    """Return float(value) preserving None and real 0.0."""
    if value is None or isinstance(value, bool):
        return None
    try:
        val = float(value)
        return val if val == val else None  # Filter NaN
    except (TypeError, ValueError):
        return None


class PmsAiDataAccess:
    """Authorized, read-only data access layer for PMS AI operations."""

    def __init__(
        self,
        db: Session,
        *,
        dashboard_service: DashboardRecordService | None = None,
        evidence_service: CorrectiveActionEvidenceService | None = None,
        corrective_action_service: CorrectiveActionService | None = None,
    ) -> None:
        self.db = db
        self.dashboard_service = dashboard_service or DashboardRecordService(db)
        self.evidence_service = evidence_service or CorrectiveActionEvidenceService(db)
        self.corrective_action_service = corrective_action_service or CorrectiveActionService(db)

    # -----------------------------------------------------------------------
    # Pilot Authorization Check
    # -----------------------------------------------------------------------

    def verify_pilot_authorization(self, user_scope: dict[str, Any]) -> None:
        """Enforce the Admin-only AI pilot policy.
        
        During the pilot, non-Admin users are strictly prohibited from accessing PMS AI data tools.
        """
        role = str(user_scope.get("role") or user_scope.get("db_role") or "").strip()
        if role != AI_PILOT_ROLE:
            logger.warning("AI pilot access rejected for role '%s' (pilot requires %s)", role, AI_PILOT_ROLE)
            raise PermissionError(f"PMS AI data access is restricted to {AI_PILOT_ROLE} during the pilot phase")

    # -----------------------------------------------------------------------
    # Operation 1: List Authorized Scopes
    # -----------------------------------------------------------------------

    def list_authorized_scopes(
        self,
        user_scope: dict[str, Any],
        *,
        enforce_pilot: bool = True,
    ) -> dict[str, Any]:
        """List functions, teams, regions, and branches authorized for the current user.
        
        Returns minimized scope metadata without exposing system internals.
        """
        with ReadOnlySessionGuard(self.db, allow_preexisting_writes=True):
            if enforce_pilot:
                self.verify_pilot_authorization(user_scope)

            role = str(user_scope.get("role") or user_scope.get("db_role") or "Viewer").strip()
            accessible_teams = list(user_scope.get("accessible_teams") or [])
            accessible_functions = list(user_scope.get("accessible_functions") or [])
            accessible_regions = list(user_scope.get("accessible_regions") or [])
            accessible_branches = list(user_scope.get("accessible_branches") or [])
            has_unrestricted = bool(user_scope.get("has_unrestricted_team_access"))

            configured_teams = sorted(get_team_names())
            tested_teams = sorted([t for t in TESTED_PILOT_TEAMS if t in configured_teams])
            unverified_teams = sorted([t for t in configured_teams if t not in TESTED_PILOT_TEAMS])

            return {
                "role": role,
                "has_unrestricted_access": has_unrestricted,
                "accessible_teams": sorted(accessible_teams),
                "accessible_functions": sorted(accessible_functions),
                "accessible_regions": sorted(accessible_regions),
                "accessible_branches": sorted(accessible_branches),
                "configured_teams": configured_teams,
                "tested_pilot_teams": tested_teams,
                "unverified_teams": unverified_teams,
                "audit_status": "partial_pilot_tested",
                "source_metadata": {
                    "source": "pms_rbac_scope",
                    "read_only": True,
                    "verified": True,
                    "scope_verified": True,
                },
            }

    # -----------------------------------------------------------------------
    # Operation 2: Get Performance Summary
    # -----------------------------------------------------------------------

    def get_performance_summary(
        self,
        user_scope: dict[str, Any],
        *,
        team: str,
        month: str,
        year: int,
        employee_id: str | None = None,
        performance_level: str = "Employee",
        enforce_pilot: bool = True,
    ) -> dict[str, Any]:
        """Retrieve authorized team or employee performance summary for a period.
        
        Guarantees:
        - Scope verification before reading any rows.
        - Preserves real zero values vs missing records.
        - Read-only execution under ReadOnlySessionGuard with caller write preservation.
        - Never guesses, hallucinates scores, or invents demo data.
        """
        with ReadOnlySessionGuard(self.db, allow_preexisting_writes=True):
            if enforce_pilot:
                self.verify_pilot_authorization(user_scope)

            team_name = str(team or "").strip()
            if not team_name:
                raise ValueError("team is required")

            month_name = str(month or "").strip()
            if not month_name:
                raise ValueError("month is required")

            try:
                year_value = int(year)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"year must be an integer, got {year!r}") from exc
            if year_value < 2000 or year_value > 2100:
                raise ValueError(f"year is out of valid range (2000-2100): {year_value}")

            level = normalize_performance_level(performance_level)
            emp_id = str(employee_id).strip() if employee_id else None

            # 1. Enforce Scope
            if not user_can_access_team(user_scope, team_name):
                raise PermissionError(f"Access denied: Team '{team_name}' is outside your authorized scope")

            if not user_can_access_team_level(user_scope, team_name, level):
                raise PermissionError(f"Access denied: Level '{level}' for team '{team_name}' is outside your scope")

            # Regional validation: do not reject solely because team.region differs if historical records match user's region
            assigned_regions = {r.casefold() for r in (user_scope.get("accessible_regions") or []) if str(r).strip()}
            if assigned_regions and not user_scope.get("has_unrestricted_team_access"):
                candidate_records = self.dashboard_service.list_records(
                    team=team_name,
                    month=month_name,
                    year=year_value,
                    employee_id=emp_id,
                    performance_level=level,
                    scope=user_scope,
                )
                has_record_in_region = any(
                    str(getattr(r, "region", "") or "").casefold() in assigned_regions
                    for r in (candidate_records or [])
                )
                if not has_record_in_region:
                    team_row = (
                        self.db.query(Team).filter(Team.display_name == team_name).first()
                        or self.db.query(Team).filter(Team.name == team_name).first()
                    )
                    if team_row and team_row.region and str(team_row.region).strip().casefold() not in assigned_regions:
                        raise PermissionError(
                            f"Access denied: Team '{team_name}' (region: {team_row.region}) is outside your assigned region(s)"
                        )

            if emp_id:
                # Employee-specific scope check
                self.corrective_action_service.ensure_employee_scope(emp_id, user_scope)
                employee_row = self.db.query(Employee).filter(Employee.employee_id == emp_id).first()
                if not employee_row:
                    raise ValueError(f"Unknown employee ID: {emp_id}")

                emp_team = getattr(employee_row.team, "display_name", None) or getattr(employee_row.team, "name", None)
                if emp_team and str(emp_team).strip().casefold() != team_name.casefold():
                    # Check whether the employee had a valid historical record in the requested team
                    historical_check = self.dashboard_service.list_records(
                        team=team_name,
                        month=month_name,
                        year=year_value,
                        employee_id=emp_id,
                        performance_level=level,
                        scope=user_scope,
                    )
                    historical_check = list(historical_check or [])
                    # Filter historical check by user's actual branch and region
                    assigned_branches = {b.casefold() for b in (user_scope.get("accessible_branches") or user_scope.get("allowed_branches") or []) if str(b).strip()}
                    user_role = str(user_scope.get("role") or user_scope.get("db_role") or "")
                    is_branch_restricted = bool(
                        user_role == "Branch Director"
                        or user_scope.get("is_branch_restricted")
                        or (assigned_branches and not user_scope.get("has_unrestricted_team_access") and user_role not in ("Regional Manager", "General Manager", "Admin", "Super Admin"))
                    )
                    if is_branch_restricted:
                        historical_check = [
                            r for r in historical_check
                            if str(getattr(r, "branch_key", "") or "").casefold() in assigned_branches
                        ]
                    if assigned_regions and not user_scope.get("has_unrestricted_team_access"):
                        historical_check = [
                            r for r in historical_check
                            if str(getattr(r, "region", "") or "").casefold() in assigned_regions
                        ]
                    if not historical_check:
                        raise PermissionError(
                            f"Employee {emp_id} belongs to '{emp_team}', "
                            f"and has no historical record in requested team '{team_name}' within your authorized branch/region for {month_name} {year_value}"
                        )

            # 2. Query Authoritative Records Under ReadOnlySessionGuard
            records = self.dashboard_service.list_records(
                team=team_name,
                month=month_name,
                year=year_value,
                employee_id=emp_id,
                performance_level=level,
                scope=user_scope,
            )
            records = list(records or [])

            # 3. Post-Filter Regional & Branch Scope Checks
            records = filter_records_by_scope(records, user_scope)

            assigned_regions = {r.casefold() for r in (user_scope.get("accessible_regions") or []) if str(r).strip()}
            if assigned_regions and not user_scope.get("has_unrestricted_team_access"):
                records = [r for r in records if str(getattr(r, "region", "") or "").casefold() in assigned_regions]

            user_role = str(user_scope.get("role") or user_scope.get("db_role") or "")
            assigned_branches = {b.casefold() for b in (user_scope.get("accessible_branches") or user_scope.get("allowed_branches") or []) if str(b).strip()}
            is_branch_restricted = bool(
                user_role == "Branch Director"
                or user_scope.get("is_branch_restricted")
                or (assigned_branches and not user_scope.get("has_unrestricted_team_access") and user_role not in ("Regional Manager", "General Manager", "Admin", "Super Admin"))
            )
            if is_branch_restricted:
                records = [r for r in records if str(getattr(r, "branch_key", "") or "").casefold() in assigned_branches]

            if not records:
                return {
                    "team": team_name,
                    "period": {"month": month_name, "year": year_value},
                    "performance_level": level,
                    "employee_id": emp_id,
                    "status": "no_data",
                    "records_count": 0,
                    "summary": "No performance records found for the requested period and scope",
                    "source_metadata": {
                        "source": "pms_dashboard_records",
                        "read_only": True,
                        "scope_verified": True,
                    },
                }

            # 4. Minimize and format record items
            minimized_items = []
            valid_scores: list[float] = []
            for r in records:
                evaluation = getattr(r, "evaluation", None)
                score = _float_or_none(getattr(evaluation, "score", None)) if evaluation else None
                grade = getattr(evaluation, "grade", None) if evaluation else None
                if score is not None:
                    valid_scores.append(score)

                item = {
                    "employee_id": getattr(r, "employee_id", None),
                    "employee_name": getattr(r, "employee_name", None),
                    "team": getattr(r, "team", team_name),
                    "region": getattr(r, "region", None),
                    "branch_key": getattr(r, "branch_key", None),
                    "score": score,
                    "grade": grade,
                    "status": getattr(r, "status", None),
                }
                minimized_items.append(item)

            avg_score = round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else None

            return {
                "team": team_name,
                "period": {"month": month_name, "year": year_value},
                "performance_level": level,
                "employee_id": emp_id,
                "status": "data_available",
                "records_count": len(minimized_items),
                "average_score": avg_score,
                "records": minimized_items,
                "source_metadata": {
                    "source": "pms_dashboard_records",
                    "read_only": True,
                    "scope_verified": True,
                },
            }

    # -----------------------------------------------------------------------
    # Operation 3: Get KPI Details
    # -----------------------------------------------------------------------

    def get_kpi_details(
        self,
        user_scope: dict[str, Any],
        *,
        team: str,
        month: str,
        year: int,
        kpi_key: str | None = None,
        employee_id: str | None = None,
        performance_level: str = "Employee",
        enforce_pilot: bool = True,
    ) -> dict[str, Any]:
        """Retrieve approved KPI values, targets, direction, and unit.
        
        Guarantees:
        - Preserves real 0.0 vs missing (None).
        - Preserves target direction and direction resolution source.
        - Reports direction and historical scoring basis uncertainty when defaulted/unpinned.
        - Never guesses or extrapolates missing KPIs.
        """
        with ReadOnlySessionGuard(self.db, allow_preexisting_writes=True):
            if enforce_pilot:
                self.verify_pilot_authorization(user_scope)

            team_name = str(team or "").strip()
            if not team_name:
                raise ValueError("team is required")

            month_name = str(month or "").strip()
            if not month_name:
                raise ValueError("month is required")

            try:
                year_value = int(year)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"year must be an integer, got {year!r}") from exc

            level = normalize_performance_level(performance_level)
            filter_kpi = str(kpi_key).strip() if kpi_key else None
            emp_id = str(employee_id).strip() if employee_id else None

            # Scope Check
            if not user_can_access_team(user_scope, team_name):
                raise PermissionError(f"Access denied: Team '{team_name}' is outside your authorized scope")

            if not user_can_access_team_level(user_scope, team_name, level):
                raise PermissionError(f"Access denied: Level '{level}' for team '{team_name}' is outside your scope")

            # Regional validation: do not reject solely because team.region differs if historical records match user's region
            assigned_regions = {r.casefold() for r in (user_scope.get("accessible_regions") or []) if str(r).strip()}
            if assigned_regions and not user_scope.get("has_unrestricted_team_access"):
                candidate_records = self.dashboard_service.list_records(
                    team=team_name,
                    month=month_name,
                    year=year_value,
                    employee_id=emp_id,
                    performance_level=level,
                    scope=user_scope,
                )
                has_record_in_region = any(
                    str(getattr(r, "region", "") or "").casefold() in assigned_regions
                    for r in (candidate_records or [])
                )
                if not has_record_in_region:
                    team_row = (
                        self.db.query(Team).filter(Team.display_name == team_name).first()
                        or self.db.query(Team).filter(Team.name == team_name).first()
                    )
                    if team_row and team_row.region and str(team_row.region).strip().casefold() not in assigned_regions:
                        raise PermissionError(
                            f"Access denied: Team '{team_name}' (region: {team_row.region}) is outside your assigned region(s)"
                        )

            if emp_id:
                self.corrective_action_service.ensure_employee_scope(emp_id, user_scope)
                employee_row = self.db.query(Employee).filter(Employee.employee_id == emp_id).first()
                if not employee_row:
                    raise ValueError(f"Unknown employee ID: {emp_id}")

                emp_team = getattr(employee_row.team, "display_name", None) or getattr(employee_row.team, "name", None)
                if emp_team and str(emp_team).strip().casefold() != team_name.casefold():
                    historical_check = self.dashboard_service.list_records(
                        team=team_name,
                        month=month_name,
                        year=year_value,
                        employee_id=emp_id,
                        performance_level=level,
                        scope=user_scope,
                    )
                    if not historical_check:
                        raise PermissionError(
                            f"Employee {emp_id} belongs to '{emp_team}', "
                            f"and has no historical record in requested team '{team_name}' for {month_name} {year_value}"
                        )

            records = self.dashboard_service.list_records(
                team=team_name,
                month=month_name,
                year=year_value,
                employee_id=emp_id,
                performance_level=level,
                scope=user_scope,
            )
            records = list(records or [])

            # Filter records by scope
            records = filter_records_by_scope(records, user_scope)

            assigned_regions = {r.casefold() for r in (user_scope.get("accessible_regions") or []) if str(r).strip()}
            if assigned_regions and not user_scope.get("has_unrestricted_team_access"):
                records = [r for r in records if str(getattr(r, "region", "") or "").casefold() in assigned_regions]

            user_role = str(user_scope.get("role") or user_scope.get("db_role") or "")
            assigned_branches = {b.casefold() for b in (user_scope.get("accessible_branches") or user_scope.get("allowed_branches") or []) if str(b).strip()}
            is_branch_restricted = bool(
                user_role == "Branch Director"
                or user_scope.get("is_branch_restricted")
                or (assigned_branches and not user_scope.get("has_unrestricted_team_access") and user_role not in ("Regional Manager", "General Manager", "Admin", "Super Admin"))
            )
            if is_branch_restricted:
                records = [r for r in records if str(getattr(r, "branch_key", "") or "").casefold() in assigned_branches]

            # Resolve scoring basis from historical records
            raw_records = (
                self.db.query(PerformanceRecord)
                .filter(
                    PerformanceRecord.month == month_name,
                    PerformanceRecord.year == year_value,
                )
                .all()
            )
            record_ids = {str(getattr(r, "id", "")) for r in records}
            scoring_bases: set[str] = set()
            for raw in raw_records:
                if str(raw.id) not in record_ids:
                    continue
                payload = raw.record_payload if isinstance(raw.record_payload, dict) else {}
                basis = payload.get("evaluation_basis")
                if isinstance(basis, dict) and (basis.get("pinned") is True or basis.get("confirmed") is True):
                    v = basis.get("version_number")
                    pol = basis.get("policy")
                    lbl = f"pinned team-configuration version {v}" if v is not None else "pinned team-configuration"
                    if pol:
                        lbl = f"{lbl} ({pol})"
                    scoring_bases.add(lbl)
            scoring_basis = "; ".join(sorted(scoring_bases)) if scoring_bases else None
            scoring_basis_confirmed = bool(scoring_basis)
            scoring_basis_uncertainty = (
                None if scoring_basis_confirmed else "Historical scoring basis is unpinned or unrecorded for this period"
            )

            if not records:
                return {
                    "team": team_name,
                    "period": {"month": month_name, "year": year_value},
                    "performance_level": level,
                    "kpi_key": filter_kpi,
                    "status": "no_data",
                    "kpi_items": [],
                    "scoring_basis": scoring_basis,
                    "scoring_basis_confirmed": scoring_basis_confirmed,
                    "scoring_basis_uncertainty": scoring_basis_uncertainty,
                    "source_metadata": {
                        "source": "pms_dashboard_records",
                        "read_only": True,
                        "scope_verified": True,
                    },
                }

            kpi_items = []
            for r in records:
                raw_kpis = getattr(r, "kpi_values", []) or []
                for item in raw_kpis:
                    curr_key = item.get("kpi_key") if isinstance(item, dict) else getattr(item, "kpi_key", None)
                    if not curr_key:
                        continue
                    curr_key_str = str(curr_key).strip()
                    if filter_kpi and curr_key_str.casefold() != filter_kpi.casefold():
                        continue

                    actual = _float_or_none(item.get("actual_value") if isinstance(item, dict) else getattr(item, "actual_value", None))
                    target = _float_or_none(item.get("target_value") if isinstance(item, dict) else getattr(item, "target_value", None))
                    ratio = _float_or_none(item.get("achievement_ratio") if isinstance(item, dict) else getattr(item, "achievement_ratio", None))
                    weight = _float_or_none(item.get("weight_applied") if isinstance(item, dict) else getattr(item, "weight_applied", None))
                    contribution = _float_or_none(item.get("contribution") if isinstance(item, dict) else getattr(item, "contribution", None))
                    unit = item.get("unit") if isinstance(item, dict) else getattr(item, "unit", "%")
                    label = item.get("label") if isinstance(item, dict) else getattr(item, "label", curr_key_str)

                    # Direction resolution and source tracking
                    resolved_dir, dir_source = resolve_kpi_direction(team_name, item)
                    dir_confirmed = (dir_source != "default")
                    dir_uncertainty = (
                        None if dir_confirmed else "KPI direction could not be confirmed from configuration or persisted metadata; defaulted to higher_better"
                    )

                    kpi_items.append({
                        "employee_id": getattr(r, "employee_id", None),
                        "kpi_key": curr_key_str,
                        "label": label,
                        "actual": actual,
                        "target": target,
                        "achievement_ratio": ratio,
                        "achievement_percent": round(ratio * 100.0, 2) if ratio is not None else None,
                        "direction": resolved_dir,
                        "direction_source": dir_source,
                        "direction_confirmed": dir_confirmed,
                        "direction_uncertainty": dir_uncertainty,
                        "unit": unit,
                        "weight_applied": weight,
                        "contribution": contribution,
                    })

            return {
                "team": team_name,
                "period": {"month": month_name, "year": year_value},
                "performance_level": level,
                "kpi_key": filter_kpi,
                "status": "data_available" if kpi_items else "kpi_not_found",
                "kpi_count": len(kpi_items),
                "kpi_items": kpi_items,
                "scoring_basis": scoring_basis,
                "scoring_basis_confirmed": scoring_basis_confirmed,
                "scoring_basis_uncertainty": scoring_basis_uncertainty,
                "source_metadata": {
                    "source": "pms_dashboard_records",
                    "read_only": True,
                    "scope_verified": True,
                },
            }

    # -----------------------------------------------------------------------
    # Operation 4: Get Corrective Action Context
    # -----------------------------------------------------------------------

    def get_corrective_action_context(
        self,
        user_scope: dict[str, Any],
        *,
        team: str,
        month: str,
        year: int,
        employee_id: str | None = None,
        performance_level: str = "Employee",
        linked_kpi_key: str | None = None,
        enforce_pilot: bool = True,
    ) -> dict[str, Any]:
        """Retrieve authorized corrective action context bundle without saving anything.
        
        Guarantees:
        - Full parity with CorrectiveActionEvidenceService.
        - Prior actions sanitized (no raw notes, no personal phone/email, no free-text causes).
        - Read-only execution under ReadOnlySessionGuard with caller write preservation.
        """
        with ReadOnlySessionGuard(self.db, allow_preexisting_writes=True):
            if enforce_pilot:
                self.verify_pilot_authorization(user_scope)

            team_name = str(team or "").strip()
            month_name = str(month or "").strip()
            try:
                year_value = int(year)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"year must be an integer, got {year!r}") from exc

            bundle = self.evidence_service.build(
                user_scope=user_scope,
                employee_id=employee_id,
                team=team_name,
                month=month_name,
                year=year_value,
                performance_level=performance_level,
                linked_kpi_key=linked_kpi_key,
            )

            # Attach explicit read-only AI evidence metadata
            bundle["source_metadata"] = {
                "source": "pms_corrective_action_evidence",
                "read_only": True,
                "scope_verified": True,
                "writes_forbidden": True,
            }
            return bundle

    # -----------------------------------------------------------------------
    # Unified Tool Dispatcher
    # -----------------------------------------------------------------------

    def execute_tool(
        self,
        operation: str,
        user_scope: dict[str, Any],
        params: dict[str, Any] | None = None,
        *,
        enforce_pilot: bool = True,
    ) -> dict[str, Any]:
        """Unified safe execution entrypoint for AI data tools."""
        with ReadOnlySessionGuard(self.db, allow_preexisting_writes=True):
            op_norm = str(operation or "").strip()
            if op_norm not in SUPPORTED_OPERATIONS:
                raise ValueError(
                    f"Unsupported AI data operation '{op_norm}'. "
                    f"Supported operations: {', '.join(sorted(SUPPORTED_OPERATIONS))}"
                )

            call_params = dict(params or {})

            # Parameter safety validation
            for k, v in call_params.items():
                _validate_param_safety(k, v)

            if op_norm == "list_authorized_scopes":
                return self.list_authorized_scopes(user_scope, enforce_pilot=enforce_pilot)

            if op_norm == "get_performance_summary":
                return self.get_performance_summary(
                    user_scope,
                    team=call_params.get("team"),
                    month=call_params.get("month"),
                    year=call_params.get("year"),
                    employee_id=call_params.get("employee_id"),
                    performance_level=call_params.get("performance_level", "Employee"),
                    enforce_pilot=enforce_pilot,
                )

            if op_norm == "get_kpi_details":
                return self.get_kpi_details(
                    user_scope,
                    team=call_params.get("team"),
                    month=call_params.get("month"),
                    year=call_params.get("year"),
                    kpi_key=call_params.get("kpi_key"),
                    employee_id=call_params.get("employee_id"),
                    performance_level=call_params.get("performance_level", "Employee"),
                    enforce_pilot=enforce_pilot,
                )

            if op_norm == "get_corrective_action_context":
                return self.get_corrective_action_context(
                    user_scope,
                    team=call_params.get("team"),
                    month=call_params.get("month"),
                    year=call_params.get("year"),
                    employee_id=call_params.get("employee_id"),
                    performance_level=call_params.get("performance_level", "Employee"),
                    linked_kpi_key=call_params.get("linked_kpi_key"),
                    enforce_pilot=enforce_pilot,
                )

            raise ValueError(f"Unhandled operation: {op_norm}")
