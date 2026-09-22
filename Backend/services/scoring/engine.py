"""
Pure KPI Scoring Engine.

Provides pure, typed functions for computing KPI achievement, contribution,
score, coverage, status, and grade across all organizational tiers (Employee,
Rollup, Management, and Functional).

This module contains zero database access, zero network operations, and zero I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AchievementResult:
    """Represents the outcome of a single KPI achievement calculation."""

    value: float | None
    state: str  # "measured" | "missing_actual" | "invalid_target" | "negative_actual" | "unknown_direction"
    raw_ratio: float | None = None


@dataclass(frozen=True)
class ScoreResult:
    """Represents the aggregated score across a set of KPI results."""

    score: float | None
    earned: float | None
    measured_weight: float
    configured_weight: float
    coverage: float | None
    state: str  # "measured" | "provisional" | "no_data"


@dataclass(frozen=True)
class KPIResult:
    """Input representation of a single KPI for score rollup."""

    achievement: float | None
    weight: float
    contribution: float | None = None
    # Callers that already have a persisted contribution can preserve their
    # legacy measured/unmeasured decision even when the raw achievement field
    # is absent (or present without a contribution).
    measured: bool | None = None


# ---------------------------------------------------------------------------
# Helper Utilities (Pure)
# ---------------------------------------------------------------------------

def _is_none_or_nan(val: Any) -> bool:
    if val is None:
        return True
    try:
        return math.isnan(float(val))
    except (ValueError, TypeError):
        return False


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Scoring Policies
# ---------------------------------------------------------------------------

class ScoringPolicy:
    """Base protocol/interface for scoring policies."""

    name: str

    def calculate(
        self,
        actual: float | None,
        target: float | None,
        direction: str | None,
    ) -> AchievementResult:
        raise NotImplementedError


class EmployeePolicy(ScoringPolicy):
    """
    Reproduces KPIService._calculate_achievement and row-evaluation behavior.

    - safe_float conversion (None / NaN -> 0.0)
    - lower_better: actual == 0 -> 1.0 (zero_actual_value = 100.0%)
    - higher_better: target == 0 -> 0.0
    - Capped at 1.0 (0-1 scale)
    - Negative actuals produce 0.0
    """

    name = "employee"

    def calculate(
        self,
        actual: float | None,
        target: float | None,
        direction: str | None,
    ) -> AchievementResult:
        actual_is_missing = _is_none_or_nan(actual)
        target_is_missing = _is_none_or_nan(target)

        act = 0.0 if actual_is_missing else float(actual)
        tgt = 0.0 if target_is_missing else float(target)

        is_inverse = direction == "lower_better"

        if is_inverse:
            if act == 0.0:
                raw_ratio = 1.0
            else:
                raw_ratio = tgt / act
        else:
            if tgt == 0.0:
                raw_ratio = 0.0
            else:
                raw_ratio = act / tgt

        capped_val = min(max(raw_ratio, 0.0), 1.0)

        # Determine state
        if actual_is_missing:
            state = "missing_actual"
        elif target_is_missing or tgt == 0.0:
            state = "invalid_target"
        elif act < 0:
            state = "negative_actual"
        else:
            state = "measured"

        return AchievementResult(value=capped_val, state=state, raw_ratio=raw_ratio)


class RollupPolicy(ScoringPolicy):
    """
    Reproduces kpi_aggregation.capped_achievement behavior.

    - Missing actual or target (None/NaN) -> None (excluded)
    - target <= 0 -> None (excluded)
    - Unknown direction -> None
    - lower_better with actual <= 0 -> 1.0
    - Capped at 0.0 .. 1.0
    """

    name = "rollup"

    def calculate(
        self,
        actual: float | None,
        target: float | None,
        direction: str | None,
    ) -> AchievementResult:
        if _is_none_or_nan(actual):
            return AchievementResult(value=None, state="missing_actual", raw_ratio=None)
        if _is_none_or_nan(target) or float(target) <= 0:
            return AchievementResult(value=None, state="invalid_target", raw_ratio=None)

        act = float(actual)
        tgt = float(target)

        if direction == "lower_better":
            if act <= 0:
                state = "negative_actual" if act < 0 else "measured"
                return AchievementResult(value=1.0, state=state, raw_ratio=1.0)
            ratio = tgt / act
            state = "measured"
        elif direction == "higher_better":
            ratio = act / tgt
            state = "negative_actual" if act < 0 else "measured"
        else:
            return AchievementResult(value=None, state="unknown_direction", raw_ratio=None)

        capped_val = min(max(ratio, 0.0), 1.0)
        return AchievementResult(value=capped_val, state=state, raw_ratio=ratio)


class ManagementPolicy(ScoringPolicy):
    """
    Reproduces management_bsc_service._direction_ratio behavior.

    - Missing actual or target -> None
    - lower_better: actual == 0 -> 1.0 if target == 0 else None
    - higher_better: target == 0 -> 1.0 if actual == 0 else None
    - NOT capped: returns raw ratio (can be > 1.0 or negative)
    """

    name = "management"

    def calculate(
        self,
        actual: float | None,
        target: float | None,
        direction: str | None,
    ) -> AchievementResult:
        if _is_none_or_nan(actual):
            return AchievementResult(value=None, state="missing_actual", raw_ratio=None)
        if _is_none_or_nan(target):
            return AchievementResult(value=None, state="invalid_target", raw_ratio=None)

        act = float(actual)
        tgt = float(target)

        if direction == "lower_better":
            if act == 0.0:
                if tgt == 0.0:
                    return AchievementResult(value=1.0, state="measured", raw_ratio=1.0)
                return AchievementResult(value=None, state="measured", raw_ratio=None)
            ratio = tgt / act
            state = "negative_actual" if act < 0 else "measured"
            return AchievementResult(value=ratio, state=state, raw_ratio=ratio)

        # higher_better or others
        if tgt == 0.0:
            if act == 0.0:
                return AchievementResult(value=1.0, state="measured", raw_ratio=1.0)
            return AchievementResult(value=None, state="invalid_target", raw_ratio=None)

        ratio = act / tgt
        state = "negative_actual" if act < 0 else "measured"
        return AchievementResult(value=ratio, state=state, raw_ratio=ratio)


class FunctionPolicy(ScoringPolicy):
    """
    Policy for upcoming Functional performance level:

    - higher_better: actual/target capped 0..1
    - lower_better: target/actual capped 0..1
    - actual missing -> excluded (counts against coverage), state: missing_actual
    - target missing or <= 0 -> invalid_target, excluded
    - actual == 0 & lower_better -> 1.0
    - actual == 0 & higher_better -> 0.0
    - negative actual -> 0.0 flagged (state: negative_actual)
    - unknown direction -> state: unknown_direction, value: None
    """

    name = "function"

    def calculate(
        self,
        actual: float | None,
        target: float | None,
        direction: str | None,
    ) -> AchievementResult:
        if _is_none_or_nan(actual):
            return AchievementResult(value=None, state="missing_actual", raw_ratio=None)
        if _is_none_or_nan(target) or float(target) <= 0:
            return AchievementResult(value=None, state="invalid_target", raw_ratio=None)
        if direction not in ("higher_better", "lower_better"):
            return AchievementResult(value=None, state="unknown_direction", raw_ratio=None)

        act = float(actual)
        tgt = float(target)

        # Flag negative actuals: 0.0 achievement
        if act < 0:
            raw = (tgt / act) if direction == "lower_better" else (act / tgt)
            return AchievementResult(value=0.0, state="negative_actual", raw_ratio=raw)

        if direction == "lower_better":
            if act == 0.0:
                return AchievementResult(value=1.0, state="measured", raw_ratio=1.0)
            raw = tgt / act
            return AchievementResult(value=min(max(raw, 0.0), 1.0), state="measured", raw_ratio=raw)

        # higher_better
        if act == 0.0:
            return AchievementResult(value=0.0, state="measured", raw_ratio=0.0)
        raw = act / tgt
        return AchievementResult(value=min(max(raw, 0.0), 1.0), state="measured", raw_ratio=raw)


# Explicit named instances
EMPLOYEE_POLICY = EmployeePolicy()
ROLLUP_POLICY = RollupPolicy()
MANAGEMENT_POLICY = ManagementPolicy()
FUNCTION_POLICY = FunctionPolicy()


# ---------------------------------------------------------------------------
# Pure Engine Functions
# ---------------------------------------------------------------------------

def achievement(
    actual: float | None,
    target: float | None,
    direction: str | None,
    policy: ScoringPolicy = EMPLOYEE_POLICY,
) -> AchievementResult:
    """
    Calculate KPI achievement ratio according to the specified policy.

    Args:
        actual: Actual performance value
        target: Target performance value
        direction: Optimization direction ('higher_better' or 'lower_better')
        policy: Scoring policy to evaluate with

    Returns:
        AchievementResult with value (0..1 or None), state, and raw_ratio.
    """
    return policy.calculate(actual, target, direction)


def contribution(
    achievement_val: float | None,
    weight: float,
) -> float | None:
    """
    Calculate the weighted contribution of a KPI.

    Args:
        achievement_val: Achievement ratio (0-1 decimal scale) or None
        weight: Allocated weight for this KPI (0-1 scale)

    Returns:
        Contribution (achievement * weight) or None if achievement is None.
    """
    if achievement_val is None or _is_none_or_nan(achievement_val):
        return None
    return float(achievement_val) * float(weight)


def score(
    kpi_results: Sequence[KPIResult | Mapping[str, Any]],
) -> ScoreResult:
    """
    Aggregate KPI results into an overall score, coverage, and state.

    Score is calculated as: earned ÷ measured_weight * 100
    when partial data exists.

    Args:
        kpi_results: Sequence of KPIResult or dicts containing achievement/weight.

    Returns:
        ScoreResult with score (0-100), earned, measured_weight, configured_weight, coverage, state.
    """
    if not kpi_results:
        return ScoreResult(
            score=None,
            earned=None,
            measured_weight=0.0,
            configured_weight=0.0,
            coverage=None,
            state="no_data",
        )

    configured_weight = 0.0
    measured_weight = 0.0
    earned = 0.0
    measured_count = 0

    for item in kpi_results:
        if isinstance(item, KPIResult):
            ach = item.achievement
            w = float(item.weight)
            c = item.contribution
            measured_override = item.measured
        elif isinstance(item, Mapping):
            ach = item.get("achievement")
            if ach is None:
                ach = item.get("achievement_ratio")
            w = float(item.get("weight") or item.get("weight_applied") or 0.0)
            c = item.get("contribution")
            measured_override = item.get("measured")
        else:
            ach = getattr(item, "achievement", getattr(item, "achievement_ratio", None))
            w = float(getattr(item, "weight", getattr(item, "weight_applied", 0.0)))
            c = getattr(item, "contribution", None)
            measured_override = getattr(item, "measured", None)

        configured_weight += w

        is_measured = (
            bool(measured_override)
            if measured_override is not None
            else ach is not None and not _is_none_or_nan(ach)
        )
        if is_measured:
            measured_count += 1
            measured_weight += w
            if c is not None and not _is_none_or_nan(c):
                earned += float(c)
            elif ach is not None and not _is_none_or_nan(ach):
                earned += float(ach) * w

    coverage = (measured_weight / configured_weight) if configured_weight > 0 else None

    if measured_count == 0:
        return ScoreResult(
            score=None,
            earned=None,
            measured_weight=measured_weight,
            configured_weight=configured_weight,
            coverage=coverage,
            state="no_data",
        )

    if measured_weight <= 0:
        return ScoreResult(
            score=None,
            earned=earned,
            measured_weight=measured_weight,
            configured_weight=configured_weight,
            coverage=coverage,
            state="measured" if measured_count == len(kpi_results) else "provisional",
        )

    raw_score = (earned / measured_weight) * 100.0
    final_score = min(raw_score, 100.0)
    state = "measured" if measured_count == len(kpi_results) else "provisional"

    return ScoreResult(
        score=final_score,
        earned=earned,
        measured_weight=measured_weight,
        configured_weight=configured_weight,
        coverage=coverage,
        state=state,
    )


def status(score_val: float | None) -> str:
    """
    Determine qualitative status from performance score using standard bands:
    - On Track: >= 85
    - Attention: 75 – 84.99
    - At Risk: < 75
    - None: No data
    """
    if score_val is None or _is_none_or_nan(score_val):
        return "No data"
    s = float(score_val)
    if s >= 85.0:
        return "On Track"
    if s >= 75.0:
        return "Attention"
    return "At Risk"


def grade(
    score_val: float | None,
    thresholds: Mapping[str, float] | None = None,
) -> str | None:
    """
    Assign letter grade based on score and thresholds.

    Default thresholds:
    A: >= 95, B: >= 90, C: >= 80, D: >= 70, E: < 70
    """
    if score_val is None or _is_none_or_nan(score_val):
        return None

    s = float(score_val)
    th = thresholds or {}
    th_a = float(th.get("A", 95))
    th_b = float(th.get("B", 90))
    th_c = float(th.get("C", 80))
    th_d = float(th.get("D", 70))

    if s >= th_a:
        return "A"
    if s >= th_b:
        return "B"
    if s >= th_c:
        return "C"
    if s >= th_d:
        return "D"
    return "E"


def validate_weights(weights: Sequence[float] | Mapping[str, float]) -> None:
    """
    Validate that KPI weights sum to 1.0 (±0.001).

    Does NOT auto-normalize. Raises ValueError on failure.
    """
    vals = weights.values() if isinstance(weights, Mapping) else weights
    total = sum(float(w) for w in vals)
    if abs(total - 1.0) > 0.001:
        raise ValueError(
            f"KPI weights must sum to 1.0 (±0.001). Current sum: {total:.4f}"
        )
