"""Published employee scores in the dated UAE trend workbook."""

import math

from data_cleaning.standard_mappings import calculate_grade
from services.clinical_trend_import import GRADE_LABELS
from services.csr_sharjah_scoring import (
    COMPLAINT_COUNT_COLUMN,
    GRADE_THRESHOLDS,
    SERVING_TIME_COLUMN,
    SERVING_TIME_TARGET,
    score_sharjah_csr,
)
from services.preapprovals_offshore_scoring import reporting_period_from_row
from utils.branch_scope import explicit_branch_key


METHOD_ID = "uae_published_employee_score"
TEAMS = frozenset({"CSR", "Coding", "Pharmacy", "Re-Submission", "Sales", "Submission"})
FIRST_PERIOD = (2026, 10)
INACTIVE_STAFF_GRADE = "inactive staff"


def uses_published_score(raw_data) -> bool:
    return isinstance(raw_data, dict) and raw_data.get("ScoringMethod") == METHOD_ID


def has_published_score_columns(team, region, performance_level, row) -> bool:
    if team not in TEAMS or region != "UAE" or performance_level != "Employee":
        return False
    if not {"Role", "PerformanceScore", "PerformanceGrade"}.issubset(row):
        return False
    period = reporting_period_from_row(row)
    return period is not None and period >= FIRST_PERIOD


def published_score(team, row) -> tuple[float, str] | None:
    grade_cell = str(row.get("PerformanceGrade") or "").strip().casefold()
    if grade_cell == INACTIVE_STAFF_GRADE:
        return None
    cell = row.get("PerformanceScore")
    score = _number(cell)
    if score is None:
        if cell is None or str(cell).strip().casefold() in {"", "-", "na", "n/a", "nan", "none"}:
            return None
        raise ValueError("Published Performance Score must be a valid percentage")
    percent = score * 100 if 0 <= score <= 1 else score
    if not 0 <= percent <= 100:
        raise ValueError("Published Performance Score must be between 0% and 100%")
    grade = GRADE_LABELS.get(grade_cell)
    if grade is None:
        grade = calculate_grade(percent, GRADE_THRESHOLDS if team == "CSR" else None)
    return round(percent, 2), grade


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _observation(definition, actual, target) -> dict | None:
    if actual is None or target is None:
        return None
    lower = definition["direction"] == "lower_better"
    if lower:
        ratio = 1 if actual == 0 else target / actual
    else:
        ratio = actual / target if target > 0 else 0
    return {
        "kpi_key": definition["key"],
        "label": definition["label"],
        "unit": definition.get("unit", "%"),
        "direction": definition["direction"],
        "actual_value": float(actual),
        "target_value": float(target),
        "achievement_ratio": min(max(float(ratio), 0), 1),
        "weight_applied": 0,
        "contribution": 0,
        "view_only": True,
    }


def published_kpi_values(team, row, score, config) -> list[dict]:
    """Preserve source observations without assigning unverified score weights."""
    definitions = config["kpis"]
    if team == "CSR":
        branch = explicit_branch_key({"raw_data": row})
        if branch in {"ajman", "sharjah"}:
            try:
                computed, _grade, evidence = score_sharjah_csr(row)
            except ValueError:
                pass
            else:
                if abs(computed - score) <= 0.01:
                    return evidence
        definitions = [
            {**definition, "direction": "lower_better"} if definition["key"] == "Queries" else definition
            for definition in definitions
        ]
        definitions.extend([
            {
                "key": "ServingTime", "label": "Serving Time", "unit": "min",
                "direction": "lower_better", "actual_col": SERVING_TIME_COLUMN,
                "source_target": SERVING_TIME_TARGET,
            },
            {
                "key": "Complaints", "label": "Complaints", "unit": "number",
                "direction": "lower_better", "actual_col": COMPLAINT_COUNT_COLUMN,
                "source_target": 0,
            },
        ])

    from services.evaluation.workflow import _raw_lookup

    values = []
    for definition in definitions:
        _, actual_cell = _raw_lookup(row, definition.get("actual_col"))
        actual = _number(actual_cell)
        if "source_target" in definition:
            target = definition["source_target"]
        else:
            _, target_cell = _raw_lookup(row, definition.get("target_col"))
            target = _number(target_cell)
        value = _observation(definition, actual, target)
        if value is not None:
            values.append(value)
    return values
