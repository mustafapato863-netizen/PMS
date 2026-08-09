from datetime import date, datetime, timezone
from decimal import Decimal
import uuid
from typing import List, Dict, Any

from sqlalchemy.orm import Session

from models.models import (
    Action, AuditLog, Employee, PerformancePlan, PlanInsightLink, PlanKPI,
    PlanMilestone, PlanNote, PlanObjective, PlanObjectiveKPI, Team, User,
    UserTeamAssignment,
)
from models.planning_schemas import (
    PlanCreate,
    PlanItemUpdate,
    PlanMilestoneCreate,
    PlanMilestoneUpdate,
    PlanNoteCreate,
    PlanUpdate,
)
from models.schemas import PerformanceRecord
from repositories.base import PerformanceRepository
from repositories.planning_repository import PlanningRepository
from services.dashboard_record_service import DashboardRecordService
from services.management_bsc_service import ManagementBSCService
from utils.report_scope import (
    filter_records_by_scope,
    filter_records_by_team_levels,
    user_can_access_team,
    user_can_access_team_level,
)
from utils.team_identity import get_scoped_team, logical_team_name

MONTH_ORDER = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12
}

class PlanningAccessError(PermissionError): pass
class PlanningNotFoundError(LookupError): pass
class PlanningValidationError(ValueError): pass


class PlanningService:
    def __init__(self, performance_repo: PerformanceRepository, db: Session | None = None):
        self.performance_repo = performance_repo
        self.db = db
        self.plans = PlanningRepository(db) if db is not None else None

    def classify_all(self, month: str, performance_level: str | None = None) -> Dict[str, List[PerformanceRecord]]:
        """
        Classifies all employee performance records for the target month into planning categories.
        Returns:
          - categories (dict): Map of category name to list of PerformanceRecord
        """
        all_records = self.performance_repo.get_all()
        if performance_level:
            all_records = [r for r in all_records if r.performance_level == performance_level]
        return self.classify_records(all_records, month=month)

    def classify_records(
        self,
        all_records: List[PerformanceRecord],
        *,
        month: str,
        year: int | None = None,
    ) -> Dict[str, List[PerformanceRecord]]:
        """Classify an already-authorized record set without loading a second data source."""
        month_records = [
            r for r in all_records
            if r.month == month and (year is None or getattr(r, "year", None) == year)
        ]
        
        # Group records by employee to analyze history
        employee_history: Dict[str, List[PerformanceRecord]] = {}
        for r in all_records:
            employee_history.setdefault(r.employee_id, []).append(r)

        # Sort each employee's history chronologically
        for emp_id in employee_history:
            employee_history[emp_id].sort(
                key=lambda x: (getattr(x, "year", None) or 0, MONTH_ORDER.get(x.month, 0))
            )

        categories = {
            "Reward Candidate": [],
            "Promotion Candidate": [],
            "Training Candidate": [],
            "PI Candidate": [],
            "SIP Candidate": [],
            "Attrition Risk": []
        }

        for r in month_records:
            emp_id = r.employee_id
            history = employee_history.get(emp_id, [])
            
            # Find current index in history
            curr_idx = -1
            for idx, hist_r in enumerate(history):
                if hist_r.month == month and (year is None or getattr(hist_r, "year", None) == year):
                    curr_idx = idx
                    break

            # 1. Reward Candidate: Score >= 95 and Attendance >= 95%
            # attend_rate is actual.attend_rate (0-1)
            if r.evaluation.score >= 95.0 and r.actual.attend_rate >= 0.95:
                categories["Reward Candidate"].append(r)

            # 2. Promotion Candidate: Score >= 90 maintained for 3 consecutive months
            # Check if this month and preceding 2 months are all >= 90
            if r.evaluation.score >= 90.0:
                if curr_idx >= 2:
                    h_prev1 = history[curr_idx - 1]
                    h_prev2 = history[curr_idx - 2]
                    if h_prev1.evaluation.score >= 90.0 and h_prev2.evaluation.score >= 90.0:
                        categories["Promotion Candidate"].append(r)
                elif len(history) == 1:
                    # Fallback: if we only have 1 month and it's >= 90, but to be safe we require 3 months
                    pass

            # 3. Training Candidate: Score between 70 and 80, and Root Cause exists
            if 70.0 <= r.evaluation.score <= 80.0 and r.evaluation.root_cause is not None:
                categories["Training Candidate"].append(r)

            # 4. PI Candidate: Score between 50 and 60
            if 50.0 <= r.evaluation.score < 60.0:
                categories["PI Candidate"].append(r)

            # 5. SIP Candidate: Score below 50
            if r.evaluation.score < 50.0:
                categories["SIP Candidate"].append(r)

            # 6. Attrition Risk:
            # - Attendance decline > 20% MoM
            # - Performance decline > 15% MoM
            # - Continuous deterioration for 3 months (Month N-2 > Month N-1 > Month N)
            is_attrition = False
            
            if curr_idx >= 1:
                prev_r = history[curr_idx - 1]
                # Attendance decline (absolute difference, e.g. 0.95 to 0.70 is 0.25 decline)
                attend_decline = prev_r.actual.attend_rate - r.actual.attend_rate
                # Performance decline (absolute difference, e.g. 85.0 to 65.0 is 20.0 decline)
                perf_decline = prev_r.evaluation.score - r.evaluation.score
                
                if attend_decline > 0.20 or perf_decline > 15.0:
                    is_attrition = True

            # Continuous deterioration for 3 months (i.e. score decreasing over 3 consecutive data points)
            if not is_attrition and curr_idx >= 2:
                prev1 = history[curr_idx - 1]
                prev2 = history[curr_idx - 2]
                if prev2.evaluation.score > prev1.evaluation.score > r.evaluation.score:
                    is_attrition = True

            if is_attrition:
                categories["Attrition Risk"].append(r)

        return categories

    def _require_workspace(self) -> None:
        if self.db is None or self.plans is None:
            raise RuntimeError("Planning workspace requires a database session")

    @staticmethod
    def _number(value) -> float | None:
        return float(value) if isinstance(value, (Decimal, int, float)) else None

    @staticmethod
    def _objective_progress(objective: PlanObjective) -> float:
        current = PlanningService._number(objective.current_value)
        baseline = PlanningService._number(objective.baseline_value)
        target = PlanningService._number(objective.target_value)
        if current is None or baseline is None or target is None or target == baseline:
            return 100.0 if objective.status == "Completed" else 0.0
        ratio = (current - baseline) / (target - baseline)
        return round(max(0.0, min(1.0, ratio)) * 100, 1)

    @classmethod
    def progress(cls, plan: PerformancePlan) -> dict[str, Any]:
        components: list[tuple[str, float, float]] = []
        if plan.objectives:
            components.append(("objectives", 50, sum(cls._objective_progress(item) for item in plan.objectives) / len(plan.objectives)))
        if plan.actions:
            components.append(("actions", 30, sum(item.status in {"Completed", "Cancelled"} for item in plan.actions) / len(plan.actions) * 100))
        if plan.milestones:
            components.append(("milestones", 20, sum(item.status == "Completed" for item in plan.milestones) / len(plan.milestones) * 100))
        total_weight = sum(weight for _, weight, _ in components)
        overall = sum(weight * value for _, weight, value in components) / total_weight if total_weight else 0.0
        return {
            "overall": round(max(0, min(100, overall)), 1),
            "components": {name: round(value, 1) for name, _, value in components},
            "explanation": "50% objectives, 30% actions and 20% milestones; absent components are excluded and remaining weights are normalized.",
        }

    @classmethod
    def risk_reasons(cls, plan: PerformancePlan, progress: float, today: date | None = None) -> list[str]:
        today = today or date.today()
        reasons = []
        days_left = (plan.due_date - today).days
        if plan.status not in {"Completed", "Archived"} and 0 <= days_left <= 14 and progress < 70:
            reasons.append(f"Due in {days_left} days with only {progress:.0f}% progress")
        overdue_actions = sum(bool(item.due_date and item.due_date < today and item.status not in {"Completed", "Cancelled"}) for item in plan.actions)
        overdue_milestones = sum(item.due_date < today and item.status != "Completed" for item in plan.milestones)
        if overdue_actions: reasons.append(f"{overdue_actions} required action(s) overdue")
        if overdue_milestones: reasons.append(f"{overdue_milestones} milestone(s) overdue")
        current, baseline, target = map(cls._number, (plan.current_value, plan.baseline_value, plan.target_value))
        if current is not None and baseline is not None and target is not None:
            moving_away = current < baseline if plan.outcome_direction == "higher_better" else current > baseline
            if moving_away: reasons.append("Current result moved away from the plan target")
        return reasons

    def _can_access(self, plan: PerformancePlan, scope: dict) -> bool:
        if scope.get("role") == "Admin" or scope.get("is_general_manager"):
            return True
        team = logical_team_name(plan.team)
        if scope.get("role") == "Manager":
            return user_can_access_team_level(scope, team, plan.performance_level)
        return bool(plan.employee and str(plan.employee.employee_id) == str(scope.get("employee_id") or ""))

    def _validate_context(self, payload: PlanCreate, scope: dict):
        if not user_can_access_team(scope, payload.team) or not user_can_access_team_level(scope, payload.team, payload.performance_level):
            raise PlanningAccessError("The selected plan scope is outside your authorized teams or performance levels")
        team_level = "management" if payload.performance_level in {"Managerial", "Corporate"} else "employee"
        team = get_scoped_team(self.db, payload.team, team_level)
        if not team:
            raise PlanningNotFoundError("The selected team scope is not configured")
        employee = None
        if payload.employee_identifier:
            employee = self.db.query(Employee).filter(Employee.employee_id == payload.employee_identifier).first()
            if not employee or employee.team_id != team.id:
                raise PlanningValidationError("The selected employee does not belong to the plan team scope")
        owner = self.db.query(User).filter(User.id == payload.owner_user_id, User.is_active.is_(True)).first()
        if not owner or owner.role not in {"Admin", "Manager"}:
            raise PlanningValidationError("Plan owner is not an active planning owner")
        if not self._owner_allowed(owner, scope, payload.team):
            raise PlanningAccessError("The selected plan owner is outside your authorized team scope")
        if payload.region and team.region and payload.region.casefold() != team.region.casefold():
            raise PlanningValidationError("The selected region does not match the plan team scope")
        return team, employee, owner

    def _owner_allowed(self, owner: User, scope: dict, team_name: str | None = None) -> bool:
        if scope.get("role") == "Admin" or scope.get("is_general_manager"):
            return True
        if str(owner.id) == str(scope.get("user_id")):
            return True
        assignments = (
            self.db.query(UserTeamAssignment)
            .join(Team, UserTeamAssignment.team_id == Team.id)
            .filter(UserTeamAssignment.user_id == owner.id)
            .all()
        )
        return any(
            user_can_access_team(scope, logical_team_name(assignment.team))
            and (
                not team_name
                or logical_team_name(assignment.team).casefold() == team_name.casefold()
            )
            for assignment in assignments
        )

    def _audit(self, plan_id, operation: str, actor_id: str, old=None, new=None) -> None:
        self.db.add(AuditLog(id=uuid.uuid4(), table_name="performance_plans", operation=operation, record_id=plan_id, old_values=old, new_values=new, performed_by_user_id=uuid.UUID(actor_id)))

    def options(self, scope: dict) -> dict[str, Any]:
        self._require_workspace()
        records = [
            *DashboardRecordService(self.db).list_option_rows(),
            *ManagementBSCService(self.db).list_option_rows(),
        ]
        records = filter_records_by_scope(records, scope)
        records = filter_records_by_team_levels(records, scope)
        value = lambda record, key: record.get(key) if isinstance(record, dict) else getattr(record, key, None)
        teams = sorted({str(value(record, "team")) for record in records if value(record, "team")})
        users = self.db.query(User).filter(User.is_active.is_(True), User.role.in_(["Admin", "Manager"])).order_by(User.username).all()
        users = [user for user in users if self._owner_allowed(user, scope)]
        employees = {
            str(value(record, "employee_id")): {
                "id": str(value(record, "employee_id")),
                "name": str(value(record, "employee_name")),
                "team": str(value(record, "team")),
            }
            for record in records
            if value(record, "employee_id")
        }
        return {
            "teams": teams,
            "regions": sorted({str(value(r, "region")) for r in records if value(r, "region")}),
            "performance_levels": sorted({str(value(r, "performance_level")) for r in records if value(r, "performance_level")}),
            "positions": sorted({str(value(r, "position")) for r in records if value(r, "position")}),
            "employees": sorted(employees.values(), key=lambda item: item["name"]),
            "owners": [{"id": str(user.id), "name": user.username, "role": user.role} for user in users],
            "statuses": ["Draft", "In Progress", "At Risk", "Completed", "Archived"],
            "can_edit": scope.get("role") in {"Admin", "Manager"},
        }

    def create(self, payload: PlanCreate, scope: dict) -> PerformancePlan:
        self._require_workspace()
        team, employee, _owner = self._validate_context(payload, scope)
        if payload.insight_ids:
            from services.insights_service import InsightsService
            workspace = InsightsService(self.performance_repo, self, db=self.db).generate_workspace(scope, month=payload.evidence_month, year=payload.evidence_year, team=payload.team, performance_level=payload.performance_level, position=payload.position_name, employee_id=payload.employee_identifier)
            available = {item.id for item in workspace.priority_insights}
            if set(payload.insight_ids) - available:
                raise PlanningValidationError("One or more linked insights are unavailable in the authorized evidence period")
        actor_id = str(scope["user_id"])
        try:
            plan = PerformancePlan(name=payload.name, scope_type=payload.scope_type, team_id=team.id, performance_level=payload.performance_level, region=team.region, position_name=payload.position_name, employee_id=employee.id if employee else None, period_start=payload.period_start, period_end=payload.period_end, due_date=payload.due_date, owner_user_id=payload.owner_user_id, baseline_value=payload.baseline_value, target_value=payload.target_value, current_value=payload.current_value if payload.current_value is not None else payload.baseline_value, outcome_unit=payload.outcome_unit, outcome_direction=payload.outcome_direction, expected_impact=payload.expected_impact, status="In Progress" if payload.activate else "Draft", no_insight_reason=(payload.no_insight_reason or "").strip() or None, created_by_user_id=uuid.UUID(actor_id), updated_by_user_id=uuid.UUID(actor_id))
            self.plans.add(plan); self.db.flush()
            kpis = {}
            for item in payload.kpis:
                values = item.model_dump()
                if values["current_value"] is None: values["current_value"] = item.baseline_value
                row = PlanKPI(plan_id=plan.id, **values); self.db.add(row); self.db.flush(); kpis[item.kpi_key] = row
            objectives = []
            for item in payload.objectives:
                values = item.model_dump(exclude={"linked_kpi_keys"})
                if values["current_value"] is None: values["current_value"] = item.baseline_value
                objective = PlanObjective(plan_id=plan.id, status="Not Started", **values); self.db.add(objective); self.db.flush(); objectives.append(objective)
                for key in item.linked_kpi_keys:
                    if key not in kpis: raise PlanningValidationError(f"Objective references unknown KPI: {key}")
                    self.db.add(PlanObjectiveKPI(objective_id=objective.id, kpi_id=kpis[key].id))
            for item in payload.actions:
                if item.objective_index is not None and not 0 <= item.objective_index < len(objectives):
                    raise PlanningValidationError("Action references an unknown objective")
                employee_id = employee.id if employee else None
                if item.employee_identifier:
                    action_employee = self.db.query(Employee).filter(Employee.employee_id == item.employee_identifier, Employee.team_id == team.id).first()
                    if not action_employee: raise PlanningValidationError("Action employee is outside the plan scope")
                    employee_id = action_employee.id
                objective_id = objectives[item.objective_index].id if item.objective_index is not None else None
                self.db.add(Action(employee_id=employee_id, team_id=team.id, month=payload.period_start.strftime("%B"), year=payload.period_start.year, action_type=item.action_type, plan_title=item.title, action_text=item.description, status="Open", plan_id=plan.id, objective_id=objective_id, owner_user_id=item.owner_user_id, due_date=item.due_date, priority=item.priority, linked_kpi_key=item.linked_kpi_key, created_by_user_id=uuid.UUID(actor_id)))
            for item in payload.milestones: self.db.add(PlanMilestone(plan_id=plan.id, status="Pending", **item.model_dump()))
            for insight_id in payload.insight_ids: self.db.add(PlanInsightLink(plan_id=plan.id, insight_id=insight_id, evidence_month=payload.evidence_month, evidence_year=payload.evidence_year))
            self._audit(plan.id, "INSERT", actor_id, new={"name": plan.name, "status": plan.status}); self.db.commit()
            return self.plans.get(plan.id)
        except Exception:
            self.db.rollback(); raise

    def _serialize_card(self, plan: PerformancePlan) -> dict[str, Any]:
        progress = self.progress(plan); risks = self.risk_reasons(plan, progress["overall"])
        effective = "At Risk" if risks and plan.status == "In Progress" else plan.status
        return {"id": str(plan.id), "name": plan.name, "scope": plan.employee.name if plan.employee else plan.position_name or logical_team_name(plan.team), "scope_type": plan.scope_type, "team": logical_team_name(plan.team), "performance_level": plan.performance_level, "status": effective, "stored_status": plan.status, "risk_reasons": risks, "progress": progress, "owner": {"id": str(plan.owner.id), "name": plan.owner.username}, "period": f"{plan.period_start:%d %b %Y} – {plan.period_end:%d %b %Y}", "due_date": plan.due_date.isoformat(), "counts": {"objectives": len(plan.objectives), "actions": len(plan.actions), "kpis": len(plan.kpis), "milestones": len(plan.milestones), "notes": len(plan.notes)}, "updated_at": plan.updated_at.isoformat() if plan.updated_at else None}

    def list(self, scope: dict, team=None, owner_id=None, status=None, search=None) -> list[dict[str, Any]]:
        rows = [plan for plan in self.plans.list_active() if self._can_access(plan, scope)]
        cards = [self._serialize_card(plan) for plan in rows]
        return [card for card in cards if (not team or card["team"].casefold() == team.casefold()) and (not owner_id or card["owner"]["id"] == owner_id) and (not status or card["status"] == status) and (not search or search.casefold() in card["name"].casefold() or search.casefold() in card["scope"].casefold())]

    def get(self, plan_id: str, scope: dict) -> dict[str, Any]:
        self._require_workspace()
        try: parsed = uuid.UUID(plan_id)
        except ValueError: raise PlanningNotFoundError("Plan not found")
        plan = self.plans.get(parsed)
        if not plan: raise PlanningNotFoundError("Plan not found")
        if not self._can_access(plan, scope): raise PlanningAccessError("This plan is outside your authorized scope")
        data = self._serialize_card(plan)
        data.update({"summary": {"scope_type": plan.scope_type, "scope_name": data["scope"], "period": data["period"], "owner": data["owner"], "baseline": self._number(plan.baseline_value), "target": self._number(plan.target_value), "current": self._number(plan.current_value), "expected_impact": self._number(plan.expected_impact), "actual_impact": self._number(plan.actual_impact), "unit": plan.outcome_unit, "direction": plan.outcome_direction, "status_reason": plan.status_reason}, "objectives": [{"id": str(x.id), "name": x.name, "measurement_type": x.measurement_type, "baseline": self._number(x.baseline_value), "target": self._number(x.target_value), "current": self._number(x.current_value), "unit": x.unit, "direction": x.direction, "due_date": x.due_date.isoformat(), "owner": x.owner.username, "status": x.status, "required": x.is_required, "progress": self._objective_progress(x), "linked_kpis": [next((k.kpi_key for k in plan.kpis if k.id == link.kpi_id), "") for link in x.kpi_links]} for x in plan.objectives], "actions": [{"id": str(x.id), "title": x.plan_title or x.action_type, "action_type": x.action_type, "description": x.action_text, "owner": x.owner.username if x.owner else None, "due_date": x.due_date.isoformat() if x.due_date else None, "priority": x.priority, "status": x.status, "objective_id": str(x.objective_id) if x.objective_id else None, "linked_kpi": x.linked_kpi_key, "completion_note": x.completion_note, "evidence_reference": x.evidence_reference} for x in plan.actions], "kpis": [{"id": str(x.id), "key": x.kpi_key, "label": x.kpi_label, "unit": x.unit, "direction": x.direction, "baseline": self._number(x.baseline_value), "target": self._number(x.target_value), "current": self._number(x.current_value), "achievement": self._kpi_achievement(x), "gap": self._kpi_gap(x), "contribution": self._number(x.contribution), "data_period": f"{x.data_month} {x.data_year}" if x.data_month and x.data_year else None} for x in plan.kpis], "milestones": [{"id": str(x.id), "name": x.name, "due_date": x.due_date.isoformat(), "status": "Overdue" if x.due_date < date.today() and x.status != "Completed" else x.status, "completion_date": x.completion_date.isoformat() if x.completion_date else None, "owner_id": str(x.owner.id), "owner": x.owner.username, "note": x.note} for x in plan.milestones], "notes": [{"id": str(x.id), "author": x.author.username, "timestamp": x.created_at.isoformat(), "text": x.text, "review_period": f"{x.review_month} {x.review_year}" if x.review_month and x.review_year else None} for x in plan.notes], "linked_insights": self._resolve_insights(plan, scope)})
        return data

    @classmethod
    def _kpi_achievement(cls, kpi):
        current, target = cls._number(kpi.current_value), cls._number(kpi.target_value)
        if current is None or target is None or target == 0: return None
        return round((current / target if kpi.direction == "higher_better" else target / current if current else 0) * 100, 1)

    @classmethod
    def _kpi_gap(cls, kpi):
        current, target = cls._number(kpi.current_value), cls._number(kpi.target_value)
        return round(target - current, 2) if current is not None and target is not None else None

    def _resolve_insights(self, plan, scope):
        if not plan.insight_links: return []
        from services.insights_service import InsightsService
        first = plan.insight_links[0]
        workspace = InsightsService(self.performance_repo, self, db=self.db).generate_workspace(scope, month=first.evidence_month, year=first.evidence_year, team=logical_team_name(plan.team), performance_level=plan.performance_level, position=plan.position_name, employee_id=plan.employee.employee_id if plan.employee else None)
        by_id = {item.id: item for item in workspace.priority_insights}
        return [{"id": link.insight_id, "resolved": link.insight_id in by_id, **(by_id[link.insight_id].model_dump(include={"severity", "title", "explanation", "scope"}) if link.insight_id in by_id else {})} for link in plan.insight_links]

    def update(self, plan_id: str, payload: PlanUpdate, scope: dict) -> dict[str, Any]:
        data = self.get(plan_id, scope); plan = self.plans.get(uuid.UUID(plan_id))
        if scope.get("role") not in {"Admin", "Manager"}: raise PlanningAccessError("Plan editing is not permitted")
        try:
            values = payload.model_dump(exclude_none=True)
            if "owner_user_id" in values:
                owner = self.db.query(User).filter(User.id == values["owner_user_id"], User.is_active.is_(True)).first()
                if not owner or owner.role not in {"Admin", "Manager"}:
                    raise PlanningValidationError("Plan owner is not an active planning owner")
                if not self._owner_allowed(owner, scope, logical_team_name(plan.team)):
                    raise PlanningAccessError("The selected plan owner is outside your authorized team scope")
            if values.get("due_date") and values["due_date"] < plan.period_start:
                raise PlanningValidationError("Plan due date cannot be before the plan start date")
            if values.get("status") == "At Risk" and not (values.get("status_reason") or "").strip(): raise PlanningValidationError("Manual At Risk status requires a reason")
            if values.get("status") == "Completed":
                required = [x for x in plan.objectives if x.is_required]
                if any(x.status != "Completed" for x in required) or any(x.status not in {"Completed", "Cancelled"} for x in plan.actions) or not plan.notes or not (values.get("completion_note") or "").strip(): raise PlanningValidationError("Completion requires required objectives, closed actions, a review note and completion note")
                plan.completion_date = date.today(); plan.completed_by_user_id = uuid.UUID(scope["user_id"]); plan.actual_impact = (self._number(plan.current_value) or 0) - self._number(plan.baseline_value)
            old = {"status": plan.status, "name": plan.name}
            for key, value in values.items(): setattr(plan, key, value)
            plan.updated_by_user_id = uuid.UUID(scope["user_id"]); plan.updated_at = datetime.now(timezone.utc)
            self._audit(plan.id, "UPDATE", scope["user_id"], old=old, new=values); self.db.commit()
            return self.get(plan_id, scope)
        except Exception:
            self.db.rollback()
            raise

    def delete(self, plan_id: str, scope: dict) -> dict[str, str]:
        self.get(plan_id, scope)
        if scope.get("role") not in {"Admin", "Manager"}:
            raise PlanningAccessError("Plan deletion is not permitted")
        plan = self.plans.get(uuid.UUID(plan_id))
        result = {"id": str(plan.id), "name": plan.name}
        try:
            self.plans.deactivate(plan)
            plan.updated_by_user_id = uuid.UUID(scope["user_id"])
            plan.updated_at = datetime.now(timezone.utc)
            self._audit(plan.id, "DELETE", scope["user_id"], old={"name": plan.name, "status": plan.status, "is_active": True}, new={"is_active": False})
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    def _editable_plan(self, plan_id: str, scope: dict) -> PerformancePlan:
        self.get(plan_id, scope)
        if scope.get("role") not in {"Admin", "Manager"}:
            raise PlanningAccessError("Plan editing is not permitted")
        return self.plans.get(uuid.UUID(plan_id))

    def _validate_milestone_owner(self, owner_user_id, plan: PerformancePlan, scope: dict) -> User:
        owner = self.db.query(User).filter(User.id == owner_user_id, User.is_active.is_(True)).first()
        if not owner or owner.role not in {"Admin", "Manager"}:
            raise PlanningValidationError("Milestone owner is not an active planning owner")
        if not self._owner_allowed(owner, scope, logical_team_name(plan.team)):
            raise PlanningAccessError("The milestone owner is outside your authorized team scope")
        return owner

    @staticmethod
    def _validate_milestone_due_date(plan: PerformancePlan, due_date: date) -> None:
        if due_date < plan.period_start or due_date > plan.due_date:
            raise PlanningValidationError("Milestone due date must be within the plan start and due dates")

    def add_milestone(self, plan_id: str, payload: PlanMilestoneCreate, scope: dict) -> dict[str, Any]:
        plan = self._editable_plan(plan_id, scope)
        self._validate_milestone_owner(payload.owner_user_id, plan, scope)
        self._validate_milestone_due_date(plan, payload.due_date)
        values = payload.model_dump()
        status = values.pop("status")
        milestone = PlanMilestone(
            plan_id=plan.id,
            status=status,
            completion_date=date.today() if status == "Completed" else None,
            **values,
        )
        try:
            self.plans.add_milestone(milestone)
            plan.updated_by_user_id = uuid.UUID(scope["user_id"])
            plan.updated_at = datetime.now(timezone.utc)
            self._audit(plan.id, "UPDATE", scope["user_id"], old={"milestones": len(plan.milestones)}, new={"milestone_added": payload.name})
            self.db.commit()
            return self.get(plan_id, scope)
        except Exception:
            self.db.rollback()
            raise

    def update_milestone(self, plan_id: str, milestone_id: str, payload: PlanMilestoneUpdate, scope: dict) -> dict[str, Any]:
        plan = self._editable_plan(plan_id, scope)
        try:
            parsed_id = uuid.UUID(milestone_id)
        except ValueError as exc:
            raise PlanningNotFoundError("Milestone not found") from exc
        milestone = self.plans.get_item("milestone", parsed_id)
        if not milestone or milestone.plan_id != plan.id:
            raise PlanningNotFoundError("Milestone not found")
        values = payload.model_dump(exclude_unset=True)
        if values.get("owner_user_id") is not None:
            self._validate_milestone_owner(values["owner_user_id"], plan, scope)
        if values.get("due_date") is not None:
            self._validate_milestone_due_date(plan, values["due_date"])
        old = {"name": milestone.name, "status": milestone.status, "due_date": milestone.due_date.isoformat()}
        audit_values = {
            key: str(value) if isinstance(value, uuid.UUID) else value.isoformat() if isinstance(value, date) else value
            for key, value in values.items()
        }
        try:
            for key, value in values.items():
                setattr(milestone, key, value)
            if "status" in values:
                milestone.completion_date = date.today() if milestone.status == "Completed" else None
            plan.updated_by_user_id = uuid.UUID(scope["user_id"])
            plan.updated_at = datetime.now(timezone.utc)
            self._audit(plan.id, "UPDATE", scope["user_id"], old={"milestone": old}, new={"milestone": audit_values})
            self.db.commit()
            return self.get(plan_id, scope)
        except Exception:
            self.db.rollback()
            raise

    def delete_milestone(self, plan_id: str, milestone_id: str, scope: dict) -> dict[str, Any]:
        plan = self._editable_plan(plan_id, scope)
        try:
            parsed_id = uuid.UUID(milestone_id)
        except ValueError as exc:
            raise PlanningNotFoundError("Milestone not found") from exc
        milestone = self.plans.get_item("milestone", parsed_id)
        if not milestone or milestone.plan_id != plan.id:
            raise PlanningNotFoundError("Milestone not found")
        old = {"name": milestone.name, "status": milestone.status, "due_date": milestone.due_date.isoformat()}
        try:
            self.plans.delete_milestone(milestone)
            plan.updated_by_user_id = uuid.UUID(scope["user_id"])
            plan.updated_at = datetime.now(timezone.utc)
            self._audit(plan.id, "UPDATE", scope["user_id"], old={"milestone": old}, new={"milestone_deleted": str(milestone.id)})
            self.db.commit()
            return self.get(plan_id, scope)
        except Exception:
            self.db.rollback()
            raise

    def update_item(self, plan_id: str, kind: str, item_id: str, payload: PlanItemUpdate, scope: dict) -> dict[str, Any]:
        if kind == "milestone":
            if payload.status is not None and payload.status not in {"Pending", "In Progress", "Completed"}:
                raise PlanningValidationError("Milestone status is invalid")
            values = payload.model_dump(include={"status", "note"}, exclude_none=True)
            return self.update_milestone(
                plan_id,
                item_id,
                PlanMilestoneUpdate(**values),
                scope,
            )
        self.get(plan_id, scope)
        if scope.get("role") not in {"Admin", "Manager"}: raise PlanningAccessError("Plan editing is not permitted")
        item = self.plans.get_item(kind, uuid.UUID(item_id))
        if not item or str(getattr(item, "plan_id", "")) != plan_id: raise PlanningNotFoundError("Plan item not found")
        allowed = {"objective": {"status", "current_value"}, "kpi": {"current_value"}, "action": {"status", "completion_note"}, "milestone": {"status", "note"}}[kind]
        for key, value in payload.model_dump(exclude_none=True).items():
            if key in allowed: setattr(item, key, value)
        if kind == "milestone" and item.status == "Completed": item.completion_date = date.today()
        self.db.commit(); return self.get(plan_id, scope)

    def add_note(self, plan_id: str, payload: PlanNoteCreate, scope: dict) -> dict[str, Any]:
        self.get(plan_id, scope)
        if scope.get("role") not in {"Admin", "Manager"}: raise PlanningAccessError("Adding plan notes is not permitted")
        self.db.add(PlanNote(plan_id=uuid.UUID(plan_id), author_user_id=uuid.UUID(scope["user_id"]), **payload.model_dump())); self.db.commit()
        return self.get(plan_id, scope)
