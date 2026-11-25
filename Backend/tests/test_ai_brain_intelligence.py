"""Golden evaluation tests for the 5-pillar PMS AI Brain Upgrade."""

from __future__ import annotations

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.ai_schemas import (
    AiChatRequest,
    PageContextV1,
    SessionFilterContext,
    TypedMetricEvidence,
)
from models.schemas import CallsData, EvaluationData, GeoBreakdown, GeoData, PerformanceRecord
from services.ai.catalog import ai_evidence_cache
from services.ai.config import get_ai_runtime_config
from services.ai.local_evidence_synthesis import (
    _wants_arabic_reply,
    synthesize_validated_executive_variation,
)
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.pii_tokenizer import PiiPseudonymizer
from services.ai.provider_config_store import (
    DEFAULT_CLOUDFLARE_ALTER_MODEL,
    DEFAULT_CLOUDFLARE_MODEL,
    DEFAULT_NVIDIA_DAILY_LIMIT,
)
from services.ai.provider_engine import ProviderResponse
from services.ai.tool_registry import DeterministicToolRegistry, ToolExecutionContext
from services.dashboard_record_service import DashboardRecordService


def _build_in_memory_db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def _make_outbound_record(
    *,
    emp_id: str,
    name: str,
    score: float,
    booking_actual: float,
    booking_target: float = 0.30,
    reachability_actual: float = 0.60,
    reachability_target: float = 0.75,
    calls_handled: int = 500,
    bookings_dubai: int = 150,
    attended_dubai: int = 90,
    month: str = "September",
    year: int = 2026,
) -> PerformanceRecord:
    return PerformanceRecord(
        id=f"Outbound_{emp_id}_{year}_{month[:3]}",
        employee_id=emp_id,
        employee_name=name,
        team="Outbound",
        month=month,
        year=year,
        region="UAE",
        position="Outbound Agent",
        performance_level="Employee",
        status="Below Target" if score < 90 else "On Track",
        evaluation=EvaluationData(
            score=score,
            grade="Below Average" if score < 85 else "Average",
        ),
        calls=CallsData(inbound=0, total_handled=calls_handled, abandoned=0),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=bookings_dubai, sharjah=0, ajman=0, clinics=0),
            attended=GeoBreakdown(dubai=attended_dubai, sharjah=0, ajman=0, clinics=0),
        ),
        kpi_values=[
            {
                "kpi_key": "Booking",
                "label": "Booking Rate",
                "actual_value": booking_actual,
                "target_value": booking_target,
                "achievement_ratio": min(1.0, booking_actual / booking_target) if booking_target else 1.0,
                "weight_applied": 0.40,
                "contribution": min(1.0, booking_actual / booking_target) * 0.40,
                "direction": "higher_better",
                "unit": "%",
            },
            {
                "kpi_key": "Other",
                "label": "Reachability",
                "actual_value": reachability_actual,
                "target_value": reachability_target,
                "achievement_ratio": min(1.0, reachability_actual / reachability_target) if reachability_target else 1.0,
                "weight_applied": 0.30,
                "contribution": min(1.0, reachability_actual / reachability_target) * 0.30,
                "direction": "higher_better",
                "unit": "%",
            },
        ],
    )


def _patch_records(monkeypatch: pytest.MonkeyPatch, records: list[PerformanceRecord]) -> None:
    monkeypatch.setattr(DashboardRecordService, "list_records", lambda _self, **_kw: records)
    monkeypatch.setattr(DashboardRecordService, "list_analysis_records", lambda _self, **_kw: records)
    monkeypatch.setattr(DashboardRecordService, "list_record_index", lambda _self: None)


# ---------------------------------------------------------------------------
# Pillar 1: Provider defaults, Clinical scopes & Role access
# ---------------------------------------------------------------------------

def test_pillar1_provider_defaults_and_clinical_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    assert DEFAULT_CLOUDFLARE_MODEL == "@cf/zai-org/glm-4.7-flash"
    assert DEFAULT_CLOUDFLARE_ALTER_MODEL == "@cf/ibm-granite/granite-4.0-h-micro"
    assert DEFAULT_NVIDIA_DAILY_LIMIT == 500

    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_MODEL_LED_ALL_ROLES_ENABLED", "true")
    cfg = get_ai_runtime_config()
    assert cfg.is_scope_allowed_for_cloud("ER Dr")
    assert cfg.is_scope_allowed_for_cloud("Radiologist")
    assert cfg.is_scope_allowed_for_cloud("Quality and management")
    assert cfg.is_scope_allowed_for_cloud("Clinical")

    # Model-led planner open to all authenticated roles (not restricted to Admin)
    assert cfg.can_use_model_led_planner("Admin", None) is True
    assert cfg.can_use_model_led_planner("General Manager", None) is True
    assert cfg.can_use_model_led_planner("Manager", None) is True
    assert cfg.can_use_model_led_planner("", None) is False
    assert cfg.can_use_model_led_planner(None, None) is False


# ---------------------------------------------------------------------------
# Pillar 3: Reversible PII Pseudonymizer & Turn-1 Bilingual LLM Synthesis
# ---------------------------------------------------------------------------

def test_pillar3_pii_pseudonymizer_roundtrip() -> None:
    pii = PiiPseudonymizer()
    tok_name, tok_id = pii.register_employee(
        employee_name="Rawan Mohamed Salah Elnajjar",
        employee_id="SGHD70101",
    )
    assert tok_name == "EMP_01"
    assert tok_id == "ID_01"

    raw = "Rawan Mohamed Salah Elnajjar (SGHD70101) — also Rawan Elnajjar — scored 81.0%."
    masked = pii.tokenize_text(raw)
    assert "Rawan" not in masked
    assert "Elnajjar" not in masked
    assert "SGHD70101" not in masked
    assert "EMP_01" in masked
    assert "ID_01" in masked
    assert pii.has_unmasked_pii(masked) is False
    assert pii.has_unmasked_pii(raw) is True

    restored = pii.detokenize_text("EMP_01 (ID_01) is the lowest-scoring agent at 81.0%.")
    assert restored == "Rawan Mohamed Salah Elnajjar (SGHD70101) is the lowest-scoring agent at 81.0%."


def test_pillar3_turn1_pseudonymized_synthesis_zero_pii_leak_and_arabic_mirror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.ai import local_evidence_synthesis as syn_mod

    monkeypatch.setenv("PMS_AI_LOCAL_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_PSEUDONYMIZED_PII_SYNTHESIS_ENABLED", "true")

    assert _wants_arabic_reply("مين أسوأ موظف؟") is True
    assert _wants_arabic_reply("meen aswa agent?") is True
    assert _wants_arabic_reply("who needs coaching most?") is False

    captured_requests = []

    class _FakeEngine:
        def generate(self, req):
            captured_requests.append(req)
            # LLM only sees EMP_01 and responds in Arabic keeping EMP_01 + exact numbers
            return ProviderResponse(
                provider="nvidia",
                model="meta/llama-3.3-70b-instruct",
                content=json.dumps(
                    {
                        "headline": "EMP_01 سجل أقل نتيجة إجمالية بنسبة 81.0% في Outbound خلال September 2026.",
                        "narrative_bullets": [
                            "أكبر فجوة في Reachability بنسبة 54.1% مقارنة بالهدف 75.0%."
                        ],
                    },
                    ensure_ascii=False,
                ),
                outcome="success",
            )

    monkeypatch.setattr(syn_mod, "get_unified_provider_engine", lambda: _FakeEngine())

    ev = TypedMetricEvidence(
        metric_id="ranking:outbound:overall_score",
        kpi_key="overall_score",
        display_name="Rawan Mohamed Salah Elnajjar Overall Score",
        team="Outbound",
        period="September 2026",
        actual=81.0,
        actual_display="81.0%",
        unit="%",
        direction="higher_better",
        source_link="/monthly-presentation?team=Outbound",
    )
    ev_kpi = TypedMetricEvidence(
        metric_id="kpi:outbound:reachability",
        kpi_key="reachability",
        display_name="Reachability",
        team="Outbound",
        period="September 2026",
        actual=54.1,
        target=75.0,
        actual_display="54.1%",
        target_display="75.0%",
        unit="%",
        direction="higher_better",
        source_link="/monthly-presentation?team=Outbound",
    )

    result = synthesize_validated_executive_variation(
        question="مين أسوأ موظف في Outbound؟",
        digests=[{"tool": "rank_entities", "employee_name": "Rawan Mohamed Salah Elnajjar", "employee_id": "SGHD70101"}],
        typed_evidence=[ev, ev_kpi],
        visible_summary={"headline_score": 85.4, "below_90_count": 5},
        allow_pseudonymized_pii=True,
    )

    assert result is not None
    assert result.provider_used == "nvidia"
    assert len(captured_requests) == 1
    sent_payload = captured_requests[0].messages[0].content
    sent_system = captured_requests[0].system_instruction
    # Zero PII left the server
    assert "Rawan" not in sent_payload
    assert "SGHD70101" not in sent_payload
    assert "EMP_01" in sent_payload
    assert "screen_context" in sent_payload
    # Arabic mirroring instruction was injected
    assert "business Arabic" in sent_system
    # Detokenized response restored exact verified employee name
    assert "Rawan Mohamed Salah Elnajjar" in result.headline
    assert "81.0%" in result.headline
    assert "EMP_01" not in result.headline


# ---------------------------------------------------------------------------
# Pillars 2 & 5: Natural & Bilingual Ranking Cues, KPI Drags, Explicit Click & Page Snapshot
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "prompt",
    [
        "who needs coaching most",
        "who is struggling",
        "مين أسوأ موظف",
        "meen aswa",
    ],
)
def test_pillar5_natural_and_bilingual_ranking_with_kpi_drags(
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
) -> None:
    db = _build_in_memory_db()
    rawan = _make_outbound_record(
        emp_id="SGHD70101",
        name="Rawan Mohamed Salah Elnajjar",
        score=81.0,
        booking_actual=0.23,
        reachability_actual=0.541,
    )
    ahmed = _make_outbound_record(
        emp_id="SGHD70184",
        name="Ahmed Mohamed Abdelrashed",
        score=84.5,
        booking_actual=0.295,
        reachability_actual=0.469,
    )
    _patch_records(monkeypatch, [rawan, ahmed])
    ai_evidence_cache.clear()

    gm_scope = {
        "role": "General Manager",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "has_unrestricted_team_access": True,
    }
    orch = PmsAiOrchestrator(db, gm_scope)

    res = orch.run_chat_turn(
        AiChatRequest(
            prompt=prompt,
            page_context=PageContextV1(
                page_id="executive_summary",
                route_id="/monthly-presentation/call-center/outbound",
                team_id="Outbound",
                period="2026-09",
                month="September",
                year=2026,
                selected_metric_id="Reachability",
                user_selected_metric=False,
            ),
            session_state=SessionFilterContext(
                team="Outbound",
                performance_level="Employee",
                month="September",
                year=2026,
            ),
        )
    )
    assert res.outcome == "answer"
    assert "Rawan" in res.headline
    assert "81.0%" in res.headline
    # Pillar 3 deterministic KPI drags bullet must surface Rawan's actual KPI gaps
    joined_bullets = " ".join(res.narrative_bullets or [])
    assert "Key KPI drags:" in joined_bullets
    assert "Reachability" in joined_bullets


def test_pillar2_explicit_kpi_click_and_visible_summary_explain_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _build_in_memory_db()
    rawan = _make_outbound_record(
        emp_id="SGHD70101",
        name="Rawan Mohamed Salah Elnajjar",
        score=81.0,
        booking_actual=0.23,
        reachability_actual=0.541,
    )
    ahmed = _make_outbound_record(
        emp_id="SGHD70184",
        name="Ahmed Mohamed Abdelrashed",
        score=84.5,
        booking_actual=0.295,
        reachability_actual=0.469,
    )
    _patch_records(monkeypatch, [rawan, ahmed])
    ai_evidence_cache.clear()

    gm_scope = {
        "role": "General Manager",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "has_unrestricted_team_access": True,
    }
    orch = PmsAiOrchestrator(db, gm_scope)

    # 1. Explicit KPI card click (user_selected_metric=True) DOES bind Reachability even on generic "who is worst"
    res_clicked = orch.run_chat_turn(
        AiChatRequest(
            prompt="who is worst",
            page_context=PageContextV1(
                page_id="executive_summary",
                route_id="/monthly-presentation/call-center/outbound",
                team_id="Outbound",
                period="2026-09",
                month="September",
                year=2026,
                selected_metric_id="Reachability",
                user_selected_metric=True,
            ),
            session_state=SessionFilterContext(
                team="Outbound",
                performance_level="Employee",
                month="September",
                year=2026,
            ),
        )
    )
    assert res_clicked.outcome == "answer"
    assert "Ahmed" in res_clicked.headline
    assert "has the lowest Reachability" in res_clicked.headline

    # 2. "Explain this page" uses visible_summary live screen snapshot
    res_help = orch.run_chat_turn(
        AiChatRequest(
            prompt="Explain this page",
            page_context=PageContextV1(
                page_id="executive_summary",
                route_id="/monthly-presentation/call-center/outbound",
                team_id="Outbound",
                period="2026-09",
                month="September",
                year=2026,
                visible_summary={
                    "headline_score": 87.3,
                    "score_basis": "Team KPI Average",
                    "headcount": 6,
                    "below_90_count": 5,
                    "top_gap_kpi": "Reachability",
                    "top_gap_actual": "53.8%",
                    "top_gap_target": "75.0%",
                },
            ),
        )
    )
    assert res_help.outcome == "answer"
    assert "87.3%" in res_help.headline
    assert "5 of 6" in res_help.headline
    bullets_str = " ".join(res_help.narrative_bullets or [])
    assert "Reachability" in bullets_str
    assert "53.8%" in bullets_str


# ---------------------------------------------------------------------------
# Pillar 4: Pooled Call Center KPI Parity in execute_kpi_diagnosis_and_trends
# ---------------------------------------------------------------------------

def test_pillar4_outbound_pooled_booking_rate_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pooled all-branch Booking Rate for Outbound must equal total_bookings / total_calls_handled
    (317 / 1000 = 31.7% -> 100.0% ach vs 30.0% target), NOT unweighted agent mean (38.6%)."""
    db = _build_in_memory_db()
    # Agent A: 100 bookings / 200 handled = 50.0%
    agent_a = _make_outbound_record(
        emp_id="EMP01",
        name="Agent Alpha",
        score=95.0,
        booking_actual=0.50,
        booking_target=0.30,
        calls_handled=200,
        bookings_dubai=100,
        attended_dubai=70,
    )
    # Agent B: 217 bookings / 800 handled = 27.125%
    agent_b = _make_outbound_record(
        emp_id="EMP02",
        name="Agent Beta",
        score=85.0,
        booking_actual=0.27125,
        booking_target=0.30,
        calls_handled=800,
        bookings_dubai=217,
        attended_dubai=130,
    )
    _patch_records(monkeypatch, [agent_a, agent_b])
    ai_evidence_cache.clear()

    gm_scope = {
        "role": "General Manager",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "has_unrestricted_team_access": True,
    }
    ctx = ToolExecutionContext(
        db=db,
        scope=gm_scope,
        session_state=SessionFilterContext(
            team="Outbound",
            performance_level="Employee",
            month="September",
            year=2026,
        ),
    )
    executor = DeterministicToolRegistry(ctx)
    diag = executor.execute_kpi_diagnosis_and_trends(
        team="Outbound",
        month="September",
        year=2026,
        performance_level="Employee",
    )

    booking_ev = next(
        (ev for ev in diag.typed_evidence if "booking" in str(ev.display_name or "").casefold()),
        None,
    )
    assert booking_ev is not None
    # Pooled: (100 + 217) / (200 + 800) = 317 / 1000 = 31.7% (NOT unweighted mean 38.6%)
    assert booking_ev.actual == pytest.approx(31.7, abs=0.1)
    assert booking_ev.achievement_percent == pytest.approx(100.0, abs=0.1)


# ---------------------------------------------------------------------------
# Reply Quality: Employee Corrective Action Lookup & Overall Score Phrasing
# ---------------------------------------------------------------------------

def test_employee_corrective_action_lookup_saved_and_unsaved(monkeypatch: pytest.MonkeyPatch) -> None:
    """Asking 'what corrective action we did for ammar yasser ?' must check saved corrective actions
    for Ammar (not return his overall score as 'falling short of 100.0%'), clearly report when none
    are saved yet alongside his KPI drag, and list saved actions when present."""
    from models.models import Action, Employee, Team

    db = _build_in_memory_db()
    team_row = Team(
        name="Outbound",
        db_name="Outbound",
        display_name="Outbound",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    db.add(team_row)
    db.flush()
    ammar_emp = Employee(
        employee_id="SGHD70301",
        name="Ammar Yasser sayed Ghareb",
        team_id=team_row.id,
        region="EGY",
        performance_level="Employee",
        is_active=True,
    )
    rawan_emp = Employee(
        employee_id="SGHD70101",
        name="Rawan Mohamed Salah Elnajjar",
        team_id=team_row.id,
        region="EGY",
        performance_level="Employee",
        is_active=True,
    )
    db.add_all([ammar_emp, rawan_emp])
    db.flush()

    # Rawan has a saved corrective action; Ammar does NOT
    db.add(
        Action(
            employee_id=rawan_emp.id,
            team_id=team_row.id,
            month="October",
            year=2026,
            action_type="Coaching",
            action_text="Address Reachability below target and check disconnected numbers.",
            status="Open",
        )
    )
    db.commit()

    ammar_rec = _make_outbound_record(
        emp_id="SGHD70301",
        name="Ammar Yasser sayed Ghareb",
        score=69.17,
        booking_actual=0.145,
        reachability_actual=0.472,
        month="October",
        year=2026,
    )
    rawan_rec = _make_outbound_record(
        emp_id="SGHD70101",
        name="Rawan Mohamed Salah Elnajjar",
        score=74.0,
        booking_actual=0.25,
        reachability_actual=0.541,
        month="October",
        year=2026,
    )
    _patch_records(monkeypatch, [ammar_rec, rawan_rec])
    ai_evidence_cache.clear()

    gm_scope = {
        "role": "General Manager",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "has_unrestricted_team_access": True,
    }
    orch = PmsAiOrchestrator(db, gm_scope)

    page_ctx = PageContextV1(
        page_id="executive_summary",
        route_id="/monthly-presentation/call-center/outbound",
        team_id="Outbound",
        period="2026-10",
        month="October",
        year=2026,
    )

    # 1. Ammar (0 saved actions) -> explicitly states no saved corrective action yet + KPI context
    res_ammar = orch.run_chat_turn(
        AiChatRequest(
            prompt="what corrective action we did for ammar yasser ?",
            page_context=page_ctx,
            session_state=SessionFilterContext(team="Outbound", performance_level="Employee", month="October", year=2026),
        )
    )
    assert res_ammar.outcome == "answer"
    assert "No saved corrective action" in res_ammar.headline
    assert "Ammar Yasser sayed Ghareb" in res_ammar.headline
    assert "100.0%" not in res_ammar.headline
    bullets_ammar = " ".join(res_ammar.narrative_bullets or [])
    assert "69.2%" in bullets_ammar
    assert "Booking Rate" in bullets_ammar

    # 2. Rawan (1 saved action) -> reports her saved action directly
    res_rawan = orch.run_chat_turn(
        AiChatRequest(
            prompt="what corrective action we did for rawan ?",
            page_context=page_ctx,
            session_state=SessionFilterContext(team="Outbound", performance_level="Employee", month="October", year=2026),
        )
    )
    assert res_rawan.outcome == "answer"
    assert "1 saved corrective action" in res_rawan.headline
    assert "Rawan Mohamed Salah Elnajjar" in res_rawan.headline
    bullets_rawan = " ".join(res_rawan.narrative_bullets or [])
    assert "Reachability" in bullets_rawan


def test_model_led_overall_score_avoids_100pct_target_and_schema_jargon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model-led synthesis for an employee Overall Score must not say 'falling short of 100.0%',
    must strip leaked '(value)' / '(target)' tags, and must drop bullets that parrot the headline."""
    from services.ai import orchestrator as orch_mod
    from services.ai import provider_engine as eng_mod

    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_MODEL_LED_ALL_ROLES_ENABLED", "true")

    db = _build_in_memory_db()
    ammar_rec = _make_outbound_record(
        emp_id="SGHD70301",
        name="Ammar Yasser sayed Ghareb",
        score=69.17,
        booking_actual=0.145,
        reachability_actual=0.472,
        month="October",
        year=2026,
    )
    _patch_records(monkeypatch, [ammar_rec])
    ai_evidence_cache.clear()

    call_idx = {"n": 0}
    captured_synth_prompts: list[str] = []

    class _FakeEngine:
        def generate(self, req):
            call_idx["n"] += 1
            if req.purpose == "model_led_router":
                return ProviderResponse(
                    provider="nvidia",
                    model="nvidia/test",
                    content=json.dumps(
                        {
                            "response_type": "tool_call",
                            "tool_name": "read_employee_metric",
                            "tool_arguments": {
                                "employee_name": "Ammar Yasser sayed Ghareb",
                                "metric_id": "overall_score",
                                "team": "Outbound",
                                "period": "2026-10",
                            },
                        }
                    ),
                    outcome="success",
                )
            captured_synth_prompts.append(req.messages[0].content + "\n" + req.messages[1].content)
            # Simulate a sloppy LLM that echoes (value) and parrots the headline in bullet 1
            return ProviderResponse(
                provider="nvidia",
                model="nvidia/test",
                content=json.dumps(
                    {
                        "headline": "Ammar Yasser sayed Ghareb scored 69.2% (value) in October 2026.",
                        "narrative_bullets": [
                            "Ammar Yasser sayed Ghareb scored 69.2% (value) in October 2026.",
                            "Key KPI drags: Booking Rate at 14.5% vs 30.0% target.",
                        ],
                    }
                ),
                outcome="success",
            )

    monkeypatch.setattr(orch_mod, "get_unified_provider_engine", lambda: _FakeEngine())
    monkeypatch.setattr(eng_mod, "get_unified_provider_engine", lambda: _FakeEngine())

    gm_scope = {
        "role": "General Manager",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "has_unrestricted_team_access": True,
    }
    res = PmsAiOrchestrator(db, gm_scope).run_chat_turn(
        AiChatRequest(
            prompt="How did Ammar Yasser score in October 2026?",
            session_state=SessionFilterContext(team="Outbound", performance_level="Employee", month="October", year=2026),
        )
    )
    assert res.outcome == "answer"
    assert "69.2%" in res.headline
    assert "(value)" not in res.headline
    assert "100.0%" not in res.headline
    assert "falling short" not in res.headline.casefold()
    # Parroted bullet must be dropped; real KPI drag bullet kept
    assert all("(value)" not in b and "(target)" not in b for b in res.narrative_bullets)
    assert len(res.narrative_bullets) <= 1
    assert captured_synth_prompts and "falling short of the target of 100.0" not in captured_synth_prompts[0]
