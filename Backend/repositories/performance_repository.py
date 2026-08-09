from sqlalchemy.orm import Session, selectinload
from repositories.base_repository import BaseRepository
from sqlalchemy import func, or_

from models.models import PerformanceRecord, Employee, Team
import logging

logger = logging.getLogger(__name__)

MERGED_OP_FINAL_TEAM = "pre-approvals op final"
MERGED_OP_FINAL_SOURCES = ("pre-approvals op dubai", "pre-approvals op final shjajm")
MERGED_IP_FINAL_TEAM = "pre-approvals ip final"
MERGED_IP_FINAL_SOURCES = ("pre-approvals ip final dubai", "pre-approvals ip final shjajm")
PRE_APPROVALS_UAE_TEAM = "pre-approvals"
PRE_APPROVALS_UAE_SOURCES = (
    *MERGED_OP_FINAL_SOURCES,
    *MERGED_IP_FINAL_SOURCES,
    "pre-approvals ip elective dubai",
)
CALL_CENTER_TEAM = "call center"
CALL_CENTER_SOURCES = ("inbound", "outbound")

def _team_filter_values(team: str) -> tuple[str, ...]:
    normalized = str(team).strip().casefold()
    if normalized == MERGED_OP_FINAL_TEAM:
        return MERGED_OP_FINAL_SOURCES
    if normalized == MERGED_IP_FINAL_TEAM:
        return MERGED_IP_FINAL_SOURCES
    if normalized == PRE_APPROVALS_UAE_TEAM:
        return PRE_APPROVALS_UAE_SOURCES
    if normalized == CALL_CENTER_TEAM:
        return CALL_CENTER_SOURCES
    return (normalized,)


class PerformanceRepository(BaseRepository[PerformanceRecord]):
    """Repository for PerformanceRecord model"""

    def get_option_rows(self) -> list[dict[str, object]]:
        """Return only scalar dimensions needed by filter-option endpoints."""
        logical_team_name = func.coalesce(Team.display_name, Team.name)
        position_name = func.coalesce(PerformanceRecord.position_name, Employee.position_name)
        region_name = func.coalesce(PerformanceRecord.region, Employee.region)
        rows = (
            self.db.query(
                Employee.employee_id,
                Employee.name,
                logical_team_name.label("logical_team_name"),
                PerformanceRecord.month,
                PerformanceRecord.year,
                region_name.label("region_name"),
                PerformanceRecord.performance_level,
                position_name.label("position_name"),
                PerformanceRecord.grade,
                PerformanceRecord.status,
            )
            .join(Employee, PerformanceRecord.employee_id == Employee.id)
            .join(Team, PerformanceRecord.team_id == Team.id)
            .filter(Team.team_level == "employee")
            .all()
        )
        return [
            {
                "employee_id": str(employee_id),
                "employee_name": str(employee_name),
                "team": str(team_name),
                "month": str(month),
                "year": int(year),
                "region": str(region) if region else None,
                "performance_level": str(performance_level),
                "position": str(position) if position else None,
                "grade": str(grade) if grade else None,
                "status": str(status) if status else None,
            }
            for (
                employee_id,
                employee_name,
                team_name,
                month,
                year,
                region,
                performance_level,
                position,
                grade,
                status,
            ) in rows
        ]

    def get_dashboard_record_keys(
        self,
        team: str | None = None,
        month: str | None = None,
        employee_id: str | None = None,
        grade: str | None = None,
        status: str | None = None,
        performance_level: str | None = None,
        year: int | None = None,
        position: str | None = None,
        region: str | None = None,
    ) -> list[tuple[str, str, str, int]]:
        """Return lightweight dashboard record identifiers filtered in SQL."""
        logical_team_name = func.coalesce(Team.display_name, Team.name)
        query = self.db.query(
            Employee.employee_id,
            logical_team_name.label("logical_team_name"),
            PerformanceRecord.month,
            PerformanceRecord.year,
        ).join(
            Employee, PerformanceRecord.employee_id == Employee.id
        ).join(
            Team, PerformanceRecord.team_id == Team.id
        ).filter(Team.team_level == "employee")

        if team:
            normalized_team = _team_filter_values(team)
            query = query.filter(or_(
                func.lower(logical_team_name).in_(normalized_team),
                func.lower(Team.name).in_(normalized_team),
                func.lower(Team.db_name).in_(normalized_team),
            ))
        if month:
            query = query.filter(PerformanceRecord.month == month)
        if employee_id:
            query = query.filter(Employee.employee_id == employee_id)
        if grade:
            query = query.filter(PerformanceRecord.grade == grade)
        if status:
            query = query.filter(PerformanceRecord.status == status)
        if performance_level:
            query = query.filter(PerformanceRecord.performance_level == performance_level)
        if year is not None:
            query = query.filter(PerformanceRecord.year == year)
        if position:
            query = query.filter(PerformanceRecord.position_name == position)
        if region:
            query = query.filter(PerformanceRecord.region == region)

        return [
            (str(emp_id), str(team_name), str(record_month), int(record_year))
            for emp_id, team_name, record_month, record_year in query.distinct().all()
        ]

    def get_dashboard_records(
        self,
        team: str | None = None,
        month: str | None = None,
        employee_id: str | None = None,
        grade: str | None = None,
        status: str | None = None,
        performance_level: str | None = None,
        year: int | None = None,
        position: str | None = None,
        region: str | None = None,
    ) -> list[PerformanceRecord]:
        """Return canonical employee performance rows for analysis workspaces with SQL-level filtering."""
        query = (
            self.db.query(PerformanceRecord)
            .options(
                selectinload(PerformanceRecord.kpi_values),
                selectinload(PerformanceRecord.team),
                selectinload(PerformanceRecord.employee).selectinload(Employee.team),
            )
            .join(Team, PerformanceRecord.team_id == Team.id)
            .join(Employee, PerformanceRecord.employee_id == Employee.id)
            .filter(Team.team_level == "employee")
        )

        if team:
            normalized_team = _team_filter_values(team)
            logical_team_name = func.coalesce(Team.display_name, Team.name)
            query = query.filter(or_(
                func.lower(logical_team_name).in_(normalized_team),
                func.lower(Team.name).in_(normalized_team),
                func.lower(Team.db_name).in_(normalized_team),
            ))
        if month and month.lower() != "all":
            query = query.filter(PerformanceRecord.month == month)
        if employee_id:
            query = query.filter(Employee.employee_id == employee_id)
        if grade:
            query = query.filter(PerformanceRecord.grade == grade)
        if status:
            query = query.filter(func.lower(PerformanceRecord.status) == str(status).lower())
        if performance_level and performance_level.lower() != "all":
            query = query.filter(func.lower(PerformanceRecord.performance_level) == str(performance_level).lower())
        if year:
            query = query.filter(PerformanceRecord.year == year)
        if position:
            query = query.filter(func.lower(PerformanceRecord.position_name) == str(position).lower())
        if region:
            query = query.filter(func.lower(PerformanceRecord.region) == str(region).lower())

        return query.all()

    def get_by_employee_month(self, employee_id, month: str, year: int):
        """Get performance record for specific month"""
        return self.db.query(PerformanceRecord).filter(
            (PerformanceRecord.employee_id == employee_id) &
            (PerformanceRecord.month == month) &
            (PerformanceRecord.year == year)
        ).first()
    
    def get_monthly_records(self, team_id, month: str, year: int) -> list:
        """Get all records for team in specific month"""
        return self.db.query(PerformanceRecord).options(
            selectinload(PerformanceRecord.kpi_values)
        ).filter(
            (PerformanceRecord.team_id == team_id) &
            (PerformanceRecord.month == month) &
            (PerformanceRecord.year == year)
        ).all()
    
    def get_employee_history(self, employee_id, year: int) -> list:
        """Get all records for employee in year"""
        return self.db.query(PerformanceRecord).options(
            selectinload(PerformanceRecord.kpi_values)
        ).filter(
            (PerformanceRecord.employee_id == employee_id) &
            (PerformanceRecord.year == year)
        ).order_by(PerformanceRecord.month).all()
    
    def get_team_yearly_records(self, team_id, year: int) -> list:
        """Get all records for team in year"""
        return self.db.query(PerformanceRecord).filter(
            (PerformanceRecord.team_id == team_id) &
            (PerformanceRecord.year == year)
        ).all()
    
    def count_by_grade(self, team_id, grade: str, month: str, year: int) -> int:
        """Count records by grade"""
        return self.db.query(PerformanceRecord).filter(
            (PerformanceRecord.team_id == team_id) &
            (PerformanceRecord.grade == grade) &
            (PerformanceRecord.month == month) &
            (PerformanceRecord.year == year)
        ).count()
    
    def get_by_grade(self, team_id, grade: str, month: str, year: int) -> list:
        """Get records by grade"""
        return self.db.query(PerformanceRecord).filter(
            (PerformanceRecord.team_id == team_id) &
            (PerformanceRecord.grade == grade) &
            (PerformanceRecord.month == month) &
            (PerformanceRecord.year == year)
        ).all()
    
    def get_by_status(self, team_id, status: str, month: str, year: int) -> list:
        """Get records by status"""
        return self.db.query(PerformanceRecord).filter(
            (PerformanceRecord.team_id == team_id) &
            (PerformanceRecord.status == status) &
            (PerformanceRecord.month == month) &
            (PerformanceRecord.year == year)
        ).all()
