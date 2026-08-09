from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from models.models import Employee, Team
from utils.team_identity import logical_team_name


class EmployeeDirectoryService:
    """SQL-backed employee directory used by search and administration APIs."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def serialize(employee: Employee) -> dict:
        return {
            "id": employee.employee_id,
            "employee_id": employee.employee_id,
            "name": employee.name,
            "team": logical_team_name(employee.team),
            "region": employee.region,
            "performance_level": employee.performance_level,
            "position": employee.position_name,
            "status": "Active" if employee.is_active else "Inactive",
        }

    def list(
        self,
        *,
        include_deleted: bool = False,
        name: str | None = None,
        team: str | None = None,
        performance_level: str | None = None,
        position: str | None = None,
        region: str | None = None,
    ) -> list[dict]:
        query = self.db.query(Employee).options(joinedload(Employee.team)).join(Team)
        if not include_deleted:
            query = query.filter(Employee.is_active.is_(True))
        if name:
            pattern = f"%{name.strip()}%"
            query = query.filter(or_(Employee.name.ilike(pattern), Employee.employee_id.ilike(pattern)))
        if team:
            normalized = team.strip().casefold()
            query = query.filter(or_(
                func.lower(func.coalesce(Team.display_name, Team.name)) == normalized,
                func.lower(Team.name) == normalized,
                func.lower(Team.db_name) == normalized,
            ))
        if performance_level:
            query = query.filter(func.lower(Employee.performance_level) == performance_level.casefold())
        if position:
            query = query.filter(func.lower(func.coalesce(Employee.position_name, "")) == position.casefold())
        if region:
            query = query.filter(func.lower(Employee.region) == region.casefold())
        return [self.serialize(employee) for employee in query.order_by(Employee.name.asc()).all()]

    def get_model(self, identifier: str, *, include_deleted: bool = False) -> Employee | None:
        query = self.db.query(Employee).options(joinedload(Employee.team)).filter(
            Employee.employee_id == identifier.strip()
        )
        if not include_deleted:
            query = query.filter(Employee.is_active.is_(True))
        return query.first()

    def _team(self, reference: str) -> Team | None:
        normalized = reference.strip().casefold()
        return self.db.query(Team).filter(
            Team.is_active.is_(True),
            Team.team_level == "employee",
            or_(
                func.lower(func.coalesce(Team.display_name, Team.name)) == normalized,
                func.lower(Team.name) == normalized,
                func.lower(Team.db_name) == normalized,
            ),
        ).first()

    def create(self, *, employee_id: str, name: str, team: str, region: str) -> dict:
        if self.get_model(employee_id, include_deleted=True):
            raise ValueError("Employee already exists")
        team_model = self._team(team)
        if not team_model:
            raise LookupError("Team not found")
        employee = Employee(
            employee_id=employee_id.strip(),
            name=name.strip(),
            team_id=team_model.id,
            region=region.strip() or team_model.region,
            performance_level="Employee",
            is_active=True,
        )
        try:
            self.db.add(employee)
            self.db.commit()
            self.db.refresh(employee)
            employee.team = team_model
            return self.serialize(employee)
        except Exception:
            self.db.rollback()
            raise

    def update(
        self,
        identifier: str,
        *,
        name: str | None = None,
        team: str | None = None,
        region: str | None = None,
    ) -> dict:
        employee = self.get_model(identifier)
        if not employee:
            raise LookupError("Employee not found")
        if name is not None:
            employee.name = name.strip()
        if team is not None:
            team_model = self._team(team)
            if not team_model:
                raise LookupError("Team not found")
            employee.team_id = team_model.id
            employee.team = team_model
        if region is not None:
            employee.region = region.strip()
        try:
            self.db.commit()
            self.db.refresh(employee)
            return self.serialize(employee)
        except Exception:
            self.db.rollback()
            raise
