"""Period-specific Outbound basis. This is not the monthly catalog.

Catalog and workflow code should call ``canonical_outbound_basis`` and
``assess_monthly_actuals`` when a month template is attached later. This
module does not read or write ``config/teams/outbound.json``. That file stays
the technical four-KPI baseline.

Call contract::

    basis = canonical_outbound_basis(year, month)
    decision = period_capability(year, month)
    evidence = assess_monthly_actuals(year, month, actuals_by_kpi_key)

``decision["lines"]`` is the canonical scored set for that exact period.
``decision["approved_binding"]`` is ``apply`` or ``refuse``. ``refuse`` means an
independently approved snapshot must not be scored and must not fall back to
the workbook total. ``decision["catalog_template_supported"]`` is true only for
July 2026 and August 2026. ``decision["silent_fallback"]`` and
``decision["infer_from_august"]`` are always false. Upload dry-run and commit
share ``seeding_service.pin_upload_score``, which calls
``resolver.score_basis`` and does not catch its errors.

``basis["status"]`` is ``june_2026_exception``, ``july_2026``, ``august_2026``,
``technical_baseline``, or ``unconfigured``. ``basis["infer_from_august"]`` is
always false. A September 2026 (or later) caller must not copy
``august_2026`` lines. ``evidence["sufficient"]`` is false when a scored
actual on the requested basis is missing. That refusal is visible: callers
do not zero-fill, drop the KPI, renormalize the other weights, or derive
Productivity from available time or a stored trend score.

The stable KPI key is ``Productivity``. Reachability stays on the existing
key ``Other``. AHT stays a zero-weight diagnostic and is not part of the
scored lines.
"""

from __future__ import annotations

import datetime
import math
from typing import Any, Mapping

from services.evaluation.periods import MONTHS, PeriodError, month_number
from services.scoring.engine import (
    EMPLOYEE_POLICY,
    KPIResult,
    achievement,
    contribution,
    score,
)


PRODUCTIVITY_KEY = "Productivity"
REACHABILITY_KEY = "Other"
AHT_KEY = "AHT"

# Existing standard-mapping aliases, plus the A./T. rate columns used by the
# outbound sheet. Matching is exact after spaces are removed. Available-time
# and AHT columns are not aliases.
PRODUCTIVITY_ACTUAL_ALIASES = (
    "Productivity",
    "Productivity %",
    "Productivity%",
    "Productivity Score",
    "A.Productivity",
    "A.Productivity%",
    "A.Productivity %",
)
PRODUCTIVITY_TARGET_ALIASES = (
    "T.Productivity%",
    "T.Productivity",
    "T.Productivity %",
)

# Columns whose unit is a ratio. A date-formatted cell in one of these columns
# still stores a numeric serial (0.65), and that serial is the scoring value.
KNOWN_PERCENT_COLUMNS = (
    "A.Attend%",
    "T.Attend%",
    "A.Booking%",
    "T.Booking%",
    "A.QualityScore",
    "T.Quality%",
    "A.Reachability%",
    "T.Reachability%",
    "AttendC.RAch%",
    "BookingC.RAch%",
    "QualityAch%",
    "Reachability%Ach%",
    *PRODUCTIVITY_ACTUAL_ALIASES,
    *PRODUCTIVITY_TARGET_ALIASES,
)

OUTBOUND_SHEET_NAMES = ("Outbound", "Outbound Offshore Call Center")

TECHNICAL_LINES = (
    {"kpi_key": "Attendance", "weight_key": "Attend", "label": "Attendance Rate", "weight": 0.70, "target": None},
    {"kpi_key": "Booking", "weight_key": "Booking", "label": "Booking Rate", "weight": 0.10, "target": None},
    {"kpi_key": "Quality", "weight_key": "Quality", "label": "Quality Score", "weight": 0.10, "target": None},
    {"kpi_key": "Other", "weight_key": "Other", "label": "Reachability", "weight": 0.10, "target": None},
)

# Source targets shared by the reconciled July row and the August workbook.
# January–May attendance 0.55 is source timeline only; it is not applied here
# over the technical baseline. July 0.55 / August 0.65 is a synthetic
# acceptance scenario, not this basis.
SOURCE_TARGETS = {
    "Booking": 0.3,
    "Attendance": 0.65,
    "Other": 0.75,
    "Quality": 0.95,
    "Productivity": 0.8,
}

JULY_LINES = (
    {"kpi_key": "Attendance", "weight_key": "Attend", "label": "Attendance Rate", "weight": 0.70, "target": 0.65},
    {"kpi_key": "Booking", "weight_key": "Booking", "label": "Booking Rate", "weight": 0.10, "target": 0.3},
    {"kpi_key": "Quality", "weight_key": "Quality", "label": "Quality Score", "weight": 0.10, "target": 0.95},
    {"kpi_key": "Other", "weight_key": "Other", "label": "Reachability", "weight": 0.10, "target": 0.75},
)

AUGUST_LINES = (
    {"kpi_key": "Booking", "weight_key": "Booking", "label": "Booking Rate", "weight": 0.10, "target": 0.3},
    {"kpi_key": "Attendance", "weight_key": "Attend", "label": "Attendance Rate", "weight": 0.60, "target": 0.65},
    {"kpi_key": "Other", "weight_key": "Other", "label": "Reachability", "weight": 0.10, "target": 0.75},
    {"kpi_key": "Quality", "weight_key": "Quality", "label": "Quality Score", "weight": 0.10, "target": 0.95},
    {"kpi_key": "Productivity", "weight_key": "Productivity", "label": "Productivity", "weight": 0.10, "target": 0.8},
)


class OutboundMonthlyActualMissing(ValueError):
    """A requested monthly basis has no source actual. The row is not scored."""

    def __init__(self, period_label: str, missing_keys: list[str]):
        self.period_label = period_label
        self.missing_keys = list(missing_keys)
        keys = ", ".join(self.missing_keys)
        super().__init__(
            f"Outbound {period_label} monthly basis is missing source actuals: {keys}. "
            "The row is not scored as zero, renormalized, derived from available time, "
            "or taken from a stored trend score."
        )


def _norm(value: Any) -> str:
    return "".join(char.lower() for char in str(value or "") if not char.isspace())


_PRODUCTIVITY_NORMS = {_norm(name) for name in PRODUCTIVITY_ACTUAL_ALIASES}
_PRODUCTIVITY_TARGET_NORMS = {_norm(name) for name in PRODUCTIVITY_TARGET_ALIASES}
_PERCENT_NORMS = {_norm(name) for name in KNOWN_PERCENT_COLUMNS}
_SHEET_NORMS = {_norm(name): name for name in OUTBOUND_SHEET_NAMES}


def is_productivity_column(name: Any) -> bool:
    return _norm(name) in _PRODUCTIVITY_NORMS


def is_known_percent_column(name: Any) -> bool:
    return _norm(name) in _PERCENT_NORMS


def is_outbound_sheet(name: Any) -> bool:
    return _norm(name) in _SHEET_NORMS


def resolve_outbound_sheet_name(sheet_names) -> str | None:
    """Prefer the historical ``Outbound`` tab, then the source offshore tab."""
    names = list(sheet_names or [])
    for candidate in OUTBOUND_SHEET_NAMES:
        if candidate in names:
            return candidate
    folded = {_norm(name): name for name in names}
    for candidate in OUTBOUND_SHEET_NAMES:
        match = folded.get(_norm(candidate))
        if match is not None:
            return match
    return None


def _line(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kpi_key": raw["kpi_key"],
        "weight_key": raw["weight_key"],
        "label": raw["label"],
        "weight": float(raw["weight"]),
        "direction": "higher_better",
        "unit": "%",
        "target": None if raw.get("target") is None else float(raw["target"]),
        "target_mode": "workbook",
    }


def _basis(
    *,
    year: int | None,
    month: int | None,
    status: str,
    lines: tuple[Mapping[str, Any], ...],
    productivity_required: bool,
    attendance_target: float | None,
) -> dict[str, Any]:
    copied = [_line(line) for line in lines]
    month_name = MONTHS[month - 1] if month else None
    return {
        "team": "Outbound",
        "year": year,
        "month": month,
        "month_name": month_name,
        "period": f"{year:04d}-{month:02d}" if year and month else None,
        "status": status,
        "infer_from_august": False,
        "productivity_key": PRODUCTIVITY_KEY,
        "productivity_required": productivity_required,
        "scored_keys": [line["kpi_key"] for line in copied if line["weight"] > 0],
        "lines": copied,
        "attendance_target": attendance_target,
        "aht": {"kpi_key": AHT_KEY, "weight": 0.0, "enabled": False, "scored": False},
        "technical_baseline_file": "Backend/config/teams/outbound.json",
        "historical_score_readable_without_productivity": True,
        "approved_binding": "refuse" if status == "unconfigured" else "apply",
        "catalog_template_supported": status in {"july_2026", "august_2026"},
        "silent_fallback": False,
    }


def period_capability(year: int | None, month: int | str | None) -> dict[str, Any]:
    """Canonical lines and whether an approved binding may be applied.

    Catalog and workflow code should use this decision when a month template
    is attached. This function does not read the catalog or an approved row.
    """
    basis = canonical_outbound_basis(year, month)
    return {
        "team": "Outbound",
        "period": basis["period"],
        "year": basis["year"],
        "month": basis["month"],
        "month_name": basis["month_name"],
        "status": basis["status"],
        "lines": basis["lines"],
        "scored_keys": list(basis["scored_keys"]),
        "productivity_key": basis["productivity_key"],
        "productivity_required": basis["productivity_required"],
        "approved_binding": basis["approved_binding"],
        "catalog_template_supported": basis["catalog_template_supported"],
        "silent_fallback": False,
        "infer_from_august": False,
        "aht": basis["aht"],
        "historical_score_readable_without_productivity": True,
    }


class OutboundUnsupportedApprovedBinding(ValueError):
    """An approved snapshot is outside this period's canonical capability."""

    def __init__(self, period_label: str, reason: str):
        self.period_label = period_label
        self.reason = reason
        super().__init__(
            f"Outbound {period_label} has an approved binding that this period does not support ({reason}). "
            "The upload is not scored with that binding and does not fall back to the workbook total."
        )


def canonical_outbound_basis(year: int | None, month: int | str | None) -> dict[str, Any]:
    """Return the scored basis for one exact period.

    August 2026 is the only five-KPI month. Later months stay ``unconfigured``
    and keep the technical four-KPI lines until a catalog template says
    otherwise. They do not inherit August's Productivity weight.
    """
    number: int | None
    try:
        number = None if month is None or month == "" else month_number(month)
    except PeriodError:
        number = None
    try:
        year_number = None if year is None else int(year)
    except (TypeError, ValueError):
        year_number = None

    if year_number == 2026 and number == 6:
        lines = (
            {"kpi_key": "Attendance", "weight_key": "Attend", "label": "Attendance Rate", "weight": 0.70, "target": None},
            {"kpi_key": "Booking", "weight_key": "Booking", "label": "Booking Rate", "weight": 0.10, "target": None},
            {"kpi_key": "Quality", "weight_key": "Quality", "label": "Quality Score", "weight": 0.00, "target": None},
            {"kpi_key": "Other", "weight_key": "Other", "label": "Reachability", "weight": 0.20, "target": None},
        )
        return _basis(
            year=year_number,
            month=number,
            status="june_2026_exception",
            lines=lines,
            productivity_required=False,
            attendance_target=None,
        )
    if year_number == 2026 and number == 7:
        return _basis(
            year=year_number,
            month=number,
            status="july_2026",
            lines=JULY_LINES,
            productivity_required=False,
            attendance_target=0.65,
        )
    if year_number == 2026 and number == 8:
        return _basis(
            year=year_number,
            month=number,
            status="august_2026",
            lines=AUGUST_LINES,
            productivity_required=True,
            attendance_target=0.65,
        )
    if year_number is not None and number is not None and (year_number > 2026 or (year_number == 2026 and number > 8)):
        return _basis(
            year=year_number,
            month=number,
            status="unconfigured",
            lines=TECHNICAL_LINES,
            productivity_required=False,
            attendance_target=None,
        )
    return _basis(
        year=year_number,
        month=number,
        status="technical_baseline",
        lines=TECHNICAL_LINES,
        productivity_required=False,
        attendance_target=None,
    )


def period_from_value(value: Any) -> tuple[int, int] | None:
    """Year and month from a real date. A time-of-day value is not a period."""
    if value is None or isinstance(value, datetime.time):
        return None
    if isinstance(value, datetime.datetime):
        return value.year, value.month
    if isinstance(value, datetime.date):
        return value.year, value.month
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return None
    if ":" in text and "-" not in text and "/" not in text:
        return None
    try:
        import pandas as pd
    except Exception:
        return None
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return int(parsed.year), int(parsed.month)


def explicit_number(row: Mapping[str, Any] | None, *keys: str) -> float | None:
    """A stored number. Times and date values are refused, not converted."""
    if row is None:
        return None
    try:
        if len(row) == 0:
            return None
    except TypeError:
        if not row:
            return None
    wanted = {_norm(key) for key in keys}
    matches: list[Any] = []
    for key in keys:
        if key in row:
            matches.append(row.get(key))
    if not matches:
        for key, value in row.items():
            if _norm(key) in wanted:
                matches.append(value)
    for value in matches:
        number = _plain_number(value)
        if number is not None:
            return number
    return None


def _plain_number(value: Any) -> float | None:
    if value is None or isinstance(value, (datetime.date, datetime.time, datetime.datetime, bool)):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.endswith("%") or ":" in text:
            return None
        value = text.replace(",", "")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def productivity_actual(row: Mapping[str, Any] | None) -> float | None:
    """Stored Productivity actual. Never available time, AHT, or a final score."""
    return explicit_number(row, *PRODUCTIVITY_ACTUAL_ALIASES)


def productivity_target(row: Mapping[str, Any] | None, fallback: float | None = None) -> float | None:
    found = explicit_number(row, *PRODUCTIVITY_TARGET_ALIASES)
    return found if found is not None else fallback


def scoring_weights(basis: Mapping[str, Any], repo_weights: Mapping[str, Any] | None) -> dict[str, float]:
    """Weights for ``calculate_performance``. June still honours the repo attend/booking weights."""
    repo = repo_weights or {}
    weights: dict[str, float] = {}
    for line in basis.get("lines") or []:
        key = str(line["weight_key"])
        if basis.get("status") == "june_2026_exception" and key in {"Attend", "Booking"}:
            weights[key] = float(repo.get(key, line["weight"]))
        elif basis.get("status") in {"technical_baseline", "unconfigured"} and line.get("target") is None:
            weights[key] = float(repo.get(key, line["weight"]))
        else:
            weights[key] = float(line["weight"])
    return weights


def apply_basis_targets(basis: Mapping[str, Any]) -> bool:
    """July and August use source targets when the workbook cell is absent."""
    return basis.get("status") in {"july_2026", "august_2026"}


def assess_monthly_actuals(year: int | None, month: int | str | None, actuals: Mapping[str, Any] | None) -> dict[str, Any]:
    """Whether the requested basis has source actuals.

    A legacy trend row without Productivity stays historically readable.
    It is not sufficient evidence for the August five-KPI basis.
    """
    basis = canonical_outbound_basis(year, month)
    supplied = actuals or {}
    missing = [
        line["kpi_key"]
        for line in basis["lines"]
        if float(line["weight"]) > 0 and _plain_number(supplied.get(line["kpi_key"])) is None
    ]
    sufficient = not missing
    five_kpi = basis["status"] == "august_2026"
    return {
        "basis": basis,
        "sufficient": sufficient,
        "missing_keys": missing,
        "disposition": "measured" if sufficient else "fail_visible_missing_source_actual",
        "historical_score_readable": True,
        "accepted_as_period_basis_evidence": sufficient,
        "accepted_as_five_kpi_monthly_evidence": bool(five_kpi and sufficient),
        "forbidden_substitutions": [
            "zero",
            "renormalize_remaining_weights",
            "infer_from_available_time",
            "infer_from_final_score",
            "trend_lookup",
        ],
    }


def capped_achievement(actual: float, target: float):
    """Supported employee cap: min(actual / target, 1). No time-of-day reading."""
    return achievement(float(actual), float(target), "higher_better", EMPLOYEE_POLICY)


def score_capped_lines(actuals: Mapping[str, float], lines: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Score a complete basis. Missing actuals are not replaced."""
    details = {}
    results = []
    missing = []
    for line in lines:
        weight = float(line["weight"])
        if weight <= 0:
            continue
        key = str(line["kpi_key"])
        actual = _plain_number(actuals.get(key))
        target = _plain_number(line.get("target"))
        if actual is None or target is None:
            missing.append(key)
            continue
        result = capped_achievement(actual, target)
        if result.value is None:
            missing.append(key)
            continue
        weighted = contribution(result.value, weight)
        details[key] = {"achievement": result, "contribution": weighted}
        results.append(KPIResult(achievement=result.value, weight=weight, contribution=weighted))
    if missing:
        return {"sufficient": False, "missing_keys": missing, "details": details, "total": None}
    total = score(results)
    return {"sufficient": True, "missing_keys": [], "details": details, "total": total}
