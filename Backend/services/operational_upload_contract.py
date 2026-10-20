"""Operational Inbound and Outbound upload contract.

Ordinary upload scoring and new evaluation drafts use this module. A row date
selects only the June 2026 weight exception already in the cleaners. It does
not select the reference workbook's July or August KPI set, targets, per-KPI
cap, or Productivity.

The reference workbook stays on ``canonical_outbound_basis`` /
``period_capability`` and is applied only when a snapshot's contract is
``reference_workbook`` (or a legacy reference snapshot with no contract tag).
"""

from __future__ import annotations

import datetime
import math
from decimal import Decimal
from typing import Any, Mapping

from config.loader import load_team_config
from services.evaluation.periods import MONTHS, PeriodError, month_number

OPERATIONAL_CONTRACT = "operational_upload"
REFERENCE_CONTRACT = "reference_workbook"
FINAL_TOTAL_CAP = "final_total"

_OUTBOUND_KEYS = ("Attendance", "Booking", "Quality", "Other")
_INBOUND_KEYS = ("Attendance", "Booking", "Quality", "AHT", "Other")


def period_numbers(year, month) -> tuple[int | None, int | None]:
    try:
        year_number = None if year is None or year == "" else int(year)
    except (TypeError, ValueError):
        year_number = None
    try:
        month_value = None if month is None or month == "" else month_number(month)
    except (PeriodError, TypeError, ValueError):
        month_value = None
    return year_number, month_value


def is_june_2026(year, month) -> bool:
    year_number, month_value = period_numbers(year, month)
    return year_number == 2026 and month_value == 6


def is_operational_team(team_name: str, level: str, position: str | None) -> bool:
    folded = str(team_name or "").casefold().replace(" ", "").replace("_", "").replace("-", "")
    return folded in {"inbound", "outbound"} and str(level or "") == "Employee" and (position or "") == ""


def operational_team_kind(team_name: str) -> str | None:
    folded = str(team_name or "").casefold().replace(" ", "").replace("_", "").replace("-", "")
    if folded == "inbound":
        return "Inbound"
    if folded == "outbound":
        return "Outbound"
    return None


def _configured_kpis(team: str) -> list[dict]:
    config = load_team_config(team)
    return [dict(kpi) for kpi in (config.get("kpis") or []) if kpi.get("key")]


def _weight_for(kpi: Mapping[str, Any], overrides: Mapping[str, float]) -> float:
    key = str(kpi.get("key") or "")
    if key in overrides:
        return float(overrides[key])
    return float(kpi.get("weight") or 0)


def operational_lines(team: str, year, month) -> list[dict] | None:
    """Checked-in labels and the operational weights for one exact period.

    Targets stay workbook-owned. Productivity is not added. June 2026 applies
    the cleaner weight exception and nothing else.
    """
    kind = operational_team_kind(team)
    year_number, month_value = period_numbers(year, month)
    if kind is None or year_number is None or month_value is None:
        return None
    kpis = _configured_kpis(kind)
    overrides: dict[str, float] = {}
    if is_june_2026(year_number, month_value):
        if kind == "Outbound":
            overrides = {"Quality": 0.0, "Other": 0.20}
        else:
            overrides = {"Quality": 0.0, "Other": 0.15}
    lines = []
    for kpi in kpis:
        key = str(kpi.get("key") or "")
        if kind == "Outbound" and key not in _OUTBOUND_KEYS:
            continue
        if kind == "Inbound" and key not in _INBOUND_KEYS:
            continue
        line = {
            "kpi_key": key,
            "label": kpi.get("label") or key,
            "weight": _weight_for(kpi, overrides),
            "direction": kpi.get("direction"),
            "target": None,
            "target_mode": "workbook",
            "unit": kpi.get("unit") or "%",
            "cap_each": True,
        }
        if kind == "Inbound" and key == "Other":
            line["row_selection"] = "utz_or_abandon"
        lines.append(line)
    return lines


def operational_period_status(team: str, year, month) -> str:
    if is_june_2026(year, month):
        return "june_2026_exception"
    return "operational_upload"


def operational_mapped_keys(lines: list[dict] | None) -> list[str]:
    """Contract identity, including a known KPI saved at weight zero for tracking."""
    found = []
    for line in lines or []:
        key = str(line.get("kpi_key") or "")
        if key and key not in found:
            found.append(key)
    return found


def operational_scored_keys(lines: list[dict] | None) -> list[str]:
    """Default positive weights. Not the set Admin must keep positive."""
    found = []
    for line in lines or []:
        try:
            weight = float(line.get("weight") or 0)
        except (TypeError, ValueError):
            continue
        key = str(line.get("kpi_key") or "")
        if key and weight > 0:
            found.append(key)
    return found


def utz_supplied(raw: Mapping[str, Any] | None) -> bool:
    """True when the Inbound row has a UTZ cell, including a numeric zero."""
    if not isinstance(raw, dict):
        return False
    value = None
    if "A.UTZ%" in raw:
        value = raw.get("A.UTZ%")
    else:
        for key, item in raw.items():
            folded = "".join(char for char in str(key) if not char.isspace()).casefold()
            if folded in {"a.utz%", "utz%"}:
                value = item
                break
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return True
    return math.isfinite(number)


def other_direction_for_row(raw: Mapping[str, Any] | None, line: Mapping[str, Any]) -> str:
    if str(line.get("row_selection") or "") == "utz_or_abandon" and utz_supplied(raw):
        return "higher_better"
    return str(line.get("direction") or "")


def operational_achievement(actual: float, target: float, direction: str, *, kpi_key: str) -> float:
    """Same raw ratios as ``KPIService`` for these teams; weighted shares are capped.

    AHT at zero minutes is an achievement of zero, matching the upload service.
    Abandon (lower-is-better, not AHT) stays at 1 when the actual beats the target,
    which is the upload service's inverse branch.     Higher-is-better ratios may exceed 1, but they cannot earn more than their
    configured weight in ``score_operational_lines``.
    """
    if target <= 0:
        return 0.0
    if kpi_key == "AHT":
        if actual <= 0:
            return 0.0
        return float(target) / float(actual)
    if direction == "lower_better":
        if actual <= target:
            return 1.0
        if actual <= 0:
            return 1.0
        return float(target) / float(actual)
    if actual <= 0:
        return 0.0
    return float(actual) / float(target)


def _finite(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except Exception:
        return None
    if not number.is_finite():
        return None
    return number


def score_operational_lines(lines: list[dict], rows: list[dict]) -> list[dict]:
    """Score stored actuals with the operational ratios.

    A missing weighted actual is an error that names the KPI. A numeric zero
    stays zero. A zero-weight line with no actual stays visible as unavailable
    and is not filled with zero. A present Outbound Productivity actual is a
    known monitoring row: weight 0, contribution 0, and the scored weights stay
    as approved. Any other key outside the contract is rejected.
    """
    from services.evaluation.access import EvaluationError
    from services.evaluation.scoring import SUPPORTED_DIRECTIONS, _missing_actual, _require_json_finite

    if not isinstance(lines, list) or not isinstance(rows, list):
        raise EvaluationError("Scoring evidence must list the approved contract and the input rows.", code="incomplete_evidence")
    by_key: dict[str, dict] = {}
    for line in lines:
        key = str(line.get("kpi_key") or "")
        if not key or key in by_key:
            raise EvaluationError("The approved contract has a blank or duplicate KPI key.", code="duplicate_kpi")
        weight = _finite(line.get("weight"))
        if weight is None or weight < 0:
            raise EvaluationError(f"Weight for {key} must be zero or greater.", code="nonfinite_evidence")
        direction = str(line.get("direction") or "")
        if direction not in SUPPORTED_DIRECTIONS:
            raise EvaluationError(f"{key} direction is not supported.", code="unsupported_direction", kpi_key=key)
        by_key[key] = line
    monitoring_allowed = set(by_key) == set(_OUTBOUND_KEYS)
    provided: dict[str, dict] = {}
    monitoring: list[dict] = []
    for row in rows:
        key = str(row.get("kpi_key") or "")
        if not key or key in provided or any(str(item.get("kpi_key") or "") == key for item in monitoring):
            raise EvaluationError("Scoring input has a blank or duplicate KPI key.", code="duplicate_kpi", kpi_key=key)
        if key not in by_key:
            if monitoring_allowed and key == "Productivity":
                monitoring.append(row)
                continue
            if monitoring_allowed and key == "Utilization":
                if not _missing_actual(row.get("actual")):
                    attend_line = dict(by_key.get("Attendance") or {})
                    attend_weight = float(attend_line.get("weight") or 0)
                    utz_weight = 0.10
                    if attend_weight >= utz_weight:
                        attend_line["weight"] = round(attend_weight - utz_weight, 4)
                        by_key["Attendance"] = attend_line
                    by_key["Utilization"] = {
                        "kpi_key": "Utilization",
                        "label": "Utilization",
                        "weight": utz_weight,
                        "direction": "higher_better",
                        "target": 0.80,
                        "target_mode": "workbook",
                        "unit": "%",
                        "cap_each": True,
                    }
                    provided[key] = row
                continue
            raise EvaluationError(
                f"{key} is not in the approved contract. Unknown rows are not treated as diagnostics.",
                code="unknown_kpi",
                kpi_key=key,
            )
        provided[key] = row
    missing = [
        key
        for key, line in by_key.items()
        if float(line.get("weight") or 0) > 0 and key not in provided
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
        weight = float(line.get("weight") or 0)
        direction = str(row.get("direction") or line.get("direction") or "")
        workbook = row.get("workbook_target")
        workbook_number = None if workbook in (None, "") else float(_finite(workbook) or 0)
        if line.get("target_mode") == "fixed" and line.get("target") not in (None, ""):
            target = float(line.get("target"))
        elif workbook not in (None, ""):
            target = float(workbook)
        elif line.get("target") not in (None, ""):
            target = float(line.get("target"))
        else:
            target = None
        if _missing_actual(row.get("actual")):
            if weight > 0:
                raise EvaluationError(
                    f"Actual for {key} is missing. A missing actual is not scored as zero.",
                    code="missing_actual",
                    kpi_key=key,
                )
            scored.append({
                "kpi_key": key,
                "label": line.get("label") or key,
                "actual": None,
                "target": target,
                "workbook_target": workbook_number,
                "weight": weight,
                "direction": direction,
                "target_mode": line.get("target_mode"),
                "achievement": None,
                "achievement_state": "missing_actual",
                "contribution": None,
                "ignored_precomputed_achievement": row.get("precomputed_achievement"),
            })
            continue
        actual = float(row.get("actual"))
        if target is None:
            if weight > 0:
                raise EvaluationError(
                    f"Target for {key} is missing.",
                    code="incomplete_evidence",
                    kpi_key=key,
                )
            achievement = None
            share = None
            state = "invalid_target"
        else:
            achievement = operational_achievement(actual, target, direction, kpi_key=key)
            from services.scoring.engine import contribution

            share = contribution(achievement, weight)
            state = "measured"
            _require_json_finite(achievement, f"Achievement for {key}")
            _require_json_finite(share, f"Contribution for {key}")
        scored.append({
            "kpi_key": key,
            "label": line.get("label") or key,
            "actual": actual,
            "target": target,
            "workbook_target": workbook_number,
            "weight": weight,
            "direction": direction,
            "target_mode": line.get("target_mode"),
            "achievement": achievement,
            "achievement_state": state,
            "contribution": share,
            "ignored_precomputed_achievement": row.get("precomputed_achievement"),
        })
    for row in monitoring:
        scored.append(_monitoring_productivity(row))
    return scored


def _monitoring_productivity(row: dict) -> dict:
    """One present Outbound Productivity actual. It never takes score weight."""
    from services.evaluation.scoring import _missing_actual, _require_json_finite

    workbook = row.get("workbook_target")
    workbook_number = None if workbook in (None, "") else float(_finite(workbook) or 0)
    if workbook not in (None, ""):
        target = float(workbook)
    else:
        target = None
    if _missing_actual(row.get("actual")):
        return {
            "kpi_key": "Productivity",
            "label": "Productivity",
            "actual": None,
            "target": target,
            "workbook_target": workbook_number,
            "weight": 0.0,
            "direction": "higher_better",
            "target_mode": "workbook",
            "achievement": None,
            "achievement_state": "missing_actual",
            "contribution": None,
            "ignored_precomputed_achievement": row.get("precomputed_achievement"),
        }
    actual = float(row.get("actual"))
    if target is None:
        achievement = None
        state = "invalid_target"
    else:
        achievement = operational_achievement(actual, target, "higher_better", kpi_key="Productivity")
        state = "measured"
        _require_json_finite(achievement, "Achievement for Productivity")
    return {
        "kpi_key": "Productivity",
        "label": "Productivity",
        "actual": actual,
        "target": target,
        "workbook_target": workbook_number,
        "weight": 0.0,
        "direction": "higher_better",
        "target_mode": "workbook",
        "achievement": achievement,
        "achievement_state": state,
        "contribution": 0.0,
        "ignored_precomputed_achievement": row.get("precomputed_achievement"),
    }


def final_total_score(scored: list[dict]) -> float | None:
    """Sum per-KPI capped shares and cap the total. Same rounding as upload scoring."""
    if not scored:
        return None
    total = 0.0
    seen = False
    for row in scored:
        share = row.get("contribution")
        if share is None:
            continue
        total += float(share)
        seen = True
    if not seen:
        return None
    return float(round(min(max(total, 0.0), 1.0) * 100.0, 2))


def snapshot_contract(snapshot: Mapping[str, Any] | None) -> str | None:
    if not isinstance(snapshot, dict):
        return None
    contract = snapshot.get("contract")
    if contract in {OPERATIONAL_CONTRACT, REFERENCE_CONTRACT}:
        return str(contract)
    return None


def legacy_reference_snapshot(snapshot: Mapping[str, Any] | None, team_name: str) -> bool:
    """Approved rows saved before contract tags stay on the reference formula."""
    if snapshot_contract(snapshot) == OPERATIONAL_CONTRACT:
        return False
    if snapshot_contract(snapshot) == REFERENCE_CONTRACT:
        return True
    if not isinstance(snapshot, dict):
        return False
    if operational_team_kind(team_name) is None:
        return False
    policy = str(snapshot.get("policy") or "employee_ratio")
    if policy != "employee_ratio":
        return False
    lines = snapshot.get("lines") if isinstance(snapshot.get("lines"), list) else []
    for line in lines:
        if str(line.get("kpi_key") or "") == "Productivity" and float(line.get("weight") or 0) > 0:
            return True
    status = str(snapshot.get("period_status") or "")
    return status in {"july_2026", "august_2026"}


def revision_choice(team_name: str, level: str, position: str | None, snapshot: Mapping[str, Any] | None) -> dict | None:
    """Visible Admin choice. Reading it does not change the stored snapshot."""
    if not is_operational_team(team_name, level, position):
        return None
    if snapshot_contract(snapshot) == OPERATIONAL_CONTRACT:
        return {
            "available": False,
            "contract": OPERATIONAL_CONTRACT,
            "code": None,
            "message": "This version uses the operational upload contract.",
        }
    return {
        "available": True,
        "contract": REFERENCE_CONTRACT,
        "code": "adopt_operational_upload",
        "message": (
            "This version uses the reference workbook contract and was not changed. "
            "Admin can adopt the operational upload contract explicitly."
        ),
    }


def month_label(month: int | None) -> str | None:
    if month is None or not 1 <= int(month) <= 12:
        return None
    return MONTHS[int(month) - 1]


def coerce_date(value: Any) -> datetime.date | None:
    if value is None or isinstance(value, datetime.time):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return None
