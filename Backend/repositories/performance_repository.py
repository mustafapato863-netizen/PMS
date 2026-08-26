from sqlalchemy.orm import Session, selectinload
from repositories.base_repository import BaseRepository
from sqlalchemy import String, and_, case, cast, false, func, or_

from models.models import PerformanceRecord, Employee, KPIValue, Team
from utils.report_scope import _team_keys
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


def _expanded_scope_team_values(teams) -> set[str]:
    values: set[str] = set()
    for team in teams or []:
        values.update(str(value).casefold() for value in _team_keys(str(team)))
    return values


def _team_name_clause(team_values: set[str]):
    logical_team_name = func.lower(func.coalesce(Team.display_name, Team.name))
    return or_(
        logical_team_name.in_(team_values),
        func.lower(Team.name).in_(team_values),
        func.lower(Team.db_name).in_(team_values),
    )


class PerformanceRepository(BaseRepository[PerformanceRecord]):
    """Repository for PerformanceRecord model"""

    def _dashboard_query(self):
        return (
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

    @staticmethod
    def _apply_scope(query, scope: dict | None):
        if not scope or scope.get("legacy_unscoped"):
            return query

        role = str(scope.get("role") or "")
        if role in {"Admin", "Viewer"} or scope.get("is_general_manager"):
            return query

        if role in {"Agent", "Executive"}:
            employee_id = str(scope.get("employee_id") or "").strip()
            return query.filter(Employee.employee_id == employee_id) if employee_id else query.filter(false())

        if role != "Manager":
            return query

        accessible_teams = _expanded_scope_team_values(scope.get("accessible_teams"))
        if not accessible_teams:
            return query.filter(false())

        team_levels = scope.get("accessible_team_levels") or []
        if not team_levels:
            return query.filter(_team_name_clause(accessible_teams))

        level_clauses = []
        for team, level in team_levels:
            team_values = _expanded_scope_team_values([team]) & accessible_teams
            if not team_values:
                continue
            level_clauses.append(
                and_(
                    _team_name_clause(team_values),
                    func.lower(cast(PerformanceRecord.performance_level, String)) == str(level).casefold(),
                )
            )
        return query.filter(or_(*level_clauses)) if level_clauses else query.filter(false())

    @staticmethod
    def _apply_dashboard_filters(
        query,
        *,
        team: str | None = None,
        month: str | None = None,
        employee_id: str | None = None,
        grade: str | None = None,
        status: str | None = None,
        performance_level: str | None = None,
        year: int | None = None,
        position: str | None = None,
        region: str | None = None,
        periods: list[tuple[int, str]] | None = None,
        employee_search: str | None = None,
    ):
        if team:
            team_values = set(_team_filter_values(team))
            query = query.filter(_team_name_clause(team_values))
        if month and month.lower() != "all":
            query = query.filter(PerformanceRecord.month == month)
        if employee_id:
            query = query.filter(Employee.employee_id == employee_id)
        if employee_search:
            pattern = f"%{str(employee_search).strip().casefold()}%"
            query = query.filter(
                or_(
                    func.lower(Employee.name).like(pattern),
                    func.lower(Employee.employee_id).like(pattern),
                )
            )
        if grade:
            grade_value = func.lower(cast(PerformanceRecord.grade, String))
            query = query.filter(grade_value == str(grade).casefold())
        if status:
            # PostgreSQL stores performance status as the ``perf_status``
            # enum.  LOWER(enum) is invalid there; cast to text before doing
            # the case-insensitive comparison used by the Reports filters.
            status_value = func.lower(cast(PerformanceRecord.status, String))
            query = query.filter(status_value == str(status).casefold())
        if performance_level and performance_level.lower() != "all":
            level_value = func.lower(cast(PerformanceRecord.performance_level, String))
            query = query.filter(level_value == str(performance_level).casefold())
        if year is not None:
            query = query.filter(PerformanceRecord.year == year)
        if position:
            position_value = func.lower(func.coalesce(PerformanceRecord.position_name, Employee.position_name))
            query = query.filter(position_value == str(position).casefold())
        if region:
            region_value = func.lower(func.coalesce(PerformanceRecord.region, Employee.region))
            query = query.filter(region_value == str(region).casefold())
        if periods:
            period_clauses = [
                and_(PerformanceRecord.year == period_year, PerformanceRecord.month == period_month)
                for period_year, period_month in periods
            ]
            query = query.filter(or_(*period_clauses)) if period_clauses else query.filter(false())
        return query

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

    def get_option_kpi_keys(self, scope: dict | None = None) -> list[str]:
        """Return KPI keys for the same authorized employee-record scope."""
        query = (
            self.db.query(KPIValue.kpi_key)
            .join(
                PerformanceRecord,
                and_(KPIValue.record_id == PerformanceRecord.id, KPIValue.record_year == PerformanceRecord.year),
            )
            .join(Team, PerformanceRecord.team_id == Team.id)
            .join(Employee, PerformanceRecord.employee_id == Employee.id)
            .filter(Team.team_level == "employee")
        )
        query = self._apply_scope(query, scope)
        return [str(kpi_key) for (kpi_key,) in query.distinct().order_by(KPIValue.kpi_key).all() if kpi_key]

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
        periods: list[tuple[int, str]] | None = None,
        scope: dict | None = None,
        employee_search: str | None = None,
        kpi: str | None = None,
    ) -> list[PerformanceRecord]:
        """Return canonical employee performance rows for analysis workspaces with SQL-level filtering."""
        query = self._dashboard_query()
        query = self._apply_dashboard_filters(
            query,
            team=team,
            month=month,
            employee_id=employee_id,
            grade=grade,
            status=status,
            performance_level=performance_level,
            year=year,
            position=position,
            region=region,
            periods=periods,
            employee_search=employee_search,
        )
        if kpi:
            query = query.join(
                KPIValue,
                and_(KPIValue.record_id == PerformanceRecord.id, KPIValue.record_year == PerformanceRecord.year),
            ).filter(func.lower(KPIValue.kpi_key) == str(kpi).casefold())
        query = self._apply_scope(query, scope)
        return query.all()

    def get_dashboard_summary_rows(
        self,
        *,
        team: str | None = None,
        performance_level: str | None = None,
        position: str | None = None,
        region: str | None = None,
        periods: list[tuple[int, str]] | None = None,
        scope: dict | None = None,
        employee_id: str | None = None,
        grade: str | None = None,
        status: str | None = None,
        kpi: str | None = None,
    ) -> list[dict[str, object]]:
        """Return scalar summary fields without loading KPI child rows."""
        position_name = func.coalesce(PerformanceRecord.position_name, Employee.position_name)
        region_name = func.coalesce(PerformanceRecord.region, Employee.region)
        logical_team_name = func.coalesce(Team.display_name, Team.name)
        query = self.db.query(
            PerformanceRecord.id.label("record_id"),
            PerformanceRecord.year.label("year"),
            PerformanceRecord.month.label("month"),
            Employee.employee_id.label("employee_id"),
            Employee.name.label("employee_name"),
            logical_team_name.label("team"),
            region_name.label("region"),
            PerformanceRecord.performance_level.label("performance_level"),
            position_name.label("position"),
            PerformanceRecord.score.label("score"),
            PerformanceRecord.grade.label("grade"),
            PerformanceRecord.status.label("status"),
            PerformanceRecord.record_payload.label("record_payload"),
        ).join(
            Team, PerformanceRecord.team_id == Team.id
        ).join(
            Employee, PerformanceRecord.employee_id == Employee.id
        ).filter(
            Team.team_level == "employee"
        )
        query = self._apply_dashboard_filters(
            query,
            team=team,
            performance_level=performance_level,
            position=position,
            region=region,
            employee_id=employee_id,
            grade=grade,
            status=status,
            periods=periods,
        )
        if kpi:
            query = query.join(
                KPIValue,
                and_(KPIValue.record_id == PerformanceRecord.id, KPIValue.record_year == PerformanceRecord.year),
            ).filter(func.lower(KPIValue.kpi_key) == str(kpi).casefold())
        query = self._apply_scope(query, scope)
        return [dict(row._mapping) for row in query.all()]

    def get_dashboard_record_page(
        self,
        *,
        scope: dict | None = None,
        team: str | None = None,
        month: str | None = None,
        employee_id: str | None = None,
        grade: str | None = None,
        status: str | None = None,
        performance_level: str | None = None,
        year: int | None = None,
        position: str | None = None,
        region: str | None = None,
        employee_search: str | None = None,
        kpi: str | None = None,
        sort: str = "name",
        cursor: dict | None = None,
        page_size: int = 50,
        include_total: bool = False,
    ) -> tuple[list[PerformanceRecord], int | None]:
        """Return one SQL-paginated dashboard page after applying authorization."""
        query = self._dashboard_query()
        query = self._apply_dashboard_filters(
            query,
            team=team,
            month=month,
            employee_id=employee_id,
            grade=grade,
            status=status,
            performance_level=performance_level,
            year=year,
            position=position,
            region=region,
            employee_search=employee_search,
        )
        if kpi:
            query = query.join(
                KPIValue,
                and_(KPIValue.record_id == PerformanceRecord.id, KPIValue.record_year == PerformanceRecord.year),
            ).filter(func.lower(KPIValue.kpi_key) == str(kpi).casefold())
        query = self._apply_scope(query, scope)

        name_key = func.lower(Employee.name)
        employee_key = func.lower(Employee.employee_id)
        record_key = func.replace(func.lower(cast(PerformanceRecord.id, String)), "-", "")
        score_key = case(
            (and_(PerformanceRecord.score > 0, PerformanceRecord.score <= 10), PerformanceRecord.score * 100),
            else_=PerformanceRecord.score,
        )
        normalized_sort = str(sort or "name").strip().lower()
        if normalized_sort not in {"name", "score_desc", "score_asc"}:
            raise ValueError("sort must be name, score_desc, or score_asc")

        if cursor:
            if normalized_sort == "name":
                last_name = str(cursor.get("name") or "")
                last_employee = str(cursor.get("employee_id") or "")
                last_record = str(cursor.get("record_id") or "").replace("-", "").casefold()
                query = query.filter(
                    or_(
                        name_key > last_name,
                        and_(name_key == last_name, employee_key > last_employee),
                        and_(name_key == last_name, employee_key == last_employee, record_key > last_record),
                    )
                )
            else:
                last_score = float(cursor.get("score") or 0)
                comparator = score_key < last_score if normalized_sort == "score_desc" else score_key > last_score
                same_score = score_key == last_score
                last_name = str(cursor.get("name") or "")
                last_employee = str(cursor.get("employee_id") or "")
                last_record = str(cursor.get("record_id") or "").replace("-", "").casefold()
                query = query.filter(
                    or_(
                        comparator,
                        and_(same_score, name_key > last_name),
                        and_(same_score, name_key == last_name, employee_key > last_employee),
                        and_(same_score, name_key == last_name, employee_key == last_employee, record_key > last_record),
                    )
                )

        if include_total:
            total = query.order_by(None).count()
        else:
            total = None

        if normalized_sort == "name":
            query = query.order_by(name_key.asc(), employee_key.asc(), record_key.asc())
        elif normalized_sort == "score_desc":
            query = query.order_by(score_key.desc(), name_key.asc(), employee_key.asc(), record_key.asc())
        else:
            query = query.order_by(score_key.asc(), name_key.asc(), employee_key.asc(), record_key.asc())
        return query.limit(page_size + 1).all(), total

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
