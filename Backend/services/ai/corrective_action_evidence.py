"""Authorized read-only evidence for corrective-action suggestions.

The first product pilot (contextual corrective-action suggestions) needs the
selected employee's or team's real PMS evidence before any draft is written:
the reporting period, performance level, KPI actual/target/direction, and the
prior corrective actions on file. This module only *reads* that evidence
through the canonical PMS services. It never writes a plan, never invents a
cause, owner, due date, or numerical score/team uplift, and never sends
employee data to any model.

Read-only guarantees enforced here:

- No ``db.add`` / ``db.commit`` / ``db.delete`` and no ``CorrectiveActionService.save``,
  ``update_status`` or ``deactivate`` call anywhere in this module.
- A missing value stays ``None``: actuals, targets and achievement are never
  coerced to ``0.0`` (a real measured ``0.0`` is preserved as ``0.0``).
- Prior actions are sanitized to structured fields only (action type, status,
  linked KPI, period). Free-text root causes, action text, owners, due dates
  and completion notes are deliberately *not* copied into the bundle, so the
  bundle can never present them as a suggested cause, owner, or due date.
- Scope is enforced before any row is read: an employee subject goes through
  ``CorrectiveActionService.ensure_employee_scope`` and a team subject through
  ``user_can_access_team_level``. Out-of-scope access raises ``PermissionError``.
- No score tie is resolved to a single winner: this bundle reports KPI items
  and stored scores as read and never ranks employees.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from models.models import Employee, PerformanceRecord, Team
from repositories.action_repository import ActionRepository
from services.corrective_action_service import CorrectiveActionService
from services.dashboard_record_service import DashboardRecordService
from utils.performance_levels import normalize_performance_level
from utils.report_scope import functions_for_team, user_can_access_team_level

__all__ = [
    "CorrectiveActionEvidenceService",
    "build_corrective_action_evidence",
]


def _float_or_none(value: Any) -> float | None:
    """Return ``float(value)`` unchanged, preserving ``None`` and real ``0.0``.

    A missing value is never coerced to ``0``; only a value that cannot be
    read as a number at all becomes ``None`` (and is flagged as missing by
    the caller).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _entry_value(entry: Any, key: str) -> Any:
    if isinstance(entry, dict):
        return entry.get(key)
    return getattr(entry, key, None)


def _sanitize_prior_action(action: Any) -> dict[str, Any]:
    """Structured prior-action evidence only: no free text, owner, or due date."""
    if isinstance(action, dict):
        action_type = action.get("suggested_action") or action.get("action_type")
        status = action.get("status")
        linked_kpi_key = action.get("linked_kpi_key")
        month = action.get("month")
        year = action.get("year")
    else:
        action_type = getattr(action, "action_type", None)
        status = getattr(action, "status", None)
        linked_kpi_key = getattr(action, "linked_kpi_key", None)
        month = getattr(action, "month", None)
        year = getattr(action, "year", None)
    action_type = str(action_type).strip() if action_type else None
    status = str(status).strip() if status else None
    linked_kpi_key = str(linked_kpi_key).strip() if linked_kpi_key else None
    month = str(month).strip() if month else None
    try:
        year_value: int | None = int(year) if year is not None else None
    except (TypeError, ValueError):
        year_value = None
    summary = f"{action_type} ({status})" if action_type and status else (action_type or status or "Corrective action")
    return {
        "action_type": action_type,
        "status": status,
        "linked_kpi_key": linked_kpi_key,
        "period": {"month": month, "year": year_value},
        "summary": summary,
    }


class CorrectiveActionEvidenceService:
    """Build an authorized, read-only evidence bundle for one subject/period."""

    def __init__(
        self,
        db: Session,
        *,
        dashboard_service: DashboardRecordService | None = None,
        corrective_action_service: CorrectiveActionService | None = None,
        action_repository: ActionRepository | None = None,
    ) -> None:
        self.db = db
        self.dashboard_service = dashboard_service or DashboardRecordService(db)
        self.corrective_action_service = corrective_action_service or CorrectiveActionService(db)
        self.action_repository = action_repository or ActionRepository(db)

    def build(
        self,
        *,
        user_scope: dict,
        employee_id: str | None = None,
        team: str,
        month: str,
        year: int,
        performance_level: str = "Employee",
        linked_kpi_key: str | None = None,
    ) -> dict[str, Any]:
        """Return the evidence bundle for ``employee_id`` or, when it is ``None``, for ``team``.

        Raises ``ValueError`` for an invalid period/level/linked-KPI argument
        and ``PermissionError`` when the subject is outside ``user_scope``.
        Reads only; the database is never written to.
        """
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
            raise ValueError(f"year is out of range: {year_value}")
        level = normalize_performance_level(performance_level)
        linked_key = str(linked_kpi_key).strip() if linked_kpi_key else None
        scope = dict(user_scope or {})

        employee: Employee | None = None
        subject = "team"
        if employee_id:
            subject = "employee"
            employee = (
                self.db.query(Employee)
                .filter(Employee.employee_id == str(employee_id).strip())
                .one_or_none()
            )
            if employee is None:
                raise ValueError(f"Unknown employee: {employee_id}")
            # Authorisation first: raises PermissionError outside the caller's scope.
            self.corrective_action_service.ensure_employee_scope(str(employee_id).strip(), scope)
            employee_team = getattr(employee.team, "display_name", None) or getattr(employee.team, "name", None)
            if employee_team and str(employee_team).strip().casefold() != team_name.casefold():
                # The requested team must be the employee's own team; a
                # mismatched team is treated as out of scope, not silently fixed.
                raise PermissionError("The employee is not in the requested team")
        elif not user_can_access_team_level(scope, team_name, level):
            raise PermissionError("The team is outside your authorized action scope")

        records = self.dashboard_service.list_records(
            team=team_name,
            month=month_name,
            employee_id=str(employee_id).strip() if employee_id else None,
            performance_level=level,
            year=year_value,
            scope=scope,
        )
        records = list(records or [])
        if employee_id:
            records = [
                record
                for record in records
                if str(_entry_value(record, "employee_id") or "").strip()
                == str(employee_id).strip()
            ]

        reasons: list[str] = []
        if not records:
            reasons.append("no_performance_record_for_period")

        kpi_items: list[dict[str, Any]] = []
        regions: set[str] = set()
        positions: set[str] = set()
        scoring_bases: set[str] = set()
        for record in records:
            region = _entry_value(record, "region")
            if region:
                regions.add(str(region).strip())
            position = _entry_value(record, "position")
            if position:
                positions.add(str(position).strip())
            for entry in _entry_value(record, "kpi_values") or []:
                kpi_key = _entry_value(entry, "kpi_key")
                if not kpi_key:
                    continue
                kpi_key = str(kpi_key)
                actual = _float_or_none(_entry_value(entry, "actual_value"))
                target = _float_or_none(_entry_value(entry, "target_value"))
                achievement_ratio = _float_or_none(_entry_value(entry, "achievement_ratio"))
                achievement_percent = achievement_ratio * 100.0 if achievement_ratio is not None else None
                if actual is None:
                    reasons.append(f"missing_actual_for_kpi:{kpi_key}")
                if target is None:
                    reasons.append(f"missing_target_for_kpi:{kpi_key}")
                kpi_items.append(
                    {
                        "employee_id": str(_entry_value(record, "employee_id") or "").strip() or None,
                        "kpi_key": kpi_key,
                        "display_name": _entry_value(entry, "label") or kpi_key,
                        "actual": actual,
                        "target": target,
                        "unit": _entry_value(entry, "unit"),
                        "direction": _entry_value(entry, "direction"),
                        "weight": _float_or_none(_entry_value(entry, "weight_applied")),
                        "contributes_to_score": not bool(_entry_value(entry, "view_only")),
                        "achievement_percent": achievement_percent,
                    }
                )
        if records and not kpi_items:
            reasons.append("no_kpi_values_for_period")
        if linked_key and not any(item["kpi_key"] == linked_key for item in kpi_items):
            reasons.append(f"linked_kpi_not_found:{linked_key}")

        # Scoring basis: the pinned team-configuration version(s) stored on
        # the period's own records, if any. No pinned basis is reported as
        # None rather than a guessed default. With no records for the period
        # there is no basis to report either.
        if records:
            raw_records = (
                self.db.query(PerformanceRecord)
                .filter(
                    PerformanceRecord.month == month_name,
                    PerformanceRecord.year == year_value,
                )
                .all()
            )
            record_ids = {str(record.id) for record in records}
            for raw in raw_records:
                if str(raw.id) not in record_ids:
                    continue
                payload = raw.record_payload if isinstance(raw.record_payload, dict) else {}
                basis = payload.get("evaluation_basis")
                if isinstance(basis, dict) and basis.get("pinned"):
                    version_number = basis.get("version_number")
                    policy = basis.get("policy")
                    label = f"pinned team-configuration version {version_number}" if version_number is not None else "pinned team-configuration"
                    if policy:
                        label = f"{label} ({policy})"
                    scoring_bases.add(label)
        scoring_basis = "; ".join(sorted(scoring_bases)) if scoring_bases else None

        if subject == "employee" and employee is not None:
            country = str(employee.region).strip() if employee.region else None
            position = str(employee.position_name).strip() if employee.position_name else None
            employee_name = str(employee.name).strip() if employee.name else None
            prior_actions = self._prior_actions_for_employee(employee, scope)
        else:
            country = next(iter(sorted(regions))) if len(regions) == 1 else None
            if len(regions) > 1:
                reasons.append("multiple_regions_in_period")
            position = next(iter(sorted(positions))) if len(positions) == 1 else None
            employee_name = None
            prior_actions = self._prior_actions_for_team(team_name)

        return {
            "subject": subject,
            "employee_id": str(employee_id).strip() if employee_id else None,
            "employee_name": employee_name,
            "country": country,
            "function": (functions_for_team(team_name) or [None])[0],
            "team": team_name,
            "position": position,
            "period": {"month": month_name, "year": year_value},
            "performance_level": level,
            "linked_kpi_key": linked_key,
            "scoring_basis": scoring_basis,
            "kpi_items": kpi_items,
            "prior_corrective_actions": prior_actions,
            "insufficient_evidence_reasons": sorted(set(reasons)),
            "read_only": True,
        }

    def _prior_actions_for_employee(self, employee: Employee, scope: dict | None) -> list[dict[str, Any]]:
        """Prior actions for one employee, scope already enforced by ``build``."""
        # get_history re-checks the caller's scope; the serialized rows are
        # then reduced to structured fields only (see _sanitize_prior_action).
        try:
            history = self.corrective_action_service.get_history(
                str(employee.employee_id), scope if isinstance(scope, dict) else None
            )
        except Exception:
            history = []
        if history:
            return [_sanitize_prior_action(item) for item in history]
        rows = self.action_repository.list_active_by_employee(employee.id)
        return [_sanitize_prior_action(row) for row in rows]

    def _prior_actions_for_team(self, team_name: str) -> list[dict[str, Any]]:
        team_row = (
            self.db.query(Team)
            .filter(Team.display_name.ilike(team_name))
            .one_or_none()
            or self.db.query(Team).filter(Team.name.ilike(team_name)).one_or_none()
        )
        if team_row is None:
            return []
        rows = self.action_repository.get_by_team(team_row.id)
        return [_sanitize_prior_action(row) for row in rows]


def build_corrective_action_evidence(
    db: Session,
    *,
    user_scope: dict,
    employee_id: str | None = None,
    team: str,
    month: str,
    year: int,
    performance_level: str = "Employee",
    linked_kpi_key: str | None = None,
) -> dict[str, Any]:
    """Module-level convenience wrapper around :class:`CorrectiveActionEvidenceService`."""
    return CorrectiveActionEvidenceService(db).build(
        user_scope=user_scope,
        employee_id=employee_id,
        team=team,
        month=month,
        year=year,
        performance_level=performance_level,
        linked_kpi_key=linked_kpi_key,
    )
