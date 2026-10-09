"""Score one pinned basis with the existing engine. Preview and commit both call this."""

from __future__ import annotations

import math
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


def _finite(value: Any, label: str) -> Decimal:
    """Reject missing, non-numeric, and non-finite configuration or evidence."""
    from services.evaluation.access import EvaluationError

    if value is None or value == "":
        raise EvaluationError(f"{label} is missing.", code="nonfinite_evidence")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise EvaluationError(f"{label} must be a finite number.", code="nonfinite_evidence") from exc
    if not number.is_finite():
        raise EvaluationError(f"{label} must be a finite number.", code="nonfinite_evidence")
    try:
        rendered = float(number)
    except (OverflowError, ValueError) as exc:
        raise EvaluationError(f"{label} must be a finite number.", code="nonfinite_evidence") from exc
    # Decimal('1e999') is finite and float('1e-400') collapses to 0. Neither may enter a score.
    if not math.isfinite(rendered) or (rendered == 0.0 and number != 0):
        raise EvaluationError(f"{label} is outside the finite range used for scores.", code="nonfinite_evidence")
    return number


def _require_json_finite(value: Any, label: str) -> None:
    from services.evaluation.access import EvaluationError

    if value is None:
        return
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise EvaluationError(f"{label} must be a finite number.", code="nonfinite_evidence") from exc
    if not math.isfinite(number):
        raise EvaluationError(f"{label} must be a finite number.", code="nonfinite_evidence")


def _missing_actual(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def decimal_places(value: Decimal) -> int:
    exponent = value.normalize().as_tuple().exponent
    return 0 if not isinstance(exponent, int) or exponent >= 0 else -exponent


def score_rows(level: str, lines: list[dict], rows: list[dict]) -> list[dict]:
    """Score a complete weighted contract. Partial inputs are refused, not skipped.

    A numeric actual of zero stays zero. A missing actual is not coerced to zero,
    so a missing lower-is-better actual cannot become 100% success. Known
    zero-weight lines are diagnostics: they stay visible when the caller sends
    them and are not required. Unknown keys, duplicate keys, and non-finite
    values are rejected before a score is returned.
    """
    from services.evaluation.access import EvaluationError

    if not isinstance(lines, list) or not isinstance(rows, list):
        raise EvaluationError("Scoring evidence must list the approved contract and the input rows.", code="incomplete_evidence")
    policy = POLICIES.get(level, EMPLOYEE_POLICY)
    by_key: dict[str, dict] = {}
    for line in lines:
        key = str(line.get("kpi_key") or "")
        if not key or key in by_key:
            raise EvaluationError("The approved contract has a blank or duplicate KPI key.", code="duplicate_kpi")
        weight = _finite(line.get("weight"), f"Weight for {key}")
        if weight < 0:
            raise EvaluationError(f"Weight for {key} must be zero or greater.", code="nonfinite_evidence")
        if line.get("target") not in (None, ""):
            _finite(line.get("target"), f"Target for {key}")
        by_key[key] = line

    provided: dict[str, dict] = {}
    for row in rows:
        key = str(row.get("kpi_key") or "")
        if not key or key in provided:
            raise EvaluationError("Scoring input has a blank or duplicate KPI key.", code="duplicate_kpi", kpi_key=key)
        if key not in by_key:
            raise EvaluationError(
                f"{key} is not in the approved contract. Unknown rows are not treated as diagnostics.",
                code="unknown_kpi",
                kpi_key=key,
            )
        provided[key] = row

    missing = [
        key
        for key, line in by_key.items()
        if _finite(line.get("weight"), f"Weight for {key}") > 0 and key not in provided
    ]
    if missing:
        raise EvaluationError(
            "Required weighted evidence is incomplete: " + ", ".join(missing) + ".",
            code="incomplete_evidence",
            missing=missing,
        )

    scored = []
    for key, line in by_key.items():
        if key not in provided:
            continue
        row = provided[key]
        weight = _finite(line.get("weight"), f"Weight for {key}")
        workbook = row.get("workbook_target")
        workbook_number = None if workbook in (None, "") else _finite(workbook, f"Workbook target for {key}")
        if _missing_actual(row.get("actual")):
            if weight > 0:
                raise EvaluationError(
                    f"Actual for {key} is missing. A missing actual is not scored as zero, so it cannot become full success.",
                    code="missing_actual",
                    kpi_key=key,
                )
            target = _target_for(line, row, required=False)
            scored.append(_row_body(key, line, weight, actual=None, target=target, workbook=workbook_number, result_value=None, result_state="missing_actual", share=None, row=row))
            continue
        actual = _finite(row.get("actual"), f"Actual for {key}")
        target = _target_for(line, row, required=weight > 0)
        result = achievement(
            float(actual),
            float(target) if target is not None else None,
            line.get("direction"),
            policy=policy,
        )
        _require_json_finite(result.value, f"Achievement for {key}")
        _require_json_finite(result.raw_ratio, f"Achievement for {key}")
        share = contribution(result.value, float(weight))
        _require_json_finite(share, f"Contribution for {key}")
        scored.append(_row_body(key, line, weight, actual=actual, target=target, workbook=workbook_number, result_value=result.value, result_state=result.state, share=share, row=row))
    return scored


def _target_for(line: dict, row: dict, *, required: bool) -> Decimal | None:
    if line.get("target_mode") == "fixed" and line.get("target") is not None:
        return _finite(line.get("target"), f"Target for {line.get('kpi_key')}")
    workbook = row.get("workbook_target")
    if workbook not in (None, ""):
        return _finite(workbook, f"Workbook target for {line.get('kpi_key')}")
    if line.get("target") not in (None, ""):
        return _finite(line.get("target"), f"Target for {line.get('kpi_key')}")
    if required:
        from services.evaluation.access import EvaluationError

        raise EvaluationError(
            f"Target for {line.get('kpi_key')} is missing.",
            code="incomplete_evidence",
            kpi_key=line.get("kpi_key"),
        )
    return None


def _row_body(key, line, weight, *, actual, target, workbook, result_value, result_state, share, row) -> dict:
    # Workbook achievements never drive this calculation. Keep valid diagnostic
    # numbers only; Excel NaN/Infinity must not make an otherwise valid DTO invalid.
    ignored = row.get("precomputed_achievement")
    try:
        ignored = None if ignored is None else float(ignored)
    except (ValueError, TypeError, OverflowError):
        ignored = None
    if ignored is not None and not math.isfinite(ignored):
        ignored = None
    return {
        "kpi_key": key,
        "label": line.get("label") or key,
        "actual": float(actual) if actual is not None else None,
        "target": float(target) if target is not None else None,
        "workbook_target": float(workbook) if workbook is not None else None,
        "weight": float(weight),
        "direction": line.get("direction"),
        "target_mode": line.get("target_mode"),
        "achievement": result_value,
        "achievement_state": result_state,
        "contribution": share,
        "ignored_precomputed_achievement": ignored,
    }


def overall_score(scored: list[dict]) -> float | None:
    if not scored:
        return None
    total = 0.0
    for row in scored:
        share = row.get("contribution")
        if share is None:
            continue
        _require_json_finite(share, "Contribution")
        total += float(share)
    _require_json_finite(total, "Total contribution")
    score = round(min(max(total, 0.0), 1.0) * 100.0, 2)
    _require_json_finite(score, "Score")
    return score


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
                    "workbook_target": float(_finite(workbook, f"Workbook target for {line['kpi_key']}")),
                    "approved_target": float(_finite(approved, f"Approved target for {line['kpi_key']}")),
                }
            )
    return found
