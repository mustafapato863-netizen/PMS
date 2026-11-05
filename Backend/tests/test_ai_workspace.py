from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.database import Base
from models.ai_schemas import AiChatRequest, SessionFilterContext
from models.schemas import CallsData, EvaluationData, GeoBreakdown, GeoData, PerformanceRecord
from services.ai.domain_policies import (
    disambiguate_call_center_kpi_label,
    extract_prompt_signals,
)
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.trace_logger import TrainingTraceLogger, sanitize_prompt_for_router_training


def _make_call_center_record(
    emp_id: str,
    name: str,
    team: str,
    score: float,
    sharjah_attended: int,
    sharjah_bookings: int,
    dubai_attended: int,
    dubai_bookings: int,
) -> PerformanceRecord:
    total_attended = sharjah_attended + dubai_attended
    total_bookings = sharjah_bookings + dubai_bookings
    attend_rate = (total_attended / total_bookings) if total_bookings > 0 else 0.0
    other_label = "Abandon Rate" if team == "Inbound" else "Reachability"
    return PerformanceRecord(
        id=f"{team}_{emp_id}_2026_09",
        employee_id=emp_id,
        employee_name=name,
        team=team,
        month="September",
        year=2026,
        region="EGY",
        position="Call Center Agent",
        performance_level="Employee",
        status="Below Target" if score < 80 else "On Track",
        evaluation=EvaluationData(score=score, grade="C" if score < 80 else "B"),
        calls=CallsData(inbound=400, total_handled=500, abandoned=15),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=dubai_bookings, sharjah=sharjah_bookings, ajman=20, clinics=10),
            attended=GeoBreakdown(dubai=dubai_attended, sharjah=sharjah_attended, ajman=15, clinics=8),
        ),
        kpi_values=[
            {
                "kpi_key": "Attendance",
                "label": "Attendance Rate",
                "actual_value": attend_rate,
                "target_value": 0.65,
                "weight_applied": 0.70,
                "contribution": min(attend_rate / 0.65, 1.0) * 0.70,
            },
            {
                "kpi_key": "Booking",
                "label": "Booking Rate",
                "actual_value": 0.28,
                "target_value": 0.30,
                "weight_applied": 0.10,
                "contribution": (0.28 / 0.30) * 0.10,
            },
            {
                "kpi_key": "Other",
                "label": other_label,
                "actual_value": 0.06 if team == "Inbound" else 0.85,
                "target_value": 0.05 if team == "Inbound" else 0.90,
                "weight_applied": 0.10,
                "contribution": 0.08,
            },
        ],
    )


def _build_in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _patch_records(monkeypatch, records):
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_records", lambda _self, **_kw: records)
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_analysis_records", lambda _self, **_kw: records)
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_record_index", lambda _self: None)


def test_call_center_kpi_disambiguation_and_signal_extraction():
    assert disambiguate_call_center_kpi_label("Inbound", "Other", "Abandon Rate") == "Abandon Rate (Inbound)"
    assert disambiguate_call_center_kpi_label("Outbound", "Other", "Reachability") == "Reachability (Outbound)"
    assert "Patient Attended / Bookings" in disambiguate_call_center_kpi_label("Inbound", "Attendance", "Attendance Rate")
    assert "Managerial Shift Compliance" in disambiguate_call_center_kpi_label(
        "Inbound", "AttendanceCompliance", "Attendance Compliance"
    )

    state = SessionFilterContext(function="Call Center")
    sig_ar = extract_prompt_signals("مين اكتر تيم واقع في شهر سبتمبر في دبي ومين السبب؟", state)
    assert sig_ar.is_arabic is True
    assert sig_ar.detected_month == "September"
    assert sig_ar.detected_branch == "dubai"
    assert "executive_insights" in sig_ar.primary_intents
    assert "people_contribution" in sig_ar.primary_intents

    sig_rev = extract_prompt_signals("ايه ارقام ايرادات تيم الاوتباوند في سبتمبر؟", state)
    assert sig_rev.asks_revenue_in_call_center is True
    assert sig_rev.detected_team == "Outbound"


def test_orchestrator_arabic_team_and_root_cause_analysis(monkeypatch):
    db = _build_in_memory_db()
    records = [
        _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 91.0, 40, 50, 180, 220),
        _make_call_center_record("EMP201", "Ahmed Tarek", "Outbound", 68.5, 10, 30, 80, 250),
        _make_call_center_record("EMP202", "Mona Adel", "Outbound", 74.0, 15, 35, 100, 240),
    ]
    _patch_records(monkeypatch, records)

    scope = {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True}
    orchestrator = PmsAiOrchestrator(db, scope)

    # 1. Test Zero-Token Watching Workspace
    watching = orchestrator.build_watching_workspace(SessionFilterContext(function="Call Center"))
    assert watching.measured_records == 3
    assert len(watching.alerts) >= 1
    assert len(watching.guardrails) == 4
    assert len(watching.starter_prompts) == 6

    # 2. Test Arabic Multi-Tool Query ("Which team dropped most and who caused it?")
    chat_req = AiChatRequest(
        prompt="مين اكتر تيم واقع في شهر سبتمبر ومين الموظفين السبب؟",
        session_state=SessionFilterContext(function="Call Center", month="September", year=2026),
        provider_override="deterministic",
    )
    resp = orchestrator.run_chat_turn(chat_req)
    assert ("Outbound" in resp.headline) or ("Ahmed Tarek" in resp.headline)
    assert len(resp.visual_cards) >= 2
    assert any(c.card_type == "horizontal_bar" for c in resp.visual_cards)
    assert any(c.card_type == "entity_list" for c in resp.visual_cards)
    assert any(c.card_type == "decision_playbook" and len(c.decisions) >= 1 for c in resp.visual_cards)
    assert any("September 2026" in pill.label for pill in resp.citations)
    assert len(resp.deep_links) >= 1


def test_orchestrator_call_center_revenue_guardrail_and_branch_comparison(monkeypatch):
    db = _build_in_memory_db()
    records = [
        _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 91.0, 45, 50, 90, 200),
        _make_call_center_record("EMP201", "Ahmed Tarek", "Outbound", 72.0, 35, 45, 80, 220),
    ]
    _patch_records(monkeypatch, records)

    scope = {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True}
    orchestrator = PmsAiOrchestrator(db, scope)

    # Revenue question in Call Center triggers guardrail notice + returns Bookings & Attended volumes
    rev_req = AiChatRequest(
        prompt="إيه أرقام إيرادات الكول سنتر في سبتمبر؟",
        session_state=SessionFilterContext(function="Call Center", month="September", year=2026),
        provider_override="deterministic",
    )
    rev_resp = orchestrator.run_chat_turn(rev_req)
    assert len(rev_resp.domain_guardrail_notes) == 1
    assert any(c.card_type == "guardrail_notice" for c in rev_resp.visual_cards)
    assert any("Bookings" in pill.label for pill in rev_resp.citations)

    # Branch comparison (Dubai vs Sharjah) preserves EGY records and projects per branch
    branch_req = AiChatRequest(
        prompt="Compare Dubai vs Sharjah performance for Call Center in September",
        session_state=SessionFilterContext(function="Call Center", month="September", year=2026),
        provider_override="deterministic",
    )
    branch_resp = orchestrator.run_chat_turn(branch_req)
    assert "Sharjah" in branch_resp.headline and "Dubai" in branch_resp.headline


def test_branch_director_bsc_guardrail_and_trace_distillation_lifecycle(monkeypatch):
    db = _build_in_memory_db()
    records = [
        _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 91.0, 45, 50, 90, 200),
    ]
    _patch_records(monkeypatch, records)

    # Branch Director asking for Managerial BSC receives deterministic guardrail card (not a 403 crash)
    bd_scope = {
        "role": "Branch Director",
        "user_id": "bd-1",
        "allowed_branches": ["dubai"],
        "has_unrestricted_team_access": False,
    }
    bd_orchestrator = PmsAiOrchestrator(db, bd_scope)
    bsc_resp = bd_orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="Show Managerial Balanced Scorecard for Inbound",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
            provider_override="deterministic",
        )
    )
    assert any(c.card_type == "guardrail_notice" for c in bsc_resp.visual_cards)

    # Verify PII sanitization and feedback upsert for local model distillation
    assert sanitize_prompt_for_router_training("Show stats for EMP101 and SGHD9988") == (
        "Show stats for <EMPLOYEE_ID> and <EMPLOYEE_ID>"
    )

    admin_scope = {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True}
    normal_resp = PmsAiOrchestrator(db, admin_scope).run_chat_turn(
        AiChatRequest(
            prompt="Analyze Inbound KPI gaps in September 2026",
            session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            provider_override="deterministic",
        )
    )
    logger = TrainingTraceLogger(db)
    found, eligible = logger.record_feedback(trace_id=normal_resp.trace_id, rating="up")
    assert found is True
    assert eligible is True

    exported = logger.export_distillation_dataset(verified_only=True)
    assert len(exported) == 1
    assert exported[0].trace_id == normal_resp.trace_id
    assert exported[0].router_training_pair["schema_version"] == "pms-ai-router-v1"

    # Toggle to down -> no longer eligible for verified distillation export
    found2, eligible2 = logger.record_feedback(trace_id=normal_resp.trace_id, rating="down", reason="Incomplete")
    assert found2 is True
    assert eligible2 is False
    assert len(logger.export_distillation_dataset(verified_only=True)) == 0


def test_focused_agent_and_team_trend_spotlight(monkeypatch):
    db = _build_in_memory_db()
    aug_rec = _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 88.5, 40, 50, 170, 220)
    aug_rec.id = "Inbound_EMP101_2026_08"
    aug_rec.month = "August"
    sep_rec1 = _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 95.4, 45, 50, 195, 220)
    sep_rec2 = _make_call_center_record("EMP102", "Radwa Ahmed", "Inbound", 84.0, 30, 50, 140, 220)
    _patch_records(monkeypatch, [aug_rec, sep_rec1, sep_rec2])

    scope = {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True}
    orchestrator = PmsAiOrchestrator(db, scope)

    # Specific question: "who is better agent in inbound and his trend"
    resp = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="who is better agent in inbound and his trend",
            session_state=SessionFilterContext(function="Call Center"),
            provider_override="deterministic",
        )
    )
    assert "Sara Mahmoud" in resp.headline
    assert "95.4%" in resp.headline
    assert "+6.9% vs August" in resp.headline
    assert resp.narrative_bullets == []
    assert len(resp.visual_cards) == 1
    assert resp.visual_cards[0].card_type == "trend_spotlight"
    assert resp.visual_cards[0].spotlight is not None
    assert resp.visual_cards[0].spotlight.grade == "A"
    assert len(resp.visual_cards[0].spotlight.trend_points) == 2
