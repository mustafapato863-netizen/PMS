"""Identical cold insights/workspace requests compute once; later ones read the cache."""
import threading
import time

import pytest
from fastapi import Response
from starlette.requests import Request

from api.routers import insights as insights_router
from models.insight_schemas import InsightComparison, InsightFilterOptions, InsightsWorkspace, InsightSummary
from services import response_cache
from services.cache_service import in_memory_cache


class _Session(insights_router.Session):  # a Session subclass so the cache path is used
    def __init__(self):  # no engine needed: the cache key and release are stubbed
        pass

    def in_transaction(self):
        return False


def _request():
    return Request({"type": "http", "headers": [], "method": "GET", "path": "/"})


@pytest.fixture()
def calls(monkeypatch):
    in_memory_cache.cache.clear()
    in_memory_cache.current_bytes = 0
    counter = {"n": 0}
    scope = {"role": "Admin", "user_id": "u1", "has_unrestricted_team_access": True}
    monkeypatch.setattr(insights_router, "require_authenticated_scope", lambda *_a, **_k: scope)
    monkeypatch.setattr(insights_router, "build_scoped_response_cache_key", lambda *_a, **_k: "pms:test:insights:single-flight")

    class FakeService:
        def __init__(self, *_a, **_k):
            pass

        def generate_workspace(self, *_a, **_k):
            counter["n"] += 1
            time.sleep(0.1)
            return InsightsWorkspace(
                summary=InsightSummary(), priority_insights=[], performance_drivers=[], risks=[], opportunities=[],
                data_issues=[], options=InsightFilterOptions(), comparison=InsightComparison(),
            )

    monkeypatch.setattr(insights_router, "InsightsService", FakeService)
    monkeypatch.setattr(insights_router, "PlanningService", lambda *_a, **_k: None)
    monkeypatch.setattr(insights_router, "DatabaseRecordSource", lambda *_a, **_k: None)
    return counter


def _call(db):
    response = Response()
    result = insights_router.get_insights_workspace(
        _request(), db, month=None, year=None, region=None, team=None, function=None, performance_level=None,
        position=None, employee_id=None, kpi=None, severity=None, insight_type=None, status_filter=None,
        branch=None, view="full", sections=None, response=response, _role="Admin",
    )
    return result, response.headers.get("x-cache")


def test_parallel_identical_cold_requests_compute_once(calls):
    db = _Session()
    results = []
    threads = [threading.Thread(target=lambda: results.append(_call(db))) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert calls["n"] == 1
    assert sorted(x for _r, x in results) == ["HIT"] * 5 + ["MISS"]
    assert len({r.model_dump_json() for r, _x in results}) == 1
    assert response_cache._flights == {}


def test_later_request_is_a_cache_hit(calls):
    db = _Session()
    assert _call(db)[1] == "MISS"
    assert _call(db)[1] == "HIT"
    assert calls["n"] == 1
