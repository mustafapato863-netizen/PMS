from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from exports.presentation_pdf import build_presentation_pdf, pdf_integrity_identifier
from models.models import GeneratedReport, PerformanceRecord as ORMPerformanceRecord, ReportDraft, ReportTemplate
from models.report_definitions import (
    BlockDataResult, GeneratedNarrative, MANAGEMENT_BLOCK_CONTRACTS, ManagementCommentary, NarrativeRegenerateRequest, ReportDraftCreate,
    ReportDraftDefinition, ReportDraftUpdate, ReportGenerateRequest, ReportPeriod, ReportScope,
    ReportTemplateCreate, ReportTemplateDefinition, ReportTemplateUpdate, ReportValidationIssue,
    ReportValidationResult, SlideDataResult,
)
from repositories.action_repository import ActionRepository
from repositories.performance_repository import PerformanceRepository
from repositories.planning_repository import PlanningRepository
from repositories.report_repository import ReportRepository
from services.dashboard_record_service import DashboardRecordService
from services.insights_service import InsightsService
from services.planning_service import PlanningService
from services.permission_seed import PERMISSION_MATRIX
from services.report_registry import BLOCK_REGISTRY, LAYOUT_REGISTRY, public_block_registry, public_layout_registry, validate_definition
from services.report_system_templates import SYSTEM_TEMPLATES
from services.reporting_evidence_service import ReportingEvidenceService, period_key as evidence_period_key, previous_calendar_period, score as evidence_score
from utils.report_scope import filter_records_by_scope, filter_records_by_team_levels, user_can_access_team, user_can_access_team_level
from utils.team_identity import logical_team_name


MONTHS = {name: index for index, name in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}
MONTH_NAMES = {value: key for key, value in MONTHS.items()}


class StoryValidationError(ValueError): pass
class StoryNotFoundError(LookupError): pass
class StoryAccessError(PermissionError): pass
class StoryConflictError(RuntimeError): pass


def _safe_uuid(value: Any) -> uuid.UUID | None:
    if not value:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _number(value) -> float | None:
    try: return float(value) if value is not None else None
    except (TypeError, ValueError): return None


def _score(record) -> float | None:
    return evidence_score(record)


def _period_key(record) -> tuple[int, int] | None:
    return evidence_period_key(record)


def _previous_period(period: ReportPeriod, count: int = 1) -> ReportPeriod:
    value = period.year * 12 + MONTHS[period.month] - 1 - count
    return ReportPeriod(year=value // 12, month=MONTH_NAMES[value % 12 + 1])


class ReportStoryService:
    def __init__(self, db: Session, record_service: DashboardRecordService | None = None):
        self.db = db
        self.records = record_service or DashboardRecordService(db)
        self.repo = ReportRepository(db)
        self.actions = ActionRepository(db)
        self.plans = PlanningRepository(db)
        performance_repo = PerformanceRepository(db, ORMPerformanceRecord)
        self.insights = InsightsService(
            performance_repo,
            PlanningService(performance_repo, db=db),
            db=db,
            record_service=self.records,
        )
        self.evidence = ReportingEvidenceService()

    def ensure_system_templates(self) -> None:
        changed = False
        for item in SYSTEM_TEMPLATES:
            version = int(item.get("version", 1))
            if self.repo.get_template_key_version(item["template_key"], version): continue
            definition = ReportTemplateDefinition.model_validate(item["definition"])
            issues = validate_definition(definition)
            if any(issue["severity"] == "error" for issue in issues):
                raise StoryValidationError(f"Invalid system template {item['template_key']}: {issues[0]['message']}")
            self.repo.add_template(ReportTemplate(
                name=item["name"], template_key=item["template_key"], report_type=item["report_type"],
                description=item["description"], owner_user_id=None, visibility="organization", version=version,
                definition_json=definition.model_dump(mode="json"), theme_key=definition.theme_key,
                language=definition.language, preferred_format="pdf", is_system_template=True,
            )); changed = True
        if changed:
            try: self.db.commit()
            except Exception: self.db.rollback(); raise

    @staticmethod
    def registries(scope: dict | None = None) -> dict[str, Any]:
        blocks = public_block_registry()
        if scope:
            permissions = set(PERMISSION_MATRIX.get(str(scope.get("role")), []))
            for block in blocks:
                missing = [permission for permission in block.get("permissions", []) if scope.get("role") != "Admin" and permission not in permissions]
                block["available"] = not missing
                block["unavailable_reason"] = f"Requires {', '.join(missing)} permission" if missing else None
        return {"blocks": blocks, "layouts": public_layout_registry(), "categories": ["All", "Executive Summary", "Performance", "Teams & People", "Insights & Drivers", "Actions & Planning", "Narrative", "Data Quality"]}

    def _template_access(self, template: ReportTemplate, scope: dict, *, edit: bool = False) -> None:
        if template.is_system_template and not edit: return
        if template.visibility == "organization" and not edit: return
        if str(template.owner_user_id) != str(scope.get("user_id")) and scope.get("role") != "Admin":
            raise StoryAccessError("This report template belongs to another user")
        if edit and template.is_system_template:
            raise StoryAccessError("System templates cannot be modified")

    def list_templates(self, scope: dict) -> list[dict[str, Any]]:
        self.ensure_system_templates()
        user_id = _safe_uuid(scope.get("user_id"))
        visible = [row for row in self.repo.list_templates(user_id) if self._template_visible(row, scope)]
        latest_by_key: dict[str, ReportTemplate] = {}
        for row in visible:
            if row.template_key not in latest_by_key or row.version > latest_by_key[row.template_key].version:
                latest_by_key[row.template_key] = row
        templates = [self._serialize_template(row) for row in latest_by_key.values()]
        return sorted(
            templates,
            key=lambda item: (
                not bool(item["definition"].get("story_metadata", {}).get("recommended")),
                {"full": 0, "compact": 1}.get(item["definition"].get("story_metadata", {}).get("mode"), 2),
                item["name"],
            ),
        )

    def _template_visible(self, row, scope):
        try: self._template_access(row, scope); return True
        except StoryAccessError: return False

    @staticmethod
    def _serialize_template(row: ReportTemplate) -> dict[str, Any]:
        definition = ReportTemplateDefinition.model_validate(row.definition_json)
        return {"id": str(row.id), "name": row.name, "template_key": row.template_key, "report_type": row.report_type, "description": row.description, "visibility": row.visibility, "version": row.version, "definition": definition.model_dump(mode="json"), "theme_key": row.theme_key, "language": row.language, "preferred_format": row.preferred_format, "is_system_template": row.is_system_template, "updated_at": row.updated_at.isoformat() if row.updated_at else None, "page_count": len(definition.slides)}

    def get_template(self, template_id: str, scope: dict) -> dict[str, Any]:
        row = self._get_template(template_id); self._template_access(row, scope); return self._serialize_template(row)

    def _get_template(self, template_id: str) -> ReportTemplate:
        try: parsed = uuid.UUID(template_id)
        except ValueError: raise StoryNotFoundError("Report template was not found")
        row = self.repo.get_template(parsed)
        if not row: raise StoryNotFoundError("Report template was not found")
        return row

    def create_template(self, payload: ReportTemplateCreate, scope: dict) -> dict[str, Any]:
        if payload.visibility == "organization" and scope.get("role") != "Admin":
            raise StoryAccessError("Only administrators can publish organization templates")
        issues = validate_definition(payload.definition)
        if any(issue["severity"] == "error" for issue in issues): raise StoryValidationError(issues[0]["message"])
        row = ReportTemplate(name=payload.name, template_key=payload.template_key, report_type=payload.report_type, description=payload.description, owner_user_id=_safe_uuid(scope.get("user_id")), visibility=payload.visibility, version=1, definition_json=payload.definition.model_dump(mode="json"), theme_key=payload.definition.theme_key, language=payload.definition.language, preferred_format=payload.definition.preferred_format, is_system_template=False)
        try: self.repo.add_template(row); self.db.commit(); self.db.refresh(row)
        except IntegrityError as exc: self.db.rollback(); raise StoryValidationError("A template with this key already exists") from exc
        return self._serialize_template(row)

    def update_template(self, template_id: str, payload: ReportTemplateUpdate, scope: dict) -> dict[str, Any]:
        current = self._get_template(template_id); self._template_access(current, scope, edit=True)
        if payload.visibility == "organization" and scope.get("role") != "Admin":
            raise StoryAccessError("Only administrators can publish organization templates")
        latest = self.repo.latest_template_version(current.template_key)
        if payload.expected_version != latest: raise StoryConflictError("A newer template version already exists")
        definition = payload.definition or ReportTemplateDefinition.model_validate(current.definition_json)
        issues = validate_definition(definition)
        if any(issue["severity"] == "error" for issue in issues): raise StoryValidationError(issues[0]["message"])
        row = ReportTemplate(name=payload.name or current.name, template_key=current.template_key, report_type=current.report_type, description=payload.description if payload.description is not None else current.description, owner_user_id=current.owner_user_id, visibility=payload.visibility or current.visibility, version=latest + 1, definition_json=definition.model_dump(mode="json"), theme_key=definition.theme_key, language=definition.language, preferred_format=definition.preferred_format, is_system_template=False)
        try: self.repo.add_template(row); self.db.commit(); self.db.refresh(row)
        except Exception: self.db.rollback(); raise
        return self._serialize_template(row)

    def archive_template(self, template_id: str, scope: dict) -> dict[str, str]:
        row = self._get_template(template_id); self._template_access(row, scope, edit=True)
        self.repo.archive_template_key(row.template_key)
        try: self.db.commit()
        except Exception: self.db.rollback(); raise
        return {"id": str(row.id), "name": row.name}

    def _validate_scope(self, report_scope: ReportScope, scope: dict) -> None:
        if report_scope.team and not user_can_access_team(scope, report_scope.team): raise StoryAccessError("The selected team is outside your authorized reporting scope")
        if report_scope.team and report_scope.performance_level and not user_can_access_team_level(scope, report_scope.team, report_scope.performance_level): raise StoryAccessError("The selected performance level is outside your authorized reporting scope")

    def _authorized_records(self, report_scope: ReportScope, auth_scope: dict) -> list[Any]:
        self._validate_scope(report_scope, auth_scope)
        # Insights owns the existing authorized union of employee analysis rows
        # and management BSC analysis rows. Reuse it instead of rebuilding that
        # union or falling back to the narrower dashboard display path.
        if hasattr(self.insights, "_authorized_records"):
            raw_rows, _missing_year_count = self.insights._authorized_records(auth_scope)
        else:
            analysis_loader = getattr(self.records, "list_analysis_records", None)
            raw_rows = analysis_loader() if analysis_loader else self.records.list_records()
        rows = filter_records_by_team_levels(
            filter_records_by_scope(
                raw_rows,
                auth_scope,
            ),
            auth_scope,
        )
        def matches(record):
            read = record.get if isinstance(record, dict) else lambda key, default=None: getattr(record, key, default)
            values = {key: read(key) for key in ("region", "team", "position", "performance_level", "employee_id", "status")}
            evaluation = read("evaluation")
            grade = evaluation.get("grade") if isinstance(evaluation, dict) else getattr(evaluation, "grade", "")
            if report_scope.grade and str(grade) != report_scope.grade: return False
            return all(not getattr(report_scope, key) or str(value).casefold() == str(getattr(report_scope, key)).casefold() for key, value in values.items())
        return [row for row in rows if matches(row)]

    def _available_departments(self, report_scope: ReportScope, auth_scope: dict, period: ReportPeriod) -> list[str]:
        period_key = (period.year, MONTHS[period.month])
        rows = [row for row in self._authorized_records(report_scope, auth_scope) if _period_key(row) == period_key]
        departments = sorted({str(row.get("team") if isinstance(row, dict) else row.team) for row in rows if (row.get("team") if isinstance(row, dict) else getattr(row, "team", None))})
        if report_scope.team and not departments:
            raise StoryValidationError(f"No performance data is available for {period.month} {period.year} in {report_scope.team}")
        if not departments:
            raise StoryValidationError(f"No performance data is available for {period.month} {period.year} in the authorized scope")
        return [report_scope.team] if report_scope.team else departments

    def _expand_offshore(self, definition: ReportDraftDefinition, departments: list[str]) -> ReportDraftDefinition:
        detail_titles = {"Department Divider", "Department Scorecard", "Actual vs Target", "Grade Distribution", "Employee Performance", "Lowest KPIs and Lost Points", "Root Cause Analysis", "Process and Staff Action Plans", "Feedback Sessions Status"}
        expanded = []
        for slide in definition.slides:
            if slide.title not in detail_titles:
                expanded.append(slide.model_copy(deep=True)); continue
            for department in departments:
                clone = slide.model_copy(deep=True)
                clone.id = f"{slide.id}-{re.sub(r'[^a-z0-9]+', '-', department.casefold()).strip('-')}"
                clone.title = f"{department} - {slide.title}"
                for block in clone.blocks:
                    block.id = f"{block.id}-{re.sub(r'[^a-z0-9]+', '-', department.casefold()).strip('-')}"
                    block.config.scope_override = {"team": department}
                expanded.append(clone)
        for order, slide in enumerate(expanded): slide.order = order
        definition.slides = expanded
        return definition

    def _expand_team_story(self, definition: ReportDraftDefinition, departments: list[str]) -> ReportDraftDefinition:
        repeat_titles = {"Team Performance Review", "Team Snapshot", "Team / Position Deep Dive"}
        expanded = []
        for slide in definition.slides:
            if slide.title not in repeat_titles:
                expanded.append(slide.model_copy(deep=True))
                continue
            for department in departments:
                slug = re.sub(r"[^a-z0-9]+", "-", department.casefold()).strip("-")
                clone = slide.model_copy(deep=True)
                clone.id = f"{slide.id}-{slug}"
                clone.title = f"{department} - {slide.title}"
                for block in clone.blocks:
                    block.id = f"{block.id}-{slug}"
                    block.config.scope_override = {"team": department}
                expanded.append(clone)
        for order, slide in enumerate(expanded):
            slide.order = order
        definition.slides = expanded
        return definition

    @staticmethod
    def _prune_definition_for_permissions(definition: ReportDraftDefinition, scope: dict) -> ReportDraftDefinition:
        if scope.get("role") == "Admin":
            return definition
        permissions = set(PERMISSION_MATRIX.get(str(scope.get("role")), []))
        slides = []
        for slide in definition.slides:
            clone = slide.model_copy(deep=True)
            clone.blocks = [
                block for block in clone.blocks
                if all(permission in permissions for permission in BLOCK_REGISTRY[block.type].get("permissions", []))
            ]
            if clone.blocks:
                slides.append(clone)
        for order, slide in enumerate(slides):
            slide.order = order
        definition.slides = slides
        return definition

    def create_draft(self, payload: ReportDraftCreate, scope: dict) -> dict[str, Any]:
        self._validate_scope(payload.scope, scope)
        template = None
        if payload.template_id:
            template = self._get_template(payload.template_id); self._template_access(template, scope)
            definition = ReportDraftDefinition(**ReportTemplateDefinition.model_validate(template.definition_json).model_dump())
            if template.template_key in {"offshore_monthly_performance_review", "offshore_monthly_executive_brief"}:
                departments = self._available_departments(payload.scope, scope, payload.primary_period)
                if template.template_key == "offshore_monthly_performance_review" and template.version < 2:
                    definition = self._expand_offshore(definition, departments)
                else:
                    definition = self._expand_team_story(definition, departments)
            definition = self._prune_definition_for_permissions(definition, scope)
        else:
            definition = ReportDraftDefinition(slides=[])
        commentary = ManagementCommentary(entries={block.id: "" for slide in definition.slides for block in slide.blocks if block.type == "management_commentary"})
        draft = ReportDraft(name=payload.name, report_type=payload.report_type, template_id=template.id if template else None, template_version=template.version if template else None, owner_user_id=_safe_uuid(scope.get("user_id")), status="editing", primary_period_month=payload.primary_period.month, primary_period_year=payload.primary_period.year, comparison_period_month=payload.comparison_period.month if payload.comparison_period else None, comparison_period_year=payload.comparison_period.year if payload.comparison_period else None, scope_json=payload.scope.model_dump(mode="json"), definition_json=definition.model_dump(mode="json"), management_commentary_json=commentary.model_dump(mode="json"), version=1)
        try: self.repo.add_draft(draft); self.db.flush(); self._regenerate_narratives(draft, scope); self.db.commit(); self.db.refresh(draft)
        except Exception: self.db.rollback(); raise
        return self._serialize_draft(draft)

    def _get_draft(self, draft_id: str, scope: dict, *, edit: bool = False) -> ReportDraft:
        try: parsed = uuid.UUID(draft_id)
        except ValueError: raise StoryNotFoundError("Report draft was not found")
        row = self.repo.get_draft(parsed)
        if not row: raise StoryNotFoundError("Report draft was not found")
        if str(row.owner_user_id) != str(scope.get("user_id")) and scope.get("role") != "Admin": raise StoryAccessError("This report draft belongs to another user")
        self._validate_scope(ReportScope.model_validate(row.scope_json), scope)
        if edit and row.status == "generated": raise StoryValidationError("Generated drafts are immutable; duplicate the report for a new period")
        return row

    def _serialize_draft(self, row: ReportDraft) -> dict[str, Any]:
        definition = ReportDraftDefinition.model_validate(row.definition_json)
        return {"id": str(row.id), "name": row.name, "report_type": row.report_type, "template_id": str(row.template_id) if row.template_id else None, "template_version": row.template_version, "owner_user_id": str(row.owner_user_id), "status": row.status, "primary_period": {"month": row.primary_period_month, "year": row.primary_period_year}, "comparison_period": {"month": row.comparison_period_month, "year": row.comparison_period_year} if row.comparison_period_month else None, "scope": row.scope_json, "definition": definition.model_dump(mode="json"), "management_commentary": ManagementCommentary.model_validate(row.management_commentary_json or {}).model_dump(mode="json"), "validation": row.validation_json, "version": row.version, "last_saved_at": row.last_saved_at.isoformat() if row.last_saved_at else None, "updated_at": row.updated_at.isoformat() if row.updated_at else None}

    def get_draft(self, draft_id: str, scope: dict) -> dict[str, Any]: return self._serialize_draft(self._get_draft(draft_id, scope))

    def list_drafts(self, scope: dict) -> list[dict[str, Any]]:
        user_id = _safe_uuid(scope.get("user_id"))
        rows = self.repo.list_drafts(user_id) if user_id else []
        return [self._serialize_draft(row) for row in rows]

    def archive_draft(self, draft_id: str, scope: dict) -> dict[str, str]:
        row = self._get_draft(draft_id, scope, edit=True)
        result = {"id": str(row.id), "name": row.name}
        row.status = "archived"
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return result

    def update_draft(self, draft_id: str, payload: ReportDraftUpdate, scope: dict) -> dict[str, Any]:
        row = self._get_draft(draft_id, scope, edit=True)
        values: dict[str, Any] = {"last_saved_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
        if payload.name is not None: values["name"] = payload.name
        if payload.definition is not None:
            issues = validate_definition(payload.definition)
            if any(issue["severity"] == "error" for issue in issues): raise StoryValidationError(issues[0]["message"])
            values["definition_json"] = payload.definition.model_dump(mode="json")
        if payload.management_commentary is not None: values["management_commentary_json"] = payload.management_commentary.model_dump(mode="json")
        try:
            if not self.repo.update_draft_versioned(row.id, payload.expected_version, values): self.db.rollback(); raise StoryConflictError("This draft was updated elsewhere. Reload before saving again")
            self.db.commit(); self.db.expire_all()
        except StoryConflictError: raise
        except Exception: self.db.rollback(); raise
        return self._serialize_draft(self._get_draft(draft_id, scope))

    def _context(
        self,
        draft: ReportDraft,
        auth_scope: dict,
        override: dict[str, str] | None = None,
        *,
        include_actions: bool = False,
        include_plans: bool = False,
        include_uploads: bool = False,
        action_evidence_authorized: bool = False,
        authorized_records: list[Any] | None = None,
    ) -> dict[str, Any]:
        scope_data = dict(draft.scope_json or {}); scope_data.update(override or {})
        report_scope = ReportScope.model_validate(scope_data)
        all_rows = authorized_records if authorized_records is not None else self._authorized_records(report_scope, auth_scope)
        primary = (draft.primary_period_year, MONTHS[draft.primary_period_month])
        # Reporting comparison is always the immediately preceding calendar month.
        # A missing adjacent month is explicitly unavailable; never jump backwards.
        comparison = previous_calendar_period(primary)
        current = [row for row in all_rows if _period_key(row) == primary]
        previous = [row for row in all_rows if comparison and _period_key(row) == comparison]
        actions = [
            action for action in self._authorized_actions(report_scope, auth_scope)
            if (action.year, MONTHS.get(action.month)) == primary
        ] if include_actions else []
        uploads = [upload for upload in self.repo.list_upload_logs() if (upload.year, MONTHS.get(upload.month)) in {primary, comparison}] if include_uploads else []
        uploads = [upload for upload in uploads if user_can_access_team(auth_scope, logical_team_name(upload.team)) and (not report_scope.team or logical_team_name(upload.team).casefold() == report_scope.team.casefold()) and (not report_scope.region or str(upload.team.region).casefold() == report_scope.region.casefold())]
        evidence = self.evidence.build(
            all_rows,
            primary,
            actions if action_evidence_authorized else None,
            action_evidence_authorized=action_evidence_authorized,
        )
        return {
            "scope": report_scope,
            "auth_scope": auth_scope,
            "all": all_rows,
            "current": current,
            "previous": previous,
            "primary": primary,
            "comparison": comparison,
            "actions": actions,
            "plans": self._authorized_plans(report_scope, auth_scope) if include_plans else [],
            "uploads": uploads,
            "action_evidence_authorized": action_evidence_authorized,
            "evidence": evidence,
        }

    def _authorized_actions(self, report_scope: ReportScope, auth_scope: dict):
        rows = []
        for action in self.actions.list_active():
            team = logical_team_name(action.team)
            if report_scope.region and str(action.team.region).casefold() != report_scope.region.casefold(): continue
            if report_scope.team and team.casefold() != report_scope.team.casefold(): continue
            if report_scope.employee_id and (not action.employee or str(action.employee.employee_id) != report_scope.employee_id): continue
            if auth_scope.get("role") != "Admin" and not user_can_access_team(auth_scope, team): continue
            rows.append(action)
        return rows

    def _authorized_plans(self, report_scope: ReportScope, auth_scope: dict):
        rows = []
        for plan in self.plans.list_active():
            team = logical_team_name(plan.team)
            if report_scope.region and str(plan.region or plan.team.region).casefold() != report_scope.region.casefold(): continue
            if report_scope.team and team.casefold() != report_scope.team.casefold(): continue
            if auth_scope.get("role") != "Admin" and not user_can_access_team_level(auth_scope, team, plan.performance_level): continue
            rows.append(plan)
        return rows

    @staticmethod
    def _period_label(value) -> str | None:
        return f"{MONTH_NAMES[value[1]]} {value[0]}" if value else None

    def _summary(self, ctx) -> dict[str, Any]:
        return ctx["evidence"]["summary"]

    def _insights_workspace(self, ctx):
        filters = {
            key: value for key, value in ctx["scope"].model_dump(mode="json").items()
            if key in {"region", "team", "performance_level", "position", "employee_id", "status"} and value
        }
        return self.insights.generate_workspace(
            ctx["auth_scope"],
            month=MONTH_NAMES[ctx["primary"][1]],
            year=ctx["primary"][0],
            **filters,
        )

    def _team_overview_data(self, ctx, summary: dict[str, Any], kpis: list[dict[str, Any]]) -> dict[str, Any]:
        grade_counts = Counter(str(row.evaluation.grade) for row in ctx["current"])
        weighted = [item for item in kpis if item.get("weight") not in {None, 0}]
        return {
            "metrics": [
                {"label": "Team Score", "value": summary["average_score"], "display": f"{summary['average_score']:.1f}%" if summary["average_score"] is not None else "N/A", "change_display": f"{summary['score_change']:+.1f}%" if summary["score_change"] is not None else None, "movement": "positive" if (summary["score_change"] or 0) >= 0 else "negative"},
                {"label": "Employees", "value": summary["total_employees"], "display": summary["total_employees"]},
                {"label": "Below Target", "value": summary["employees_below_target"], "display": summary["employees_below_target"]},
                {"label": "Weighted KPIs", "value": len(weighted), "display": len(weighted)},
            ],
            "series": [{"label": f"Grade {grade}", "value": count} for grade, count in sorted(grade_counts.items())],
            "rows": [
                {"kpi": item["name"], "actual": item["actual"], "target": item["target"], "achievement": item["achievement"], "status": item["status"]}
                for item in weighted[:4]
            ],
        }

    def _actions_summary_data(self, ctx) -> dict[str, Any]:
        actions = ctx["actions"]
        employees = {str(action.employee.employee_id) for action in actions if action.employee}
        open_actions = [action for action in actions if str(action.status).casefold() not in {"completed", "cancelled"}]
        high_priority = [action for action in open_actions if str(action.priority or "").casefold() == "high"]
        types = Counter(str(action.action_type or "Unspecified") for action in actions)
        causes = Counter(self._issue_category(f"{action.action_type} {action.action_text} {action.root_cause_note or ''}") for action in actions)
        return {
            "metrics": [
                {"label": "Actions This Month", "value": len(actions), "display": len(actions)},
                {"label": "Employees Actioned", "value": len(employees), "display": len(employees)},
                {"label": "Open Actions", "value": len(open_actions), "display": len(open_actions)},
                {"label": "High Priority", "value": len(high_priority), "display": len(high_priority)},
            ],
            "series": [{"label": label, "value": value} for label, value in types.most_common(6)],
            "rows": [{"root_cause_group": label, "actions": value} for label, value in causes.most_common(5)],
        }

    @staticmethod
    def _insight_rows(items) -> list[dict[str, Any]]:
        return [
            {
                "severity": item.severity,
                "insight": item.title,
                "impact": item.impact_points,
                "trend": item.trend_label,
                "recommended_focus": item.detail.recommended_focus,
            }
            for item in items
        ]

    @staticmethod
    def _is_below(record) -> bool:
        return ReportingEvidenceService().is_below_target(record)

    def _kpis(self, ctx) -> list[dict[str, Any]]:
        return ctx["evidence"]["kpis"]

    def _movement(self, ctx, kpis) -> dict[str, Any]:
        movement = dict(ctx["evidence"]["movement"])
        items = [{"label": item["label"], "impact": item["score_point_change"], "display": f"{item['score_point_change']:+.1f} score points"} for item in movement["kpi_contribution_movements"]]
        delta = movement["total_score_point_change"]
        if delta is None:
            narrative = "Previous-calendar-month comparison is unavailable."
        else:
            direction = "increased" if delta > 0 else "declined" if delta < 0 else "was unchanged"
            narrative = f"Overall PMS Score {direction} by {abs(delta):.1f} score points. Measured KPI contribution and population effects produce a {movement['reconciliation_state']} matched-cohort bridge with a {movement['residual']:+.1f} score-point residual."
        movement.update({"score_change": delta, "contributions": items, "reconciled_total": round(delta - movement["residual"], 2) if delta is not None else None, "is_exact": movement["reconciliation_state"] == "reconciled", "narrative": narrative})
        return movement

    def _people(self, ctx, lowest=True) -> list[dict[str, Any]]:
        previous = {str(row.employee_id): row for row in ctx["previous"]}; actions = defaultdict(list)
        for action in ctx["actions"]:
            if action.employee: actions[str(action.employee.employee_id)].append(action)
        rows = []
        for record in ctx["current"]:
            score = _score(record)
            if score is None: continue
            employee_id = str(record.employee_id); prior = _score(previous.get(employee_id)) if employee_id in previous else None
            kpis = sorted(record.kpi_values or [], key=lambda value: (_number(value.get("achievement_ratio")) if _number(value.get("achievement_ratio")) is not None else 999))
            linked = actions[employee_id]; feedback = self._feedback_status(linked)
            rows.append({"employee": record.employee_name, "employee_id": employee_id, "team": record.team, "current_score": score, "previous_score": prior, "change": round(score-prior, 2) if prior is not None else None, "grade": record.evaluation.grade, "lowest_kpi": (kpis[0].get("label") or kpis[0].get("kpi_key")) if kpis else "N/A", "main_gap": getattr(getattr(record.evaluation, "root_cause", None), "kpi", None) or "Requires confirmation", "corrective_action_status": linked[0].status if linked else "No action", "feedback_status": feedback, "is_below": self._is_below(record)})
        return sorted(rows, key=lambda item: item["current_score"], reverse=not lowest)

    @staticmethod
    def _feedback_status(actions) -> str:
        sessions = [action for action in actions if any(token in str(action.action_type).casefold() for token in ["feedback", "coaching", "pip", "training", "review"])]
        if not sessions: return "Not Scheduled"
        action = sessions[0]; status = str(action.status).casefold()
        if status == "completed": return "Completed"
        if status == "cancelled": return "Cancelled"
        if action.due_date and action.due_date < date.today(): return "Overdue"
        if action.due_date: return "Scheduled"
        return "Follow-up Required"

    def _consecutive_low(self, ctx) -> list[dict[str, Any]]:
        primary = ReportPeriod(year=ctx["primary"][0], month=MONTH_NAMES[ctx["primary"][1]])
        periods = [_previous_period(primary, 2), _previous_period(primary, 1), primary]; keys = [(p.year, MONTHS[p.month]) for p in periods]
        by_employee: dict[str, dict[tuple[int, int], Any]] = defaultdict(dict)
        for row in ctx["all"]:
            if _period_key(row) in keys: by_employee[str(row.employee_id)][_period_key(row)] = row
        rows = []
        for employee_id, history in by_employee.items():
            if any(key not in history for key in keys): continue
            records = [history[key] for key in keys]
            if not all(self._is_below(record) for record in records): continue
            scores = [_score(record) for record in records]
            if any(value is None for value in scores): continue
            weakest = Counter((min(record.kpi_values or [], key=lambda value: _number(value.get("achievement_ratio")) if _number(value.get("achievement_ratio")) is not None else 999).get("label") if record.kpi_values else "N/A") for record in records)
            related_actions = [action for action in ctx["actions"] if action.employee and str(action.employee.employee_id) == employee_id]
            rows.append({"employee": records[-1].employee_name, "team": records[-1].team, periods[0].month: scores[0], periods[1].month: scores[1], periods[2].month: scores[2], "three_month_average": round(sum(scores)/3, 2), "trend": round(scores[-1]-scores[0], 2), "repeated_weakest_kpi": weakest.most_common(1)[0][0], "action_status": related_actions[0].status if related_actions else "No action", "feedback_status": self._feedback_status(related_actions), "recommended_escalation": "Manager review and quantified intervention required"})
        return sorted(rows, key=lambda item: (item["three_month_average"], item["trend"]))

    def _root_causes(self, ctx) -> list[dict[str, Any]]:
        rows = []
        for action in ctx["actions"]:
            if action.root_cause_note:
                text = action.root_cause_note; category = self._issue_category(f"{action.action_type} {text}")
                rows.append({"classification": "Likely Root Cause", "confidence": "likely", "category": category, "scope": logical_team_name(action.team), "evidence": text, "source": "Corrective action record; no persisted confirmation evidence"})
        for record in ctx["current"]:
            cause = getattr(record.evaluation, "root_cause", None)
            if cause:
                text = f"{getattr(cause, 'kpi', 'KPI')} is associated with a measured performance gap."
                rows.append({"classification": "Likely Contributing Factor", "confidence": "likely", "category": self._issue_category(text), "scope": f"{record.team} - {record.employee_name}", "evidence": text, "source": "Measured performance pattern; requires confirmation"})
            for value in record.kpi_values or []:
                if _number(value.get("target_value")) in {None, 0}: rows.append({"classification": "Data Issue", "confidence": "configuration_requires_review", "category": "Data/Configuration", "scope": record.team, "evidence": f"{value.get('label') or value.get('kpi_key')} has a missing or zero target.", "source": "KPI configuration"})
        unique = []; seen = set()
        for row in rows:
            key = tuple(row.values())
            if key not in seen: seen.add(key); unique.append(row)
        return unique[:20]

    @staticmethod
    def _issue_category(text: str) -> str:
        lowered = text.casefold(); process = any(value in lowered for value in ["system", "process", "workflow", "routing", "sop", "target", "access", "schedule"]); staff = any(value in lowered for value in ["attendance", "coaching", "training", "agent", "employee", "adherence", "quality"])
        return "Both" if process and staff else "Process" if process else "Staff" if staff else "Requires confirmation"

    def _serialize_actions(self, ctx, category: str | None = None) -> list[dict[str, Any]]:
        rows = []
        for action in ctx["actions"]:
            action_category = self._issue_category(f"{action.action_type} {action.action_text} {action.root_cause_note or ''}")
            if category and action_category not in {category, "Both"}: continue
            plan = action.plan
            baseline = _number(plan.baseline_value) if plan else None; target = _number(plan.target_value) if plan else None; impact = _number(plan.expected_impact) if plan else None
            quantified = bool(baseline is not None and target is not None and action.owner and action.due_date and plan and getattr(plan, "kpis", []))
            if not quantified: impact = None
            assumptions = "Projected impact is the stored expected-impact value from the linked performance plan; it is not guaranteed" if impact is not None else "Projected score impact is unavailable; baseline, target, owner, due date and measurement criteria are required"
            milestones = sorted((plan.milestones if plan else []), key=lambda item: item.due_date)
            next_review = next((item.due_date for item in milestones if item.status != "Completed"), None)
            vague = action.action_text.strip().casefold().rstrip(".") in {"improve performance", "increase performance", "monitor performance", "take action"} or len(action.action_text.strip()) < 20
            validation = [message for condition, message in [(not action.owner, "Owner is required"), (not action.due_date, "Due date is required"), (baseline is None or target is None, "Baseline and quantified target are required"), (vague, "Action statement is too vague"), (plan is not None and not milestones, "Review frequency is not represented by plan milestones")] if condition]
            rows.append({"problem": action.root_cause_note or action.action_text, "scope": logical_team_name(action.team), "linked_kpi_or_employee": action.linked_kpi_key or (action.employee.name if action.employee else "Team"), "baseline": baseline, "target": target, "unit": plan.outcome_unit if plan else None, "expected_change": round(target-baseline, 2) if quantified else None, "quantified_action_plan": quantified, "completed_management_intervention": quantified and action.status == "Completed" and bool(action.completion_note or action.evidence_reference), "projected_score_impact": impact, "projection_assumptions": assumptions, "owner": action.owner.username if action.owner else None, "start_date": plan.period_start.isoformat() if plan else action.created_at.date().isoformat() if action.created_at else None, "due_date": action.due_date.isoformat() if action.due_date else None, "status": action.status, "priority": action.priority, "review_date": next_review.isoformat() if next_review else action.due_date.isoformat() if action.due_date else None, "review_frequency": "Plan milestone cadence" if milestones else None, "evidence": action.evidence_reference, "completion_note": action.completion_note, "actual_result": _number(plan.actual_impact) if quantified and plan else None, "validation": validation})
        return rows

    def _feedback(self, ctx) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows = []
        current_low = {str(row.employee_id): row for row in ctx["current"] if self._is_below(row)}
        actions_by_employee = defaultdict(list)
        for action in ctx["actions"]:
            if action.employee: actions_by_employee[str(action.employee.employee_id)].append(action)
        for employee_id, record in current_low.items():
            sessions = [action for action in actions_by_employee[employee_id] if any(token in str(action.action_type).casefold() for token in ["feedback", "coaching", "pip", "training", "review"])]
            action = sessions[0] if sessions else None; status = self._feedback_status(actions_by_employee[employee_id])
            rows.append({"employee": record.employee_name, "department": record.team, "session_type": action.action_type if action else "Not recorded", "session_owner": action.owner.username if action and action.owner else None, "scheduled_date": action.due_date.isoformat() if action and action.due_date else None, "completion_date": action.updated_at.date().isoformat() if action and status == "Completed" and action.updated_at else None, "status": status, "linked_issue": action.linked_kpi_key if action else getattr(getattr(record.evaluation, "root_cause", None), "kpi", None), "agreed_actions": action.action_text if action else None, "next_follow_up_date": action.due_date.isoformat() if action and status == "Follow-up Required" and action.due_date else None, "outcome_note": action.completion_note if action else None})
        counts = Counter(row["status"] for row in rows); completed = counts["Completed"]
        return rows, {"total_required": len(rows), "completed": completed, "scheduled": counts["Scheduled"], "overdue": counts["Overdue"], "completion_rate": round(completed/len(rows)*100, 1) if rows else None}

    def _resolve_provider(self, provider: str, ctx, block, draft) -> BlockDataResult:
        summary = self._summary(ctx); kpis = self._kpis(ctx); warnings = []
        if provider == "cover": data = {"narrative": f"{draft.name} - {self._period_label(ctx['primary'])} compared with {self._period_label(ctx['comparison']) or 'no comparison period'}"}
        elif provider == "agenda": data = {"rows": [{"page": slide.order + 1, "title": slide.title} for slide in ReportDraftDefinition.model_validate(draft.definition_json).slides]}
        elif provider == "summary":
            data = {"metrics": [{"label": "Overall PMS Score", "value": summary["average_score"], "display": f"{summary['average_score']:.1f}%" if summary["average_score"] is not None else "N/A", "change_display": f"{summary['score_change']:+.1f}%" if summary["score_change"] is not None else None, "movement": "positive" if (summary["score_change"] or 0) >= 0 else "negative"}, {"label": "Employees", "value": summary["total_employees"], "display": summary["total_employees"]}, {"label": "Below Target", "value": summary["employees_below_target"], "display": summary["employees_below_target"]}, {"label": "Critical Risks", "value": summary["critical_risks"], "display": summary["critical_risks"]}]}
        elif provider == "team_overview":
            data = self._team_overview_data(ctx, summary, kpis)
        elif provider in {"team_analysis", "insights_summary", "team_risk_matrix"}:
            workspace = self._insights_workspace(ctx)
            if provider == "team_risk_matrix":
                data = {"rows": [item.model_dump(mode="json") for item in workspace.team_summaries]}
            else:
                insight_items = workspace.team_analyses if provider == "team_analysis" else workspace.priority_insights
                insight_rows = self._insight_rows(insight_items[:block.config.row_limit])
                top = insight_items[0] if insight_items else None
                data = {"rows": insight_rows, "narrative": top.explanation if top else "No material insight is available for this scope and period."}
                if provider == "insights_summary":
                    data["metrics"] = [
                        {"label": "Critical Issues", "value": workspace.summary.critical_issues, "display": workspace.summary.critical_issues},
                        {"label": "At Risk", "value": workspace.summary.at_risk, "display": workspace.summary.at_risk},
                        {"label": "Positive Drivers", "value": workspace.summary.positive_weighted_drivers, "display": workspace.summary.positive_weighted_drivers},
                        {"label": "Analysis Coverage", "value": workspace.summary.coverage_percent, "display": f"{workspace.summary.coverage_percent:.0f}%" if workspace.summary.coverage_percent is not None else "N/A"},
                    ]
        elif provider == "actions_summary":
            data = self._actions_summary_data(ctx)
        elif provider == "score_comparison": data = {"items": [{"label": self._period_label(ctx["comparison"]) or "Comparison unavailable", "state": "ready" if summary["previous_score"] is not None else "comparison_unavailable", "value": summary["previous_score"], "display": f"{summary['previous_score']:.1f}%" if summary["previous_score"] is not None else "N/A"}, {"label": self._period_label(ctx["primary"]), "state": "ready" if summary["average_score"] is not None else "unavailable", "value": summary["average_score"], "display": f"{summary['average_score']:.1f}%" if summary["average_score"] is not None else "N/A"}], "narrative": self._movement(ctx, kpis)["narrative"]}
        elif provider == "trend": data = ctx["evidence"]["trend"]
        elif provider == "grade_distribution": data = {"series": [{"label": key, "value": value} for key, value in sorted(ctx["evidence"]["grade_distribution"].items())]}
        elif provider in {"team_ranking", "position_ranking"}:
            key = "team" if provider == "team_ranking" else "position"; grouped = defaultdict(list)
            for row in ctx["current"]:
                if _score(row) is not None: grouped[str(getattr(row, key, None) or "Unspecified")].append(_score(row))
            data = {"rows": [{key: label, "average_score": round(sum(values)/len(values), 2), "employees": len(values)} for label, values in sorted(grouped.items(), key=lambda item: sum(item[1])/len(item[1]), reverse=True)]}
        elif provider == "kpi": data = {"rows": kpis}
        elif provider in {"drivers", "movement"}: movement = self._movement(ctx, kpis); data = {"items": movement["contributions"], "narrative": movement["narrative"], "reconciliation": movement}
        elif provider == "lowest_kpis": data = {"rows": kpis}
        elif provider in {
            "overall_score_movement_bridge", "lowest_kpis_weighted_impact",
            "lowest_employees_current_period", "three_month_consecutive_low_performers",
            "applied_configuration_audit", "root_cause_evidence_matrix",
        }:
            data = MANAGEMENT_BLOCK_CONTRACTS[provider].model_validate(ctx["evidence"][provider]).model_dump(mode="json")
        elif provider in {"top_people", "bottom_people", "lowest_people", "below_target", "employee_table"}:
            rankings = ctx["evidence"]["rankings"]
            if provider == "top_people": people = rankings["top"]
            elif provider in {"bottom_people", "lowest_people"}: people = rankings["bottom"]
            elif provider == "below_target": people = [row for row in rankings["all"] if row["is_below"]]
            else: people = rankings["all"]
            data = {"rows": people}
        elif provider == "consecutive_low": data = {"rows": self._consecutive_low(ctx)}
        elif provider in {"root_causes", "process_issues", "staff_issues"}:
            rows = self._root_causes(ctx)
            if provider == "process_issues": rows = [row for row in rows if row["category"] in {"Process", "Both"}]
            elif provider == "staff_issues": rows = [row for row in rows if row["category"] in {"Staff", "Both"}]
            data = {"rows": rows}
        elif provider in {"actions", "process_actions", "staff_actions"}: data = {"rows": self._serialize_actions(ctx, "Process" if provider == "process_actions" else "Staff" if provider == "staff_actions" else None)}
        elif provider == "feedback": rows, counts = self._feedback(ctx); data = {"rows": rows, "metrics": [{"label": key.replace("_", " ").title(), "display": f"{value}%" if key == "completion_rate" and value is not None else value, "value": value} for key, value in counts.items()]}
        elif provider in {"plans", "at_risk_plans", "milestones"}:
            if provider == "milestones":
                today = date.today()
                rows = [{"milestone": milestone.name, "plan": plan.name, "owner": milestone.owner.username if milestone.owner else None, "due_date": milestone.due_date.isoformat(), "completion_date": milestone.completion_date.isoformat() if milestone.completion_date else None, "status": milestone.status, "overdue": milestone.status != "Completed" and milestone.due_date < today} for plan in ctx["plans"] for milestone in plan.milestones]
            else:
                rows = [{"plan": plan.name, "team": logical_team_name(plan.team), "status": plan.status, "owner": plan.owner.username, "due_date": plan.due_date.isoformat()} for plan in ctx["plans"] if provider != "at_risk_plans" or plan.status == "At Risk"]
            data = {"rows": rows}
        elif provider == "actions_by_owner": data = {"series": [{"label": key, "value": value} for key, value in Counter(action.owner.username if action.owner else "Unassigned" for action in ctx["actions"]).items()]}
        elif provider in {"narrative", "recommendations", "decisions"}:
            stored = ReportDraftDefinition.model_validate(draft.definition_json).narratives.get(block.id)
            data = {"narrative": stored.text if stored else (self._movement(ctx, kpis)["narrative"] if provider == "narrative" else self._recommendations(kpis, provider))}
        elif provider == "commentary":
            commentary = ManagementCommentary.model_validate(draft.management_commentary_json or {}).entries.get(block.id, "").strip()
            data = {"narrative": commentary or "Management commentary has not been entered."}
        elif provider in {"data_quality", "upload_errors"}:
            zero_targets = [item for item in kpis if item["target"] in {None, 0}]
            upload_rows = [{"team": logical_team_name(upload.team), "period": f"{upload.month} {upload.year}", "records": upload.record_count, "status": upload.status, "error": upload.error_message or ""} for upload in ctx["uploads"]]
            errors = [row for row in upload_rows if row["error"] or str(row["status"]).casefold() not in {"success", "completed"}]
            if block.type == "upload_error_table": rows = errors
            elif block.type == "missing_period_data": rows = [] if ctx["current"] and (ctx["previous"] or not ctx["comparison"]) else [{"issue": "Missing primary period" if not ctx["current"] else "Missing comparison period"}]
            else: rows = zero_targets
            data = {"metrics": [{"label": "Primary Records", "value": len(ctx["current"]), "display": len(ctx["current"])}, {"label": "Comparison Records", "value": len(ctx["previous"]), "display": len(ctx["previous"])}, {"label": "Upload Errors", "value": len(errors), "display": len(errors)}, {"label": "Invalid Targets", "value": len(zero_targets), "display": len(zero_targets)}], "rows": rows}
        else: data = {}
        if isinstance(data.get("rows"), list):
            total_rows = len(data["rows"])
            row_limit = 18 if provider == "agenda" else block.config.row_limit
            data["rows"] = data["rows"][:row_limit]
            data["row_summary"] = {"shown": len(data["rows"]), "total": total_rows}
        warnings.extend(ctx["evidence"].get("warnings", []))
        if not ctx["previous"] and provider in {"score_comparison", "movement", "drivers"}: warnings.append("Previous-calendar-month comparison is unavailable.")
        meaningful = any(value not in (None, [], {}, "") for value in data.values())
        independent = {"cover", "agenda", "commentary", "actions", "actions_summary", "process_actions", "staff_actions", "process_issues", "staff_issues", "feedback", "plans", "at_risk_plans", "milestones", "actions_by_owner", "data_quality", "upload_errors"}
        state = "ready" if meaningful and (ctx["current"] or provider in independent) else "no_data"
        if state == "no_data": warnings.append(f"No performance data is available for {self._period_label(ctx['primary'])} in this scope.")
        return BlockDataResult(block_id=block.id, block_type=block.type, state=state, data=data, warnings=warnings, source_periods=[value for value in [self._period_label(ctx["primary"]), self._period_label(ctx["comparison"])] if value])

    @staticmethod
    def _recommendations(kpis, provider):
        material = [item for item in kpis if item["status"] == "below target"][:3]
        if not material: return "No material below-target KPI requires a management decision in this scope."
        prefix = "Management decision required:" if provider == "decisions" else "Recommended focus:"
        return prefix + " " + "; ".join(f"{item['name']} ({item['lost_points'] if item['lost_points'] is not None else 'unquantified'} lost points)" for item in material) + "."

    def resolve_slide(self, draft_id: str, slide_id: str, scope: dict, *, _context_cache: dict[str, Any] | None = None) -> dict[str, Any]:
        draft = self._get_draft(draft_id, scope); definition = ReportDraftDefinition.model_validate(draft.definition_json)
        slide = next((item for item in definition.slides if item.id == slide_id), None)
        if not slide: raise StoryNotFoundError("Report page was not found")
        permissions = set(PERMISSION_MATRIX.get(str(scope.get("role")), [])); cache = _context_cache if _context_cache is not None else {}; results = {}
        for block in slide.blocks:
            registry = BLOCK_REGISTRY[block.type]
            if scope.get("role") != "Admin" and any(permission not in permissions for permission in registry.get("permissions", [])):
                results[block.id] = BlockDataResult(block_id=block.id, block_type=block.type, state="permission_denied", warnings=["You do not have permission to resolve this report block"]); continue
            provider = registry["provider"]
            actions_requested = provider in {
                "summary", "bottom_people", "lowest_people", "below_target", "employee_table",
                "consecutive_low", "root_causes", "actions", "actions_summary", "process_actions",
                "staff_actions", "process_issues", "staff_issues", "feedback", "actions_by_owner",
                "lowest_employees_current_period", "three_month_consecutive_low_performers", "root_cause_evidence_matrix",
            }
            action_evidence_authorized = scope.get("role") == "Admin" or "view_actions" in permissions
            include_actions = actions_requested and action_evidence_authorized
            include_plans = provider in {"plans", "at_risk_plans", "milestones"}
            include_uploads = provider in {"data_quality", "upload_errors"}
            cache_key = (
                f"{json.dumps(block.config.scope_override, sort_keys=True)}:"
                f"{include_actions}:{include_plans}:{include_uploads}:{action_evidence_authorized}"
            )
            if cache_key not in cache:
                record_cache_key = f"records:{json.dumps(block.config.scope_override, sort_keys=True)}"
                if record_cache_key not in cache:
                    scoped = dict(draft.scope_json or {})
                    scoped.update(block.config.scope_override)
                    cache[record_cache_key] = self._authorized_records(ReportScope.model_validate(scoped), scope)
                cache[cache_key] = self._context(
                    draft,
                    scope,
                    block.config.scope_override,
                    include_actions=include_actions,
                    include_plans=include_plans,
                    include_uploads=include_uploads,
                    action_evidence_authorized=action_evidence_authorized and actions_requested,
                    authorized_records=cache[record_cache_key],
                )
            results[block.id] = self._resolve_provider(registry["provider"], cache[cache_key], block, draft)
        return SlideDataResult(slide_id=slide.id, blocks=results, resolved_at=datetime.now(timezone.utc).isoformat()).model_dump(mode="json")

    def _regenerate_narratives(self, draft: ReportDraft, scope: dict, slide_id: str | None = None) -> None:
        definition = ReportDraftDefinition.model_validate(draft.definition_json)
        for slide in definition.slides:
            if slide_id and slide.id != slide_id: continue
            narrative_blocks = [block for block in slide.blocks if BLOCK_REGISTRY[block.type]["provider"] in {"narrative", "recommendations", "decisions"}]
            if not narrative_blocks: continue
            ctx = self._context(draft, scope, narrative_blocks[0].config.scope_override); kpis = self._kpis(ctx)
            for block in narrative_blocks:
                text = self._movement(ctx, kpis)["narrative"] if BLOCK_REGISTRY[block.type]["provider"] == "narrative" else self._recommendations(kpis, BLOCK_REGISTRY[block.type]["provider"])
                definition.narratives[block.id] = GeneratedNarrative(block_id=block.id, text=text[:block.config.max_length], generated_at=datetime.now(timezone.utc).isoformat(), evidence=[self._period_label(ctx["primary"])] + ([self._period_label(ctx["comparison"])] if ctx["comparison"] else []))
        draft.definition_json = definition.model_dump(mode="json")

    def regenerate_narratives(self, draft_id: str, payload: NarrativeRegenerateRequest, scope: dict) -> dict[str, Any]:
        draft = self._get_draft(draft_id, scope, edit=True)
        if draft.version != payload.expected_version: raise StoryConflictError("This draft was updated elsewhere. Reload before regenerating")
        try: self._regenerate_narratives(draft, scope, payload.slide_id); draft.version += 1; draft.last_saved_at = datetime.now(timezone.utc); self.db.commit(); self.db.refresh(draft)
        except Exception: self.db.rollback(); raise
        return self._serialize_draft(draft)

    def validate_draft(self, draft_id: str, scope: dict, *, persist: bool = True) -> ReportValidationResult:
        draft = self._get_draft(draft_id, scope); definition = ReportDraftDefinition.model_validate(draft.definition_json)
        issues = [ReportValidationIssue.model_validate(item) for item in validate_definition(definition)]
        if not definition.slides: issues.append(ReportValidationIssue(severity="error", code="empty_report", message="The report has no pages"))
        permissions = set(PERMISSION_MATRIX.get(str(scope.get("role")), []))
        can_view_actions = scope.get("role") == "Admin" or "view_actions" in permissions
        primary_context = self._context(
            draft,
            scope,
            include_actions=can_view_actions,
            action_evidence_authorized=can_view_actions,
        )
        if not primary_context["current"] and draft.report_type not in {"corrective_actions", "data_quality"}: issues.append(ReportValidationIssue(severity="error", code="missing_primary_data", message=f"No performance data is available for {draft.primary_period_month} {draft.primary_period_year}"))
        if draft.comparison_period_month and not primary_context["previous"]: issues.append(ReportValidationIssue(severity="warning", code="missing_comparison", message="Previous-period comparison is unavailable"))
        if not draft.comparison_period_month: issues.append(ReportValidationIssue(severity="warning", code="comparison_not_selected", message="A comparison period has not been selected"))
        shared_context_cache: dict[str, Any] = {}
        for slide in definition.slides:
            if not slide.blocks: issues.append(ReportValidationIssue(severity="error", code="empty_page", message="The page has no report blocks", slide_id=slide.id))
            else:
                resolved = self.resolve_slide(draft_id, slide.id, scope, _context_cache=shared_context_cache)
                for block_id, block_data in resolved["blocks"].items():
                    if block_data["state"] == "permission_denied":
                        issues.append(ReportValidationIssue(severity="error", code="block_permission_denied", message="A report block is outside the current user's permissions", slide_id=slide.id, block_id=block_id))
                    elif block_data["state"] != "ready":
                        issues.append(ReportValidationIssue(severity="warning", code="block_without_data", message="A report block has no resolved data for the selected scope", slide_id=slide.id, block_id=block_id))
        for item in self._kpis(primary_context):
            if item["target"] in {None, 0}: issues.append(ReportValidationIssue(severity="warning", code="invalid_target", message=f"{item['name']} has a missing or zero target"))
        if can_view_actions:
            for action in self._serialize_actions(primary_context):
                for message in action["validation"]: issues.append(ReportValidationIssue(severity="warning", code="unquantified_action", message=f"{action['problem'][:80]}: {message}"))
        result = ReportValidationResult(valid=not any(issue.severity == "error" for issue in issues), issues=issues, validated_at=datetime.now(timezone.utc).isoformat())
        if persist:
            draft.validation_json = result.model_dump(mode="json")
            try: self.db.commit()
            except Exception: self.db.rollback(); raise
        return result

    def generate(self, draft_id: str, payload: ReportGenerateRequest, scope: dict) -> dict[str, Any]:
        draft = self._get_draft(draft_id, scope, edit=True)
        if draft.version != payload.expected_version: raise StoryConflictError("This draft changed before export. Reload and validate again")
        validation = self.validate_draft(draft_id, scope)
        if not validation.valid: raise StoryValidationError("Resolve report validation errors before export")
        definition = ReportDraftDefinition.model_validate(draft.definition_json)
        shared_context_cache: dict[str, Any] = {}
        slide_data = {slide.id: self.resolve_slide(draft_id, slide.id, scope, _context_cache=shared_context_cache) for slide in definition.slides}
        metadata = {"scope": self._scope_label(ReportScope.model_validate(draft.scope_json)), "primary_period": f"{draft.primary_period_month} {draft.primary_period_year}", "comparison_period": f"{draft.comparison_period_month} {draft.comparison_period_year}" if draft.comparison_period_month else "Unavailable", "generated_by": str(scope.get("username") or getattr(scope.get("user"), "username", "User")), "generated_at": datetime.now(timezone.utc).isoformat()}
        snapshot = {"definition": definition.model_dump(mode="json"), "commentary": draft.management_commentary_json, "slide_data": slide_data, "metadata": metadata}; snapshot_bytes = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
        file_data = build_presentation_pdf(report_name=draft.name, definition=snapshot["definition"], slide_data=slide_data, commentary=draft.management_commentary_json, metadata=metadata)
        integrity = pdf_integrity_identifier(file_data, snapshot_bytes); safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", draft.name).strip("_") or "PMS_Report"
        generated = GeneratedReport(name=draft.name, report_type=draft.report_type, scope_summary=metadata["scope"], period_label=metadata["primary_period"], created_by_user_id=_safe_uuid(scope.get("user_id")), created_by_name=metadata["generated_by"], output_format="pdf", status="ready", file_name=f"{safe_name}.pdf", content_type="application/pdf", file_data=file_data, configuration={"draft_id": str(draft.id)}, record_count=len(self._context(draft, scope)["current"]), warning=" ".join(issue.message for issue in validation.issues if issue.severity == "warning") or None, draft_id=draft.id, template_id=draft.template_id, template_version=draft.template_version, primary_period_month=draft.primary_period_month, primary_period_year=draft.primary_period_year, comparison_period_month=draft.comparison_period_month, comparison_period_year=draft.comparison_period_year, scope_json=deepcopy(draft.scope_json), final_definition_json=deepcopy(snapshot["definition"]), narrative_snapshot_json={"system_analysis": deepcopy(snapshot["definition"].get("narratives", {})), "management_commentary": deepcopy(draft.management_commentary_json)}, data_snapshot_json=deepcopy(slide_data), validation_json=validation.model_dump(mode="json"), integrity_identifier=integrity, generated_at=datetime.now(timezone.utc))
        try: self.repo.add_generated(generated); draft.status = "generated"; self.db.commit(); self.db.refresh(generated)
        except Exception: self.db.rollback(); raise
        return {"id": str(generated.id), "name": generated.name, "status": generated.status, "format": "pdf", "file_name": generated.file_name, "integrity_identifier": integrity, "download_url": f"/api/reports/{generated.id}/download"}

    @staticmethod
    def _scope_label(scope: ReportScope) -> str:
        return scope.employee_id or scope.position or scope.team or scope.region or "All authorized teams"

    def duplicate_generated(self, report_id: str, primary: ReportPeriod, comparison: ReportPeriod | None, scope: dict) -> dict[str, Any]:
        generated = self._get_generated(report_id, scope)
        definition = ReportDraftDefinition.model_validate(generated.final_definition_json)
        definition.narratives = {}
        commentary = ManagementCommentary(entries={block.id: "" for slide in definition.slides for block in slide.blocks if block.type == "management_commentary"})
        draft = ReportDraft(name=generated.name, report_type=generated.report_type, template_id=generated.template_id, template_version=generated.template_version, owner_user_id=_safe_uuid(scope.get("user_id")), status="editing", primary_period_month=primary.month, primary_period_year=primary.year, comparison_period_month=comparison.month if comparison else None, comparison_period_year=comparison.year if comparison else None, scope_json=deepcopy(generated.scope_json), definition_json=definition.model_dump(mode="json"), management_commentary_json=commentary.model_dump(mode="json"), version=1)
        try: self.repo.add_draft(draft); self.db.flush(); self._regenerate_narratives(draft, scope); self.db.commit(); self.db.refresh(draft)
        except Exception: self.db.rollback(); raise
        return self._serialize_draft(draft)

    def _get_generated(self, report_id: str, scope: dict) -> GeneratedReport:
        try: parsed = uuid.UUID(report_id)
        except ValueError: raise StoryNotFoundError("Generated report was not found")
        row = self.repo.get_generated(parsed)
        if not row: raise StoryNotFoundError("Generated report was not found")
        if scope.get("role") != "Admin" and str(row.created_by_user_id) != str(scope.get("user_id")): raise StoryAccessError("This report belongs to another user")
        return row

    def delete_generated(self, report_id: str, scope: dict) -> dict[str, str]:
        row = self._get_generated(report_id, scope); result = {"id": str(row.id), "name": row.name}
        try: self.repo.delete_generated(row); self.db.commit()
        except Exception: self.db.rollback(); raise
        return result
