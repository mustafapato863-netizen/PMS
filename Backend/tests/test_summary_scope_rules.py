"""Scope rules for the summary and records reads: score scale, branch, period choice, paging.

In-memory SQLite and synthetic employees only. Each test pins one rule that the
parity fixture (test_summary_parity_capture.py) also exercises.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import Employee, PerformanceRecord, Team
from services.cache_service import CacheService
from services.performance_dashboard_read_service import PerformanceDashboardReadService, _grade
from utils.branch_scope import record_matches_branch, text_branch
from utils.scoring_rules import GRADE_THRESHOLDS, letter_grade, score_percent, score_percent_sql


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _scope():
    return {
        "user_id": str(uuid.uuid4()),
        "role": "Admin",
        "employee_id": None,
        "accessible_teams": [],
        "accessible_team_levels": [],
        "has_unrestricted_team_access": True,
        "is_self_only": False,
        "legacy_unscoped": False,
    }


def _geo(**values):
    base = {"dubai": 0, "sharjah": 0, "ajman": 0, "clinics": 0}
    base.update(values)
    return NS(bookings=NS(**base), attended=NS(**base))


@pytest.fixture
def no_cache(monkeypatch):
    monkeypatch.setattr(CacheService, "get_json", lambda *_, **__: None)
    monkeypatch.setattr(CacheService, "set_json", lambda *_, **__: None)


def _seed(db):
    team = Team(id=uuid.uuid4(), name="Inbound", db_name="inbound", display_name="Inbound", region="EGY", team_level="employee", is_active=True)
    db.add(team)
    db.flush()
    people = {
        "RB-1": "Rule Agent 1", "RB-2": "Rule Agent 2", "RB-3": "Rule Agent 3", "RB-4": "Rule Agent 4",
        "RB-5": "Rule Agent 5", "RB-6": "Rule Agent 6", "RB-7": "Rule Agent 7",
    }
    employees = {
        code: Employee(id=uuid.uuid4(), employee_id=code, name=name, team_id=team.id, region="EGY")
        for code, name in people.items()
    }
    db.add_all(employees.values())
    db.flush()

    def row(code, month, score, grade, *, branch_key=None, raw=None):
        payload = {"raw_data": raw} if raw else None
        return PerformanceRecord(
            id=uuid.uuid4(), year=2026, month=month, employee_id=employees[code].id, team_id=team.id,
            performance_level="Employee", region="EGY", branch_key=branch_key, score=score, grade=grade,
            status="Meets", record_payload=payload,
        )

    db.add_all([
        row("RB-1", "July", 90, "B", branch_key="dubai"),
        row("RB-1", "August", 80, "C", branch_key="sharjah"),
        row("RB-2", "August", 70, "D", raw={"Branch": "SHJ"}),
        row("RB-3", "September", 0, "E"),  # no activity: a zero-only month
        row("RB-4", "July", 60, "E"),
        row("RB-5", "July", 50, "E", raw={"Attendance": "4"}),
        row("RB-6", "July", 40, "E", branch_key="dubai"),
        row("RB-7", "July", 0, "E"),  # zero score, no activity: never counted
    ])
    db.commit()


# ── Score scale ──

@pytest.mark.parametrize("stored, expected", [(0.85, 85.0), (1, 100.0), (1.5, 1.5), (5.48, 5.48), (100, 100), (0, 0)])
def test_score_percent_treats_ratio_form_only_up_to_one(stored, expected):
    assert score_percent(float(stored)) == pytest.approx(expected)


def test_score_percent_sql_is_built_from_the_same_rule():
    compiled = str(score_percent_sql(PerformanceRecord.score).compile(compile_kwargs={"literal_binds": True}))
    assert "<= 1" in compiled and "<= 10" not in compiled


# ── Grade cut-offs ──

def test_letter_grade_uses_the_shared_thresholds():
    assert GRADE_THRESHOLDS == (("A", 95.0), ("B", 90.0), ("C", 80.0), ("D", 70.0))
    assert [letter_grade(value) for value in (95, 94.9, 90, 89.9, 80, 79.9, 70, 69.9)] == ["A", "B", "B", "C", "C", "D", "D", "E"]


def test_grade_fallback_uses_the_shared_thresholds_not_85_75_65():
    record = NS(evaluation=NS(grade=""))
    assert _grade(record, 85.0) == "C"
    assert _grade(record, 75.0) == "D"
    assert _grade(record, 65.0) == "E"


# ── Branch rule ──

def test_stored_branch_key_decides_when_present():
    record = NS(branch_key="sharjah", raw_data={"Branch": "DUBAI"}, team="Inbound", geo=_geo(dubai=3))
    assert record_matches_branch(record, "sharjah")
    assert not record_matches_branch(record, "dubai")


def test_text_then_geo_decide_when_branch_key_is_empty():
    assert record_matches_branch(NS(branch_key=None, raw_data={"Branch": "SHJ"}, team="Inbound", geo=_geo()), "sharjah")
    assert record_matches_branch(NS(branch_key="", raw_data={}, team="Inbound", geo=_geo(clinics=1)), "clinics")
    assert record_matches_branch(NS(branch_key=None, raw_data={}, team="Pre-Approvals IP Final Dubai", geo=_geo()), "dubai")
    assert not record_matches_branch(NS(branch_key=None, raw_data={}, team="Inbound", geo=_geo()), "dubai")


def test_text_order_matches_the_server_rule():
    assert text_branch(NS(raw_data={"Branch": "SHJ AJM"}, team="Inbound")) == "ajman"
    assert text_branch(NS(raw_data={}, team="Pre-Approvals OP Final SHJAJM")) is None


# ── Summary: previous month, fallback and empty scope ──

def test_previous_month_is_chosen_within_the_filtered_scope(no_cache):
    db = _session()
    try:
        _seed(db)
        svc = PerformanceDashboardReadService(db, _scope())
        sharjah = svc.summary(period="2026-08", location="sharjah", trend_months=12)
        # RB-1 was Dubai in July, so Sharjah has no earlier month with counted rows.
        assert sharjah["previous_period"] is None
        assert sharjah["period_selection"]["fallback_applied"] is False
        assert sharjah["current"]["total_agents"] == 2
        all_branches = svc.summary(period="2026-08", location="all", trend_months=12)
        assert all_branches["previous_period"]["key"] == "2026-07"
    finally:
        db.close()


def test_requested_month_without_counted_rows_reports_the_month_used(no_cache):
    db = _session()
    try:
        _seed(db)
        data = PerformanceDashboardReadService(db, _scope()).summary(period="2026-08", location="dubai", trend_months=12)
        selection = data["period_selection"]
        assert data["period"]["key"] == "2026-07"
        assert selection["requested"] == "2026-08"
        assert selection["effective"] == "2026-07"
        assert selection["fallback_applied"] is True
        assert selection["reason"] == "requested_period_has_no_counted_rows_in_scope"
        assert selection["notice"] == "No performance data for August 2026 yet — showing July 2026, the latest month with data."
    finally:
        db.close()


def test_zero_only_month_is_not_a_period_and_the_default_skips_it(no_cache):
    db = _session()
    try:
        _seed(db)
        svc = PerformanceDashboardReadService(db, _scope())
        assert "2026-09" not in svc.counted_period_keys()
        assert {"2026-07", "2026-08"} <= svc.counted_period_keys()
        data = svc.summary(period="2026-09", location="all", trend_months=12)
        assert data["period"]["key"] == "2026-08"
        assert data["period_selection"]["fallback_applied"] is True
    finally:
        db.close()


def test_a_scope_with_no_counted_rows_has_no_period(no_cache):
    db = _session()
    try:
        _seed(db)
        data = PerformanceDashboardReadService(db, _scope()).summary(period="2026-09", location="clinics", trend_months=12)
        assert data["period"] is None
        assert data["period_selection"]["reason"] == "no_counted_rows_in_scope"
        assert data["current"]["total_agents"] == 0
    finally:
        db.close()


# ── Records: activity rule in the SQL page, paging and totals, branch filter ──

def _page_all(svc, **kwargs):
    items, cursor = [], None
    while True:
        page = svc.records_page(cursor=cursor, **kwargs)
        items.extend(page["items"])
        if not page["has_more"]:
            return items, page
        cursor = page["next_cursor"]


def test_below_target_pages_and_totals_count_only_counted_rows(no_cache):
    db = _session()
    try:
        _seed(db)
        svc = PerformanceDashboardReadService(db, _scope())
        # July below 90: RB-4 (60), RB-5 (50), RB-6 (40) count; RB-7 (zero, no activity) does not.
        items, last = _page_all(svc, period="2026-07", score_lt=90, sort="score_asc", page_size=1, include_total=True)
        assert [item["employee_id"] for item in items] == ["RB-6", "RB-5", "RB-4"]
        assert len(set(item["id"] for item in items)) == 3
        assert last["total"] == 3
    finally:
        db.close()


def test_below_target_total_is_zero_for_a_zero_only_month(no_cache):
    db = _session()
    try:
        _seed(db)
        page = PerformanceDashboardReadService(db, _scope()).records_page(period="2026-09", score_lt=90, page_size=5, include_total=True)
        assert page["items"] == [] and page["total"] == 0 and page["has_more"] is False
    finally:
        db.close()


def test_branch_filter_uses_the_one_branch_rule(no_cache):
    db = _session()
    try:
        _seed(db)
        svc = PerformanceDashboardReadService(db, _scope())
        sharjah = svc.records_page(period="2026-08", branch="sharjah", page_size=10)
        assert sorted(item["employee_id"] for item in sharjah["items"]) == ["RB-1", "RB-2"]
        dubai = svc.records_page(period="2026-08", branch="dubai", page_size=10)
        assert dubai["items"] == []
    finally:
        db.close()
