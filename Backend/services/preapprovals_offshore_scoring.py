"""Pre-Approvals IP Offshore scoring from raw request counters.

Pure Python: no pandas, no database. The importer, the upload seeding path,
the dashboard read paths and the rescore command all call this module, so the
formula lives in one place.

From the effective period (June 2026) the team is scored from raw counts. The
workbook's achievement columns are not used. Earlier periods keep the legacy
formula in ``Data_Cleaning_Teams/preapprovals_offshore.py`` unchanged.

Counts per employee-month (names as stored in ``raw_data``):
    AssignedRequest (F), ApprovedRequests (G), RejectedRequests (H),
    PolicyRej (N), ApprovalWithin48HR (R), SubmittedClaims (S), ErrosClaims (T).
"""

from __future__ import annotations

import calendar
import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Mapping

# The one place the effective period is written down.
EFFECTIVE_YEAR = 2026
EFFECTIVE_MONTH = 6
EFFECTIVE_PERIOD_TEXT = "June 2026"

NEW_METHOD_ID = "preapprovals_offshore_v2"
TEAM_NAME = "Pre-Approvals IP Offshore"

# Fixed targets for every period from the effective date.
TARGET_CONTROLLABLE_REJECTION_RATE = 0.01
TARGET_ERROR_RATE = 0.01
TARGET_APPROVAL_WITHIN_48H = 0.90

WEIGHTS = {"Rejection": 0.50, "InitialError": 0.20, "Submission": 0.30}
# Fixed alternative set used when SubmittedClaims is 0. Not a redistribution.
WEIGHTS_WITHOUT_CLAIMS = {"Rejection": 0.60, "InitialError": 0.00, "Submission": 0.40}
DEFAULT_GRADE_THRESHOLDS = {"A": 95, "B": 85, "C": 75, "D": 65}

RAW_COUNT_COLUMNS = (
    "AssignedRequest",
    "ApprovedRequests",
    "RejectedRequests",
    "PolicyRej",
    "ApprovalWithin48HR",
    "SubmittedClaims",
    "ErrosClaims",
)

# Derived values written next to the raw counts. Existing raw keys are never changed.
DERIVED_RAW_KEYS = (
    "ControllableRejections",
    "ControllableRejectionRate",
    "PolicyRejectionRate",
    "PolicyShareOfRejections",
    "ScoringMethod",
)

POLICY_INDICATOR_KEY = "PolicyRejection"

_MONTH_NUMBERS = {name.lower(): number for number, name in enumerate(calendar.month_name) if number}
_MONTH_NUMBERS.update({name.lower(): number for number, name in enumerate(calendar.month_abbr) if number})


class OffshoreDataError(ValueError):
    """A required count is missing or unusable. The message names the column."""

    def __init__(self, column: str, reason: str):
        self.column = column
        self.reason = reason
        super().__init__(f"{column}: {reason}")


@dataclass(frozen=True)
class OffshoreCounts:
    assigned: float  # F
    approved: float  # G
    rejected: float  # H
    policy_rejected: float  # N
    approved_within_48h: float  # R
    submitted: float  # S
    errors: float  # T


@dataclass(frozen=True)
class OffshoreScore:
    counts: OffshoreCounts
    controllable_rejections: float  # O = max(H - N, 0)
    controllable_rejection_rate: float  # Q = O / F
    error_rate: float  # V = T / S (0 when S is 0; not applicable then)
    approval_within_48h_rate: float  # W = R / G
    policy_share: float  # P = N / H, clamped to 0..1 (display only)
    policy_rejection_rate: float  # N / F (display only)
    achievements: dict[str, float | None]  # InitialError is None when not applicable
    weights: dict[str, float]
    score: float  # percentage, rounded to 2 decimals
    grade: str
    claims_submitted: bool


def uses_new_method(year: Any, month: Any) -> bool:
    """True when the reporting period is the effective period or later."""
    number = month_number(month)
    if number is None or year is None:
        return False
    return (int(year), number) >= (EFFECTIVE_YEAR, EFFECTIVE_MONTH)


def month_number(month: Any) -> int | None:
    """Return 1-12 for a month number or an English month name, else None."""
    if month is None or isinstance(month, bool):
        return None
    if isinstance(month, int):
        return month if 1 <= month <= 12 else None
    if isinstance(month, float) and math.isfinite(month) and month.is_integer():
        return month_number(int(month))
    text = str(month).strip().lower()
    if text.isdigit():
        return month_number(int(text))
    return _MONTH_NUMBERS.get(text)


_ISO_PERIOD = re.compile(r"^\s*(\d{4})[-/](\d{1,2})(?:[-/]\d{1,2})?\s*$")
_DAY_FIRST_DATE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")
_NAMED_PERIOD = re.compile(r"^\s*([A-Za-z]+)\.?,?\s+(\d{4})\s*$")


def _period_from_value(value: Any) -> tuple[int, int] | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        match = _ISO_PERIOD.match(text)
        if match:
            return _valid_period(int(match.group(1)), int(match.group(2)))
        match = _DAY_FIRST_DATE.match(text)
        if match:
            return _valid_period(int(match.group(3)), int(match.group(2)))
        match = _NAMED_PERIOD.match(text)
        if match:
            number = month_number(match.group(1))
            return _valid_period(int(match.group(2)), number) if number else None
        return None
    # datetime, date and pandas Timestamp. NaT has a float year and is skipped.
    year = getattr(value, "year", None)
    month = getattr(value, "month", None)
    if isinstance(year, int) and isinstance(month, int):
        return _valid_period(year, month)
    return None


def _valid_period(year: int, month: int | None) -> tuple[int, int] | None:
    if month is None or not 1 <= month <= 12 or year < 1900:
        return None
    return year, month


def reporting_period_from_row(row: Mapping[str, Any]) -> tuple[int, int] | None:
    """(year, month) of one row, from ``Date``, else ``Month``, else ``Month`` + ``Year``.

    Returns None when the period cannot be determined. Callers must treat that
    as an error for the row, never as a default period.
    """
    period = _period_from_value(row.get("Date"))
    if period:
        return period
    month_value = row.get("Month")
    period = _period_from_value(month_value)
    if period:
        return period
    number = month_number(month_value) if isinstance(month_value, str) else None
    year = row.get("Year")
    if number and year is not None and not isinstance(year, bool):
        try:
            year_number = int(float(str(year).strip()))
        except ValueError:
            return None
        return _valid_period(year_number, number)
    return None


def _number(value: Any, column: str) -> float:
    if value is None:
        raise OffshoreDataError(column, "no value")
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            raise OffshoreDataError(column, "no value")
        try:
            number = float(text)
        except ValueError as exc:
            raise OffshoreDataError(column, "not a number") from exc
    else:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise OffshoreDataError(column, "not a number") from exc
    if not math.isfinite(number):
        raise OffshoreDataError(column, "no value")
    if number < 0:
        raise OffshoreDataError(column, "negative count")
    return number


def counts_from_mapping(row: Mapping[str, Any]) -> OffshoreCounts:
    """Read the seven raw counts from one row. Missing or unusable values raise."""
    values: dict[str, float] = {}
    for column in RAW_COUNT_COLUMNS:
        if column not in row:
            raise OffshoreDataError(column, "column is missing")
        values[column] = _number(row[column], column)
    return OffshoreCounts(
        assigned=values["AssignedRequest"],
        approved=values["ApprovedRequests"],
        rejected=values["RejectedRequests"],
        policy_rejected=values["PolicyRej"],
        approved_within_48h=values["ApprovalWithin48HR"],
        submitted=values["SubmittedClaims"],
        errors=values["ErrosClaims"],
    )


def _round_half_up(value: float, places: int) -> float:
    quantum = Decimal(1).scaleb(-places)
    return float(Decimal(repr(float(value))).quantize(quantum, rounding=ROUND_HALF_UP))


def grade_for(score: float, thresholds: Mapping[str, Any] | None = None) -> str:
    limits = thresholds or DEFAULT_GRADE_THRESHOLDS
    for grade in ("A", "B", "C", "D"):
        if score >= float(limits[grade]):
            return grade
    return "E"


def score_counts(counts: OffshoreCounts, grade_thresholds: Mapping[str, Any] | None = None) -> OffshoreScore:
    """Apply the June 2026 method to one employee-month's counts."""
    assigned, approved, rejected = counts.assigned, counts.approved, counts.rejected
    policy, within_48h, submitted, errors = counts.policy_rejected, counts.approved_within_48h, counts.submitted, counts.errors

    controllable = max(rejected - policy, 0.0)
    controllable_rate = controllable / assigned if assigned else 0.0
    error_rate = errors / submitted if submitted else 0.0
    approval_rate = within_48h / approved if approved else 0.0
    policy_share = min(policy / rejected, 1.0) if rejected else 0.0
    policy_rate = policy / assigned if assigned else 0.0

    rejection_achievement = 1.0 if controllable_rate == 0 else min(1.0, TARGET_CONTROLLABLE_REJECTION_RATE / controllable_rate)
    if not submitted:
        error_achievement: float | None = None
    elif error_rate == 0:
        error_achievement = 1.0
    else:
        error_achievement = min(1.0, TARGET_ERROR_RATE / error_rate)
    submission_achievement = min(1.0, approval_rate / TARGET_APPROVAL_WITHIN_48H)

    claims_submitted = submitted != 0
    weights = dict(WEIGHTS if claims_submitted else WEIGHTS_WITHOUT_CLAIMS)
    total = (
        rejection_achievement * weights["Rejection"]
        + (error_achievement or 0.0) * weights["InitialError"]
        + submission_achievement * weights["Submission"]
    )
    score = _round_half_up(total * 100, 2)

    return OffshoreScore(
        counts=counts,
        controllable_rejections=controllable,
        controllable_rejection_rate=controllable_rate,
        error_rate=error_rate,
        approval_within_48h_rate=approval_rate,
        policy_share=policy_share,
        policy_rejection_rate=policy_rate,
        achievements={
            "Rejection": rejection_achievement,
            "InitialError": error_achievement,
            "Submission": submission_achievement,
        },
        weights=weights,
        score=score,
        grade=grade_for(score, grade_thresholds),
        claims_submitted=claims_submitted,
    )


def score_row(row: Mapping[str, Any], grade_thresholds: Mapping[str, Any] | None = None) -> OffshoreScore:
    return score_counts(counts_from_mapping(row), grade_thresholds)


def derived_raw_values(result: OffshoreScore) -> dict[str, Any]:
    """Values written to ``raw_data`` for a row scored by the June 2026 method."""
    return {
        "ControllableRejections": round(result.controllable_rejections, 6),
        "ControllableRejectionRate": round(result.controllable_rejection_rate, 6),
        "PolicyRejectionRate": round(result.policy_rejection_rate, 6),
        "PolicyShareOfRejections": round(result.policy_share, 6),
        "ScoringMethod": NEW_METHOD_ID,
    }


def kpi_values(result: OffshoreScore, kpi_meta: Mapping[str, Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    """KPI rows in the same shape as ``kpi_service.calculate_performance_multi_team``.

    ``kpi_meta`` supplies label, unit, color and direction from the team config.
    The policy indicator has weight 0 and no contribution. Its target is a
    placeholder of 0 and is flagged ``tracking_only``.
    """
    meta = kpi_meta or {}

    def describe(key: str, fallback_label: str) -> dict[str, Any]:
        source = meta.get(key, {})
        return {
            "label": source.get("label", fallback_label),
            "unit": source.get("unit", "%"),
            "color": source.get("color", "#64748B"),
            "direction": source.get("direction", "lower_better"),
        }

    rows: list[dict[str, Any]] = []

    def add(key: str, actual: float, target: float, achievement: float, weight: float, *, applicable: bool = True, tracking_only: bool = False) -> None:
        contribution = 0.0 if not applicable or tracking_only else achievement * weight
        rows.append({
            "kpi_key": key,
            **describe(key, key),
            "actual_value": round(actual, 4),
            "target_value": round(target, 4),
            "achievement_ratio": round(achievement, 4),
            "weight_applied": round(weight, 4),
            "contribution": round(contribution, 4),
            "applicable": applicable,
            "tracking_only": tracking_only,
        })

    add("Rejection", result.controllable_rejection_rate, TARGET_CONTROLLABLE_REJECTION_RATE, result.achievements["Rejection"] or 0.0, result.weights["Rejection"])
    applicable = result.claims_submitted
    add(
        "InitialError",
        result.error_rate,
        TARGET_ERROR_RATE,
        result.achievements["InitialError"] or 0.0,
        result.weights["InitialError"],
        applicable=applicable,
    )
    add("Submission", result.approval_within_48h_rate, TARGET_APPROVAL_WITHIN_48H, result.achievements["Submission"] or 0.0, result.weights["Submission"])
    add(
        POLICY_INDICATOR_KEY,
        result.policy_rejection_rate,
        0.0,
        0.0,
        0.0,
        tracking_only=True,
    )
    return rows


def actuals_from_row(row: Mapping[str, Any]) -> dict[str, float | None]:
    """Controllable rejection rate, error rate and 48-hour approval rate from raw counts."""
    result = score_row(row)
    return {
        "Rejection": result.controllable_rejection_rate,
        "InitialError": result.error_rate if result.claims_submitted else None,
        "Submission": result.approval_within_48h_rate,
    }


def config_grade_thresholds(team_config: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """The team's grade thresholds from its config (95/85/75/65 for this team)."""
    return (team_config or {}).get("grade_thresholds") or DEFAULT_GRADE_THRESHOLDS


def config_kpi_meta(team_config: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    """Label, unit, color and direction per KPI key, from the team config."""
    config = team_config or {}
    meta: dict[str, Mapping[str, Any]] = {}
    for item in list(config.get("kpis") or []) + list(config.get("tracking_indicators") or []):
        meta[str(item["key"])] = item
    return meta


def score_offshore_row(row: Mapping[str, Any], team_config: Mapping[str, Any] | None) -> OffshoreScore:
    """Score one row by the June 2026 method using the team config's grade thresholds."""
    return score_row(row, config_grade_thresholds(team_config))
