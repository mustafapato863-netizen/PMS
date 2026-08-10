from __future__ import annotations

import datetime as dt
import json
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from models.models import Action, Employee, PerformancePlan, PerformanceRecord, PlanObjective, Team, User
from repositories.action_repository import ActionRepository
from utils.report_scope import user_can_access_team_level
from utils.team_identity import logical_team_name


ACTION_TYPES = {"Training", "Reward", "PIP", "Monitor", "Coaching", "Warning", "Promotion"}
ACTION_ID_NAMESPACE = uuid.UUID("d752dc8d-2cae-4e7e-9efd-447550c27cf8")
TRANSFER_FORMAT = "pms.corrective-actions"
TRANSFER_VERSION = 1


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

    @staticmethod
    def _iso(value: Any) -> str | None:
        return value.isoformat() if value is not None and hasattr(value, "isoformat") else None

    @staticmethod
    def _identity(user: User | None) -> dict[str, str | None] | None:
        if not user:
            return None
        return {
            "id": str(user.id) if user.id else None,
            "username": user.username,
            "email": user.email,
        }

    @staticmethod
    def _team_reference(team: Team | None) -> dict[str, str | None] | None:
        if not team:
            return None
        return {
            "id": str(team.id) if team.id else None,
            "name": team.name,
            "db_name": team.db_name,
            "display_name": team.display_name,
            "region": team.region,
            "team_level": team.team_level,
        }

    @staticmethod
    def _employee_reference(employee: Employee | None) -> dict[str, str | None] | None:
        if not employee:
            return None
        return {
            "id": str(employee.id) if employee.id else None,
            "employee_id": employee.employee_id,
            "name": employee.name,
            "performance_level": employee.performance_level,
        }

    def export_transfer_payload(self) -> dict[str, Any]:
        """Build a portable, versioned JSON snapshot of every corrective action row."""
        actions = (
            self.db.query(Action)
            .options(
                joinedload(Action.employee),
                joinedload(Action.team),
                joinedload(Action.created_by_user),
                joinedload(Action.updated_by_user),
                joinedload(Action.owner),
            )
            .order_by(Action.created_at.asc(), Action.id.asc())
            .all()
        )
        records: list[dict[str, Any]] = []
        for action in actions:
            records.append(
                {
                    "id": str(action.id),
                    "employee": self._employee_reference(action.employee),
                    "team": self._team_reference(action.team),
                    "month": action.month,
                    "year": action.year,
                    "action_type": action.action_type,
                    "plan_title": action.plan_title,
                    "action_text": action.action_text,
                    "root_cause_note": action.root_cause_note,
                    "status": action.status,
                    "plan_id": str(action.plan_id) if action.plan_id else None,
                    "objective_id": str(action.objective_id) if action.objective_id else None,
                    "owner": self._identity(action.owner),
                    "due_date": self._iso(action.due_date),
                    "priority": action.priority,
                    "linked_kpi_key": action.linked_kpi_key,
                    "completion_note": action.completion_note,
                    "evidence_reference": action.evidence_reference,
                    "is_active": bool(action.is_active),
                    "created_by": self._identity(action.created_by_user),
                    "created_at": self._iso(action.created_at),
                    "updated_by": self._identity(action.updated_by_user),
                    "updated_at": self._iso(action.updated_at),
                }
            )
        return {
            "format": TRANSFER_FORMAT,
            "version": TRANSFER_VERSION,
            "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "record_count": len(records),
            "records": records,
        }

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _parse_uuid(value: Any) -> uuid.UUID | None:
        if value is None or value == "":
            return None
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError, AttributeError):
            return None

    @staticmethod
    def _parse_datetime(value: Any, field_name: str, row_number: int) -> dt.datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, dt.datetime):
            return value
        try:
            return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise CorrectiveActionValidationError(f"Row {row_number}: invalid {field_name}") from exc

    @staticmethod
    def _parse_active(value: Any, status: Any = None) -> bool:
        """Parse JSON activity flags without treating the string ``false`` as true."""
        if value is None:
            normalized_status = str(status or "").strip().casefold()
            return normalized_status not in {"deleted", "inactive", "archived", "closed"}
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        normalized = str(value).strip().casefold()
        if normalized in {"false", "0", "no", "off", "inactive", "archived", "deleted", "closed"}:
            return False
        if normalized in {"true", "1", "yes", "on", "active", "open"}:
            return True
        return True

    @staticmethod
    def _parse_date(value: Any, row_number: int) -> dt.date | None:
        if value in (None, ""):
            return None
        if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
            return value
        try:
            return dt.date.fromisoformat(str(value))
        except ValueError as exc:
            raise CorrectiveActionValidationError(f"Row {row_number}: invalid due_date") from exc

    def _resolve_team(self, reference: Any, fallback_id: Any, row_number: int) -> Team | None:
        data = self._as_dict(reference)
        team_id = self._parse_uuid(data.get("id") or fallback_id)
        if team_id:
            team = self.db.query(Team).filter(Team.id == team_id).first()
            if team:
                return team

        names = [reference] if isinstance(reference, str) else [data.get("name"), data.get("db_name"), data.get("display_name")]
        for candidate in names:
            if not isinstance(candidate, str) or not candidate.strip():
                continue
            normalized = candidate.strip().casefold()
            team = (
                self.db.query(Team)
                .filter(
                    or_(
                        func.lower(Team.name) == normalized,
                        func.lower(Team.db_name) == normalized,
                        func.lower(func.coalesce(Team.display_name, "")) == normalized,
                    )
                )
                .first()
            )
            if team:
                return team
        if reference or fallback_id:
            raise CorrectiveActionValidationError(f"Row {row_number}: referenced team was not found")
        return None

    def _resolve_employee(self, reference: Any, fallback_id: Any, row_number: int) -> Employee | None:
        data = self._as_dict(reference)
        employee_identifier = (
            reference.strip() if isinstance(reference, str) and reference.strip()
            else data.get("employee_id") or data.get("hr_id") or data.get("id") or fallback_id
        )
        if isinstance(employee_identifier, str) and employee_identifier.strip():
            employee = self.db.query(Employee).filter(Employee.employee_id == employee_identifier.strip()).first()
            if employee:
                return employee
        employee_uuid = self._parse_uuid(data.get("id"))
        if employee_uuid:
            employee = self.db.query(Employee).filter(Employee.id == employee_uuid).first()
            if employee:
                return employee
        if reference or fallback_id:
            raise CorrectiveActionValidationError(f"Row {row_number}: referenced employee was not found")
        return None

    def _resolve_user(self, reference: Any) -> uuid.UUID | None:
        data = self._as_dict(reference)
        user_id = self._parse_uuid(data.get("id"))
        if user_id and self.db.query(User.id).filter(User.id == user_id).first():
            return user_id
        candidates = [data.get("username"), data.get("email")]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                user = self.db.query(User).filter(
                    or_(func.lower(User.username) == candidate.strip().casefold(), func.lower(User.email) == candidate.strip().casefold())
                ).first()
                if user:
                    return user.id
        return None

    def _resolve_optional_fk(self, model: type, value: Any) -> uuid.UUID | None:
        candidate = self._parse_uuid(value)
        if candidate and self.db.query(model.id).filter(model.id == candidate).first():
            return candidate
        return None

    def import_transfer_payload(self, payload: Any) -> dict[str, int]:
        """Atomically upsert a JSON snapshot, resolving portable employee/team references."""
        if not isinstance(payload, dict) or payload.get("format") != TRANSFER_FORMAT:
            raise CorrectiveActionValidationError("Invalid corrective action JSON format")
        if payload.get("version") != TRANSFER_VERSION:
            raise CorrectiveActionValidationError("Unsupported corrective action JSON version")
        records = payload.get("records")
        if not isinstance(records, list):
            raise CorrectiveActionValidationError("Corrective action JSON must contain a records array")
        if len(records) > 100_000:
            raise CorrectiveActionValidationError("Corrective action file contains too many records")

        created = 0
        updated = 0
        try:
            for index, raw_record in enumerate(records, start=1):
                if not isinstance(raw_record, dict):
                    raise CorrectiveActionValidationError(f"Row {index}: record must be an object")

                # A backup can contain legacy rows whose required fields are
                # blank even though the current schema does not allow new
                # rows to be created that way. When restoring into the same
                # database, keep those existing values so an edited backup
                # remains round-trippable without weakening validation for
                # genuinely new records.
                source_id = str(raw_record.get("id") or "").strip()
                action_id = self._parse_uuid(source_id)
                action = self.db.query(Action).filter(Action.id == action_id).first() if action_id else None
                month = str(raw_record.get("month") or "").strip()
                action_text = str(raw_record.get("action_text") or "").strip()

                # Older action exports used manager_action instead of the
                # canonical action_type/action_text pair. Accept that shape
                # when a user re-uploads an older downloaded snapshot.
                legacy_action = str(raw_record.get("manager_action") or "").strip()
                legacy_action_type = ""
                if legacy_action:
                    legacy_action_type, legacy_action_text = self.split_manager_action(legacy_action)
                    action_text = action_text or legacy_action_text

                if action:
                    month = month or str(action.month or "").strip()
                    action_text = action_text or str(action.action_text or "").strip()

                is_active = self._parse_active(raw_record.get("is_active"), raw_record.get("status"))

                timestamp_value = raw_record.get("created_at") or raw_record.get("timestamp")
                parsed_timestamp = None
                if timestamp_value not in (None, ""):
                    try:
                        parsed_timestamp = dt.datetime.fromisoformat(str(timestamp_value).replace("Z", "+00:00"))
                    except ValueError:
                        parsed_timestamp = None
                month = month or (parsed_timestamp.strftime("%B") if parsed_timestamp else "")
                missing_fields = []
                if not month:
                    missing_fields.append("month")
                # Archived placeholder rows from older databases may have no
                # action body. Keep them transferable, while rejecting an
                # incomplete active action.
                if is_active and not action_text:
                    missing_fields.append("action_text")
                if missing_fields:
                    raise CorrectiveActionValidationError(
                        f"Row {index}: {' and '.join(missing_fields)} are required"
                    )
                try:
                    year = int(raw_record.get("year") or (parsed_timestamp.year if parsed_timestamp else ""))
                except (TypeError, ValueError) as exc:
                    raise CorrectiveActionValidationError(f"Row {index}: year must be a number") from exc
                if year < 2000 or year > 2100:
                    raise CorrectiveActionValidationError(f"Row {index}: year is outside the supported range")

                employee = self._resolve_employee(raw_record.get("employee"), raw_record.get("employee_id"), index)
                team = self._resolve_team(raw_record.get("team"), raw_record.get("team_id"), index)
                if employee:
                    team = employee.team
                if not team:
                    raise CorrectiveActionValidationError(f"Row {index}: an employee or team reference is required")

                if not action_id:
                    employee_reference = self._as_dict(raw_record.get("employee"))
                    action_id = uuid.uuid5(
                        ACTION_ID_NAMESPACE,
                        f"{employee_reference.get('employee_id', '')}:{team.id}:{month}:{year}:{raw_record.get('action_type', 'Coaching')}:{action_text}",
                    )
                action_type = str(raw_record.get("action_type") or raw_record.get("suggested_action") or legacy_action_type or "Coaching").strip()[:50] or "Coaching"
                values = {
                    "employee_id": employee.id if employee else None,
                    "team_id": team.id,
                    "month": month[:20],
                    "year": year,
                    "action_type": action_type,
                    "plan_title": str(raw_record.get("plan_title") or "")[:255] or None,
                    "action_text": action_text,
                    "root_cause_note": str(raw_record.get("root_cause_note") or raw_record.get("manager_notes") or "").strip() or None,
                    "status": str(raw_record.get("status") or "Open").strip()[:50] or "Open",
                    "plan_id": self._resolve_optional_fk(PerformancePlan, raw_record.get("plan_id")),
                    "objective_id": self._resolve_optional_fk(PlanObjective, raw_record.get("objective_id")),
                    "owner_user_id": self._resolve_user(raw_record.get("owner")),
                    "due_date": self._parse_date(raw_record.get("due_date"), index),
                    "priority": str(raw_record.get("priority") or "")[:20] or None,
                    "linked_kpi_key": str(raw_record.get("linked_kpi_key") or "")[:100] or None,
                    "completion_note": str(raw_record.get("completion_note") or "").strip() or None,
                    "evidence_reference": str(raw_record.get("evidence_reference") or "")[:500] or None,
                    "is_active": is_active,
                    "created_by_user_id": self._resolve_user(raw_record.get("created_by")),
                    "updated_by_user_id": self._resolve_user(raw_record.get("updated_by")),
                    "created_at": self._parse_datetime(timestamp_value, "created_at", index),
                    "updated_at": self._parse_datetime(raw_record.get("updated_at") or raw_record.get("timestamp"), "updated_at", index),
                }
                if action:
                    for field, value in values.items():
                        setattr(action, field, value)
                    updated += 1
                else:
                    self.db.add(Action(id=action_id, **values))
                    created += 1
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {"created": created, "updated": updated, "total": created + updated}
