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
    month: str = "September",
) -> PerformanceRecord:
    total_attended = sharjah_attended + dubai_attended
    total_bookings = sharjah_bookings + dubai_bookings
    attend_rate = (total_attended / total_bookings) if total_bookings > 0 else 0.0
    other_label = "Abandon Rate" if team == "Inbound" else "Reachability"
    return PerformanceRecord(
        id=f"{team}_{emp_id}_2026_{month[:3]}",
        employee_id=emp_id,
        employee_name=name,
        team=team,
        month=month,
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


def test_pr2_executive_brief_defaults_scope_banner_and_primary_link(monkeypatch):
    """PR 2: Senior roles default to Brief with 1-2 sentence headline, scope banner, and primary source link."""
    db = _build_in_memory_db()
    records = [
        _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 91.0, 45, 50, 90, 200),
        _make_call_center_record("EMP102", "Nour Adel", "Inbound", 64.0, 20, 48, 30, 120),
    ]
    _patch_records(monkeypatch, records)

    exec_scope = {
        "role": "Executive",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "has_unrestricted_team_access": True,
    }
    resp_exec = PmsAiOrchestrator(db, exec_scope).run_chat_turn(
        AiChatRequest(
            prompt="What is Inbound's score in September 2026?",
            session_state=SessionFilterContext(
                function="Call Center",
                team="Inbound",
                month="September",
                year=2026,
            ),
            answer_detail="auto",
        )
    )
    assert resp_exec.answer_detail == "brief"
    assert resp_exec.scope_banner is not None
    assert "Inbound" in resp_exec.scope_banner
    assert "September 2026" in resp_exec.scope_banner
    assert resp_exec.primary_source_link is not None
    assert "/team/inbound" in resp_exec.primary_source_link.route.lower()
    # Headline is 1-2 sentences
    sentences = [s.strip() for s in resp_exec.headline.split(". ") if s.strip()]
    assert 1 <= len(sentences) <= 2

    # When explicit breakdown is requested by a senior role, answer_detail resolves to details
    resp_breakdown = PmsAiOrchestrator(db, exec_scope).run_chat_turn(
        AiChatRequest(
            prompt="Show full breakdown table of Inbound KPIs in September 2026",
            session_state=SessionFilterContext(
                function="Call Center",
                team="Inbound",
                month="September",
                year=2026,
            ),
            answer_detail="auto",
        )
    )
    assert resp_breakdown.answer_detail == "details"


def test_pr3_call_center_catalog_typed_evidence_and_dashboard_parity(monkeypatch):
    """PR 3: Call Center catalog disambiguates Other KPIs, flags tracking-only AHT, and matches dashboard parity."""
    from services.ai.catalog import ai_evidence_cache, get_ai_catalog
    from services.database_record_source import DatabaseRecordSource
    from services.insights_service import InsightsService
    from services.planning_service import PlanningService

    ai_evidence_cache.clear()
    catalog = get_ai_catalog()

    in_other = catalog.find_metric_definition(team="Inbound", kpi_key_or_label="Other")
    out_other = catalog.find_metric_definition(team="Outbound", kpi_key_or_label="Other")
    out_aht = catalog.find_metric_definition(team="Outbound", kpi_key_or_label="AHT")

    assert in_other is not None and in_other.metric_id == "inbound:abandon_rate"
    assert in_other.display_name == "Abandon Rate (Inbound)"
    assert out_other is not None and out_other.metric_id == "outbound:reachability"
    assert out_other.display_name == "Reachability (Outbound)"
    assert out_aht is not None and out_aht.metric_id == "outbound:aht"
    assert out_aht.contributes_to_score is False
    assert out_aht.weight_percent == 0.0
    assert out_aht.tracking_only_note is not None

    db = _build_in_memory_db()
    records = [
        _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 91.0, 45, 50, 90, 200),
        _make_call_center_record("EMP102", "Nour Adel", "Inbound", 64.0, 20, 48, 30, 120),
        _make_call_center_record("EMP201", "Hossam Ali", "Outbound", 88.0, 35, 42, 70, 160),
    ]
    _patch_records(monkeypatch, records)
    gm_scope = {
        "role": "General Manager",
        "user_id": "00000000-0000-0000-0000-000000000002",
        "has_unrestricted_team_access": True,
    }

    # Compare AI typed_evidence directly against InsightsService dashboard KPI diagnosis
    source = DatabaseRecordSource(db)
    ws = InsightsService(source, PlanningService(source, db=db), db=db).generate_workspace(
        gm_scope,
        sections="kpi_diagnosis",
        team="Inbound",
        function="Call Center",
        month="September",
        year=2026,
    )
    dashboard_kpis = {row.key: row for row in (ws.kpi_diagnosis or [])}

    resp = PmsAiOrchestrator(db, gm_scope).run_chat_turn(
        AiChatRequest(
            prompt="Diagnose Inbound KPIs and Abandon Rate in September 2026",
            session_state=SessionFilterContext(
                function="Call Center",
                team="Inbound",
                month="September",
                year=2026,
            ),
        )
    )
    assert len(resp.typed_evidence) >= 2
    ev_by_key = {ev.kpi_key: ev for ev in resp.typed_evidence}
    assert "Other" in ev_by_key
    assert ev_by_key["Other"].metric_id == "inbound:abandon_rate"
    assert ev_by_key["Other"].display_name == "Abandon Rate (Inbound)"
    for kpi_key, ev in ev_by_key.items():
        dash_row = dashboard_kpis[kpi_key]
        expected_ach = min(100.0, round(float(dash_row.achievement_percent or 0.0), 1))
        assert ev.achievement_percent == expected_ach

    # Asking about Outbound AHT surfaces tracking-only evidence with 0% weight note
    resp_track = PmsAiOrchestrator(db, gm_scope).run_chat_turn(
        AiChatRequest(
            prompt="What is Outbound AHT handle time in September 2026?",
            session_state=SessionFilterContext(
                function="Call Center",
                team="Outbound",
                month="September",
                year=2026,
            ),
        )
    )
    track_ev = [ev for ev in resp_track.typed_evidence if ev.metric_id == "outbound:aht"]
    assert len(track_ev) == 1
    assert track_ev[0].contributes_to_score is False
    assert track_ev[0].weight_percent == 0.0
    assert resp_track.basis_warning is not None
    assert "tracking-only" in resp_track.basis_warning.casefold()


def test_pr3_scoped_evidence_cache_invalidation_and_rbac_isolation(monkeypatch):
    """PR 3: Versioned AI cache hits on identical scope, isolates RBAC scopes, and invalidates on data/config/eval changes."""
    from models.models import UploadLog
    from services.ai.catalog import ai_evidence_cache
    from services.cache_invalidation_service import CacheInvalidationService

    ai_evidence_cache.clear()
    db = _build_in_memory_db()
    records = [
        _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 91.0, 45, 50, 90, 200),
        _make_call_center_record("EMP102", "Nour Adel", "Inbound", 64.0, 20, 48, 30, 120),
    ]
    _patch_records(monkeypatch, records)

    gm_scope = {
        "role": "General Manager",
        "user_id": "00000000-0000-0000-0000-000000000002",
        "has_unrestricted_team_access": True,
    }
    req = AiChatRequest(
        prompt="Diagnose Inbound KPIs in September 2026",
        session_state=SessionFilterContext(
            function="Call Center",
            team="Inbound",
            month="September",
            year=2026,
        ),
    )

    cold = PmsAiOrchestrator(db, gm_scope).run_chat_turn(req)
    assert cold.cache_hit is False

    warm = PmsAiOrchestrator(db, gm_scope).run_chat_turn(req)
    assert warm.cache_hit is True

    # Different RBAC scope must NOT hit GM's cache entry
    dubai_scope = {
        "role": "Branch Director",
        "user_id": "00000000-0000-0000-0000-000000000009",
        "has_unrestricted_team_access": True,
        "accessible_branches": ["dubai"],
        "allowed_branches": ["dubai"],
    }
    dubai_turn = PmsAiOrchestrator(db, dubai_scope).run_chat_turn(req)
    assert dubai_turn.cache_hit is False

    # Data version bump invalidates cache
    CacheInvalidationService.bump_data_version()
    after_data_bump = PmsAiOrchestrator(db, gm_scope).run_chat_turn(req)
    assert after_data_bump.cache_hit is False

    # Config version bump invalidates cache
    warm2 = PmsAiOrchestrator(db, gm_scope).run_chat_turn(req)
    assert warm2.cache_hit is True
    CacheInvalidationService.bump_config_version()
    after_cfg_bump = PmsAiOrchestrator(db, gm_scope).run_chat_turn(req)
    assert after_cfg_bump.cache_hit is False

    # UploadLog mutation changes evaluation_cache_identity(db) and invalidates cache
    import uuid
    warm3 = PmsAiOrchestrator(db, gm_scope).run_chat_turn(req)
    assert warm3.cache_hit is True
    db.add(
        UploadLog(
            id=uuid.uuid4(),
            team_id=uuid.uuid4(),
            month="September",
            year=2026,
            status="success",
            record_count=35,
        )
    )
    db.commit()
    after_upload = PmsAiOrchestrator(db, gm_scope).run_chat_turn(req)
    assert after_upload.cache_hit is False


def test_pr4_local_first_routing_followups_clarifications_and_restricted_branch(monkeypatch):
    """PR 4: Local-first routing, follow-up inheritance, ambiguity clarification, restricted branch refusal, and unavailable periods."""
    import json
    from pathlib import Path
    from models.ai_schemas import ConfirmedQueryContext
    from services.ai.router import HybridQueryRouter

    db = _build_in_memory_db()
    records = [
        _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 91.0, 45, 50, 90, 200, month="September"),
        _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 87.0, 40, 46, 85, 190, month="August"),
        _make_call_center_record("EMP201", "Mona Hassan", "Outbound", 82.0, 34, 60, 72, 160, month="August"),
    ]
    _patch_records(monkeypatch, records)

    gm_scope = {
        "role": "General Manager",
        "user_id": "00000000-0000-0000-0000-000000000002",
        "has_unrestricted_team_access": True,
    }
    orch = PmsAiOrchestrator(db, gm_scope)

    # 1. Turn 1: Explicit question establishes ConfirmedQueryContext
    t1 = orch.run_chat_turn(
        AiChatRequest(
            prompt="What is Inbound Booking Conversion Rate in September 2026?",
            session_state=SessionFilterContext(function="Call Center"),
        )
    )
    assert t1.outcome == "answer"
    assert t1.structured_query is not None
    assert t1.structured_query.team == "Inbound"
    assert t1.structured_query.metric == "inbound:booking_rate"
    assert t1.structured_query.periods == ["2026-09"]
    assert t1.resolved_session_state.last_confirmed_query is not None

    # 2. Turn 2: Follow-up "And August?" inherits team, metric, and intent
    t2 = orch.run_chat_turn(
        AiChatRequest(
            prompt="And August?",
            session_state=SessionFilterContext(
                function="Call Center",
                last_confirmed_query=t1.resolved_session_state.last_confirmed_query,
            ),
        )
    )
    assert t2.outcome == "answer"
    assert t2.structured_query is not None
    assert t2.structured_query.team == "Inbound"
    assert t2.structured_query.metric == "inbound:booking_rate"
    assert t2.structured_query.periods == ["2026-08"]
    assert "team" in t2.inherited_filters
    assert "metric" in t2.inherited_filters

    # 3. Ambiguous Attendance prompt without team/level triggers clarification with 0 DB tool reads
    t_clar = orch.run_chat_turn(
        AiChatRequest(
            prompt="What is the Attendance score in September 2026?",
            session_state=SessionFilterContext(function="Call Center"),
        )
    )
    assert t_clar.outcome == "clarification"
    assert t_clar.clarification is not None
    assert t_clar.clarification.code == "AMBIGUOUS_ATTENDANCE_DEFINITION"
    assert len(t_clar.clarification.choices) >= 2
    assert t_clar.tool_calls == []
    assert t_clar.timings.database_ms == 0.0

    # 4. Restricted branch refusal: Dubai-only user asking about Sharjah gets restricted_access (NEVER Dubai data)
    dubai_only_scope = {
        "role": "Branch Director",
        "user_id": "00000000-0000-0000-0000-000000000009",
        "has_unrestricted_team_access": True,
        "accessible_branches": ["dubai"],
        "allowed_branches": ["dubai"],
    }
    t_restr = PmsAiOrchestrator(db, dubai_only_scope).run_chat_turn(
        AiChatRequest(
            prompt="What is Inbound score in Sharjah in September 2026?",
            session_state=SessionFilterContext(function="Call Center", branch="dubai"),
        )
    )
    assert t_restr.outcome == "restricted_access"
    assert "sharjah" in t_restr.headline.casefold()
    assert t_restr.tool_calls == []
    assert t_restr.typed_evidence == []

    # 5. Unavailable future period returns unavailable_data with 0 tool calls
    t_unavail = orch.run_chat_turn(
        AiChatRequest(
            prompt="What is the Inbound team score in December 2026?",
            session_state=SessionFilterContext(function="Call Center"),
        )
    )
    assert t_unavail.outcome == "unavailable_data"
    assert "2026-12" in t_unavail.headline
    assert t_unavail.tool_calls == []

    # 6. Unsupported write/mutation returns unsupported_request
    t_unsup = orch.run_chat_turn(
        AiChatRequest(
            prompt="Delete all September 2026 Inbound evaluation records and recalculate scores.",
            session_state=SessionFilterContext(function="Call Center"),
        )
    )
    assert t_unsup.outcome == "unsupported_request"
    assert t_unsup.tool_calls == []

    # 7. Verify >= 95% (actual 100%) exact outcome, intent, and filter match on all 126 English fixtures
    fixture_path = Path(__file__).parent / "fixtures" / "ai_english_questions.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    questions = data["questions"]
    matched = 0
    for q in questions:
        q_scope = dict(q.get("caller_scope") or {"role": q.get("caller_role", "General Manager")})
        if q.get("caller_branches") is not None:
            q_scope["accessible_branches"] = q["caller_branches"]
            q_scope["allowed_branches"] = q["caller_branches"]
        if q.get("caller_functions") is not None:
            q_scope["accessible_functions"] = q["caller_functions"]
        if not q.get("caller_branches") and not q.get("caller_functions"):
            q_scope.setdefault("has_unrestricted_team_access", True)
        ss_dict = dict(q.get("session_state") or {})
        if q.get("prior_confirmed_query"):
            ss_dict["last_confirmed_query"] = ConfirmedQueryContext(**q["prior_confirmed_query"])
        ss = SessionFilterContext(**ss_dict)
        res = HybridQueryRouter(scope=q_scope).resolve_and_validate(prompt=q["prompt"], session_state=ss)
        exp_f = q.get("expected_filters") or {}
        if (
            res.outcome == q["expected_outcome"]
            and res.plan.intent == q["expected_intent"]
            and all(getattr(res.plan, k) == v for k, v in exp_f.items())
        ):
            matched += 1
    assert matched == len(questions)


def test_pr5_multi_scope_certification_and_200_employee_latency_gate(monkeypatch):
    """PR 5 & PR 7: Multi-scope certification (RCM/Pre-Approvals June 2026 revision, Marketing positions, Pharmacy, BSC) and 200-emp latency gate."""
    from scripts.certify_scopes_and_benchmark import run_200_employee_benchmark
    from services.ai.catalog import get_ai_catalog

    cat = get_ai_catalog()
    registry = cat.get_scope_certification_registry()
    assert len(registry) == 17
    assert all(r["certified"] is True for r in registry)

    # 1. Verify Offshore Pre-Approvals June 2026 controllable vs policy rejection definitions
    offshore_rej = cat.find_metric_definition(
        team="Pre-Approvals IP Offshore",
        kpi_key_or_label="Rejection",
    )
    assert offshore_rej is not None
    assert offshore_rej.contributes_to_score is True
    assert offshore_rej.weight_percent == 50.0
    assert offshore_rej.effective_from == "2026-06"

    offshore_pol = cat.find_metric_definition(
        team="Pre-Approvals IP Offshore",
        kpi_key_or_label="PolicyRejection",
    )
    assert offshore_pol is not None
    assert offshore_pol.contributes_to_score is False
    assert offshore_pol.weight_percent == 0.0

    # 2. Verify Marketing position-specific metrics
    mb_cpl = cat.find_metric_definition(
        team="Marketing",
        position="Media Buyer",
        kpi_key_or_label="CPL",
    )
    assert mb_cpl is not None
    assert mb_cpl.position == "Media Buyer"
    assert mb_cpl.contributes_to_score is True

    # 3. Verify Pharmacy scored Waiting Time (20%) vs 0-weight diagnostic AJM Pharmacy Manager IV Cost Saving
    ph_wait = cat.find_metric_definition(
        team="Pharmacy",
        kpi_key_or_label="WaitingTime",
    )
    assert ph_wait is not None
    assert ph_wait.contributes_to_score is True
    assert ph_wait.weight_percent == 20.0

    ph_iv = cat.find_metric_definition(
        team="Pharmacy",
        position="AJM Pharmacy Manager",
        kpi_key_or_label="IV Cost Saving",
    )
    assert ph_iv is not None
    assert ph_iv.contributes_to_score is False
    assert ph_iv.weight_percent == 0.0

    # 4. Run end-to-end turn on Offshore Pre-Approvals Policy Rejection and verify basis_warning
    db = _build_in_memory_db()
    records = [
        _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 91.0, 45, 50, 90, 200),
    ]
    _patch_records(monkeypatch, records)
    gm_scope = {
        "role": "General Manager",
        "user_id": "00000000-0000-0000-0000-000000000002",
        "has_unrestricted_team_access": True,
    }
    off_resp = PmsAiOrchestrator(db, gm_scope).run_chat_turn(
        AiChatRequest(
            prompt="What is Policy Rejection Rate in Pre-Approvals IP Offshore in September 2026?",
            session_state=SessionFilterContext(function="RCM", team="Pre-Approvals IP Offshore"),
        )
    )
    assert off_resp.outcome == "answer"
    assert off_resp.basis_warning is not None
    assert "2026-06" in off_resp.basis_warning or "policy rejection" in off_resp.basis_warning.casefold()
    pol_ev = [e for e in off_resp.typed_evidence if "policy_rejection" in e.metric_id]
    assert len(pol_ev) == 1
    assert pol_ev[0].contributes_to_score is False

    # 5. Verify 200-employee-per-team concurrency & latency benchmark gates
    bench = run_200_employee_benchmark()
    assert bench["employees_per_team"] == 200
    assert bench["categories"]["routine_local"]["cold_p95_ms"] < 1000.0
    assert bench["categories"]["routine_local"]["warm_p95_ms"] < 1000.0
    assert bench["categories"]["single_kpi"]["cold_p95_ms"] < 3000.0
    assert bench["categories"]["single_kpi"]["warm_p95_ms"] < 3000.0
    assert bench["categories"]["standard_comparison"]["cold_p95_ms"] < 5000.0
    assert bench["categories"]["standard_comparison"]["warm_p95_ms"] < 5000.0





