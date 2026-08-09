from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from repositories.employee_upload_repository import EmployeeUploadRepository


class EmployeeUploadService:
    """Workbook-level upload history and atomic deletion orchestration."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = EmployeeUploadRepository(db)

    def list_uploads(self) -> list[dict]:
        return self.repository.list_batches()

    def delete_upload(self, upload_id: str) -> dict:
        try:
            batch_id = UUID(str(upload_id))
        except (TypeError, ValueError, AttributeError):
            return {"found": False, "uploads_deleted": 0, "performance_deleted": 0}
        try:
            deleted, performance_deleted = self.repository.delete_batch(batch_id)
            if not deleted:
                return {"found": False, "uploads_deleted": 0, "performance_deleted": 0}
            self.db.commit()
            return {
                "found": True,
                "uploads_deleted": deleted,
                "performance_deleted": performance_deleted,
            }
        except Exception:
            self.db.rollback()
            raise

    def delete_uploads(self, upload_ids: list[str]) -> dict:
        deleted = 0
        performance_deleted = 0
        try:
            for upload_id in dict.fromkeys(upload_ids):
                try:
                    batch_id = UUID(str(upload_id))
                except (TypeError, ValueError, AttributeError):
                    continue
                batch_deleted, records_deleted = self.repository.delete_batch(batch_id)
                deleted += batch_deleted
                performance_deleted += records_deleted
            self.db.commit()
            return {
                "uploads_deleted": deleted,
                "performance_deleted": performance_deleted,
            }
        except Exception:
            self.db.rollback()
            raise
