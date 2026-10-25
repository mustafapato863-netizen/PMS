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
3. reads the index newest first in SQL (ORDER BY year DESC, month number
   DESC, id DESC, LIMIT/OFFSET pages) and resolves matching keys only until
   the cap (``limit``, default and maximum 50,000) is reached; the rest are
   only counted for X-Total-Count. Only a truncated response is reordered
   (oldest first, the reverse of the fetch, as on the legacy path); one that
   fits under the cap keeps the exact pre-change row order.

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
from utils.months import month_number
from utils.report_scope import filter_records_by_scope, filter_records_by_team_levels
from utils.team_identity import logical_team_name

logger = logging.getLogger(__name__)

RESOLVE_CHUNK = 500
# Default and maximum rows per response (the API max is the same 50k).
SUMMARY_RECORDS_CAP = 50_000
# Light index rows read per ORDER BY ... LIMIT/OFFSET page.
INDEX_PAGE = 5_000
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
    region: str | None = None

    @property
    def month_key(self) -> str | None:
        return self.month.strip().casefold() if self.month and self.month.strip() else None

    @property
    def team_key(self) -> str | None:
        return self.team.strip().casefold() if self.team and self.team.strip() else None

    @property
    def region_key(self) -> str | None:
        return self.region.strip().casefold() if self.region and self.region.strip() else None


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
    if filters.team_key and str(_field(record, "team") or "").strip().casefold() != filters.team_key:
        return False
    return not (filters.region_key and str(_field(record, "region") or "").strip().casefold() != filters.region_key)


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
    if filters.region_key:
        # Same predicate as the dashboard list: record, then employee, then team.
        sql_filters["region"] = filters.region.strip()
    # employee_id predates this path and the frontend relies on its row order,
    # which is the unfiltered query's natural order; it is applied to the light
    # index rows (still before any payload is resolved) instead of in SQL, where
    # an extra predicate can change the plan and therefore the row order.

    cap = SUMMARY_RECORDS_CAP if limit is None else min(limit, SUMMARY_RECORDS_CAP)

    def authorize(rows):
        allowed = filter_records_by_team_levels(filter_records_by_scope(list(rows), scope), scope)
        return [row for row in allowed if matches(row, filters)]

    management_payloads = [
        payload for payload in (to_payload(record) for record in authorize(
            ManagementBSCService(db).list_analysis_records())) if payload is not None
    ]

    # Fits under the cap (the normal case): the response is exactly the
    # pre-change one, in the index's natural row order, nothing sorted.
    index = index_loader(**sql_filters)
    if index is None:
        return None
    candidates = authorize(index)
    if len(candidates) + len(management_payloads) <= cap:
        data: list[dict] = []
        for start in range(0, len(candidates), RESOLVE_CHUNK):
            chunk = candidates[start:start + RESOLVE_CHUNK]
            resolved = keys_loader([(uuid.UUID(hex=row.record_key[0]), row.record_key[1]) for row in chunk])
            if resolved is None:
                return None
            for record in resolved:
                if matches(record, filters):
                    payload = to_payload(record)
                    if payload is not None:
                        data.append(payload)
        data.extend(management_payloads)
        return SummaryResult(data=data, truncated=False, total=len(data))
    del index, candidates

    # Over the cap: the newest rows are chosen in SQL (ORDER BY ... LIMIT
    # pages) and only those are resolved; returned oldest first.
    try:
        first_page = index_loader(**sql_filters, newest_first=True, limit=INDEX_PAGE, offset=0)
    except TypeError:  # an index loader without ordering support
        return None
    if first_page is None:
        return None
    management = sorted(management_payloads, key=order_key, reverse=True)
    kept: list[dict] = []
    overflow = 0
    next_management = 0

    def take(payload: dict) -> None:
        nonlocal overflow
        if len(kept) < cap:
            kept.append(payload)
        else:
            overflow += 1

    page, offset = first_page, 0
    while True:
        offset += len(page)
        rows = authorize(page)
        if len(kept) >= cap:
            # Already full: count the remaining candidates for X-Total-Count
            # without resolving them (score is NOT NULL, so each has a payload).
            overflow += len(rows)
        else:
            for start in range(0, len(rows), RESOLVE_CHUNK):
                chunk = rows[start:start + RESOLVE_CHUNK]
                if len(kept) >= cap:
                    overflow += len(chunk)
                    continue
                resolved = keys_loader([(uuid.UUID(hex=row.record_key[0]), row.record_key[1]) for row in chunk])
                if resolved is None:
                    return None
                for record in resolved:
                    if not matches(record, filters):
                        continue
                    payload = to_payload(record)
                    if payload is None:
                        continue
                    key = order_key(payload)
                    while next_management < len(management) and order_key(management[next_management]) > key:
                        take(management[next_management])
                        next_management += 1
                    take(payload)
        if len(page) < INDEX_PAGE:
            break
        page = index_loader(**sql_filters, newest_first=True, limit=INDEX_PAGE, offset=offset)
        if page is None:
            return None
    for payload in management[next_management:]:
        take(payload)
    result = SummaryResult(data=kept[::-1], truncated=overflow > 0, total=len(kept) + overflow)
    if result.truncated:
        _log_truncation(result, limit)
    return result


def order_key(payload: dict) -> tuple[int, int, str]:
    """(year, month number, id): the SQL ORDER BY of the index, ascending."""
    year, month = period_key(payload)
    return year, month, str(payload.get("id") or "")


def period_key(payload: dict) -> tuple[int, int]:
    """(year, month number); unknown parts sort oldest."""
    try:
        year = int(str(payload.get("year") or "").strip())
    except ValueError:
        year = 0
    return year, month_number(payload.get("month"))


def _log_truncation(result: SummaryResult, limit: int | None) -> None:
    logger.warning(
        "summary-records truncated: returned %d of %d rows (limit=%s, cap=%d, oldest kept period=%s)",
        len(result.data), result.total, limit, SUMMARY_RECORDS_CAP,
        period_key(result.data[0]) if result.data else None,
    )


def apply_limit(data: list[dict], limit: int | None) -> SummaryResult:
    """Legacy-path twin: unchanged when within the cap; otherwise the newest
    ``limit`` (default and maximum SUMMARY_RECORDS_CAP) rows, ascending by order_key."""
    cap = SUMMARY_RECORDS_CAP if limit is None else min(limit, SUMMARY_RECORDS_CAP)
    if len(data) <= cap:
        return SummaryResult(data=data, truncated=False, total=len(data))
    result = SummaryResult(data=sorted(data, key=order_key)[-cap:], truncated=True, total=len(data))
    _log_truncation(result, limit)
    return result
