"""Phase 4 Test Suite: Multi-Turn Conversation Chains & Evidence-Grounded Answers.

Verifies:
1. Chain 1: Metric follow-up and period switch (Waiting Time Sep 2026 -> Aug 2026 -> 2-month trend -> overall score).
2. Chain 2: Same-name ambiguity resolution & identity preservation (Mariam -> choice -> follow-up score -> job title -> subject switch).
3. Chain 3: Department and scope switch with country isolation (Coding UAE -> switch Coding Egypt -> follow-up score).
4. Chain 4: Multi-tool analytical queries (compare_branches and rank_employees).
5. Chain 5: Edge cases, real 0.0 preservation, unavailable data, RBAC restriction, and provider failure fallback.
"""
from __future__ import annotations

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.ai_schemas import (
    AiChatMessage,
    AiChatRequest,
    ConfirmedQueryContext,
    SessionFilterContext,
)
from models.schemas import (
    CallsData,
    EvaluationData,
    GeoBreakdown,
    GeoData,
    PerformanceRecord,
)
from services.ai.catalog import ai_evidence_cache
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.provider_engine import ProviderResponse, TokenUsage
from services.dashboard_record_service import DashboardRecordService
from services.database_record_source import DatabaseRecordSource
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
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()


@pytest.fixture
def synth_records() -> list[PerformanceRecord]:
    recs: list[PerformanceRecord] = []

    # 1. Nadia Fadel in August 2026 (Waiting Time = 6.8 min, Score = 88.5%)
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
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 88.5, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )
    # 2. Nadia Fadel in September 2026 (Waiting Time = 6.2 min, Score = 91.0%, Abandon Rate = 0.0%)
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
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 91.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 3. Mariam Ali in September 2026 (Score = 87.0%)
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
    # Mariam Ali in August 2026
    r_mariam_ali_aug = PerformanceRecord(
        id="Inbound_EMP601_2026_Aug",
        employee_id="EMP601",
        employee_name="Mariam Ali",
        team="Inbound",
        month="August",
        year=2026,
        region="EGY",
        branch="dubai",
        raw_data={"Branch": "Dubai"},
        position="Call Center Agent",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=84.0, grade="C"),
        calls=CallsData(inbound=280, total_handled=320, abandoned=12),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=70, sharjah=25, ajman=10, clinics=5),
            attended=GeoBreakdown(dubai=60, sharjah=20, ajman=8, clinics=4),
        ),
        kpi_values=[
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 84.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 4. Mariam Hassan in September 2026 (Score = 79.0%)
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

    # 5. Tarek Omar in September 2026 (Score = 79.5%)
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
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 79.5, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 6. Coding UAE (Hassan Zaki, EMP701)
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

    # 7. Coding Egypt (Mona Samir, EMP801)
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
        r_mariam_ali,
        r_mariam_ali_aug,
        r_mariam_hassan,
        r_tarek,
        r_coding_uae,
        r_coding_egy,
    ])
    return recs


def _patch_sources(monkeypatch, records: list[PerformanceRecord]):
    monkeypatch.setattr(DatabaseRecordSource, "get_all", lambda *args, **kwargs: records)
    monkeypatch.setattr(DashboardRecordService, "list_analysis_records", lambda *args, **kwargs: records)
    monkeypatch.setattr(DashboardRecordService, "list_record_index", lambda *args, **kwargs: None)


# ===========================================================================
# Chain 1: Metric Follow-Up and Period Switch
# ===========================================================================

def test_chain1_waiting_time_period_switch_and_metric_followup(memory_db, synth_records, monkeypatch):
    """Chain 1: Turn 1 Waiting Time Sep -> Turn 2 Aug -> Turn 3 Trend -> Turn 4 Overall Score."""
    _patch_sources(monkeypatch, synth_records)
    install_scripted_provider(monkeypatch, [
        tool_response("read_employee_metric", metric_id="waitingtime", period="2026-09"),
        failed_response("timeout"),
        tool_response("read_employee_metric", metric_id="waitingtime", period="2026-08"),
        failed_response("timeout"),
        tool_response("get_employee_history", metric_id="waitingtime", periods=["2026-08", "2026-09"]),
        failed_response("timeout"),
        tool_response("read_employee_metric", metric_id="overall_score", period="2026-09"),
        failed_response("timeout"),
    ])
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    orchestrator = PmsAiOrchestrator(memory_db, admin_scope)

    # Turn 1: Sep 2026 Waiting Time
    req1 = AiChatRequest(
        prompt="What was Nadia Fadel's Waiting Time in September 2026?",
        session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
    )
    resp1 = orchestrator.run_chat_turn(req1)
    assert resp1.outcome == "answer"
    assert "6.2" in resp1.headline
    assert "min" in resp1.headline.lower()
    assert "Nadia" in resp1.headline
    assert resp1.answer_source in ("model_synthesis", "fallback")
    assert resp1.resolved_session_state.employee_id == "EMP501"

    # Turn 2: Period switch to August
    req2 = AiChatRequest(
        prompt="And in August?",
        session_state=resp1.resolved_session_state,
        history=[
            AiChatMessage(role="user", content=req1.prompt),
            AiChatMessage(role="assistant", content=resp1.headline),
        ],
    )
    resp2 = orchestrator.run_chat_turn(req2)
    assert resp2.outcome == "answer"
    assert "6.8" in resp2.headline
    assert "min" in resp2.headline.lower()
    assert "August" in resp2.headline or "Aug" in resp2.headline

    # Turn 3: 2-month trend question
    req3 = AiChatRequest(
        prompt="How did her Waiting Time change over time?",
        session_state=resp2.resolved_session_state,
        history=[
            AiChatMessage(role="user", content=req1.prompt),
            AiChatMessage(role="assistant", content=resp1.headline),
            AiChatMessage(role="user", content=req2.prompt),
            AiChatMessage(role="assistant", content=resp2.headline),
        ],
    )
    resp3 = orchestrator.run_chat_turn(req3)
    assert resp3.outcome == "answer"
    assert ("6.8" in resp3.headline and "6.2" in resp3.headline) or any("6.8" in b for b in resp3.narrative_bullets)
    assert "0.6" in resp3.headline or any("0.6" in b for b in resp3.narrative_bullets)
    assert "improvement" in resp3.headline.lower() or "improved" in resp3.headline.lower() or any("improvement" in b.lower() for b in resp3.narrative_bullets)

    # Turn 4: Metric switch to Overall Score
    req4 = AiChatRequest(
        prompt="What is her overall score?",
        session_state=resp3.resolved_session_state,
        history=[
            AiChatMessage(role="user", content=req3.prompt),
            AiChatMessage(role="assistant", content=resp3.headline),
        ],
    )
    resp4 = orchestrator.run_chat_turn(req4)
    assert resp4.outcome == "answer"
    assert "91" in resp4.headline
    assert "%" in resp4.headline


# ===========================================================================
# Chain 2: Same-Name Ambiguity Resolution & Identity Preservation
# ===========================================================================

def test_chain2_mariam_disambiguation_selection_and_identity_retention(memory_db, synth_records, monkeypatch):
    """Chain 2: Ambiguity -> selection choice -> follow-up score -> job title -> subject switch."""
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    orchestrator = PmsAiOrchestrator(memory_db, admin_scope)

    # Turn 1: Ambiguous prompt "Show performance for Mariam"
    req1 = AiChatRequest(
        prompt="Show performance for Mariam",
        session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
    )
    resp1 = orchestrator.run_chat_turn(req1)
    assert resp1.outcome == "clarification"
    assert resp1.clarification is not None
    choice_ids = [c.id for c in (resp1.resolved_session_state.last_confirmed_query.pending_clarification_choices or [])]
    assert "choice-person-EMP601" in choice_ids

    # Turn 2: User selects Mariam Ali
    req2 = AiChatRequest(
        prompt=req1.prompt,
        clarification_choice_id="choice-person-EMP601",
        session_state=resp1.resolved_session_state,
    )
    resp2 = orchestrator.run_chat_turn(req2)
    assert resp2.outcome == "answer"
    assert "87" in resp2.headline
    assert "Mariam Ali" in resp2.headline
    assert resp2.resolved_session_state.employee_id == "EMP601"

    # Turn 3: "What was her score in August?" -> preserves Mariam Ali WITHOUT re-asking!
    req3 = AiChatRequest(
        prompt="What was her score in August 2026?",
        session_state=resp2.resolved_session_state,
        history=[
            AiChatMessage(role="user", content="Mariam Ali"),
            AiChatMessage(role="assistant", content=resp2.headline),
        ],
    )
    resp3 = orchestrator.run_chat_turn(req3)
    assert resp3.outcome == "answer"
    assert "84" in resp3.headline
    assert "Mariam Ali" in resp3.headline

    # Turn 4: "What is her job title?" -> preserves Mariam Ali, reports position
    req4 = AiChatRequest(
        prompt="What is her job title?",
        session_state=resp3.resolved_session_state,
        history=[
            AiChatMessage(role="user", content=req3.prompt),
            AiChatMessage(role="assistant", content=resp3.headline),
        ],
    )
    resp4 = orchestrator.run_chat_turn(req4)
    assert resp4.outcome == "answer"
    assert "Call Center Agent" in resp4.headline or any("Call Center Agent" in b for b in resp4.narrative_bullets)
    assert "Mariam" in resp4.headline

    # Turn 5: User explicitly switches subject to Tarek Omar
    req5 = AiChatRequest(
        prompt="What about Tarek Omar's score?",
        session_state=resp4.resolved_session_state,
        history=[
            AiChatMessage(role="user", content=req4.prompt),
            AiChatMessage(role="assistant", content=resp4.headline),
        ],
    )
    resp5 = orchestrator.run_chat_turn(req5)
    assert resp5.outcome == "answer"
    assert "79.5" in resp5.headline
    assert "Tarek" in resp5.headline
    assert resp5.resolved_session_state.employee_id == "EMP502"


# ===========================================================================
# Chain 3: Department Switch with Country Isolation
# ===========================================================================

def test_chain3_scope_department_switch_with_country_isolation(memory_db, synth_records, monkeypatch):
    """Chain 3: Coding UAE -> switch Coding Egypt -> follow-up score."""
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    orchestrator = PmsAiOrchestrator(memory_db, admin_scope)

    # Turn 1: Coding UAE Quality Errors
    req1 = AiChatRequest(
        prompt="What is Hassan Zaki's Quality Errors in September 2026?",
        session_state=SessionFilterContext(team="Coding", region="UAE", month="September", year=2026),
    )
    resp1 = orchestrator.run_chat_turn(req1)
    assert resp1.outcome == "answer"
    assert "2.5" in resp1.headline
    assert "Hassan" in resp1.headline

    # Turn 2: Switch to Egypt Coding team
    req2 = AiChatRequest(
        prompt="What is Mona Samir's Quality Errors in Coding EGY in September 2026?",
        session_state=resp1.resolved_session_state,
    )
    resp2 = orchestrator.run_chat_turn(req2)
    assert resp2.outcome == "answer"
    assert "1.8" in resp2.headline
    assert "Mona" in resp2.headline

    # Turn 3: Follow-up score in Coding EGY
    req3 = AiChatRequest(
        prompt="What is her overall score?",
        session_state=resp2.resolved_session_state,
        history=[
            AiChatMessage(role="user", content=req2.prompt),
            AiChatMessage(role="assistant", content=resp2.headline),
        ],
    )
    resp3 = orchestrator.run_chat_turn(req3)
    assert resp3.outcome == "answer"
    assert "94.5" in resp3.headline
    assert "Mona" in resp3.headline


# ===========================================================================
# Chain 4: Multi-Tool & Analytical Queries
# ===========================================================================

def test_chain4_multi_tool_compound_analytics(memory_db, synth_records, monkeypatch):
    """Chain 4: compare_branches and rank_employees."""
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    orchestrator = PmsAiOrchestrator(memory_db, admin_scope)

    # Turn 1: compare_branches
    req1 = AiChatRequest(
        prompt="Compare Dubai and Sharjah bookings handled by Egypt-based Inbound in September 2026.",
        session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
    )
    resp1 = orchestrator.run_chat_turn(req1)
    assert resp1.outcome == "answer"
    assert len(resp1.tool_calls) >= 1
    assert any("compare_branches" in tc.tool_name or "kpi_diagnosis" in tc.tool_name for tc in resp1.tool_calls)

    # Turn 2: rank_employees
    req2 = AiChatRequest(
        prompt="Rank employees in Inbound in September 2026",
        session_state=resp1.resolved_session_state,
    )
    resp2 = orchestrator.run_chat_turn(req2)
    assert resp2.outcome == "answer"
    assert len(resp2.tool_calls) >= 1
    assert any("rank" in tc.tool_name or "people_contribution" in tc.tool_name for tc in resp2.tool_calls)


def test_uae_based_inbound_staff_does_not_reuse_egy_records(memory_db, synth_records, monkeypatch):
    """An explicit UAE employee-region request cannot reuse Egypt-based Inbound records."""
    _patch_sources(monkeypatch, synth_records)
    monkeypatch.setattr("services.ai.orchestrator.local_exploration_enabled", lambda: False)
    provider_requests = install_scripted_provider(
        monkeypatch,
        {
            "response_type": "tool_call",
            "tool_name": "get_employee_history",
            "tool_arguments": {
                "team": "Inbound",
                "metric_id": "overall_score",
                "period": "2026-09",
            },
        },
    )
    orchestrator = PmsAiOrchestrator(
        memory_db,
        {"role": "Admin", "has_unrestricted_team_access": True},
    )

    response = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="What was the overall score for UAE-based Inbound employees in September 2026?",
            session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
        )
    )

    assert response.outcome == "unavailable_data"
    assert response.resolved_session_state.region == "UAE"
    assert response.typed_evidence == []
    assert response.provider_usage.route_used == "model_led_pilot"
    assert provider_requests


# ===========================================================================
# Chain 5: Edge Cases, Real Zero, and Security Boundaries
# ===========================================================================

def test_chain5_edge_cases_zero_preservation_and_fallback(memory_db, synth_records, monkeypatch):
    """Chain 5: Real 0.0 preservation, unavailable data, self-only RBAC, and failure fallback."""
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    orchestrator = PmsAiOrchestrator(memory_db, admin_scope)

    # 1. Real 0.0% abandon rate preserved
    req1 = AiChatRequest(
        prompt="What was Nadia Fadel's abandon rate in September 2026?",
        session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
    )
    resp1 = orchestrator.run_chat_turn(req1)
    assert resp1.outcome == "answer"
    assert "0" in resp1.headline
    assert "%" in resp1.headline

    # 2. Unavailable data period (January 2020)
    req2 = AiChatRequest(
        prompt="What was Nadia Fadel's Waiting Time in January 2020?",
        session_state=SessionFilterContext(team="Inbound", month="January", year=2020),
    )
    install_scripted_provider(monkeypatch, tool_response("read_employee_metric", metric_id="waitingtime", period="2020-01"))
    resp2 = orchestrator.run_chat_turn(req2)
    assert resp2.outcome in ("unavailable_data", "clarification")
    assert "no published" in resp2.headline.lower() or "not found" in resp2.headline.lower()

    # 3. Self-only RBAC boundary
    self_scope = {"role": "Employee", "is_self_only": True, "employee_id": "EMP501", "user_id": "u-emp501"}
    self_orch = PmsAiOrchestrator(memory_db, self_scope)
    req3 = AiChatRequest(
        prompt="What was Tarek Omar's Waiting Time in September 2026?",
        session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
    )
    resp3 = self_orch.run_chat_turn(req3)
    assert resp3.outcome == "restricted_access"

    # 4. Graceful provider failure fallback
    install_scripted_provider(monkeypatch, [
        tool_response("read_employee_metric", metric_id="waitingtime", period="2026-09"),
        failed_response("timeout"),
    ])
    req4 = AiChatRequest(
        prompt="What was Nadia Fadel's Waiting Time in September 2026?",
        session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
    )
    resp4 = orchestrator.run_chat_turn(req4)
    assert resp4.outcome == "answer"
    assert resp4.answer_source == "fallback"
    assert "6.2" in resp4.headline


def test_self_only_team_ranking_is_denied_before_ranking_tool(memory_db, synth_records, monkeypatch):
    """A self-scoped employee cannot invoke organizational ranking, even for their own team."""
    _patch_sources(monkeypatch, synth_records)
    monkeypatch.setattr("services.ai.orchestrator.local_exploration_enabled", lambda: False)

    def fail_if_ranking_runs(*args, **kwargs):
        raise AssertionError("self-only organizational ranking reached a data tool")

    monkeypatch.setattr(
        "services.ai.tool_registry.DeterministicToolRegistry.execute_agent_spotlight_and_trend",
        fail_if_ranking_runs,
    )
    monkeypatch.setattr(
        "services.ai.tool_registry.DeterministicToolRegistry.execute_people_contribution_and_rankings",
        fail_if_ranking_runs,
    )

    ai_evidence_cache.clear()
    self_scope = {
        "role": "Employee",
        "is_self_only": True,
        "employee_id": "EMP501",
        "user_id": "u-emp501",
        "accessible_teams": ["Inbound"],
    }
    self_orch = PmsAiOrchestrator(memory_db, self_scope)
    response = self_orch.run_chat_turn(
        AiChatRequest(
            prompt="Who had the highest bookings count in Inbound in September 2026?",
            session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
        )
    )

    assert response.outcome == "restricted_access"
    assert "Access restricted" in response.headline
    assert response.tool_calls == []
    assert response.typed_evidence == []


def test_self_only_named_booking_count_keeps_employee_scope(memory_db, synth_records, monkeypatch):
    """A self-scoped user asking for their own count must not fall through to a team aggregate."""
    _patch_sources(monkeypatch, synth_records)
    monkeypatch.setattr("services.ai.orchestrator.local_exploration_enabled", lambda: False)
    monkeypatch.setenv("PMS_AI_INTENT_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_SYNTHESIS_ENABLED", "false")

    self_scope = {
        "role": "Employee",
        "is_self_only": True,
        "employee_id": "EMP501",
        "user_id": "u-emp501",
        "accessible_teams": ["Inbound"],
    }
    response = PmsAiOrchestrator(memory_db, self_scope).run_chat_turn(
        AiChatRequest(
            prompt="How many bookings did Nadia Fadel have in September 2026?",
            session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
        )
    )

    own_record = next(
        record
        for record in synth_records
        if record.employee_id == "EMP501" and record.month == "September" and record.year == 2026
    )
    expected_count = sum(
        getattr(own_record.geo.bookings, branch)
        for branch in ("dubai", "sharjah", "ajman", "clinics")
    )

    assert response.outcome == "answer"
    assert response.typed_evidence
    assert all(item.employee_id == "EMP501" for item in response.typed_evidence), [
        item.model_dump(mode="json") for item in response.typed_evidence
    ]
    booking_evidence = [item for item in response.typed_evidence if item.metric_id.endswith("bookings_count")]
    assert booking_evidence
    assert all(item.employee_name == "Nadia Fadel" for item in booking_evidence)
    current_booking_evidence = [item for item in booking_evidence if item.period == "September 2026"]
    assert len(current_booking_evidence) == 1
    assert current_booking_evidence[0].actual == expected_count
    assert not any(
        call.tool_name in {"rank_employees", "get_kpi_diagnosis", "get_kpi_diagnosis_and_trends"}
        for call in response.tool_calls
    )


@pytest.mark.parametrize(
    "prompt",
    [
        "What was Nadia Fadel's booking count in September 2026?",
        "How many bookings did Nadia Fadel have in September 2026?",
        "How many bookings did EMP501 have in September 2026?",
    ],
    ids=["possessive-name", "interrogative-name", "employee-id"],
)
def test_model_led_planner_binds_explicit_employee_and_exact_booking_count(
    memory_db, synth_records, monkeypatch, prompt
):
    """A model-selected team diagnostic is canonicalized to the locally resolved person read."""
    _patch_sources(monkeypatch, synth_records)
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    expected_response = {
        "response_type": "tool_call",
        "tool_name": "get_kpi_diagnosis",
        "tool_arguments": {
            "team": "Inbound",
            "metric_id": "bookings_count",
            "period": "2026-09",
        },
    }
    install_scripted_provider(monkeypatch, expected_response)

    response = PmsAiOrchestrator(
        memory_db,
        {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True},
    ).run_chat_turn(
        AiChatRequest(
            prompt=prompt,
            session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
        )
    )

    expected_count = sum((130, 45, 25, 10))
    assert response.outcome == "answer"
    assert response.provider_usage.route_used == "model_led_pilot"
    assert response.validated_plan_v2.scope.employee_id == "EMP501"
    assert response.tool_calls[0].tool_name == "read_employee_metric"
    assert response.tool_calls[0].arguments["employee_id"] == "EMP501"
    current_booking_evidence = [
        item
        for item in response.typed_evidence
        if item.metric_id.endswith("bookings_count") and item.period == "September 2026"
    ]
    assert len(current_booking_evidence) == 1
    assert current_booking_evidence[0].actual == expected_count
    assert current_booking_evidence[0].employee_id == "EMP501"
    assert current_booking_evidence[0].employee_name == "Nadia Fadel"


def test_model_led_followup_pronoun_keeps_validated_employee_and_count(memory_db, synth_records, monkeypatch):
    """A pronoun inherits the previously validated person while the model selects a team tool."""
    _patch_sources(monkeypatch, synth_records)
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(
        monkeypatch,
        [
            {
                "response_type": "tool_call",
                "tool_name": "get_kpi_diagnosis",
                "tool_arguments": {
                    "team": "Inbound",
                    "metric_id": "waitingtime",
                    "period": "2026-09",
                },
            },
            {
                "response_type": "tool_call",
                "tool_name": "get_kpi_diagnosis",
                "tool_arguments": {
                    "team": "Inbound",
                    "metric_id": "bookings_count",
                    "period": "2026-09",
                },
            },
        ],
    )
    orchestrator = PmsAiOrchestrator(
        memory_db,
        {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True},
    )
    first = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="What was Nadia Fadel's Waiting Time in September 2026?",
            session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
        )
    )
    followup = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="How many bookings did she have in September 2026?",
            session_state=first.resolved_session_state,
            history=[
                AiChatMessage(role="user", content="What was Nadia Fadel's Waiting Time in September 2026?"),
                AiChatMessage(role="assistant", content=first.headline),
            ],
        )
    )

    current_booking_evidence = [
        item
        for item in followup.typed_evidence
        if item.metric_id.endswith("bookings_count") and item.period == "September 2026"
    ]
    assert followup.outcome == "answer", (
        followup.headline,
        {
            "employee_id": followup.structured_query.employee_id,
            "employee_name": followup.structured_query.employee_name,
            "team": followup.structured_query.team,
            "branch": followup.structured_query.branch,
            "performance_level": followup.structured_query.performance_level,
            "periods": followup.structured_query.periods,
        }
        if followup.structured_query
        else None,
        [
            {"tool_name": call.tool_name, "arguments": call.arguments, "records_evaluated": call.records_evaluated}
            for call in followup.tool_calls
        ],
        [item.model_dump(mode="json") for item in followup.typed_evidence],
    )
    assert followup.validated_plan_v2.scope.employee_id == "EMP501"
    assert followup.tool_calls[0].tool_name == "read_employee_metric"
    assert len(current_booking_evidence) == 1
    assert current_booking_evidence[0].actual == sum((130, 45, 25, 10))
    assert current_booking_evidence[0].employee_id == "EMP501"


def test_model_led_team_period_query_ignores_model_invented_employee(memory_db, monkeypatch):
    """A model tool argument cannot turn a team trend into a named employee read."""
    months = ("August", "September")
    records = []
    for employee_id, employee_name, counts in (
        ("EMP901", "Omar Khalid", (100, 130)),
        ("EMP902", "Laila Nasser", (40, 70)),
    ):
        for month, count in zip(months, counts):
            records.append(
                PerformanceRecord(
                    id=f"Outbound_{employee_id}_2026_{month}",
                    employee_id=employee_id,
                    employee_name=employee_name,
                    team="Outbound",
                    month=month,
                    year=2026,
                    region="EGY",
                    branch="all",
                    raw_data={},
                    position="Outbound Sales Agent",
                    performance_level="Employee",
                    status="On Track",
                    evaluation=EvaluationData(score=90.0, grade="A"),
                    calls=CallsData(outbound=200, total_handled=200, abandoned=0),
                    geo=GeoData(bookings=GeoBreakdown(dubai=count, sharjah=0, ajman=0, clinics=0)),
                    kpi_values=[
                        {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 90.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"}
                    ],
                )
            )
    _patch_sources(monkeypatch, records)
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(
        monkeypatch,
        {
            "response_type": "tool_call",
            "tool_name": "get_employee_history",
            "tool_arguments": {
                "employee_id": "EMP901",
                "employee_name": "Omar Khalid",
                "team": "Outbound",
                "metric_id": "bookings_count",
                "periods": ["2026-08", "2026-09"],
            },
        },
    )

    response = PmsAiOrchestrator(
        memory_db,
        {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True},
    ).run_chat_turn(
        AiChatRequest(
            prompt="How did Outbound bookings change between August and September 2026?",
            session_state=SessionFilterContext(team="Outbound"),
        )
    )

    assert response.outcome == "answer"
    assert response.validated_plan_v2.scope.employee_id is None
    assert response.tool_calls[0].tool_name == "get_score_trend"
    assert not response.tool_calls[0].arguments.get("employee_id")
    booking_evidence = [item for item in response.typed_evidence if item.metric_id.endswith("bookings_count")]
    assert booking_evidence
    assert all(item.employee_id is None for item in booking_evidence)
    assert {(item.period, item.actual) for item in booking_evidence} == {
        ("August 2026", 140.0),
        ("September 2026", 200.0),
    }


def test_model_led_direct_person_read_returns_exact_employee_period(memory_db, monkeypatch):
    """A valid employee tool call reads the exact employee-period row and its typed score."""
    adham_aug = PerformanceRecord(
        id="Inbound_EMP102_2026_Aug",
        employee_id="EMP102",
        employee_name="Adham Tarek",
        team="Inbound",
        month="August",
        year=2026,
        region="EGY",
        raw_data={},
        position="Inbound Agent",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=96.5, grade="A"),
        geo=GeoData(bookings=GeoBreakdown(dubai=40, sharjah=35, ajman=25, clinics=0)),
        kpi_values=[
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 96.5, "target_value": 85.0, "unit": "%", "direction": "higher_better"}
        ],
    )
    _patch_sources(monkeypatch, [adham_aug])
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(
        monkeypatch,
        {
            "response_type": "tool_call",
            "tool_name": "read_employee_metric",
            "tool_arguments": {
                "employee_name": "Adham Tarek",
                "team": "Inbound",
                "metric_id": "overall_score",
                "period": "2026-08",
            },
        },
    )

    response = PmsAiOrchestrator(
        memory_db,
        {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True},
    ).run_chat_turn(
        AiChatRequest(
            prompt="What was Adham Tarek's overall score in August 2026?",
            session_state=SessionFilterContext(team="Inbound"),
        )
    )

    evidence = [
        item
        for item in response.typed_evidence
        if item.metric_id.endswith("overall_score") and item.period == "August 2026"
    ]
    assert response.outcome == "answer"
    assert response.validated_plan_v2.scope.employee_id == "EMP102"
    assert response.tool_calls[0].tool_name == "read_employee_metric"
    assert evidence
    assert all(item.actual == 96.5 for item in evidence)
    assert all(item.employee_id == "EMP102" for item in evidence)
    assert all(item.employee_name == "Adham Tarek" for item in evidence)


def test_model_led_explicit_employee_overrides_inherited_team_scope(memory_db, monkeypatch):
    """An explicitly named employee resolves to their authorized team, not the prior turn's team."""
    omar_aug = PerformanceRecord(
        id="Outbound_EMP201_2026_Aug",
        employee_id="EMP201",
        employee_name="Omar Khalid",
        team="Outbound",
        month="August",
        year=2026,
        region="EGY",
        raw_data={},
        position="Outbound Specialist",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=89.0, grade="B"),
        geo=GeoData(bookings=GeoBreakdown(dubai=80, sharjah=90, ajman=90, clinics=40)),
    )
    _patch_sources(monkeypatch, [omar_aug])
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(
        monkeypatch,
        {
            "response_type": "tool_call",
            "tool_name": "read_employee_metric",
            "tool_arguments": {
                "employee_name": "Omar Khalid",
                "team": "Inbound",
                "metric_id": "overall_score",
                "period": "2026-08",
            },
        },
    )

    prior = ConfirmedQueryContext(
        intent="current_value",
        team="Inbound",
        function="Call Center",
        performance_level="Employee",
        metric_id="inbound:overall_score",
        periods=["2026-09"],
        last_subject_employee_id="EMP101",
        last_subject_employee_name="Sara Mahmoud",
    )
    response = PmsAiOrchestrator(
        memory_db,
        {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True},
    ).run_chat_turn(
        AiChatRequest(
            prompt="What was Omar Khalid's overall score in August 2026?",
            session_state=SessionFilterContext(
                team="Inbound",
                function="Call Center",
                performance_level="Employee",
                month="September",
                year=2026,
                last_confirmed_query=prior,
            ),
        )
    )

    evidence = [
        item
        for item in response.typed_evidence
        if item.kpi_key == "overall_score" and item.period == "August 2026"
    ]
    assert response.outcome == "answer"
    assert response.validated_plan_v2.scope.employee_id == "EMP201"
    assert response.validated_plan_v2.scope.team == "Outbound"
    assert response.tool_calls[0].arguments["team"] == "Outbound"
    assert evidence
    assert all(item.actual == 89.0 and item.employee_id == "EMP201" for item in evidence)


def test_model_led_call_center_ranking_uses_the_named_source_team(memory_db, monkeypatch):
    """A Call Center ranking is scoped to the named source team, not defaulted to Inbound."""
    records = [
        PerformanceRecord(
            id=f"Call Center_{employee_id}_2026_Sep",
            employee_id=employee_id,
            employee_name=employee_name,
            team="Inbound" if employee_id == "EMP101" else "Call Center",
            month="September",
            year=2026,
            region="EGY",
            raw_data={},
            position=position,
            performance_level="Employee",
            status="On Track",
            evaluation=EvaluationData(score=score, grade="C" if score == 62.0 else "A"),
            geo=GeoData(bookings=GeoBreakdown(dubai=0, sharjah=0, ajman=0, clinics=0)),
        )
        for employee_id, employee_name, position, score in (
            ("EMP301", "Kareem Adel", "Quality Assurance", 62.0),
            ("EMP302", "Ziad Nabil", "Trainer", 62.0),
            ("EMP303", "Nour Hassan", "Workforce analyst", 93.0),
            ("EMP101", "Sara Mahmoud", "Call Center Agent", 94.0),
        )
    ]
    _patch_sources(monkeypatch, records)
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(
        monkeypatch,
        {
            "response_type": "tool_call",
            "tool_name": "rank_employees",
            "tool_arguments": {
                "team": "Inbound",
                "metric_id": "overall_score",
                "direction": "best",
                "period": "2026-09",
                "limit": 5,
            },
        },
    )

    response = PmsAiOrchestrator(
        memory_db,
        {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True},
    ).run_chat_turn(
        AiChatRequest(
            prompt="Who had the lowest overall score in Call Center in September 2026, including ties?",
            session_state=SessionFilterContext(),
        )
    )

    tied_evidence = [item for item in response.typed_evidence if item.employee_id in {"EMP301", "EMP302"}]
    assert response.outcome == "answer", (
        response.headline,
        response.structured_query.model_dump() if response.structured_query else None,
        response.validated_plan_v2.scope.model_dump() if response.validated_plan_v2 else None,
        [call.model_dump() for call in response.tool_calls],
    )
    assert response.validated_plan_v2.scope.team == "Call Center"
    assert response.tool_calls[0].tool_name == "rank_employees"
    assert response.tool_calls[0].arguments["team"] == "Call Center"
    assert {item.employee_id for item in tied_evidence} == {"EMP301", "EMP302"}
    assert all(item.actual == 62.0 for item in tied_evidence)
    assert not any(item.employee_id == "EMP101" for item in response.typed_evidence)


def test_model_led_single_reading_team_kpi_keeps_team_scope(memory_db, monkeypatch):
    """A team question and its short follow-up retain team scope with one published reading."""
    salma = PerformanceRecord(
        id="Coding EGY_EMP501_2026_Sep",
        employee_id="EMP501",
        employee_name="Salma Youssef",
        team="Coding EGY",
        month="September",
        year=2026,
        region="EGY",
        raw_data={},
        position="Call Center Agent",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=89.0, grade="B"),
        geo=GeoData(bookings=GeoBreakdown(dubai=0, sharjah=0, ajman=0, clinics=0)),
        kpi_values=[
            {
                "kpi_key": "QualityErrors",
                "label": "Quality Errors",
                "actual_value": 1.8,
                "target_value": 3.0,
                "unit": "%",
                "direction": "lower_better",
            }
        ],
    )
    _patch_sources(monkeypatch, [salma])
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(
        monkeypatch,
        {
            "response_type": "tool_call",
            "tool_name": "read_employee_metric",
            "tool_arguments": {
                "team": "Coding EGY",
                "metric_id": "quality_errors_rate",
                "period": "2026-09",
            },
        },
    )
    orchestrator = PmsAiOrchestrator(
        memory_db,
        {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True},
    )
    first = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="What was the Quality Errors rate for Coding EGY in September 2026?",
            session_state=SessionFilterContext(team="Coding EGY", function="RCM", region="EGY"),
        )
    )
    followup = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="And the rate?",
            session_state=first.resolved_session_state,
        )
    )

    assert first.outcome == "answer", (
        first.headline,
        first.structured_query.model_dump() if first.structured_query else None,
        first.validated_plan_v2.scope.model_dump() if first.validated_plan_v2 else None,
        [call.model_dump() for call in first.tool_calls],
    )
    assert any(item.actual == 1.8 and item.sample_size == 1 for item in first.typed_evidence)
    assert all(item.team == "Coding EGY" and not item.employee_id for item in first.typed_evidence)
    assert first.resolved_session_state.employee_id is None
    assert first.resolved_session_state.last_confirmed_query.last_subject_employee_id is None
    followup_evidence = [
        item
        for item in followup.typed_evidence
        if item.kpi_key.casefold() in {"qualityerrors", "quality_errors"}
    ]
    assert followup.outcome == "answer"
    assert followup.validated_plan_v2.scope.employee_id is None
    assert followup_evidence
    assert all(item.actual == 1.8 and item.team == "Coding EGY" and not item.employee_id for item in followup_evidence)


def test_model_led_person_correction_and_followup_keep_new_subject(memory_db, monkeypatch):
    """A corrected person replaces the prior subject for the current and next period read."""
    records = [
        PerformanceRecord(
            id="Inbound_EMP601_2026_Sep",
            employee_id="EMP601",
            employee_name="Mariam Ali",
            team="Inbound",
            month="September",
            year=2026,
            region="EGY",
            raw_data={},
            position="Call Center Agent",
            performance_level="Employee",
            status="On Track",
            evaluation=EvaluationData(score=87.0, grade="B"),
            geo=GeoData(bookings=GeoBreakdown(dubai=80, sharjah=30, ajman=10, clinics=5)),
        ),
        PerformanceRecord(
            id="Inbound_EMP102_2026_Sep",
            employee_id="EMP102",
            employee_name="Adham Tarek",
            team="Inbound",
            month="September",
            year=2026,
            region="EGY",
            raw_data={},
            position="Inbound Agent",
            performance_level="Employee",
            status="On Track",
            evaluation=EvaluationData(score=91.0, grade="A"),
            geo=GeoData(bookings=GeoBreakdown(dubai=40, sharjah=35, ajman=25, clinics=0)),
        ),
        PerformanceRecord(
            id="Inbound_EMP102_2026_Aug",
            employee_id="EMP102",
            employee_name="Adham Tarek",
            team="Inbound",
            month="August",
            year=2026,
            region="EGY",
            raw_data={},
            position="Inbound Agent",
            performance_level="Employee",
            status="On Track",
            evaluation=EvaluationData(score=96.5, grade="A"),
            geo=GeoData(bookings=GeoBreakdown(dubai=40, sharjah=35, ajman=25, clinics=0)),
        ),
    ]
    _patch_sources(monkeypatch, records)
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(
        monkeypatch,
        {
            "response_type": "tool_call",
            "tool_name": "get_kpi_diagnosis",
            "tool_arguments": {
                "team": "Inbound",
                "metric_id": "overall_score",
                "period": "2026-09",
            },
        },
    )
    orchestrator = PmsAiOrchestrator(
        memory_db,
        {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True},
    )
    prior = ConfirmedQueryContext(
        intent="current_value",
        team="Inbound",
        performance_level="Employee",
        metric_id="overall_score",
        periods=["2026-09"],
        single_person=True,
        last_subject_employee_id="EMP601",
        last_subject_employee_name="Mariam Ali",
    )
    corrected = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="Not Mariam Ali — show me Adham Tarek instead.",
            session_state=SessionFilterContext(
                team="Inbound",
                month="September",
                year=2026,
                last_confirmed_query=prior,
            ),
        )
    )
    followup = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="What was Adham Tarek's overall score in August 2026?",
            session_state=corrected.resolved_session_state,
        )
    )

    corrected_evidence = [item for item in corrected.typed_evidence if item.kpi_key == "overall_score"]
    followup_evidence = [
        item
        for item in followup.typed_evidence
        if item.kpi_key == "overall_score" and item.period == "August 2026"
    ]
    assert corrected.outcome == "answer"
    assert corrected.validated_plan_v2.scope.employee_id == "EMP102"
    assert corrected.tool_calls[0].tool_name == "read_employee_metric"
    assert corrected_evidence
    assert all(item.actual == 91.0 and item.employee_id == "EMP102" for item in corrected_evidence)
    assert followup.outcome == "answer", (
        followup.headline,
        {
            "employee_id": followup.structured_query.employee_id,
            "team": followup.structured_query.team,
            "branch": followup.structured_query.branch,
            "performance_level": followup.structured_query.performance_level,
        }
        if followup.structured_query
        else None,
        [
            {
                "tool_name": call.tool_name,
                "employee_id": call.arguments.get("employee_id"),
                "employee_name": call.arguments.get("employee_name"),
                "team": call.arguments.get("team"),
                "branch": call.arguments.get("branch"),
                "performance_level": call.arguments.get("performance_level"),
                "metric_id": call.arguments.get("metric_id"),
                "period": call.arguments.get("period"),
                "records_evaluated": call.records_evaluated,
            }
            for call in followup.tool_calls
        ],
        len(followup.typed_evidence),
    )
    assert followup.validated_plan_v2.scope.employee_id == "EMP102"
    assert followup.tool_calls[0].tool_name == "read_employee_metric"
    assert followup_evidence
    assert all(item.actual == 96.5 and item.employee_id == "EMP102" for item in followup_evidence)


def test_model_led_fresh_chat_reads_overall_score_from_performance_record(memory_db, monkeypatch):
    """A person score is available from the published evaluation even without a duplicated KPI row."""
    mariam = PerformanceRecord(
        id="Inbound_EMP601_2026_Aug",
        employee_id="EMP601",
        employee_name="Mariam Ali",
        team="Inbound",
        month="August",
        year=2026,
        region="EGY",
        raw_data={},
        position="Call Center Agent",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=88.0, grade="B"),
        geo=GeoData(bookings=GeoBreakdown(dubai=70, sharjah=25, ajman=10, clinics=5)),
    )
    _patch_sources(monkeypatch, [mariam])
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(
        monkeypatch,
        {
            "response_type": "tool_call",
            "tool_name": "read_employee_metric",
            "tool_arguments": {
                "employee_name": "Mariam Ali",
                "team": "Inbound",
                "metric_id": "overall_score",
                "period": "2026-08",
            },
        },
    )

    response = PmsAiOrchestrator(
        memory_db,
        {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True},
    ).run_chat_turn(
        AiChatRequest(
            prompt="What was Mariam Ali's overall score in August 2026?",
            session_state=SessionFilterContext(),
        )
    )

    evidence = [
        item
        for item in response.typed_evidence
        if item.kpi_key == "overall_score" and item.period == "August 2026"
    ]
    assert response.outcome == "answer"
    assert response.validated_plan_v2.scope.employee_id == "EMP601"
    assert evidence
    assert all(item.actual == 88.0 and item.employee_id == "EMP601" for item in evidence)


def test_model_led_named_corporate_read_infers_record_level(memory_db, monkeypatch):
    """An explicit person lookup inherits Corporate level from authorized source metadata."""
    mina = PerformanceRecord(
        id="IT_EMP903_2026_Sep",
        employee_id="EMP903",
        employee_name="Mina Fawzi",
        team="IT",
        month="September",
        year=2026,
        region="EGY",
        raw_data={},
        position="IT Director",
        performance_level="Corporate",
        status="On Track",
        evaluation=EvaluationData(score=90.0, grade="A"),
        kpi_values=[
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 90.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"}
        ],
    )
    _patch_sources(monkeypatch, [mina])
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(
        monkeypatch,
        {
            "response_type": "tool_call",
            "tool_name": "read_employee_metric",
            "tool_arguments": {
                "employee_name": "Mina Fawzi",
                "team": "IT",
                "metric_id": "overall_score",
                "period": "2026-09",
            },
        },
    )

    response = PmsAiOrchestrator(
        memory_db,
        {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True},
    ).run_chat_turn(
        AiChatRequest(
            prompt="What was Mina Fawzi's overall score in IT in September 2026?",
            session_state=SessionFilterContext(),
        )
    )

    evidence = [
        item
        for item in response.typed_evidence
        if item.metric_id.endswith("overall_score") and item.period == "September 2026"
    ]
    assert response.outcome == "answer"
    assert response.validated_plan_v2.scope.employee_id == "EMP903"
    assert response.validated_plan_v2.scope.performance_level == "Corporate"
    assert response.tool_calls[0].tool_name == "read_employee_metric"
    assert evidence
    assert all(item.actual == 90.0 for item in evidence)
    assert all(item.employee_id == "EMP903" for item in evidence)


def test_model_led_team_ranking_uses_only_available_managerial_level(memory_db, monkeypatch):
    """A team-only ranking uses its single source level rather than inventing Employee rows."""
    nour = PerformanceRecord(
        id="Sales_EMP904_2026_Sep",
        employee_id="EMP904",
        employee_name="Nour El-Sayed",
        team="Sales",
        month="September",
        year=2026,
        region="UAE",
        raw_data={},
        position="Sales Manager",
        performance_level="Managerial",
        status="On Track",
        evaluation=EvaluationData(score=89.0, grade="B"),
        kpi_values=[
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 89.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"}
        ],
    )
    _patch_sources(monkeypatch, [nour])
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(
        monkeypatch,
        {
            "response_type": "tool_call",
            "tool_name": "rank_employees",
            "tool_arguments": {
                "team": "Sales",
                "metric_id": "overall_score",
                "period": "2026-09",
                "direction": "best",
                "limit": 1,
            },
        },
    )

    response = PmsAiOrchestrator(
        memory_db,
        {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True},
    ).run_chat_turn(
        AiChatRequest(
            prompt="Who had the highest overall score in Sales in September 2026?",
            session_state=SessionFilterContext(),
        )
    )

    assert response.outcome == "answer"
    assert response.validated_plan_v2.scope.performance_level == "Managerial"
    assert response.tool_calls[0].tool_name == "rank_employees"
    assert response.tool_calls[0].arguments["performance_level"] == "Managerial"
    assert any(item.employee_id == "EMP904" and item.actual == 89.0 for item in response.typed_evidence)


def test_explicit_ksa_scope_does_not_return_other_region_records(memory_db, synth_records, monkeypatch):
    """An explicit unsupported country stays a region filter instead of falling back to EGY/UAE data."""
    _patch_sources(monkeypatch, synth_records)
    monkeypatch.setattr("services.ai.orchestrator.local_exploration_enabled", lambda: False)
    provider_requests = install_scripted_provider(
        monkeypatch,
        {
            "response_type": "tool_call",
            "tool_name": "get_employee_history",
            "tool_arguments": {
                "team": "Inbound",
                "metric_id": "bookings_count",
                "period": "2026-09",
            },
        },
    )

    ai_evidence_cache.clear()
    orchestrator = PmsAiOrchestrator(
        memory_db,
        {"role": "Admin", "has_unrestricted_team_access": True},
    )
    response = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="How many Inbound bookings were recorded in Saudi Arabia in September 2026?",
            session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
        )
    )

    assert response.outcome in ("unavailable_data", "clarification"), response.model_dump_json(indent=2)
    assert response.provider_usage.route_used == "model_led_pilot"
    assert provider_requests
    assert response.resolved_session_state.region == "KSA"
    assert response.typed_evidence == []


def test_ksa_scope_is_denied_before_reads_for_region_limited_user(memory_db, synth_records, monkeypatch):
    """An EGY-only region grant cannot query KSA even when the team itself is accessible."""
    _patch_sources(monkeypatch, synth_records)
    monkeypatch.setattr("services.ai.orchestrator.local_exploration_enabled", lambda: False)

    def fail_if_data_tool_runs(*args, **kwargs):
        raise AssertionError("a KSA request escaped the EGY region permission gate")

    monkeypatch.setattr(
        "services.ai.tool_registry.DeterministicToolRegistry.execute_model_led_tool",
        fail_if_data_tool_runs,
    )
    monkeypatch.setattr(
        "services.ai.tool_registry.DeterministicToolRegistry.execute_agent_spotlight_and_trend",
        fail_if_data_tool_runs,
    )
    ai_evidence_cache.clear()
    scoped_orchestrator = PmsAiOrchestrator(
        memory_db,
        {
            "role": "Regional Manager",
            "user_id": "u-egy-regional-manager",
            "accessible_regions": ["EGY"],
            "accessible_teams": ["Inbound"],
        },
    )
    response = scoped_orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="How many Inbound bookings were recorded in Saudi Arabia in September 2026?",
            session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
        )
    )

    assert response.outcome == "restricted_access"
    assert response.tool_calls == []
    assert response.typed_evidence == []


def test_named_employee_target_check_and_diagnosis(memory_db, synth_records, monkeypatch):
    heba_sep = PerformanceRecord(
        id="PreApprovals_EMP401_2026_Sep",
        employee_id="EMP401",
        employee_name="Heba Nabil",
        team="Pre-Approvals IP Offshore",
        month="September",
        year=2026,
        region="EGY",
        position="Pre-Authorization Specialist",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=86.0, grade="B"),
        kpi_values=[
            {
                "kpi_key": "RejectionRate",
                "label": "Controllable Rejection Rate",
                "actual_value": 0.12,
                "target_value": 0.05,
                "achievement_ratio": 0.5,
                "weight_applied": 0.5,
                "unit": "%",
                "direction": "lower_better",
            }
        ],
    )
    _patch_sources(monkeypatch, [*synth_records, heba_sep])
    admin_scope = {"role": "Admin", "user_id": "admin-t2", "has_unrestricted_team_access": True}
    orchestrator = PmsAiOrchestrator(memory_db, admin_scope)

    # 1. Target check ("Did ... meet ... target")
    ai_evidence_cache.clear()
    resp_meet = orchestrator.run_chat_turn(
        AiChatRequest(prompt="Did Nadia Fadel meet the Waiting Time target in September 2026?")
    )
    assert resp_meet.outcome == "answer"
    assert resp_meet.structured_query.employee_id == "EMP501"
    assert "6.2" in resp_meet.headline and "5" in resp_meet.headline
    assert "miss" in resp_meet.headline.casefold() or "exceed" in resp_meet.headline.casefold()

    # 2. Root-cause diagnosis ("Why did Nadia Fadel's Waiting Time miss...")
    ai_evidence_cache.clear()
    resp_why_nadia = orchestrator.run_chat_turn(
        AiChatRequest(prompt="Why did Nadia Fadel's Waiting Time miss the 5 minute target in September 2026?")
    )
    assert any(tc.tool_name == "get_kpi_diagnosis" for tc in resp_why_nadia.tool_calls)
    assert "6.2" in resp_why_nadia.headline and "5" in resp_why_nadia.headline

    # 3. Root-cause diagnosis ("Why did Heba Nabil miss...")
    ai_evidence_cache.clear()
    resp_why_heba = orchestrator.run_chat_turn(
        AiChatRequest(prompt="Why did Heba Nabil miss the 5% controllable rejection rate target in September 2026?")
    )
    assert resp_why_heba.structured_query.employee_id == "EMP401"
    assert any(tc.tool_name == "get_kpi_diagnosis" for tc in resp_why_heba.tool_calls)
    assert any(e.employee_id == "EMP401" and e.kpi_key == "RejectionRate" for e in resp_why_heba.typed_evidence)
    assert "12" in resp_why_heba.headline and "5" in resp_why_heba.headline


def test_ticket_03_unavailable_parity_and_employee_trends(memory_db, synth_records, monkeypatch):
    # Add an extra April/May/June/July/August history for Nadia Fadel? Wait: synth_records already has
    # EMP501 (Nadia Fadel) in August (6.8 min, 88.5%) and September (6.2 min, 91.0%), plus an earlier June record
    # so we can verify filtering to the 2 requested periods (August & September) rather than June!
    nadia_aug = synth_records[0].model_copy(update={"branch": "sharjah", "raw_data": {"Branch": "Sharjah"}})
    nadia_sep = synth_records[1].model_copy(update={"branch": "sharjah", "raw_data": {"Branch": "Sharjah"}})
    nadia_jun = nadia_aug.model_copy(
        update={
            "id": "Inbound_EMP501_2026_Jun",
            "month": "June",
            "evaluation": EvaluationData(score=82.0, grade="C"),
            "kpi_values": [
                {"kpi_key": "waitingtime", "label": "Waiting Time", "actual_value": 7.5, "target_value": 5.0, "unit": "min", "direction": "lower_better"},
                {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 82.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
            ],
        }
    )
    # Pharmacy Nadia Fadel (EMP701) only in September 2026, plus an EGY Finance employee (EMP901)
    pharma_sep = PerformanceRecord(
        id="Pharmacy_EMP702_2026_Sep",
        employee_id="EMP702",
        employee_name="Rami Zaki",
        team="Pharmacy",
        month="September",
        year=2026,
        region="UAE",
        branch="sharjah",
        position="Pharmacist",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=87.5, grade="B"),
        kpi_values=[
            {"kpi_key": "waitingtime", "label": "Waiting Time", "actual_value": 6.2, "target_value": 5.0, "unit": "min", "direction": "lower_better"},
        ],
    )
    fin_sep = PerformanceRecord(
        id="Finance_EMP901_2026_Sep",
        employee_id="EMP901",
        employee_name="Layla Sami",
        team="Finance",
        month="September",
        year=2026,
        region="EGY",
        position="Finance Specialist",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=86.0, grade="B"),
        kpi_values=[
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 86.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )
    # Inbound record with branch="sharjah" only (no Dubai branch-attributed Inbound records)
    inbound_shj_only = PerformanceRecord(
        id="Inbound_EMP102_2026_Sep",
        employee_id="EMP102",
        employee_name="Omar Khalid",
        team="Inbound",
        month="September",
        year=2026,
        region="EGY",
        branch="sharjah",
        raw_data={"Branch": "Sharjah"},
        position="Call Center Agent",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=88.0, grade="B"),
        calls=CallsData(inbound=300, total_handled=340, abandoned=5),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=350, sharjah=150, ajman=0, clinics=0),
            attended=GeoBreakdown(dubai=300, sharjah=130, ajman=0, clinics=0),
        ),
        kpi_values=[
            {"kpi_key": "Booking", "label": "Booking Rate", "actual_value": 26.0, "target_value": 25.0, "unit": "%", "direction": "higher_better"},
        ],
    )
    _patch_sources(monkeypatch, [nadia_jun, nadia_aug, nadia_sep, pharma_sep, fin_sep, inbound_shj_only])
    admin_scope = {"role": "Admin", "user_id": "admin-t3", "has_unrestricted_team_access": True}
    orchestrator = PmsAiOrchestrator(memory_db, admin_scope)
    branch_dir_scope = {
        "role": "Branch Director",
        "user_id": "u-bd-t3",
        "has_unrestricted_team_access": False,
        "accessible_functions": ["Call Center"],
        "accessible_teams": ["Inbound"],
        "accessible_branches": ["dubai"],
    }
    branch_orchestrator = PmsAiOrchestrator(memory_db, branch_dir_scope)

    # 1. Branch-attributed count metric with 0 matching branch records -> unavailable_data, zero evidence, mentions Dubai, never 350
    ai_evidence_cache.clear()
    resp_cnt = branch_orchestrator.run_chat_turn(
        AiChatRequest(prompt="How many Inbound bookings came from Dubai in September 2026?")
    )
    assert resp_cnt.outcome == "unavailable_data"
    assert resp_cnt.typed_evidence == []
    assert resp_cnt.evidence_envelope_v2 == []
    assert "Dubai" in resp_cnt.headline
    assert "350" not in resp_cnt.headline

    # 2. Non-count zero-row response keeps outcome="answer" and includes Dubai
    ai_evidence_cache.clear()
    resp_rate = branch_orchestrator.run_chat_turn(
        AiChatRequest(prompt="What is Inbound Booking Rate in Dubai in September 2026?")
    )
    assert resp_rate.outcome == "answer"
    assert "Dubai" in resp_rate.headline

    # 3. Unpublished period for named employee includes employee_name
    ai_evidence_cache.clear()
    resp_unpub = orchestrator.run_chat_turn(
        AiChatRequest(prompt="What was Rami Zaki's Waiting Time in October 2026?")
    )
    assert resp_unpub.outcome == "unavailable_data"
    assert "Rami Zaki" in resp_unpub.headline

    # 4a. Missing employee-month triggers unavailable_data (no substitution)
    ai_evidence_cache.clear()
    resp_miss_emp = orchestrator.run_chat_turn(
        AiChatRequest(prompt="What was Rami Zaki's Waiting Time in August 2026?")
    )
    assert resp_miss_emp.outcome == "unavailable_data"
    assert resp_miss_emp.typed_evidence == []
    assert "Rami Zaki" in resp_miss_emp.headline

    # 4b. KSA on Finance triggers unavailable_data
    ai_evidence_cache.clear()
    resp_ksa_fin = orchestrator.run_chat_turn(
        AiChatRequest(prompt="What was the overall score for Finance in Saudi Arabia in September 2026?")
    )
    assert resp_ksa_fin.outcome == "unavailable_data"
    assert resp_ksa_fin.typed_evidence == []

    # 5. Multi-period employee change filters to requested periods (August 2026 -> September 2026, not June 82.0%)
    ai_evidence_cache.clear()
    resp_trend = orchestrator.run_chat_turn(
        AiChatRequest(prompt="How did Nadia Fadel's overall score change from August to September 2026?")
    )
    assert resp_trend.outcome == "answer"
    assert resp_trend.structured_query.operation_kind_v2 == "trend"
    assert "August 2026" in resp_trend.headline and "September 2026" in resp_trend.headline
    assert "88.5" in resp_trend.headline and "91" in resp_trend.headline
    assert "82.0" not in resp_trend.headline


def test_ticket_04_metadata_alignment_and_dockerignore(memory_db, synth_records, monkeypatch):
    from pathlib import Path
    from services.ai.tool_registry import DeterministicToolRegistry, ToolExecutionContext

    heba_sep = PerformanceRecord(
        id="PreApprovals_EMP401_2026_Sep",
        employee_id="EMP401",
        employee_name="Heba Nabil",
        team="Pre-Approvals IP Offshore",
        month="September",
        year=2026,
        region="EGY",
        position="Pre-Authorization Specialist",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=86.0, grade="B"),
        kpi_values=[
            {
                "kpi_key": "RejectionRate",
                "label": "Controllable Rejection Rate",
                "actual_value": 0.12,
                "target_value": 0.05,
                "unit": "%",
                "direction": "lower_better",
            }
        ],
    )
    salma_sep = PerformanceRecord(
        id="CodingEGY_EMP501_2026_Sep",
        employee_id="EMP501",
        employee_name="Salma Youssef",
        team="Coding EGY",
        month="September",
        year=2026,
        region="EGY",
        position="RCM -SHJ- OP CODING",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=89.0, grade="B"),
        kpi_values=[
            {
                "kpi_key": "QualityErrors",
                "label": "Quality Errors",
                "actual_value": 1.8,
                "target_value": 3.0,
                "unit": "%",
                "direction": "lower_better",
            }
        ],
    )
    _patch_sources(monkeypatch, [synth_records[0], synth_records[1], heba_sep])
    admin_scope = {"role": "Admin", "user_id": "admin-t4", "has_unrestricted_team_access": True}
    orchestrator = PmsAiOrchestrator(memory_db, admin_scope)

    # 1. Plain KPI lookup keeps intent="actual_vs_target", requested_parts=1, operation_kind_v2="current_value"
    ai_evidence_cache.clear()
    resp_kpi = orchestrator.run_chat_turn(
        AiChatRequest(prompt="What was Nadia Fadel's Booking Rate in September 2026?")
    )
    assert resp_kpi.structured_query.intent == "actual_vs_target"
    assert len(resp_kpi.structured_query.requested_parts) == 1
    assert resp_kpi.structured_query.operation_kind_v2 == "current_value"
    assert resp_kpi.validated_plan_v2.operations[0].kind == "person_summary"

    # 2. Overall-score answer keeps metric=None and attaches model_led_tool_call overall_score provenance
    ai_evidence_cache.clear()
    resp_score = orchestrator.run_chat_turn(
        AiChatRequest(prompt="What was Nadia Fadel's overall score in September 2026?")
    )
    assert resp_score.outcome == "answer"
    assert resp_score.structured_query.metric is None
    assert resp_score.structured_query.model_led_tool_call is not None
    assert resp_score.structured_query.model_led_tool_call["tool_arguments"]["metric_id"] == "overall_score"

    # 3a. Preserves verbatim catalog metric_id prefixes when team matches
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)
    res_rej = registry.execute_agent_spotlight_and_trend(
        team="Pre-Approvals IP Offshore",
        month="September",
        year=2026,
        kpi="pre_approvals_ip_offshore:rejection",
        employee_query="EMP401",
    )
    assert any(e.metric_id == "pre_approvals_ip_offshore:rejection" and e.kpi_key == "RejectionRate" for e in res_rej.typed_evidence)

    _patch_sources(monkeypatch, [salma_sep])
    registry_cod = DeterministicToolRegistry(
        ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    )
    res_cod = registry_cod.execute_agent_spotlight_and_trend(
        team="Coding EGY",
        month="September",
        year=2026,
        kpi="coding_egy:rcm_shj_op_coding:quality_errors_rate",
        employee_query="EMP501",
    )
    assert any(
        e.metric_id == "coding_egy:rcm_shj_op_coding:quality_errors_rate" and e.kpi_key == "QualityErrors"
        for e in res_cod.typed_evidence
    )

    # 3b. Model-led path attaches kpi_key to model_led_tool_call["tool_arguments"]
    _patch_sources(monkeypatch, [heba_sep])
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(
        monkeypatch,
        {
            "response_type": "tool_call",
            "tool_name": "read_employee_metric",
            "tool_arguments": {
                "employee_id": "EMP401",
                "employee_name": "Heba Nabil",
                "team": "Pre-Approvals IP Offshore",
                "metric_id": "pre_approvals_ip_offshore:rejection",
                "period": "2026-09",
            },
        },
    )
    ai_evidence_cache.clear()
    resp_ml = orchestrator.run_chat_turn(
        AiChatRequest(prompt="What was Heba Nabil's controllable rejection rate in September 2026?")
    )
    assert resp_ml.structured_query.model_led_tool_call is not None
    assert resp_ml.structured_query.model_led_tool_call["tool_arguments"].get("kpi_key") == "Rejection"

    # 4. Root .dockerignore restores !**/.env.example right below **/.env.*
    dockerignore_lines = (Path(__file__).resolve().parents[2] / ".dockerignore").read_text(encoding="utf-8").splitlines()
    idx_env = dockerignore_lines.index("**/.env.*")
    assert dockerignore_lines[idx_env + 1] == "!**/.env.example"



