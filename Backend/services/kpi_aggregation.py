"""Shared KPI rollups used by Marketing insights and report exports.

Individual performance records keep their source KPI values.  This module is
only for aggregating those values across a selected position/team scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any, Iterable


@dataclass(frozen=True)
class AggregatedKpiMetric:
    actual: float | None
    target: float | None


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def finite_value(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _sum(values: Iterable[float]) -> float | None:
    measured = list(values)
    return sum(measured) if measured else None


def aggregation_method(definition: dict[str, Any] | None) -> str:
    definition = definition or {}
    configured = definition.get("aggregation") or {}
    method = configured.get("method")
    if method:
        return str(method)

    unit = str(definition.get("unit") or "").strip().casefold()
    label = str(definition.get("label") or "")
    if unit in {"count", "number", "visits"} or any(
        word in label.casefold() for word in ("revenue", "income", "sales")
    ):
        return "sum"
    return "weighted_average"


def aggregate_kpi_metric(
    values: Iterable[Any],
    definition: dict[str, Any] | None = None,
) -> AggregatedKpiMetric:
    """Apply the configured cross-record actual/target rollup.

    The weighted-average contract uses the configured target value as the
    weight, matching the Marketing dashboard.  A missing or non-positive
    target falls back to a unit weight for that row.
    """
    rows = [
        {
            "actual": finite_value(_value(value, "actual_value")),
            "target": finite_value(_value(value, "target_value")),
        }
        for value in values
    ]
    actuals = [row["actual"] for row in rows if row["actual"] is not None]
    targets = [row["target"] for row in rows if row["target"] is not None]
    if not actuals and not targets:
        return AggregatedKpiMetric(actual=None, target=None)

    method = aggregation_method(definition)
    if method == "sum":
        return AggregatedKpiMetric(actual=_sum(actuals), target=_sum(targets))

    if method == "ratio":
        # The rows already contain the KPI's calculated actual and configured
        # target.  Dividing one by the other here produces achievement, not a
        # KPI measurement, and makes every ratio target render as 1.0 (100%).
        # Keep both series on their configured actual/target scale.  Scoring
        # applies the direction-aware achievement separately via
        # ``capped_achievement`` below.
        return AggregatedKpiMetric(
            actual=mean(actuals) if actuals else None,
            target=mean(targets) if targets else None,
        )

    if method == "weighted_average":
        weighted_rows = [row for row in rows if row["actual"] is not None]
        if weighted_rows:
            def row_weight(row: dict[str, float | None]) -> float:
                target = row["target"]
                return target if target is not None and target > 0 else 1.0

            total_weight = sum(row_weight(row) for row in weighted_rows)
            target_rows = [row for row in weighted_rows if row["target"] is not None]
            target_weight = sum(row_weight(row) for row in target_rows)
            return AggregatedKpiMetric(
                actual=sum(float(row["actual"]) * row_weight(row) for row in weighted_rows) / total_weight,
                target=(
                    sum(float(row["target"]) * row_weight(row) for row in target_rows) / target_weight
                    if target_rows and target_weight > 0
                    else None
                ),
            )

    return AggregatedKpiMetric(
        actual=mean(actuals) if actuals else None,
        target=mean(targets) if targets else None,
    )


def capped_achievement(
    metric: AggregatedKpiMetric,
    direction: str | None,
) -> float | None:
    if metric.actual is None or metric.target is None or metric.target <= 0:
        return None
    if direction == "lower_better":
        ratio = 1.0 if metric.actual <= 0 else metric.target / metric.actual
    elif direction == "higher_better":
        ratio = metric.actual / metric.target
    else:
        return None
    return min(max(ratio, 0.0), 1.0)


def configured_weight(value: Any, definition: dict[str, Any] | None = None) -> float | None:
    weight = finite_value(_value(value, "weight_applied"))
    if weight is None and definition:
        weight = finite_value(definition.get("weight"))
    if weight is None:
        return None
    return weight / 100 if weight > 1 else max(weight, 0.0)
