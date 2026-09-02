"""Bounded, scope-aware read services for the performance dashboard."""

from __future__ import annotations

import base64
import hashlib
import json
import random
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from models.report_schemas import MONTHS
from models.schemas import EvaluationData, PerformanceRecord as SummaryRecord
from models.models import PerformanceRecord
from repositories.performance_repository import PerformanceRepository
from services.cache_invalidation_service import CacheInvalidationService
from services.cache_service import CacheService
from services.dashboard_record_service import DashboardRecordService


_MONTH_BY_NUMBER = {number: name for name, number in MONTHS.items()}
_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})$")
_LOCATION_KEYS = {"all", "dubai", "sharjah", "ajman", "clinics"}


def parse_period(value: str) -> tuple[int, str]:
    match = _PERIOD_RE.fullmatch(str(value or "").strip())
    if not match:
        raise HTTPException(status_code=422, detail="period must use YYYY-MM format")
    year, month_number = int(match.group(1)), int(match.group(2))
    if not 2000 <= year <= 2100 or month_number not in _MONTH_BY_NUMBER:
        raise HTTPException(status_code=422, detail="period must contain a valid month and year")
    return year, _MONTH_BY_NUMBER[month_number]


def period_key(year: int, month: str) -> str:
    return f"{year:04d}-{MONTHS[month]:02d}"


def _periods_ending(year: int, month: str, count: int) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    current_year, current_month = year, MONTHS[month]
    for _ in range(max(1, count)):
        result.append((current_year, _MONTH_BY_NUMBER[current_month]))
        current_month -= 1
        if current_month == 0:
            current_year -= 1
            current_month = 12
    return result


def _period_ref(year: int, month: str) -> dict[str, Any]:
    return {"key": period_key(year, month), "month": month, "year": year}


def _number(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, str):
        value = value.strip().replace("%", "")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def _scope_identity(scope: dict) -> dict[str, Any]:
    return {
        "user_id": str(scope.get("user_id") or ""),
        "role": str(scope.get("role") or ""),
        "employee_id": str(scope.get("employee_id") or ""),
        "is_general_manager": bool(scope.get("is_general_manager")),
        "is_self_only": bool(scope.get("is_self_only")),
        "accessible_teams": sorted(str(item) for item in scope.get("accessible_teams") or []),
        "accessible_team_levels": sorted(
            (str(team), str(level))
            for team, level in scope.get("accessible_team_levels") or []
        ),
    }


def _record_location(record, location: str) -> bool:
    normalized = str(location or "all").strip().casefold()
    if normalized not in _LOCATION_KEYS:
        raise HTTPException(status_code=422, detail="location must be all, dubai, sharjah, ajman, or clinics")
    if normalized == "all":
        return True

    raw = record.raw_data or {}
    branch_text = " ".join(
        str(raw.get(key) or "")
        for key in ("Team", "Out Team", "Branch", "Site", "Area")
    ).upper()
    identity_team = str(record.team or "").upper()
    explicit = None
    if "AJM" in branch_text or "AJMAN" in branch_text:
        explicit = "ajman"
    elif "SHJ" in branch_text or "SHARJAH" in branch_text or "SHARQA" in branch_text:
        explicit = "sharjah"
    elif "DUBAI" in branch_text or "DUBAI" in identity_team:
        explicit = "dubai"
    elif "CLINIC" in branch_text:
        explicit = "clinics"
    if explicit:
        return explicit == normalized

    geo = record.geo
    return (
        _number(getattr(geo.bookings, normalized, 0)) > 0
        or _number(getattr(geo.attended, normalized, 0)) > 0
    )


def _has_real_activity(record) -> bool:
    if str(record.employee_name or "").strip().casefold() == "total":
        return False
    if _number(record.evaluation.score) > 0:
        return True
    if any(_number(value.get("contribution")) > 0 for value in record.kpi_values or []):
        return True
    if any(
        _number(value) > 0
        for value in (
            record.calls.inbound,
            record.calls.outbound,
            record.calls.total_handled,
            record.calls.abandoned,
            record.geo.bookings.dubai,
            record.geo.bookings.sharjah,
            record.geo.bookings.ajman,
            record.geo.bookings.clinics,
            record.geo.attended.dubai,
            record.geo.attended.sharjah,
            record.geo.attended.ajman,
            record.geo.attended.clinics,
        )
    ):
        return True
    return any(_number(value) > 0 for value in (record.raw_data or {}).values())


def _score(record) -> float:
    score = _number(record.evaluation.score)
    return score * 100 if 0 < score <= 10 else score


def _stored_score(record) -> float:
    """Return the relational score scale used by SQL cursor predicates."""
    score = _number(getattr(record, "score", 0))
    return score * 100 if 0 < score <= 10 else score


def _grade(record, score: float) -> str:
    raw = str(record.evaluation.grade or "").strip().upper()
    if raw and raw[0] in "ABCDE":
        return raw[0]
    return "A" if score >= 95 else "B" if score >= 85 else "C" if score >= 75 else "D" if score >= 65 else "E"


def _active_records(records: Iterable, location: str) -> list:
    return [record for record in records if _has_real_activity(record) and _record_location(record, location)]


def _summary_record(row: dict[str, Any]) -> SummaryRecord:
    """Build the summary model from scalar columns plus the JSON evidence payload."""
    payload = row.get("record_payload")
    rich_record = None
    if isinstance(payload, dict):
        try:
            rich_record = SummaryRecord.model_validate(payload)
        except ValidationError:
            rich_record = None

    score = _number(row.get("score"))
    grade = str(row.get("grade") or "E")
    if rich_record is None:
        rich_record = SummaryRecord(
            id=str(row.get("record_id") or ""),
            employee_id=str(row.get("employee_id") or ""),
            employee_name=str(row.get("employee_name") or ""),
            team=str(row.get("team") or ""),
            month=str(row.get("month") or ""),
            year=int(row.get("year")) if row.get("year") is not None else None,
            region=str(row.get("region") or "EGY"),
            performance_level=str(row.get("performance_level") or "Employee"),
            position=str(row.get("position")) if row.get("position") else None,
            status=str(row.get("status")) if row.get("status") else None,
            evaluation=EvaluationData(score=score, grade=grade),
            raw_data=payload.get("raw_data", {}) if isinstance(payload, dict) and isinstance(payload.get("raw_data"), dict) else {},
            kpi_values=payload.get("kpi_values", []) if isinstance(payload, dict) and isinstance(payload.get("kpi_values"), list) else [],
        )

    return rich_record.model_copy(update={
        "id": str(row.get("record_id") or rich_record.id),
        "employee_id": str(row.get("employee_id") or rich_record.employee_id),
        "employee_name": str(row.get("employee_name") or rich_record.employee_name),
        "team": str(row.get("team") or rich_record.team),
        "month": str(row.get("month") or rich_record.month),
        "year": int(row.get("year")) if row.get("year") is not None else rich_record.year,
        "region": row.get("region") or rich_record.region,
        "performance_level": str(row.get("performance_level") or rich_record.performance_level),
        "position": row.get("position") or rich_record.position,
        "status": row.get("status") or rich_record.status,
        "evaluation": rich_record.evaluation.model_copy(update={"score": score, "grade": grade}),
    })


def _geo_total(record, field: str, location: str) -> float:
    values = getattr(getattr(record, "geo"), field)
    if location == "all":
        return sum(_number(getattr(values, key, 0)) for key in ("dubai", "sharjah", "ajman", "clinics"))
    return _number(getattr(values, location, 0))


def _summary(records: list, location: str) -> dict[str, Any]:
    current = _active_records(records, location)
    grade_counts = {grade: 0 for grade in "ABCDE"}
    status_counts: dict[str, int] = {}
    inbound = outbound = handled = abandoned = bookings = attended = 0.0
    total_aht_seconds = 0.0
    score_total = 0.0
    on_track = at_risk = critical = 0

    for record in current:
        score = _score(record)
        grade_counts[_grade(record, score)] += 1
        status = str(record.status or "").strip() or "Unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
        inbound += _number(record.calls.inbound)
        outbound += _number(record.calls.outbound)
        handled += _number(record.calls.total_handled)
        abandoned += _number(record.calls.abandoned)
        bookings += _geo_total(record, "bookings", location)
        attended += _geo_total(record, "attended", location)
        score_total += score
        if score >= 100:
            on_track += 1
        elif score >= 70:
            at_risk += 1
        else:
            critical += 1
        raw_aht = str(record.calls.aht_raw or "00:00:00").split(":")
        if len(raw_aht) == 3:
            total_aht_seconds += _number(raw_aht[0]) * 3600 + _number(raw_aht[1]) * 60 + _number(raw_aht[2])

    total_agents = len(current)
    booking_rate = bookings / handled if handled > 0 else 0.0
    attend_rate = attended / bookings if bookings > 0 else 0.0
    abandon_rate = abandoned / handled if handled > 0 else 0.0
    return {
        "total_agents": total_agents,
        "total_records": len(current),
        "average_score": round(score_total / total_agents, 2) if total_agents else 0.0,
        "weighted_score": round(score_total / total_agents, 2) if total_agents else 0.0,
        "on_track_count": on_track,
        "at_risk_count": at_risk,
        "critical_count": critical,
        "grade_counts": grade_counts,
        "status_counts": status_counts,
        "totals": {
            "inbound": int(inbound),
            "outbound": int(outbound),
            "total_handled": int(handled),
            "abandoned": int(abandoned),
            "bookings": int(bookings),
            "attended": int(attended),
        },
        "rates": {
            "booking_rate": round(booking_rate, 6),
            "attend_rate": round(attend_rate, 6),
            "abandon_rate": round(abandon_rate, 6),
            "average_aht_seconds": round(total_aht_seconds / total_agents, 2) if total_agents else 0.0,
        },
    }


def _team_breakdown(records: list, location: str) -> list[dict[str, Any]]:
    buckets: dict[str, list] = {}
    for record in _active_records(records, location):
        team = str(record.team or "Unknown").strip() or "Unknown"
        buckets.setdefault(team, []).append(record)

    result = []
    for team, rows in buckets.items():
        scores = [_score(row) for row in rows]
        counts = {grade: 0 for grade in "ABCDE"}
        for row, score in zip(rows, scores):
            counts[_grade(row, score)] += 1
        team_id = re.sub(r"[^a-z0-9]+", "-", team.casefold()).strip("-") or "unknown"
        result.append({
            "teamId": team_id,
            "teamName": team,
            "agentCount": len({str(row.employee_id) for row in rows}),
            "avgScore": round(sum(scores) / len(scores), 2) if scores else 0.0,
            "classA": counts["A"],
            "classB": counts["B"],
            "classC": counts["C"],
            "classD": counts["D"],
            "classE": counts["E"],
        })
    return sorted(result, key=lambda item: item["avgScore"], reverse=True)


def encode_cursor(value: dict[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        padded = str(value) + "=" * (-len(str(value)) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        if not isinstance(decoded, dict):
            raise ValueError
        return decoded
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="cursor is invalid")


class PerformanceDashboardReadService:
    """Application service for bounded, cacheable dashboard read contracts."""

    def __init__(self, db: Session, scope: dict):
        self.db = db
        self.scope = scope
        self.records = DashboardRecordService(db, sql_repository_cls=PerformanceRepository)
        self.repository = PerformanceRepository(db, PerformanceRecord)

    def _cache_key(self, endpoint: str, filters: dict[str, Any]) -> str:
        data_version = CacheInvalidationService.get_data_version()
        config_version = CacheInvalidationService.get_config_version()
        payload = {
            "endpoint": endpoint,
            "filters": filters,
            "scope": _scope_identity(self.scope),
            "data_version": data_version,
            "config_version": config_version,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        return f"pms:v1:performance:{endpoint}:{digest}"

    @staticmethod
    def _ttl(seconds: int) -> int:
        return max(1, int(round(seconds * random.uniform(0.9, 1.1))))

    def summary(
        self,
        *,
        period: str,
        team: str | None = None,
        performance_level: str | None = None,
        region: str | None = None,
        position: str | None = None,
        employee_id: str | None = None,
        location: str = "all",
        trend_months: int = 12,
        grade: str | None = None,
        status: str | None = None,
        kpi: str | None = None,
    ) -> dict[str, Any]:
        year, month = parse_period(period)
        if not 1 <= trend_months <= 24:
            raise HTTPException(status_code=422, detail="trend_months must be between 1 and 24")
        filters = {
            "period": period,
            "team": team,
            "performance_level": performance_level,
            "region": region,
            "position": position,
            "location": location,
            "trend_months": trend_months,
            "employee_id": employee_id,
            "grade": grade,
            "status": status,
            "kpi": kpi,
        }
        key = self._cache_key("summary", filters)
        cached = CacheService.get_json(key, cache_type="performance_summary")
        if cached is not None:
            return cached

        periods = _periods_ending(year, month, trend_months)
        summary_rows = self.repository.get_dashboard_summary_rows(
            team=team,
            performance_level=performance_level,
            position=position,
            region=region,
            employee_id=employee_id,
            grade=grade,
            status=status,
            kpi=kpi,
            periods=periods,
            scope=self.scope,
        )
        rows = [_summary_record(row) for row in summary_rows]
        by_period: dict[str, list] = {period_key(row_year, row_month): [] for row_year, row_month in periods}
        for row in rows:
            by_period.setdefault(period_key(int(row.year), str(row.month)), []).append(row)

        current_key = period_key(year, month)
        current = _summary(by_period.get(current_key, []), location)
        previous_period = None
        previous = None
        for candidate_year, candidate_month in periods[1:]:
            candidate_key = period_key(candidate_year, candidate_month)
            if by_period.get(candidate_key):
                previous_period = _period_ref(candidate_year, candidate_month)
                previous = _summary(by_period[candidate_key], location)
                break

        trend = []
        for trend_year, trend_month in reversed(periods):
            trend_key = period_key(trend_year, trend_month)
            if by_period.get(trend_key):
                trend.append({
                    **_period_ref(trend_year, trend_month),
                    **_summary(by_period[trend_key], location),
                })

        data = {
            "scope": {
                "period": period,
                "team": team,
                "performance_level": performance_level,
                "region": region,
                "position": position,
                "location": location,
            },
            "period": _period_ref(year, month),
            "previous_period": previous_period,
            "current": current,
            "previous": (
                {
                    **previous,
                    "team_breakdown": _team_breakdown(
                        by_period.get(period_key(previous_period["year"], previous_period["month"]), []),
                        location,
                    ),
                }
                if previous and previous_period
                else None
            ),
            "trend": trend,
            "team_breakdown": _team_breakdown(by_period.get(current_key, []), location),
            "data_version": CacheInvalidationService.get_data_version(),
            "as_of": datetime.now(timezone.utc).isoformat(),
        }
        CacheService.set_json(key, data, ttl=self._ttl(180), cache_type="performance_summary")
        return data

    def records_page(
        self,
        *,
        period: str,
        team: str | None = None,
        performance_level: str | None = None,
        region: str | None = None,
        position: str | None = None,
        employee_id: str | None = None,
        location: str = "all",
        employee_search: str | None = None,
        grade: str | None = None,
        status: str | None = None,
        sort: str = "name",
        detail: str = "table",
        cursor: str | None = None,
        page_size: int = 50,
        include_total: bool = False,
        kpi: str | None = None,
    ) -> dict[str, Any]:
        year, month = parse_period(period)
        if detail not in {"table", "full"}:
            raise HTTPException(status_code=422, detail="detail must be table or full")
        if not 1 <= page_size <= 100:
            raise HTTPException(status_code=422, detail="page_size must be between 1 and 100")
        if str(sort or "name").casefold() not in {"name", "score_desc", "score_asc"}:
            raise HTTPException(status_code=422, detail="sort must be name, score_desc, or score_asc")
        if str(location or "all").casefold() not in _LOCATION_KEYS:
            raise HTTPException(status_code=422, detail="location must be all, dubai, sharjah, ajman, or clinics")
        cursor_data = decode_cursor(cursor)
        filters = {
            "period": period,
            "team": team,
            "performance_level": performance_level,
            "region": region,
            "position": position,
            "employee_id": employee_id,
            "location": location,
            "employee_search": employee_search,
            "grade": grade,
            "status": status,
            "sort": sort,
            "detail": detail,
            "cursor": cursor_data,
            "page_size": page_size,
            "include_total": include_total,
            "kpi": kpi,
        }
        key = self._cache_key("records", filters)
        cached = CacheService.get_json(key, cache_type="performance_records")
        if cached is not None:
            return cached

        use_sql_page = str(location or "all").casefold() == "all"
        if use_sql_page:
            rows, total = self.repository.get_dashboard_record_page(
                scope=self.scope,
                team=team,
                month=month,
                employee_id=employee_id,
                year=year,
                performance_level=performance_level,
                position=position,
                region=region,
                employee_search=employee_search,
                grade=grade,
                status=status,
                kpi=kpi,
                sort=sort,
                cursor=cursor_data,
                page_size=page_size,
                include_total=include_total,
            )
            resolved = self.records.resolve_records(rows)
        else:
            all_rows = self.records.list_records(
                team=team,
                employee_id=employee_id,
                performance_level=performance_level,
                position=position,
                region=region,
                month=month,
                year=year,
                scope=self.scope,
                employee_search=employee_search,
                grade=grade,
                status=status,
                kpi=kpi,
            )
            resolved = _active_records(all_rows, location)
            if sort == "score_desc":
                resolved.sort(key=lambda row: (-_score(row), str(row.employee_name).casefold(), str(row.employee_id).casefold(), str(row.id).casefold()))
            elif sort == "score_asc":
                resolved.sort(key=lambda row: (_score(row), str(row.employee_name).casefold(), str(row.employee_id).casefold(), str(row.id).casefold()))
            else:
                resolved.sort(key=lambda row: (str(row.employee_name).casefold(), str(row.employee_id).casefold(), str(row.id).casefold()))
            total = len(resolved) if include_total else None
            if cursor_data:
                resolved = self._after_cursor(resolved, cursor_data, sort)
            rows = resolved[: page_size + 1]

        has_more = len(resolved) > page_size if use_sql_page else len(rows) > page_size
        page_rows = resolved[:page_size]
        previous_scores = self._previous_scores(
            page_rows,
            year=year,
            month=month,
            team=team,
            employee_id=employee_id,
            performance_level=performance_level,
            region=region,
            position=position,
            employee_search=employee_search,
            grade=grade,
            status=status,
        )
        items = [self._record_item(row, detail, previous_scores.get(str(row.employee_id))) for row in page_rows]
        next_cursor = None
        if has_more and page_rows:
            last = page_rows[-1]
            cursor_score = _score(last)
            if use_sql_page and rows:
                raw_page_rows = rows[:page_size]
                if raw_page_rows:
                    cursor_score = _stored_score(raw_page_rows[-1])
            next_cursor = encode_cursor({
                "sort": sort,
                "name": str(last.employee_name).casefold(),
                "employee_id": str(last.employee_id).casefold(),
                "record_id": str(last.id).casefold(),
                "score": cursor_score,
            })
        data = {
            "items": items,
            "page_size": page_size,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "total": total,
            "data_version": CacheInvalidationService.get_data_version(),
            "as_of": datetime.now(timezone.utc).isoformat(),
        }
        CacheService.set_json(key, data, ttl=self._ttl(180), cache_type="performance_records")
        return data

    def employee_history(
        self,
        *,
        employee_id: str,
        period_end: str | None = None,
        months: int = 12,
        performance_level: str | None = None,
        position: str | None = None,
        region: str | None = None,
    ) -> list[dict[str, Any]]:
        if not 1 <= months <= 24:
            raise HTTPException(status_code=422, detail="months must be between 1 and 24")
        if period_end:
            year, month = parse_period(period_end)
        else:
            latest = self.records.list_records(employee_id=employee_id, scope=self.scope)
            if not latest:
                return []
            latest.sort(key=lambda row: (int(row.year or 0), MONTHS.get(str(row.month), 0)), reverse=True)
            year, month = int(latest[0].year), str(latest[0].month)
            period_end = period_key(year, month)
        periods = _periods_ending(year, month, months)
        records = self.records.list_records(
            employee_id=employee_id,
            performance_level=performance_level,
            position=position,
            region=region,
            periods=periods,
            scope=self.scope,
        )
        records.sort(key=lambda row: (int(row.year or 0), MONTHS.get(str(row.month), 0)))
        return [self._record_item(row, "full", None) for row in records]

    def _previous_scores(self, rows: list, *, year: int, month: str, **filters) -> dict[str, float]:
        previous_periods = _periods_ending(year, month, 2)
        if len(previous_periods) < 2:
            return {}
        previous_year, previous_month = previous_periods[1]
        wanted = {str(row.employee_id) for row in rows}
        if not wanted:
            return {}
        previous = self.records.list_records(
            periods=[(previous_year, previous_month)],
            employee_ids=sorted(wanted),
            team=filters.get("team"),
            performance_level=filters.get("performance_level"),
            position=filters.get("position"),
            region=filters.get("region"),
            employee_search=filters.get("employee_search"),
            scope=self.scope,
        )
        return {str(row.employee_id): _score(row) for row in previous if str(row.employee_id) in wanted}

    @staticmethod
    def _after_cursor(rows: list, cursor: dict, sort: str) -> list:
        sort_value = str(sort or "name")
        name = str(cursor.get("name") or "")
        employee_id = str(cursor.get("employee_id") or "")
        record_id = str(cursor.get("record_id") or "")
        score = _number(cursor.get("score"))
        result = []
        for row in rows:
            row_name = str(row.employee_name).casefold()
            row_employee = str(row.employee_id).casefold()
            row_record = str(row.id).casefold()
            row_score = _score(row)
            if sort_value == "score_desc":
                after = row_score < score or (
                    row_score == score
                    and (row_name, row_employee, row_record) > (name, employee_id, record_id)
                )
            elif sort_value == "score_asc":
                after = row_score > score or (
                    row_score == score
                    and (row_name, row_employee, row_record) > (name, employee_id, record_id)
                )
            else:
                after = (row_name, row_employee, row_record) > (name, employee_id, record_id)
            if after:
                result.append(row)
        return result

    @staticmethod
    def _record_item(record, detail: str, previous_score: float | None) -> dict[str, Any]:
        score = _score(record)
        grade = _grade(record, score)
        item = {
            "id": str(record.id),
            "employee_id": str(record.employee_id),
            "employee_name": record.employee_name,
            "team": record.team,
            "month": record.month,
            "year": record.year,
            "region": record.region,
            "performance_level": record.performance_level,
            "position": record.position,
            "status": record.status,
            "score": score,
            "grade": grade,
            "previous_score": previous_score,
            "trend": None if previous_score is None else round(score - previous_score, 2),
        }
        if detail == "full":
            item.update(record.model_dump(mode="json"))
            item["score"] = score
            item["grade"] = grade
        else:
            item.update({
                "calls": record.calls.model_dump(mode="json"),
                "geo": record.geo.model_dump(mode="json"),
                "actual": record.actual.model_dump(mode="json"),
                "achievement": record.achievement.model_dump(mode="json"),
                "evaluation": record.evaluation.model_dump(mode="json"),
                "kpi_values": record.kpi_values,
            })
        return item
