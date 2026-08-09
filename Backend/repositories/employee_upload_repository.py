from __future__ import annotations

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.models import (
    EmployeeUploadBatch,
    KPIValue,
    PerformanceRecord,
    Team,
    UploadLog,
)


MONTH_ORDER = {
    month: index
    for index, month in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        start=1,
    )
}


class EmployeeUploadRepository:
    """Persistence operations for workbook-level employee PMS uploads."""

    def __init__(self, db: Session):
        self.db = db

    def list_batches(self) -> list[dict]:
        batches = (
            self.db.query(EmployeeUploadBatch)
            .order_by(EmployeeUploadBatch.uploaded_at.desc(), EmployeeUploadBatch.id.desc())
            .all()
        )
        if not batches:
            return []

        batch_ids = [batch.id for batch in batches]
        scope_rows = (
            self.db.query(
                UploadLog.batch_id,
                Team.display_name,
                Team.name,
                UploadLog.month,
                UploadLog.year,
            )
            .join(Team, UploadLog.team_id == Team.id)
            .filter(UploadLog.batch_id.in_(batch_ids))
            .all()
        )
        scopes: dict[UUID, dict[str, set]] = {
            batch_id: {"teams": set(), "periods": set()} for batch_id in batch_ids
        }
        for batch_id, display_name, team_name, month, year in scope_rows:
            scope = scopes.setdefault(batch_id, {"teams": set(), "periods": set()})
            scope["teams"].add(display_name or team_name)
            scope["periods"].add((int(year), str(month)))

        return [
            {
                "id": str(batch.id),
                "filename": batch.filename,
                "uploaded_at": batch.uploaded_at.isoformat() if batch.uploaded_at else None,
                "uploaded_by": batch.uploaded_by_name
                or (str(batch.uploaded_by_user_id) if batch.uploaded_by_user_id else "Admin"),
                "status": batch.status,
                "record_count": int(batch.record_count or 0),
                "team_count": int(batch.team_count or 0),
                "teams": sorted(scopes.get(batch.id, {}).get("teams", set())),
                "periods": [
                    f"{month} {year}"
                    for year, month in sorted(
                        scopes.get(batch.id, {}).get("periods", set()),
                        key=lambda period: (period[0], MONTH_ORDER.get(period[1], 13)),
                    )
                ],
            }
            for batch in batches
        ]

    def delete_batch(self, batch_id: UUID) -> tuple[int, int]:
        batch = (
            self.db.query(EmployeeUploadBatch)
            .filter(EmployeeUploadBatch.id == batch_id)
            .first()
        )
        if batch is None:
            return 0, 0

        log_ids = [
            row[0]
            for row in self.db.query(UploadLog.id)
            .filter(UploadLog.batch_id == batch_id)
            .all()
        ]
        performance_ids = []
        if log_ids:
            performance_ids = [
                row[0]
                for row in self.db.query(PerformanceRecord.id)
                .filter(PerformanceRecord.upload_id.in_(log_ids))
                .all()
            ]
        if performance_ids:
            self.db.query(KPIValue).filter(
                KPIValue.record_id.in_(performance_ids)
            ).delete(synchronize_session=False)
            self.db.query(PerformanceRecord).filter(
                PerformanceRecord.id.in_(performance_ids)
            ).delete(synchronize_session=False)

        self.db.delete(batch)
        return 1, len(performance_ids)

    def count_current_records(self, batch_id: UUID) -> int:
        return int(
            self.db.query(func.count(PerformanceRecord.id))
            .join(UploadLog, PerformanceRecord.upload_id == UploadLog.id)
            .filter(UploadLog.batch_id == batch_id)
            .scalar()
            or 0
        )
