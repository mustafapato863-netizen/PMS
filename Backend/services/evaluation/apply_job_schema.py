"""Expand-only schema for a later bounded evaluation apply job.

The synchronous ``EvaluationWorkflow.apply`` path stays in place. These tables
do not score, promote, or publish anything. They give a later slice a place to
store one job header, immutable per-record before/after evidence, and one
cache-notification outbox row.

Foreign keys prove that a scope, version, job, revision, and ``(record id,
year)`` exist. They do not prove that those rows describe the same team,
month, approved rules, or live source payload. Enqueue and promotion still
have to check that.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import event, inspect, text


APPLY_FOUNDATION_REVISION = "b4e7c2a9d815"
APPLY_FOUNDATION_PREDECESSOR = "f7c3a9e1d5b8"

CONTROL_TABLE = "evaluation_apply_controls"
STAGE_TABLE = "evaluation_apply_stage_rows"
OUTBOX_TABLE = "cache_invalidation_outbox"
JOB_TABLE = "processing_jobs"
FOUNDATION_TABLES = (CONTROL_TABLE, STAGE_TABLE, OUTBOX_TABLE)

OPEN_STATES = ("pending", "staging", "promoting")
CONTROL_STATES = OPEN_STATES + ("promoted", "failed", "cancelled")
NAMESPACE_DATA = "data"
JOB_KIND_EVALUATION_APPLY = "evaluation_apply"
PRIOR_JOB_KINDS = ("pms_upload", "report_generation", "story_report_generation")
JOB_KINDS = PRIOR_JOB_KINDS + (JOB_KIND_EVALUATION_APPLY,)
STATUS_PAYLOAD_LIMIT = 2048
OUTBOX_ERROR_LIMIT = 240
CURSOR_LIMIT = 80

PRIOR_KIND_CHECK_SQL = (
    "kind IN ('pms_upload', 'report_generation', 'story_report_generation')"
)
KIND_CHECK_SQL = (
    "kind IN ('pms_upload', 'report_generation', 'story_report_generation', "
    "'evaluation_apply')"
)
CLAIM_EPOCH_CHECK_SQL = "claim_epoch IS NULL OR claim_epoch >= 0"

_MONTHS = (
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

PROCESSING_JOB_COLUMNS_BEFORE = (
    "id",
    "kind",
    "status",
    "requested_by_user_id",
    "requested_by_name",
    "request_json",
    "input_path",
    "progress",
    "attempt_count",
    "max_attempts",
    "available_at",
    "worker_id",
    "lease_expires_at",
    "heartbeat_at",
    "started_at",
    "finished_at",
    "result_type",
    "result_id",
    "result_json",
    "error_code",
    "safe_error_message",
    "idempotency_key",
    "created_at",
    "updated_at",
)

CONTROL_COLUMNS = (
    "job_id",
    "scope_id",
    "version_id",
    "team_id",
    "performance_level",
    "position_name",
    "year",
    "month",
    "engine_version",
    "rules_checksum",
    "proof_source_fingerprint",
    "lineage_fingerprint",
    "requested_by_user_id",
    "actor_snapshot",
    "state",
    "claim_epoch",
    "stage_cursor",
    "staged_count",
    "promoted_count",
    "promoted_revision_id",
    "created_at",
)
STAGE_COLUMNS = (
    "job_id",
    "claim_epoch",
    "record_id",
    "record_year",
    "before_row",
    "after_row",
    "before_hash",
    "after_hash",
    "rules_checksum",
    "captured_at",
)
OUTBOX_COLUMNS = (
    "id",
    "job_id",
    "revision_id",
    "namespace",
    "dedup_key",
    "created_at",
    "delivery_attempts",
    "next_retry_at",
    "published_at",
    "last_error",
)

CONTROL_CHECKS = {
    "ck_evaluation_apply_state": (
        "state IN ('pending', 'staging', 'promoting', 'promoted', 'failed', 'cancelled')"
    ),
    "ck_evaluation_apply_month": "month BETWEEN 1 AND 12",
    "ck_evaluation_apply_year": "year BETWEEN 2000 AND 2100",
    "ck_evaluation_apply_level": (
        "performance_level IN ('Employee', 'Managerial', 'Corporate')"
    ),
    "ck_evaluation_apply_position": "position_name IS NOT NULL",
    "ck_evaluation_apply_epoch": "claim_epoch >= 0",
    "ck_evaluation_apply_staged_count": "staged_count >= 0",
    "ck_evaluation_apply_promoted_count": "promoted_count >= 0",
    "ck_evaluation_apply_cursor": (
        f"stage_cursor IS NULL OR length(stage_cursor) BETWEEN 1 AND {CURSOR_LIMIT}"
    ),
    "ck_evaluation_apply_engine_version": "length(engine_version) BETWEEN 1 AND 64",
    "ck_evaluation_apply_rules_checksum": "length(rules_checksum) = 64",
    "ck_evaluation_apply_proof_fingerprint": "length(proof_source_fingerprint) = 64",
    "ck_evaluation_apply_lineage_fingerprint": "length(lineage_fingerprint) = 64",
    "ck_evaluation_apply_open_requester": (
        "state NOT IN ('pending', 'staging', 'promoting') OR requested_by_user_id IS NOT NULL"
    ),
    "ck_evaluation_apply_promoted_revision": (
        "(state = 'promoted' AND promoted_revision_id IS NOT NULL AND promoted_count >= 0) "
        "OR (state <> 'promoted' AND promoted_revision_id IS NULL AND promoted_count = 0)"
    ),
    "ck_evaluation_apply_pending_progress": (
        "state <> 'pending' OR (staged_count = 0 AND stage_cursor IS NULL)"
    ),
}
STAGE_CHECKS = {
    "ck_evaluation_apply_stage_epoch": "claim_epoch >= 0",
    "ck_evaluation_apply_stage_year": "record_year BETWEEN 2000 AND 2100",
    "ck_evaluation_apply_stage_before_hash": "length(before_hash) = 64",
    "ck_evaluation_apply_stage_after_hash": "length(after_hash) = 64",
    "ck_evaluation_apply_stage_rules_checksum": "length(rules_checksum) = 64",
}
OUTBOX_CHECKS = {
    "ck_cache_invalidation_namespace": "namespace = 'data'",
    "ck_cache_invalidation_attempts": "delivery_attempts >= 0",
    "ck_cache_invalidation_dedup": "length(dedup_key) BETWEEN 1 AND 200",
    "ck_cache_invalidation_error": (
        f"last_error IS NULL OR length(last_error) <= {OUTBOX_ERROR_LIMIT}"
    ),
    "ck_cache_invalidation_published_attempt": (
        "published_at IS NULL OR delivery_attempts >= 1"
    ),
}

CONTROL_INDEXES = (
    "uq_evaluation_apply_one_open_scope_month",
    "idx_evaluation_apply_control_version",
    "idx_evaluation_apply_control_revision",
)
STAGE_INDEXES = ("idx_evaluation_apply_stage_keyset",)
OUTBOX_INDEXES = (
    "uq_cache_invalidation_outbox_dedup",
    "idx_cache_invalidation_outbox_unpublished",
)

CONTROL_FOREIGN_KEYS = {
    "job_id": ("processing_jobs", ("id",), "RESTRICT"),
    "scope_id": ("evaluation_scopes", ("id",), "RESTRICT"),
    "version_id": ("team_configuration_versions", ("id",), "RESTRICT"),
    "team_id": ("teams", ("id",), "RESTRICT"),
    "requested_by_user_id": ("users", ("id",), "SET NULL"),
    "promoted_revision_id": ("evaluation_revisions", ("id",), "RESTRICT"),
}
STAGE_FOREIGN_KEYS = {
    "job_id": ("evaluation_apply_controls", ("job_id",), "RESTRICT"),
    ("record_id", "record_year"): ("performance_records", ("id", "year"), "RESTRICT"),
}
OUTBOX_FOREIGN_KEYS = {
    "job_id": ("evaluation_apply_controls", ("job_id",), "RESTRICT"),
    "revision_id": ("evaluation_revisions", ("id",), "RESTRICT"),
}
JOB_FOUNDATION_CHECKS = {
    "ck_processing_job_kind": KIND_CHECK_SQL,
    "ck_processing_job_claim_epoch": CLAIM_EPOCH_CHECK_SQL,
}
# Later rows are locked only after earlier rows. A statement that already holds
# its own row may lock rows that sort later, never rows that sort earlier.
_LOCK_ORDER_SQL = (
    "Lock order is processing_jobs, evaluation_scopes, "
    "evaluation_apply_controls, performance_records. "
    "Never lock a later row and then an earlier one."
)
_INDEX_CONTRACTS = (
    (
        CONTROL_TABLE,
        "uq_evaluation_apply_one_open_scope_month",
        ("scope_id", "year", "month"),
        True,
        "state IN ('pending', 'staging', 'promoting')",
    ),
    (CONTROL_TABLE, "idx_evaluation_apply_control_version", ("version_id",), False, None),
    (
        CONTROL_TABLE,
        "idx_evaluation_apply_control_revision",
        ("promoted_revision_id",),
        False,
        None,
    ),
    (
        STAGE_TABLE,
        "idx_evaluation_apply_stage_keyset",
        ("job_id", "claim_epoch", "record_year", "record_id"),
        False,
        None,
    ),
    (
        OUTBOX_TABLE,
        "uq_cache_invalidation_outbox_dedup",
        ("namespace", "dedup_key"),
        True,
        None,
    ),
    (
        OUTBOX_TABLE,
        "idx_cache_invalidation_outbox_unpublished",
        ("namespace", "next_retry_at"),
        False,
        "published_at IS NULL",
    ),
)
_GUARD_TRIGGER_CONTRACT = (
    ("trg_evaluation_apply_control_guard", CONTROL_TABLE, "guard_evaluation_apply_control"),
    ("trg_evaluation_apply_stage_guard", STAGE_TABLE, "guard_evaluation_apply_stage_row"),
    ("trg_cache_invalidation_outbox_guard", OUTBOX_TABLE, "guard_cache_invalidation_outbox"),
    ("trg_processing_job_apply_foundation", JOB_TABLE, "guard_processing_job_apply_foundation"),
    ("trg_evaluation_scope_apply_foundation", "evaluation_scopes", "guard_evaluation_scope_apply_foundation"),
    (
        "trg_performance_record_apply_foundation",
        "performance_records",
        "guard_performance_record_apply_foundation",
    ),
)

GUARD_SNIPPETS = (
    "evaluation apply captured identity is immutable",
    "evaluation apply actor snapshot must record a known user",
    "evaluation apply fingerprints must be lowercase sha256",
    "evaluation apply control must be captured pending",
    "evaluation apply claim epoch must match the processing job",
    "illegal evaluation apply state transition",
    "evaluation apply claim epoch changes only on retry",
    "evaluation apply retry must advance the epoch and clear progress",
    "open evaluation apply cannot replay a missing requester",
    "evaluation apply evidence cannot be deleted",
    "stale evaluation apply epoch cannot write stage evidence",
    "evaluation apply stage evidence is immutable",
    "evaluation apply stage evidence cannot be deleted",
    "evaluation apply stage payload must be a json object",
    "evaluation apply stage rules checksum does not match the captured rules",
    "evaluation apply stage record is outside the captured scope month",
    "evaluation apply job header cannot be deleted while a control exists",
    "evaluation apply job kind cannot change after control capture",
    "evaluation apply job status cannot carry a population payload",
    "captured evaluation scope identity cannot change while apply evidence exists",
    "staged performance evidence cannot be deleted",
    "staged performance identity cannot change while apply evidence exists",
    "cache invalidation outbox requires a promoted revision",
    "cache invalidation outbox identity is immutable",
    "cache invalidation delivery is append-only until publish",
    "published cache invalidation cannot be reversed or rewritten",
    "cache invalidation outbox evidence cannot be deleted",
    "evaluation apply scope identity does not match the scope row",
    "evaluation apply version team does not match the captured team",
    "evaluation apply staged count is frozen outside staging",
    "evaluation apply stage cursor is frozen",
    "evaluation apply staged count cannot decrease",
    "promoted evaluation apply requires a revision",
    "promoted evaluation apply evidence is immutable",
    "evaluation apply requester can only be cleared by audit deletion",
    "evaluation apply stage hash must be lowercase sha256",
)

POPULATION_COLUMNS = frozenset(
    {
        "record_payload",
        "prior_snapshot",
        "applied_snapshot",
        "population",
        "employees",
        "preview_evidence",
        "request_json",
        "result_json",
    }
)


def canonical_json_text(value: Any) -> str:
    """Stable JSON for one record. Callers pass a single row, not a population."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_row_hash(row: Any) -> str:
    if not isinstance(row, dict):
        raise TypeError("A staged evaluation row must be a JSON object.")
    return sha256_hex(canonical_json_text(row))


def cache_dedup_key(job_id: Any, revision_id: Any) -> str:
    return f"evaluation_apply:{job_id}:{revision_id}:{NAMESPACE_DATA}"


def known_actor_snapshot(user_id: Any) -> dict[str, str]:
    """Attribution captured with the job. This is not an authorization claim."""

    return {"state": "known", "user_id": str(user_id)}


def _month_name_case(expression: str) -> str:
    branches = " ".join(
        f"WHEN {number} THEN '{name}'" for number, name in enumerate(_MONTHS, start=1)
    )
    return f"CASE {expression} {branches} ELSE NULL END"


def _normalize_sql(value: str) -> str:
    return " ".join((value or "").replace("public.", "").replace('"', "").split()).casefold()


_CAST_RE = re.compile(
    r"::(?:character\s+varying|double\s+precision|[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s*\(\s*[0-9]+\s*\))?(?:\[\])?",
    re.IGNORECASE,
)
_CHECK_TOKEN_RE = re.compile(
    r"\s+"
    r"|'(?:[^']|'')*'"
    r"|[0-9]+(?:\.[0-9]+)?"
    r"|>=|<=|<>|!="
    r"|[(),\[\]]"
    r"|[A-Za-z_][A-Za-z0-9_]*"
    r"|[=><]"
)
_TRIGGER_HEAD_RE = re.compile(
    r"CREATE\s+TRIGGER\s+(\w+)\s+BEFORE\s+"
    r"(?:INSERT|UPDATE|DELETE)(?:\s+OR\s+(?:INSERT|UPDATE|DELETE))*\s+ON\s+(\w+)",
    re.IGNORECASE,
)


def _prepare_check_sql(value: str) -> str:
    text_value = (value or "").replace("public.", "").replace('"', "")
    previous = None
    while text_value != previous:
        previous = text_value
        text_value = _CAST_RE.sub("", text_value)
    return text_value.strip()


class _CheckParser:
    """Canonical form for authored checks and PostgreSQL's deparser.

    Casts, extra parentheses, ``IN`` and ``= ANY (ARRAY[...])``, and
    ``BETWEEN`` are the same predicate. The year bounds and the allowed state
    set stay in the tree, so a wider bound or a different state does not match.
    """

    def __init__(self, sql: str):
        self.tokens: list[tuple[str, object]] = []
        position = 0
        for match in _CHECK_TOKEN_RE.finditer(sql):
            if match.start() != position:
                raise ValueError(sql[position:match.start()])
            position = match.end()
            token = match.group(0)
            if token.isspace():
                continue
            if token.startswith("'"):
                self.tokens.append(("lit", token[1:-1].replace("''", "'")))
            elif token[0].isdigit():
                self.tokens.append(("lit", float(token) if "." in token else int(token)))
            elif token in {">=", "<=", "<>", "!=", "=", ">", "<"}:
                self.tokens.append(("op", "<>" if token == "!=" else token))
            elif token in {"(", ")", ",", "[", "]"}:
                self.tokens.append(("punct", token))
            else:
                self.tokens.append(("word", token.casefold()))
        if position != len(sql):
            raise ValueError(sql[position:])
        self.index = 0

    def parse(self):
        if self._peek_word() == "check":
            self._pop()
        node = self._parse_or()
        if self.index != len(self.tokens):
            raise ValueError(f"unparsed check tail: {self.tokens[self.index:]}")
        return node

    def _peek(self):
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def _peek_word(self) -> str | None:
        token = self._peek()
        if token and token[0] == "word":
            return str(token[1])
        return None

    def _pop(self):
        token = self.tokens[self.index]
        self.index += 1
        return token

    def _expect(self, kind: str, value: str) -> None:
        token = self._peek()
        if token != (kind, value):
            raise ValueError(f"expected {(kind, value)}, found {token}")
        self._pop()

    def _parse_or(self):
        nodes = [self._parse_and()]
        while self._peek_word() == "or":
            self._pop()
            nodes.append(self._parse_and())
        return _flatten("or", nodes)

    def _parse_and(self):
        nodes = [self._parse_not()]
        while self._peek_word() == "and":
            self._pop()
            nodes.append(self._parse_not())
        return _flatten("and", nodes)

    def _parse_not(self):
        if self._peek_word() != "not":
            return self._parse_pred()
        self._pop()
        node = self._parse_not()
        if isinstance(node, tuple) and node and node[0] == "in":
            return ("not_in", node[1], node[2])
        if isinstance(node, tuple) and node and node[0] == "not_in":
            return ("in", node[1], node[2])
        return ("not", node)

    def _parse_pred(self):
        left = self._parse_primary()
        if self._peek_word() == "is":
            self._pop()
            negated = self._peek_word() == "not"
            if negated:
                self._pop()
            self._expect("word", "null")
            return ("is_not_null" if negated else "is_null", left)
        if self._peek_word() == "not" and self._word_at(1) == "in":
            self._pop()
            self._pop()
            return ("not_in", left, self._parse_parenthesized_list())
        if self._peek_word() == "in":
            self._pop()
            return ("in", left, self._parse_parenthesized_list())
        if self._peek_word() == "between":
            self._pop()
            low = self._parse_primary()
            self._expect("word", "and")
            high = self._parse_primary()
            return ("and", (("cmp", ">=", left, low), ("cmp", "<=", left, high)))
        token = self._peek()
        if token and token[0] == "op":
            op = self._pop()[1]
            if op == "=" and self._peek_word() == "any":
                self._pop()
                return ("in", left, self._parse_wrapped_array())
            if op == "<>" and self._peek_word() == "all":
                self._pop()
                return ("not_in", left, self._parse_wrapped_array())
            return ("cmp", op, left, self._parse_primary())
        return left

    def _word_at(self, offset: int) -> str | None:
        position = self.index + offset
        if position >= len(self.tokens):
            return None
        token = self.tokens[position]
        if token[0] == "word":
            return str(token[1])
        return None

    def _parse_primary(self):
        token = self._peek()
        if token == ("punct", "("):
            self._pop()
            node = self._parse_or()
            self._expect("punct", ")")
            return node
        if token is None:
            raise ValueError("unexpected end of check")
        if token[0] in {"lit", "word"}:
            self._pop()
            if token[0] == "lit":
                return ("lit", token[1])
            if self._peek() == ("punct", "("):
                self._pop()
                arguments = []
                if self._peek() != ("punct", ")"):
                    arguments.append(self._parse_or())
                    while self._peek() == ("punct", ","):
                        self._pop()
                        arguments.append(self._parse_or())
                self._expect("punct", ")")
                return ("call", token[1], tuple(arguments))
            return ("ident", token[1])
        raise ValueError(f"unexpected check token {token}")

    def _parse_parenthesized_list(self):
        self._expect("punct", "(")
        values = self._parse_value_list(")")
        self._expect("punct", ")")
        return tuple(sorted(values, key=repr))

    def _parse_wrapped_array(self):
        opened = 0
        while self._peek() == ("punct", "("):
            self._pop()
            opened += 1
        self._expect("word", "array")
        self._expect("punct", "[")
        values = [] if self._peek() == ("punct", "]") else self._parse_value_list("]")
        self._expect("punct", "]")
        for _ in range(opened):
            self._expect("punct", ")")
        return tuple(sorted(values, key=repr))

    def _parse_value_list(self, terminator: str):
        values = [self._parse_primary()]
        while self._peek() == ("punct", ","):
            self._pop()
            values.append(self._parse_primary())
        if self._peek() != ("punct", terminator):
            raise ValueError(f"expected {terminator}, found {self._peek()}")
        return values


def _flatten(kind: str, nodes: list):
    if len(nodes) == 1:
        return nodes[0]
    flat = []
    for node in nodes:
        if isinstance(node, tuple) and node and node[0] == kind:
            flat.extend(node[1])
        else:
            flat.append(node)
    return (kind, tuple(flat))


def _canonical_check(sql: str):
    prepared = _prepare_check_sql(sql)
    if not prepared:
        raise ValueError("empty check")
    return _CheckParser(prepared).parse()


def check_expressions_equivalent(expected: str, actual: str) -> bool:
    """True when two check texts are the same predicate, including PG deparsing."""

    try:
        return _canonical_check(expected) == _canonical_check(actual)
    except ValueError:
        return False


def check_catalog_problems(
    table: str,
    found: dict[str, str],
    validated: dict[str, bool],
    expected: dict[str, str],
) -> list[str]:
    problems = []
    for name, expression in expected.items():
        definition = found.get(name, "")
        if not definition:
            problems.append(f"check {table}.{name}")
            continue
        if validated.get(name) is False:
            problems.append(f"check {table}.{name} is not validated")
        if not check_expressions_equivalent(expression, definition):
            problems.append(f"check {table}.{name} expression drifted")
    return problems


# pg_trigger.tgtype bits from PostgreSQL: ROW, BEFORE, INSERT, DELETE, UPDATE, TRUNCATE, INSTEAD.
_TG_ROW = 1 << 0
_TG_BEFORE = 1 << 1
_TG_INSERT = 1 << 2
_TG_DELETE = 1 << 3
_TG_UPDATE = 1 << 4
_TG_TRUNCATE = 1 << 5
_TG_INSTEAD = 1 << 6
_GUARD_TRIGGER_EVENTS = frozenset({"INSERT", "UPDATE", "DELETE"})


def _decode_trigger_tgtype(tgtype: int) -> tuple[str, str, frozenset[str]]:
    events = frozenset(
        name
        for bit, name in (
            (_TG_INSERT, "INSERT"),
            (_TG_DELETE, "DELETE"),
            (_TG_UPDATE, "UPDATE"),
            (_TG_TRUNCATE, "TRUNCATE"),
        )
        if tgtype & bit
    )
    if tgtype & _TG_INSTEAD:
        timing = "INSTEAD OF"
    elif tgtype & _TG_BEFORE:
        timing = "BEFORE"
    else:
        timing = "AFTER"
    granularity = "ROW" if tgtype & _TG_ROW else "STATEMENT"
    return timing, granularity, events


def guard_trigger_problems(found: dict[str, tuple]) -> list[str]:
    """Require each PostgreSQL guard trigger's catalog identity, not its name alone.

    Each value is ``(table, function_schema, function, enabled, timing,
    granularity, events, when_predicate)``. ``enabled`` is ``O`` or ``A``.
    Replica-only ``R`` is disabled for a normal session. ``when_predicate``
    is ``None`` only when ``tgqual`` is null. Events are the exact set.
    """

    problems = []
    for name, table, function in _GUARD_TRIGGER_CONTRACT:
        actual = found.get(name)
        if actual is None:
            problems.append(f"guard trigger {name} is missing")
            continue
        (
            actual_table,
            function_schema,
            actual_function,
            enabled,
            timing,
            granularity,
            events,
            when_predicate,
        ) = actual
        if actual_table != table:
            problems.append(f"guard trigger {name} is on {actual_table}, expected {table}")
        if actual_function != function:
            problems.append(
                f"guard trigger {name} calls {actual_function}, expected {function}"
            )
        if function_schema != "public":
            problems.append(
                f"guard trigger {name} function schema is {function_schema}, expected public"
            )
        if enabled is not None and enabled not in {"O", "A"}:
            problems.append(f"guard trigger {name} is disabled")
        if timing != "BEFORE":
            problems.append(f"guard trigger {name} timing is {timing}, expected BEFORE")
        if granularity != "ROW":
            problems.append(f"guard trigger {name} granularity is {granularity}, expected ROW")
        if frozenset(events) != _GUARD_TRIGGER_EVENTS:
            problems.append(
                f"guard trigger {name} events are {tuple(sorted(events))}, "
                "expected INSERT, UPDATE, DELETE"
            )
        if when_predicate is not None:
            problems.append(f"guard trigger {name} has a WHEN predicate")
    return problems


def index_identity_problems(
    table: str,
    name: str,
    sql: str,
    columns: tuple[str, ...],
    unique: bool,
    predicate: str | None,
) -> list[str]:
    if not (sql or "").strip():
        return [f"index {table}.{name} definition missing"]
    try:
        found_columns, found_unique, found_predicate = _parse_index_identity(sql)
        expected_predicate = _canonical_check(predicate) if predicate else None
    except ValueError:
        return [f"index {table}.{name} predicate drifted"]
    problems = []
    if found_columns != columns:
        problems.append(
            f"index {table}.{name} keys are {found_columns or 'missing'}, expected {columns}"
        )
    if found_unique != unique:
        problems.append(f"index {table}.{name} unique is {found_unique}, expected {unique}")
    if found_predicate != expected_predicate:
        problems.append(f"index {table}.{name} predicate drifted")
    return problems


def _parse_index_identity(sql: str):
    prepared = _prepare_check_sql(sql)
    prepared = re.sub(r"\busing\s+btree\b", "", prepared, flags=re.IGNORECASE)
    unique = re.search(r"\bunique\b", prepared, flags=re.IGNORECASE) is not None
    where_match = re.search(r"\bwhere\b", prepared, flags=re.IGNORECASE)
    head = prepared[: where_match.start()] if where_match else prepared
    predicate_sql = prepared[where_match.end():].strip() if where_match else ""
    groups = list(re.finditer(r"\(([^()]*)\)", head))
    if not groups:
        raise ValueError("index has no key list")
    columns = []
    for part in groups[-1].group(1).split(","):
        token = part.strip().casefold().split()
        if token:
            columns.append(token[0])
    predicate = _canonical_check(predicate_sql) if predicate_sql else None
    return tuple(columns), unique, predicate


def _foreign_key_identity_problems(
    table: str,
    found: dict,
    expected: dict,
    *,
    referred_schema: str = "public",
) -> list[str]:
    """Compare schema, column order, delete action, and PostgreSQL validity.

    ``found`` values are ``(schema, table, columns, action, validated)``.
    SQLite records schema ``main`` and validated ``True`` because it has no
    ``NOT VALID`` foreign keys.
    """

    problems = []
    for columns, spec in expected.items():
        key = columns if isinstance(columns, tuple) else (columns,)
        referred, referred_columns, action = spec
        actual = found.get(key)
        expected_identity = (referred_schema, referred, referred_columns, action, True)
        if actual != expected_identity:
            problems.append(
                f"foreign key {table}.{','.join(key)} is {actual or 'missing'}, "
                f"expected {expected_identity}"
            )
    return problems


def _table_exists(connection, table: str) -> bool:
    return inspect(connection).has_table(table)


def _column_names(connection, table: str) -> list[str]:
    return [column["name"] for column in inspect(connection).get_columns(table)]


def _execute(connection, statement: str, params: dict | None = None):
    return connection.execute(text(statement), params or {})


def processing_job_kind_definition(connection) -> str:
    if connection.dialect.name == "postgresql":
        row = _execute(
            connection,
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conname = 'ck_processing_job_kind'
              AND conrelid = 'public.processing_jobs'::regclass
            """,
        ).scalar()
        return row or ""
    if connection.dialect.name == "sqlite":
        row = _execute(
            connection,
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'processing_jobs'",
        ).scalar()
        return row or ""
    raise RuntimeError(f"Unsupported dialect {connection.dialect.name}.")


def apply_foundation_downgrade_blockers(connection) -> dict[str, int]:
    """Read-only counts. Downgrade raises on any non-zero value before DDL."""

    required = (
        (JOB_TABLE, "claim_epoch"),
        (CONTROL_TABLE, "job_id"),
        (STAGE_TABLE, "job_id"),
        (OUTBOX_TABLE, "id"),
    )
    for table, column in required:
        columns = set(_column_names(connection, table))
        if column not in columns:
            raise RuntimeError(
                "Evaluation apply foundation is not installed; refusing to invent "
                f"a downgrade path for {table}.{column}."
            )
    return {
        "evaluation_apply_jobs": int(
            _execute(
                connection,
                "SELECT COUNT(*) FROM processing_jobs WHERE kind = 'evaluation_apply'",
            ).scalar()
            or 0
        ),
        "advanced_claim_epochs": int(
            _execute(
                connection,
                """
                SELECT COUNT(*) FROM processing_jobs
                WHERE claim_epoch IS NOT NULL AND claim_epoch <> 0
                """,
            ).scalar()
            or 0
        ),
        "controls": int(_execute(connection, f"SELECT COUNT(*) FROM {CONTROL_TABLE}").scalar() or 0),
        "stage_rows": int(_execute(connection, f"SELECT COUNT(*) FROM {STAGE_TABLE}").scalar() or 0),
        "outbox_rows": int(_execute(connection, f"SELECT COUNT(*) FROM {OUTBOX_TABLE}").scalar() or 0),
    }


def upgrade_apply_foundation(connection) -> None:
    _widen_processing_jobs(connection)
    _create_foundation_tables(connection)
    install_apply_foundation_guards(connection)


def downgrade_apply_foundation(connection) -> None:
    blockers = apply_foundation_downgrade_blockers(connection)
    populated = {key: value for key, value in blockers.items() if value}
    if populated:
        raise RuntimeError(
            "Refusing populated evaluation apply downgrade before any schema change: "
            f"{populated}"
        )
    remove_apply_foundation_guards(connection)
    for table in (OUTBOX_TABLE, STAGE_TABLE, CONTROL_TABLE):
        _execute(connection, f"DROP TABLE IF EXISTS {table}")
    _restore_processing_jobs(connection)


def _create_foundation_tables(connection) -> None:
    from models.models import (  # late import: models imports this module
        CacheInvalidationOutbox,
        EvaluationApplyControl,
        EvaluationApplyStageRow,
    )

    for table in (
        EvaluationApplyControl.__table__,
        EvaluationApplyStageRow.__table__,
        CacheInvalidationOutbox.__table__,
    ):
        if _table_exists(connection, table.name):
            raise RuntimeError(
                f"{table.name} already exists; refusing to recreate an existing "
                "evaluation apply table."
            )
        _create_table_skipping_unready_foreign_keys(connection, table)


def _create_table_skipping_unready_foreign_keys(connection, table) -> None:
    """Create ``table``; omit FKs whose referenced key is missing (with a warning)."""
    from sqlalchemy.schema import CreateIndex, CreateTable

    from utils.schema_key_guards import fk_target_ready

    unready = [
        fk
        for fk in table.foreign_key_constraints
        if not fk_target_ready(
            connection,
            fk.referred_table.name,
            tuple(element.column.name for element in fk.elements),
            f"{table.name}({', '.join(fk.column_keys)})",
        )
    ]
    if not unready:
        table.create(bind=connection, checkfirst=False)
        return
    keep = [fk for fk in table.foreign_key_constraints if fk not in unready]
    connection.execute(CreateTable(table, include_foreign_key_constraints=keep))
    for index in table.indexes:
        connection.execute(CreateIndex(index))


def _widen_processing_jobs(connection) -> None:
    if connection.dialect.name == "postgresql":
        _widen_processing_jobs_postgres(connection)
        return
    if connection.dialect.name == "sqlite":
        _widen_processing_jobs_sqlite(connection)
        return
    raise RuntimeError(f"Evaluation apply foundation is not implemented for {connection.dialect.name}.")


def _widen_processing_jobs_postgres(connection) -> None:
    definition = processing_job_kind_definition(connection)
    if not definition:
        raise RuntimeError(
            "ck_processing_job_kind is missing; refusing to invent a processing job kind check."
        )
    normalized = _normalize_sql(definition)
    for kind in PRIOR_JOB_KINDS:
        if f"'{kind}'" not in normalized:
            raise RuntimeError(
                "ck_processing_job_kind does not contain the existing job kinds; "
                "refusing to replace it."
            )
    _execute(
        connection,
        "ALTER TABLE processing_jobs ADD COLUMN IF NOT EXISTS claim_epoch integer NULL DEFAULT 0",
    )
    _execute(connection, "ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS ck_processing_job_kind")
    _execute(
        connection,
        f"ALTER TABLE processing_jobs ADD CONSTRAINT ck_processing_job_kind CHECK ({KIND_CHECK_SQL})",
    )
    _execute(
        connection,
        "ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS ck_processing_job_claim_epoch",
    )
    _execute(
        connection,
        "ALTER TABLE processing_jobs ADD CONSTRAINT ck_processing_job_claim_epoch "
        f"CHECK ({CLAIM_EPOCH_CHECK_SQL})",
    )


def _sqlite_job_names(connection) -> list[str]:
    return [row[1] for row in _execute(connection, "PRAGMA table_info(processing_jobs)")]


def _widen_processing_jobs_sqlite(connection) -> None:
    names = _sqlite_job_names(connection)
    expected = list(PROCESSING_JOB_COLUMNS_BEFORE)
    if names == expected + ["claim_epoch"]:
        definition = _normalize_sql(processing_job_kind_definition(connection))
        if "evaluation_apply" not in definition or "ck_processing_job_claim_epoch" not in definition:
            raise RuntimeError(
                "processing_jobs already has claim_epoch but the kind checks do not match "
                "the foundation; refusing to rebuild them."
            )
        return
    if names != expected:
        raise RuntimeError(
            "Refusing to rebuild processing_jobs with unexpected columns: "
            f"{names}"
        )
    _sqlite_replace_processing_jobs(connection, foundation=True)


def _restore_processing_jobs(connection) -> None:
    if connection.dialect.name == "postgresql":
        definition = processing_job_kind_definition(connection)
        if not definition:
            raise RuntimeError("ck_processing_job_kind is missing during downgrade.")
        _execute(connection, "ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS ck_processing_job_kind")
        _execute(
            connection,
            "ALTER TABLE processing_jobs ADD CONSTRAINT ck_processing_job_kind "
            f"CHECK ({PRIOR_KIND_CHECK_SQL})",
        )
        _execute(
            connection,
            "ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS ck_processing_job_claim_epoch",
        )
        _execute(connection, "ALTER TABLE processing_jobs DROP COLUMN IF EXISTS claim_epoch")
        return
    if connection.dialect.name != "sqlite":
        raise RuntimeError(f"Unsupported dialect {connection.dialect.name}.")
    names = _sqlite_job_names(connection)
    if set(names) != set(PROCESSING_JOB_COLUMNS_BEFORE) | {"claim_epoch"}:
        raise RuntimeError(
            "Refusing to restore processing_jobs from an unexpected column set: "
            f"{names}"
        )
    _sqlite_replace_processing_jobs(connection, foundation=False)


def _sqlite_replace_processing_jobs(connection, *, foundation: bool) -> None:
    temporary = "processing_jobs__apply_foundation_new"
    _execute(connection, f"DROP TABLE IF EXISTS {temporary}")
    _execute(connection, _sqlite_processing_job_ddl(temporary, foundation=foundation))
    destination = list(PROCESSING_JOB_COLUMNS_BEFORE)
    source = list(PROCESSING_JOB_COLUMNS_BEFORE)
    if foundation:
        destination.append("claim_epoch")
        select_list = ", ".join(source + ["0"])
    else:
        select_list = ", ".join(source)
    _execute(
        connection,
        f"INSERT INTO {temporary} ({', '.join(destination)}) "
        f"SELECT {select_list} FROM processing_jobs",
    )
    _execute(connection, "DROP TABLE processing_jobs")
    _execute(connection, f"ALTER TABLE {temporary} RENAME TO processing_jobs")
    _execute(
        connection,
        "CREATE INDEX IF NOT EXISTS idx_processing_job_claim "
        "ON processing_jobs (status, available_at, created_at)",
    )
    _execute(
        connection,
        "CREATE INDEX IF NOT EXISTS idx_processing_job_requester "
        "ON processing_jobs (requested_by_user_id, created_at)",
    )


def sqlite_prior_processing_job_ddl() -> str:
    """Old processing_jobs shape used by the in-memory upgrade probe."""

    return _sqlite_processing_job_ddl("processing_jobs", foundation=False)


def _sqlite_processing_job_ddl(table: str, *, foundation: bool) -> str:
    kind_sql = KIND_CHECK_SQL if foundation else PRIOR_KIND_CHECK_SQL
    epoch_column = "    claim_epoch INTEGER NULL DEFAULT 0,\n" if foundation else ""
    epoch_check = (
        f"    CONSTRAINT ck_processing_job_claim_epoch CHECK ({CLAIM_EPOCH_CHECK_SQL}),\n"
        if foundation
        else ""
    )
    return f"""
    CREATE TABLE {table} (
        id CHAR(32) NOT NULL PRIMARY KEY,
        kind VARCHAR(40) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'queued',
        requested_by_user_id CHAR(32),
        requested_by_name VARCHAR(255),
        request_json TEXT NOT NULL,
        input_path VARCHAR(500),
        progress SMALLINT NOT NULL DEFAULT 0,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        max_attempts INTEGER NOT NULL DEFAULT 3,
        available_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        worker_id VARCHAR(150),
        lease_expires_at DATETIME,
        heartbeat_at DATETIME,
        started_at DATETIME,
        finished_at DATETIME,
        result_type VARCHAR(60),
        result_id VARCHAR(100),
        result_json TEXT,
        error_code VARCHAR(80),
        safe_error_message TEXT,
        idempotency_key VARCHAR(255),
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        {epoch_column.rstrip()}
        CONSTRAINT uq_processing_job_idempotency UNIQUE (kind, idempotency_key),
        CONSTRAINT ck_processing_job_kind CHECK ({kind_sql}),
        CONSTRAINT ck_processing_job_status CHECK (
            status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')
        ),
        {epoch_check.rstrip()}
        CONSTRAINT ck_processing_job_progress CHECK (progress >= 0 AND progress <= 100),
        CONSTRAINT ck_processing_job_attempts CHECK (attempt_count >= 0),
        CONSTRAINT ck_processing_job_max_attempts CHECK (max_attempts >= 1),
        FOREIGN KEY(requested_by_user_id) REFERENCES users(id) ON DELETE SET NULL
    )
    """


def missing_apply_foundation_objects(connection) -> list[str]:
    dialect = connection.dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        return [f"unsupported dialect {dialect}"]
    missing: list[str] = []
    for table, columns in (
        (CONTROL_TABLE, CONTROL_COLUMNS),
        (STAGE_TABLE, STAGE_COLUMNS),
        (OUTBOX_TABLE, OUTBOX_COLUMNS),
    ):
        if not _table_exists(connection, table):
            missing.append(f"table {table}")
            continue
        found = set(_column_names(connection, table))
        expected = set(columns)
        for column in sorted(expected - found):
            missing.append(f"column {table}.{column}")
        for column in sorted(found - expected):
            missing.append(f"unexpected column {table}.{column}")
        for column in sorted(found & POPULATION_COLUMNS):
            missing.append(f"forbidden column {table}.{column}")
    if _table_exists(connection, JOB_TABLE):
        if "claim_epoch" not in set(_column_names(connection, JOB_TABLE)):
            missing.append("column processing_jobs.claim_epoch")
        missing.extend(_missing_checks(connection, JOB_TABLE, JOB_FOUNDATION_CHECKS))
    else:
        missing.append("table processing_jobs")

    missing.extend(_missing_checks(connection, CONTROL_TABLE, CONTROL_CHECKS))
    missing.extend(_missing_checks(connection, STAGE_TABLE, STAGE_CHECKS))
    missing.extend(_missing_checks(connection, OUTBOX_TABLE, OUTBOX_CHECKS))
    missing.extend(_missing_indexes(connection, CONTROL_TABLE, CONTROL_INDEXES))
    missing.extend(_missing_indexes(connection, STAGE_TABLE, STAGE_INDEXES))
    missing.extend(_missing_indexes(connection, OUTBOX_TABLE, OUTBOX_INDEXES))
    missing.extend(_missing_index_identities(connection))
    missing.extend(_missing_foreign_keys(connection, CONTROL_TABLE, CONTROL_FOREIGN_KEYS))
    missing.extend(_missing_foreign_keys(connection, STAGE_TABLE, STAGE_FOREIGN_KEYS))
    missing.extend(_missing_foreign_keys(connection, OUTBOX_TABLE, OUTBOX_FOREIGN_KEYS))
    missing.extend(_missing_guard_triggers(connection))
    missing.extend(_missing_guard_snippets(connection))
    return missing


def _missing_checks(connection, table: str, expected: dict[str, str]) -> list[str]:
    if not _table_exists(connection, table):
        return []
    return check_catalog_problems(
        table,
        _check_sql(connection, table),
        _check_validated(connection, table),
        expected,
    )


def _present_index_names(connection, table: str) -> set[str]:
    """Index names plus named UNIQUE constraints.

    SQLite stores a named UNIQUE table constraint as ``sqlite_autoindex_*``.
    The CREATE TABLE text still carries the constraint name, which is the
    contract shared with PostgreSQL.
    """

    inspector = inspect(connection)
    names = {index["name"] for index in inspector.get_indexes(table)}
    names.update(
        item["name"]
        for item in inspector.get_unique_constraints(table)
        if item.get("name")
    )
    if connection.dialect.name == "sqlite":
        sql = _execute(
            connection,
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :table",
            {"table": table},
        ).scalar() or ""
        for name in (*CONTROL_INDEXES, *STAGE_INDEXES, *OUTBOX_INDEXES):
            if name in sql:
                names.add(name)
    return names


def _missing_indexes(connection, table: str, names: tuple[str, ...]) -> list[str]:
    if not _table_exists(connection, table):
        return []
    found_names = _present_index_names(connection, table)
    return [f"index {table}.{name}" for name in names if name not in found_names]


def _missing_index_identities(connection) -> list[str]:
    problems = []
    for table, name, columns, unique, predicate in _INDEX_CONTRACTS:
        if not _table_exists(connection, table):
            continue
        sql = _index_sql(connection, table, name)
        if not sql and connection.dialect.name == "sqlite":
            sql = _sqlite_unique_constraint_sql(connection, table, name)
        problems.extend(index_identity_problems(table, name, sql, columns, unique, predicate))
    return problems


def _sqlite_unique_constraint_sql(connection, table: str, name: str) -> str:
    sql = _execute(
        connection,
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :table",
        {"table": table},
    ).scalar() or ""
    match = re.search(
        rf"CONSTRAINT\s+{re.escape(name)}\s+UNIQUE\s*\([^)]*\)",
        sql,
        flags=re.IGNORECASE,
    )
    return match.group(0) if match else ""


def _missing_foreign_keys(connection, table: str, expected: dict) -> list[str]:
    if not _table_exists(connection, table):
        return []
    referred_schema = "public" if connection.dialect.name == "postgresql" else "main"
    return _foreign_key_identity_problems(
        table,
        _foreign_key_actions(connection, table),
        expected,
        referred_schema=referred_schema,
    )


def _missing_guard_snippets(connection) -> list[str]:
    body = _guard_sql(connection)
    normalized = _normalize_sql(body)
    return [f"guard missing {snippet}" for snippet in GUARD_SNIPPETS if snippet not in normalized]


def _missing_guard_triggers(connection) -> list[str]:
    if connection.dialect.name == "postgresql":
        rows = _execute(
            connection,
            """
            SELECT t.tgname, c.relname, fn.nspname, p.proname, t.tgenabled::text,
                   t.tgtype, t.tgqual IS NULL
            FROM pg_trigger t
            JOIN pg_class c ON c.oid = t.tgrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_proc p ON p.oid = t.tgfoid
            JOIN pg_namespace fn ON fn.oid = p.pronamespace
            WHERE n.nspname = 'public' AND NOT t.tgisinternal
            """,
        )
        found = {}
        for name, relname, function_schema, function_name, enabled, tgtype, unconditional in rows:
            timing, granularity, events = _decode_trigger_tgtype(int(tgtype))
            found[name] = (
                relname,
                function_schema,
                function_name,
                enabled,
                timing,
                granularity,
                events,
                None if unconditional else "present",
            )
        return guard_trigger_problems(found)
    if connection.dialect.name != "sqlite":
        return []
    rows = _execute(
        connection,
        "SELECT name, tbl_name FROM sqlite_master WHERE type = 'trigger'",
    )
    found = {row[0]: row[1] for row in rows}
    problems = []
    for name, table in _sqlite_trigger_targets().items():
        actual = found.get(name)
        if actual is None:
            problems.append(f"guard trigger {name} is missing")
        elif actual != table:
            problems.append(f"guard trigger {name} is on {actual}, expected {table}")
    return problems


def _sqlite_trigger_targets() -> dict[str, str]:
    targets = {}
    for statement in _sqlite_guard_statements():
        match = _TRIGGER_HEAD_RE.search(statement)
        if match:
            targets[match.group(1)] = match.group(2)
    return targets


def _check_validated(connection, table: str) -> dict[str, bool]:
    if connection.dialect.name != "postgresql":
        return {}
    rows = _execute(
        connection,
        """
        SELECT con.conname AS name, con.convalidated AS validated
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        WHERE nsp.nspname = 'public' AND rel.relname = :table AND con.contype = 'c'
        """,
        {"table": table},
    )
    return {row[0]: bool(row[1]) for row in rows}


def _check_sql(connection, table: str) -> dict[str, str]:
    if connection.dialect.name == "postgresql":
        rows = _execute(
            connection,
            """
            SELECT con.conname AS name, pg_get_constraintdef(con.oid) AS definition
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            WHERE nsp.nspname = 'public' AND rel.relname = :table AND con.contype = 'c'
            """,
            {"table": table},
        )
        return {row[0]: row[1] for row in rows}
    row = _execute(
        connection,
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :table",
        {"table": table},
    ).scalar()
    return _sqlite_named_constraints(row or "")


def _sqlite_named_constraints(sql: str) -> dict[str, str]:
    """Pair each named CHECK with its own body.

    A UNIQUE or FOREIGN KEY constraint also starts with CONSTRAINT. Searching
    forward from that keyword would steal the next CHECK and hide its name.
    """

    found = {}
    for match in re.finditer(r"CONSTRAINT\s+(\w+)\s+CHECK\s*\(", sql, flags=re.IGNORECASE):
        name = match.group(1)
        paren = match.end() - 1
        depth = 0
        end = paren
        for index, char in enumerate(sql[paren:], start=paren):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = index
                    break
        found[name] = sql[paren + 1:end]
    return found


def _foreign_key_actions(connection, table: str) -> dict[tuple[str, ...], tuple]:
    grouped: dict[tuple[str, ...], tuple] = {}
    if connection.dialect.name == "sqlite":
        rows = list(_execute(connection, f"PRAGMA foreign_key_list({table})"))
        buckets: dict[int, list] = {}
        for row in rows:
            buckets.setdefault(row[0], []).append(row)
        for bucket in buckets.values():
            bucket.sort(key=lambda item: item[1])
            columns = tuple(item[3] for item in bucket)
            referred_columns = tuple(item[4] for item in bucket)
            grouped[columns] = (
                "main",
                bucket[0][2],
                referred_columns,
                str(bucket[0][6]).upper(),
                True,
            )
        return grouped
    rows = _execute(
        connection,
        """
        SELECT att.attname, refatt.attname, refnsp.nspname, confrel.relname,
               con.confdeltype, con.convalidated, con.oid, cols.ord
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_class confrel ON confrel.oid = con.confrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        JOIN pg_namespace refnsp ON refnsp.oid = confrel.relnamespace
        CROSS JOIN LATERAL unnest(con.conkey, con.confkey)
            WITH ORDINALITY AS cols(attnum, refnum, ord)
        JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = cols.attnum
        JOIN pg_attribute refatt
          ON refatt.attrelid = confrel.oid AND refatt.attnum = cols.refnum
        WHERE nsp.nspname = 'public' AND rel.relname = :table AND con.contype = 'f'
        ORDER BY con.oid, cols.ord
        """,
        {"table": table},
    )
    actions = {"a": "NO ACTION", "r": "RESTRICT", "c": "CASCADE", "n": "SET NULL", "d": "SET DEFAULT"}
    buckets: dict[int, list] = {}
    for column_name, referred_column, referred_schema, referred, action, validated, oid, _ord in rows:
        buckets.setdefault(oid, []).append(
            (
                column_name,
                referred_column,
                referred_schema,
                referred,
                actions.get(action, action),
                bool(validated),
            )
        )
    for bucket in buckets.values():
        grouped[tuple(item[0] for item in bucket)] = (
            bucket[0][2],
            bucket[0][3],
            tuple(item[1] for item in bucket),
            bucket[0][4],
            bucket[0][5],
        )
    return grouped


def _index_sql(connection, table: str, name: str) -> str:
    if connection.dialect.name == "postgresql":
        row = _execute(
            connection,
            """
            SELECT indexdef FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = :table AND indexname = :name
            """,
            {"table": table, "name": name},
        ).scalar()
        return row or ""
    row = _execute(
        connection,
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = :name",
        {"name": name},
    ).scalar()
    return row or ""


def _guard_sql(connection) -> str:
    if connection.dialect.name == "postgresql":
        rows = _execute(
            connection,
            """
            SELECT pg_get_functiondef(pg_proc.oid)
            FROM pg_proc
            JOIN pg_namespace ON pg_namespace.oid = pg_proc.pronamespace
            WHERE pg_namespace.nspname = 'public'
              AND pg_proc.proname IN (
                  'guard_evaluation_apply_control',
                  'guard_evaluation_apply_stage_row',
                  'guard_cache_invalidation_outbox',
                  'guard_processing_job_apply_foundation',
                  'guard_evaluation_scope_apply_foundation',
                  'guard_performance_record_apply_foundation'
              )
            """
        )
        return "\n".join(row[0] for row in rows if row[0])
    rows = _execute(
        connection,
        """
        SELECT sql FROM sqlite_master
        WHERE type = 'trigger'
          AND (
              name LIKE 'trg_%apply%'
              OR name LIKE 'trg_cache_invalidation_outbox%'
          )
        """,
    )
    return "\n".join(row[0] for row in rows if row[0])


def _postgres_constraint_exists(connection, table: str, name: str) -> bool:
    return bool(
        _execute(
            connection,
            """
            SELECT 1
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            WHERE nsp.nspname = 'public' AND rel.relname = :table AND con.conname = :name
            """,
            {"table": table, "name": name},
        ).scalar()
    )


def install_apply_foundation_guards(connection) -> None:
    if not all(_table_exists(connection, table) for table in FOUNDATION_TABLES):
        return
    for parent in (
        JOB_TABLE,
        "evaluation_scopes",
        "performance_records",
        "evaluation_revisions",
        "team_configuration_versions",
        "teams",
        "users",
    ):
        if not _table_exists(connection, parent):
            raise RuntimeError(
                f"Cannot install evaluation apply guards without {parent}."
            )
    if connection.dialect.name == "postgresql":
        for statement in _postgres_guard_statements():
            _execute(connection, statement)
        return
    if connection.dialect.name == "sqlite":
        for statement in _sqlite_guard_statements():
            _execute(connection, statement)
        return
    raise RuntimeError(f"Evaluation apply guards are not implemented for {connection.dialect.name}.")


def remove_apply_foundation_guards(connection) -> None:
    if connection.dialect.name == "postgresql":
        for name, table in _postgres_trigger_targets():
            _execute(connection, f"DROP TRIGGER IF EXISTS {name} ON {table}")
        for name in (
            "guard_evaluation_apply_control",
            "guard_evaluation_apply_stage_row",
            "guard_cache_invalidation_outbox",
            "guard_processing_job_apply_foundation",
            "guard_evaluation_scope_apply_foundation",
            "guard_performance_record_apply_foundation",
        ):
            _execute(connection, f"DROP FUNCTION IF EXISTS {name}()")
        return
    if connection.dialect.name == "sqlite":
        for name in _sqlite_trigger_names():
            _execute(connection, f"DROP TRIGGER IF EXISTS {name}")


def _postgres_trigger_targets() -> tuple[tuple[str, str], ...]:
    return (
        ("trg_evaluation_apply_control_guard", CONTROL_TABLE),
        ("trg_evaluation_apply_stage_guard", STAGE_TABLE),
        ("trg_cache_invalidation_outbox_guard", OUTBOX_TABLE),
        ("trg_processing_job_apply_foundation", JOB_TABLE),
        ("trg_evaluation_scope_apply_foundation", "evaluation_scopes"),
        ("trg_performance_record_apply_foundation", "performance_records"),
    )


def _postgres_guard_statements() -> list[str]:
    month_case = _month_name_case("control_month")
    statements = [
        f"""
        CREATE OR REPLACE FUNCTION guard_evaluation_apply_control() RETURNS trigger
        LANGUAGE plpgsql AS $guard$
        DECLARE
            scope_team uuid;
            scope_level text;
            scope_position text;
            version_team uuid;
            job_epoch integer;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.state IS DISTINCT FROM 'pending'
                   OR OLD.promoted_revision_id IS NOT NULL
                   OR EXISTS (SELECT 1 FROM evaluation_apply_stage_rows WHERE job_id = OLD.job_id)
                   OR EXISTS (SELECT 1 FROM cache_invalidation_outbox WHERE job_id = OLD.job_id)
                THEN
                    RAISE EXCEPTION 'evaluation apply evidence cannot be deleted';
                END IF;
                RETURN OLD;
            END IF;

            IF COALESCE(NEW.actor_snapshot->>'state', '') IS DISTINCT FROM 'known'
               OR COALESCE(NEW.actor_snapshot->>'user_id', '') = ''
               OR (
                    NEW.requested_by_user_id IS NOT NULL
                    AND replace(NEW.actor_snapshot->>'user_id', '-', '')
                        IS DISTINCT FROM replace(NEW.requested_by_user_id::text, '-', '')
               )
            THEN
                RAISE EXCEPTION 'evaluation apply actor snapshot must record a known user';
            END IF;
            IF NEW.rules_checksum !~ '^[0-9a-f]{{64}}$'
               OR NEW.proof_source_fingerprint !~ '^[0-9a-f]{{64}}$'
               OR NEW.lineage_fingerprint !~ '^[0-9a-f]{{64}}$'
            THEN
                RAISE EXCEPTION 'evaluation apply fingerprints must be lowercase sha256';
            END IF;

            IF TG_OP = 'INSERT' THEN
                -- {_LOCK_ORDER_SQL}
                -- team_configuration_versions is read after the job and scope locks.
                -- It is not part of the row-lock order.
                SELECT claim_epoch INTO job_epoch
                  FROM processing_jobs
                 WHERE id = NEW.job_id
                   FOR UPDATE;
                SELECT team_id, performance_level, position_name
                  INTO scope_team, scope_level, scope_position
                  FROM evaluation_scopes
                 WHERE id = NEW.scope_id
                   FOR UPDATE;
                IF NOT FOUND
                   OR scope_team IS DISTINCT FROM NEW.team_id
                   OR scope_level IS DISTINCT FROM NEW.performance_level
                   OR scope_position IS DISTINCT FROM NEW.position_name
                THEN
                    RAISE EXCEPTION 'evaluation apply scope identity does not match the scope row';
                END IF;
                SELECT team_id INTO version_team
                  FROM team_configuration_versions WHERE id = NEW.version_id;
                IF NOT FOUND OR version_team IS DISTINCT FROM NEW.team_id THEN
                    RAISE EXCEPTION 'evaluation apply version team does not match the captured team';
                END IF;
                IF job_epoch IS DISTINCT FROM NEW.claim_epoch THEN
                    RAISE EXCEPTION 'evaluation apply claim epoch must match the processing job';
                END IF;
                IF NEW.state IS DISTINCT FROM 'pending'
                   OR NEW.staged_count <> 0
                   OR NEW.promoted_count <> 0
                   OR NEW.promoted_revision_id IS NOT NULL
                   OR NEW.stage_cursor IS NOT NULL
                   OR NEW.requested_by_user_id IS NULL
                THEN
                    RAISE EXCEPTION 'evaluation apply control must be captured pending';
                END IF;
                RETURN NEW;
            END IF;

            IF NEW.job_id IS DISTINCT FROM OLD.job_id
               OR NEW.scope_id IS DISTINCT FROM OLD.scope_id
               OR NEW.version_id IS DISTINCT FROM OLD.version_id
               OR NEW.team_id IS DISTINCT FROM OLD.team_id
               OR NEW.performance_level IS DISTINCT FROM OLD.performance_level
               OR NEW.position_name IS DISTINCT FROM OLD.position_name
               OR NEW.year IS DISTINCT FROM OLD.year
               OR NEW.month IS DISTINCT FROM OLD.month
               OR NEW.engine_version IS DISTINCT FROM OLD.engine_version
               OR NEW.rules_checksum IS DISTINCT FROM OLD.rules_checksum
               OR NEW.proof_source_fingerprint IS DISTINCT FROM OLD.proof_source_fingerprint
               OR NEW.lineage_fingerprint IS DISTINCT FROM OLD.lineage_fingerprint
               OR NEW.actor_snapshot IS DISTINCT FROM OLD.actor_snapshot
               OR NEW.created_at IS DISTINCT FROM OLD.created_at
            THEN
                RAISE EXCEPTION 'evaluation apply captured identity is immutable';
            END IF;
            IF NEW.requested_by_user_id IS DISTINCT FROM OLD.requested_by_user_id
               AND NEW.requested_by_user_id IS NOT NULL
            THEN
                RAISE EXCEPTION 'evaluation apply requester can only be cleared by audit deletion';
            END IF;
            IF NOT (
                (OLD.state = 'pending' AND NEW.state IN ('pending', 'staging', 'failed', 'cancelled'))
                OR (OLD.state = 'staging' AND NEW.state IN ('staging', 'promoting', 'failed', 'cancelled'))
                OR (OLD.state = 'promoting' AND NEW.state IN ('promoting', 'promoted', 'failed'))
                OR (OLD.state = 'promoted' AND NEW.state = 'promoted')
                OR (OLD.state = 'failed' AND NEW.state IN ('failed', 'pending'))
                OR (OLD.state = 'cancelled' AND NEW.state IN ('cancelled', 'pending'))
            ) THEN
                RAISE EXCEPTION 'illegal evaluation apply state transition';
            END IF;
            IF NEW.claim_epoch IS DISTINCT FROM OLD.claim_epoch
               AND NOT (
                    OLD.state IN ('failed', 'cancelled')
                    AND NEW.state = 'pending'
                    AND NEW.claim_epoch = OLD.claim_epoch + 1
               )
            THEN
                RAISE EXCEPTION 'evaluation apply claim epoch changes only on retry';
            END IF;
            IF OLD.state IN ('failed', 'cancelled') AND NEW.state = 'pending' THEN
                -- The reclaim statement already locked processing_jobs, then this control.
                -- Do not lock processing_jobs here; that inverts the lock order.
                SELECT claim_epoch INTO job_epoch FROM processing_jobs WHERE id = NEW.job_id;
                IF NEW.claim_epoch IS DISTINCT FROM OLD.claim_epoch + 1
                   OR NEW.staged_count <> 0
                   OR NEW.promoted_count <> 0
                   OR NEW.promoted_revision_id IS NOT NULL
                   OR NEW.stage_cursor IS NOT NULL
                   OR NEW.requested_by_user_id IS NULL
                   OR job_epoch IS DISTINCT FROM NEW.claim_epoch
                THEN
                    RAISE EXCEPTION 'evaluation apply retry must advance the epoch and clear progress';
                END IF;
            END IF;
            IF NEW.state IN ('pending', 'staging', 'promoting') AND NEW.requested_by_user_id IS NULL THEN
                RAISE EXCEPTION 'open evaluation apply cannot replay a missing requester';
            END IF;
            IF OLD.state = 'promoted' AND (
                NEW.state IS DISTINCT FROM OLD.state
                OR NEW.claim_epoch IS DISTINCT FROM OLD.claim_epoch
                OR NEW.staged_count IS DISTINCT FROM OLD.staged_count
                OR NEW.promoted_count IS DISTINCT FROM OLD.promoted_count
                OR NEW.promoted_revision_id IS DISTINCT FROM OLD.promoted_revision_id
                OR NEW.stage_cursor IS DISTINCT FROM OLD.stage_cursor
            ) THEN
                RAISE EXCEPTION 'promoted evaluation apply evidence is immutable';
            END IF;
            IF NEW.state = 'promoting'
               AND (NEW.promoted_revision_id IS NOT NULL OR NEW.promoted_count <> 0)
            THEN
                RAISE EXCEPTION 'promoting evaluation apply has not committed a revision';
            END IF;
            IF NEW.state = 'promoted' AND NEW.promoted_revision_id IS NULL THEN
                RAISE EXCEPTION 'promoted evaluation apply requires a revision';
            END IF;
            IF NEW.state IS DISTINCT FROM 'promoted'
               AND (NEW.promoted_revision_id IS NOT NULL OR NEW.promoted_count <> 0)
            THEN
                RAISE EXCEPTION 'only a promoted evaluation apply references a revision';
            END IF;
            IF NOT (OLD.state IN ('failed', 'cancelled') AND NEW.state = 'pending')
               AND NOT (OLD.state = 'staging' AND NEW.state = 'staging')
               AND NEW.staged_count IS DISTINCT FROM OLD.staged_count
            THEN
                RAISE EXCEPTION 'evaluation apply staged count is frozen outside staging';
            END IF;
            IF OLD.state = 'staging' AND NEW.state = 'staging' AND NEW.staged_count < OLD.staged_count THEN
                RAISE EXCEPTION 'evaluation apply staged count cannot decrease';
            END IF;
            IF NOT (OLD.state = 'staging' AND NEW.state = 'staging')
               AND NOT (OLD.state = 'pending' AND NEW.state = 'staging')
               AND NOT (OLD.state IN ('failed', 'cancelled') AND NEW.state = 'pending')
               AND NEW.stage_cursor IS DISTINCT FROM OLD.stage_cursor
            THEN
                RAISE EXCEPTION 'evaluation apply stage cursor is frozen';
            END IF;
            RETURN NEW;
        END;
        $guard$
        """,
        f"""
        CREATE OR REPLACE FUNCTION guard_evaluation_apply_stage_row() RETURNS trigger
        LANGUAGE plpgsql AS $guard$
        DECLARE
            control_state text;
            control_epoch integer;
            control_rules text;
            control_team uuid;
            control_level text;
            control_position text;
            control_year integer;
            control_month integer;
            job_epoch integer;
            record_team uuid;
            record_level text;
            record_position text;
            record_year integer;
            record_month text;
        BEGIN
            -- {_LOCK_ORDER_SQL}
            -- Stage validation locks the job, then the control, then the record
            -- before it trusts the epoch or the month. Scope was locked when the
            -- control row was captured; captured identity is immutable.
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'evaluation apply stage evidence cannot be deleted';
            END IF;
            SELECT claim_epoch INTO job_epoch
              FROM processing_jobs
             WHERE id = NEW.job_id
               FOR UPDATE;
            SELECT state, claim_epoch, rules_checksum, team_id, performance_level,
                   position_name, year, month
              INTO control_state, control_epoch, control_rules, control_team, control_level,
                   control_position, control_year, control_month
              FROM evaluation_apply_controls
             WHERE job_id = NEW.job_id
               FOR UPDATE;
            IF control_epoch IS DISTINCT FROM NEW.claim_epoch
               OR job_epoch IS DISTINCT FROM NEW.claim_epoch
               OR (TG_OP = 'UPDATE' AND OLD.claim_epoch IS DISTINCT FROM NEW.claim_epoch)
            THEN
                RAISE EXCEPTION 'stale evaluation apply epoch cannot write stage evidence';
            END IF;
            IF TG_OP = 'INSERT' AND control_state IS DISTINCT FROM 'staging' THEN
                RAISE EXCEPTION 'stale evaluation apply epoch cannot write stage evidence';
            END IF;
            IF TG_OP = 'UPDATE' AND (
                control_state IS DISTINCT FROM 'staging'
                OR OLD.job_id IS DISTINCT FROM NEW.job_id
                OR OLD.record_id IS DISTINCT FROM NEW.record_id
                OR OLD.record_year IS DISTINCT FROM NEW.record_year
                OR OLD.before_row IS DISTINCT FROM NEW.before_row
                OR OLD.after_row IS DISTINCT FROM NEW.after_row
                OR OLD.before_hash IS DISTINCT FROM NEW.before_hash
                OR OLD.after_hash IS DISTINCT FROM NEW.after_hash
                OR OLD.rules_checksum IS DISTINCT FROM NEW.rules_checksum
                OR OLD.captured_at IS DISTINCT FROM NEW.captured_at
            ) THEN
                RAISE EXCEPTION 'evaluation apply stage evidence is immutable';
            END IF;
            IF jsonb_typeof(NEW.before_row) IS DISTINCT FROM 'object'
               OR jsonb_typeof(NEW.after_row) IS DISTINCT FROM 'object'
            THEN
                RAISE EXCEPTION 'evaluation apply stage payload must be a json object';
            END IF;
            IF NEW.before_hash !~ '^[0-9a-f]{{64}}$'
               OR NEW.after_hash !~ '^[0-9a-f]{{64}}$'
               OR NEW.rules_checksum !~ '^[0-9a-f]{{64}}$'
            THEN
                RAISE EXCEPTION 'evaluation apply stage hash must be lowercase sha256';
            END IF;
            IF NEW.rules_checksum IS DISTINCT FROM control_rules THEN
                RAISE EXCEPTION 'evaluation apply stage rules checksum does not match the captured rules';
            END IF;
            IF TG_OP = 'INSERT' THEN
                SELECT team_id, performance_level, position_name, year, month
                  INTO record_team, record_level, record_position, record_year, record_month
                  FROM performance_records
                 WHERE id = NEW.record_id AND year = NEW.record_year
                   FOR UPDATE;
                IF FOUND AND (
                    record_team IS DISTINCT FROM control_team
                    OR record_level IS DISTINCT FROM control_level
                    OR COALESCE(record_position, '') IS DISTINCT FROM control_position
                    OR record_year IS DISTINCT FROM control_year
                    OR lower(trim(record_month)) IS DISTINCT FROM ({month_case})
                ) THEN
                    RAISE EXCEPTION 'evaluation apply stage record is outside the captured scope month';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $guard$
        """,
        """
        CREATE OR REPLACE FUNCTION guard_cache_invalidation_outbox() RETURNS trigger
        LANGUAGE plpgsql AS $guard$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'cache invalidation outbox evidence cannot be deleted';
            END IF;
            IF TG_OP = 'INSERT' THEN
                IF NEW.published_at IS NOT NULL
                   OR NEW.delivery_attempts <> 0
                   OR NEW.last_error IS NOT NULL
                   OR NOT EXISTS (
                        SELECT 1 FROM evaluation_apply_controls control
                        WHERE control.job_id = NEW.job_id
                          AND control.state = 'promoted'
                          AND control.promoted_revision_id = NEW.revision_id
                   )
                THEN
                    RAISE EXCEPTION 'cache invalidation outbox requires a promoted revision';
                END IF;
                RETURN NEW;
            END IF;
            IF NEW.id IS DISTINCT FROM OLD.id
               OR NEW.job_id IS DISTINCT FROM OLD.job_id
               OR NEW.revision_id IS DISTINCT FROM OLD.revision_id
               OR NEW.namespace IS DISTINCT FROM OLD.namespace
               OR NEW.dedup_key IS DISTINCT FROM OLD.dedup_key
               OR NEW.created_at IS DISTINCT FROM OLD.created_at
            THEN
                RAISE EXCEPTION 'cache invalidation outbox identity is immutable';
            END IF;
            IF OLD.published_at IS NOT NULL AND (
                NEW.published_at IS DISTINCT FROM OLD.published_at
                OR NEW.delivery_attempts IS DISTINCT FROM OLD.delivery_attempts
                OR NEW.next_retry_at IS DISTINCT FROM OLD.next_retry_at
                OR NEW.last_error IS DISTINCT FROM OLD.last_error
            ) THEN
                RAISE EXCEPTION 'published cache invalidation cannot be reversed or rewritten';
            END IF;
            IF OLD.published_at IS NULL AND NEW.delivery_attempts < OLD.delivery_attempts THEN
                RAISE EXCEPTION 'cache invalidation delivery is append-only until publish';
            END IF;
            RETURN NEW;
        END;
        $guard$
        """,
        f"""
        CREATE OR REPLACE FUNCTION guard_processing_job_apply_foundation() RETURNS trigger
        LANGUAGE plpgsql AS $guard$
        DECLARE
            control_epoch integer;
            live_epoch integer;
            staged record;
        BEGIN
            -- {_LOCK_ORDER_SQL}
            -- This UPDATE already holds processing_jobs. Reclaim then locks the
            -- control and staged performance records, and re-reads the live epoch.
            IF TG_OP = 'DELETE' THEN
                IF EXISTS (SELECT 1 FROM evaluation_apply_controls WHERE job_id = OLD.id) THEN
                    RAISE EXCEPTION 'evaluation apply job header cannot be deleted while a control exists';
                END IF;
                RETURN OLD;
            END IF;
            IF TG_OP = 'UPDATE'
               AND NEW.kind IS DISTINCT FROM OLD.kind
               AND EXISTS (SELECT 1 FROM evaluation_apply_controls WHERE job_id = OLD.id)
            THEN
                RAISE EXCEPTION 'evaluation apply job kind cannot change after control capture';
            END IF;
            IF TG_OP = 'UPDATE' AND NEW.id IS DISTINCT FROM OLD.id
               AND EXISTS (SELECT 1 FROM evaluation_apply_controls WHERE job_id = OLD.id)
            THEN
                RAISE EXCEPTION 'evaluation apply job header cannot be deleted while a control exists';
            END IF;
            IF TG_OP = 'UPDATE' AND NEW.claim_epoch IS DISTINCT FROM OLD.claim_epoch THEN
                SELECT claim_epoch INTO control_epoch
                  FROM evaluation_apply_controls
                 WHERE job_id = NEW.id
                   FOR UPDATE;
                IF FOUND THEN
                    FOR staged IN
                        SELECT record_row.id, record_row.year
                          FROM performance_records AS record_row
                         WHERE (record_row.id, record_row.year) IN (
                                SELECT stage_row.record_id, stage_row.record_year
                                  FROM evaluation_apply_stage_rows AS stage_row
                                 WHERE stage_row.job_id = NEW.id
                               )
                         ORDER BY record_row.id, record_row.year
                           FOR UPDATE
                    LOOP
                        NULL;
                    END LOOP;
                    SELECT claim_epoch INTO live_epoch
                      FROM processing_jobs
                     WHERE id = NEW.id;
                    IF live_epoch IS DISTINCT FROM OLD.claim_epoch
                       OR control_epoch IS DISTINCT FROM live_epoch
                    THEN
                        RAISE EXCEPTION 'evaluation apply claim epoch must match the processing job';
                    END IF;
                END IF;
            END IF;
            IF NEW.kind = 'evaluation_apply' AND (
                length(NEW.request_json::text) > {STATUS_PAYLOAD_LIMIT}
                OR (NEW.result_json IS NOT NULL AND length(NEW.result_json::text) > {STATUS_PAYLOAD_LIMIT})
            ) THEN
                RAISE EXCEPTION 'evaluation apply job status cannot carry a population payload';
            END IF;
            RETURN NEW;
        END;
        $guard$
        """,
        f"""
        CREATE OR REPLACE FUNCTION guard_evaluation_scope_apply_foundation() RETURNS trigger
        LANGUAGE plpgsql AS $guard$
        BEGIN
            -- {_LOCK_ORDER_SQL}
            -- This statement already holds evaluation_scopes. Do not lock
            -- processing_jobs here.
            IF TG_OP = 'DELETE' THEN
                IF EXISTS (SELECT 1 FROM evaluation_apply_controls WHERE scope_id = OLD.id) THEN
                    RAISE EXCEPTION 'evaluation apply evidence cannot be deleted';
                END IF;
                RETURN OLD;
            END IF;
            IF EXISTS (SELECT 1 FROM evaluation_apply_controls WHERE scope_id = OLD.id)
               AND (
                    NEW.id IS DISTINCT FROM OLD.id
                    OR NEW.team_id IS DISTINCT FROM OLD.team_id
                    OR NEW.performance_level IS DISTINCT FROM OLD.performance_level
                    OR NEW.position_name IS DISTINCT FROM OLD.position_name
               )
            THEN
                RAISE EXCEPTION 'captured evaluation scope identity cannot change while apply evidence exists';
            END IF;
            RETURN NEW;
        END;
        $guard$
        """,
        f"""
        CREATE OR REPLACE FUNCTION guard_performance_record_apply_foundation() RETURNS trigger
        LANGUAGE plpgsql AS $guard$
        BEGIN
            -- {_LOCK_ORDER_SQL}
            -- This statement already holds performance_records, the last lock.
            -- Do not lock processing_jobs or evaluation_apply_controls here.
            IF TG_OP = 'DELETE' THEN
                IF EXISTS (
                    SELECT 1 FROM evaluation_apply_stage_rows
                    WHERE record_id = OLD.id AND record_year = OLD.year
                ) THEN
                    RAISE EXCEPTION 'staged performance evidence cannot be deleted';
                END IF;
                RETURN OLD;
            END IF;
            IF EXISTS (
                SELECT 1 FROM evaluation_apply_stage_rows
                WHERE record_id = OLD.id AND record_year = OLD.year
            ) AND (
                NEW.id IS DISTINCT FROM OLD.id
                OR NEW.year IS DISTINCT FROM OLD.year
                OR NEW.team_id IS DISTINCT FROM OLD.team_id
                OR lower(trim(NEW.month)) IS DISTINCT FROM lower(trim(OLD.month))
                OR NEW.performance_level IS DISTINCT FROM OLD.performance_level
                OR COALESCE(NEW.position_name, '') IS DISTINCT FROM COALESCE(OLD.position_name, '')
            ) THEN
                RAISE EXCEPTION 'staged performance identity cannot change while apply evidence exists';
            END IF;
            RETURN NEW;
        END;
        $guard$
        """,
    ]
    for name, table in _postgres_trigger_targets():
        function = {
            "trg_evaluation_apply_control_guard": "guard_evaluation_apply_control",
            "trg_evaluation_apply_stage_guard": "guard_evaluation_apply_stage_row",
            "trg_cache_invalidation_outbox_guard": "guard_cache_invalidation_outbox",
            "trg_processing_job_apply_foundation": "guard_processing_job_apply_foundation",
            "trg_evaluation_scope_apply_foundation": "guard_evaluation_scope_apply_foundation",
            "trg_performance_record_apply_foundation": "guard_performance_record_apply_foundation",
        }[name]
        statements.append(f"DROP TRIGGER IF EXISTS {name} ON {table}")
        statements.append(
            f"""
            CREATE TRIGGER {name}
            BEFORE INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION {function}()
            """
        )
    return statements


def _sqlite_trigger_names() -> tuple[str, ...]:
    names = []
    for statement in _sqlite_guard_statements():
        stripped = statement.strip()
        if stripped.startswith("CREATE TRIGGER"):
            names.append(stripped.split()[2])
    return tuple(names)


def _sqlite_guard_statements() -> list[str]:
    month_case = _month_name_case("c.month")
    names = [
        "trg_evaluation_apply_control_delete",
        "trg_evaluation_apply_control_actor_insert",
        "trg_evaluation_apply_control_actor_update",
        "trg_evaluation_apply_control_fingerprint_insert",
        "trg_evaluation_apply_control_fingerprint_update",
        "trg_evaluation_apply_control_scope_insert",
        "trg_evaluation_apply_control_version_insert",
        "trg_evaluation_apply_control_epoch_insert",
        "trg_evaluation_apply_control_pending_insert",
        "trg_evaluation_apply_control_identity_update",
        "trg_evaluation_apply_control_requester_update",
        "trg_evaluation_apply_control_state_update",
        "trg_evaluation_apply_control_epoch_update",
        "trg_evaluation_apply_control_retry_update",
        "trg_evaluation_apply_control_open_requester",
        "trg_evaluation_apply_control_promoted_update",
        "trg_evaluation_apply_control_promoting_update",
        "trg_evaluation_apply_control_revision_update",
        "trg_evaluation_apply_control_count_update",
        "trg_evaluation_apply_control_count_decrease",
        "trg_evaluation_apply_control_cursor_update",
        "trg_evaluation_apply_stage_delete",
        "trg_evaluation_apply_stage_epoch_insert",
        "trg_evaluation_apply_stage_epoch_update",
        "trg_evaluation_apply_stage_immutable_update",
        "trg_evaluation_apply_stage_payload_insert",
        "trg_evaluation_apply_stage_payload_update",
        "trg_evaluation_apply_stage_hash_insert",
        "trg_evaluation_apply_stage_hash_update",
        "trg_evaluation_apply_stage_rules_insert",
        "trg_evaluation_apply_stage_scope_insert",
        "trg_processing_job_apply_delete",
        "trg_processing_job_apply_kind",
        "trg_processing_job_apply_payload_insert",
        "trg_processing_job_apply_payload_update",
        "trg_evaluation_scope_apply_delete",
        "trg_evaluation_scope_apply_identity",
        "trg_performance_record_apply_delete",
        "trg_performance_record_apply_identity",
        "trg_cache_invalidation_outbox_delete",
        "trg_cache_invalidation_outbox_insert",
        "trg_cache_invalidation_outbox_identity",
        "trg_cache_invalidation_outbox_published",
        "trg_cache_invalidation_outbox_attempts",
    ]
    drops = [f"DROP TRIGGER IF EXISTS {name}" for name in names]
    creates = [
        f"""
        CREATE TRIGGER trg_evaluation_apply_control_delete
        BEFORE DELETE ON evaluation_apply_controls
        WHEN OLD.state IS NOT 'pending'
          OR OLD.promoted_revision_id IS NOT NULL
          OR EXISTS (SELECT 1 FROM evaluation_apply_stage_rows WHERE job_id = OLD.job_id)
          OR EXISTS (SELECT 1 FROM cache_invalidation_outbox WHERE job_id = OLD.job_id)
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply evidence cannot be deleted');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_actor_insert
        BEFORE INSERT ON evaluation_apply_controls
        WHEN json_extract(NEW.actor_snapshot, '$.state') IS NOT 'known'
          OR COALESCE(json_extract(NEW.actor_snapshot, '$.user_id'), '') = ''
          OR replace(json_extract(NEW.actor_snapshot, '$.user_id'), '-', '')
             IS NOT replace(NEW.requested_by_user_id, '-', '')
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply actor snapshot must record a known user');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_actor_update
        BEFORE UPDATE ON evaluation_apply_controls
        WHEN json_extract(NEW.actor_snapshot, '$.state') IS NOT 'known'
          OR COALESCE(json_extract(NEW.actor_snapshot, '$.user_id'), '') = ''
          OR (
              NEW.requested_by_user_id IS NOT NULL
              AND replace(json_extract(NEW.actor_snapshot, '$.user_id'), '-', '')
                  IS NOT replace(NEW.requested_by_user_id, '-', '')
          )
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply actor snapshot must record a known user');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_fingerprint_insert
        BEFORE INSERT ON evaluation_apply_controls
        WHEN length(NEW.rules_checksum) <> 64
          OR length(NEW.proof_source_fingerprint) <> 64
          OR length(NEW.lineage_fingerprint) <> 64
          OR NEW.rules_checksum GLOB '*[^0-9a-f]*'
          OR NEW.proof_source_fingerprint GLOB '*[^0-9a-f]*'
          OR NEW.lineage_fingerprint GLOB '*[^0-9a-f]*'
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply fingerprints must be lowercase sha256');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_fingerprint_update
        BEFORE UPDATE ON evaluation_apply_controls
        WHEN length(NEW.rules_checksum) <> 64
          OR length(NEW.proof_source_fingerprint) <> 64
          OR length(NEW.lineage_fingerprint) <> 64
          OR NEW.rules_checksum GLOB '*[^0-9a-f]*'
          OR NEW.proof_source_fingerprint GLOB '*[^0-9a-f]*'
          OR NEW.lineage_fingerprint GLOB '*[^0-9a-f]*'
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply fingerprints must be lowercase sha256');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_scope_insert
        BEFORE INSERT ON evaluation_apply_controls
        WHEN NOT EXISTS (
            SELECT 1 FROM evaluation_scopes scope
            WHERE scope.id = NEW.scope_id
              AND scope.team_id IS NEW.team_id
              AND scope.performance_level IS NEW.performance_level
              AND scope.position_name IS NEW.position_name
        )
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply scope identity does not match the scope row');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_version_insert
        BEFORE INSERT ON evaluation_apply_controls
        WHEN NOT EXISTS (
            SELECT 1 FROM team_configuration_versions version
            WHERE version.id = NEW.version_id AND version.team_id IS NEW.team_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply version team does not match the captured team');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_epoch_insert
        BEFORE INSERT ON evaluation_apply_controls
        WHEN NEW.claim_epoch IS NOT (
            SELECT claim_epoch FROM processing_jobs WHERE id = NEW.job_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply claim epoch must match the processing job');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_pending_insert
        BEFORE INSERT ON evaluation_apply_controls
        WHEN NEW.state IS NOT 'pending'
          OR NEW.staged_count <> 0
          OR NEW.promoted_count <> 0
          OR NEW.promoted_revision_id IS NOT NULL
          OR NEW.stage_cursor IS NOT NULL
          OR NEW.requested_by_user_id IS NULL
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply control must be captured pending');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_identity_update
        BEFORE UPDATE ON evaluation_apply_controls
        WHEN OLD.job_id IS NOT NEW.job_id
          OR OLD.scope_id IS NOT NEW.scope_id
          OR OLD.version_id IS NOT NEW.version_id
          OR OLD.team_id IS NOT NEW.team_id
          OR OLD.performance_level IS NOT NEW.performance_level
          OR OLD.position_name IS NOT NEW.position_name
          OR OLD.year IS NOT NEW.year
          OR OLD.month IS NOT NEW.month
          OR OLD.engine_version IS NOT NEW.engine_version
          OR OLD.rules_checksum IS NOT NEW.rules_checksum
          OR OLD.proof_source_fingerprint IS NOT NEW.proof_source_fingerprint
          OR OLD.lineage_fingerprint IS NOT NEW.lineage_fingerprint
          OR json(OLD.actor_snapshot) IS NOT json(NEW.actor_snapshot)
          OR OLD.created_at IS NOT NEW.created_at
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply captured identity is immutable');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_requester_update
        BEFORE UPDATE ON evaluation_apply_controls
        WHEN OLD.requested_by_user_id IS NOT NEW.requested_by_user_id
          AND NEW.requested_by_user_id IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply requester can only be cleared by audit deletion');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_state_update
        BEFORE UPDATE ON evaluation_apply_controls
        WHEN NOT (
            (OLD.state = 'pending' AND NEW.state IN ('pending', 'staging', 'failed', 'cancelled'))
            OR (OLD.state = 'staging' AND NEW.state IN ('staging', 'promoting', 'failed', 'cancelled'))
            OR (OLD.state = 'promoting' AND NEW.state IN ('promoting', 'promoted', 'failed'))
            OR (OLD.state = 'promoted' AND NEW.state = 'promoted')
            OR (OLD.state = 'failed' AND NEW.state IN ('failed', 'pending'))
            OR (OLD.state = 'cancelled' AND NEW.state IN ('cancelled', 'pending'))
        )
        BEGIN
            SELECT RAISE(ABORT, 'illegal evaluation apply state transition');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_epoch_update
        BEFORE UPDATE ON evaluation_apply_controls
        WHEN NEW.claim_epoch IS NOT OLD.claim_epoch
          AND NOT (
              OLD.state IN ('failed', 'cancelled')
              AND NEW.state = 'pending'
              AND NEW.claim_epoch = OLD.claim_epoch + 1
          )
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply claim epoch changes only on retry');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_retry_update
        BEFORE UPDATE ON evaluation_apply_controls
        WHEN OLD.state IN ('failed', 'cancelled') AND NEW.state = 'pending'
          AND (
              NEW.claim_epoch IS NOT OLD.claim_epoch + 1
              OR NEW.staged_count <> 0
              OR NEW.promoted_count <> 0
              OR NEW.promoted_revision_id IS NOT NULL
              OR NEW.stage_cursor IS NOT NULL
              OR NEW.requested_by_user_id IS NULL
              OR NEW.claim_epoch IS NOT (
                  SELECT claim_epoch FROM processing_jobs WHERE id = NEW.job_id
              )
          )
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply retry must advance the epoch and clear progress');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_open_requester
        BEFORE UPDATE ON evaluation_apply_controls
        WHEN NEW.state IN ('pending', 'staging', 'promoting')
          AND NEW.requested_by_user_id IS NULL
        BEGIN
            SELECT RAISE(ABORT, 'open evaluation apply cannot replay a missing requester');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_promoted_update
        BEFORE UPDATE ON evaluation_apply_controls
        WHEN OLD.state = 'promoted' AND (
            NEW.state IS NOT OLD.state
            OR NEW.claim_epoch IS NOT OLD.claim_epoch
            OR NEW.staged_count IS NOT OLD.staged_count
            OR NEW.promoted_count IS NOT OLD.promoted_count
            OR NEW.promoted_revision_id IS NOT OLD.promoted_revision_id
            OR NEW.stage_cursor IS NOT OLD.stage_cursor
        )
        BEGIN
            SELECT RAISE(ABORT, 'promoted evaluation apply evidence is immutable');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_promoting_update
        BEFORE UPDATE ON evaluation_apply_controls
        WHEN NEW.state = 'promoting'
          AND (NEW.promoted_revision_id IS NOT NULL OR NEW.promoted_count <> 0)
        BEGIN
            SELECT RAISE(ABORT, 'promoting evaluation apply has not committed a revision');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_revision_update
        BEFORE UPDATE ON evaluation_apply_controls
        WHEN (
            NEW.state = 'promoted' AND NEW.promoted_revision_id IS NULL
        ) OR (
            NEW.state IS NOT 'promoted'
            AND (NEW.promoted_revision_id IS NOT NULL OR NEW.promoted_count <> 0)
        )
        BEGIN
            SELECT RAISE(ABORT, 'promoted evaluation apply requires a revision');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_count_update
        BEFORE UPDATE ON evaluation_apply_controls
        WHEN NOT (OLD.state IN ('failed', 'cancelled') AND NEW.state = 'pending')
          AND NOT (OLD.state = 'staging' AND NEW.state = 'staging')
          AND NEW.staged_count IS NOT OLD.staged_count
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply staged count is frozen outside staging');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_count_decrease
        BEFORE UPDATE ON evaluation_apply_controls
        WHEN OLD.state = 'staging' AND NEW.state = 'staging' AND NEW.staged_count < OLD.staged_count
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply staged count cannot decrease');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_control_cursor_update
        BEFORE UPDATE ON evaluation_apply_controls
        WHEN NOT (OLD.state = 'staging' AND NEW.state = 'staging')
          AND NOT (OLD.state = 'pending' AND NEW.state = 'staging')
          AND NOT (OLD.state IN ('failed', 'cancelled') AND NEW.state = 'pending')
          AND NEW.stage_cursor IS NOT OLD.stage_cursor
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply stage cursor is frozen');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_stage_delete
        BEFORE DELETE ON evaluation_apply_stage_rows
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply stage evidence cannot be deleted');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_stage_epoch_insert
        BEFORE INSERT ON evaluation_apply_stage_rows
        WHEN (SELECT state FROM evaluation_apply_controls WHERE job_id = NEW.job_id) IS NOT 'staging'
          OR (SELECT claim_epoch FROM evaluation_apply_controls WHERE job_id = NEW.job_id)
             IS NOT NEW.claim_epoch
          OR (SELECT claim_epoch FROM processing_jobs WHERE id = NEW.job_id) IS NOT NEW.claim_epoch
        BEGIN
            SELECT RAISE(ABORT, 'stale evaluation apply epoch cannot write stage evidence');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_stage_epoch_update
        BEFORE UPDATE ON evaluation_apply_stage_rows
        WHEN OLD.claim_epoch IS NOT NEW.claim_epoch
          OR (SELECT claim_epoch FROM evaluation_apply_controls WHERE job_id = NEW.job_id)
             IS NOT NEW.claim_epoch
          OR (SELECT claim_epoch FROM processing_jobs WHERE id = NEW.job_id) IS NOT NEW.claim_epoch
        BEGIN
            SELECT RAISE(ABORT, 'stale evaluation apply epoch cannot write stage evidence');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_stage_immutable_update
        BEFORE UPDATE ON evaluation_apply_stage_rows
        WHEN (SELECT state FROM evaluation_apply_controls WHERE job_id = NEW.job_id) IS NOT 'staging'
          OR OLD.job_id IS NOT NEW.job_id
          OR OLD.record_id IS NOT NEW.record_id
          OR OLD.record_year IS NOT NEW.record_year
          OR json(OLD.before_row) IS NOT json(NEW.before_row)
          OR json(OLD.after_row) IS NOT json(NEW.after_row)
          OR OLD.before_hash IS NOT NEW.before_hash
          OR OLD.after_hash IS NOT NEW.after_hash
          OR OLD.rules_checksum IS NOT NEW.rules_checksum
          OR OLD.captured_at IS NOT NEW.captured_at
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply stage evidence is immutable');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_stage_payload_insert
        BEFORE INSERT ON evaluation_apply_stage_rows
        WHEN json_type(NEW.before_row) IS NOT 'object' OR json_type(NEW.after_row) IS NOT 'object'
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply stage payload must be a json object');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_stage_payload_update
        BEFORE UPDATE ON evaluation_apply_stage_rows
        WHEN json_type(NEW.before_row) IS NOT 'object' OR json_type(NEW.after_row) IS NOT 'object'
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply stage payload must be a json object');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_stage_hash_insert
        BEFORE INSERT ON evaluation_apply_stage_rows
        WHEN length(NEW.before_hash) <> 64
          OR length(NEW.after_hash) <> 64
          OR length(NEW.rules_checksum) <> 64
          OR NEW.before_hash GLOB '*[^0-9a-f]*'
          OR NEW.after_hash GLOB '*[^0-9a-f]*'
          OR NEW.rules_checksum GLOB '*[^0-9a-f]*'
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply stage hash must be lowercase sha256');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_stage_hash_update
        BEFORE UPDATE ON evaluation_apply_stage_rows
        WHEN length(NEW.before_hash) <> 64
          OR length(NEW.after_hash) <> 64
          OR length(NEW.rules_checksum) <> 64
          OR NEW.before_hash GLOB '*[^0-9a-f]*'
          OR NEW.after_hash GLOB '*[^0-9a-f]*'
          OR NEW.rules_checksum GLOB '*[^0-9a-f]*'
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply stage hash must be lowercase sha256');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_apply_stage_rules_insert
        BEFORE INSERT ON evaluation_apply_stage_rows
        WHEN NEW.rules_checksum IS NOT (
            SELECT rules_checksum FROM evaluation_apply_controls WHERE job_id = NEW.job_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply stage rules checksum does not match the captured rules');
        END
        """,
        f"""
        CREATE TRIGGER trg_evaluation_apply_stage_scope_insert
        BEFORE INSERT ON evaluation_apply_stage_rows
        WHEN EXISTS (
            SELECT 1
            FROM performance_records record
            JOIN evaluation_apply_controls c ON c.job_id = NEW.job_id
            WHERE record.id = NEW.record_id
              AND record.year = NEW.record_year
              AND (
                  record.team_id IS NOT c.team_id
                  OR record.performance_level IS NOT c.performance_level
                  OR COALESCE(record.position_name, '') IS NOT c.position_name
                  OR record.year IS NOT c.year
                  OR lower(trim(record.month)) IS NOT ({month_case})
              )
        )
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply stage record is outside the captured scope month');
        END
        """,
        """
        CREATE TRIGGER trg_processing_job_apply_delete
        BEFORE DELETE ON processing_jobs
        WHEN EXISTS (SELECT 1 FROM evaluation_apply_controls WHERE job_id = OLD.id)
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply job header cannot be deleted while a control exists');
        END
        """,
        """
        CREATE TRIGGER trg_processing_job_apply_kind
        BEFORE UPDATE ON processing_jobs
        WHEN OLD.kind IS NOT NEW.kind
          AND EXISTS (SELECT 1 FROM evaluation_apply_controls WHERE job_id = OLD.id)
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply job kind cannot change after control capture');
        END
        """,
        f"""
        CREATE TRIGGER trg_processing_job_apply_payload_insert
        BEFORE INSERT ON processing_jobs
        WHEN NEW.kind = 'evaluation_apply' AND (
            length(CAST(NEW.request_json AS TEXT)) > {STATUS_PAYLOAD_LIMIT}
            OR (
                NEW.result_json IS NOT NULL
                AND length(CAST(NEW.result_json AS TEXT)) > {STATUS_PAYLOAD_LIMIT}
            )
        )
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply job status cannot carry a population payload');
        END
        """,
        f"""
        CREATE TRIGGER trg_processing_job_apply_payload_update
        BEFORE UPDATE ON processing_jobs
        WHEN NEW.kind = 'evaluation_apply' AND (
            length(CAST(NEW.request_json AS TEXT)) > {STATUS_PAYLOAD_LIMIT}
            OR (
                NEW.result_json IS NOT NULL
                AND length(CAST(NEW.result_json AS TEXT)) > {STATUS_PAYLOAD_LIMIT}
            )
        )
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply job status cannot carry a population payload');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_scope_apply_delete
        BEFORE DELETE ON evaluation_scopes
        WHEN EXISTS (SELECT 1 FROM evaluation_apply_controls WHERE scope_id = OLD.id)
        BEGIN
            SELECT RAISE(ABORT, 'evaluation apply evidence cannot be deleted');
        END
        """,
        """
        CREATE TRIGGER trg_evaluation_scope_apply_identity
        BEFORE UPDATE ON evaluation_scopes
        WHEN EXISTS (SELECT 1 FROM evaluation_apply_controls WHERE scope_id = OLD.id)
          AND (
              OLD.id IS NOT NEW.id
              OR OLD.team_id IS NOT NEW.team_id
              OR OLD.performance_level IS NOT NEW.performance_level
              OR OLD.position_name IS NOT NEW.position_name
          )
        BEGIN
            SELECT RAISE(ABORT, 'captured evaluation scope identity cannot change while apply evidence exists');
        END
        """,
        """
        CREATE TRIGGER trg_performance_record_apply_delete
        BEFORE DELETE ON performance_records
        WHEN EXISTS (
            SELECT 1 FROM evaluation_apply_stage_rows
            WHERE record_id = OLD.id AND record_year = OLD.year
        )
        BEGIN
            SELECT RAISE(ABORT, 'staged performance evidence cannot be deleted');
        END
        """,
        """
        CREATE TRIGGER trg_performance_record_apply_identity
        BEFORE UPDATE ON performance_records
        WHEN EXISTS (
            SELECT 1 FROM evaluation_apply_stage_rows
            WHERE record_id = OLD.id AND record_year = OLD.year
        ) AND (
            OLD.id IS NOT NEW.id
            OR OLD.year IS NOT NEW.year
            OR OLD.team_id IS NOT NEW.team_id
            OR lower(trim(OLD.month)) IS NOT lower(trim(NEW.month))
            OR OLD.performance_level IS NOT NEW.performance_level
            OR COALESCE(OLD.position_name, '') IS NOT COALESCE(NEW.position_name, '')
        )
        BEGIN
            SELECT RAISE(ABORT, 'staged performance identity cannot change while apply evidence exists');
        END
        """,
        """
        CREATE TRIGGER trg_cache_invalidation_outbox_delete
        BEFORE DELETE ON cache_invalidation_outbox
        BEGIN
            SELECT RAISE(ABORT, 'cache invalidation outbox evidence cannot be deleted');
        END
        """,
        """
        CREATE TRIGGER trg_cache_invalidation_outbox_insert
        BEFORE INSERT ON cache_invalidation_outbox
        WHEN NEW.published_at IS NOT NULL
          OR NEW.delivery_attempts <> 0
          OR NEW.last_error IS NOT NULL
          OR NOT EXISTS (
              SELECT 1 FROM evaluation_apply_controls control
              WHERE control.job_id = NEW.job_id
                AND control.state = 'promoted'
                AND control.promoted_revision_id IS NEW.revision_id
          )
        BEGIN
            SELECT RAISE(ABORT, 'cache invalidation outbox requires a promoted revision');
        END
        """,
        """
        CREATE TRIGGER trg_cache_invalidation_outbox_identity
        BEFORE UPDATE ON cache_invalidation_outbox
        WHEN OLD.id IS NOT NEW.id
          OR OLD.job_id IS NOT NEW.job_id
          OR OLD.revision_id IS NOT NEW.revision_id
          OR OLD.namespace IS NOT NEW.namespace
          OR OLD.dedup_key IS NOT NEW.dedup_key
          OR OLD.created_at IS NOT NEW.created_at
        BEGIN
            SELECT RAISE(ABORT, 'cache invalidation outbox identity is immutable');
        END
        """,
        """
        CREATE TRIGGER trg_cache_invalidation_outbox_published
        BEFORE UPDATE ON cache_invalidation_outbox
        WHEN OLD.published_at IS NOT NULL AND (
            NEW.published_at IS NOT OLD.published_at
            OR NEW.delivery_attempts IS NOT OLD.delivery_attempts
            OR NEW.next_retry_at IS NOT OLD.next_retry_at
            OR NEW.last_error IS NOT OLD.last_error
        )
        BEGIN
            SELECT RAISE(ABORT, 'published cache invalidation cannot be reversed or rewritten');
        END
        """,
        """
        CREATE TRIGGER trg_cache_invalidation_outbox_attempts
        BEFORE UPDATE ON cache_invalidation_outbox
        WHEN OLD.published_at IS NULL AND NEW.delivery_attempts < OLD.delivery_attempts
        BEGIN
            SELECT RAISE(ABORT, 'cache invalidation delivery is append-only until publish');
        END
        """,
    ]
    # SQLite runs BEFORE triggers in reverse creation order. Reversing the
    # statements makes runtime order follow the list above, which is also
    # the order of the PostgreSQL guard functions.
    return drops + list(reversed(creates))


_registered = False


def register_apply_foundation_guards(metadata) -> None:
    global _registered
    if _registered:
        return
    _registered = True

    @event.listens_for(metadata, "after_create")
    def _install_after_metadata_create(target, connection, **kw):
        created = {table.name for table in kw.get("tables") or []}
        if created and not set(FOUNDATION_TABLES).issubset(created):
            return
        if not all(_table_exists(connection, table) for table in FOUNDATION_TABLES):
            return
        install_apply_foundation_guards(connection)
