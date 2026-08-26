"""Build the single, filtered snapshot consumed by the executive Insights deck.

The report exporter is deliberately kept presentation-only.  This module owns
the small amount of report-specific shaping needed to make the story coherent:
period rollups, direction-aware KPI evidence, weighted loss ranking, employee
impact, evidence states, and action completeness.  It delegates KPI math to
the canonical aggregation helpers used by the dashboard.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any, Iterable

from services.kpi_aggregation import (
    AggregatedKpiMetric,
    aggregate_kpi_metric,
    capped_achievement,
    configured_weight,
)


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
MONTH_NAMES = {value: key for key, value in MONTHS.items()}
EVIDENCE_STATES = (
    "Confirmed cause",
    "Evidence recorded — cause pending confirmation",
    "KPI signal only",
    "No evidence recorded",
)
TREND_THRESHOLD = 1.0


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _text(value: Any, fallback: str = "") -> str:
    return " ".join(str(value or fallback).split())


def _record_value(record: Any, key: str, default: Any = None) -> Any:
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


def _period_key(value: Any) -> tuple[int, int] | None:
    if isinstance(value, (tuple, list)) and len(value) == 2:
        year = _number(value[0])
        month = _number(value[1])
        return (int(year), int(month)) if year and month else None
    if isinstance(value, dict):
        year = _number(value.get("year"))
        raw_month = value.get("month")
        month = _number(raw_month) or MONTHS.get(str(raw_month))
        return (int(year), int(month)) if year and month else None
    raw = _text(value)
    if "-" in raw:
        iso_parts = raw.split("-")
        if len(iso_parts) >= 2:
            year = _number(iso_parts[0])
            month = _number(iso_parts[1])
            if year and month:
                return int(year), int(month)
    parts = raw.replace("–", "-").split()
    if len(parts) >= 2:
        month = MONTHS.get(parts[0].title())
        year = _number(parts[1])
        if month and year:
            return int(year), month
    return None


def period_label(period: tuple[int, int] | None) -> str:
    if not period:
        return "Selected period"
    return f"{MONTH_NAMES.get(period[1], period[1])} {period[0]}"


def normalize_ratio(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    if number > 2:
        number /= 100
    return max(0.0, min(number, 1.0))


def kpi_achievement(
    actual: Any,
    target: Any,
    direction: str | None,
    stored_ratio: Any = None,
) -> float | None:
    """Return a capped 0–1 achievement using the canonical scoring rule.

    Raw actual/target values always take precedence over a persisted ratio.  A
    persisted ratio is only a safe fallback when the raw values are absent.
    This prevents a lower-is-better KPI from appearing healthy merely because
    a target field exists or because an old ratio was stored on the row.
    """

    actual_number = _number(actual)
    target_number = _number(target)
    if actual_number is not None and target_number is not None:
        return capped_achievement(
            AggregatedKpiMetric(actual=actual_number, target=target_number),
            direction,
        )
    if actual_number is not None or target_number is not None:
        return None
    return normalize_ratio(stored_ratio)


def kpi_gap(achievement: float | None) -> float | None:
    """Return the signed achievement gap as a percentage."""

    return None if achievement is None else (achievement * 100) - 100


def weighted_impact(achievement: float | None, weight: float | None) -> float:
    """Return weighted negative contribution as a percentage of total score."""

    if achievement is None or weight is None:
        return 0.0
    return max(0.0, 1.0 - achievement) * max(0.0, weight) * 100


def _trend_state(scores: list[float]) -> dict[str, Any]:
    """Classify only the amount of history the snapshot can support.

    Scores are already canonical period-level performance percentages.  Two
    periods can show movement, but they cannot establish a sustained trend.
    Three or more periods use the chronological movement pattern and net
    change, with a one-percentage-point tolerance for normal variation.
    """

    ordered = [float(score) for score in scores if score is not None]
    count = len(ordered)
    if not count:
        return {
            "key": "no_data",
            "label": "No measured history",
            "headline": "No performance data is available for the selected scope.",
            "direction": None,
            "sustained": False,
        }
    if count == 1:
        return {
            "key": "single_period",
            "label": "Trend unavailable",
            "headline": "Trend unavailable — only one measured period.",
            "direction": None,
            "sustained": False,
        }

    deltas = [current - previous for previous, current in zip(ordered, ordered[1:])]
    latest_movement = deltas[-1]
    net_movement = ordered[-1] - ordered[0]
    if count == 2:
        if latest_movement > TREND_THRESHOLD:
            headline = "Performance moved up between the two measured periods; sustained trend not established."
            direction = "upward movement"
        elif latest_movement < -TREND_THRESHOLD:
            headline = "Performance moved down between the two measured periods; sustained trend not established."
            direction = "downward movement"
        else:
            headline = "Performance changed within the available two-period history; sustained trend not established."
            direction = "limited movement"
        return {
            "key": "movement_only",
            "label": "Movement only",
            "headline": headline,
            "direction": direction,
            "sustained": False,
        }

    positive = sum(delta > TREND_THRESHOLD for delta in deltas)
    negative = sum(delta < -TREND_THRESHOLD for delta in deltas)
    if net_movement > TREND_THRESHOLD and positive >= negative:
        return {
            "key": "improving",
            "label": "Improving",
            "headline": "Performance is improving across the available periods, but the target gap remains unresolved."
            if ordered[-1] < 100
            else "Performance is improving toward target.",
            "direction": "improving",
            "sustained": True,
        }
    if net_movement < -TREND_THRESHOLD and negative >= positive:
        return {
            "key": "declining",
            "label": "Declining",
            "headline": "Performance is declining across the available periods and requires intervention.",
            "direction": "declining",
            "sustained": True,
        }
    return {
        "key": "stable",
        "label": "Stable",
        "headline": "Performance is stable across the available periods.",
        "direction": "stable",
        "sustained": True,
    }


def _definition_for(raw: dict[str, Any], definitions: list[dict[str, Any]]) -> dict[str, Any]:
    key = _text(raw.get("kpi_key") or raw.get("key") or raw.get("label") or "KPI")
    label = _text(raw.get("label") or key)
    match = next(
        (
            definition
            for definition in definitions
            if _text(definition.get("key")) == key
            or _text(definition.get("label")).casefold() == label.casefold()
        ),
        None,
    )
    if match:
        return {
            "key": key,
            "label": label,
            "unit": raw.get("unit") or "",
            "direction": raw.get("direction") or "higher_better",
            "aggregation": raw.get("aggregation"),
            "weight": raw.get("weight") or raw.get("weight_applied"),
            **dict(match),
        }
    return {
        "key": key,
        "label": label,
        "unit": raw.get("unit") or "",
        "direction": raw.get("direction") or "higher_better",
        "aggregation": raw.get("aggregation"),
        "weight": raw.get("weight") or raw.get("weight_applied"),
    }


def _normalize_record(record: Any) -> dict[str, Any]:
    root_cause = _record_value(record, "root_cause") or {}
    if not isinstance(root_cause, dict):
        root_cause = {}
    raw_kpis = _record_value(record, "kpis", None)
    if raw_kpis is None:
        raw_kpis = _record_value(record, "kpi_values", [])
    return {
        "employee_id": _text(_record_value(record, "employee_id")),
        "employee_name": _text(_record_value(record, "employee_name"), "Unknown employee"),
        "team": _text(_record_value(record, "team"), "Unassigned"),
        "position": _text(_record_value(record, "position") or _record_value(record, "position_name"), "Unassigned"),
        "region": _text(_record_value(record, "region")),
        "year": _record_value(record, "year"),
        "month": _record_value(record, "month"),
        "score": _number(_record_value(record, "score")),
        "grade": _text(_record_value(record, "grade"), "N/A"),
        "status": _text(_record_value(record, "status")),
        "root_cause": root_cause,
        "root_cause_text": _text(root_cause.get("text") or root_cause.get("cause") or root_cause.get("description")),
        "manager_notes": _text(_record_value(record, "manager_notes")),
        "suggested_action": _text(_record_value(record, "suggested_action")),
        "corrective_action": _text(_record_value(record, "corrective_action")),
        "kpis": [dict(value) for value in (raw_kpis or []) if isinstance(value, dict)],
    }


def _employee_key(record: dict[str, Any]) -> str:
    return _text(record.get("employee_id")) or _text(record.get("employee_name"))


def _period_for_record(record: dict[str, Any]) -> tuple[int, int] | None:
    return _period_key({"year": record.get("year"), "month": record.get("month")})


def _record_kpi_key(raw: dict[str, Any]) -> str:
    return _text(raw.get("kpi_key") or raw.get("key") or raw.get("label") or "KPI")


def _kpi_rows(record: dict[str, Any], selected_kpi: str = "") -> list[dict[str, Any]]:
    rows = record.get("kpis") or []
    if not selected_kpi:
        return rows
    return [
        row
        for row in rows
        if _record_kpi_key(row).casefold() == selected_kpi.casefold()
        or _text(row.get("label")).casefold() == selected_kpi.casefold()
    ]


def _kpi_summary(
    rows: list[dict[str, Any]],
    definitions: list[dict[str, Any]],
    *,
    affected_records: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not rows:
        return None
    raw = rows[0]
    definition = _definition_for(raw, definitions)
    key = _text(raw.get("kpi_key") or raw.get("key") or raw.get("label") or "KPI")
    label = _text(definition.get("label") or raw.get("label") or key)
    direction = _text(definition.get("direction") or raw.get("direction") or "higher_better")
    unit = _text(definition.get("unit") or raw.get("unit"))
    metric = aggregate_kpi_metric(rows, definition)
    achievement = kpi_achievement(
        metric.actual,
        metric.target,
        direction,
        sum(
            ratio
            for ratio in (normalize_ratio(row.get("achievement_ratio")) for row in rows)
            if ratio is not None
        ) / len(rows)
        if rows
        else None,
    )
    weights = [configured_weight(row, definition) for row in rows]
    measured_weights = [weight for weight in weights if weight is not None]
    weight = mean(measured_weights) if measured_weights else None
    if achievement is None:
        status = "Data quality"
    elif achievement >= 1:
        status = "On track"
    elif achievement >= 0.7:
        status = "At risk"
    else:
        status = "Critical"
    affected_count = None
    if affected_records is not None:
        affected_count = len(
            {
                _employee_key(record)
                for record in affected_records
                if _employee_key(record)
            }
        )
    return {
        "key": key,
        "label": label,
        "unit": unit,
        "direction": direction,
        "actual": metric.actual,
        "target": metric.target,
        "achievement": achievement,
        "achievement_pct": achievement * 100 if achievement is not None else None,
        "gap": kpi_gap(achievement),
        "shortfall": max(0.0, -(kpi_gap(achievement) or 0.0)),
        "weight": weight,
        "weight_pct": weight * 100 if weight is not None else None,
        "weighted_impact": weighted_impact(achievement, weight),
        "status": status,
        "affected_count": affected_count,
        "definition": definition,
    }


def _kpi_group_key(label: Any, unit: Any, direction: Any) -> str:
    """Return the stable display-level identity for a KPI.

    Employee and managerial configurations can use different storage keys for
    the same business KPI (for example ``sms_response_time`` and
    ``response_time``).  The executive report must not present those as two
    unrelated drivers when their label, unit, and direction are identical.
    """

    return "|".join(
        (
            _text(label, "KPI").casefold(),
            _text(unit).casefold(),
            _text(direction, "higher_better").casefold(),
        )
    )


def _kpi_group_key_from_raw(raw: dict[str, Any], definitions: list[dict[str, Any]]) -> str:
    definition = _definition_for(raw, definitions)
    return _kpi_group_key(
        definition.get("label") or raw.get("label") or _record_kpi_key(raw),
        definition.get("unit") or raw.get("unit"),
        definition.get("direction") or raw.get("direction"),
    )


def _kpi_group_key_from_summary(summary: dict[str, Any]) -> str:
    return _kpi_group_key(summary.get("label"), summary.get("unit"), summary.get("direction"))


def _merge_kpi_summaries(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Merge same-label KPI summaries without changing canonical scoring.

    Each input row has already been scored using its configured direction,
    aggregation, and weight.  We therefore combine the already-scored
    weighted losses and period-level metrics; we never pool raw actuals and
    targets across unrelated KPI configurations.
    """

    if not rows:
        return None
    ordered = sorted(rows, key=lambda row: (_number(row.get("weight")) is None, _text(row.get("key")).casefold()))
    first = dict(ordered[0])
    source_keys = sorted(
        {
            source_key
            for row in ordered
            for source_key in [row.get("key"), *(row.get("source_keys") or [])]
            if _text(source_key)
        }
    )
    weights = [_number(row.get("weight")) for row in ordered]
    weighted_rows = [
        (row, weight)
        for row, weight in zip(ordered, weights)
        if weight is not None and weight > 0
    ]
    total_weight = sum(weight for _, weight in weighted_rows)
    weighted_impact_total = sum(_number(row.get("weighted_impact")) or 0.0 for row in ordered)

    def aggregate_value(key: str) -> float | None:
        values = [(_number(row.get(key)), weight) for row, weight in weighted_rows if _number(row.get(key)) is not None]
        if values and total_weight > 0:
            return sum(value * weight for value, weight in values) / sum(weight for _, weight in values)
        return _average_summary(ordered, key)

    achievement = (
        None
        if any(row.get("status") == "Data quality" or row.get("achievement") is None for row in ordered)
        else max(0.0, min(1.0, 1.0 - (weighted_impact_total / (total_weight * 100.0))))
        if total_weight > 0
        else _average_summary(ordered, "achievement")
    )
    affected_values = [_number(row.get("affected_count")) for row in ordered]
    affected_values = [value for value in affected_values if value is not None]
    status = "Data quality" if achievement is None else "On track" if achievement >= 1 else "At risk" if achievement >= 0.7 else "Critical"
    merged = {
        **first,
        "key": source_keys[0] if source_keys else first.get("key"),
        "source_keys": source_keys,
        "group_key": _kpi_group_key_from_summary(first),
        "actual": aggregate_value("actual"),
        "target": aggregate_value("target"),
        "achievement": achievement,
        "achievement_pct": achievement * 100 if achievement is not None else None,
        "gap": kpi_gap(achievement),
        "shortfall": max(0.0, -(kpi_gap(achievement) or 0.0)),
        "weight": total_weight if weighted_rows else None,
        "weight_pct": total_weight * 100 if weighted_rows else None,
        "weighted_impact": weighted_impact_total,
        "status": status,
        "affected_count": round(sum(affected_values)) if affected_values else None,
        "source_definitions": [row.get("definition") for row in ordered if row.get("definition")],
    }
    return merged


def _merge_kpi_summary_groups(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_kpi_group_key_from_summary(row)].append(row)
    merged: dict[str, dict[str, Any]] = {}
    for group_key, group_rows in grouped.items():
        summary = _merge_kpi_summaries(group_rows)
        if summary:
            summary["group_key"] = group_key
            merged[group_key] = summary
    return merged


def _average_summary(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [_number(row.get(key)) for row in rows]
    values = [value for value in values if value is not None]
    return mean(values) if values else None


def _average_kpi_summaries(period_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    first = period_summaries[0]
    achievement_values = [row["achievement"] for row in period_summaries if row.get("achievement") is not None]
    achievement = mean(achievement_values) if achievement_values else None
    weight_values = [row["weight"] for row in period_summaries if row.get("weight") is not None]
    weight = mean(weight_values) if weight_values else None
    affected_values = [row["affected_count"] for row in period_summaries if row.get("affected_count") is not None]
    weighted_loss_values = [row["weighted_impact"] for row in period_summaries if row.get("weighted_impact") is not None]
    source_keys = sorted(
        {
            source_key
            for row in period_summaries
            for source_key in [row.get("key"), *(row.get("source_keys") or [])]
            if _text(source_key)
        }
    )
    if achievement is None:
        status = "Data quality"
    elif achievement >= 1:
        status = "On track"
    elif achievement >= 0.7:
        status = "At risk"
    else:
        status = "Critical"
    return {
        **first,
        "key": source_keys[0] if source_keys else first.get("key"),
        "source_keys": source_keys,
        "group_key": _kpi_group_key_from_summary(first),
        "actual": _average_summary(period_summaries, "actual"),
        "target": _average_summary(period_summaries, "target"),
        "achievement": achievement,
        "achievement_pct": achievement * 100 if achievement is not None else None,
        "gap": kpi_gap(achievement),
        "shortfall": max(0.0, -(kpi_gap(achievement) or 0.0)),
        "weight": weight,
        "weight_pct": weight * 100 if weight is not None else None,
        "weighted_impact": mean(weighted_loss_values) if weighted_loss_values else weighted_impact(achievement, weight),
        "status": status,
        "affected_count": round(mean(affected_values)) if affected_values else None,
        "source_definitions": [row.get("definition") for row in period_summaries if row.get("definition")],
    }


def _score_for_records(records: list[dict[str, Any]]) -> float | None:
    by_employee: dict[str, list[float]] = defaultdict(list)
    for record in records:
        score = _number(record.get("score"))
        if score is not None:
            by_employee[_employee_key(record)].append(score)
    scores = [mean(values) for values in by_employee.values() if values]
    return mean(scores) if scores else None


def _period_data(
    report_data: dict[str, Any],
) -> tuple[
    list[tuple[int, int]],
    dict[tuple[int, int], list[dict[str, Any]]],
    list[tuple[int, int]],
    dict[tuple[int, int], list[dict[str, Any]]],
    dict[tuple[int, int], str],
]:
    history = list(report_data.get("history") or [])
    selected_records = [
        _normalize_record(record)
        for record in (report_data.get("selected_records") or [])
    ]
    selected_grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    if selected_records:
        for record in selected_records:
            period = _period_for_record(record)
            if period:
                selected_grouped[period].append(record)

    history_grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for item in history:
        item_period = _period_key(item.get("key") or item.get("label"))
        if not item_period:
            continue
        history_grouped[item_period].extend(
            _normalize_record(record) for record in item.get("records") or []
        )
    if not history_grouped:
        history_grouped.update(selected_grouped)
    if not selected_grouped:
        selected_grouped.update(history_grouped)
        if not selected_grouped:
            current = [_normalize_record(record) for record in report_data.get("records") or []]
            for record in current:
                period = _period_for_record(record)
                if period:
                    selected_grouped[period].append(record)
            history_grouped.update(selected_grouped)
    labels = {
        period: period_label(period)
        for period in set(selected_grouped) | set(history_grouped)
    }
    for item in history:
        item_period = _period_key(item.get("key") or item.get("label"))
        if item_period in labels:
            labels[item_period] = _text(item.get("label"), period_label(item_period))
    selected_periods = sorted(selected_grouped)
    history_periods = sorted(set(selected_grouped) | set(history_grouped))
    return selected_periods, selected_grouped, history_periods, history_grouped, labels


def _action_matches(action: dict[str, Any], employee_id: str, team: str, kpi_key: str = "") -> bool:
    action_employee = _text(action.get("employee_id"))
    if action_employee and employee_id and action_employee != employee_id:
        return False
    action_team = _text(action.get("team"))
    if action_team and team and action_team.casefold() != team.casefold():
        return False
    linked_kpi = _text(action.get("linked_kpi_key"))
    return not (linked_kpi and kpi_key and linked_kpi.casefold() != kpi_key.casefold())


def evidence_status(
    records: Iterable[dict[str, Any]],
    actions: Iterable[dict[str, Any]],
    *,
    employee_id: str = "",
    team: str = "",
    kpi_key: str = "",
    has_gap: bool = True,
) -> tuple[str, str]:
    """Return one of the four management-facing evidence states."""

    relevant_actions = [
        action
        for action in actions
        if _action_matches(action, employee_id, team, kpi_key)
    ]
    notes = [
        _text(action.get("root_cause_note"))
        for action in relevant_actions
        if _text(action.get("root_cause_note"))
    ]
    if notes:
        confirmed = any(_text(action.get("evidence_reference")) for action in relevant_actions if _text(action.get("root_cause_note")))
        return (
            "Confirmed cause" if confirmed else "Evidence recorded — cause pending confirmation",
            notes[0],
        )
    explicit = [
        _text(record.get("root_cause_text"))
        for record in records
        if _text(record.get("root_cause_text"))
    ]
    if explicit:
        return "Evidence recorded — cause pending confirmation", explicit[0]
    return ("KPI signal only" if has_gap else "No evidence recorded", "")


def _severity(score: float | None, loss: float) -> str:
    if (score is not None and score < 70) or loss >= 30:
        return "Critical"
    if (score is not None and score < 85) or loss >= 15:
        return "At risk"
    if loss > 0:
        return "Watch"
    return "On track"


def _action_rows(actions: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for action in actions:
        owner = _text(action.get("owner")) or "Owner needed"
        due_date = _text(action.get("due_date")) or "Due date needed"
        success_metric = _text(action.get("success_metric")) or "Success metric needed"
        is_proposed = bool(action.get("is_proposed"))
        rows.append(
            {
                **dict(action),
                "is_proposed": is_proposed,
                "source_display": "Proposed" if is_proposed else "Recorded",
                "owner_display": owner,
                "due_date_display": due_date,
                "success_metric_display": success_metric,
                "action_display": _text(action.get("action_text"), "Action text needed"),
                "status_display": "Proposed" if is_proposed else _text(action.get("status")) or "Status not recorded",
                "evidence_display": _text(action.get("evidence_reference")) or "No evidence reference",
            }
        )
    return rows


def _kpi_source_keys(kpi: dict[str, Any] | None) -> set[str]:
    if not kpi:
        return set()
    return {
        _text(value).casefold()
        for value in [kpi.get("key"), *(kpi.get("source_keys") or [])]
        if _text(value)
    }


def _action_matches_kpi(action: dict[str, Any], kpi: dict[str, Any] | None) -> bool:
    linked_key = _text(action.get("linked_kpi_key")).casefold()
    return bool(linked_key and linked_key in _kpi_source_keys(kpi))


def _enrich_action_success_metrics(actions: list[dict[str, Any]], kpis: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Make plan targets explicit when they differ from the configured KPI target."""

    enriched: list[dict[str, Any]] = []
    for action in actions:
        row = dict(action)
        matched_kpi = next((kpi for kpi in kpis if _action_matches_kpi(row, kpi)), None)
        configured_target = matched_kpi.get("target") if matched_kpi else None
        configured_unit = matched_kpi.get("unit") if matched_kpi else None
        plan_target = _number(row.get("plan_target_value"))
        plan_unit = _text(row.get("plan_target_unit")) or _text(configured_unit)
        if plan_target is not None:
            plan_text = _format_value(plan_target, plan_unit)
            configured_text = _format_value(configured_target, configured_unit) if configured_target is not None else None
            direction = "lower is better" if _text(row.get("plan_target_direction")).casefold() == "lower_better" else "higher is better"
            success_text = f"Management plan target: {plan_text} ({direction})"
            if configured_text and configured_text != plan_text:
                success_text += f"; configured KPI target: {configured_text}"
            row["success_metric_display"] = success_text
        elif _text(row.get("success_metric_display")) == "Success metric needed" and configured_target is not None:
            row["success_metric_display"] = f"Reach configured KPI target: {_format_value(configured_target, configured_unit)}"
        row["configured_kpi_target"] = configured_target
        row["configured_kpi_unit"] = configured_unit
        row["configured_kpi_direction"] = matched_kpi.get("direction") if matched_kpi else None
        enriched.append(row)
    return enriched


def _proposed_action(driver: dict[str, Any] | None, affected_people: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Create a transparent proposal when no recorded action covers the driver."""

    if not driver:
        return None
    people = [str(person.get("name")) for person in affected_people[:4] if person.get("name")]
    scope = ", ".join(people) if people else "Selected team scope"
    actual = _format_value(driver.get("actual"), driver.get("unit"))
    target = _format_value(driver.get("target"), driver.get("unit"))
    return {
        "is_proposed": True,
        "action_type": "Proposed management action",
        "action_text": f"Review {driver['label']} workflow and provide focused coaching.",
        "team": "Selected scope",
        "employee_name": scope,
        "linked_kpi_key": driver.get("key", ""),
        "owner": None,
        "due_date": None,
        "success_metric": (
            f"{driver['label']} reaches the configured KPI target of {target}."
            if driver.get("target") is not None
            else "Success metric needed"
        ),
        "status": "Proposed",
        "evidence_reference": f"{driver['label']} actual {actual} vs target {target}",
        "root_cause_note": "Cause validation required before closing the gap.",
    }


def _story_headline(scope: str, score: float | None, trend_state: dict[str, Any]) -> str:
    subject = scope or "The selected scope"
    if score is None:
        return "No performance data is available for the selected scope."
    gap = 100 - score
    key = trend_state.get("key")
    if key == "single_period":
        return f"{subject} is {gap:.1f}% below target; trend unavailable — only one measured period." if score < 100 else f"{subject} is on track; trend unavailable — only one measured period."
    if key == "movement_only":
        return f"{subject} is {gap:.1f}% below target; movement is visible but sustained trend is not established." if score < 100 else f"{subject} is on track; movement is visible but sustained trend is not established."
    if key == "improving":
        return f"{subject} is improving but remains {gap:.1f}% below target" if score < 100 else f"{subject} is improving toward target"
    if key == "declining":
        return f"{subject} is declining and is {gap:.1f}% below target" if score < 100 else f"{subject} is declining from target"
    if key == "stable":
        return f"{subject} is stable at {score:.1f}% with a {gap:.1f}% achievement gap" if score < 100 else f"{subject} is stable at target"
    return f"{subject} is {gap:.1f}% below target" if score < 100 else f"{subject} is on track"


def _context_headline(trend_state: dict[str, Any]) -> str:
    return str(trend_state.get("headline") or "Trend unavailable — only one measured period.")


def build_insights_snapshot(report_data: dict[str, Any]) -> dict[str, Any]:
    """Build one immutable-in-practice snapshot for every deck section."""

    definitions = [dict(item) for item in report_data.get("kpi_definitions") or [] if isinstance(item, dict)]
    selected_kpi = _text((report_data.get("filters") or {}).get("kpi"))
    periods, grouped, history_periods, history_grouped, labels = _period_data(report_data)
    if not periods:
        return {
            "periods": [],
            "history": [],
            "records": [],
            "kpis": [],
            "driver": None,
            "headline": "No performance data is available for this filtered scope",
            "context_headline": "No measured periods are available for this filtered scope.",
            "trend_status": "No measured history",
            "movement_status": "no_data",
            "trend_headline": "No performance data is available for the selected scope.",
            "history_count": 0,
            "selected_period_count": 0,
            "overall_score": None,
            "latest_score": None,
            "baseline_score": None,
            "baseline_period_label": None,
            "target_score": 100.0,
            "gap_to_target": None,
            "movement": None,
            "scope_label": _text(report_data.get("scope_label"), "Authorized scope"),
            "period_label": _text(report_data.get("period_label"), "Selected period"),
            "aggregate_only": bool(report_data.get("aggregate_only")),
            "people_visible": not bool(report_data.get("aggregate_only")),
            "actions": _action_rows(report_data.get("actions") or []),
            "recorded_action_count": len(report_data.get("actions") or []),
            "proposed_action_count": 0,
            "warnings": ["No performance data is available for the selected filters."],
        }

    period_summaries: dict[tuple[int, int], dict[str, Any]] = {}
    all_kpi_keys: set[str] = set()
    for period in history_periods:
        rows = history_grouped[period]
        by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in rows:
            for raw in _kpi_rows(record, selected_kpi):
                by_key[_record_kpi_key(raw)].append(raw)
        kpi_summaries = []
        for key, values in by_key.items():
            affected = []
            by_employee: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for record in rows:
                employee = _employee_key(record)
                employee_values = [raw for raw in _kpi_rows(record, selected_kpi) if _record_kpi_key(raw) == key]
                if employee_values:
                    by_employee[employee].extend(employee_values)
            definition = _definition_for(values[0], definitions)
            for employee, employee_values in by_employee.items():
                employee_metric = aggregate_kpi_metric(employee_values, definition)
                employee_ratio = kpi_achievement(
                    employee_metric.actual,
                    employee_metric.target,
                    definition.get("direction"),
                    employee_values[0].get("achievement_ratio"),
                )
                if employee_ratio is not None and employee_ratio < 1:
                    affected.append({"employee_id": employee})
            summary = _kpi_summary(values, definitions, affected_records=affected)
            if summary:
                kpi_summaries.append(summary)
        grouped_kpis = _merge_kpi_summary_groups(kpi_summaries)
        if period in periods:
            all_kpi_keys.update(grouped_kpis)
        period_summaries[period] = {
            "period": period,
            "label": labels.get(period, period_label(period)),
            "score": _score_for_records(rows),
            "record_count": len(rows),
            "employee_count": len({_employee_key(row) for row in rows if _employee_key(row)}),
            "kpis": grouped_kpis,
        }

    score_rows = [period_summaries[period] for period in periods if period_summaries[period].get("score") is not None]
    scores = [row["score"] for row in score_rows]
    latest_period = periods[-1]
    # A comparison period can be explicitly selected by the direct Reports
    # workflow. Keep future comparison data out of trend classification while
    # still allowing the requested period to drive the movement card.
    trend_history_score_rows = [
        period_summaries[period]
        for period in history_periods
        if period <= latest_period and period_summaries[period].get("score") is not None
    ]
    history_score_rows = trend_history_score_rows
    history_scores = [row["score"] for row in history_score_rows]
    trend_state = _trend_state(history_scores)
    overall_score = mean(scores) if scores else None
    requested_comparison = _period_key((report_data.get("filters") or {}).get("comparison_period"))
    previous_period = (
        requested_comparison
        if requested_comparison in period_summaries and requested_comparison != latest_period
        else (periods[-2] if len(periods) >= 2 else next(
            (period for period in reversed(history_periods) if period < latest_period),
            None,
        ))
    )
    latest_score = period_summaries[latest_period].get("score")
    previous_score = period_summaries[previous_period].get("score") if previous_period else None
    movement = latest_score - previous_score if latest_score is not None and previous_score is not None else None
    baseline_period_label = period_summaries[previous_period]["label"] if previous_period else None

    kpis = []
    for key in sorted(all_kpi_keys):
        rows = [period_summaries[period]["kpis"][key] for period in periods if key in period_summaries[period]["kpis"]]
        if rows:
            kpis.append(_average_kpi_summaries(rows))
    kpis.sort(key=lambda row: (row.get("weighted_impact", 0), row.get("shortfall", 0)), reverse=True)
    previous_kpi_rows = period_summaries.get(previous_period, {}).get("kpis", {}) if previous_period else {}
    for row in kpis:
        baseline = previous_kpi_rows.get(row.get("group_key")) if isinstance(previous_kpi_rows, dict) else None
        row["baseline_actual"] = baseline.get("actual") if baseline else None
        row["baseline_target"] = baseline.get("target") if baseline else None
        row["baseline_achievement_pct"] = baseline.get("achievement_pct") if baseline else None
        row["mom"] = (
            row.get("achievement_pct") - baseline.get("achievement_pct")
            if baseline
            and row.get("achievement_pct") is not None
            and baseline.get("achievement_pct") is not None
            else None
        )
    driver = next(
        (
            row
            for row in kpis
            if row.get("status") != "Data quality" and row.get("weighted_impact", 0) > 0
        ),
        None,
    )

    # Aggregate people across selected periods using period-level KPI results,
    # so multi-month reports never divide pooled actuals by pooled targets.
    aggregate_only = bool(report_data.get("aggregate_only"))
    people: list[dict[str, Any]] = []
    employee_keys = {
        _employee_key(record)
        for period in periods
        for record in grouped[period]
        if _employee_key(record)
    }
    recorded_actions = _action_rows(report_data.get("actions") or [])
    recorded_actions = _enrich_action_success_metrics(recorded_actions, kpis)
    for employee in sorted(employee_keys):
        employee_records = [
            record
            for period in periods
            for record in grouped[period]
            if _employee_key(record) == employee
        ]
        representative = employee_records[-1]
        employee_scores = [
            _score_for_records(
                [row for row in grouped[period] if _employee_key(row) == employee]
            )
            for period in periods
            if any(_employee_key(row) == employee for row in grouped[period])
        ]
        employee_scores = [value for value in employee_scores if value is not None]
        employee_score = mean(employee_scores) if employee_scores else None
        employee_kpis: list[dict[str, Any]] = []
        employee_keys_for_rows = {
            _kpi_group_key_from_raw(raw, definitions)
            for record in employee_records
            for raw in _kpi_rows(record, selected_kpi)
        }
        for key in employee_keys_for_rows:
            per_period = []
            for period in periods:
                rows = [
                    raw
                    for record in grouped[period]
                    if _employee_key(record) == employee
                    for raw in _kpi_rows(record, selected_kpi)
                    if _kpi_group_key_from_raw(raw, definitions) == key
                ]
                if rows:
                    summary = _kpi_summary(rows, definitions)
                    if summary:
                        per_period.append(summary)
            if per_period:
                employee_kpis.append(_average_kpi_summaries(per_period))
        employee_kpis.sort(key=lambda row: row.get("weighted_impact", 0), reverse=True)
        leading_kpi = employee_kpis[0] if employee_kpis else None
        total_loss = sum(row.get("weighted_impact", 0) for row in employee_kpis)
        employee_actions = [
            action
            for action in recorded_actions
            if _action_matches(action, _text(representative.get("employee_id")), _text(representative.get("team")))
        ]
        state, cause = evidence_status(
            employee_records,
            employee_actions,
            employee_id=_text(representative.get("employee_id")),
            team=_text(representative.get("team")),
            kpi_key=leading_kpi.get("key", "") if leading_kpi else "",
            has_gap=bool(total_loss > 0),
        )
        employee_history_scores = []
        for history_period in history_periods:
            history_employee_rows = [
                row
                for row in history_grouped[history_period]
                if _employee_key(row) == employee
            ]
            history_score = _score_for_records(history_employee_rows)
            if history_score is not None:
                employee_history_scores.append(history_score)
        employee_movement = (
            employee_history_scores[-1] - employee_history_scores[-2]
            if len(employee_history_scores) >= 2
            else None
        )
        people.append(
            {
                "name": representative.get("employee_name") or "Unknown employee",
                "employee_id": representative.get("employee_id") or "",
                "team": representative.get("team") or "Unassigned",
                "position": representative.get("position") or "Unassigned",
                "score": employee_score,
                "baseline_score": employee_history_scores[-2] if len(employee_history_scores) >= 2 else None,
                "baseline_period_label": baseline_period_label if len(employee_history_scores) >= 2 else None,
                "grade": representative.get("grade") or "N/A",
                "status": representative.get("status") or "",
                "weighted_loss": total_loss,
                "weighted_loss_pct": total_loss,
                "severity": _severity(employee_score, total_loss),
                "leading_kpi": leading_kpi,
                "kpis": employee_kpis,
                "root_cause_status": state,
                "root_cause": cause,
                "actions": employee_actions,
                "action_status": employee_actions[0].get("status_display") if employee_actions else "No action recorded",
                "movement": employee_movement,
                "history_count": len(employee_history_scores),
            }
        )
    people.sort(key=lambda row: (-row["weighted_loss"], row["score"] if row["score"] is not None else 999, row["name"]))
    affected_people = [row for row in people if row["weighted_loss"] > 0]
    focus_ids = {row["employee_id"] for row in affected_people}
    score_snapshot = [row for row in sorted(people, key=lambda item: (item["score"] if item["score"] is not None else 999, item["name"])) if row["employee_id"] not in focus_ids][:4]

    # KPI rows are the common source for loss breakdown and root-cause evidence.
    root_cause_rows = []
    for kpi in kpis[:6]:
        relevant_records = [
            record
            for period in periods
            for record in grouped[period]
            if any(_kpi_group_key_from_raw(raw, definitions) == kpi.get("group_key") for raw in _kpi_rows(record, selected_kpi))
        ]
        matching_actions = [
            action
            for action in recorded_actions
            if _action_matches_kpi(action, kpi)
        ]
        state, cause = evidence_status(
            relevant_records,
            matching_actions,
            kpi_key=kpi["key"],
            has_gap=bool(kpi.get("shortfall", 0) > 0),
        )
        validation = (
            ""
            if state == "Confirmed cause"
            else "The KPI identifies where to investigate, but the operational cause has not been confirmed. Validate workflow queue, staffing, delayed handoff, system issue, prioritization, or process adherence."
        )
        owner = next(
            (
                action.get("owner_display")
                for action in matching_actions
                if action.get("owner_display") and action.get("owner_display") != "Owner needed"
            ),
            "Owner needed",
        )
        root_cause_rows.append(
            {
                **kpi,
                "evidence_status": state,
                "recorded_root_cause": cause or "No operational cause recorded",
                "required_validation": validation,
                "owner_display": owner,
            }
        )

    driver_trend = []
    if driver:
        for period in history_periods:
            row = period_summaries[period]["kpis"].get(driver.get("group_key"))
            if row:
                driver_trend.append(
                    {
                        "label": period_summaries[period]["label"],
                        "actual": row.get("actual"),
                        "target": row.get("target"),
                        "achievement_pct": row.get("achievement_pct"),
                        "gap": row.get("gap"),
                    }
                )

    # Keep the action page decision-ready even when the system has only one
    # recorded action.  Uncovered high-impact KPI gaps become explicitly
    # labelled proposals with missing owner/due fields, rather than leaving a
    # mostly empty action table or implying that an action was recorded.
    proposed_actions: list[dict[str, Any]] = []
    proposal_kpis = [
        kpi
        for kpi in kpis[:4]
        if kpi.get("status") != "Data quality"
        and (_number(kpi.get("weighted_impact")) or 0) > 0
        and not any(_action_matches_kpi(action, kpi) for action in recorded_actions)
    ]
    for kpi in proposal_kpis:
        kpi_group = kpi.get("group_key")
        kpi_people = [
            person
            for person in affected_people
            if any(
                row.get("group_key") == kpi_group
                for row in person.get("kpis") or []
            )
        ]
        proposed = _proposed_action(kpi, kpi_people or affected_people)
        if proposed:
            proposed_actions.append(proposed)
    actions = list(recorded_actions)
    if proposed_actions:
        actions.extend(_action_rows(proposed_actions))

    open_actions = [
        action
        for action in recorded_actions
        if _text(action.get("status")).casefold() not in {"completed", "cancelled"}
    ]
    trend = [
        {
            "label": row["label"],
            "score": row.get("score"),
            "target": 100.0,
            "record_count": row["record_count"],
        }
        for row in history_score_rows[-6:]
    ]
    headline = _story_headline(_text(report_data.get("scope_label"), "The selected scope"), overall_score, trend_state)
    context_headline = _context_headline(trend_state)
    driver_story = "No measurable KPI gap is available for the selected filters."
    if driver and driver.get("actual") is not None and driver.get("target") is not None:
        direction = driver.get("direction")
        if direction == "lower_better":
            relation = "above" if driver["actual"] > driver["target"] else "at or below"
            driver_story = f"{driver['label']} is {_format_value(driver['actual'], driver['unit'])}, {relation} the {_format_value(driver['target'], driver['unit'])} target."
        else:
            relation = "below" if driver["actual"] < driver["target"] else "at or above"
            driver_story = f"{driver['label']} is {_format_value(driver['actual'], driver['unit'])}, {relation} the {_format_value(driver['target'], driver['unit'])} target."

    team_rows = _team_rows(periods, grouped, labels)
    team_health = _team_health(team_rows, periods, grouped, people, kpis, driver, aggregate_only)

    warnings = []
    if not history_scores:
        warnings.append("No performance data is available for the selected scope.")
    elif len(history_scores) == 1:
        warnings.append("Trend unavailable — only one measured period.")
    elif len(history_scores) == 2:
        warnings.append("Two measured periods show movement only; sustained trend is not established.")
    if any(row.get("status") == "Data quality" for row in kpis):
        warnings.append("One or more KPI rows lack a valid target or direction and are excluded from loss ranking.")
    if not affected_people and not aggregate_only:
        warnings.append("No affected employees were identified in the selected snapshot.")

    return {
        "periods": periods,
        "period_label": _text(report_data.get("period_label"), "Selected period"),
        "latest_period_label": period_summaries[latest_period]["label"],
        "comparison_period_label": period_summaries[previous_period]["label"] if previous_period else None,
        "scope_label": _text(report_data.get("scope_label"), "Authorized scope"),
        "filters": dict(report_data.get("filters") or {}),
        "aggregate_only": aggregate_only,
        "people_visible": not aggregate_only,
        "records": grouped[latest_period],
        "selected_record_count": sum(period_summaries[period]["record_count"] for period in periods),
        "population_size": sum(period_summaries[period]["record_count"] for period in periods) if aggregate_only else len(people),
        "team_count": len({_text(record.get("team")) for period in periods for record in grouped[period] if _text(record.get("team"))}),
        "overall_score": overall_score,
        "latest_score": latest_score,
        "baseline_score": previous_score,
        "baseline_period_label": baseline_period_label,
        "target_score": 100.0,
        "gap_to_target": overall_score - 100 if overall_score is not None else None,
        "movement": movement,
        "movement_status": trend_state["key"],
        "trend_status": trend_state["label"],
        "trend_headline": trend_state["headline"],
        "trend_direction": trend_state["direction"],
        "trend_sustained": trend_state["sustained"],
        "history_count": len(history_scores),
        "selected_period_count": len(scores),
        "best_period": max(history_score_rows, key=lambda row: row["score"]) if history_score_rows else None,
        "worst_period": min(history_score_rows, key=lambda row: row["score"]) if history_score_rows else None,
        "net_movement": history_scores[-1] - history_scores[0] if len(history_scores) > 1 else None,
        "history_periods": history_periods,
        "trend": trend,
        "teams": team_rows,
        "team_health": team_health,
        "kpis": kpis,
        "driver": driver,
        "driver_story": driver_story,
        "driver_trend": driver_trend,
        "root_cause_rows": root_cause_rows,
        # Keep every affected employee available to the presentation layer;
        # the builder uses a readable primary table plus a conditional
        # appendix when the filtered scope contains more than four rows.
        "people": affected_people,
        "score_snapshot": score_snapshot,
        "all_people": people,
        "affected_count": len(affected_people) if not aggregate_only else None,
        "open_actions": len(open_actions),
        "recorded_action_count": len(recorded_actions),
        "proposed_action_count": len(proposed_actions),
        "actions": actions,
        "headline": headline,
        "context_headline": context_headline,
        "next_review": _next_review(driver, root_cause_rows, affected_people, actions, overall_score),
        "warnings": warnings,
    }


def _team_rows(
    periods: list[tuple[int, int]],
    grouped: dict[tuple[int, int], list[dict[str, Any]]],
    labels: dict[tuple[int, int], str],
) -> list[dict[str, Any]]:
    teams = sorted({_text(record.get("team"), "Unassigned") for period in periods for record in grouped[period]})
    result = []
    for team in teams:
        period_scores = []
        employee_ids = set()
        risk_counts = {"at_risk": 0, "critical": 0}
        for period in periods:
            rows = [record for record in grouped[period] if _text(record.get("team"), "Unassigned") == team]
            if rows:
                score = _score_for_records(rows)
                if score is not None:
                    period_scores.append((period, score))
                employee_ids.update(_employee_key(row) for row in rows if _employee_key(row))
                for row in rows:
                    score_value = _number(row.get("score"))
                    if score_value is not None and score_value < 70:
                        risk_counts["critical"] += 1
                    elif score_value is not None and score_value < 100:
                        risk_counts["at_risk"] += 1
        score = mean(value for _, value in period_scores) if period_scores else None
        latest = next((value for period, value in reversed(period_scores) if period == periods[-1]), None)
        previous = next((value for period, value in reversed(period_scores[:-1]) if period < periods[-1]), None)
        result.append(
            {
                "name": team,
                "score": score,
                "movement": latest - previous if latest is not None and previous is not None else None,
                "gap": score - 100 if score is not None else None,
                "headcount": len(employee_ids),
                "affected_count": risk_counts["at_risk"] + risk_counts["critical"],
                "at_risk_count": risk_counts["at_risk"],
                "critical_count": risk_counts["critical"],
            }
        )
    return sorted(result, key=lambda row: (row["score"] is None, row["score"] if row["score"] is not None else 999, row["name"]))


def _team_health(
    team_rows: list[dict[str, Any]],
    periods: list[tuple[int, int]],
    grouped: dict[tuple[int, int], list[dict[str, Any]]],
    people: list[dict[str, Any]],
    kpis: list[dict[str, Any]],
    driver: dict[str, Any] | None,
    aggregate_only: bool,
) -> dict[str, Any] | None:
    """Return a compact health view only when there is one team in scope."""

    if len(team_rows) != 1:
        return None
    row = team_rows[0]
    team_name = row.get("name") or "Selected team"
    selected_records = [
        record
        for period in periods
        for record in grouped[period]
        if _text(record.get("team"), "Unassigned") == team_name
    ]
    if aggregate_only:
        score_values = [_number(record.get("score")) for record in selected_records]
        score_values = [value for value in score_values if value is not None]
        employee_count = len(selected_records)
        meeting_target = sum(value >= 100 for value in score_values)
        below_target = sum(value < 100 for value in score_values)
        critical = sum(value < 70 for value in score_values)
    else:
        team_people = [person for person in people if person.get("team") == team_name]
        employee_count = len(team_people)
        meeting_target = sum((person.get("score") or 0) >= 100 for person in team_people)
        below_target = sum((person.get("score") or 0) < 100 for person in team_people)
        critical = sum((person.get("score") or 0) < 70 for person in team_people)
    return {
        "team": team_name,
        "score": row.get("score"),
        "employee_count": employee_count,
        "employees_meeting_target": meeting_target,
        "employees_below_target": below_target,
        "critical_employees": critical,
        "leading_kpi": driver.get("label") if driver else "No measurable driver",
        "leading_kpi_impact": driver.get("weighted_impact") if driver else None,
        "kpi_status_distribution": dict(Counter(row.get("status") for row in kpis if row.get("status"))),
    }


def _next_review(
    driver: dict[str, Any] | None,
    root_cause_rows: list[dict[str, Any]],
    affected_people: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    overall_score: float | None,
) -> dict[str, Any]:
    if not driver:
        return {
            "leading_kpi_target": "No leading KPI is available",
            "expected_movement": "Insufficient measured evidence",
            "root_cause_requirement": "Validate whether a KPI gap exists before assigning a cause.",
            "people_requirement": "No employee review requirement is derived from this snapshot.",
            "action_requirement": "No action requirement is derived from this snapshot.",
            "overall_target": "Overall performance target: 100.0%.",
            "due_cadence": "Review in the next available reporting period.",
            "success_evidence": "Compare the next period's score, KPI actuals, targets, and evidence in the same scope.",
            "escalation_rule": "Escalate only after a measurable KPI gap is confirmed.",
            "decision_request": "Management decision required: confirm whether an owner and review date are needed.",
            "question": "Did the action plan reduce the leading KPI gap?",
        }
    evidence = next((row for row in root_cause_rows if row["key"] == driver["key"]), None)
    gap = abs(driver.get("gap") or 0)
    evidence_status = evidence.get("evidence_status") if evidence else None
    recorded_cause = _text((evidence or {}).get("recorded_root_cause"))
    if evidence_status == "Confirmed cause":
        root_cause_requirement = "Recheck the confirmed cause against the latest evidence."
    elif recorded_cause and recorded_cause.casefold() != "no operational cause recorded":
        root_cause_requirement = "Confirm the recorded cause with supporting evidence."
    else:
        root_cause_requirement = "Validate the operational cause before assigning corrective action."
    target_text = _format_value(driver.get("target"), driver.get("unit")) if driver.get("target") is not None else "target needed"
    target_direction = "lower is better" if driver.get("direction") == "lower_better" else "higher is better"
    failure_relation = "above target" if driver.get("direction") == "lower_better" else "below target"
    return {
        "overall_target": f"Overall performance: move from {_format_value(overall_score, '%') if overall_score is not None else 'N/A'} toward 100.0%.",
        "leading_kpi_target": f"{driver['label']}: reach {target_text} ({target_direction})",
        "expected_movement": f"Reduce the {gap:.1f}% achievement gap toward 0.0% in the next review." if gap > 0 else f"Maintain {driver['label']} at target.",
        "root_cause_requirement": root_cause_requirement,
        "people_requirement": f"Review the {len(affected_people)} affected employee(s) and record coaching evidence." if affected_people else "No affected employees require person-level review.",
        "action_requirement": "Complete or update every action with an owner, due date, and success metric." if actions else "Assign an owner, due date, and success metric before the next review.",
        "due_cadence": next((action.get("due_date_display") for action in actions if action.get("due_date_display") not in {None, "Due date needed"}), "Due date needed"),
        "success_evidence": f"Show {driver['label']} actual versus target and supporting operational evidence in the next review.",
        "escalation_rule": f"Escalate if {driver['label']} remains {failure_relation} after the next review cycle.",
        "decision_request": "Management decision required: assign an owner and review date before the next reporting period." if any(action.get("owner_display") == "Owner needed" or action.get("due_date_display") == "Due date needed" for action in actions) else "Confirm the assigned owner, review cadence, and success evidence.",
        "question": "Did the action plan reduce the leading KPI gap?",
    }


def _format_value(value: Any, unit: Any = "") -> str:
    number = _number(value)
    if number is None:
        return "N/A"
    normalized_unit = _text(unit)
    if normalized_unit == "%" and abs(number) <= 1:
        number *= 100
    if normalized_unit == "%":
        return f"{number:.1f}%"
    formatted = f"{number:,.1f}" if not number.is_integer() else f"{number:,.0f}"
    return f"{formatted} {normalized_unit}".strip()


__all__ = [
    "EVIDENCE_STATES",
    "build_insights_snapshot",
    "evidence_status",
    "kpi_achievement",
    "kpi_gap",
    "weighted_impact",
]
