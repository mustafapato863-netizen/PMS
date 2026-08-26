from __future__ import annotations

import re
import textwrap
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import timezone
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from pydantic import ValidationError

from config.loader import ConfigurationError, load_team_config, resolve_team_config
from exports.report_exporter import ReportExporter
from exports.pptx_builder import build_pptx_from_slides
from exports.marketing_pptx_builder import build_marketing_pptx
from exports.marketing_legendary_pptx_builder import build_marketing_legendary_pptx
from exports.insights_pptx_builder import build_insights_pptx
from exports.offshore_status_pptx_builder import build_offshore_status_pptx
from exports.executive_group_summary_pptx_builder import build_executive_group_summary_pptx
from exports.uae_executive_summary_pptx_builder import build_uae_executive_summary_pptx
from services.narrative_engine import generate_narrative
from models.models import GeneratedReport, SavedReportTemplate
from models.report_schemas import MONTHS, ReportConfiguration
from repositories.action_repository import ActionRepository
from repositories.report_repository import ReportRepository
from services.dashboard_record_service import DashboardRecordService
from services.management_bsc_service import ManagementBSCService, ManagementBSCSchemaError
from services.insights_report_service import build_insights_snapshot
from services.permission_seed import PERMISSION_MATRIX
from utils.performance_levels import PERFORMANCE_LEVELS
from utils.report_scope import (
    filter_records_by_scope,
    filter_records_by_team_levels,
    user_can_access_team,
    user_can_access_team_level,
)
from utils.team_identity import logical_team_name
from models.schemas import PerformanceRecord as SchemaPerformanceRecord


def _safe_uuid(value: Any) -> uuid.UUID | None:
    if not value:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _clean(value: Any, fallback: str = "—") -> str:
    if value is None:
        return fallback
    text = " ".join(str(value).replace("\n", " ").split()).strip()
    return text or fallback


def _native(value: Any, unit: Any = "") -> str:
    number = _number(value)
    if number is None:
        return "—"
    normalized = _clean(unit, "").casefold()
    if normalized in {"%", "percent", "percentage"}:
        if abs(number) <= 1:
            number *= 100
        return f"{number:.1f}%"
    if normalized in {"minutes", "minute", "min"}:
        return f"{number:,.0f} min" if number.is_integer() else f"{number:,.1f} min"
    if normalized in {"seconds", "second", "sec"}:
        return f"{number:,.0f} sec" if number.is_integer() else f"{number:,.1f} sec"
    return f"{number:,.0f} {_clean(unit, '').strip()}".strip()


def _pct(value: Any) -> str:
    number = _number(value)
    return "—" if number is None else f"{number:.1f}%"


def _fit(value: Any, limit: int) -> str:
    text = _clean(value, "")
    return textwrap.shorten(text, width=max(8, limit), placeholder="...") if text else "—"


class ReportValidationError(ValueError):
    pass


class ReportNotFoundError(LookupError):
    pass


class ReportAccessError(PermissionError):
    pass


REPORT_TEMPLATES = [
    {
        "type": "monthly_uae",
        "category": "executive",
        "name": "UAE Detailed Departments Performance Review",
        "description": "Detailed operational UAE department review with evidence, employee scorecards, and corrective-action tracking.",
        "formats": ["pdf", "pptx", "excel"],
        "sections": ["summary", "grade_distribution", "team_breakdown", "details"],
    },
    {
        "type": "monthly_egypt",
        "category": "executive",
        "name": "Offshore Departments Performance Review - Offshore EGY",
        "description": "Dynamic executive departmental performance review using the approved Offshore Departments reference.",
        "formats": ["pdf", "pptx", "excel"],
        "sections": ["summary", "grade_distribution", "team_breakdown", "details"],
    },
    {
        "type": "team_marketing",
        "category": "team",
        "name": "Marketing Summary - PowerPoint",
        "description": "Filtered-month executive story: overall performance, largest gap, KPI driver, affected people, and actions.",
        "formats": ["pptx"],
        "sections": ["summary", "details"],
    },
    {
        "type": "executive_group_summary",
        "category": "executive",
        "name": "Executive Group Performance Summary",
        "description": "CEO-level view of authorized regions, teams, KPI drivers, evidence, commitments, and next-review decisions.",
        "formats": ["pptx"],
        "sections": ["summary", "details"],
    },
    {
        "type": "uae_executive_summary",
        "category": "executive",
        "name": "UAE Executive Performance Summary",
        "description": "Concise CEO, Group Management, and Regional Leadership summary for the live UAE PMS scope.",
        "formats": ["pptx"],
        "sections": ["summary", "details"],
    },
]


@dataclass
class CollectedReport:
    rows: list[dict[str, Any]]
    records: list[Any]
    summary: dict[str, Any]
    warnings: list[str]


class ReportService:
    def __init__(self, db: Session, record_service: DashboardRecordService | None = None):
        self.db = db
        self.record_service = record_service or DashboardRecordService(db)
        self.reports = ReportRepository(db)
        self.actions = ActionRepository(db)

    @staticmethod
    def templates() -> list[dict[str, Any]]:
        return REPORT_TEMPLATES

    @staticmethod
    def _record_value(record, key: str, default=None):
        return record.get(key, default) if isinstance(record, dict) else getattr(record, key, default)

    @staticmethod
    def _record_period(record) -> tuple[int, int] | None:
        year = ReportService._record_value(record, "year")
        month = MONTHS.get(str(ReportService._record_value(record, "month", "")))
        return (int(year), month) if year and month else None

    @staticmethod
    def _record_team_name(record) -> str:
        team = ReportService._record_value(record, "team", "")
        return logical_team_name(team) if hasattr(team, "display_name") else str(team or "")

    @staticmethod
    def _period_bounds(configuration: ReportConfiguration) -> tuple[tuple[int, int], tuple[int, int]]:
        start = (configuration.start_year, MONTHS[configuration.start_month])
        end = (
            configuration.end_year or configuration.start_year,
            MONTHS[configuration.end_month or configuration.start_month],
        )
        return start, end

    @staticmethod
    def _comparison_period(configuration: ReportConfiguration) -> tuple[int, int] | None:
        if configuration.comparison_month is None or configuration.comparison_year is None:
            return None
        return configuration.comparison_year, MONTHS[configuration.comparison_month]

    @classmethod
    def _in_period(cls, year: int, month: str, configuration: ReportConfiguration) -> bool:
        month_number = MONTHS.get(month)
        if not month_number:
            return False
        start, end = cls._period_bounds(configuration)
        return start <= (int(year), month_number) <= end

    @staticmethod
    def _period_label(configuration: ReportConfiguration) -> str:
        start = f"{configuration.start_month} {configuration.start_year}"
        if not configuration.end_month:
            return start
        end = f"{configuration.end_month} {configuration.end_year}"
        return start if end == start else f"{start} – {end}"

    @staticmethod
    def _scope_summary(configuration: ReportConfiguration) -> str:
        parts = [
            f"Region {configuration.region}" if configuration.region else None,
            f"Team {configuration.team}" if configuration.team else None,
            f"Level {configuration.performance_level}" if configuration.performance_level else None,
            f"Position {configuration.position}" if configuration.position else None,
            f"Employee {configuration.employee_id}" if configuration.employee_id else None,
            f"Grade {configuration.grade}" if configuration.grade else None,
            f"Status {configuration.status}" if configuration.status else None,
            f"KPI {configuration.kpi}" if configuration.kpi else None,
        ]
        return " | ".join(part for part in parts if part) or "All authorized teams"

    @staticmethod
    def _canonical_report_region(configuration: ReportConfiguration) -> str | None:
        """Normalize UI/report aliases without changing the public filter contract."""

        return ReportService._canonical_region_value(configuration.region)

    @staticmethod
    def _canonical_region_value(value: Any) -> str | None:
        """Compare the region aliases used by the UI, employees, teams, and uploads."""

        text = str(value or "").strip()
        if not text:
            return None
        normalized = " ".join(text.casefold().replace("_", " ").replace("-", " ").split())
        if normalized in {"egypt", "egy", "offshore egy", "offshore egypt"}:
            return "EGY"
        if normalized in {"uae", "united arab emirates"}:
            return "UAE"
        return text

    @classmethod
    def _regions_match(cls, left: Any, right: Any) -> bool:
        left_value = cls._canonical_region_value(left)
        right_value = cls._canonical_region_value(right)
        return bool(left_value and right_value and left_value.casefold() == right_value.casefold())

    @staticmethod
    def _record_grade(record: Any) -> str:
        grade = ReportService._record_value(record, "grade")
        if grade:
            return str(grade)
        evaluation = ReportService._record_value(record, "evaluation")
        if isinstance(evaluation, dict):
            return str(evaluation.get("grade") or "")
        return str(getattr(evaluation, "grade", "") or "")

    @staticmethod
    def _record_kpi_matches(record: Any, kpi: str) -> bool:
        requested = str(kpi or "").casefold()
        if not requested:
            return True
        return any(
            str(value.get("kpi_key") or value.get("key") or value.get("label") or "").casefold() == requested
            for value in (ReportService._record_value(record, "kpi_values", []) or [])
            if isinstance(value, dict)
        )

    @staticmethod
    def _filter_level_assignments(records: list[Any], scope: dict) -> list[Any]:
        return filter_records_by_team_levels(records, scope)

    @staticmethod
    def _effective_scope(scope: dict) -> dict:
        """Normalize aggregate report reads without widening manager access."""

        role = str(scope.get("role") or "Viewer")
        if role not in {"Executive", "Viewer"}:
            return scope
        return {
            **scope,
            "role": "Admin",
            "is_general_manager": True,
            "is_self_only": False,
            "accessible_teams": list(scope.get("active_team_names") or scope.get("accessible_teams") or []),
            "accessible_team_levels": [],
            "report_role": role,
        }

    @staticmethod
    def _is_aggregate_scope(scope: dict) -> bool:
        return str(scope.get("report_role") or scope.get("role") or "") in {"Executive", "Viewer"}

    def options(self, scope: dict) -> dict[str, Any]:
        effective_scope = self._effective_scope(scope)
        option_loader = getattr(self.record_service, "list_option_rows", None)
        records = option_loader() if callable(option_loader) else self.record_service.list_records()
        # Employee dashboard options intentionally come from the bounded
        # performance projection. Management BSC dimensions live in their
        # separate snapshot tables, so merge the lightweight projection here
        # instead of making the report filter silently employee-only.
        try:
            management_records = ManagementBSCService(self.db).list_option_rows()
        except (SQLAlchemyError, ManagementBSCSchemaError):
            management_records = []
        records = [*records, *management_records]
        records = filter_records_by_scope(records, effective_scope)
        records = self._filter_level_assignments(records, effective_scope)
        periods = sorted(
            {period for record in records if (period := self._record_period(record))},
            reverse=True,
        )
        employees: dict[str, dict[str, str]] = {}
        kpis: set[str] = set()
        kpi_loader = getattr(self.record_service, "list_kpi_options", None)
        if callable(kpi_loader):
            kpis.update(str(kpi) for kpi in (kpi_loader(effective_scope) or []) if kpi)
        for record in records:
            employee_id = str(self._record_value(record, "employee_id", ""))
            employees[employee_id] = {
                "id": employee_id,
                "name": str(self._record_value(record, "employee_name", "")),
                "team": str(self._record_value(record, "team", "")),
                "position": str(self._record_value(record, "position", "") or ""),
                "performance_level": str(self._record_value(record, "performance_level", "")),
                "region": str(self._record_value(record, "region", "") or ""),
            }
            for value in self._record_value(record, "kpi_values", []) or []:
                kpi_key = self._record_value(value, "kpi_key")
                if kpi_key:
                    kpis.add(str(kpi_key))
            option_kpi = self._record_value(record, "kpi_key")
            if option_kpi:
                kpis.add(str(option_kpi))
        role = str(scope.get("role") or "Viewer")
        performance_levels = {
            str(self._record_value(record, "performance_level"))
            for record in records
            if self._record_value(record, "performance_level")
        }
        # Aggregate-capable roles need an explicit way to request the full
        # team scope even when the current snapshot has rows for only one
        # level. Managers keep only levels present in their authorized rows.
        if role in {"Admin", "Executive", "Viewer"} or scope.get("is_general_manager"):
            performance_levels.update(PERFORMANCE_LEVELS)
        can_view_people = role in {"Admin", "Manager"}
        can_view_actions = role == "Admin" or "view_actions" in PERMISSION_MATRIX.get(role, [])
        can_export = "export_data" in PERMISSION_MATRIX.get(role, [])
        return {
            "periods": [
                {
                    "year": year,
                    "month": next(name for name, number in MONTHS.items() if number == month),
                    "key": f"{year}-{month:02d}",
                }
                for year, month in periods
            ],
            "teams": sorted({str(self._record_value(record, "team")) for record in records if self._record_value(record, "team")}),
            "regions": sorted({str(self._record_value(record, "region")) for record in records if self._record_value(record, "region")}),
            "performance_levels": [
                level for level in PERFORMANCE_LEVELS if level in performance_levels
            ] + sorted(performance_levels.difference(PERFORMANCE_LEVELS)),
            "positions": sorted({str(self._record_value(record, "position")) for record in records if self._record_value(record, "position")}),
            "employees": sorted(employees.values(), key=lambda item: (item["name"], item["id"])) if can_view_people else [],
            "grades": sorted({
                str(grade)
                for record in records
                if (grade := self._record_value(record, "grade") or getattr(self._record_value(record, "evaluation"), "grade", None))
            }),
            "statuses": sorted({str(self._record_value(record, "status")) for record in records if self._record_value(record, "status")}),
            "kpis": sorted(kpis),
            "can_export": can_export,
            "can_view_people": can_view_people,
            "can_view_actions": can_view_actions,
            "allowed_formats": ["pdf", "pptx", "excel"] if can_export else [],
            "role": role,
        }

    def _validate_scope(self, configuration: ReportConfiguration, scope: dict) -> None:
        original_role = str(scope.get("report_role") or scope.get("role") or "Viewer")
        effective_scope = self._effective_scope(scope)
        if configuration.employee_id and original_role not in {"Admin", "Manager"}:
            raise ReportAccessError("This role can only view aggregate reporting data")
        if configuration.report_type == "corrective_actions" and original_role != "Admin" and "view_actions" not in PERMISSION_MATRIX.get(original_role, []):
            raise ReportAccessError("This role cannot view corrective-action details")
        if configuration.team and not user_can_access_team(effective_scope, configuration.team):
            raise ReportAccessError("The selected team is outside the authorized reporting scope")
        if configuration.team and configuration.performance_level and not user_can_access_team_level(
            effective_scope,
            configuration.team,
            configuration.performance_level,
        ):
            raise ReportAccessError("The selected performance level is outside the authorized reporting scope")
        if configuration.report_type == "team" and not configuration.team:
            raise ReportValidationError("Team Performance Report requires a team")
        if configuration.report_type == "position" and not configuration.position:
            raise ReportValidationError("Position Performance Report requires a position")
        if configuration.report_type == "employee" and not configuration.employee_id:
            raise ReportValidationError("Employee Performance Report requires an employee")
        template = next(
            (item for item in REPORT_TEMPLATES if item["type"] == configuration.report_type),
            None,
        )
        if template is not None and configuration.output_format not in set(template.get("formats") or []):
            raise ReportValidationError(
                f"{template['name']} supports: {', '.join(template.get('formats') or [])}"
            )
        # Generic report types remain part of the public schema for legacy
        # clients even though the current UI advertises only the three direct
        # download templates above.
        allowed_sections = set(
            template["sections"]
            if template is not None
            else ["summary", "grade_distribution", "team_breakdown", "kpi_breakdown", "details"]
        )
        selected_sections = set(configuration.included_sections)
        if not selected_sections:
            raise ReportValidationError("At least one report section must be selected")
        unsupported = selected_sections - allowed_sections
        if unsupported:
            raise ReportValidationError(f"Unsupported report sections: {', '.join(sorted(unsupported))}")

    def _performance_records(self, configuration: ReportConfiguration, scope: dict) -> list[Any]:
        """Return scoped records before period slicing for trend-aware exports."""
        filters = {
            "team": configuration.team,
            "employee_id": configuration.employee_id,
            "grade": configuration.grade,
            "status": configuration.status,
            "performance_level": configuration.performance_level,
            "position": configuration.position,
            "region": self._canonical_report_region(configuration),
        }
        if configuration.kpi:
            filters["kpi"] = configuration.kpi
        records = self.record_service.list_records(
            **filters,
        )
        # ``DashboardRecordService`` is deliberately bounded to employee
        # ``PerformanceRecord`` rows. Management BSC snapshots are a separate
        # canonical source and must be added explicitly for Managerial,
        # Corporate, or an unqualified (All levels) report.
        try:
            management_records = ManagementBSCService(self.db).list_analysis_records()
        except (SQLAlchemyError, ManagementBSCSchemaError):
            management_records = []

        def matches_management(record: dict[str, Any]) -> bool:
            def value(key: str, default: Any = None) -> Any:
                return record.get(key, default)

            if configuration.team and self._record_team_name(record).casefold() != configuration.team.casefold():
                return False
            if configuration.employee_id and str(value("employee_id", "")) != configuration.employee_id:
                return False
            if configuration.performance_level and str(value("performance_level", "")).casefold() != configuration.performance_level.casefold():
                return False
            if configuration.position and str(value("position", "") or "").casefold() != configuration.position.casefold():
                return False
            canonical_region = self._canonical_report_region(configuration)
            if canonical_region and str(value("region", "") or "").casefold() != canonical_region.casefold():
                return False
            if configuration.grade:
                evaluation = value("evaluation", {})
                grade = evaluation.get("grade") if isinstance(evaluation, dict) else getattr(evaluation, "grade", None)
                if str(grade or "").casefold() != configuration.grade.casefold():
                    return False
            if configuration.status and str(value("status", "") or "").casefold() != configuration.status.casefold():
                return False
            if configuration.kpi:
                if not any(
                    str(kpi.get("kpi_key") or kpi.get("label") or "").casefold() == configuration.kpi.casefold()
                    for kpi in (value("kpi_values", []) or [])
                ):
                    return False
            return True

        validated_management_records = []
        for record in management_records:
            if not matches_management(record):
                continue
            try:
                validated_management_records.append(SchemaPerformanceRecord.model_validate(record))
            except ValidationError:
                # Management BSC keeps incomplete / not-yet-measured rows for
                # operational follow-up. They cannot participate in score,
                # trend, or KPI aggregation and must not make an executive
                # report fail when the user requests all levels.
                continue
        management_records = validated_management_records
        records = [*records, *management_records]
        effective_scope = self._effective_scope(scope)
        records = filter_records_by_scope(records, effective_scope)
        records = self._filter_level_assignments(records, effective_scope)
        return [record for record in records if self._record_period(record)]

    def _presentation_actions(
        self,
        configuration: ReportConfiguration,
        scope: dict,
        records: list[Any],
    ) -> list[Any]:
        """Return actions that belong to the same filtered scorecard scope.

        Corrective actions are stored separately from performance records, so a
        report filter cannot be considered integrated until the action rows use
        the same team/region/position/level/employee boundary.  Grade, status,
        and KPI filters are resolved against the performance row for the
        action's employee and period; an action without matching evidence is
        not silently attached to an unrelated filtered report.
        """

        if self._is_aggregate_scope(scope):
            return []

        records_by_employee_period: dict[tuple[str, tuple[int, int]], list[Any]] = {}
        for record in records:
            employee_id = str(self._record_value(record, "employee_id", "") or "")
            period = self._record_period(record)
            if employee_id and period:
                records_by_employee_period.setdefault((employee_id, period), []).append(record)

        filtered: list[Any] = []
        requested_region = self._canonical_report_region(configuration)
        for action in self.actions.list_active():
            if not self._in_period(action.year, action.month, configuration):
                continue

            team_name = logical_team_name(action.team) if action.team else ""
            if configuration.team and team_name.casefold() != configuration.team.casefold():
                continue

            employee = getattr(action, "employee", None)
            employee_identifier = str(getattr(employee, "employee_id", "") or "")
            if configuration.employee_id and employee_identifier != configuration.employee_id:
                continue

            employee_region = getattr(employee, "region", None) or getattr(action.team, "region", None)
            if requested_region and not self._regions_match(employee_region, requested_region):
                continue

            employee_position = getattr(employee, "position_name", None) or getattr(employee, "position", None)
            if configuration.position and str(employee_position or "").casefold() != configuration.position.casefold():
                continue
            if configuration.performance_level and str(getattr(employee, "performance_level", "") or "").casefold() != configuration.performance_level.casefold():
                continue

            if scope.get("role") in {"Agent", "Executive"} and employee_identifier != str(scope.get("employee_id") or ""):
                continue
            if scope.get("role") == "Manager" and not scope.get("is_general_manager") and not user_can_access_team(scope, team_name):
                continue

            # `status` in the Reports Center is the performance status.  Do
            # not compare it to Action.status (Open/In Progress/etc.); use the
            # employee performance row for the action's own month instead.
            action_period = self._record_period({"year": action.year, "month": action.month})
            evidence = records_by_employee_period.get((employee_identifier, action_period), []) if action_period else []
            if configuration.grade and not any(
                self._record_grade(record).casefold() == configuration.grade.casefold()
                for record in evidence
            ):
                continue
            if configuration.status and not any(
                str(self._record_value(record, "status", "") or "").casefold() == configuration.status.casefold()
                for record in evidence
            ):
                continue
            if configuration.kpi:
                linked_kpi = str(getattr(action, "linked_kpi_key", "") or "")
                if not linked_kpi or linked_kpi.casefold() != configuration.kpi.casefold():
                    continue
                if not evidence or not any(self._record_kpi_matches(record, configuration.kpi) for record in evidence):
                    continue

            filtered.append(action)
        return filtered

    def _executive_action_rows(
        self,
        configuration: ReportConfiguration,
        scope: dict,
        records: list[Any],
    ) -> list[dict[str, Any]]:
        """Return authorized action evidence for the aggregate executive deck.

        ``_presentation_actions`` intentionally returns no person-level rows
        for aggregate roles.  The CEO summary still needs commitment counts
        and ownership quality, so this method resolves actions against the
        already-scoped performance records and emits only group-safe fields.
        Employee names are never needed by the executive presentation.
        """

        records_by_employee_period: dict[tuple[str, tuple[int, int]], list[Any]] = {}
        records_by_period: dict[tuple[int, int], list[Any]] = {}
        for record in records:
            employee_id = str(self._record_value(record, "employee_id", "") or "")
            period = self._record_period(record)
            if not period:
                continue
            records_by_period.setdefault(period, []).append(record)
            if employee_id:
                records_by_employee_period.setdefault((employee_id, period), []).append(record)

        requested_region = self._canonical_report_region(configuration)
        result: list[dict[str, Any]] = []
        for action in self.actions.list_active():
            action_period = self._record_period({"year": action.year, "month": action.month})
            if not action_period or not self._in_period(action.year, action.month, configuration):
                continue

            team_name = logical_team_name(action.team) if action.team else ""
            if configuration.team and team_name.casefold() != configuration.team.casefold():
                continue

            employee = getattr(action, "employee", None)
            employee_identifier = str(getattr(employee, "employee_id", "") or "")
            if configuration.employee_id and employee_identifier != configuration.employee_id:
                continue

            evidence = (
                records_by_employee_period.get((employee_identifier, action_period), [])
                if employee_identifier
                else [
                    record
                    for record in records_by_period.get(action_period, [])
                    if not configuration.team
                    or self._record_team_name(record).casefold() == team_name.casefold()
                ]
            )
            # An employee action without a matching authorized scorecard must
            # not leak into an executive aggregate. Team/position actions can
            # be retained when they match an authorized team-period row.
            if not evidence:
                continue

            action_region = getattr(employee, "region", None) or getattr(action.team, "region", None)
            if not action_region and evidence:
                action_region = self._record_value(evidence[0], "region", None)
            if requested_region and not self._regions_match(action_region, requested_region):
                continue

            action_position = getattr(employee, "position_name", None) or getattr(employee, "position", None)
            if configuration.position and str(action_position or "").casefold() != configuration.position.casefold():
                continue
            if configuration.performance_level and str(getattr(employee, "performance_level", "") or "").casefold() != configuration.performance_level.casefold():
                continue
            if scope.get("role") == "Manager" and not scope.get("is_general_manager") and not user_can_access_team(scope, team_name):
                continue

            if configuration.grade and not any(
                self._record_grade(record).casefold() == configuration.grade.casefold()
                for record in evidence
            ):
                continue
            if configuration.status and not any(
                str(self._record_value(record, "status", "") or "").casefold() == configuration.status.casefold()
                for record in evidence
            ):
                continue
            linked_kpi = str(getattr(action, "linked_kpi_key", "") or "")
            if configuration.kpi:
                if linked_kpi.casefold() != configuration.kpi.casefold():
                    continue
                if not any(self._record_kpi_matches(record, configuration.kpi) for record in evidence):
                    continue

            owner = getattr(action, "owner", None)
            plan = getattr(action, "plan", None)
            success_metric = None
            if plan is not None and getattr(plan, "target_value", None) is not None:
                success_metric = (
                    f"{getattr(plan, 'name', 'Plan')}: target "
                    f"{plan.target_value} {getattr(plan, 'outcome_unit', '')}".strip()
                )
            result.append(
                {
                    "employee_id": employee_identifier,
                    "employee_name": "Authorized group scope",
                    "team": team_name or "Selected scope",
                    "region": self._canonical_region_value(action_region) or "",
                    "scope_label": " / ".join(
                        part for part in (
                            self._canonical_region_value(action_region),
                            team_name,
                        ) if part
                    ) or "Authorized group scope",
                    "year": action.year,
                    "month": action.month,
                    "action_type": getattr(action, "action_type", None) or "Management workstream",
                    "action_text": getattr(action, "action_text", None) or "Action text needed",
                    "root_cause_note": getattr(action, "root_cause_note", None) or "",
                    "status": getattr(action, "status", None) or "Status not recorded",
                    "priority": getattr(action, "priority", None) or "",
                    "linked_kpi_key": linked_kpi,
                    "owner": (
                        getattr(owner, "username", None)
                        or getattr(owner, "full_name", None)
                        if owner is not None
                        else None
                    ),
                    "due_date": action.due_date.isoformat() if action.due_date else None,
                    "success_metric": success_metric,
                    "evidence_reference": getattr(action, "evidence_reference", None) or "",
                }
            )
        return result

    def _executive_group_presentation_data(self, configuration: ReportConfiguration, scope: dict) -> dict[str, Any]:
        """Build the live, aggregate payload for the CEO/group PPTX."""

        all_records = self._performance_records(configuration, scope)
        start_period, end_period = self._period_bounds(configuration)
        selected_records = [
            record
            for record in all_records
            if (period := self._record_period(record)) and start_period <= period <= end_period
        ]
        if not selected_records:
            raise ReportNotFoundError("No performance data is available for the selected executive group period and scope")

        periods: dict[tuple[int, int], list[Any]] = {}
        for record in all_records:
            period = self._record_period(record)
            if period and period <= end_period:
                periods.setdefault(period, []).append(record)
        comparison_period = self._comparison_period(configuration)
        if comparison_period and comparison_period in {
            self._record_period(record) for record in all_records
        }:
            periods.setdefault(comparison_period, [
                record for record in all_records if self._record_period(record) == comparison_period
            ])

        selected_periods = sorted({self._record_period(record) for record in selected_records if self._record_period(record)})
        latest_period = max(selected_periods) if selected_periods else end_period
        current_records = periods.get(latest_period) or [
            record for record in selected_records if self._record_period(record) == latest_period
        ]
        if not current_records:
            raise ReportNotFoundError("No current performance data is available for the selected executive group period")

        # Historical snapshots can contain a broader population than the
        # latest selected period (for example, July has Offshore EGY rows while
        # June also has UAE rows). Keep the executive baseline/trend like for
        # like by retaining the current period's region scope first, and team
        # scope as the fallback when region is not populated.
        current_region_keys = {
            self._canonical_region_value(self._record_value(record, "region"))
            for record in current_records
            if self._canonical_region_value(self._record_value(record, "region"))
        }
        current_team_keys = {
            self._record_team_name(record).casefold()
            for record in current_records
            if self._record_team_name(record)
        }

        def comparable_scope(record: Any) -> bool:
            region = self._canonical_region_value(self._record_value(record, "region"))
            if current_region_keys:
                return bool(region and region in current_region_keys)
            return self._record_team_name(record).casefold() in current_team_keys

        periods = {
            period: [record for record in rows if comparable_scope(record)]
            for period, rows in periods.items()
        }
        periods = {period: rows for period, rows in periods.items() if rows}
        current_records = periods.get(latest_period) or []
        selected_records = [record for record in selected_records if comparable_scope(record)]
        if not current_records or not selected_records:
            raise ReportNotFoundError("No comparable performance data is available for the selected executive group period")

        def serialize(record: Any) -> dict[str, Any]:
            evaluation = self._record_value(record, "evaluation")
            root_cause = self._record_value(evaluation, "root_cause")
            root_cause_text = ""
            if root_cause:
                root_cause_text = str(
                    self._record_value(root_cause, "text")
                    or self._record_value(root_cause, "cause")
                    or self._record_value(root_cause, "description")
                    or ""
                )
            return {
                "employee_id": str(self._record_value(record, "employee_id", "") or ""),
                "employee_name": str(self._record_value(record, "employee_name", "") or ""),
                "team": self._record_team_name(record),
                "position": str(self._record_value(record, "position", "") or ""),
                "region": str(self._record_value(record, "region", "") or ""),
                "performance_level": str(self._record_value(record, "performance_level", "") or ""),
                "year": self._record_value(record, "year"),
                "month": self._record_value(record, "month"),
                "score": self._record_value(evaluation, "score"),
                "grade": self._record_grade(record),
                "status": str(self._record_value(record, "status", "") or ""),
                "root_cause_text": root_cause_text,
                "kpis": [dict(value) for value in (self._record_value(record, "kpi_values", []) or []) if isinstance(value, dict)],
            }

        serialized_by_period = {
            period: [serialize(record) for record in rows]
            for period, rows in periods.items()
        }
        selected_serialized = [serialize(record) for record in selected_records]
        current_serialized = [serialize(record) for record in current_records]
        history = [
            {
                "key": f"{year}-{month:02d}",
                "label": f"{next(name for name, number in MONTHS.items() if number == month)} {year}",
                "records": serialized_by_period[(year, month)],
            }
            for year, month in sorted(serialized_by_period)
        ]
        comparison_key = f"{comparison_period[0]}-{comparison_period[1]:02d}" if comparison_period else None
        filters = {
            "region": configuration.region,
            "team": configuration.team,
            "performance_level": configuration.performance_level,
            "position": configuration.position,
            "employee_id": configuration.employee_id,
            "grade": configuration.grade,
            "status": configuration.status,
            "kpi": configuration.kpi,
            "comparison_period": comparison_key,
        }
        definitions = self._insights_kpi_definitions(configuration, selected_records)
        scope_label = self._scope_summary(configuration)
        if scope_label == "All authorized teams":
            scope_label = "All authorized regions and teams"
        raw_actions = self._executive_action_rows(configuration, scope, all_records)
        insight_payload = {
            "period_label": self._period_label(configuration),
            "scope_label": scope_label,
            "filters": filters,
            "aggregate_only": True,
            "kpi_definitions": definitions,
            "records": current_serialized,
            "selected_records": selected_serialized,
            "history": history,
            "actions": raw_actions,
        }
        snapshot = build_insights_snapshot(insight_payload)

        def display_region(value: Any) -> str:
            canonical = self._canonical_region_value(value)
            if canonical == "EGY":
                return "Offshore EGY"
            if canonical == "UAE":
                return "UAE"
            return str(value or "Region not available")

        def record_score(record: dict[str, Any]) -> float | None:
            try:
                value = float(record.get("score"))
            except (TypeError, ValueError):
                return None
            return value if value == value else None

        def group_key(record: dict[str, Any], dimension: str) -> str:
            if dimension == "region":
                return display_region(record.get("region"))
            return str(record.get("team") or "Team not available")

        def raw_kpi_matches(driver: dict[str, Any], raw: dict[str, Any]) -> bool:
            requested = {
                str(value or "").casefold()
                for value in (
                    driver.get("key"),
                    driver.get("group_key"),
                    driver.get("label"),
                    *(driver.get("source_keys") or []),
                )
                if value
            }
            actual = {
                str(value or "").casefold()
                for value in (raw.get("kpi_key"), raw.get("key"), raw.get("label"))
                if value
            }
            return bool(requested & actual)

        def raw_has_gap(raw: dict[str, Any]) -> bool:
            ratio = raw.get("achievement_ratio")
            try:
                ratio = float(ratio)
            except (TypeError, ValueError):
                ratio = None
            if ratio is not None:
                if abs(ratio) > 1.5:
                    ratio /= 100.0
                return ratio < 1.0
            actual = self._record_value(raw, "actual_value")
            target = self._record_value(raw, "target_value")
            try:
                actual = float(actual)
                target = float(target)
            except (TypeError, ValueError):
                return False
            direction = str(raw.get("direction") or "higher_better").casefold()
            return actual > target if direction in {"lower_better", "lower is better"} else actual < target

        baseline_period_for_groups = comparison_period or max(
            (period for period in periods if period < latest_period),
            default=None,
        )

        def group_snapshot(group_records: list[dict[str, Any]], baseline_group_records: list[dict[str, Any]]) -> dict[str, Any]:
            group_history = [{
                "key": f"{latest_period[0]}-{latest_period[1]:02d}",
                "label": f"{next(name for name, number in MONTHS.items() if number == latest_period[1])} {latest_period[0]}",
                "records": group_records,
            }]
            if baseline_group_records and baseline_period_for_groups:
                group_history.insert(0, {
                    "key": f"{baseline_period_for_groups[0]}-{baseline_period_for_groups[1]:02d}",
                    "label": f"{next(name for name, number in MONTHS.items() if number == baseline_period_for_groups[1])} {baseline_period_for_groups[0]}",
                    "records": baseline_group_records,
                })
            return build_insights_snapshot({
                "period_label": self._period_label(configuration),
                "scope_label": scope_label,
                "filters": filters,
                "aggregate_only": True,
                "kpi_definitions": definitions,
                "records": group_records,
                "selected_records": group_records,
                "history": group_history,
                "actions": [],
            })

        def group_rows(dimension: str) -> list[dict[str, Any]]:
            current_groups: dict[str, list[dict[str, Any]]] = {}
            baseline_groups: dict[str, list[dict[str, Any]]] = {}
            baseline_period_rows = periods.get(baseline_period_for_groups, []) if baseline_period_for_groups else []
            baseline_serialized = [serialize(record) for record in baseline_period_rows]
            for record in current_serialized:
                current_groups.setdefault(group_key(record, dimension), []).append(record)
            for record in baseline_serialized:
                baseline_groups.setdefault(group_key(record, dimension), []).append(record)
            rows: list[dict[str, Any]] = []
            for name, group_records in sorted(current_groups.items()):
                baseline_group_records = baseline_groups.get(name, [])
                group_data = group_snapshot(group_records, baseline_group_records)
                scores = [record_score(record) for record in group_records]
                scores = [score for score in scores if score is not None]
                group_kpis = [dict(kpi) for kpi in group_data.get("kpis") or []]
                leading = group_kpis[0] if group_kpis else {}
                matching_actions = [
                    action for action in raw_actions
                    if (dimension == "team" and str(action.get("team") or "").casefold() == name.casefold())
                    or (dimension == "region" and display_region(action.get("region")) == name)
                ]
                action_status = "No action recorded"
                if matching_actions:
                    if any(not action.get("owner") or not action.get("due_date") for action in matching_actions):
                        action_status = "Owner / due unresolved"
                    else:
                        action_status = "Open"
                rows.append({
                    "name": name,
                    "scope_type": "Region" if dimension == "region" else "Team",
                    "scope_label": display_region(name) if dimension == "region" else name,
                    "score": group_data.get("latest_score"),
                    "baseline": group_data.get("baseline_score"),
                    "movement": group_data.get("movement"),
                    "target": 100.0,
                    "gap_to_target": max(0.0, 100.0 - (group_data.get("latest_score") or 0.0)) if group_data.get("latest_score") is not None else None,
                    "status": "Requires action" if group_data.get("latest_score") is not None and group_data.get("latest_score") < 70 else "Watch" if group_data.get("latest_score") is not None and group_data.get("latest_score") < 90 else "On track" if group_data.get("latest_score") is not None else "Data unavailable",
                    "record_count": len(group_records),
                    "below_threshold": sum(1 for score in scores if score < 70),
                    "watch_count": sum(1 for score in scores if 70 <= score < 90),
                    "on_track_count": sum(1 for score in scores if score >= 90),
                    "weighted_loss": leading.get("weighted_impact", 0.0) if leading else 0.0,
                    "kpis": group_kpis,
                    "leading_driver": leading.get("label") if leading else None,
                    "action_focus": leading.get("label") if leading else "No measured KPI gap",
                    "action_status": action_status,
                })
            return sorted(rows, key=lambda row: (_number(row.get("score")) is None, _number(row.get("score")) or 0.0, row.get("name", "").casefold()))

        regions = group_rows("region")
        teams = group_rows("team")
        group_lookup = {row["name"]: row for row in regions + teams}
        drivers: list[dict[str, Any]] = []
        for source_driver in snapshot.get("kpis") or []:
            driver = dict(source_driver)
            affected_regions: set[str] = set()
            affected_teams: set[str] = set()
            for record in current_serialized:
                if any(raw_kpi_matches(driver, raw) and raw_has_gap(raw) for raw in record.get("kpis") or []):
                    affected_regions.add(display_region(record.get("region")))
                    affected_teams.add(str(record.get("team") or "Team not available"))
            driver["affected_regions"] = sorted(affected_regions)
            driver["affected_teams"] = sorted(affected_teams)
            driver["affected_scope"] = sorted(affected_regions or affected_teams)
            drivers.append(driver)
        drivers.sort(key=lambda row: (-(_number(row.get("weighted_impact")) or 0.0), _clean(row.get("label"), "").casefold()))

        driver_by_key = {
            str(value or "").casefold(): driver
            for driver in drivers
            for value in (driver.get("key"), driver.get("label"), driver.get("group_key"))
            if value
        }
        actions: list[dict[str, Any]] = []
        for action in snapshot.get("actions") or []:
            linked = str(action.get("linked_kpi_key") or "")
            driver = driver_by_key.get(linked.casefold())
            actions.append({
                "is_proposed": bool(action.get("is_proposed")),
                "action_type": action.get("action_type") or "Management workstream",
                "action_text": action.get("action_display") or action.get("action_text") or "Action text needed",
                "team": action.get("team") or "Selected scope",
                "region": action.get("region") or ((driver or {}).get("affected_regions") or [""])[0],
                "scope": ", ".join((driver or {}).get("affected_scope") or [action.get("scope_label") or "Authorized group scope"]),
                "linked_kpi_key": linked,
                "owner": action.get("owner_display") or action.get("owner") or "Owner needed",
                "due_date": action.get("due_date_display") or action.get("due_date"),
                "status": action.get("status_display") or action.get("status") or "Status not recorded",
                "priority": action.get("priority") or ("High" if driver and (_number(driver.get("weighted_impact")) or 0) >= 10 else "Medium"),
                "success_metric": action.get("success_metric_display") or action.get("success_metric") or "Success metric needed",
                "evidence_reference": action.get("evidence_display") or action.get("evidence_reference") or "No evidence reference",
                "root_cause_note": action.get("root_cause_note") or "",
                "employee_name": "Authorized group scope",
            })
        action_keys = {str(action.get("linked_kpi_key") or "").casefold() for action in actions}
        for driver in drivers[:4]:
            key = str(driver.get("key") or "").casefold()
            if (_number(driver.get("weighted_impact")) or 0.0) <= 0 or key in action_keys:
                continue
            actions.append({
                "is_proposed": True,
                "action_type": "Proposed management action",
                "action_text": f"Validate {driver.get('label', 'KPI')} workflow, ownership, and operating cause.",
                "team": "Selected scope",
                "region": ((driver.get("affected_regions") or [""])[0]),
                "scope": ", ".join(driver.get("affected_scope") or ["Authorized group scope"]),
                "linked_kpi_key": driver.get("key") or "",
                "owner": "Owner needed",
                "due_date": "Due date needed",
                "status": "Proposed",
                "priority": "High" if (_number(driver.get("weighted_impact")) or 0.0) >= 10 else "Medium",
                "success_metric": (
                    f"Move {driver.get('label', 'KPI')} toward {_native(driver.get('target'), driver.get('unit'))}"
                ),
                "evidence_reference": f"{driver.get('label', 'KPI')} actual {_native(driver.get('actual'), driver.get('unit'))} vs target {_native(driver.get('target'), driver.get('unit'))}",
                "root_cause_note": "Investigation Required — cause validation is not recorded.",
                "employee_name": "Authorized group scope",
            })

        evidence: list[dict[str, Any]] = []
        evidence_rows: list[list[str]] = []
        for driver in drivers:
            source_evidence = next(
                (row for row in snapshot.get("root_cause_rows") or [] if str(row.get("key") or row.get("label") or "").casefold() in {str(driver.get("key") or "").casefold(), str(driver.get("label") or "").casefold()}),
                {},
            )
            state = str(source_evidence.get("evidence_status") or "KPI signal only")
            if "confirmed" in state.casefold() and "pending" not in state.casefold():
                display_state = "Confirmed Root Cause"
                note = source_evidence.get("recorded_root_cause") or "Confirmed cause recorded"
            elif "recorded" in state.casefold():
                display_state = "Investigation Required"
                note = f"Recorded note requires confirmation: {source_evidence.get('recorded_root_cause') or 'validate cause'}"
            else:
                display_state = "KPI Evidence"
                note = "KPI evidence identifies the gap; no confirmed operational root cause is recorded."
            evidence_row = {
                **driver,
                "evidence_status": display_state,
                "recorded_root_cause": note,
                "required_validation": "Validate workflow, staffing, handoff, system, prioritization, or process adherence before closing the gap.",
            }
            evidence.append(evidence_row)
            evidence_display = {
                "Confirmed Root Cause": "Confirmed Root Cause — recorded evidence",
                "Investigation Required": "Investigation Required — validate operational cause",
                "KPI Evidence": "KPI Evidence — cause not confirmed",
            }.get(display_state, "Investigation Required — validate operational cause")
            evidence_rows.append([
                ", ".join(driver.get("affected_scope") or ["Authorized group scope"]),
                ", ".join(driver.get("affected_teams") or driver.get("affected_regions") or ["Not available"]),
                _clean(driver.get("label"), "KPI"),
                _native(driver.get("actual"), driver.get("unit")),
                _native(driver.get("target"), driver.get("unit")),
                _pct(driver.get("achievement_pct")),
                _pct(driver.get("weighted_impact")),
                evidence_display,
            ])

        overall_score = snapshot.get("latest_score")
        baseline_score = snapshot.get("baseline_score")
        overall = {
            "name": "Authorized Group Scope",
            "score": overall_score,
            "baseline": baseline_score,
            "movement": snapshot.get("movement"),
            "target": snapshot.get("target_score") or 100.0,
            "gap_to_target": max(0.0, (snapshot.get("target_score") or 100.0) - overall_score) if overall_score is not None else None,
            "status": "Requires action" if overall_score is not None and overall_score < 70 else "Watch" if overall_score is not None and overall_score < 90 else "On track" if overall_score is not None else "Data unavailable",
            "record_count": len(current_serialized),
            "below_threshold": sum(1 for record in current_serialized if record_score(record) is not None and record_score(record) < 70),
        }
        return {
            "report_type": "executive_group_summary",
            "period_label": snapshot.get("latest_period_label") or self._period_label(configuration),
            "comparison_period_label": snapshot.get("comparison_period_label"),
            "scope_label": scope_label,
            "filters": filters,
            "aggregate_only": True,
            "overall": overall,
            "regions": regions,
            "teams": teams,
            "history_count": snapshot.get("history_count", 0),
            "trend": snapshot.get("trend") or [],
            "best_period": snapshot.get("best_period") or {},
            "worst_period": snapshot.get("worst_period") or {},
            "net_movement": snapshot.get("net_movement"),
            "kpis": drivers,
            "drivers": drivers,
            "evidence": evidence,
            # Keep the first page in the primary story and retain every KPI
            # row for the appended reference pages generated by the builder.
            "evidence_rows": evidence_rows[:8],
            "kpi_appendix_rows": evidence_rows,
            "actions": actions,
            "raw_actions": actions,
            "warnings": snapshot.get("warnings") or [],
            "selected_record_count": len(selected_serialized),
            "current_record_count": len(current_serialized),
            "group_lookup": group_lookup,
        }

    @staticmethod
    def _marketing_average_score(records: list[Any]) -> float | None:
        scores_by_employee: dict[str, list[float]] = {}
        for record in records:
            evaluation = ReportService._record_value(record, "evaluation")
            score = ReportService._record_value(evaluation, "score")
            employee_id = str(
                ReportService._record_value(record, "employee_id")
                or ReportService._record_value(record, "employee_name")
                or ""
            )
            if score is None or not employee_id:
                continue
            scores_by_employee.setdefault(employee_id, []).append(float(score))
        employee_scores = [sum(scores) / len(scores) for scores in scores_by_employee.values() if scores]
        return sum(employee_scores) / len(employee_scores) if employee_scores else None

    @staticmethod
    def _marketing_kpi_definitions(configuration: ReportConfiguration) -> list[dict[str, Any]]:
        if (configuration.team or "").casefold() != "marketing":
            return []
        try:
            base_config = load_team_config(configuration.team or "Marketing")
            level = configuration.performance_level or "Employee"
            if configuration.position:
                return list(resolve_team_config(base_config, level, configuration.position).get("kpis", []))
            level_config = base_config.get("performance_levels", {}).get(level, {})
            positions = level_config.get("positions", {}) if isinstance(level_config, dict) else {}
            if positions:
                return [
                    kpi
                    for position_config in positions.values()
                    for kpi in position_config.get("kpis", [])
                ]
            return list(resolve_team_config(base_config, level).get("kpis", []))
        except (ConfigurationError, TypeError, ValueError):
            return []

    @classmethod
    def _insights_kpi_definitions(
        cls,
        configuration: ReportConfiguration,
        records: list[Any],
    ) -> list[dict[str, Any]]:
        """Collect applied KPI metadata without recalculating persisted scores."""

        definitions: dict[str, dict[str, Any]] = {}
        for record in records:
            team_name = cls._record_team_name(record)
            level = str(cls._record_value(record, "performance_level", "Employee") or "Employee")
            position = str(
                cls._record_value(record, "position", None)
                or cls._record_value(record, "position_name", None)
                or ""
            )
            try:
                resolved = resolve_team_config(
                    load_team_config(team_name),
                    level,
                    position or None,
                )
            except (ConfigurationError, TypeError, ValueError, KeyError):
                continue
            for definition in resolved.get("kpis", []) or []:
                key = str(definition.get("key") or definition.get("label") or "").strip()
                if key and key not in definitions:
                    definitions[key] = dict(definition)

        if not definitions:
            definitions.update(
                {
                    str(item.get("key") or item.get("label")): dict(item)
                    for item in cls._marketing_kpi_definitions(configuration)
                    if item.get("key") or item.get("label")
                }
            )
        return list(definitions.values())

    def _performance_data(self, configuration: ReportConfiguration, scope: dict) -> CollectedReport:
        records = self._performance_records(configuration, scope)
        records = [
            record for record in records
            if (period := self._record_period(record))
            and self._period_bounds(configuration)[0] <= period <= self._period_bounds(configuration)[1]
        ]
        if not records:
            raise ReportNotFoundError("No performance data is available for the selected period and scope")

        scores = [float(record.evaluation.score) for record in records if record.evaluation.score is not None]
        average_score = (
            self._marketing_average_score(records)
            if configuration.report_type == "team_marketing"
            else (sum(scores) / len(scores) if scores else None)
        )
        grades = Counter(str(record.evaluation.grade) for record in records)
        statuses = Counter(str(record.status or "Unspecified") for record in records)
        kpi_keys = {
            str(value.get("kpi_key"))
            for record in records
            for value in (record.kpi_values or [])
            if value.get("kpi_key")
        }
        rows = [ReportExporter.flatten_record(record) for record in records]
        return CollectedReport(
            rows=rows,
            records=records,
            summary={
                "record_count": len(records),
                "employee_count": len({str(record.employee_id) for record in records}),
                "team_count": len({str(record.team) for record in records}),
                "average_score": round(average_score, 2) if average_score is not None else None,
                "grade_distribution": dict(sorted(grades.items())),
                "status_distribution": dict(sorted(statuses.items())),
                "kpi_count": len(kpi_keys),
            },
            warnings=[] if scores else ["The selected records do not contain measured performance scores."],
        )

    def _action_data(self, configuration: ReportConfiguration, scope: dict) -> CollectedReport:
        actions = self.actions.list_active()
        evidence_records: list[Any] = []
        if configuration.grade or configuration.kpi:
            # Corrective-action status is the action lifecycle status in this
            # legacy report type.  Keep that meaning while resolving grade and
            # KPI filters against the employee's measured period record.
            evidence_configuration = configuration.model_copy(update={"status": None})
            evidence_records = self._performance_records(evidence_configuration, scope)
        evidence_by_employee_period: dict[tuple[str, tuple[int, int]], list[Any]] = {}
        for record in evidence_records:
            employee_id = str(self._record_value(record, "employee_id", "") or "")
            period = self._record_period(record)
            if employee_id and period:
                evidence_by_employee_period.setdefault((employee_id, period), []).append(record)
        filtered = []
        for action in actions:
            team_name = logical_team_name(action.team) if action.team else ""
            employee_identifier = str(action.employee.employee_id) if action.employee else ""
            if not self._in_period(action.year, action.month, configuration):
                continue
            if configuration.team and team_name.casefold() != configuration.team.casefold():
                continue
            if configuration.employee_id and employee_identifier != configuration.employee_id:
                continue
            action_region = getattr(action.employee, "region", None) or getattr(action.team, "region", None)
            if configuration.region and not self._regions_match(action_region, self._canonical_report_region(configuration)):
                continue
            action_position = getattr(action.employee, "position_name", None) or getattr(action.employee, "position", None)
            if configuration.position and str(action_position or "").casefold() != configuration.position.casefold():
                continue
            if configuration.performance_level and str(getattr(action.employee, "performance_level", "") or "").casefold() != configuration.performance_level.casefold():
                continue
            if configuration.status and action.status.casefold() != configuration.status.casefold():
                continue
            evidence = evidence_by_employee_period.get(
                (employee_identifier, self._record_period({"year": action.year, "month": action.month})),
                [],
            )
            if configuration.grade and not any(
                self._record_grade(record).casefold() == configuration.grade.casefold()
                for record in evidence
            ):
                continue
            if configuration.kpi:
                linked_kpi = str(getattr(action, "linked_kpi_key", "") or "")
                if linked_kpi.casefold() != configuration.kpi.casefold():
                    continue
                if not evidence or not any(self._record_kpi_matches(record, configuration.kpi) for record in evidence):
                    continue
            if scope.get("role") in {"Agent", "Executive"} and employee_identifier != str(scope.get("employee_id") or ""):
                continue
            if scope.get("role") == "Manager" and not scope.get("is_general_manager") and not user_can_access_team(scope, team_name):
                continue
            filtered.append(action)
        if not filtered:
            raise ReportNotFoundError("No corrective actions are available for the selected period and scope")
        rows = [
            {
                "Employee ID": str(action.employee.employee_id) if action.employee else "",
                "Employee Name": action.employee.name if action.employee else "Team / position action",
                "Team": logical_team_name(action.team),
                "Period": f"{action.month} {action.year}",
                "Action Type": action.action_type,
                "Action": action.action_text,
                "Root Cause": action.root_cause_note or "",
                "Status": action.status,
                "Created By": action.created_by_user.username if action.created_by_user else "System",
                "Created At": action.created_at.isoformat() if action.created_at else "",
            }
            for action in filtered
        ]
        statuses = Counter(action.status for action in filtered)
        return CollectedReport(
            rows=rows,
            records=[],
            summary={
                "record_count": len(filtered),
                "employee_count": len({str(action.employee.employee_id) for action in filtered if action.employee}),
                "team_count": len({logical_team_name(action.team) for action in filtered}),
                "status_distribution": dict(sorted(statuses.items())),
            },
            warnings=[],
        )

    def _marketing_presentation_data(self, configuration: ReportConfiguration, scope: dict) -> dict[str, Any]:
        """Build the presentation payload from the same filtered records/actions as the API.

        Marketing used to be generated from a fixed workbook inside the PPTX
        builder.  Keep the filtering here so the selected Reports period,
        region, position and authorization scope are applied before export.
        """
        performance = self._performance_data(configuration, scope)
        # The Marketing template is month-over-month by design.  Keep the
        # selected records and the authorized historical window together so
        # the builder can calculate the comparison from the same scoped
        # snapshot rather than querying a second, unfiltered source.
        all_records = self._performance_records(configuration, scope)
        start_period, end_period = self._period_bounds(configuration)
        selected_records = [
            record
            for record in all_records
            if (record_period := self._record_period(record))
            and start_period <= record_period <= end_period
        ]
        history_grouped: dict[tuple[int, int], list[Any]] = {}
        comparison_period = self._comparison_period(configuration)
        for record in all_records:
            record_period = self._record_period(record)
            if record_period and (record_period <= end_period or record_period == comparison_period):
                history_grouped.setdefault(record_period, []).append(record)
        aggregate_only = self._is_aggregate_scope(scope)
        action_rows: list[dict[str, Any]] = []
        for action in self._presentation_actions(configuration, scope, all_records):
            team_name = logical_team_name(action.team)
            employee_identifier = str(action.employee.employee_id) if action.employee else ""
            owner = getattr(action, "owner", None)
            plan = getattr(action, "plan", None)
            linked_kpi_key = getattr(action, "linked_kpi_key", None)
            success_metric = None
            plan_target_value = None
            plan_target_unit = None
            plan_target_direction = None
            if plan is not None and getattr(plan, "target_value", None) is not None:
                try:
                    plan_target_value = float(plan.target_value)
                except (TypeError, ValueError):
                    plan_target_value = None
                plan_target_unit = getattr(plan, "outcome_unit", None) or None
                plan_target_direction = getattr(plan, "outcome_direction", None) or None
                success_metric = (
                    f"{getattr(plan, 'name', 'Plan')}: target "
                    f"{plan.target_value} {getattr(plan, 'outcome_unit', '')}".strip()
                )
            action_rows.append({
                "employee_id": employee_identifier,
                "employee_name": action.employee.name if action.employee else "Team / position action",
                "team": team_name,
                "month": action.month,
                "year": action.year,
                "action_type": action.action_type,
                "action_text": action.action_text,
                "root_cause_note": action.root_cause_note or "",
                "status": action.status,
                "priority": action.priority or "",
                "linked_kpi_key": linked_kpi_key or "",
                "owner": (
                    getattr(owner, "username", None)
                    or getattr(owner, "full_name", None)
                    if owner is not None
                    else None
                ),
                "due_date": action.due_date.isoformat() if action.due_date else None,
                "success_metric": success_metric,
                "plan_target_value": plan_target_value,
                "plan_target_unit": plan_target_unit,
                "plan_target_direction": plan_target_direction,
                "review_frequency": "Plan milestone cadence" if plan is not None and getattr(plan, "milestones", None) else None,
                "evidence_reference": action.evidence_reference or "",
            })

        def serialize(record: Any) -> dict[str, Any]:
            raw_kpis = list(record.kpi_values or [])
            if configuration.kpi:
                raw_kpis = [
                    value
                    for value in raw_kpis
                    if str(value.get("kpi_key") or value.get("label") or "").casefold()
                    == configuration.kpi.casefold()
                ]
            evaluation = getattr(record, "evaluation", None)
            root_cause = getattr(evaluation, "root_cause", None)
            root_cause_payload = {}
            if root_cause:
                root_cause_payload = {
                    "kpi": getattr(root_cause, "kpi", None),
                    "impact_pct": getattr(root_cause, "impact_pct", None),
                    "actual": getattr(root_cause, "actual", None),
                    "target": getattr(root_cause, "target", None),
                    "text": getattr(root_cause, "text", None),
                    "cause": getattr(root_cause, "cause", None),
                    "description": getattr(root_cause, "description", None),
                }
            return {
                "employee_id": "" if aggregate_only else str(record.employee_id),
                "employee_name": "Aggregate team data" if aggregate_only else record.employee_name,
                "team": self._record_team_name(record),
                "position": record.position or "Marketing",
                "region": record.region or "",
                "year": record.year,
                "month": record.month,
                "score": evaluation.score if evaluation else None,
                "grade": evaluation.grade if evaluation else "",
                "status": record.status or "",
                "root_cause": root_cause_payload,
                "suggested_action": evaluation.suggested_action if evaluation else "",
                "corrective_action": evaluation.corrective_action if evaluation else "",
                "manager_notes": evaluation.manager_notes if evaluation else "",
                "kpis": raw_kpis,
            }

        serialized_selected = [serialize(record) for record in selected_records or performance.records]
        history = []
        for year, month_number in sorted(history_grouped):
            month_name = next(
                (name for name, number in MONTHS.items() if number == month_number),
                str(month_number),
            )
            history.append({
                "key": f"{year}-{month_number:02d}",
                "label": f"{month_name} {year}",
                "records": [serialize(record) for record in history_grouped[(year, month_number)]],
            })
        if not history:
            history = [{
                "key": f"{configuration.start_year}-{MONTHS[configuration.start_month]:02d}",
                "label": self._period_label(configuration),
                "records": serialized_selected,
            }]
        comparison_period_key = (
            f"{comparison_period[0]}-{comparison_period[1]:02d}"
            if comparison_period
            else None
        )
        return {
            # Resolve definitions from the actual selected records first so a
            # position/level filter cannot silently fall back to Employee.
            "kpi_definitions": self._insights_kpi_definitions(
                configuration,
                selected_records or performance.records,
            ),
            "aggregate_only": aggregate_only,
            "period_label": self._period_label(configuration),
            "scope_label": self._scope_summary(configuration),
            "filters": {
                "region": configuration.region,
                "team": configuration.team,
                "performance_level": configuration.performance_level,
                "position": configuration.position,
                "employee_id": configuration.employee_id,
                "grade": configuration.grade,
                "status": configuration.status,
                "kpi": configuration.kpi,
                "comparison_period": comparison_period_key,
            },
            "records": serialized_selected,
            "selected_records": serialized_selected,
            "history": history,
                "actions": action_rows,
        }

    def _offshore_status_presentation_data(self, configuration: ReportConfiguration, scope: dict) -> dict[str, Any]:
        """Build the full scoped payload used by the Departments reference deck.

        The corrected Offshore deck needs the same rich contract as the
        Marketing story: selected records, comparable history, KPI
        definitions, evidence, and action rows.  Keeping this call here
        preserves the existing Reports filters and authorization boundary.
        """

        payload = self._marketing_presentation_data(configuration, scope)
        if configuration.report_type == "monthly_egypt":
            region_label = "Offshore EGY"
        elif configuration.report_type == "monthly_uae":
            region_label = "UAE"
        else:
            region_label = configuration.region or "UAE"
        payload["region_label"] = region_label
        payload["scope_label"] = self._scope_summary(configuration)
        payload["report_type"] = configuration.report_type
        return payload

    def _uae_executive_presentation_data(self, configuration: ReportConfiguration, scope: dict) -> dict[str, Any]:
        """Build one canonical, aggregate-safe UAE executive contract.

        All rows come through ``_performance_records`` and all action rows
        come through ``_executive_action_rows``.  The contract then resolves
        the selected current period, the like-for-like baseline, department
        population, KPI loss, and action completeness once for every slide.
        """

        from services.uae_executive_summary import build_uae_executive_summary_contract

        all_records = self._performance_records(configuration, scope)
        start_period, end_period = self._period_bounds(configuration)
        selected_periods = sorted(
            {
                period
                for record in all_records
                if (period := self._record_period(record)) and start_period <= period <= end_period
            }
        )
        # A selected month with no current rows is still a valid report state;
        # the contract renders "No current UAE data" and keeps coverage rows
        # rather than converting missing data into NEW.
        current_period = selected_periods[-1] if selected_periods else end_period
        definitions = self._insights_kpi_definitions(configuration, all_records)
        known_departments = sorted(
            {
                self._record_team_name(record)
                for record in all_records
                if self._record_team_name(record)
            },
            key=str.casefold,
        )
        action_rows = self._executive_action_rows(configuration, scope, all_records)
        filters = {
            "region": configuration.region or "UAE",
            "team": configuration.team,
            "performance_level": configuration.performance_level,
            "position": configuration.position,
            "employee_id": configuration.employee_id,
            "grade": configuration.grade,
            "status": configuration.status,
            "kpi": configuration.kpi,
            "comparison_period": (
                f"{configuration.comparison_year}-{MONTHS[configuration.comparison_month]:02d}"
                if configuration.comparison_year and configuration.comparison_month
                else None
            ),
        }
        scope_label = self._scope_summary(configuration)
        if not scope_label or scope_label == "All authorized teams":
            scope_label = "UAE"
        payload = build_uae_executive_summary_contract(
            all_records,
            current_period=current_period,
            comparison_period=self._comparison_period(configuration),
            definitions=definitions,
            actions=action_rows,
            known_departments=known_departments,
            period_label_override=self._period_label(configuration),
            scope_label=scope_label,
            filters=filters,
            aggregate_only=self._is_aggregate_scope(scope),
        )
        payload["report_type"] = configuration.report_type
        payload["region_label"] = "UAE"
        return payload

    def _uae_executive_collected(self, configuration: ReportConfiguration, scope: dict) -> CollectedReport:
        """Provide preview/persistence metadata from the same CEO contract."""

        payload = self._uae_executive_presentation_data(configuration, scope)
        population = payload.get("population") or {}
        summary = {
            "record_count": population.get("current_record_count", 0),
            "employee_count": payload.get("employee_count", 0),
            "team_count": payload.get("active_departments", 0),
            "average_score": payload.get("current_score"),
            "baseline_score": payload.get("baseline"),
            "movement": payload.get("mom"),
            "target": payload.get("target"),
            "gap_to_target": payload.get("gap_to_target"),
            "open_actions": payload.get("open_action_count", 0),
            "missing_owners": payload.get("missing_owner_count", 0),
            "missing_due_dates": payload.get("missing_due_date_count", 0),
            "aggregate_only": bool(payload.get("aggregate_only")),
        }
        return CollectedReport(
            rows=list(payload.get("department_scorecard_rows") or []),
            records=[],
            summary=summary,
            warnings=list(payload.get("warnings") or []),
        )

    def _insights_presentation_data(self, configuration: ReportConfiguration, scope: dict) -> dict[str, Any]:
        """Build the filtered, trend-aware payload used by the Insights deck."""
        all_records = self._performance_records(configuration, scope)
        start_period, end_period = self._period_bounds(configuration)
        selected_records = [
            record
            for record in all_records
            if (record_period := self._record_period(record))
            and start_period <= record_period <= end_period
        ]
        if not selected_records:
            raise ReportNotFoundError("No performance data is available for the selected Insights period and scope")

        # Keep the selected range separate from the historical comparison
        # window.  A single-month export must still be able to compare with
        # the previous available period without changing the selected scope.
        period_records: dict[tuple[int, int], list[Any]] = {}
        history_records: dict[tuple[int, int], list[Any]] = {}
        for record in all_records:
            period = self._record_period(record)
            if period and period <= end_period:
                history_records.setdefault(period, []).append(record)
            if period and start_period <= period <= end_period:
                period_records.setdefault(period, []).append(record)
        ordered_periods = sorted(period_records)
        ordered_history_periods = sorted(history_records)
        latest_period = ordered_periods[-1]
        current_records = period_records[latest_period]
        selected_kpi = str(configuration.kpi or "").casefold()
        aggregate_only = self._is_aggregate_scope(scope)

        def serialize(record: Any) -> dict[str, Any]:
            raw_kpis = list(record.kpi_values or [])
            if selected_kpi:
                raw_kpis = [
                    value for value in raw_kpis
                    if str(value.get("kpi_key") or value.get("label") or "").casefold() == selected_kpi
                ]
            evaluation = getattr(record, "evaluation", None)
            root_cause = getattr(evaluation, "root_cause", None)
            root_cause_payload = None
            if root_cause:
                root_cause_payload = {
                    "kpi": getattr(root_cause, "kpi", None),
                    "impact_pct": getattr(root_cause, "impact_pct", None),
                    "actual": getattr(root_cause, "actual", None),
                    "target": getattr(root_cause, "target", None),
                }
            return {
                "employee_id": "" if aggregate_only else str(record.employee_id),
                "employee_name": "Aggregate team data" if aggregate_only else record.employee_name,
                "team": self._record_team_name(record),
                "position": record.position or "Unassigned",
                "region": record.region or "",
                "score": record.evaluation.score,
                "year": record.year,
                "month": record.month,
                "grade": record.evaluation.grade,
                "status": record.status or "",
                "root_cause": root_cause_payload,
                "suggested_action": evaluation.suggested_action or "",
                "corrective_action": evaluation.corrective_action or "",
                "manager_notes": evaluation.manager_notes or "",
                "planning_category": list(evaluation.planning_category or []),
                "trend_status": dict(evaluation.trend_status or {}),
                "kpis": raw_kpis,
            }

        history = []
        for year, month_number in ordered_history_periods:
            month_name = next(name for name, number in MONTHS.items() if number == month_number)
            history.append({
                "key": f"{year}-{month_number:02d}",
                "label": f"{month_name} {year}",
                "records": [serialize(record) for record in history_records[(year, month_number)]],
            })

        actions = self._marketing_presentation_data(configuration, scope).get("actions", [])
        scope_parts = [part for part in (configuration.region, configuration.team, configuration.performance_level, configuration.position) if part]
        if configuration.employee_id:
            scope_parts.append(f"Employee {configuration.employee_id}")
        return {
            "kpi_definitions": self._insights_kpi_definitions(configuration, selected_records),
            "aggregate_only": aggregate_only,
            "selected_period_keys": [f"{year}-{month:02d}" for year, month in ordered_periods],
            "period_label": self._period_label(configuration),
            "scope_label": " • ".join(scope_parts) or "All authorized scope",
            "filters": {
                "region": configuration.region,
                "team": configuration.team,
                "performance_level": configuration.performance_level,
                "position": configuration.position,
                "employee_id": configuration.employee_id,
                "kpi": configuration.kpi,
                "severity": configuration.severity,
                "insight_type": configuration.insight_type,
            },
            "records": [serialize(record) for record in current_records],
            "selected_records": [serialize(record) for record in selected_records],
            "history": history,
            "actions": actions,
        }

    def _upload_data(self, configuration: ReportConfiguration, scope: dict) -> CollectedReport:
        uploads = []
        for upload in self.reports.list_upload_logs():
            team_name = logical_team_name(upload.team)
            if not self._in_period(upload.year, upload.month, configuration):
                continue
            if configuration.team and team_name.casefold() != configuration.team.casefold():
                continue
            if not user_can_access_team(scope, team_name):
                continue
            if configuration.status and upload.status.casefold() != configuration.status.casefold():
                continue
            uploads.append(upload)
        if not uploads:
            raise ReportNotFoundError("No upload data is available for the selected period and scope")
        rows = [
            {
                "Team": logical_team_name(upload.team),
                "Period": f"{upload.month} {upload.year}",
                "Record Count": upload.record_count,
                "Status": upload.status,
                "Error": upload.error_message or "",
                "Uploaded At": upload.uploaded_at.isoformat() if upload.uploaded_at else "",
            }
            for upload in uploads
        ]
        statuses = Counter(upload.status for upload in uploads)
        return CollectedReport(
            rows=rows,
            records=[],
            summary={
                "record_count": len(uploads),
                "processed_record_count": sum(upload.record_count for upload in uploads),
                "team_count": len({logical_team_name(upload.team) for upload in uploads}),
                "status_distribution": dict(sorted(statuses.items())),
            },
            warnings=["Some uploads contain processing errors."] if any(upload.error_message for upload in uploads) else [],
        )

    def _collect(self, configuration: ReportConfiguration, scope: dict) -> CollectedReport:
        self._validate_scope(configuration, scope)
        effective_scope = self._effective_scope(scope)
        if configuration.report_type == "uae_executive_summary":
            return self._uae_executive_collected(configuration, scope)
        if configuration.report_type == "corrective_actions":
            return self._action_data(configuration, effective_scope)
        if configuration.report_type == "data_quality":
            return self._upload_data(configuration, effective_scope)
        return self._performance_data(configuration, effective_scope)

    def _redact_aggregate_data(self, data: CollectedReport, scope: dict) -> CollectedReport:
        """Keep previews and exports useful while removing person-level fields."""

        if not self._is_aggregate_scope(scope):
            return data
        grouped: dict[str, list[Any]] = {}
        for record in data.records:
            grouped.setdefault(self._record_team_name(record) or "Unknown", []).append(record)

        if grouped:
            rows: list[dict[str, Any]] = []
            for team, records in sorted(grouped.items()):
                scores: list[float] = []
                for record in records:
                    raw_score = self._record_value(self._record_value(record, "evaluation"), "score")
                    try:
                        if raw_score is not None:
                            scores.append(float(raw_score))
                    except (TypeError, ValueError):
                        continue
                average = sum(scores) / len(scores) if scores else None
                rows.append({
                    "Team": team,
                    "Record Count": len(records),
                    "Average Score": round(average, 2) if average is not None else None,
                    "At Risk Count": sum(70 <= score < 100 for score in scores),
                    "Critical Count": sum(score < 70 for score in scores),
                })
            summary = dict(data.summary)
            summary["employee_count"] = len(data.records)
            summary["team_count"] = len(grouped)
            summary["aggregate_only"] = True
            warnings = list(data.warnings)
            warnings.append("Person-level fields are omitted for this role.")
            return CollectedReport(rows=rows, records=[], summary=summary, warnings=warnings)

        safe_rows = []
        sensitive = {
            "employee id", "employee name", "employee", "action", "root cause",
            "created by", "suggested action", "manager notes", "manager corrective action",
        }
        for row in data.rows:
            safe_rows.append({
                key: value
                for key, value in row.items()
                if str(key).strip().casefold() not in sensitive
                and "employee" not in str(key).casefold()
            })
        summary = dict(data.summary)
        summary["aggregate_only"] = True
        warnings = list(data.warnings)
        if data.rows:
            warnings.append("Person-level fields are omitted for this role.")
        return CollectedReport(rows=safe_rows, records=[], summary=summary, warnings=warnings)

    def preview(self, configuration: ReportConfiguration, scope: dict) -> dict[str, Any]:
        data = self._redact_aggregate_data(self._collect(configuration, scope), scope)
        return {
            "title": configuration.report_name,
            "report_type": configuration.report_type,
            "scope": self._scope_summary(configuration),
            "period": self._period_label(configuration),
            "filters": configuration.model_dump(exclude={"included_sections", "report_name", "output_format"}),
            "included_sections": configuration.included_sections,
            "summary": data.summary,
            "record_count": data.summary["record_count"],
            "warnings": data.warnings,
            "table_preview": data.rows[:5],
            "preview_redacted": self._is_aggregate_scope(scope),
            "capabilities": {
                "can_view_people": str(scope.get("role") or "") in {"Admin", "Manager"},
                "can_view_actions": (
                    str(scope.get("role") or "Viewer") == "Admin"
                    or "view_actions" in PERMISSION_MATRIX.get(str(scope.get("role") or "Viewer"), [])
                ),
            },
        }

    def generate(
        self,
        configuration: ReportConfiguration,
        scope: dict,
        *,
        processing_job_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> GeneratedReport:
        effective_scope = self._effective_scope(scope)
        data = self._redact_aggregate_data(self._collect(configuration, scope), scope)
        period_label = self._period_label(configuration)
        scope_summary = self._scope_summary(configuration)
        metadata = {
            "Report Name": configuration.report_name,
            "Report Type": configuration.report_type,
            "Scope": scope_summary,
            "Period": period_label,
            "Record Count": data.summary["record_count"],
        }
        metadata["Included Sections"] = ", ".join(configuration.included_sections)
        sheets: dict[str, list[dict[str, Any]]] = {}
        sections = set(configuration.included_sections)
        if "summary" in sections:
            sheets["Summary"] = [
                {"Metric": key.replace("_", " ").title(), "Value": value}
                for key, value in data.summary.items()
                if not isinstance(value, dict)
            ]
        if "grade_distribution" in sections:
            sheets["Grade Distribution"] = [
                {"Grade": grade, "Count": count}
                for grade, count in data.summary.get("grade_distribution", {}).items()
            ]
        if "status_breakdown" in sections:
            sheets["Status Breakdown"] = [
                {"Status": status, "Count": count}
                for status, count in data.summary.get("status_distribution", {}).items()
            ]
        if "team_breakdown" in sections and data.records:
            teams = Counter(str(record.team) for record in data.records)
            sheets["Team Breakdown"] = [{"Team": team, "Count": count} for team, count in sorted(teams.items())]
        elif "team_breakdown" in sections and data.summary.get("aggregate_only") and data.rows:
            sheets["Team Breakdown"] = data.rows
        if "kpi_breakdown" in sections and data.records:
            sheets["KPI Breakdown"] = [
                {
                    "Employee ID": str(record.employee_id),
                    "Employee Name": record.employee_name,
                    "Team": record.team,
                    "KPI": value.get("label") or value.get("kpi_key"),
                    "Actual": value.get("actual_value"),
                    "Target": value.get("target_value"),
                    "Achievement": value.get("achievement_ratio"),
                    "Contribution": value.get("contribution"),
                }
                for record in data.records
                for value in (record.kpi_values or [])
            ]
        if "details" in sections:
            sheets["Report Details"] = data.rows

        # UAE and Offshore EGY monthly PPTX reports use the approved Offshore
        # Departments reference. Keep this branch ahead of the generic slide
        # builder so
        # the Reports page cannot accidentally fall back to a blank layout.
        if configuration.report_type in {"monthly_uae", "monthly_egypt"} and configuration.output_format == "pptx":
            file_data = build_offshore_status_pptx(
                period_label,
                self._offshore_status_presentation_data(configuration, effective_scope),
            )
            content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            extension = ".pptx"
        elif configuration.report_type == "uae_executive_summary" and configuration.output_format == "pptx":
            file_data = build_uae_executive_summary_pptx(
                period_label,
                self._uae_executive_presentation_data(configuration, scope),
            )
            content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            extension = ".pptx"
            configuration.output_format = "pptx"
        elif configuration.report_type == "executive_group_summary" and configuration.output_format == "pptx":
            file_data = build_executive_group_summary_pptx(
                period_label,
                self._executive_group_presentation_data(configuration, scope),
            )
            content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            extension = ".pptx"
            configuration.output_format = "pptx"
        # If slides are provided in the configuration, we use the advanced python-pptx builder
        elif getattr(configuration, "slides", None) and configuration.output_format == "pptx":
            # Generate narratives for any narrative blocks
            for slide in configuration.slides:
                for block in slide.blocks:
                    if block.type == "narrative":
                        block.config.settings["title"] = generate_narrative(data.summary, "Performance")

            # Serialize the Pydantic models to dicts for the builder
            slides_data = [slide.model_dump() for slide in configuration.slides]
            file_data = build_pptx_from_slides(configuration.report_name, slides_data, period_label)
            content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            extension = ".pptx"
        elif configuration.report_type == "team_marketing":
            file_data = build_marketing_legendary_pptx(
                period_label,
                self._marketing_presentation_data(configuration, effective_scope),
            )
            content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            extension = ".pptx"
            configuration.output_format = "pptx"
        elif configuration.report_type == "insights":
            file_data = build_insights_pptx(
                period_label,
                self._insights_presentation_data(configuration, effective_scope),
            )
            content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            extension = ".pptx"
            configuration.output_format = "pptx"
        else:
            file_data, content_type, extension = ReportExporter.export_report(
                title=configuration.report_name,
                metadata=metadata,
                sheets=sheets,
                output_format=configuration.output_format,
            )

        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", configuration.report_name).strip("_") or "PMS_Report"
        user = scope.get("user")
        user_id = getattr(user, "id", None) or _safe_uuid(scope.get("user_id"))
        persisted_configuration = configuration.model_dump(mode="json")
        if processing_job_id:
            persisted_configuration["_processing_job_id"] = str(processing_job_id)
        if idempotency_key:
            persisted_configuration["_idempotency_key"] = str(idempotency_key)[:255]
        report = GeneratedReport(
            name=configuration.report_name,
            report_type=configuration.report_type,
            scope_summary=scope_summary,
            period_label=period_label,
            created_by_user_id=user_id,
            created_by_name=getattr(user, "username", None) or str(scope.get("username") or "User"),
            output_format=configuration.output_format,
            status="ready",
            file_name=f"{safe_name}{extension}",
            content_type=content_type,
            file_data=file_data,
            configuration=persisted_configuration,
            record_count=data.summary["record_count"],
            warning=" ".join(data.warnings) or None,
        )
        try:
            self.reports.add_generated(report)
            self.db.commit()
            self.db.refresh(report)
        except Exception:
            self.db.rollback()
            raise
        return report

    @staticmethod
    def serialize_generated(report: GeneratedReport) -> dict[str, Any]:
        created_at = report.created_at
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        configuration = report.configuration if isinstance(report.configuration, dict) else {}
        public_configuration = {
            key: value for key, value in configuration.items() if not str(key).startswith("_")
        }
        return {
            "id": str(report.id),
            "name": report.name,
            "report_type": report.report_type,
            "scope": report.scope_summary,
            "period": report.period_label,
            "created_by": report.created_by_name,
            "created_at": created_at.isoformat() if created_at else None,
            "format": report.output_format,
            "status": report.status,
            "file_name": report.file_name,
            "record_count": report.record_count,
            "warning": report.warning,
            "configuration": public_configuration,
            "download_url": f"/api/reports/{report.id}/download",
        }

    def list_generated(
        self,
        scope: dict,
        *,
        mine: bool,
        page: int,
        page_size: int,
        report_type: str | None = None,
        period: str | None = None,
        status: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        user_id = _safe_uuid(scope.get("user_id"))
        owner = user_id if mine or scope.get("role") != "Admin" else None
        rows, total = self.reports.list_generated(
            owner_user_id=owner,
            offset=(page - 1) * page_size,
            limit=page_size,
            report_type=report_type,
            period=period,
            status=status,
            search=search,
        )
        return {"items": [self.serialize_generated(row) for row in rows], "total": total, "page": page, "page_size": page_size}

    def get_download(self, report_id: str, scope: dict) -> GeneratedReport:
        try:
            parsed_id = uuid.UUID(report_id)
        except ValueError as exc:
            raise ReportNotFoundError("Report was not found") from exc
        report = self.reports.get_generated(parsed_id)
        if not report:
            raise ReportNotFoundError("Report was not found")
        if scope.get("role") != "Admin" and str(report.created_by_user_id) != str(scope.get("user_id")):
            raise ReportAccessError("This report belongs to another user")
        return report

    def find_generated_by_idempotency(self, scope: dict, idempotency_key: str | None) -> GeneratedReport | None:
        normalized = (idempotency_key or "").strip()
        if not normalized:
            return None
        return self.reports.get_generated_by_idempotency_key(
            normalized,
            owner_user_id=_safe_uuid(scope.get("user_id")),
        )

    def delete_generated(self, report_id: str, scope: dict) -> dict[str, str]:
        report = self.get_download(report_id, scope)
        result = {"id": str(report.id), "name": report.name}
        try:
            self.reports.delete_generated(report)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return result

    def delete_generated_many(self, report_ids: list[str], scope: dict) -> list[dict[str, str]]:
        reports = [self.get_download(report_id, scope) for report_id in dict.fromkeys(report_ids)]
        results = [{"id": str(report.id), "name": report.name} for report in reports]
        try:
            for report in reports:
                self.reports.delete_generated(report)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return results

    def save_template(self, name: str, configuration: ReportConfiguration, scope: dict) -> SavedReportTemplate:
        self._validate_scope(configuration, scope)
        template = SavedReportTemplate(
            name=name,
            report_type=configuration.report_type,
            configuration=configuration.model_dump(mode="json"),
            included_sections=configuration.included_sections,
            preferred_format=configuration.output_format,
            owner_user_id=_safe_uuid(scope.get("user_id")),
            visibility="private",
        )
        try:
            self.reports.add_saved_template(template)
            self.db.commit()
            self.db.refresh(template)
        except IntegrityError as exc:
            self.db.rollback()
            raise ReportValidationError("A saved template with this name already exists") from exc
        except Exception:
            self.db.rollback()
            raise
        return template

    def list_saved_templates(self, scope: dict) -> list[dict[str, Any]]:
        user_id = _safe_uuid(scope.get("user_id"))
        rows = self.reports.list_saved_templates(user_id) if user_id else []
        return [
            {
                "id": str(row.id),
                "name": row.name,
                "report_type": row.report_type,
                "configuration": row.configuration,
                "included_sections": row.included_sections,
                "preferred_format": row.preferred_format,
                "visibility": row.visibility,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]
