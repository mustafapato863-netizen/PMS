"""Versioned data snapshot: the business tables of one database, streamed out as a JSON document and imported back.

The snapshot moves business data between databases and environments. It is never written to the server's disk:
the export streams straight to the response, and the import reads the upload into memory only.

Export: every table listed in INCLUDED tables (all of Base.metadata except EXCLUDED_TABLES) is written with its row
count and its rows, in primary-key order. Parents come before children, so an import can insert them in file order.
User accounts never leave the database. A row that names a user (an owner, an author, a creator) keeps the user's id,
and the header lists those users as id and username only. On import each one is matched to an existing account with
the same username. An optional reference with no matching account is cleared; a required one blocks the import.
Other foreign keys into excluded tables are written as null, and the header lists them.

Import: a dry run and a commit run the same code. Both validate the header and the rows, check conflicts and
referential integrity, and report per-table counts. Only a commit keeps the changes. The commit is one transaction,
and any error rolls it back. Conflicts are never merged silently: an existing id is skipped or replaced, as the
admin chose for the whole import, while a business key that would be held twice always blocks the import.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterator

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    LargeBinary,
    Numeric,
    Table,
    Uuid,
    UniqueConstraint,
    func,
    insert,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from models.models import AuditLog, Base

FORMAT = "pms-data-snapshot"
SCHEMA_VERSION = 1
CHUNK_ROWS = 500
POLICIES = ("skip", "replace")
AUDIT_TABLE_NAME = "data_snapshot"
SAMPLE_CONFLICTS = 20
USERS_TABLE = "users"

# Tables that never leave the database, with the reason. Users and their sessions hold credentials and per-environment
# accounts, so no user row is exported. References to users travel as id and username only (see user_reference_columns).
EXCLUDED_TABLES: dict[str, str] = {
    "users": "credentials (password hashes) and per-environment accounts",
    "refresh_sessions": "login sessions and token hashes",
    "user_team_assignments": "access grants tied to user accounts",
    "user_function_assignments": "access grants tied to user accounts",
    "user_region_assignments": "access grants tied to user accounts",
    "user_branch_assignments": "access grants tied to user accounts",
    "role_permissions": "the permission matrix is seeded by the application at startup",
    "audit_log": "the environment's own audit trail; a snapshot writes its entries here instead",
    "notifications": "transient per-user notices",
    "notification_recipients": "transient per-user notices",
    "processing_jobs": "runtime job queue; holds request payloads and staged file paths",
    "evaluation_apply_controls": "runtime state of evaluation apply jobs",
    "evaluation_apply_stage_rows": "runtime state of evaluation apply jobs",
    "cache_invalidation_outbox": "runtime cache queue",
    "error_logs": "runtime error log",
    "report_drafts": "user-owned drafts",
    "generated_reports": "generated artifacts; they can be regenerated from the data",
    "saved_report_templates": "user-owned saved templates",
}

# Business keys that must stay unique across an import, beyond the database's own unique constraints.
BUSINESS_KEYS: dict[str, tuple[str, ...]] = {
    "performance_records": ("employee_id", "month", "year"),
}


class SnapshotError(Exception):
    """A refusal with the HTTP status the router should return. Nothing has been kept when it is raised."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def included_tables() -> list[Table]:
    return [table for table in Base.metadata.sorted_tables if table.name not in EXCLUDED_TABLES]


def _references_out(*, to_users: bool) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for table in included_tables():
        columns = sorted({
            column.name
            for column in table.columns
            for foreign_key in column.foreign_keys
            if foreign_key.column.table.name in EXCLUDED_TABLES
            and (foreign_key.column.table.name == USERS_TABLE) == to_users
        })
        if columns:
            found[table.name] = columns
    return found


def user_reference_columns() -> dict[str, list[str]]:
    """Columns of included tables that name a user. They are matched to accounts by username on import."""
    return _references_out(to_users=True)


def cleared_references() -> dict[str, list[str]]:
    """Columns of included tables that point at an excluded table other than users. They travel as null."""
    return _references_out(to_users=False)


def current_revision(connection: Connection) -> str | None:
    """The Alembic revision of the database, or None for a database that was never migrated (tests, bootstrap)."""
    if not inspect(connection).has_table("alembic_version"):
        return None
    row = connection.execute(text("SELECT version_num FROM alembic_version")).first()
    return str(row[0]) if row else None


def _to_json(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, dict):
        return {str(key): _to_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json(item) for item in value]
    return str(value)


def _from_json(column, value: Any) -> Any:
    """Read one value back into the Python type of its column."""
    if value is None:
        return None
    column_type = column.type
    if isinstance(column_type, Uuid):
        return uuid.UUID(str(value))
    if isinstance(column_type, DateTime):
        return dt.datetime.fromisoformat(str(value))
    if isinstance(column_type, Date):
        return dt.date.fromisoformat(str(value))
    if isinstance(column_type, Float):
        return float(value)
    if isinstance(column_type, Numeric):
        return Decimal(str(value))
    if isinstance(column_type, LargeBinary):
        return base64.b64decode(str(value))
    if isinstance(column_type, Boolean):
        return bool(value)
    return value


def _self_referencing_column(table: Table) -> str | None:
    for column in table.columns:
        for foreign_key in column.foreign_keys:
            if foreign_key.column.table is table:
                return column.name
    return None


def _parents_first(rows: list[dict[str, Any]], parent_column: str, primary_key: str) -> list[dict[str, Any]]:
    """Order a self-referencing table so every parent precedes its children. A cycle keeps its remaining order."""
    placed: set[Any] = set()
    ordered: list[dict[str, Any]] = []
    pending = list(rows)
    while pending:
        ready = [row for row in pending if row[parent_column] is None or row[parent_column] in placed]
        if not ready:
            ordered.extend(pending)
            break
        for row in ready:
            placed.add(row[primary_key])
            ordered.append(row)
        pending = [row for row in pending if row[primary_key] not in placed]
    return ordered


# ---------------------------------------------------------------- export


@dataclass(frozen=True)
class ExportPlan:
    exported_at: dt.datetime
    database_revision: str | None
    tables: tuple[str, ...]
    counts: dict[str, int]
    user_references: tuple[dict[str, str], ...]

    @property
    def total_rows(self) -> int:
        return sum(self.counts.values())


def plan_export(engine: Engine) -> ExportPlan:
    """Count every included table in one read transaction. The counts go in the header and the audit entry."""
    with engine.connect() as connection:
        if connection.dialect.name == "postgresql":
            connection = connection.execution_options(isolation_level="REPEATABLE READ")
        tables = included_tables()
        counts = {
            table.name: connection.execute(select(func.count()).select_from(table)).scalar_one()
            for table in tables
        }
        revision = current_revision(connection)
        user_references = _referenced_users(connection)
        connection.rollback()
    return ExportPlan(
        exported_at=dt.datetime.now(dt.timezone.utc),
        database_revision=revision,
        tables=tuple(table.name for table in tables),
        counts=counts,
        user_references=user_references,
    )


def _referenced_users(connection: Connection) -> tuple[dict[str, str], ...]:
    """The users the business rows name, as id and username only. No other user field is read."""
    referenced: set[Any] = set()
    for table_name, columns in user_reference_columns().items():
        table = Base.metadata.tables[table_name]
        for name in columns:
            column = table.c[name]
            referenced.update(value for (value,) in connection.execute(select(column).where(column.is_not(None)).distinct()))
    users = Base.metadata.tables[USERS_TABLE]
    ids = sorted(referenced, key=str)
    accounts: list[dict[str, str]] = []
    for start in range(0, len(ids), CHUNK_ROWS):
        accounts.extend(
            {"id": str(account_id), "username": username}
            for account_id, username in connection.execute(
                select(users.c.id, users.c.username).where(users.c.id.in_(ids[start:start + CHUNK_ROWS]))
            )
        )
    return tuple(sorted(accounts, key=lambda account: account["username"]))


def _export_header(plan: ExportPlan) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "schema_version": SCHEMA_VERSION,
        "exported_at": plan.exported_at.isoformat(),
        "database_revision": plan.database_revision,
        "excluded_tables": [{"table": name, "reason": reason} for name, reason in EXCLUDED_TABLES.items()],
        "user_reference_columns": user_reference_columns(),
        "user_references": list(plan.user_references),
        "cleared_references": cleared_references(),
    }


def _table_rows(connection: Connection, table: Table, cleared: list[str]) -> Iterator[list[dict[str, Any]]]:
    columns = {column.name: column for column in table.columns}
    primary_key = [column.name for column in table.primary_key.columns]
    parent = _self_referencing_column(table)
    if parent is not None:
        # Small self-referencing tables are read whole, so the parents can be placed first.
        rows = [_row_json(row, columns, cleared) for row in connection.execute(select(table)).mappings()]
        yield _parents_first(rows, parent, primary_key[0])
        return
    result = connection.execute(select(table).order_by(*table.primary_key.columns))
    for chunk in result.mappings().partitions(CHUNK_ROWS):
        yield [_row_json(row, columns, cleared) for row in chunk]


def _row_json(row, columns: dict[str, Any], cleared: list[str]) -> dict[str, Any]:
    return {
        name: None if name in cleared else _to_json(row[column])
        for name, column in columns.items()
    }


def stream_export(engine: Engine, plan: ExportPlan) -> Iterator[bytes]:
    """The snapshot document as a stream of UTF-8 chunks. A table that changed since plan_export ends the stream early."""
    header = _export_header(plan)
    cleared_by_table = cleared_references()
    yield (json.dumps(header, ensure_ascii=False)[:-1] + ',"tables":{').encode("utf-8")
    with engine.connect() as connection:
        if connection.dialect.name == "postgresql":
            connection = connection.execution_options(isolation_level="REPEATABLE READ")
        first_table = True
        for table in included_tables():
            count = plan.counts[table.name]
            prefix = "" if first_table else ","
            first_table = False
            yield f'{prefix}{json.dumps(table.name)}:{{"count":{count},"rows":['.encode("utf-8")
            written = 0
            first_row = True
            for chunk in _table_rows(connection, table, cleared_by_table.get(table.name, [])):
                if not chunk:
                    continue
                body = ",".join(json.dumps(row, ensure_ascii=False) for row in chunk)
                written += len(chunk)
                yield (body if first_row else "," + body).encode("utf-8")
                first_row = False
            if written != count:
                raise RuntimeError(f"{table.name} changed while it was being exported")
            yield b"]}"
        connection.rollback()
    yield b"}}"


def export_audit_summary(plan: ExportPlan) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "database_revision": plan.database_revision,
        "exported_at": plan.exported_at.isoformat(),
        "tables": plan.counts,
        "total_rows": plan.total_rows,
        "user_references": len(plan.user_references),
    }


# ---------------------------------------------------------------- import


def parse_snapshot(payload: bytes) -> dict[str, Any]:
    """Parse the upload and check the header. The schema version is refused unless this code reads it."""
    try:
        document = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotError(422, "The uploaded file is not valid UTF-8 JSON") from exc
    if not isinstance(document, dict) or document.get("format") != FORMAT:
        raise SnapshotError(422, "The uploaded file is not a PMS data snapshot")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise SnapshotError(
            422,
            f"Snapshot schema version {document.get('schema_version')!r} is not supported; this server reads version {SCHEMA_VERSION}.",
        )
    if not isinstance(document.get("tables"), dict):
        raise SnapshotError(422, "The snapshot has no tables section")
    references = document.get("user_references")
    if not isinstance(references, list) or not all(
        isinstance(item, dict) and set(item) == {"id", "username"}
        and isinstance(item["id"], str) and isinstance(item["username"], str)
        for item in references
    ):
        raise SnapshotError(422, "The snapshot's user references must be a list of id and username pairs")
    return document


def _validated_rows(document: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Check the table set and every row's keys and count, and convert each value to its column's type."""
    tables = document["tables"]
    included = included_tables()
    names = {table.name for table in included}
    unknown = sorted(set(tables) - names)
    if any(name in EXCLUDED_TABLES for name in unknown):
        raise SnapshotError(422, "The snapshot contains tables that are never exported: " + ", ".join(
            name for name in unknown if name in EXCLUDED_TABLES
        ))
    if unknown:
        raise SnapshotError(422, "The snapshot contains unknown tables: " + ", ".join(unknown))
    missing = sorted(names - set(tables))
    if missing:
        raise SnapshotError(422, "The snapshot is missing tables: " + ", ".join(missing))

    converted: dict[str, list[dict[str, Any]]] = {}
    for table in included:
        section = tables[table.name]
        if not isinstance(section, dict) or not isinstance(section.get("rows"), list):
            raise SnapshotError(422, f"Table {table.name} has no rows list")
        rows = section["rows"]
        if section.get("count") != len(rows):
            raise SnapshotError(422, f"Table {table.name} declares {section.get('count')} rows but holds {len(rows)}")
        expected = {column.name for column in table.columns}
        columns = {column.name: column for column in table.columns}
        result: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict) or set(row) != expected:
                raise SnapshotError(422, f"Row {index} of table {table.name} does not match its columns")
            try:
                result.append({name: _from_json(columns[name], row[name]) for name in expected})
            except (TypeError, ValueError) as exc:
                raise SnapshotError(422, f"Row {index} of table {table.name} has an invalid value: {exc}") from exc
        converted[table.name] = result
    return converted


def _clear_references(converted: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    """Null any reference into an excluded table, whatever the file says. Returns how many values were cleared."""
    cleared_counts: dict[str, int] = {}
    for table_name, columns in cleared_references().items():
        for name in columns:
            cleared = 0
            for row in converted[table_name]:
                if row[name] is not None:
                    row[name] = None
                    cleared += 1
            if cleared:
                cleared_counts[f"{table_name}.{name}"] = cleared
    return cleared_counts


def _map_user_references(
    db: Session,
    document: dict[str, Any],
    converted: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    """Point every user reference at this database's account with the same username.

    Returns the report section, the conflict samples and the conflict count. A reference with no matching account is
    cleared when the column allows it, and is a blocking conflict when the column requires a user.
    """
    username_by_id = {item["id"]: item["username"] for item in document["user_references"]}
    usernames = sorted(set(username_by_id.values()))
    users = Base.metadata.tables[USERS_TABLE]
    accounts: dict[str, Any] = {}
    for start in range(0, len(usernames), CHUNK_ROWS):
        for account_id, username in db.execute(
            select(users.c.id, users.c.username).where(users.c.username.in_(usernames[start:start + CHUNK_ROWS]))
        ).all():
            accounts[username] = account_id

    matched = 0
    cleared: dict[str, int] = {}
    missing: set[str] = set()
    conflicts: list[dict[str, Any]] = []
    conflict_count = 0
    for table_name, columns in user_reference_columns().items():
        table = Base.metadata.tables[table_name]
        primary_key = [column.name for column in table.primary_key.columns]
        for name in columns:
            for row in converted[table_name]:
                value = row[name]
                if value is None:
                    continue
                username = username_by_id.get(str(value))
                account = accounts.get(username) if username is not None else None
                if account is not None:
                    row[name] = account
                    matched += 1
                    continue
                missing.add(username or str(value))
                if table.c[name].nullable:
                    row[name] = None
                    cleared[f"{table_name}.{name}"] = cleared.get(f"{table_name}.{name}", 0) + 1
                    continue
                conflict_count += 1
                if len(conflicts) < SAMPLE_CONFLICTS:
                    conflicts.append({
                        "table": table_name,
                        "key": {name: username or str(value)},
                        "id": {key: row[key] for key in primary_key},
                        "reason": (
                            f"no account named {username!r} exists in this database; create it before importing"
                            if username is not None
                            else "the snapshot does not name the account this row requires"
                        ),
                    })
    section = {"matched": matched, "cleared": cleared, "missing_accounts": sorted(missing)}
    return section, conflicts, conflict_count


def _key(row: dict[str, Any], names: tuple[str, ...]) -> tuple | None:
    values = tuple(row[name] for name in names)
    return None if any(value is None for value in values) else values


def _plan_table(db: Session, table: Table, rows: list[dict[str, Any]], policy: str) -> dict[str, Any]:
    primary_key = tuple(column.name for column in table.primary_key.columns)
    existing_rows = db.execute(select(*table.primary_key.columns)).all()
    existing_ids = {tuple(row) for row in existing_rows}

    unique_sets: list[tuple[str, ...]] = []
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint):
            unique_sets.append(tuple(column.name for column in constraint.columns))
    for index in table.indexes:
        if index.unique:
            unique_sets.append(tuple(column.name for column in index.columns))
    if table.name in BUSINESS_KEYS:
        unique_sets.append(BUSINESS_KEYS[table.name])
    unique_sets = [names for names in dict.fromkeys(unique_sets) if set(names) != set(primary_key)]

    conflicts: list[dict[str, Any]] = []
    conflict_count = 0
    for names in unique_sets:
        held = {}
        for record in db.execute(select(*table.primary_key.columns, *(table.c[name] for name in names))).all():
            held[tuple(record[len(primary_key):])] = tuple(record[: len(primary_key)])
        seen_in_snapshot: dict[tuple, tuple] = {}
        for row in rows:
            key = _key(row, names)
            row_id = tuple(row[name] for name in primary_key)
            if key is None or (policy == "skip" and row_id in existing_ids):
                # A skipped row is not written, so its business key cannot collide with anything.
                continue
            if key in seen_in_snapshot and seen_in_snapshot[key] != row_id:
                conflict_count += 1
                reason = "the same business key appears twice in the snapshot"
            elif key in held and held[key] != row_id:
                conflict_count += 1
                reason = "the same business key is already held by another row in this database"
            else:
                seen_in_snapshot.setdefault(key, row_id)
                continue
            if len(conflicts) < SAMPLE_CONFLICTS:
                conflicts.append({"table": table.name, "key": dict(zip(names, key)), "id": dict(zip(primary_key, row_id)), "reason": reason})

    incoming_existing = [row for row in rows if tuple(row[name] for name in primary_key) in existing_ids]
    return {
        "primary_key": primary_key,
        "existing_ids": existing_ids,
        "incoming_existing": incoming_existing,
        "conflicts": conflicts,
        "conflict_count": conflict_count,
    }


def _check_references(db: Session, tables: list[Table]) -> list[str]:
    """Every non-null foreign key must point at a row that exists after the import."""
    problems: list[str] = []
    for table in tables:
        for constraint in table.foreign_key_constraints:
            local = [column.name for column in constraint.columns]
            remote_table = constraint.referred_table
            if remote_table.name in EXCLUDED_TABLES:
                continue
            remote = [element.column.name for element in constraint.elements]
            child = db.execute(select(*(table.c[name] for name in local)).where(
                *(table.c[name].is_not(None) for name in local)
            )).all()
            parent = {tuple(row) for row in db.execute(select(*(remote_table.c[name] for name in remote))).all()}
            missing = sum(1 for row in child if tuple(row) not in parent)
            if missing:
                problems.append(f"{table.name}({', '.join(local)}) refers to {missing} missing row(s) in {remote_table.name}")
    return problems


def import_snapshot(
    db: Session,
    document: dict[str, Any],
    *,
    policy: str,
    dry_run: bool,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Apply the snapshot in one transaction. A dry run rolls it back; a commit keeps it. Both return the same report."""
    if policy not in POLICIES:
        raise SnapshotError(422, f"Conflict policy must be one of: {', '.join(POLICIES)}")
    revision = document.get("database_revision")
    current = current_revision(db.connection())
    if revision != current:
        raise SnapshotError(
            409,
            f"The snapshot was exported from database revision {revision!r}, but this database is at {current!r}. "
            "Migrate the database to the snapshot's revision, or export again from a matching database.",
        )

    converted = _validated_rows(document)
    cleared = _clear_references(converted)
    included = included_tables()

    try:
        user_section, user_conflicts, user_conflict_count = _map_user_references(db, document, converted)
        plans = {table.name: _plan_table(db, table, converted[table.name], policy) for table in included}
        blocking = (user_conflicts + [sample for plan in plans.values() for sample in plan["conflicts"]])[:SAMPLE_CONFLICTS]
        blocking_total = user_conflict_count + sum(plan["conflict_count"] for plan in plans.values())
        report: dict[str, Any] = {
            "dry_run": dry_run,
            "committed": False,
            "policy": policy,
            "schema_version": SCHEMA_VERSION,
            "database_revision": current,
            "snapshot_revision": revision,
            "user_references": user_section,
            "cleared_references": cleared,
            "tables": {},
            "blocking_conflicts": blocking,
            "blocking_conflict_count": blocking_total,
        }
        if blocking_total:
            report["importable"] = False
            if not dry_run:
                raise SnapshotError(409, f"{blocking_total} conflict(s) block the import. Nothing was saved.")
            db.rollback()
            return report

        for table in included:
            plan = plans[table.name]
            rows = converted[table.name]
            existing_rows = plan["incoming_existing"]
            existing_keys = {tuple(row[name] for name in plan["primary_key"]) for row in existing_rows}
            new_rows = [row for row in rows if tuple(row[name] for name in plan["primary_key"]) not in plan["existing_ids"]]
            replaced = 0
            skipped = 0
            if policy == "replace":
                for row in existing_rows:
                    values = {name: value for name, value in row.items() if name not in plan["primary_key"]}
                    where = [table.c[name] == row[name] for name in plan["primary_key"]]
                    db.execute(update(table).where(*where).values(**values))
                    replaced += 1
            else:
                skipped = len(existing_keys)
            for start in range(0, len(new_rows), CHUNK_ROWS):
                db.execute(insert(table), new_rows[start:start + CHUNK_ROWS])
            report["tables"][table.name] = {
                "incoming": len(rows),
                "new": len(new_rows),
                "existing_ids": len(existing_rows),
                "skipped": skipped,
                "replaced": replaced,
            }

        problems = _check_references(db, included)
        if problems:
            raise SnapshotError(422, "The snapshot does not hold together: " + "; ".join(problems[:5]))

        report["totals"] = {
            key: sum(entry[key] for entry in report["tables"].values())
            for key in ("incoming", "new", "existing_ids", "skipped", "replaced")
        }
        report["importable"] = True
        if dry_run:
            db.rollback()
            return report

        db.add(AuditLog(
            id=uuid.uuid4(),
            table_name=AUDIT_TABLE_NAME,
            operation="IMPORT",
            record_id=None,
            new_values={
                "policy": policy,
                "schema_version": SCHEMA_VERSION,
                "database_revision": current,
                "snapshot_revision": revision,
                "totals": report["totals"],
                "tables": {name: entry["new"] for name, entry in report["tables"].items()},
                "user_references_matched": user_section["matched"],
                "user_references_cleared": user_section["cleared"],
            },
            performed_by_user_id=uuid.UUID(actor_user_id) if actor_user_id else None,
        ))
        db.commit()
        report["committed"] = True
        return report
    except SnapshotError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise SnapshotError(500, "The import failed. No changes were saved.") from exc


def record_export(db: Session, plan: ExportPlan, actor_user_id: str | None) -> None:
    """Write the export's audit entry (who, when, counts) before the stream starts."""
    db.add(AuditLog(
        id=uuid.uuid4(),
        table_name=AUDIT_TABLE_NAME,
        operation="EXPORT",
        record_id=None,
        new_values=export_audit_summary(plan),
        performed_by_user_id=uuid.UUID(actor_user_id) if actor_user_id else None,
    ))
    db.commit()
