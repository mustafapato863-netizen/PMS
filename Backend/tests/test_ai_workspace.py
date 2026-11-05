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


def test_pr1_provider_controls_header_auth_redaction_and_trace_ownership(monkeypatch):
    import io
    import json
    from pathlib import Path
    import pytest
    from models.models import AuditLog
    from services.ai.config import redact_secrets
    from services.ai.providers import (
        GeminiStructuredRouterAdapter,
        build_minimized_routing_payload,
        is_prompt_safe_for_external_projection,
    )
    from services.ai.trace_logger import TraceOwnershipError

    # 1. Verify English question fixture set integrity and split isolation
    fixture_path = Path(__file__).parent / "fixtures" / "ai_english_questions.json"
    assert fixture_path.exists()
    fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))
    questions = fixture_data["questions"]
    assert len(questions) >= 120
    group_splits: dict[str, set[str]] = {}
    for q in questions:
        group_splits.setdefault(q["paraphrase_group"], set()).add(q["split"])
    # Paraphrase groups must never span multiple splits
    assert all(len(splits) == 1 for splits in group_splits.values())

    # 2. Verify outbound payload minimization and PII/secret redaction
    minimized = build_minimized_routing_payload(
        prompt="Show score for Sara Mahmoud (EMP101) and email sara@example.com with key AIzaSySecretKey123456789012345",
        current_view={"function": "Call Center", "team": "Inbound", "period": "2026-09", "raw_data": {"secret": 1}},
        candidate_teams=["Inbound", "Outbound"],
        candidate_metrics=["inbound:abandon_rate"],
        candidate_branches=["dubai", "sharjah"],
        known_employee_names=["Sara Mahmoud"],
    )
    serialized_min = json.dumps(minimized)
    assert "Sara Mahmoud" not in serialized_min
    assert "EMP101" not in serialized_min
    assert "sara@example.com" not in serialized_min
    assert "AIzaSySecretKey" not in serialized_min
    assert "<EMPLOYEE_NAME>" in minimized["question"]
    assert "<EMPLOYEE_ID>" in minimized["question"]
    assert "raw_data" not in minimized["current_view"]

    assert is_prompt_safe_for_external_projection("col1\tcol2\tcol3\nval1\tval2\tval3") is False
    assert "[REDACTED_API_KEY]" in redact_secrets("https://example.com?key=AIzaSy1234567890123456789012345")

    # 3. Verify server-owned switch blocks cloud calls by default, and uses x-goog-api-key header when enabled
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyTestKey12345678901234567890")
    router_adapter = GeminiStructuredRouterAdapter()
    disabled_res = router_adapter.propose_query_plan(
        prompt="Compare Inbound in July vs August",
        current_view={"function": "Call Center", "team": "Inbound"},
        candidate_teams=["Inbound"],
        candidate_metrics=["inbound:abandon_rate"],
        candidate_branches=["dubai"],
    )
    assert disabled_res.plan is None
    assert disabled_res.metrics.provider_calls == 0
    assert disabled_res.metrics.fallback_outcome == "cloud_disabled"

    # Enable cloud routing and verify x-goog-api-key header, token usage, and timeout fallback
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_PILOT_SCOPES", "call center,inbound,outbound")

    captured_requests = []

    class _FakeHttpResponse:
        def __init__(self, payload: dict):
            self._bytes = json.dumps(payload).encode("utf-8")

        def read(self):
            return self._bytes

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake_urlopen(req, timeout=None):
        captured_requests.append((req, timeout))
        plan_json = {
            "intent": "compare_periods",
            "team": "Inbound",
            "branch": "dubai",
            "metric": "inbound:abandon_rate",
            "performance_level": "Employee",
            "periods": ["2026-07", "2026-08"],
        }
        return _FakeHttpResponse(
            {
                "candidates": [{"content": {"parts": [{"text": json.dumps(plan_json)}]}}],
                "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 40},
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    ok_res = router_adapter.propose_query_plan(
        prompt="Compare Inbound Abandon Rate in Dubai for July vs August 2026",
        current_view={"function": "Call Center", "team": "Inbound"},
        candidate_teams=["Inbound", "Outbound"],
        candidate_metrics=["inbound:abandon_rate"],
        candidate_branches=["dubai", "sharjah"],
    )
    assert ok_res.plan is not None
    assert ok_res.plan.intent == "compare_periods"
    assert ok_res.metrics.provider_calls == 1
    assert ok_res.metrics.input_tokens == 120
    assert ok_res.metrics.output_tokens == 40
    assert ok_res.metrics.estimated_cost_usd > 0
    sent_req, _ = captured_requests[-1]
    assert "key=" not in sent_req.full_url
    header_map = {k.casefold(): v for k, v in sent_req.header_items()}
    assert header_map.get("x-goog-api-key") == "AIzaSyTestKey12345678901234567890"

    # Simulate timeout fallback
    def _timeout_urlopen(req, timeout=None):
        raise TimeoutError("Request timed out")

    monkeypatch.setattr("urllib.request.urlopen", _timeout_urlopen)
    timeout_res = router_adapter.propose_query_plan(
        prompt="Compare Inbound Abandon Rate in Dubai for July vs August 2026",
        current_view={"function": "Call Center", "team": "Inbound"},
        candidate_teams=["Inbound"],
        candidate_metrics=["inbound:abandon_rate"],
        candidate_branches=["dubai"],
    )
    assert timeout_res.plan is None
    assert timeout_res.metrics.fallback_outcome == "timeout"

    # 4. Verify trace ownership, redaction, timing breakdown, and audited export
    db = _build_in_memory_db()
    records = [
        _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 91.0, 45, 50, 90, 200),
    ]
    _patch_records(monkeypatch, records)
    owner_scope = {"role": "General Manager", "user_id": "00000000-0000-0000-0000-000000000011", "has_unrestricted_team_access": True}
    resp = PmsAiOrchestrator(db, owner_scope).run_chat_turn(
        AiChatRequest(
            prompt="Analyze Inbound KPI gaps in September 2026",
            session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            provider_override="deterministic",
        )
    )
    assert resp.timings.total_ms >= 0
    assert resp.provider_usage.provider_calls == 0
    assert resp.answer_detail == "brief"

    trace_logger = TrainingTraceLogger(db)
    # Another user cannot modify feedback on owner's trace
    with pytest.raises(TraceOwnershipError):
        trace_logger.record_feedback(
            trace_id=resp.trace_id,
            rating="up",
            caller_user_id="00000000-0000-0000-0000-000000000099",
            caller_role="Manager",
        )

    # Owner can submit feedback
    found, eligible = trace_logger.record_feedback(
        trace_id=resp.trace_id,
        rating="up",
        caller_user_id="00000000-0000-0000-0000-000000000011",
        caller_role="General Manager",
    )
    assert found is True
    assert eligible is True

    # Export logs an AuditLog entry and anonymizes data
    exported = trace_logger.export_distillation_dataset(
        verified_only=True,
        performed_by_user_id="00000000-0000-0000-0000-000000000011",
        ip_address="127.0.0.1",
        request_id="req-audit-1",
    )
    assert len(exported) == 1
    audit_rows = db.query(AuditLog).filter(AuditLog.table_name == "ai_interaction_traces").all()
    assert len(audit_rows) == 1
    assert audit_rows[0].operation == "EXPORT"

