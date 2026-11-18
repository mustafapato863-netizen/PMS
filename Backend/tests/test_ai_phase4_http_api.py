"""Phase 4 Test Suite: Authenticated HTTP API Boundary & Multi-Turn Verification.

Verifies end-to-end HTTP API behavior over FastAPI TestClient:
1. Compound question in one turn (trend and ranking for same scope).
2. Country-only follow-up with strict country/team scope isolation (Coding UAE -> Coding Egypt).
3. Ambiguity resolution, conversation persistence across GET /conversations/{id}, follow-up retention, and fresh chat isolation.
4. Idempotent submission with client_request_id and clean conversation deletion via DELETE /conversations/{id}.
5. Server-side RBAC enforcement (non-admin 403) and graceful provider timeout fallback to authoritative facts.
6. Frontend response contract verification matching AiResponseCard schema.
"""
from __future__ import annotations

import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base, get_db
from models.schemas import (
    CallsData,
    EvaluationData,
    GeoBreakdown,
    GeoData,
    PerformanceRecord,
)
import api.routers.ai_workspace as ai_workspace
import services.ai.feature_gate as feature_gate
from services.ai.catalog import ai_evidence_cache
from services.database_record_source import DatabaseRecordSource
from services.dashboard_record_service import DashboardRecordService
from tests.ai_provider_fakes import failed_response, install_scripted_provider, tool_response


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_PROVIDER_TIMEOUT_SECONDS", "20.0")
    install_scripted_provider(monkeypatch, failed_response())
    ai_evidence_cache.clear()
    yield
    ai_evidence_cache.clear()


@pytest.fixture
def memory_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()


@pytest.fixture
def synth_records() -> list[PerformanceRecord]:
    recs: list[PerformanceRecord] = []

    # 1. Nadia Fadel in August 2026 (Inbound, Waiting Time = 6.8 min, Score = 88.5%, Booking Rate = 24.4%)
    r_nadia_aug = PerformanceRecord(
        id="Inbound_EMP501_2026_Aug",
        employee_id="EMP501",
        employee_name="Nadia Fadel",
        team="Inbound",
        month="August",
        year=2026,
        region="EGY",
        branch="dubai",
        raw_data={"Branch": "Dubai"},
        position="Senior Call Center Agent",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=88.5, grade="B"),
        calls=CallsData(inbound=450, total_handled=520, abandoned=10),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=110, sharjah=40, ajman=20, clinics=10),
            attended=GeoBreakdown(dubai=95, sharjah=35, ajman=18, clinics=8),
        ),
        kpi_values=[
            {"kpi_key": "waitingtime", "label": "Waiting Time", "actual_value": 6.8, "target_value": 5.0, "unit": "min", "direction": "lower_better"},
            {"kpi_key": "Booking", "label": "Booking Rate", "actual_value": 24.4, "target_value": 25.0, "unit": "%", "direction": "higher_better"},
            {"kpi_key": "bookings_count", "label": "Bookings Count", "actual_value": 160, "target_value": 150, "unit": "count", "direction": "higher_better"},
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 88.5, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 2. Nadia Fadel in September 2026 (Inbound, Waiting Time = 6.2 min, Score = 91.0%, Booking Rate = 27.1%, Abandon = 0.0%)
    r_nadia_sep = PerformanceRecord(
        id="Inbound_EMP501_2026_Sep",
        employee_id="EMP501",
        employee_name="Nadia Fadel",
        team="Inbound",
        month="September",
        year=2026,
        region="EGY",
        branch="dubai",
        raw_data={"Branch": "Dubai"},
        position="Senior Call Center Agent",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=91.0, grade="A"),
        calls=CallsData(inbound=480, total_handled=550, abandoned=0),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=130, sharjah=45, ajman=25, clinics=10),
            attended=GeoBreakdown(dubai=115, sharjah=40, ajman=22, clinics=9),
        ),
        kpi_values=[
            {"kpi_key": "waitingtime", "label": "Waiting Time", "actual_value": 6.2, "target_value": 5.0, "unit": "min", "direction": "lower_better"},
            {"kpi_key": "abandon_rate", "label": "Abandon Rate", "actual_value": 0.0, "target_value": 3.0, "unit": "%", "direction": "lower_better"},
            {"kpi_key": "Booking", "label": "Booking Rate", "actual_value": 27.1, "target_value": 25.0, "unit": "%", "direction": "higher_better"},
            {"kpi_key": "bookings_count", "label": "Bookings Count", "actual_value": 180, "target_value": 150, "unit": "count", "direction": "higher_better"},
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 91.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 3. Tarek Omar in September 2026 (Inbound, Score = 79.5%)
    r_tarek = PerformanceRecord(
        id="Inbound_EMP502_2026_Sep",
        employee_id="EMP502",
        employee_name="Tarek Omar",
        team="Inbound",
        month="September",
        year=2026,
        region="EGY",
        branch="sharjah",
        raw_data={"Branch": "Sharjah"},
        position="Call Center Agent",
        performance_level="Employee",
        status="Needs Improvement",
        evaluation=EvaluationData(score=79.5, grade="C"),
        calls=CallsData(inbound=300, total_handled=320, abandoned=15),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=60, sharjah=50, ajman=10, clinics=5),
            attended=GeoBreakdown(dubai=50, sharjah=42, ajman=8, clinics=4),
        ),
        kpi_values=[
            {"kpi_key": "waitingtime", "label": "Waiting Time", "actual_value": 7.4, "target_value": 5.0, "unit": "min", "direction": "lower_better"},
            {"kpi_key": "Booking", "label": "Booking Rate", "actual_value": 20.0, "target_value": 25.0, "unit": "%", "direction": "higher_better"},
            {"kpi_key": "bookings_count", "label": "Bookings Count", "actual_value": 120, "target_value": 150, "unit": "count", "direction": "higher_better"},
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 79.5, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 4. Mariam Ali in September 2026 (Inbound, Dubai, Score = 87.0%)
    r_mariam_ali = PerformanceRecord(
        id="Inbound_EMP601_2026_Sep",
        employee_id="EMP601",
        employee_name="Mariam Ali",
        team="Inbound",
        month="September",
        year=2026,
        region="EGY",
        branch="dubai",
        raw_data={"Branch": "Dubai"},
        position="Call Center Agent",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=87.0, grade="B"),
        calls=CallsData(inbound=300, total_handled=350, abandoned=15),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=80, sharjah=30, ajman=10, clinics=5),
            attended=GeoBreakdown(dubai=70, sharjah=25, ajman=8, clinics=4),
        ),
        kpi_values=[
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 87.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 5. Mariam Hassan in September 2026 (Inbound, Sharjah, Score = 79.0%)
    r_mariam_hassan = PerformanceRecord(
        id="Inbound_EMP602_2026_Sep",
        employee_id="EMP602",
        employee_name="Mariam Hassan",
        team="Inbound",
        month="September",
        year=2026,
        region="EGY",
        branch="sharjah",
        raw_data={"Branch": "Sharjah"},
        position="Call Center Agent",
        performance_level="Employee",
        status="Below Target",
        evaluation=EvaluationData(score=79.0, grade="C"),
        calls=CallsData(inbound=280, total_handled=320, abandoned=20),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=70, sharjah=25, ajman=10, clinics=5),
            attended=GeoBreakdown(dubai=60, sharjah=20, ajman=8, clinics=4),
        ),
        kpi_values=[
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 79.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 6. Hassan Zaki in September 2026 (Coding UAE, Quality Errors = 2.5%)
    r_coding_uae = PerformanceRecord(
        id="Coding_EMP701_2026_Sep",
        employee_id="EMP701",
        employee_name="Hassan Zaki",
        team="Coding",
        month="September",
        year=2026,
        region="UAE",
        branch="dubai",
        position="Medical Coder",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=92.0, grade="A"),
        kpi_values=[
            {"kpi_key": "QualityErrors", "label": "Quality Errors", "actual_value": 2.5, "target_value": 3.0, "unit": "%", "direction": "lower_better"},
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 92.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 7. Mona Samir in September 2026 (Coding EGY, Quality Errors = 1.8%)
    r_coding_egy = PerformanceRecord(
        id="CodingEGY_EMP801_2026_Sep",
        employee_id="EMP801",
        employee_name="Mona Samir",
        team="Coding EGY",
        month="September",
        year=2026,
        region="EGY",
        branch="cairo",
        position="RCM -SHJ- OP CODING",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=94.5, grade="A"),
        kpi_values=[
            {"kpi_key": "egy_coding_quality_errors", "label": "Quality Errors Rate", "actual_value": 1.8, "target_value": 2.5, "unit": "%", "direction": "lower_better"},
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 94.5, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    recs.extend([
        r_nadia_aug,
        r_nadia_sep,
        r_tarek,
        r_mariam_ali,
        r_mariam_hassan,
        r_coding_uae,
        r_coding_egy,
    ])
    return recs


def _patch_sources(monkeypatch, records: list[PerformanceRecord]):
    monkeypatch.setattr(DatabaseRecordSource, "get_all", lambda *args, **kwargs: records)
    monkeypatch.setattr(DashboardRecordService, "list_analysis_records", lambda *args, **kwargs: records)
    monkeypatch.setattr(DashboardRecordService, "list_record_index", lambda *args, **kwargs: None)


@pytest.fixture
def test_client(memory_db, synth_records, monkeypatch) -> TestClient:
    _patch_sources(monkeypatch, synth_records)
    monkeypatch.setattr(feature_gate, "is_ai_enabled", lambda db: True)
    monkeypatch.setattr(feature_gate, "_legacy_role_header_allowed", lambda: True)

    def mock_scope(db, request):
        role = request.headers.get("X-User-Role", "Admin")
        if role == "Admin":
            return {
                "role": "Admin",
                "user_id": "admin-test-user",
                "has_unrestricted_team_access": True,
                "is_admin": True,
            }
        return {
            "role": role,
            "user_id": "user-test-emp",
            "is_self_only": True if role == "Employee" else False,
            "employee_id": "EMP501",
            "accessible_teams": ["Inbound"],
        }

    monkeypatch.setattr(ai_workspace, "require_authenticated_scope", mock_scope)
    monkeypatch.setattr(ai_workspace, "release_read_transaction", lambda db: None)

    app = FastAPI()
    app.include_router(ai_workspace.router, prefix="/api")

    def override_db():
        try:
            yield memory_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    return TestClient(app, raise_server_exceptions=True)


# ===========================================================================
# 1. Compound Question in One Turn
# ===========================================================================

def test_http_compound_question_in_one_turn(test_client, synth_records, monkeypatch):
    """Scenario 1: Ask for booking trend AND top performer for Inbound in September 2026."""
    install_scripted_provider(monkeypatch, [
        tool_response("get_score_trend", team="Inbound", metric_id="inbound:bookings_count",
                      periods=["2026-08", "2026-09"]),
        failed_response("timeout"),
    ])
    payload = {
        "prompt": "What was the total number of bookings for the Inbound team in August and September 2026, and which employee had the highest bookings count in September 2026?",
        "session_state": {
            "team": "Inbound",
            "month": "September",
            "year": 2026,
        },
    }
    resp = test_client.post("/api/ai/chat", headers={"X-User-Role": "Admin"}, json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["outcome"] == "answer", json.dumps(data, default=str)
    assert data["conversation_id"] is not None

    headline = data["headline"]
    combined_text = " ".join(
        [headline, *data.get("narrative_bullets", []), *data.get("detail_bullets", [])]
    ).casefold()
    evidence = data.get("typed_evidence", [])
    def is_bookings_count_evidence(item):
        key = str(item.get("kpi_key") or "").casefold().replace("_", "").replace(" ", "")
        display = str(item.get("display_name") or "").casefold().replace("_", "").replace(" ", "").replace("(", "").replace(")", "")
        metric = str(item.get("metric_id") or "").casefold().rsplit(":", 1)[-1].replace("_", "").replace(" ", "")
        return key in {"bookingscount", "totalbookings"} or display in {"bookingscount", "totalbookings"} or metric in {"bookingscount", "totalbookings"}

    booking_evidence = [item for item in evidence if is_bookings_count_evidence(item)]

    def bookings_in_record(record):
        bookings = record.geo.bookings
        return sum(float(getattr(bookings, field) or 0) for field in ("dubai", "sharjah", "ajman", "clinics"))

    expected_team_totals = {
        month: sum(
            bookings_in_record(record)
            for record in synth_records
            if record.team.casefold() == "inbound" and record.month.casefold() == month.casefold() and record.year == 2026
        )
        for month in ("August", "September")
    }
    trend_evidence = [item for item in booking_evidence if not item.get("employee_id") and not item.get("employee_name")]
    ranked_evidence = [item for item in booking_evidence if item.get("employee_id") or item.get("employee_name")]

    def period_evidence(items, month):
        month_name = month.casefold()
        month_num = "08" if month == "August" else "09"
        return [
            item
            for item in items
            if month_name in str(item.get("period") or "").casefold()
            or f"2026-{month_num}" in str(item.get("period") or "")
        ]

    for month, expected_total in expected_team_totals.items():
        matching = period_evidence(trend_evidence, month)
        assert matching, f"Missing team-level {month} booking evidence: {json.dumps(data, default=str)}"
        assert any(float(item.get("actual")) == expected_total for item in matching), (
            f"{month} Inbound total must independently aggregate synthetic source records to {expected_total}: "
            f"{json.dumps(data, default=str)}"
        )
    assert all(not item.get("employee_id") and not item.get("employee_name") for item in trend_evidence), (
        f"Team trend evidence must not narrow to an employee: {json.dumps(trend_evidence, default=str)}"
    )

    september_ranked = period_evidence(ranked_evidence, "September")
    assert any(
        item.get("employee_id") == "EMP501"
        and item.get("employee_name") == "Nadia Fadel"
        and float(item.get("actual")) == bookings_in_record(next(
            record for record in synth_records
            if record.employee_id == "EMP501" and record.month == "September" and record.year == 2026
        ))
        for item in september_ranked
    ), f"Ranking evidence must show Nadia's independently calculated September bookings: {json.dumps(data, default=str)}"

    tool_names = {str(item.get("tool_name") or "") for item in data.get("tool_calls", [])}
    assert any("trend" in name or "history" in name for name in tool_names), tool_names
    assert any("rank" in name for name in tool_names), tool_names
    assert "nadia fadel" in combined_text, f"Ranked person missing from same response: {combined_text}"
    assert "booking" in combined_text, f"Ranked metric missing from same response: {combined_text}"
    assert all(str(int(total)) in combined_text for total in expected_team_totals.values()), (
        f"Team trend answer must include both independently calculated totals {expected_team_totals}: {combined_text}"
    )
    nadia_bookings = bookings_in_record(next(
        record for record in synth_records
        if record.employee_id == "EMP501" and record.month == "September" and record.year == 2026
    ))
    assert str(int(nadia_bookings)) in combined_text, f"Top booking value missing: {combined_text}"


# ===========================================================================
# 2. Country-Only Follow-Up Scope Isolation
# ===========================================================================

def test_http_country_only_follow_up_scope_isolation(test_client, monkeypatch):
    """Scenario 2: Switch country only, then use a terse follow-up with no new identity or country."""
    install_scripted_provider(monkeypatch, [
        tool_response("read_employee_metric", metric_id="quality_errors_rate", period="2026-09"),
        failed_response("timeout"),
    ] * 3)
    # Turn 1: Team metric in UAE; no employee identity is bound.
    payload1 = {
        "prompt": "What was the Quality Errors rate for Coding in the UAE in September 2026?",
        "session_state": {
            "team": "Coding",
            "month": "September",
            "year": 2026,
            "region": "UAE",
        },
    }
    resp1 = test_client.post("/api/ai/chat", headers={"X-User-Role": "Admin"}, json=payload1)
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()["data"]
    assert data1["outcome"] == "answer", json.dumps(data1, default=str)
    evidence1 = data1.get("typed_evidence", [])
    assert evidence1, json.dumps(data1, default=str)
    assert all(item.get("team") == "Coding" for item in evidence1)
    conv_id = data1["conversation_id"]
    assert conv_id is not None

    # Turn 2: Switch country to Egypt
    payload2 = {
        "prompt": "Switch to Egypt instead",
        "conversation_id": conv_id,
        "session_state": data1["resolved_session_state"],
    }
    resp2 = test_client.post("/api/ai/chat", headers={"X-User-Role": "Admin"}, json=payload2)
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()["data"]
    state2 = data2["resolved_session_state"]
    confirmed2 = state2.get("last_confirmed_query") or {}
    actual_region = state2.get("region") or confirmed2.get("region")
    actual_team = state2.get("team") or confirmed2.get("team")
    assert actual_region == "EGY", json.dumps(data2, default=str)
    assert actual_team == "Coding EGY", json.dumps(data2, default=str)
    assert not state2.get("employee_id") and not confirmed2.get("last_subject_employee_id"), json.dumps(data2, default=str)

    # Turn 3: A terse follow-up carries the Egypt scope without a new person/country.
    payload3 = {
        "prompt": "And the rate?",
        "conversation_id": conv_id,
        "session_state": state2,
    }
    resp3 = test_client.post("/api/ai/chat", headers={"X-User-Role": "Admin"}, json=payload3)
    assert resp3.status_code == 200, resp3.text
    data3 = resp3.json()["data"]
    assert data3["outcome"] == "answer"
    evidence3 = data3.get("typed_evidence", [])
    assert evidence3, json.dumps(data3, default=str)
    assert all(e.get("team") == "Coding EGY" for e in evidence3), json.dumps(data3, default=str)
    assert any(e.get("actual") is not None and abs(float(e["actual"]) - 1.8) < 0.01 for e in evidence3), json.dumps(data3, default=str)
    state3 = data3["resolved_session_state"]
    confirmed3 = state3.get("last_confirmed_query") or {}
    assert (state3.get("region") or confirmed3.get("region")) == "EGY", json.dumps(data3, default=str)


# ===========================================================================
# 3. Context Persistence and Fresh Chat Isolation
# ===========================================================================

def test_http_context_persistence_and_chat_isolation(test_client):
    """Scenario 3: Same-name ambiguity -> choice selection -> reload GET -> follow-up -> fresh chat isolation."""
    # Step 1: Same-name ambiguity prompt
    payload1 = {
        "prompt": "Show performance for Mariam",
        "session_state": {
            "team": "Inbound",
            "month": "September",
            "year": 2026,
        },
    }
    resp1 = test_client.post("/api/ai/chat", headers={"X-User-Role": "Admin"}, json=payload1)
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()["data"]
    assert data1["outcome"] == "clarification"
    conv_id = data1["conversation_id"]
    assert conv_id is not None

    # Step 2: User selects Mariam Ali choice
    payload2 = {
        "prompt": "Show performance for Mariam",
        "clarification_choice_id": "choice-person-EMP601",
        "conversation_id": conv_id,
        "session_state": data1["resolved_session_state"],
    }
    resp2 = test_client.post("/api/ai/chat", headers={"X-User-Role": "Admin"}, json=payload2)
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()["data"]
    assert data2["outcome"] == "answer", json.dumps(data2, default=str)
    assert "87" in data2["headline"]
    assert "Mariam Ali" in data2["headline"]

    # Step 3: Reload conversation via GET /api/ai/conversations/{id}
    get_resp = test_client.get(f"/api/ai/conversations/{conv_id}", headers={"X-User-Role": "Admin"})
    assert get_resp.status_code == 200, get_resp.text
    detail = get_resp.json()["data"]
    assert detail["conversation_id"] == conv_id
    assert len(detail["turns"]) >= 2

    # Step 4: Reload through the server-owned conversation; the request carries no client session state.
    payload4 = {
        "prompt": "What is her job title?",
        "conversation_id": conv_id,
    }
    resp4 = test_client.post("/api/ai/chat", headers={"X-User-Role": "Admin"}, json=payload4)
    assert resp4.status_code == 200, resp4.text
    data4 = resp4.json()["data"]
    assert data4["outcome"] == "answer"
    assert "Call Center Agent" in data4["headline"] or any("Call Center Agent" in b for b in data4.get("narrative_bullets", []))

    # Step 5: Fresh chat isolation (start fresh conversation without passing conversation_id)
    payload_fresh = {
        "prompt": "What was her Waiting Time in September 2026?",
        "session_state": {
            "team": "Inbound",
            "month": "September",
            "year": 2026,
        },
    }
    resp_fresh = test_client.post("/api/ai/chat", headers={"X-User-Role": "Admin"}, json=payload_fresh)
    assert resp_fresh.status_code == 200, resp_fresh.text
    fresh_data = resp_fresh.json()["data"]
    fresh_cid = fresh_data["conversation_id"]
    # New conversation must have distinct ID and not retain Mariam Ali
    assert fresh_cid != conv_id
    assert "EMP601" not in json.dumps(fresh_data["resolved_session_state"], ensure_ascii=False)
    assert "Mariam Ali" not in (fresh_data["headline"] + " " + " ".join(fresh_data.get("narrative_bullets", [])))


# ===========================================================================
# 4. Deletion and Client Request ID Idempotency
# ===========================================================================

def test_http_deletion_and_client_request_id_idempotency(test_client):
    """Scenario 4: Idempotent resubmission with client_request_id and conversation deletion."""
    req_id = "test-client-req-uuid-999"
    payload = {
        "prompt": "What was Nadia Fadel's Waiting Time in September 2026?",
        "client_request_id": req_id,
        "session_state": {
            "team": "Inbound",
            "month": "September",
            "year": 2026,
        },
    }
    # Turn 1
    resp1 = test_client.post("/api/ai/chat", headers={"X-User-Role": "Admin"}, json=payload)
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()["data"]
    turn_id_1 = data1["turn_id"]
    conv_id = data1["conversation_id"]
    list_before = test_client.get("/api/ai/conversations?origin=workspace", headers={"X-User-Role": "Admin"})
    assert list_before.status_code == 200, list_before.text
    summary_before = next((c for c in list_before.json().get("conversations", []) if c["conversation_id"] == conv_id), None)
    assert summary_before is not None, list_before.json()
    assert summary_before["turn_count"] == 1, summary_before

    # Turn 1 repeat (identical client_request_id within conversation)
    payload_repeat = dict(payload)
    payload_repeat["conversation_id"] = conv_id
    resp1_repeat = test_client.post("/api/ai/chat", headers={"X-User-Role": "Admin"}, json=payload_repeat)
    assert resp1_repeat.status_code == 200, resp1_repeat.text
    data1_repeat = resp1_repeat.json()["data"]
    # Idempotent return should match the same turn
    assert data1_repeat["turn_id"] == turn_id_1
    list_after_repeat = test_client.get("/api/ai/conversations?origin=workspace", headers={"X-User-Role": "Admin"})
    assert list_after_repeat.status_code == 200, list_after_repeat.text
    summary_after_repeat = next(
        (c for c in list_after_repeat.json().get("conversations", []) if c["conversation_id"] == conv_id), None
    )
    assert summary_after_repeat is not None, list_after_repeat.json()
    assert summary_after_repeat["turn_count"] == 1, summary_after_repeat
    detail_after_repeat = test_client.get(f"/api/ai/conversations/{conv_id}", headers={"X-User-Role": "Admin"})
    assert detail_after_repeat.status_code == 200, detail_after_repeat.text
    assert len(detail_after_repeat.json()["data"]["turns"]) == 1

    # Deletion via DELETE /api/ai/conversations/{id}
    del_resp = test_client.delete(f"/api/ai/conversations/{conv_id}", headers={"X-User-Role": "Admin"})
    assert del_resp.status_code == 200, del_resp.text
    assert del_resp.json()["success"] is True

    # Reload deleted conversation: must return 404
    get_del = test_client.get(f"/api/ai/conversations/{conv_id}", headers={"X-User-Role": "Admin"})
    assert get_del.status_code == 404, get_del.text
    list_after_delete = test_client.get("/api/ai/conversations?origin=workspace", headers={"X-User-Role": "Admin"})
    assert list_after_delete.status_code == 200, list_after_delete.text
    assert all(c["conversation_id"] != conv_id for c in list_after_delete.json().get("conversations", []))


# ===========================================================================
# 5. RBAC Permissions & Provider Failure Graceful Fallback
# ===========================================================================

def test_http_rbac_permissions_and_provider_failure_fallback(test_client, monkeypatch):
    """Scenario 5: Non-Admin role rejection (403) and graceful provider timeout fallback."""
    payload = {
        "prompt": "What was Nadia Fadel's Waiting Time in September 2026?",
        "session_state": {"team": "Inbound", "month": "September", "year": 2026},
    }

    # 1. Non-Admin (Employee) rejection
    resp_emp = test_client.post("/api/ai/chat", headers={"X-User-Role": "Employee"}, json=payload)
    assert resp_emp.status_code == 403, resp_emp.text

    # 2. Simulated provider timeout / error fallback
    install_scripted_provider(monkeypatch, [
        tool_response("read_employee_metric", metric_id="waitingtime", period="2026-09"),
        failed_response("timeout"),
    ])
    resp_fallback = test_client.post("/api/ai/chat", headers={"X-User-Role": "Admin"}, json=payload)
    assert resp_fallback.status_code == 200, resp_fallback.text
    data = resp_fallback.json()["data"]
    assert data["outcome"] == "answer", json.dumps(data, default=str)
    assert data["answer_source"] == "fallback", data
    assert data["provider_usage"]["fallback_outcome"] == "timeout", data["provider_usage"]
    assert data["provider_used"] == "deterministic", data
    assert "6.2" in data["headline"]
    assert "min" in data["headline"].lower()
    assert any(
        item.get("kpi_key", "").casefold().replace("_", "") == "waitingtime"
        and item.get("unit") == "min"
        and item.get("actual") is not None
        and abs(float(item["actual"]) - 6.2) < 0.01
        for item in data.get("typed_evidence", [])
    ), data.get("typed_evidence")


# ===========================================================================
# 6. Response Payload Contract for AiResponseCard
# ===========================================================================

def test_http_response_payload_contract_for_frontend(test_client):
    """Scenario 6: Verify AiChatResponse JSON matches frontend AiResponseCard schema."""
    payload = {
        "prompt": "What was Nadia Fadel's Waiting Time in September 2026?",
        "session_state": {"team": "Inbound", "month": "September", "year": 2026},
    }
    resp = test_client.post("/api/ai/chat", headers={"X-User-Role": "Admin"}, json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    data = body["data"]

    # Verify all essential fields expected by Frontend/src/components/ai/AiResponseCard.tsx
    expected_fields = [
        "outcome",
        "headline",
        "narrative_bullets",
        "visual_cards",
        "citations",
        "deep_links",
        "suggested_followups",
        "resolved_session_state",
        "answer_source",
        "typed_evidence",
    ]
    for field in expected_fields:
        assert field in data, f"Missing expected field '{field}' in response payload"

    assert isinstance(data["narrative_bullets"], list)
    assert isinstance(data["visual_cards"], list)
    assert isinstance(data["citations"], list)
    assert isinstance(data["suggested_followups"], list)
    assert isinstance(data["typed_evidence"], list)
