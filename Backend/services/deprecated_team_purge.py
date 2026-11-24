"""Idempotent database purge for the deprecated Inbound UAE team and its data.

Used both by the Alembic migration and the standalone cleanup script so
``Inbound UAE`` (deprecated in April) is permanently removed across every
table regardless of how the schema is updated.
"""
from __future__ import annotations

import json
from typing import Iterable

import sqlalchemy as sa


DEPRECATED_TEAM_KEYS: frozenset[str] = frozenset({"inbound uae", "inbound_uae", "inbound-uae"})
_POSTGRES_HISTORY_TRIGGERS: tuple[tuple[str, str], ...] = (
    ("team_configuration_versions", "trg_team_config_version_guard"),
    ("evaluation_revisions", "trg_evaluation_revision_guard"),
    ("evaluation_apply_controls", "trg_evaluation_apply_control_guard"),
    ("evaluation_apply_stage_rows", "trg_evaluation_apply_stage_guard"),
    ("cache_invalidation_outbox", "trg_cache_invalidation_outbox_guard"),
    ("processing_jobs", "trg_processing_job_apply_foundation"),
    ("evaluation_scopes", "trg_evaluation_scope_apply_foundation"),
    ("performance_records", "trg_performance_record_apply_foundation"),
)


def _chunked(values: list, size: int = 400) -> Iterable[list]:
    for idx in range(0, len(values), size):
        yield values[idx : idx + size]


def _delete_in_chunks(connection, table: str, column: str, values: list) -> int:
    if not values:
        return 0
    total = 0
    stmt = sa.text(f"DELETE FROM {table} WHERE {column} IN :ids").bindparams(
        sa.bindparam("ids", expanding=True)
    )
    for chunk in _chunked(values):
        res = connection.execute(stmt, {"ids": chunk})
        total += max(0, int(res.rowcount or 0))
    return total


def _scalar_in_chunks(connection, sql_template: str, param: str, values: list) -> list:
    if not values:
        return []
    found = []
    stmt = sa.text(sql_template).bindparams(sa.bindparam(param, expanding=True))
    for chunk in _chunked(values):
        found.extend(row[0] for row in connection.execute(stmt, {param: chunk}).fetchall())
    return list(dict.fromkeys(found))


def _is_deprecated_team_name(value: object) -> bool:
    return str(value or "").strip().casefold() in DEPRECATED_TEAM_KEYS


def _parse_json_obj(value: object) -> dict | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def _toggle_postgres_triggers(connection, tables: set[str], enable: bool) -> None:
    verb = "ENABLE" if enable else "DISABLE"
    for table, trigger in _POSTGRES_HISTORY_TRIGGERS:
        if table not in tables:
            continue
        exists = connection.execute(
            sa.text(
                "SELECT 1 FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE c.relname = :tbl AND t.tgname = :trg AND NOT t.tgisinternal "
                "LIMIT 1"
            ),
            {"tbl": table, "trg": trigger},
        ).first()
        if exists:
            connection.execute(sa.text(f"ALTER TABLE {table} {verb} TRIGGER {trigger}"))


def _drop_sqlite_delete_triggers(connection) -> bool:
    rows = connection.execute(
        sa.text(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' "
            "AND (name LIKE 'trg_team_config_version%' "
            "OR name LIKE 'trg_evaluation_revision%' "
            "OR name LIKE 'trg_evaluation_apply_%' "
            "OR name LIKE 'trg_cache_invalidation_outbox%' "
            "OR name LIKE 'trg_processing_job_apply%' "
            "OR name LIKE 'trg_evaluation_scope_apply%' "
            "OR name LIKE 'trg_performance_record_apply%')"
        )
    ).fetchall()
    for (name,) in rows:
        connection.execute(sa.text(f'DROP TRIGGER IF EXISTS "{name}"'))
    return bool(rows)


def _reinstall_sqlite_guards(connection) -> None:
    try:
        from models.evaluation_history_schema import install_history_guards

        install_history_guards(connection)
    except Exception:
        pass
    try:
        from services.evaluation.apply_job_schema import ensure_apply_foundation_triggers

        ensure_apply_foundation_triggers(connection)
    except Exception:
        pass


def purge_deprecated_inbound_uae(connection) -> dict[str, int]:
    """Delete ``Inbound UAE`` team rows and all dependent/scoped records cleanly."""
    insp = sa.inspect(connection)
    tables = set(insp.get_table_names())
    counts: dict[str, int] = {}

    def record_count(tbl: str, delta: int) -> None:
        if delta:
            counts[tbl] = counts.get(tbl, 0) + delta

    team_ids: list = []
    if "teams" in tables:
        team_ids = [
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT id FROM teams "
                    "WHERE lower(trim(name)) IN ('inbound uae', 'inbound_uae', 'inbound-uae') "
                    "OR lower(trim(coalesce(db_name, ''))) IN ('inbound uae', 'inbound_uae', 'inbound-uae') "
                    "OR lower(trim(coalesce(display_name, ''))) = 'inbound uae' "
                    "OR (lower(trim(name)) = 'inbound' AND upper(trim(coalesce(region, ''))) = 'UAE')"
                )
            ).fetchall()
        ]

    employee_ids: list = []
    if team_ids and "employees" in tables:
        employee_ids = _scalar_in_chunks(
            connection, "SELECT id FROM employees WHERE team_id IN :tids", "tids", team_ids
        )

    record_ids: list = []
    if "performance_records" in tables and (team_ids or employee_ids):
        if team_ids:
            record_ids.extend(
                _scalar_in_chunks(
                    connection,
                    "SELECT id FROM performance_records WHERE team_id IN :tids",
                    "tids",
                    team_ids,
                )
            )
        if employee_ids:
            record_ids.extend(
                _scalar_in_chunks(
                    connection,
                    "SELECT id FROM performance_records WHERE employee_id IN :eids",
                    "eids",
                    employee_ids,
                )
            )
        record_ids = list(dict.fromkeys(record_ids))

    scope_ids: list = []
    if "evaluation_scopes" in tables:
        scope_ids.extend(
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT id FROM evaluation_scopes "
                    "WHERE lower(trim(team_key)) IN ('inbound uae', 'inbound_uae', 'inbound-uae')"
                )
            ).fetchall()
        )
        if team_ids:
            scope_ids.extend(
                _scalar_in_chunks(
                    connection,
                    "SELECT id FROM evaluation_scopes WHERE team_id IN :tids",
                    "tids",
                    team_ids,
                )
            )
        scope_ids = list(dict.fromkeys(scope_ids))

    version_ids: list = []
    if team_ids and "team_configuration_versions" in tables:
        version_ids = _scalar_in_chunks(
            connection,
            "SELECT id FROM team_configuration_versions WHERE team_id IN :tids",
            "tids",
            team_ids,
        )

    revision_ids: list = []
    if "evaluation_revisions" in tables:
        if team_ids:
            revision_ids.extend(
                _scalar_in_chunks(
                    connection,
                    "SELECT id FROM evaluation_revisions WHERE team_id IN :tids",
                    "tids",
                    team_ids,
                )
            )
        if version_ids:
            revision_ids.extend(
                _scalar_in_chunks(
                    connection,
                    "SELECT id FROM evaluation_revisions WHERE version_id IN :vids",
                    "vids",
                    version_ids,
                )
            )
        revision_ids = list(dict.fromkeys(revision_ids))

    job_ids: list = []
    if "evaluation_apply_controls" in tables:
        for col, vals in (
            ("team_id", team_ids),
            ("version_id", version_ids),
            ("scope_id", scope_ids),
            ("promoted_revision_id", revision_ids),
        ):
            if vals:
                job_ids.extend(
                    _scalar_in_chunks(
                        connection,
                        f"SELECT job_id FROM evaluation_apply_controls WHERE {col} IN :vals",
                        "vals",
                        vals,
                    )
                )
        job_ids = list(dict.fromkeys(job_ids))

    plan_ids: list = []
    if "performance_plans" in tables:
        if team_ids:
            plan_ids.extend(
                _scalar_in_chunks(
                    connection,
                    "SELECT id FROM performance_plans WHERE team_id IN :tids",
                    "tids",
                    team_ids,
                )
            )
        if employee_ids:
            plan_ids.extend(
                _scalar_in_chunks(
                    connection,
                    "SELECT id FROM performance_plans WHERE employee_id IN :eids",
                    "eids",
                    employee_ids,
                )
            )
        plan_ids = list(dict.fromkeys(plan_ids))

    needs_guard_bypass = bool(
        revision_ids
        or version_ids
        or job_ids
        or (
            "evaluation_apply_stage_rows" in tables
            and record_ids
            and _scalar_in_chunks(
                connection,
                "SELECT record_id FROM evaluation_apply_stage_rows WHERE record_id IN :rids",
                "rids",
                record_ids,
            )
        )
    )

    dialect = connection.dialect.name
    sqlite_dropped = False
    pg_disabled = False
    if needs_guard_bypass:
        if dialect == "postgresql":
            _toggle_postgres_triggers(connection, tables, enable=False)
            pg_disabled = True
        elif dialect == "sqlite":
            sqlite_dropped = _drop_sqlite_delete_triggers(connection)

    try:
        if "kpi_values" in tables and record_ids:
            record_count("kpi_values", _delete_in_chunks(connection, "kpi_values", "record_id", record_ids))

        if "performance_record_versions" in tables and record_ids:
            record_count(
                "performance_record_versions",
                _delete_in_chunks(connection, "performance_record_versions", "original_record_id", record_ids),
            )

        if "evaluation_apply_stage_rows" in tables:
            if job_ids:
                record_count(
                    "evaluation_apply_stage_rows",
                    _delete_in_chunks(connection, "evaluation_apply_stage_rows", "job_id", job_ids),
                )
            if record_ids:
                record_count(
                    "evaluation_apply_stage_rows",
                    _delete_in_chunks(connection, "evaluation_apply_stage_rows", "record_id", record_ids),
                )

        if "cache_invalidation_outbox" in tables:
            if job_ids:
                record_count(
                    "cache_invalidation_outbox",
                    _delete_in_chunks(connection, "cache_invalidation_outbox", "job_id", job_ids),
                )
            if revision_ids:
                record_count(
                    "cache_invalidation_outbox",
                    _delete_in_chunks(connection, "cache_invalidation_outbox", "revision_id", revision_ids),
                )

        if "evaluation_apply_controls" in tables and job_ids:
            record_count(
                "evaluation_apply_controls",
                _delete_in_chunks(connection, "evaluation_apply_controls", "job_id", job_ids),
            )

        if "evaluation_revisions" in tables and revision_ids:
            clear_stmt = sa.text(
                "UPDATE evaluation_revisions SET previous_revision_id = NULL "
                "WHERE previous_revision_id IN :rids"
            ).bindparams(sa.bindparam("rids", expanding=True))
            for chunk in _chunked(revision_ids):
                connection.execute(clear_stmt, {"rids": chunk})
            record_count(
                "evaluation_revisions",
                _delete_in_chunks(connection, "evaluation_revisions", "id", revision_ids),
            )

        if "evaluation_scopes" in tables and scope_ids:
            record_count(
                "evaluation_scopes",
                _delete_in_chunks(connection, "evaluation_scopes", "id", scope_ids),
            )

        if plan_ids:
            if "plan_objective_kpis" in tables:
                if "plan_objectives" in tables:
                    obj_ids = _scalar_in_chunks(
                        connection,
                        "SELECT id FROM plan_objectives WHERE plan_id IN :pids",
                        "pids",
                        plan_ids,
                    )
                    record_count(
                        "plan_objective_kpis",
                        _delete_in_chunks(connection, "plan_objective_kpis", "objective_id", obj_ids),
                    )
                if "plan_kpis" in tables:
                    pk_ids = _scalar_in_chunks(
                        connection,
                        "SELECT id FROM plan_kpis WHERE plan_id IN :pids",
                        "pids",
                        plan_ids,
                    )
                    record_count(
                        "plan_objective_kpis",
                        _delete_in_chunks(connection, "plan_objective_kpis", "kpi_id", pk_ids),
                    )
            for child_tbl in (
                "plan_insight_links",
                "plan_objectives",
                "plan_kpis",
                "plan_milestones",
                "plan_notes",
            ):
                if child_tbl in tables:
                    record_count(
                        child_tbl,
                        _delete_in_chunks(connection, child_tbl, "plan_id", plan_ids),
                    )

        if "actions" in tables:
            if team_ids:
                record_count("actions", _delete_in_chunks(connection, "actions", "team_id", team_ids))
            if employee_ids:
                record_count("actions", _delete_in_chunks(connection, "actions", "employee_id", employee_ids))
            if plan_ids:
                record_count("actions", _delete_in_chunks(connection, "actions", "plan_id", plan_ids))

        if "performance_plans" in tables and plan_ids:
            record_count(
                "performance_plans",
                _delete_in_chunks(connection, "performance_plans", "id", plan_ids),
            )

        if "performance_records" in tables and record_ids:
            record_count(
                "performance_records",
                _delete_in_chunks(connection, "performance_records", "id", record_ids),
            )

        if "upload_log" in tables and team_ids:
            record_count("upload_log", _delete_in_chunks(connection, "upload_log", "team_id", team_ids))

        if "employees" in tables and employee_ids:
            record_count("employees", _delete_in_chunks(connection, "employees", "id", employee_ids))

        if "team_configuration_versions" in tables and version_ids:
            record_count(
                "team_configuration_versions",
                _delete_in_chunks(connection, "team_configuration_versions", "id", version_ids),
            )

        for tbl in (
            "team_kpi_config",
            "management_kpi_config",
            "management_kpi_config_history",
            "management_kpi_snapshots",
            "user_team_assignments",
            "grade_thresholds",
            "kpi_weight_history",
            "onboarding_states",
        ):
            if tbl in tables and team_ids:
                record_count(tbl, _delete_in_chunks(connection, tbl, "team_id", team_ids))

        if "team_onboarding_drafts" in tables:
            draft_ids: list = []
            if team_ids:
                draft_ids.extend(
                    _scalar_in_chunks(
                        connection,
                        "SELECT id FROM team_onboarding_drafts WHERE published_team_id IN :tids",
                        "tids",
                        team_ids,
                    )
                )
            for row_id, identity in connection.execute(
                sa.text(
                    "SELECT id, team_identity FROM team_onboarding_drafts "
                    "WHERE lower(cast(team_identity as text)) LIKE '%inbound%uae%'"
                )
            ).fetchall():
                obj = _parse_json_obj(identity) or {}
                if any(
                    _is_deprecated_team_name(obj.get(k))
                    for k in ("name", "db_name", "display_name", "team", "team_name")
                ):
                    draft_ids.append(row_id)
            record_count(
                "team_onboarding_drafts",
                _delete_in_chunks(
                    connection,
                    "team_onboarding_drafts",
                    "id",
                    list(dict.fromkeys(draft_ids)),
                ),
            )

        for rep_tbl in ("report_drafts", "generated_reports"):
            if rep_tbl not in tables:
                continue
            scoped_ids = []
            for row_id, scope_json in connection.execute(
                sa.text(
                    f"SELECT id, scope_json FROM {rep_tbl} "
                    "WHERE lower(cast(scope_json as text)) LIKE '%inbound%uae%'"
                )
            ).fetchall():
                obj = _parse_json_obj(scope_json) or {}
                if any(
                    _is_deprecated_team_name(obj.get(k))
                    for k in ("team", "team_name", "db_name")
                ):
                    scoped_ids.append(row_id)
            record_count(
                rep_tbl,
                _delete_in_chunks(connection, rep_tbl, "id", list(dict.fromkeys(scoped_ids))),
            )

        if "teams" in tables and team_ids:
            record_count("teams", _delete_in_chunks(connection, "teams", "id", team_ids))
    finally:
        if pg_disabled:
            _toggle_postgres_triggers(connection, tables, enable=True)
        if sqlite_dropped:
            _reinstall_sqlite_guards(connection)

    return counts
