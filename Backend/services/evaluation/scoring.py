"""Score one pinned basis with the existing engine. Preview and commit both call this."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from services.scoring.engine import (
    EMPLOYEE_POLICY,
    FUNCTION_POLICY,
    MANAGEMENT_POLICY,
    achievement,
    contribution,
)

SUPPORTED_DIRECTIONS = {"higher_better", "lower_better"}
POLICIES = {
    "Employee": EMPLOYEE_POLICY,
    "Managerial": MANAGEMENT_POLICY,
    "Corporate": MANAGEMENT_POLICY,
    "Function": FUNCTION_POLICY,
}


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        return None
    return number


def decimal_places(value: Decimal) -> int:
    exponent = value.normalize().as_tuple().exponent
    return 0 if not isinstance(exponent, int) or exponent >= 0 else -exponent


def score_rows(level: str, lines: list[dict], rows: list[dict]) -> list[dict]:
    """Return achievement on the engine's 0..1 scale and contribution = achievement x weight."""
    policy = POLICIES.get(level, EMPLOYEE_POLICY)
    by_key = {str(line["kpi_key"]): line for line in lines}
    scored = []
    for row in rows:
        key = str(row.get("kpi_key") or "")
        line = by_key.get(key)
        if line is None:
            continue
        actual = _decimal(row.get("actual"))
        if line.get("target_mode") == "fixed" and line.get("target") is not None:
            target = _decimal(line.get("target"))
        else:
            target = _decimal(row.get("workbook_target"))
            if target is None:
                target = _decimal(line.get("target"))
        result = achievement(
            float(actual) if actual is not None else None,
            float(target) if target is not None else None,
            line.get("direction"),
            policy=policy,
        )
        ratio = result.value
        weight = float(_decimal(line.get("weight")) or 0)
        share = contribution(ratio, weight)
        scored.append(
            {
                "kpi_key": key,
                "label": line.get("label") or key,
                "actual": float(actual) if actual is not None else None,
                "target": float(target) if target is not None else None,
                "workbook_target": float(_decimal(row.get("workbook_target"))) if _decimal(row.get("workbook_target")) is not None else None,
                "weight": weight,
                "direction": line.get("direction"),
                "target_mode": line.get("target_mode"),
                "achievement": ratio,
                "achievement_state": result.state,
                "contribution": share,
                "ignored_precomputed_achievement": row.get("precomputed_achievement"),
            }
        )
    return scored


def overall_score(scored: list[dict]) -> float | None:
    if not scored:
        return None
    total = sum(float(row.get("contribution") or 0) for row in scored)
    return round(min(max(total, 0.0), 1.0) * 100.0, 2)


def grade_for(score: float | None, thresholds: dict | None) -> str | None:
    if score is None:
        return None
    bands = thresholds or {"A": 95, "B": 85, "C": 75, "D": 65}
    if score >= float(bands.get("A", 95)):
        return "A"
    if score >= float(bands.get("B", 85)):
        return "B"
    if score >= float(bands.get("C", 75)):
        return "C"
    if score >= float(bands.get("D", 65)):
        return "D"
    return "E"


def conflicts_for(lines: list[dict], rows: list[dict]) -> list[dict]:
    """Fixed approved targets that differ from the workbook target. No acknowledgement bypass."""
    by_key = {str(line["kpi_key"]): line for line in lines}
    found = []
    for row in rows:
        line = by_key.get(str(row.get("kpi_key") or ""))
        if not line or line.get("target_mode") != "fixed" or line.get("target") is None:
            continue
        workbook = _decimal(row.get("workbook_target"))
        approved = _decimal(line.get("target"))
        if workbook is None or approved is None:
            continue
        if abs(workbook - approved) > Decimal("0.0001"):
            found.append(
                {
                    "kpi_key": line["kpi_key"],
                    "workbook_target": float(workbook),
                    "approved_target": float(approved),
                }
            )
    return found
