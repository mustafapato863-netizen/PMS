"""Query-level filtering for /api/performance/summary-records.

The legacy path resolved every authorized record (payload, KPI values) and
filtered in Python, which produced multi-megabyte responses and long-held
connections. This path:

1. reads the light record index with year/month/team/employee pushed into the
   SQL WHERE clause (plain ``IN``/``=`` predicates on raw columns);
2. applies the *same* scope functions (filter_records_by_scope then
   filter_records_by_team_levels) to the light rows that the legacy path
   applies to full records, exactly as the Insights period window does;
   The new year/month/team filters have no existing callers, so their rows
   come back in the filtered query's natural order (same set as before).
3. resolves only the matching keys, in index order, in chunks. Nothing is
   dropped by default; an explicit ``limit`` keeps the newest periods
   (see apply_limit) and is reported through X-Result-Truncated.

The Branch Director scope (and any repository without the index) falls back to the legacy path by returning ``None``.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from models.models import Team
from services.management_bsc_service import ManagementBSCService
from utils.report_scope import filter_records_by_scope, filter_records_by_team_levels
from utils.team_identity import logical_team_name

logger = logging.getLogger(__name__)

RESOLVE_CHUNK = 500
# Branch Director reads the source row's branch marker, so it stays on the
# legacy path. Regional Manager uses the fast path: the light index and the
# resolved records share the record -> employee -> team region fallback.
LEGACY_PATH_ROLES = frozenset({"Branch Director"})


@dataclass
class SummaryFilters:
    employee_id: str | None = None
    year: int | None = None
    month: str | None = None
    team: str | None = None

    @property
    def month_key(self) -> str | None:
        return self.month.strip().casefold() if self.month and self.month.strip() else None

    @property
    def team_key(self) -> str | None:
        return self.team.strip().casefold() if self.team and self.team.strip() else None


@dataclass
class SummaryResult:
    data: list[dict]
    truncated: bool
    total: int | None  # exact count when every candidate was resolved


def _field(record: Any, name: str):
    if isinstance(record, dict):
        return record.get(name)
    return getattr(record, name, None)


def matches(record: Any, filters: SummaryFilters) -> bool:
    """The legacy per-record predicate, unchanged."""
    if filters.employee_id and str(_field(record, "employee_id")) != filters.employee_id:
        return False
    if filters.year is not None and _field(record, "year") not in (filters.year, str(filters.year)):
        return False
    if filters.month_key and str(_field(record, "month") or "").strip().casefold() != filters.month_key:
        return False
    return not (filters.team_key and str(_field(record, "team") or "").strip().casefold() != filters.team_key)


def to_payload(record: Any) -> dict | None:
    payload = dict(record) if isinstance(record, dict) else record.model_dump(mode="json")
    if (payload.get("evaluation") or {}).get("score") is None:
        return None
    return payload


def _month_spellings(month: str) -> list[str]:
    raw = month.strip()
    return sorted({raw, raw.casefold(), raw.lower(), raw.upper(), raw.title(), raw.capitalize()} - {""})


def summary_records_indexed(
    db: Session,
    record_service: Any,
    scope: dict,
    filters: SummaryFilters,
    limit: int | None = None,
) -> SummaryResult | None:
    if scope.get("role") in LEGACY_PATH_ROLES:
        return None
    index_loader = getattr(record_service, "list_record_index", None)
    keys_loader = getattr(record_service, "list_records_by_keys", None)
    if not callable(index_loader) or not callable(keys_loader):
        return None

    sql_filters: dict[str, Any] = {}
    if filters.year is not None:
        sql_filters["year"] = filters.year
    if filters.month_key:
        sql_filters["months"] = _month_spellings(filters.month)
    if filters.team_key:
        sql_filters["team_names"] = sorted({
            team.name for team in db.query(Team).all() if logical_team_name(team).strip().casefold() == filters.team_key
        })
    # employee_id predates this path and the frontend relies on its row order,
    # which is the unfiltered query's natural order; it is applied to the light
    # index rows (still before any payload is resolved) instead of in SQL, where
    # an extra predicate can change the plan and therefore the row order.
    index = index_loader(**sql_filters)
    if index is None:
        return None

    management_records = ManagementBSCService(db).list_analysis_records()
    authorized = filter_records_by_team_levels(
        filter_records_by_scope([*index, *management_records], scope), scope,
    )
    index_ids = {id(row) for row in index}
    employee_rows = [row for row in authorized if id(row) in index_ids and matches(row, filters)]
    management = [row for row in authorized if id(row) not in index_ids and matches(row, filters)]

    data: list[dict] = []
    for start in range(0, len(employee_rows), RESOLVE_CHUNK):
        chunk = employee_rows[start:start + RESOLVE_CHUNK]
        resolved = keys_loader([(uuid.UUID(hex=row.record_key[0]), row.record_key[1]) for row in chunk])
        if resolved is None:
            return None
        for record in resolved:
            if not matches(record, filters):
                continue
            payload = to_payload(record)
            if payload is not None:
                data.append(payload)
    for record in management:
        payload = to_payload(record)
        if payload is not None:
            data.append(payload)
    return apply_limit(data, limit)


_MONTHS = {
    name: number
    for number, names in enumerate(
        [
            ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"),
            ("may",), ("june", "jun"), ("july", "jul"), ("august", "aug"),
            ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"), ("december", "dec"),
        ],
        start=1,
    )
    for name in names
}


def period_key(payload: dict) -> tuple[int, int]:
    """(year, month number) for newest-first ordering; unknown parts sort oldest."""
    try:
        year = int(str(payload.get("year") or "").strip())
    except ValueError:
        year = 0
    month_raw = str(payload.get("month") or "").strip().casefold()
    month = _MONTHS.get(month_raw)
    if month is None:
        month = int(month_raw) if month_raw.isdigit() and 1 <= int(month_raw) <= 12 else 0
    return year, month


def apply_limit(data: list[dict], limit: int | None) -> SummaryResult:
    """No limit: everything. With a limit: keep the newest ``limit`` rows by
    (year, month), preserving their original response order; ties within a
    period keep the earlier rows."""
    total = len(data)
    if limit is None or total <= limit:
        return SummaryResult(data=data, truncated=False, total=total)
    ranked = sorted(range(total), key=lambda i: period_key(data[i]), reverse=True)
    # sorted() is stable, but reverse=True keeps equal keys in original order too.
    keep = sorted(ranked[:limit])
    kept = [data[i] for i in keep]
    logger.warning(
        "summary-records truncated: returned %d of %d rows (limit=%d, oldest kept period=%s)",
        len(kept), total, limit, period_key(data[ranked[limit - 1]]),
    )
    return SummaryResult(data=kept, truncated=True, total=total)
