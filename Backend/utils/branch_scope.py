"""Canonical branch parsing for access control.

Only explicit source fields are authorization evidence. Booking/attendance geo
totals are deliberately excluded because a single employee can have activity
in more than one branch while the score row itself is not branch-partitioned.
"""

from __future__ import annotations

import re
from typing import Any


BRANCH_KEYS = ("dubai", "sharjah", "ajman", "clinics")
REGION_CODES = ("UAE", "EGY", "Other")

_ALIASES = {
    "dubai": ("DUBAI", "DXB"),
    "sharjah": ("SHARJAH", "SHARQA", "SHJ"),
    "ajman": ("AJMAN", "AJM"),
    "clinics": ("CLINIC", "CLINICS"),
}


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _raw_data(record: Any) -> dict[str, Any]:
    raw = _value(record, "raw_data")
    if isinstance(raw, dict):
        return raw
    payload = _value(record, "record_payload")
    if isinstance(payload, dict) and isinstance(payload.get("raw_data"), dict):
        return payload["raw_data"]
    return {}


def explicit_branch_key(record: Any) -> str | None:
    """Return a unique branch explicitly named in source fields, else ``None``.

    There is intentionally no fallback to region, team assignments, or geo
    activity. Multiple branch markers make a row ambiguous and fail closed.
    """

    raw = _raw_data(record)
    source_values = [
        raw.get("Branch"),
        raw.get("Site"),
        raw.get("Area"),
        raw.get("Out Team"),
        raw.get("Team"),
    ]
    text = " ".join(str(value or "").upper() for value in source_values)
    matches = {
        branch
        for branch, aliases in _ALIASES.items()
        if any(re.search(rf"(?<![A-Z0-9]){re.escape(alias)}(?![A-Z0-9])", text) for alias in aliases)
    }
    return next(iter(matches)) if len(matches) == 1 else None


_TEXT_BRANCH_FIELDS = ("Team", "Out Team", "Branch", "Site", "Area")


def _positive(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def text_branch(record: Any) -> str | None:
    """Branch named by the source text of a record, in the fixed server order.

    Raw Team, Out Team, Branch, Site and Area are read first. The team name only
    contributes Dubai, and only when the raw text names no other branch. A row
    that names several branches resolves to the first match in this order.
    """

    raw = _raw_data(record)
    branch_text = " ".join(str(raw.get(field) or "") for field in _TEXT_BRANCH_FIELDS).upper()
    team_text = str(_value(record, "team") or "").upper()
    if "AJM" in branch_text or "AJMAN" in branch_text:
        return "ajman"
    if "SHJ" in branch_text or "SHARJAH" in branch_text or "SHARQA" in branch_text:
        return "sharjah"
    if "DUBAI" in branch_text or "DUBAI" in team_text:
        return "dubai"
    if "CLINIC" in branch_text:
        return "clinics"
    return None


def record_matches_branch(record: Any, branch: str | None) -> bool:
    """The one branch rule for summaries, team breakdowns, basis rows and record pages.

    A stored ``branch_key`` decides when present; ingest writes it from the same
    source text. Otherwise the text rule above decides, and geo bookings or
    attendance for the branch decide when the text names no branch.
    """

    wanted = str(branch or "").strip().casefold()
    if not wanted or wanted == "all":
        return True
    stored = str(_value(record, "branch_key") or "").strip().casefold()
    if stored:
        return stored == wanted
    explicit = text_branch(record)
    if explicit:
        return explicit == wanted
    geo = _value(record, "geo")
    if geo is None:
        return False
    return any(_positive(_value(_value(geo, name), wanted)) for name in ("bookings", "attended"))


def _finite_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        n = float(value)
        return n if n == n else None
    except (TypeError, ValueError):
        return None


def project_record_for_branch(record: Any, branch: str | None) -> Any:
    """Project a record to a specific branch if it contains branch-partitioned geo data.

    For Call Center teams (Outbound, Inbound, etc.) where agents handle calls across
    all UAE branches, attendance is tracked per branch in `geo.bookings` and `geo.attended`.
    When a specific branch is selected, this projects the Attendance Rate KPI to the branch-specific
    ratio (attended[branch] / bookings[branch]), recalculates achievement ratio and contribution,
    and updates the overall evaluation score. For records without branch-partitioned geo activity,
    the record is returned unchanged.
    """
    wanted = str(branch or "").strip().casefold()
    if not wanted or wanted == "all" or wanted not in BRANCH_KEYS:
        return record

    geo = _value(record, "geo")
    if geo is None:
        return record

    bookings_obj = _value(geo, "bookings")
    attended_obj = _value(geo, "attended")
    if bookings_obj is None and attended_obj is None:
        return record

    b_bookings = _finite_float(_value(bookings_obj, wanted))
    b_attended = _finite_float(_value(attended_obj, wanted))
    if b_bookings is None and b_attended is None:
        return record

    bookings_val = max(b_bookings or 0.0, 0.0)
    attended_val = max(b_attended or 0.0, 0.0)
    new_actual = (attended_val / bookings_val) if bookings_val > 0 else 0.0

    if hasattr(record, "model_copy"):
        cloned = record.model_copy(deep=True)
    else:
        import copy
        cloned = copy.deepcopy(record)

    kpi_values = _value(cloned, "kpi_values")
    if isinstance(kpi_values, list):
        for kpi in kpi_values:
            kpi_key = str(_value(kpi, "kpi_key", "")).casefold()
            label = str(_value(kpi, "label", "")).casefold()
            if kpi_key == "attendance" or "attend" in label or "attend" in kpi_key:
                target = _finite_float(_value(kpi, "target_value")) or 0.65
                ratio = (new_actual / target) if target > 0 else 1.0
                weight = _finite_float(_value(kpi, "weight_applied")) or 0.7
                contribution = ratio * weight
                if isinstance(kpi, dict):
                    kpi["actual_value"] = new_actual
                    kpi["achievement_ratio"] = ratio
                    kpi["contribution"] = contribution
                else:
                    if hasattr(kpi, "actual_value"):
                        kpi.actual_value = new_actual
                    if hasattr(kpi, "achievement_ratio"):
                        kpi.achievement_ratio = ratio
                    if hasattr(kpi, "contribution"):
                        kpi.contribution = contribution

        total_contribution = 0.0
        for kpi in kpi_values:
            c = _finite_float(_value(kpi, "contribution"))
            if c is not None:
                total_contribution += c
        new_score = round(total_contribution * 100, 2)

        eval_obj = _value(cloned, "evaluation")
        if eval_obj is not None:
            if isinstance(eval_obj, dict):
                eval_obj["score"] = new_score
            elif hasattr(eval_obj, "score"):
                eval_obj.score = new_score

        if hasattr(cloned, "score"):
            try:
                cloned.score = new_score
            except Exception:
                pass

    if hasattr(cloned, "branch_key"):
        try:
            cloned.branch_key = wanted
        except Exception:
            pass
    elif isinstance(cloned, dict):
        cloned["branch_key"] = wanted

    raw = _value(cloned, "raw_data")
    if isinstance(raw, dict):
        if "A.Attend%" in raw:
            raw["A.Attend%"] = new_actual
        if "PerformanceScore" in raw:
            raw["PerformanceScore"] = new_score

    return cloned
