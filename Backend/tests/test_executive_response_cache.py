"""Tests for versioned, scope-safe backend response caching on Executive Summary endpoints."""
from __future__ import annotations

from fastapi import Response
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.routers import insights as insights_router
from api.routers import performance as performance_router
from models.insight_schemas import (
    InsightComparison,
    InsightFilterOptions,
    InsightSummary,
    InsightsWorkspace,
)
from models.models import Base
from services.cache_invalidation_service import CacheInvalidationService
from services.insights_service import InsightsService
from services.summary_records_service import SummaryResult


@pytest.fixture()
def sqlite_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_summary_records_caches_per_scope_and_invalidates_on_data_version_bump(monkeypatch, sqlite_session):
    calls = 0
    active_scope = {"user_id": "u-admin", "role": "Admin", "has_unrestricted_team_access": True}

    monkeypatch.setattr(performance_router, "enforce_user_route_limit", lambda *_a, **_kw: None)
    monkeypatch.setattr(performance_router, "require_authenticated_scope", lambda *_a: active_scope)

    def fake_indexed(_db, _record_service, scope, _filters, _limit):
        nonlocal calls
        calls += 1
        return SummaryResult(
            data=[{"employee_id": f"emp-{scope['user_id']}-{calls}", "evaluation": {"score": 91.5}}],
            truncated=False,
            total=1,
        )

    monkeypatch.setattr(performance_router, "summary_records_indexed", fake_indexed)

    resp1 = Response()
    first = performance_router.get_summary_records(None, sqlite_session, response=resp1)
    assert calls == 1
    assert resp1.headers["X-Cache"] == "MISS"
    assert resp1.headers["Cache-Control"] == "private, max-age=60"
    assert resp1.headers["X-Total-Count"] == "1"

    # Second identical request must be served from cache without calling summary_records_indexed.
    resp2 = Response()
    second = performance_router.get_summary_records(None, sqlite_session, response=resp2)
    assert calls == 1
    assert resp2.headers["X-Cache"] == "HIT"
    assert resp2.headers["X-Total-Count"] == "1"
    assert second.data == first.data

    # Different user scope must never receive Admin's cached rows.
    active_scope = {"user_id": "u-mgr", "role": "Manager", "accessible_teams": ["Inbound"], "has_unrestricted_team_access": False}
    resp3 = Response()
    third = performance_router.get_summary_records(None, sqlite_session, response=resp3)
    assert calls == 2
    assert resp3.headers["X-Cache"] == "MISS"
    assert third.data != first.data

    # Bumping data version invalidates Admin's cached entry immediately.
    active_scope = {"user_id": "u-admin", "role": "Admin", "has_unrestricted_team_access": True}
    CacheInvalidationService.bump_data_version()
    resp4 = Response()
    fourth = performance_router.get_summary_records(None, sqlite_session, response=resp4)
    assert calls == 3
    assert resp4.headers["X-Cache"] == "MISS"
    assert fourth.data != first.data


def test_insights_workspace_caches_by_sections_and_level_and_invalidates_on_version_bump(monkeypatch, sqlite_session):
    calls = 0
    scope = {"user_id": "u-exec", "role": "Executive", "has_unrestricted_team_access": True}

    monkeypatch.setattr(insights_router, "require_authenticated_scope", lambda *_a: scope)

    def fake_generate_workspace(_self, _scope, **_kwargs):
        nonlocal calls
        calls += 1
        return InsightsWorkspace(
            summary=InsightSummary(),
            priority_insights=[],
            performance_drivers=[],
            risks=[],
            opportunities=[],
            data_issues=[],
            options=InsightFilterOptions(),
            comparison=InsightComparison(),
        )

    monkeypatch.setattr(InsightsService, "generate_workspace", fake_generate_workspace)

    sections = "options,performance_drivers,team_analyses,priority_insights,opportunities"

    resp1 = Response()
    insights_router.get_insights_workspace(
        None,
        sqlite_session,
        month="September",
        year=2026,
        region=None,
        team=None,
        function=None,
        performance_level="Employee",
        position=None,
        employee_id=None,
        kpi=None,
        severity=None,
        insight_type=None,
        status_filter=None,
        branch=None,
        view="full",
        sections=sections,
        response=resp1,
        _role="Executive",
    )
    assert calls == 1
    assert resp1.headers["X-Cache"] == "MISS"
    assert resp1.headers["Cache-Control"] == "private, max-age=60"

    # Same filter + reordered sections string hits the same cache key.
    resp2 = Response()
    insights_router.get_insights_workspace(
        None,
        sqlite_session,
        month="September",
        year=2026,
        region=None,
        team=None,
        function=None,
        performance_level="Employee",
        position=None,
        employee_id=None,
        kpi=None,
        severity=None,
        insight_type=None,
        status_filter=None,
        branch=None,
        view="full",
        sections="opportunities,options,performance_drivers,priority_insights,team_analyses",
        response=resp2,
        _role="Executive",
    )
    assert calls == 1
    assert resp2.headers["X-Cache"] == "HIT"

    # Switching performance_level misses and caches its own entry.
    resp3 = Response()
    insights_router.get_insights_workspace(
        None,
        sqlite_session,
        month="September",
        year=2026,
        region=None,
        team=None,
        function=None,
        performance_level="Managerial",
        position=None,
        employee_id=None,
        kpi=None,
        severity=None,
        insight_type=None,
        status_filter=None,
        branch=None,
        view="full",
        sections=sections,
        response=resp3,
        _role="Executive",
    )
    assert calls == 2
    assert resp3.headers["X-Cache"] == "MISS"

    # Data version bump invalidates cached Employee entry.
    CacheInvalidationService.bump_data_version()
    resp4 = Response()
    insights_router.get_insights_workspace(
        None,
        sqlite_session,
        month="September",
        year=2026,
        region=None,
        team=None,
        function=None,
        performance_level="Employee",
        position=None,
        employee_id=None,
        kpi=None,
        severity=None,
        insight_type=None,
        status_filter=None,
        branch=None,
        view="full",
        sections=sections,
        response=resp4,
        _role="Executive",
    )
    assert calls == 3
    assert resp4.headers["X-Cache"] == "MISS"
