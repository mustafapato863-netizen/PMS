"""Phase 4 & Phase 5 verification tests:
- Phase 4: Scoped model-led evidence caching (warm hit, cross-user RBAC isolation, data/config invalidation)
  and idempotent completed-turn replay with ZERO repeated provider calls.
- Phase 5: Admin-approved de-identified guidance is supplied to the active model-led planner prompt,
  improves an unseen rephrase (computing fresh PMS scores), preserves contrasting intent, and is
  removed immediately upon deactivation/rollback.
"""
from __future__ import annotations

import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.ai_schemas import AiApprovePatternRequest, AiChatRequest, SessionFilterContext
from models.schemas import EvaluationData, PerformanceRecord
from services.ai.approved_patterns import ApprovedPatternMatcher
from services.ai.catalog import ai_evidence_cache
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.tool_registry import DeterministicToolRegistry
from services.cache_invalidation_service import CacheInvalidationService
from services.dashboard_record_service import DashboardRecordService
from services.database_record_source import DatabaseRecordSource
from tests.ai_provider_fakes import install_scripted_provider, ok_response, tool_response


def _rec(emp_id: str, name: str, team: str, region: str, score: float, month: str = "September") -> PerformanceRecord:
    return PerformanceRecord(
        id=f"{team}_{emp_id}_2026_{month[:3]}",
        employee_id=emp_id,
        employee_name=name,
        team=team,
        position="Agent",
        region=region,
        branch="dubai",
        month=month,
        year=2026,
        performance_level="Employee",
        status="On Track" if score >= 80 else "Below Target",
        evaluation=EvaluationData(score=score, grade="A" if score >= 90 else "B"),
        kpi_values=[
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": score, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )


def _db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    return sessionmaker(bind=eng)()


def _patch_records(monkeypatch, records: list[PerformanceRecord]) -> None:
    monkeypatch.setattr(DatabaseRecordSource, "get_all", lambda *a, **kw: list(records))
    monkeypatch.setattr(DashboardRecordService, "list_analysis_records", lambda *a, **kw: list(records))
    monkeypatch.setattr(DashboardRecordService, "list_record_index", lambda *a, **kw: None)


def _synth_json(headline: str, bullets: list[str] | None = None):
    return ok_response(
        json.dumps({"headline": headline, "narrative_bullets": bullets or []}),
        provider="nvidia",
        model="nvidia/test-alternate-model",
    )


def test_phase4_model_led_scoped_evidence_cache_invalidation_and_idempotent_replay(monkeypatch):
    records = [
        _rec("E-1", "Nour Leader", "Inbound", "EGY", 96.0),
        _rec("E-2", "Hossam Two", "Outbound", "EGY", 88.0),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_TURN_DEADLINE_SECONDS", "5")

    tool_exec_count = {"n": 0}
    orig_exec = DeterministicToolRegistry.execute_model_led_tool

    def counting_exec(self, *args, **kwargs):
        tool_exec_count["n"] += 1
        return orig_exec(self, *args, **kwargs)

    monkeypatch.setattr(DeterministicToolRegistry, "execute_model_led_tool", counting_exec)

    calls = install_scripted_provider(
        monkeypatch,
        [
            # Turn 1 (Admin A, cold): planner + synthesis
            tool_response("query_rankings", entity="department", region="EGY", period="2026-09", limit=1),
            _synth_json("Call Center led Egypt in September 2026 at 92.0%."),
            # Turn 2 (Admin A, warm same plan): planner + synthesis -> evidence cache HIT!
            tool_response("query_rankings", entity="department", region="EGY", period="2026-09", limit=1),
            _synth_json("Call Center led Egypt in September 2026 at 92.0%."),
            # Turn 3 (Admin A, after data version invalidation): cache MISS!
            tool_response("query_rankings", entity="department", region="EGY", period="2026-09", limit=1),
            _synth_json("Call Center led Egypt in September 2026 at 92.0%."),
            # Turn 4 (Different scope: restricted Admin B): cache MISS (no cross-scope cache hit)!
            tool_response("query_rankings", entity="department", region="EGY", period="2026-09", limit=1),
            _synth_json("Call Center led Egypt in September 2026 at 96.0%."),
        ],
    )

    db = _db()
    try:
        scope_a = {"role": "Admin", "user_id": "admin-cache-a", "has_unrestricted_team_access": True}
        orch_a = PmsAiOrchestrator(db, scope_a)

        # 1. Cold turn with client_request_id -> 1 DB tool exec, 2 provider calls
        r1 = orch_a.run_chat_turn(
            AiChatRequest(
                prompt="Which department led Egypt in September 2026?",
                session_state=SessionFilterContext(month="September", year=2026),
                client_request_id="req-idem-001",
            )
        )
        assert r1.outcome == "answer"
        assert tool_exec_count["n"] == 1
        assert len(calls) == 2
        assert [call["purpose"] for call in calls] == ["model_led_router", "model_led_synthesis"]
        assert 0 < calls[1]["timeout_seconds"] <= calls[0]["timeout_seconds"] <= 5

        # 2. Idempotent retry of the exact completed turn -> ZERO additional provider calls & ZERO tool reads!
        r1_replay = orch_a.run_chat_turn(
            AiChatRequest(
                conversation_id=r1.conversation_id,
                prompt="Which department led Egypt in September 2026?",
                session_state=SessionFilterContext(month="September", year=2026),
                client_request_id="req-idem-001",
            )
        )
        assert r1_replay.headline == r1.headline
        assert len(calls) == 2  # NO duplicate provider calls on replay!
        assert tool_exec_count["n"] == 1

        # 3. Fresh turn with same scope & normalized plan -> warm evidence cache HIT (tool_exec_count stays 1)
        r2 = orch_a.run_chat_turn(
            AiChatRequest(
                prompt="Which department had the top average score in Egypt in September 2026?",
                session_state=SessionFilterContext(month="September", year=2026),
            )
        )
        assert r2.outcome == "answer"
        assert tool_exec_count["n"] == 1  # Evidence cache HIT!

        # 4. Data invalidation -> cache MISS (tool_exec_count increments to 2)
        CacheInvalidationService.bump_data_version()
        r3 = orch_a.run_chat_turn(
            AiChatRequest(
                prompt="Which department led Egypt in September 2026?",
                session_state=SessionFilterContext(month="September", year=2026),
            )
        )
        assert r3.outcome == "answer"
        assert tool_exec_count["n"] == 2

        # 5. Different RBAC scope (Manager restricted to Inbound only -> score=96.0% instead of 92.0%)
        #    MUST NOT hit Admin A's cached evidence!
        scope_restricted = {
            "role": "Manager",
            "user_id": "mgr-cache-b",
            "has_unrestricted_team_access": False,
            "accessible_teams": ["Inbound"],
            "accessible_regions": ["EGY"],
        }
        # Confirm ai_evidence_cache hits for Admin A (matching region/level) and returns None (MISS)
        # for a different RBAC scope OR a different region (cross-country isolation).
        probe_sig = {
            "stage": "model_led_tool",
            "tool_name": r3.tool_calls[0].tool_name,
            "tool_arguments": r3.tool_calls[0].arguments,
            "month": "September",
            "year": 2026,
            "region": "EGY",
            "team": "",
            "function": None,
            "position": None,
            "performance_level": "Employee",
            "branch": None,
        }
        assert ai_evidence_cache.get(db=db, scope=scope_a, query_signature=probe_sig) is not None
        assert ai_evidence_cache.get(db=db, scope=scope_a, query_signature={**probe_sig, "region": "UAE"}) is None
        assert ai_evidence_cache.get(db=db, scope=scope_restricted, query_signature=probe_sig) is None
        orch_b = PmsAiOrchestrator(db, scope_restricted)
        r4 = orch_b.run_chat_turn(
            AiChatRequest(
                prompt="Which department had the highest score in Egypt in September 2026?",
                session_state=SessionFilterContext(month="September", year=2026),
                provider_override="deterministic",
            )
        )
        assert r4.outcome == "answer"
        assert "96.0%" in r4.headline
    finally:
        db.close()


def test_phase5_approved_guidance_reaches_active_model_led_planner_and_rolls_back_on_deactivate(monkeypatch):
    records = [
        _rec("E-1", "Nour Star", "Inbound", "EGY", 97.0),
        _rec("E-2", "Tariq Mid", "Inbound", "EGY", 83.0),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")

    db = _db()
    try:
        admin_scope = {"role": "Admin", "user_id": "admin-p5", "has_unrestricted_team_access": True}
        orch = PmsAiOrchestrator(db, admin_scope)

        # 1. Create a flagged trace on an unfamiliar phrase
        base_turn = orch.run_chat_turn(
            AiChatRequest(
                prompt="Show Inbound golden trophy in September 2026",
                session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
                provider_override="deterministic",
            )
        )
        assert base_turn.trace_id
        from services.ai.trace_logger import TrainingTraceLogger
        TrainingTraceLogger(db).record_feedback(
            trace_id=base_turn.trace_id,
            rating="down",
            reason="Misinterpreted golden trophy",
        )

        # Mock only the provider. The real planner, evidence and governance run in each arm.
        rephrase = "Who earned the Inbound honor medal in September 2026?"
        contrast = "Who had the lowest score in Inbound in September 2026?"

        def scripted_model(call):
            messages = "\n".join(message["content"] for message in call["messages"])
            if call["purpose"] == "model_led_router":
                if "lowest score in Inbound" in messages:
                    return tool_response(
                        "query_rankings", entity="employee", team="Inbound", region="EGY",
                        period="2026-09", limit=1, sort_order="asc",
                    )
                if "Admin-approved interpretation guidance" in messages and "golden trophy" in messages.casefold():
                    return tool_response(
                        "query_rankings", entity="employee", team="Inbound", region="EGY",
                        period="2026-09", limit=1,
                    )
                return {
                    "response_type": "clarification",
                    "clarification_prompt": "What does honor medal mean for this team?",
                }
            if "lowest score in Inbound" in messages:
                return _synth_json("Tariq Mid had the lowest score in Inbound at 83.00%.")
            return _synth_json("Nour Star achieved the highest score in Inbound at 97.00%.")

        calls = install_scripted_provider(monkeypatch, scripted_model)

        def ask(prompt):
            response = orch.run_chat_turn(
                AiChatRequest(
                    prompt=prompt,
                    session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
                    provider_override="auto",
                )
            )
            planner_call = next(call for call in reversed(calls) if call["purpose"] == "model_led_router")
            return response, "\n".join(message["content"] for message in planner_call["messages"])

        before, before_prompt = ask(rephrase)
        before_contrast, _ = ask(contrast)
        assert before.outcome == "clarification"
        assert "golden trophy" not in before_prompt.casefold()
        assert "Tariq Mid" in before_contrast.headline

        matcher = ApprovedPatternMatcher(db)
        pat_item, _ = matcher.approve_pattern_from_trace(
            trace_id=base_turn.trace_id,
            payload=AiApprovePatternRequest(
                corrected_pattern_prompt="Show Inbound golden trophy",
                intent="ranking",
                operation_kind="ranking",
                tool_choice="query_rankings",
                metric_hint="overall_score",
                review_notes="Golden trophy means highest scoring employee in the team.",
                verified_against_pms=True,
            ),
            approver_user_id="admin-p5",
            caller_role="Admin",
        )
        db.commit()

        active, active_prompt = ask(rephrase)
        active_contrast, _ = ask(contrast)
        assert active.outcome == "answer"
        assert "Nour Star" in active.headline
        assert "97.00%" in active.headline
        assert any(call.tool_name == "query_rankings" and call.records_evaluated > 0 for call in active.tool_calls)
        assert "Admin-approved interpretation guidance" in active_prompt
        assert "golden trophy" in active_prompt.casefold()
        assert "Nour Star" not in active_prompt
        assert "97.0" not in active_prompt
        assert before_contrast.headline == active_contrast.headline

        assert matcher.deactivate_pattern(
            pattern_id=pat_item.id,
            actor_user_id="admin-p5",
            caller_role="Admin",
        )
        db.commit()

        revoked, revoked_prompt = ask(rephrase)
        revoked_contrast, _ = ask(contrast)
        assert revoked.outcome == before.outcome
        assert revoked.headline == before.headline
        assert "golden trophy" not in revoked_prompt.casefold()
        assert revoked_contrast.headline == before_contrast.headline
    finally:
        db.close()
