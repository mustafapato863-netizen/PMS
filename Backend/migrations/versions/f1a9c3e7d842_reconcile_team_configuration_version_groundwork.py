"""Reconcile existing team configuration version groundwork.

Revision ID: f1a9c3e7d842
Revises: d9e4b7a2c106

Supported fresh startup creates tables from ORM metadata and stamps head.
Databases stamped at d9e4b7a2c106 by that older bootstrap have no
team_configuration_versions table and no performance_records.configuration_version_id.
Databases that reached the same revision through the historical chain already
have both, including coverage columns, publish snapshot columns, and the
partitioned record foreign key.

This revision inspects and changes only the public schema. Search path is
pinned to public for the migration transaction, and catalog reads, writes, and
foreign-key targets are schema-qualified. Identity of unique keys and the
coverage index comes from constraint and index attribute numbers, not from
definition text. A named unique or coverage index with a different key,
predicate, expression, included column, or invalid/not-ready state fails
before any catalog change.

Missing nullable contract columns, such as preview_snapshot, may be added.
Missing required columns are not repaired, including on an empty table. Check
identity keeps PostgreSQL's stored parentheses. A named check whose grouping
is a different arithmetic or boolean expression fails before any catalog
change. Foreign keys count only when pg_constraint.convalidated is true; an
otherwise matching NOT VALID key is left in place. This revision does not
update, backfill, validate, or coerce existing rows. A type, nullability,
key, referred schema, or delete-action mismatch fails before any catalog
change is attempted. Offline SQL generation is refused because an
unconditional script cannot tell the two shapes apart.

Downgrade is retention-first and intentionally a no-op. It does not drop
team_configuration_versions, coverage columns, snapshot columns, or
performance_records.configuration_version_id. Those objects may already have
existed before this revision, and this revision cannot know which rows are
referenced. Production rollback is the previous application build with the
expanded schema retained.

Team ON DELETE CASCADE and actor/record ON DELETE SET NULL are the existing
contract. They are not an immutable-history guarantee.
"""

from collections.abc import Mapping, Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f1a9c3e7d842"
down_revision = "d9e4b7a2c106"
branch_labels = None
depends_on = None

SCHEMA = "public"
VERSION_TABLE = "team_configuration_versions"
RECORD_TABLE = "performance_records"
RECORD_FK = "fk_performance_records_configuration_version"
COVERAGE_INDEX = "idx_team_config_coverage"
COVERAGE_COLUMNS = (
    "team_id",
    "status",
    "effective_from_year",
    "effective_from_month",
    "effective_until_year",
    "effective_until_month",
)
VERSION_UNIQUE = "uq_team_config_version"
VERSION_UNIQUE_COLUMNS = ("team_id", "version_number")

# pg_get_constraintdef output for the historical checks, with case and
# whitespace folded and parentheses kept. PostgreSQL rewrites BETWEEN, but
# these groupings are not equivalent to other parenthesizations of the same
# operators. Probed on PostgreSQL 16.15 and 18.6.
_CHECKS = {
    "ck_team_config_effective_from_month": (
        "(((effective_from_month >= 1) and (effective_from_month <= 12)))",
    ),
    "ck_team_config_effective_until_month": (
        "(((effective_until_month is null) or ((effective_until_month >= 1) and (effective_until_month <= 12))))",
    ),
    "ck_team_config_effective_range": (
        "(((effective_until_year is null) or (((effective_until_year * 12) + effective_until_month) >= ((effective_from_year * 12) + effective_from_month))))",
    ),
}
_CHECK_SQL = {
    "ck_team_config_effective_from_month": "effective_from_month BETWEEN 1 AND 12",
    "ck_team_config_effective_until_month": (
        "effective_until_month IS NULL OR effective_until_month BETWEEN 1 AND 12"
    ),
    "ck_team_config_effective_range": (
        "effective_until_year IS NULL OR "
        "(effective_until_year * 12 + effective_until_month) >= "
        "(effective_from_year * 12 + effective_from_month)"
    ),
}

_VERSION_COLUMNS = {
    "id": {"udt": "uuid", "nullable": False},
    "team_id": {"udt": "uuid", "nullable": False},
    "version_number": {"udt": "int4", "nullable": False},
    "status": {"udt": "varchar", "length": 20, "nullable": False},
    "effective_month": {"udt": "varchar", "length": 20, "nullable": False},
    "effective_year": {"udt": "int2", "nullable": False},
    "config_snapshot": {"udt": "json", "nullable": False},
    "config_checksum": {"udt": "varchar", "length": 64, "nullable": False},
    "created_by_user_id": {"udt": "uuid", "nullable": True},
    "published_by_user_id": {"udt": "uuid", "nullable": True},
    "created_at": {"udt": "timestamptz", "nullable": True},
    "published_at": {"udt": "timestamptz", "nullable": True},
    "superseded_at": {"udt": "timestamptz", "nullable": True},
    "notes": {"udt": "text", "nullable": True},
    "effective_from_month": {"udt": "int2", "nullable": False},
    "effective_from_year": {"udt": "int2", "nullable": False},
    "effective_until_month": {"udt": "int2", "nullable": True},
    "effective_until_year": {"udt": "int2", "nullable": True},
    "preview_snapshot": {"udt": "json", "nullable": True},
    "total_weight": {"udt": "numeric", "precision": 7, "scale": 4, "nullable": True},
    "overall_score": {"udt": "numeric", "precision": 10, "scale": 2, "nullable": True},
    "is_active": {"udt": "bool", "nullable": False},
}

_VERSION_FKS = (
    ("team_id", "teams", "id", "c", "team_configuration_versions_team_id_fkey"),
    ("created_by_user_id", "users", "id", "n", "team_configuration_versions_created_by_user_id_fkey"),
    ("published_by_user_id", "users", "id", "n", "team_configuration_versions_published_by_user_id_fkey"),
)


def upgrade() -> None:
    context = op.get_context()
    if context.as_sql:
        raise RuntimeError(
            "f1a9c3e7d842 inspects the live PostgreSQL catalog and cannot emit offline SQL."
        )
    bind = op.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        raise RuntimeError(
            "f1a9c3e7d842 requires a live PostgreSQL connection; it does not guess a schema."
        )
    # Transaction-local. Alembic runs this upgrade inside begin_transaction, so
    # unqualified operations cannot follow a caller's shadow schema.
    bind.execute(sa.text("SELECT set_config('search_path', 'public', true)"))
    _require_partition_catalog(bind)
    problems = _incompatibilities(bind)
    if problems:
        raise RuntimeError(
            "Incompatible team configuration version shape; no catalog changes were applied:\n- "
            + "\n- ".join(problems)
        )
    _apply_missing(bind)


def downgrade() -> None:
    """Keep version evidence and record links.

    See the module docstring. This is a deliberate no-op, not an unfinished
    downgrade: dropping the reused groundwork would delete history that this
    revision did not create.
    """
    return


def _require_partition_catalog(bind) -> None:
    found = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_attribute
            WHERE attrelid = 'pg_catalog.pg_constraint'::regclass
              AND attname = 'conparentid'
              AND NOT attisdropped
            """
        )
    ).scalar()
    if found != 1:
        raise RuntimeError(
            "PostgreSQL catalog has no pg_constraint.conparentid, so partition "
            "foreign keys cannot be distinguished from parent keys."
        )


def _incompatibilities(bind) -> list[str]:
    problems: list[str] = []
    record_kind = _relkind(bind, RECORD_TABLE)
    if record_kind not in {"r", "p"}:
        problems.append(
            f"{RECORD_TABLE} must already exist as a table or partitioned table "
            f"(found relkind={record_kind!r}). This revision does not create a replacement."
        )
    version_kind = _relkind(bind, VERSION_TABLE)
    if version_kind not in {None, "r"}:
        problems.append(
            f"{VERSION_TABLE} relkind={version_kind!r}; expected a regular table or absence."
        )
        return problems
    if version_kind is None:
        if _relkind(bind, "teams") != "r" or _relkind(bind, "users") != "r":
            problems.append("teams and users must exist before creating team_configuration_versions.")
    else:
        problems.extend(_version_table_problems(bind))
    if record_kind in {"r", "p"}:
        problems.extend(_record_link_problems(bind))
    return problems


def _version_table_problems(bind) -> list[str]:
    problems: list[str] = []
    columns = _columns(bind, VERSION_TABLE)
    missing_required = False
    for name, expected in _VERSION_COLUMNS.items():
        actual = columns.get(name)
        if actual is None:
            if not expected["nullable"]:
                missing_required = True
                problems.append(
                    f"{VERSION_TABLE}.{name} is missing. Refusing to repair a partial "
                    "version table that lacks a required column."
                )
            continue
        if not _column_matches(actual, expected):
            problems.append(
                f"{VERSION_TABLE}.{name} is { _describe(actual) }; expected { _describe_expected(expected) }."
            )
    if missing_required:
        return problems
    problems.extend(_primary_key_problems(bind))
    problems.extend(_unique_problems(bind))
    problems.extend(_check_problems(bind))
    problems.extend(_index_problems(bind))
    for column, referred_table, referred_column, delete_code, _name in _VERSION_FKS:
        problems.extend(
            _fk_problems(
                bind,
                VERSION_TABLE,
                column,
                referred_table,
                referred_column,
                delete_code,
            )
        )
    return problems


def _record_link_problems(bind) -> list[str]:
    columns = _columns(bind, RECORD_TABLE)
    actual = columns.get("configuration_version_id")
    if actual is None:
        return []
    expected = {"udt": "uuid", "nullable": True}
    if not _column_matches(actual, expected):
        return [
            f"{RECORD_TABLE}.configuration_version_id is { _describe(actual) }; "
            f"expected { _describe_expected(expected) }."
        ]
    if _relkind(bind, VERSION_TABLE) is None and _nonnull_record_links(bind):
        return [
            "performance_records.configuration_version_id is populated but "
            "team_configuration_versions is absent. Refusing to clear those links "
            "or create an empty version table behind them."
        ]
    return _fk_problems(bind, RECORD_TABLE, "configuration_version_id", VERSION_TABLE, "id", "n")


def _apply_missing(bind) -> None:
    if _relkind(bind, VERSION_TABLE) is None:
        _create_version_table()
    else:
        columns = _columns(bind, VERSION_TABLE)
        for name, expected in _VERSION_COLUMNS.items():
            if name not in columns:
                if not expected["nullable"]:
                    raise RuntimeError(
                        f"{VERSION_TABLE}.{name} is missing. Refusing to repair a partial "
                        "version table that lacks a required column."
                    )
                _add_version_column(name)
        if not _key_columns(bind, "p"):
            op.create_primary_key(f"{VERSION_TABLE}_pkey", VERSION_TABLE, ["id"], schema=SCHEMA)
        if not _exact_unique_names(bind):
            op.create_unique_constraint(
                VERSION_UNIQUE,
                VERSION_TABLE,
                list(VERSION_UNIQUE_COLUMNS),
                schema=SCHEMA,
            )
        for name, expression in _CHECK_SQL.items():
            if _matching_checks(bind).get(name) != "present":
                op.create_check_constraint(name, VERSION_TABLE, expression, schema=SCHEMA)
        if not _exact_coverage_names(bind):
            op.create_index(COVERAGE_INDEX, VERSION_TABLE, list(COVERAGE_COLUMNS), schema=SCHEMA)
        for column, referred_table, referred_column, delete_code, name in _VERSION_FKS:
            if _fk_state(bind, VERSION_TABLE, column, referred_table, referred_column, delete_code) == "missing":
                op.create_foreign_key(
                    name,
                    VERSION_TABLE,
                    referred_table,
                    [column],
                    [referred_column],
                    ondelete="CASCADE" if delete_code == "c" else "SET NULL",
                    source_schema=SCHEMA,
                    referent_schema=SCHEMA,
                )
    if "configuration_version_id" not in _columns(bind, RECORD_TABLE):
        op.add_column(
            RECORD_TABLE,
            sa.Column("configuration_version_id", postgresql.UUID(as_uuid=True), nullable=True),
            schema=SCHEMA,
        )
    if _fk_state(bind, RECORD_TABLE, "configuration_version_id", VERSION_TABLE, "id", "n") == "missing":
        if _orphan_record_links(bind):
            raise RuntimeError(
                "performance_records.configuration_version_id contains values that do not "
                "match team_configuration_versions.id. Refusing to clear or rewrite them."
            )
        op.create_foreign_key(
            RECORD_FK,
            RECORD_TABLE,
            VERSION_TABLE,
            ["configuration_version_id"],
            ["id"],
            ondelete="SET NULL",
            source_schema=SCHEMA,
            referent_schema=SCHEMA,
        )


def _create_version_table() -> None:
    op.create_table(
        VERSION_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("effective_month", sa.String(length=20), nullable=False),
        sa.Column("effective_year", sa.SmallInteger(), nullable=False),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("config_checksum", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("effective_from_month", sa.SmallInteger(), nullable=False),
        sa.Column("effective_from_year", sa.SmallInteger(), nullable=False),
        sa.Column("effective_until_month", sa.SmallInteger(), nullable=True),
        sa.Column("effective_until_year", sa.SmallInteger(), nullable=True),
        sa.Column("preview_snapshot", sa.JSON(), nullable=True),
        sa.Column("total_weight", sa.Numeric(7, 4), nullable=True),
        sa.Column("overall_score", sa.Numeric(10, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["team_id"],
            [f"{SCHEMA}.teams.id"],
            name="team_configuration_versions_team_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            [f"{SCHEMA}.users.id"],
            name="team_configuration_versions_created_by_user_id_fkey",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["published_by_user_id"],
            [f"{SCHEMA}.users.id"],
            name="team_configuration_versions_published_by_user_id_fkey",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("team_id", "version_number", name=VERSION_UNIQUE),
        sa.CheckConstraint(_CHECK_SQL["ck_team_config_effective_from_month"], name="ck_team_config_effective_from_month"),
        sa.CheckConstraint(_CHECK_SQL["ck_team_config_effective_until_month"], name="ck_team_config_effective_until_month"),
        sa.CheckConstraint(_CHECK_SQL["ck_team_config_effective_range"], name="ck_team_config_effective_range"),
        schema=SCHEMA,
    )
    op.create_index(COVERAGE_INDEX, VERSION_TABLE, list(COVERAGE_COLUMNS), schema=SCHEMA)


def _add_version_column(name: str) -> None:
    expected = _VERSION_COLUMNS[name]
    if not expected["nullable"]:
        raise RuntimeError(
            f"{VERSION_TABLE}.{name} is missing. Refusing to repair a partial "
            "version table that lacks a required column."
        )
    op.add_column(VERSION_TABLE, _new_column(name, expected), schema=SCHEMA)


def _new_column(name: str, expected: Mapping[str, object]) -> sa.Column:
    udt = expected["udt"]
    if udt == "uuid":
        type_ = postgresql.UUID(as_uuid=True)
    elif udt == "int4":
        type_ = sa.Integer()
    elif udt == "int2":
        type_ = sa.SmallInteger()
    elif udt == "varchar":
        type_ = sa.String(length=int(expected["length"]))
    elif udt == "json":
        type_ = sa.JSON()
    elif udt == "timestamptz":
        type_ = sa.DateTime(timezone=True)
    elif udt == "text":
        type_ = sa.Text()
    elif udt == "numeric":
        type_ = sa.Numeric(int(expected["precision"]), int(expected["scale"]))
    elif udt == "bool":
        type_ = sa.Boolean()
    else:
        raise RuntimeError(f"No PostgreSQL type mapping for {name}.")
    kwargs = {"nullable": bool(expected["nullable"])}
    if name in {"created_at", "published_at"}:
        kwargs["server_default"] = sa.func.now()
    if name == "is_active":
        kwargs["server_default"] = sa.text("true")
    return sa.Column(name, type_, **kwargs)


def _column_matches(actual: Mapping[str, object], expected: Mapping[str, object]) -> bool:
    nullable = "YES" if expected["nullable"] else "NO"
    if actual["udt_name"] != expected["udt"] or actual["is_nullable"] != nullable:
        return False
    if "length" in expected and actual["character_maximum_length"] != expected["length"]:
        return False
    if "precision" in expected:
        precision = actual["numeric_precision"]
        scale = actual["numeric_scale"]
        if precision is None or scale is None:
            return False
        if int(precision) != expected["precision"] or int(scale) != expected["scale"]:
            return False
    return True


def _describe(actual: Mapping[str, object]) -> str:
    return (
        f"udt={actual['udt_name']} length={actual['character_maximum_length']} "
        f"precision={actual['numeric_precision']} scale={actual['numeric_scale']} "
        f"nullable={actual['is_nullable']}"
    )


def _describe_expected(expected: Mapping[str, object]) -> str:
    nullable = "YES" if expected["nullable"] else "NO"
    return (
        f"udt={expected['udt']} length={expected.get('length')} "
        f"precision={expected.get('precision')} scale={expected.get('scale')} nullable={nullable}"
    )


def _primary_key_problems(bind) -> list[str]:
    keys = _key_columns(bind, "p")
    if not keys:
        if _row_count(bind, VERSION_TABLE) > 0:
            return [f"{VERSION_TABLE} has no primary key and already has rows. Refusing to rebuild it."]
        return []
    if any(columns != ("id",) for columns in keys.values()):
        rendered = ", ".join(f"{name} {list(columns)}" for name, columns in sorted(keys.items()))
        return [
            f"{VERSION_TABLE} primary key is {rendered}. Expected PRIMARY KEY (id). Refusing to replace it."
        ]
    return []


def _unique_problems(bind) -> list[str]:
    keys = _key_columns(bind, "u")
    named = keys.get(VERSION_UNIQUE)
    if named is not None and named != VERSION_UNIQUE_COLUMNS:
        return [
            f"{VERSION_UNIQUE} constrains {list(named)}, not {list(VERSION_UNIQUE_COLUMNS)}. "
            "Refusing to replace it."
        ]
    exact = _exact_unique_names(bind)
    if len(exact) > 1:
        return [f"Duplicate unique keys on {VERSION_TABLE} (team_id, version_number): {sorted(exact)}."]
    if not exact and _duplicate_versions(bind):
        return [
            "Duplicate team_id/version_number rows exist. Refusing to add "
            "uq_team_config_version or delete them."
        ]
    return []


def _exact_unique_names(bind) -> list[str]:
    return [name for name, columns in _key_columns(bind, "u").items() if columns == VERSION_UNIQUE_COLUMNS]


def _key_columns(bind, contype: str) -> dict[str, tuple[str, ...]]:
    rows = bind.execute(
        sa.text(
            """
            SELECT con.conname AS name,
                   array_agg(att.attname ORDER BY key.ord) AS columns
            FROM pg_constraint AS con
            JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS key(attnum, ord) ON true
            JOIN pg_attribute AS att
              ON att.attrelid = con.conrelid
             AND att.attnum = key.attnum
             AND NOT att.attisdropped
            WHERE con.contype = :contype
              AND con.conrelid = 'public.team_configuration_versions'::regclass
            GROUP BY con.oid, con.conname
            """
        ),
        {"contype": contype},
    ).mappings().all()
    return {str(row["name"]): tuple(str(column) for column in row["columns"]) for row in rows}


def _duplicate_versions(bind) -> bool:
    columns = _columns(bind, VERSION_TABLE)
    if not set(VERSION_UNIQUE_COLUMNS).issubset(columns):
        raise RuntimeError(
            "Refusing to scan duplicate team configuration versions without team_id and version_number."
        )
    found = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM public.team_configuration_versions
            GROUP BY team_id, version_number
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).scalar()
    return found is not None


def _check_problems(bind) -> list[str]:
    states = _matching_checks(bind)
    problems = []
    for name, state in states.items():
        if state == "incompatible":
            problems.append(f"{name} exists with a different expression. Refusing to replace it.")
    return problems


def _matching_checks(bind) -> dict[str, str]:
    identities = {
        name: _check_identity(definition)
        for name, definition in _constraint_definitions(bind, "c").items()
    }
    states = {}
    for name, accepted in _CHECKS.items():
        current = identities.get(name)
        if current is not None:
            states[name] = "present" if current in accepted else "incompatible"
            continue
        states[name] = "present" if any(value in accepted for value in identities.values()) else "missing"
    return states


def _index_problems(bind) -> list[str]:
    indexes = _indexes(bind)
    named = indexes.get(COVERAGE_INDEX)
    if named is not None and not _is_complete_coverage(named):
        return [
            f"{COVERAGE_INDEX} is not a valid complete index on {list(COVERAGE_COLUMNS)} "
            f"({_describe_index(named)}). Refusing to accept or replace it."
        ]
    exact = _exact_coverage_names(bind)
    if len(exact) > 1:
        return [f"Duplicate complete coverage indexes on {VERSION_TABLE}: {sorted(exact)}."]
    return []


def _exact_coverage_names(bind) -> list[str]:
    return [name for name, index in _indexes(bind).items() if _is_complete_coverage(index)]


def _is_complete_coverage(index: Mapping[str, object]) -> bool:
    return (
        tuple(index["columns"]) == COVERAGE_COLUMNS
        and not index["is_unique"]
        and index["is_valid"]
        and index["is_ready"]
        and not index["is_partial"]
        and not index["has_expressions"]
        and not index["has_included"]
    )


def _describe_index(index: Mapping[str, object]) -> str:
    return (
        f"columns={list(index['columns'])} unique={index['is_unique']} "
        f"valid={index['is_valid']} ready={index['is_ready']} partial={index['is_partial']} "
        f"expressions={index['has_expressions']} included={index['has_included']}"
    )


def _fk_problems(bind, table: str, column: str, referred_table: str, referred_column: str, delete_code: str) -> list[str]:
    state = _fk_state(bind, table, column, referred_table, referred_column, delete_code)
    if state == "duplicate":
        return [f"Duplicate foreign keys on {table}.{column}."]
    if state == "incompatible":
        return [
            f"{table}.{column} foreign key is not a validated reference to "
            f"{referred_table}({referred_column}) ON DELETE {_delete_name(delete_code)}. "
            "Refusing to drop, replace, or validate it."
        ]
    if state == "missing" and table == RECORD_TABLE and _orphan_record_links(bind):
        return [
            "performance_records.configuration_version_id contains values that do not "
            "match team_configuration_versions.id. Refusing to clear or rewrite them."
        ]
    return []


def _fk_state(bind, table: str, column: str, referred_table: str, referred_column: str, delete_code: str) -> str:
    involving = []
    exact = []
    for foreign_key in _foreign_keys(bind, table):
        columns = [str(item) for item in foreign_key["columns"]]
        if column not in columns:
            continue
        involving.append(foreign_key)
        referred_columns = [str(item) for item in foreign_key["referred_columns"]]
        if (
            columns == [column]
            and foreign_key["referred_schema"] == SCHEMA
            and foreign_key["referred_table"] == referred_table
            and referred_columns == [referred_column]
            and foreign_key["delete_action"] == delete_code
            and foreign_key["validated"]
        ):
            exact.append(foreign_key)
    if len(exact) > 1:
        return "duplicate"
    if len(involving) != len(exact):
        return "incompatible"
    if exact:
        return "present"
    return "missing"


def _nonnull_record_links(bind) -> bool:
    if "configuration_version_id" not in _columns(bind, RECORD_TABLE):
        return False
    found = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM public.performance_records
            WHERE configuration_version_id IS NOT NULL
            LIMIT 1
            """
        )
    ).scalar()
    return found is not None


def _orphan_record_links(bind) -> bool:
    if _relkind(bind, VERSION_TABLE) is None:
        return False
    if "id" not in _columns(bind, VERSION_TABLE):
        return False
    if "configuration_version_id" not in _columns(bind, RECORD_TABLE):
        return False
    found = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM public.performance_records AS record
            WHERE record.configuration_version_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM public.team_configuration_versions AS version
                  WHERE version.id = record.configuration_version_id
              )
            LIMIT 1
            """
        )
    ).scalar()
    return found is not None


def _foreign_keys(bind, table: str) -> Sequence[Mapping[str, object]]:
    return bind.execute(
        sa.text(
            """
            SELECT con.conname AS name,
                   con.confdeltype AS delete_action,
                   con.convalidated AS validated,
                   array_agg(src.attname ORDER BY src_key.ord) AS columns,
                   ref_nsp.nspname AS referred_schema,
                   ref_cls.relname AS referred_table,
                   array_agg(dst.attname ORDER BY src_key.ord) AS referred_columns
            FROM pg_constraint AS con
            JOIN pg_class AS rel ON rel.oid = con.conrelid
            JOIN pg_namespace AS nsp ON nsp.oid = rel.relnamespace
            JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS src_key(attnum, ord) ON true
            JOIN pg_attribute AS src
              ON src.attrelid = rel.oid
             AND src.attnum = src_key.attnum
             AND NOT src.attisdropped
            JOIN pg_class AS ref_cls ON ref_cls.oid = con.confrelid
            JOIN pg_namespace AS ref_nsp ON ref_nsp.oid = ref_cls.relnamespace
            JOIN LATERAL unnest(con.confkey) WITH ORDINALITY AS dst_key(attnum, ord)
              ON dst_key.ord = src_key.ord
            JOIN pg_attribute AS dst
              ON dst.attrelid = ref_cls.oid
             AND dst.attnum = dst_key.attnum
             AND NOT dst.attisdropped
            WHERE nsp.nspname = 'public'
              AND rel.relname = :table
              AND con.contype = 'f'
              AND con.conparentid = 0
            GROUP BY con.oid, con.conname, con.confdeltype, con.convalidated, ref_nsp.nspname, ref_cls.relname
            """
        ),
        {"table": table},
    ).mappings().all()


def _indexes(bind) -> dict[str, dict[str, object]]:
    rows = bind.execute(
        sa.text(
            """
            SELECT i.relname AS name,
                   ix.indisunique AS is_unique,
                   ix.indisvalid AS is_valid,
                   ix.indisready AS is_ready,
                   (ix.indpred IS NOT NULL) AS is_partial,
                   (ix.indexprs IS NOT NULL) AS has_expressions,
                   (ix.indnatts > ix.indnkeyatts) AS has_included,
                   array_agg(att.attname ORDER BY key.ord)
                       FILTER (WHERE key.attnum > 0 AND key.ord <= ix.indnkeyatts) AS columns
            FROM pg_index AS ix
            JOIN pg_class AS t ON t.oid = ix.indrelid
            JOIN pg_class AS i ON i.oid = ix.indexrelid
            JOIN pg_namespace AS n ON n.oid = t.relnamespace
            JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY AS key(attnum, ord) ON true
            LEFT JOIN pg_attribute AS att
              ON att.attrelid = t.oid
             AND att.attnum = key.attnum
             AND key.attnum > 0
             AND NOT att.attisdropped
            WHERE n.nspname = 'public'
              AND t.relname = :table
            GROUP BY ix.indexrelid, i.relname
            """
        ),
        {"table": VERSION_TABLE},
    ).mappings().all()
    indexes = {}
    for row in rows:
        raw_columns = row["columns"] or []
        indexes[str(row["name"])] = {
            "is_unique": bool(row["is_unique"]),
            "is_valid": bool(row["is_valid"]),
            "is_ready": bool(row["is_ready"]),
            "is_partial": bool(row["is_partial"]),
            "has_expressions": bool(row["has_expressions"]),
            "has_included": bool(row["has_included"]),
            "columns": tuple(str(column) for column in raw_columns if column is not None),
        }
    return indexes


def _constraint_definitions(bind, contype: str) -> dict[str, str]:
    rows = bind.execute(
        sa.text(
            """
            SELECT conname, pg_get_constraintdef(oid) AS definition
            FROM pg_constraint
            WHERE contype = :contype
              AND conrelid = 'public.team_configuration_versions'::regclass
            """
        ),
        {"contype": contype},
    ).mappings().all()
    return {str(row["conname"]): str(row["definition"]) for row in rows}


def _columns(bind, table: str) -> dict[str, Mapping[str, object]]:
    rows = bind.execute(
        sa.text(
            """
            SELECT column_name, udt_name, character_maximum_length,
                   numeric_precision, numeric_scale, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table
            """
        ),
        {"table": table},
    ).mappings().all()
    return {str(row["column_name"]): row for row in rows}


def _relkind(bind, table: str):
    return bind.execute(
        sa.text(
            """
            SELECT c.relkind
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = :table
            """
        ),
        {"table": table},
    ).scalar()


def _row_count(bind, table: str) -> int:
    if table != VERSION_TABLE:
        raise RuntimeError(f"Refusing to count rows for unexpected table {table}.")
    return int(
        bind.execute(sa.text("SELECT count(*) FROM public.team_configuration_versions")).scalar_one()
    )


def _check_identity(expression: str) -> str:
    """Fold case and whitespace. Parentheses stay, so they still distinguish expressions."""
    compact = " ".join(expression.lower().split())
    prefix = "check "
    if compact.startswith(prefix):
        compact = compact[len(prefix):]
    return compact


def _delete_name(code: str) -> str:
    return {"c": "CASCADE", "n": "SET NULL", "a": "NO ACTION", "r": "RESTRICT", "d": "SET DEFAULT"}.get(code, code)
