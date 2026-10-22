from types import SimpleNamespace

from sqlalchemy.orm import Session, selectinload
from utils.scoring_rules import score_percent_sql
from repositories.base_repository import BaseRepository
from sqlalchemy import String, and_, case, cast, false, func, or_, select, tuple_

from models.models import PerformanceRecord, Employee, KPIValue, Team
from utils.report_scope import FUNCTION_SCOPED_ROLES, _team_keys, selection_team_keys
from utils.team_identity import logical_team_name
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
# The parent view is Inbound + Outbound plus people stored on the Call Center
# team itself (trainers, analysts, and team leaders). Channel pages still
# select Inbound or Outbound alone.
CALL_CENTER_SOURCES = ("inbound", "outbound", "call center")

def _team_filter_values(team: str) -> tuple[str, ...]:
    normalized = str(team).strip().casefold()
    if normalized == MERGED_OP_FINAL_TEAM:
        return MERGED_OP_FINAL_SOURCES
    if normalized == MERGED_IP_FINAL_TEAM:
        return MERGED_IP_FINAL_SOURCES
    if normalized == PRE_APPROVALS_UAE_TEAM:
        return tuple(sorted(selection_team_keys(team)))
    if normalized == 'rcm':
        return tuple(sorted(selection_team_keys(team)))
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


def _uuid_key(value) -> str:
    """A UUID as lowercase hex without dashes, whether the driver gives text, hex or a UUID."""
    return str(value).replace("-", "").lower()


class PerformanceRepository(BaseRepository[PerformanceRecord]):
    """Repository for PerformanceRecord model"""

    def _dashboard_query(self, *, kpi_values: bool = True):
        # Without kpi_values the KPI rows are not loaded as objects; get_kpi_value_rows reads only the columns the
        # record resolver uses.
        options = [
            selectinload(PerformanceRecord.team),
            selectinload(PerformanceRecord.employee).selectinload(Employee.team),
        ]
        if kpi_values:
            options.insert(0, selectinload(PerformanceRecord.kpi_values))
        return (
            self.db.query(PerformanceRecord)
            .options(*options)
            .join(Team, PerformanceRecord.team_id == Team.id)
            .join(Employee, PerformanceRecord.employee_id == Employee.id)
            .filter(Team.team_level == "employee")
        )

    @staticmethod
    def _apply_scope(query, scope: dict | None):
        if not scope:
            return query

        role = str(scope.get("role") or "")
        if role in FUNCTION_SCOPED_ROLES:
            accessible_functions = scope.get("accessible_functions") or []
            accessible_teams = _expanded_scope_team_values(accessible_functions)
            return query.filter(_team_name_clause(accessible_teams)) if accessible_teams else query.filter(false())

        if scope.get("legacy_unscoped"):
            return query
        if role in {"Admin", "General Manager", "Performance Team", "Viewer"}:
            return query

        if role in {"Agent", "Executive", "Employee"}:
            employee_id = str(scope.get("employee_id") or "").strip()
            return query.filter(Employee.employee_id == employee_id) if employee_id else query.filter(false())

        if role == "Regional Manager":
            regions = {str(value).strip().casefold() for value in scope.get("accessible_regions", []) if str(value).strip()}
            if not regions:
                return query.filter(false())
            row_region = func.lower(func.coalesce(PerformanceRecord.region, Employee.region, Team.region))
            return query.filter(row_region.in_(regions))

        if role == "Branch Director":
            branches = {str(value).strip().casefold() for value in scope.get("accessible_branches", []) if str(value).strip()}
            return query.filter(func.lower(PerformanceRecord.branch_key).in_(branches)) if branches else query.filter(false())

        if role != "Manager":
            return query.filter(false())

        if scope.get("has_unrestricted_team_access"):
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
        employee_ids: list[str] | None = None,
        grade: str | None = None,
        status: str | None = None,
        performance_level: str | None = None,
        year: int | None = None,
        position: str | None = None,
        region: str | None = None,
        branch: str | None = None,
        score_lt: float | None = None,
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
        if employee_ids is not None:
            query = query.filter(Employee.employee_id.in_(employee_ids)) if employee_ids else query.filter(false())
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
        if branch:
            query = query.filter(func.lower(PerformanceRecord.branch_key) == str(branch).strip().casefold())
        if score_lt is not None:
            query = query.filter(score_percent_sql(PerformanceRecord.score) < score_lt)
        if periods:
            period_clauses = [
                and_(PerformanceRecord.year == period_year, PerformanceRecord.month == period_month)
                for period_year, period_month in periods
            ]
            query = query.filter(or_(*period_clauses)) if period_clauses else query.filter(false())
        return query

    def get_option_rows(self, scope: dict | None = None, *, include_scores: bool = False) -> list[dict[str, object]]:
        """Return only scalar dimensions needed by filter-option endpoints.

        ``include_scores`` adds one score column to the same query. The default
        projection does not carry it.
        """
        logical_team_name = func.coalesce(Team.display_name, Team.name)
        position_name = func.coalesce(PerformanceRecord.position_name, Employee.position_name)
        region_name = func.coalesce(PerformanceRecord.region, Employee.region)
        query = (
            self.db.query(
                Employee.employee_id,
                Employee.name,
                logical_team_name.label("logical_team_name"),
                PerformanceRecord.month,
                PerformanceRecord.year,
                region_name.label("region_name"),
                PerformanceRecord.performance_level,
                position_name.label("position_name"),
                PerformanceRecord.branch_key,
                PerformanceRecord.grade,
                PerformanceRecord.status,
                *([PerformanceRecord.score.label("score")] if include_scores else []),
            )
            .join(Employee, PerformanceRecord.employee_id == Employee.id)
            .join(Team, PerformanceRecord.team_id == Team.id)
            .filter(Team.team_level == "employee")
        )
        rows = self._apply_scope(query, scope).all()
        items = [
            {
                "employee_id": str(employee_id),
                "employee_name": str(employee_name),
                "team": str(team_name),
                "month": str(month),
                "year": int(year),
                "region": str(region) if region else None,
                "performance_level": str(performance_level),
                "position": str(position) if position else None,
                "branch_key": str(branch_key) if branch_key else None,
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
                branch_key,
                grade,
                status,
            ) in [tuple(row)[:11] for row in rows]
        ]
        if include_scores:
            for item, row in zip(items, rows):
                item["score"] = float(row[11]) if row[11] is not None else None
        return items

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
        scope: dict | None = None,
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

        query = self._apply_scope(query, scope)

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
        employee_ids: list[str] | None = None,
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
        return self._dashboard_records_query(
            True,
            team=team, month=month, employee_id=employee_id, employee_ids=employee_ids, grade=grade, status=status,
            performance_level=performance_level, year=year, position=position, region=region, periods=periods,
            scope=scope, employee_search=employee_search, kpi=kpi,
        ).all()

    def get_dashboard_record_rows(self, **filters) -> list[SimpleNamespace]:
        """get_dashboard_records' rows as light objects, for the record resolver.

        The same SELECT runs without the ORM, so the rows come back in the same order and no ORM object is built.
        Each row carries ``employee`` and ``team`` (and the employee's ``team``) from two column lookups. The KPI
        values are read with get_kpi_value_rows.
        """
        query = self._dashboard_records_query(False, **filters)
        return self._with_relations(self.db.connection().execute(query.statement).mappings().all())

    def get_dashboard_record_rows_by_keys(self, keys: list[tuple]) -> list[SimpleNamespace]:
        """get_dashboard_record_rows' rows for the given (record id, year) keys, in the order of the keys."""
        rows = []
        for start in range(0, len(keys), 500):
            query = self._dashboard_records_query(False).filter(
                tuple_(PerformanceRecord.id, PerformanceRecord.year).in_(keys[start:start + 500])
            )
            rows.extend(self.db.connection().execute(query.statement).mappings().all())
        position = {key: index for index, key in enumerate(keys)}
        rows.sort(key=lambda row: position[(row["id"], row["year"])])
        return self._with_relations(rows)

    def get_dashboard_record_index(
        self,
        *,
        year: int | None = None,
        months: list[str] | None = None,
        team_names: list[str] | None = None,
        employee_code: str | None = None,
    ) -> list[SimpleNamespace]:
        """Every row of get_dashboard_record_rows(), in the same order, with only the values a filter or a period
        reads: the key, the employee code, the team name, the region, the position and level, the year and month.

        The identical SELECT runs as driver SQL, so no column is converted (no payload is decoded). The values
        are the resolver's: the team's display name or name, and the record's region and position or else the
        employee's. ``record_key`` is the record id as lowercase hex without dashes, and the year.
        """
        connection = self.db.connection()
        query = self._dashboard_records_query(False, year=year, employee_id=employee_code or None)
        # Optional narrowing for callers that filter by period/team: plain
        # IN predicates on the raw columns, so indexes stay usable.
        if months is not None:
            query = query.filter(PerformanceRecord.month.in_(months)) if months else query.filter(false())
        if team_names is not None:
            # String predicate (driver SQL skips UUID bind processing); a superset
            # that callers narrow with the exact logical-team comparison.
            query = query.filter(Team.name.in_(team_names)) if team_names else query.filter(false())
        compiled = query.statement.compile(
            dialect=connection.dialect, compile_kwargs={"render_postcompile": True}
        )
        params = compiled.construct_params()
        arguments = tuple(params[name] for name in compiled.positiontup) if compiled.positional else params
        rows = connection.exec_driver_sql(compiled.string, arguments).mappings().all()
        employees = {
            _uuid_key(employee.id): employee
            for employee in self.db.execute(
                select(Employee.id, Employee.employee_id, Employee.region, Employee.position_name)
            )
        }
        teams = {
            _uuid_key(team.id): team
            for team in self.db.execute(select(Team.id, Team.name, Team.display_name))
        }
        index = []
        for row in rows:
            employee = employees[_uuid_key(row["employee_id"])]
            index.append(SimpleNamespace(
                record_key=(_uuid_key(row["id"]), int(row["year"])),
                employee_id=str(employee.employee_id),
                team=logical_team_name(teams[_uuid_key(row["team_id"])]),
                region=row["region"] or employee.region,
                position=row["position_name"] or employee.position_name,
                performance_level=str(row["performance_level"]),
                branch_key=row["branch_key"],
                year=int(row["year"]),
                month=str(row["month"]),
            ))
        return index

    def _with_relations(self, rows) -> list[SimpleNamespace]:
        """Dashboard rows as light objects, each with ``employee`` and ``team`` (and the employee's ``team``)."""
        employee_ids = list({row["employee_id"] for row in rows})
        employees: dict = {}
        for start in range(0, len(employee_ids), 500):
            for employee in self.db.execute(
                select(
                    Employee.id,
                    Employee.employee_id,
                    Employee.name,
                    Employee.region,
                    Employee.position_name,
                    Employee.team_id,
                ).where(Employee.id.in_(employee_ids[start:start + 500]))
            ):
                employees[employee.id] = employee
        team_ids = list({row["team_id"] for row in rows} | {employee.team_id for employee in employees.values()})
        teams: dict = {}
        for start in range(0, len(team_ids), 500):
            for team in self.db.execute(
                select(Team.id, Team.name, Team.display_name).where(Team.id.in_(team_ids[start:start + 500]))
            ):
                teams[team.id] = SimpleNamespace(id=team.id, name=team.name, display_name=team.display_name)
        people = {
            key: SimpleNamespace(
                id=employee.id,
                employee_id=employee.employee_id,
                name=employee.name,
                region=employee.region,
                position_name=employee.position_name,
                team=teams.get(employee.team_id),
            )
            for key, employee in employees.items()
        }
        return [
            SimpleNamespace(**row, employee=people.get(row["employee_id"]), team=teams.get(row["team_id"]))
            for row in rows
        ]

    def get_kpi_value_rows(self, keys: list[tuple]) -> dict[tuple, list]:
        """The KPI value columns the record resolver reads, grouped by (record id, record year).

        The rows are read with the same tuple IN filter, in batches of the same size, as the KPI relationship's
        selectin load, so each record's values come back in the same order. The record id is read as text and
        matched by its hex form, so no UUID object is built per KPI value.
        """
        grouped: dict[tuple, list] = {key: [] for key in keys}
        by_hex = {(key[0].hex, key[1]): grouped[key] for key in keys}
        for start in range(0, len(keys), 500):
            batch = keys[start:start + 500]
            rows = self.db.execute(
                select(
                    cast(KPIValue.record_id, String).label("record_id"),
                    KPIValue.record_year,
                    KPIValue.kpi_key,
                    KPIValue.actual_value,
                    KPIValue.target_value,
                    KPIValue.achievement_ratio,
                    KPIValue.weight_applied,
                    KPIValue.contribution,
                ).where(tuple_(KPIValue.record_id, KPIValue.record_year).in_(batch))
            ).all()
            for row in rows:
                by_hex[(str(row.record_id).replace("-", "").lower(), row.record_year)].append(row)
        return grouped

    def _dashboard_records_query(
        self,
        kpi_values: bool,
        *,
        team: str | None = None,
        month: str | None = None,
        employee_id: str | None = None,
        employee_ids: list[str] | None = None,
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
    ):
        query = self._dashboard_query(kpi_values=kpi_values)
        query = self._apply_dashboard_filters(
            query,
            team=team,
            month=month,
            employee_id=employee_id,
            employee_ids=employee_ids,
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
        return self._apply_scope(query, scope)

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
        max_score: float | None = None,
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
            PerformanceRecord.branch_key.label("branch_key"),
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
        if max_score is not None:
            query = query.filter(PerformanceRecord.score <= max_score)
        query = self._apply_scope(query, scope)
        return [dict(row._mapping) for row in query.all()]

    def get_active_period_pairs(self, *, scope: dict | None = None) -> list[tuple[int, str]]:
        """(year, month) of scope rows with a score above zero; those rows always count under the activity rule."""
        query = self._dashboard_query().filter(PerformanceRecord.score > 0)
        query = self._apply_scope(query, scope)
        rows = query.with_entities(PerformanceRecord.year, PerformanceRecord.month).distinct().all()
        return [(int(row.year), str(row.month)) for row in rows]

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
        branch: str | None = None,
        employee_search: str | None = None,
        score_lt: float | None = None,
        kpi: str | None = None,
        sort: str = "name",
        cursor: dict | None = None,
        page_size: int = 50,
        include_total: bool = False,
        exclude_record_ids: list | None = None,
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
            branch=branch,
            score_lt=score_lt,
            employee_search=employee_search,
        )
        if kpi:
            query = query.join(
                KPIValue,
                and_(KPIValue.record_id == PerformanceRecord.id, KPIValue.record_year == PerformanceRecord.year),
            ).filter(func.lower(KPIValue.kpi_key) == str(kpi).casefold())
        query = self._apply_scope(query, scope)
        if exclude_record_ids:
            query = query.filter(PerformanceRecord.id.not_in(list(exclude_record_ids)))

        name_key = func.lower(Employee.name)
        employee_key = func.lower(Employee.employee_id)
        record_key = func.replace(func.lower(cast(PerformanceRecord.id, String)), "-", "")
        score_key = score_percent_sql(PerformanceRecord.score)
        normalized_sort = str(sort or "name").strip().lower()
        if normalized_sort not in {"name", "score_desc", "score_asc"}:
            raise ValueError("sort must be name, score_desc, or score_asc")

        # The reported total describes the full filtered result, not just the
        # rows remaining after the current cursor.
        if include_total:
            total = query.order_by(None).count()
        else:
            total = None

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
