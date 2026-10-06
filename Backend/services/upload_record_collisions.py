"""One performance record per employee per month: resolve upload collisions.

``performance_records`` holds one row per (employee, month, year) - the upload
upsert, record ids, notes, corrective actions and employee dashboards are all
keyed that way and ``employees.team_id`` is a single team. A multi-sheet
upload can still contain the same employee-month more than once:

* on two team sheets (e.g. Pre-Approvals IP Final Dubai *and* IP Elective
  Dubai), or
* twice on one sheet (e.g. both IP Elective workstream tables).

Before this module the duplicates collapsed into one stored record whose
team/payload came from the last row while the KPI rows of *all* duplicates
were attached and summed into the score (production: 16 IP Elective Dubai
records stored as E with unscaled sums of 1.51-2.72, one with both Elective
workstreams adding up to 171.77). Now exactly one row per employee-month is
scored - the employee's assigned team (and position) - and every ignored row
is reported as an upload warning naming the employee and the ignored sheet.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence

WARNING_CODE = "DUPLICATE_EMPLOYEE_MONTH"


def _key(value: Any) -> str:
    return str(value or "").strip()


def _same(left: Any, right: Any) -> bool:
    return _key(left).casefold() == _key(right).casefold() and _key(left) != ""


def colliding_employee_ids(records: Sequence[Any]) -> set[str]:
    """Employees that occur more than once for the same month/year."""
    seen: set[tuple[str, Any, Any]] = set()
    colliding: set[str] = set()
    for record in records:
        key = (_key(record.employee_id), record.month, getattr(record, "year", None))
        if key in seen:
            colliding.add(key[0])
        seen.add(key)
    return colliding


def resolve_employee_month_collisions(
    records: Sequence[Any],
    employees: Sequence[Any],
    assigned: Mapping[str, tuple[str | None, str | None]] | None = None,
) -> tuple[list[Any], list[Any], list[dict[str, Any]]]:
    """Return ``(records, employees, warnings)`` with one record per employee-month.

    ``assigned`` maps an employee id to the ``(team, position)`` already stored
    for that employee (the employee master). The assigned team is that stored
    team when it is one of the employee's sheets in this upload; otherwise it is
    the team the upload itself would assign (the employee's last row, which is
    what employee sync keeps). Within the assigned team, the stored position is
    preferred, then the last row (the row whose payload used to be kept).
    Records of other employees, and employee-months that occur once, are
    returned unchanged and in their original order.
    """
    assigned = assigned or {}
    groups: dict[tuple[str, Any, Any], list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        groups[(_key(record.employee_id), record.month, getattr(record, "year", None))].append(index)

    colliding_employees = {key[0] for key, indexes in groups.items() if len(indexes) > 1}
    if not colliding_employees:
        return list(records), list(employees), []

    last_entry_team: dict[str, str] = {}
    for employee in employees:
        last_entry_team[_key(employee.id)] = employee.team

    assigned_team: dict[str, str] = {}
    assigned_position: dict[str, str | None] = {}
    for employee_id in colliding_employees:
        batch_teams = [records[i].team for key, indexes in groups.items() if key[0] == employee_id for i in indexes]
        stored_team, stored_position = assigned.get(employee_id, (None, None))
        match = next((team for team in batch_teams if _same(team, stored_team)), None)
        if match is not None:
            assigned_team[employee_id] = match
            assigned_position[employee_id] = stored_position
        else:
            assigned_team[employee_id] = last_entry_team.get(employee_id) or batch_teams[-1]
            assigned_position[employee_id] = None

    dropped: set[int] = set()
    warnings: list[dict[str, Any]] = []
    for (employee_id, month, year), indexes in groups.items():
        if len(indexes) < 2:
            continue
        team = assigned_team[employee_id]
        same_team = [i for i in indexes if _same(records[i].team, team)] or indexes
        preferred = assigned_position[employee_id]
        keep = next(
            (i for i in reversed(same_team) if preferred and _same(records[i].position, preferred)),
            same_team[-1],
        )
        kept = records[keep]
        for index in indexes:
            if index == keep:
                continue
            dropped.add(index)
            ignored = records[index]
            reason = "same_sheet_duplicate" if _same(ignored.team, kept.team) else "other_team_sheet"
            where = (
                f"a second '{ignored.team}' row ({ignored.position or 'no position'})"
                if reason == "same_sheet_duplicate"
                else f"the '{ignored.team}' sheet"
            )
            warnings.append({
                "code": WARNING_CODE,
                "employee_id": employee_id,
                "employee_name": getattr(kept, "employee_name", None),
                "month": month,
                "year": year,
                "kept_team": kept.team,
                "kept_position": kept.position,
                "ignored_sheet": ignored.team,
                "ignored_position": ignored.position,
                "reason": reason,
                "message": (
                    f"Employee {employee_id} appears more than once for {month} {year or ''}".rstrip()
                    + f": scored on '{kept.team}' ({kept.position or 'no position'}), the assigned team; "
                    f"{where} was ignored and not mixed into the score. "
                    "Performance records are one per employee per month."
                ),
            })

    kept_records = [record for index, record in enumerate(records) if index not in dropped]
    kept_employees = [
        employee
        for employee in employees
        if _key(employee.id) not in assigned_team or _same(employee.team, assigned_team[_key(employee.id)])
    ]
    # Never lose an employee entirely (e.g. assigned team only via records).
    present = {_key(employee.id) for employee in kept_employees}
    kept_employees.extend(employee for employee in employees if _key(employee.id) not in present)
    return kept_records, kept_employees, warnings


def stored_assignments(db, employee_ids: Iterable[str]) -> dict[str, tuple[str | None, str | None]]:
    """``employee_id -> (team name, position)`` from the employee master."""
    from models.models import Employee as DBEmployee, Team

    ids = sorted({_key(value) for value in employee_ids if _key(value)})
    if db is None or not ids:
        return {}
    rows = (
        db.query(DBEmployee.employee_id, Team.name, DBEmployee.position_name)
        .join(Team, Team.id == DBEmployee.team_id)
        .filter(DBEmployee.employee_id.in_(ids))
        .all()
    )
    return {str(employee_id): (team, position) for employee_id, team, position in rows}
