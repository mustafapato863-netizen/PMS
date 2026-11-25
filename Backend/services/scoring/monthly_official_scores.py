"""Authoritative server-owned Monthly Review official scoring and measure resolution.

Ports the Monthly Review scoring rules (``teamKpiAggregator.ts``,
``teamDeepDiveData.ts``, ``callCenterDeepDiveData.ts``, ``kpiScore.ts``,
``types.ts``) into pure Python so chat, Monthly Review, and rankings share
one server-computed result per scope, region, level, period, and measure
without spawning Vite/Node during requests.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable, Literal, Mapping, Sequence

from config.loader import ConfigurationError, load_team_config
from services.clinical_trend_import import TEAMS as CLINICAL_TREND_TEAMS
from services.evaluation.cache_identity import evaluation_cache_identity
from services.performance_dashboard_read_service import _has_real_activity
from services.uae_published_scores import uses_published_score
from utils.scoring_rules import score_percent
from utils.team_identity import dedupe_egypt_resubmission_records, is_egypt_resubmission_team

ScoreMeasure = Literal["official", "employee_average"]

HOSSAM_EMPLOYEE_ID = "SGHD70094"
_PRE_AUG_MONTHS = frozenset({"jan", "feb", "mar", "apr", "may", "jun", "jul"})

_INBOUND_BOOKING_GROUPS: tuple[tuple[str, ...], ...] = (
    ("Dubai_Booking", "Dubai _Booking"),
    ("Sharjah_Booking", "Sharjah_Booking "),
    ("Ajman_Booking", "Ajman_Booking "),
    ("Clinics_Booking", "Clinics _Booking", "clinics_Booking", "clinics.Booking"),
)

_OUTBOUND_UTZ_DEF: dict[str, Any] = {
    "key": "Utilization",
    "label": "Utilization",
    "weight": 0.10,
    "direction": "higher_better",
    "unit": "%",
    "color": "#6366F1",
    "actual_col": "A.Utilization%",
    "target_col": "T.Utilization%",
    "score_formula": "target_ratio",
    "cap_achievement": True,
    "aggregation": {"method": "average"},
}

_PRE_APPROVALS_WORKSTREAMS: dict[str, list[dict[str, Any]]] = {
    "ip": [
        {
            "key": "ip_initial_rejection_rate",
            "label": "IP Initial Rejection %",
            "direction": "lower_better",
            "weight": 0.6,
            "actual_keys": ("A.IPInitialRejectionRate",),
            "target_keys": ("T.IPInitialRejectionRate",),
            "fallback_target": 0.03,
        },
        {
            "key": "approval_within_48_hours",
            "label": "Approval Within 48 Hours %",
            "direction": "higher_better",
            "weight": 0.4,
            "actual_keys": ("A.ApprovalWithin48HoursRate",),
            "target_keys": ("T.ApprovalWithin48HoursRate",),
            "fallback_target": 0.75,
        },
    ],
    "er": [
        {
            "key": "er_initial_rejection_rate",
            "label": "ER Initial Rejection %",
            "direction": "lower_better",
            "weight": 0.6,
            "actual_keys": ("A.ERInitialRejectionRate",),
            "target_keys": ("T.ERInitialRejectionRate",),
            "fallback_target": 0.01,
        },
        {
            "key": "approval_within_1_5_hours",
            "label": "Approval Within 1.5 Hours %",
            "direction": "higher_better",
            "weight": 0.4,
            "actual_keys": ("A.ApprovalWithin1.5HoursRate",),
            "target_keys": ("T.ApprovalWithin1.5HoursRate",),
            "fallback_target": 1.0,
        },
    ],
}


@dataclass(frozen=True)
class OfficialScoreResult:
    """Resolved score for a team or department under an explicit measure."""

    entity_type: Literal["team", "department"]
    entity_name: str
    measure: ScoreMeasure
    score: float | None
    score_basis: str
    employee_average: float | None = None
    sample_size: int = 0
    applied_pin: bool = False
    unavailable_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _val(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def round1(value: float | None) -> float | None:
    """Round half-away-from-zero for non-negative scores, matching JS Math.round(v*10)/10."""
    if value is None or not math.isfinite(value):
        return None
    if value >= 0:
        return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    # For negative numbers, JS Math.round(-x) rounds toward +infinity (-0.05 -> 0.0)
    return math.floor(value * 10.0 + 0.5) / 10.0


def _nearly_equal(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return abs(left - right) <= 1e-9


def _finite_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            text = value.replace(",", "").strip()
            if text.endswith("%"):
                text = text[:-1].strip()
            num = float(text)
        else:
            num = float(value)
        return num if math.isfinite(num) else None
    except (TypeError, ValueError):
        return None


def _normalize_rate(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            num = float(value.replace("%", "").replace(",", "").strip())
        else:
            num = float(value)
        if not math.isfinite(num):
            return None
        return num / 100.0 if num > 1.0 else num
    except (TypeError, ValueError):
        return None


def _normalize_performance_score(raw: Any) -> float | None:
    num = _finite_float(raw)
    if num is None:
        return None
    if num <= 0:
        return 0.0
    if num <= 1.0:
        return num * 100.0
    return min(num, 100.0)


def _record_raw_data(record: Any) -> dict[str, Any]:
    raw = _val(record, "raw_data")
    return raw if isinstance(raw, Mapping) else {}


def _record_kpis(record: Any) -> list[dict[str, Any]]:
    kpis = _val(record, "kpi_values")
    return [dict(k) if isinstance(k, Mapping) else vars(k) for k in kpis] if isinstance(kpis, (list, tuple)) else []


def is_hossam_record(record: Any) -> bool:
    if record is None:
        return False
    emp_id = str(_val(record, "employee_id") or _val(record, "id") or "").strip().upper()
    if emp_id in {HOSSAM_EMPLOYEE_ID, "70094"}:
        return True
    name = str(_val(record, "employee_name") or _val(record, "name") or "").strip()
    if name and re.search(r"hossam", name, re.I) and re.search(r"mohamed", name, re.I):
        return True
    pos = str(_val(record, "position") or "").strip()
    if pos and re.search(r"pre-authorization supervisor", pos, re.I):
        return True
    return False


def pre_approvals_leader_team_total(records: Sequence[Any]) -> float | None:
    for rec in records:
        if is_hossam_record(rec):
            eval_obj = _val(rec, "evaluation")
            raw_score = _finite_float(_val(eval_obj, "score") if eval_obj is not None else _val(rec, "score"))
            if raw_score is not None:
                return round1(score_percent(raw_score))
    return None


def _get_raw_value(raw: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
        clean = re.sub(r"[\s_.]+", "", key.lower())
        for rkey, rval in raw.items():
            if rval is not None and re.sub(r"[\s_.]+", "", str(rkey).lower()) == clean:
                return rval
    return None


def _get_raw_number(raw: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    val = _get_raw_value(raw, keys)
    return _normalize_rate(val) if val is not None else None


def _get_pre_approvals_count_ratio(
    raw: Mapping[str, Any],
    numerator_keys: Sequence[str],
    denominator_keys: Sequence[str],
) -> float | None:
    num_raw = _get_raw_value(raw, numerator_keys)
    den_raw = _get_raw_value(raw, denominator_keys)
    num = _finite_float(num_raw)
    den = _finite_float(den_raw)
    if num is None or den is None or den <= 0:
        return None
    return max(0.0, num / den)


def _inbound_call_count(record: Any) -> float:
    calls = _val(record, "calls")
    from_calls = _finite_float(_val(calls, "inbound") if calls is not None else None)
    if from_calls is not None and from_calls > 0:
        return from_calls
    raw = _record_raw_data(record)
    val = _finite_float(raw.get("InboundCalls") if raw.get("InboundCalls") is not None else raw.get("InboundCalls "))
    return val if (val is not None and val > 0) else 0.0


def _inbound_booking_rate(record: Any) -> float | None:
    team = str(_val(record, "team") or "").strip().lower()
    if team != "inbound":
        return None
    calls = _inbound_call_count(record)
    if calls <= 0:
        return None
    geo = _val(record, "geo")
    bookings_obj = _val(geo, "bookings") if geo is not None else None
    from_geo: float | None = None
    if bookings_obj is not None:
        total = 0.0
        for bk in ("dubai", "sharjah", "ajman", "clinics"):
            total += _finite_float(_val(bookings_obj, bk)) or 0.0
        from_geo = max(0.0, total)
    from_raw: float | None = None
    raw = _record_raw_data(record)
    if raw:
        total = 0.0
        found = False
        for group in _INBOUND_BOOKING_GROUPS:
            for key in group:
                parsed = _finite_float(raw.get(key))
                if parsed is not None:
                    total += parsed
                    found = True
                    break
        if found:
            from_raw = max(0.0, total)
    bookings = from_geo if (from_geo is not None and from_geo > 0) else from_raw
    if bookings is None:
        return None
    return bookings / calls


def _resolve_pre_approvals_workstream(record: Any) -> str:
    pos = _norm(_val(record, "position"))
    if "eripapproval" in pos or ("er" in pos and "approval" in pos):
        return "er"
    if "ipelective" in pos:
        return "ip"
    keys = {_norm(k.get("kpi_key")) for k in _record_kpis(record)}
    if "erinitialrejectionrate" in keys or "approvalwithin15hours" in keys:
        return "er"
    raw = _record_raw_data(record)
    turn = _get_raw_number(raw, ("T.ERInitialRejectionRate", "T.ApprovalWithin1.5HoursRate"))
    exp = _get_raw_number(raw, ("T.%OfApprovalwithin48HR/1.5HR", "T.%OfApprovalwithin48HR1.5HR"))
    if (turn if turn is not None else (exp if exp is not None else 0.0)) >= 0.95:
        return "er"
    return "ip"


def _build_pre_approvals_kpis(record: Any, workstream: str) -> list[dict[str, Any]]:
    raw = _record_raw_data(record)
    persisted = {_norm(k.get("kpi_key")): k for k in _record_kpis(record)}
    defs = _PRE_APPROVALS_WORKSTREAMS[workstream]
    out: list[dict[str, Any]] = []
    for d in defs:
        src = persisted.get(_norm(d["key"]))
        if src is not None:
            actual = _normalize_rate(src.get("actual_value"))
            target = _normalize_rate(src.get("target_value"))
        else:
            actual = None
            target = None
        if actual is None:
            actual = _get_raw_number(raw, d["actual_keys"])
            if actual is None:
                if "rejection" in d["key"]:
                    actual = _get_pre_approvals_count_ratio(raw, ("RejectedRequests", "RejectedRequest"), ("AssignedRequests", "AssignedRequest")) or 0.0
                elif "48" in d["key"]:
                    actual = _get_pre_approvals_count_ratio(raw, ("ApprovalWithin48HR", "ApprovalWithin48hrs"), ("ApprovedRequests", "ApprovedRequest")) or 0.0
                else:
                    actual = _get_pre_approvals_count_ratio(raw, ("ApprovalWithin1.5HR", "ApprovalWithin1.5Hours"), ("ApprovedRequests", "ApprovedRequest")) or 0.0
        if target is None:
            target = _get_raw_number(raw, d["target_keys"])
            if target is None:
                fallback_keys = ("T.InitialRejection%", "T.InitialRejectionRate") if "rejection" in d["key"] else ("T.%OfApprovalwithin48HR/1.5HR", "T.%OfApprovalwithin48HR1.5HR")
                target = _get_raw_number(raw, fallback_keys)
            if target is None:
                target = float(d["fallback_target"])
        lower_better = d["direction"] == "lower_better"
        ach = (100.0 if actual <= 0 else (target / actual) * 100.0) if lower_better else ((actual / target) * 100.0 if target > 0 else 0.0)
        safe_ach = min(max(0.0, ach), 100.0)
        w = float(d["weight"])
        out.append({
            "key": d["key"],
            "label": d["label"],
            "actual": actual,
            "target": target,
            "unit": "%",
            "isLowerBetter": lower_better,
            "weight": w,
            "achievement": safe_ach,
            "contribution": (safe_ach / 100.0) * w * 100.0,
            "viewOnly": False,
            "evaluationPinned": False,
        })
    return out


def _build_pre_approvals_ip_offshore_kpis(record: Any) -> list[dict[str, Any]]:
    raw = _record_raw_data(record)
    controllable = str(raw.get("ScoringMethod") or "") == "preapprovals_offshore_v2"
    persisted = {_norm(k.get("kpi_key")): k for k in _record_kpis(record)}

    def _p(key: str) -> dict[str, Any] | None:
        return persisted.get(_norm(key))

    rej, err, sub = _p("Rejection"), _p("InitialError"), _p("Submission")
    rej_act = (
        (_get_raw_number(raw, ("ControllableRejectionRate",)) or (_normalize_rate(rej.get("actual_value")) if rej else None) or 0.0)
        if controllable
        else (
            _get_pre_approvals_count_ratio(raw, ("RejectedRequests", "RejectedRequest"), ("AssignedRequests", "AssignedRequest"))
            or _get_raw_number(raw, ("IPInitialRejection%", "A.IPInitialRejectionRate", "A.IPInitialRejection%", "RejectionRate"))
            or (_normalize_rate(rej.get("actual_value")) if rej else None)
            or 0.0
        )
    )
    err_act = (
        _get_pre_approvals_count_ratio(raw, ("ErrosClaims", "ErrorsClaims", "ErrorClaims"), ("SubmittedClaims", "SubmittedClaim"))
        or _get_raw_number(raw, ("Error%", "A.InitialErrorRate", "A.InitialError%", "InitialError%"))
        or (_normalize_rate(err.get("actual_value")) if err else None)
        or 0.0
    )
    sub_act = (
        _get_pre_approvals_count_ratio(raw, ("ApprovalWithin48HR", "ApprovalWithin48hrs", "NumberApprovalwithin48hrs"), ("ApprovedRequests", "ApprovedRequest"))
        or _get_raw_number(raw, ("%ofSubmissionWithinDuedate", "A.SubmissionRate", "A.Submission%", "SubmissionRate"))
        or (_normalize_rate(sub.get("actual_value")) if sub else None)
        or 0.0
    )
    rej_tgt = 0.01 if controllable else (
        _get_raw_number(raw, ("T.IPInitialRejection%", "T.Rejection%", "T.InitialRejection%", "T.Rejection", "T.InitialRejectionRate", "T.InitialRejection"))
        or (_normalize_rate(rej.get("target_value")) if rej else None)
        or 0.03
    )
    err_tgt = 0.01 if controllable else (
        _get_raw_number(raw, ("T.InitialError%", "T.InitialError", "T.InitialErrorRate", "T.Error%", "T.Error"))
        or (_normalize_rate(err.get("target_value")) if err else None)
        or 0.03
    )
    sub_tgt = 0.90 if controllable else (
        _get_raw_number(raw, ("T.%ofApprovalwithin48hrs", "T.%OfApprovalwithin48HR", "T.%OfApprovalwithin48hrs", "T.%ofApprovalwithin48HR", "T.Submission%", "T.Submission", "T.SubmissionRate", "T.%ofSubmissionWithinDuedate", "T.%OfSubmissionWithin48HR"))
        or (_normalize_rate(sub.get("target_value")) if sub else None)
        or 0.90
    )

    def _item(src: dict[str, Any] | None, key: str, label: str, act: float, tgt: float, lower: bool, fw: float) -> dict[str, Any]:
        sw = _finite_float(src.get("weight_applied")) if src else None
        safe_w = max(0.0, sw) if sw is not None else fw
        raw_ach = (100.0 if act <= 0 else (tgt / act) * 100.0) if lower else ((act / tgt) * 100.0 if tgt > 0 else 0.0)
        safe_ach = min(max(0.0, raw_ach), 100.0)
        return {
            "key": key,
            "label": label,
            "actual": act,
            "target": tgt,
            "unit": "%",
            "isLowerBetter": lower,
            "weight": safe_w,
            "achievement": safe_ach,
            "contribution": (safe_ach / 100.0) * safe_w * 100.0,
            "viewOnly": False,
            "evaluationPinned": False,
        }

    return [
        _item(rej, "Rejection", "Controllable Rejection Rate" if controllable else "Rejection Rate", rej_act, rej_tgt, True, 0.50),
        _item(err, "InitialError", "Initial Error Rate", err_act, err_tgt, True, 0.20),
        _item(sub, "Submission", "Submission Rate", sub_act, sub_tgt, False, 0.30),
    ]


def get_kpis_for_agent(record: Any) -> list[dict[str, Any]]:
    team = str(_val(record, "team") or "Inbound").strip()
    tnorm = _norm(team)
    if tnorm == _norm("Pre-Approvals IP Elective Dubai") or tnorm == _norm("Pre-Approvals IP Elective"):
        return _build_pre_approvals_kpis(record, _resolve_pre_approvals_workstream(record))
    if tnorm == _norm("Pre-Approvals IP Offshore"):
        return _build_pre_approvals_ip_offshore_kpis(record)
    kpis = _record_kpis(record)
    if kpis:
        inbound_booking = _inbound_booking_rate(record)
        out: list[dict[str, Any]] = []
        for kpi in kpis:
            key = str(kpi.get("kpi_key") or "")
            label = str(kpi.get("label") or key)
            actual = _finite_float(kpi.get("actual_value"))
            actual = actual if actual is not None else 0.0
            target = _finite_float(kpi.get("target_value"))
            target = target if target is not None else 0.0
            unit_raw = str(kpi.get("unit") or "%")
            unit = unit_raw if unit_raw in {"%", "min", "number", "currency"} else "number"
            ach_ratio = _finite_float(kpi.get("achievement_ratio")) or 0.0
            weight_applied = _finite_float(kpi.get("weight_applied"))
            contrib_raw = _finite_float(kpi.get("contribution")) or 0.0
            if inbound_booking is not None and "booking" in f"{key} {label}".lower():
                actual = inbound_booking
                ach_ratio = min(actual / target, 1.0) if target > 0 else ach_ratio
                nw = (weight_applied / 100.0 if weight_applied > 1 else weight_applied) if weight_applied is not None else 0.0
                contrib_raw = min(max(ach_ratio, 0.0), 1.0) * max(nw, 0.0)
            w_eff = max(weight_applied or 0.0, 0.0)
            is_penalty = kpi.get("is_penalty") is True
            out.append({
                "key": key,
                "label": label,
                "actual": actual,
                "target": target,
                "unit": unit,
                "isLowerBetter": str(kpi.get("direction") or "") == "lower_better",
                "achievement": min(max(ach_ratio, 0.0), 1.0) * 100.0,
                "weight": weight_applied,
                "viewOnly": kpi.get("view_only") in (True, 1),
                "contribution": contrib_raw * 100.0 if is_penalty else min(max(contrib_raw, 0.0), w_eff) * 100.0,
                "evaluationPinned": kpi.get("evaluation_pinned") is True,
                "isPenalty": is_penalty,
            })
        return out
    return []


def _geo_source_value(record: Any, field_name: str, location: str = "all") -> float:
    geo = _val(record, "geo")
    values = _val(geo, field_name) if geo is not None else None
    if values is None:
        return 0.0
    if location != "all":
        return _finite_float(_val(values, location)) or 0.0
    return sum(_finite_float(_val(values, bk)) or 0.0 for bk in ("dubai", "sharjah", "ajman", "clinics"))


def _source_value(record: Any, source: str | None, location: str = "all") -> float | None:
    if not source:
        return None
    calls = _val(record, "calls")
    if source == "$calls.total_handled":
        return _finite_float(_val(calls, "total_handled") if calls is not None else None) or 0.0
    if source == "$calls.inbound":
        return _inbound_call_count(record)
    if source == "$calls.abandoned":
        return _finite_float(_val(calls, "abandoned") if calls is not None else None) or 0.0
    if source == "$geo.bookings":
        return _geo_source_value(record, "bookings", location)
    if source == "$geo.attended":
        return _geo_source_value(record, "attended", location)
    raw = _record_raw_data(record)
    raw_val = raw.get(source)
    if raw_val is None:
        aliases = {
            "errosclaims": ("ErrorsClaims", "ErrorClaims"),
            "errorsclaims": ("ErrosClaims", "ErrorClaims"),
            "errorclaims": ("ErrosClaims", "ErrorsClaims"),
        }.get(_norm(source), ())
        for alt in aliases:
            if raw.get(alt) is not None:
                raw_val = raw[alt]
                break
    if raw_val is None and source == "A.DispensedItems":
        for alt in ("Dispensed Items", "A.TotalDispensedPrescriptions", "Dispensed Prescriptions"):
            if raw.get(alt) is not None:
                raw_val = raw[alt]
                break
    if raw_val is None and source == "A.TotalPrescribedItems":
        for alt in ("Total Prescribed Items", "Total Prescriped Items", "Prescribed Items"):
            if raw.get(alt) is not None:
                raw_val = raw[alt]
                break
    if raw_val is None or raw_val == "":
        return None
    text = str(raw_val).replace(",", "").strip()
    is_pct = text.endswith("%")
    num = _finite_float(text[:-1] if is_pct else text)
    if num is None:
        return None
    return num / 100.0 if is_pct else num


def _is_outbound_from_aug_2026(record: Any) -> bool:
    year = _val(record, "year")
    if isinstance(year, (int, float)) and math.isfinite(year):
        if int(year) < 2026:
            return False
        if int(year) > 2026:
            return True
    month = str(_val(record, "month") or "").strip().lower()
    if month and any(month.startswith(p) for p in _PRE_AUG_MONTHS):
        return False
    return True


def _has_outbound_utilization(record: Any) -> bool:
    if _norm(_val(record, "team")) != "outbound":
        return False
    if not _is_outbound_from_aug_2026(record):
        return False
    for k in _record_kpis(record):
        if _norm(k.get("kpi_key") or k.get("label")) == "utilization":
            return True
    raw = _record_raw_data(record)
    rv = raw.get("A.Utilization%") if raw.get("A.Utilization%") is not None else raw.get("A.Utilization")
    if rv is None or str(rv).strip() == "":
        return False
    return _finite_float(rv) is not None


def _position_definitions(config: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not config:
        return None
    levels = config.get("performance_levels") or {}
    emp = levels.get("Employee") if isinstance(levels, Mapping) else None
    pos = emp.get("positions") if isinstance(emp, Mapping) else None
    return dict(pos) if isinstance(pos, Mapping) else None


def _keeps_unconfigured_position_kpi(config: Mapping[str, Any] | None) -> bool:
    if not config:
        return False
    if str(config.get("team") or "").strip().lower() == "marketing":
        return True
    positions = _position_definitions(config)
    return bool(positions) and len(config.get("kpis") or []) == 0


def _employee_definitions(config: Mapping[str, Any] | None, record: Any) -> list[dict[str, Any]]:
    if not config:
        return []
    positions = _position_definitions(config)
    pos_name = _val(record, "position")
    if positions and pos_name:
        target_p = _norm(pos_name)
        for name, pdef in positions.items():
            if _norm(name) == target_p:
                return list(pdef.get("kpis") or [])
    kpis = list(config.get("kpis") or [])
    if kpis:
        if _norm(config.get("team")) == "outbound" and _has_outbound_utilization(record):
            if any(_norm(k.get("key")) == "utilization" for k in kpis):
                return kpis
            updated = [
                ({**k, "weight": max(0.0, round(float(k.get("weight", 0)) - 0.10, 4))} if _norm(k.get("key")) == "attendance" else k)
                for k in kpis
            ]
            updated.append(_OUTBOUND_UTZ_DEF)
            return updated
        return kpis
    if positions:
        flat: list[dict[str, Any]] = []
        for pdef in positions.values():
            flat.extend(pdef.get("kpis") or [])
        return flat
    return []


def _find_definition(definitions: Sequence[Mapping[str, Any]], kpi: Mapping[str, Any]) -> Mapping[str, Any] | None:
    label = _norm(kpi.get("label"))
    key = _norm(kpi.get("key"))
    for d in definitions:
        if _norm(d.get("label")) == label or _norm(d.get("key")) == label or (key and _norm(d.get("key")) == key):
            return d
    if any(alias in label for alias in ("utz", "utilization", "abandonrate", "reachability")):
        for d in definitions:
            if _norm(d.get("key")) == "other":
                return d
    return None


def _kpi_weight_keys(label: str) -> list[str]:
    low = label.lower()
    if "quality errors rate" in low:
        return ["quality_errors_rate"]
    if "rejection rate after re-submission" in low:
        return ["rejection_rate_after_resubmission"]
    if low == "tat":
        return ["tat", "TAT"]
    if "initial rejection rate" in low:
        return ["initial_rejection_rate", "Rejection"]
    if "submission within due date" in low:
        return ["submission_within_due_date", "Submission"]
    if "attendance" in low:
        return ["Attendance", "Attend"]
    if "booking" in low:
        return ["Booking"]
    if low == "aht" or any(w in low for w in ("aht", "handle time", "avg. handle time")):
        return ["AHT", "AHT (Handle Time)", "TAT"]
    if "turnaround time" in low:
        return ["TAT"]
    if "quality errors" in low:
        return ["QualityErrors"]
    if "quality score" in low or low == "quality":
        return ["Quality"]
    if "queries handled" in low:
        return ["Queries"]
    if "attended cr" in low or "attendedcr" in low:
        return ["AttendedCR"]
    if "waiting time" in low:
        return ["WaitingTime"]
    if "average transaction value" in low or "atv" in low:
        return ["ATV"]
    if "prescription contribution" in low or "prescription" in low:
        return ["Prescription"]
    if "tender compliance" in low:
        return ["TenderCompliance"]
    if "leakage" in low:
        return ["Leakage"]
    if "utz" in low or "utilization" in low:
        return ["Utilization", "UTZ", "Other"]
    if "reachability" in low or "abandon" in low:
        return ["Other"]
    if "rejection" in low:
        return ["Rejection"]
    if "initial error" in low:
        return ["InitialError"]
    if "submission" in low:
        return ["Submission", "submission_within_due_date"]
    if label == "OP Census Ach":
        return ["OPCensus"]
    if label == "OP Revenue Ach":
        return ["OPRevenue"]
    if label == "IP Census Ach":
        return ["IPCensus"]
    if label == "IP Revenue Ach":
        return ["IPRevenue"]
    if "activity score" in low:
        return ["Activity"]
    return [""]


def _get_weight_for_label(
    team_weights: Mapping[str, float] | None,
    label: str,
    team_name: str | None = None,
    raw_data: Mapping[str, Any] | None = None,
    month: str | None = None,
) -> float | None:
    nt = (team_name or "").strip().lower()
    nm = (month or "").strip().lower()
    low = label.lower()
    if nt == "pre-approvals ip offshore":
        claims = _finite_float((raw_data or {}).get("SubmittedClaims")) or 0.0
        if claims == 0:
            if "rejection" in low:
                return 0.60
            if "error" in low:
                return 0.00
            if "submission" in low:
                return 0.40
        else:
            if "rejection" in low:
                return 0.50
            if "error" in low:
                return 0.20
            if "submission" in low:
                return 0.30
    if nt == "inbound" and nm == "june":
        if "quality" in low:
            return 0.00
        if "utz" in low or "utilization" in low or "abandon" in low:
            return 0.15
    if nt == "outbound":
        is_pre_aug = bool(nm) and any(nm.startswith(m) for m in _PRE_AUG_MONTHS)
        raw_utz = (raw_data or {}).get("A.Utilization%") if (raw_data or {}).get("A.Utilization%") is not None else (raw_data or {}).get("A.Utilization")
        parsed_utz = _finite_float(raw_utz)
        if not is_pre_aug and parsed_utz is not None:
            if "attendance" in low or low == "attend":
                base_att = float((team_weights or {}).get("Attendance") or (team_weights or {}).get("Attend") or 0.70)
                norm_base = base_att / 100.0 if base_att > 1.0 else base_att
                if team_weights and "Utilization" in team_weights:
                    return norm_base
                return max(0.0, round(norm_base - 0.10, 4))
            if "utilization" in low or "utz" in low:
                return float((team_weights or {}).get("Utilization", 0.10))
        if nm == "june":
            if "quality" in low:
                return 0.00
            if "reachability" in low or "other" in low:
                return 0.20
    if not team_weights:
        return None
    for key in _kpi_weight_keys(label):
        if key in team_weights and team_weights[key] is not None:
            return float(team_weights[key])
    return None


def _achievement_for(kpi: Mapping[str, Any]) -> float:
    actual = _finite_float(kpi.get("actual"))
    target = _finite_float(kpi.get("target"))
    if actual is None or target is None:
        return 0.0
    label_low = str(kpi.get("label") or "").lower()
    if "prescription" in label_low:
        ach = actual if actual > 1.5 else actual * 100.0
        return min(max(ach, 0.0), 100.0)
    unit = str(kpi.get("unit") or "%")
    is_time = unit == "min" or "aht" in label_low or "waitingtime" in label_low
    raw_target = target * 1440.0 if (is_time and 0 < target < 1.0 and actual >= 1.0) else target
    raw_actual = actual
    if not is_time and unit != "%":
        if 0 < raw_actual <= 1.0 and raw_target > 1.0:
            raw_actual *= 100.0
        elif 0 < raw_target <= 1.0 and raw_actual > 1.0:
            raw_target *= 100.0
    formula = kpi.get("scoreFormula") or "target_ratio"
    if formula == "baseline_80":
        denom = raw_target - 0.8
        ach = ((raw_actual - 0.8) / denom) * 100.0 if denom > 0 else 0.0
    elif kpi.get("isLowerBetter"):
        ach = 100.0 if raw_actual <= 0 else (raw_target / raw_actual) * 100.0
    else:
        ach = (raw_actual / raw_target) * 100.0 if raw_target > 0 else 0.0
    return min(max(ach, 0.0), 100.0)


def _aggregate_configured_team_kpis(
    records: Sequence[Any],
    config: Mapping[str, Any] | None,
    location: str = "all",
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    keeps_unconf = _keeps_unconfigured_position_kpi(config)
    for rec in records:
        defs = _employee_definitions(config, rec)
        for kpi in get_kpis_for_agent(rec):
            key = _norm(kpi.get("label"))
            pinned = kpi.get("evaluationPinned") is True
            definition = _find_definition(defs, kpi)
            stored_pos_kpi = definition is None and keeps_unconf
            if defs and definition is None and not pinned and not stored_pos_kpi:
                continue
            label_norm = _norm(kpi.get("label"))
            is_utz = "utz" in label_norm or "utilization" in label_norm
            agg = (
                {"method": "average"}
                if (definition is not None and _norm(definition.get("key")) == "other" and is_utz)
                else dict((definition or {}).get("aggregation") or {"method": "average"})
            )
            bucket = buckets.get(key)
            if bucket is None:
                bucket = {
                    "key": (definition or {}).get("key") or kpi.get("key"),
                    "label": kpi.get("label"),
                    "unit": kpi.get("unit"),
                    "isLowerBetter": bool(kpi.get("isLowerBetter")),
                    "method": agg.get("method") or "average",
                    "actualSum": 0.0,
                    "targetSum": 0.0,
                    "count": 0,
                    "numerator": 0.0,
                    "denominator": 0.0,
                    "hasRatioCounters": False,
                    "weightedActual": 0.0,
                    "aggregationWeight": 0.0,
                    "scoreWeight": 0.0,
                    "scoreWeightCount": 0,
                    "contributionSum": 0.0,
                    "contributionCount": 0,
                    "scoreFormula": (definition or {}).get("score_formula") or "target_ratio",
                    "scoreTarget": (definition or {}).get("score_target"),
                    "pinnedCount": 0,
                    "legacyCount": 0,
                    "pinnedAgrees": True,
                    "pinnedTarget": None,
                    "pinnedWeight": None,
                    "pinnedLowerBetter": None,
                    "pinnedUnit": None,
                    "pinnedKey": None,
                    "pinnedUnitAgrees": True,
                    "pinnedKeyAgrees": True,
                    "viewOnlyCount": 0,
                }
                buckets[key] = bucket

            inb_book = _norm((config or {}).get("team")) == "inbound" and _norm((definition or {}).get("key")) == "booking"
            conf_act = _source_value(rec, (definition or {}).get("actual_col"), location) if (definition and definition.get("actual_col") and not inb_book) else None
            conf_tgt = _source_value(rec, (definition or {}).get("target_col"), location) if (definition and definition.get("target_col")) else None

            if pinned:
                bucket["pinnedCount"] += 1
                pw = kpi.get("weight")
                same_pin = (
                    _nearly_equal(bucket["pinnedTarget"], kpi.get("target"))
                    and _nearly_equal(bucket["pinnedWeight"], pw)
                    and bool(bucket["pinnedLowerBetter"]) == bool(kpi.get("isLowerBetter"))
                    and (bucket["pinnedUnit"] or "") == (kpi.get("unit") or "")
                    and _norm(bucket["pinnedKey"]) == _norm(kpi.get("key"))
                )
                if bucket["pinnedCount"] == 1:
                    bucket["pinnedTarget"] = kpi.get("target")
                    bucket["pinnedWeight"] = pw
                    bucket["pinnedLowerBetter"] = bool(kpi.get("isLowerBetter"))
                    bucket["pinnedUnit"] = kpi.get("unit")
                    bucket["pinnedKey"] = kpi.get("key")
                elif not same_pin:
                    if (bucket["pinnedUnit"] or "") != (kpi.get("unit") or ""):
                        bucket["pinnedUnitAgrees"] = False
                    if _norm(bucket["pinnedKey"]) != _norm(kpi.get("key")):
                        bucket["pinnedKeyAgrees"] = False
                    bucket["pinnedAgrees"] = False
                bucket["actualSum"] += float(kpi["actual"]) if math.isfinite(float(kpi.get("actual") or 0.0)) else 0.0
                bucket["targetSum"] += float(kpi["target"]) if math.isfinite(float(kpi.get("target") or 0.0)) else 0.0
            else:
                bucket["legacyCount"] += 1
                bucket["actualSum"] += conf_act if (bucket["method"] == "ratio" and conf_act is not None) else float(kpi.get("actual") or 0.0)
                bucket["targetSum"] += conf_tgt if (bucket["method"] == "ratio" and conf_tgt is not None) else float(kpi.get("target") or 0.0)

            bucket["count"] += 1
            if kpi.get("viewOnly"):
                bucket["viewOnlyCount"] += 1
            eff_w = kpi.get("weight") if pinned else (kpi.get("weight") if kpi.get("weight") is not None else (definition or {}).get("weight"))
            if eff_w is not None:
                bucket["scoreWeight"] += float(eff_w)
                bucket["scoreWeightCount"] += 1
            if kpi.get("contribution") is not None:
                bucket["contributionSum"] += float(kpi["contribution"])
                bucket["contributionCount"] += 1

            if bucket["method"] == "ratio":
                num_val = _source_value(rec, agg.get("numerator_col"), location)
                den_src = "$calls.inbound" if inb_book else agg.get("denominator_col")
                den_val = _source_value(rec, den_src, location)
                if num_val is not None and den_val is not None:
                    bucket["hasRatioCounters"] = True
                    bucket["numerator"] += num_val
                    bucket["denominator"] += den_val
            elif bucket["method"] == "weighted_average":
                w_val = _source_value(rec, agg.get("weight_col"), location) or 0.0
                bucket["weightedActual"] += float(kpi.get("actual") or 0.0) * w_val
                bucket["aggregationWeight"] += w_val

    result: dict[str, dict[str, Any]] = {}
    for key, b in buckets.items():
        cnt = b["count"]
        fallback_avg = (b["actualSum"] / cnt) if cnt > 0 else 0.0
        if b["method"] == "sum":
            pooled_act = b["actualSum"]
        elif b["method"] == "ratio" and b["hasRatioCounters"]:
            pooled_act = (b["numerator"] / b["denominator"]) if b["denominator"] > 0 else 0.0
        elif b["method"] == "weighted_average" and b["aggregationWeight"] > 0:
            pooled_act = b["weightedActual"] / b["aggregationWeight"]
        else:
            pooled_act = fallback_avg
        act = math.nan if (not b["pinnedUnitAgrees"] or not b["pinnedKeyAgrees"]) else pooled_act
        mixed = b["pinnedCount"] > 0 and (b["legacyCount"] > 0 or not b["pinnedAgrees"])
        uniform = b["pinnedCount"] > 0 and b["legacyCount"] == 0 and b["pinnedAgrees"]
        if mixed:
            tgt = math.nan
            weight = None
        elif uniform:
            tgt = float(b["pinnedTarget"]) if b["pinnedTarget"] is not None else math.nan
            weight = b["pinnedWeight"]
        else:
            if b["method"] == "ratio" and b["scoreTarget"] is not None:
                tgt = float(b["scoreTarget"])
            elif b["method"] == "sum":
                tgt = b["targetSum"]
            elif cnt > 0 and b["targetSum"] > 0:
                tgt = b["targetSum"] / cnt
            else:
                tgt = 0.0
            weight = (b["scoreWeight"] / b["scoreWeightCount"]) if b["scoreWeightCount"] > 0 else None
        result[key] = {
            "key": (b["pinnedKey"] if b["pinnedCount"] > 0 else b["key"]) if b["pinnedKeyAgrees"] else None,
            "label": b["label"],
            "unit": b["unit"] if b["pinnedUnitAgrees"] else None,
            "isLowerBetter": None if mixed else b["isLowerBetter"],
            "actual": act,
            "target": tgt,
            "weight": weight,
            "contribution": None if (mixed or b["contributionCount"] == 0) else (b["contributionSum"] / b["contributionCount"]),
            "scoreFormula": b["scoreFormula"],
            "evaluationPinned": uniform or (mixed and b["legacyCount"] == 0),
            "basisVaries": mixed,
            "viewOnly": cnt > 0 and b["viewOnlyCount"] == cnt,
        }
    return result


def _position_group(config: Mapping[str, Any], record: Any) -> str:
    positions = _position_definitions(config)
    pos = _norm(_val(record, "position"))
    if positions and pos:
        for name in positions:
            if _norm(name) == pos:
                return str(name)
    if (config.get("kpis") or []) or not positions:
        return "__root__"
    return f"__unmatched__:{pos}"


def _basis_group_key(config: Mapping[str, Any], record: Any) -> str:
    pos_group = _position_group(config, record)
    pinned = [k for k in _record_kpis(record) if k.get("evaluation_pinned") is True]
    if not pinned:
        return f"{pos_group}::legacy-utz" if _has_outbound_utilization(record) else f"{pos_group}::legacy"
    sig_parts = []
    for k in pinned:
        tv = _finite_float(k.get("target_value"))
        wa = _finite_float(k.get("weight_applied"))
        sig_parts.append("=".join([
            _norm(k.get("kpi_key") or k.get("label")),
            str(k.get("direction") or ""),
            str(k.get("unit") or ""),
            f"{tv:.8f}" if tv is not None else "nan",
            f"{wa:.8f}" if wa is not None else "nan",
        ]))
    sig_parts.sort()
    return f"{pos_group}::{'&'.join(sig_parts)}"


def calculate_aggregated_team_performance(
    records: Sequence[Any],
    config: Mapping[str, Any] | None,
    location: str = "all",
) -> tuple[float, int] | None:
    """Return `(raw_pooled_team_score, kpi_count)` matching `teamKpiAggregator.ts`."""
    if not config or not records:
        return None
    team_name = str(config.get("team") or "")
    if _norm(team_name) in (_norm("Pre-Approvals IP"), _norm("Pre-Approvals IP Offshore")):
        leader_total = pre_approvals_leader_team_total(records)
        if leader_total is not None:
            for rec in records:
                if is_hossam_record(rec):
                    hk = _aggregate_configured_team_kpis([rec], config, location)
                    eval_obj = _val(rec, "evaluation")
                    raw_sc = _finite_float(_val(eval_obj, "score") if eval_obj is not None else _val(rec, "score")) or 0.0
                    return (raw_sc, len(hk))

    groups: dict[str, list[Any]] = {}
    for rec in records:
        gk = _basis_group_key(config, rec)
        groups.setdefault(gk, []).append(rec)

    weighted_score = 0.0
    records_used = 0
    kpi_keys_seen: set[str] = set()
    for group_recs in groups.values():
        defs = _employee_definitions(config, group_recs[0])
        if not defs:
            continue
        conf_weights = {str(d.get("key") or ""): float(d.get("weight") or 0.0) for d in defs}
        agg_raw = None
        if team_name == "Pre-Approvals IP Offshore":
            sub_claims = sum(_finite_float(_record_raw_data(r).get("SubmittedClaims")) or 0.0 for r in group_recs)
            agg_raw = {"SubmittedClaims": str(sub_claims)}
        month = str(_val(group_recs[0], "month") or "")
        kpis = _aggregate_configured_team_kpis(group_recs, config, location)
        kpi_keys_seen.update(kpis.keys())
        group_score = 0.0
        for _, kpi in kpis.items():
            if kpi.get("basisVaries"):
                continue
            definition = _find_definition(defs, kpi)
            uniform_pin = kpi.get("evaluationPinned") is True and kpi.get("basisVaries") is not True
            if uniform_pin:
                w = float(kpi.get("weight") or 0.0)
            else:
                special_w = _get_weight_for_label(conf_weights, str(kpi.get("label") or ""), team_name, agg_raw, month)
                if special_w is not None:
                    w = float(special_w)
                elif kpi.get("weight") is not None:
                    w = float(kpi["weight"])
                elif definition is not None and definition.get("weight") is not None:
                    w = float(definition["weight"])
                else:
                    w = 0.0
            group_score += _achievement_for(kpi) * w
        weighted_score += min(group_score, 100.0) * len(group_recs)
        records_used += len(group_recs)

    if records_used == 0:
        return None
    return (weighted_score / records_used, len(kpi_keys_seen))


def _records_use_applied_pin(records: Sequence[Any]) -> bool:
    return any(k.get("evaluation_pinned") is True for r in records for k in _record_kpis(r))


def _displayed_team_score(canonical: float | None, employee_avg: float, applied_pin: bool) -> float:
    if applied_pin:
        return canonical if (canonical is not None and math.isfinite(canonical)) else employee_avg
    if canonical is not None and math.isfinite(canonical) and canonical > 0 and abs(canonical - employee_avg) <= 15.0:
        return canonical
    return employee_avg


def _load_config_safe(team_name: str, extra_configs: Mapping[str, Mapping[str, Any]] | None = None) -> Mapping[str, Any] | None:
    if extra_configs and team_name in extra_configs:
        return extra_configs[team_name]
    try:
        return load_team_config(team_name)
    except ConfigurationError:
        return None


def _resolve_team_config(
    records: Sequence[Any],
    canonical_team: str,
    configs: Mapping[str, Mapping[str, Any]] | None = None,
) -> Mapping[str, Any] | None:
    if not records:
        return None
    raw_names = {str(_val(r, "team") or "").strip() for r in records if str(_val(r, "team") or "").strip()}
    if len(raw_names) == 1:
        single = next(iter(raw_names))
        if is_egypt_resubmission_team(single):
            cfg = _load_config_safe("Resubmission", configs) or _load_config_safe(single, configs)
        else:
            cfg = _load_config_safe(single, configs) or _load_config_safe(canonical_team, configs)
        if cfg is not None:
            return cfg
    return _load_config_safe(canonical_team, configs)


def _is_stored_employee_scorecard(record: Any) -> bool:
    team = str(_val(record, "team") or "").strip()
    return team in CLINICAL_TREND_TEAMS or uses_published_score(_record_raw_data(record))


def _record_display_score(record: Any) -> float | None:
    if str(_val(record, "employee_name") or "").strip().lower() == "total":
        return None
    if _record_raw_data(record) and not _has_real_activity(record):
        return None
    eval_obj = _val(record, "evaluation")
    raw = _val(eval_obj, "score") if eval_obj is not None else _val(record, "score")
    if _is_stored_employee_scorecard(record):
        return _finite_float(raw)
    return _normalize_performance_score(raw)


def _active_scores(records: Sequence[Any]) -> list[float]:
    scores: list[float] = []
    for rec in records:
        sc = _record_display_score(rec)
        if sc is not None:
            scores.append(sc)
    return scores


def official_team_score(
    team_records: Sequence[Any],
    canonical_team: str,
    *,
    measure: ScoreMeasure = "official",
    location: str = "all",
    configs: Mapping[str, Mapping[str, Any]] | None = None,
) -> OfficialScoreResult:
    """Compute official Monthly Review team score OR employee average for one team cohort."""
    deduped = dedupe_egypt_resubmission_records(list(team_records))
    scores = _active_scores(deduped)
    if not scores:
        return OfficialScoreResult(
            entity_type="team",
            entity_name=canonical_team,
            measure=measure,
            score=None,
            score_basis="average employee score" if measure == "employee_average" else "Monthly Review team score",
            employee_average=None,
            sample_size=0,
            unavailable_reason="No measured employee records matched this team and period.",
        )

    emp_avg = sum(scores) / len(scores)
    emp_avg_r1 = round1(emp_avg)

    if measure == "employee_average":
        return OfficialScoreResult(
            entity_type="team",
            entity_name=canonical_team,
            measure="employee_average",
            score=emp_avg_r1,
            score_basis="average employee score",
            employee_average=emp_avg_r1,
            sample_size=len(scores),
        )

    # Official Monthly Review team calculation
    leader = pre_approvals_leader_team_total(deduped)
    if leader is not None:
        return OfficialScoreResult(
            entity_type="team",
            entity_name=canonical_team,
            measure="official",
            score=round1(leader),
            score_basis="Monthly Review leader scorecard",
            employee_average=emp_avg_r1,
            sample_size=len(scores),
        )

    if any(_is_stored_employee_scorecard(record) for record in deduped):
        return OfficialScoreResult(
            entity_type="team",
            entity_name=canonical_team,
            measure="official",
            score=emp_avg_r1,
            score_basis="average published employee scores",
            employee_average=emp_avg_r1,
            sample_size=len(scores),
            applied_pin=_records_use_applied_pin(deduped),
        )

    cfg = _resolve_team_config(deduped, canonical_team, configs=configs)
    if cfg is None:
        return OfficialScoreResult(
            entity_type="team",
            entity_name=canonical_team,
            measure="official",
            score=None,
            score_basis="Monthly Review team score",
            employee_average=emp_avg_r1,
            sample_size=len(scores),
            unavailable_reason="Scoring basis unavailable (no verified team scoring configuration).",
        )

    applied_pin = _records_use_applied_pin(deduped)
    is_cc_channel = _norm(cfg.get("team")) in {"inbound", "outbound"}
    if is_cc_channel and all(not _record_raw_data(r) for r in deduped):
        return OfficialScoreResult(
            entity_type="team",
            entity_name=canonical_team,
            measure="official",
            score=emp_avg_r1,
            score_basis="Monthly Review team score",
            employee_average=emp_avg_r1,
            sample_size=len(scores),
            applied_pin=applied_pin,
        )
    pooled = calculate_aggregated_team_performance(deduped, cfg, location=location)
    if pooled is None or pooled[1] == 0:
        if is_cc_channel:
            return OfficialScoreResult(
                entity_type="team",
                entity_name=canonical_team,
                measure="official",
                score=emp_avg_r1,
                score_basis="Monthly Review team score",
                employee_average=emp_avg_r1,
                sample_size=len(scores),
                applied_pin=applied_pin,
            )
        return OfficialScoreResult(
            entity_type="team",
            entity_name=canonical_team,
            measure="official",
            score=None,
            score_basis="Monthly Review team score",
            employee_average=emp_avg_r1,
            sample_size=len(scores),
            applied_pin=applied_pin,
            unavailable_reason="Scoring basis unavailable (no configured KPIs matched the records).",
        )

    official = round1(_displayed_team_score(pooled[0], emp_avg, applied_pin))
    return OfficialScoreResult(
        entity_type="team",
        entity_name=canonical_team,
        measure="official",
        score=official,
        score_basis="Monthly Review team score",
        employee_average=emp_avg_r1,
        sample_size=len(scores),
        applied_pin=applied_pin,
    )


def official_department_score(
    dept_name: str,
    dept_records: Sequence[Any],
    *,
    measure: ScoreMeasure = "official",
    location: str = "all",
    configs: Mapping[str, Mapping[str, Any]] | None = None,
) -> OfficialScoreResult:
    """Compute official Monthly Review department/function score OR employee average."""
    deduped = dedupe_egypt_resubmission_records(list(dept_records))
    scores = _active_scores(deduped)
    if not scores:
        return OfficialScoreResult(
            entity_type="department",
            entity_name=dept_name,
            measure=measure,
            score=None,
            score_basis="average employee score" if measure == "employee_average" else "Monthly Review department score",
            employee_average=None,
            sample_size=0,
            unavailable_reason="No measured employee records matched this department and period.",
        )

    emp_avg_r1 = round1(sum(scores) / len(scores))
    if measure == "employee_average":
        return OfficialScoreResult(
            entity_type="department",
            entity_name=dept_name,
            measure="employee_average",
            score=emp_avg_r1,
            score_basis="average employee score",
            employee_average=emp_avg_r1,
            sample_size=len(scores),
        )

    if _norm(dept_name) == _norm("Call Center"):
        inbound_recs = [r for r in deduped if str(_val(r, "team") or "") == "Inbound"]
        outbound_recs = [r for r in deduped if str(_val(r, "team") or "") == "Outbound"]
        support_recs = [r for r in deduped if str(_val(r, "team") or "") == "Call Center" and _val(r, "position")]
        if not inbound_recs and not outbound_recs:
            return OfficialScoreResult(
                entity_type="department",
                entity_name=dept_name,
                measure="official",
                score=None,
                score_basis="Monthly Review department score",
                employee_average=emp_avg_r1,
                sample_size=len(scores),
                unavailable_reason="No measured Inbound or Outbound channel rows exist for Call Center in this period.",
            )
        channel_scores: list[float] = []
        if inbound_recs:
            inb = official_team_score(inbound_recs, "Inbound", measure="official", location=location, configs=configs)
            if inb.score is not None:
                channel_scores.append(inb.score)
        if outbound_recs:
            out = official_team_score(outbound_recs, "Outbound", measure="official", location=location, configs=configs)
            if out.score is not None:
                channel_scores.append(out.score)
        if support_recs:
            sup_scores = _active_scores(support_recs)
            if sup_scores:
                sup_r1 = round1(sum(sup_scores) / len(sup_scores))
                if sup_r1 is not None:
                    channel_scores.append(sup_r1)
        if not channel_scores:
            return OfficialScoreResult(
                entity_type="department",
                entity_name=dept_name,
                measure="official",
                score=None,
                score_basis="Monthly Review department score",
                employee_average=emp_avg_r1,
                sample_size=len(scores),
                unavailable_reason="No verified channel scores available for Call Center.",
            )
        cc_official = round1(sum(channel_scores) / len(channel_scores))
        return OfficialScoreResult(
            entity_type="department",
            entity_name=dept_name,
            measure="official",
            score=cc_official,
            score_basis="Monthly Review Call Center channel average",
            employee_average=emp_avg_r1,
            sample_size=len(scores),
            metadata={"channel_scores": channel_scores},
        )

    # All other Monthly Review departments report round1(mean(record scores)).
    return OfficialScoreResult(
        entity_type="department",
        entity_name=dept_name,
        measure="official",
        score=emp_avg_r1,
        score_basis="Monthly Review department score",
        employee_average=emp_avg_r1,
        sample_size=len(scores),
    )


def build_official_scores_snapshot(
    db: Any,
    scope: dict[str, Any],
    records: Sequence[Any],
    *,
    region: str | None = None,
    level: str = "Employee",
    period_key: str | None = None,
    measure: ScoreMeasure = "official",
    location: str = "all",
    function_for_team_fn: Any = None,
    display_team_fn: Any = None,
) -> dict[str, Any]:
    """Compute a scoped, revision-stamped snapshot of team and department scores."""
    from services.cache_invalidation_service import CacheInvalidationService
    from utils.report_scope import canonical_scope_identity

    by_team: dict[str, list[Any]] = {}
    by_dept: dict[str, list[Any]] = {}
    for rec in records:
        rec_team = str(_val(rec, "team") or "").strip()
        if not rec_team:
            continue
        disp_team = display_team_fn(rec_team) if display_team_fn else rec_team
        by_team.setdefault(disp_team, []).append(rec)
        dept = function_for_team_fn(rec_team) if function_for_team_fn else rec_team
        by_dept.setdefault(dept or rec_team, []).append(rec)

    teams_out: dict[str, dict[str, Any]] = {}
    for tname, trecs in sorted(by_team.items()):
        res = official_team_score(trecs, tname, measure=measure, location=location)
        teams_out[tname] = {
            "score": res.score,
            "score_basis": res.score_basis,
            "employee_average": res.employee_average,
            "sample_size": res.sample_size,
            "unavailable_reason": res.unavailable_reason,
        }

    depts_out: dict[str, dict[str, Any]] = {}
    for dname, drecs in sorted(by_dept.items()):
        res = official_department_score(dname, drecs, measure=measure, location=location)
        depts_out[dname] = {
            "score": res.score,
            "score_basis": res.score_basis,
            "employee_average": res.employee_average,
            "sample_size": res.sample_size,
            "unavailable_reason": res.unavailable_reason,
        }

    scope_hash = hashlib.sha256(
        json.dumps(canonical_scope_identity(scope), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]

    return {
        "region": region,
        "performance_level": level,
        "period": period_key,
        "measure": measure,
        "teams": teams_out,
        "departments": depts_out,
        "metadata": {
            "scope_hash": scope_hash,
            "upload_revision": CacheInvalidationService.get_data_version(),
            "settings_revision": CacheInvalidationService.get_config_version(),
            "evaluation_identity": evaluation_cache_identity(db) if db is not None else "no_db",
        },
    }
