"""Resolve one approved basis for an exact team, level, position, and month.

Schema inspection uses the caller's session connection and does not roll the
caller's transaction back. ``schema_ready`` returns false only for a truly old
database that has no monthly marker (no ``evaluation_scopes`` table, and no
``performance_level`` column on versions). Once that monthly schema is
activated, both ``schema_ready`` and ``assert_schema`` require the full
history schema: scope columns, the revisions table and its columns, version
and revision guards, and ``missing_history_objects``. A missing guard or table
raises ``SchemaIncomplete`` (status 503) even when no approved row exists.
PostgreSQL inspection targets the ``public`` schema explicitly. It does not
follow ``current_schema()`` or ``search_path``. ``score_basis`` does not query
the database.

``require_approved_capability(version, *, team_name, config, year=None, month=None)``
uses the version's exact period when ``year`` or ``month`` is omitted. Pass
both only when they name that same period.

``lock_team_rows(db, team_ids)`` is the PostgreSQL ``SELECT ... ORDER BY id
FOR UPDATE`` the upload seeder and the evaluation lifecycle share. Call it
before reading an approved pin and before deleting or replacing performance
rows. The lock lasts until the caller commits or rolls back.

``overlay_pinned_kpis(..., records=None, *, preview_approved=False)`` leaves
historical KPI targets and evidence unchanged when ``records`` is omitted.
It does not query performance rows or the latest approved version on that
path. Pass the already-authorized current-period records to read each row's
saved ``evaluation_basis``. ``preview_approved=True`` is the only settings
preview, and historical BSC callers do not use it.
"""

from __future__ import annotations

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from models.evaluation_history_schema import REVISION_COLUMNS, missing_history_objects
from models.models import Team, TeamConfigurationVersion
from services.evaluation.access import SchemaIncomplete
from services.evaluation.periods import month_aliases, month_name, month_number
from services.evaluation.scoring import SUPPORTED_DIRECTIONS, conflicts_for, grade_for, overall_score, score_rows
from utils.team_identity import logical_team_name

SCOPE_COLUMNS = (
    "id",
    "team_id",
    "team_key",
    "display_name",
    "performance_level",
    "position_name",
    "readiness",
    "block_reason",
    "history_note",
    "ambiguous_kpis",
    "importer_name",
    "policy_family",
    "source_kind",
    "updated_at",
)
_AHT_KEY = "AHT"


def _connection(db: Session):
    """The session's connection. Do not check out a second pool connection."""
    return db.connection()


def _table_names(connection) -> set[str]:
    dialect = connection.dialect.name
    if dialect == "sqlite":
        rows = connection.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))
    elif dialect == "postgresql":
        rows = connection.execute(
            text(
                "SELECT c.relname FROM pg_catalog.pg_class c "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r'"
            )
        )
    else:
        raise RuntimeError(f"Evaluation schema inspection does not support {dialect}.")
    return {row[0] for row in rows}


def _column_names(connection, table: str) -> set[str]:
    dialect = connection.dialect.name
    if dialect == "sqlite":
        rows = connection.execute(text(f"PRAGMA table_info({table})"))
        return {row[1] for row in rows}
    rows = connection.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :table"
        ),
        {"table": table},
    )
    return {row[0] for row in rows}


def monthly_schema_activated(connection) -> bool:
    """Whether this database has started installing monthly evaluation objects.

    A synthetic database with no history tables, and an old versions table that
    has no ``performance_level`` column and no ``evaluation_scopes`` table, is
    not activated. The probe does not select a missing column.
    """
    tables = _table_names(connection)
    if "evaluation_scopes" in tables:
        return True
    if "team_configuration_versions" not in tables:
        return False
    if "performance_level" not in _column_names(connection, "team_configuration_versions"):
        return False
    connection.execute(text("SELECT performance_level FROM team_configuration_versions WHERE performance_level IS NOT NULL LIMIT 1"))
    return True


def schema_gaps(connection) -> list[str]:
    """Missing scope columns, revision columns, and history-guard objects.

    Once monthly evaluation is activated, both ``schema_ready`` and
    ``assert_schema`` use this full list. A missing revisions table is
    incomplete even when no approved row exists.
    """
    gaps: list[str] = []
    tables = _table_names(connection)
    if "evaluation_scopes" not in tables:
        gaps.append("table evaluation_scopes")
    else:
        present = _column_names(connection, "evaluation_scopes")
        gaps.extend(f"column evaluation_scopes.{name}" for name in SCOPE_COLUMNS if name not in present)
    if "evaluation_revisions" not in tables:
        gaps.append("table evaluation_revisions")
    else:
        present = _column_names(connection, "evaluation_revisions")
        gaps.extend(f"column evaluation_revisions.{name}" for name in REVISION_COLUMNS if name not in present)
    gaps.extend(missing_history_objects(connection))
    return gaps


def _incomplete(gaps: list[str]) -> SchemaIncomplete:
    listed = "; ".join(gaps[:12])
    return SchemaIncomplete(
        "Evaluation settings schema is incomplete. Run alembic upgrade head. "
        "Monthly evaluation is refused until the history guards and scope tables exist. "
        + listed,
        missing=list(gaps),
    )


def assert_schema(db: Session) -> None:
    """Refuse management settings until history guards and scope columns exist.

    Inspection does not roll back the caller's transaction.
    """
    gaps = schema_gaps(_connection(db))
    if gaps:
        raise _incomplete(gaps)


def schema_ready(db: Session) -> bool:
    """True when an activated monthly schema has the full history contract.

    A legacy database with no monthly marker returns false so upload can keep
    the workbook score. An activated schema missing any scope column, revision
    table or column, or history guard raises ``SchemaIncomplete`` and does not
    return none as a fallback. Database failures propagate. This does not roll
    back the caller and does not cache a previous answer on the session.
    """
    connection = _connection(db)
    if not monthly_schema_activated(connection):
        return False
    gaps = schema_gaps(connection)
    if gaps:
        raise _incomplete(gaps)
    return True


def _team_lock_query(db: Session, ids: list):
    """One ``SELECT ... ORDER BY id FOR UPDATE`` for every team id in this write.

    Callers compile this statement with the PostgreSQL dialect to see
    ``FOR UPDATE``. SQLite executes the same statement without a row lock.
    The ``ORDER BY id`` is the deadlock order: the full id set, not the first pin.
    """
    return (
        db.query(Team)
        .filter(Team.id.in_(ids))
        .order_by(Team.id.asc())
        .with_for_update()
    )


def lock_team_rows(db: Session, team_ids) -> list:
    """Lock team rows in primary-key order before a pin read or a performance write.

    PostgreSQL renders ``FOR UPDATE``. The row lock is held by the caller's
    transaction until commit, and a preview rollback releases it. SQLite has
    no row lock; the same ordered read still runs. Pass every team the
    transaction will write. Locking a subset after another team is already
    locked can deadlock, so callers lock the full set once, before
    ``approved_version`` and before deleting performance rows. Each acquired
    id list is appended to ``db.info["evaluation_team_lock_order"]``.
    """
    ids = []
    seen = set()
    for team_id in team_ids or []:
        if team_id is None or team_id in seen:
            continue
        seen.add(team_id)
        ids.append(team_id)
    if not ids:
        return []
    rows = _team_lock_query(db, ids).all()
    db.info.setdefault("evaluation_team_lock_order", []).append([row.id for row in rows])
    return rows


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


def _period_numbers(year, month) -> tuple[int | None, int | None]:
    if year is None and month is None:
        return None, None
    try:
        parsed_year = None if year is None else int(year)
    except (TypeError, ValueError):
        parsed_year = None
    try:
        parsed_month = None if month is None else month_number(month)
    except Exception:
        parsed_month = None
    return parsed_year, parsed_month


def _refuse_capability(message: str, reason: str):
    from services.evaluation.access import EvaluationError

    raise EvaluationError(
        message,
        code="unsupported_calculation",
        edit_mode="blocked",
        weight_only_allowed=False,
        capability_reason=reason,
    )


def _assert_outbound_version_lines(version: TeamConfigurationVersion, team_name: str, year: int, month: int) -> None:
    """Weighted keys must match the exact period. Default weight numbers need not.

    Admin may change weights. AHT may remain a zero-weight diagnostic and cannot
    be given a positive weight. Policy must stay the capped employee ratio.
    """
    from services.evaluation.capabilities import is_outbound_employee_scope
    from services.outbound_period_basis import period_capability

    level = str(getattr(version, "performance_level", "") or "")
    position = str(getattr(version, "position_name", "") or "")
    if not is_outbound_employee_scope(team_name, level, position):
        return
    decision = period_capability(year, month)
    if not decision.get("catalog_template_supported"):
        _refuse_capability(
            "Approved recomputation is refused for this monthly configuration. "
            f"Outbound {decision.get('period') or 'this period'} is not an admitted exact month.",
            decision.get("status") or "unconfigured",
        )
    snapshot = version.config_snapshot if isinstance(version.config_snapshot, dict) else {}
    policy = str(snapshot.get("policy") or "employee_ratio")
    if policy != "employee_ratio":
        _refuse_capability(
            "Approved recomputation is refused for this monthly configuration. "
            f"Policy {policy} is not the audited employee cap.",
            "policy",
        )
    canonical = set(decision.get("scored_keys") or [])
    weighted = set()
    for line in snapshot_lines(version):
        key = str(line.get("kpi_key") or "")
        try:
            weight = float(line.get("weight") or 0)
        except (TypeError, ValueError):
            _refuse_capability(
                "Approved recomputation is refused for this monthly configuration. A line weight is not a number.",
                "weight",
            )
        direction = str(line.get("direction") or "")
        if direction and direction not in SUPPORTED_DIRECTIONS:
            _refuse_capability(
                "Approved recomputation is refused for this monthly configuration. "
                f"{key} direction is not supported.",
                "direction",
            )
        capping = line.get("capping")
        if capping not in (None, "", "capped_at_100"):
            _refuse_capability(
                "Approved recomputation is refused for this monthly configuration. "
                f"Cap {capping} is not the audited 100% cap.",
                "cap",
            )
        if line.get("cap_achievement") is False:
            _refuse_capability(
                "Approved recomputation is refused for this monthly configuration. The audited 100% cap is turned off.",
                "cap",
            )
        if key == _AHT_KEY:
            if weight > 0:
                _refuse_capability(
                    "Approved recomputation is refused for this monthly configuration. "
                    "AHT is an optional zero-weight diagnostic and cannot be activated.",
                    "aht",
                )
            continue
        if weight > 0:
            weighted.add(key)
        elif key not in canonical:
            _refuse_capability(
                "Approved recomputation is refused for this monthly configuration. "
                f"{key} is outside the canonical period template.",
                "kpi_key",
            )
        if key in canonical and direction not in {"", "higher_better"}:
            _refuse_capability(
                "Approved recomputation is refused for this monthly configuration. "
                f"{key} must stay higher-is-better.",
                "direction",
            )
    if weighted != canonical:
        _refuse_capability(
            "Approved recomputation is refused for this monthly configuration. "
            "The weighted KPI set does not match the canonical exact period. "
            "Weight values may differ from the source defaults, but the scored keys may not.",
            "scored_keys",
        )


def require_approved_capability(
    version: TeamConfigurationVersion,
    *,
    team_name: str,
    config: dict | None,
    year: int | None = None,
    month: int | str | None = None,
):
    """Refuse recomputation when an approved month is not an audited ratio.

    Upload preview imports this from ``services.evaluation.resolver`` and calls
    it after ``approved_version`` finds a row and after the team row is locked.
    Pass the canonical team name and the checked-in team file as ``config``
    (``None`` when that file is missing). ``year`` and ``month`` default to the
    version's ``effective_from_year`` and ``effective_from_month``. When the
    caller passes them, they must name that same period.

    A blocked decision raises ``EvaluationError`` with
    ``code="unsupported_calculation"``, ``edit_mode="blocked"``, and
    ``weight_only_allowed=False``. For an admitted Outbound month the weighted
    keys must match ``period_capability`` for that exact month. Admin-changed
    weights are accepted. The function does not read or write performance
    evidence and does not query the database, so the original workbook values
    stay in place. Historical reads do not call it. ``score_basis`` stays a
    pure function of the version and the rows.
    """
    from services.evaluation.catalog import calculation_for

    version_year = getattr(version, "effective_from_year", None)
    version_month = getattr(version, "effective_from_month", None)
    if year is None:
        year = version_year
    if month is None:
        month = version_month
    asked_year, asked_month = _period_numbers(year, month)
    stored_year, stored_month = _period_numbers(version_year, version_month)
    if stored_year is not None and asked_year is not None and asked_year != stored_year:
        _refuse_capability(
            "Approved recomputation is refused for this monthly configuration. The requested year is not the version period.",
            "period",
        )
    if stored_month is not None and asked_month is not None and asked_month != stored_month:
        _refuse_capability(
            "Approved recomputation is refused for this monthly configuration. The requested month is not the version period.",
            "period",
        )
    decision = calculation_for(
        team_name,
        str(getattr(version, "performance_level", "") or ""),
        str(getattr(version, "position_name", "") or ""),
        config,
        year=year,
        month=month,
    )
    if not decision.allows_ratio_edit:
        _refuse_capability(
            "Approved recomputation is refused for this monthly configuration. " + decision.reason,
            decision.reason,
        )
    if asked_year is not None and asked_month is not None:
        _assert_outbound_version_lines(version, team_name, asked_year, asked_month)
    return decision


def score_basis(version: TeamConfigurationVersion, rows: list[dict], *, check_conflicts: bool = True) -> dict:
    """Same function for preview and commit. Apply rescoring passes check_conflicts=False.

    This function does not look up a team, an approved row, or the schema.
    Call ``require_approved_capability`` before it when a pin must be gated.
    """
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
    if isinstance(thresholds, dict):
        from services.evaluation.scoring import _finite

        for band, limit in thresholds.items():
            _finite(limit, f"Grade threshold {band}")
    return {
        "version_id": str(version.id),
        "lines": lines,
        "rows": scored,
        "score": score,
        "grade": grade_for(score, thresholds),
        "basis": basis_payload(version),
    }


def _record_attr(record, key: str, default=None):
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


def _saved_basis(record) -> dict | None:
    payload = _record_attr(record, "record_payload")
    if not isinstance(payload, dict):
        return None
    basis = payload.get("evaluation_basis")
    if not isinstance(basis, dict) or basis.get("pinned") is not True:
        return None
    return basis


def _record_team_name(record) -> str:
    team = _record_attr(record, "team")
    if isinstance(team, str):
        return team
    if team is not None:
        return logical_team_name(team)
    payload = _record_attr(record, "record_payload")
    if isinstance(payload, dict) and payload.get("team"):
        return str(payload.get("team"))
    return ""


def _record_matches_scope(record, team_name: str, level: str, position: str | None, year: int, month: int) -> bool:
    if _record_team_name(record).casefold() != str(team_name or "").casefold():
        return False
    if str(_record_attr(record, "performance_level") or "") != str(level or ""):
        return False
    record_position = _record_attr(record, "position_name")
    if record_position is None:
        record_position = _record_attr(record, "position") or ""
    if str(record_position or "") != str(position or ""):
        return False
    try:
        if int(_record_attr(record, "year") or 0) != int(year):
            return False
    except (TypeError, ValueError):
        return False
    aliases = {item.casefold() for item in month_aliases(month)}
    record_month = str(_record_attr(record, "month") or "").strip().casefold()
    return record_month in aliases


def _basis_matches_period(basis: dict, year: int, month: int) -> bool:
    try:
        if basis.get("year") is not None and int(basis.get("year") or 0) != int(year):
            return False
    except (TypeError, ValueError, OverflowError):
        return False
    if basis.get("month") is not None:
        try:
            if month_number(basis.get("month")) != int(month):
                return False
        except Exception:
            return False
    return True


def _apply_score_line(kpi: dict, line: dict | None) -> dict:
    """Copy scoring fields. The caller's business weight stays on ``weight``."""
    copy = dict(kpi)
    if line is None:
        return copy
    if "aggregation_weight" not in copy:
        copy["aggregation_weight"] = copy.get("weight")
    copy["direction"] = line.get("direction")
    copy["evaluation_pinned"] = True
    copy["scoring_weight"] = line.get("weight")
    if line.get("target_mode") == "fixed" and line.get("target") is not None:
        copy["target"] = line.get("target")
        copy["target_value"] = line.get("target")
    return copy


def _line_signature(line: dict) -> tuple:
    return (
        line.get("direction"),
        line.get("weight"),
        line.get("target"),
        line.get("target_mode"),
    )


def _overlay_saved_lines(kpis: list[dict], line_sets: list[list[dict]]) -> list[dict]:
    """Apply one saved pin, or only the keys every saved pin agrees on."""
    if len(line_sets) == 1:
        by_key = {str(line.get("kpi_key")): line for line in line_sets[0]}
        return [_apply_score_line(kpi, by_key.get(str(kpi.get("key") or kpi.get("kpi_key") or ""))) for kpi in kpis]
    indexes = []
    for lines in line_sets:
        indexes.append({str(line.get("kpi_key")): line for line in lines})
    updated = []
    for kpi in kpis:
        key = str(kpi.get("key") or kpi.get("kpi_key") or "")
        rows = [found.get(key) for found in indexes]
        if any(row is None for row in rows):
            updated.append(dict(kpi))
            continue
        if len({_line_signature(row) for row in rows}) != 1:
            updated.append(dict(kpi))
            continue
        updated.append(_apply_score_line(kpi, rows[0]))
    return updated


def _overlay_from_records(team_name: str, level: str, position: str | None, year: int, month: int, kpis: list[dict], records) -> list[dict]:
    """Use the authorized rows' saved basis. Approving a newer version does not relabel them."""
    matched = [record for record in records if _record_matches_scope(record, team_name, level, position, year, month)]
    if not matched:
        return [dict(kpi) for kpi in kpis]
    bases = []
    for record in matched:
        basis = _saved_basis(record)
        if basis is None or not _basis_matches_period(basis, year, month):
            return [dict(kpi) for kpi in kpis]
        bases.append(basis)
    line_sets = [list(basis.get("lines") or []) for basis in bases]
    # A shared version label is not proof that every saved row agrees per KPI.
    return _overlay_saved_lines(kpis, line_sets)


def overlay_pinned_kpis(
    db: Session,
    team_name: str,
    level: str,
    position: str | None,
    year: int,
    month: int,
    kpis: list[dict],
    records: list | None = None,
    *,
    preview_approved: bool = False,
) -> list[dict]:
    """Attach scoring fields without replacing a business or aggregation weight.

    ``records`` is the authorized set already filtered by team, level, branch,
    and region. This function narrows that set to the exact position, year, and
    month and reads each row's saved ``evaluation_basis``. It does not query
    performance records, so a director scope cannot grow inside this call and
    another branch's metadata is not loaded. A row with no pinned basis, including
    a rollback that restored the legacy payload, leaves the caller's target and
    evidence unchanged. Mixed saved bases do not become one pin: a KPI is
    overlaid only when every matched row agrees on that key. An empty list is
    an authorized set with no rows, not a cue to look up a newer approval.

    Omitting ``records`` leaves the caller's targets and evidence unchanged and
    does not query the latest approved version. ``preview_approved=True`` is an
    explicit settings preview of one named active team. Historical BSC does not
    pass that flag. Business ``weight`` stays the caller's aggregation weight.
    ``scoring_weight`` carries a saved pin.
    """
    if not kpis or int(year or 0) < 1 or int(month or 0) < 1 or int(month or 0) > 12:
        return kpis
    if records is not None:
        return _overlay_from_records(team_name, level, position, int(year), int(month), kpis, records)
    if not preview_approved:
        return [dict(kpi) for kpi in kpis]
    if not schema_ready(db):
        return kpis
    normalized = str(team_name or "").strip().casefold()
    teams = (
        db.query(Team)
        .filter(Team.is_active.is_(True))
        .filter(
            or_(
                func.lower(Team.name) == normalized,
                func.lower(func.coalesce(Team.display_name, Team.name)) == normalized,
                func.lower(Team.db_name) == normalized,
            )
        )
        .all()
    )
    if len(teams) != 1:
        return kpis
    version = approved_version(db, team_id=teams[0].id, level=level, position=position, year=year, month=month)
    if version is None:
        return kpis
    return _overlay_saved_lines(kpis, [snapshot_lines(version)])
