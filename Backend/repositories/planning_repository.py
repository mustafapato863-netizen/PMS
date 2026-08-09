from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session, joinedload, selectinload

from models.models import PerformancePlan, PlanObjective, PlanKPI, PlanMilestone, PlanNote, Action


class PlanningRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, plan: PerformancePlan) -> None:
        self.db.add(plan)

    def deactivate(self, plan: PerformancePlan) -> None:
        plan.is_active = False

    def list_active(self) -> list[PerformancePlan]:
        return self.db.query(PerformancePlan).options(joinedload(PerformancePlan.team), joinedload(PerformancePlan.employee), joinedload(PerformancePlan.owner), selectinload(PerformancePlan.objectives), selectinload(PerformancePlan.kpis), selectinload(PerformancePlan.milestones), selectinload(PerformancePlan.actions), selectinload(PerformancePlan.notes)).filter(PerformancePlan.is_active.is_(True)).order_by(PerformancePlan.updated_at.desc()).all()

    def get(self, plan_id: UUID) -> PerformancePlan | None:
        return self.db.query(PerformancePlan).options(joinedload(PerformancePlan.team), joinedload(PerformancePlan.employee), joinedload(PerformancePlan.owner), selectinload(PerformancePlan.objectives).joinedload(PlanObjective.owner), selectinload(PerformancePlan.objectives).selectinload(PlanObjective.kpi_links), selectinload(PerformancePlan.kpis), selectinload(PerformancePlan.milestones).joinedload(PlanMilestone.owner), selectinload(PerformancePlan.actions).joinedload(Action.owner), selectinload(PerformancePlan.notes).joinedload(PlanNote.author), selectinload(PerformancePlan.insight_links)).filter(PerformancePlan.id == plan_id, PerformancePlan.is_active.is_(True)).first()

    def get_item(self, kind: str, item_id: UUID):
        model = {"objective": PlanObjective, "kpi": PlanKPI, "action": Action, "milestone": PlanMilestone}.get(kind)
        return self.db.query(model).filter(model.id == item_id).first() if model else None

    def add_milestone(self, milestone: PlanMilestone) -> None:
        self.db.add(milestone)

    def delete_milestone(self, milestone: PlanMilestone) -> None:
        self.db.delete(milestone)
