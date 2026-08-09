from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session, defer, joinedload

from models.models import GeneratedReport, ReportDraft, ReportTemplate, SavedReportTemplate, UploadLog


class ReportRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_generated(self, report: GeneratedReport) -> None:
        self.db.add(report)

    def add_template(self, template: ReportTemplate) -> None:
        self.db.add(template)

    def list_templates(self, owner_user_id: UUID) -> list[ReportTemplate]:
        return self.db.query(ReportTemplate).filter(
            ReportTemplate.is_archived.is_(False),
            or_(
                ReportTemplate.is_system_template.is_(True),
                ReportTemplate.visibility == "organization",
                ReportTemplate.owner_user_id == owner_user_id,
            ),
        ).order_by(ReportTemplate.is_system_template.desc(), ReportTemplate.name, ReportTemplate.version.desc()).all()

    def get_template(self, template_id: UUID) -> ReportTemplate | None:
        return self.db.query(ReportTemplate).filter(ReportTemplate.id == template_id, ReportTemplate.is_archived.is_(False)).first()

    def get_template_key_version(self, template_key: str, version: int) -> ReportTemplate | None:
        return self.db.query(ReportTemplate).filter(ReportTemplate.template_key == template_key, ReportTemplate.version == version).first()

    def latest_template_version(self, template_key: str) -> int:
        row = self.db.query(ReportTemplate.version).filter(ReportTemplate.template_key == template_key).order_by(ReportTemplate.version.desc()).first()
        return int(row[0]) if row else 0

    def archive_template_key(self, template_key: str) -> None:
        self.db.query(ReportTemplate).filter(ReportTemplate.template_key == template_key).update(
            {"is_archived": True}, synchronize_session=False,
        )

    def add_draft(self, draft: ReportDraft) -> None:
        self.db.add(draft)

    def get_draft(self, draft_id: UUID) -> ReportDraft | None:
        return self.db.query(ReportDraft).filter(ReportDraft.id == draft_id, ReportDraft.status != "archived").first()

    def list_drafts(self, owner_user_id: UUID) -> list[ReportDraft]:
        return self.db.query(ReportDraft).filter(ReportDraft.owner_user_id == owner_user_id, ReportDraft.status != "archived").order_by(ReportDraft.updated_at.desc()).all()

    def update_draft_versioned(self, draft_id: UUID, expected_version: int, values: dict) -> bool:
        return self.db.query(ReportDraft).filter(
            ReportDraft.id == draft_id,
            ReportDraft.version == expected_version,
            ReportDraft.status != "archived",
        ).update({**values, "version": expected_version + 1}, synchronize_session=False) == 1

    def delete_generated(self, report: GeneratedReport) -> None:
        self.db.delete(report)

    def list_generated(
        self,
        *,
        owner_user_id: UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[GeneratedReport], int]:
        query = self.db.query(GeneratedReport).options(defer(GeneratedReport.file_data))
        if owner_user_id is not None:
            query = query.filter(GeneratedReport.created_by_user_id == owner_user_id)
        total = query.count()
        rows = query.order_by(GeneratedReport.created_at.desc()).offset(offset).limit(limit).all()
        return rows, total

    def get_generated(self, report_id: UUID) -> GeneratedReport | None:
        return self.db.query(GeneratedReport).filter(GeneratedReport.id == report_id).first()

    def add_saved_template(self, template: SavedReportTemplate) -> None:
        self.db.add(template)

    def list_saved_templates(self, owner_user_id: UUID) -> list[SavedReportTemplate]:
        return (
            self.db.query(SavedReportTemplate)
            .filter(SavedReportTemplate.owner_user_id == owner_user_id)
            .order_by(SavedReportTemplate.updated_at.desc())
            .all()
        )

    def list_upload_logs(self) -> list[UploadLog]:
        return (
            self.db.query(UploadLog)
            .options(joinedload(UploadLog.team))
            .order_by(UploadLog.uploaded_at.desc())
            .all()
        )
