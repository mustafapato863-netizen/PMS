"""Canonical data contract for the UAE Executive Performance Summary.

The detailed Offshore deck and the CEO deck have different jobs.  This module
is the boundary between live PMS rows and the CEO presentation: it resolves a
single current population, a like-for-like comparison population, direction-
aware KPI loss, deterministic department priority, and action completeness.

It intentionally accepts both Pydantic records and plain dictionaries.  That
keeps the contract easy to test without a database and makes it safe to reuse
from the report service, background jobs, and future API previews.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime
from statistics import mean
from typing import Any, Iterable

from services.insights_report_service import kpi_achievement, weighted_impact
from services.kpi_aggregation import aggregate_kpi_metric, configured_weight


MONTHS = {
    name: index
    for index, name in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        1,
    )
}
MONTH_NAMES = {number: name for name, number in MONTHS.items()}

TARGET_SCORE = 100.0
ACTION_SCORE_THRESHOLD = 70.0
INVESTIGATION_REQUIRED = "Investigation Required — cause validation is not recorded"

# The weights are deliberately public.  They are part of the report contract,
# are deterministic, and are included in each department's appendix row.
PRIORITY_WEIGHTS = {
    "target_gap": 40.0,
    "negative_mom": 20.0,
    "weighted_kpi_loss": 25.0,
    "employees_affected": 10.0,
    "unresolved_actions": 5.0,
}


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    result = " ".join(str(value).replace("\n", " ").split()).strip()
    return result or fallback


def _month_number(value: Any) -> int | None:
    number = _number(value)
    if number is not None and 1 <= int(number) <= 12:
        return int(number)
    return MONTHS.get(_text(value).title())


def period_key(year: Any, month: Any) -> tuple[int, int] | None:
    year_number = _number(year)
    month_number = _month_number(month)
    if year_number is None or month_number is None:
        return None
    return int(year_number), month_number


def period_label(period: tuple[int, int] | None) -> str:
    if not period:
        return "Selected period"
    return f"{MONTH_NAMES.get(period[1], period[1])} {period[0]}"


def normalize_direction(value: Any) -> str:
    normalized = _text(value, "higher_better").casefold().replace("-", "_").replace(" ", "_")
    return "lower_better" if normalized in {
        "lower_better",
        "lower_is_better",
        "lowerisbetter",
        "lower",
    } or "lower" in normalized else "higher_better"


def _normalize_record(record: Any) -> dict[str, Any]:
    evaluation = _value(record, "evaluation") or {}
    score = _number(_value(evaluation, "score"))
    raw_kpis = _value(record, "kpis")
    if raw_kpis is None:
        raw_kpis = _value(record, "kpi_values", [])
    root_cause = _value(evaluation, "root_cause") or _value(record, "root_cause")
    if not isinstance(root_cause, dict):
        root_cause = {
            "text": _text(_value(root_cause, "text") or _value(root_cause, "cause"))
        } if root_cause else {}
    employee_id = _text(_value(record, "employee_id"))
    employee_name = _text(_value(record, "employee_name"), "Unknown employee")
    team = _text(_value(record, "team"), "Department not available")
    position = _text(
        _value(record, "position") or _value(record, "position_name"),
        "Function not available",
    )
    kpis: list[dict[str, Any]] = []
    for raw in raw_kpis or []:
        if isinstance(raw, dict):
            kpis.append(dict(raw))
    return {
        "employee_id": employee_id,
        "employee_name": employee_name,
        "team": team,
        "position": position,
        "region": _text(_value(record, "region")),
        "performance_level": _text(_value(record, "performance_level"), "Employee"),
        "status": _text(_value(record, "status")),
        "grade": _text(_value(evaluation, "grade") or _value(record, "grade")),
        "score": score,
        "year": _value(record, "year"),
        "month": _value(record, "month"),
        "period": period_key(_value(record, "year"), _value(record, "month")),
        "root_cause_text": _text(
            _value(root_cause, "text")
            or _value(root_cause, "cause")
            or _value(root_cause, "description")
        ),
        "kpis": kpis,
    }


def _entity_key(record: dict[str, Any]) -> str:
    return _text(record.get("employee_id")) or "|".join(
        (_text(record.get("team")), _text(record.get("position")), _text(record.get("performance_level")))
    )


def _score(records: Iterable[dict[str, Any]]) -> float | None:
    by_entity: dict[str, list[float]] = defaultdict(list)
    for record in records:
        score = _number(record.get("score"))
        if score is not None:
            by_entity[_entity_key(record)].append(score)
    values = [mean(scores) for scores in by_entity.values() if scores]
    return mean(values) if values else None


def _employee_scores(records: Iterable[dict[str, Any]]) -> dict[str, float]:
    by_entity: dict[str, list[float]] = defaultdict(list)
    for record in records:
        score = _number(record.get("score"))
        if score is not None:
            by_entity[_entity_key(record)].append(score)
    return {key: mean(values) for key, values in by_entity.items() if values}


def _definition(raw: dict[str, Any], definitions: list[dict[str, Any]]) -> dict[str, Any]:
    raw_key = _text(raw.get("kpi_key") or raw.get("key") or raw.get("label"), "KPI")
    raw_label = _text(raw.get("label") or raw_key, raw_key)
    match = next(
        (
            item for item in definitions
            if _text(item.get("key")).casefold() == raw_key.casefold()
            or _text(item.get("label")).casefold() == raw_label.casefold()
        ),
        {},
    )
    merged = {**dict(match), **dict(raw)}
    merged["key"] = raw_key
    merged["label"] = _text(match.get("label") or raw.get("label") or raw_key, raw_key)
    merged["unit"] = _text(raw.get("unit") or match.get("unit"))
    merged["direction"] = normalize_direction(raw.get("direction") or match.get("direction"))
    return merged


def _kpi_identity(raw: dict[str, Any], definitions: list[dict[str, Any]]) -> tuple[str, str, str]:
    definition = _definition(raw, definitions)
    return (
        _text(definition.get("label"), "KPI").casefold(),
        _text(definition.get("unit")).casefold(),
        normalize_direction(definition.get("direction")),
    )


def _kpi_rows(records: Iterable[dict[str, Any]], definitions: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]]:
    groups: dict[tuple[str, str, str], list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for record in records:
        for raw in record.get("kpis") or []:
            definition = _definition(raw, definitions)
            groups[_kpi_identity(raw, definitions)].append((record, raw, definition))
    return groups


def _comparable_rows(current: list[dict[str, Any]], previous: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_keys = {_entity_key(row) for row in current if _entity_key(row)}
    if current_keys:
        # Employee IDs are the like-for-like boundary when they exist.  Do
        # not silently broaden to a team average when the selected comparison
        # period has different employees; that would fabricate MoM.
        if any(_text(row.get("employee_id")) for row in current):
            return [row for row in previous if _entity_key(row) in current_keys]
        matched = [row for row in previous if _entity_key(row) in current_keys]
        if matched:
            return matched
    current_departments = {_text(row.get("team")).casefold() for row in current}
    return [row for row in previous if _text(row.get("team")).casefold() in current_departments]


def _kpi_metrics(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    definitions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current_groups = _kpi_rows(current, definitions)
    previous_groups = _kpi_rows(previous, definitions)
    rows: list[dict[str, Any]] = []
    for identity, entries in current_groups.items():
        first_definition = entries[0][2]
        raw_values = [raw for _, raw, _ in entries]
        metric = aggregate_kpi_metric(raw_values, first_definition)
        achievement = kpi_achievement(
            metric.actual,
            metric.target,
            first_definition.get("direction"),
            None,
        )
        # A configured weight is normally present on every source row.  Keep
        # the measured mean here; missing weights are filled equally below.
        weights = [configured_weight(raw, first_definition) for _, raw, _ in entries]
        measured_weights = [weight for weight in weights if weight is not None]
        weight = mean(measured_weights) if measured_weights else None
        affected_ids: set[str] = set()
        affected_departments: set[str] = set()
        affected_functions: dict[tuple[str, str], set[str]] = defaultdict(set)
        by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record, raw, _definition_row in entries:
            by_entity[_entity_key(record)].append(raw)
        for entity, values in by_entity.items():
            entity_metric = aggregate_kpi_metric(values, first_definition)
            entity_achievement = kpi_achievement(
                entity_metric.actual,
                entity_metric.target,
                first_definition.get("direction"),
                None,
            )
            if entity_achievement is not None and entity_achievement < 1:
                affected_ids.add(entity)
                matching = next((record for record, _, _ in entries if _entity_key(record) == entity), None)
                if matching:
                    affected_departments.add(_text(matching.get("team"), "Department not available"))
                    affected_functions[(_text(matching.get("team")), _text(matching.get("position")))].add(entity)
        previous_entries = previous_groups.get(identity, [])
        previous_metric = aggregate_kpi_metric([raw for _, raw, _ in previous_entries], first_definition) if previous_entries else None
        previous_achievement = (
            kpi_achievement(
                previous_metric.actual,
                previous_metric.target,
                first_definition.get("direction"),
                None,
            )
            if previous_entries and previous_metric
            else None
        )
        achievement_pct = achievement * 100 if achievement is not None else None
        baseline_achievement_pct = previous_achievement * 100 if previous_achievement is not None else None
        rows.append(
            {
                "key": first_definition.get("key"),
                "label": first_definition.get("label"),
                "unit": first_definition.get("unit"),
                "direction": first_definition.get("direction"),
                "actual": metric.actual,
                "target": metric.target,
                "baseline_actual": previous_metric.actual if previous_entries and previous_metric else None,
                "baseline_target": previous_metric.target if previous_entries and previous_metric else None,
                "achievement": achievement,
                "achievement_pct": achievement_pct,
                "baseline_achievement_pct": baseline_achievement_pct,
                "mom": achievement_pct - baseline_achievement_pct if achievement_pct is not None and baseline_achievement_pct is not None else None,
                "achievement_gap": max(0.0, 100.0 - achievement_pct) if achievement_pct is not None else None,
                "gap": max(0.0, 100.0 - achievement_pct) if achievement_pct is not None else None,
                "weight": weight,
                "weighted_loss": 0.0,
                "status": (
                    "Data Not Available" if achievement is None
                    else "On Track" if achievement >= 1
                    else "Watch" if achievement >= 0.7
                    else "Requires Action"
                ),
                "employees_affected": len(affected_ids),
                "affected_count": len(affected_ids),
                "affected_departments": sorted(affected_departments, key=str.casefold),
                "affected_functions": [
                    {
                        "department": department,
                        "function": function or "Function not available",
                        "employee_count": len(ids),
                    }
                    for (department, function), ids in sorted(affected_functions.items())
                ],
                "source_keys": sorted({
                    _text(raw.get("kpi_key") or raw.get("key") or raw.get("label"))
                    for _, raw, _ in entries
                    if _text(raw.get("kpi_key") or raw.get("key") or raw.get("label"))
                }),
            }
        )
    measured = [row for row in rows if row.get("weight") is not None and row.get("weight") > 0]
    missing = [row for row in rows if row.get("weight") is None or row.get("weight") <= 0]
    fallback_weight = 1.0 / len(rows) if rows else 0.0
    if missing:
        fallback_weight = (1.0 - sum(float(row.get("weight") or 0.0) for row in measured)) / len(missing) if measured else fallback_weight
    for row in rows:
        if row.get("weight") is None or row.get("weight") <= 0:
            row["weight"] = max(0.0, fallback_weight)
        row["weighted_loss"] = weighted_impact(
            (row.get("achievement_pct") / 100.0) if row.get("achievement_pct") is not None else None,
            row.get("weight"),
        )
    return sorted(rows, key=lambda row: (-float(row.get("weighted_loss") or 0.0), _text(row.get("label")).casefold()))


def _action_period(action: Any) -> tuple[int, int] | None:
    return period_key(_value(action, "year"), _value(action, "month"))


def _action_team(action: Any) -> str:
    team = _value(action, "team")
    if team and not isinstance(team, str):
        team = _value(team, "display_name") or _value(team, "name") or str(team)
    return _text(team, "Selected scope")


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _missing(value: Any, fallback: str) -> bool:
    return _text(value).casefold() in {"", fallback.casefold(), "none", "null", "not available", "not recorded"}


def _action_rows(
    actions: Iterable[Any],
    current_period: tuple[int, int] | None,
    current_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current_entities = {_entity_key(row) for row in current_records}
    current_by_id = {_text(row.get("employee_id")): row for row in current_records if _text(row.get("employee_id"))}
    period_end = None
    if current_period:
        period_end = date(current_period[0], current_period[1], calendar.monthrange(*current_period)[1])
    result: list[dict[str, Any]] = []
    for source in actions or []:
        source_period = _action_period(source)
        if current_period and source_period != current_period:
            continue
        employee_id = _text(_value(source, "employee_id"))
        employee = _value(source, "employee")
        employee_id = employee_id or _text(_value(employee, "employee_id"))
        evidence = current_by_id.get(employee_id)
        team = _action_team(source)
        if team == "Selected scope" and evidence:
            team = _text(evidence.get("team"), "Selected scope")
        # The action service has already applied authorization and report
        # filters.  This extra guard prevents a hand-built payload from
        # attaching an employee action outside the current population.
        if employee_id and current_entities and employee_id not in current_entities and not evidence:
            continue
        owner = _value(source, "owner") or _value(source, "owner_display")
        due_date = _value(source, "due_date") or _value(source, "due_date_display")
        success = _value(source, "success_metric") or _value(source, "success_metric_display")
        status = _text(_value(source, "status") or _value(source, "status_display"), "Status not recorded")
        normalized_status = status.casefold()
        is_open = normalized_status not in {"completed", "closed", "resolved", "cancelled", "canceled"}
        due = _date_value(due_date)
        result.append(
            {
                "department": team,
                "workstream": team,
                "kpi": _text(_value(source, "linked_kpi_key"), "Issue not linked"),
                "linked_kpi_key": _text(_value(source, "linked_kpi_key")),
                "action": _text(_value(source, "action_text") or _value(source, "action_display"), "Action text needed"),
                "owner": _text(owner),
                "due_date": due.isoformat() if due else _text(due_date),
                "status": status,
                "priority": _text(_value(source, "priority")),
                "success_measure": _text(success),
                "success_metric": _text(success),
                "evidence_reference": _text(_value(source, "evidence_reference") or _value(source, "evidence_display")),
                "root_cause_note": _text(_value(source, "root_cause_note")),
                "employee_id": employee_id,
                "employee_name": "" if employee_id else "Authorized group scope",
                "position": _text(_value(source, "position") or (evidence or {}).get("position"), "Function not available"),
                "employee_count": 1 if employee_id else 0,
                "is_proposed": bool(_value(source, "is_proposed")),
                "is_open": is_open,
                "missing_owner": _missing(owner, "Owner needed"),
                "missing_due_date": _missing(due_date, "Due date needed"),
                "missing_success_measure": _missing(success, "Success metric needed"),
                "overdue": bool(is_open and due and period_end and due < period_end),
            }
        )
    return result


def _status(score: float | None) -> str:
    if score is None:
        return "Data Not Available"
    if score < 70:
        return "Requires Action"
    if score < 90:
        return "Watch"
    return "On Track"


def _priority_components(
    score: float | None,
    baseline: float | None,
    target: float,
    weighted_loss: float,
    affected: int,
    employee_count: int,
    unresolved_actions: int,
    open_actions: int,
) -> dict[str, float]:
    gap = max(0.0, target - (score or 0.0)) / max(target, 1.0)
    negative_mom = max(0.0, (baseline or score or 0.0) - (score or 0.0)) / max(target, 1.0)
    loss = max(0.0, weighted_loss) / 100.0
    affected_ratio = affected / max(employee_count, 1)
    unresolved_ratio = unresolved_actions / max(open_actions, 1)
    return {
        "target_gap": round(gap * PRIORITY_WEIGHTS["target_gap"], 4),
        "negative_mom": round(negative_mom * PRIORITY_WEIGHTS["negative_mom"], 4),
        "weighted_kpi_loss": round(loss * PRIORITY_WEIGHTS["weighted_kpi_loss"], 4),
        "employees_affected": round(min(1.0, affected_ratio) * PRIORITY_WEIGHTS["employees_affected"], 4),
        "unresolved_actions": round(min(1.0, unresolved_ratio) * PRIORITY_WEIGHTS["unresolved_actions"], 4),
    }


def _safe_sort_text(value: Any) -> str:
    return _text(value).casefold()


def build_uae_executive_summary_contract(
    records: Iterable[Any],
    *,
    current_period: tuple[int, int] | None = None,
    comparison_period: tuple[int, int] | None = None,
    definitions: Iterable[dict[str, Any]] | None = None,
    actions: Iterable[Any] | None = None,
    known_departments: Iterable[str] | None = None,
    period_label_override: str | None = None,
    scope_label: str = "UAE",
    filters: dict[str, Any] | None = None,
    aggregate_only: bool = True,
    target_score: float = TARGET_SCORE,
) -> dict[str, Any]:
    """Return the validated, deterministic UAE executive report contract."""

    normalized = [_normalize_record(record) for record in records or []]
    normalized = [row for row in normalized if row.get("period")]
    definitions_list = [dict(item) for item in definitions or [] if isinstance(item, dict)]
    if current_period is None:
        periods = sorted({row["period"] for row in normalized if row.get("period")})
        current_period = periods[-1] if periods else None
    current_records = [row for row in normalized if row.get("period") == current_period and row.get("score") is not None]
    current_all_rows = [row for row in normalized if row.get("period") == current_period]
    current_departments = sorted(
        {_text(row.get("team"), "Department not available") for row in current_records},
        key=str.casefold,
    )
    known = {
        _text(value)
        for value in (known_departments or [])
        if _text(value)
    }
    known.update(_text(row.get("team"), "Department not available") for row in normalized)
    known.update(current_departments)
    no_current_departments = sorted(known - set(current_departments), key=str.casefold)

    previous_records: list[dict[str, Any]] = []
    baseline_period: tuple[int, int] | None = None
    if comparison_period:
        explicit = [row for row in normalized if row.get("period") == comparison_period and row.get("score") is not None]
        comparable = _comparable_rows(current_records, explicit)
        if comparable:
            previous_records = comparable
            baseline_period = comparison_period
    if not previous_records and comparison_period is None and current_period:
        prior_periods = sorted({row["period"] for row in normalized if row.get("period") and row["period"] < current_period}, reverse=True)
        for candidate in prior_periods:
            candidate_rows = [row for row in normalized if row.get("period") == candidate and row.get("score") is not None]
            comparable = _comparable_rows(current_records, candidate_rows)
            if comparable:
                previous_records = comparable
                baseline_period = candidate
                break

    current_entity_scores = _employee_scores(current_records)
    previous_by_entity = _employee_scores(previous_records)
    overall_score = _score(current_records)
    baseline_score = _score(previous_records)
    mom = overall_score - baseline_score if overall_score is not None and baseline_score is not None else None

    current_actions = _action_rows(actions or [], current_period, current_records)
    recorded_actions = [row for row in current_actions if not row.get("is_proposed")]
    open_recorded_actions = [row for row in recorded_actions if row.get("is_open")]

    departments: list[dict[str, Any]] = []
    for department in current_departments:
        rows = [row for row in current_records if _text(row.get("team"), "Department not available") == department]
        previous_rows = [row for row in previous_records if _text(row.get("team"), "Department not available") == department]
        previous_rows = _comparable_rows(rows, previous_rows)
        department_score = _score(rows)
        department_baseline = _score(previous_rows)
        department_mom = department_score - department_baseline if department_score is not None and department_baseline is not None else None
        department_kpis = _kpi_metrics(rows, previous_rows, definitions_list)
        department_loss = sum(float(kpi.get("weighted_loss") or 0.0) for kpi in department_kpis)
        entity_scores = _employee_scores(rows)
        affected_employees = sum(score < ACTION_SCORE_THRESHOLD for score in entity_scores.values())
        department_actions = [row for row in open_recorded_actions if _safe_sort_text(row.get("department")) == _safe_sort_text(department)]
        unresolved = sum(
            bool(row.get("missing_owner") or row.get("missing_due_date") or row.get("missing_success_measure"))
            for row in department_actions
        )
        components = _priority_components(
            department_score,
            department_baseline,
            target_score,
            department_loss,
            affected_employees,
            len(entity_scores),
            unresolved,
            len(department_actions),
        )
        leading = department_kpis[0] if department_kpis else {}
        departments.append(
            {
                "department": department,
                "name": department,
                "current_score": department_score,
                "score": department_score,
                "baseline": department_baseline,
                "mom": department_mom,
                "movement": department_mom,
                "target": target_score,
                "target_gap": target_score - department_score if department_score is not None else None,
                "gap_to_target": target_score - department_score if department_score is not None else None,
                "status": _status(department_score),
                "record_count": len(rows),
                "employee_count": len(entity_scores),
                "employees_requiring_action": affected_employees,
                "affected_employee_count": affected_employees,
                "open_actions": len(department_actions),
                "action_count": len(department_actions),
                "missing_owner_count": sum(bool(row.get("missing_owner")) for row in department_actions),
                "missing_due_date_count": sum(bool(row.get("missing_due_date")) for row in department_actions),
                "leading_kpi_driver": leading.get("label"),
                "leading_driver": leading.get("label"),
                "weighted_loss": department_loss,
                "kpis": department_kpis,
                "action_status": (
                    "Owner / due unresolved" if unresolved
                    else "Open" if department_actions
                    else "No open actions"
                ),
                "priority_components": components,
                "priority_score": round(sum(components.values()), 4),
                "positions": sorted({_text(row.get("position"), "Function not available") for row in rows}, key=str.casefold),
            }
        )
    departments.sort(
        key=lambda row: (
            -float(row.get("priority_score") or 0.0),
            _number(row.get("current_score")) is None,
            _safe_sort_text(row.get("department")),
        )
    )
    for index, row in enumerate(departments, 1):
        row["rank"] = index

    all_kpis = _kpi_metrics(current_records, previous_records, definitions_list)
    # Attach department impact to each driver from the department rollups.
    for driver in all_kpis:
        labels = {_safe_sort_text(value) for value in (driver.get("source_keys") or [])}
        labels.add(_safe_sort_text(driver.get("key")))
        affected_departments: set[str] = set()
        affected_functions: list[dict[str, Any]] = []
        for department in departments:
            match = next(
                (
                    kpi for kpi in department.get("kpis") or []
                    if _safe_sort_text(kpi.get("label")) == _safe_sort_text(driver.get("label"))
                    or _safe_sort_text(kpi.get("key")) in labels
                ),
                None,
            )
            if match and float(match.get("weighted_loss") or 0.0) > 0:
                affected_departments.add(department["department"])
                for function in match.get("affected_functions") or []:
                    affected_functions.append(function)
        driver["affected_departments"] = sorted(affected_departments, key=str.casefold)
        driver["affected_scope"] = list(driver["affected_departments"])
        driver["affected_functions"] = affected_functions
        driver["employees_affected"] = driver.get("affected_count", 0)
    all_kpis.sort(key=lambda row: (-float(row.get("weighted_loss") or 0.0), _safe_sort_text(row.get("label"))))
    largest_driver = all_kpis[0] if all_kpis else None

    risk_map = {
        "Requires Action": [row for row in departments if row.get("status") == "Requires Action"],
        "Watch": [row for row in departments if row.get("status") == "Watch"],
        "On Track": [row for row in departments if row.get("status") == "On Track"],
        "Data Not Available": [
            {"department": department, "name": department, "status": "Data Not Available"}
            for department in no_current_departments
        ],
    }
    largest_decline = min(
        (row for row in departments if row.get("mom") is not None),
        key=lambda row: (float(row.get("mom")), _safe_sort_text(row.get("department"))),
        default=None,
    )
    best_department = max(
        departments,
        key=lambda row: (_number(row.get("current_score")) is not None, _number(row.get("current_score")) or -1, _safe_sort_text(row.get("department"))),
        default=None,
    )

    current_valid_periods = sorted(
        {
            row["period"]
            for row in normalized
            if row.get("period")
            and row.get("score") is not None
            and (current_period is None or row["period"] <= current_period)
        }
    )
    comparable_entities = {_entity_key(row) for row in current_records}
    comparable_departments = set(current_departments)
    trend: list[dict[str, Any]] = []
    for period in current_valid_periods:
        period_rows = [row for row in normalized if row.get("period") == period and row.get("score") is not None]
        if comparable_entities:
            same_entities = [row for row in period_rows if _entity_key(row) in comparable_entities]
            if same_entities:
                period_rows = same_entities
        elif comparable_departments:
            period_rows = [row for row in period_rows if _text(row.get("team")).casefold() in {_text(v).casefold() for v in comparable_departments}]
        period_score = _score(period_rows)
        if period_score is not None:
            trend.append({
                "key": f"{period[0]}-{period[1]:02d}",
                "label": period_label(period),
                "score": period_score,
                "target": target_score,
                "record_count": len(period_rows),
                "department_count": len({_text(row.get("team")) for row in period_rows}),
            })
    trend_by_period = {row["key"]: row for row in trend}
    best_period = max(trend, key=lambda row: (row["score"], row["key"]), default=None)
    worst_period = min(trend, key=lambda row: (row["score"], row["key"]), default=None)
    net_movement = trend[-1]["score"] - trend[0]["score"] if len(trend) > 1 else None

    open_actions = len(open_recorded_actions)
    missing_owner = sum(bool(row.get("missing_owner")) for row in open_recorded_actions)
    missing_due = sum(bool(row.get("missing_due_date")) for row in open_recorded_actions)
    missing_success = sum(bool(row.get("missing_success_measure")) for row in open_recorded_actions)
    overdue = sum(bool(row.get("overdue")) for row in open_recorded_actions)
    high_priority_unresolved = [
        row for row in open_recorded_actions
        if _text(row.get("priority")).casefold() in {"high", "critical", "urgent"}
        and (row.get("missing_owner") or row.get("missing_due_date") or row.get("missing_success_measure"))
    ]
    actions_by_department: dict[str, int] = defaultdict(int)
    for row in open_recorded_actions:
        actions_by_department[_text(row.get("department"), "Selected scope")] += 1

    employee_action_rows: list[dict[str, Any]] = []
    for entity, score in sorted(current_entity_scores.items(), key=lambda item: (item[1], item[0])):
        if score >= ACTION_SCORE_THRESHOLD:
            continue
        source = next((row for row in current_records if _entity_key(row) == entity), {})
        employee_action_rows.append({
            "department": _text(source.get("team"), "Department not available"),
            "role_function": _text(source.get("position"), "Function not available"),
            "score": score,
            "employee_count": 1,
            "employee_name": "" if aggregate_only else _text(source.get("employee_name"), "Unknown employee"),
            "employee_id": "" if aggregate_only else _text(source.get("employee_id")),
        })

    # Build a small, evidence-first decision list.  It is intentionally based
    # only on measured gaps and stored action evidence; it never guesses a
    # root cause from a KPI label.
    decisions: list[dict[str, Any]] = []
    for driver in all_kpis:
        if float(driver.get("weighted_loss") or 0.0) <= 0:
            continue
        affected = driver.get("affected_departments") or ["UAE scope"]
        matching = next(
            (
                action for action in open_recorded_actions
                if _safe_sort_text(action.get("linked_kpi_key")) in {
                    _safe_sort_text(driver.get("key")),
                    *[_safe_sort_text(key) for key in driver.get("source_keys") or []],
                }
            ),
            None,
        )
        confirmed = bool(matching and matching.get("root_cause_note") and matching.get("evidence_reference"))
        evidence_state = "Confirmed Root Cause" if confirmed else "Investigation Required"
        decisions.append({
            "issue": f"{driver.get('label')} is below target",
            "affected_scope": ", ".join(affected),
            "supporting_evidence": f"Current {_text(driver.get('actual'))} vs target {_text(driver.get('target'))}; achievement {_text(driver.get('achievement_pct'))}% ; weighted loss {_text(driver.get('weighted_loss'))}%.",
            "required_decision": "Confirm the intervention, accountable owner, and review cadence for this KPI gap.",
            "accountable_owner": _text((matching or {}).get("owner")) or "Owner needed",
            "commitment_date": _text((matching or {}).get("due_date")) or "Commitment date needed",
            "success_criterion": _text((matching or {}).get("success_metric")) or f"Recheck {driver.get('label')} actual vs target next review.",
            "evidence_state": evidence_state,
            "root_cause": "Confirmed Root Cause" if confirmed else INVESTIGATION_REQUIRED,
            "kpi": driver.get("label"),
            "weighted_loss": driver.get("weighted_loss"),
        })
        if len(decisions) >= 5:
            break
    if len(decisions) < 3:
        for department in departments:
            if department.get("status") not in {"Requires Action", "Watch"}:
                continue
            decisions.append({
                "issue": f"{department.get('department')} is {department.get('status').lower()}",
                "affected_scope": department.get("department"),
                "supporting_evidence": f"Current score {_text(department.get('current_score'))} vs target {_text(department.get('target'))}; {_text(department.get('employees_requiring_action'))} employee(s) below action threshold.",
                "required_decision": "Confirm department intervention and accountable management owner.",
                "accountable_owner": "Owner needed",
                "commitment_date": "Commitment date needed",
                "success_criterion": "Department score and leading KPI gap improve at the next review.",
                "evidence_state": "Investigation Required",
                "root_cause": INVESTIGATION_REQUIRED,
                "kpi": department.get("leading_kpi_driver"),
                "weighted_loss": department.get("weighted_loss"),
            })
            if len(decisions) >= 5:
                break

    coverage_rows = [
        {
            "department": department,
            "current_data": department in current_departments,
            "status": "Active" if department in current_departments else "No current data",
        }
        for department in sorted(known, key=str.casefold)
    ]
    department_rows = [
        {
            "rank": row.get("rank"),
            "department": row.get("department"),
            "current_score": row.get("current_score"),
            "baseline": row.get("baseline"),
            "mom": row.get("mom"),
            "target_gap": row.get("target_gap"),
            "status": row.get("status"),
            "leading_kpi_driver": row.get("leading_kpi_driver"),
            "employees_requiring_action": row.get("employees_requiring_action"),
            "open_actions": row.get("open_actions"),
            "priority_score": row.get("priority_score"),
            "priority_components": row.get("priority_components"),
        }
        for row in departments
    ]
    kpi_evidence_rows = [
        {
            "kpi": row.get("label"),
            "affected_department": ", ".join(row.get("affected_departments") or ["UAE scope"]),
            "current_actual": row.get("actual"),
            "baseline": row.get("baseline_actual"),
            "mom": row.get("mom"),
            "target": row.get("target"),
            "achievement": row.get("achievement_pct"),
            "achievement_gap": row.get("achievement_gap"),
            "direction": row.get("direction"),
            "weighted_loss": row.get("weighted_loss"),
            "status": row.get("status"),
            "employees_affected": row.get("employees_affected"),
        }
        for row in all_kpis
    ]
    driver_department_rows: list[dict[str, Any]] = []
    for driver in all_kpis:
        for function in driver.get("affected_functions") or []:
            driver_department_rows.append({
                "driver": driver.get("label"),
                "department": function.get("department"),
                "role_function": function.get("function"),
                "employees_affected": function.get("employee_count", 0),
                "required_action": "Confirm owner, intervention, and next-review evidence.",
            })

    active_department_count = len(current_departments)
    overall_status = _status(overall_score) if current_records else "No current UAE data"
    cover = {
        "active_departments": active_department_count,
        "employee_count": len(current_entity_scores),
        "open_actions": open_actions,
        "department_count": active_department_count,
    }
    next_period = (current_period[0] + 1, 1) if current_period and current_period[1] == 12 else (current_period[0], current_period[1] + 1) if current_period else None
    payload: dict[str, Any] = {
        "report_type": "uae_executive_summary",
        "period": current_period,
        "period_label": period_label_override or period_label(current_period),
        "comparison_period": baseline_period,
        "comparison_period_label": period_label(baseline_period) if baseline_period else None,
        "scope_label": scope_label or "UAE",
        "filters": dict(filters or {}),
        "aggregate_only": aggregate_only,
        "overall": {
            "current_score": overall_score,
            "score": overall_score,
            "baseline": baseline_score,
            "mom": mom,
            "movement": mom,
            "target": target_score,
            "gap_to_target": target_score - overall_score if overall_score is not None else None,
            "target_gap": target_score - overall_score if overall_score is not None else None,
            "status": overall_status,
        },
        "current_score": overall_score,
        "baseline": baseline_score,
        "mom": mom,
        "target": target_score,
        "gap_to_target": target_score - overall_score if overall_score is not None else None,
        "status": overall_status,
        "cover": cover,
        "active_departments": active_department_count,
        "department_count": active_department_count,
        "employee_count": len(current_entity_scores),
        "employees_requiring_action": len(employee_action_rows),
        "open_actions": open_actions,
        "open_action_count": open_actions,
        "assigned_owner_actions": sum(not row.get("missing_owner") for row in open_recorded_actions),
        "actions_with_due_date": sum(not row.get("missing_due_date") for row in open_recorded_actions),
        "missing_owners": missing_owner,
        "missing_owner_count": missing_owner,
        "missing_due_dates": missing_due,
        "missing_due_date_count": missing_due,
        "overdue_actions": overdue,
        "missing_success_measures": missing_success,
        "high_priority_unresolved": len(high_priority_unresolved),
        "actions_by_department": dict(sorted(actions_by_department.items(), key=lambda item: item[0].casefold())),
        "largest_kpi_driver": largest_driver,
        "largest_department_decline": largest_decline,
        "best_department": best_department,
        "departments": departments,
        "department_ranking": department_rows,
        "risk_map": risk_map,
        "no_current_departments": no_current_departments,
        "data_coverage": coverage_rows,
        "kpis": all_kpis,
        "drivers": all_kpis,
        "driver_department_impact": driver_department_rows,
        "trend": trend,
        "history": trend,
        "history_count": len(trend),
        "best_period": best_period,
        "worst_period": worst_period,
        "net_movement": net_movement,
        "departments_improving": sum(1 for row in departments if (row.get("mom") or 0) > 0),
        "departments_declining": sum(1 for row in departments if (row.get("mom") or 0) < 0),
        "actions": current_actions,
        "recorded_actions": recorded_actions,
        "raw_actions": recorded_actions,
        "decisions": decisions,
        "employee_priority_rows": employee_action_rows,
        "kpi_evidence_rows": kpi_evidence_rows,
        "department_scorecard_rows": department_rows,
        "action_rows": current_actions,
        "historical_rows": trend,
        "next_review": {
            "period": period_label(next_period),
            "expected_improvement": max(0.0, target_score - overall_score) if overall_score is not None else None,
            "top_kpi_gaps": [row.get("label") for row in all_kpis[:5] if row.get("achievement_gap")],
            "departments_requiring_action": [row.get("department") for row in risk_map["Requires Action"]],
            "success_criteria": "Recheck current score, KPI actuals versus target, action ownership, due dates, and closure evidence in the next period.",
            "commitments": "Confirm accountable owners and dates for every unresolved high-priority action.",
        },
        "warnings": (["No current UAE data is available for the selected period."] if not current_records else [])
        + ([f"{len(no_current_departments)} known department(s) have no current data and are shown only in Data Coverage."] if no_current_departments else []),
        "priority_formula": {
            "weights": dict(PRIORITY_WEIGHTS),
            "description": "Target gap + negative MoM + weighted KPI loss + affected employees + unresolved open actions; deterministic descending score with department-name tie break.",
        },
    }
    # Keep a single canonical population marker available to tests and future
    # consumers.  It is a count, never a second independently calculated list.
    payload["population"] = {
        "current_record_count": len(current_records),
        "current_employee_count": len(current_entity_scores),
        "active_department_count": active_department_count,
        "known_department_count": len(known),
        "current_period": current_period,
    }
    return payload


# Friendly aliases used by callers/tests that describe the contract as a
# snapshot rather than a presentation payload.
build_uae_executive_snapshot = build_uae_executive_summary_contract
build_uae_executive_summary_data = build_uae_executive_summary_contract


__all__ = [
    "ACTION_SCORE_THRESHOLD",
    "INVESTIGATION_REQUIRED",
    "PRIORITY_WEIGHTS",
    "TARGET_SCORE",
    "build_uae_executive_summary_contract",
    "build_uae_executive_snapshot",
    "build_uae_executive_summary_data",
    "normalize_direction",
    "period_key",
    "period_label",
]
