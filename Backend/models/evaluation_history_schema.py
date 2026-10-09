"""Monthly evaluation history guards shared by Alembic and fresh bootstrap.

Legacy rows keep a NULL performance level and their open-ended period.
Monthly rows are an exact team, level, position, and calendar month.
An empty position string means the scope has no position. NULL does not.

Actor snapshots are JSON objects, either ``{"state": "unknown"}`` or
``{"state": "known", ...}``. Existing rows are marked unknown. This module
does not read the users table and does not invent a name, role, or user id.
"""

from __future__ import annotations

from sqlalchemy import event, inspect, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.elements import ClauseElement


class ActorUnknownDefault(ClauseElement):
    """JSON object default that stays valid SQL on SQLite and PostgreSQL."""

    inherit_cache = True


@compiles(ActorUnknownDefault, "postgresql")
def _compile_actor_unknown_postgresql(element, compiler, **kw):
    return """'{"state":"unknown"}'::jsonb"""


@compiles(ActorUnknownDefault)
def _compile_actor_unknown_default(element, compiler, **kw):
    return """'{"state":"unknown"}'"""


REVISION = "f7c3a9e1d5b8"
PREDECESSOR_REVISION = "e1b6c9d4a870"
ROOT_REVISION = "975c072657f1"

VERSION_TABLE = "team_configuration_versions"
REVISION_TABLE = "evaluation_revisions"
ACTOR_UNKNOWN_SQL = """'{"state":"unknown"}'"""
LEVELS_SQL = "'Employee', 'Managerial', 'Corporate'"
MONTH_NAMES = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)

VERSION_ACTOR_COLUMNS = ("actor_created_snapshot", "actor_published_snapshot")
REVISION_ACTOR_COLUMNS = ("actor_snapshot",)

VERSION_CHECKS = {
    "ck_team_config_effective_from_month": "effective_from_month BETWEEN 1 AND 12",
    "ck_team_config_effective_until_month": (
        "effective_until_month IS NULL OR effective_until_month BETWEEN 1 AND 12"
    ),
    "ck_team_config_effective_range": (
        "effective_until_year IS NULL OR "
        "(effective_until_year * 12 + effective_until_month) >= "
        "(effective_from_year * 12 + effective_from_month)"
    ),
    "ck_team_config_version_level": (
        f"performance_level IS NULL OR performance_level IN ({LEVELS_SQL})"
    ),
    "ck_team_config_monthly_position": "performance_level IS NULL OR position_name IS NOT NULL",
    "ck_team_config_monthly_status": (
        "performance_level IS NULL OR status IN ('draft', 'approved', 'superseded')"
    ),
    "ck_team_config_monthly_published_marker": (
        "performance_level IS NULL OR status <> 'approved' OR published_at IS NOT NULL"
    ),
}
REVISION_STATUS_SQL = "status IN ('active', 'rolled_back', 'superseded')"
REVISION_CHECKS = {
    "ck_evaluation_revision_status": REVISION_STATUS_SQL,
    "ck_evaluation_revision_month": "month BETWEEN 1 AND 12",
    "ck_evaluation_revision_level": f"performance_level IN ({LEVELS_SQL})",
    "ck_evaluation_revision_year": "year BETWEEN 2000 AND 2200",
}

VERSION_INDEXES = (
    "uq_team_config_version",
    "idx_team_config_coverage",
    "uq_team_config_one_approved_month",
    "uq_team_config_one_draft_month",
)
REVISION_INDEXES = (
    "idx_evaluation_revision_period",
    "uq_evaluation_revision_one_active",
)
VERSION_TRIGGERS = (
    "trg_team_config_version_guard",
)
REVISION_TRIGGERS = (
    "trg_evaluation_revision_guard",
)
SQLITE_VERSION_TRIGGERS = (
    "trg_team_config_version_no_delete_sealed",
    "trg_team_config_version_actor_insert",
    "trg_team_config_version_actor_update",
    "trg_team_config_version_legacy_level",
    "trg_team_config_version_identity",
    "trg_team_config_version_status",
    "trg_team_config_version_approve_marker",
    "trg_team_config_version_sealed_evidence",
)
SQLITE_REVISION_TRIGGERS = (
    "trg_evaluation_revision_no_delete",
    "trg_evaluation_revision_actor_insert",
    "trg_evaluation_revision_actor_update",
    "trg_evaluation_revision_evidence",
    "trg_evaluation_revision_status",
)

VERSION_COLUMNS = (
    "id",
    "team_id",
    "version_number",
    "status",
    "effective_month",
    "effective_year",
    "config_snapshot",
    "config_checksum",
    "created_by_user_id",
    "published_by_user_id",
    "created_at",
    "published_at",
    "superseded_at",
    "notes",
    "effective_from_month",
    "effective_from_year",
    "effective_until_month",
    "effective_until_year",
    "preview_snapshot",
    "total_weight",
    "overall_score",
    "is_active",
    "performance_level",
    "position_name",
    "actor_created_snapshot",
    "actor_published_snapshot",
)
REVISION_COLUMNS = (
    "id",
    "team_id",
    "performance_level",
    "position_name",
    "year",
    "month",
    "version_id",
    "status",
    "previous_revision_id",
    "prior_snapshot",
    "applied_snapshot",
    "created_by_user_id",
    "created_at",
    "actor_snapshot",
)

# Column -> required ON DELETE action. User references stay SET NULL.
VERSION_FOREIGN_KEYS = {
    "team_id": "RESTRICT",
    "created_by_user_id": "SET NULL",
    "published_by_user_id": "SET NULL",
}
REVISION_FOREIGN_KEYS = {
    "team_id": "RESTRICT",
    "version_id": "RESTRICT",
    "previous_revision_id": "RESTRICT",
    "created_by_user_id": "SET NULL",
}

FIELD_CONTRACT = {
    "version_actor_created_snapshot": (
        "JSON object written on insert. state is unknown or known. "
        "Immutable after insert. Existing rows are {\"state\": \"unknown\"}."
    ),
    "version_actor_published_snapshot": (
        "JSON object. Mutable while the monthly row is still a draft, including "
        "the draft-to-approved update. Immutable once the stored status is "
        "approved or superseded. Existing rows are {\"state\": \"unknown\"}."
    ),
    "revision_actor_snapshot": (
        "JSON object written on insert and immutable after that. "
        "Existing rows are {\"state\": \"unknown\"}."
    ),
    "known_actor_fields": (
        "When state is known, later workflow may include user_id, username, "
        "full_name, and role. The database requires only state."
    ),
    "position_name": "Monthly rows use '' for no position. NULL is not a monthly position.",
    "monthly_end_fields": (
        "A monthly row requires effective_until_month and effective_until_year, "
        "both equal to the from month. NULL does not satisfy the equality."
    ),
    "monthly_status_transitions": ("draft->approved", "approved->superseded"),
    "revision_status_transitions": ("active->rolled_back", "active->superseded"),
}
EXACT_PERIOD_REQUIRED_SQL = (
    "effective_until_month is not null",
    "effective_until_year is not null",
)
GUARD_BODY_SNIPPETS = {
    "guard_team_configuration_version": (
        "monthly approved evaluation history cannot be deleted",
        "approved monthly evaluation evidence is immutable",
        "illegal monthly configuration status transition",
        "legacy configuration versions cannot become monthly bindings",
        "monthly evaluation identity cannot change",
    ),
    "guard_evaluation_revision": (
        "evaluation revision history cannot be deleted",
        "evaluation revision evidence is immutable",
        "illegal evaluation revision status transition",
    ),
}


def monthly_exact_period_sql() -> str:
    names = ", ".join(f"'{name}'" for name in MONTH_NAMES)
    cases = " ".join(
        f"WHEN '{name}' THEN {number}" for number, name in enumerate(MONTH_NAMES, start=1)
    )
    return (
        "performance_level IS NULL OR ("
        "position_name IS NOT NULL "
        "AND effective_from_month BETWEEN 1 AND 12 "
        "AND effective_until_month IS NOT NULL "
        "AND effective_until_year IS NOT NULL "
        "AND effective_until_month = effective_from_month "
        "AND effective_until_year = effective_from_year "
        "AND effective_year = effective_from_year "
        "AND effective_from_year BETWEEN 2000 AND 2200 "
        f"AND lower(trim(effective_month)) IN ({names}) "
        f"AND (CASE lower(trim(effective_month)) {cases} ELSE NULL END) = effective_from_month"
        ")"
    )


def version_check_sql() -> dict[str, str]:
    checks = dict(VERSION_CHECKS)
    checks["ck_team_config_monthly_exact_period"] = monthly_exact_period_sql()
    return checks


def _month_number(value) -> int | None:
    if value is None:
        return None
    text_value = str(value).strip().casefold()
    if text_value.isdigit():
        number = int(text_value)
        return number if 1 <= number <= 12 else None
    for number, name in enumerate(MONTH_NAMES, start=1):
        if text_value == name:
            return number
    return None


def collect_preflight_problems(connection) -> list[dict]:
    """Return actionable conflicts. Callers must not delete or choose a row."""
    problems: list[dict] = []
    version_rows = connection.execute(
        text(
            """
            SELECT id, team_id, performance_level, position_name, status,
                   effective_month, effective_year, effective_from_year, effective_from_month,
                   effective_until_year, effective_until_month, published_at
            FROM team_configuration_versions
            WHERE performance_level IS NOT NULL
            """
        )
    ).mappings().all()
    grouped: dict[tuple, list[dict]] = {}
    for row in version_rows:
        item = dict(row)
        reasons = _monthly_row_reasons(item)
        if reasons:
            problems.append(
                {
                    "code": "invalid_monthly_version",
                    "version_id": str(item["id"]),
                    "team_id": str(item["team_id"]),
                    "performance_level": item["performance_level"],
                    "position_name": item["position_name"],
                    "status": item["status"],
                    "effective_from_year": item["effective_from_year"],
                    "effective_from_month": item["effective_from_month"],
                    "reasons": reasons,
                }
            )
        if item["status"] in {"approved", "draft"}:
            key = (
                str(item["team_id"]),
                item["performance_level"],
                "" if item["position_name"] is None else item["position_name"],
                item["effective_from_year"],
                item["effective_from_month"],
                item["status"],
            )
            grouped.setdefault(key, []).append(item)
    for key, rows in grouped.items():
        if len(rows) < 2:
            continue
        problems.append(
            {
                "code": "duplicate_monthly_binding",
                "team_id": key[0],
                "performance_level": key[1],
                "canonical_position_name": key[2],
                "effective_from_year": key[3],
                "effective_from_month": key[4],
                "status": key[5],
                "versions": [
                    {"id": str(row["id"]), "position_name": row["position_name"]}
                    for row in rows
                ],
            }
        )

    revision_rows = connection.execute(
        text(
            """
            SELECT id, team_id, performance_level, position_name, status, year, month
            FROM evaluation_revisions
            """
        )
    ).mappings().all()
    active: dict[tuple, list[dict]] = {}
    for row in revision_rows:
        item = dict(row)
        reasons = []
        if item["performance_level"] not in {"Employee", "Managerial", "Corporate"}:
            reasons.append("performance level is not Employee, Managerial, or Corporate")
        if item["position_name"] is None:
            reasons.append("position_name is NULL")
        if item["status"] not in {"active", "rolled_back", "superseded"}:
            reasons.append("status is not active, rolled_back, or superseded")
        if item["month"] is None or not 1 <= int(item["month"]) <= 12:
            reasons.append("month is outside 1..12")
        if item["year"] is None or not 2000 <= int(item["year"]) <= 2200:
            reasons.append("year is outside 2000..2200")
        if reasons:
            problems.append(
                {
                    "code": "invalid_evaluation_revision",
                    "revision_id": str(item["id"]),
                    "team_id": str(item["team_id"]),
                    "reasons": reasons,
                }
            )
        if item["status"] == "active":
            active_key = (
                str(item["team_id"]),
                item["performance_level"],
                item["position_name"],
                item["year"],
                item["month"],
            )
            active.setdefault(active_key, []).append(item)
    for key, rows in active.items():
        if len(rows) < 2:
            continue
        problems.append(
            {
                "code": "duplicate_active_revision",
                "team_id": key[0],
                "performance_level": key[1],
                "position_name": key[2],
                "year": key[3],
                "month": key[4],
                "revision_ids": [str(row["id"]) for row in rows],
            }
        )
    return problems


def _monthly_row_reasons(row: dict) -> list[str]:
    reasons = []
    if row["performance_level"] not in {"Employee", "Managerial", "Corporate"}:
        reasons.append("performance level is not Employee, Managerial, or Corporate")
    if row["status"] not in {"draft", "approved", "superseded"}:
        reasons.append("monthly status is not draft, approved, or superseded")
    if row["effective_from_month"] is None or not 1 <= int(row["effective_from_month"]) <= 12:
        reasons.append("effective_from_month is outside 1..12")
    if row["effective_from_year"] is None or not 2000 <= int(row["effective_from_year"]) <= 2200:
        reasons.append("effective_from_year is outside 2000..2200")
    if row["effective_until_month"] is None or row["effective_until_year"] is None:
        reasons.append("monthly end month and year must both be present")
    elif (
        row["effective_until_year"] != row["effective_from_year"]
        or row["effective_until_month"] != row["effective_from_month"]
    ):
        reasons.append("monthly coverage is not the exact from month")
    if row["effective_year"] != row["effective_from_year"]:
        reasons.append("effective_year does not match effective_from_year")
    if _month_number(row["effective_month"]) != row["effective_from_month"]:
        reasons.append("effective_month does not name effective_from_month")
    if row["status"] == "approved" and row["published_at"] is None:
        reasons.append("approved monthly row has no published_at")
    return reasons


def format_preflight_failure(problems: list[dict]) -> str:
    return (
        "monthly evaluation history preflight refused; no rows were deleted or chosen: "
        f"{problems}"
    )


def normalize_harmless_null_positions(connection) -> int:
    result = connection.execute(
        text(
            """
            UPDATE team_configuration_versions
            SET position_name = ''
            WHERE performance_level IS NOT NULL
              AND position_name IS NULL
            """
        )
    )
    return int(result.rowcount or 0)


def evidence_blocks_downgrade(connection) -> dict:
    approved = connection.execute(
        text(
            """
            SELECT id
            FROM team_configuration_versions
            WHERE performance_level IS NOT NULL
              AND status IN ('approved', 'superseded')
            ORDER BY id
            LIMIT 20
            """
        )
    ).scalars().all()
    revisions = connection.execute(
        text("SELECT id FROM evaluation_revisions ORDER BY id LIMIT 20")
    ).scalars().all()
    approved_count = connection.execute(
        text(
            """
            SELECT count(*)
            FROM team_configuration_versions
            WHERE performance_level IS NOT NULL
              AND status IN ('approved', 'superseded')
            """
        )
    ).scalar_one()
    revision_count = connection.execute(text("SELECT count(*) FROM evaluation_revisions")).scalar_one()
    return {
        "approved_or_superseded_versions": int(approved_count or 0),
        "evaluation_revisions": int(revision_count or 0),
        "sample_version_ids": [str(value) for value in approved],
        "sample_revision_ids": [str(value) for value in revisions],
    }


def add_actor_columns(connection) -> None:
    json_type = "jsonb" if connection.dialect.name == "postgresql" else "JSON"
    statements = [
        f"ALTER TABLE {VERSION_TABLE} ADD COLUMN actor_created_snapshot {json_type}",
        f"ALTER TABLE {VERSION_TABLE} ADD COLUMN actor_published_snapshot {json_type}",
        f"ALTER TABLE {REVISION_TABLE} ADD COLUMN actor_snapshot {json_type}",
    ]
    for statement in statements:
        connection.execute(text(statement))
    connection.execute(
        text(
            f"""
            UPDATE {VERSION_TABLE}
            SET actor_created_snapshot = {ACTOR_UNKNOWN_SQL},
                actor_published_snapshot = {ACTOR_UNKNOWN_SQL}
            """
        )
    )
    connection.execute(
        text(f"UPDATE {REVISION_TABLE} SET actor_snapshot = {ACTOR_UNKNOWN_SQL}")
    )
    if connection.dialect.name == "postgresql":
        default_sql = """'{"state":"unknown"}'::jsonb"""
        for column in VERSION_ACTOR_COLUMNS:
            connection.execute(
                text(f"ALTER TABLE {VERSION_TABLE} ALTER COLUMN {column} SET DEFAULT {default_sql}")
            )
            connection.execute(text(f"ALTER TABLE {VERSION_TABLE} ALTER COLUMN {column} SET NOT NULL"))
        connection.execute(
            text(f"ALTER TABLE {REVISION_TABLE} ALTER COLUMN actor_snapshot SET DEFAULT {default_sql}")
        )
        connection.execute(
            text(f"ALTER TABLE {REVISION_TABLE} ALTER COLUMN actor_snapshot SET NOT NULL")
        )


def install_new_checks_and_index(connection) -> None:
    checks = version_check_sql()
    for name in (
        "ck_team_config_monthly_position",
        "ck_team_config_monthly_exact_period",
        "ck_team_config_monthly_status",
        "ck_team_config_monthly_published_marker",
    ):
        _add_check(connection, VERSION_TABLE, name, checks[name])
    _drop_check(connection, REVISION_TABLE, "ck_evaluation_revision_status")
    for name, sql in REVISION_CHECKS.items():
        if name == "ck_evaluation_revision_month":
            continue
        _add_check(connection, REVISION_TABLE, name, sql)
    connection.execute(
        text(
            f"""
            CREATE UNIQUE INDEX uq_evaluation_revision_one_active
            ON {REVISION_TABLE} (team_id, performance_level, position_name, year, month)
            WHERE status = 'active'
            """
        )
    )


def restrict_history_foreign_keys(connection) -> None:
    _replace_foreign_key(connection, VERSION_TABLE, "team_id", "teams", "RESTRICT")
    _replace_foreign_key(connection, REVISION_TABLE, "team_id", "teams", "RESTRICT")
    _replace_foreign_key(
        connection,
        REVISION_TABLE,
        "previous_revision_id",
        REVISION_TABLE,
        "RESTRICT",
    )


def restore_history_foreign_keys(connection) -> None:
    _replace_foreign_key(connection, VERSION_TABLE, "team_id", "teams", "CASCADE")
    _replace_foreign_key(connection, REVISION_TABLE, "team_id", "teams", "CASCADE")
    _replace_foreign_key(
        connection,
        REVISION_TABLE,
        "previous_revision_id",
        REVISION_TABLE,
        "SET NULL",
    )


def install_history_guards(connection) -> None:
    if connection.dialect.name == "postgresql":
        _install_postgres_guards(connection)
    elif connection.dialect.name == "sqlite":
        _install_sqlite_guards(connection)
    else:
        raise RuntimeError(f"History guards are not implemented for {connection.dialect.name}.")


def remove_history_guards(connection) -> None:
    if connection.dialect.name == "postgresql":
        for name in VERSION_TRIGGERS:
            connection.execute(text(f"DROP TRIGGER IF EXISTS {name} ON {VERSION_TABLE}"))
        for name in REVISION_TRIGGERS:
            connection.execute(text(f"DROP TRIGGER IF EXISTS {name} ON {REVISION_TABLE}"))
        connection.execute(text("DROP FUNCTION IF EXISTS guard_team_configuration_version()"))
        connection.execute(text("DROP FUNCTION IF EXISTS guard_evaluation_revision()"))
        return
    if connection.dialect.name == "sqlite":
        for name in SQLITE_VERSION_TRIGGERS + SQLITE_REVISION_TRIGGERS:
            connection.execute(text(f"DROP TRIGGER IF EXISTS {name}"))


def drop_guard_objects_for_downgrade(connection) -> None:
    remove_history_guards(connection)
    for name in (
        "ck_team_config_monthly_position",
        "ck_team_config_monthly_exact_period",
        "ck_team_config_monthly_status",
        "ck_team_config_monthly_published_marker",
        "ck_evaluation_revision_level",
        "ck_evaluation_revision_year",
    ):
        table = REVISION_TABLE if name.startswith("ck_evaluation_revision") else VERSION_TABLE
        _drop_check(connection, table, name)
    _drop_check(connection, REVISION_TABLE, "ck_evaluation_revision_status")
    _add_check(
        connection,
        REVISION_TABLE,
        "ck_evaluation_revision_status",
        "status IN ('active', 'rolled_back')",
    )
    connection.execute(text("DROP INDEX IF EXISTS uq_evaluation_revision_one_active"))
    restore_history_foreign_keys(connection)
    if connection.dialect.name == "postgresql":
        for column in VERSION_ACTOR_COLUMNS:
            connection.execute(text(f"ALTER TABLE {VERSION_TABLE} DROP COLUMN IF EXISTS {column}"))
        connection.execute(text(f"ALTER TABLE {REVISION_TABLE} DROP COLUMN IF EXISTS actor_snapshot"))


def missing_history_objects(connection) -> list[str]:
    """Required history guards that are absent or whose definitions do not match."""
    dialect = connection.dialect.name
    missing: list[str] = []
    if dialect == "postgresql":
        version_columns = _pg_columns(connection, VERSION_TABLE)
        revision_columns = _pg_columns(connection, REVISION_TABLE)
        version_checks = _pg_check_definitions(connection, VERSION_TABLE)
        revision_checks = _pg_check_definitions(connection, REVISION_TABLE)
        version_indexes = _pg_index_definitions(connection, VERSION_TABLE)
        revision_indexes = _pg_index_definitions(connection, REVISION_TABLE)
        version_triggers = _pg_trigger_definitions(connection, VERSION_TABLE)
        revision_triggers = _pg_trigger_definitions(connection, REVISION_TABLE)
        version_fks = _pg_foreign_keys(connection, VERSION_TABLE)
        revision_fks = _pg_foreign_keys(connection, REVISION_TABLE)
        expected_version_triggers = VERSION_TRIGGERS
        expected_revision_triggers = REVISION_TRIGGERS
    elif dialect == "sqlite":
        version_columns = _sqlite_columns(connection, VERSION_TABLE)
        revision_columns = _sqlite_columns(connection, REVISION_TABLE)
        version_checks = _sqlite_check_names(connection, VERSION_TABLE)
        revision_checks = _sqlite_check_names(connection, REVISION_TABLE)
        version_indexes = _sqlite_indexes(connection, VERSION_TABLE)
        revision_indexes = _sqlite_indexes(connection, REVISION_TABLE)
        version_triggers = _sqlite_triggers(connection, VERSION_TABLE)
        revision_triggers = _sqlite_triggers(connection, REVISION_TABLE)
        version_fks = _sqlite_foreign_keys(connection, VERSION_TABLE)
        revision_fks = _sqlite_foreign_keys(connection, REVISION_TABLE)
        expected_version_triggers = SQLITE_VERSION_TRIGGERS
        expected_revision_triggers = SQLITE_REVISION_TRIGGERS
    else:
        return [f"unsupported dialect {dialect}"]

    missing.extend(_missing_names("column", VERSION_TABLE, VERSION_COLUMNS, version_columns))
    missing.extend(_missing_names("column", REVISION_TABLE, REVISION_COLUMNS, revision_columns))
    missing.extend(_missing_names("check", VERSION_TABLE, version_check_sql(), version_checks))
    missing.extend(_missing_names("check", REVISION_TABLE, REVISION_CHECKS, revision_checks))
    missing.extend(_missing_names("index", VERSION_TABLE, VERSION_INDEXES, version_indexes))
    missing.extend(_missing_names("index", REVISION_TABLE, REVISION_INDEXES, revision_indexes))
    missing.extend(_missing_names("trigger", VERSION_TABLE, expected_version_triggers, version_triggers))
    missing.extend(_missing_names("trigger", REVISION_TABLE, expected_revision_triggers, revision_triggers))
    missing.extend(_missing_actions(VERSION_TABLE, VERSION_FOREIGN_KEYS, version_fks))
    missing.extend(_missing_actions(REVISION_TABLE, REVISION_FOREIGN_KEYS, revision_fks))
    if dialect == "postgresql":
        for column in VERSION_ACTOR_COLUMNS:
            if version_columns.get(column, {}).get("udt") != "jsonb":
                missing.append(f"column {VERSION_TABLE}.{column} must be jsonb")
        if revision_columns.get("actor_snapshot", {}).get("udt") != "jsonb":
            missing.append(f"column {REVISION_TABLE}.actor_snapshot must be jsonb")
        missing.extend(_missing_definition_snippets(
            version_checks.get("ck_team_config_monthly_exact_period", ""),
            EXACT_PERIOD_REQUIRED_SQL,
            f"check {VERSION_TABLE}.ck_team_config_monthly_exact_period",
        ))
        missing.extend(_missing_guard_bodies(_pg_guard_functions(connection)))
    else:
        table_sql = _sqlite_table_sql(connection, VERSION_TABLE)
        missing.extend(_missing_definition_snippets(
            table_sql,
            EXACT_PERIOD_REQUIRED_SQL,
            f"check {VERSION_TABLE}.ck_team_config_monthly_exact_period",
        ))
        trigger_sql = "\n".join(_sqlite_trigger_sql(connection, VERSION_TABLE).values())
        trigger_sql += "\n" + "\n".join(_sqlite_trigger_sql(connection, REVISION_TABLE).values())
        for snippets in GUARD_BODY_SNIPPETS.values():
            missing.extend(_missing_definition_snippets(trigger_sql, snippets, "sqlite history trigger"))
    return missing


def _missing_definition_snippets(definition: str, snippets: tuple[str, ...], label: str) -> list[str]:
    normalized = _normalize_catalog_sql(definition).casefold()
    return [f"{label} missing {snippet}" for snippet in snippets if snippet not in normalized]


def _missing_guard_bodies(bodies: dict[str, str]) -> list[str]:
    missing = []
    for name, snippets in GUARD_BODY_SNIPPETS.items():
        body = bodies.get(name, "")
        if not body:
            missing.append(f"function {name}")
            continue
        missing.extend(_missing_definition_snippets(body, snippets, f"function {name}"))
    return missing


def _normalize_catalog_sql(value: str) -> str:
    normalized = " ".join((value or "").split())
    return normalized.replace("public.", "").replace(" USING btree", "")


def history_schema_signature(connection) -> dict:
    """Catalog definitions for the two history tables, not object names alone."""
    if connection.dialect.name != "postgresql":
        raise RuntimeError("History schema signatures are compared on PostgreSQL.")
    return {
        "version_columns": _pg_columns(connection, VERSION_TABLE),
        "revision_columns": _pg_columns(connection, REVISION_TABLE),
        "version_checks": _pg_check_definitions(connection, VERSION_TABLE),
        "revision_checks": _pg_check_definitions(connection, REVISION_TABLE),
        "version_indexes": _pg_index_definitions(connection, VERSION_TABLE),
        "revision_indexes": _pg_index_definitions(connection, REVISION_TABLE),
        "version_triggers": _pg_trigger_definitions(connection, VERSION_TABLE),
        "revision_triggers": _pg_trigger_definitions(connection, REVISION_TABLE),
        "guard_functions": _pg_guard_functions(connection),
        "version_foreign_keys": _pg_foreign_keys(connection, VERSION_TABLE),
        "revision_foreign_keys": _pg_foreign_keys(connection, REVISION_TABLE),
    }


_registered = False


def register_history_guards(version_table, revision_table) -> None:
    global _registered
    if _registered:
        return
    _registered = True

    @event.listens_for(version_table, "after_create")
    def _install_version_guards(target, connection, **kw):
        # Revision triggers are installed from that table. Version creation only
        # installs the version guard so a partial create_all stays ordered.
        if connection.dialect.name == "postgresql":
            _install_postgres_version_guard(connection)
        elif connection.dialect.name == "sqlite":
            for statement in _sqlite_version_statements():
                connection.execute(text(statement))

    @event.listens_for(revision_table, "after_create")
    def _install_revision_guards(target, connection, **kw):
        if connection.dialect.name == "postgresql":
            _install_postgres_revision_guard(connection)
        elif connection.dialect.name == "sqlite":
            for statement in _sqlite_revision_statements():
                connection.execute(text(statement))


def _add_check(connection, table: str, name: str, expression: str) -> None:
    connection.execute(text(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression})"))


def _drop_check(connection, table: str, name: str) -> None:
    if connection.dialect.name == "postgresql":
        connection.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}"))
        return
    connection.execute(text(f"SELECT 1"))


def _replace_foreign_key(connection, table: str, column: str, referred: str, ondelete: str) -> None:
    if connection.dialect.name != "postgresql":
        raise RuntimeError("Foreign-key retention changes are applied by PostgreSQL migrations.")
    inspector = inspect(connection)
    matches = [
        fk
        for fk in inspector.get_foreign_keys(table)
        if fk.get("constrained_columns") == [column] and fk.get("referred_table") == referred
    ]
    if len(matches) != 1 or not matches[0].get("name"):
        raise RuntimeError(
            f"Expected one foreign key for {table}.{column} referencing {referred}, found {matches}."
        )
    name = matches[0]["name"]
    connection.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT {name}"))
    connection.execute(
        text(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} "
            f"FOREIGN KEY ({column}) REFERENCES {referred} (id) ON DELETE {ondelete}"
        )
    )


def _install_postgres_guards(connection) -> None:
    _install_postgres_version_guard(connection)
    _install_postgres_revision_guard(connection)


def _install_postgres_version_guard(connection) -> None:
    connection.execute(text("DROP TRIGGER IF EXISTS trg_team_config_version_guard ON team_configuration_versions"))
    connection.execute(text(_POSTGRES_VERSION_FUNCTION))
    connection.execute(
        text(
            """
            CREATE TRIGGER trg_team_config_version_guard
            BEFORE INSERT OR UPDATE OR DELETE ON team_configuration_versions
            FOR EACH ROW EXECUTE FUNCTION guard_team_configuration_version()
            """
        )
    )


def _install_postgres_revision_guard(connection) -> None:
    connection.execute(text("DROP TRIGGER IF EXISTS trg_evaluation_revision_guard ON evaluation_revisions"))
    connection.execute(text(_POSTGRES_REVISION_FUNCTION))
    connection.execute(
        text(
            """
            CREATE TRIGGER trg_evaluation_revision_guard
            BEFORE INSERT OR UPDATE OR DELETE ON evaluation_revisions
            FOR EACH ROW EXECUTE FUNCTION guard_evaluation_revision()
            """
        )
    )


def _install_sqlite_guards(connection) -> None:
    for statement in _sqlite_version_statements() + _sqlite_revision_statements():
        connection.execute(text(statement))


def _sqlite_version_statements() -> list[str]:
    actor_when = """
        json_extract(NEW.actor_created_snapshot, '$.state') IS NULL
        OR json_extract(NEW.actor_created_snapshot, '$.state') NOT IN ('unknown', 'known')
        OR json_extract(NEW.actor_published_snapshot, '$.state') IS NULL
        OR json_extract(NEW.actor_published_snapshot, '$.state') NOT IN ('unknown', 'known')
    """
    identity_when = """
        OLD.performance_level IS NOT NULL AND (
            OLD.team_id IS NOT NEW.team_id
            OR OLD.performance_level IS NOT NEW.performance_level
            OR OLD.position_name IS NOT NEW.position_name
            OR OLD.version_number IS NOT NEW.version_number
            OR OLD.effective_month IS NOT NEW.effective_month
            OR OLD.effective_year IS NOT NEW.effective_year
            OR OLD.effective_from_month IS NOT NEW.effective_from_month
            OR OLD.effective_from_year IS NOT NEW.effective_from_year
            OR OLD.effective_until_month IS NOT NEW.effective_until_month
            OR OLD.effective_until_year IS NOT NEW.effective_until_year
            OR OLD.actor_created_snapshot IS NOT NEW.actor_created_snapshot
            OR OLD.created_at IS NOT NEW.created_at
            OR (OLD.created_by_user_id IS NOT NEW.created_by_user_id AND NEW.created_by_user_id IS NOT NULL)
        )
    """
    evidence_when = """
        OLD.performance_level IS NOT NULL AND OLD.status IN ('approved', 'superseded') AND (
            OLD.config_snapshot IS NOT NEW.config_snapshot
            OR OLD.config_checksum IS NOT NEW.config_checksum
            OR OLD.preview_snapshot IS NOT NEW.preview_snapshot
            OR OLD.total_weight IS NOT NEW.total_weight
            OR OLD.overall_score IS NOT NEW.overall_score
            OR OLD.is_active IS NOT NEW.is_active
            OR OLD.notes IS NOT NEW.notes
            OR OLD.published_at IS NOT NEW.published_at
            OR OLD.actor_published_snapshot IS NOT NEW.actor_published_snapshot
            OR (OLD.published_by_user_id IS NOT NEW.published_by_user_id AND NEW.published_by_user_id IS NOT NULL)
            OR (
                OLD.superseded_at IS NOT NEW.superseded_at
                AND NOT (OLD.status = 'approved' AND NEW.status = 'superseded')
            )
        )
    """
    return [
        "DROP TRIGGER IF EXISTS trg_team_config_version_no_delete_sealed",
        """
        CREATE TRIGGER trg_team_config_version_no_delete_sealed
        BEFORE DELETE ON team_configuration_versions
        WHEN OLD.performance_level IS NOT NULL AND OLD.status IN ('approved', 'superseded')
        BEGIN
            SELECT RAISE(ABORT, 'monthly approved evaluation history cannot be deleted');
        END
        """,
        "DROP TRIGGER IF EXISTS trg_team_config_version_actor_insert",
        f"""
        CREATE TRIGGER trg_team_config_version_actor_insert
        BEFORE INSERT ON team_configuration_versions
        WHEN {actor_when}
        BEGIN
            SELECT RAISE(ABORT, 'actor snapshot state must be unknown or known');
        END
        """,
        "DROP TRIGGER IF EXISTS trg_team_config_version_actor_update",
        f"""
        CREATE TRIGGER trg_team_config_version_actor_update
        BEFORE UPDATE ON team_configuration_versions
        WHEN {actor_when}
        BEGIN
            SELECT RAISE(ABORT, 'actor snapshot state must be unknown or known');
        END
        """,
        "DROP TRIGGER IF EXISTS trg_team_config_version_legacy_level",
        """
        CREATE TRIGGER trg_team_config_version_legacy_level
        BEFORE UPDATE ON team_configuration_versions
        WHEN OLD.performance_level IS NULL AND NEW.performance_level IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'legacy configuration versions cannot become monthly bindings');
        END
        """,
        "DROP TRIGGER IF EXISTS trg_team_config_version_identity",
        f"""
        CREATE TRIGGER trg_team_config_version_identity
        BEFORE UPDATE ON team_configuration_versions
        WHEN {identity_when}
        BEGIN
            SELECT RAISE(ABORT, 'monthly evaluation identity cannot change');
        END
        """,
        "DROP TRIGGER IF EXISTS trg_team_config_version_status",
        """
        CREATE TRIGGER trg_team_config_version_status
        BEFORE UPDATE ON team_configuration_versions
        WHEN OLD.performance_level IS NOT NULL AND NOT (
            (OLD.status = 'draft' AND NEW.status IN ('draft', 'approved'))
            OR (OLD.status = 'approved' AND NEW.status IN ('approved', 'superseded'))
            OR (OLD.status = 'superseded' AND NEW.status = 'superseded')
        )
        BEGIN
            SELECT RAISE(ABORT, 'illegal monthly configuration status transition');
        END
        """,
        "DROP TRIGGER IF EXISTS trg_team_config_version_approve_marker",
        """
        CREATE TRIGGER trg_team_config_version_approve_marker
        BEFORE UPDATE ON team_configuration_versions
        WHEN OLD.performance_level IS NOT NULL
          AND OLD.status = 'draft'
          AND NEW.status = 'approved'
          AND NEW.published_at IS NULL
        BEGIN
            SELECT RAISE(ABORT, 'approved monthly version requires published_at');
        END
        """,
        "DROP TRIGGER IF EXISTS trg_team_config_version_sealed_evidence",
        f"""
        CREATE TRIGGER trg_team_config_version_sealed_evidence
        BEFORE UPDATE ON team_configuration_versions
        WHEN {evidence_when}
        BEGIN
            SELECT RAISE(ABORT, 'approved monthly evaluation evidence is immutable');
        END
        """,
    ]


def _sqlite_revision_statements() -> list[str]:
    actor_when = """
        json_extract(NEW.actor_snapshot, '$.state') IS NULL
        OR json_extract(NEW.actor_snapshot, '$.state') NOT IN ('unknown', 'known')
    """
    evidence_when = """
        OLD.team_id IS NOT NEW.team_id
        OR OLD.performance_level IS NOT NEW.performance_level
        OR OLD.position_name IS NOT NEW.position_name
        OR OLD.year IS NOT NEW.year
        OR OLD.month IS NOT NEW.month
        OR OLD.version_id IS NOT NEW.version_id
        OR OLD.previous_revision_id IS NOT NEW.previous_revision_id
        OR OLD.prior_snapshot IS NOT NEW.prior_snapshot
        OR OLD.applied_snapshot IS NOT NEW.applied_snapshot
        OR OLD.actor_snapshot IS NOT NEW.actor_snapshot
        OR OLD.created_at IS NOT NEW.created_at
        OR (OLD.created_by_user_id IS NOT NEW.created_by_user_id AND NEW.created_by_user_id IS NOT NULL)
    """
    return [
        "DROP TRIGGER IF EXISTS trg_evaluation_revision_no_delete",
        """
        CREATE TRIGGER trg_evaluation_revision_no_delete
        BEFORE DELETE ON evaluation_revisions
        BEGIN
            SELECT RAISE(ABORT, 'evaluation revision history cannot be deleted');
        END
        """,
        "DROP TRIGGER IF EXISTS trg_evaluation_revision_actor_insert",
        f"""
        CREATE TRIGGER trg_evaluation_revision_actor_insert
        BEFORE INSERT ON evaluation_revisions
        WHEN {actor_when}
        BEGIN
            SELECT RAISE(ABORT, 'actor snapshot state must be unknown or known');
        END
        """,
        "DROP TRIGGER IF EXISTS trg_evaluation_revision_actor_update",
        f"""
        CREATE TRIGGER trg_evaluation_revision_actor_update
        BEFORE UPDATE ON evaluation_revisions
        WHEN {actor_when}
        BEGIN
            SELECT RAISE(ABORT, 'actor snapshot state must be unknown or known');
        END
        """,
        "DROP TRIGGER IF EXISTS trg_evaluation_revision_evidence",
        f"""
        CREATE TRIGGER trg_evaluation_revision_evidence
        BEFORE UPDATE ON evaluation_revisions
        WHEN {evidence_when}
        BEGIN
            SELECT RAISE(ABORT, 'evaluation revision evidence is immutable');
        END
        """,
        "DROP TRIGGER IF EXISTS trg_evaluation_revision_status",
        """
        CREATE TRIGGER trg_evaluation_revision_status
        BEFORE UPDATE ON evaluation_revisions
        WHEN OLD.status IS NOT NEW.status AND NOT (
            OLD.status = 'active' AND NEW.status IN ('rolled_back', 'superseded')
        )
        BEGIN
            SELECT RAISE(ABORT, 'illegal evaluation revision status transition');
        END
        """,
    ]


def _missing_names(kind: str, table: str, expected, found) -> list[str]:
    found_names = set(found)
    missing = []
    for name in expected:
        if name not in found_names:
            missing.append(f"{kind} {table}.{name}")
    return missing


def _missing_actions(table: str, expected: dict[str, str], found: dict[str, str]) -> list[str]:
    missing = []
    for column, action in expected.items():
        actual = found.get(column)
        if actual != action:
            missing.append(f"foreign key {table}.{column} on delete {actual or 'missing'} != {action}")
    return missing


def _pg_columns(connection, table: str) -> dict[str, dict]:
    rows = connection.execute(
        text(
            """
            SELECT column_name, is_nullable, udt_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table
            """
        ),
        {"table": table},
    ).mappings()
    return {
        row["column_name"]: {"nullable": row["is_nullable"] == "YES", "udt": row["udt_name"]}
        for row in rows
    }


def _pg_check_definitions(connection, table: str) -> dict[str, str]:
    rows = connection.execute(
        text(
            """
            SELECT con.conname, pg_get_constraintdef(con.oid)
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            WHERE con.contype = 'c' AND nsp.nspname = 'public' AND rel.relname = :table
            """
        ),
        {"table": table},
    )
    return {row[0]: _normalize_catalog_sql(row[1]) for row in rows}


def _pg_index_definitions(connection, table: str) -> dict[str, str]:
    rows = connection.execute(
        text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = :table
            """
        ),
        {"table": table},
    )
    return {row[0]: _normalize_catalog_sql(row[1]) for row in rows}


def _pg_trigger_definitions(connection, table: str) -> dict[str, str]:
    rows = connection.execute(
        text(
            """
            SELECT tg.tgname, pg_get_triggerdef(tg.oid)
            FROM pg_trigger tg
            JOIN pg_class rel ON rel.oid = tg.tgrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            WHERE nsp.nspname = 'public' AND rel.relname = :table AND NOT tg.tgisinternal
            """
        ),
        {"table": table},
    )
    return {row[0]: _normalize_catalog_sql(row[1]) for row in rows}


def _pg_guard_functions(connection) -> dict[str, str]:
    rows = connection.execute(
        text(
            """
            SELECT p.proname, pg_get_functiondef(p.oid)
            FROM pg_proc p
            JOIN pg_namespace nsp ON nsp.oid = p.pronamespace
            WHERE nsp.nspname = 'public'
              AND p.proname IN ('guard_team_configuration_version', 'guard_evaluation_revision')
            """
        )
    )
    return {row[0]: _normalize_catalog_sql(row[1]) for row in rows}


def _pg_foreign_keys(connection, table: str) -> dict[str, str]:
    actions = {"a": "NO ACTION", "r": "RESTRICT", "c": "CASCADE", "n": "SET NULL", "d": "SET DEFAULT"}
    rows = connection.execute(
        text(
            """
            SELECT att.attname, con.confdeltype
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = con.conkey[1]
            WHERE con.contype = 'f' AND nsp.nspname = 'public' AND rel.relname = :table
              AND array_length(con.conkey, 1) = 1
            """
        ),
        {"table": table},
    )
    return {row[0]: actions.get(row[1], row[1]) for row in rows}


def _sqlite_columns(connection, table: str) -> dict[str, dict]:
    rows = connection.execute(text(f"PRAGMA table_info({table})")).mappings()
    return {row["name"]: {"nullable": row["notnull"] == 0, "udt": row["type"]} for row in rows}


def _sqlite_indexes(connection, table: str) -> set[str]:
    rows = connection.execute(text(f"PRAGMA index_list({table})")).mappings()
    names = {row["name"] for row in rows}
    # SQLite stores a named UNIQUE table constraint as sqlite_autoindex_*.
    # The constraint name in the CREATE TABLE statement is the ORM contract.
    if table == VERSION_TABLE and "uq_team_config_version" not in names:
        sql = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :table"),
            {"table": table},
        ).scalar() or ""
        if "uq_team_config_version" in sql:
            names.add("uq_team_config_version")
    return names


def _sqlite_table_sql(connection, table: str) -> str:
    return connection.execute(
        text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :table"),
        {"table": table},
    ).scalar() or ""


def _sqlite_trigger_sql(connection, table: str) -> dict[str, str]:
    rows = connection.execute(
        text(
            """
            SELECT name, sql FROM sqlite_master
            WHERE type = 'trigger' AND tbl_name = :table
            """
        ),
        {"table": table},
    )
    return {row[0]: row[1] or "" for row in rows}


def _sqlite_triggers(connection, table: str) -> set[str]:
    return set(_sqlite_trigger_sql(connection, table))


def _sqlite_check_names(connection, table: str) -> set[str]:
    row = connection.execute(
        text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :table"),
        {"table": table},
    ).scalar()
    if not row:
        return set()
    expected = set(version_check_sql() if table == VERSION_TABLE else REVISION_CHECKS)
    return {name for name in expected if name in row}


def _sqlite_foreign_keys(connection, table: str) -> dict[str, str]:
    rows = connection.execute(text(f"PRAGMA foreign_key_list({table})")).mappings()
    found = {}
    for row in rows:
        action = str(row["on_delete"] or "").upper()
        if action == "NO ACTION":
            action = "NO ACTION"
        found[row["from"]] = action
    return found


_POSTGRES_VERSION_FUNCTION = """
CREATE OR REPLACE FUNCTION guard_team_configuration_version()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.performance_level IS NOT NULL AND OLD.status IN ('approved', 'superseded') THEN
            RAISE EXCEPTION 'monthly approved evaluation history cannot be deleted';
        END IF;
        RETURN OLD;
    END IF;

    IF jsonb_typeof(NEW.actor_created_snapshot) IS DISTINCT FROM 'object'
       OR COALESCE(NEW.actor_created_snapshot->>'state', '') NOT IN ('unknown', 'known')
       OR jsonb_typeof(NEW.actor_published_snapshot) IS DISTINCT FROM 'object'
       OR COALESCE(NEW.actor_published_snapshot->>'state', '') NOT IN ('unknown', 'known')
    THEN
        RAISE EXCEPTION 'actor snapshot state must be unknown or known';
    END IF;

    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;

    IF OLD.performance_level IS NULL AND NEW.performance_level IS NOT NULL THEN
        RAISE EXCEPTION 'legacy configuration versions cannot become monthly bindings';
    END IF;
    IF OLD.performance_level IS NULL THEN
        RETURN NEW;
    END IF;

    IF OLD.team_id IS DISTINCT FROM NEW.team_id
       OR OLD.performance_level IS DISTINCT FROM NEW.performance_level
       OR OLD.position_name IS DISTINCT FROM NEW.position_name
       OR OLD.version_number IS DISTINCT FROM NEW.version_number
       OR OLD.effective_month IS DISTINCT FROM NEW.effective_month
       OR OLD.effective_year IS DISTINCT FROM NEW.effective_year
       OR OLD.effective_from_month IS DISTINCT FROM NEW.effective_from_month
       OR OLD.effective_from_year IS DISTINCT FROM NEW.effective_from_year
       OR OLD.effective_until_month IS DISTINCT FROM NEW.effective_until_month
       OR OLD.effective_until_year IS DISTINCT FROM NEW.effective_until_year
       OR OLD.actor_created_snapshot IS DISTINCT FROM NEW.actor_created_snapshot
       OR OLD.created_at IS DISTINCT FROM NEW.created_at
       OR (OLD.created_by_user_id IS DISTINCT FROM NEW.created_by_user_id AND NEW.created_by_user_id IS NOT NULL)
    THEN
        RAISE EXCEPTION 'monthly evaluation identity cannot change';
    END IF;

    IF OLD.status = 'draft' AND NEW.status IN ('draft', 'approved') THEN
        IF NEW.status = 'approved' AND NEW.published_at IS NULL THEN
            RAISE EXCEPTION 'approved monthly version requires published_at';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.status = 'approved' AND NEW.status = 'superseded' THEN
        IF OLD.config_snapshot::jsonb IS DISTINCT FROM NEW.config_snapshot::jsonb
           OR OLD.config_checksum IS DISTINCT FROM NEW.config_checksum
           OR OLD.preview_snapshot::jsonb IS DISTINCT FROM NEW.preview_snapshot::jsonb
           OR OLD.total_weight IS DISTINCT FROM NEW.total_weight
           OR OLD.overall_score IS DISTINCT FROM NEW.overall_score
           OR OLD.is_active IS DISTINCT FROM NEW.is_active
           OR OLD.notes IS DISTINCT FROM NEW.notes
           OR OLD.published_at IS DISTINCT FROM NEW.published_at
           OR OLD.actor_published_snapshot IS DISTINCT FROM NEW.actor_published_snapshot
           OR (OLD.published_by_user_id IS DISTINCT FROM NEW.published_by_user_id AND NEW.published_by_user_id IS NOT NULL)
        THEN
            RAISE EXCEPTION 'approved monthly evaluation evidence is immutable';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.status = NEW.status AND OLD.status IN ('approved', 'superseded') THEN
        IF OLD.config_snapshot::jsonb IS DISTINCT FROM NEW.config_snapshot::jsonb
           OR OLD.config_checksum IS DISTINCT FROM NEW.config_checksum
           OR OLD.preview_snapshot::jsonb IS DISTINCT FROM NEW.preview_snapshot::jsonb
           OR OLD.total_weight IS DISTINCT FROM NEW.total_weight
           OR OLD.overall_score IS DISTINCT FROM NEW.overall_score
           OR OLD.is_active IS DISTINCT FROM NEW.is_active
           OR OLD.notes IS DISTINCT FROM NEW.notes
           OR OLD.published_at IS DISTINCT FROM NEW.published_at
           OR OLD.actor_published_snapshot IS DISTINCT FROM NEW.actor_published_snapshot
           OR OLD.superseded_at IS DISTINCT FROM NEW.superseded_at
           OR (OLD.published_by_user_id IS DISTINCT FROM NEW.published_by_user_id AND NEW.published_by_user_id IS NOT NULL)
        THEN
            RAISE EXCEPTION 'approved monthly evaluation evidence is immutable';
        END IF;
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'illegal monthly configuration status transition';
END;
$$;
"""


_POSTGRES_REVISION_FUNCTION = """
CREATE OR REPLACE FUNCTION guard_evaluation_revision()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'evaluation revision history cannot be deleted';
    END IF;

    IF jsonb_typeof(NEW.actor_snapshot) IS DISTINCT FROM 'object'
       OR COALESCE(NEW.actor_snapshot->>'state', '') NOT IN ('unknown', 'known')
    THEN
        RAISE EXCEPTION 'actor snapshot state must be unknown or known';
    END IF;

    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;

    IF OLD.team_id IS DISTINCT FROM NEW.team_id
       OR OLD.performance_level IS DISTINCT FROM NEW.performance_level
       OR OLD.position_name IS DISTINCT FROM NEW.position_name
       OR OLD.year IS DISTINCT FROM NEW.year
       OR OLD.month IS DISTINCT FROM NEW.month
       OR OLD.version_id IS DISTINCT FROM NEW.version_id
       OR OLD.previous_revision_id IS DISTINCT FROM NEW.previous_revision_id
       OR OLD.prior_snapshot IS DISTINCT FROM NEW.prior_snapshot
       OR OLD.applied_snapshot IS DISTINCT FROM NEW.applied_snapshot
       OR OLD.actor_snapshot IS DISTINCT FROM NEW.actor_snapshot
       OR OLD.created_at IS DISTINCT FROM NEW.created_at
       OR (OLD.created_by_user_id IS DISTINCT FROM NEW.created_by_user_id AND NEW.created_by_user_id IS NOT NULL)
    THEN
        RAISE EXCEPTION 'evaluation revision evidence is immutable';
    END IF;

    IF OLD.status = NEW.status THEN
        RETURN NEW;
    END IF;
    IF OLD.status = 'active' AND NEW.status IN ('rolled_back', 'superseded') THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'illegal evaluation revision status transition';
END;
$$;
"""
