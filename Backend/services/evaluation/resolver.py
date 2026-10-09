"""Resolve one approved basis for an exact team, level, position, and month."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from models.models import Team, TeamConfigurationVersion
from services.evaluation.access import SchemaIncomplete
from services.evaluation.periods import month_name, month_number
from services.evaluation.scoring import conflicts_for, grade_for, overall_score, score_rows
from utils.team_identity import logical_team_name


def assert_schema(db: Session) -> None:
    try:
        db.execute(text("SELECT performance_level FROM team_configuration_versions LIMIT 0"))
        db.execute(text("SELECT id FROM evaluation_scopes LIMIT 0"))
    except (OperationalError, ProgrammingError) as exc:
        db.rollback()
        raise SchemaIncomplete(
            "Evaluation settings schema is incomplete. Run alembic upgrade head. Monthly evaluation is refused until the new tables exist."
        ) from exc


def schema_ready(db: Session) -> bool:
    try:
        columns = {column["name"] for column in inspect(db.bind).get_columns("team_configuration_versions")}
    except Exception:
        return False
    return "performance_level" in columns and inspect(db.bind).has_table("evaluation_scopes")


def _position(value: str | None) -> str:
    return str(value or "")


def approved_version(
    db: Session,
    *,
    team_id,
    level: str,
    position: str | None,
    year: int,
    month,
) -> TeamConfigurationVersion | None:
    if not schema_ready(db):
        return None
    number = month_number(month)
    return (
        db.query(TeamConfigurationVersion)
        .filter(
            TeamConfigurationVersion.team_id == team_id,
            TeamConfigurationVersion.performance_level == level,
            TeamConfigurationVersion.position_name == _position(position),
            TeamConfigurationVersion.effective_from_year == int(year),
            TeamConfigurationVersion.effective_from_month == number,
            TeamConfigurationVersion.status == "approved",
        )
        .one_or_none()
    )


def snapshot_lines(version: TeamConfigurationVersion | None) -> list[dict]:
    if version is None:
        return []
    snapshot = version.config_snapshot or {}
    lines = snapshot.get("lines") if isinstance(snapshot, dict) else None
    return list(lines or [])


def basis_payload(version: TeamConfigurationVersion) -> dict:
    snapshot = version.config_snapshot if isinstance(version.config_snapshot, dict) else {}
    return {
        "pinned": True,
        "version_id": str(version.id),
        "version_number": version.version_number,
        "performance_level": version.performance_level,
        "position_name": version.position_name or "",
        "year": version.effective_from_year,
        "month": version.effective_from_month,
        "month_name": month_name(version.effective_from_month),
        "policy": (snapshot or {}).get("policy") or "employee_ratio",
        "lines": snapshot_lines(version),
        "grade_thresholds": (snapshot or {}).get("grade_thresholds") or {"A": 95, "B": 85, "C": 75, "D": 65},
    }


def score_basis(version: TeamConfigurationVersion, rows: list[dict], *, check_conflicts: bool = True) -> dict:
    """Same function for preview and commit. Apply rescoring passes check_conflicts=False."""
    lines = snapshot_lines(version)
    found = conflicts_for(lines, rows) if check_conflicts else []
    if found:
        from services.evaluation.access import TargetConflict

        raise TargetConflict(
            "Workbook target differs from the approved fixed target. Commit is blocked.",
            code="target_conflict",
            conflicts=found,
        )
    scored = score_rows(version.performance_level or "Employee", lines, rows)
    score = overall_score(scored)
    thresholds = (version.config_snapshot or {}).get("grade_thresholds") if isinstance(version.config_snapshot, dict) else None
    return {
        "version_id": str(version.id),
        "lines": lines,
        "rows": scored,
        "score": score,
        "grade": grade_for(score, thresholds),
        "basis": basis_payload(version),
    }


def overlay_pinned_kpis(
    db: Session,
    team_name: str,
    level: str,
    position: str | None,
    year: int,
    month: int,
    kpis: list[dict],
) -> list[dict]:
    """Attach a pinned scoring basis without replacing a saved aggregation weight."""
    if not schema_ready(db) or not kpis or int(year or 0) < 1 or int(month or 0) < 1 or int(month or 0) > 12:
        return kpis
    team = (
        db.query(Team)
        .filter(Team.is_active.is_(True))
        .all()
    )
    match = next((row for row in team if logical_team_name(row).casefold() == str(team_name).casefold()), None)
    if match is None:
        return kpis
    version = approved_version(db, team_id=match.id, level=level, position=position, year=year, month=month)
    if version is None:
        return kpis
    by_key = {str(line.get("kpi_key")): line for line in snapshot_lines(version)}
    updated = []
    for kpi in kpis:
        copy = dict(kpi)
        line = by_key.get(str(copy.get("key") or copy.get("kpi_key") or ""))
        if line:
            if "aggregation_weight" not in copy:
                copy["aggregation_weight"] = copy.get("weight")
            copy["direction"] = line.get("direction")
            copy["evaluation_pinned"] = True
            copy["scoring_weight"] = line.get("weight")
            copy["weight"] = line.get("weight")
            if line.get("target_mode") == "fixed" and line.get("target") is not None:
                copy["target"] = line.get("target")
                copy["target_value"] = line.get("target")
        updated.append(copy)
    return updated
