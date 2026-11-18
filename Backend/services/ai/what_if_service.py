"""Deterministic What-If simulator for KPI improvement projection.

Computes "If I improve KPI X by N percentage points, what grade/score do I reach?"
Reuses the canonical scoring rules:
- target_ratio achievement (actual/target or target/actual for lower_better)
- GLOBAL_KPI_ACHIEVEMENT_CAP = 1.0
- grade_for / GRADE_THRESHOLD_MAP
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.loader import GLOBAL_KPI_ACHIEVEMENT_CAP
from utils.scoring_rules import letter_grade


@dataclass
class KpiInput:
    name: str
    actual: float
    target: float
    weight: float  # decimal, e.g. 0.25 for 25%
    direction: str = "higher_better"  # or "lower_better"


@dataclass
class WhatIfResult:
    kpi_name: str
    improvement_pct: float
    current_score: float  # percentage 0-100
    projected_score: float  # percentage 0-100
    current_grade: str
    projected_grade: str
    score_delta: float
    current_achievement: float
    projected_achievement: float
    capped: bool


def compute_achievement(actual: float, target: float, direction: str) -> float:
    """Compute achievement ratio for a target_ratio KPI, capped at 1.0."""
    if target <= 0:
        return 0.0
    if direction == "lower_better":
        if actual <= 0:
            return GLOBAL_KPI_ACHIEVEMENT_CAP
        ratio = target / actual
    else:
        ratio = actual / target
    return min(max(ratio, 0.0), GLOBAL_KPI_ACHIEVEMENT_CAP)


def compute_weighted_score(kpis: list[KpiInput]) -> float:
    """Compute weighted score as a percentage 0-100."""
    total = 0.0
    for kpi in kpis:
        ach = compute_achievement(kpi.actual, kpi.target, kpi.direction)
        total += ach * max(kpi.weight, 0.0)
    return round(total * 100.0, 2)


def simulate_kpi_improvement(
    kpis: list[KpiInput],
    kpi_name: str,
    improvement_pct: float,
) -> WhatIfResult | None:
    """Project the score change if one KPI improves by `improvement_pct` points.

    For lower_better KPIs, a positive improvement reduces the actual value.
    For higher_better KPIs, it increases the actual value.
    """
    target_kpi = next((k for k in kpis if k.name.casefold() == kpi_name.casefold()), None)
    if target_kpi is None:
        return None

    current_score = compute_weighted_score(kpis)
    current_grade = letter_grade(current_score)
    current_ach = compute_achievement(target_kpi.actual, target_kpi.target, target_kpi.direction)

    # Build projected KPI list with the modified actual value
    projected_kpis: list[KpiInput] = []
    for kpi in kpis:
        if kpi is target_kpi:
            if kpi.direction == "lower_better":
                new_actual = max(kpi.actual - improvement_pct, 0.0)
            else:
                new_actual = kpi.actual + improvement_pct
            projected_kpis.append(
                KpiInput(kpi.name, new_actual, kpi.target, kpi.weight, kpi.direction)
            )
        else:
            projected_kpis.append(kpi)

    projected_score = compute_weighted_score(projected_kpis)
    projected_grade = letter_grade(projected_score)
    projected_target = next(k for k in projected_kpis if k.name.casefold() == kpi_name.casefold())
    projected_ach = compute_achievement(
        projected_target.actual,
        projected_target.target,
        projected_target.direction,
    )

    return WhatIfResult(
        kpi_name=kpi_name,
        improvement_pct=improvement_pct,
        current_score=current_score,
        projected_score=projected_score,
        current_grade=current_grade,
        projected_grade=projected_grade,
        score_delta=round(projected_score - current_score, 2),
        current_achievement=round(current_ach, 4),
        projected_achievement=round(projected_ach, 4),
        capped=current_ach >= GLOBAL_KPI_ACHIEVEMENT_CAP or projected_ach >= GLOBAL_KPI_ACHIEVEMENT_CAP,
    )


def simulate_kpi_improvement_dict(kpis: list[dict[str, Any]], kpi_name: str, improvement_pct: float) -> dict[str, Any] | None:
    """Dict-based wrapper for API/LLM tool use."""
    typed = [
        KpiInput(
            name=str(k.get("name") or ""),
            actual=float(k.get("actual") or 0),
            target=float(k.get("target") or 0),
            weight=float(k.get("weight") or 0),
            direction=str(k.get("direction") or "higher_better"),
        )
        for k in kpis
    ]
    result = simulate_kpi_improvement(typed, kpi_name, improvement_pct)
    if result is None:
        return None
    return {
        "kpi_name": result.kpi_name,
        "improvement_pct": result.improvement_pct,
        "current_score": result.current_score,
        "projected_score": result.projected_score,
        "current_grade": result.current_grade,
        "projected_grade": result.projected_grade,
        "score_delta": result.score_delta,
        "current_achievement": result.current_achievement,
        "projected_achievement": result.projected_achievement,
        "capped": result.capped,
    }
