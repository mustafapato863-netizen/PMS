from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from models.models import Action, Employee, PerformanceRecord, User
from repositories.action_repository import ActionRepository
from utils.report_scope import user_can_access_team_level
from utils.team_identity import logical_team_name


ACTION_TYPES = {"Training", "Reward", "PIP", "Monitor", "Coaching", "Warning", "Promotion"}
ACTION_ID_NAMESPACE = uuid.UUID("d752dc8d-2cae-4e7e-9efd-447550c27cf8")


class CorrectiveActionNotFoundError(ValueError):
    pass


class CorrectiveActionValidationError(ValueError):
    pass


class CorrectiveActionService:
    def __init__(self, db: Session):
        self.db = db
        self.actions = ActionRepository(db)

    @staticmethod
    def split_manager_action(manager_action: str) -> tuple[str, str]:
        value = manager_action.strip()
        if not value:
            raise CorrectiveActionValidationError("Corrective Action is required")
        action_type, separator, action_text = value.partition(": ")
        if separator and action_type in ACTION_TYPES:
            return action_type, action_text.strip()
        return "Coaching", value

    def _employee(self, employee_identifier: str) -> Employee:
        identifier = employee_identifier.strip()
        employee = self.db.query(Employee).filter(Employee.employee_id == identifier).first()
        if employee:
            return employee

        # Compatibility for old imports that stored numeric IDs without the SGH prefix.
        if identifier.upper().startswith(("SGHD", "SGHA")):
            suffix = identifier[4:]
            employee = self.db.query(Employee).filter(Employee.employee_id == suffix).first()
        if not employee:
            raise CorrectiveActionNotFoundError("Employee not found")
        return employee

    @staticmethod
    def _uuid(value: str | None) -> uuid.UUID | None:
        if not value:
            return None
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError):
            return None

    @classmethod
    def _action_uuid(cls, value: str | None) -> uuid.UUID | None:
        if not value:
            return None
        parsed = cls._uuid(value)
        return parsed or uuid.uuid5(ACTION_ID_NAMESPACE, value.strip())

    def _score_snapshot(self, action: Action) -> tuple[float | None, str | None]:
        if not action.employee_id:
            return None, None
        record = (
            self.db.query(PerformanceRecord)
            .filter(
                PerformanceRecord.employee_id == action.employee_id,
                PerformanceRecord.month == action.month,
                PerformanceRecord.year == action.year,
            )
            .order_by(PerformanceRecord.uploaded_at.desc())
            .first()
        )
        if not record:
            return None, None
        score = float(record.score) if isinstance(record.score, (Decimal, int, float)) else None
        return score, record.grade or None

    def serialize(self, action: Action) -> dict[str, Any]:
        score, grade = self._score_snapshot(action)
        created_by = action.created_by_user
        timestamp = action.created_at or dt.datetime.now(dt.timezone.utc)
        return {
            "id": str(action.id),
            "employee_id": action.employee.employee_id if action.employee else None,
            "employee_name": action.employee.name if action.employee else None,
            "team": action.team.display_name or action.team.name,
            "month": action.month,
            "year": action.year,
            "score": score,
            "grade": grade,
            "root_cause": action.root_cause_note or "None",
            "suggested_action": action.action_type,
            "manager_action": f"{action.action_type}: {action.action_text}",
            "manager_notes": action.root_cause_note or "",
            "timestamp": timestamp.isoformat(),
            "created_by_name": created_by.username if created_by else None,
            "created_by_role": created_by.role if created_by else None,
            "status": action.status,
        }

    def list_all(self) -> list[dict[str, Any]]:
        # Planning reuses Action, while this legacy workspace remains
        # employee-specific and keeps its existing response contract.
        return [
            self.serialize(action)
            for action in self.actions.list_active()
            if action.employee_id is not None
        ]

    def list_scoped(self, scope: dict) -> list[dict[str, Any]]:
        return [
            self.serialize(action)
            for action in self.actions.list_active()
            if action.employee_id is not None
            and action.employee is not None
            and user_can_access_team_level(scope, logical_team_name(action.team), action.employee.performance_level)
        ]

    def ensure_employee_scope(self, employee_identifier: str, scope: dict) -> Employee:
        employee = self._employee(employee_identifier)
        if not user_can_access_team_level(scope, logical_team_name(employee.team), employee.performance_level):
            raise PermissionError("The employee is outside your authorized action scope")
        return employee

    def get_history(self, employee_identifier: str) -> list[dict[str, Any]]:
        employee = self._employee(employee_identifier)
        return [self.serialize(action) for action in self.actions.list_active_by_employee(employee.id)]

    def save(
        self,
        *,
        employee_identifier: str,
        month: str,
        manager_action: str,
        manager_notes: str = "",
        action_id: str | None = None,
        year: int | None = None,
        user_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        month = month.strip()
        if not month:
            raise CorrectiveActionValidationError("Month is required")
        action_type, action_text = self.split_manager_action(manager_action)
        employee = self._employee(employee_identifier)
        parsed_action_id = self._action_uuid(action_id)
        action = self.actions.get_active(parsed_action_id) if parsed_action_id else None
        if parsed_action_id and not action:
            inactive_action = self.actions.get_by_id(parsed_action_id, include_deleted=True)
            if inactive_action:
                raise CorrectiveActionNotFoundError("Corrective Action is inactive")
        is_update = action is not None

        if action and action.employee_id != employee.id:
            raise CorrectiveActionNotFoundError("Corrective Action not found for this employee")

        actor_id = self._uuid(user_id)
        if actor_id and not self.db.query(User.id).filter(User.id == actor_id).first():
            actor_id = None

        try:
            if action:
                action.month = month
                action.year = year or action.year
                action.action_type = action_type
                action.action_text = action_text
                action.root_cause_note = manager_notes.strip() or None
                action.updated_by_user_id = actor_id
                action.updated_at = dt.datetime.now(dt.timezone.utc)
            else:
                action = Action(
                    id=parsed_action_id or uuid.uuid4(),
                    employee_id=employee.id,
                    team_id=employee.team_id,
                    month=month,
                    year=year or dt.datetime.now().year,
                    action_type=action_type,
                    action_text=action_text,
                    root_cause_note=manager_notes.strip() or None,
                    status="Open",
                    is_active=True,
                    created_by_user_id=actor_id,
                )
                self.actions.add(action)
            self.db.commit()
            self.db.refresh(action)
            return self.serialize(action), is_update
        except Exception:
            self.db.rollback()
            raise

    def deactivate(self, *, employee_identifier: str, action_id: str, user_id: str | None = None) -> dict[str, Any]:
        employee = self._employee(employee_identifier)
        parsed_action_id = self._uuid(action_id)
        action = self.actions.get_active(parsed_action_id) if parsed_action_id else None
        if not action or action.employee_id != employee.id:
            raise CorrectiveActionNotFoundError("Corrective Action not found")

        try:
            action.is_active = False
            action.updated_by_user_id = self._uuid(user_id)
            action.updated_at = dt.datetime.now(dt.timezone.utc)
            self.db.commit()
            return self.serialize(action)
        except Exception:
            self.db.rollback()
            raise
