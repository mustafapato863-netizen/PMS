"""Compare stored scoring rules without inferring them from a version id.

A comparison reads pinned KPI rows already on the records it is given.
Identical targets, weights, directions, units, and explicit source, formula,
or aggregation values are the same basis even when the version id, checksum,
or row order differs. A missing pin, a one-sided optional field, a blank
team or level, or a non-overlapping scope is unknown. A blank position is a
valid team-scope identity and stays distinct from a populated position. A
row that lacks a team or level does not disappear beside a trusted scope: it
blocks a full-population like-for-like claim. A scope present on only one
side is a population-coverage change, not an invented rule.
Explicit source, formula, or aggregation differences are not proof that the
stored actuals are comparable. Raw actuals are compared only for employee
identities present on both sides; a joiner or leaver is not a rule change and
is not proof that the whole population's raw performance moved.
"""
from __future__ import annotations

import math
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from utils.kpi_direction import normalize_direction

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

_SETTINGS = "Scores can be affected by evaluation settings."
_FULL_UNCHANGED = "Comparable raw performance is unchanged."
_FULL_CHANGED = "Comparable raw performance changed."
_SHARED_UNCHANGED = "Shared comparable KPI values are unchanged."
_SHARED_CHANGED = "Shared comparable KPI values changed."
_RAW_UNAVAILABLE = "Comparable raw performance is not available."
_PARTIAL = "Some KPI actuals are not comparable."
_MEMBERSHIP = (
    "The compared employee population changed, so this score movement "
    "is not a matched-cohort comparison."
)
_UNIDENTIFIED = (
    "Some records have no employee identity, so raw performance is not "
    "confirmed for a matched cohort."
)
_UNKNOWN = (
    "Evaluation settings for this comparison are unavailable, "
    "so this score movement is not confirmed as like-for-like."
)
_UNAVAILABLE = "Evaluation settings comparison is unavailable for the exact previous month."
_NO_SCOPE = (
    "The compared populations do not share a team, position, and level, "
    "so this score movement is not confirmed as like-for-like."
)
_MIXED = (
    "Evaluation settings are mixed in this comparison, so scores are not like-for-like. "
    + _SETTINGS
)
_OPTIONAL = ("source", "formula", "aggregation")


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _present(value: Any, name: str) -> bool:
    if isinstance(value, dict):
        return name in value and value.get(name) is not None
    return getattr(value, name, None) is not None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        if isinstance(value, Decimal):
            number = value
        elif isinstance(value, (int, float)):
            number = Decimal(str(value))
        elif isinstance(value, str):
            number = Decimal(value.strip())
        else:
            return None
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        return None
    return number


def _explicit(raw: Any, names: tuple[str, ...]) -> tuple[tuple[str, str], ...] | None:
    found = []
    for name in names:
        if _present(raw, name):
            found.append((name, _text(_get(raw, name))))
    return tuple(found) or None


def _number_field(raw: Any, names: tuple[str, ...]) -> Decimal | None:
    for name in names:
        if _present(raw, name):
            return _decimal(_get(raw, name))
    return None


def _message(state: str, raw: str, membership: str, proven: str | None, kpi_gap: bool) -> str | None:
    if state == "unavailable":
        return _UNAVAILABLE
    if state == "unknown":
        return _NO_SCOPE if membership == "none" else _UNKNOWN
    if state == "unchanged" and membership == "stable" and raw in {"unchanged", "changed"}:
        return None
    parts: list[str] = []
    if state == "mixed":
        parts.append(_MIXED)
    elif state == "changed":
        parts.append(_SETTINGS)
    if membership == "changed":
        parts.append(_MEMBERSHIP)
    elif membership == "unknown" and state != "unknown":
        parts.append(_UNIDENTIFIED)
    if raw == "partial":
        if proven == "unchanged":
            parts.append(_SHARED_UNCHANGED)
        elif proven == "changed":
            parts.append(_SHARED_CHANGED)
        if kpi_gap:
            parts.append(_PARTIAL)
    elif raw == "unchanged" and state != "unchanged":
        parts.append(_FULL_UNCHANGED)
    elif raw == "changed" and state != "unchanged":
        parts.append(_FULL_CHANGED)
    elif raw in {"not_comparable", "unknown"}:
        parts.append(_RAW_UNAVAILABLE)
    return " ".join(parts) or None


def _context(
    state: str,
    raw: str,
    reasons: list[str],
    membership: str,
    proven: str | None = None,
    kpi_gap: bool = False,
) -> dict[str, Any]:
    if state in {"unknown", "unavailable"}:
        raw = "unknown"
        proven = None
        kpi_gap = False
    if state == "mixed":
        raw = "not_comparable"
        proven = None
    if membership in {"changed", "unknown"} and state not in {"unknown", "unavailable", "mixed"} and raw in {"unchanged", "changed"}:
        proven = proven or raw
        raw = "partial"
    like_for_like = state == "unchanged" and membership == "stable" and raw in {"unchanged", "changed"}
    return {
        "state": state,
        "like_for_like": like_for_like,
        "raw_performance": raw,
        "membership": "none" if state == "unavailable" else membership,
        "reasons": sorted(set(reasons)) if state == "changed" else [],
        "message": _message(state, raw, membership, proven, kpi_gap),
    }


def _parse_rule(raw: Any) -> tuple[tuple, Decimal | None] | None:
    if _get(raw, "evaluation_pinned") is not True:
        return None
    key = _text(_get(raw, "kpi_key") or _get(raw, "key")).casefold()
    direction = normalize_direction(_get(raw, "direction"))
    unit = _text(_get(raw, "unit")).casefold()
    target = _number_field(raw, ("target_value", "target"))
    weight = _number_field(raw, ("weight_applied", "weight", "weight_pct"))
    if not key or direction not in {"higher_better", "lower_better"} or not unit or target is None or weight is None:
        return None
    rule = (
        key,
        target,
        weight,
        direction,
        unit,
        _explicit(raw, ("source", "target_source", "achievement_source")),
        _explicit(raw, ("formula", "score_formula")),
        _explicit(raw, ("aggregation",)),
    )
    return rule, _number_field(raw, ("actual_value", "actual"))


def _record_rules(record: Any) -> tuple[str, tuple[tuple, ...] | None, dict[str, Decimal | None] | None]:
    rows = list(_get(record, "kpi_values") or [])
    if not rows:
        return "unknown", None, None
    by_key: dict[str, tuple] = {}
    actuals: dict[str, Decimal | None] = {}
    for raw in rows:
        parsed = _parse_rule(raw)
        if parsed is None:
            return "unknown", None, None
        rule, actual = parsed
        previous = by_key.get(rule[0])
        if previous is not None and previous != rule:
            return "mixed", None, None
        by_key[rule[0]] = rule
        if rule[0] in actuals and actuals[rule[0]] != actual:
            actuals[rule[0]] = None
        else:
            actuals[rule[0]] = actual
    return "uniform", tuple(sorted(by_key.values())), actuals


def _employee_id(record: Any) -> str | None:
    return _text(_get(record, "employee_id")) or None


def _scope_key(record: Any) -> tuple[str, str, str]:
    return (
        _text(_get(record, "team")),
        _text(_get(record, "position")),
        _text(_get(record, "performance_level")),
    )


def _trusted_scope(key: tuple[str, str, str]) -> bool:
    """Team and level identify a population. Position may be blank."""
    team, _position, level = key
    return bool(team and level)


def _slice_rules(
    records: list[Any],
) -> tuple[str, tuple[tuple, ...] | None, dict[str, dict[str, Decimal | None]], bool]:
    if not records:
        return "empty", None, {}, False
    unidentified = False
    by_employee: dict[str, dict[str, Decimal | None]] = {}
    signature: tuple[tuple, ...] | None = None
    for record in records:
        status, rules, actuals = _record_rules(record)
        if status == "unknown":
            return "unknown", None, {}, True
        if status == "mixed":
            return "mixed", None, {}, True
        if signature is None:
            signature = rules
        elif signature != rules:
            return "mixed", None, {}, True
        employee_id = _employee_id(record)
        if employee_id is None:
            unidentified = True
            continue
        current = by_employee.get(employee_id)
        if current is None:
            by_employee[employee_id] = dict(actuals or {})
            continue
        for key, actual in (actuals or {}).items():
            if key in current and current[key] != actual:
                current[key] = None
            elif key not in current:
                current[key] = actual
    return "uniform", signature, by_employee, unidentified


def _rule_map(rules: tuple[tuple, ...] | None) -> dict[str, tuple]:
    return {rule[0]: rule for rule in rules or ()}


def _reasons(left: tuple[tuple, ...], right: tuple[tuple, ...]) -> tuple[list[str], bool]:
    before, after = _rule_map(left), _rule_map(right)
    reasons: list[str] = []
    unknown_optional = False
    if set(before) != set(after):
        reasons.append("kpi_set")
    labels = ("target", "weight", "direction", "unit", "source", "formula", "aggregation")
    for key in set(before) & set(after):
        for index, label in enumerate(labels, start=1):
            left_value, right_value = before[key][index], after[key][index]
            if label in _OPTIONAL and (left_value is None or right_value is None):
                if left_value is not None or right_value is not None:
                    unknown_optional = True
                continue
            if left_value != right_value:
                reasons.append(label)
    return reasons, unknown_optional


def _raw_between(
    left_rules,
    left_actuals: dict[str, dict[str, Decimal | None]],
    right_rules,
    right_actuals: dict[str, dict[str, Decimal | None]],
) -> tuple[str, str | None, bool]:
    before, after = _rule_map(left_rules), _rule_map(right_rules)
    shared_keys = set(before) & set(after)
    shared_ids = set(left_actuals) & set(right_actuals)
    kpi_gap = bool(set(before) ^ set(after))
    proven: list[str] = []
    blocked = False
    if not shared_ids:
        return "unknown", None, kpi_gap
    for key in shared_keys:
        left_rule, right_rule = before[key], after[key]
        explicit_differs = any(
            left_rule[index] is not None and right_rule[index] is not None and left_rule[index] != right_rule[index]
            for index in (5, 6, 7)
        )
        if left_rule[3] != right_rule[3] or left_rule[4] != right_rule[4] or explicit_differs:
            blocked = True
            kpi_gap = True
            continue
        for employee_id in shared_ids:
            left_map = left_actuals.get(employee_id) or {}
            right_map = right_actuals.get(employee_id) or {}
            if key not in left_map or key not in right_map or left_map[key] is None or right_map[key] is None:
                kpi_gap = True
                continue
            proven.append("changed" if left_map[key] != right_map[key] else "unchanged")
    note = "changed" if "changed" in proven else "unchanged" if proven else None
    if proven and (blocked or kpi_gap):
        return "partial", note, True
    if "changed" in proven:
        return "changed", "changed", False
    if proven:
        return "unchanged", "unchanged", False
    if blocked:
        return "not_comparable", None, True
    return "unknown", None, kpi_gap


def _aggregate_state(states: list[str]) -> str:
    if any(state == "changed" for state in states) and any(state in {"unknown", "mixed"} for state in states):
        return "mixed"
    if any(state == "unknown" for state in states):
        return "unknown"
    if any(state == "mixed" for state in states):
        return "mixed"
    if any(state == "changed" for state in states):
        return "changed"
    return "unchanged"


def _aggregate_membership(values: list[str]) -> str:
    if not values:
        return "none"
    if "changed" in values:
        return "changed"
    if "unknown" in values:
        return "unknown"
    return "stable"


def _aggregate_raw(state: str, raws: list[tuple[str, str | None, bool]]) -> tuple[str, str | None, bool]:
    if state in {"unknown", "unavailable"}:
        return "unknown", None, False
    if state == "mixed":
        return "not_comparable", None, False
    statuses = [item[0] for item in raws]
    notes = [item[1] for item in raws if item[1]]
    kpi_gap = any(item[2] for item in raws) or any(status in {"partial", "not_comparable", "unknown"} for status in statuses)
    proven = "changed" if "changed" in notes else "unchanged" if "unchanged" in notes else None
    if any(status == "partial" for status in statuses) or (proven and any(status in {"unknown", "not_comparable"} for status in statuses)):
        return "partial", proven, True
    if "changed" in statuses:
        return "changed", "changed", False
    if statuses and all(status == "unchanged" for status in statuses):
        return "unchanged", "unchanged", False
    if "not_comparable" in statuses:
        return "not_comparable", None, True
    return "unknown", None, kpi_gap


def compare_scoring_basis(current: list[Any] | None, previous: list[Any] | None) -> dict[str, Any]:
    """Compare two already selected populations. An empty side is not a fallback."""
    current_rows = list(current or [])
    previous_rows = list(previous or [])
    if not current_rows or not previous_rows:
        return _context("unavailable", "unknown", [], "none")
    current_groups: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
    previous_groups: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
    untrusted_rows = False
    for record in current_rows:
        key = _scope_key(record)
        if _trusted_scope(key):
            current_groups[key].append(record)
        else:
            untrusted_rows = True
    for record in previous_rows:
        key = _scope_key(record)
        if _trusted_scope(key):
            previous_groups[key].append(record)
        else:
            untrusted_rows = True
    shared = sorted(set(current_groups) & set(previous_groups))
    one_sided = bool(set(current_groups) ^ set(previous_groups))
    if not shared:
        return _context("unknown", "unknown", [], "none")
    coverage_gap = one_sided or untrusted_rows
    states: list[str] = []
    raws: list[tuple[str, str | None, bool]] = []
    memberships: list[str] = []
    reasons: list[str] = []
    for key in shared:
        current_status, current_rules, current_actuals, current_unidentified = _slice_rules(current_groups[key])
        previous_status, previous_rules, previous_actuals, previous_unidentified = _slice_rules(previous_groups[key])
        if "unknown" in {current_status, previous_status}:
            states.append("unknown")
            raws.append(("unknown", None, False))
            memberships.append("stable")
            continue
        if "mixed" in {current_status, previous_status}:
            states.append("mixed")
            raws.append(("not_comparable", None, True))
            memberships.append("stable")
            continue
        difference, unknown_optional = _reasons(previous_rules or (), current_rules or ())
        if unknown_optional and difference:
            states.append("mixed")
        elif unknown_optional:
            states.append("unknown")
        else:
            states.append("changed" if difference else "unchanged")
            reasons.extend(difference)
        current_ids = set(current_actuals)
        previous_ids = set(previous_actuals)
        if current_unidentified or previous_unidentified:
            memberships.append("unknown")
        elif current_ids != previous_ids:
            memberships.append("changed")
        else:
            memberships.append("stable")
        raws.append(_raw_between(current_rules, current_actuals, previous_rules, previous_actuals))
    if coverage_gap:
        memberships.append("changed")
    state = _aggregate_state(states)
    raw, proven, kpi_gap = _aggregate_raw(state, raws)
    if coverage_gap:
        kpi_gap = True
    return _context(state, raw, reasons, _aggregate_membership(memberships), proven, kpi_gap)


def previous_calendar_month(year: int, month: str) -> tuple[int, str] | None:
    if month not in MONTHS:
        return None
    index = MONTHS.index(month)
    if index == 0:
        return year - 1, MONTHS[-1]
    return year, MONTHS[index - 1]


def compare_adjacent_records(
    records: list[Any] | None,
    *,
    year: int,
    month: str,
    team: str | None = None,
    position: str | None = None,
) -> dict[str, Any]:
    """Use only the named month and the immediately previous calendar month."""
    previous = previous_calendar_month(int(year), str(month))
    if previous is None:
        return _context("unavailable", "unknown", [], "none")
    previous_year, previous_month = previous

    def selected(target_year: int, target_month: str) -> list[Any]:
        chosen = []
        for record in records or []:
            record_year = _get(record, "year")
            try:
                same_year = int(record_year) == int(target_year)
            except (TypeError, ValueError):
                same_year = False
            if not same_year or _text(_get(record, "month")) != target_month:
                continue
            if team is not None and _text(_get(record, "team")) != team:
                continue
            if position is not None and _text(_get(record, "position")) != position:
                continue
            chosen.append(record)
        return chosen

    return compare_scoring_basis(
        selected(int(year), str(month)),
        selected(previous_year, previous_month),
    )
