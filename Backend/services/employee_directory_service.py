from __future__ import annotations

from sqlalchemy import and_, case, false, func, or_
from sqlalchemy.orm import Session, joinedload

from models.models import Employee, PerformanceRecord, Team
from utils.report_scope import (
    FUNCTION_SCOPED_ROLES, GLOBAL_DATA_ROLES, SELF_SCOPED_ROLES,
    _team_keys, user_can_access_team_level,
)
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
        scope: dict | None = None,
    ) -> list[dict]:
        query = self.db.query(Employee).options(joinedload(Employee.team)).join(Team)
        if scope and scope.get("role") == "Branch Director" and not scope.get("legacy_unscoped"):
            return self._branch_list(scope, include_deleted=include_deleted, name=name, team=team,
                                     performance_level=performance_level, position=position, region=region)
        query = self._apply_scope(query, scope)
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

    @staticmethod
    def _apply_scope(query, scope: dict | None):
        if not scope or scope.get("legacy_unscoped"):
            return query
        role = scope.get("role")
        team_name = func.lower(func.coalesce(Team.display_name, Team.name))
        if role in FUNCTION_SCOPED_ROLES:
            keys = {key for name in scope.get("accessible_functions", []) for key in _team_keys(name)}
            return query.filter(team_name.in_(keys)) if keys else query.filter(false())
        if role in GLOBAL_DATA_ROLES or (role == "Manager" and scope.get("has_unrestricted_team_access")):
            return query
        if role in SELF_SCOPED_ROLES:
            self_id = str(scope.get("employee_id") or "").strip()
            return query.filter(Employee.employee_id == self_id) if self_id else query.filter(false())
        if role == "Regional Manager":
            regions = {str(value).strip().casefold() for value in scope.get("accessible_regions", [])}
            return query.filter(func.lower(Employee.region).in_(regions)) if regions else query.filter(false())
        if role != "Manager":
            return query.filter(false())
        keys = {key for name in scope.get("accessible_teams", []) for key in _team_keys(name)}
        query = query.filter(team_name.in_(keys)) if keys else query.filter(false())
        assignments = scope.get("accessible_team_levels") or []
        if assignments:
            clauses = [and_(team_name.in_(_team_keys(name)),
                            func.lower(Employee.performance_level) == str(level).casefold())
                       for name, level in assignments]
            query = query.filter(or_(*clauses))
        return query

    def _branch_list(self, scope: dict, *, include_deleted: bool, name: str | None,
                     team: str | None, performance_level: str | None,
                     position: str | None, region: str | None) -> list[dict]:
        """Project metadata from the latest authorized row, not another branch."""
        branches = {str(value).strip().casefold() for value in scope.get("accessible_branches", [])}
        if not branches:
            return []
        months = {month: number for number, month in enumerate(
            ("January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"), 1)}
        rows = self.db.query(
            PerformanceRecord.employee_id.label("person_id"),
            func.coalesce(Team.display_name, Team.name).label("team"),
            func.coalesce(PerformanceRecord.region, Team.region).label("region"),
            PerformanceRecord.performance_level.label("level"),
            PerformanceRecord.position_name.label("position"),
            func.row_number().over(partition_by=PerformanceRecord.employee_id, order_by=(
                PerformanceRecord.year.desc(), case(months, value=PerformanceRecord.month, else_=0).desc(),
                PerformanceRecord.uploaded_at.desc(), PerformanceRecord.id.desc(),
            )).label("rank"),
        ).join(Team, Team.id == PerformanceRecord.team_id).filter(
            func.lower(PerformanceRecord.branch_key).in_(branches), Team.is_active.is_(True),
        ).subquery()
        query = self.db.query(Employee, rows.c.team, rows.c.region, rows.c.level, rows.c.position).join(
            rows, rows.c.person_id == Employee.id,
        ).filter(rows.c.rank == 1)
        if not include_deleted:
            query = query.filter(Employee.is_active.is_(True))
        if name:
            pattern = f"%{name.strip()}%"
            query = query.filter(or_(Employee.name.ilike(pattern), Employee.employee_id.ilike(pattern)))
        for value, column in ((team, rows.c.team), (region, rows.c.region),
                              (performance_level, rows.c.level), (position, rows.c.position)):
            if value:
                query = query.filter(func.lower(column) == value.strip().casefold())
        return [{"id": employee.employee_id, "employee_id": employee.employee_id,
                 "name": employee.name, "team": team_name, "region": region_name,
                 "performance_level": level, "position": position_name,
                 "status": "Active" if employee.is_active else "Inactive"}
                for employee, team_name, region_name, level, position_name
                in query.order_by(Employee.name.asc()).all()]

    @staticmethod
    def _ensure_write_scope(team: Team, level: str, scope: dict | None) -> None:
        if scope is not None and not user_can_access_team_level(scope, logical_team_name(team), level):
            raise PermissionError("Access denied for this team and performance level")

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

    def create(self, *, employee_id: str, name: str, team: str, region: str, scope: dict | None = None) -> dict:
        team_model = self._team(team)
        if not team_model:
            raise LookupError("Team not found")
        self._ensure_write_scope(team_model, "Employee", scope)
        if self.get_model(employee_id, include_deleted=True):
            raise ValueError("Employee already exists")
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
        scope: dict | None = None,
    ) -> dict:
        employee = self.get_model(identifier)
        if not employee:
            raise LookupError("Employee not found")
        self._ensure_write_scope(employee.team, employee.performance_level, scope)
        # Authorize the destination before mutating *any* source fields.
        team_model = self._team(team) if team is not None else employee.team
        if not team_model:
            raise LookupError("Team not found")
        self._ensure_write_scope(team_model, employee.performance_level, scope)
        if name is not None:
            employee.name = name.strip()
        if team is not None:
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
