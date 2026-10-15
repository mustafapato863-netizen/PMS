"""Corrective-action history from the database.

It replaces the JSON corrective-action file for two readers: the upload's suggested action, and the recommendation
history. The mapping from the JSON record, with the migration in scripts/migrate_corrective_actions_to_db.py reversed:

- manager_action is "<Action.action_type>: <Action.action_text>", the same string the migration split apart.
- manager_notes is Action.root_cause_note.
- An action belongs to an employee-month only when the employee code, the month name and the year all match.
- Only active actions count (is_active). The newest action wins: created_at, then id.
- Recommendations need team, score, grade, root cause and suggested action. An Action row holds none of them, so they
  come from the performance record of the same employee, month and year. The record's team, score, grade, root cause
  and suggested action are the snapshot the endpoint already uses. An action with no matching record is left out.
- Team-level actions (no employee) are not employee history and are left out.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from models.models import Action, Employee
from models.schemas import CorrectiveAction
from services.dashboard_record_service import DashboardRecordService


@dataclass(frozen=True)
class LatestAction:
    manager_action: str
    manager_notes: str


def _manager_action(action: Action) -> str:
    return f"{action.action_type}: {action.action_text}"


class DatabaseActionHistory:
    def __init__(self, db: Session):
        self.db = db

    def _active_rows(self, *filters):
        return (
            self.db.query(Action, Employee.employee_id)
            .join(Employee, Action.employee_id == Employee.id)
            .filter(Action.is_active.is_(True), *filters)
            .order_by(Action.created_at.asc(), Action.id.asc())
            .all()
        )

    def latest_by_employee_and_period(self) -> dict[tuple[str, str, int], LatestAction]:
        """The latest active action for every employee-month, read in one query. Keys: (employee code, month, year)."""
        latest: dict[tuple[str, str, int], LatestAction] = {}
        # Rows come oldest first, so the last row seen for a key is the newest action.
        for action, employee_code in self._active_rows():
            latest[(str(employee_code), str(action.month), int(action.year))] = LatestAction(
                manager_action=_manager_action(action),
                manager_notes=action.root_cause_note or "",
            )
        return latest

    def get_latest_by_employee_and_month(self, employee_id: str, month: str, year: int) -> LatestAction | None:
        rows = self._active_rows(
            Employee.employee_id == str(employee_id),
            Action.month == month,
            Action.year == int(year),
        )
        if not rows:
            return None
        action, _employee_code = rows[-1]
        return LatestAction(manager_action=_manager_action(action), manager_notes=action.root_cause_note or "")

    def get_history(self, employee_id: str | None = None) -> list[CorrectiveAction]:
        filters = (Employee.employee_id == str(employee_id),) if employee_id else ()
        rows = self._active_rows(*filters)
        if not rows:
            return []
        records: dict[tuple[str, int, str], object] = {}
        for record in DashboardRecordService(self.db).list_records():
            key = (str(record.employee_id), int(record.year or 0), str(record.month))
            records.setdefault(key, record)
        history: list[CorrectiveAction] = []
        for action, employee_code in rows:
            record = records.get((str(employee_code), int(action.year), str(action.month)))
            if record is None:
                continue
            evaluation = record.evaluation
            history.append(CorrectiveAction(
                id=str(action.id),
                employee_id=str(employee_code),
                employee_name=str(record.employee_name or employee_code),
                team=str(record.team),
                month=str(action.month),
                score=float(evaluation.score),
                grade=str(evaluation.grade),
                root_cause=evaluation.root_cause.kpi if evaluation.root_cause else "None",
                suggested_action=str(evaluation.suggested_action or ""),
                manager_action=_manager_action(action),
                manager_notes=action.root_cause_note or "",
                timestamp=action.created_at.isoformat() if action.created_at else "",
            ))
        return history
