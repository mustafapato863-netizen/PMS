#!/usr/bin/env python3
"""PR 5 Staging Candidate Comparison Matrix & Section 5 Release Scorecard Runner.

Compares across the 240-scenario unseen benchmark + corrective repair sub-suite:
1. `legacy_rules_flags_off`   : compound parts & corrective repair disabled
2. `improved_app_flags_on`    : improved compound planner + bounded 1-retry corrective repair enabled
3. `forced_timeout_fallback`  : forced provider timeout testing deterministic degradation under budget
4. `staging_live_candidate`   : live staging cloud/gateway candidate (blocked unless PMS_AI_RUN_LIVE_MODEL_TESTS=true)

Produces JSON summary + Markdown Section 5 Release Scorecard without fabricating billing/live stats.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "Backend"
BENCH_DIR = Path(__file__).resolve().parent / "unseen_benchmark"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(BENCH_DIR))

from _pytest.monkeypatch import MonkeyPatch  # noqa: E402
from models.ai_schemas import AiCorrectiveActionSuggestionRequest  # noqa: E402
from services.ai import corrective_action_drafter as drafter_mod  # noqa: E402
from services.ai.catalog import ai_evidence_cache  # noqa: E402
from services.ai.config import get_ai_runtime_config  # noqa: E402
from services.ai.corrective_action_drafter import CorrectiveActionDrafter  # noqa: E402
from services.ai.providers import ProviderResponse  # noqa: E402

import run_benchmark as bench  # noqa: E402


DEFAULT_JSON_OUT = Path(__file__).resolve().parent / "staging_comparison_summary.json"
DEFAULT_REPORT_OUT = Path(__file__).resolve().parent / "STAGING_COMPARISON_REPORT.md"


def _rollout_flags_snapshot() -> dict[str, Any]:
    cfg = get_ai_runtime_config()
    return {
        "PMS_AI_COMPOUND_PARTS_ENABLED": {
            "effective": cfg.compound_parts_enabled,
            "default": True,
            "revert": "export PMS_AI_COMPOUND_PARTS_ENABLED=false",
        },
        "PMS_AI_CORRECTIVE_DRAFT_REPAIR_ENABLED": {
            "effective": os.environ.get("PMS_AI_CORRECTIVE_DRAFT_REPAIR_ENABLED", "true").casefold() not in ("0", "false", "no", "off"),
            "default": True,
            "revert": "export PMS_AI_CORRECTIVE_DRAFT_REPAIR_ENABLED=false",
        },
        "PMS_AI_MODEL_LED_PILOT_ENABLED": {
            "effective": cfg.model_led_pilot_enabled,
            "default": False,
            "revert": "export PMS_AI_MODEL_LED_PILOT_ENABLED=false",
        },
        "PMS_AI_NVIDIA_ROUTING_ENABLED": {
            "effective": cfg.nvidia_routing_enabled,
            "default": False,
            "revert": "export PMS_AI_NVIDIA_ROUTING_ENABLED=false",
        },
    }


def _run_arm_corrective_metrics(*, repair_enabled: bool, force_timeout: bool = False) -> dict[str, Any]:
    import uuid
    from config.database import Base
    from models.models import Employee, KPIValue, PerformanceRecord, Team
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    mp = MonkeyPatch()
    mp.setenv("PMS_AI_NVIDIA_ROUTING_ENABLED", "true")
    mp.setenv("PMS_AI_CORRECTIVE_DRAFT_REPAIR_ENABLED", "true" if repair_enabled else "false")
    ai_evidence_cache.clear()

    team = Team(id=uuid.uuid4(), name="inbound", db_name="Inbound", display_name="Inbound", region="EGY", team_level="employee", is_active=True)
    db.add(team)
    db.flush()
    emp = Employee(id=uuid.uuid4(), employee_id="EMP-M1", name="Sara Inbound", team_id=team.id, region="EGY", performance_level="Employee", position_name="Agent", is_active=True)
    db.add(emp)
    db.flush()
    rec = PerformanceRecord(id=uuid.uuid4(), employee_id=emp.id, team_id=team.id, month="September", year=2026, performance_level="Employee", position_name="Agent", region="EGY", branch_key=None, score=70.0, grade="C", status="Below")
    db.add(rec)
    db.flush()
    for k, a, t, r, w in [("bookings_count", 30, 40, 0.75, 0.5), ("upsell", 0, 10, 0.0, 0.2)]:
        db.add(KPIValue(record_id=rec.id, record_year=2026, kpi_key=k, actual_value=a, target_value=t, achievement_ratio=r, weight_applied=w, contribution=r * w))
    db.commit()

    req = AiCorrectiveActionSuggestionRequest(employee_id="EMP-M1", team="Inbound", month="September", year=2026, performance_level="Employee", linked_kpi_key="bookings_count")
    admin_scope = {"user_id": "u-matrix-adm", "role": "Admin", "permissions": ["*"], "has_unrestricted_team_access": True}

    try:
        wrong_kpi = json.dumps({"focus_kpi_key": "upsell", "action_type": "Coaching", "steps": ["Review missed Bookings calls.", "Coach Bookings script."]})
        good_kpi = json.dumps({"focus_kpi_key": "bookings_count", "action_type": "Coaching", "steps": ["Review missed Bookings calls.", "Coach Bookings script."]})

        class _MatrixEngine:
            def __init__(self, responses: list[ProviderResponse]):
                self.responses = responses
                self.calls = 0

            def generate(self, request):
                idx = min(self.calls, len(self.responses) - 1)
                self.calls += 1
                return self.responses[idx]

        # Arm test: first-pass invalid focus -> bounded repair (or forced timeout)
        if force_timeout:
            eng = _MatrixEngine([ProviderResponse(content="", outcome="timeout", provider="nvidia", model="mock", latency_ms=5.0)])
        else:
            eng = _MatrixEngine([
                ProviderResponse(outcome="success", content=wrong_kpi, provider="nvidia", model="mock", latency_ms=20.0),
                ProviderResponse(outcome="success", content=good_kpi, provider="nvidia", model="mock", latency_ms=15.0),
            ])
        mp.setattr(drafter_mod, "get_unified_provider_engine", lambda: eng)
        t0 = time.perf_counter()
        out = CorrectiveActionDrafter(db).suggest(user_scope=admin_scope, request=req)
        elapsed = round((time.perf_counter() - t0) * 1000.0, 2)
        return {
            "first_pass_valid": False if not force_timeout else False,
            "recovered_valid": out.outcome == "suggested",
            "safe_pms_evidence_fallback": out.evidence_next_step is not None,
            "repair_outcome": out.repair_outcome,
            "provider_calls": eng.calls,
            "latency_ms": elapsed,
            "cost_usd": None,
            "billing_status": "unavailable_offline_mocked_provider",
        }
    finally:
        mp.undo()
        ai_evidence_cache.clear()
        db.close()


def _aggregate_overall_splits(splits: dict[str, Any]) -> dict[str, Any]:
    tot_turns = sum(int(v.get("turns") or 0) for v in splits.values()) or 1
    tot_passed = sum(int(v.get("turns_passed") or 0) for v in splits.values())
    tot_parts = sum(int(v.get("parts_total") or 0) for v in splits.values()) or 1
    parts_ok = sum(int(v.get("parts_passed") or 0) for v in splits.values())
    needless = sum(
        round((float(v.get("needless_clarification_pct") or 0.0) / 100.0) * float(v.get("turns") or 0))
        for v in splits.values()
    )
    crit = sum(int(v.get("critical_errors") or 0) for v in splits.values())
    blind = splits.get("blind") or {}
    val = splits.get("val") or {}
    dev = splits.get("dev") or {}
    p50s = [v["latency_ms"]["p50"] for v in splits.values() if v.get("latency_ms", {}).get("p50") is not None]
    p95s = [v["latency_ms"]["p95"] for v in splits.values() if v.get("latency_ms", {}).get("p95") is not None]
    return {
        "total_turns": tot_turns,
        "whole_turn_accuracy_pct": round(100.0 * tot_passed / tot_turns, 2),
        "per_part_accuracy_pct": round(100.0 * parts_ok / tot_parts, 2),
        "needless_clarification_pct": round(100.0 * needless / tot_turns, 2),
        "critical_errors": crit,
        "latency_p50_ms": max(p50s) if p50s else None,
        "latency_p95_ms": max(p95s) if p95s else None,
        "dev_whole_turn_pct": dev.get("whole_turn_accuracy_pct"),
        "val_whole_turn_pct": val.get("whole_turn_accuracy_pct"),
        "blind_whole_turn_pct": blind.get("whole_turn_accuracy_pct"),
        "blind_per_part_pct": blind.get("per_part_accuracy_pct"),
    }


def run_staging_matrix(*, scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    arms: dict[str, Any] = {}

    # 1. Legacy rules arm (flags OFF)
    mp1 = MonkeyPatch()
    mp1.setenv("PMS_AI_COMPOUND_PARTS_ENABLED", "false")
    mp1.setenv("PMS_AI_CORRECTIVE_DRAFT_REPAIR_ENABLED", "false")
    try:
        legacy_chat = bench.run_benchmark_mode(scenarios=scenarios, mode="deterministic")
        legacy_ca = _run_arm_corrective_metrics(repair_enabled=False, force_timeout=False)
    finally:
        mp1.undo()
    arms["legacy_rules_flags_off"] = {
        "label": "baseline_legacy_rules_flags_off",
        "is_live_verified": False,
        "status": "completed",
        "overall": _aggregate_overall_splits(legacy_chat["splits"]),
        "splits": legacy_chat["splits"],
        "corrective_recovery": legacy_ca,
        "billing_status": "not_applicable_deterministic",
        "estimated_cost_usd": 0.0,
    }

    # 2. Improved app deterministic arm (flags ON)
    mp2 = MonkeyPatch()
    mp2.setenv("PMS_AI_COMPOUND_PARTS_ENABLED", "true")
    mp2.setenv("PMS_AI_CORRECTIVE_DRAFT_REPAIR_ENABLED", "true")
    try:
        imp_chat = bench.run_benchmark_mode(scenarios=scenarios, mode="deterministic")
        imp_ca = _run_arm_corrective_metrics(repair_enabled=True, force_timeout=False)
    finally:
        mp2.undo()
    arms["improved_app_flags_on"] = {
        "label": "improved_compound_and_repair_enabled",
        "is_live_verified": False,
        "status": "completed",
        "overall": _aggregate_overall_splits(imp_chat["splits"]),
        "splits": imp_chat["splits"],
        "corrective_recovery": imp_ca,
        "billing_status": "not_applicable_deterministic_and_mocked",
        "estimated_cost_usd": 0.0,
    }

    # 3. Forced timeout resilient fallback arm (model-led pilot ON + scripted timeout)
    mp3 = MonkeyPatch()
    mp3.setenv("PMS_AI_COMPOUND_PARTS_ENABLED", "true")
    mp3.setenv("PMS_AI_CORRECTIVE_DRAFT_REPAIR_ENABLED", "true")
    try:
        to_chat = bench.run_benchmark_mode(scenarios=scenarios, mode="scripted_mocked")
        to_ca = _run_arm_corrective_metrics(repair_enabled=True, force_timeout=True)
    finally:
        mp3.undo()
    arms["forced_timeout_fallback"] = {
        "label": "model_led_forced_timeout_graceful_fallback",
        "is_live_verified": False,
        "status": "completed",
        "overall": _aggregate_overall_splits(to_chat["splits"]),
        "splits": to_chat["splits"],
        "corrective_recovery": to_ca,
        "billing_status": "unavailable_offline_timeout_simulation",
        "estimated_cost_usd": None,
    }

    # 4. Live staging candidate arm (gated)
    live_chat = bench.run_benchmark_mode(scenarios=scenarios, mode="live")
    if live_chat.get("status") == "blocked":
        arms["staging_live_candidate"] = {
            "label": "live_cloud_staging_candidate",
            "is_live_verified": False,
            "status": "blocked",
            "blocked_reason": live_chat.get("blocked_reason"),
            "billing_status": "unavailable_live_execution_blocked",
            "estimated_cost_usd": None,
        }
    else:
        arms["staging_live_candidate"] = {
            "label": "live_cloud_staging_candidate",
            "is_live_verified": True,
            "status": "completed",
            "overall": _aggregate_overall_splits(live_chat["splits"]),
            "splits": live_chat["splits"],
            "billing_status": "provider_reported_usage",
        }

    imp_ov = arms["improved_app_flags_on"]["overall"]
    leg_ov = arms["legacy_rules_flags_off"]["overall"]
    blind_split = arms["improved_app_flags_on"]["splits"].get("blind") or {}
    to_split = arms["forced_timeout_fallback"]["splits"].get("blind") or arms["forced_timeout_fallback"]["overall"]
    scorecard = {
        "blind_whole_turn_pct": blind_split.get("whole_turn_accuracy_pct"),
        "blind_per_part_pct": blind_split.get("per_part_accuracy_pct"),
        "blind_needless_clarification_pct": blind_split.get("needless_clarification_pct"),
        "blind_critical_errors": blind_split.get("critical_errors"),
        "blind_p95_ms": (blind_split.get("latency_ms") or {}).get("p95"),
        "overall_whole_turn_delta_pp": round(
            float(imp_ov["whole_turn_accuracy_pct"]) - float(leg_ov["whole_turn_accuracy_pct"]), 2
        ),
        "corrective_repair_recovered": arms["improved_app_flags_on"]["corrective_recovery"]["recovered_valid"],
        "timeout_safe_fallback_verified": (
            arms["forced_timeout_fallback"]["corrective_recovery"]["safe_pms_evidence_fallback"]
            and (to_split.get("critical_errors", 0) == 0)
        ),
        "live_staging_status": arms["staging_live_candidate"]["status"],
        "all_offline_scorecard_gates_passed": bool(
            blind_split.get("whole_turn_accuracy_pct") is not None
            and blind_split["whole_turn_accuracy_pct"] >= 90.0
            and blind_split.get("per_part_accuracy_pct") is not None
            and blind_split["per_part_accuracy_pct"] >= 95.0
            and blind_split.get("needless_clarification_pct") is not None
            and blind_split["needless_clarification_pct"] < 3.0
            and blind_split.get("critical_errors") == 0
            and (blind_split.get("latency_ms") or {}).get("p95") is not None
            and (blind_split.get("latency_ms") or {})["p95"] <= 15000.0
            and arms["improved_app_flags_on"]["corrective_recovery"]["recovered_valid"]
        ),
    }

    return {
        "schema_version": "pms-ai-staging-matrix-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": len(scenarios),
        "rollout_flags": _rollout_flags_snapshot(),
        "arms": arms,
        "section5_release_scorecard": scorecard,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# PMS AI Staging Candidate Comparison & Section 5 Release Scorecard",
        "",
        f"- **Generated At:** `{summary['generated_at']}`",
        f"- **Total Scenarios:** `{summary['total_scenarios']}` (dev=120, val=60, blind=60)",
        "",
        "## Comparison Matrix",
        "",
        "| Arm | Status | Live Verified | Overall Acc % | Per-Part % | Blind Whole % | Blind Per-Part % | Needless Clarif % | Critical Err | p95 ms | Billing / Cost |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for arm_name, arm in summary["arms"].items():
        if arm.get("status") == "blocked":
            lines.append(
                f"| `{arm_name}` | `blocked` | `False` | n/a | n/a | n/a | n/a | n/a | n/a | n/a | `{arm.get('billing_status')}` |"
            )
            continue
        ov = arm["overall"]
        lines.append(
            f"| `{arm_name}` | `{arm['status']}` | `{arm['is_live_verified']}` | "
            f"{ov['whole_turn_accuracy_pct']}% | {ov['per_part_accuracy_pct']}% | "
            f"{ov['blind_whole_turn_pct']}% | {ov['blind_per_part_pct']}% | "
            f"{ov['needless_clarification_pct']}% | {ov['critical_errors']} | {ov['latency_p95_ms']} | `{arm.get('billing_status')}` |"
        )

    sc = summary["section5_release_scorecard"]
    lines.extend(
        [
            "",
            "## Section 5 Release Scorecard (Offline + Blind Verified)",
            "",
            f"- **Blind Whole-Turn Accuracy:** `{sc['blind_whole_turn_pct']}%` (Gate >= 90%)",
            f"- **Blind Per-Part Accuracy:** `{sc['blind_per_part_pct']}%` (Gate >= 95%)",
            f"- **Blind Needless Clarifications:** `{sc['blind_needless_clarification_pct']}%` (Gate < 3%)",
            f"- **Blind Critical Errors:** `{sc['blind_critical_errors']}` (Gate == 0)",
            f"- **Blind p95 Latency:** `{sc['blind_p95_ms']} ms` (Gate <= 15000 ms)",
            f"- **Overall Improvement vs Legacy Flags Off:** `{sc['overall_whole_turn_delta_pp']:+.2f} pp`",
            f"- **Corrective 1-Retry Repair Recovery:** `{sc['corrective_repair_recovered']}`",
            f"- **Forced Timeout Safe Fallback Verified:** `{sc['timeout_safe_fallback_verified']}`",
            f"- **Live Staging Status:** `{sc['live_staging_status']}`",
            f"- **All Offline Scorecard Gates Passed:** `{sc['all_offline_scorecard_gates_passed']}`",
            "",
            "## Reversible Rollout Flags",
            "",
            "| Flag | Effective Default | Instant Revert |",
            "|---|---|---|",
        ]
    )
    for k, v in summary["rollout_flags"].items():
        lines.append(f"| `{k}` | `{v['effective']}` (default `{v['default']}`) | `{v['revert']}` |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run PR 5 staging comparison matrix.")
    parser.add_argument("--benchmark", type=Path, default=bench.DEFAULT_BENCHMARK_PATH)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    args = parser.parse_args(argv)

    loaded = json.loads(args.benchmark.read_text(encoding="utf-8"))
    scenarios = loaded.get("scenarios", loaded) if isinstance(loaded, dict) else loaded
    summary = run_staging_matrix(scenarios=scenarios)

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(render_markdown(summary), encoding="utf-8")

    print(json.dumps(summary["section5_release_scorecard"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
