"""Authorized read-only evidence for corrective-action suggestions.

The first product pilot (contextual corrective-action suggestions) needs the
selected employee's or team's real PMS evidence before any draft is written:
the reporting period, performance level, KPI actual/target/direction, and the
prior corrective actions on file. This module only *reads* that evidence
through the canonical PMS services. It never writes a plan, never invents a
cause, owner, due date, or numerical score/team uplift, and never sends
employee data to any model.

Read-only guarantees enforced here:

- No ``db.add`` / ``db.commit`` / ``db.delete`` and no ``CorrectiveActionService.save``,
  ``update_status`` or ``deactivate`` call anywhere in this module.
- A missing value stays ``None``: actuals, targets and achievement are never
  coerced to ``0.0`` (a real measured ``0.0`` is preserved as ``0.0``).
- Prior actions are sanitized to structured fields only (action type, status,
  linked KPI, period). Free-text root causes, action text, owners, due dates
  and completion notes are deliberately *not* copied into the bundle, so the
  bundle can never present them as a suggested cause, owner, or due date.
- Scope is enforced before any row is read: an employee subject goes through
  ``CorrectiveActionService.ensure_employee_scope`` and a team subject through
  ``user_can_access_team_level``. Out-of-scope access raises ``PermissionError``.
- No score tie is resolved to a single winner: this bundle reports KPI items
  and stored scores as read and never ranks employees.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from sqlalchemy.orm import Session

from models.models import Employee, PerformanceRecord, Team
from repositories.action_repository import ActionRepository
from services.corrective_action_service import CorrectiveActionService
from services.dashboard_record_service import DashboardRecordService
from utils.performance_levels import normalize_performance_level
from utils.report_scope import functions_for_team, user_can_access_team_level
from utils.team_identity import logical_team_name

__all__ = [
    "CorrectiveActionEvidenceService",
    "build_corrective_action_evidence",
    "classify_kpi_observation",
    "normalize_kpi_values_for_unit",
]

_PERCENT_UNITS = frozenset({"%", "percent", "percentage"})
_AUDIT_ASSESSMENT_TOKENS = frozenset(
    {
        "quality",
        "csat",
        "satisfaction",
        "compliance",
        "audit",
        "nps",
        "qa",
        "survey",
        "assessment",
        "accuracy",
        "calibration",
        "evaluation",
    }
)
_RAW_ACTUAL_KEYS_BY_KPI: dict[str, tuple[str, ...]] = {
    "quality": ("A.QualityScore", "QualityTargetAch%", "QualityAch%", "QualityScore", "A.Quality%", "A.Quality"),
    "qualityscore": ("A.QualityScore", "QualityTargetAch%", "QualityAch%", "QualityScore", "A.Quality%", "A.Quality"),
    "attendance": ("A.Attend%", "Attend%Ach%", "AttendC.RAch%", "A.Attendance%", "A.Attendance"),
    "attend": ("A.Attend%", "Attend%Ach%", "AttendC.RAch%", "A.Attendance%", "A.Attendance"),
    "booking": ("A.Booking%", "Booking%Ach%", "BookingC.RAch%", "A.Booking"),
    "aht": ("AHT_Minutes", "AHTAch%", "A.AHT", "AHT"),
    "utilization": ("A.UTZ%", "UTZ%", "UTZ%Ach%", "A.Utilization%", "A.Utilization", "Utilization%Ach", "Utilization%Ach%"),
    "utz": ("A.UTZ%", "UTZ%", "UTZ%Ach%", "A.Utilization%", "A.Utilization", "Utilization%Ach", "Utilization%Ach%"),
    "reachability": ("A.Reachability%", "Reachability%Ach%"),
    "abandonrate": ("A.AbandonRate%", "AbandonRate%Ach%"),
    "abandon": ("A.AbandonRate%", "AbandonRate%Ach%"),
    "productivity": ("A.Productivity%", "A.Productivity", "Productivity%", "Productivity"),
    "rejection": ("IPInitialRejection%", "RejectionRate", "RejectedRequests", "RejectedRequest"),
    "initialrejection": ("IPInitialRejection%", "RejectionRate", "RejectedRequests", "RejectedRequest"),
    "ipinitialrejection": ("IPInitialRejection%", "RejectionRate", "RejectedRequests", "RejectedRequest"),
    "initialerror": ("Error%", "InitialError%", "ErrosClaims", "ErrorsClaims", "ErrorClaims"),
    "error": ("Error%", "InitialError%", "ErrosClaims", "ErrorsClaims", "ErrorClaims"),
    "submission": ("NumberApprovalwithin48hrs", "%ofSubmissionWithinDuedate", "ApprovalWithin48HR", "ApprovalWithin48hrs"),
    "opcensus": ("A.OPCensus", "OPCensusAch%"),
    "oprevenue": ("A.OPRevenue", "OPRevenueAch%"),
    "ipcensus": ("A.IPCensus", "IPCensusAch%"),
    "iprevenue": ("A.IPRevenue", "IPRevenueAch%"),
}
_AUDIT_DENOM_KEYWORDS = (
    "audit",
    "audits",
    "evaluated",
    "evaluations",
    "sample",
    "samples",
    "survey",
    "surveys",
    "response",
    "responses",
    "qa_count",
    "review_count",
    "checked",
    "denominator",
)
_ACTIVITY_DENOM_KEYWORDS = (
    "handled",
    "calls",
    "offered",
    "assigned",
    "submitted",
    "approved",
    "shifts",
    "days",
    "scheduled",
    "attempts",
    "contacts",
    "volume",
    "bookings",
    "requests",
    "claims",
    "tickets",
    "orders",
    "denominator",
)


def _is_percent_unit(unit: Any) -> bool:
    return str(unit or "").strip().casefold() in _PERCENT_UNITS


def _round_metric(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _norm_token(text: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").casefold())


def _is_empty_raw_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _raw_actual_entries_for_kpi(
    raw_data: dict[str, Any] | None,
    kpi_key: str,
    label: str = "",
) -> list[tuple[str, Any]]:
    """Return raw_data (key, value) pairs that hold actual/achievement inputs for ``kpi_key``."""
    if not isinstance(raw_data, dict) or not raw_data:
        return []
    key_norm = _norm_token(kpi_key)
    label_norm = _norm_token(label)
    if key_norm == "other" and label_norm:
        alias_list = _RAW_ACTUAL_KEYS_BY_KPI.get(label_norm, ())
    else:
        alias_list = _RAW_ACTUAL_KEYS_BY_KPI.get(key_norm, ())
    alias_norms = {_norm_token(a) for a in alias_list}

    matches: list[tuple[str, Any]] = []
    seen_keys: set[str] = set()
    for raw_k, raw_v in raw_data.items():
        raw_k_str = str(raw_k)
        raw_k_norm = _norm_token(raw_k_str)
        # Skip target, weight, and denominator metadata columns.
        if raw_k_str.startswith(("T.", "W.")) or any(
            prefix in raw_k_str.casefold() for prefix in ("target_", "weight_")
        ):
            continue
        if raw_k_norm in alias_norms:
            matches.append((raw_k_str, raw_v))
            seen_keys.add(raw_k_str)
            continue
        stripped = re.sub(r"^(?:a\.|actual[._]?)", "", raw_k_str, flags=re.IGNORECASE)
        stripped = re.sub(r"(?:ach%|score|rate|%)$", "", stripped, flags=re.IGNORECASE)
        stripped_norm = _norm_token(stripped)
        if stripped_norm and stripped_norm in {key_norm, label_norm} and raw_k_str not in seen_keys:
            matches.append((raw_k_str, raw_v))
            seen_keys.add(raw_k_str)
    return matches


def _has_raw_ratio_for_kpi(
    raw_data: dict[str, Any] | None,
    kpi_key: str,
    actual: float | None,
    label: str = "",
) -> bool:
    """Return True only if raw_data shows a numeric 0..1 ratio input (without '%') for ``kpi_key``."""
    entries = _raw_actual_entries_for_kpi(raw_data, kpi_key, label)
    if not entries:
        return False
    for _, raw_v in entries:
        if _is_empty_raw_value(raw_v):
            continue
        if isinstance(raw_v, str) and "%" in raw_v:
            continue
        parsed = _float_or_none(raw_v)
        if parsed is not None and 0.0 <= parsed <= 1.0:
            if actual is None or abs(parsed - actual) <= 1e-6 or parsed > 0.0:
                return True
    return False


def normalize_kpi_values_for_unit(
    items: list[dict[str, Any]],
    *,
    historical_targets: dict[str, list[float]] | None = None,
    raw_data_by_index: list[dict[str, Any] | None] | None = None,
    raw_data: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Normalize percentage KPIs stored on a 0..1 ratio scale to 0..100%.

    Never guesses units from ``actual`` magnitude alone. Only applies when the
    declared ``unit`` is ``%``, ``percent``, or ``percentage`` and either:
    - ``target`` is in ``(0, 1.0]``, or
    - ``target`` is missing/``0`` and historical non-zero targets for the same
      ``kpi_key`` are in ``(0, 1.0]`` (or raw 0..1 ratio keys exist in ``raw_data``).
    Non-percentage KPIs (count, currency, score, duration) remain untouched.
    """
    normalized: list[dict[str, Any]] = []
    for idx, raw_item in enumerate(items):
        item = dict(raw_item)
        unit = item.get("unit")
        if not _is_percent_unit(unit):
            normalized.append(item)
            continue

        actual_key = "actual" if "actual" in item else "actual_value"
        target_key = "target" if "target" in item else "target_value"
        actual = _float_or_none(item.get(actual_key))
        target = _float_or_none(item.get(target_key))
        kpi_key = str(item.get("kpi_key") or "")
        label = str(item.get("display_name") or item.get("label") or "")
        item_raw = (
            raw_data_by_index[idx]
            if raw_data_by_index is not None and idx < len(raw_data_by_index)
            else raw_data
        )

        scale = 1.0
        if target is not None and 0.0 < target <= 1.0:
            scale = 100.0
        elif target is None or target == 0.0:
            hist_nonzero = [
                t for t in (historical_targets or {}).get(kpi_key, []) if t is not None and t > 0.0
            ]
            if hist_nonzero and any(t <= 1.0 for t in hist_nonzero):
                scale = 100.0
            elif _has_raw_ratio_for_kpi(item_raw, kpi_key, actual, label):
                scale = 100.0

        if scale != 1.0:
            if actual is not None:
                item[actual_key] = _round_metric(actual * scale)
            if target is not None:
                item[target_key] = _round_metric(target * scale)
        normalized.append(item)
    return normalized


def _positive_counter(raw_data: dict[str, Any] | None, keywords: tuple[str, ...]) -> tuple[bool, bool]:
    """Return ``(has_matching_counter, has_positive_counter)`` from ``raw_data``."""
    if not isinstance(raw_data, dict) or not raw_data:
        return False, False
    matched = False
    for k, v in raw_data.items():
        k_lower = str(k).casefold()
        if any(prefix in k_lower for prefix in ("t.", "target", "w.", "weight")):
            continue
        if any(kw in k_lower for kw in keywords):
            val = _float_or_none(v)
            if val is not None:
                matched = True
                if val > 0.0:
                    return True, True
    return matched, False


def _is_audit_or_survey_kpi(kpi_key: str, display_name: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", f"{kpi_key} {display_name}".casefold()))
    return bool(tokens & _AUDIT_ASSESSMENT_TOKENS)


def classify_kpi_observation(
    *,
    kpi_key: str,
    display_name: str,
    actual: float | None,
    direction: str | None,
    weight: float | None,
    contributes_to_score: bool,
    raw_data: dict[str, Any] | None,
) -> tuple[str, float | None, str | None, str | None]:
    """Classify KPI observation as verified, recorded_zero, unverified_zero, or missing."""
    label = display_name or kpi_key
    raw_entries = _raw_actual_entries_for_kpi(raw_data, kpi_key, label)
    if actual is None:
        return (
            "missing",
            None,
            f"missing_source_value_for_kpi:{kpi_key}",
            f"Source record value for {label} is missing or blank; verify the raw upload before acting.",
        )
    if isinstance(raw_data, dict) and raw_data and raw_entries:
        if all(_is_empty_raw_value(v) for _, v in raw_entries):
            return (
                "missing",
                None,
                f"missing_source_value_for_kpi:{kpi_key}",
                f"Source record column ({raw_entries[0][0]}) for {label} is blank or missing; verify source records before acting.",
            )

    if abs(float(actual)) > 1e-12:
        return "verified", float(actual), None, None

    # actual == 0.0
    if str(direction or "").strip() == "lower_better":
        return "recorded_zero", 0.0, None, None

    is_diagnostic = (weight is not None and weight <= 0.0) or not contributes_to_score
    if is_diagnostic:
        return (
            "unverified_zero",
            0.0,
            f"unverified_zero_for_kpi:{kpi_key}",
            f"{label} shows 0 on a non-scored/zero-weight metric; verify source records before coaching.",
        )

    if _is_audit_or_survey_kpi(kpi_key, label):
        _, has_pos_audit = _positive_counter(raw_data, _AUDIT_DENOM_KEYWORDS)
        if has_pos_audit:
            return "recorded_zero", 0.0, None, None
        return (
            "unverified_zero",
            0.0,
            f"unverified_zero_for_kpi:{kpi_key}",
            f"{label} recorded 0 without a positive audit or survey sample count in source records; verify source records before coaching.",
        )

    has_denom, has_pos_activity = _positive_counter(raw_data, _ACTIVITY_DENOM_KEYWORDS)
    if has_denom and not has_pos_activity:
        return (
            "unverified_zero",
            0.0,
            f"unverified_zero_for_kpi:{kpi_key}",
            f"{label} recorded 0 with zero denominator volume in source records; verify source records before coaching.",
        )

    return "recorded_zero", 0.0, None, None


def _projected_score_lift(
    *,
    contributes_to_score: bool,
    weight: float | None,
    achievement_ratio: float | None,
    observation_status: str,
    status: str,
) -> float | None:
    if (
        not contributes_to_score
        or weight is None
        or weight <= 0.0
        or observation_status not in {"verified", "recorded_zero"}
        or status != "below_target"
        or achievement_ratio is None
    ):
        return None
    w_ratio = weight / 100.0 if weight > 1.0 else weight
    clamped = min(max(float(achievement_ratio), 0.0), 1.0)
    return round(max(0.0, (1.0 - clamped) * w_ratio * 100.0), 2)


MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _trailing_periods(month_name: str, year_value: int, count: int = 6) -> list[tuple[str, int]]:
    """Return chronological ``(month, year)`` pairs ending at ``(month_name, year_value)``."""
    month_idx = MONTH_MAP.get(str(month_name).strip().casefold())
    if not month_idx or count <= 1:
        return [(month_name, year_value)]
    total = min(int(count), 12)
    periods: list[tuple[str, int]] = []
    for offset in range(total - 1, -1, -1):
        zero_based = (year_value * 12 + (month_idx - 1)) - offset
        y, m0 = divmod(zero_based, 12)
        if 2000 <= y <= 2100:
            periods.append((_MONTH_NAMES[m0], y))
    return periods or [(month_name, year_value)]


def _record_score(record: Any) -> float | None:
    direct = _float_or_none(_entry_value(record, "score"))
    if direct is not None:
        return direct
    evaluation = _entry_value(record, "evaluation")
    if evaluation is not None:
        nested = _float_or_none(_entry_value(evaluation, "score"))
        if nested is not None:
            return nested
        return _float_or_none(_entry_value(evaluation, "total_score"))
    return None


def _kpi_entry_status(
    actual: float | None,
    target: float | None,
    direction: Any,
    achievement_percent: float | None,
) -> str:
    dir_str = str(direction or "").strip()
    if actual is not None and target is not None and dir_str in {"higher_better", "lower_better"}:
        if dir_str == "higher_better":
            return "below_target" if actual < target else "at_or_above_target"
        return "below_target" if actual > target else "at_or_above_target"
    if actual is not None and target is not None and achievement_percent is not None:
        return "below_target" if achievement_percent < 100.0 else "at_or_above_target"
    return "unknown"


def _parse_timestamp(val: Any) -> tuple[int | None, int | None, bool]:
    """Parse a timestamp into (year, month, is_malformed).

    Returns:
        (year, month, False) when valid.
        (None, None, False) when val is missing or empty.
        (None, None, True) when val is present but cannot be parsed as a full valid date.
    """
    if val is None:
        return None, None, False
    if isinstance(val, (dt.datetime, dt.date)):
        if 2000 <= val.year <= 2100:
            return val.year, val.month, False
        return None, None, True
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None, None, False
        # Full strict ISO parsing: must not accept trailing junk or invalid days
        try:
            clean_s = s.replace("Z", "+00:00")
            parsed = dt.datetime.fromisoformat(clean_s)
            if 2000 <= parsed.year <= 2100:
                return parsed.year, parsed.month, False
            return None, None, True
        except (ValueError, TypeError):
            pass
        try:
            parsed_d = dt.date.fromisoformat(s)
            if 2000 <= parsed_d.year <= 2100:
                return parsed_d.year, parsed_d.month, False
            return None, None, True
        except (ValueError, TypeError):
            pass
        return None, None, True
    return None, None, True


def _action_period(action: Any) -> tuple[int | None, int | None, bool]:
    """Parse an action's stated period into (year, month, is_malformed)."""
    if isinstance(action, dict):
        period = action.get("period") or {}
        year = period.get("year") or action.get("year")
        month = period.get("month") or action.get("month")
    else:
        year = getattr(action, "year", None)
        month = getattr(action, "month", None)

    y_val: int | None = None
    if year is not None:
        try:
            y_val = int(year)
            if y_val < 2000 or y_val > 2100:
                return None, None, True
        except (TypeError, ValueError):
            return None, None, True

    m_val: int | None = None
    if month is not None:
        m_str = str(month).strip().casefold()
        if m_str:
            m_val = MONTH_MAP.get(m_str)
            if m_val is None:
                return None, None, True

    return y_val, m_val, False


def _is_action_prior_to_period(action: Any, req_month: str, req_year: int) -> bool:
    """Enforce period boundary: actions created/dated after requested period are not prior.

    Keep reporting period and actual creation time as separate concepts.
    Fail-safe behavior: missing, malformed, or ambiguous timestamps are rejected (return False).
    Actions created after the requested period are excluded from historical evidence.
    """
    req_m = MONTH_MAP.get(str(req_month).strip().casefold(), 0)
    try:
        req_y = int(req_year)
    except (TypeError, ValueError):
        return False
    if req_m <= 0 or req_y < 2000 or req_y > 2100:
        return False

    # 1. Parse real creation time (checks created_at and timestamp)
    raw_created = None
    if isinstance(action, dict):
        raw_created = action.get("created_at")
        if raw_created is None:
            raw_created = action.get("timestamp")
    else:
        raw_created = getattr(action, "created_at", None)
        if raw_created is None:
            raw_created = getattr(action, "timestamp", None)

    ts_y, ts_m, ts_malformed = _parse_timestamp(raw_created)
    if ts_malformed:
        # Malformed creation timestamp fails closed
        return False
    if ts_y is None or ts_m is None:
        # Missing creation timestamp: fail closed, do not invent it
        return False

    # Check creation time boundary: must not be after requested period
    if ts_y > req_y:
        return False
    if ts_y == req_y and ts_m > req_m:
        return False

    # 2. Parse stated reporting period (year, month)
    act_y, act_m, period_malformed = _action_period(action)
    if period_malformed:
        # Malformed reporting period fails closed
        return False

    if act_y is not None and act_m is not None:
        if act_y > req_y:
            return False
        if act_y == req_y and act_m > req_m:
            return False

    return True


def _resolve_action_branch(action: Any, corrective_action_service: CorrectiveActionService | None = None) -> tuple[str | None, bool]:
    """Resolve the branch attribution of an action.

    Returns:
        (branch_key, is_ambiguous)
        If established and clear: (branch_key, False)
        If missing: (None, False)
        If ambiguous/conflicting: (None, True)
    """
    action_branch = None
    if isinstance(action, dict):
        action_branch = action.get("branch_key")
    else:
        action_branch = getattr(action, "branch_key", None)

    # Check for multiple or delimiter-separated branches
    if isinstance(action_branch, (list, tuple, set)):
        items = [str(x).strip() for x in action_branch if str(x).strip()]
        if len(items) > 1:
            return None, True
        action_branch = items[0] if items else None
    elif isinstance(action_branch, str):
        action_branch = action_branch.strip()
        if "," in action_branch or "/" in action_branch or ";" in action_branch:
            return None, True
        if not action_branch:
            action_branch = None

    record_branch = None
    if not isinstance(action, dict) and corrective_action_service is not None:
        try:
            perf_rec = corrective_action_service._performance_record_for_action(action)
            if perf_rec and perf_rec.branch_key:
                record_branch = str(perf_rec.branch_key).strip()
        except Exception:
            record_branch = None

    if action_branch and record_branch:
        if action_branch.casefold() != record_branch.casefold():
            return None, True
        return action_branch, False

    established = action_branch or record_branch
    if not established:
        return None, False
    return established, False


def _float_or_none(value: Any) -> float | None:
    """Return ``float(value)`` unchanged, preserving ``None`` and real ``0.0``.

    A missing value is never coerced to ``0``; only a value that cannot be
    read as a number at all becomes ``None`` (and is flagged as missing by
    the caller).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _entry_value(entry: Any, key: str) -> Any:
    if isinstance(entry, dict):
        return entry.get(key)
    return getattr(entry, key, None)


def _sanitize_prior_action(action: Any) -> dict[str, Any]:
    """Structured prior-action evidence only: no free text, owner, or due date."""
    if isinstance(action, dict):
        action_type = action.get("suggested_action") or action.get("action_type")
        status = action.get("status")
        linked_kpi_key = action.get("linked_kpi_key")
        month = action.get("month")
        year = action.get("year")
    else:
        action_type = getattr(action, "action_type", None)
        status = getattr(action, "status", None)
        linked_kpi_key = getattr(action, "linked_kpi_key", None)
        month = getattr(action, "month", None)
        year = getattr(action, "year", None)
    action_type = str(action_type).strip() if action_type else None
    status = str(status).strip() if status else None
    linked_kpi_key = str(linked_kpi_key).strip() if linked_kpi_key else None
    month = str(month).strip() if month else None
    try:
        year_value: int | None = int(year) if year is not None else None
    except (TypeError, ValueError):
        year_value = None
    summary = f"{action_type} ({status})" if action_type and status else (action_type or status or "Corrective action")
    return {
        "action_type": action_type,
        "status": status,
        "linked_kpi_key": linked_kpi_key,
        "period": {"month": month, "year": year_value},
        "summary": summary,
    }


class CorrectiveActionEvidenceService:
    """Build an authorized, read-only evidence bundle for one subject/period."""

    def __init__(
        self,
        db: Session,
        *,
        dashboard_service: DashboardRecordService | None = None,
        corrective_action_service: CorrectiveActionService | None = None,
        action_repository: ActionRepository | None = None,
    ) -> None:
        self.db = db
        self.dashboard_service = dashboard_service or DashboardRecordService(db)
        self.corrective_action_service = corrective_action_service or CorrectiveActionService(db)
        self.action_repository = action_repository or ActionRepository(db)

    def build(
        self,
        *,
        user_scope: dict,
        employee_id: str | None = None,
        team: str,
        month: str,
        year: int,
        performance_level: str = "Employee",
        linked_kpi_key: str | None = None,
    ) -> dict[str, Any]:
        """Return the evidence bundle for ``employee_id`` or, when it is ``None``, for ``team``.

        Raises ``ValueError`` for an invalid period/level/linked-KPI argument
        and ``PermissionError`` when the subject is outside ``user_scope``.
        Reads only; the database is never written to.
        """
        team_name = str(team or "").strip()
        if not team_name:
            raise ValueError("team is required")
        month_name = str(month or "").strip()
        if not month_name:
            raise ValueError("month is required")
        try:
            year_value = int(year)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"year must be an integer, got {year!r}") from exc
        if year_value < 2000 or year_value > 2100:
            raise ValueError(f"year is out of range: {year_value}")
        level = normalize_performance_level(performance_level)
        linked_key = str(linked_kpi_key).strip() if linked_kpi_key else None
        scope = dict(user_scope or {})

        user_branches = [b.casefold() for b in (scope.get("accessible_branches") or scope.get("allowed_branches") or []) if str(b).strip()]
        user_regions = [r.casefold() for r in (scope.get("accessible_regions") or []) if str(r).strip()]
        has_unrestricted_scope = bool(scope.get("has_unrestricted_team_access"))
        user_role = str(scope.get("role") or scope.get("db_role") or "")
        is_branch_restricted = bool(
            user_role == "Branch Director"
            or scope.get("is_branch_restricted")
            or (user_branches and not has_unrestricted_scope and user_role not in ("Regional Manager", "General Manager", "Admin", "Super Admin"))
        )

        employee: Employee | None = None
        resolved_employee_id: str | None = str(employee_id).strip() if employee_id else None
        subject = "team"
        if resolved_employee_id:
            subject = "employee"
            employee = (
                self.db.query(Employee)
                .filter(Employee.employee_id == resolved_employee_id)
                .order_by(Employee.is_active.desc(), Employee.id.asc())
                .first()
            )
            if employee is None and resolved_employee_id.upper().startswith(("SGHD", "SGHA")):
                suffix = resolved_employee_id[4:]
                employee = (
                    self.db.query(Employee)
                    .filter(Employee.employee_id == suffix)
                    .order_by(Employee.is_active.desc(), Employee.id.asc())
                    .first()
                )
            if employee is None:
                raise ValueError(f"Unknown employee: {employee_id}")
            # Authorisation first: raises PermissionError outside the caller's scope.
            self.corrective_action_service.ensure_employee_scope(resolved_employee_id, scope)
            resolved_employee_id = str(employee.employee_id).strip()
            emp_team_obj = getattr(employee, "team", None)
            employee_teams = {
                str(val).strip().casefold()
                for val in (
                    getattr(emp_team_obj, "display_name", None),
                    getattr(emp_team_obj, "name", None),
                    logical_team_name(emp_team_obj) if emp_team_obj is not None else None,
                )
                if val and str(val).strip()
            }
            is_current_team = team_name.casefold() in employee_teams
            if not is_current_team:
                # Check if employee had a historical record in the requested team for that period (transfers)
                historical_query = (
                    self.db.query(PerformanceRecord)
                    .join(Team, Team.id == PerformanceRecord.team_id)
                    .filter(
                        PerformanceRecord.employee_id == employee.id,
                        PerformanceRecord.month == month_name,
                        PerformanceRecord.year == year_value,
                        (
                            Team.display_name.ilike(team_name)
                            | Team.name.ilike(team_name)
                            | Team.db_name.ilike(team_name)
                        ),
                    )
                )

                hist_records = historical_query.all()
                if is_branch_restricted:
                    hist_records = [
                        r for r in hist_records
                        if r.branch_key and str(r.branch_key).strip().casefold() in user_branches
                    ]
                if user_regions and not has_unrestricted_scope:
                    hist_records = [
                        r for r in hist_records
                        if r.region and str(r.region).strip().casefold() in user_regions
                    ]

                if not hist_records:
                    raise PermissionError(
                        "The employee is not in the requested team within your authorized branch/region for the period"
                    )
        elif not user_can_access_team_level(scope, team_name, level):
            raise PermissionError("The team is outside your authorized action scope")

        records = self.dashboard_service.list_records(
            team=team_name,
            month=month_name,
            employee_id=resolved_employee_id,
            performance_level=level,
            year=year_value,
            scope=scope,
        )
        records = list(records or [])
        if resolved_employee_id:
            records = [
                record
                for record in records
                if str(_entry_value(record, "employee_id") or "").strip() == resolved_employee_id
            ]

        # Verify historical branch and region of actual scoped records (including transferred employees)
        if resolved_employee_id and records:
            for rec in records:
                rec_branch = _entry_value(rec, "branch_key") or getattr(rec, "branch_key", None)
                if is_branch_restricted and rec_branch and str(rec_branch).strip().casefold() not in user_branches:
                    raise PermissionError(
                        "The employee's historical record for this period belongs to a branch outside your authorized scope"
                    )
                rec_reg = _entry_value(rec, "region") or getattr(rec, "region", None)
                if user_regions and not has_unrestricted_scope and rec_reg and str(rec_reg).strip().casefold() not in user_regions:
                    raise PermissionError(
                        "The employee's historical record for this period belongs to a region outside your authorized scope"
                    )
        elif resolved_employee_id and not records and employee is not None:
            # Check if record exists in DB for this period but was outside user's branch/region
            out_of_scope_rec = (
                self.db.query(PerformanceRecord)
                .filter(
                    PerformanceRecord.employee_id == employee.id,
                    PerformanceRecord.month == month_name,
                    PerformanceRecord.year == year_value,
                )
                .first()
            )
            if out_of_scope_rec is not None:
                oos_b = str(getattr(out_of_scope_rec, "branch_key", "") or "").strip().casefold()
                oos_r = str(getattr(out_of_scope_rec, "region", "") or "").strip().casefold()
                if is_branch_restricted and oos_b and oos_b not in user_branches:
                    raise PermissionError(
                        "The employee's historical record for this period belongs to a branch outside your authorized scope"
                    )
                if user_regions and not has_unrestricted_scope and oos_r and oos_r not in user_regions:
                    raise PermissionError(
                        "The employee's historical record for this period belongs to a region outside your authorized scope"
                    )

        reasons: list[str] = []
        evidence_limitations: list[str] = []
        if not records:
            reasons.append("no_performance_record_for_period")

        window = _trailing_periods(month_name, year_value, 6)
        prior_periods = window[:-1]
        prior_by_key = self._fetch_prior_records(
            team_name=team_name,
            level=level,
            resolved_employee_id=resolved_employee_id,
            prior_periods=prior_periods,
            scope=scope,
            is_branch_restricted=is_branch_restricted,
            user_branches=user_branches,
            user_regions=user_regions,
            has_unrestricted_scope=has_unrestricted_scope,
        ) if records else {}
        historical_targets: dict[str, list[float]] = {}
        for recs in prior_by_key.values():
            for rec in recs:
                for entry in _entry_value(rec, "kpi_values") or []:
                    k = _entry_value(entry, "kpi_key")
                    t_val = _float_or_none(_entry_value(entry, "target_value"))
                    if k and t_val is not None and t_val > 0.0:
                        historical_targets.setdefault(str(k), []).append(t_val)

        kpi_items: list[dict[str, Any]] = []
        raw_data_by_index: list[dict[str, Any] | None] = []
        regions: set[str] = set()
        positions: set[str] = set()
        scoring_bases: set[str] = set()
        for record in records:
            region = _entry_value(record, "region")
            if region:
                regions.add(str(region).strip())
            position = _entry_value(record, "position")
            if position:
                positions.add(str(position).strip())
            raw_data = _entry_value(record, "raw_data")
            raw_data_dict = raw_data if isinstance(raw_data, dict) else None
            for entry in _entry_value(record, "kpi_values") or []:
                kpi_key = _entry_value(entry, "kpi_key")
                if not kpi_key:
                    continue
                kpi_key = str(kpi_key)
                display_name = str(_entry_value(entry, "label") or kpi_key)
                raw_actual = _float_or_none(_entry_value(entry, "actual_value"))
                target = _float_or_none(_entry_value(entry, "target_value"))
                direction = _entry_value(entry, "direction")
                weight = _float_or_none(_entry_value(entry, "weight_applied"))
                view_only = bool(_entry_value(entry, "view_only"))
                contributes_to_score = (not view_only) and (weight is None or weight > 0.0)
                achievement_ratio = _float_or_none(_entry_value(entry, "achievement_ratio"))
                achievement_percent = achievement_ratio * 100.0 if achievement_ratio is not None else None

                obs_status, clean_actual, obs_reason, obs_note = classify_kpi_observation(
                    kpi_key=kpi_key,
                    display_name=display_name,
                    actual=raw_actual,
                    direction=str(direction) if direction is not None else None,
                    weight=weight,
                    contributes_to_score=contributes_to_score,
                    raw_data=raw_data_dict,
                )
                if obs_status == "missing":
                    clean_actual = None
                    achievement_ratio = None
                    achievement_percent = None
                    reasons.append(f"missing_actual_for_kpi:{kpi_key}")
                if obs_reason:
                    reasons.append(obs_reason)
                if obs_note and obs_note not in evidence_limitations:
                    evidence_limitations.append(obs_note)
                if target is None:
                    reasons.append(f"missing_target_for_kpi:{kpi_key}")
                kpi_items.append(
                    {
                        "employee_id": str(_entry_value(record, "employee_id") or "").strip() or None,
                        "kpi_key": kpi_key,
                        "display_name": display_name,
                        "actual": clean_actual,
                        "target": target,
                        "unit": _entry_value(entry, "unit"),
                        "direction": direction,
                        "weight": weight,
                        "contributes_to_score": contributes_to_score,
                        "achievement_ratio": achievement_ratio,
                        "achievement_percent": achievement_percent,
                        "observation_status": obs_status,
                        "previous_actual": None,
                        "previous_period": None,
                        "projected_agent_score_lift": None,
                    }
                )
                raw_data_by_index.append(raw_data_dict)

        kpi_items = normalize_kpi_values_for_unit(
            kpi_items,
            historical_targets=historical_targets,
            raw_data_by_index=raw_data_by_index,
        )
        for item in kpi_items:
            if item.get("observation_status") == "missing":
                item["status"] = "unknown"
                item["projected_agent_score_lift"] = None
                continue
            status = _kpi_entry_status(
                item.get("actual"),
                item.get("target"),
                item.get("direction"),
                item.get("achievement_percent"),
            )
            item["status"] = status
            ratio = item.get("achievement_ratio")
            if ratio is None and item.get("actual") is not None and item.get("target") is not None and float(item["target"]) > 0.0:
                if str(item.get("direction") or "").strip() == "lower_better":
                    ratio = (float(item["target"]) / float(item["actual"])) if float(item["actual"]) > 0.0 else 1.0
                else:
                    ratio = float(item["actual"]) / float(item["target"])
                item["achievement_ratio"] = ratio
                if item.get("achievement_percent") is None:
                    item["achievement_percent"] = ratio * 100.0
            item["projected_agent_score_lift"] = _projected_score_lift(
                contributes_to_score=bool(item.get("contributes_to_score", True)),
                weight=item.get("weight"),
                achievement_ratio=item.get("achievement_ratio"),
                observation_status=str(item.get("observation_status") or "verified"),
                status=status,
            )

        if records and not kpi_items:
            reasons.append("no_kpi_values_for_period")
        if linked_key and not any(item["kpi_key"] == linked_key for item in kpi_items):
            linked_cf = linked_key.casefold()
            linked_norm = _norm_token(linked_key)
            ci_keys = {str(item["kpi_key"]) for item in kpi_items if str(item["kpi_key"]).casefold() == linked_cf}
            if len(ci_keys) == 1:
                linked_key = next(iter(ci_keys))
            else:
                name_keys = {
                    str(item["kpi_key"])
                    for item in kpi_items
                    if _norm_token(item.get("display_name")) == linked_norm
                }
                if len(name_keys) == 1:
                    linked_key = next(iter(name_keys))
                else:
                    reasons.append(f"linked_kpi_not_found:{linked_key}")

        # Scoring basis: the pinned team-configuration version(s) stored on
        # the period's own records, if any. No pinned basis is reported as
        # None rather than a guessed default. With no records for the period
        # there is no basis to report either.
        if records:
            valid_uuids = [
                u
                for r in records
                if (u := CorrectiveActionService._uuid(str(_entry_value(r, "id") or ""))) is not None
            ]
            if valid_uuids:
                raw_records = (
                    self.db.query(PerformanceRecord)
                    .filter(PerformanceRecord.id.in_(valid_uuids))
                    .all()
                )
            else:
                raw_records = (
                    self.db.query(PerformanceRecord)
                    .filter(
                        PerformanceRecord.month == month_name,
                        PerformanceRecord.year == year_value,
                    )
                    .all()
                )
            record_ids = {str(_entry_value(record, "id") or "") for record in records}
            for raw in raw_records:
                if str(raw.id) not in record_ids:
                    continue
                payload = raw.record_payload if isinstance(raw.record_payload, dict) else {}
                basis = payload.get("evaluation_basis")
                if isinstance(basis, dict) and (basis.get("pinned") is True or basis.get("confirmed") is True):
                    version_number = basis.get("version_number")
                    policy = basis.get("policy")
                    label = f"pinned team-configuration version {version_number}" if version_number is not None else "pinned team-configuration"
                    if policy:
                        label = f"{label} ({policy})"
                    scoring_bases.add(label)
        scoring_basis = "; ".join(sorted(scoring_bases)) if scoring_bases else None

        if subject == "employee" and employee is not None:
            country = str(employee.region).strip() if employee.region else None
            position = str(employee.position_name).strip() if employee.position_name else None
            employee_name = str(employee.name).strip() if employee.name else None
            prior_actions = self._prior_actions_for_employee(employee, scope, month_name, year_value)
            team_headcount: int | None = None
            if records:
                team_recs = self.dashboard_service.list_records(
                    team=team_name,
                    month=month_name,
                    year=year_value,
                    performance_level=level,
                    scope=scope,
                )
                team_ids = {
                    str(_entry_value(r, "employee_id") or _entry_value(r, "id") or idx)
                    for idx, r in enumerate(team_recs or [])
                }
                team_headcount = len(team_ids) or len(records)
        else:
            country = next(iter(sorted(regions))) if len(regions) == 1 else None
            if len(regions) > 1:
                reasons.append("multiple_regions_in_period")
            position = next(iter(sorted(positions))) if len(positions) == 1 else None
            employee_name = None
            prior_actions = self._prior_actions_for_team(team_name, scope, month_name, year_value)
            team_headcount = (
                len({str(_entry_value(r, "employee_id") or _entry_value(r, "id") or idx) for idx, r in enumerate(records)})
                if records
                else None
            )

        trend_summary = (
            self._build_trend_summary(
                subject=subject,
                team_name=team_name,
                month_name=month_name,
                year_value=year_value,
                level=level,
                resolved_employee_id=resolved_employee_id,
                current_records=records,
                current_kpi_items=kpi_items,
                scope=scope,
                is_branch_restricted=is_branch_restricted,
                user_branches=user_branches,
                user_regions=user_regions,
                has_unrestricted_scope=has_unrestricted_scope,
                prior_by_key=prior_by_key,
                historical_targets=historical_targets,
            )
            if records
            else {}
        )

        return {
            "subject": subject,
            "employee_id": resolved_employee_id if resolved_employee_id else None,
            "employee_name": employee_name,
            "country": country,
            "function": (functions_for_team(team_name) or [None])[0],
            "team": team_name,
            "position": position,
            "period": {"month": month_name, "year": year_value},
            "performance_level": level,
            "linked_kpi_key": linked_key,
            "scoring_basis": scoring_basis,
            "team_headcount": team_headcount,
            "kpi_items": kpi_items,
            "trend_summary": trend_summary,
            "prior_corrective_actions": prior_actions,
            "evidence_limitations": evidence_limitations,
            "insufficient_evidence_reasons": sorted(set(reasons)),
            "read_only": True,
        }

    def _fetch_prior_records(
        self,
        *,
        team_name: str,
        level: str,
        resolved_employee_id: str | None,
        prior_periods: list[tuple[str, int]],
        scope: dict,
        is_branch_restricted: bool,
        user_branches: list[str],
        user_regions: list[str],
        has_unrestricted_scope: bool,
    ) -> dict[tuple[str, int], list[Any]]:
        prior_by_key: dict[tuple[str, int], list[Any]] = {(m.casefold(), y): [] for m, y in prior_periods}
        if not prior_periods:
            return prior_by_key
        try:
            raw_prior = self.dashboard_service.list_records(
                team=team_name,
                employee_id=resolved_employee_id,
                performance_level=level,
                periods=[(y, m) for m, y in prior_periods],
                scope=scope,
            )
        except TypeError:
            raw_prior = []
            for m, y in prior_periods:
                raw_prior.extend(
                    self.dashboard_service.list_records(
                        team=team_name,
                        month=m,
                        employee_id=resolved_employee_id,
                        performance_level=level,
                        year=y,
                        scope=scope,
                    )
                    or []
                )

        for rec in raw_prior or []:
            if resolved_employee_id and str(_entry_value(rec, "employee_id") or "").strip() != resolved_employee_id:
                continue
            rec_branch = _entry_value(rec, "branch_key") or getattr(rec, "branch_key", None)
            if is_branch_restricted:
                if not rec_branch or str(rec_branch).strip().casefold() not in user_branches:
                    continue
            rec_reg = _entry_value(rec, "region") or getattr(rec, "region", None)
            if user_regions and not has_unrestricted_scope:
                if not rec_reg or str(rec_reg).strip().casefold() not in user_regions:
                    continue
            rec_month = str(_entry_value(rec, "month") or "").strip().casefold()
            try:
                rec_year = int(_entry_value(rec, "year") or 0)
            except (TypeError, ValueError):
                continue
            bucket = prior_by_key.get((rec_month, rec_year))
            if bucket is not None:
                bucket.append(rec)
        return prior_by_key

    def _build_trend_summary(
        self,
        *,
        subject: str,
        team_name: str,
        month_name: str,
        year_value: int,
        level: str,
        resolved_employee_id: str | None,
        current_records: list[Any],
        current_kpi_items: list[dict[str, Any]],
        scope: dict,
        is_branch_restricted: bool,
        user_branches: list[str],
        user_regions: list[str],
        has_unrestricted_scope: bool,
        prior_by_key: dict[tuple[str, int], list[Any]] | None = None,
        historical_targets: dict[str, list[float]] | None = None,
    ) -> dict[str, Any]:
        """Compute bounded trailing 6-month score & KPI trends (strictly read-only, ``<=`` period)."""
        window = _trailing_periods(month_name, year_value, 6)
        prior_periods = window[:-1]
        if prior_by_key is None:
            prior_by_key = self._fetch_prior_records(
                team_name=team_name,
                level=level,
                resolved_employee_id=resolved_employee_id,
                prior_periods=prior_periods,
                scope=scope,
                is_branch_restricted=is_branch_restricted,
                user_branches=user_branches,
                user_regions=user_regions,
                has_unrestricted_scope=has_unrestricted_scope,
            )

        period_buckets: list[tuple[str, int, list[Any]]] = [
            (m, y, prior_by_key.get((m.casefold(), y), [])) for m, y in prior_periods
        ]
        period_buckets.append((month_name, year_value, list(current_records)))

        period_scores: list[tuple[int, str, int, float | None]] = []
        measured_periods = 0
        for bucket_idx, (m, y, recs) in enumerate(period_buckets):
            if not recs:
                continue
            measured_periods += 1
            scores = [s for rec in recs if (s := _record_score(rec)) is not None]
            mean_score = round(sum(scores) / len(scores), 1) if scores else None
            period_scores.append((bucket_idx, m, y, mean_score))

        scored_periods = [p for p in period_scores if p[3] is not None]
        current_score = period_scores[-1][3] if period_scores else None
        prior_scored = [p for p in period_scores[:-1] if p[3] is not None]
        if prior_scored:
            prev_idx, prev_m, prev_y, previous_score = prior_scored[-1]
            previous_period = f"{prev_m} {prev_y}"
            curr_idx = len(period_buckets) - 1
            missing_intermediate_periods = [
                f"{m} {y}"
                for m, y, recs in period_buckets[prev_idx + 1 : curr_idx]
                if not recs or all(_record_score(r) is None for r in recs)
            ]
            previous_is_adjacent = len(missing_intermediate_periods) == 0
        else:
            previous_score = None
            previous_period = None
            missing_intermediate_periods = []
            previous_is_adjacent = True

        if scored_periods:
            _, win_m, win_y, window_start_score = scored_periods[0]
            window_start_period = f"{win_m} {win_y}"
            window_delta = (
                round(current_score - window_start_score, 1)
                if len(scored_periods) >= 2 and current_score is not None and window_start_score is not None
                else None
            )
        else:
            window_start_period = None
            window_start_score = None
            window_delta = None

        score_delta = (
            round(current_score - previous_score, 1)
            if current_score is not None and previous_score is not None
            else None
        )
        if score_delta is None:
            score_direction = "single_period"
        elif score_delta <= -1.0:
            score_direction = "declining"
        elif score_delta >= 1.0:
            score_direction = "improving"
        else:
            score_direction = "stable"

        kpi_trends: dict[str, Any] = {}
        weak_kpis: list[dict[str, Any]] = []

        if subject == "employee":
            history_by_kpi: dict[str, list[dict[str, Any]]] = {}
            for m, y, recs in period_buckets:
                if not recs:
                    continue
                is_current = m.casefold() == month_name.casefold() and y == year_value
                period_label = f"{m} {y}"
                if is_current:
                    for item in current_kpi_items:
                        key_str = str(item.get("kpi_key") or "")
                        if not key_str:
                            continue
                        history_by_kpi.setdefault(key_str, []).append(
                            {
                                "is_current": True,
                                "period_label": period_label,
                                "actual": item.get("actual"),
                                "target": item.get("target"),
                                "direction": item.get("direction"),
                                "achievement_percent": item.get("achievement_percent"),
                                "status": item.get("status")
                                or _kpi_entry_status(
                                    item.get("actual"),
                                    item.get("target"),
                                    item.get("direction"),
                                    item.get("achievement_percent"),
                                ),
                            }
                        )
                    continue

                rec = recs[0]
                raw_data = _entry_value(rec, "raw_data")
                raw_data_dict = raw_data if isinstance(raw_data, dict) else None
                raw_period_items: list[dict[str, Any]] = []
                for entry in _entry_value(rec, "kpi_values") or []:
                    key = _entry_value(entry, "kpi_key")
                    if not key:
                        continue
                    key_str = str(key)
                    label = str(_entry_value(entry, "label") or key_str)
                    raw_actual = _float_or_none(_entry_value(entry, "actual_value"))
                    target = _float_or_none(_entry_value(entry, "target_value"))
                    ratio = _float_or_none(_entry_value(entry, "achievement_ratio"))
                    ach_pct = ratio * 100.0 if ratio is not None else None
                    direction_val = _entry_value(entry, "direction")
                    weight = _float_or_none(_entry_value(entry, "weight_applied"))
                    contributes = (not bool(_entry_value(entry, "view_only"))) and (weight is None or weight > 0.0)
                    obs_status, clean_actual, _, _ = classify_kpi_observation(
                        kpi_key=key_str,
                        display_name=label,
                        actual=raw_actual,
                        direction=str(direction_val) if direction_val is not None else None,
                        weight=weight,
                        contributes_to_score=contributes,
                        raw_data=raw_data_dict,
                    )
                    if obs_status == "missing":
                        clean_actual = None
                        ach_pct = None
                    raw_period_items.append(
                        {
                            "kpi_key": key_str,
                            "display_name": label,
                            "actual": clean_actual,
                            "target": target,
                            "unit": _entry_value(entry, "unit"),
                            "direction": direction_val,
                            "achievement_percent": ach_pct,
                            "observation_status": obs_status,
                        }
                    )
                norm_period_items = normalize_kpi_values_for_unit(
                    raw_period_items,
                    historical_targets=historical_targets,
                    raw_data=raw_data_dict,
                )
                for pt in norm_period_items:
                    pt_status = (
                        "unknown"
                        if pt.get("observation_status") == "missing"
                        else _kpi_entry_status(
                            pt.get("actual"),
                            pt.get("target"),
                            pt.get("direction"),
                            pt.get("achievement_percent"),
                        )
                    )
                    history_by_kpi.setdefault(pt["kpi_key"], []).append(
                        {
                            "is_current": False,
                            "period_label": period_label,
                            "actual": pt.get("actual"),
                            "target": pt.get("target"),
                            "direction": pt.get("direction"),
                            "achievement_percent": pt.get("achievement_percent"),
                            "status": pt_status,
                        }
                    )

            for key_str, points in history_by_kpi.items():
                measured_pts = [p for p in points if p["actual"] is not None]
                prior_pts = [p for p in measured_pts if not p["is_current"]]
                curr_pts = [p for p in measured_pts if p["is_current"]]
                curr_pt = curr_pts[-1] if curr_pts else None
                prev_pt = prior_pts[-1] if prior_pts else None
                months_below = sum(1 for p in measured_pts if p["status"] == "below_target")
                dir_str = str((curr_pt or {}).get("direction") or (prev_pt or {}).get("direction") or "").strip()
                if curr_pt is None or prev_pt is None or curr_pt["actual"] is None or prev_pt["actual"] is None:
                    trend_dir = "single_period"
                elif dir_str == "lower_better":
                    if curr_pt["actual"] > prev_pt["actual"] + 1e-6:
                        trend_dir = "worsening"
                    elif curr_pt["actual"] < prev_pt["actual"] - 1e-6:
                        trend_dir = "improving"
                    else:
                        trend_dir = "unchanged"
                else:
                    if curr_pt["actual"] < prev_pt["actual"] - 1e-6:
                        trend_dir = "worsening"
                    elif curr_pt["actual"] > prev_pt["actual"] + 1e-6:
                        trend_dir = "improving"
                    else:
                        trend_dir = "unchanged"

                kpi_trends[key_str] = {
                    "measured_periods": len(measured_pts),
                    "months_below_target": months_below,
                    "previous_actual": prev_pt["actual"] if prev_pt else None,
                    "previous_period": prev_pt["period_label"] if prev_pt else None,
                    "direction": trend_dir,
                }

            for item in current_kpi_items:
                t_info = kpi_trends.get(item["kpi_key"], {})
                item["previous_actual"] = t_info.get("previous_actual")
                item["previous_period"] = t_info.get("previous_period")
                status = item.get("status") or _kpi_entry_status(
                    item.get("actual"),
                    item.get("target"),
                    item.get("direction"),
                    item.get("achievement_percent"),
                )
                if status != "below_target":
                    continue
                weak_kpis.append(
                    {
                        "kpi_key": item["kpi_key"],
                        "display_name": item.get("display_name") or item["kpi_key"],
                        "actual": item.get("actual"),
                        "target": item.get("target"),
                        "unit": item.get("unit"),
                        "direction": item.get("direction"),
                        "achievement_percent": item.get("achievement_percent"),
                        "observation_status": item.get("observation_status", "verified"),
                        "trend_direction": t_info.get("direction", "single_period"),
                        "previous_actual": t_info.get("previous_actual"),
                        "previous_period": t_info.get("previous_period"),
                        "months_below_target": t_info.get("months_below_target", 1),
                        "measured_periods": t_info.get("measured_periods", 1),
                    }
                )
            weak_kpis.sort(
                key=lambda k: (
                    k["achievement_percent"] if k["achievement_percent"] is not None else float("inf"),
                    str(k["kpi_key"]),
                )
            )
        else:
            team_history_by_kpi: dict[str, list[dict[str, Any]]] = {}
            for m, y, recs in period_buckets:
                if not recs:
                    continue
                is_current = m.casefold() == month_name.casefold() and y == year_value
                period_label = f"{m} {y}"
                per_kpi_statuses: dict[str, list[str]] = {}
                if is_current:
                    for item in current_kpi_items:
                        status = item.get("status") or _kpi_entry_status(
                            item.get("actual"),
                            item.get("target"),
                            item.get("direction"),
                            item.get("achievement_percent"),
                        )
                        if status != "unknown":
                            per_kpi_statuses.setdefault(str(item["kpi_key"]), []).append(status)
                else:
                    for rec in recs:
                        raw_data = _entry_value(rec, "raw_data")
                        raw_data_dict = raw_data if isinstance(raw_data, dict) else None
                        raw_period_items: list[dict[str, Any]] = []
                        for entry in _entry_value(rec, "kpi_values") or []:
                            key = _entry_value(entry, "kpi_key")
                            if not key:
                                continue
                            key_str = str(key)
                            label = str(_entry_value(entry, "label") or key_str)
                            raw_actual = _float_or_none(_entry_value(entry, "actual_value"))
                            target = _float_or_none(_entry_value(entry, "target_value"))
                            ratio = _float_or_none(_entry_value(entry, "achievement_ratio"))
                            ach_pct = ratio * 100.0 if ratio is not None else None
                            direction_val = _entry_value(entry, "direction")
                            weight = _float_or_none(_entry_value(entry, "weight_applied"))
                            contributes = (not bool(_entry_value(entry, "view_only"))) and (weight is None or weight > 0.0)
                            obs_status, clean_actual, _, _ = classify_kpi_observation(
                                kpi_key=key_str,
                                display_name=label,
                                actual=raw_actual,
                                direction=str(direction_val) if direction_val is not None else None,
                                weight=weight,
                                contributes_to_score=contributes,
                                raw_data=raw_data_dict,
                            )
                            if obs_status == "missing":
                                clean_actual = None
                                ach_pct = None
                            raw_period_items.append(
                                {
                                    "kpi_key": key_str,
                                    "display_name": label,
                                    "actual": clean_actual,
                                    "target": target,
                                    "unit": _entry_value(entry, "unit"),
                                    "direction": direction_val,
                                    "achievement_percent": ach_pct,
                                    "observation_status": obs_status,
                                }
                            )
                        for pt in normalize_kpi_values_for_unit(
                            raw_period_items,
                            historical_targets=historical_targets,
                            raw_data=raw_data_dict,
                        ):
                            if pt.get("observation_status") == "missing":
                                continue
                            status = _kpi_entry_status(
                                pt.get("actual"),
                                pt.get("target"),
                                pt.get("direction"),
                                pt.get("achievement_percent"),
                            )
                            if status != "unknown":
                                per_kpi_statuses.setdefault(str(pt["kpi_key"]), []).append(status)
                for key_str, statuses in per_kpi_statuses.items():
                    below_count = sum(1 for s in statuses if s == "below_target")
                    team_history_by_kpi.setdefault(key_str, []).append(
                        {
                            "is_current": is_current,
                            "period_label": period_label,
                            "members_below": below_count,
                            "members_with_data": len(statuses),
                        }
                    )

            for key_str, pts in team_history_by_kpi.items():
                prior_pts = [p for p in pts if not p["is_current"] and p["members_with_data"] > 0]
                curr_pts = [p for p in pts if p["is_current"] and p["members_with_data"] > 0]
                curr_pt = curr_pts[-1] if curr_pts else None
                prev_pt = prior_pts[-1] if prior_pts else None
                months_with_gap = sum(1 for p in pts if p["members_below"] > 0)
                if curr_pt and prev_pt:
                    curr_share = curr_pt["members_below"] / curr_pt["members_with_data"]
                    prev_share = prev_pt["members_below"] / prev_pt["members_with_data"]
                    if curr_share - prev_share > 0.02:
                        trend_dir = "worsening"
                    elif curr_share - prev_share < -0.02:
                        trend_dir = "improving"
                    else:
                        trend_dir = "unchanged"
                else:
                    trend_dir = "single_period"
                kpi_trends[key_str] = {
                    "measured_periods": len(pts),
                    "months_with_gap": months_with_gap,
                    "previous_members_below": prev_pt["members_below"] if prev_pt else None,
                    "previous_members_with_data": prev_pt["members_with_data"] if prev_pt else None,
                    "previous_period": prev_pt["period_label"] if prev_pt else None,
                    "direction": trend_dir,
                }

        return {
            "measured_periods": measured_periods,
            "current_score": current_score,
            "previous_score": previous_score,
            "previous_period": previous_period,
            "previous_is_adjacent": previous_is_adjacent,
            "missing_intermediate_periods": missing_intermediate_periods,
            "window_start_period": window_start_period,
            "window_start_score": window_start_score,
            "window_delta": window_delta,
            "score_delta": score_delta,
            "score_direction": score_direction,
            "kpi_trends": kpi_trends,
            "weak_kpis": weak_kpis,
        }

    def _prior_actions_for_employee(
        self,
        employee: Employee,
        scope: dict | None,
        requested_month: str,
        requested_year: int,
    ) -> list[dict[str, Any]]:
        """Prior actions for one employee, strictly scope-enforced and period-bounded."""
        history = []
        if isinstance(scope, dict):
            try:
                history = self.corrective_action_service.get_history(str(employee.employee_id), scope)
            except Exception:
                history = []
        else:
            # When scope is None (e.g. system read), serialize active rows
            rows = self.action_repository.list_active_by_employee(employee.id)
            history = [self.corrective_action_service.serialize(row) for row in rows]

        user_scope = scope if isinstance(scope, dict) else {}
        accessible_branches = [b.casefold() for b in (user_scope.get("accessible_branches") or user_scope.get("allowed_branches") or []) if str(b).strip()]
        has_unrestricted = bool(user_scope.get("has_unrestricted_team_access"))
        user_role = str(user_scope.get("role") or user_scope.get("db_role") or "")
        is_branch_restricted = bool(
            user_role == "Branch Director"
            or user_scope.get("is_branch_restricted")
            or (accessible_branches and not has_unrestricted and user_role not in ("Regional Manager", "General Manager", "Admin", "Super Admin"))
        )

        # NEVER fall back to unfiltered repo when scoped history is empty!
        # Filter by period boundary: actions created/dated after requested period are excluded.
        filtered = []
        for item in (history or []):
            if not _is_action_prior_to_period(item, requested_month, requested_year):
                continue

            # Branch scope check for branch-restricted user: fail closed on missing/ambiguous/unauthorized
            if is_branch_restricted:
                branch, is_ambiguous = _resolve_action_branch(item, self.corrective_action_service)
                if is_ambiguous or not branch or not any(b == branch.casefold() for b in accessible_branches):
                    continue

            filtered.append(_sanitize_prior_action(item))
        return filtered

    def _prior_actions_for_team(
        self,
        team_name: str,
        scope: dict | None,
        requested_month: str,
        requested_year: int,
    ) -> list[dict[str, Any]]:
        """Prior actions for a team, strictly scope-enforced and period-bounded."""
        team_rows = (
            self.db.query(Team)
            .filter(
                Team.display_name.ilike(team_name)
                | Team.name.ilike(team_name)
                | Team.db_name.ilike(team_name)
            )
            .all()
        )
        if not team_rows:
            return []
        team_by_id = {t.id: t for t in team_rows}

        rows: list[Any] = []
        seen_row_ids: set[Any] = set()
        for t in team_rows:
            for r in self.action_repository.get_by_team(t.id) or []:
                key = getattr(r, "id", id(r))
                if key is None:
                    key = id(r)
                if key in seen_row_ids:
                    continue
                seen_row_ids.add(key)
                rows.append(r)

        user_scope = scope if isinstance(scope, dict) else {}
        accessible_branches = [b.casefold() for b in (user_scope.get("accessible_branches") or user_scope.get("allowed_branches") or []) if str(b).strip()]
        accessible_regions = [r.casefold() for r in (user_scope.get("accessible_regions") or []) if str(r).strip()]
        has_unrestricted = bool(user_scope.get("has_unrestricted_team_access"))
        user_role = str(user_scope.get("role") or user_scope.get("db_role") or "")
        is_branch_restricted = bool(
            user_role == "Branch Director"
            or user_scope.get("is_branch_restricted")
            or (accessible_branches and not has_unrestricted and user_role not in ("Regional Manager", "General Manager", "Admin", "Super Admin"))
        )

        filtered = []
        for row in rows:
            if getattr(row, "is_active", True) is False:
                continue

            ev_ref = str(getattr(row, "evidence_reference", "") or "")
            if ev_ref.startswith("cohort-plan:") and not getattr(row, "linked_kpi_key", None):
                continue

            # Period boundary check
            if not _is_action_prior_to_period(row, requested_month, requested_year):
                continue

            # Branch scope check: user restricted to specific branches cannot see other branches
            # Fail closed on missing, ambiguous, or unauthorized branch attribution
            if is_branch_restricted:
                branch, is_ambiguous = _resolve_action_branch(row, self.corrective_action_service)
                if is_ambiguous or not branch or not any(b == branch.casefold() for b in accessible_branches):
                    continue

            row_team = getattr(row, "team", None) or team_by_id.get(getattr(row, "team_id", None))

            # Regional scope check: user restricted to specific regions cannot see other regions
            if accessible_regions and not has_unrestricted:
                perf_rec = self.corrective_action_service._performance_record_for_action(row)
                rec_region = getattr(perf_rec, "region", None) if perf_rec else None
                act_region = (
                    rec_region
                    or getattr(getattr(row, "employee", None), "region", None)
                    or getattr(row_team, "region", None)
                    or ""
                )
                if act_region and act_region.casefold() not in accessible_regions:
                    continue

            # Team level scope check
            emp = getattr(row, "employee", None)
            if emp is not None:
                level = getattr(emp, "performance_level", "Employee") or "Employee"
            else:
                level = "Management" if getattr(row_team, "team_level", None) == "management" else "Employee"
            if not user_can_access_team_level(user_scope, team_name, level):
                continue

            filtered.append(_sanitize_prior_action(row))
        return filtered


def build_corrective_action_evidence(
    db: Session,
    *,
    user_scope: dict,
    employee_id: str | None = None,
    team: str,
    month: str,
    year: int,
    performance_level: str = "Employee",
    linked_kpi_key: str | None = None,
) -> dict[str, Any]:
    """Module-level convenience wrapper around :class:`CorrectiveActionEvidenceService`."""
    return CorrectiveActionEvidenceService(db).build(
        user_scope=user_scope,
        employee_id=employee_id,
        team=team,
        month=month,
        year=year,
        performance_level=performance_level,
        linked_kpi_key=linked_kpi_key,
    )
