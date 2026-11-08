"""Performance records for the runtime, read from the database.

The planning and insights services ask for every record (``get_all``) and for one employee's month
(``get_by_employee_and_month``). They used to ask the JSON mirror. This adapter answers the same two calls from the
canonical database rows that the dashboards already read, so the runtime no longer reads or writes data/*.json.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from services.dashboard_record_service import DashboardRecordService


class DatabaseRecordSource:
    def __init__(self, db: Session, scope: dict[str, Any] | None = None):
        self.db = db
        self.scope = scope

    def get_all(self, *, scope: dict[str, Any] | None = None) -> list[Any]:
        effective_scope = scope if scope is not None else self.scope
        return DashboardRecordService(self.db).list_records(scope=effective_scope)

    def get_by_employee_and_month(
        self,
        employee_id: str,
        month: str,
        *,
        scope: dict[str, Any] | None = None,
    ) -> Any | None:
        effective_scope = scope if scope is not None else self.scope
        rows = DashboardRecordService(self.db).list_records(
            employee_id=str(employee_id),
            month=month,
            scope=effective_scope,
        )
        return rows[0] if rows else None
