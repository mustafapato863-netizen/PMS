"""Phase 1 acceptance tests: Monthly Review official scoring vs employee average, RBAC & cache invalidation."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base, get_db
from api.dependencies import require_authenticated_scope, get_current_user_scope
from models.ai_schemas import AiChatRequest, SessionFilterContext
from models.schemas import CallsData, EvaluationData, GeoBreakdown, GeoData, PerformanceRecord
from services.ai.catalog import ai_evidence_cache
from services.ai.orchestrator import PmsAiOrchestrator
from services.cache_invalidation_service import CacheInvalidationService
from services.dashboard_record_service import DashboardRecordService
from services.database_record_source import DatabaseRecordSource
from services.scoring.monthly_official_scores import official_department_score, official_team_score


STAGING_SQLITE = Path(__file__).resolve().parents[2] / ".tmp" / "assistant-upgrade-browser.db"


def _in_memory_db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    return sessionmaker(bind=eng)()


def _outbound_pooled_record(
    emp_id: str,
    name: str,
    score: float,
    *,
    month: str = "January",
    region: str = "EGY",
    branch: str = "dubai",
    attended: int = 80,
    bookings: int = 100,
    handled: int = 300,
    quality: float = 95.0,
    reachability: float = 92.0,
) -> PerformanceRecord:
    return PerformanceRecord(
        id=f"out_{emp_id}_{month}",
        employee_id=emp_id,
        employee_name=name,
        team="Outbound",
        position="Outbound Agent",
        region=region,
        branch=branch,
        branch_key=branch,
        month=month,
        year=2026,
        performance_level="Employee",
        status="On Track",
        raw_data={"Branch": branch.capitalize(), "pinState": "applied"},
        evaluation=EvaluationData(score=score, grade="A" if score >= 90 else "B"),
        calls=CallsData(inbound=handled, total_handled=handled, abandoned=5),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=bookings, sharjah=0, ajman=0, clinics=0),
            attended=GeoBreakdown(dubai=attended, sharjah=0, ajman=0, clinics=0),
        ),
        kpi_values=[
            {"kpi_key": "Attendance", "label": "Attendance Rate", "actual_value": attended / bookings, "target_value": 0.70, "unit": "%", "direction": "higher_better"},
            {"kpi_key": "Booking", "label": "Booking Rate", "actual_value": bookings / handled, "target_value": 0.25, "unit": "%", "direction": "higher_better"},
            {"kpi_key": "Quality", "label": "Quality Score", "actual_value": quality, "target_value": 95.0, "unit": "%", "direction": "higher_better"},
            {"kpi_key": "Other", "label": "Reachability", "actual_value": reachability, "target_value": 90.0, "unit": "%", "direction": "higher_better"},
        ],
    )


def _patch_records(monkeypatch, records: list[PerformanceRecord]) -> None:
    monkeypatch.setattr(DatabaseRecordSource, "get_all", lambda *a, **kw: list(records))
    monkeypatch.setattr(DashboardRecordService, "list_analysis_records", lambda *a, **kw: list(records))
    monkeypatch.setattr(DashboardRecordService, "list_records", lambda *a, **kw: list(records))
    monkeypatch.setattr(DashboardRecordService, "list_record_index", lambda *a, **kw: None)


def test_official_vs_employee_average_followup_and_switching(monkeypatch):
    # Agent individual scores average to (91 + 87)/2 = 89.0%,
    # while pooled Outbound KPIs (Attendance 90/100=100%, Booking 100/300=100%, Q=98%, R=96%) yield ~98.6% (within 15-pt guard).
    records = [
        _outbound_pooled_record("OUT-1", "Salma Out", 91.0, attended=85, bookings=95, handled=250, quality=98.0, reachability=96.0),
        _outbound_pooled_record("OUT-2", "Tarek Out", 87.0, attended=5, bookings=5, handled=50, quality=98.0, reachability=96.0),
        PerformanceRecord(
            id="in_1",
            employee_id="IN-1",
            employee_name="Hana In",
            team="Inbound",
            position="Inbound Agent",
            region="EGY",
            branch="dubai",
            branch_key="dubai",
            month="January",
            year=2026,
            performance_level="Employee",
            status="On Track",
            raw_data={"Branch": "Dubai", "pinState": "applied"},
            evaluation=EvaluationData(score=82.0, grade="B"),
            calls=CallsData(inbound=200, total_handled=200, abandoned=2),
            geo=GeoData(
                bookings=GeoBreakdown(dubai=80, sharjah=0, ajman=0, clinics=0),
                attended=GeoBreakdown(dubai=76, sharjah=0, ajman=0, clinics=0),
            ),
            kpi_values=[
                {"kpi_key": "Attendance", "label": "Attendance Rate", "actual_value": 0.95, "target_value": 0.70, "unit": "%", "direction": "higher_better"},
                {"kpi_key": "Booking", "label": "Booking Rate", "actual_value": 0.40, "target_value": 0.30, "unit": "%", "direction": "higher_better"},
                {"kpi_key": "Quality", "label": "Quality Score", "actual_value": 96.0, "target_value": 95.0, "unit": "%", "direction": "higher_better"},
                {"kpi_key": "AHT", "label": "AHT (Handle Time)", "actual_value": 4.0, "target_value": 5.0, "unit": "min", "direction": "lower_better"},
            ],
        ),
        PerformanceRecord(
            id="qm_1",
            employee_id="QM-1",
            employee_name="Nabil QA",
            team="Quality Management",
            position="QA Specialist",
            region="EGY",
            branch="dubai",
            month="January",
            year=2026,
            performance_level="Employee",
            status="On Track",
            evaluation=EvaluationData(score=99.0, grade="A"),
            kpi_values=[],
        ),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    official_expected = official_team_score(records[:2], "Outbound", measure="official").score
    emp_avg_expected = official_team_score(records[:2], "Outbound", measure="employee_average").score
    assert official_expected is not None and emp_avg_expected == 89.0
    assert official_expected != emp_avg_expected

    db = _in_memory_db()
    try:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "phase1-test", "has_unrestricted_team_access": True})

        # 1. Default question returns Monthly Review official score
        r_off = orch.run_chat_turn(AiChatRequest(
            prompt="What did Outbound score in Egypt in January 2026?",
            session_state=SessionFilterContext(month="January", year=2026),
            provider_override="deterministic",
        ))
        assert r_off.outcome == "answer", r_off.headline
        assert f"{official_expected:.1f}%" in r_off.headline
        assert "Monthly Review" in r_off.headline

        # 2. Explicit employee average returns employee average
        r_avg = orch.run_chat_turn(AiChatRequest(
            prompt="What was the average employee score for Outbound in Egypt in January 2026?",
            session_state=SessionFilterContext(month="January", year=2026),
            provider_override="deterministic",
        ))
        assert r_avg.outcome == "answer", r_avg.headline
        assert f"{emp_avg_expected:.1f}%" in r_avg.headline
        assert r_avg.resolved_session_state.last_confirmed_query.score_measure == "employee_average"

        # 3. Follow-up preserves employee_average unless changed ("Inbound" official=96.0 vs avg=82.0)
        r_follow = orch.run_chat_turn(AiChatRequest(
            conversation_id=r_avg.conversation_id,
            prompt="What about Inbound?",
            session_state=r_avg.resolved_session_state,
            provider_override="deterministic",
        ))
        assert r_follow.outcome == "answer", r_follow.headline
        assert "82.0%" in r_follow.headline
        assert r_follow.resolved_session_state.last_confirmed_query.score_measure == "employee_average"

        # 4. Explicit switch back to official Monthly Review score
        in_official_expected = official_team_score([records[2]], "Inbound", measure="official").score
        assert in_official_expected is not None and in_official_expected != 82.0
        r_back = orch.run_chat_turn(AiChatRequest(
            conversation_id=r_follow.conversation_id,
            prompt="What was the official Monthly Review score for Inbound?",
            session_state=r_follow.resolved_session_state,
            provider_override="deterministic",
        ))
        assert r_back.outcome == "answer", r_back.headline
        assert f"{in_official_expected:.1f}%" in r_back.headline
        assert r_back.resolved_session_state.last_confirmed_query.score_measure == "official"

        # 5. Unverified team (Quality Management) abstains rather than substituting 99.0% employee average
        r_qm = orch.run_chat_turn(AiChatRequest(
            prompt="What did Quality Management score in Egypt in January 2026?",
            session_state=SessionFilterContext(month="January", year=2026),
            provider_override="deterministic",
        ))
        assert r_qm.outcome == "unavailable_data", r_qm.headline
        assert "99.0%" not in r_qm.headline

        # 6. Rankings disclose coverage & exclude unverified Quality Management
        r_rank = orch.run_chat_turn(AiChatRequest(
            prompt="Which team was best in Egypt in January 2026?",
            session_state=SessionFilterContext(month="January", year=2026),
            provider_override="deterministic",
        ))
        assert r_rank.outcome == "answer", r_rank.headline
        assert "Quality Management" not in r_rank.headline
        assert any("excluded without verified official score" in b and "Quality Management" in b for b in r_rank.narrative_bullets)
    finally:
        db.close()


def test_restricted_manager_cohort_isolation_and_cache_invalidation(monkeypatch):
    mutable_records = [
        _outbound_pooled_record("OUT-DXB", "Dubai Agent", 95.0, branch="dubai", attended=95, bookings=100, handled=200),
        _outbound_pooled_record("OUT-SHJ", "Sharjah Agent", 50.0, branch="sharjah", attended=20, bookings=100, handled=400),
    ]
    monkeypatch.setattr(DatabaseRecordSource, "get_all", lambda *a, **kw: list(mutable_records))
    monkeypatch.setattr(DashboardRecordService, "list_analysis_records", lambda *a, **kw: list(mutable_records))
    monkeypatch.setattr(DashboardRecordService, "list_record_index", lambda *a, **kw: None)
    ai_evidence_cache.clear()

    db = _in_memory_db()
    try:
        dubai_mgr_scope = {
            "role": "Branch Director",
            "user_id": "mgr-dxb",
            "is_active": True,
            "accessible_teams": ["Outbound"],
            "accessible_team_levels": [("Outbound", "Employee")],
            "accessible_branches": ["dubai"],
            "accessible_regions": ["EGY"],
            "has_unrestricted_team_access": False,
        }
        admin_scope = {"role": "Admin", "user_id": "adm-all", "is_active": True, "has_unrestricted_team_access": True}

        mgr_orch = PmsAiOrchestrator(db, dubai_mgr_scope)
        adm_orch = PmsAiOrchestrator(db, admin_scope)

        r_mgr = mgr_orch.run_chat_turn(AiChatRequest(
            prompt="What did Outbound score in Egypt in January 2026?",
            session_state=SessionFilterContext(month="January", year=2026),
            provider_override="deterministic",
        ))
        r_adm = adm_orch.run_chat_turn(AiChatRequest(
            prompt="What did Outbound score in Egypt in January 2026?",
            session_state=SessionFilterContext(month="January", year=2026),
            provider_override="deterministic",
        ))
        assert r_mgr.outcome == "answer" and r_adm.outcome == "answer"
        mgr_val = r_mgr.typed_evidence[-1].actual
        adm_val = r_adm.typed_evidence[-1].actual
        # Restricted manager must see Dubai-only cohort score, NOT admin's combined cohort
        assert mgr_val != adm_val

        # Mutate underlying records + bump upload/settings revisions -> cache must invalidate immediately
        mutable_records[0] = _outbound_pooled_record("OUT-DXB", "Dubai Agent", 65.0, branch="dubai", attended=40, bookings=100, handled=500, quality=65.0, reachability=60.0)
        CacheInvalidationService.bump_data_version()
        r_after_upload = mgr_orch.run_chat_turn(AiChatRequest(
            prompt="What did Outbound score in Egypt in January 2026?",
            session_state=SessionFilterContext(month="January", year=2026),
            provider_override="deterministic",
        ))
        assert r_after_upload.typed_evidence[-1].actual != mgr_val

        CacheInvalidationService.bump_config_version()
        assert ai_evidence_cache.get(db=db, scope=dubai_mgr_scope, query_signature={"probe": 1}) is None
    finally:
        db.close()


def test_official_scores_endpoint_rbac_and_revisions(monkeypatch):
    from fastapi import FastAPI
    from api.routers.performance import router as perf_router

    app = FastAPI()
    app.include_router(perf_router, prefix="/api")

    records = [
        _outbound_pooled_record("OUT-DXB", "Dubai Agent", 95.0, branch="dubai"),
        _outbound_pooled_record("OUT-SHJ", "Sharjah Agent", 55.0, branch="sharjah"),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    db = _in_memory_db()
    active_scope = {
        "role": "Branch Director",
        "user_id": "mgr-api",
        "is_active": True,
        "accessible_teams": ["Outbound"],
        "accessible_team_levels": [("Outbound", "Employee")],
        "accessible_branches": ["dubai"],
        "accessible_regions": ["EGY"],
        "has_unrestricted_team_access": False,
    }
    monkeypatch.setattr("api.routers.performance.get_current_user_scope", lambda _db, _req: active_scope)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_authenticated_scope] = lambda: active_scope
    try:
        client = TestClient(app)
        resp = client.get("/api/performance/official-scores?region=EGY&month=January&year=2026&measure=official")
        assert resp.status_code == 200, resp.text
        payload = resp.json()["data"]
        assert payload["teams"]["Outbound"]["sample_size"] == 1  # Strictly Dubai cohort, never Sharjah!
        assert payload["metadata"]["upload_revision"] >= 0
        assert payload["metadata"]["settings_revision"] >= 0

        # Denied branch must return 403
        denied = client.get("/api/performance/official-scores?region=EGY&month=January&year=2026&location=sharjah")
        assert denied.status_code == 403
    finally:
        app.dependency_overrides.clear()
        db.close()


@pytest.mark.skipif(not STAGING_SQLITE.exists(), reason="Offline staging sqlite copy not present")
def test_staging_egy_outbound_jan_2026_official_91_5_vs_emp_avg_90_4(monkeypatch):
    uri = STAGING_SQLITE.resolve(strict=True).as_uri() + "?mode=ro"
    eng = create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True))
    try:
        ro_session = sessionmaker(bind=eng)()
        try:
            staging_records = list(DashboardRecordService(ro_session).list_analysis_records())
        finally:
            ro_session.close()
    finally:
        eng.dispose()

    _patch_records(monkeypatch, staging_records)
    ai_evidence_cache.clear()
    mem_db = _in_memory_db()
    try:
        orch = PmsAiOrchestrator(mem_db, {"role": "Admin", "user_id": "staging-parity", "has_unrestricted_team_access": True})

        r_off = orch.run_chat_turn(AiChatRequest(
            prompt="What did Outbound score in Egypt in January 2026?",
            session_state=SessionFilterContext(month="January", year=2026),
            provider_override="deterministic",
        ))
        assert r_off.outcome == "answer", r_off.headline
        assert "91.5%" in r_off.headline, r_off.headline

        r_avg = orch.run_chat_turn(AiChatRequest(
            prompt="What was the average employee score for Outbound in Egypt in January 2026?",
            session_state=SessionFilterContext(month="January", year=2026),
            provider_override="deterministic",
        ))
        assert r_avg.outcome == "answer", r_avg.headline
        assert "90.4%" in r_avg.headline, r_avg.headline
    finally:
        mem_db.close()
