from __future__ import annotations

import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from exports.report_exporter import ReportExporter
from exports.pptx_builder import build_pptx_from_slides
from exports.marketing_pptx_builder import build_marketing_pptx
from services.narrative_engine import generate_narrative
from models.models import GeneratedReport, SavedReportTemplate
from models.report_schemas import MONTHS, ReportConfiguration
from repositories.action_repository import ActionRepository
from repositories.report_repository import ReportRepository
from services.dashboard_record_service import DashboardRecordService
from services.permission_seed import PERMISSION_MATRIX
from utils.report_scope import (
    filter_records_by_scope,
    filter_records_by_team_levels,
    user_can_access_team,
    user_can_access_team_level,
)
from utils.team_identity import logical_team_name


def _safe_uuid(value: Any) -> uuid.UUID | None:
    if not value:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


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
        "name": "Monthly Report - UAE",
        "description": "Comprehensive monthly performance overview for the UAE region.",
        "formats": ["pdf", "pptx"],
        "sections": ["summary", "grade_distribution", "team_breakdown", "details"],
    },
    {
        "type": "monthly_egypt",
        "category": "executive",
        "name": "Monthly Report - Egypt",
        "description": "Comprehensive monthly performance overview for the Egypt region.",
        "formats": ["pdf", "pptx"],
        "sections": ["summary", "grade_distribution", "team_breakdown", "details"],
    },
    {
        "type": "team_marketing",
        "category": "team",
        "name": "Team Report - Marketing",
        "description": "Storytelling PPTX report for Marketing department performance.",
        "formats": ["pptx"],
        "sections": ["summary", "details"],
    }
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
    def _period_bounds(configuration: ReportConfiguration) -> tuple[tuple[int, int], tuple[int, int]]:
        start = (configuration.start_year, MONTHS[configuration.start_month])
        end = (
            configuration.end_year or configuration.start_year,
            MONTHS[configuration.end_month or configuration.start_month],
        )
        return start, end

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
        if configuration.employee_id:
            return f"Employee {configuration.employee_id}"
        if configuration.position:
            return configuration.position
        return configuration.team or "All authorized teams"

    @staticmethod
    def _filter_level_assignments(records: list[Any], scope: dict) -> list[Any]:
        return filter_records_by_team_levels(records, scope)

    def options(self, scope: dict) -> dict[str, Any]:
        option_loader = getattr(self.record_service, "list_option_rows", None)
        records = option_loader() if callable(option_loader) else self.record_service.list_records()
        records = filter_records_by_scope(records, scope)
        records = self._filter_level_assignments(records, scope)
        periods = sorted(
            {period for record in records if (period := self._record_period(record))},
            reverse=True,
        )
        employees: dict[str, dict[str, str]] = {}
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
        role = str(scope.get("role") or "Viewer")
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
            "performance_levels": sorted({str(self._record_value(record, "performance_level")) for record in records if self._record_value(record, "performance_level")}),
            "positions": sorted({str(self._record_value(record, "position")) for record in records if self._record_value(record, "position")}),
            "employees": sorted(employees.values(), key=lambda item: (item["name"], item["id"])),
            "grades": sorted({
                str(grade)
                for record in records
                if (grade := self._record_value(record, "grade") or getattr(self._record_value(record, "evaluation"), "grade", None))
            }),
            "statuses": sorted({str(self._record_value(record, "status")) for record in records if self._record_value(record, "status")}),
            "can_export": "export_data" in PERMISSION_MATRIX.get(role, []),
        }

    def _validate_scope(self, configuration: ReportConfiguration, scope: dict) -> None:
        if configuration.team and not user_can_access_team(scope, configuration.team):
            raise ReportAccessError("The selected team is outside the authorized reporting scope")
        if configuration.team and configuration.performance_level and not user_can_access_team_level(
            scope,
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

    def _performance_data(self, configuration: ReportConfiguration, scope: dict) -> CollectedReport:
        records = self.record_service.list_records(
            team=configuration.team,
            employee_id=configuration.employee_id,
            grade=configuration.grade,
            status=configuration.status,
            performance_level=configuration.performance_level,
            position=configuration.position,
            region=configuration.region,
        )
        records = filter_records_by_scope(records, scope)
        records = self._filter_level_assignments(records, scope)
        records = [
            record for record in records
            if (period := self._record_period(record))
            and self._period_bounds(configuration)[0] <= period <= self._period_bounds(configuration)[1]
        ]
        if not records:
            raise ReportNotFoundError("No performance data is available for the selected period and scope")

        scores = [float(record.evaluation.score) for record in records if record.evaluation.score is not None]
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
                "average_score": round(sum(scores) / len(scores), 2) if scores else None,
                "grade_distribution": dict(sorted(grades.items())),
                "status_distribution": dict(sorted(statuses.items())),
                "kpi_count": len(kpi_keys),
            },
            warnings=[] if scores else ["The selected records do not contain measured performance scores."],
        )

    def _action_data(self, configuration: ReportConfiguration, scope: dict) -> CollectedReport:
        actions = self.actions.list_active()
        filtered = []
        for action in actions:
            team_name = logical_team_name(action.team)
            employee_identifier = str(action.employee.employee_id) if action.employee else ""
            if not self._in_period(action.year, action.month, configuration):
                continue
            if configuration.team and team_name.casefold() != configuration.team.casefold():
                continue
            if configuration.employee_id and employee_identifier != configuration.employee_id:
                continue
            if configuration.status and action.status.casefold() != configuration.status.casefold():
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
        if configuration.report_type == "corrective_actions":
            return self._action_data(configuration, scope)
        if configuration.report_type == "data_quality":
            return self._upload_data(configuration, scope)
        return self._performance_data(configuration, scope)

    def preview(self, configuration: ReportConfiguration, scope: dict) -> dict[str, Any]:
        data = self._collect(configuration, scope)
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
        }

    def generate(
        self,
        configuration: ReportConfiguration,
        scope: dict,
        *,
        processing_job_id: str | None = None,
    ) -> GeneratedReport:
        data = self._collect(configuration, scope)
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

        # If slides are provided in the configuration, we use the advanced python-pptx builder
        if getattr(configuration, "slides", None) and configuration.output_format == "pptx":
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
            file_data = build_marketing_pptx(period_label)
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

    def list_generated(self, scope: dict, *, mine: bool, page: int, page_size: int) -> dict[str, Any]:
        user_id = _safe_uuid(scope.get("user_id"))
        owner = user_id if mine or scope.get("role") != "Admin" else None
        rows, total = self.reports.list_generated(
            owner_user_id=owner,
            offset=(page - 1) * page_size,
            limit=page_size,
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
