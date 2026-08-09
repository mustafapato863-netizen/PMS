from __future__ import annotations

import math
from typing import Any, Mapping


LEGACY_EMPLOYEE_TEAMS = {
    "Inbound",
    "Outbound",
    "Inbound UAE",
    "Pre-Approvals IP Offshore",
    "Sales",
}

PRE_APPROVALS_IP_ELECTIVE_TEAM = "Pre-Approvals IP Elective Dubai"


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.replace("%", "").replace(",", "").strip()
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _first(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _number(row.get(key))
        if value is not None:
            return value
    return None


def _weight(weights: Mapping[str, float], key: str) -> float:
    normalized_weights = {str(name).casefold(): value for name, value in weights.items()}
    aliases = {
        "Attendance": ("Attendance", "Attend"),
        "Booking": ("Booking",),
        "Quality": ("Quality",),
        "AHT": ("AHT",),
        "Other": ("Other",),
        "Rejection": ("Rejection",),
        "InitialError": ("InitialError",),
        "Submission": ("Submission",),
        "OPCensus": ("OPCensus",),
        "OPRevenue": ("OPRevenue",),
        "IPCensus": ("IPCensus",),
        "IPRevenue": ("IPRevenue",),
        "Activity": ("Activity",),
    }
    for alias in aliases.get(key, (key,)):
        value = _number(normalized_weights.get(alias.casefold()))
        if value is not None:
            return max(value, 0.0)
    return 0.0


def _target(actual: float, achievement: float, direction: str, fallback: float) -> float:
    if achievement > 0:
        if direction == "lower_better":
            if actual > 0:
                return round(actual * achievement, 6)
        else:
            return round(actual / achievement, 6)
    return fallback


def _rate(value: Any, fallback: float = 0.0) -> float:
    parsed = _number(value)
    if parsed is None:
        return fallback
    return parsed / 100.0 if parsed > 1.0 else parsed


def _normalized_text(value: Any) -> str:
    return "".join(char.lower() for char in str(value or "") if char.isalnum())


def _first_normalized(row: Mapping[str, Any], *keys: str) -> float | None:
    direct = _first(row, *keys)
    if direct is not None:
        return direct
    candidates = {_normalized_text(key) for key in keys}
    for key, value in row.items():
        if _normalized_text(key) in candidates:
            parsed = _number(value)
            if parsed is not None:
                return parsed
    return None


def _pre_approvals_workstream(row: Mapping[str, Any], config: Mapping[str, Any] | None) -> str:
    configured_position = _normalized_text((config or {}).get("position_name"))
    if "eripapproval" in configured_position or ("er" in configured_position and "approval" in configured_position):
        return "ER / IP Approval"
    if "ipelective" in configured_position:
        return "IP Elective"

    for kpi in (config or {}).get("kpis", []):
        key = _normalized_text(kpi.get("key"))
        if key in {"erinitialrejectionrate", "approvalwithin15hours"}:
            return "ER / IP Approval"
        if key in {"ipinitialrejectionrate", "approvalwithin48hours"}:
            return "IP Elective"

    turnaround_target = _first_normalized(row, "T.%OfApprovalwithin48HR/1.5HR", "T.%OfApprovalwithin48HR1.5HR")
    if turnaround_target is not None:
        return "ER / IP Approval" if _rate(turnaround_target) >= 0.95 else "IP Elective"

    # The cleaner emits only the selected turnaround numerator for each row.
    if _first_normalized(row, "ApprovalWithin1.5HR", "ApprovalWithin1.5Hours") is not None:
        return "ER / IP Approval"
    return "IP Elective"


def _pre_approvals_definitions(
    workstream: str,
    config: Mapping[str, Any] | None,
) -> list[Mapping[str, Any]]:
    configured = list((config or {}).get("kpis", []))
    if configured:
        return configured
    positions = ((config or {}).get("performance_levels", {}).get("Employee", {}).get("positions", {}))
    return list(positions.get(workstream, {}).get("kpis", []))


def build_pre_approvals_ip_elective_kpi_values(
    row: Mapping[str, Any],
    *,
    weights: Mapping[str, float] | None = None,
    config: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Rebuild the two scoped KPIs from source volumes and target columns.

    This is intentionally independent of the persisted KPIValue rows. It
    repairs records imported before the two-position configuration existed,
    where old combined KPIs and an old evaluation score may still be stored.
    """
    workstream = _pre_approvals_workstream(row, config)
    definitions = _pre_approvals_definitions(workstream, config)
    if not definitions:
        return []

    assigned = _first_normalized(row, "AssignedRequests", "AssignedRequest")
    approved = _first_normalized(row, "ApprovedRequests", "ApprovedRequest")
    rejected = _first_normalized(row, "RejectedRequests", "RejectedRequest")
    within_48 = _first_normalized(row, "ApprovalWithin48HR", "ApprovalWithin48hrs")
    within_1_5 = _first_normalized(row, "ApprovalWithin1.5HR", "ApprovalWithin1.5Hours")
    if assigned is not None and assigned > 0 and rejected is not None:
        rejection_actual = rejected / assigned
    else:
        rejection_actual = None
    if approved is not None and approved > 0:
        turnaround_actual = (within_48 if workstream == "IP Elective" else within_1_5)
        turnaround_actual = turnaround_actual / approved if turnaround_actual is not None else None
    else:
        turnaround_actual = None

    normalized_weights = {_normalized_text(key): _number(value) or 0.0 for key, value in (weights or {}).items()}
    result: list[dict[str, Any]] = []
    for definition in definitions:
        key = str(definition.get("key"))
        is_rejection = "rejection" in key
        actual_col = str(definition.get("actual_col") or "")
        target_col = str(definition.get("target_col") or "")
        actual_source = _first_normalized(row, actual_col)
        target_source = _first_normalized(row, target_col)
        actual = _rate(actual_source) if actual_source is not None else (rejection_actual if is_rejection else turnaround_actual)
        fallback_target = 0.03 if is_rejection and workstream == "IP Elective" else 0.01 if is_rejection else 0.75 if workstream == "IP Elective" else 1.0
        if target_source is None:
            target_source = _first_normalized(
                row,
                "T.InitialRejection%" if is_rejection else "T.%OfApprovalwithin48HR/1.5HR",
                "T.InitialRejectionRate" if is_rejection else "T.%OfApprovalwithin48HR1.5HR",
            )
        target = _rate(target_source, fallback_target)
        actual = max(float(actual or 0.0), 0.0)
        achievement = (target / actual) if is_rejection and actual > 0 else 1.0 if is_rejection else (actual / target if target > 0 else 0.0)
        weight = normalized_weights.get(_normalized_text(key), _number(definition.get("weight")) or 0.0)
        result.append({
            "kpi_key": key,
            "label": definition.get("label", key),
            "perspective": definition.get("perspective"),
            "unit": definition.get("unit", "%"),
            "color": definition.get("color", "#3B82F6"),
            "direction": definition.get("direction", "higher_better"),
            "actual_value": actual,
            "target_value": target,
            "achievement_ratio": min(max(achievement, 0.0), 1.0),
            "weight_applied": max(weight, 0.0),
            "contribution": min(max(achievement, 0.0), 1.0) * max(weight, 0.0),
            "cap_achievement": True,
        })
    return result


def _sales_activity_totals(row: Mapping[str, Any]) -> tuple[float, float]:
    """Match the Sales cleaner's dynamic activity numerator/denominator."""
    activity_keys = ("ClinicActivity", "CorporateActivity", "CBDTour", "Visits")
    source_keys = [
        str(key).replace(" ", "")
        for key in row
        if any(keyword in str(key).replace(" ", "") for keyword in activity_keys)
        and "Ach%" not in str(key)
    ]
    actual_keys = [key for key in source_keys if key.startswith("A.")]
    target_keys = [key for key in source_keys if key.startswith("T.")]
    if actual_keys or target_keys:
        return (
            sum(_first(row, key) or 0.0 for key in actual_keys),
            sum(_first(row, key) or 0.0 for key in target_keys),
        )

    target_keys = [key for key in source_keys if not key.endswith((".1", ".2"))]
    actual_keys = [key for key in source_keys if key.endswith((".1", ".2"))]
    if len(actual_keys) != len(target_keys):
        halfway = len(source_keys) // 2
        target_keys, actual_keys = source_keys[:halfway], source_keys[halfway:]
    return (
        sum(_first(row, key) or 0.0 for key in actual_keys),
        sum(_first(row, key) or 0.0 for key in target_keys),
    )


def build_legacy_employee_kpi_values(
    team: str,
    row: Mapping[str, Any],
    *,
    achievements: Mapping[str, float] | None = None,
    weights: Mapping[str, float] | None = None,
    config: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build the canonical KPI evidence for legacy formula-based teams.

    These teams calculate their score from normalized source fields rather
    than directly from the static config columns. Persisting the static
    columns previously stored Excel time fractions and zero/mismatched
    targets. This builder is shared by ingestion and the compatibility read
    path so existing rows and future uploads expose the same evidence.
    """

    if team == PRE_APPROVALS_IP_ELECTIVE_TEAM:
        return build_pre_approvals_ip_elective_kpi_values(
            row,
            weights=weights,
            config=config,
        )

    if team not in LEGACY_EMPLOYEE_TEAMS:
        return []

    evidence_keys = {
        "Inbound": ("A.Attend%", "A.Booking%", "A.QualityScore", "AHT_Minutes", "A.UTZ%", "A.AbandonRate%"),
        "Outbound": ("A.Attend%", "A.Booking%", "A.QualityScore", "A.Reachability%"),
        "Inbound UAE": ("A.Attend%", "A.Booking%", "A.AbandonRate%"),
        "Pre-Approvals IP Offshore": ("IPInitialRejection%", "Error%", "NumberApprovalwithin48hrs"),
        "Sales": ("A.OPCensus", "A.OPRevenue", "A.IPCensus", "A.IPRevenue", "OPCensusAch%"),
    }
    if not any(_first(row, key) is not None for key in evidence_keys[team]):
        return []

    achievements = achievements or {}
    weights = weights or {}
    definitions = {
        str(item.get("key")): item
        for item in (config or {}).get("kpis", [])
        if item.get("key")
    }

    if team == "Inbound":
        has_utz = _first(row, "A.UTZ%", "UTZ%") is not None
        specs = [
            ("Attendance", "Attendance Rate", "higher_better", _first(row, "A.Attend%"), _first(row, "Attend%Ach%"), 0.75),
            ("Booking", "Booking Rate", "higher_better", _first(row, "A.Booking%"), _first(row, "Booking%Ach%"), 0.45),
            ("Quality", "Quality Score", "higher_better", _first(row, "A.QualityScore"), _first(row, "QualityTargetAch%"), 0.95),
            ("AHT", "AHT (Handle Time)", "lower_better", _first(row, "AHT_Minutes"), _first(row, "AHTAch%"), 2.5),
            (
                "Other",
                "Utilization" if has_utz else "Abandon Rate",
                "higher_better" if has_utz else "lower_better",
                _first(row, "A.UTZ%", "UTZ%") if has_utz else _first(row, "A.AbandonRate%"),
                _first(row, "UTZ%Ach%") if has_utz else _first(row, "AbandonRate%Ach%"),
                0.85 if has_utz else 0.01,
            ),
        ]
    elif team == "Outbound":
        specs = [
            ("Attendance", "Attendance Rate", "higher_better", _first(row, "A.Attend%"), _first(row, "AttendC.RAch%", "Attend%Ach%"), 0.55),
            ("Booking", "Booking Rate", "higher_better", _first(row, "A.Booking%"), _first(row, "BookingC.RAch%", "Booking%Ach%"), 0.46),
            ("Quality", "Quality Score", "higher_better", _first(row, "A.QualityScore"), _first(row, "QualityAch%", "QualityTargetAch%"), 0.95),
            ("Other", "Reachability", "higher_better", _first(row, "A.Reachability%"), _first(row, "Reachability%Ach%"), 0.75),
        ]
    elif team == "Inbound UAE":
        specs = [
            ("Attendance", "Attendance Rate", "higher_better", _first(row, "A.Attend%"), _first(row, "AttendC.RAch%", "Attend%Ach%"), 0.75),
            ("Booking", "Booking Rate", "higher_better", _first(row, "A.Booking%"), _first(row, "BookingC.RAch%", "Booking%Ach%"), 0.60),
            ("Other", "Abandon Rate", "lower_better", _first(row, "A.AbandonRate%"), _first(row, "AbandonRateAch%", "AbandonRate%Ach%"), 0.01),
        ]
    elif team == "Sales":
        activity_actual, activity_target = _sales_activity_totals(row)
        specs = [
            ("OPCensus", "OP Census Ach", "higher_better", _first(row, "A.OPCensus"), _first(row, "OPCensusAch%"), _first(row, "T.OPCensus") or 1.0),
            ("OPRevenue", "OP Revenue Ach", "higher_better", _first(row, "A.OPRevenue"), _first(row, "OPRevenueAch%"), _first(row, "T.OPRevenue") or 1.0),
            ("IPCensus", "IP Census Ach", "higher_better", _first(row, "A.IPCensus"), _first(row, "IPCensusAch%"), _first(row, "T.IPCensus") or 1.0),
            ("IPRevenue", "IP Revenue Ach", "higher_better", _first(row, "A.IPRevenue"), _first(row, "IPRevenueAch%"), _first(row, "T.IPRevenue") or 1.0),
            ("Activity", "Activity Score", "higher_better", activity_actual, _first(row, "ActivityAch%", "SalesActivtiesAch%", "SalesActivitiesAch%"), activity_target or 1.0),
        ]
    else:
        specs = [
            ("Rejection", "Rejection Rate", "lower_better", _first(row, "IPInitialRejection%"), _first(row, "RejectionRate"), 0.03),
            ("InitialError", "Initial Error Rate", "lower_better", _first(row, "Error%"), _first(row, "InitialError%"), 0.03),
            ("Submission", "Submission Rate", "higher_better", _first(row, "NumberApprovalwithin48hrs"), _first(row, "%ofSubmissionWithinDuedate"), 0.90),
        ]

    result: list[dict[str, Any]] = []
    achievement_alias = {
        "Attendance": "Attend",
        "Booking": "Booking",
        "Quality": "Quality",
        "AHT": "AHT",
        "Other": "Other",
        "Rejection": "Rejection",
        "InitialError": "InitialError",
        "Submission": "Submission",
        "OPCensus": "OPCensus",
        "OPRevenue": "OPRevenue",
        "IPCensus": "IPCensus",
        "IPRevenue": "IPRevenue",
        "Activity": "Activity",
    }
    for key, label, direction, actual_value, row_achievement, fallback_target in specs:
        actual = max(actual_value or 0.0, 0.0)
        supplied_achievement = _number(achievements.get(achievement_alias[key]))
        achievement = max(supplied_achievement if supplied_achievement is not None else (row_achievement or 0.0), 0.0)
        weight = _weight(weights, key)
        definition = definitions.get(key, {})
        explicit_target = _first(row, f"T.{key}%", f"T.{key} %", f"T.{key}", f"Target_{key}")
        if explicit_target is not None and explicit_target > 0:
            if key in ("AHT", "WaitingTime") and 0 < explicit_target < 1.0:
                target = round(explicit_target * 1440.0, 4)
            else:
                target = explicit_target
        else:
            target = _target(actual, achievement, direction, fallback_target)

        # Recalculate achievement ratio dynamically from actual and target for 100% precision
        if target > 0 and actual >= 0:
            if direction == "lower_better":
                raw_ach = (target / actual) if actual > 0 else 1.0
            else:
                raw_ach = (actual / target)
            achievement = round(min(max(raw_ach, 0.0), 1.0), 4)
        result.append({
            "kpi_key": key,
            "label": label,
            "perspective": definition.get("perspective"),
            "unit": definition.get("unit", "%" if key != "AHT" else "min"),
            "color": definition.get("color", "#3B82F6"),
            "direction": direction,
            "actual_value": actual,
            "target_value": target,
            "achievement_ratio": achievement,
            "weight_applied": weight,
            "contribution": min(achievement, 1.0) * weight,
            "cap_achievement": True,
        })
    return result
