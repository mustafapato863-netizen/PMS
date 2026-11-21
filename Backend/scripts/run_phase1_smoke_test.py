#!/usr/bin/env python3
"""Phase 1 Bounded Provider Smoke Test Runner.

Executes a 4-turn synthetic conversation sequence:
1. Turn 1: Greeting ("Hi, how can you help?")
2. Turn 2: Single-employee current_value ("What was Sara Mahmoud's score in September 2026?")
3. Turn 3: Period change ("And in August?")
4. Turn 4: Trend / metric change ("What was her score pattern across the available months?")

Runs across three strictly isolated execution modes:
- Run A: Deterministic Run (all cloud routing/synthesis disabled)
- Run B: Mocked Provider Run (faked provider responses)
- Run C: Live Provider Run (actual live Cloudflare Workers AI / Gemini provider)

Uses strictly in-memory SQLite and synthetic employee records. Zero production data or secrets touched.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# Add Backend and tests to sys.path
backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir / "tests"))

from config.environment import load_project_environment
load_project_environment(str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.ai_schemas import AiChatRequest, SessionFilterContext
from models.models import ProductSetting
from services.ai.catalog import ai_evidence_cache
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.provider_engine import (
    UnifiedProviderEngine,
    get_unified_provider_engine,
    ProviderRequest,
    ProviderResponse,
    TokenUsage,
)
from services.auth_service import AuthenticationService
from tests.test_ai_workspace import _build_in_memory_db, _make_call_center_record, _patch_records
from tests.test_ai_response_quality import _make_rich_records


TURNS = [
    ("Turn 1 (Greeting)", "Hi, how can you help?"),
    ("Turn 2 (Single-employee Current Value)", "What was Sara Mahmoud's score in September 2026?"),
    ("Turn 3 (Period Change Follow-up)", "And in August?"),
    ("Turn 4 (Trend / Metric Change Follow-up)", "What was her score pattern across the available months?"),
]


class MonkeyPatchLite:
    def __init__(self):
        self._undo = []

    def setattr(self, target: str, value: Any):
        parts = target.split(".")
        mod = None
        remaining = []
        for i in range(len(parts), 0, -1):
            mod_candidate = ".".join(parts[:i])
            try:
                __import__(mod_candidate)
                mod = sys.modules[mod_candidate]
                remaining = parts[i:]
                break
            except (ModuleNotFoundError, KeyError):
                continue
        if mod is None:
            raise ValueError(f"Could not import module for {target}")
        obj = mod
        for part in remaining[:-1]:
            obj = getattr(obj, part)
        attr_name = remaining[-1]
        old_val = getattr(obj, attr_name)
        setattr(obj, attr_name, value)
        self._undo.append((obj, attr_name, old_val))

    def setenv(self, key: str, value: str):
        old_val = os.environ.get(key)
        os.environ[key] = value
        self._undo.append(("ENV", key, old_val))

    def undo(self):
        for item in reversed(self._undo):
            if item[0] == "ENV":
                _, key, old_val = item
                if old_val is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old_val
            else:
                mod, attr_name, old_val = item
                setattr(mod, attr_name, old_val)
        self._undo.clear()


def run_conversation_sequence(run_name: str) -> list[dict[str, Any]]:
    results = []
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        AuthenticationService.create_user(db, "smoke_admin", "admin@smoke.invalid", "AdminSecret123!", "Admin")
        db.add(ProductSetting(key="ai_enabled", enabled=True))
        db.commit()

    db = Session()
    mp = MonkeyPatchLite()
    _patch_records(mp, _make_rich_records())
    ai_evidence_cache.clear()

    try:
        orch = PmsAiOrchestrator(
            db,
            {"role": "Admin", "user_id": "u-smoke-test", "has_unrestricted_team_access": True},
        )
        conv_id = None
        ctx_ver = None
        session_state = SessionFilterContext()

        for turn_label, prompt in TURNS:
            t_start = time.perf_counter()
            req = AiChatRequest(
                prompt=prompt,
                conversation_id=conv_id,
                context_version=ctx_ver,
                session_state=session_state,
            )
            resp = orch.run_chat_turn(req)
            elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 2)

            conv_id = resp.conversation_id
            ctx_ver = resp.context_version
            session_state = resp.resolved_session_state

            turn_info = {
                "turn": turn_label,
                "prompt": prompt,
                "outcome": resp.outcome,
                "headline": resp.headline,
                "bullets": resp.narrative_bullets,
                "detail_level": resp.answer_detail,
                "provider_used": resp.provider_used,
                "model_used": resp.model_used,
                "route_used": resp.provider_usage.route_used if resp.provider_usage else "unknown",
                "provider_calls": resp.provider_usage.provider_calls if resp.provider_usage else 0,
                "provider_ms": resp.timings.provider_ms if resp.timings else 0.0,
                "input_tokens": resp.provider_usage.input_tokens if resp.provider_usage else 0,
                "output_tokens": resp.provider_usage.output_tokens if resp.provider_usage else 0,
                "estimated_cost_usd": resp.provider_usage.estimated_cost_usd if resp.provider_usage else 0.0,
                "fallback_outcome": resp.provider_usage.fallback_outcome if resp.provider_usage else "none",
                "total_turn_ms": elapsed_ms,
                "structured_intent": resp.structured_query.intent if resp.structured_query else None,
                "structured_employee": resp.structured_query.employee_name if resp.structured_query else None,
                "structured_metric": resp.structured_query.metric if resp.structured_query else None,
            }
            results.append(turn_info)

    finally:
        mp.undo()
        db.close()

    return results


def main():
    print("=================================================================")
    print("PHASE 1 BOUNDED PROVIDER SMOKE TEST (SYNTHETIC DATA & IN-MEMORY)")
    print("=================================================================\n")

    # 1. RUN A: DETERMINISTIC RUN
    print("--> Executing Run A: Deterministic Run (Model features disabled)...")
    os.environ["PMS_AI_INTENT_ENABLED"] = "false"
    os.environ["PMS_AI_SYNTHESIS_ENABLED"] = "false"
    os.environ["PMS_AI_NVIDIA_ROUTING_ENABLED"] = "false"
    os.environ["PMS_AI_LOCAL_ROUTER_ENABLED"] = "false"
    os.environ["PMS_AI_CONVERSATION_STATE_ENABLED"] = "true"
    run_a_results = run_conversation_sequence("Run A: Deterministic")

    # 2. RUN B: MOCKED PROVIDER RUN
    print("--> Executing Run B: Mocked Provider Run (Synthetic double)...")
    os.environ["PMS_AI_INTENT_ENABLED"] = "true"
    os.environ["PMS_AI_SYNTHESIS_ENABLED"] = "true"

    # Install fake adapter on unified engine
    engine = get_unified_provider_engine(reload=True)
    real_generate = engine.generate

    def fake_generate(request: ProviderRequest) -> ProviderResponse:
        # Mocked provider response
        if request.purpose == "intent":
            return ProviderResponse(
                content=json.dumps({"intent": "performance_query"}),
                provider="mock_provider",
                model="mock-v1",
                outcome="success",
                latency_ms=12.5,
                usage=TokenUsage(prompt_tokens=40, completion_tokens=8, total_tokens=48),
            )
        return ProviderResponse(
            content=json.dumps({"answer": "Sara Mahmoud scored 94.0% in September 2026."}),
            provider="mock_provider",
            model="mock-v1",
            outcome="success",
            latency_ms=25.0,
            usage=TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
        )

    engine.generate = fake_generate
    run_b_results = run_conversation_sequence("Run B: Mocked Provider")
    engine.generate = real_generate

    # 3. RUN C: ACTUAL LIVE PROVIDER RUN
    print("--> Executing Run C: Live Provider Run (Actual Cloudflare / Gemini API)...")
    os.environ["PMS_AI_INTENT_ENABLED"] = "true"
    os.environ["PMS_AI_SYNTHESIS_ENABLED"] = "true"
    os.environ["PMS_AI_LOCAL_ROUTER_ENABLED"] = "true"
    # Ensure fresh engine with real credentials
    get_unified_provider_engine(reload=True)
    run_c_results = run_conversation_sequence("Run C: Live Provider")

    # Print summary of all runs
    summary_data = {
        "run_a_deterministic": run_a_results,
        "run_b_mocked": run_b_results,
        "run_c_live": run_c_results,
    }

    out_file = Path("docs/plans/pms-ai-model-led/smoke_test_results.json")
    out_file.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")
    print(f"\n[OK] Smoke test completed. Results written to {out_file}\n")

    for run_key, res_list in summary_data.items():
        print(f"--- {run_key.upper()} ---")
        for turn in res_list:
            print(f"  {turn['turn']}:")
            print(f"    Headline: {turn['headline']}")
            print(f"    Outcome: {turn['outcome']} | Intent: {turn['structured_intent']}")
            print(f"    Provider Used: {turn['provider_used']} | Model: {turn['model_used']}")
            print(f"    Provider Calls: {turn['provider_calls']} | Total Turn Latency: {turn['total_turn_ms']} ms")
            print(f"    Fallback: {turn['fallback_outcome']}")
        print()

if __name__ == "__main__":
    main()
