"""Clinical employee scorecard computation for ER Dr, Radiologist, and Qlty&Case-Mngt.

Recomputes the employee's performance score from workbook source KPIs using the
prescribed weight formulas, conditional exclusions, and penalty deductions. The
overall score is the headline; the KPI breakdown shows only KPIs that contributed
to the selected employee's score and the penalties applied.

Each scorer returns ``(score, grade, kpi_values)`` where ``kpi_values`` is a list
of dicts compatible with the ``kpi_values`` schema used by ``clinical_trend_import``
and ``dashboard_record_service``.
"""

from __future__ import annotations

import math
import re
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# Shared Utilities
# ---------------------------------------------------------------------------

_GRADE_THRESHOLDS: list[tuple[float, str]] = [
    (95.0, "A"),
    (90.0, "B"),
    (80.0, "C"),
    (70.0, "D"),
]


def _grade(score: float) -> str:
    """Letter grade from percentage score."""
    for threshold, label in _GRADE_THRESHOLDS:
        if score >= threshold:
            return label
    return "E"


def _number(value: Any) -> float | None:
    """Safe float conversion; returns None for missing/non-finite values."""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            text = value.replace(",", "").strip()
            if text.endswith("%"):
                text = text[:-1].strip()
            if not text or text.lower() in {"", "-", "na", "n/a", "nan", "none"}:
                return None
            num = float(text)
        else:
            num = float(value)
        return num if math.isfinite(num) else None
    except (TypeError, ValueError):
        return None


def _pct(value: Any) -> float | None:
    """Parse a value that may be 0-1 fraction or 0-100 percentage; normalise to 0-1."""
    num = _number(value)
    if num is None:
        return None
    return num / 100.0 if num > 1.0 else num


def _kpi_entry(
    key: str,
    label: str,
    weight: float,
    achievement: float,
    *,
    actual: float | None = None,
    target: float | None = None,
    direction: str = "higher_better",
    unit: str = "%",
    is_penalty: bool = False,
) -> dict[str, Any]:
    """Build a single KPI value dict for the breakdown."""
    contribution = achievement * weight
    return {
        "kpi_key": key,
        "label": label,
        "direction": direction,
        "unit": unit,
        "actual_value": actual if actual is not None else achievement,
        "target_value": target if target is not None else 1.0,
        "achievement_ratio": min(max(achievement, 0.0), 1.0) if not is_penalty else achievement,
        "weight_applied": weight,
        "contribution": contribution,
        "view_only": False,
        "is_penalty": is_penalty,
    }


def _penalty_entry(
    key: str,
    label: str,
    deduction: float,
    *,
    actual: float | None = None,
    unit: str = "%",
) -> dict[str, Any]:
    """Build a penalty deduction entry (negative contribution, zero weight)."""
    return {
        "kpi_key": key,
        "label": label,
        "direction": "lower_better",
        "unit": unit,
        "actual_value": actual if actual is not None else deduction,
        "target_value": 0.0,
        "achievement_ratio": 0.0,
        "weight_applied": 0.0,
        "contribution": -deduction,
        "view_only": False,
        "is_penalty": True,
    }


def _raw_lookup(raw: Mapping[str, Any], keys: list[str]) -> Any:
    """Find the first non-None value from multiple candidate column names."""
    for key in keys:
        val = raw.get(key)
        if val is not None:
            return val
        # Try fuzzy match (strip whitespace/dots differences)
        clean = re.sub(r"[\s_.]+", "", key.lower())
        for rkey, rval in raw.items():
            if rval is not None and re.sub(r"[\s_.]+", "", str(rkey).lower()) == clean:
                return rval
    return None


# ---------------------------------------------------------------------------
# ER Dr Scoring
# ---------------------------------------------------------------------------

# Column mappings for ER Dr achievement values in the right-hand 24-hour block.
# The workbook repeats labels for actual/target/achievement; we need the
# achievement columns (the third repetition, suffix ".2" or ".3").
_ER_ACHIEVEMENT_COLUMNS: dict[str, list[str]] = {
    "admission_rate": ["Admission Rate %.2", "Admission Rate %", "Admission Rate"],
    "revisit_rate": ["Re-visit Rate  %.2", "Re-visit Rate  %", "Re-visit Rate %", "Re-visit Rate"],
    "time_to_assessment": [
        "Avg Time to Initial Patient Assessment 10%",
        "Avg Time to Initial Patient Assessment",
    ],
    "satisfaction": ["Satisfaction Score.3", "Satisfaction Score", "Satisfaction"],
    "documentation": ["Documentation%.3", "Documentation%", "Documentation"],
    "lama_retention": ["LAMA Retention %.2", "LAMA Retention %", "LAMA Retention"],
}

_ER_DEDUCTION_COLUMNS: dict[str, list[str]] = {
    "valid_complaints": ["Valid Complains", "Valid Complaints", "Valid complaints"],
    "medical_error": ["Medical Error Rate ", "Medical Error Rate", "Medical Error"],
}

_ER_TOTAL_LAMA_COLUMNS: list[str] = ["Total LAMA", "Total LAMA ", "TotalLAMA"]
_ER_RETAINED_COLUMNS: list[str] = [
    "Retained",
    "Retained Patients",
    "LAMA Retained",
    "No. of Retained",
    "No of Retained",
    "Retained Count",
    "No. of LAMA Retained",
    "No of LAMA Retained",
]

# Nominal weights for ER Dr
_ER_NOMINAL_WEIGHTS: dict[str, tuple[str, float]] = {
    "admission_rate": ("Admission rate", 0.40),
    "revisit_rate": ("24-hour revisit rate", 0.10),
    "time_to_assessment": ("Time to initial patient assessment", 0.15),
    "satisfaction": ("Satisfaction", 0.15),
    "documentation": ("Documentation", 0.10),
    "lama_retention": ("LAMA retention", 0.10),
}

# Deduction KPIs (subtracted after normalization)
_ER_DEDUCTIONS: dict[str, tuple[str, str]] = {
    "valid_complaints": ("Valid complaints", "lower_better"),
    "medical_error": ("Medical error rate", "lower_better"),
}


def _is_lama_blank(raw: Mapping[str, Any]) -> bool:
    """Return True when Total LAMA is truly blank/absent (not a measured zero)."""
    total_lama = _raw_lookup(raw, _ER_TOTAL_LAMA_COLUMNS)
    if total_lama is None:
        return True
    text = str(total_lama).strip()
    if text.lower() in ("", "nan", "none", "n/a", "na", "-"):
        return True
    return False


def _is_lama_zero(raw: Mapping[str, Any]) -> bool:
    """Return True when Total LAMA is an explicit measured zero."""
    total_lama = _raw_lookup(raw, _ER_TOTAL_LAMA_COLUMNS)
    if total_lama is None:
        return False
    num = _number(total_lama)
    return num is not None and num == 0.0


def er_lama_status(raw: Mapping[str, Any]) -> str:
    """Classify Total LAMA state, preserving measured-zero vs ambiguous-blank distinction.

    Returns one of:
    - ``"positive"``: Total LAMA is numeric and > 0 (include LAMA Retention, / 0.90)
    - ``"measured_zero"``: Total LAMA is explicitly 0 (exclude LAMA Retention, / 0.80)
    - ``"blank_no_lama"``: Total LAMA is blank/NA and retained count is 0 or absent (treat as no LAMA, / 0.80)
    - ``"ambiguous_blank"``: Total LAMA is blank/NA while positive retained patients are recorded
    """
    total_lama = _raw_lookup(raw, _ER_TOTAL_LAMA_COLUMNS)
    total_lama_num = _number(total_lama)
    if total_lama_num is not None:
        return "positive" if total_lama_num > 0 else "measured_zero"

    retained = _number(_raw_lookup(raw, _ER_RETAINED_COLUMNS))
    if retained is not None and retained > 0:
        return "ambiguous_blank"
    return "blank_no_lama"


def score_er_dr(raw: Mapping[str, Any]) -> tuple[float, str, list[dict[str, Any]]] | None:
    """Compute ER Dr employee score from raw workbook row data.

    Returns ``(score_percent, grade_letter, kpi_values)`` or None if insufficient
    or ambiguous data.

    Rules:
    - Nominal weights: Admission 40%, Revisit 10%, Assessment 15%, Satisfaction 15%,
      Documentation 10%, LAMA Retention 10%.
    - If Total LAMA is measured zero -> exclude LAMA Retention, denominator = 0.80.
    - If Total LAMA is positive -> include LAMA Retention, denominator = 0.90.
    - If Total LAMA is blank -> treat as no LAMA only when zero retained patients
      are recorded (denominator = 0.80); if positive retained patients are recorded,
      return None (ambiguous blank).
    - Subtract Valid Complaints and Medical Error Rate penalties after normalization.
    """
    lama_status = er_lama_status(raw)
    if lama_status == "ambiguous_blank":
        return None

    # Gather achievement values
    achievements: dict[str, float | None] = {}
    for key, columns in _ER_ACHIEVEMENT_COLUMNS.items():
        val = _raw_lookup(raw, columns)
        achievements[key] = _pct(val)

    include_lama = lama_status == "positive"
    denominator = 0.90 if include_lama else 0.80

    # Build KPI entries with effective weights (= nominal_weight / denominator)
    kpi_values: list[dict[str, Any]] = []
    weighted_sum = 0.0
    has_any = False

    for key, (label, nominal_weight) in _ER_NOMINAL_WEIGHTS.items():
        if key == "lama_retention" and not include_lama:
            continue

        ach = achievements.get(key)
        if ach is None:
            # Missing achievement = zero contribution, but counts
            ach = 0.0

        has_any = True
        effective_weight = nominal_weight / denominator
        kpi_values.append(_kpi_entry(
            key=key,
            label=label,
            weight=effective_weight,
            achievement=ach,
        ))
        weighted_sum += ach * nominal_weight

    if not has_any:
        return None

    # Normalize by denominator
    normalized_score = weighted_sum / denominator

    # Gather and apply deductions
    deductions: dict[str, float] = {}
    for key, columns in _ER_DEDUCTION_COLUMNS.items():
        val = _raw_lookup(raw, columns)
        num = _pct(val)
        if num is not None and num > 0:
            deductions[key] = num

    total_deduction = 0.0
    for key, deduction_value in deductions.items():
        label, _direction = _ER_DEDUCTIONS[key]
        kpi_values.append(_penalty_entry(
            key=key,
            label=f"{label} penalty",
            deduction=deduction_value,
            actual=deduction_value,
        ))
        total_deduction += deduction_value

    final_score = round(max(0.0, min(100.0, (normalized_score - total_deduction) * 100.0)), 2)
    grade_letter = _grade(final_score)

    return final_score, grade_letter, kpi_values


# ---------------------------------------------------------------------------
# Radiologist Scoring
# ---------------------------------------------------------------------------

_RAD_NOMINAL_WEIGHTS: dict[str, tuple[str, float]] = {
    "tat": ("TAT", 0.20),
    "productivity": ("Productivity", 0.35),
    "report_quality": ("Report Quality", 0.10),
    "imaging_protocol": ("Imaging Protocol", 0.10),
    "critical_findings": ("Critical Findings", 0.15),
    "patient_waiting_time": ("Patient Waiting Time", 0.10),
}

# Map from internal key to possible workbook column names
_RAD_ACHIEVEMENT_COLUMNS: dict[str, list[str]] = {
    "tat": ["Ach.TAT %", "Ach.TAT%", "Ach. TAT %", "Ach. TAT%", "TAT"],
    "productivity": ["Ach.Productivity %", "Ach.Productivity%", "Ach. Productivity %", "Productivity"],
    "report_quality": ["Ach.Report Quality %", "Ach.Report Quality%", "Ach. Report Quality %", "Report Quality"],
    "imaging_protocol": ["Ach.Imaging Protocol %", "Ach.Imaging Protocol%", "Ach. Imaging Protocol %", "Imaging Protocol"],
    "critical_findings": ["Ach.Critical Findings %", "Ach.Critical Findings%", "Ach. Critical Findings %", "Critical Findings"],
    "patient_waiting_time": ["Ach.Patient Waiting Time %", "Ach.Patient Waiting Time%", "Ach. Patient Waiting Time %", "Patient Waiting Time"],
}

_RAD_NA_COLUMNS: dict[str, list[str]] = {
    "critical_findings": ["Critical Findings", "Ach.Critical Findings %", "Ach.Critical Findings%", "Ach. Critical Findings %"],
    "patient_waiting_time": ["Patient Waiting Time", "Ach.Patient Waiting Time %", "Ach.Patient Waiting Time%", "Ach. Patient Waiting Time %"],
}

_RAD_COMPLAINT_COLUMNS: list[str] = [
    "Complaints", "No. of Complaints", "No of Complaints", "Number of Complaints",
    "Valid Complaints", "Valid Complains",
]


def _has_raw_key(raw: Mapping[str, Any], candidates: list[str]) -> bool:
    """Return True if any candidate column name exists in raw (even when value is None)."""
    clean_raw = {re.sub(r"[\s_.]+", "", str(k).lower()) for k in raw.keys()}
    for key in candidates:
        if key in raw:
            return True
        if re.sub(r"[\s_.]+", "", key.lower()) in clean_raw:
            return True
    return False


def _is_rad_na(raw: Mapping[str, Any], key: str) -> bool:
    """Check if a Radiologist KPI is marked NA (or pandas-converted None) in the workbook."""
    ach_columns = _RAD_ACHIEVEMENT_COLUMNS.get(key, [])
    for col in ach_columns:
        val = _raw_lookup(raw, [col])
        if val is None:
            continue
        if _number(val) is not None:
            return False
        if str(val).strip().lower() in ("na", "n/a", "not applicable", "-", ""):
            return True

    columns = _RAD_NA_COLUMNS.get(key, [])
    for col in columns:
        val = _raw_lookup(raw, [col])
        if val is None:
            continue
        if str(val).strip().lower() in ("na", "n/a", "not applicable"):
            return True

    # pandas.read_excel converts "NA" cells into NaN -> safe_value -> None.
    # If the column exists in raw_data with None (and no numeric achievement was found),
    # treat it as NA rather than a 0% achievement score.
    if _has_raw_key(raw, ach_columns) or _has_raw_key(raw, columns):
        return True
    return False


def score_radiologist(raw: Mapping[str, Any]) -> tuple[float, str, list[dict[str, Any]]] | None:
    """Compute Radiologist employee score from raw workbook row data.

    Rules:
    - TAT 20%, Productivity 35%, Report Quality 10%, Imaging Protocol 10%,
      Critical Findings 15%, Patient Waiting Time 10%.
    - Exclude Critical Findings and Patient Waiting Time independently when marked NA.
    - Denominator = sum of applicable weights.
    - Effective weight for each included KPI = nominal_weight / applicable_weight.
    - Subtract flat 10pp if complaint count > 0 (once per employee-month).
    - Exclude modality-level view metrics from breakdown.
    """
    achievements: dict[str, float | None] = {}
    excluded: set[str] = set()

    for key, columns in _RAD_ACHIEVEMENT_COLUMNS.items():
        if key in ("critical_findings", "patient_waiting_time") and _is_rad_na(raw, key):
            excluded.add(key)
            continue
        val = _raw_lookup(raw, columns)
        achievements[key] = _pct(val)

    # First compute applicable weight sum across non-excluded KPIs
    applicable_weight = sum(
        nominal_weight
        for key, (_label, nominal_weight) in _RAD_NOMINAL_WEIGHTS.items()
        if key not in excluded
    )
    if applicable_weight <= 0:
        return None

    # Build KPI entries using effective weights
    kpi_values: list[dict[str, Any]] = []
    weighted_sum = 0.0
    has_any = False

    for key, (label, nominal_weight) in _RAD_NOMINAL_WEIGHTS.items():
        if key in excluded:
            continue

        ach = achievements.get(key)
        if ach is None:
            ach = 0.0

        has_any = True
        effective_weight = nominal_weight / applicable_weight
        kpi_values.append(_kpi_entry(
            key=key,
            label=label,
            weight=effective_weight,
            achievement=ach,
        ))
        weighted_sum += ach * nominal_weight

    if not has_any:
        return None

    # Normalize by applicable weight sum
    normalized_score = weighted_sum / applicable_weight

    # Check complaints for flat -10pp penalty
    complaint_val = _raw_lookup(raw, _RAD_COMPLAINT_COLUMNS)
    complaint_num = _number(complaint_val)
    has_complaint = complaint_num is not None and complaint_num > 0

    if has_complaint:
        kpi_values.append(_penalty_entry(
            key="complaint_penalty",
            label="Complaint penalty",
            deduction=0.10,
            actual=complaint_num,
            unit="number",
        ))
        normalized_score -= 0.10

    final_score = round(max(0.0, min(100.0, normalized_score * 100.0)), 2)
    grade_letter = _grade(final_score)

    return final_score, grade_letter, kpi_values


# ---------------------------------------------------------------------------
# Qlty&Case-Mngt Scoring
# ---------------------------------------------------------------------------

# Score columns: AD = Audit Compliance, AE = Rejection, AF = Case Management, AG = Revenue Impact
_QLTY_COLUMNS: dict[str, list[str]] = {
    "audit": [
        "Audit Compliance Rate % (IP, OP, Re-Submission)",
        "Audit Compliance Rate %",
        "Audit Compliance",
        "Audit",
    ],
    "rejection": [
        "Rejection Rate",
        "Rejection",
    ],
    "case_management": [
        "Case Management Rate",
        "Case Management",
    ],
    "revenue_impact": [
        "Revenue Impact",
        "Revenue",
    ],
}


def _qlty_value(raw: Mapping[str, Any], key: str) -> float | None:
    """Get a Qlty&Case-Mngt KPI value, returning None if blank/NA."""
    val = _raw_lookup(raw, _QLTY_COLUMNS[key])
    if val is None:
        return None
    text = str(val).strip().lower()
    if text in ("", "nan", "none", "n/a", "na", "-"):
        return None
    return _pct(val)


def _qlty_is_blank(raw: Mapping[str, Any], key: str) -> bool:
    """Check if a column value is blank/absent (not a measured zero)."""
    val = _raw_lookup(raw, _QLTY_COLUMNS[key])
    if val is None:
        return True
    text = str(val).strip().lower()
    return text in ("", "nan", "none", "n/a", "na", "-")


def _qlty_is_zero(raw: Mapping[str, Any], key: str) -> float | None:
    """Check if a column value is numeric zero."""
    val = _qlty_value(raw, key)
    return val is not None and val == 0.0


def score_qlty_case_mngt(raw: Mapping[str, Any]) -> tuple[float, str, list[dict[str, Any]]] | None:
    """Compute Qlty&Case-Mngt employee score from raw workbook row data.

    Formula paths:
    1. Case Management path: blank AF (case_management), numeric AG (revenue_impact),
       unavailable AE (rejection) → Audit 30% + Revenue Impact 70%.
    2. Quality AF=0: Audit 40% + Rejection 60%.
    3. Quality AF nonzero, AD=0 branch: Rejection 60% + Case Management 40%.
    4. Full formula: Audit 30% + Rejection 50% + Case Management 20%.

    Missing text in a KPI used by the selected formula contributes zero.
    Zero-weight KPIs are excluded from the breakdown.
    """
    audit = _qlty_value(raw, "audit")
    rejection = _qlty_value(raw, "rejection")
    case_mgmt = _qlty_value(raw, "case_management")
    revenue = _qlty_value(raw, "revenue_impact")

    cm_blank = _qlty_is_blank(raw, "case_management")
    rej_blank = _qlty_is_blank(raw, "rejection")
    audit_val = audit if audit is not None else 0.0
    rej_val = rejection if rejection is not None else 0.0
    cm_val = case_mgmt if case_mgmt is not None else 0.0
    rev_val = revenue if revenue is not None else 0.0

    # Determine which formula path to use
    kpi_values: list[dict[str, Any]] = []
    weighted_sum = 0.0

    # Path 1: Case Management rows — blank AF, numeric AG, unavailable AE
    if cm_blank and revenue is not None and rej_blank:
        weights = {"audit": 0.30, "revenue_impact": 0.70}
        if weights["audit"] > 0:
            kpi_values.append(_kpi_entry("audit", "Audit compliance", weights["audit"], audit_val))
            weighted_sum += audit_val * weights["audit"]
        if weights["revenue_impact"] > 0:
            kpi_values.append(_kpi_entry("revenue_impact", "Revenue impact", weights["revenue_impact"], rev_val))
            weighted_sum += rev_val * weights["revenue_impact"]

    # Path 2: Quality with AF = 0
    elif case_mgmt is not None and case_mgmt == 0.0:
        weights = {"audit": 0.40, "rejection": 0.60}
        if weights["audit"] > 0:
            kpi_values.append(_kpi_entry("audit", "Audit compliance", weights["audit"], audit_val))
            weighted_sum += audit_val * weights["audit"]
        if weights["rejection"] > 0:
            kpi_values.append(_kpi_entry("rejection", "Rejection rate", weights["rejection"], rej_val))
            weighted_sum += rej_val * weights["rejection"]

    # Path 3: AF nonzero, AD = 0 → Rejection 60% + Case Management 40%
    elif case_mgmt is not None and case_mgmt != 0.0 and (audit is None or audit == 0.0):
        weights = {"rejection": 0.60, "case_management": 0.40}
        if weights["rejection"] > 0:
            kpi_values.append(_kpi_entry("rejection", "Rejection rate", weights["rejection"], rej_val))
            weighted_sum += rej_val * weights["rejection"]
        if weights["case_management"] > 0:
            kpi_values.append(_kpi_entry("case_management", "Case management", weights["case_management"], cm_val))
            weighted_sum += cm_val * weights["case_management"]

    # Path 4: Full formula — Audit 30% + Rejection 50% + Case Management 20%
    elif case_mgmt is not None:
        weights = {"audit": 0.30, "rejection": 0.50, "case_management": 0.20}
        if weights["audit"] > 0:
            kpi_values.append(_kpi_entry("audit", "Audit compliance", weights["audit"], audit_val))
            weighted_sum += audit_val * weights["audit"]
        if weights["rejection"] > 0:
            kpi_values.append(_kpi_entry("rejection", "Rejection rate", weights["rejection"], rej_val))
            weighted_sum += rej_val * weights["rejection"]
        if weights["case_management"] > 0:
            kpi_values.append(_kpi_entry("case_management", "Case management", weights["case_management"], cm_val))
            weighted_sum += cm_val * weights["case_management"]

    else:
        # Fallback: when only Audit and/or Rejection are present (no CM or Revenue)
        if audit is not None or rejection is not None:
            # Use Path 2 weights: Audit 40% + Rejection 60%
            weights = {"audit": 0.40, "rejection": 0.60}
            if weights["audit"] > 0:
                kpi_values.append(_kpi_entry("audit", "Audit compliance", weights["audit"], audit_val))
                weighted_sum += audit_val * weights["audit"]
            if weights["rejection"] > 0:
                kpi_values.append(_kpi_entry("rejection", "Rejection rate", weights["rejection"], rej_val))
                weighted_sum += rej_val * weights["rejection"]
        else:
            return None

    final_score = round(max(0.0, min(100.0, weighted_sum * 100.0)), 2)
    grade_letter = _grade(final_score)

    return final_score, grade_letter, kpi_values


# ---------------------------------------------------------------------------
# Unified Entry Point
# ---------------------------------------------------------------------------

def compute_clinical_score(
    team: str,
    raw: Mapping[str, Any],
) -> tuple[float, str, list[dict[str, Any]]] | None:
    """Compute clinical employee score for any supported team.

    Returns ``(score_percent, grade_letter, kpi_values)`` or None if the team
    is not a clinical team or if there's insufficient data to compute a score.
    """
    if team == "ER Dr":
        return score_er_dr(raw)
    elif team == "Radiologist":
        return score_radiologist(raw)
    elif team == "Qlty&Case-Mngt":
        return score_qlty_case_mngt(raw)
    return None


def can_recompute(team: str, raw: Mapping[str, Any]) -> bool:
    """Check if we have enough source KPI data to recompute a clinical score.

    Requires a minimum number of applicable KPI columns to be present in the raw
    data to avoid producing misleading scores from partial observations.
    """
    if team not in ("ER Dr", "Radiologist", "Qlty&Case-Mngt"):
        return False
    if not isinstance(raw, dict):
        return False

    if team == "ER Dr":
        if er_lama_status(raw) == "ambiguous_blank":
            return False
        # Need at least 3 of the 6 achievement columns (covering the major weights)
        count = sum(1 for columns in _ER_ACHIEVEMENT_COLUMNS.values()
                    if _raw_lookup(raw, columns) is not None)
        return count >= 3

    if team == "Radiologist":
        # Need at least 3 non-NA achievement columns
        count = sum(
            1
            for key, columns in _RAD_ACHIEVEMENT_COLUMNS.items()
            if (key not in ("critical_findings", "patient_waiting_time") or not _is_rad_na(raw, key))
            and _raw_lookup(raw, columns) is not None
        )
        return count >= 3

    if team == "Qlty&Case-Mngt":
        # Need at least 2 relevant score columns to determine formula path
        count = sum(1 for columns in _QLTY_COLUMNS.values()
                    if _raw_lookup(raw, columns) is not None)
        return count >= 2

    return False


def reconcile_clinical_records_in_db(db: Any) -> int:
    """Recompute and persist clinical scores, grades, statuses, and KPI rows in DB.

    Updates existing ``ER Dr``, ``Radiologist``, and ``Qlty&Case-Mngt`` rows whose
    saved ``raw_data`` contains sufficient source KPI inputs. Rows with
    insufficient or ambiguous source evidence preserve their historical headline.
    Returns the number of updated ``PerformanceRecord`` rows.
    """
    import uuid
    from decimal import Decimal
    from models.models import KPIValue, PerformanceRecord, Team
    from utils.performance_status import status_for_grade

    rows = (
        db.query(PerformanceRecord, Team.name)
        .join(Team, PerformanceRecord.team_id == Team.id)
        .filter(Team.name.in_(("ER Dr", "Radiologist", "Qlty&Case-Mngt")))
        .all()
    )
    updated = 0
    for record, team_name in rows:
        payload = record.record_payload if isinstance(record.record_payload, dict) else None
        raw = payload.get("raw_data") if payload else None
        if not can_recompute(team_name, raw):
            continue
        recomputed = compute_clinical_score(team_name, raw)
        if recomputed is None:
            continue
        new_score, new_grade, new_kpis = recomputed
        record.score = Decimal(str(new_score))
        record.grade = new_grade
        record.status = status_for_grade(new_grade)
        if isinstance(payload, dict):
            updated_payload = dict(payload)
            updated_eval = dict(updated_payload.get("evaluation") or {})
            updated_eval["score"] = new_score
            updated_eval["grade"] = new_grade
            updated_payload["evaluation"] = updated_eval
            updated_payload["kpi_values"] = new_kpis
            record.record_payload = updated_payload

        db.query(KPIValue).filter(
            KPIValue.record_id == record.id,
            KPIValue.record_year == record.year,
        ).delete(synchronize_session=False)
        for kpi in new_kpis:
            db.add(KPIValue(
                id=uuid.uuid4(),
                record_id=record.id,
                record_year=record.year,
                kpi_key=str(kpi["kpi_key"]),
                actual_value=Decimal(str(round(float(kpi.get("actual_value", 0.0)), 4))),
                target_value=Decimal(str(round(float(kpi.get("target_value", 0.0)), 4))),
                achievement_ratio=Decimal(str(round(float(kpi.get("achievement_ratio", 0.0)), 4))),
                weight_applied=Decimal(str(round(float(kpi.get("weight_applied", 0.0)), 4))),
                contribution=Decimal(str(round(float(kpi.get("contribution", 0.0)), 4))),
            ))
        updated += 1
    if updated:
        db.flush()
    return updated
