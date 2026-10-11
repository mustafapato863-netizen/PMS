"""Runtime guards for primary/unique keys that foreign keys depend on.

Production was bootstrapped from an older schema in which several tables
(teams, performance_records, ...) have no primary key or unique constraint.
PostgreSQL refuses a foreign key whose referenced columns are not covered by
one, so migrations use these helpers to:

* add a missing key only when the data allows it (no NULLs, no duplicates),
  never modifying or deleting rows, and
* skip a dependent foreign key with a warning instead of failing when the
  referenced key is still missing.
"""

from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy import text

log = logging.getLogger("alembic.runtime.migration")

ADDED_BY_COMMENT_PREFIX = "added_by_migration:"


def _pg(connection) -> bool:
    return connection.dialect.name == "postgresql"


def has_unique_key(connection, table: str, columns: Sequence[str]) -> bool:
    """True when a PK or UNIQUE constraint covers exactly ``columns``."""
    if not _pg(connection):
        return True
    rows = connection.execute(
        text(
            """
            SELECT array_agg(a.attname::text ORDER BY a.attname)
            FROM pg_constraint c
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
            WHERE c.conrelid = to_regclass(:table) AND c.contype IN ('p', 'u')
            GROUP BY c.oid
            """
        ),
        {"table": f"public.{table}"},
    ).fetchall()
    wanted = sorted(columns)
    return any(list(row[0]) == wanted for row in rows)


def _has_primary_key(connection, table: str) -> bool:
    return bool(
        connection.execute(
            text("SELECT 1 FROM pg_constraint WHERE conrelid = to_regclass(:t) AND contype = 'p'"),
            {"t": f"public.{table}"},
        ).first()
    )


def key_data_problems(connection, table: str, columns: Sequence[str]) -> dict[str, int]:
    cols = ", ".join(columns)
    null_pred = " OR ".join(f"{c} IS NULL" for c in columns)
    nulls = connection.execute(text(f"SELECT count(*) FROM {table} WHERE {null_pred}")).scalar()
    dupes = connection.execute(
        text(
            f"SELECT count(*) FROM (SELECT {cols} FROM {table} "
            f"WHERE NOT ({null_pred}) GROUP BY {cols} HAVING count(*) > 1) d"
        )
    ).scalar()
    return {"null_rows": int(nulls or 0), "duplicate_keys": int(dupes or 0)}


def ensure_key(connection, table: str, columns: Sequence[str], revision: str) -> bool:
    """Add PK (or UNIQUE if a different PK exists) on ``columns`` when safe.

    Returns True when a covering key exists afterwards.
    """
    if not _pg(connection) or has_unique_key(connection, table, columns):
        return True
    problems = key_data_problems(connection, table, columns)
    if any(problems.values()):
        log.warning(
            "SKIPPED key on %s(%s): data is not unique/non-null %s. Dependent foreign keys "
            "will be skipped. Clean the data and re-run the key manually.",
            table, ", ".join(columns), problems,
        )
        return False
    cols = ", ".join(columns)
    if _has_primary_key(connection, table):
        name = f"uq_{table}_{'_'.join(columns)}"
        connection.execute(text(f"ALTER TABLE {table} ADD CONSTRAINT {name} UNIQUE ({cols})"))
    else:
        name = f"{table}_pkey"
        connection.execute(text(f"ALTER TABLE {table} ADD CONSTRAINT {name} PRIMARY KEY ({cols})"))
    connection.execute(
        text(f"COMMENT ON CONSTRAINT {name} ON {table} IS '{ADDED_BY_COMMENT_PREFIX}{revision}'")
    )
    log.info("Added %s on %s(%s)", name, table, cols)
    return True


def drop_added_key(connection, table: str, columns: Sequence[str], revision: str) -> None:
    """Drop a key only if ``revision`` added it and nothing depends on it."""
    if not _pg(connection):
        return
    row = connection.execute(
        text(
            """
            SELECT c.conname, c.oid
            FROM pg_constraint c
            WHERE c.conrelid = to_regclass(:t) AND c.contype IN ('p', 'u')
              AND obj_description(c.oid, 'pg_constraint') = :marker
            """
        ),
        {"t": f"public.{table}", "marker": f"{ADDED_BY_COMMENT_PREFIX}{revision}"},
    ).first()
    if row is None:
        return
    dependents = connection.execute(
        text("SELECT count(*) FROM pg_constraint WHERE contype = 'f' AND conindid = "
             "(SELECT conindid FROM pg_constraint WHERE oid = :oid)"),
        {"oid": row.oid},
    ).scalar()
    if dependents:
        log.warning(
            "Keeping %s on %s: %s foreign key(s) still depend on it.", row.conname, table, dependents
        )
        return
    connection.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT {row.conname}"))


def fk_target_ready(connection, table: str, columns: Sequence[str], context: str) -> bool:
    if has_unique_key(connection, table, columns):
        return True
    log.warning(
        "SKIPPED foreign key %s -> %s(%s): referenced key is missing.",
        context, table, ", ".join(columns),
    )
    return False
