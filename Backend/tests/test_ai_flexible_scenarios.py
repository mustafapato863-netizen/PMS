"""Multi-scenario tests for flexible role/position understanding, ordinal follow-ups,
cross-department pivots, natural trend phrasing, and adaptive NVIDIA thinking effort.
"""
from __future__ import annotations

import io
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.ai_schemas import AiChatRequest, SessionFilterContext
from models.schemas import CallsData, EvaluationData, GeoData, PerformanceRecord
from services.ai.catalog import ai_evidence_cache
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.provider_engine import (
    DEFAULT_NVIDIA_MODEL,
    NvidiaProviderAdapter,
    ProviderMessage,
    ProviderRequest,
    UnifiedProviderConfig,
)
from services.dashboard_record_service import DashboardRecordService
from services.database_record_source import DatabaseRecordSource


def _in_memory_db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    return sessionmaker(bind=eng)()


def _rec(
    emp_id: str,
    name: str,
    team: str,
    position: str,
    month: str,
    score: float,
    *,
    region: str = "EGY",
) -> PerformanceRecord:
    return PerformanceRecord(
        id=f"{emp_id}-{month}-2026",
        employee_id=emp_id,
        employee_name=name,
        team=team,
        region=region,
        position=position,
        performance_level="Employee",
        month=month,
        year=2026,
        evaluation=EvaluationData(
            score=score,
            grade="A" if score >= 95 else ("B" if score >= 85 else "C"),
            status="Exceeds" if score >= 95 else "Meets",
        ),
        calls=CallsData(),
        geo=GeoData(),
        raw_data={"Position": position},
    )


def _multi_department_records() -> list[PerformanceRecord]:
    return [
        # Human Resources (3 roles x 3 months)
        _rec("70207", "Mohamed Diaa", "Human Resources", "Assessment Center Lead", "August", 99.3),
        _rec("70207", "Mohamed Diaa", "Human Resources", "Assessment Center Lead", "September", 100.0),
        _rec("70207", "Mohamed Diaa", "Human Resources", "Assessment Center Lead", "October", 97.6),
        _rec("70208", "Sara Ahmed", "Human Resources", "HR Operation Supervisor", "August", 91.0),
        _rec("70208", "Sara Ahmed", "Human Resources", "HR Operation Supervisor", "September", 93.2),
        _rec("70208", "Sara Ahmed", "Human Resources", "HR Operation Supervisor", "October", 95.4),
        _rec("70209", "Nour Hassan", "Human Resources", "HR Specialist", "August", 93.5),
        _rec("70209", "Nour Hassan", "Human Resources", "HR Specialist", "September", 93.6),
        _rec("70209", "Nour Hassan", "Human Resources", "HR Specialist", "October", 91.7),
        # Marketing (3 roles x 3 months)
        _rec("70301", "Lina Adel", "Marketing", "Media Buyer", "August", 86.0),
        _rec("70301", "Lina Adel", "Marketing", "Media Buyer", "September", 89.5),
        _rec("70301", "Lina Adel", "Marketing", "Media Buyer", "October", 94.0),
        _rec("70302", "Omar Sami", "Marketing", "Graphic Designer", "August", 88.0),
        _rec("70302", "Omar Sami", "Marketing", "Graphic Designer", "September", 85.0),
        _rec("70302", "Omar Sami", "Marketing", "Graphic Designer", "October", 82.5),
        _rec("70303", "Mona Tarek", "Marketing", "Content Writer", "August", 90.0),
        _rec("70303", "Mona Tarek", "Marketing", "Content Writer", "September", 91.0),
        _rec("70303", "Mona Tarek", "Marketing", "Content Writer", "October", 92.0),
        # Finance (2 roles x 3 months)
        _rec("70401", "Youssef Nabil", "Finance", "Finance Controller", "August", 92.0),
        _rec("70401", "Youssef Nabil", "Finance", "Finance Controller", "September", 94.0),
        _rec("70401", "Youssef Nabil", "Finance", "Finance Controller", "October", 96.2),
        _rec("70402", "Heba Fathy", "Finance", "General Accountant", "August", 84.0),
        _rec("70402", "Heba Fathy", "Finance", "General Accountant", "September", 87.0),
        _rec("70402", "Heba Fathy", "Finance", "General Accountant", "October", 89.4),
    ]


def _patch_records(monkeypatch, records: list[PerformanceRecord]) -> None:
    monkeypatch.setattr(DatabaseRecordSource, "get_all", lambda *a, **kw: list(records))
    monkeypatch.setattr(DashboardRecordService, "list_analysis_records", lambda *a, **kw: list(records))
    monkeypatch.setattr(DashboardRecordService, "list_record_index", lambda *a, **kw: None)


def test_flexible_position_plurals_abbreviations_and_natural_trend_phrasing(monkeypatch):
    """Natural phrasings, plurals ('HR Operations Supervisor', 'Media Buyers'), abbreviations ('HR Ops Supervisor'), and partial role names ('assessment center') all resolve cleanly."""
    _patch_records(monkeypatch, _multi_department_records())
    ai_evidence_cache.clear()
    db = _in_memory_db()
    try:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "flex-1", "has_unrestricted_team_access": True})

        # Plural + natural trajectory phrasing
        r1 = orch.run_chat_turn(AiChatRequest(
            prompt="How has HR Operations Supervisor been moving month by month?",
            session_state=SessionFilterContext(),
            provider_override="deterministic",
        ))
        assert r1.outcome == "answer", r1.headline
        assert "HR Operation Supervisor" in r1.headline and "95.4%" in r1.headline, r1.headline

        # Abbreviation ('HR Ops Supervisor') + 'progress'
        r2 = orch.run_chat_turn(AiChatRequest(
            prompt="HR Ops Supervisor progress over recent months",
            session_state=SessionFilterContext(),
            provider_override="deterministic",
        ))
        assert r2.outcome == "answer", r2.headline
        assert "HR Operation Supervisor" in r2.headline and "95.4%" in r2.headline, r2.headline

        # Plural role in Marketing ('Media Buyers')
        r3 = orch.run_chat_turn(AiChatRequest(
            prompt="Media Buyers trend",
            session_state=SessionFilterContext(),
            provider_override="deterministic",
        ))
        assert r3.outcome == "answer", r3.headline
        assert "Media Buyer" in r3.headline and "94.0%" in r3.headline, r3.headline

        # Unique partial match ('assessment center')
        r4 = orch.run_chat_turn(AiChatRequest(
            prompt="assessment center trend",
            session_state=SessionFilterContext(),
            provider_override="deterministic",
        ))
        assert r4.outcome == "answer", r4.headline
        assert "Assessment Center Lead" in r4.headline and "97.6%" in r4.headline, r4.headline
    finally:
        db.close()


def test_ordinal_followups_from_role_ranking_and_cross_department_pivot(monkeypatch):
    """After 'what is the best team in HR', follow-ups like 'show me the second one's trend', '#3 trend', and pivoting to Marketing/Finance work accurately."""
    _patch_records(monkeypatch, _multi_department_records())
    ai_evidence_cache.clear()
    db = _in_memory_db()
    try:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "flex-2", "has_unrestricted_team_access": True})

        # Turn 1: Best role in HR (stores all 3 ranked roles in ranking_results!)
        r1 = orch.run_chat_turn(AiChatRequest(
            prompt="what is the best team in HR",
            session_state=SessionFilterContext(),
            provider_override="deterministic",
        ))
        assert r1.outcome == "answer" and "Assessment Center Lead" in r1.headline
        ranked = r1.resolved_session_state.last_confirmed_query.ranking_results
        assert len(ranked) == 3, [item.name for item in ranked]
        assert ranked[1].name == "HR Operation Supervisor"
        assert ranked[2].name == "HR Specialist"

        # Turn 2: Ordinal follow-up ("show me the second one's trend") -> HR Operation Supervisor (95.4%)
        r2 = orch.run_chat_turn(AiChatRequest(
            prompt="show me the second one's trend",
            conversation_id=r1.conversation_id,
            context_version=r1.context_version,
            session_state=r1.resolved_session_state,
            history=[{"role": "user", "content": "what is the best team in HR"}, {"role": "assistant", "content": r1.headline}],
            provider_override="deterministic",
        ))
        assert r2.outcome == "answer", r2.headline
        assert "HR Operation Supervisor" in r2.headline and "95.4%" in r2.headline, r2.headline

        # Turn 3: Ordinal follow-up continuing the SAME conversation ("lowest one trend") -> HR Specialist (91.7%)
        r3 = orch.run_chat_turn(AiChatRequest(
            prompt="lowest one trend",
            conversation_id=r2.conversation_id,
            context_version=r2.context_version,
            session_state=r2.resolved_session_state,
            history=[
                {"role": "user", "content": "what is the best team in HR"},
                {"role": "assistant", "content": r1.headline},
                {"role": "user", "content": "show me the second one's trend"},
                {"role": "assistant", "content": r2.headline},
            ],
            provider_override="deterministic",
        ))
        assert r3.outcome == "answer", r3.headline
        assert "HR Specialist" in r3.headline and "91.7%" in r3.headline, r3.headline

        # Turn 4: Cross-department pivot ("what is the best team in Marketing" -> "Graphic Designer trend")
        r4 = orch.run_chat_turn(AiChatRequest(
            prompt="what is the best team in Marketing",
            conversation_id=r3.conversation_id,
            context_version=r3.context_version,
            session_state=r3.resolved_session_state,
            provider_override="deterministic",
        ))
        assert r4.outcome == "answer" and "Media Buyer" in r4.headline, r4.headline

        r5 = orch.run_chat_turn(AiChatRequest(
            prompt="Graphic Designer trend",
            conversation_id=r4.conversation_id,
            context_version=r4.context_version,
            session_state=r4.resolved_session_state,
            provider_override="deterministic",
        ))
        assert r5.outcome == "answer", r5.headline
        assert "Graphic Designer" in r5.headline and "82.5%" in r5.headline, r5.headline
        assert "Media Buyer" not in r5.headline

        # Turn 5: Finance role trend
        r6 = orch.run_chat_turn(AiChatRequest(
            prompt="Finance Controller trajectory",
            conversation_id=r5.conversation_id,
            context_version=r5.context_version,
            session_state=r5.resolved_session_state,
            provider_override="deterministic",
        ))
        assert r6.outcome == "answer", r6.headline
        assert "Finance Controller" in r6.headline and "96.2%" in r6.headline, r6.headline
    finally:
        db.close()


def test_nvidia_adaptive_reasoning_effort_gives_investigation_thinking_time(monkeypatch):
    """NVIDIA Nemotron uses 'low' thinking effort on investigation/repair turns and 'none' on fast routine turns by default (and respects explicit env overrides)."""
    monkeypatch.delenv("PMS_AI_NVIDIA_REASONING_EFFORT", raising=False)
    cfg = UnifiedProviderConfig(
        nvidia_enabled=True,
        nvidia_api_key="nvapi-test-adaptive-key",
        nvidia_model=DEFAULT_NVIDIA_MODEL,
        primary_provider="nvidia",
    )

    def _capture(task_role: str) -> str:
        bodies = []
        def transport(http_req, *, timeout):
            bodies.append(json.loads(http_req.data))
            return io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}).encode())
        req = ProviderRequest(
            messages=[ProviderMessage(role="user", content="Analyze complex HR position trend.")],
            purpose="model_led_router",
            task_role=task_role,
            response_format="json",
            max_tokens=None,
        )
        NvidiaProviderAdapter(transport).execute(req, cfg, timeout=18.0, model=DEFAULT_NVIDIA_MODEL)
        return bodies[0]["reasoning_effort"]

    assert _capture("investigation") == "low"
    assert _capture("repair") == "low"
    assert _capture("routine") == "none"

    monkeypatch.setenv("PMS_AI_NVIDIA_REASONING_EFFORT", "high")
    assert _capture("routine") == "high"
    monkeypatch.setenv("PMS_AI_NVIDIA_REASONING_EFFORT", "none")
    assert _capture("investigation") == "none"


def test_position_period_drilldown_runner_up_and_natural_phrasings(monkeypatch):
    """Specific-month role drill-down, #3 / runner-up ordinal follow-ups in Marketing, and natural 3-month progress phrasing in Finance."""
    _patch_records(monkeypatch, _multi_department_records())
    ai_evidence_cache.clear()
    db = _in_memory_db()
    try:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "flex-3", "has_unrestricted_team_access": True})

        # Specific historical month for a position (September = 93.2%, not October 95.4%)
        r_sep = orch.run_chat_turn(AiChatRequest(
            prompt="How did HR Operation Supervisor score in September 2026?",
            session_state=SessionFilterContext(),
            provider_override="deterministic",
        ))
        assert r_sep.outcome == "answer", r_sep.headline
        assert "93.2%" in r_sep.headline or any("93.2%" in b for b in r_sep.narrative_bullets), (r_sep.headline, r_sep.narrative_bullets)
        assert "95.4%" not in r_sep.headline, r_sep.headline

        # Natural 3-month progress phrasing in Finance
        r_fin = orch.run_chat_turn(AiChatRequest(
            prompt="How is Finance Controller progressing over the last 3 months?",
            session_state=SessionFilterContext(),
            provider_override="deterministic",
        ))
        assert r_fin.outcome == "answer", r_fin.headline
        assert "Finance Controller" in r_fin.headline and "96.2%" in r_fin.headline, r_fin.headline

        # Marketing best team -> runner-up trend (Content Writer 92.0%) -> #3 trend (Graphic Designer 82.5%)
        r_mkt = orch.run_chat_turn(AiChatRequest(
            prompt="what is the best team in Marketing",
            session_state=SessionFilterContext(),
            provider_override="deterministic",
        ))
        assert r_mkt.outcome == "answer" and "Media Buyer" in r_mkt.headline, r_mkt.headline

        r_runner = orch.run_chat_turn(AiChatRequest(
            prompt="runner up trend",
            conversation_id=r_mkt.conversation_id,
            context_version=r_mkt.context_version,
            session_state=r_mkt.resolved_session_state,
            provider_override="deterministic",
        ))
        assert r_runner.outcome == "answer", r_runner.headline
        assert "Content Writer" in r_runner.headline and "92.0%" in r_runner.headline, r_runner.headline

        r_third = orch.run_chat_turn(AiChatRequest(
            prompt="show me #3's trend",
            conversation_id=r_runner.conversation_id,
            context_version=r_runner.context_version,
            session_state=r_runner.resolved_session_state,
            provider_override="deterministic",
        ))
        assert r_third.outcome == "answer", r_third.headline
        assert "Graphic Designer" in r_third.headline and "82.5%" in r_third.headline, r_third.headline
    finally:
        db.close()


def test_position_missing_period_is_honest_not_hallucinated(monkeypatch):
    """Asking for a role in an unpublished future month returns an honest unavailable message rather than silently substituting October."""
    _patch_records(monkeypatch, _multi_department_records())
    ai_evidence_cache.clear()
    db = _in_memory_db()
    try:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "flex-4", "has_unrestricted_team_access": True})
        r = orch.run_chat_turn(AiChatRequest(
            prompt="HR Operation Supervisor score in December 2026",
            session_state=SessionFilterContext(),
            provider_override="deterministic",
        ))
        assert "95.4%" not in r.headline, r.headline
        combined = (r.headline + " " + " ".join(r.narrative_bullets)).casefold()
        assert any(tok in combined for tok in ("no ", "unavailable", "not available", "not published", "missing", "december")), combined
    finally:
        db.close()


def test_thinking_and_timeout_budget_defaults(monkeypatch):
    """Provider timeout defaults and config ceilings give models ample thinking time without premature cutoff."""
    from services.ai.config import get_ai_runtime_config

    monkeypatch.delenv("PMS_AI_PROVIDER_TIMEOUT_SECONDS", raising=False)
    cfg = get_ai_runtime_config()
    assert cfg.provider_timeout_seconds >= 18.0
    assert UnifiedProviderConfig().timeout_seconds >= 18.0


def test_position_drivers_and_period_comparison_scenarios(monkeypatch):
    """Asking what is driving a role, why a declining role dropped, or comparing a role across two months stays scoped to that exact role."""
    records = _multi_department_records()
    # Attach realistic KPI details to HR Operation Supervisor and Graphic Designer so drivers are grounded
    for r in records:
        if r.position == "HR Operation Supervisor":
            r.kpi_values = [
                {"kpi_key": "payroll_accuracy", "label": "Payroll Accuracy", "actual": 98.0, "target": 99.0, "achievement": 96.0, "weight": 50.0},
                {"kpi_key": "onboarding_sla", "label": "Onboarding SLA", "actual": 94.0, "target": 95.0, "achievement": 94.8, "weight": 50.0},
            ]
        elif r.position == "Graphic Designer":
            r.kpi_values = [
                {"kpi_key": "design_turnaround", "label": "Design Turnaround", "actual": 78.0, "target": 95.0, "achievement": 80.0, "weight": 60.0},
                {"kpi_key": "brand_compliance", "label": "Brand Compliance", "actual": 86.0, "target": 95.0, "achievement": 86.25, "weight": 40.0},
            ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    db = _in_memory_db()
    try:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "flex-5", "has_unrestricted_team_access": True})

        # Score drivers on a specific role
        r_drv = orch.run_chat_turn(AiChatRequest(
            prompt="What is driving HR Operation Supervisor in October 2026?",
            session_state=SessionFilterContext(),
            provider_override="deterministic",
        ))
        assert r_drv.outcome == "answer", r_drv.headline
        drv_text = (r_drv.headline + " " + " ".join(r_drv.narrative_bullets) + " " + " ".join(r_drv.detail_bullets))
        assert "HR Operation Supervisor" in drv_text or "95.4%" in drv_text or "Onboarding SLA" in drv_text, drv_text
        assert "Assessment Center Lead" not in r_drv.headline, r_drv.headline

        # Why did a declining role drop?
        r_drop = orch.run_chat_turn(AiChatRequest(
            prompt="Why did Graphic Designer drop in October 2026?",
            session_state=SessionFilterContext(),
            provider_override="deterministic",
        ))
        assert r_drop.outcome == "answer", r_drop.headline
        drop_text = (r_drop.headline + " " + " ".join(r_drop.narrative_bullets) + " " + " ".join(r_drop.detail_bullets))
        assert "Graphic Designer" in drop_text or "82.5%" in drop_text or "Design Turnaround" in drop_text, drop_text
        assert "Media Buyer" not in r_drop.headline, r_drop.headline

        # Role-level comparison across two explicit months
        r_cmp = orch.run_chat_turn(AiChatRequest(
            prompt="Compare HR Operation Supervisor in August 2026 and October 2026",
            session_state=SessionFilterContext(),
            provider_override="deterministic",
        ))
        assert r_cmp.outcome == "answer", r_cmp.headline
        cmp_text = r_cmp.headline + " " + " ".join(r_cmp.narrative_bullets)
        assert "95.4%" in cmp_text and ("91.0%" in cmp_text or "August" in cmp_text), cmp_text
    finally:
        db.close()
