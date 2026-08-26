"""Pure data adapter for the UAE/Offshore EGY status-dashboard export.

The PowerPoint renderer consumes this normalized payload instead of knowing
anything about SQLAlchemy or the shape of uploaded workbook evidence.  The
adapter intentionally uses only the already scoped canonical report records.
"""

from __future__ import annotations

import re
from collections import Counter, OrderedDict
from typing import Any


COMPLETED = "Completed & Running"
PENDING = "Pending Manager Review"
NOT_MEASURED = "Not Measured"
MISSING = "\u2014"
POSITION_STATUSES = ("Current", "Vacant", "Hold")
KPI_STATUSES = (COMPLETED, PENDING, NOT_MEASURED)


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    cleaned = " ".join(str(value).replace("\n", " ").split()).strip()
    return cleaned or fallback


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _text(value).casefold()).strip()


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _count_label(value: Any, singular: str) -> str:
    number = _number(value)
    if number is None:
        return f"{MISSING} {singular}s"
    count = int(number)
    return f"{count:,} {singular if count == 1 else singular + 's'}"


def _raw_maps(record: Any) -> list[dict[str, Any]]:
    raw = _value(record, "raw_data", {})
    maps = [raw] if isinstance(raw, dict) else []
    nested = raw.get("data") if isinstance(raw, dict) else None
    if isinstance(nested, dict):
        maps.append(nested)
    return maps


def _raw_value(record: Any, *keys: str) -> Any:
    wanted = {_norm(key) for key in keys}
    for mapping in _raw_maps(record):
        normalized = {_norm(key): value for key, value in mapping.items()}
        for key in wanted:
            if key in normalized and normalized[key] not in (None, ""):
                return normalized[key]
    return None


def _normalize_kpi_status(value: Any) -> str | None:
    normalized = _norm(value)
    if not normalized:
        return None
    if normalized in {
        "completed running",
        "completed and running",
        "completed",
        "complete",
        "running",
        "measured",
        "active",
    }:
        return COMPLETED
    if normalized in {
        "pending manager review",
        "pending review",
        "manager review",
        "awaiting manager review",
        "awaiting manager",
        "pending",
        "under review",
    }:
        return PENDING
    if normalized in {
        "not measured",
        "not measure",
        "unmeasured",
        "not available",
        "missing",
        "no data",
    }:
        return NOT_MEASURED
    return None


def _record_kpi_status(record: Any) -> str:
    explicit = _raw_value(
        record,
        "kpi_status",
        "KPI Status",
        "measurement_status",
        "Measurement Status",
        "review_status",
        "Review Status",
        "status_bucket",
        "Status Bucket",
        "manager_review_status",
        "Manager Review Status",
    )
    normalized = _normalize_kpi_status(explicit)
    if normalized:
        return normalized

    # Some source rows already carry the reference vocabulary in `status`.
    normalized = _normalize_kpi_status(_value(record, "status"))
    if normalized:
        return normalized

    evaluation = _value(record, "evaluation")
    score = _value(evaluation, "score")
    kpis = _value(record, "kpi_values", []) or []
    has_measured_kpi = any(
        _value(kpi, "actual_value") is not None or _value(kpi, "achievement_ratio") is not None
        for kpi in kpis
    )
    return COMPLETED if score is not None or has_measured_kpi else NOT_MEASURED


def _normalize_position_status(value: Any) -> str | None:
    normalized = _norm(value)
    if not normalized:
        return None
    if "vacant" in normalized or "vacancy" in normalized:
        return "Vacant"
    if "hold" in normalized or "on hold" in normalized:
        return "Hold"
    if normalized in {"current", "active", "filled", "occupied"}:
        return "Current"
    return None


def _record_position_status(record: Any) -> str:
    explicit = _raw_value(
        record,
        "position_status",
        "Position Status",
        "occupancy_status",
        "Occupancy Status",
        "vacancy_status",
        "Vacancy Status",
        "position_state",
        "Position State",
    )
    status = _normalize_position_status(explicit)
    if status:
        return status

    name = _text(_value(record, "employee_name"))
    if _normalize_position_status(name):
        return _normalize_position_status(name) or "Vacant"
    employee_id = _text(_value(record, "employee_id"))
    return "Vacant" if not name and not employee_id else "Current"


def _is_placeholder_name(name: str) -> bool:
    normalized = _norm(name)
    return normalized in {"vacant", "hold", "on hold", "unassigned", "not assigned"}


def _explicit_count(record: Any) -> int | None:
    value = _raw_value(record, "cnt", "count", "headcount", "employee_count", "position_count")
    number = _number(value)
    if number is None or number < 0:
        return None
    return int(number)


def _status_priority(status: str) -> int:
    return {NOT_MEASURED: 0, PENDING: 1, COMPLETED: 2}.get(status, 0)


def _aggregate_status(statuses: list[str]) -> str:
    if not statuses:
        return NOT_MEASURED
    return min(statuses, key=_status_priority)


def _aggregate_position_status(statuses: list[str], has_real_employee: bool) -> str:
    if has_real_employee or "Current" in statuses:
        return "Current"
    if "Hold" in statuses:
        return "Hold"
    return "Vacant"


def build_offshore_status_payload(
    records: list[Any],
    *,
    period_label: str,
    region_label: str,
    scope_label: str = "All authorized teams",
) -> dict[str, Any]:
    """Aggregate canonical records into the reference deck's dashboard model."""

    groups: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
    for record in records:
        department = _text(_value(record, "team"), "Unassigned")
        position = _text(
            _value(record, "position") or _value(record, "position_name"),
            "Unassigned",
        )
        key = (_norm(department), _norm(position))
        group = groups.setdefault(
            key,
            {
                "department": department,
                "position": position,
                "position_statuses": [],
                "kpi_statuses": [],
                "employee_ids": [],
                "employee_names": [],
                "explicit_counts": [],
                "first_seen": len(groups),
            },
        )
        position_status = _record_position_status(record)
        group["position_statuses"].append(position_status)
        group["kpi_statuses"].append(_record_kpi_status(record))
        if (count := _explicit_count(record)) is not None:
            group["explicit_counts"].append(count)

        employee_id = _text(_value(record, "employee_id"))
        employee_name = _text(_value(record, "employee_name"))
        if employee_id and not _is_placeholder_name(employee_name):
            if employee_id not in group["employee_ids"]:
                group["employee_ids"].append(employee_id)
        if employee_name and not _is_placeholder_name(employee_name):
            if employee_name.casefold() not in {name.casefold() for name in group["employee_names"]}:
                group["employee_names"].append(employee_name)

    detail_rows: list[dict[str, Any]] = []
    for group in groups.values():
        has_real_employee = bool(group["employee_ids"] or group["employee_names"])
        position_status = _aggregate_position_status(group["position_statuses"], has_real_employee)
        employee_count = len(group["employee_ids"]) or len(group["employee_names"])
        if group["explicit_counts"]:
            employee_count = max(employee_count, max(group["explicit_counts"]))
        employee_count = employee_count or 1
        detail_rows.append(
            {
                "department": group["department"],
                "position": group["position"],
                "count": employee_count,
                "position_status": position_status,
                "kpi_status": _aggregate_status(group["kpi_statuses"]),
                "employee_names": sorted(group["employee_names"], key=str.casefold)
                if _norm(group["department"]) == "marketing"
                else [],
                "first_seen": group["first_seen"],
            }
        )

    department_groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for row in detail_rows:
        department = row["department"]
        department_key = _norm(department)
        summary = department_groups.setdefault(
            department_key,
            {"department": department, "rows": [], "first_seen": len(department_groups)},
        )
        summary["rows"].append(row)

    departments: list[dict[str, Any]] = []
    for summary in department_groups.values():
        rows = summary["rows"]
        running = sum(row["kpi_status"] == COMPLETED for row in rows)
        pending = sum(row["kpi_status"] == PENDING for row in rows)
        not_measured = sum(row["kpi_status"] == NOT_MEASURED for row in rows)
        total = len(rows)
        measured = running + pending
        departments.append(
            {
                "department": summary["department"],
                "total": total,
                "measured": measured,
                "running": running,
                "pending": pending,
                "not_measured": not_measured,
                "progress": (measured / total * 100.0) if total else None,
                "first_seen": summary["first_seen"],
            }
        )

    departments.sort(
        key=lambda item: (
            -(item["progress"] if item["progress"] is not None else -1),
            item["first_seen"],
            item["department"].casefold(),
        )
    )
    department_rank = {item["department"].casefold(): index for index, item in enumerate(departments)}
    detail_rows.sort(
        key=lambda row: (
            department_rank.get(row["department"].casefold(), 999),
            row["first_seen"],
            _status_priority(row["kpi_status"]),
            row["position"].casefold(),
        )
    )

    status_counts = Counter(row["kpi_status"] for row in detail_rows)
    position_status_counts = Counter(row["position_status"] for row in detail_rows)
    total_positions = len(detail_rows)
    measured_positions = status_counts[COMPLETED] + status_counts[PENDING]
    measured_rate = measured_positions / total_positions * 100.0 if total_positions else None
    queue = Counter(
        row["department"]
        for row in detail_rows
        if row["kpi_status"] == PENDING
    )
    manager_queue = [
        {"department": department, "count": count}
        for department, count in sorted(queue.items(), key=lambda item: (-item[1], item[0].casefold()))
    ]
    exceptions = [
        {
            "department": row["department"],
            "position": row["position"],
            "position_status": row["position_status"],
            "kpi_status": row["kpi_status"],
        }
        for row in detail_rows
        if row["kpi_status"] == NOT_MEASURED
    ]

    complete_departments = sum(
        item["total"] > 0 and item["progress"] == 100.0 for item in departments
    )
    lowest_department = min(
        departments,
        key=lambda item: (
            item["progress"] if item["progress"] is not None else 101,
            item["department"].casefold(),
        ),
        default=None,
    )
    findings = [
        f"{_count_label(complete_departments, 'department')} at 100% measured completion",
        (
            f"{lowest_department['department']} lowest at {lowest_department['progress']:.0f}%"
            if lowest_department and lowest_department["progress"] is not None
            else "No department progress is available"
        ),
        f"{_count_label(status_counts[PENDING], 'part')} awaiting manager review",
        f"{_count_label(status_counts[NOT_MEASURED], 'part')} not yet measured",
        f"{_count_label(position_status_counts['Vacant'], 'vacant part')} under tracking",
    ]

    return {
        "region_label": region_label,
        "period_label": period_label,
        "scope_label": scope_label,
        "total_positions": total_positions,
        "department_count": len(departments),
        "measured_rate": measured_rate,
        "status_counts": {status: status_counts[status] for status in KPI_STATUSES},
        "position_status_counts": {
            status: position_status_counts[status] for status in POSITION_STATUSES
        },
        "departments": departments,
        "exceptions": exceptions,
        "manager_queue": manager_queue,
        "detail_rows": detail_rows,
        "findings": findings,
    }
