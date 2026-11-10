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


def test_greeting_returns_a_short_reply_without_running_analytics(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("A greeting must not run the analytics router")

    monkeypatch.setattr(
        "services.ai.orchestrator.HybridQueryRouter.resolve_and_validate",
        fail_if_called,
    )
    with _build_in_memory_db() as db:
        response = PmsAiOrchestrator(db, {"role": "Admin"}).run_chat_turn(
            AiChatRequest(prompt="Hi!")
        )

    assert response.headline.startswith("Hi!")
    assert response.answer_detail == "brief"
    assert not response.tool_calls
    assert not response.visual_cards


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

    assert logger.export_distillation_dataset(verified_only=True) == []
    logger.review_trace(trace_id=normal_resp.trace_id, reviewer_verified=True, reviewer_id="admin-1", caller_role="Admin")
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

    # Export logs an AuditLog entry and anonymizes data (requires reviewer_verified=True when verified_only=True)
    trace_logger.review_trace(trace_id=resp.trace_id, reviewer_verified=True, reviewer_id="00000000-0000-0000-0000-000000000011", caller_role="Admin")
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
    assert len(registry) == 18
    assert all(r["enabled"] is True for r in registry)
    assert {r["team"] for r in registry if r["certified"] is True} == set()

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


def test_pr6_classifier_evaluation_and_promotion_gate_decision():
    """PR 6: Evaluate local intent classifier on paraphrase-grouped splits and verify promotion gate decision."""
    from scripts.evaluate_ai_classifier import run_classifier_evaluation

    report = run_classifier_evaluation()
    assert report["paraphrase_split_zero_leakage"] is True
    assert report["splits"]["test"]["hybrid_router_exact_match_pct"] == 100.0
    assert report["gates"]["accepted_local_exact_match_measured_pct"] >= 99.0
    assert report["gates"]["overall_test_exact_match_measured_pct"] >= 95.0
    assert report["gates"]["passes_cost_gate"] is False
    assert report["promotion_decision"] == "DO_NOT_PROMOTE_KEEP_HYBRID_RULES"
    assert report["runtime_dependency_added"] is False


def test_goldfish_review_enhancements_and_security_hardening(monkeypatch):
    """Goldfish Swarm Review: verify cross-branch comparison RBAC, multi-team RBAC, clarification context preservation, single-KPI headline synthesis, PII phone redaction, and catalog config version invalidation."""
    from models.ai_schemas import ConfirmedQueryContext
    from services.ai.catalog import ai_evidence_cache, get_ai_catalog
    from services.ai.router import HybridQueryRouter
    from services.ai.trace_logger import sanitize_prompt_for_router_training
    from services.cache_invalidation_service import CacheInvalidationService

    db = _build_in_memory_db()
    records = [
        _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 91.0, 45, 50, 90, 200),
        _make_call_center_record("EMP201", "Lina Tariq", "Outbound", 88.0, 50, 75, 110, 260),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()

    # 1. Single-branch director asking to compare Dubai and Sharjah or all UAE branches gets restricted_access
    dubai_director_scope = {
        "role": "Branch Director",
        "user_id": "00000000-0000-0000-0000-000000000091",
        "has_unrestricted_team_access": True,
        "accessible_branches": ["dubai"],
    }
    orch_dubai = PmsAiOrchestrator(db, dubai_director_scope)
    res_cmp_sharjah = orch_dubai.run_chat_turn(
        AiChatRequest(
            prompt="Compare Dubai and Sharjah Inbound Attendance Rate in September 2026.",
            session_state=SessionFilterContext(function="Call Center", branch="dubai"),
        )
    )
    assert res_cmp_sharjah.outcome == "restricted_access"
    assert "sharjah" in res_cmp_sharjah.headline.casefold()
    assert res_cmp_sharjah.tool_calls == []

    res_cmp_all = orch_dubai.run_chat_turn(
        AiChatRequest(
            prompt="Compare all UAE branches for Inbound in September 2026.",
            session_state=SessionFilterContext(function="Call Center", branch="dubai"),
        )
    )
    assert res_cmp_all.outcome == "restricted_access"
    assert res_cmp_all.tool_calls == []

    # 2. Function-scoped Call Center user asking to compare Coding and Submission gets restricted_access
    cc_viewer_scope = {
        "role": "Function Viewer",
        "user_id": "00000000-0000-0000-0000-000000000092",
        "has_unrestricted_team_access": False,
        "accessible_functions": ["Call Center"],
        "accessible_teams": ["Inbound", "Outbound"],
    }
    res_rcm = HybridQueryRouter(scope=cc_viewer_scope).resolve_and_validate(
        prompt="Compare Coding and Submission scores in September 2026.",
        session_state=SessionFilterContext(function="Call Center"),
    )
    assert res_rcm.outcome == "restricted_access"

    # 3. Clarification preserves prior ConfirmedQueryContext and filters choices by caller RBAC
    prior_ctx = ConfirmedQueryContext(
        intent="actual_vs_target",
        team="Inbound",
        function="Call Center",
        branch="dubai",
        performance_level="Employee",
        metric_id="inbound:attendance_rate",
        period="2026-09",
    )
    clar_dubai = HybridQueryRouter(scope=dubai_director_scope).resolve_and_validate(
        prompt="Show the Attendance score in September 2026.",
        session_state=SessionFilterContext(function="Call Center", last_confirmed_query=prior_ctx),
    )
    assert clar_dubai.outcome == "clarification"
    assert clar_dubai.confirmed_context.team == "Inbound"
    assert clar_dubai.confirmed_context.branch == "dubai"
    assert clar_dubai.confirmed_context.metric_id == "inbound:attendance_rate"
    assert clar_dubai.clarification is not None
    # Branch Director must NOT be offered Managerial BSC in clarification choices
    choice_ids = [c.id for c in clar_dubai.clarification.choices]
    assert "inbound_managerial_attendance" not in choice_ids

    # 4. Single-KPI query leads headline with the requested KPI (both scored and tracking-only)
    gm_scope = {
        "role": "General Manager",
        "user_id": "00000000-0000-0000-0000-000000000002",
        "has_unrestricted_team_access": True,
    }
    orch_gm = PmsAiOrchestrator(db, gm_scope)
    t_aht = orch_gm.run_chat_turn(
        AiChatRequest(
            prompt="What is the Outbound AHT in September 2026?",
            session_state=SessionFilterContext(function="Call Center", team="Outbound"),
        )
    )
    assert t_aht.outcome == "answer"
    assert "average handle time" in t_aht.headline.casefold() or "aht" in t_aht.headline.casefold()
    assert "0%" in t_aht.headline or "tracking" in t_aht.headline.casefold()

    # 5. Phone number redaction in router training prompt sanitizer
    sanitized = sanitize_prompt_for_router_training("Call agent Sara at +971 50 123 4567 or emp101@sgh.ae")
    assert "<PHONE>" in sanitized
    assert "<EMAIL>" in sanitized
    assert "123 4567" not in sanitized

    # 6. Catalog cache invalidation on config version bump
    cat1 = get_ai_catalog()
    CacheInvalidationService.bump_config_version()
    cat2 = get_ai_catalog()
    assert cat1 is not cat2


def test_conversation_and_hierarchy_acceptance_criteria(monkeypatch):
    """Verify Monthly Presentation Call Center hierarchy (Support Positions + position drill-down),
    greeting turn, multi-part booking trend + top performer with explicit ranking metric,
    ambiguous ranking clarification, open-ended Gemini routing when team is known, and dynamic latest month."""
    from models.ai_schemas import StructuredQueryPlan
    from services.ai.catalog import ai_evidence_cache
    from services.ai.providers import ProviderCallMetrics, StructuredRoutingProviderResult

    db = _build_in_memory_db()
    aug_in = _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 88.0, 40, 50, 170, 220)
    aug_in.id = "Inbound_EMP101_2026_08"
    aug_in.month = "August"
    sep_in1 = _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 93.0, 48, 50, 195, 220)
    sep_in2 = _make_call_center_record("EMP102", "Radwa Ahmed", "Inbound", 84.0, 30, 50, 140, 220)

    # Support position record stored in DB as team="Call Center" with position="Workforce analyst"
    sup_rec = _make_call_center_record("EMP301", "Nour Hassan", "Call Center", 91.5, 0, 0, 0, 0)
    sup_rec.position = "Workforce analyst"
    sup_rec.kpi_values = [
        {
            "kpi_key": "ForecastAccuracy",
            "label": "Forecast Accuracy",
            "actual_value": 0.92,
            "target_value": 0.90,
            "achievement_ratio": 1.0,
            "weight_applied": 0.40,
            "unit": "%",
            "direction": "higher_better",
        },
        {
            "kpi_key": "ScheduleAdherence",
            "label": "Schedule Adherence",
            "actual_value": 0.94,
            "target_value": 0.95,
            "achievement_ratio": 0.989,
            "weight_applied": 0.30,
            "unit": "%",
            "direction": "higher_better",
        },
    ]

    records = [aug_in, sep_in1, sep_in2, sup_rec]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()

    gm_scope = {
        "role": "General Manager",
        "user_id": "00000000-0000-0000-0000-000000000002",
        "has_unrestricted_team_access": True,
    }
    orch = PmsAiOrchestrator(db, gm_scope)

    # 1. Greeting turn: short English sentence, zero performance reads
    greet_res = orch.run_chat_turn(
        AiChatRequest(
            prompt="Hi!",
            session_state=SessionFilterContext(function="Call Center"),
        )
    )
    assert greet_res.outcome == "answer"
    assert greet_res.answer_detail == "brief"
    assert greet_res.headline == "Hi! What would you like to know about performance?"
    assert greet_res.tool_calls == []
    assert greet_res.visual_cards == []

    # 2. Support Positions group & individual position drill-down (Workforce analyst)
    sup_res = orch.run_chat_turn(
        AiChatRequest(
            prompt="How is Workforce analyst performing in Support Positions in September 2026?",
            session_state=SessionFilterContext(function="Call Center"),
        )
    )
    assert sup_res.outcome == "answer"
    assert sup_res.structured_query is not None
    assert sup_res.structured_query.function == "Call Center"
    assert sup_res.structured_query.team == "Support Positions"
    assert sup_res.structured_query.position == "Workforce analyst"
    assert "Support Positions (Workforce analyst)" in (sup_res.scope_banner or "")
    assert sup_res.primary_source_link is not None
    assert "position=Workforce+analyst" in sup_res.primary_source_link.route

    # 3. Multi-part booking trend + top performer yields compact trend AND one person with explicit ranking metric, period, scope, source
    multi_res = orch.run_chat_turn(
        AiChatRequest(
            prompt="Show Inbound booking trend and top performer in September 2026.",
            session_state=SessionFilterContext(function="Call Center"),
        )
    )
    assert multi_res.outcome == "answer"
    assert multi_res.structured_query is not None
    assert multi_res.structured_query.requested_parts == ["trend", "ranking"]
    assert "Booking Rate" in multi_res.headline
    assert "Sara Mahmoud" in multi_res.headline
    assert "September 2026" in multi_res.headline
    assert any("Ranking metric: Booking Rate" in b and "/employee/EMP101" in b for b in multi_res.narrative_bullets)
    assert len(multi_res.suggested_followups) >= 1

    # 4. Ambiguous ranking metric triggers focused clarification (AMBIGUOUS_KPI_SCOPE)
    ambig_rank = orch.run_chat_turn(
        AiChatRequest(
            prompt="Who is the top performer in Inbound by conversion?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert ambig_rank.outcome == "clarification"
    assert ambig_rank.structured_query is not None
    assert ambig_rank.structured_query.clarification_code == "AMBIGUOUS_KPI_SCOPE"
    assert ambig_rank.tool_calls == []

    # 5. Gemini interprets open-ended requests even when team is known and metric/action is unclear,
    #    after authorization and payload checks pass
    monkeypatch.setenv("PMS_AI_ROUTER_MODE", "hybrid")
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret-gemini-key-999")

    gemini_calls: list[str] = []

    def _mock_gemini_propose(self, **kwargs):
        gemini_calls.append(kwargs.get("prompt", ""))
        return StructuredRoutingProviderResult(
            plan=StructuredQueryPlan(
                intent="score_drivers",
                requested_parts=["score_drivers"],
                team="Inbound",
                function="Call Center",
                performance_level="Employee",
                periods=["2026-09"],
                clarification_code="NONE",
            ),
            metrics=ProviderCallMetrics(
                provider_used="gemini",
                model_used="gemini-2.5-flash",
                provider_calls=1,
                provider_ms=12.5,
                input_tokens=80,
                output_tokens=30,
                estimated_cost_usd=0.000021,
                fallback_outcome="none",
            ),
        )

    monkeypatch.setattr(
        "services.ai.router.GeminiStructuredRouterAdapter.propose_query_plan",
        _mock_gemini_propose,
    )

    open_res = orch.run_chat_turn(
        AiChatRequest(
            prompt="Where should I focus in Inbound this month?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert len(gemini_calls) == 1
    assert open_res.outcome == "answer"
    assert open_res.provider_usage is not None
    assert open_res.provider_usage.route_used == "gemini_router"
    assert open_res.provider_usage.provider_calls == 1

    # Unauthorized branch request is blocked BEFORE calling Gemini
    dubai_only_scope = {
        "role": "Branch Director",
        "user_id": "00000000-0000-0000-0000-000000000095",
        "has_unrestricted_team_access": True,
        "accessible_branches": ["dubai"],
    }
    gemini_calls.clear()
    blocked_res = PmsAiOrchestrator(db, dubai_only_scope).run_chat_turn(
        AiChatRequest(
            prompt="Where should I focus in Inbound for Sharjah this month?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound", branch="dubai"),
        )
    )
    assert blocked_res.outcome == "restricted_access"
    assert len(gemini_calls) == 0

    # 6. Dynamic latest published month advances from September 2026 to October 2026 upon new upload
    monkeypatch.setenv("PMS_AI_ROUTER_MODE", "rules")
    oct_in = _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 96.0, 49, 50, 205, 220)
    oct_in.id = "Inbound_EMP101_2026_10"
    oct_in.month = "October"
    oct_in.year = 2026
    _patch_records(monkeypatch, [aug_in, sep_in1, sep_in2, sup_rec, oct_in])
    ai_evidence_cache.clear()

    oct_res = orch.run_chat_turn(
        AiChatRequest(
            prompt="What is the Inbound score in October 2026?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert oct_res.outcome == "answer"
    assert oct_res.resolved_session_state.month == "October"
    assert oct_res.resolved_session_state.year == 2026


def test_v2_blueprint_conversational_analytics_and_owned_sessions(monkeypatch):
    """Covers all 9 required v2 blueprint behaviors plus owned conversation sessions, optimistic concurrency, and idempotency."""
    import pytest
    from services.ai.catalog import ai_evidence_cache
    from services.ai.conversation_service import (
        AiConversationService,
        ConversationAccessError,
        ConversationVersionConflictError,
    )

    db = _build_in_memory_db()
    monkeypatch.setenv("PMS_AI_ROUTER_MODE", "rules")

    # Build multi-month records for Adham (March-September 2026, best in August at 96.5%),
    # two Mariams in Inbound (Mariam Ali earliest July, Mariam Hassan earliest August),
    # and Support Positions records with a tie for lowest.
    records = []
    adham_scores = [
        ("March", 82.0),
        ("April", 85.0),
        ("May", 87.5),
        ("June", 90.0),
        ("July", 91.0),
        ("August", 96.5),
        ("September", 91.0),
    ]
    for m_name, sc in adham_scores:
        rec = _make_call_center_record("EMP501", "Adham Tarek", "Inbound", sc, 45, 60, 120, 150, month=m_name)
        rec.geo.bookings.ajman = 85
        rec.geo.attended.ajman = 65
        records.append(rec)

    # Mariam 1 (earliest July 2026) and Mariam 2 (earliest August 2026)
    for m_name in ("July", "August", "September"):
        records.append(
            _make_call_center_record("EMP601", "Mariam Ali", "Inbound", 88.0, 30, 50, 80, 100, month=m_name)
        )
    for m_name in ("August", "September"):
        records.append(
            _make_call_center_record("EMP602", "Mariam Hassan", "Inbound", 84.0, 25, 45, 70, 95, month=m_name)
        )

    # Support Positions stored under team="Call Center" with specific position
    sup_low_1 = _make_call_center_record("EMP701", "Kareem Adel", "Call Center", 62.0, 0, 0, 0, 0, month="September")
    sup_low_1.position = "Quality Assurance"
    sup_low_2 = _make_call_center_record("EMP702", "Ziad Nabil", "Call Center", 62.0, 0, 0, 0, 0, month="September")
    sup_low_2.position = "Trainer"
    sup_high = _make_call_center_record("EMP703", "Nour Hassan", "Call Center", 93.0, 0, 0, 0, 0, month="September")
    sup_high.position = "Workforce analyst"
    records.extend([sup_low_1, sup_low_2, sup_high])

    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()

    scope = {
        "role": "General Manager",
        "user_id": "00000000-0000-0000-0000-000000000077",
        "has_unrestricted_team_access": True,
    }
    orch = PmsAiOrchestrator(db, scope)
    conv_svc = AiConversationService(db)
    created_conv = conv_svc.create_conversation(
        scope=scope,
        initial_state=SessionFilterContext(function="Call Center", team="Inbound"),
    )
    conv_id = created_conv.conversation_id
    assert created_conv.context_version == 1

    # 1. "Hi" -> short welcome, zero tool/provider calls, increments conversation version
    r_hi = orch.run_chat_turn(
        AiChatRequest(
            prompt="Hi",
            conversation_id=conv_id,
            context_version=1,
            client_request_id="req-hi-1",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert r_hi.headline.startswith("Hi!")
    assert r_hi.tool_calls == []
    assert r_hi.suggested_followups == []
    assert r_hi.validated_plan_v2 is not None and r_hi.validated_plan_v2.turn_kind == "social"
    assert r_hi.context_version == 2

    # Idempotent replay with same client_request_id returns identical response without incrementing version
    r_hi_replay = orch.run_chat_turn(
        AiChatRequest(
            prompt="Hi",
            conversation_id=conv_id,
            context_version=1,
            client_request_id="req-hi-1",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert r_hi_replay.turn_id == r_hi.turn_id

    # Stale context_version raises ConversationVersionConflictError
    with pytest.raises(ConversationVersionConflictError):
        orch.run_chat_turn(
            AiChatRequest(
                prompt="Hi again",
                conversation_id=conv_id,
                context_version=1,
                client_request_id="req-stale",
            )
        )

    # Cross-user access is denied
    with pytest.raises(ConversationAccessError):
        conv_svc.get_context(
            conversation_id=conv_id,
            scope={"role": "Manager", "user_id": "00000000-0000-0000-0000-000000000099"},
        )

    # 2. "Is Mariam a new joiner in Inbound?" -> Disambiguates the two Mariams first (AMBIGUOUS_PERSON),
    # then after selecting Mariam Hassan via clarification_choice_id, states earliest record month (August 2026)
    # without fabricating an HR join date (MISSING_HR_JOIN_DATE).
    r_mariam_ambig = orch.run_chat_turn(
        AiChatRequest(
            prompt="Is Mariam a new joiner in Inbound?",
            conversation_id=conv_id,
            context_version=2,
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert r_mariam_ambig.outcome == "clarification"
    assert r_mariam_ambig.clarification is not None
    assert r_mariam_ambig.clarification.code == "AMBIGUOUS_PERSON"
    assert "two Mariams in Inbound" in r_mariam_ambig.headline
    choice_mariam_2 = next(c for c in r_mariam_ambig.clarification.choices if c.employee_id == "EMP602")

    r_mariam_resolved = orch.run_chat_turn(
        AiChatRequest(
            prompt="Mariam Hassan",
            conversation_id=conv_id,
            context_version=r_mariam_ambig.context_version,
            clarification_choice_id=choice_mariam_2.id,
            session_state=r_mariam_ambig.resolved_session_state,
        )
    )
    assert r_mariam_resolved.outcome == "clarification"
    assert r_mariam_resolved.clarification is not None
    assert r_mariam_resolved.clarification.code == "MISSING_HR_JOIN_DATE"
    assert "Mariam Hassan's first available Inbound record is August 2026" in r_mariam_resolved.headline
    assert "no verified joining date" in r_mariam_resolved.headline

    # 3. "Who is lowest in Support and what is his position?" -> Support Positions, person, position, score, month, and tie
    r_support = orch.run_chat_turn(
        AiChatRequest(
            prompt="Who is lowest in Support and what is his position?",
            session_state=SessionFilterContext(function="Call Center"),
        )
    )
    assert r_support.outcome == "answer"
    assert r_support.structured_query is not None
    assert r_support.structured_query.team == "Support Positions"
    assert ("Kareem Adel" in r_support.headline or "Ziad Nabil" in r_support.headline)
    assert ("Quality Assurance" in r_support.headline or "Trainer" in r_support.headline)
    assert "62.0%" in r_support.headline
    assert "September 2026" in r_support.headline
    assert "tied with" in r_support.headline

    # 4. "Was September Adham's best month?" -> Compares March–September 2026 (all 7 months), identifies August 2026 at 96.5%
    r_adham_sep = orch.run_chat_turn(
        AiChatRequest(
            prompt="Was September Adham's best month?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert r_adham_sep.outcome == "answer"
    assert r_adham_sep.headline.startswith("No.")
    assert "Adham Tarek" in r_adham_sep.headline
    assert "91.0% in September 2026" in r_adham_sep.headline
    assert "March–September 2026" in r_adham_sep.headline
    assert "August 2026 at 96.5%" in r_adham_sep.headline

    # 7. "What about August?" -> Retains Adham and best-month check, confirms August 2026 was Adham's best month
    r_adham_aug = orch.run_chat_turn(
        AiChatRequest(
            prompt="What about August?",
            session_state=r_adham_sep.resolved_session_state,
        )
    )
    assert r_adham_aug.outcome == "answer"
    assert r_adham_aug.headline.startswith("Yes.")
    assert "August 2026 was Adham Tarek's" in r_adham_aug.headline
    assert "96.5%" in r_adham_aug.headline

    # 5. "Which has more bookings: Dubai, Ajman or Sharjah?" -> Ranks all 3 branches by booking count
    r_3branch = orch.run_chat_turn(
        AiChatRequest(
            prompt="Which has more bookings: Dubai, Ajman or Sharjah?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
        )
    )
    assert r_3branch.outcome == "answer"
    assert r_3branch.structured_query is not None
    assert r_3branch.structured_query.branches == ["dubai", "ajman", "sharjah"]
    assert "Dubai led September 2026 Inbound bookings with 345" in r_3branch.headline
    assert "Sharjah with 155" in r_3branch.headline
    assert "Ajman with 125" in r_3branch.headline

    # 6 & 8. "Show booking trend and who is best" -> followed by "No, I mean the lowest"
    r_trend_best = orch.run_chat_turn(
        AiChatRequest(
            prompt="Show booking trend and who is best in Inbound",
            session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
        )
    )
    assert r_trend_best.outcome == "answer"
    assert "Booking Rate" in r_trend_best.headline
    assert "#1 top performer" in r_trend_best.headline

    r_correction = orch.run_chat_turn(
        AiChatRequest(
            prompt="No, I mean the lowest",
            session_state=r_trend_best.resolved_session_state,
        )
    )
    assert r_correction.outcome == "answer"
    assert r_correction.structured_query is not None
    assert r_correction.structured_query.ranking_direction == "worst"
    assert "lowest-scoring" in r_correction.headline
    assert "Mariam Hassan" in r_correction.headline

    # 9. "Thanks" -> Short acknowledgement without analytics
    r_thanks = orch.run_chat_turn(
        AiChatRequest(
            prompt="Thanks!",
            session_state=r_correction.resolved_session_state,
        )
    )
    assert r_thanks.outcome == "answer"
    assert "welcome" in r_thanks.headline.lower()
    assert r_thanks.tool_calls == []
    assert r_thanks.suggested_followups == []
    assert r_thanks.validated_plan_v2 is not None and r_thanks.validated_plan_v2.turn_kind == "social"










def test_v2_multi_role_scenarios_and_phonetic_disambiguation(monkeypatch):
    """Tests multi-role RBAC enforcement, phonetic name disambiguation (Mariam/Maryam), and Gemini model failover."""
    import json
    import urllib.error
    import pytest
    from services.ai.catalog import ai_evidence_cache
    from services.ai.conversation_service import (
        AiConversationService,
        ConversationAccessError,
    )
    from services.ai.providers import GeminiStructuredRouterAdapter
    from services.ai.trace_logger import TrainingTraceLogger

    db = _build_in_memory_db()
    monkeypatch.setenv("PMS_AI_ROUTER_MODE", "rules")

    # Build multi-team, multi-month records:
    # - 3 Mariams/Maryams in Inbound:
    #   * SGHD70148: Mariam Tarek Hassan Mohamed (January 2026)
    #   * SGHD70231: Mariam Mohssen Mahmoud (August & September 2026)
    #   * SGHD70250: Maryam Elsayed Mahmoud Eid (September 2026)
    # - 1 Mariam in CSR (outside Inbound Manager's scope):
    #   * SGHA01306: Mariam Reda Rakha (August 2026)
    # - Support Positions & Outbound & Coding records
    records = [
        _make_call_center_record("SGHD70148", "Mariam Tarek Hassan Mohamed", "Inbound", 85.3, 40, 55, 110, 140, month="January"),
        _make_call_center_record("SGHD70231", "Mariam Mohssen Mahmoud", "Inbound", 93.7, 45, 60, 120, 150, month="August"),
        _make_call_center_record("SGHD70231", "Mariam Mohssen Mahmoud", "Inbound", 94.4, 48, 62, 130, 160, month="September"),
        _make_call_center_record("SGHD70250", "Maryam Elsayed Mahmoud Eid", "Inbound", 83.9, 35, 50, 95, 130, month="September"),
        _make_call_center_record("SGHA01306", "Mariam Reda Rakha", "CSR", 66.7, 0, 0, 0, 0, month="August"),
        _make_call_center_record("OUT201", "Omar Khaled", "Outbound", 89.5, 30, 40, 90, 110, month="September"),
        _make_call_center_record("COD301", "Heba Mostafa", "Coding", 92.1, 0, 0, 0, 0, month="September"),
    ]
    for r in records:
        if r.team == "Inbound":
            r.geo.bookings.ajman = 75
            r.geo.attended.ajman = 55

    sup_qa = _make_call_center_record("SUP401", "Kareem Adel", "Call Center", 64.0, 0, 0, 0, 0, month="September")
    sup_qa.position = "Quality Assurance"
    records.append(sup_qa)

    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()

    # -------------------------------------------------------------------------
    # Role 1: Team-Scoped Inbound Manager (only Inbound in Call Center)
    # -------------------------------------------------------------------------
    inbound_manager_scope = {
        "role": "Manager",
        "user_id": "mgr-inbound-01",
        "has_unrestricted_team_access": False,
        "accessible_functions": ["Call Center"],
        "accessible_teams": ["Inbound"],
    }
    inbound_orch = PmsAiOrchestrator(db, inbound_manager_scope)

    # Scenario 1A: Statement-order "mariam is new joiner in inbound team ?"
    # Matches all 3 Inbound Mariam/Maryam records (excluding CSR Mariam Reda Rakha)
    r_mariam_3 = inbound_orch.run_chat_turn(
        AiChatRequest(
            prompt="mariam is new joiner in inbound team ?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert r_mariam_3.outcome == "clarification"
    assert r_mariam_3.clarification is not None
    assert r_mariam_3.clarification.code == "AMBIGUOUS_PERSON"
    assert "three Mariams in Inbound" in r_mariam_3.headline
    choice_ids = {c.employee_id for c in r_mariam_3.clarification.choices}
    assert choice_ids == {"SGHD70148", "SGHD70231", "SGHD70250"}
    assert "SGHA01306" not in choice_ids  # CSR Mariam excluded by Inbound scope

    # Resolving Maryam Elsayed Mahmoud Eid (SGHD70250) reports September 2026 earliest record + no HR join date
    maryam_choice = next(c for c in r_mariam_3.clarification.choices if c.employee_id == "SGHD70250")
    r_maryam_sel = inbound_orch.run_chat_turn(
        AiChatRequest(
            prompt="Maryam Elsayed",
            clarification_choice_id=maryam_choice.id,
            session_state=r_mariam_3.resolved_session_state,
        )
    )
    assert r_maryam_sel.outcome == "clarification"
    assert r_maryam_sel.clarification is not None
    assert r_maryam_sel.clarification.code == "MISSING_HR_JOIN_DATE"
    assert "Maryam Elsayed Mahmoud Eid's first available Inbound record is September 2026" in r_maryam_sel.headline
    assert "no verified joining date" in r_maryam_sel.headline

    # Direct partial 2-word or full 4-word name query also resolves uniquely to SGHD70250
    for direct_prompt in (
        "Is Maryam Elsayed a new joiner in Inbound?",
        "Is Maryam Elsayed Mahmoud Eid a new joiner in Inbound?",
    ):
        r_direct_maryam = inbound_orch.run_chat_turn(
            AiChatRequest(
                prompt=direct_prompt,
                session_state=SessionFilterContext(function="Call Center", team="Inbound"),
            )
        )
        assert r_direct_maryam.outcome == "clarification"
        assert r_direct_maryam.clarification is not None
        assert r_direct_maryam.clarification.code == "MISSING_HR_JOIN_DATE"
        assert "Maryam Elsayed Mahmoud Eid's first available Inbound record is September 2026" in r_direct_maryam.headline

    # Scenario 1B: Inbound Manager blocked from Support Positions & Outbound
    r_mgr_sup_blocked = inbound_orch.run_chat_turn(
        AiChatRequest(
            prompt="Who is lowest in Support and what is his position?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert r_mgr_sup_blocked.outcome == "restricted_access"
    assert "Support Positions" in r_mgr_sup_blocked.headline

    r_mgr_out_blocked = inbound_orch.run_chat_turn(
        AiChatRequest(
            prompt="What is Outbound Reachability in September 2026?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert r_mgr_out_blocked.outcome == "restricted_access"
    assert "Outbound" in r_mgr_out_blocked.headline

    # -------------------------------------------------------------------------
    # Role 2: Dubai-Only Branch Director (Employee-level only, Dubai branch only)
    # -------------------------------------------------------------------------
    dubai_director_scope = {
        "role": "Branch Director",
        "user_id": "dir-dubai-01",
        "has_unrestricted_team_access": True,
        "accessible_branches": ["dubai"],
    }
    dubai_orch = PmsAiOrchestrator(db, dubai_director_scope)

    # Scenario 2A: 3-branch booking count query is blocked because Ajman and Sharjah are outside Dubai scope
    r_bd_3branch = dubai_orch.run_chat_turn(
        AiChatRequest(
            prompt="Which has more bookings: Dubai, Ajman or Sharjah?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound", branch="dubai"),
        )
    )
    assert r_bd_3branch.outcome == "restricted_access"
    assert "Access restricted" in r_bd_3branch.headline

    # Scenario 2B: Authorized Dubai-only query succeeds
    r_bd_dubai_ok = dubai_orch.run_chat_turn(
        AiChatRequest(
            prompt="What is Inbound Booking Rate in Dubai in September 2026?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound", branch="dubai"),
        )
    )
    assert r_bd_dubai_ok.outcome == "answer"
    assert "Dubai" in r_bd_dubai_ok.scope_banner

    # Scenario 2C: Ambiguous Attendance clarification omits Managerial option for Branch Director
    r_bd_att = dubai_orch.run_chat_turn(
        AiChatRequest(
            prompt="What is Attendance in Call Center?",
            session_state=SessionFilterContext(function="Call Center", branch="dubai"),
        )
    )
    assert r_bd_att.outcome == "clarification"
    assert r_bd_att.clarification is not None
    assert all(c.performance_level != "Managerial" for c in r_bd_att.clarification.choices)

    # -------------------------------------------------------------------------
    # Role 3: RCM Function Director (scoped to RCM teams only)
    # -------------------------------------------------------------------------
    rcm_director_scope = {
        "role": "Function Director",
        "user_id": "dir-rcm-01",
        "has_unrestricted_team_access": False,
        "accessible_functions": ["RCM"],
        "accessible_teams": ["Coding", "Submission", "Re-Submission"],
    }
    rcm_orch = PmsAiOrchestrator(db, rcm_director_scope)

    # Scenario 3A: Blocked from Call Center Inbound
    r_rcm_inb_blocked = rcm_orch.run_chat_turn(
        AiChatRequest(
            prompt="What is Inbound Abandon Rate in September 2026?",
            session_state=SessionFilterContext(function="RCM", team="Coding"),
        )
    )
    assert r_rcm_inb_blocked.outcome == "restricted_access"
    assert "Inbound" in r_rcm_inb_blocked.headline

    # Scenario 3B: Authorized Coding query succeeds
    r_rcm_coding_ok = rcm_orch.run_chat_turn(
        AiChatRequest(
            prompt="What is Coding score in September 2026?",
            session_state=SessionFilterContext(function="RCM", team="Coding"),
        )
    )
    assert r_rcm_coding_ok.outcome == "answer"
    assert "Coding" in r_rcm_coding_ok.headline

    # -------------------------------------------------------------------------
    # Role 4 & 5: Function Viewer vs Admin Conversation Isolation & Trace Verification
    # -------------------------------------------------------------------------
    viewer_scope = {
        "role": "Function Viewer",
        "user_id": "viewer-cc-01",
        "has_unrestricted_team_access": False,
        "accessible_functions": ["Call Center"],
        "accessible_teams": ["Inbound", "Outbound"],
    }
    conv_svc = AiConversationService(db)
    mgr_conv = conv_svc.create_conversation(
        scope=inbound_manager_scope,
        initial_state=SessionFilterContext(function="Call Center", team="Inbound"),
    )
    # Function Viewer cannot read or delete Inbound Manager's conversation
    with pytest.raises(ConversationAccessError):
        conv_svc.get_context(conversation_id=mgr_conv.conversation_id, scope=viewer_scope)
    with pytest.raises(ConversationAccessError):
        conv_svc.delete_conversation(mgr_conv.conversation_id, scope=viewer_scope)

    # Function Viewer cannot self-certify traces as reviewer_verified
    viewer_turn = PmsAiOrchestrator(db, viewer_scope).run_chat_turn(
        AiChatRequest(
            prompt="What is Inbound Booking Rate in September 2026?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    trace_logger = TrainingTraceLogger(db)
    found_fb, elig_fb = trace_logger.record_feedback(
        trace_id=viewer_turn.trace_id,
        rating="up",
        reason="Accurate",
        caller_user_id="viewer-cc-01",
        caller_role="Function Viewer",
        reviewer_verified=True,
    )
    assert found_fb is True
    assert elig_fb is True
    assert trace_logger.export_distillation_dataset(verified_only=True) == []  # Non-admin cannot self-verify
    assert trace_logger.export_distillation_dataset(verified_only=False)[0].reviewer_verified is False
    with pytest.raises(PermissionError):
        trace_logger.review_trace(
            trace_id=viewer_turn.trace_id,
            reviewer_verified=True,
            reviewer_id="viewer-cc-01",
            caller_role="Function Viewer",
        )

    # Admin can verify the trace and mark reviewer_verified=True
    found_adm, elig_adm, _ = trace_logger.review_trace(
        trace_id=viewer_turn.trace_id,
        reviewer_verified=True,
        reviewer_id="admin-root-01",
        caller_role="Admin",
        notes="Verified by Admin",
    )
    assert found_adm is True
    assert elig_adm is True
    assert trace_logger.export_distillation_dataset(verified_only=True)[0].reviewer_verified is True
    # Feedback changes invalidate the existing review, even if the owner later
    # changes a negative rating back to positive.
    trace_logger.record_feedback(trace_id=viewer_turn.trace_id, rating="down", caller_user_id="viewer-cc-01", caller_role="Function Viewer")
    trace_logger.record_feedback(trace_id=viewer_turn.trace_id, rating="up", caller_user_id="viewer-cc-01", caller_role="Function Viewer")
    assert trace_logger.export_distillation_dataset(verified_only=True) == []

    # -------------------------------------------------------------------------
    # Scenario 6: Gemini Multi-Model Fallback Chain (503 on primary -> 200 on secondary)
    # -------------------------------------------------------------------------
    monkeypatch.setenv("PMS_AI_GEMINI_ROUTING_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyTestFallbackKey123456789012345")
    monkeypatch.setenv("PMS_GEMINI_MODEL", "gemini-3.5-flash-lite,gemini-2.5-flash")
    attempted_urls: list[str] = []

    class _FallbackHttpResponse:
        def __init__(self, payload: dict):
            self._bytes = json.dumps(payload).encode("utf-8")

        def read(self):
            return self._bytes

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fallback_urlopen(req, timeout=None):
        attempted_urls.append(req.full_url)
        if "gemini-3.5-flash-lite" in req.full_url:
            raise urllib.error.HTTPError(
                req.full_url, 503, "Service Unavailable", hdrs=None, fp=None
            )
        plan_json = {
            "intent": "score_drivers",
            "team": "Inbound",
            "performance_level": "Employee",
            "ranking_direction": "NONE",
            "clarification_code": "NONE",
        }
        return _FallbackHttpResponse(
            {
                "candidates": [{"content": {"parts": [{"text": json.dumps(plan_json)}]}}],
                "usageMetadata": {"promptTokenCount": 95, "candidatesTokenCount": 32},
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", _fallback_urlopen)
    fb_res = GeminiStructuredRouterAdapter().propose_query_plan(
        prompt="Where should I focus in Inbound this month?",
        current_view={"function": "Call Center", "team": "Inbound"},
        candidate_teams=["Inbound"],
        candidate_metrics=["inbound:abandon_rate"],
        candidate_branches=["dubai"],
    )
    assert fb_res.plan is not None
    assert fb_res.plan.intent == "score_drivers"
    assert fb_res.plan.ranking_direction == "best"  # Normalized from "NONE"
    assert fb_res.metrics.model_used == "gemini-2.5-flash"
    assert fb_res.metrics.provider_calls == 2
    assert len(attempted_urls) == 2


def test_v2_review_findings_all_nine_fixes(monkeypatch):
    """Comprehensive verification of all 9 v2 review findings:
    1. Auto-created server-owned conversation when conversation_id is None + controlled 404 ConversationDeletedError.
    2. Optimistic concurrency + expired worker claim_token protection at turn completion.
    3. Safe retries under permission/data/account changes + request_fingerprint conflict detection.
    4. Best vs worst month distinction, unrounded precision, >100 scores, ties, None score handling, and pronoun inheritance.
    6. Employee full/partial name redaction in traces/turns/exports + strict verified_only export boundary.
    7. Separation of enabled allowlist vs 6-gate certified scopes.
    9. Production runtime DDL prohibition + disposable PostgreSQL schema upgrade/downgrade verification.
    """
    from datetime import datetime, timedelta, timezone
    import pytest
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from models.ai_schemas import ConfirmedQueryContext
    from models.models import AiInteractionTrace, AiTurn, Base
    from repositories.ai_conversation_repository import (
        AiConversationRepository,
        ConversationDeletedError,
        ConversationMigrationUnavailableError,
        ConversationStaleContextError,
        RequestIdReuseConflictError,
    )
    from services.ai.catalog import ai_evidence_cache, get_ai_catalog
    from services.ai.conversation_service import AiConversationService
    from services.ai.trace_logger import TrainingTraceLogger, sanitize_prompt_for_router_training
    from services.cache_invalidation_service import CacheInvalidationService
    from services.insights_service import InsightAccessError

    db = _build_in_memory_db()
    monkeypatch.setenv("PMS_AI_ROUTER_MODE", "rules")

    # Build precision multi-month records for Adham Precision (EMP888)
    adham_months = [
        ("March", 82.50),
        ("April", 61.20),
        ("May", 61.20),
        ("June", None),      # Missing score -> must NEVER become 0.0%
        ("July", 94.24),     # Unrounded best (94.24 vs 94.18 both round to 94.2)
        ("August", 94.18),
        ("September", 91.00),
    ]
    records = []
    for m_name, sc in adham_months:
        rec = _make_call_center_record(
            "EMP888",
            "Adham Precision",
            "Inbound",
            sc if sc is not None else 0.0,
            45,
            60,
            120,
            150,
            month=m_name,
        )
        if sc is None:
            object.__setattr__(rec.evaluation, "score", None)
        else:
            rec.evaluation.score = sc
        records.append(rec)

    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()

    gm_scope = {
        "role": "General Manager",
        "user_id": "00000000-0000-0000-0000-000000000888",
        "has_unrestricted_team_access": True,
        "accessible_branches": ["dubai", "sharjah", "ajman", "clinics"],
    }
    orch = PmsAiOrchestrator(db, gm_scope)
    conv_svc = AiConversationService(db, gm_scope)

    # -------------------------------------------------------------------------
    # Fix 1: Server-owned conversation auto-created when conversation_id is None
    #        + controlled ConversationDeletedError on late request to deleted conversation
    # -------------------------------------------------------------------------
    t1 = orch.run_chat_turn(
        AiChatRequest(
            prompt="Hi",
            conversation_id=None,
            client_request_id="req-auto-conv-1",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert t1.conversation_id is not None
    assert t1.context_version == 2
    persisted_ctx = conv_svc.get_context(conversation_id=t1.conversation_id, scope=gm_scope)
    assert persisted_ctx.context_version == 2

    # Soft-delete the conversation and verify a late request raises ConversationDeletedError (not IntegrityError)
    assert conv_svc.delete_conversation(t1.conversation_id, scope=gm_scope) is True
    with pytest.raises(ConversationDeletedError):
        orch.run_chat_turn(
            AiChatRequest(
                prompt="Follow up after delete",
                conversation_id=t1.conversation_id,
                context_version=2,
                client_request_id="req-after-delete",
            )
        )

    # -------------------------------------------------------------------------
    # Fix 2: Optimistic concurrency at completion + expired worker claim_token protection
    # -------------------------------------------------------------------------
    race_conv = conv_svc.create_conversation(
        scope=gm_scope,
        initial_state=SessionFilterContext(function="Call Center", team="Inbound"),
    )
    race_conv_id = race_conv.conversation_id
    assert race_conv.context_version == 1

    # Two concurrent turns both start at expected_context_version=1
    turn_a, replay_a = conv_svc.claim_or_replay_turn(
        conversation_id=race_conv_id,
        scope=gm_scope,
        prompt="What is Inbound score?",
        client_request_id="req-race-a",
        expected_context_version=1,
    )
    turn_b, replay_b = conv_svc.claim_or_replay_turn(
        conversation_id=race_conv_id,
        scope=gm_scope,
        prompt="What is Outbound score?",
        client_request_id="req-race-b",
        expected_context_version=1,
    )
    assert replay_a is None and replay_b is None

    # Worker A finishes first and advances context_version to 2
    ver_after_a = conv_svc.complete_turn(
        conversation_id=race_conv_id,
        turn_id=str(turn_a.id),
        expected_context_version=1,
        claim_token=str(turn_a.claim_token),
        scope=gm_scope,
        outcome="answer",
        turn_kind="analytics",
        route_used="local_rules",
        validated_plan={"intent": "current_value"},
        evidence_envelope=[],
        response_payload={"headline": "Worker A answer"},
        session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        confirmed_context=ConfirmedQueryContext(intent="current_value", team="Inbound"),
        provider_calls=0,
        total_ms=10.0,
    )
    assert ver_after_a == 2

    # Worker B tries to complete against stale expected_context_version=1 -> rejected!
    with pytest.raises(ConversationStaleContextError):
        conv_svc.complete_turn(
            conversation_id=race_conv_id,
            turn_id=str(turn_b.id),
            expected_context_version=1,
            claim_token=str(turn_b.claim_token),
            scope=gm_scope,
            outcome="answer",
            turn_kind="analytics",
            route_used="local_rules",
            validated_plan={"intent": "current_value"},
            evidence_envelope=[],
            response_payload={"headline": "Worker B stale overwrite"},
            session_state=SessionFilterContext(function="Call Center", team="Outbound"),
            confirmed_context=ConfirmedQueryContext(intent="current_value", team="Outbound"),
            provider_calls=0,
            total_ms=12.0,
        )
    assert conv_svc.get_context(conversation_id=race_conv_id, scope=gm_scope).confirmed_context.team == "Inbound"

    # Expired worker A vs reclaiming worker B on the same turn
    exp_turn_w1, _ = conv_svc.claim_or_replay_turn(
        conversation_id=race_conv_id,
        scope=gm_scope,
        prompt="Slow query",
        client_request_id="req-expire-reclaim",
        expected_context_version=2,
    )
    old_token = str(exp_turn_w1.claim_token)
    # Force deadline expiration
    db.query(AiTurn).filter(AiTurn.id == exp_turn_w1.id).update(
        {"processing_deadline": datetime.now(timezone.utc) - timedelta(seconds=30)}
    )
    db.commit()

    # Worker 2 reclaims the expired turn and gets a new claim_token
    exp_turn_w2, _ = conv_svc.claim_or_replay_turn(
        conversation_id=race_conv_id,
        scope=gm_scope,
        prompt="Slow query",
        client_request_id="req-expire-reclaim",
        expected_context_version=2,
    )
    new_token = str(exp_turn_w2.claim_token)
    assert new_token != old_token

    # Old Worker 1 wakes up and tries to complete using old_token -> rejected!
    with pytest.raises(ConversationStaleContextError):
        conv_svc.complete_turn(
            conversation_id=race_conv_id,
            turn_id=str(exp_turn_w1.id),
            expected_context_version=2,
            claim_token=old_token,
            scope=gm_scope,
            outcome="answer",
            turn_kind="analytics",
            route_used="local_rules",
            validated_plan={"intent": "current_value"},
            evidence_envelope=[],
            response_payload={"headline": "Old worker answer"},
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
            confirmed_context=ConfirmedQueryContext(intent="current_value", team="Inbound"),
            provider_calls=0,
            total_ms=50.0,
        )

    # Worker 2 completes cleanly with new_token -> advances context_version to 3
    ver_after_w2 = conv_svc.complete_turn(
        conversation_id=race_conv_id,
        turn_id=str(exp_turn_w2.id),
        expected_context_version=2,
        claim_token=new_token,
        scope=gm_scope,
        outcome="answer",
        turn_kind="analytics",
        route_used="local_rules",
        validated_plan={"intent": "current_value"},
        evidence_envelope=[],
        response_payload={"headline": "Worker 2 authoritative answer"},
        session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        confirmed_context=ConfirmedQueryContext(intent="current_value", team="Inbound"),
        provider_calls=0,
        total_ms=15.0,
    )
    assert ver_after_w2 == 3

    # -------------------------------------------------------------------------
    # Fix 3: Safe retries under permission, account, and data changes + request_fingerprint
    # -------------------------------------------------------------------------
    retry_scope = {
        "role": "Branch Director",
        "user_id": "00000000-0000-0000-0000-000000000889",
        "has_unrestricted_team_access": True,
        "accessible_branches": ["dubai", "sharjah"],
        "is_active": True,
    }
    retry_orch = PmsAiOrchestrator(db, retry_scope)
    r_sharjah_1 = retry_orch.run_chat_turn(
        AiChatRequest(
            prompt="What is Inbound Booking Rate in Sharjah in September 2026?",
            client_request_id="req-sharjah-retry",
            session_state=SessionFilterContext(function="Call Center", team="Inbound", branch="sharjah"),
        )
    )
    assert r_sharjah_1.outcome == "answer"
    retry_conv_id = r_sharjah_1.conversation_id

    # Reusing the same client_request_id with a different prompt raises RequestIdReuseConflictError
    with pytest.raises(RequestIdReuseConflictError):
        retry_orch.run_chat_turn(
            AiChatRequest(
                prompt="What is Outbound Reachability in Dubai?",
                conversation_id=retry_conv_id,
                client_request_id="req-sharjah-retry",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", branch="sharjah"),
            )
        )

    # Deactivating the user account blocks replay with InsightAccessError
    inactive_scope = {**retry_scope, "is_active": False}
    with pytest.raises(InsightAccessError):
        PmsAiOrchestrator(db, inactive_scope).run_chat_turn(
            AiChatRequest(
                prompt="What is Inbound Booking Rate in Sharjah in September 2026?",
                conversation_id=retry_conv_id,
                client_request_id="req-sharjah-retry",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", branch="sharjah"),
            )
        )

    # Revoking Sharjah branch access invalidates the cached turn replay and returns restricted_access
    revoked_sharjah_scope = {
        **retry_scope,
        "accessible_branches": ["dubai"],
    }
    r_sharjah_revoked = PmsAiOrchestrator(db, revoked_sharjah_scope).run_chat_turn(
        AiChatRequest(
            prompt="What is Inbound Booking Rate in Sharjah in September 2026?",
            conversation_id=retry_conv_id,
            client_request_id="req-sharjah-retry",
            session_state=SessionFilterContext(function="Call Center", team="Inbound", branch="sharjah"),
        )
    )
    assert r_sharjah_revoked.outcome == "restricted_access"

    # Changing published evaluation data (eval_id bump) invalidates cached replay and recomputes
    r_eval_initial = orch.run_chat_turn(
        AiChatRequest(
            prompt="What is Inbound score in September 2026?",
            client_request_id="req-inbound-eval-change",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert r_eval_initial.outcome == "answer"
    assert "91.0%" in r_eval_initial.headline
    eval_conv_id = r_eval_initial.conversation_id

    # Update September score to 97.5% and bump data version
    for r in records:
        if r.month == "September":
            r.evaluation.score = 97.5
    CacheInvalidationService.bump_data_version()
    ai_evidence_cache.clear()

    r_eval_recomputed = orch.run_chat_turn(
        AiChatRequest(
            prompt="What is Inbound score in September 2026?",
            conversation_id=eval_conv_id,
            client_request_id="req-inbound-eval-change",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert r_eval_recomputed.outcome == "answer"
    assert "97.5%" in r_eval_recomputed.headline

    # Restore September score to 91.0% for subsequent assertions
    for r in records:
        if r.month == "September":
            r.evaluation.score = 91.0
    CacheInvalidationService.bump_data_version()
    ai_evidence_cache.clear()

    # -------------------------------------------------------------------------
    # Fix 4: Best vs worst month, unrounded precision, ties, None scores, >100 scores, pronoun follow-ups
    # -------------------------------------------------------------------------
    # 4a. Unrounded close scores: July (94.24) beats August (94.18) even though both round to 94.2 at 1dp
    r_best_aug = orch.run_chat_turn(
        AiChatRequest(
            prompt="Was August Adham's best month?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert r_best_aug.outcome == "answer"
    assert r_best_aug.headline.startswith("No.")
    assert "July 2026 at 94.24%" in r_best_aug.headline
    assert "94.18% in August 2026" in r_best_aug.headline
    # Missing June score is noted as having no evaluated score, never treated as 0.0%
    assert any("June 2026 had no evaluated score" in b for b in r_best_aug.narrative_bullets)

    # 4b. Pronoun follow-up switching to worst/lowest month ("Which month had his lowest score?")
    r_worst_pronoun = orch.run_chat_turn(
        AiChatRequest(
            prompt="Which month had his lowest score?",
            conversation_id=r_best_aug.conversation_id,
            context_version=r_best_aug.context_version,
            session_state=r_best_aug.resolved_session_state,
        )
    )
    assert r_worst_pronoun.outcome == "answer"
    assert r_worst_pronoun.validated_plan_v2 is not None
    assert r_worst_pronoun.validated_plan_v2.operations[0].kind == "person_worst_period"
    assert "April 2026 and May 2026" in r_worst_pronoun.headline
    assert "61.2%" in r_worst_pronoun.headline
    assert "was April 2026 and May 2026 (tied) at 61.2%" in r_worst_pronoun.headline
    assert "June 2026 had no evaluated score and was excluded" in r_worst_pronoun.headline

    # 4c. Follow-up "What about April?" retains worst-month check
    r_worst_april = orch.run_chat_turn(
        AiChatRequest(
            prompt="What about April?",
            conversation_id=r_worst_pronoun.conversation_id,
            context_version=r_worst_pronoun.context_version,
            session_state=r_worst_pronoun.resolved_session_state,
        )
    )
    assert r_worst_april.outcome == "answer"
    assert r_worst_april.headline.startswith("Yes.")
    assert "April 2026" in r_worst_april.headline
    assert "tied with May 2026" in r_worst_april.headline
    assert "worst month" in r_worst_april.headline

    # 4d. Scores > 100 are not capped at 100 before ranking
    oct_over = _make_call_center_record("EMP888", "Adham Precision", "Inbound", 101.2, 50, 60, 140, 150, month="October")
    nov_over = _make_call_center_record("EMP888", "Adham Precision", "Inbound", 104.5, 55, 60, 145, 150, month="November")
    _patch_records(monkeypatch, [*records, oct_over, nov_over])
    CacheInvalidationService.bump_data_version()
    ai_evidence_cache.clear()

    r_over_100 = orch.run_chat_turn(
        AiChatRequest(
            prompt="Was October Adham's best month?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert r_over_100.outcome == "answer"
    assert r_over_100.headline.startswith("No.")
    assert "November 2026 at 104.5%" in r_over_100.headline

    # -------------------------------------------------------------------------
    # Fix 6: Privacy & employee name redaction in prompts, traces, and exports
    # -------------------------------------------------------------------------
    redacted_prompt = sanitize_prompt_for_router_training(
        "Was October Adham Precision or Adham's best month?",
        db=db,
    )
    assert "Adham" not in redacted_prompt
    assert "<EMPLOYEE_NAME>" in redacted_prompt

    # Check that stored AiTurn and AiInteractionTrace rows redacted "Adham"
    turn_rows = db.query(AiTurn).all()
    assert len(turn_rows) > 0
    for tr in turn_rows:
        assert "adham" not in (tr.user_prompt_redacted or "").casefold()

    # Insert a legacy trace with unredacted employee name and verify export_distillation_dataset re-sanitizes it
    import json
    import uuid

    legacy_trace_id = uuid.uuid4()
    legacy_trace = AiInteractionTrace(
        id=legacy_trace_id,
        user_id=gm_scope["user_id"],
        role="General Manager",
        prompt="How did Adham Precision perform in July 2026?",
        sanitized_prompt="How did Adham Precision perform in July 2026?",
        session_state={"function": "Call Center", "team": "Inbound"},
        tool_calls=[],
        tool_digest={"employee": "Adham Precision"},
        structured_response={"headline": "Adham Precision scored 94.24% in July 2026.", "narrative_bullets": ["Adham led July."]},
        provider_name="deterministic-local",
        model_name="pms-deterministic-v1",
        latency_ms=10,
        non_empty_evidence=True,
        guardrail_triggered=False,
        feedback_rating="up",
        is_distillation_eligible=True,
        reviewer_verified=True,
        reviewer_id="admin-1",
    )
    db.add(legacy_trace)
    db.commit()

    exported_verified = TrainingTraceLogger(db).export_distillation_dataset(verified_only=True)
    legacy_exported = next(x for x in exported_verified if x.trace_id == str(legacy_trace_id))
    assert "Adham" not in legacy_exported.router_training_pair["sanitized_prompt"]
    assert "<EMPLOYEE_NAME>" in legacy_exported.router_training_pair["sanitized_prompt"]
    assert legacy_exported.narrative_training_pair is not None
    assert "Adham" not in legacy_exported.narrative_training_pair["headline"]
    assert "Adham" not in json.dumps(legacy_exported.narrative_training_pair["narrative_bullets"])

    # -------------------------------------------------------------------------
    # Fix 7: Scope allowlisting vs certification registry
    # -------------------------------------------------------------------------
    cat = get_ai_catalog()
    reg = cat.get_scope_certification_registry()
    certified_teams = {r["team"] for r in reg if r["certified"] is True}
    assert certified_teams == set()
    for r in reg:
        if r["certified"]:
            assert r["status"] == "verified"
            assert all(r["verification_gates"].values())
        else:
            assert r["status"] in {"partial_evidence", "unverified"}
            assert not all(r["verification_gates"].values())

    monkeypatch.setenv("PMS_AI_ENABLED_SCOPES", "Inbound,Outbound")
    reg_filtered = cat.get_scope_certification_registry()
    assert {r["team"] for r in reg_filtered if r["enabled"] is True} == {"Inbound", "Outbound"}
    monkeypatch.delenv("PMS_AI_ENABLED_SCOPES", raising=False)

    # -------------------------------------------------------------------------
    # Fix 9: Production runtime DDL prohibition + disposable PostgreSQL schema test
    # -------------------------------------------------------------------------
    empty_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    EmptySession = sessionmaker(bind=empty_engine)
    empty_db = EmptySession()

    monkeypatch.setenv("APP_ENV", "production")
    prod_repo = AiConversationRepository(empty_db)
    assert prod_repo.is_schema_ready() is False
    with pytest.raises(ConversationMigrationUnavailableError):
        prod_repo.create_conversation(owner_user_id="u1", owner_role="Manager")
    monkeypatch.setenv("APP_ENV", "test")

    # Verify single Alembic head c9e1a2b3d4f5 and test upgrade() + downgrade() on disposable schema
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect as sa_inspect

    mig_dir = Path(__file__).resolve().parent.parent / "migrations" / "versions"
    mig_files = list(mig_dir.glob("*c9e1a2b3d4f5*.py"))
    assert len(mig_files) == 1
    spec = importlib.util.spec_from_file_location("mig_c9e1a2b3d4f5", mig_files[0])
    assert spec is not None and spec.loader is not None
    mig_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig_mod)

    # Test upgrade + downgrade on a fresh disposable database with pre-existing ai_interaction_traces
    mig_engine = create_engine("sqlite:///:memory:")
    with mig_engine.begin() as conn:
        with pytest.raises(RuntimeError, match="missing required base columns"):
            conn.execute(text("CREATE TABLE ai_interaction_traces (id VARCHAR(64) PRIMARY KEY, prompt TEXT)"))
            ctx_bad = MigrationContext.configure(conn)
            monkeypatch.setattr(mig_mod, "op", Operations(ctx_bad))
            mig_mod.upgrade()
        conn.execute(text("DROP TABLE ai_interaction_traces"))
        AiInteractionTrace.__table__.create(bind=conn, checkfirst=True)
        ctx = MigrationContext.configure(conn)
        op_proxy = Operations(ctx)
        monkeypatch.setattr(mig_mod, "op", op_proxy)
        mig_mod.upgrade()
        tables_after_up = set(sa_inspect(conn).get_table_names())
        assert {"ai_conversations", "ai_turns", "ai_interaction_traces"}.issubset(tables_after_up)
        trace_cols_up = {c["name"] for c in sa_inspect(conn).get_columns("ai_interaction_traces")}
        assert "turn_id" in trace_cols_up
        mig_mod.downgrade()
        tables_after_down = set(sa_inspect(conn).get_table_names())
        assert "ai_conversations" not in tables_after_down
        assert "ai_turns" not in tables_after_down

    # Also test upgrade + downgrade on a disposable PostgreSQL schema when local PostgreSQL is configured
    from config.database import DATABASE_URL

    if str(DATABASE_URL).startswith("postgresql"):
        tmp_schema = f"tmp_ai_mig_{uuid.uuid4().hex[:12]}"
        pg_engine = create_engine(DATABASE_URL)
        try:
            with pg_engine.begin() as pg_conn:
                pg_conn.execute(text(f"CREATE SCHEMA {tmp_schema}"))
                pg_conn.execute(text(f"SET LOCAL search_path TO {tmp_schema}"))
                ctx_pg = MigrationContext.configure(pg_conn)
                op_pg = Operations(ctx_pg)
                monkeypatch.setattr(mig_mod, "op", op_pg)
                # 1. Fresh schema upgrade -> downgrade
                mig_mod.upgrade()
                pg_tables_up = set(sa_inspect(pg_conn).get_table_names(schema=tmp_schema))
                assert {"ai_conversations", "ai_turns", "ai_interaction_traces"}.issubset(pg_tables_up)
                mig_mod.downgrade()
                pg_tables_down = set(sa_inspect(pg_conn).get_table_names(schema=tmp_schema))
                assert "ai_conversations" not in pg_tables_down
                assert "ai_turns" not in pg_tables_down
                # 2. Upgrade again on schema that already has ai_interaction_traces -> downgrade
                mig_mod.upgrade()
                pg_tables_up2 = set(sa_inspect(pg_conn).get_table_names(schema=tmp_schema))
                assert {"ai_conversations", "ai_turns", "ai_interaction_traces"}.issubset(pg_tables_up2)
                mig_mod.downgrade()
        finally:
            with pg_engine.begin() as cleanup_conn:
                cleanup_conn.execute(text(f"DROP SCHEMA IF EXISTS {tmp_schema} CASCADE"))
            pg_engine.dispose()





def test_v2_post_b470ef6_nine_review_fixes(monkeypatch):
    """Comprehensive verification for all 9 post-b470ef6 review findings."""
    import importlib.util
    import json
    import uuid
    import pytest
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect as sa_inspect, text
    from sqlalchemy.orm import sessionmaker

    from config.database import Base, DATABASE_URL
    from models.ai_schemas import (
        AiChatRequest,
        AiChatResponsePayload,
        ConfirmedQueryContext,
        SessionFilterContext,
    )
    from models.models import (
        AiConversation,
        AiInteractionTrace,
        AiTurn,
        Team,
        User,
        UserBranchAssignment,
        UserFunctionAssignment,
        UserTeamAssignment,
    )
    from repositories.ai_conversation_repository import (
        AiConversationRepository,
        ConversationMigrationUnavailableError,
        ConversationStaleContextError,
        ConversationVersionConflictError,
        RequestIdReuseConflictError,
        compute_request_fingerprint,
        compute_scope_fingerprint,
    )
    from scripts.evaluate_ai_classifier import verify_semantic_answer_correctness
    from services.ai.catalog import ai_evidence_cache
    from services.ai.conversation_service import AiConversationService
    from services.ai.orchestrator import PmsAiOrchestrator
    from services.ai.trace_logger import (
        TrainingTraceLogger,
        assess_pii_quarantine,
        ensure_trace_schema_once,
        redact_nested_payload,
        sanitize_prompt_for_router_training,
    )
    from services.cache_invalidation_service import CacheInvalidationService
    from services.insights_service import InsightAccessError

    db = _build_in_memory_db()

    adham_months = [
        ("March", 82.50),
        ("April", 61.20),
        ("May", 61.20),
        ("June", None),
        ("July", 94.24),
        ("August", 94.18),
        ("September", 91.00),
        ("October", 101.20),
        ("November", 104.50),
    ]
    records = []
    for m_name, sc in adham_months:
        rec = _make_call_center_record(
            "EMP888",
            "Adham Precision",
            "Inbound",
            sc if sc is not None else 0.0,
            45,
            60,
            120,
            150,
            month=m_name,
        )
        if sc is None:
            object.__setattr__(rec.evaluation, "score", None)
        else:
            rec.evaluation.score = sc
        records.append(rec)

    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()

    # -------------------------------------------------------------------------
    # Issue 1: Replay authorization for team-specific performance levels
    # -------------------------------------------------------------------------
    scope_with_corp = {
        "role": "Manager",
        "user_id": "00000000-0000-0000-0000-000000000701",
        "has_unrestricted_team_access": False,
        "accessible_functions": ["Call Center"],
        "accessible_teams": ["Inbound"],
        "accessible_team_levels": [
            ("Inbound", "Employee"),
            ("Inbound", "Managerial"),
            ("Inbound", "Corporate"),
        ],
        "accessible_regions": ["EGY"],
        "accessible_branches": ["dubai"],
        "employee_id": "MGR701",
        "is_self_only": False,
    }
    scope_without_corp = {
        **scope_with_corp,
        "accessible_team_levels": [
            ("Inbound", "Employee"),
        ],
    }
    assert compute_scope_fingerprint(scope_with_corp) != compute_scope_fingerprint(scope_without_corp)
    assert compute_scope_fingerprint(scope_with_corp) != compute_scope_fingerprint({**scope_with_corp, "is_self_only": True})
    assert compute_scope_fingerprint(scope_with_corp) != compute_scope_fingerprint({**scope_with_corp, "employee_id": "MGR999"})
    assert compute_scope_fingerprint(scope_with_corp) != compute_scope_fingerprint({**scope_with_corp, "accessible_regions": ["UAE"]})

    orch_corp = PmsAiOrchestrator(db, scope_with_corp)
    r_corp_ok = orch_corp.run_chat_turn(
        AiChatRequest(
            prompt="Show Inbound Corporate Balanced Scorecard in September 2026",
            client_request_id="req-inbound-corp-1",
            session_state=SessionFilterContext(
                function="Call Center",
                team="Inbound",
                performance_level="Corporate",
            ),
        )
    )
    assert r_corp_ok.outcome == "answer"
    assert "Access restricted" not in r_corp_ok.headline

    # Remove only the Corporate/Managerial grant for Inbound while keeping Inbound Employee access;
    # retrying the exact same client_request_id must NOT replay the old Corporate answer.
    orch_no_corp = PmsAiOrchestrator(db, scope_without_corp)
    r_corp_revoked = orch_no_corp.run_chat_turn(
        AiChatRequest(
            prompt="Show Inbound Corporate Balanced Scorecard in September 2026",
            conversation_id=r_corp_ok.conversation_id,
            context_version=1,
            client_request_id="req-inbound-corp-1",
            session_state=SessionFilterContext(
                function="Call Center",
                team="Inbound",
                performance_level="Corporate",
            ),
        )
    )
    assert r_corp_revoked.outcome == "restricted_access"
    assert "Access restricted" in r_corp_revoked.headline
    assert r_corp_revoked.headline != r_corp_ok.headline

    # -------------------------------------------------------------------------
    # Issue 2: Fail safely for legacy turns without fingerprints
    # -------------------------------------------------------------------------
    legacy_scope = {
        "role": "Manager",
        "user_id": "00000000-0000-0000-0000-000000000702",
        "has_unrestricted_team_access": False,
        "accessible_functions": ["Call Center"],
        "accessible_teams": ["Inbound"],
    }
    conv_svc_leg = AiConversationService(db, legacy_scope)
    leg_conv = conv_svc_leg.create_conversation(
        scope=legacy_scope,
        initial_state=SessionFilterContext(function="Call Center", team="Inbound"),
    )
    # Insert a completed legacy turn WITHOUT request_fingerprint, scope_fingerprint, or eval_id
    legacy_turn_row = AiTurn(
        id=str(uuid.uuid4()),
        conversation_id=leg_conv.conversation_id,
        turn_index=1,
        client_request_id="req-legacy-nofp",
        status="completed",
        user_prompt_redacted="What was <EMPLOYEE_NAME>'s score in September 2026?",
        validated_plan={"intent": "ranking", "team": "Inbound", "function": "Call Center"},
        evidence_summary={"records": 1},  # No fingerprints!
        response_payload={
            "trace_id": "leg-trace-1",
            "outcome": "answer",
            "headline": "LEGACY STALE ANSWER 50.0%",
            "narrative_bullets": [],
            "visual_cards": [],
            "citations": [],
            "deep_links": [],
            "suggested_followups": [],
            "resolved_session_state": {"function": "Call Center", "team": "Inbound"},
            "domain_guardrail_notes": [],
            "tool_calls": [],
            "provider_used": "deterministic-local",
            "model_used": "pms-deterministic-v1",
            "latency_ms": 5,
        },
        outcome="answer",
        route_used="local_rules",
        provider_calls=0,
        total_ms=5.0,
    )
    db.add(legacy_turn_row)
    db.commit()

    # 2a. Legacy turn after changed prompt -> raises RequestIdReuseConflictError
    with pytest.raises(RequestIdReuseConflictError):
        PmsAiOrchestrator(db, legacy_scope).run_chat_turn(
            AiChatRequest(
                prompt="Completely different prompt on legacy request id",
                conversation_id=leg_conv.conversation_id,
                context_version=1,
                client_request_id="req-legacy-nofp",
                session_state=SessionFilterContext(function="Call Center", team="Inbound"),
            )
        )

    # 2b. Legacy turn after changed access -> does NOT replay "LEGACY STALE ANSWER 50.0%"; returns restricted_access
    revoked_legacy_scope = {
        **legacy_scope,
        "accessible_teams": ["Outbound"],
    }
    r_leg_revoked = PmsAiOrchestrator(db, revoked_legacy_scope).run_chat_turn(
        AiChatRequest(
            prompt="What was Adham's score in September 2026?",
            conversation_id=leg_conv.conversation_id,
            context_version=1,
            client_request_id="req-legacy-nofp",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert r_leg_revoked.outcome == "restricted_access"
    assert "LEGACY STALE ANSWER" not in r_leg_revoked.headline

    # 2c. Legacy turn after changed published data with authorized scope -> recomputes fresh 91.0% instead of replaying 50.0%
    legacy_turn_row.status = "completed"
    legacy_turn_row.evidence_summary = {"records": 1}
    legacy_turn_row.response_payload = {
        **legacy_turn_row.response_payload,
        "headline": "LEGACY STALE ANSWER 50.0%",
    }
    conv_obj = db.query(AiConversation).filter(AiConversation.id == leg_conv.conversation_id).first()
    assert conv_obj is not None
    conv_obj.context_version = 1
    db.commit()

    CacheInvalidationService.bump_data_version()
    ai_evidence_cache.clear()
    r_leg_recomputed = PmsAiOrchestrator(db, legacy_scope).run_chat_turn(
        AiChatRequest(
            prompt="What was Adham's score in September 2026?",
            conversation_id=leg_conv.conversation_id,
            context_version=1,
            client_request_id="req-legacy-nofp",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert r_leg_recomputed.outcome == "answer"
    assert "91.0%" in r_leg_recomputed.headline
    assert "LEGACY STALE ANSWER" not in r_leg_recomputed.headline

    # -------------------------------------------------------------------------
    # Issue 3: Revalidate permissions during execution and context restoration
    # -------------------------------------------------------------------------
    team_inb = Team(id=uuid.uuid4(), name="Inbound", db_name="Inbound", display_name="Inbound", is_active=True)
    team_out = Team(id=uuid.uuid4(), name="Outbound", db_name="Outbound", display_name="Outbound", is_active=True)
    db.add_all([team_inb, team_out])
    db.flush()

    live_user_uuid = uuid.uuid4()
    live_user = User(
        id=live_user_uuid,
        username="live_mgr",
        email="live_mgr@sgh.com",
        password_hash="hashed",
        full_name="Live Manager",
        role="Manager",
        is_active=True,
    )
    db.add(live_user)
    db.flush()

    ufa = UserFunctionAssignment(user_id=live_user_uuid, function_name="Call Center", assigned_by="system")
    uta_emp = UserTeamAssignment(user_id=live_user_uuid, team_id=team_inb.id, performance_level="Employee", assigned_by="system")
    uta_mgr = UserTeamAssignment(user_id=live_user_uuid, team_id=team_inb.id, performance_level="Managerial", assigned_by="system")
    uba = UserBranchAssignment(user_id=live_user_uuid, branch_key="dubai", assigned_by="system")
    db.add_all([ufa, uta_emp, uta_mgr, uba])
    db.commit()

    live_scope = {
        "user_id": str(live_user_uuid),
        "role": "Manager",
        "is_active": True,
        "has_unrestricted_team_access": False,
        "accessible_functions": ["Call Center"],
        "accessible_teams": ["Inbound"],
        "accessible_team_levels": [("Inbound", "Employee"), ("Inbound", "Managerial")],
        "accessible_branches": ["dubai"],
        "_db_user_verified": True,
    }
    live_orch = PmsAiOrchestrator(db, live_scope)
    r_live_t1 = live_orch.run_chat_turn(
        AiChatRequest(
            prompt="What was Adham's score in September 2026?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound", branch="dubai"),
        )
    )
    assert r_live_t1.outcome == "answer"
    assert r_live_t1.conversation_id is not None

    # Save pending clarification choices referencing Inbound and Outbound on the conversation
    live_conv_row = db.query(AiConversation).filter(AiConversation.id == r_live_t1.conversation_id).first()
    assert live_conv_row is not None
    live_conv_row.pending_clarification = {
        "code": "AMBIGUOUS_PERSON",
        "question": "Which person?",
        "choices": [
            {
                "id": "c-inb",
                "label": "Adham Precision (Inbound)",
                "prompt_to_send": "Adham Precision in Inbound",
                "team": "Inbound",
                "employee_id": "EMP888",
                "employee_name": "Adham Precision",
            },
            {
                "id": "c-out",
                "label": "Secret Agent (Outbound)",
                "prompt_to_send": "Secret Agent in Outbound",
                "team": "Outbound",
                "employee_id": "EMP_OUT",
                "employee_name": "Secret Agent",
            },
        ],
    }
    db.commit()

    # 3a. Mid-execution permission revocation: revoke Inbound access in DB while tool execution is running
    from services.ai.tool_registry import DeterministicToolRegistry

    orig_exec_spotlight = DeterministicToolRegistry.execute_agent_spotlight_and_trend

    def _exec_spotlight_and_revoke_db(self_tools, *args, **kwargs):
        res_tool = orig_exec_spotlight(self_tools, *args, **kwargs)
        # Revoke Inbound team access in DB before orchestrator completes turn!
        db.query(UserTeamAssignment).filter(UserTeamAssignment.user_id == live_user_uuid).delete()
        db.add(UserTeamAssignment(user_id=live_user_uuid, team_id=team_out.id, performance_level="Employee", assigned_by="system"))
        db.commit()
        return res_tool

    monkeypatch.setattr(DeterministicToolRegistry, "execute_agent_spotlight_and_trend", _exec_spotlight_and_revoke_db)
    r_mid_revoke = PmsAiOrchestrator(db, live_scope).run_chat_turn(
        AiChatRequest(
            prompt="What was Adham's score in July 2026?",
            conversation_id=r_live_t1.conversation_id,
            context_version=r_live_t1.context_version,
            session_state=SessionFilterContext(function="Call Center", team="Inbound", branch="dubai"),
        )
    )
    monkeypatch.setattr(DeterministicToolRegistry, "execute_agent_spotlight_and_trend", orig_exec_spotlight)
    assert r_mid_revoke.outcome == "restricted_access"
    assert "permissions changed during execution" in r_mid_revoke.headline
    assert "94.24%" not in r_mid_revoke.headline
    assert r_mid_revoke.visual_cards == []

    # 3b. Context restoration after Inbound revocation: get_context must redact Adham Precision & Inbound choices
    restored_ctx = AiConversationService(db, live_scope).get_context(
        conversation_id=r_live_t1.conversation_id,
        scope=live_scope,
    )
    assert restored_ctx.confirmed_context.last_subject_employee_id is None
    assert restored_ctx.confirmed_context.last_subject_employee_name is None
    assert restored_ctx.confirmed_context.team is None
    if restored_ctx.pending_clarification:
        choice_ids = [c.id for c in restored_ctx.pending_clarification.choices]
        assert "c-inb" not in choice_ids
        assert "Adham" not in json.dumps(restored_ctx.model_dump())

    # 3c. Role demotion in DB (Manager -> Employee self-only with employee_id="EMP999") replaces effective role
    live_user.role = "Employee"
    live_user.employee_id = "EMP999"
    db.commit()
    rebuilt = AiConversationService(db, live_scope).validate_live_account_and_scope(live_scope)
    assert rebuilt["role"] == "Employee"
    assert rebuilt["is_self_only"] is True
    assert rebuilt["employee_id"] == "EMP999"

    # -------------------------------------------------------------------------
    # Issue 4: Best/worst month follow-ups and missing-score handling
    # -------------------------------------------------------------------------
    gm_scope = {
        "role": "General Manager",
        "user_id": "00000000-0000-0000-0000-000000000704",
        "has_unrestricted_team_access": True,
        "accessible_branches": ["dubai", "sharjah", "ajman", "clinics"],
    }
    gm_orch = PmsAiOrchestrator(db, gm_scope)

    # 4a. Open-ended worst month question does NOT start with "No." and surfaces missing-month limitation in headline
    r_open_worst = gm_orch.run_chat_turn(
        AiChatRequest(
            prompt="What was Adham's worst month?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert r_open_worst.outcome == "answer"
    assert not r_open_worst.headline.startswith("No.")
    assert not r_open_worst.headline.startswith("Yes.")
    assert "was April 2026 and May 2026 (tied) at 61.2%" in r_open_worst.headline
    assert "June 2026 had no evaluated score and was excluded" in r_open_worst.headline

    # 4b. Follow-up "And his best month?" overrides inherited worst-month operation
    r_followup_best = gm_orch.run_chat_turn(
        AiChatRequest(
            prompt="And his best month?",
            conversation_id=r_open_worst.conversation_id,
            context_version=r_open_worst.context_version,
            session_state=r_open_worst.resolved_session_state,
        )
    )
    assert r_followup_best.outcome == "answer"
    assert r_followup_best.validated_plan_v2 is not None
    assert r_followup_best.validated_plan_v2.operations[0].kind == "person_best_period"
    assert not r_followup_best.headline.startswith("No.")
    assert "was November 2026 at 104.5%" in r_followup_best.headline
    assert "worst month" not in r_followup_best.headline

    # 4c. Follow-up "What about his worst?" overrides inherited best-month operation
    r_followup_worst_again = gm_orch.run_chat_turn(
        AiChatRequest(
            prompt="What about his worst?",
            conversation_id=r_followup_best.conversation_id,
            context_version=r_followup_best.context_version,
            session_state=r_followup_best.resolved_session_state,
        )
    )
    assert r_followup_worst_again.outcome == "answer"
    assert r_followup_worst_again.validated_plan_v2 is not None
    assert r_followup_worst_again.validated_plan_v2.operations[0].kind == "person_worst_period"
    assert "was April 2026 and May 2026 (tied) at 61.2%" in r_followup_worst_again.headline
    assert "best month" not in r_followup_worst_again.headline

    # 4d. Requested month with no score (June 2026) reports unavailable and never borrows another month's score,
    # followed by a later month with a score (July 2026 -> 94.24%)
    r_june_missing = gm_orch.run_chat_turn(
        AiChatRequest(
            prompt="What was Adham's score in June 2026?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert r_june_missing.outcome == "answer"
    assert "No published evaluation score is available for Adham Precision (EMP888) in June 2026" in r_june_missing.headline
    assert "104.5%" not in r_june_missing.headline
    assert "94.24%" not in r_june_missing.headline

    r_july_after_missing = gm_orch.run_chat_turn(
        AiChatRequest(
            prompt="What about July 2026?",
            conversation_id=r_june_missing.conversation_id,
            context_version=r_june_missing.context_version,
            session_state=r_june_missing.resolved_session_state,
        )
    )
    assert r_july_after_missing.outcome == "answer"
    assert "Adham Precision (EMP888) scored 94.24%" in r_july_after_missing.headline
    assert "July 2026" in r_july_after_missing.headline

    # -------------------------------------------------------------------------
    # Issue 5: Bind retries to full request and refreshed context
    # -------------------------------------------------------------------------
    base_fp = compute_request_fingerprint(
        prompt="Show score",
        session_filters={
            "function": "Call Center",
            "team": "Inbound",
            "position": "Agent",
            "employee_id": "EMP888",
            "region": "UAE",
            "branch": "dubai",
            "performance_level": "Employee",
            "month": "September",
            "year": 2026,
            "period": "2026-09",
            "periods": ["2026-09"],
        },
        answer_detail="brief",
        clarification_choice_id="c1",
    )
    for changed_k, changed_v in (
        ("function", "RCM"),
        ("team", "Outbound"),
        ("position", "Trainer"),
        ("employee_id", "EMP999"),
        ("region", "EGY"),
        ("branch", "sharjah"),
        ("performance_level", "Managerial"),
        ("month", "August"),
        ("year", 2025),
        ("periods", ["2026-08"]),
    ):
        mod_filters = {
            "function": "Call Center",
            "team": "Inbound",
            "position": "Agent",
            "employee_id": "EMP888",
            "region": "UAE",
            "branch": "dubai",
            "performance_level": "Employee",
            "month": "September",
            "year": 2026,
            "period": "2026-09",
            "periods": ["2026-09"],
            changed_k: changed_v,
        }
        assert compute_request_fingerprint(
            prompt="Show score",
            session_filters=mod_filters,
            answer_detail="brief",
            clarification_choice_id="c1",
        ) != base_fp

    # Reusing a client_request_id with different filters raises RequestIdReuseConflictError
    r_fp_1 = gm_orch.run_chat_turn(
        AiChatRequest(
            prompt="Hi",
            client_request_id="req-filter-bind-1",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    with pytest.raises(RequestIdReuseConflictError):
        gm_orch.run_chat_turn(
            AiChatRequest(
                prompt="Hi",
                conversation_id=r_fp_1.conversation_id,
                context_version=1,
                client_request_id="req-filter-bind-1",
                session_state=SessionFilterContext(function="Call Center", team="Outbound"),
            )
        )

    # Stale request with wrong context_version must fail BEFORE claiming a turn so immediate retry is not blocked
    with pytest.raises(ConversationVersionConflictError):
        gm_orch.run_chat_turn(
            AiChatRequest(
                prompt="Follow up with stale version",
                conversation_id=r_fp_1.conversation_id,
                context_version=1,  # current is 2!
                client_request_id="req-stale-no-block",
                session_state=SessionFilterContext(function="Call Center", team="Inbound"),
            )
        )
    # Immediate retry with the same client_request_id and refreshed context_version=2 succeeds without TurnAlreadyInFlightError!
    r_retry_after_409 = gm_orch.run_chat_turn(
        AiChatRequest(
            prompt="Follow up with stale version",
            conversation_id=r_fp_1.conversation_id,
            context_version=2,
            client_request_id="req-stale-no-block",
            session_state=SessionFilterContext(function="Call Center", team="Inbound"),
        )
    )
    assert r_retry_after_409.context_version == 3

    # -------------------------------------------------------------------------
    # Issue 6: Unicode-safe trace and training-data redaction + PII quarantine
    # -------------------------------------------------------------------------
    unicode_names = [
        "مريم محسن محمود",
        "Renée Joséphine",
        "Fatima-Zahra Al-Mansoor",
        "Adham Precision",
    ]
    unicode_prompt = (
        "Compare مريم محسن محمود and مريم with Renée Joséphine (Renée) and Fatima-Zahra in Inbound"
    )
    redacted_unicode = sanitize_prompt_for_router_training(
        unicode_prompt,
        known_employee_names=unicode_names,
    )
    for forbidden_tok in ("مريم", "محسن", "Renée", "Joséphine", "Fatima-Zahra", "Fatima"):
        assert forbidden_tok not in redacted_unicode
    assert "<EMPLOYEE_NAME>" in redacted_unicode

    nested_unicode = redact_nested_payload(
        {
            "headline": "مريم محسن محمود scored 94.4% while Renée scored 88.0%.",
            "nested": {"employee_name": "مريم محسن محمود", "note": "Check Fatima-Zahra's trend"},
        },
        known_employee_names=unicode_names,
    )
    assert "مريم" not in json.dumps(nested_unicode, ensure_ascii=False)
    assert "Renée" not in json.dumps(nested_unicode, ensure_ascii=False)
    assert "Fatima" not in json.dumps(nested_unicode, ensure_ascii=False)

    # Uncertain person reference not in known_employee_names is flagged by assess_pii_quarantine
    uncertain_sanitized = sanitize_prompt_for_router_training(
        "Is UnknownPersonXyz a new joiner in Inbound?",
        known_employee_names=unicode_names,
        run_syntactic_extraction=False,
    )
    is_quarantined, q_reasons = assess_pii_quarantine(
        uncertain_sanitized,
        original_text="Is UnknownPersonXyz a new joiner in Inbound?",
        known_employee_names=unicode_names,
    )
    assert is_quarantined is True
    assert len(q_reasons) > 0

    # Quarantined trace is excluded from unverified export unless explicitly Admin-reviewed
    q_trace_id = uuid.uuid4()
    db.add(
        AiInteractionTrace(
            id=q_trace_id,
            user_id=gm_scope["user_id"],
            role="General Manager",
            prompt="Is UnknownPersonXyz a new joiner in Inbound?",
            sanitized_prompt="Is UnknownPersonXyz a new joiner in Inbound?",
            session_state={"function": "Call Center", "team": "Inbound"},
            tool_calls=[],
            tool_digest={"pii_quarantined": True, "pii_quarantine_reasons": ["unredacted_person_context"]},
            structured_response={"headline": "Clarification needed."},
            provider_name="deterministic-local",
            model_name="pms-deterministic-v1",
            latency_ms=5,
            non_empty_evidence=True,
            guardrail_triggered=False,
            feedback_rating="up",
            is_distillation_eligible=True,
            reviewer_verified=False,
        )
    )
    db.commit()
    unverified_exports = TrainingTraceLogger(db).export_distillation_dataset(verified_only=False)
    assert all(x.trace_id != str(q_trace_id) for x in unverified_exports)

    # -------------------------------------------------------------------------
    # Issue 7: Hardened migration adoption and rollback (staging/prod DDL + 4 schema cases)
    # -------------------------------------------------------------------------
    for env_name in ("staging", "production"):
        stg_engine = create_engine("sqlite:///:memory:")
        StgSession = sessionmaker(bind=stg_engine)
        stg_db = StgSession()
        monkeypatch.setenv("APP_ENV", env_name)
        ensure_trace_schema_once(stg_db)
        assert sa_inspect(stg_engine).get_table_names() == []
        stg_repo = AiConversationRepository(stg_db)
        assert stg_repo.is_schema_ready() is False
        with pytest.raises(ConversationMigrationUnavailableError):
            stg_repo.create_conversation(owner_user_id="u1", owner_role="Manager")
    monkeypatch.setenv("APP_ENV", "test")

    mig_dir = Path(__file__).resolve().parent.parent / "migrations" / "versions"
    mig_file = next(mig_dir.glob("*c9e1a2b3d4f5*.py"))
    spec = importlib.util.spec_from_file_location("mig_c9e1a2b3d4f5_v2", mig_file)
    assert spec is not None and spec.loader is not None
    mig_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig_mod)

    # Test (a) Production-shaped pre-v2 trace table (19 base columns + existing trace row) -> upgrade -> data preserved -> review data blocks destructive downgrade
    prod_shape_engine = create_engine("sqlite:///:memory:")
    with prod_shape_engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE ai_interaction_traces (
                    id VARCHAR(64) PRIMARY KEY NOT NULL,
                    user_id VARCHAR(100),
                    role VARCHAR(50) NOT NULL,
                    prompt TEXT NOT NULL,
                    sanitized_prompt TEXT NOT NULL,
                    session_state JSON NOT NULL,
                    tool_calls JSON NOT NULL,
                    tool_digest JSON NOT NULL,
                    structured_response JSON NOT NULL,
                    provider_name VARCHAR(60) NOT NULL,
                    model_name VARCHAR(100) NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    non_empty_evidence BOOLEAN NOT NULL,
                    guardrail_triggered BOOLEAN NOT NULL,
                    feedback_rating VARCHAR(20),
                    feedback_reason VARCHAR(120),
                    is_distillation_eligible BOOLEAN NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO ai_interaction_traces (
                    id, user_id, role, prompt, sanitized_prompt, session_state,
                    tool_calls, tool_digest, structured_response, provider_name,
                    model_name, latency_ms, non_empty_evidence, guardrail_triggered,
                    is_distillation_eligible, created_at, updated_at
                ) VALUES (
                    'trace-pre-1', 'u-1', 'Manager', 'Hi', 'Hi', '{}',
                    '[]', '{}', '{}', 'deterministic', 'v1', 5, 1, 0, 1,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        monkeypatch.setattr(mig_mod, "op", Operations(MigrationContext.configure(conn)))
        mig_mod.upgrade()
        cols_after_adopt = {c["name"] for c in sa_inspect(conn).get_columns("ai_interaction_traces")}
        assert {"turn_id", "reviewer_verified", "reviewer_id", "reviewed_at"}.issubset(cols_after_adopt)
        preserved_count = int(conn.execute(text("SELECT COUNT(*) FROM ai_interaction_traces WHERE id = 'trace-pre-1'")).scalar() or 0)
        assert preserved_count == 1

        # Mark row as Admin-reviewed -> downgrade must refuse destructive rollback
        conn.execute(text("UPDATE ai_interaction_traces SET reviewer_verified = 1, reviewer_id = 'admin-1' WHERE id = 'trace-pre-1'"))
        with pytest.raises(RuntimeError, match="Refusing destructive downgrade"):
            mig_mod.downgrade()

        # Clear review metadata -> downgrade drops ai_turns and ai_conversations while preserving trace rows & columns
        conn.execute(text("UPDATE ai_interaction_traces SET reviewer_verified = 0, reviewer_id = NULL WHERE id = 'trace-pre-1'"))
        mig_mod.downgrade()
        cols_after_down = {c["name"] for c in sa_inspect(conn).get_columns("ai_interaction_traces")}
        assert {"turn_id", "reviewer_verified", "reviewer_id", "reviewed_at"}.issubset(cols_after_down)
        assert int(conn.execute(text("SELECT COUNT(*) FROM ai_interaction_traces WHERE id = 'trace-pre-1'")).scalar() or 0) == 1

    if str(DATABASE_URL).startswith("postgresql"):
        pg_engine = create_engine(DATABASE_URL)
        tmp_bad = f"tmp_ai_mig_bad_{uuid.uuid4().hex[:10]}"
        tmp_prod = f"tmp_ai_mig_prod_{uuid.uuid4().hex[:10]}"
        try:
            with pg_engine.begin() as pg_conn:
                pg_conn.execute(text(f"CREATE SCHEMA {tmp_bad}"))
                pg_conn.execute(text(f"SET LOCAL search_path TO {tmp_bad}"))
                pg_conn.execute(text("CREATE TABLE ai_interaction_traces (id UUID PRIMARY KEY, prompt TEXT)"))
                monkeypatch.setattr(mig_mod, "op", Operations(MigrationContext.configure(pg_conn)))
                with pytest.raises(RuntimeError, match="missing required base columns"):
                    mig_mod.upgrade()

            with pg_engine.begin() as pg_conn2:
                pg_conn2.execute(text(f"CREATE SCHEMA {tmp_prod}"))
                pg_conn2.execute(text(f"SET LOCAL search_path TO {tmp_prod}"))
                pg_conn2.execute(
                    text(
                        """
                        CREATE TABLE ai_interaction_traces (
                            id UUID PRIMARY KEY NOT NULL,
                            user_id VARCHAR(100),
                            role VARCHAR(50) NOT NULL,
                            prompt TEXT NOT NULL,
                            sanitized_prompt TEXT NOT NULL,
                            session_state JSON NOT NULL,
                            tool_calls JSON NOT NULL,
                            tool_digest JSON NOT NULL,
                            structured_response JSON NOT NULL,
                            provider_name VARCHAR(60) NOT NULL,
                            model_name VARCHAR(100) NOT NULL,
                            latency_ms INTEGER NOT NULL,
                            non_empty_evidence BOOLEAN NOT NULL,
                            guardrail_triggered BOOLEAN NOT NULL,
                            feedback_rating VARCHAR(20),
                            feedback_reason VARCHAR(120),
                            is_distillation_eligible BOOLEAN NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                )
                pg_conn2.execute(
                    text(
                        """
                        INSERT INTO ai_interaction_traces (
                            id, user_id, role, prompt, sanitized_prompt, session_state,
                            tool_calls, tool_digest, structured_response, provider_name,
                            model_name, latency_ms, non_empty_evidence, guardrail_triggered,
                            is_distillation_eligible
                        ) VALUES (
                            '00000000-0000-0000-0000-000000000901', 'u-pg', 'Manager', 'Hi', 'Hi', '{}',
                            '[]', '{}', '{}', 'deterministic', 'v1', 5, true, false, true
                        )
                        """
                    )
                )
                monkeypatch.setattr(mig_mod, "op", Operations(MigrationContext.configure(pg_conn2)))
                mig_mod.upgrade()
                pg_cols_up = {c["name"] for c in sa_inspect(pg_conn2).get_columns("ai_interaction_traces", schema=tmp_prod)}
                assert {"turn_id", "reviewer_verified", "reviewer_id", "reviewed_at"}.issubset(pg_cols_up)
                assert int(pg_conn2.execute(text("SELECT COUNT(*) FROM ai_interaction_traces")).scalar() or 0) == 1
                mig_mod.downgrade()
                pg_cols_down = {c["name"] for c in sa_inspect(pg_conn2).get_columns("ai_interaction_traces", schema=tmp_prod)}
                assert {"turn_id", "reviewer_verified", "reviewer_id", "reviewed_at"}.issubset(pg_cols_down)
                assert int(pg_conn2.execute(text("SELECT COUNT(*) FROM ai_interaction_traces")).scalar() or 0) == 1
        finally:
            with pg_engine.begin() as clean_conn:
                clean_conn.execute(text(f"DROP SCHEMA IF EXISTS {tmp_bad} CASCADE"))
                clean_conn.execute(text(f"DROP SCHEMA IF EXISTS {tmp_prod} CASCADE"))
            pg_engine.dispose()

    # -------------------------------------------------------------------------
    # Issue 8: Evaluation proves semantic answer correctness & rejects contradictions
    # -------------------------------------------------------------------------
    scenario_item = {
        "scenario_id": "test_contradiction",
        "expected_outcome": "answer",
        "expected_operation_kind": "person_worst_period",
        "expected_polarity": "open",
        "expected_facts": {
            "subject_name": "Adham Tarek",
            "direction": "worst",
            "target_period": "March 2026",
            "target_value": "82.0%",
        },
        "expected_must_contain": ["Adham Tarek", "March 2026", "82.0%"],
    }
    # 8a. Missing validated_plan_v2 must fail when expected_operation_kind is set
    resp_no_plan = r_open_worst.model_copy(
        update={
            "headline": "Adham Tarek's worst month was March 2026 at 82.0%.",
            "validated_plan_v2": None,
        }
    )
    ok_no_plan, errs_no_plan = verify_semantic_answer_correctness(scenario_item, resp_no_plan)
    assert ok_no_plan is False
    assert any("validated_plan_v2" in e for e in errs_no_plan)

    # 8b. Contradictory answer containing all expected substrings ("Adham Tarek", "March 2026", "82.0%") must fail
    contradictory_resp = r_open_worst.model_copy(
        update={
            "headline": (
                "No. Adham Tarek's best month was March 2026 at 82.0%, while their worst month was August 2026 at 96.5%."
            ),
        }
    )
    ok_contra, errs_contra = verify_semantic_answer_correctness(scenario_item, contradictory_resp)
    assert ok_contra is False
    assert len(errs_contra) >= 2


def test_ai_admin_diagnostics_endpoint():
    """Verify GET /api/ai/diagnostics returns safe operational posture and blocks non-Admins."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from api.middleware.auth_middleware import AuthMiddleware
    from api.routers.ai_workspace import router as ai_router
    from config.database import Base, get_db
    from models.models import ProductSetting
    from services.auth_service import AuthenticationService

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        AuthenticationService.create_user(db, "diag_admin", "diag_admin@example.invalid", "AdminSecret123!", "Admin")
        AuthenticationService.create_user(db, "diag_user", "diag_user@example.invalid", "UserSecret123!", "Manager")
        db.add(ProductSetting(key="ai_enabled", enabled=True))
        db.commit()
        admin_tok = AuthenticationService.authenticate_user(db, "diag_admin", "AdminSecret123!")
        user_tok = AuthenticationService.authenticate_user(db, "diag_user", "UserSecret123!")

    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.include_router(ai_router, prefix="/api")

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    # 1. Non-Admin receives 403 Forbidden
    res_user = client.get("/api/ai/diagnostics", headers={"Authorization": f"Bearer {user_tok}"})
    assert res_user.status_code == 403

    # 2. Admin receives 200 OK with safe diagnostics
    res_admin = client.get("/api/ai/diagnostics", headers={"Authorization": f"Bearer {admin_tok}"})
    assert res_admin.status_code == 200
    data = res_admin.json()["data"]
    assert data["feature_enabled"] is True
    assert data["pilot_role_restricted"] is True
    assert "model_configured_name" in data
    assert "concurrency_limit" in data
    assert data["concurrency_limit"] == 1
    assert data["fallback_scope"] == "process_local"
    assert "inference_verified" in data
    # Secrets must NEVER be present
    assert "api_key" not in str(res_admin.json()).lower()
    assert "password" not in str(res_admin.json()).lower()


def test_ai_catalog_truthful_certification_statuses():
    """Verify that catalog does NOT make blanket certified claims without proof."""
    from services.ai.catalog import get_ai_catalog

    catalog = get_ai_catalog()
    full_registry = catalog.get_full_coverage_scope_registry()
    assert len(full_registry) > 0

    # Unverified scopes must have certified=False and status='unverified'
    unverified_teams = {"Finance", "CSR", "IT", "Human Resources", "Marketing", "Pharmacy", "PMO"}
    found_unverified = 0
    for entry in full_registry:
        team = entry["team"]
        if team in unverified_teams:
            assert entry["certified"] is False, f"Scope {team} ({entry.get('country')}) claimed certified without evidence"
            assert entry["status"] in ("unverified", "partial", "unsupported", "no data"), f"Unexpected status {entry['status']} for {team}"
            found_unverified += 1
    assert found_unverified > 0

    # Application tests do not provide independent source parity, so these remain partial.
    inbound_entries = [e for e in full_registry if e["team"] == "Inbound" and e.get("region") == "EGY"]
    assert len(inbound_entries) > 0
    assert inbound_entries[0]["certified"] is False
    assert inbound_entries[0]["status"] == "partial"


def test_ai_diagnostics_db_failure_and_model_probe_rejection(monkeypatch):
    """Diagnostics must report performance_records_count=None on DB error, reject 400/422 probe, and sort chronologically."""
    import urllib.error
    from api.routers.ai_workspace import build_ai_diagnostics_payload
    from services.ai.llm_client import check_model_health
    from unittest.mock import MagicMock

    # 1. DB failure must return None (not 0) in data_freshness
    broken_db = MagicMock()
    broken_db.query.side_effect = RuntimeError("Database connection died")
    diag = build_ai_diagnostics_payload(broken_db)
    assert diag.data_freshness["performance_records_count"] is None
    assert diag.data_freshness["database_status"] == "read_failed"
    assert "database_error" not in diag.data_freshness
    assert diag.fallback_scope == "process_local"

    # 2. Chronological calendar sorting check: October 2026 must be later than September 2026
    normal_db = MagicMock()
    normal_db.query.return_value.scalar.return_value = 10
    normal_db.query.return_value.distinct.return_value.all.return_value = [
        (2026, "March"),
        (2026, "October"),
        (2026, "September"),
    ]
    diag_sorted = build_ai_diagnostics_payload(normal_db)
    assert diag_sorted.data_freshness["latest_published_period"] == "October 2026"

    # 3. Model probe rejecting HTTP 400 or HTTP 422
    class MockOpener:
        def open(self, *args, **kwargs):
            raise urllib.error.HTTPError(
                url="http://localhost:18080/v1/chat/completions",
                code=400,
                msg="Bad Request",
                hdrs={},
                fp=None,
            )

    monkeypatch.setattr("services.ai.llm_client.urllib.request.build_opener", lambda *_: MockOpener())
    health = check_model_health()
    assert health["available"] is False
    assert health["inference_verified"] is False
    assert "400" in health["reason"]
