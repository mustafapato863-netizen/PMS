from uuid import UUID

from sqlalchemy.orm import Session, joinedload
from repositories.base_repository import BaseRepository
from models.models import Action, PerformancePlan
import logging

logger = logging.getLogger(__name__)


class ActionRepository(BaseRepository[Action]):
    """Repository for Action model"""

    def __init__(self, db: Session, model: type = Action):
        super().__init__(db, model)

    def list_active(self) -> list[Action]:
        return (
            self.db.query(Action)
            .options(
                joinedload(Action.employee),
                joinedload(Action.team),
                joinedload(Action.created_by_user),
                joinedload(Action.owner),
                joinedload(Action.plan).selectinload(PerformancePlan.milestones),
            )
            .filter(Action.is_active.is_(True))
            .order_by(Action.created_at.desc())
            .all()
        )

    def get_active(self, action_id: UUID) -> Action | None:
        return (
            self.db.query(Action)
            .options(
                joinedload(Action.employee),
                joinedload(Action.team),
                joinedload(Action.created_by_user),
            )
            .filter(Action.id == action_id, Action.is_active.is_(True))
            .first()
        )

    def list_active_by_employee(self, employee_id: UUID) -> list[Action]:
        return (
            self.db.query(Action)
            .options(
                joinedload(Action.employee),
                joinedload(Action.team),
                joinedload(Action.created_by_user),
            )
            .filter(Action.employee_id == employee_id, Action.is_active.is_(True))
            .order_by(Action.created_at.desc())
            .all()
        )

    def add(self, action: Action) -> None:
        self.db.add(action)
    
    def get_by_employee(self, employee_id) -> list:
        """Get all actions for employee"""
        return self.db.query(Action).filter(Action.employee_id == employee_id).all()
    
    def get_by_team(self, team_id) -> list:
        """Get all actions for team"""
        return self.db.query(Action).filter(Action.team_id == team_id).all()
    
    def get_by_team_month(self, team_id, month: str, year: int) -> list:
        """Get actions for team in specific month"""
        return self.db.query(Action).filter(
            (Action.team_id == team_id) &
            (Action.month == month) &
            (Action.year == year)
        ).all()

    def get_active_team_summary(self, team_id, month: str, year: int) -> Action | None:
        return self.db.query(Action).filter(
            Action.team_id == team_id,
            Action.employee_id.is_(None),
            Action.month == month,
            Action.year == year,
            Action.action_type == "Team Action",
            Action.is_active.is_(True),
        ).order_by(Action.updated_at.desc(), Action.created_at.desc()).first()
    
    def get_by_status(self, status: str) -> list:
        """Get actions by status"""
        return self.db.query(Action).filter(Action.status == status).all()
    
    def get_by_type(self, action_type: str) -> list:
        """Get actions by type"""
        return self.db.query(Action).filter(Action.action_type == action_type).all()
    
    def get_open_actions(self) -> list:
        """Get all open actions"""
        return self.db.query(Action).filter(
            Action.status.in_(['Open', 'In Progress'])
        ).all()
    
    def count_by_status(self, status: str) -> int:
        """Count actions by status"""
        return self.db.query(Action).filter(Action.status == status).count()
    
    def count_by_type(self, action_type: str) -> int:
        """Count actions by type"""
        return self.db.query(Action).filter(Action.action_type == action_type).count()
    
    def get_employee_actions_month(self, employee_id, month: str, year: int) -> list:
        """Get actions for employee in specific month"""
        return self.db.query(Action).filter(
            (Action.employee_id == employee_id) &
            (Action.month == month) &
            (Action.year == year)
        ).all()
