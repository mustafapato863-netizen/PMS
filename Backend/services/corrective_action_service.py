from __future__ import annotations

import datetime as dt
import json
import logging
import uuid
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from models.models import (
    Action,
    Employee,
    PerformancePlan,
    PerformanceRecord,
    PlanObjective,
    Team,
    User,
    UserTeamAssignment,
)
from repositories.action_repository import ActionRepository
from services.audit_service import AuditService
from utils.report_scope import (
    filter_records_by_scope,
    user_can_access_region,
    user_can_access_team,
    user_can_access_team_level,
)
from utils.team_identity import logical_team_name


ACTION_TYPES = {"Training", "Reward", "PIP", "Monitor", "Coaching", "Warning", "Promotion"}
ACTION_STATUSES = {"Open", "In Progress", "Completed", "Cancelled"}
ACTION_PRIORITIES = {"Low", "Medium", "High"}
OPEN_ACTION_STATUSES = {"Open", "In Progress"}
DUE_SOON_WINDOW_DAYS = 7
FOLLOW_UP_STATE_ORDER = {
    "overdue": 0,
    "due_soon": 1,
    "upcoming": 2,
    "no_due_date": 3,
    "completed": 4,
    "cancelled": 5,
}
ACTION_ID_NAMESPACE = uuid.UUID("d752dc8d-2cae-4e7e-9efd-447550c27cf8")
TRANSFER_FORMAT = "pms.corrective-actions"
TRANSFER_VERSION = 1
_UNSET = object()


class CorrectiveActionNotFoundError(ValueError):
    pass


class CorrectiveActionValidationError(ValueError):
    pass


class CorrectiveActionAccessError(PermissionError):
    pass


class CorrectiveActionService:
    def __init__(self, db: Session, *, today: dt.date | None = None):
        self.db = db
        self.actions = ActionRepository(db)
        self.today = today or dt.date.today()

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

    def _period_performance_record(
        self,
        *,
        employee_id: uuid.UUID | None,
        month: str | None,
        year: int | None,
    ) -> PerformanceRecord | None:
        if not employee_id or not month or year is None:
            return None
        return (
            self.db.query(PerformanceRecord)
            .options(joinedload(PerformanceRecord.team))
            .filter(
                PerformanceRecord.employee_id == employee_id,
                func.lower(PerformanceRecord.month) == month.strip().casefold(),
                PerformanceRecord.year == year,
            )
            .order_by(PerformanceRecord.uploaded_at.desc())
            .first()
        )

    def _performance_record_for_action(self, action: Action) -> PerformanceRecord | None:
        return self._period_performance_record(
            employee_id=action.employee_id,
            month=action.month,
            year=action.year,
        )

    @staticmethod
    def _effective_action_team(action: Action, record: PerformanceRecord | None = None) -> Team | None:
        """Resolve the team for an employee action's reporting period.

        Performance records preserve the team that owned the employee in the
        measured period. That snapshot is authoritative for month-specific
        corrective-action filtering; legacy rows then fall back to the
        employee's current team and finally the action's stored team.
        """
        if record and record.team:
            return record.team
        if action.employee and action.employee.team:
            return action.employee.team
        return action.team

    def _score_snapshot(
        self,
        action: Action,
        record: PerformanceRecord | None = None,
    ) -> tuple[float | None, str | None]:
        if not action.employee_id:
            return None, None
        record = record or self._performance_record_for_action(action)
        if not record:
            return None, None
        score = float(record.score) if isinstance(record.score, (Decimal, int, float)) else None
        return score, record.grade or None

    def serialize(
        self,
        action: Action,
        *,
        effective_team: Team | None = None,
        performance_record: PerformanceRecord | None = None,
    ) -> dict[str, Any]:
        performance_record = performance_record or self._performance_record_for_action(action)
        score, grade = self._score_snapshot(action, performance_record)
        created_by = action.created_by_user
        timestamp = action.created_at or dt.datetime.now(dt.timezone.utc)
        display_team = effective_team or self._effective_action_team(action, performance_record)
        payload = {
            "id": str(action.id),
            "employee_id": action.employee.employee_id if action.employee else None,
            "employee_name": action.employee.name if action.employee else None,
            "team": display_team.display_name or display_team.name if display_team else None,
            "branch_key": action.branch_key,
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
        payload.update(self._follow_up_metadata(action))
        return payload

    def list_all(self) -> list[dict[str, Any]]:
        # Planning reuses Action, while this legacy workspace remains
        # employee-specific and keeps its existing response contract.
        return [
            self.serialize(action)
            for action in self.actions.list_active()
            if action.employee_id is not None
        ]

    def list_scoped(self, scope: dict) -> list[dict[str, Any]]:
        scoped_actions: list[dict[str, Any]] = []
        for action in self.actions.list_active():
            if action.employee_id is None or action.employee is None:
                continue
            if scope.get("role") in {"Agent", "Executive", "Employee"}:
                if str(action.employee.employee_id) != str(scope.get("employee_id") or ""):
                    continue
                try:
                    scoped_actions.append(self.serialize(action))
                except Exception:
                    logger.exception("Skipping unreadable corrective action %s", action.id)
                continue
            if scope.get("role") == "Branch Director" and action.branch_key not in scope.get("accessible_branches", []):
                continue
            performance_record = self._performance_record_for_action(action)
            effective_team = self._effective_action_team(action, performance_record)
            if scope.get("role") == "Regional Manager" and not self._regional_action_in_scope(
                action, performance_record, scope
            ):
                continue
            if not effective_team or not user_can_access_team_level(
                scope,
                logical_team_name(effective_team),
                action.employee.performance_level,
            ):
                continue
            try:
                scoped_actions.append(
                    self.serialize(
                        action,
                        effective_team=effective_team,
                        performance_record=performance_record,
                    )
                )
            except Exception:
                logger.exception("Skipping unreadable corrective action %s", action.id)
        return scoped_actions

    def ensure_employee_scope(self, employee_identifier: str, scope: dict) -> Employee:
        employee = self._employee(employee_identifier)
        if scope.get("role") == "Branch Director":
            allowed = set(scope.get("accessible_branches", []))
            has_scoped_record = bool(
                allowed
                and self.db.query(PerformanceRecord.id)
                .filter(PerformanceRecord.employee_id == employee.id, PerformanceRecord.branch_key.in_(allowed))
                .first()
            )
            if not has_scoped_record:
                raise PermissionError("The employee has no performance evidence in your assigned branches")
        elif scope.get("role") in {"Agent", "Executive", "Employee"}:
            if str(employee.employee_id) != str(scope.get("employee_id") or ""):
                raise PermissionError("The employee is outside your self-only profile scope")
        elif not user_can_access_team_level(scope, logical_team_name(employee.team), employee.performance_level):
            raise PermissionError("The employee is outside your authorized action scope")
        return employee

    def get_history(self, employee_identifier: str, scope: dict | None = None) -> list[dict[str, Any]]:
        employee = self._employee(employee_identifier)
        if scope is not None:
            self.ensure_employee_scope(employee_identifier, scope)
            return [
                action
                for action in self.list_scoped(scope)
                if str(action.get("employee_id") or "") == str(employee.employee_id)
            ]
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
        scope: dict | None = None,
        due_date: Any = _UNSET,
        owner_user_id: Any = _UNSET,
        priority: Any = _UNSET,
        linked_kpi_key: Any = _UNSET,
        plan_id: Any = _UNSET,
    ) -> tuple[dict[str, Any], bool]:
        month = month.strip()
        if not month:
            raise CorrectiveActionValidationError("Month is required")
        action_type, action_text = self.split_manager_action(manager_action)
        employee = self._employee(employee_identifier)
        period_record = self._period_performance_record(
            employee_id=employee.id,
            month=month,
            year=year or dt.datetime.now().year,
        )
        period_team = period_record.team if period_record and period_record.team else employee.team
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
                action.team_id = period_team.id
                action.branch_key = period_record.branch_key if period_record else None
                action.action_type = action_type
                action.action_text = action_text
                action.root_cause_note = manager_notes.strip() or None
                action.updated_by_user_id = actor_id
                action.updated_at = dt.datetime.now(dt.timezone.utc)
            else:
                action = Action(
                    id=parsed_action_id or uuid.uuid4(),
                    employee_id=employee.id,
                    team_id=period_team.id,
                    branch_key=period_record.branch_key if period_record else None,
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
            self._apply_tracking(
                action,
                employee=employee,
                period_team=period_team,
                scope=scope,
                due_date=due_date,
                owner_user_id=owner_user_id,
                priority=priority,
                linked_kpi_key=linked_kpi_key,
                plan_id=plan_id,
            )
            self.db.commit()
            self.db.refresh(action)
            return self.serialize(action), is_update
        except Exception:
            self.db.rollback()
            raise

    def update_status(
        self,
        action_id: str,
        *,
        status: str,
        scope: dict,
        completion_note: str | None = None,
        due_date: Any = _UNSET,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        parsed_action_id = self._uuid(action_id)
        action = self.actions.get_active(parsed_action_id) if parsed_action_id else None
        if not action:
            raise CorrectiveActionNotFoundError("Corrective Action not found")
        self._assert_can_update_status(action, scope)

        normalized = (status or "").strip()
        if normalized not in ACTION_STATUSES:
            raise CorrectiveActionValidationError("Status must be Open, In Progress, Completed, or Cancelled")
        note = (completion_note or "").strip()
        if normalized in {"Completed", "Cancelled"} and len(note) < 3:
            requirement = "completion note" if normalized == "Completed" else "cancellation reason"
            raise CorrectiveActionValidationError(f"A {requirement} of at least 3 characters is required")

        if due_date is not _UNSET and due_date not in (None, ""):
            parsed_due = self._coerce_date(due_date, "due_date")
            self._validate_due_not_before_creation(parsed_due, action)
            action.due_date = parsed_due

        previous_status = action.status
        previous = {
            "status": previous_status,
            "completed_at": self._iso(action.completed_at),
            "completion_note": action.completion_note,
            "due_date": self._iso(action.due_date),
        }
        action.status = normalized
        if normalized == "Completed":
            action.completion_note = note
            if previous_status != "Completed" or action.completed_at is None:
                action.completed_at = dt.datetime.now(dt.timezone.utc)
        elif normalized == "Cancelled":
            action.completion_note = note
        elif previous_status in {"Completed", "Cancelled"}:
            action.completed_at = None

        actor_id = self._uuid(user_id) or self._uuid(str(scope.get("user_id") or ""))
        action.updated_by_user_id = actor_id
        action.updated_at = dt.datetime.now(dt.timezone.utc)
        try:
            self.db.flush()
            AuditService.log_operation(
                self.db,
                table_name="actions",
                operation="UPDATE",
                record_id=str(action.id),
                old_values=previous,
                new_values={
                    "status": action.status,
                    "completed_at": self._iso(action.completed_at),
                    "completion_note": action.completion_note,
                    "due_date": self._iso(action.due_date),
                },
                performed_by_user_id=str(actor_id) if actor_id else None,
            )
            self.db.refresh(action)
            return self.serialize(action)
        except Exception:
            self.db.rollback()
            raise

    def list_follow_up(
        self,
        scope: dict,
        *,
        state: str | None = None,
        team: str | None = None,
        owner: str | None = None,
        month: str | None = None,
    ) -> dict[str, Any]:
        matched: list[dict[str, Any]] = []
        seen: set[uuid.UUID] = set()
        for action in self.actions.list_active():
            serialized = self._follow_up_candidate(action, scope)
            if serialized is None or action.id in seen:
                continue
            if team and str(serialized.get("team") or "").casefold() != team.strip().casefold():
                continue
            owner_id = (serialized.get("owner") or {}).get("id")
            if owner and owner_id != owner:
                continue
            if month and str(serialized.get("month") or "").casefold() != month.strip().casefold():
                continue
            seen.add(action.id)
            matched.append(serialized)

        summary = self._follow_up_summary(matched)
        selected = matched
        if state:
            selected = [item for item in matched if item.get("follow_up_state") == state.strip()]
        selected.sort(key=self._follow_up_sort_key)
        return {"summary": summary, "actions": selected}

    def list_owners(self, scope: dict) -> list[dict[str, str]]:
        if scope.get("role") in {"Regional Manager", "Branch Director", "Function Director", "Function Viewer", "Employee"}:
            return []
        users = (
            self.db.query(User)
            .filter(User.is_active.is_(True), User.role.in_(["Admin", "General Manager", "Manager", "Performance Team"]))
            .order_by(User.full_name.asc(), User.username.asc())
            .all()
        )
        owners = [user for user in users if self._caller_may_assign(user, scope)]
        return [
            {"id": str(user.id), "name": self._person_name(user), "role": user.role}
            for user in owners
        ]

    def _follow_up_candidate(self, action: Action, scope: dict) -> dict[str, Any] | None:
        if scope.get("role") == "Branch Director" and action.branch_key not in scope.get("accessible_branches", []):
            return None
        record = None
        effective_team = None
        if action.employee_id is not None and action.due_date is not None and action.employee is not None:
            record = self._performance_record_for_action(action)
            effective_team = self._effective_action_team(action, record)
            if scope.get("role") == "Regional Manager" and not self._regional_action_in_scope(
                action, record, scope
            ):
                return None
            if not effective_team or not user_can_access_team_level(
                scope,
                logical_team_name(effective_team),
                action.employee.performance_level,
            ):
                return None
        elif (
            action.employee_id is None
            and action.plan_id is not None
            and action.plan is not None
            and action.plan.is_active
            and self._can_access_plan(action.plan, scope)
        ):
            effective_team = action.team
        else:
            return None
        return self.serialize(action, effective_team=effective_team, performance_record=record)

    def _follow_up_summary(self, actions: list[dict[str, Any]]) -> dict[str, Any]:
        open_count = sum(item.get("status") == "Open" for item in actions)
        in_progress = sum(item.get("status") == "In Progress" for item in actions)
        completed = sum(item.get("status") == "Completed" for item in actions)
        denominator = open_count + in_progress + completed
        rate = round((completed / denominator) * 100, 1) if denominator else 0
        return {
            "overdue": sum(item.get("follow_up_state") == "overdue" for item in actions),
            "due_soon": sum(item.get("follow_up_state") == "due_soon" for item in actions),
            "open": open_count,
            "in_progress": in_progress,
            "completed_this_month": sum(self._completed_this_month(item) for item in actions),
            "completion_rate": rate,
        }

    def _completed_this_month(self, item: dict[str, Any]) -> bool:
        if item.get("status") != "Completed" or not item.get("completed_at"):
            return False
        try:
            completed = dt.datetime.fromisoformat(str(item["completed_at"]).replace("Z", "+00:00"))
        except ValueError:
            return False
        if completed.tzinfo is not None:
            completed = completed.astimezone(dt.timezone.utc)
        return completed.year == self.today.year and completed.month == self.today.month

    @staticmethod
    def _follow_up_sort_key(item: dict[str, Any]) -> tuple:
        state = str(item.get("follow_up_state") or "no_due_date")
        days = item.get("days_to_due")
        days_key = days if isinstance(days, int) else 10**9
        return (FOLLOW_UP_STATE_ORDER.get(state, 99), days_key, str(item.get("employee_name") or ""), str(item.get("id") or ""))

    def _follow_up_metadata(self, action: Action) -> dict[str, Any]:
        due = action.due_date
        days = (due - self.today).days if isinstance(due, dt.date) else None
        state = self._follow_up_state(action.status, due if isinstance(due, dt.date) else None)
        owner = None
        if action.owner is not None:
            owner = {"id": str(action.owner.id), "name": self._person_name(action.owner)}
        plan = None
        if action.plan is not None:
            plan = {"id": str(action.plan.id), "name": action.plan.name}
        return {
            "due_date": due.isoformat() if isinstance(due, dt.date) else None,
            "owner": owner,
            "priority": action.priority,
            "linked_kpi_key": action.linked_kpi_key,
            "plan": plan,
            "completion_note": action.completion_note,
            "completed_at": self._iso(action.completed_at),
            "is_overdue": state == "overdue",
            "days_to_due": days,
            "follow_up_state": state,
        }

    def _follow_up_state(self, status: str | None, due: dt.date | None) -> str:
        normalized = (status or "").strip()
        if normalized == "Completed":
            return "completed"
        if normalized == "Cancelled":
            return "cancelled"
        if due is None:
            return "no_due_date"
        days = (due - self.today).days
        if normalized in OPEN_ACTION_STATUSES and days < 0:
            return "overdue"
        if normalized in OPEN_ACTION_STATUSES and days <= DUE_SOON_WINDOW_DAYS:
            return "due_soon"
        return "upcoming"

    def _apply_tracking(
        self,
        action: Action,
        *,
        employee: Employee,
        period_team: Team,
        scope: dict | None,
        due_date: Any = _UNSET,
        owner_user_id: Any = _UNSET,
        priority: Any = _UNSET,
        linked_kpi_key: Any = _UNSET,
        plan_id: Any = _UNSET,
    ) -> None:
        supplied = {
            key: value
            for key, value in {
                "due_date": due_date,
                "owner_user_id": owner_user_id,
                "priority": priority,
                "linked_kpi_key": linked_kpi_key,
                "plan_id": plan_id,
            }.items()
            if value is not _UNSET
        }
        if not supplied:
            return

        if "due_date" in supplied:
            supplied["due_date"] = None if self._blank(supplied["due_date"]) else self._coerce_date(supplied["due_date"], "due_date")
        resulting_due = supplied["due_date"] if "due_date" in supplied else action.due_date
        owner_sent = "owner_user_id" in supplied and not self._blank(supplied["owner_user_id"])
        priority_sent = "priority" in supplied and not self._blank(supplied["priority"])
        plan_sent = "plan_id" in supplied and not self._blank(supplied["plan_id"])
        if (owner_sent or priority_sent) and resulting_due is None:
            raise CorrectiveActionValidationError("A due date is required when an owner or priority is provided")
        if (owner_sent or plan_sent) and scope is None:
            raise CorrectiveActionValidationError("A user scope is required to assign an owner or plan")
        if "due_date" in supplied and supplied["due_date"] is not None:
            self._validate_due_not_before_creation(supplied["due_date"], action)

        if owner_sent:
            owner = self._active_user(supplied["owner_user_id"])
            team_name = logical_team_name(period_team or employee.team)
            if not self._assignable_owner(owner, scope or {}, team_name, employee.performance_level):
                raise CorrectiveActionValidationError("The selected owner must be an active user who can access the employee's team")
            action.owner_user_id = owner.id
        elif "owner_user_id" in supplied:
            action.owner_user_id = None

        if priority_sent:
            chosen = str(supplied["priority"]).strip()
            if chosen not in ACTION_PRIORITIES:
                raise CorrectiveActionValidationError("Priority must be Low, Medium, or High")
            action.priority = chosen
        elif "priority" in supplied:
            action.priority = None

        if "linked_kpi_key" in supplied:
            action.linked_kpi_key = None if self._blank(supplied["linked_kpi_key"]) else str(supplied["linked_kpi_key"]).strip()[:100]

        if plan_sent:
            plan = self._accessible_plan(supplied["plan_id"], scope or {}, employee, period_team)
            action.plan_id = plan.id
        elif "plan_id" in supplied:
            action.plan_id = None

        if "due_date" in supplied:
            action.due_date = supplied["due_date"]

    def _assert_can_update_status(self, action: Action, scope: dict) -> None:
        role = scope.get("role")
        if role in {"Executive", "Viewer", "Regional Manager", "Branch Director", "Function Director", "Employee"} or not scope:
            raise CorrectiveActionAccessError("You do not have permission to update this action")
        if role in {"Admin", "General Manager", "Performance Team"} or scope.get("has_unrestricted_team_access"):
            return
        if action.owner_user_id and str(action.owner_user_id) == str(scope.get("user_id") or ""):
            return
        if role == "Manager" and self._action_in_manager_scope(action, scope):
            return
        raise CorrectiveActionAccessError("You do not have permission to update this action")

    def _action_in_manager_scope(self, action: Action, scope: dict) -> bool:
        if action.employee is not None:
            record = self._performance_record_for_action(action)
            team = self._effective_action_team(action, record)
            if team and user_can_access_team_level(scope, logical_team_name(team), action.employee.performance_level):
                return True
        if action.plan is not None and self._can_access_plan(action.plan, scope):
            return True
        if action.team is not None:
            return user_can_access_team(scope, logical_team_name(action.team))
        return False

    def _assignable_owner(self, owner: User, scope: dict, team_name: str, performance_level: str | None) -> bool:
        if not owner.is_active:
            return False
        if not self._caller_may_assign(owner, scope, team_name):
            return False
        return self._owner_covers_team(owner, scope, team_name, performance_level)

    def _caller_may_assign(self, owner: User, scope: dict, team_name: str | None = None) -> bool:
        if not owner.is_active:
            return False
        if scope.get("role") in {"Admin", "General Manager"} or scope.get("has_unrestricted_team_access"):
            return True
        if str(owner.id) == str(scope.get("user_id") or ""):
            return True
        assignments = (
            self.db.query(UserTeamAssignment)
            .filter(UserTeamAssignment.user_id == owner.id)
            .all()
        )
        return any(
            assignment.team is not None
            and user_can_access_team(scope, logical_team_name(assignment.team))
            and (
                team_name is None
                or logical_team_name(assignment.team).casefold() == team_name.casefold()
            )
            for assignment in assignments
        )

    def _owner_covers_team(self, owner: User, scope: dict, team_name: str, performance_level: str | None) -> bool:
        level = performance_level or "Employee"
        if owner.role in {"Admin", "Performance Team"}:
            return True
        if str(owner.id) == str(scope.get("user_id") or "") and user_can_access_team_level(scope, team_name, level):
            return True
        assignments = (
            self.db.query(UserTeamAssignment)
            .filter(UserTeamAssignment.user_id == owner.id)
            .all()
        )
        owner_scope = {
            "role": "Admin" if owner.role == "Admin" else "Manager",
            "accessible_teams": [logical_team_name(item.team) for item in assignments if item.team is not None],
            "accessible_team_levels": [
                (logical_team_name(item.team), item.performance_level or level)
                for item in assignments
                if item.team is not None
            ],
            "legacy_unscoped": False,
            "has_unrestricted_team_access": False,
        }
        return user_can_access_team_level(owner_scope, team_name, level)

    def _can_access_plan(self, plan: PerformancePlan, scope: dict) -> bool:
        role = scope.get("role")
        if role in {"Admin", "General Manager", "Performance Team"} or scope.get("has_unrestricted_team_access"):
            return True
        team_name = logical_team_name(plan.team) if plan.team is not None else ""
        if role == "Branch Director":
            return bool(plan.branch_key and plan.branch_key in scope.get("accessible_branches", []))
        if role == "Regional Manager":
            return user_can_access_region(scope, plan.region)
        if role in {"Manager", "Function Director", "Function Viewer"}:
            return user_can_access_team_level(scope, team_name, plan.performance_level)
        return bool(plan.employee and str(plan.employee.employee_id) == str(scope.get("employee_id") or ""))

    def _regional_action_in_scope(self, action: Action, record: PerformanceRecord | None, scope: dict) -> bool:
        if record is not None:
            return bool(filter_records_by_scope([record], scope))
        plan = action.plan
        return bool(plan and self._can_access_plan(plan, scope) and user_can_access_region(scope, plan.region))

    def _accessible_plan(self, plan_id: Any, scope: dict, employee: Employee, period_team: Team) -> PerformancePlan:
        parsed = self._uuid(str(plan_id))
        plan = self.db.query(PerformancePlan).filter(PerformancePlan.id == parsed, PerformancePlan.is_active.is_(True)).first() if parsed else None
        if plan is None:
            raise CorrectiveActionValidationError("The linked plan was not found")
        if not self._can_access_plan(plan, scope):
            raise CorrectiveActionAccessError("The linked plan is outside your authorized scope")
        plan_team = logical_team_name(plan.team) if plan.team is not None else ""
        allowed = {logical_team_name(employee.team).casefold(), logical_team_name(period_team).casefold()}
        if plan_team.casefold() not in allowed:
            raise CorrectiveActionValidationError("The linked plan must belong to the employee's team")
        return plan

    def _active_user(self, user_id: Any) -> User:
        parsed = self._uuid(str(user_id))
        user = self.db.query(User).filter(User.id == parsed).first() if parsed else None
        if user is None or not user.is_active:
            raise CorrectiveActionValidationError("The selected owner must be an active user who can access the employee's team")
        return user

    def _validate_due_not_before_creation(self, due: dt.date, action: Action) -> None:
        created = self._creation_date(action)
        if due < created:
            raise CorrectiveActionValidationError("Due date cannot be earlier than the date the action was created")

    def _creation_date(self, action: Action) -> dt.date:
        created = action.created_at
        if isinstance(created, dt.datetime):
            return created.date()
        if isinstance(created, dt.date):
            return created
        return self.today

    def _coerce_date(self, value: Any, field_name: str) -> dt.date:
        if isinstance(value, dt.datetime):
            return value.date()
        if isinstance(value, dt.date):
            return value
        try:
            return dt.date.fromisoformat(str(value)[:10])
        except ValueError as exc:
            raise CorrectiveActionValidationError(f"Invalid {field_name}") from exc

    @staticmethod
    def _blank(value: Any) -> bool:
        return value is None or (isinstance(value, str) and not str(value).strip())

    @staticmethod
    def _person_name(user: User) -> str:
        full_name = str(user.full_name or "").strip()
        return full_name or user.username

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
