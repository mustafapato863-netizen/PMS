from __future__ import annotations

import re
import uuid
from typing import Literal

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from models.models import Team, UserTeamAssignment


TeamLevel = Literal["employee", "management"]
MANAGEMENT_PERFORMANCE_LEVELS = {"Managerial", "Corporate"}


def logical_team_name(team: Team) -> str:
    """Return the stable user-facing name shared by scoped team identities."""
    return str(team.display_name or team.name).strip()


def team_level_for_performance(performance_level: str | None) -> TeamLevel:
    return "management" if performance_level in MANAGEMENT_PERFORMANCE_LEVELS else "employee"


def scoped_team_query(db: Session, logical_name: str, team_level: TeamLevel) -> Query:
    normalized = str(logical_name).strip().casefold()
    return db.query(Team).filter(
        Team.team_level == team_level,
        func.lower(func.coalesce(Team.display_name, Team.name)) == normalized,
    )


def get_scoped_team(
    db: Session,
    logical_name: str,
    team_level: TeamLevel,
    *,
    include_inactive: bool = False,
) -> Team | None:
    query = scoped_team_query(db, logical_name, team_level)
    if not include_inactive:
        query = query.filter(Team.is_active.is_(True))
    return query.first()


def _storage_slug(logical_name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", logical_name.strip().casefold()).strip("_")
    return value or "team"


def _unique_storage_value(db: Session, column, base_value: str) -> str:
    candidate = base_value[:100]
    suffix = 2
    while db.query(Team.id).filter(func.lower(column) == candidate.casefold()).first():
        suffix_text = f"_{suffix}"
        candidate = f"{base_value[:100 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


def create_management_team_identity(db: Session, logical_name: str, *, region: str = "UAE") -> Team:
    """Create a distinct management-scoped Team row for a logical team name."""
    existing = get_scoped_team(db, logical_name, "management", include_inactive=True)
    if existing:
        existing.is_active = True
        _copy_unrestricted_assignments(db, logical_name, existing)
        return existing

    base = f"{_storage_slug(logical_name)}_management"
    team = Team(
        name=_unique_storage_value(db, Team.name, base),
        db_name=_unique_storage_value(db, Team.db_name, base),
        display_name=str(logical_name).strip(),
        region=region or "UAE",
        team_level="management",
        is_active=True,
    )
    db.add(team)
    db.flush()
    _copy_unrestricted_assignments(db, logical_name, team)
    return team


def _copy_unrestricted_assignments(
    db: Session,
    logical_name: str,
    management_team: Team,
) -> None:
    employee_team = get_scoped_team(db, logical_name, "employee", include_inactive=True)
    if not employee_team:
        return

    source_assignments = (
        db.query(UserTeamAssignment)
        .filter(
            UserTeamAssignment.team_id == employee_team.id,
            UserTeamAssignment.performance_level.is_(None),
        )
        .all()
    )
    if not source_assignments:
        return

    existing_user_ids = {
        user_id
        for (user_id,) in (
            db.query(UserTeamAssignment.user_id)
            .filter(
                UserTeamAssignment.team_id == management_team.id,
                UserTeamAssignment.performance_level.is_(None),
            )
            .all()
        )
    }
    for assignment in source_assignments:
        if assignment.user_id in existing_user_ids:
            continue
        db.add(
            UserTeamAssignment(
                id=uuid.uuid4(),
                user_id=assignment.user_id,
                team_id=management_team.id,
                performance_level=None,
                access_level=assignment.access_level,
                assigned_by=assignment.assigned_by,
            )
        )
        existing_user_ids.add(assignment.user_id)
